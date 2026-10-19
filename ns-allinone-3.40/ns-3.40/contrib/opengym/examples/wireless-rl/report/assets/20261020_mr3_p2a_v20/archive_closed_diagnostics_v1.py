#!/usr/bin/python3
"""Copy closed diagnostic originals and verify every byte; never run a reader."""
import hashlib
import json
from pathlib import Path
import shutil
import stat
import time


def fingerprint(path):
    before = path.stat()
    assert stat.S_ISREG(before.st_mode) and not path.is_symlink(), path
    data = path.read_bytes()
    after = path.stat()
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
    assert identity(before) == identity(after), path
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "stat": identity(after)}


def main():
    asset = Path(__file__).resolve().parent
    destination = asset / "closed_diagnostics_v1"
    destination.mkdir(exist_ok=False)
    roots = {
        "kernel_output": "/tmp/mr3_p2a_v19_runtime_kernel_profile_v1",
        "kernel_outer": "/tmp/mr3_p2a_v19_runtime_kernel_profile_wait_v1",
        "profile_v1": "/tmp/mr3_p2a_v20_runtime_bounded_profile_v1",
        "profile_v1_outer": "/tmp/mr3_p2a_v20_runtime_bounded_profile_wait_v1",
        "profile_v2": "/tmp/mr3_p2a_v20_runtime_core_profile_v2",
        "profile_v2_outer": "/tmp/mr3_p2a_v20_runtime_bounded_profile_wait_v2",
        "information_outer": "/tmp/mr3_p2a_v20_v19_information_regression_wait_v1",
        "information_interrupt": "/tmp/mr3_p2a_v20_information_regression_interrupt_v1",
    }
    jobs = []
    inventories = {}
    for name, raw in roots.items():
        source = Path(raw)
        files = sorted(p for p in source.rglob("*") if not p.is_dir())
        inventories[raw] = [str(p.relative_to(source)) for p in files]
        jobs.extend((p, destination / name / p.relative_to(source)) for p in files)
    jobs.append((Path("/tmp/mr3_v19_runtime_kernel_profile_draft.py"),
                 destination / "kernel_helper.py"))
    receipt = json.loads(Path(roots["information_outer"], "actual_wait.json").read_text())
    assert receipt["actual_waited"] and receipt["source_unchanged"]
    assert receipt["actual_returncode"] == -2
    for item in receipt["source_before"]:
        path = Path(item["path"])
        assert fingerprint(path)["sha256"] == item["sha256"], path
        jobs.append((path, destination / "information_sources" / path.name))
    entries = []
    before = {str(source): fingerprint(source) for source, _ in jobs}
    for source, target in jobs:
        target.parent.mkdir(parents=True, exist_ok=True)
        assert not target.exists(), target
        shutil.copyfile(source, target)
        actual = fingerprint(target)
        assert all(actual[k] == before[str(source)][k] for k in ("bytes", "sha256"))
        entries.append({"original": str(source), "copy": str(target.relative_to(asset)),
                        **before[str(source)]})
    for source, _ in jobs:
        assert fingerprint(source) == before[str(source)], source
    for raw, expected in inventories.items():
        source = Path(raw)
        assert sorted(str(p.relative_to(source)) for p in source.rglob("*")
                      if not p.is_dir()) == expected
    result = {"schema": "mr3-v20-closed-diagnostics-copy-index-v1", "passed": True,
              "copied_files": len(entries), "copied_bytes": sum(e["bytes"] for e in entries),
              "source_before_after_equal": True, "entries": entries,
              "completed_monotonic_ns": time.monotonic_ns()}
    with (destination / "copy_index_v1.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: v for k, v in result.items() if k != "entries"}))


if __name__ == "__main__":
    main()
