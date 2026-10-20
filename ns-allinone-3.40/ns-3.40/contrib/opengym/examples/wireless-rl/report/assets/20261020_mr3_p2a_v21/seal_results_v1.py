#!/usr/bin/env python3
"""Seal the already closed V21 originals; no simulator, audit rerun or credit."""
import hashlib
import io
import json
import lzma
from pathlib import Path
import shutil
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[9]
DEST = Path(__file__).resolve().parent
RUN = ROOT / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_v21_diagnostic/uniform_two_episodes"
PART_BYTES = 32 * 1024 * 1024


def digest(path):
    with path.open("rb") as stream:
        return stream_digest(stream)


def stream_digest(stream):
    sha = hashlib.sha256()
    while True:
        block = stream.read(1024 * 1024)
        if not block:
            return sha.hexdigest()
        sha.update(block)


def inventory(root):
    records = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"unexpected symlink: {path}")
        if path.is_dir():
            continue
        before = path.stat()
        sha = digest(path)
        after = path.stat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, k) != getattr(after, k) for k in fields):
            raise ValueError(f"source changed during hashing: {path}")
        records[path.relative_to(root).as_posix()] = {
            "bytes": after.st_size, "sha256": sha,
            "stat": {k: getattr(after, k) for k in fields},
        }
    return records


def write(name, value):
    (DEST / name).write_text(json.dumps(value, indent=2) + "\n")


class Parts(io.RawIOBase):
    def __init__(self, paths):
        super().__init__()
        self.paths = iter(paths)
        self.current = None

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


def main():
    if list(DEST.glob("native.tar.xz.part*")):
        raise ValueError("archive already exists; refuse overwrite")
    before = inventory(RUN)
    write("native_inventory_v1.json", {"schema": "mr3-closed-byte-inventory-v1",
          "original_root": str(RUN), "files": before,
          "file_count": len(before), "total_bytes": sum(v["bytes"] for v in before.values())})
    print(f"inventoried {len(before)} native files", flush=True)
    tar = subprocess.Popen(["tar", "-c", "-C", str(RUN), "."], stdout=subprocess.PIPE)
    compressor = subprocess.Popen(["xz", "-T4", "-1", "--stdout"], stdin=tar.stdout,
                                  stdout=subprocess.PIPE)
    tar.stdout.close()
    parts, whole = [], hashlib.sha256()
    while True:
        data = compressor.stdout.read(PART_BYTES)
        if not data:
            break
        path = DEST / f"native.tar.xz.part{len(parts) + 1:04d}"
        path.write_bytes(data)
        whole.update(data)
        parts.append(path)
        print(f"sealed {path.name}: {len(data)} bytes", flush=True)
    compressor.stdout.close()
    compressor_rc, tar_rc = compressor.wait(), tar.wait()
    if compressor_rc or tar_rc:
        raise ValueError(f"archive command failed: tar={tar_rc}, xz={compressor_rc}")
    seen = set()
    with Parts(parts) as raw, io.BufferedReader(raw) as joined, lzma.LZMAFile(joined) as expanded:
        with tarfile.open(fileobj=expanded, mode="r|") as archive:
            for member in archive:
                if member.isdir():
                    continue
                name = member.name.removeprefix("./")
                if not member.isfile() or name not in before or name in seen:
                    raise ValueError(f"unexpected archive member: {member.name}")
                with archive.extractfile(member) as source:
                    sha = stream_digest(source)
                if member.size != before[name]["bytes"] or sha != before[name]["sha256"]:
                    raise ValueError(f"member byte mismatch: {name}")
                seen.add(name)
        # Consume through the xz integrity check, including the final tar padding.
        while expanded.read(1024 * 1024):
            pass
    if seen != set(before) or inventory(RUN) != before:
        raise ValueError("native originals changed or archive incomplete")
    auxiliary = DEST / "closed_execution"
    auxiliary.mkdir()
    copied = []
    names = ("mr3_p2a_v21_diagnostic", "mr3_p2a_v21_diagnostic_outer",
             "mr3_p2a_v21_diagnostic_final_outer", "mr3_p2a_v21_diagnostic_preflight_outer")
    for name in names:
        source = Path("/tmp") / name
        source_before = inventory(source)
        shutil.copytree(source, auxiliary / name)
        copied.extend({"original": str(source / rel),
                       "copy": str((auxiliary / name / rel).relative_to(DEST)),
                       "bytes": entry["bytes"], "sha256": entry["sha256"]}
                      for rel, entry in source_before.items())
        target = inventory(auxiliary / name)
        if inventory(source) != source_before or any(
            target[k]["bytes"] != v["bytes"] or target[k]["sha256"] != v["sha256"]
            for k, v in source_before.items()
        ) or set(target) != set(source_before):
            raise ValueError(f"auxiliary changed during copy: {source}")
    for name in ("mr3_p2a_v21_diagnostic_preflight.json", "mr3_p2a_v21_diagnostic_absence.json"):
        source = Path("/tmp") / name
        sha = digest(source)
        target = auxiliary / name
        shutil.copy2(source, target)
        if digest(source) != sha or digest(target) != sha:
            raise ValueError(f"auxiliary changed: {source}")
        copied.append({"original": str(source), "copy": str(target.relative_to(DEST)),
                       "bytes": target.stat().st_size, "sha256": sha})
    write("auxiliary_copy_index_v1.json", {"schema": "mr3-exact-copy-index-v1", "files": copied})
    write("archive_verification_v1.json", {
        "schema": "mr3-closed-archive-verification-v1", "byte_verification_passed": True,
        "scope": "archival CPU work only; original diagnostic FAIL unchanged",
        "qualification": False, "training_eligible": False,
        "tar_returncode": tar_rc, "xz_returncode": compressor_rc,
        "archive_sha256": whole.hexdigest(), "native_file_count": len(seen),
        "native_originals_unchanged": True, "all_member_bytes_verified": True,
        "parts": [{"path": p.name, "bytes": p.stat().st_size, "sha256": digest(p)} for p in parts],
        "auxiliary_file_count": len(copied),
    })
    print("all native archive members and exact auxiliary copies verified", flush=True)


if __name__ == "__main__":
    main()
