"""Read-only CPU forensic receipt for the already stopped V6 pilot."""

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = Path(__file__).resolve().parent
FREEZE = "af37b2aaa3cb9980434f7f16c1f52dec2506319d"
OUTPUT = RUN / "v6_infrastructure_review_v1.json"
ROS = "ros2_ws/ros2-multi-robot-automap/"
LEARN = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/"
started = time.monotonic()
artifacts = {}
assert not OUTPUT.exists(), "preserve any prior receipt"


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def read(path):
    payload = path.read_bytes()
    artifacts[str(path.relative_to(RUN))] = {
        "sha256": digest(payload), "bytes": len(payload)}
    return payload


def load(path):
    return json.loads(read(path))


def frozen_source(relative):
    payload = subprocess.check_output(["git", "show", FREEZE + ":" + relative], cwd=ROOT)
    current = (ROOT / relative).read_bytes()
    proof = {"git_source": FREEZE + ":" + relative, "frozen_sha256": digest(payload),
             "current_sha256_at_review": digest(current),
             "current_equals_frozen": current == payload}
    return payload.decode(), proof


def original_function(source, name):
    function = next(node for node in ast.parse(source).body
                    if isinstance(node, ast.FunctionDef) and node.name == name)
    module = ast.Module(body=[function], type_ignores=[])
    scope = {"re": re}
    exec(compile(ast.fix_missing_locations(module), "<frozen-function-only>", "exec"), scope)
    return scope[name], {"first_line": function.lineno, "last_line": function.end_lineno}


def current_identity(pid):
    try:
        rest = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
    except FileNotFoundError:
        return None
    return {"pid": pid, "parent": int(rest[1]), "group": int(rest[2]),
            "session": int(rest[3]), "start_ticks": int(rest[19]), "state": rest[0]}


def locations(source, needles):
    return {needle: [index for index, line in enumerate(source.splitlines(), 1)
                     if needle in line] for needle in needles}


metadata, summary = load(RUN / "metadata.json"), load(RUN / "summary.json")
assert metadata["freeze"] == summary["freeze"] == FREEZE
assert summary["stop_reason"] == "infrastructure_error" and not summary["completed"]
assert summary["episodes"] == summary["rounds"] == []
assert summary["optimizer_updates"] == summary["closed_episode_decisions"] == 0
assert summary["cleanup_errors"] == summary["native_accounting_errors"] == []
assert summary["native_recorded_decisions"] == summary["native_api_records"] == 718
assert summary["collector_observed_decisions"] == 717
assert summary["native_effective_sim_seconds"] == summary["native_physical_sim_seconds"] == 716.64
assert summary["wall_sec_including_all_attempts"] == 3477.507027802989
assert not list(RUN.glob("rollout_*.npz")) and not list(RUN.glob("checkpoint_*.zip"))
assert not (RUN / "final.zip").exists()
read(RUN / "initial.zip")
assert artifacts["initial.zip"]["sha256"] == summary["initial_checkpoint_sha256"]
sources, source_proof = {}, {}
for relative in (ROS + "scripts/run_mr3_adapter_probe.py", ROS + "scripts/ros_smoke_test.py",
                 ROS + "scripts/mr3_env_worker.py", ROS + "src/multi_robot/launch/"
                 "gazebo_multirobot_mapping_with_nav2.launch.py", LEARN + "supervisor.py",
                 LEARN + "ppo.py", ROS + "src/multi_robot_exploration/"
                 "multi_robot_exploration/task_evaluator.py"):
    sources[relative], source_proof[relative] = frozen_source(relative)
check_stop, stop_span = original_function(
    sources[ROS + "scripts/run_mr3_adapter_probe.py"], "native_stop_receipt")
check_failures, failure_span = original_function(
    sources[ROS + "scripts/ros_smoke_test.py"], "native_launch_failures")
