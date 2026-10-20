#!/usr/bin/env python3
"""Seal an explicitly selected closed run and auxiliary originals, including FAIL.

Archival byte verification only: no simulator, audit replay or qualification.
Existing outputs and partial outputs are preserved and never overwritten.
"""

import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path
import shutil
import stat
import subprocess
import tarfile
import time


PART_BYTES = 32 * 1024 * 1024
STAT_FIELDS = ("st_dev", "st_ino", "st_mode", "st_size", "st_mtime_ns", "st_ctime_ns")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def stream_digest(stream):
    result = hashlib.sha256()
    while block := stream.read(1024 * 1024):
        result.update(block)
    return result.hexdigest()


def digest(path):
    with Path(path).open("rb") as stream:
        return stream_digest(stream)


def file_record(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "source is not a regular file: " + str(path))
    value = digest(path)
    after = path.lstat()
    require(all(getattr(before, field) == getattr(after, field) for field in STAT_FIELDS),
            "source changed while hashing: " + str(path))
    return {"sha256": value, "bytes": after.st_size,
            "stat": {field: getattr(after, field) for field in STAT_FIELDS}}


def inventory(root):
    require(stat.S_ISDIR(root.lstat().st_mode), "source is not a real directory: " + str(root))
    files, directories = {}, []
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        relative = path.relative_to(root).as_posix()
        if stat.S_ISDIR(mode):
            directories.append(relative)
        else:
            # This also rejects links, sockets, devices and FIFOs.
            files[relative] = file_record(path)
    return {"files": files, "directories": directories}


def write(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


class Parts(io.RawIOBase):
    def __init__(self, paths):
        super().__init__()
        self.paths, self.current = iter(paths), None

    def readable(self):
        return True

    def readinto(self, buffer):
        while True:
            if self.current is None:
                path = next(self.paths, None)
                if path is None:
                    return 0
                self.current = path.open("rb")
            count = self.current.readinto(buffer)
            if count:
                return count
            self.current.close()
            self.current = None

    def close(self):
        if self.current is not None:
            self.current.close()
        super().close()


def verify_members(paths, expected):
    seen, total = set(), 0
    with Parts(paths) as raw, io.BufferedReader(raw) as joined, lzma.LZMAFile(joined) as expanded:
        with tarfile.open(fileobj=expanded, mode="r|") as archive:
            for member in archive:
                if member.isdir():
                    continue
                name = member.name.removeprefix("./")
                require(member.isfile() and name in expected and name not in seen,
                        "unexpected/duplicate/nonregular archive member: " + member.name)
                with archive.extractfile(member) as stream:
                    value = stream_digest(stream)
                require(member.size == expected[name]["bytes"] and value == expected[name]["sha256"],
                        "archive member byte mismatch: " + name)
                seen.add(name)
                total += member.size
        # Consume final tar padding and the complete xz integrity footer.
        while expanded.read(1024 * 1024):
            pass
    require(seen == set(expected), "archive omitted a source file")
    return {"file_count": len(seen), "total_bytes": total}


def create_archive(run, output, part_bytes):
    tar_argv = ["tar", "--hard-dereference", "-c", "-C", str(run), "."]
    xz_argv = ["xz", "-T4", "-1", "--stdout"]
    commands = {"tar_argv": tar_argv, "xz_argv": xz_argv, "started_monotonic_ns": time.monotonic_ns()}
    tar = compressor = None
    parts, whole = [], hashlib.sha256()
    try:
        tar = subprocess.Popen(tar_argv, stdout=subprocess.PIPE)
        compressor = subprocess.Popen(xz_argv, stdin=tar.stdout, stdout=subprocess.PIPE)
        tar.stdout.close()
        while block := compressor.stdout.read(part_bytes):
            path = output / f"run.tar.xz.part{len(parts) + 1:04d}"
            with path.open("xb") as stream:
                stream.write(block)
            whole.update(block)
            parts.append({"path": path.name, "bytes": len(block), "sha256": hashlib.sha256(block).hexdigest()})
        compressor.stdout.close()
        commands.update(xz_returncode=compressor.wait(), tar_returncode=tar.wait())
        require(commands["xz_returncode"] == commands["tar_returncode"] == 0,
                "tar/xz failed: " + str(commands))
    finally:
        for child in (compressor, tar):
            if child is not None:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=10.)
                    except subprocess.TimeoutExpired:
                        child.kill()
                child.wait()
        for stream in (() if compressor is None else (compressor.stdout,)) + (() if tar is None else (tar.stdout,)):
            if stream is not None:
                stream.close()
        commands["ended_monotonic_ns"] = time.monotonic_ns()
        commands["actual_waited"] = True
    require(parts, "empty compressed archive")
    return parts, whole.hexdigest(), commands


