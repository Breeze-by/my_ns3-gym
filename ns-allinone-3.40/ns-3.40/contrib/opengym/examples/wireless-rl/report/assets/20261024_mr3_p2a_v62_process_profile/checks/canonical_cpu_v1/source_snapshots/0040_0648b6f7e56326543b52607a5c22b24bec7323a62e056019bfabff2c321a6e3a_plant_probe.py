"""One declared from-rest plant contrast arm; no policy or optimizer imports."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from .supervisor import ROS_ROOT, WORKSPACE, Supervisor, process_identity


PHYSICS_CONFIG_ENV = "MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE"
WALL_LIMIT_SECONDS = 1800
WORK_SECONDS = 1680
KEEP = 888
DECISIONS = 4
WAVEFORM = {
    "origin": "first controlled boundary after bootstrap; equals reset release boundary",
    "quantum_ns": 20_000_000, "stationary_prefix_ns": 1_200_000_000,
    "turn_start_ns": 1_200_000_000, "pulse_start_ns": 2_200_000_000,
    "pulse_end_ns": 2_240_000_000, "turn_end_ns": 2_740_000_000,
    "angular_millirad": 800, "linear_x": 0., "target_robot": "tb3",
    "other_robots": ["tb1", "tb2"], "opportunities": 1,
    "scope": "fixed far-peer from-rest plant contrast; not the original V7 20ms event",
    "validity": "requires independent real guard/storage/actuation audit; missing contrast "
                "is INCOMPLETE, never a new opportunity",
}


def physics_config(path):
    path = Path(path).resolve(strict=True)
    raw = path.read_bytes()
    value = json.loads(raw)
    if (value.get("schema") != "mr3-physics-diagnostic-config-v2"
            or value.get("mode") != "observer_only" or "profile_library" in value):
        raise ValueError("plant contrast requires the declared passive observer-only v2 config")
    return path, {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                  "configuration": value}


def native_custody(episode, *, proc_root=Path("/proc"), expected_smoother_core=None):
    """One paused snapshot of saved owned identities and their actual mapped ELF."""
    proof = {"schema": "mr3-plant-native-custody-v1", "epoch": episode.epoch,
             "wall_monotonic_ns": time.monotonic_ns(), "processes": [], "errors": [],
             "scope": "saved owned PID/start identities only; actual /proc maps plus "
                      "stable matching device/inode file SHA256; no process signalling"}
    with episode.lock:
        owned = sorted(episode.owned.values(), key=lambda value: value["pid"])
    proof["saved_owned_identities"] = owned
    files = {}

    def file_proof(path):
        path = Path(path)
        resolved = path.resolve(strict=True)
        before = resolved.stat()
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
        after = resolved.stat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, field) != getattr(after, field) for field in fields):
            raise ValueError("mapped file changed during custody hash: " + str(path))
        return {"resolved_path": str(resolved), "sha256": digest,
                "stat": {field.removeprefix("st_"): getattr(after, field) for field in fields}}

    for saved in owned:
        current = process_identity(saved["pid"])
        if not current or current["start_ticks"] != saved["start_ticks"] or current["state"] == "Z":
            continue
        row = {"saved_identity": dict(saved), "observed_identity": current}
        try:
            process_dir = proc_root / str(saved["pid"])
            row["argv"] = [value.decode(errors="replace") for value in
                           (process_dir / "cmdline").read_bytes().split(b"\0") if value]
            executable = Path(row["argv"][0]).name if row["argv"] else ""
            kind = "gzserver" if executable == "gzserver" else (
                "velocity_smoother" if executable == "velocity_smoother" else None)
            row["component"] = kind
            if kind is not None:
                row["maps"] = []
                if kind == "velocity_smoother":
                    row["robot"] = next((name for name in ("tb1", "tb2", "tb3")
                                         if "__ns:=/" + name in row["argv"]), None)
                for line in (process_dir / "maps").read_text().splitlines():
                    fields = line.split(maxsplit=5)
                    if len(fields) != 6 or not fields[5].startswith("/"):
                        continue
                    path = fields[5]
                    basename = Path(path).name
                    role = next((name for name, pattern in (
                        ("driver", "libmr3_gazebo_diff_drive"),
                        ("observer", "libmr3_stop_response_observer"),
                        ("ray_box", "libmr3_ray_box_corrector"),
                        ("ode", "libgazebo_ode"),
                        ("smoother_core", "libvelocity_smoother_core")) if pattern in basename), None)
                    if role is None and basename.startswith("libode"):
                        role = "ode"
                    if role is None:
                        continue
                    if path not in files:
                        files[path] = file_proof(path)
                    file = files[path]
                    major, minor = [int(value, 16) for value in fields[3].split(":")]
                    device = file["stat"]["dev"]
                    if ((os.major(device), os.minor(device)) != (major, minor)
                            or file["stat"]["ino"] != int(fields[4])):
                        raise ValueError("mapped device/inode differs from hashed file: " + path)
                    row["maps"].append({"role": role, "actual_maps_line": line,
                                        "mapped_path": path, **file})
            after = process_identity(saved["pid"])
            if not after or after["start_ticks"] != saved["start_ticks"] or after["state"] == "Z":
                raise ValueError("owned process identity changed during custody snapshot")
        except (OSError, ValueError, KeyError) as error:
            row["error"] = repr(error)
            if row.get("component") is not None:
                proof["errors"].append({"pid": saved["pid"], "error": repr(error)})
        proof["processes"].append(row)
    gzservers = [row for row in proof["processes"] if row.get("component") == "gzserver"]
    smoothers = [row for row in proof["processes"]
                 if row.get("component") == "velocity_smoother"]
    if len(gzservers) != 1 or not {"driver", "observer", "ray_box", "ode"}.issubset(
            {value["role"] for row in gzservers for value in row.get("maps", [])}):
        proof["errors"].append({"error": "missing unique owned gzserver with actual native libraries"})
    if len(smoothers) != 3 or {row.get("robot") for row in smoothers} != {"tb1", "tb2", "tb3"}:
        proof["errors"].append({"error": "missing the three actual owned velocity smoothers"})
    try:
        expected = file_proof(expected_smoother_core or (
            ROS_ROOT / "install/nav2_velocity_smoother/lib/libvelocity_smoother_core.so"))
        proof["expected_current_smoother_core"] = expected
        for row in smoothers:
            cores = [value for value in row.get("maps", []) if value["role"] == "smoother_core"]
            if not cores or any(value["sha256"] != expected["sha256"]
                                or value["resolved_path"] != expected["resolved_path"]
                                for value in cores):
                proof["errors"].append({"pid": row["saved_identity"]["pid"],
                                        "error": "actual mapped smoother core differs from current build"})
    except (OSError, ValueError) as error:
        proof["errors"].append({"error": repr(error)})
    proof["passed"] = not proof["errors"]
    (episode.directory / "plant_native_custody.json").write_text(
        json.dumps(proof, indent=2, allow_nan=False) + "\n")
    return proof


def run_arm(args):
    started_ns = time.monotonic_ns()
    work_deadline_ns = started_ns + WORK_SECONDS * 1_000_000_000
    config_path, config = physics_config(args.physics_config)
    prior_config = os.environ.get(PHYSICS_CONFIG_ENV)
    os.environ[PHYSICS_CONFIG_ENV] = str(config_path)
    supervisor = None
    summary_path = None
    summary = {
        "schema": "mr3-plant-probe-v1", "arm": args.arm,
        "scene": "open", "seed": 101, "robots": ["tb1", "tb2", "tb3"],
        "native_decisions_requested": DECISIONS, "native_decisions_returned": 0,
        "optimizer_steps": 0, "policy_calls": 0, "wall_limit_seconds": WALL_LIMIT_SECONDS,
        "work_seconds": WORK_SECONDS, "work_deadline_monotonic_ns": work_deadline_ns,
        "started_wall_monotonic_ns": started_ns, "physics_config": config,
        "waveform": WAVEFORM, "steps": [], "cleanup_errors": [],
        "completed_requested_collection": False,
        "outcome": "INCOMPLETE", "training_eligible": False,
        "validity_audit_required": True, "command": [sys.executable, *sys.argv],
    }
    try:
        summary["freeze"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=WORKSPACE, text=True).strip()
        supervisor = Supervisor(
            run_id=args.run_id, domain_id=args.domain, gazebo_port=args.port,
            output_root=args.output_root, startup_timeout=420., request_timeout=90.,
            plant_stimulus_arm=args.arm,
            plant_stimulus_work_deadline_ns=work_deadline_ns)
        summary_path = supervisor.directory.parent / "plant_probe_summary.json"
        summary["run_directory"] = str(supervisor.directory.parent)
        summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
        result = supervisor.reset(scene="open", seed=101)
        summary["epoch"] = result["snapshot"]["epoch"]
        summary["release_time_ns"] = result["info"]["release_time_ns"]
        custody = native_custody(supervisor.episode)
        summary["native_custody"] = {"path": str(
            supervisor.episode.directory / "plant_native_custody.json"),
                                    "passed": custody["passed"]}
        if not custody["passed"]:
            raise RuntimeError("actual mapped native component custody is incomplete")
        for decision in range(DECISIONS):
            if time.monotonic_ns() >= work_deadline_ns:
                raise TimeoutError("plant probe work allocation exhausted before the next KEEP")
            result = supervisor.step(
                KEEP, external_truncation="plant_probe_fixed_end" if decision == DECISIONS - 1
                else None)
            summary["native_decisions_returned"] += 1
            summary["steps"].append({"decision": decision, "action": KEEP,
                                     "terminated": result["terminated"],
                                     "truncated": result["truncated"], "info": result["info"]})
            if result["terminated"] or result["truncated"]:
                break
        summary["completed_requested_collection"] = (
            summary["native_decisions_returned"] == DECISIONS
            and result["terminated"] is False and result["truncated"] is True)
        if summary["completed_requested_collection"]:
            summary["outcome"] = "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT"
    except Exception as error:
        summary["error"] = repr(error)
    finally:
        if supervisor is not None:
            try:
                supervisor.close()
            except Exception as error:
                summary["cleanup_errors"].append(repr(error))
            summary["shutdown_receipts"] = supervisor.receipts
        ended_ns = time.monotonic_ns()
        summary["ended_wall_monotonic_ns"] = ended_ns
        summary["wall_sec"] = (ended_ns - started_ns) / 1e9
        summary["wall_limit_exceeded"] = summary["wall_sec"] > WALL_LIMIT_SECONDS
        if summary["cleanup_errors"] or summary["wall_limit_exceeded"]:
            summary["outcome"] = "INCOMPLETE"
        if summary_path is not None:
            summary_path.write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
        if prior_config is None:
            os.environ.pop(PHYSICS_CONFIG_ENV, None)
        else:
            os.environ[PHYSICS_CONFIG_ENV] = prior_config
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", choices=("continuous", "pulse"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--physics-config", type=Path, required=True)
    parser.add_argument("--domain", type=int, default=180)
    parser.add_argument("--port", type=int, default=14001)
    parser.add_argument("--output-root", type=Path, default=ROS_ROOT / "log/mr3_plant")
    result = run_arm(parser.parse_args(argv))
    print(json.dumps({key: result.get(key) for key in (
        "run_directory", "outcome", "native_decisions_returned", "wall_sec", "error",
        "cleanup_errors")}, allow_nan=False))
    return 0 if result["outcome"] == "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
