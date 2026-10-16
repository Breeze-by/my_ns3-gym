"""Reproduce closed-v5 raw timing/accounting and saved process identity checks."""

import ast
import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = Path(__file__).resolve().parent
FREEZE = "de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ROS = "ros2_ws/ros2-multi-robot-automap/"


def load(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ns(value):
    scaled = Decimal(str(value)) * 1_000_000_000
    assert scaled == scaled.to_integral_value()
    return int(scaled)


def identity_now(pid):
    try:
        fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "start_ticks": int(fields[19]), "state": fields[0]}
    except FileNotFoundError:
        return None


def main():
    output = RUN / "v5_infrastructure_review_v1.json"
    assert not output.exists(), "existing forensic output must remain unchanged"
    metadata, summary = load(RUN / "metadata.json"), load(RUN / "summary.json")
    assert metadata["freeze"] == summary["freeze"] == FREEZE
    critical = RUN / "native/round0003/worker3/episode001_open_101"
    native_meta = load(critical / "metadata.json")
    transitions, physics, events = (rows(critical / name) for name in (
        "transitions.jsonl", "physics.jsonl", "adapter.jsonl"))
    task = load(critical / (native_meta["epoch"] + ".json"))
    last, previous = transitions[-1], transitions[-2]
    diagnostic = last["info"]["reward_diagnostics"]
    start = ns(diagnostic["step_start"])
    terminal_end = ns(diagnostic["effective_step_end"])
    physical_end = ns(last["snapshot"]["source_stamp"])
    assert start == 93_720_000_000 and terminal_end == 94_400_000_000
    assert physical_end == 94_440_000_000 and physical_end - terminal_end == 40_000_000
    assert ns(last["info"]["dt"]) == terminal_end - start == 680_000_000
    assert ns(last["info"]["physical_dt"]) == physical_end - start == 720_000_000
    assert ns(previous["snapshot"]["source_stamp"]) == start
    assert ns(task["end_sim_time_sec"]) == terminal_end
    critical_physics = [row for row in physics
                        if terminal_end - 20_000_000 <= row["end_time_ns"] <= physical_end]
    assert [x["request_id"] for x in critical_physics] == ["q1195", "q1196", "q1197", "q1198"]
    assert all(x["steps"] == 20 and x["end_time_ns"] - x["start_time_ns"] == 20_000_000
               and x["end_iterations"] - x["start_iterations"] == 20
               and x["ok"] and x["paused"] for x in physics if x["steps"] == 20)
    timeline = [{"line": i + 1, "record": row} for i, row in enumerate(events)
                if 94.3 <= row["stamp"] <= 94.6 and row["kind"] in (
                    "safety_stop", "task_terminal_received", "task_terminal", "task_stopped",
                    "snapshot_requested", "snapshot_completed")]
    source_paths = {
        ROS + "scripts/mr3_env_worker.py": ("_physics", "_evaluation", "step", "_snapshot"),
        WIRELESS + "mr3_learning/env.py": ("_unpack",),
        WIRELESS + "mr3_learning/ppo.py": ("collect_episodes",),
        ROS + "src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py": (
            "_control_failure_callback", "publish_task_terminal_notice", "finalize"),
        ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_information.py": ("poll_drain",),
        ROS + "src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py": ("publish_obstacles",),
        ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py": (
            "receive_failure", "poll_task_terminal"),
    }
    source_proof = {}
    for relative, names in source_paths.items():
        frozen = subprocess.check_output(["git", "show", FREEZE + ":" + relative], cwd=ROOT)
        assert (ROOT / relative).read_bytes() == frozen
        text = frozen.decode()
        tree, lines = ast.parse(text), text.splitlines()
        snippets = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names:
                snippets[node.name] = {"first_line": node.lineno, "last_line": node.end_lineno,
                                       "source": "\n".join(lines[node.lineno - 1:node.end_lineno])}
        assert set(snippets) == set(names)
        source_proof[relative] = {"sha256": hashlib.sha256(frozen).hexdigest(),
                                  "git_source": FREEZE + ":" + relative,
                                  "worktree_equal": True, "relevant_functions": snippets}
    attempts, identities, parent_pids = [], set(), set()
    aggregate = {"native_api_records": 0, "native_submitted_decisions": 0,
                 "native_effective_time_ns": 0, "native_physical_time_ns": 0,
                 "native_close_ack_sequences": 0}
    for directory in sorted(RUN.glob("native/round*/worker*/episode*")):
        m, native, supervisor, supervisor_meta = [load(directory / name) for name in (
            "metadata.json", "summary.json", "supervisor_shutdown.json", "supervisor_metadata.json")]
        assert m["freeze"] == FREEZE
        step_rows = rows(directory / "transitions.jsonl")[1:]
        evaluation = load(directory / (m["epoch"] + ".json"))
        checks = []
        for saved in supervisor["owned_processes_seen"] + [supervisor_meta["worker_identity"]]:
            key = saved["pid"], saved["start_ticks"]
            if key in {(x["pid"], x["saved_start_ticks"]) for x in checks}:
                continue
            identities.add(key)
            current = identity_now(saved["pid"])
            absent = current is None or current["start_ticks"] != saved["start_ticks"]
            assert absent, "saved owned process identity still present: " + str(key)
            checks.append({"pid": saved["pid"], "saved_start_ticks": saved["start_ticks"],
                           "current": current, "saved_identity_absent": absent})
        parent_pids.add(supervisor_meta["worker_identity"]["parent"])
        clean = (supervisor["worker_returncode"] == 0 and not supervisor["forced_shutdown"]
                 and not supervisor["failed_sample"] and not supervisor["remaining_owned_processes"]
                 and not supervisor["remaining_owned_zombies"] and native["launch_returncode"] == 0
                 and not native["native_failures"])
        states = [s["state"] for robot in native["nav2_shutdown"]["robots"] for s in robot["states"]]
        assert clean and len(states) == 18 and all(s == {"id": 4, "label": "finalized"} for s in states)
        effective = sum(ns(x["info"]["dt"]) for x in step_rows)
        physical = sum(ns(x["info"]["physical_dt"]) for x in step_rows)
        submitted = sum(x["info"].get("action_submitted", True) for x in step_rows)
        critical_attempt = directory == critical
        last_step = step_rows[-1]
        if critical_attempt:
            outcome = "genuine_peer_task_failure_with_invalid_40ms_terminal_sample; not trainable"
        elif not last_step["terminated"] and not last_step["truncated"]:
            outcome = "abandoned_native_prefix_after_peer_worker_infrastructure_error"
        else:
            outcome = "actual_native_task_success" if evaluation["success"] else "genuine_native_task_failure"
        attempts.append({"directory": str(directory), "epoch": m["epoch"], "outcome": outcome,
                         "native_api_records": len(step_rows), "native_submitted_decisions": submitted,
                         "effective_time_ns": effective, "physical_time_ns": physical,
                         "physical_minus_effective_ns": physical - effective,
                         "last_step_terminated": last_step["terminated"],
                         "last_step_truncated": last_step["truncated"],
                         "native_close_ack_sequence": native["training_finalize_request"]["ack_sequence"],
                         "task": {key: evaluation[key] for key in (
                             "success", "termination_reason", "elapsed_sim_time_sec",
                             "correct_free_coverage_ratio", "map_quality_pass", "robot_participation_pass")},
                         "native_shutdown_clean": clean, "nav2_finalized_nodes": len(states),
                         "all_saved_process_identities_absent": True, "identity_checks": checks,
                         "files_sha256": {f.name: sha(f) for f in directory.iterdir() if f.is_file()}})
        aggregate["native_api_records"] += len(step_rows)
        aggregate["native_submitted_decisions"] += submitted
        aggregate["native_effective_time_ns"] += effective
        aggregate["native_physical_time_ns"] += physical
        aggregate["native_close_ack_sequences"] += native["training_finalize_request"]["ack_sequence"]
    assert len(attempts) == 16
    assert aggregate["native_api_records"] == summary["native_api_records"] == 876
    assert aggregate["native_submitted_decisions"] == summary["native_recorded_decisions"] == 876
    assert aggregate["native_effective_time_ns"] == ns(summary["native_effective_sim_seconds"])
    assert aggregate["native_physical_time_ns"] == ns(summary["native_physical_sim_seconds"])
    assert not summary["completed"] and summary["stop_reason"] == "infrastructure_error"
    assert not (RUN / "final.zip").exists() and summary["optimizer_updates"] == 48
    result = {
        "schema": "mr3-p2a-v5-infrastructure-forensics-v1", "created_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(), "source_freeze": FREEZE,
        "reproduction_script_sha256": sha(Path(__file__)), "source_proof": source_proof,
        "original_error": summary["error"], "critical_episode": str(critical),
        "critical_timing": {"step_start_ns": start, "effective_terminal_ns": terminal_end,
                            "physical_snapshot_ns": physical_end, "physical_lag_ns": physical_end - terminal_end,
                            "strict_maximum_lag_ns": 20_000_000,
                            "actual_effective_dt_ns": terminal_end - start,
                            "actual_physical_dt_ns": physical_end - start,
                            "quantum_receipts": critical_physics, "adapter_timeline": timeline},
        "root_cause": ("The worker's per-quantum barrier proves physical pause and only its own /clock "
                       "receipt. It does not prove completion of downstream peer-safety/evaluator callbacks "
                       "or delivery of the terminal notice. step() polls _evaluation once and immediately "
                       "permits the next20 ticks. Backend information drain/snapshot occurs after this loop "
                       "and covers backend timers/maps/states, not safety/evaluator settlement. This is a "
                       "missing causal terminal-processing barrier, not an oversized quantum or float rounding."),
        "proven_control_flow_inference": [
            "Safety/evaluator frozen terminal is94.400; actual physical receipts advance to94.420 and94.440.",
            "Adapter independently records terminal receipt94.420. Final actor snapshot is94.440.",
            "Given frozen step() and _physics clock equality, the94.420 _evaluation poll returnedNone; otherwise q1198 could not execute.",
            "The94.440 poll detected terminal: physical loop stopped before nominal94.720 endpoint.",
            "Reward correctly froze94.400 while snapshot honestly remained94.440; client strict gate rejected40ms lag."],
        "unavailable_evidence": [
            "Worker per-quantum predicate observations and terminal receive wall/clock timestamps were not saved.",
            "Exact DDS/thread interleaving or wall cost of evaluator finalization cannot be reconstructed.",
            "Evaluator freezes end_time before diagnostics then publishes notice before fileI/O; this source order does not identify which computation/transport delay dominated."],
        "strict_repair_requirements": [
            "After each20tick pauseT, await an epoch/request/target-time evaluator ACK at its actualclock EXACTT, on the same SingleThreadedExecutor as finalize. Return immutable sanctioned taskterminal or LIVE only when no terminal is finalizing/finalized. Consume terminal directly from ACK before another quantum.",
            "A clock-only ACK, backend-only drain, fixed sleep or stale evaluator status query is insufficient. Exact evaluator-clock ACK is sufficient for the current frozen-finalize-now lag bound; full producer watermarks are not required unless a stronger producer-event lag guarantee is claimed. Missing/future/cross-epoch/duplicate permission or wrong-clock ACK must fail infrastructure and clean up owned processes.",
            "Preserve the20ms bound and integer-nanosecond timing. Do not clamp the40ms excess, move frozen terminal timestamps, fabricate clock/sensor stamps, or label policy advancement as cleanup.",
            "Reject invalid terminal lag at the native worker boundary before admitting a learner transition, while preserving raw failure evidence and existing client/offline gates.",
            "Test forced callback/notice delays with physics paused, normal1s transitions, short/zero-time terminals, monotone epoch/watermarks, missing ACK wall guard, native contact freshness, all goal ownership cancellation and full cleanup.",
            "A prospective new source freeze and declared native validation are required for any runtime repair; old data cannot become repaired-freeze evidence. No new native run or retry is authorized by this diagnosis."],
        "minimal_evaluator_ack_proof": {
            "judgment": "Valid under current source semantics; no counterexample found under stated proof obligations.",
            "derivation": [
                "At physical pauseT, evaluator processes exactclockT ACK on its own SingleThreadedExecutor. A currently running finalize must finish before that ACK can be processed.",
                "If ACKT isLIVE, any later finalize freezes tau=_now()>=T, because clock is monotone and there is no producer timestamp backdating.",
                "Worker advances only one20ms quantum then requires exactT+.02 ACK. If tau<=T+.02, it sees frozen terminal directly and stops; if finalization occurs later, its frozen timestamp is>=T+.02.",
                "Therefore sampled physical_end minus frozen terminal tau is at most20ms. Delayed computation or terminal-notice DDS delivery can increase wall wait but cannot permit another quantum without its ACK."],
            "obligations": [
                "Actual evaluator clock must equal requestedT; behind/advanced/regressed clocks cannot produce LIVE permission.",
                "ACK handler and finalize share the same serialized executor; no LIVE fallback from partially built final_result.",
                "Unique epoch/request/T binding, once-only permission consumption, bounded paused wall guard and direct immutable terminal consumption.",
                "Keep existing taskterminal reason filter and external-truncation semantics; no fabricated taskfailure for sampler stop."],
            "scope_limits": "Bounds lag from frozen evaluator finalize_now boundary, as existing contract. Does not prove peer/Nav2 producer callbacks drained throughT or bound lag from earliest physical safety event. Backdating terminal timestamps or multithreaded evaluator would require a new proof.",
            "correction_to_initial_diagnosis": "Initial suggestion requiring all producer watermarks was too strong for this frozen-evaluator-boundary contract; retained source facts support the narrower exact-clock evaluator ACK proof."},
        "attempts": attempts, "aggregate_native_receipts": aggregate,
        "unique_saved_pid_start_identities": len(identities), "all_saved_identities_absent": True,
        "parent_pid_checks": [{"pid": pid, "current": identity_now(pid),
                               "pid_absent": identity_now(pid) is None} for pid in sorted(parent_pids)],
        "accounting_scope": {"closed_trained_decisions": summary["decisions"],
                             "collector_observed_decisions": summary["collector_observed_decisions"],
                             "raw_native_decisions": summary["native_recorded_decisions"],
                             "optimizer_steps": summary["optimizer_updates"],
                             "round3_raw_decisions": sum(a["native_api_records"] for a in attempts if "/round0003/" in a["directory"]),
                             "critical_invalid_native_decision_count": 1,
                             "meaning": "Raw native876 includes rejected invalid40ms sample; collector875 excludes it; only completed rounds797 reached48 optimizersteps. Round3 has79 raw records and no optimizer update. Native ACK extra settlements are not actor samples."},
        "final_checkpoint_exists": False, "validation_required_to_skip": True,
        "validation_reason": "Prospective condition requires finite final checkpoint and no infrastructure error; neither is satisfied. Do not substitute checkpoint0002 for declared final.zip or run undeclared validation.",
        "run_wall_sec_including_all_attempts": summary["wall_sec_including_all_attempts"],
        "original_native_and_audit_errors_preserved": True,
        "run_artifact_sha256": {name: sha(RUN / name) for name in (
            "metadata.json", "summary.json", "progress.json", "checkpoint_0002.zip")},
        "scope": "Read-only raw/source forensic calculations and /proc checks; only this new ignored JSON and reproducibility script are written. No simulator/GPU/inference/optimizer/signals/source or gate edits.",
    }
    with output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"artifact": str(output), "sha256": sha(output),
                      "attempts": len(attempts), "unique_saved_identities": len(identities),
                      "all_absent": True, "native": aggregate, "validation_skip": True}))


if __name__ == "__main__":
    main()