def exact_copy(source, target, output, role):
    require(not target.exists() and not target.is_symlink(), "auxiliary output already exists: " + str(target))
    if source.is_dir() and not source.is_symlink():
        before = inventory(source)
        shutil.copytree(source, target, symlinks=True)
        after, copied = inventory(source), inventory(target)
        require(after == before and copied["directories"] == before["directories"]
                and copied["files"].keys() == before["files"].keys()
                and all(all(copied["files"][name][key] == record[key] for key in ("sha256", "bytes"))
                        for name, record in before["files"].items()), "auxiliary tree changed/copied incorrectly: " + str(source))
        files = [{"original": str(source / name), "copy": (target / name).relative_to(output).as_posix(),
                  "sha256": record["sha256"], "bytes": record["bytes"], "role": role}
                 for name, record in before["files"].items()]
    else:
        before = file_record(source)
        shutil.copy2(source, target, follow_symlinks=False)
        copied = file_record(target)
        require(file_record(source) == before and all(copied[key] == before[key] for key in ("sha256", "bytes")),
                "auxiliary file changed/copied incorrectly: " + str(source))
        files = [{"original": str(source), "copy": target.relative_to(output).as_posix(),
                  "sha256": before["sha256"], "bytes": before["bytes"], "role": role}]
    return files, before


