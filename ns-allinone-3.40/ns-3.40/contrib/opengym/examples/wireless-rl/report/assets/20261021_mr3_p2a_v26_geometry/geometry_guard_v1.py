"""One bounded read-only geometry consumer; the independent outer owns fees."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[9]
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
W = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
CONSUMER_MODULE = "multi_robot_exploration.mr3_proxy2d_quality_geometry"


def identity(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"pid": pid, "parent": int(fields[1]), "group": int(fields[2]),
            "session": int(fields[3]), "start_ticks": int(fields[19]), "state": fields[0]}


def sources(paths):
    result = []
    for path in paths:
        raw, stat = path.read_bytes(), path.stat()
        result.append({"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest(),
                       "bytes": len(raw), "stat": [stat.st_dev, stat.st_ino, stat.st_size,
                                                    stat.st_mtime_ns, stat.st_ctime_ns]})
    return result


def system_environment():
    removed = {"PYTHONPATH", "LD_LIBRARY_PATH", "AMENT_PREFIX_PATH", "CMAKE_PREFIX_PATH",
               "COLCON_PREFIX_PATH", "ROS_PACKAGE_PATH", "PYTHONHOME", "VIRTUAL_ENV",
               "GAZEBO_PLUGIN_PATH", "GAZEBO_MODEL_PATH", "GAZEBO_RESOURCE_PATH"}
    result = {key: value for key, value in os.environ.items()
              if key not in removed and not key.startswith("CONDA")}
    result.update(PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                  PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="",
                  OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
    return result


def write(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, indent=2, allow_nan=False) + "\n")


def stop_and_wait(child, errors, signals):
    """The unreaped Popen handle owns the new session even if /proc failed."""
    def send(number):
        try:
            os.killpg(child.pid, number)
            signals.append(signal.Signals(number).name)
        except ProcessLookupError:
            pass
        except OSError as error:
            errors.append("group signal: " + repr(error))
            try:
                child.send_signal(number)
            except ProcessLookupError:
                pass
            except OSError as direct_error:
                errors.append("direct signal: " + repr(direct_error))

    send(signal.SIGTERM)
    try:
        return child.wait(timeout=10.)
    except subprocess.TimeoutExpired:
        send(signal.SIGKILL)
    try:
        return child.wait(timeout=5.)
    except subprocess.TimeoutExpired:
        errors.append("owned child exceeded 5-second KILL reap allowance")
        # Never claim a wait or abandon a live child to preserve the ceiling.
        # The independent engineering outer charges any OS-level overrun.
        return child.wait()


def run(freeze, output, source_paths):
    if not re.fullmatch(r"[0-9a-f]{40}", freeze):
        raise ValueError("explicit full lowercase 40-hex freeze required")
    if not source_paths:
        raise ValueError("explicit nonempty complete source list required")
    output = output.resolve()
    if output == Path("/tmp") or not output.is_relative_to(Path("/tmp")):
        raise ValueError("guard output must be one new directory below /tmp")
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic_ns()
    child = None
    before, after, saved, owner, errors, signals = [], [], None, None, [], []
    rc, waited, timed_out = None, False, False
    child_started, child_ended = None, None
    result_path, console_path = output / "geometry_result.json", output / "consumer.log"
    argv = ["/usr/bin/bash", "--noprofile", "--norc", "-c",
            'source /opt/ros/humble/setup.bash && source "$1/install/setup.bash" '
            '&& exec /usr/bin/python3 -B -m "$2" --freeze "$3" --output "$4"',
            "mr3-geometry", str(ROS), CONSUMER_MODULE, freeze, str(result_path)]
    with console_path.open("xb") as console:
        try:
            owner = identity(os.getpid())
            write(output / "guard_identity.json", owner)
            before = sources(source_paths)
            child_started = time.monotonic_ns()
            child = subprocess.Popen(argv, cwd=ROS, env=system_environment(), stdout=console,
                                     stderr=subprocess.STDOUT, start_new_session=True)
            saved = identity(child.pid)
            if saved["group"] != child.pid or saved["session"] != child.pid:
                raise RuntimeError("consumer did not enter its owned session")
            write(output / "child_identity.json", saved)
            try:
                rc = child.wait(timeout=90.)
            except subprocess.TimeoutExpired:
                timed_out = True
                rc = stop_and_wait(child, errors, signals)
            waited = True
            child_ended = time.monotonic_ns()
        except BaseException as error:
            errors.append(repr(error))
            if child is not None and not waited:
                rc = stop_and_wait(child, errors, signals)
                waited = True
                child_ended = time.monotonic_ns()
    try:
        after = sources(source_paths)
    except (OSError, ValueError) as error:
        errors.append("source after: " + repr(error))
    if not result_path.is_file():
        errors.append("consumer result missing")
    ended = time.monotonic_ns()
    receipt = {"schema": "mr3-p2a-geometry-guard-v1", "freeze": freeze,
               "actual_argv": argv, "cwd": str(ROS), "guard_identity": owner,
               "child_identity": saved, "actual_returncode": rc, "actual_waited": waited,
               "started_monotonic_ns": started, "ended_monotonic_ns": ended,
               "actual_guard_seconds": str(Decimal(ended - started) / Decimal(10**9)),
               "child_started_monotonic_ns": child_started,
               "child_ended_monotonic_ns": child_ended,
               "actual_child_wait_seconds": (None if child_ended is None else
                   str(Decimal(child_ended - child_started) / Decimal(10**9))),
               "consumer_work_ceiling_seconds": 90, "term_grace_seconds": 10,
               "kill_reap_allowance_seconds": 5,
               "timed_out": timed_out, "signals_sent": signals, "errors": errors,
               "source_before": before, "source_after": after,
               "source_unchanged": bool(before) and before == after,
               "console": {"path": str(console_path),
                           "sha256": hashlib.sha256(console_path.read_bytes()).hexdigest()},
               "result_path": str(result_path), "qualification": False,
               "training_eligible": False, "native_credit": False}
    receipt["passed"] = (rc == 0 and waited and not timed_out and not errors
                         and receipt["source_unchanged"])
    write(output / "guard_receipt_v1.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, action="append", required=True)
    args = parser.parse_args()
    def terminate(number, frame):
        raise RuntimeError(f"guard received signal {number}")
    signal.signal(signal.SIGTERM, terminate)
    result = run(args.freeze, args.output, args.source)
    print(json.dumps({key: result[key] for key in ("passed", "actual_returncode", "actual_guard_seconds")}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