workers, all_identities = [], {}
totals = {"native_submitted": 0, "native_api": 0, "effective_ns": 0, "physical_ns": 0}
for number in range(4):
    directory = RUN / "native" / "round0000" / f"worker{number}" / "episode001_open_101"
    native_meta = load(directory / "metadata.json")
    supervisor_meta = load(directory / "supervisor_metadata.json")
    shutdown = load(directory / "supervisor_shutdown.json")
    nav = load(directory / "nav2_shutdown.json")
    epoch = native_meta["epoch"]
    assert native_meta["freeze"] == FREEZE
    assert epoch == shutdown["epoch"] == nav["epoch"] == supervisor_meta["epoch"]
    assert nav["success"] and nav["failures"] == []
    assert shutdown["remaining_owned_processes"] == shutdown["remaining_owned_zombies"] == []
    text = read(directory / "launch.log").decode(errors="replace")
    lines = text.splitlines()
    ordered = [{"line": index, **json.loads(line.split("MR3_ORDERED_SHUTDOWN ", 1)[1])}
               for index, line in enumerate(lines, 1) if "MR3_ORDERED_SHUTDOWN " in line]
    assert all(row["epoch"] == epoch for row in ordered)
    assert [row["receipt_index"] for row in ordered] == list(range(1, len(ordered) + 1))
    starts = [row for row in ordered if row["event"] == "process_started"]
    exits = [row for row in ordered if row["event"] == "process_exited"]
    errors = [row for row in ordered if row["event"] == "error"]
    nonzero = [row for row in exits if row["returncode"] != 0]
    try:
        parsed_stop = {"returned": check_stop(text), "exception": None}
    except RuntimeError as error:
        parsed_stop = {"returned": None, "exception": str(error)}
    stop_matches = re.findall(
        r"\[INFO\] \[mr3_gazebo_native_stop-(\d+)\]: process started with pid \[(\d+)\]",
        text)
    transitions = [json.loads(line) for line in read(
        directory / "transitions.jsonl").splitlines()]
    assert transitions[0]["kind"] == "reset"
    steps = transitions[1:]
    assert all(row["kind"] == "step" for row in steps)
    submitted = sum(row["info"].get("action_submitted", True) for row in steps)
    effective_ns = sum(round(row["info"]["dt"] * 1e9) for row in steps)
    physical_ns = sum(round(row["info"]["physical_dt"] * 1e9) for row in steps)
    totals["native_submitted"] += submitted
    totals["native_api"] += len(steps)
    totals["effective_ns"] += effective_ns
    totals["physical_ns"] += physical_ns
    terminal = load(directory / (epoch + ".json"))
    last = steps[-1]
    assert last["terminated"] and not last["truncated"]
    assert last["info"]["reason"] == terminal["termination_reason"]
    process_rows = []
    for saved in shutdown["owned_processes_seen"]:
        identity = current_identity(saved["pid"])
        state = ("absent" if identity is None else "PID_reused"
                 if identity["start_ticks"] != saved["start_ticks"] else "same_identity_present")
        assert state != "same_identity_present"
        row = {"saved": saved, "current": identity, "current_status": state}
        process_rows.append(row)
        all_identities[(saved["pid"], saved["start_ticks"])] = row
    known = {row["pid"]: row for row in shutdown["owned_processes_seen"]}
    if number == 0:
        assert len(stop_matches) == 0 and not (directory / "native_stop.json").exists()
        assert parsed_stop["exception"] == "native stop CLI identity is missing or ambiguous"
        assert len(nonzero) == len(errors) == 1
        bad, error = nonzero[0], errors[0]
        assert bad["pid"] == error["pid"] == 1438806
        assert bad["process_name"] == "multirobot_slam_toolbox_node-7"
        assert bad["returncode"] == error["returncode"] == -6
        assert bad["controlled"] and bad["signal_sequence"] == 27
        assert error["reason"] == "nonzero_process_exit"
        assert known[bad["pid"]]["start_ticks"] == 388028229
        start = next(row for row in starts if row["pid"] == bad["pid"])
        signal = next(row for row in ordered if row["event"] == "signal"
                      and row["pid"] == bad["pid"])
        assert start["action_id"] == signal["action_id"] == bad["action_id"] == error["action_id"]
        assert start["process_start_index"] == signal["process_start_index"] == 7
        assert "__ns:=/tb1" in start["argv"] and signal["signal"] == "SIGINT"
        exception_message = "terminate called after throwing an instance of 'karto::Exception'"
        exception_line = next(index for index, line in enumerate(lines, 1)
                              if exception_message in line)
        assert signal["line"] < exception_line < bad["line"] < error["line"]
        assert not any(row["event"] in ("gz_stop", "ros_complete", "complete")
                       for row in ordered)
        failure = load(directory / "infrastructure_failure.json")
        assert failure["request"]["id"] == 301 and failure["request"]["op"] == "step"
        assert failure["request"]["epoch"] == epoch and failure["request"]["action"] == 989
        assert parsed_stop["exception"] in failure["error"]
        assert (directory / "worker.log").is_file() and not read(directory / "worker.log")
        assert shutdown["worker_returncode"] == 1
        assert shutdown["forced_shutdown"] and shutdown["failed_sample"]
        assert len(steps) == 300
        missing_return_proof = {
            "native_last_record": {key: last[key] for key in (
                "kind", "reward", "terminated", "truncated")},
            "native_last_info": {key: last["info"][key] for key in (
                "epoch", "dt", "physical_dt", "reason", "command")},
            "collector_retained_count": summary["active_episodes"][0]["decisions"],
            "worker_error_request": failure["request"],
            "source_order": "write transition -> shutdown_episode -> return -> IPC send OK",
            "native_row_saved_but_successful_reply_not_emitted": True}
        assert missing_return_proof["collector_retained_count"] == 299
        abort = {"identity_start": start, "identity_saved_monitor": known[bad["pid"]],
                 "controlled_signal": signal, "nonzero_exit": bad, "strict_order_error": error,
                 "karto_exception_line": exception_line,
                 "launch_lines_around_abort": [{"line": index + 1, "text": lines[index]}
                                               for index in range(exception_line - 2,
                                                                  error["line"] + 1)]}
    else:
        assert len(stop_matches) == 1 and not nonzero and not errors
        native_stop = load(directory / "native_stop.json")
        assert parsed_stop["returned"] == native_stop
        assert shutdown["worker_returncode"] == 0 and not shutdown["forced_shutdown"]
        assert not shutdown["failed_sample"]
        load(directory / "summary.json")
    # Record evidence bytes even when detailed phase/protocol gates are owned by root's full audit.
    for name in ("evaluator_phase_worker.jsonl", "evaluator_phase_evaluator.jsonl",
                 "physics.jsonl", "adapter.jsonl"):
        read(directory / name)
    workers.append({
        "worker": number, "epoch": epoch, "domain": supervisor_meta["domain_id"],
        "worker_identity": supervisor_meta["worker_identity"],
        "native_submitted_decisions": submitted, "native_api_records": len(steps),
        "effective_ns": effective_ns, "physical_ns": physical_ns,
        "native_stop_started_regex_matches": stop_matches, "original_stop_parser": parsed_stop,
        "original_native_launch_failures": check_failures(text),
        "ordered_started_processes": len(starts), "ordered_exited_processes": len(exits),
        "ordered_nonzero_exits": nonzero, "ordered_errors": errors,
        "ordered_complete": any(row["event"] == "complete" for row in ordered),
        "nav2_shutdown_success": nav["success"], "nav2_shutdown_failures": nav["failures"],
        "supervisor_worker_returncode": shutdown["worker_returncode"],
        "supervisor_forced_shutdown": shutdown["forced_shutdown"],
        "supervisor_failed_sample": shutdown["failed_sample"],
        "remaining_owned_processes": shutdown["remaining_owned_processes"],
        "remaining_owned_zombies": shutdown["remaining_owned_zombies"],
        "saved_owned_identity_checks": process_rows,
        "isolated_native_terminal": {key: terminal[key] for key in (
            "success", "termination_reason", "elapsed_sim_time_sec", "end_sim_time_sec",
            "correct_free_coverage_ratio", "map_quality_pass", "robot_participation_pass",
            "collision_events", "navigation_protocol_closed")},
        "native_terminal_scope": "frozen evaluator result; w0 closure invalid, no task credit"})
