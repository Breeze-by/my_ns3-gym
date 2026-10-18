#!/usr/bin/env python3
"""Read-only strict closure/custody review of one declared V8 plant arm.

Uses saved PID/start identities and original launch exit records. It neither
signals processes nor starts ROS/Gazebo. A closure PASS is not stimulus validity,
physics/safety PASS, or P2A credit. Output must be a new exclusive file.
"""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time


ROBOTS = {"tb1", "tb2", "tb3"}
PROTOCOL = "nav2-finalized_then_serial-ros_then_gazebo-v1"
NAV2_NODES = {"controller_server", "planner_server", "behavior_server", "bt_navigator",
              "waypoint_follower", "velocity_smoother"}


def identity(pid):
    try:
        suffix = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": int(pid), "start_ticks": int(suffix[19]), "state": suffix[0]}
    except FileNotFoundError:
        return None


def review(run, freeze, preflight_path):
    run = Path(run).resolve()
    episode = run / "worker0/episode001_open_101"
    result = {"schema": "mr3-p2a-v8-strict-closure-custody-v1", "run_directory": str(run),
              "freeze": freeze, "review_wall_monotonic_ns": time.monotonic_ns(),
              "failures": [], "missing": [], "source_artifacts": {}, "evidence": {},
              "scope": "one saved diagnostic arm; no native execution or signalling; "
                       "saved identity closure and actual mapped file custody only; "
                       "not stimulus validity, safety/plant PASS or P2A completion"}

    def check(condition, description):
        if not condition:
            result["failures"].append(description)

    def raw(path):
        path = Path(path)
        before = path.stat()
        value = path.read_bytes()
        after = path.stat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        check(all(getattr(before, key) == getattr(after, key) for key in fields),
              "file changed while read: " + str(path))
        result["source_artifacts"][str(path)] = {
            "sha256": hashlib.sha256(value).hexdigest(), "bytes": len(value),
            "stat": {key.removeprefix("st_"): getattr(after, key) for key in fields}}
        return value

    def document(path):
        return json.loads(raw(path), parse_constant=lambda value: (_ for _ in ()).throw(
            ValueError("nonfinite JSON constant: " + value)))

    def section(name, operation):
        try:
            operation()
        except FileNotFoundError as error:
            result["missing"].append({"section": name, "path": error.filename})
        except (OSError, ValueError, TypeError, KeyError, IndexError, AttributeError) as error:
            result["failures"].append(name + ": " + repr(error))

    preflight, summary, metadata, supervisor, custody = {}, {}, {}, {}, {}
    starts, exits = {}, {}
    saved_ids = {}

    def run_summary():
        nonlocal preflight, summary, metadata
        check(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "exact 40hex freeze required")
        metadata = document(episode / "metadata.json")
        preflight = document(preflight_path)
        check(preflight.get("schema") == "mr3-p2a-v8-preflight-v1"
              and preflight.get("passed") is True and preflight.get("freeze") == freeze,
              "preflight did not admit the supplied freeze")
        summary = document(run / "plant_probe_summary.json")
        check(summary.get("schema") == "mr3-plant-probe-v1" and summary.get("freeze") == freeze
              and metadata.get("freeze") == freeze, "actual run/worker freeze differs")
        check(summary.get("arm") in ("continuous", "pulse")
              and summary.get("arm") == metadata.get("plant_stimulus_arm"), "arm differs")
        check(summary.get("epoch") == metadata.get("epoch") and bool(metadata.get("epoch")),
              "run/worker epoch differs or is missing")
        check(summary.get("run_directory") == str(run) and summary.get("scene") == "open"
              and summary.get("seed") == 101 and set(summary.get("robots", [])) == ROBOTS,
              "run identity/scene/seed/robots differs")
        check(summary.get("native_decisions_requested") == 4
              and summary.get("native_decisions_returned") == 4
              and summary.get("completed_requested_collection") is True,
              "four requested native decisions did not all genuinely return")
        check(summary.get("optimizer_steps") == 0 and summary.get("policy_calls") == 0
              and summary.get("training_eligible") is False, "probe used policy/optimizer or became training eligible")
        check(summary.get("cleanup_errors") == [] and "error" not in summary,
              "probe reported error or cleanup errors")
        check(summary.get("outcome") == "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT",
              "probe did not finish captured pending validity")
        elapsed_ns = summary["ended_wall_monotonic_ns"] - summary["started_wall_monotonic_ns"]
        check(type(elapsed_ns) is int and 0 < elapsed_ns <= 1_800_000_000_000
              and summary.get("wall_limit_seconds") == 1800
              and summary.get("wall_limit_exceeded") is False
              and math.isclose(summary["wall_sec"], elapsed_ns / 1e9, rel_tol=0., abs_tol=1e-9),
              "actual total wall duration is invalid/exceeds1800s")
        steps = summary.get("steps", [])
        check(len(steps) == 4 and [row.get("decision") for row in steps] == [0, 1, 2, 3]
              and all(row.get("action") == 888 and row.get("terminated") is False
                      and row.get("truncated") is (index == 3) for index, row in enumerate(steps)),
              "saved KEEP responses do not show three ongoing plus final truncation")
        arm_config = preflight["configs"][summary["arm"]]
        used = summary["physics_config"]
        check(used["path"] == arm_config["path"] and used["sha256"] == arm_config["sha256"],
              "run physics config differs from preflight")
        config = document(used["path"])
        check(result["source_artifacts"][used["path"]]["sha256"] == used["sha256"]
              and used["configuration"] == config, "actual config bytes differ from saved run copy")
        result["evidence"]["plant_probe_summary"] = summary

    section("run_summary", run_summary)

    def worker_closure():
        nonlocal supervisor
        worker = document(episode / "summary.json")
        supervisor = document(episode / "supervisor_shutdown.json")
        supervisor_meta = document(episode / "supervisor_metadata.json")
        nav = document(episode / "nav2_shutdown.json")
        native_stop = document(episode / "native_stop.json")
        epoch = metadata["epoch"]
        for name, value in (("worker", worker), ("supervisor", supervisor),
                            ("supervisor_metadata", supervisor_meta), ("Nav2", nav)):
            check(value.get("epoch") == epoch, name + " closure epoch differs")
        closed = worker.get("closed", {})
        check(closed.get("epoch") == epoch and closed.get("pending_goal_count") == 0
              and set(closed.get("robot_names", [])) == ROBOTS
              and closed.get("navigation_failure") is False,
              "genuine goal ownership closure missing/failed")
        check(worker.get("reason") == "external_truncation" and worker.get("transition_count") == 4
              and worker.get("failures") == [] and worker.get("native_failures") == []
              and worker.get("launch_returncode") == 0 and worker.get("shutdown_protocol") == PROTOCOL,
              "worker reason/count/failures/native-returncode/protocol is not clean")
        check(nav == worker.get("nav2_shutdown") and nav.get("success") is True
              and nav.get("failures") == [] and nav.get("protocol") == PROTOCOL
              and nav.get("goal_ownership_closed") == closed, "actual Nav2 finalization receipt differs/failed")
        robots = nav.get("robots", [])
        check(len(robots) == 3 and {row.get("robot") for row in robots} == ROBOTS,
              "Nav2 closure does not cover exactly three robots")
        for row in robots:
            states = row.get("states", [])
            check(row.get("shutdown", {}).get("response", {}).get("success") is True
                  and len(states) == 6 and {state.get("node") for state in states} == NAV2_NODES
                  and all(state.get("state") == {"id": 4, "label": "finalized"} for state in states),
                  "Nav2 nodes not genuinely finalized: " + str(row.get("robot")))
        ack, request = worker.get("training_finalize_ack", {}), worker.get("training_finalize_request", {})
        check(ack.get("kind") == "training_finalize_ack" and ack.get("epoch") == epoch
              and request.get("epoch") == epoch and ack.get("ack_sequence") == request.get("ack_sequence")
              and ack.get("reason") == request.get("reason") == "external_truncation",
              "real evaluator finalize ACK is missing/different")
        check(supervisor.get("worker_returncode") == 0 and supervisor.get("forced_shutdown") is False
              and supervisor.get("failed_sample") is False
              and supervisor.get("remaining_owned_processes") == []
              and supervisor.get("remaining_owned_zombies") == [], "supervisor closure was forced/failed/incomplete")
        check(summary.get("shutdown_receipts") == [supervisor], "run did not retain the actual sole supervisor receipt")
        check(native_stop.get("returncode") == 0 and native_stop.get("method") == "owned_launch_native_stop"
              and native_stop.get("server_clean_exit_recorded") is True,
              "native stop CLI/server receipt missing/failed")
        for row in supervisor["owned_processes_seen"] + [supervisor_meta["worker_identity"]]:
            key = (row["pid"], row["start_ticks"])
            check(all(type(value) is int and value > 0 for value in key), "invalid saved PID/start identity")
            saved_ids[key] = row
        check(bool(saved_ids), "no saved process identities")
        result["evidence"].update(worker_summary=worker, supervisor_shutdown=supervisor,
                                  native_stop=native_stop)

    section("worker_closure", worker_closure)

    def launch_closure():
        log = raw(episode / "launch.log").decode(errors="replace")
        for line_number, line in enumerate(log.splitlines(), 1):
            start = re.search(r"\[INFO\] \[([^\]]+)\]: process started with pid \[(\d+)\]", line)
            exit_ = re.search(r"\[INFO\] \[([^\]]+)\]: process has finished cleanly \[pid (\d+)\]", line)
            for match, records, label in ((start, starts, "start"), (exit_, exits, "clean exit")):
                if match:
                    key = (match[1], int(match[2]))
                    check(key not in records, "duplicate launch " + label + ": " + str(key))
                    records[key] = line_number
            if any(text in line for text in ("process has died", "failed to terminate",
                    "sending signal 'SIGTERM'", "sending signal 'SIGKILL'",
                    "MR3_GAZEBO_NATIVE_STOP_ERROR", "MR3_ROS_SHUTDOWN_ERROR")):
                result["failures"].append("native launch failure line " + str(line_number) + ": " + line)
        check(bool(starts) and set(starts) == set(exits), "actual launch starts and clean exits differ")
        check(all(exits.get(key, 0) > number for key, number in starts.items()),
              "native clean exit is missing/before its actual start")
        check(sum(name.startswith("gzserver-") for name, _ in starts) == 1
              and sum(name.startswith("velocity_smoother-") for name, _ in starts) == 3
              and sum(name.startswith("mr3_gazebo_native_stop-") for name, _ in starts) == 1,
              "actual launch lacks unique gzserver/native stop or three smoothers")
        native_stop = result["evidence"].get("native_stop", {})
        check(any(name.startswith("mr3_gazebo_native_stop-") and pid == native_stop.get("native_cli_pid")
                  for name, pid in starts), "native stop saved PID differs from actual log")
        result["evidence"]["native_launch"] = {
            "started_count": len(starts), "clean_exit_count": len(exits),
            "records": [{"name": name, "pid": pid, "start_line": number,
                         "clean_exit_line": exits.get((name, pid))} for (name, pid), number in starts.items()]}

    section("native_launch_closure", launch_closure)

    def custody_review():
        nonlocal custody
        custody = document(episode / "plant_native_custody.json")
        check(custody.get("schema") == "mr3-plant-native-custody-v1"
              and custody.get("epoch") == metadata["epoch"]
              and custody.get("passed") is True and custody.get("errors") == [],
              "saved live custody snapshot failed or differs")
        check(summary.get("native_custody") == {"path": str(episode / "plant_native_custody.json"), "passed": True},
              "run custody reference differs")
        for row in custody.get("saved_owned_identities", []):
            saved_ids[(row["pid"], row["start_ticks"])] = row
        processes = custody.get("processes", [])
        gzservers = [row for row in processes if row.get("component") == "gzserver"]
        smoothers = [row for row in processes if row.get("component") == "velocity_smoother"]
        check(len(gzservers) == 1 and len(smoothers) == 3
              and {row.get("robot") for row in smoothers} == ROBOTS,
              "actual custody does not contain one gzserver and three smoothers")
        expected = preflight["libraries"]
        check(set(expected) == {"smoother", "observer", "driver", "ray_box"}, "preflight four ELF roles differ")
        mapped_files = {}
        roles = {}
        for process in gzservers + smoothers:
            saved, observed = process["saved_identity"], process["observed_identity"]
            key = (saved["pid"], saved["start_ticks"])
            check(key in saved_ids and observed.get("pid") == saved["pid"]
                  and observed.get("start_ticks") == saved["start_ticks"] and observed.get("state") != "Z"
                  and "error" not in process, "live custody process PID/start identity is not established")
            prefix = "gzserver-" if process["component"] == "gzserver" else "velocity_smoother-"
            check(any(name.startswith(prefix) and pid == saved["pid"] for name, pid in starts),
                  "custody process differs from actual launch PID")
            found = set()
            for mapping in process.get("maps", []):
                role = mapping["role"]
                found.add(role)
                fields = mapping["actual_maps_line"].split(maxsplit=5)
                check(len(fields) == 6 and fields[5] == mapping["mapped_path"], "saved actual maps path differs")
                major, minor = [int(value, 16) for value in fields[3].split(":")]
                stat = mapping["stat"]
                check((major, minor) == (os.major(stat["dev"]), os.minor(stat["dev"]))
                      and int(fields[4]) == stat["ino"], "actual maps device/inode differs from hashed file")
                resolved = mapping["resolved_path"]
                if resolved not in mapped_files:
                    content = raw(resolved)
                    now = result["source_artifacts"][resolved]
                    mapped_files[resolved] = now
                    if role == "observer":
                        check(expected["observer"]["source_sha256"].encode() in content,
                              "actual observer ELF lacks the preflight compiled-source SHA")
                now = mapped_files[resolved]
                check(now["sha256"] == mapping["sha256"] and now["stat"]["dev"] == stat["dev"]
                      and now["stat"]["ino"] == stat["ino"],
                      "saved mapped ELF no longer matches current bytes/device/inode: " + resolved)
                expected_role = "smoother" if role == "smoother_core" else role
                if expected_role in expected:
                    spec = expected[expected_role]
                    check(mapping["sha256"] == spec["sha256"] and resolved == spec["resolved_path"],
                          "actual mapped " + role + " differs from preflight ELF")
                roles.setdefault(role, set()).add((resolved, mapping["sha256"]))
            required = {"driver", "observer", "ray_box", "ode"} if prefix == "gzserver-" else {"smoother_core"}
            check(required <= found, "actual process maps lack required roles: " + prefix)
        result["evidence"]["actual_mapped_roles"] = {key: sorted(value) for key, value in roles.items()}
        binding = document(episode / "physics_diagnostic_binding.json")
        source_sha = expected["observer"]["source_sha256"]
        check(binding.get("schema") == "mr3-physics-diagnostic-binding-v2"
              and binding.get("epoch") == metadata["epoch"] and binding.get("mode") == "observer_only"
              and binding.get("physics_intervention") == "none_observer_only"
              and binding.get("observer_paused_only") is True
              and "profile_library" not in binding and "profile_output_path" not in binding
              and binding["observer_library"]["source_sha256"] == source_sha
              and binding["observer_library"]["sha256"] == expected["observer"]["sha256"],
              "actual observer binding/source SHA differs or physics intervention is present")
        configs = {}
        for robot in sorted(ROBOTS):
            path = episode / ("physics_" + robot + ".jsonl")
            with path.open("rb") as stream:
                first = stream.readline()
            config = json.loads(first)
            check(config.get("kind") == "configuration" and config.get("epoch") == metadata["epoch"]
                  and config.get("robot") == robot and config.get("paused_only") is True
                  and config.get("read_only") is True and config.get("compiled_source_sha256") == source_sha
                  and len(gzservers) == 1 and config.get("process_id") == gzservers[0]["saved_identity"]["pid"]
                  and str(Path(config["loaded_library_path"]).resolve()) == expected["observer"]["resolved_path"]
                  and config.get("physics_type") == "ode" and config.get("max_step_size_sec") == .001
                  and config["native_ode"]["available"] is True and config["native_ode"]["values"]["iters"] == 150,
                  "actual observer configuration/source/ELF/ODE150 differs: " + robot)
            configs[robot] = {"configuration": config, "file": str(path),
                             "first_raw_line_sha256": hashlib.sha256(first).hexdigest()}
        result["evidence"]["observer_configurations"] = configs

    section("actual_live_native_custody", custody_review)

    def gone_review():
        observations = []
        for (pid, start), saved in sorted(saved_ids.items()):
            now = identity(pid)
            gone = now is None or now["start_ticks"] != start
            check(gone, "saved PID/start identity still exists (including zombie): " + str((pid, start)))
            observations.append({"saved_identity": saved, "current_identity": now, "gone": gone})
        result["evidence"]["saved_identity_closure"] = observations
        result["evidence"]["identity_coverage"] = {
            "saved_identity_count": len(saved_ids),
            "launch_pids_without_saved_start_ticks": sorted({pid for _, pid in starts}
                                                            - {pid for pid, _ in saved_ids}),
            "scope": "all enumerated saved PID/start identities only; a missing saved start tick "
                     "does not become an invented identity. Every launch child separately requires "
                     "its original clean-exit line; no global unowned-process absence claim. "
                     "Runner parent PID/start is not stored by plant_probe_summary and requires "
                     "the owner's separate parent wait/identity record."}

    section("saved_identity_gone", gone_review)
    result["status"] = "FAIL" if result["failures"] else "INCOMPLETE" if result["missing"] else "PASS"
    result["passed"] = result["status"] == "PASS"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_directory", type=Path)
    parser.add_argument("exactfreeze")
    parser.add_argument("preflight_json", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("exclusive output exists")
    result = review(args.run_directory, args.exactfreeze, args.preflight_json)
    result["review_script_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "passed": result["passed"],
                      "failures": result["failures"], "missing": result["missing"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
