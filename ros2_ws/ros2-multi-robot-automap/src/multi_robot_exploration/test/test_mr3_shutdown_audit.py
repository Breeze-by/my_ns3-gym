"""Adversarial saved-receipt audits; no ROS initialization or native processes."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "shutdown_evidence_fixtures", Path(__file__).with_name("test_mr3_env_audit.py"))
FIXTURES = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURES)
AUDIT, EPOCH = FIXTURES.AUDIT, FIXTURES.EPOCH


def nav2_fixture(closed):
    physical, started = 12020000000, 2000000000
    receipt = {"schema": "mr3-nav2-shutdown-v1", "protocol": AUDIT.SHUTDOWN_PROTOCOL,
               "epoch": EPOCH, "goal_ownership_closed": closed,
               "goal_ownership_closed_received_clock_ns": physical,
               "goal_ownership_closed_received_wall_monotonic_ns": 1000000000,
               "physical_time_ns": physical, "start_clock_ns": physical,
               "end_clock_ns": physical, "started_wall_monotonic_ns": started,
               "wall_guard_sec": 30., "success": True, "failures": [], "robots": []}
    cursor = started

    def timing():
        nonlocal cursor
        begin = cursor
        cursor += 3000000
        return {"started_wall_monotonic_ns": begin,
                "request_wall_monotonic_ns": begin + 1000000,
                "completed_wall_monotonic_ns": begin + 2000000,
                "wall_duration_sec": .002,
                "request_clock_ns": physical, "response_clock_ns": physical}

    for robot in AUDIT.ROBOTS:
        receipt["robots"].append({"robot": robot, "shutdown": {
            "service": f"/{robot}/lifecycle_manager_navigation/manage_nodes", "command": 4,
            "response": {"success": True}, **timing()}, "states": [
                {"node": node, "service": f"/{robot}/{node}/get_state",
                 "state": {"id": 4, "label": "finalized"}, **timing()}
                for node in AUDIT.NAV2_NODES]})
    receipt["completed_wall_monotonic_ns"] = cursor
    receipt["wall_duration_sec"] = (cursor - started) / AUDIT.NS
    return receipt


def launch_fixture(nav2_completed, *, early_clean=False):
    lines, records = [], []
    wall = 100000000

    def marker(event, **payload):
        nonlocal wall
        wall += 1000000
        row = {"schema": "mr3-ordered-ros-shutdown-v1", "protocol": AUDIT.SHUTDOWN_PROTOCOL,
               "epoch": EPOCH, "receipt_index": len(records) + 1,
               "wall_monotonic_ns": wall, "event": event, **payload}
        records.append(row)
        lines.append("[INFO] [launch.user]: " + AUDIT.ORDERED_SHUTDOWN_MARKER
                     + json.dumps(row) + "\n")

    def start(index, name, pid, role="owned_ros"):
        value = {"process_start_index": index, "process_name": name, "pid": pid,
                 "action_id": pid * 100, "role": role}
        lines.append(f"[INFO] [{name}]: process started with pid [{pid}]\n")
        marker("process_started", **value, argv=["/fixture/" + name])
        return value

    def exited(value, *, controlled=False, sequence=None):
        marker("process_exited", **value, returncode=0,
               controlled=controlled, signal_sequence=sequence)
        lines.append(f"[INFO] [{value['process_name']}]: process has finished cleanly "
                     f"[pid {value['pid']}]\n")

    def signal(value, sequence):
        marker("signal", **value, signal="SIGINT", signal_sequence=sequence)
        lines.append(f"[INFO] [{value['process_name']}]: sending signal 'SIGINT' "
                     f"to process[{value['process_name']}]\n")

    server = start(1, "gzserver-1", 222, "gazebo_server")
    ready = start(2, "nav2_ready_gate-3", 777)
    controller = start(3, "controller_server-4", 444)
    adapter = start(4, "mr3_adapter-5", 555)
    evaluator = start(5, "task_evaluator-6", 666)
    exited(ready)
    wall = nav2_completed
    exited(evaluator)
    marker("begin", evaluator_pid=666, evaluator_returncode=0,
           remaining=[adapter, controller])
    signal(adapter, 1)
    if early_clean:
        exited(controller)
    exited(adapter, controlled=True, sequence=1)
    if not early_clean:
        signal(controller, 2)
        exited(controller, controlled=True, sequence=2)
    count = 1 if early_clean else 2
    marker("ros_complete", signaled_count=count)
    marker("gz_stop", server_pid=222, signaled_count=count)
    cli = start(6, "mr3_gazebo_native_stop-2", 333, "native_stop_cli")
    exited(cli)
    exited(server)
    marker("complete", server_pid=222, stop_cli_pid=333,
           server_returncode=0, stop_cli_returncode=0)
    return "".join(lines), records


def rewrite_markers(text, rows):
    """Keep real SDK fixture lines while replacing only structured evidence."""
    rows = copy.deepcopy(rows)
    output, index = [], 0
    for line in text.splitlines(keepends=True):
        if AUDIT.ORDERED_SHUTDOWN_MARKER not in line:
            output.append(line)
        elif index < len(rows):
            rows[index]["receipt_index"] = index + 1
            output.append("[INFO] [launch.user]: " + AUDIT.ORDERED_SHUTDOWN_MARKER
                          + json.dumps(rows[index]) + "\n")
            index += 1
    return "".join(output)


@pytest.fixture
def saved_episode(tmp_path):
    FIXTURES.write_fixture(tmp_path)
    summary = json.loads((tmp_path / "summary.json").read_text())
    summary["closed"]["stop_sim_time_sec"] = 12.02
    receipt = nav2_fixture(summary["closed"])
    summary.update(shutdown_protocol=AUDIT.SHUTDOWN_PROTOCOL, nav2_shutdown=receipt,
                   training_finalize_request={"epoch": EPOCH, "ack_sequence": 2,
                                              "reason": "external_truncation"},
                   training_finalize_ack={"epoch": EPOCH, "ack_sequence": 2,
                                          "reason": "external_truncation",
                                          "kind": "training_finalize_ack"})
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    metadata["shutdown_protocol"] = AUDIT.SHUTDOWN_PROTOCOL
    shutdown = json.loads((tmp_path / "supervisor_shutdown.json").read_text())
    shutdown["owned_processes_seen"] += [
        {"pid": pid, "start_ticks": pid * 100, "state": "S"} for pid in (444, 555, 666, 777)]
    adapter = FIXTURES.adapter_rows(FIXTURES.transitions())
    adapter[-1]["payload"] = summary["closed"]
    text, records = launch_fixture(receipt["completed_wall_monotonic_ns"])
    text = FIXTURES.contact_fixture()[1] + text
    for name, value in (("metadata.json", metadata), ("summary.json", summary),
                        ("nav2_shutdown.json", receipt), ("supervisor_shutdown.json", shutdown)):
        (tmp_path / name).write_text(json.dumps(value))
    (tmp_path / "adapter.jsonl").write_text(
        "".join(json.dumps(row) + "\n" for row in adapter))
    (tmp_path / "launch.log").write_text(text)
    return tmp_path, receipt, summary, text, records


def test_complete_receipts_bind_lifecycle_actual_sdk_identity_and_final_ack(saved_episode):
    directory, _, _, _, _ = saved_episode
    result = AUDIT.audit_episode(directory)
    assert result["passed"], result["errors"]
    proof = result["ordered_shutdown"]
    assert proof["required"] and proof["proven"]
    assert proof["nav2"]["finalized_state_responses"] == 18
    assert proof["launch"]["serial_sigint_count"] == 2
    assert "nav2_shutdown.json" in result["evidence_sha256"]
    assert "no SDK internal-race claim" in proof["launch"]["scope"]


def test_legacy_episode_gets_no_ordered_credit_and_unknown_protocol_is_rejected(tmp_path):
    FIXTURES.write_fixture(tmp_path)
    result = AUDIT.audit_episode(tmp_path)
    assert result["passed"] and result["ordered_shutdown"]["required"] is False
    path = tmp_path / "metadata.json"
    metadata = json.loads(path.read_text())
    metadata["shutdown_protocol"] = "unknown_future_protocol"
    path.write_text(json.dumps(metadata))
    result = AUDIT.audit_episode(tmp_path)
    assert not result["passed"]
    assert any("unknown shutdown protocol" in error for error in result["errors"])


def test_declared_protocol_requires_file_and_summary_binding(saved_episode):
    directory, receipt, summary, _, _ = saved_episode
    summary["nav2_shutdown"] = {**receipt, "epoch": "different"}
    (directory / "summary.json").write_text(json.dumps(summary))
    assert not AUDIT.audit_episode(directory)["passed"]
    summary["nav2_shutdown"] = receipt
    (directory / "summary.json").write_text(json.dumps(summary))
    (directory / "nav2_shutdown.json").unlink()
    assert not AUDIT.audit_episode(directory)["passed"]


@pytest.mark.parametrize("case", [
    "wrong_epoch", "partial", "pending_goal", "wrong_command", "response_false",
    "response_numeric", "missing_state", "active_state", "wrong_service", "clock_advance",
    "overlap", "guard_changed", "invalid_wall_duration",
])
def test_lifecycle_receipt_cannot_claim_success_without_all_real_barriers(saved_episode, case):
    _, receipt, summary, _, _ = saved_episode
    if case == "wrong_epoch":
        receipt["epoch"] = "other"
    elif case == "partial":
        receipt["success"] = False
    elif case == "pending_goal":
        receipt["goal_ownership_closed"]["pending_goal_count"] = 1
    elif case == "wrong_command":
        receipt["robots"][0]["shutdown"]["command"] = 3
    elif case.startswith("response_"):
        receipt["robots"][0]["shutdown"]["response"]["success"] = (
            False if case == "response_false" else 1)
    elif case == "missing_state":
        receipt["robots"][2]["states"].pop()
    elif case == "active_state":
        receipt["robots"][1]["states"][3]["state"] = {"id": 3, "label": "active"}
    elif case == "wrong_service":
        receipt["robots"][0]["states"][0]["service"] = "/tb2/controller_server/get_state"
    elif case == "clock_advance":
        receipt["robots"][0]["states"][0]["response_clock_ns"] += 1000000
    elif case == "overlap":
        first, second = receipt["robots"][0]["states"][:2]
        for key in ("started_wall_monotonic_ns", "request_wall_monotonic_ns",
                    "completed_wall_monotonic_ns"):
            second[key] = first[key]
    elif case == "guard_changed":
        receipt["wall_guard_sec"] = 90.
    elif case == "invalid_wall_duration":
        receipt["robots"][0]["states"][0]["wall_duration_sec"] += .001
    summary["nav2_shutdown"] = receipt
    with pytest.raises(ValueError):
        AUDIT.audit_nav2_shutdown(receipt, summary, EPOCH)


@pytest.mark.parametrize("case", [
    "wrong_pid", "duplicate_action", "nonzero_exit", "overlapping_signals", "forward_order",
    "early_gazebo", "incomplete", "missing_sdk_signal", "wrong_sdk_exit", "foreign_epoch",
    "unknown_event", "wrong_role", "actual_sdk_overlap",
])
def test_sdk_receipts_cannot_hide_concurrent_or_unverified_shutdown(saved_episode, case):
    _, receipt, _, text, records = saved_episode
    if case == "wrong_pid":
        next(row for row in records if row["event"] == "signal")["pid"] = 999
    elif case == "duplicate_action":
        starts = [row for row in records if row["event"] == "process_started"]
        starts[1]["action_id"] = starts[0]["action_id"]
    elif case == "nonzero_exit":
        next(row for row in records if row["event"] == "process_exited")["returncode"] = -11
    elif case == "overlapping_signals":
        first_exit = next(index for index, row in enumerate(records)
                          if row["event"] == "process_exited" and row["controlled"])
        records[first_exit], records[first_exit + 1] = records[first_exit + 1], records[first_exit]
        records[first_exit]["wall_monotonic_ns"], records[first_exit + 1]["wall_monotonic_ns"] = (
            records[first_exit + 1]["wall_monotonic_ns"], records[first_exit]["wall_monotonic_ns"])
    elif case == "forward_order":
        next(row for row in records if row["event"] == "begin")["remaining"].reverse()
    elif case == "early_gazebo":
        next(row for row in records if row["event"] == "ros_complete")["event"] = "gz_stop"
    elif case == "incomplete":
        records.pop()
    elif case == "missing_sdk_signal":
        text = "".join(line for line in text.splitlines(keepends=True)
                       if "sending signal" not in line)
    elif case == "wrong_sdk_exit":
        text = text.replace("finished cleanly [pid 444]", "finished cleanly [pid 999]")
    elif case == "foreign_epoch":
        records[-1]["epoch"] = "other"
    elif case == "unknown_event":
        records[-1]["event"] = "pretend_complete"
    elif case == "wrong_role":
        records[0]["role"] = "owned_ros"
    elif case == "actual_sdk_overlap":
        lines = text.splitlines(keepends=True)
        earlier_exit = next(index for index, line in enumerate(lines)
                            if "mr3_adapter-5]: process has finished cleanly" in line)
        later_signal = next(index for index, line in enumerate(lines)
                            if "controller_server-4]: sending signal" in line)
        lines[earlier_exit], lines[later_signal] = lines[later_signal], lines[earlier_exit]
        text = "".join(lines)
    with pytest.raises(ValueError):
        AUDIT.audit_ordered_ros_shutdown(
            rewrite_markers(text, records), EPOCH, receipt["completed_wall_monotonic_ns"])


def test_real_unsignaled_clean_exit_can_remove_a_later_live_queue_member(saved_episode):
    _, receipt, _, _, _ = saved_episode
    text, _ = launch_fixture(receipt["completed_wall_monotonic_ns"], early_clean=True)
    proof = AUDIT.audit_ordered_ros_shutdown(text, EPOCH, receipt["completed_wall_monotonic_ns"])
    assert proof["serial_sigint_count"] == 1 and proof["all_actual_clean_exits"] == 6


def test_lifecycle_must_complete_before_actual_evaluator_exit(saved_episode):
    _, receipt, _, text, records = saved_episode
    evaluator_exit = next(row for row in records if row["event"] == "process_exited"
                          and row["process_name"].startswith("task_evaluator-"))
    with pytest.raises(ValueError, match="before actual Nav2 finalization"):
        AUDIT.audit_ordered_ros_shutdown(text, EPOCH, evaluator_exit["wall_monotonic_ns"] + 1)


@pytest.mark.parametrize("case", ["wrong_sequence", "missing_ack", "wrong_reason"])
def test_finalize_ack_is_the_actual_final_sealed_reward_receipt(saved_episode, case):
    _, receipt, summary, text, _ = saved_episode
    if case == "wrong_sequence":
        summary["training_finalize_ack"]["ack_sequence"] = 1
    elif case == "missing_ack":
        summary.pop("training_finalize_ack")
    else:
        summary["training_finalize_request"]["reason"] = "task_terminal"
    with pytest.raises(ValueError, match="actual ACK"):
        AUDIT.audit_ordered_shutdown(summary, receipt, text, FIXTURES.transitions(), EPOCH)


def test_declared_killed_worker_has_no_ordered_shutdown_or_complete_episode_credit(tmp_path):
    FIXTURES.write_fixture(tmp_path)
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    metadata["shutdown_protocol"] = AUDIT.SHUTDOWN_PROTOCOL
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    shutdown = json.loads((tmp_path / "supervisor_shutdown.json").read_text())
    shutdown.update(failed_sample=True, forced_shutdown=True, worker_returncode=-9)
    (tmp_path / "supervisor_shutdown.json").write_text(json.dumps(shutdown))
    result = AUDIT.audit_episode(tmp_path, expected_fault=True)
    assert result["passed"], result["errors"]
    assert not result["complete_episode_credit"]
    assert result["ordered_shutdown"]["required"]
    assert not result["ordered_shutdown"]["proven"]