assert totals == {"native_submitted": 718, "native_api": 718,
                  "effective_ns": 716640000000, "physical_ns": 716640000000}
read(Path(__file__).resolve())
prepared_review = RUN / "round0000_learning_review_v6.py"
read(prepared_review)
assert not (RUN / "round0000_learning_review_v6.json").exists()
assert not (RUN / "round0000_learning_review_v6_inputs").exists()
for relative, proof in artifacts.items():
    assert digest((RUN / relative).read_bytes()) == proof["sha256"]
worker_source = sources[ROS + "scripts/mr3_env_worker.py"]
launch_source = sources[ROS + "src/multi_robot/launch/"
                        "gazebo_multirobot_mapping_with_nav2.launch.py"]
receipt = {
    "schema": "mr3-v6-stopped-infrastructure-independent-review-v1",
    "diagnostic_complete": True, "native_run_pass": False, "freeze": FREEZE,
    "utc_recorded": datetime.now(timezone.utc).isoformat(),
    "source_proof": source_proof, "artifacts": artifacts,
    "classification": "genuine observed SLAM shutdown abort; strict infrastructure rejection",
    "causal_chain": [
        "All worker0 task physics reached a saved genuine 300s timeout terminal.",
        "Goal ownership and Nav2 lifecycle cleanup completed before ordered process shutdown.",
        "Ordered SIGINT27 targeted saved tb1 SLAM PID1438806/start388028229.",
        "That process printed karto::Exception terminate and exited -6.",
        "OrderedRosShutdown.exited classified nonzero_process_exit and fail emitted Shutdown.",
        "The serial drain never reached ros_complete/gz_stop; no native stop CLI was launched.",
        "Worker computed native_launch_failures then native_stop_receipt raised on zero matches.",
        "Worker wrote native decision300 but failed before returning it successfully over IPC.",
        "Collector retained299 worker0 decisions; round aborted before PPO save/train."],
    "abort_evidence": abort, "lost_worker0_return": missing_return_proof,
    "source_branches": {
        "native_stop_receipt_function": stop_span, "native_launch_failures_function": failure_span,
        "worker_lines": locations(worker_source, (
            "self.transition_file.write(json.dumps({\"kind\": \"step\", **result}",
            "self.shutdown_episode(\"task_terminal\" if terminated", "return result",
            "failures = native_launch_failures(launch_text)",
            "native_stop = native_stop_receipt(launch_text)",
            "if failures or self.launch.returncode != 0:",
            "peer.send({\"id\": request[\"id\"], \"epoch\": request[\"epoch\"],",
            "infrastructure_failure.json")),
        "ordered_launch_lines": locations(launch_source, (
            "def fail(", "elif controlled and self.phase", "event.returncode != 0:",
            "self.fail(\"nonzero_process_exit\"", "self.phase = \"native\"",
            "def start_native_stop(", "name=\"mr3_gazebo_native_stop\""))},
    "workers": workers, "totals": totals,
    "saved_owned_identities_checked_absent_or_reused": len(all_identities),
    "original_run_status": {key: summary[key] for key in (
        "completed", "error", "error_type", "stop_reason", "decisions", "optimizer_updates",
        "collector_observed_decisions", "native_recorded_decisions", "native_api_records",
        "native_effective_sim_seconds", "native_physical_sim_seconds", "cleanup_errors",
        "wall_sec_including_all_attempts")},
    "checkpoint_state": {"initial_only": True, "round0_rollout_saved": False,
                         "updated_checkpoint_saved": False, "final_saved": False,
                         "prepared_learner_review_executed": False},
    "learner_review": {"status": "SKIPPED", "prepared_script": str(prepared_review),
                       "reason": "No closed saved round, rollout, or updated checkpoint exists.",
                       "whole_run_completed_requirement_not_used": True},
    "budget_scope": {"this_attempt_native_decisions_charged": 718,
                     "this_attempt_wall_seconds_charged": 3477.507027802989,
                     "cumulative_budget_not_reset": True,
                     "parent_reported_remaining_decisions": 1870,
                     "parent_reported_remaining_wall_seconds": 2905.954739546403,
                     "remaining_budget_scope": "Root cumulative ledger; not derived locally.",
                     "automatic_retry_or_further_budget_use": False,
                     "three_final_only_validations": "SKIPPED under V6 infra no-retry rule"},
    "parent_reported_core_diagnostics": {
        "provenance": "Root message during this review; not independently captured here.",
        "kernel_core_pattern": "apport pipe", "ulimit_c": 0,
        "var_crash_slam_file": False,
        "scope": "No usable captured C++ backtrace; exact throw not established."},
    "command_argv": ["rtk", "proxy", "env", "PYTHONNOUSERSITE=1", "/usr/bin/python3", "-B",
                     str(Path(__file__).resolve())],
    "execution": {"pure_CPU_standard_library": True, "native_or_ROS_jobs": 0,
                  "GPU_jobs": 0, "optimizer_calls": 0, "signals": 0, "tracked_writes": 0,
                  "wall_seconds": time.monotonic() - started},
    "limits": [
        "No C++ exception stack/core backtrace; the internal Karto throw cause is unknown.",
        "The identity error masks a real process abort, not only a parser defect.",
        "Raw records/original failure preserved; no synthetic native receipt or gate override.",
        "Frozen task metrics do not grant credit to failed worker closure or whole run.",
        "No update happened; no policy learning benefit, final policy, or validation claim.",
        "Saved PID/start identity checks exclude unseen transient processes."]}
with OUTPUT.open("x") as target:
    target.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
print(json.dumps({"receipt": str(OUTPUT), "sha256": digest(OUTPUT.read_bytes()),
                  "native_run_pass": False, "diagnostic_complete": True,
                  "observed_abort_pid": 1438806, "native_decisions": totals["native_submitted"],
                  "saved_owned_identities_checked": len(all_identities)}, indent=2))
