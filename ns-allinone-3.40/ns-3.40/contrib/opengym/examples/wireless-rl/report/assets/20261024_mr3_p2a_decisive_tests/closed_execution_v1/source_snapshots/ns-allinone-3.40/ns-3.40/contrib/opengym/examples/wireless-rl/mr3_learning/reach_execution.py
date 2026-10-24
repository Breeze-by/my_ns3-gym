"""Exclusive actual-wait receipt for finite declared CPU or native work."""

import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from .preparation import identity


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--scope", required=True, choices=("cpu", "engineering", "pilot", "validation"))
    parser.add_argument("--source", action="append", required=True, type=Path)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("missing actual command")
    args.output.mkdir(parents=True, exist_ok=False)

    def sources():
        rows = []
        for path in args.source:
            raw, s = path.read_bytes(), path.stat()
            rows.append({"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
                         "bytes": len(raw), "stat": [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]})
        return rows

    before = sources()
    env = dict(os.environ, PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1")
    env.pop("PYTHONPATH", None)
    started = time.monotonic_ns()
    errors, returncode, child_identity = [], None, None
    with (args.output / "console.log").open("x") as console:
        try:
            child = subprocess.Popen(command, env=env, stdout=console, stderr=subprocess.STDOUT)
            child_identity = identity(child.pid)
            while True:
                try:
                    returncode = child.wait()
                    break
                except BaseException as error:
                    errors.append(repr(error))
        except OSError as error:
            errors.append(repr(error))
    ended = time.monotonic_ns()
    after = sources()
    receipt = {"schema": "mr3-reach-outer-actual-wait-v1", "scope": args.scope,
        "safety_contract": "mr3-reach-v1", "actual_argv": command,
        "cwd": str(Path.cwd()), "coordinator_identity": identity(os.getpid()),
        "child_identity": child_identity, "actual_returncode": returncode,
        "actual_waited": returncode is not None, "errors": errors,
        "started_monotonic_ns": started, "ended_monotonic_ns": ended,
        "actual_child_wait_seconds": str(Decimal(ended - started) / 10**9),
        "source_before": before, "source_after": after, "source_unchanged": before == after,
        "passed": returncode == 0 and not errors and before == after,
        "console": {"path": str((args.output / "console.log").resolve()),
                    "sha256": hashlib.sha256((args.output / "console.log").read_bytes()).hexdigest()}}
    with (args.output / "actual_wait.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({k: receipt[k] for k in ("passed", "actual_returncode", "actual_child_wait_seconds")}))
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
