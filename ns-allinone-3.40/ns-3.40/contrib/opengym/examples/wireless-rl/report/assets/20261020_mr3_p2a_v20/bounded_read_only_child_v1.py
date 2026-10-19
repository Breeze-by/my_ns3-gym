#!/usr/bin/python3
"""Wait for one owned read-only consumer, with an automatic SIGINT deadline.

The caller charges the real outer wait once. This helper makes no scientific
claim and never signals a process group. Cleanup time remains part of the fee.
"""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def identity(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"pid": pid, "parent": int(fields[1]), "start_ticks": int(fields[19]),
            "state": fields[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wall-seconds", type=int, required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    assert command and 1 <= args.wall_seconds <= 900
    args.output.mkdir(parents=True, exist_ok=False)
    signals = []
    started = time.monotonic_ns()
    with (args.output / "consumer.log").open("x") as console:
        child = subprocess.Popen(command, stdout=console, stderr=subprocess.STDOUT)
        saved = identity(child.pid)
        assert saved["parent"] == os.getpid()
        pidfd = os.pidfd_open(child.pid)
        timed_out = False

        def interrupt(sig):
            now = identity(child.pid)
            assert now["start_ticks"] == saved["start_ticks"] and now["parent"] == os.getpid()
            signal.pidfd_send_signal(pidfd, sig)
            signals.append({"signal": sig.name, "monotonic_ns": time.monotonic_ns(),
                            "verified_identity": now})

        try:
            remaining = max(0, args.wall_seconds - (time.monotonic_ns() - started) / 1e9)
            try:
                rc = child.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                timed_out = True
                interrupt(signal.SIGINT)
                try:
                    rc = child.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    interrupt(signal.SIGKILL)
                    rc = child.wait()
        finally:
            os.close(pidfd)
    ended = time.monotonic_ns()
    result = {"schema": "mr3-v20-bounded-owned-read-only-child-wait-v1",
              "actual_argv": command, "cwd": str(Path.cwd()),
              "coordinator_identity": identity(os.getpid()), "child_identity": saved,
              "started_monotonic_ns": started, "ended_monotonic_ns": ended,
              "actual_child_wait_seconds": str(Decimal(ended - started) / Decimal(10**9)),
              "supervised_wall_allocation_seconds": args.wall_seconds,
              "timed_out": timed_out, "signals_sent": signals,
              "actual_returncode": rc, "actual_waited": True,
              "passed": rc == 0 and not timed_out,
              "scientific_qualification": False, "native_runs": 0, "gpu_calls": 0}
    with (args.output / "actual_wait.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("actual_returncode", "timed_out", "passed",
                                           "actual_child_wait_seconds")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