def seal(run, output, outer, copies=(), *, part_bytes=PART_BYTES):
    """Explicit archival operation; smaller part_bytes is for tiny CPU fixtures."""
    require(not Path(run).is_symlink(), "run root cannot be a symlink")
    require(not Path(output).is_symlink(), "output root cannot be a symlink")
    run, output = Path(run).resolve(), Path(output).resolve()
    require(not output.is_relative_to(run), "outputs must be outside archived originals")
    require(type(part_bytes) is int and part_bytes > 0, "invalid archive part length")
    require(outer, "at least one explicit outer receipt/tree is required")
    selections = [("outer", Path(path)) for path in outer] + [("copy", Path(path)) for path in copies]
    require(all(not path.is_symlink() for _, path in selections), "auxiliary root cannot be a symlink")
    selections = [(role, path.resolve()) for role, path in selections]
    require(len({path for _, path in selections}) == len(selections), "auxiliary source selected twice")
    require(len({path.name for _, path in selections}) == len(selections), "auxiliary destination basename collision")
    require(all(not output.is_relative_to(path) for _, path in selections if path.is_dir()),
            "auxiliary source contains its own destination")
    output.mkdir(parents=True, exist_ok=True)
    reserved = ("run_inventory_v1.json", "archive_verification_v1.json", "auxiliary_copy_index_v1.json",
                "archive_manifest_v1.json", "seal_failure_v1.json", "closed_execution")
    require(not any((output / name).exists() or (output / name).is_symlink() for name in reserved)
            and not list(output.glob("run.tar.xz.part*")), "seal outputs already exist; preserve original/partial outputs")
    started = time.monotonic_ns()
    try:
        before = inventory(run)
        write(output / "run_inventory_v1.json", {"schema": "mr3-closed-byte-inventory-v1", "original_root": str(run),
            **before, "file_count": len(before["files"]), "total_bytes": sum(row["bytes"] for row in before["files"].values())})
        parts, archive_sha, commands = create_archive(run, output, part_bytes)
        verified = verify_members([output / row["path"] for row in parts], before["files"])
        require(inventory(run) == before, "run originals changed after archive verification")
        auxiliary = output / "closed_execution/aux"
        auxiliary.mkdir(parents=True)
        copied, auxiliary_sources = [], []
        for role, source in selections:
            files, source_before = exact_copy(source, auxiliary / source.name, output, role)
            copied.extend(files)
            auxiliary_sources.append((source, source_before))
        # Recheck every selected original at the final verdict, not only just
        # after its own copy, so later archival work cannot hide a source change.
        require(inventory(run) == before, "run originals changed during auxiliary copying")
        for source, source_before in auxiliary_sources:
            require((inventory(source) if source.is_dir() else file_record(source)) == source_before,
                    "auxiliary originals changed before verdict: " + str(source))
        for row in copied:
            target = file_record(output / row["copy"])
            require(all(target[key] == row[key] for key in ("sha256", "bytes")), "auxiliary copy changed before verdict")
        for row in parts:
            require((output / row["path"]).stat().st_size == row["bytes"] and digest(output / row["path"]) == row["sha256"],
                    "archive part changed before verdict")
        write(output / "auxiliary_copy_index_v1.json", {"schema": "mr3-exact-copy-index-v1", "files": copied,
            "sources": [{"path": str(source), "role": role} for role, source in selections]})
        result = {"schema": "mr3-closed-archive-verification-v1", "byte_verification_passed": True,
            "scope": "archival CPU verification only; original PASS/FAIL unchanged; no experiment or audit replay",
            "qualification": False, "training_eligible": False, "native_credit": False,
            "original_run": str(run), "run_originals_unchanged": True, "auxiliary_originals_unchanged": True,
            "all_member_bytes_verified": True, "all_auxiliary_copy_bytes_verified": True,
            "archive_sha256": archive_sha, "part_bytes": part_bytes, "parts": parts,
            "run_file_count": verified["file_count"], "run_total_bytes": verified["total_bytes"],
            "auxiliary_file_count": len(copied), "archive_commands": commands,
            "started_monotonic_ns": started, "ended_monotonic_ns": time.monotonic_ns()}
        write(output / "archive_verification_v1.json", result)
        references = [{"path": name, "bytes": (output / name).stat().st_size, "sha256": digest(output / name)}
                      for name in ("run_inventory_v1.json", "auxiliary_copy_index_v1.json", "archive_verification_v1.json")]
        write(output / "archive_manifest_v1.json", {"schema": "mr3-closed-archive-manifest-v1", "original_run": str(run),
            "archive_sha256": archive_sha, "parts": parts, "metadata": references,
            "byte_verification_passed": True, "qualification": False, "training_eligible": False, "native_credit": False})
        return result
    except BaseException as error:
        write(output / "seal_failure_v1.json", {"schema": "mr3-closed-archive-failure-v1", "error": repr(error),
            "started_monotonic_ns": started, "ended_monotonic_ns": time.monotonic_ns(),
            "original_run": str(run), "scope": "partial archive preserved; no successful seal declared",
            "qualification": False, "training_eligible": False, "native_credit": False})
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--outer", required=True, action="append", type=Path)
    parser.add_argument("--copy", default=[], action="append", type=Path)
    parser.add_argument("--output", default=Path(__file__).resolve().parent, type=Path)
    args = parser.parse_args(argv)
    result = seal(args.run, args.output, args.outer, args.copy)
    print(json.dumps({key: result[key] for key in ("byte_verification_passed", "run_file_count", "auxiliary_file_count")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
