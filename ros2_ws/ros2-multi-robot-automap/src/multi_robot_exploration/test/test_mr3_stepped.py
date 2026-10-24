"""Paused snapshot barriers preserve real source ages and delivery cadence."""

import copy
import json
from types import MethodType, SimpleNamespace

from nav_msgs.msg import OccupancyGrid
import pytest

from test_mr3_adapter import make_adapter, message, state
from test_mr3_information import bridge, ControlledExecutor, grid
from multi_robot_exploration.mr3_information import IdealInformation


def ready_adapter():
    node, clock = make_adapter(started=False)
    clock[0] = 2.
    node.state = state(2., sequence=10)
    node.stepped_mode = True
    responses = []
    node.snapshot_response_pub.publish = responses.append
    observed_map = OccupancyGrid()
    observed_map.header.frame_id = "map"
    observed_map.info.resolution = .1
    observed_map.info.width = observed_map.info.height = 30
    observed_map.info.origin.orientation.w = 1.
    observed_map.data = [0] * 900
    node.receive_map(observed_map)
    for robot in node.dispatcher.robots:
        node.receive_local_map(robot, observed_map)
    metadata = {
        "epoch": node.epoch, "map_version": 2, "map_payload_sha256": node.map_digest,
        "map_source_stamp": 1., "map_received_stamp": 1.5,
        "map_sources": {robot: {
            "sequence": 1, "version": 1, "source_stamp": 1., "received_stamp": 1.5,
            "payload_sha256": node.local_map_digests[robot],
        } for robot in node.dispatcher.robots},
    }
    node.receive_map_metadata(message(metadata))
    # State's previous map bundle has deliberately not caught up via a new
    # simulation timer slot. Metadata alone supplies the coherent completion.
    node.state["map_payload_sha256"] = "older-map"
    return node, clock, responses


@pytest.mark.parametrize("blocked", (
    "state_missing", "state_stale", "state_future", "state_invalid", "map_missing",
    "metadata_missing", "fused_hash_mismatch", "local_missing", "local_hash_mismatch",
    "monitor_not_ready", "nav_server_not_ready", "not_stepped", "stopped", "already_started",
))
def test_initial_input_ack_requires_every_actually_delivered_startup_gate(blocked):
    node, clock, _ = ready_adapter()
    acknowledgments = []
    node.initial_inputs_ready_pub.publish = acknowledgments.append
    if blocked == "state_missing":
        node.state = None
    elif blocked == "state_stale":
        node.state["robots"][0]["source_stamp"] = 1.49
    elif blocked == "state_future":
        node.state["robots"][0]["source_stamp"] = 2.01
    elif blocked == "state_invalid":
        node.state["robots"][0]["valid"] = False
    elif blocked == "map_missing":
        node.map = None
    elif blocked == "metadata_missing":
        node.map_metadata = None
    elif blocked == "fused_hash_mismatch":
        node.map_metadata["map_payload_sha256"] = "another-map"
    elif blocked == "local_missing":
        del node.local_maps["tb1"]
    elif blocked == "local_hash_mismatch":
        node.map_metadata["map_sources"]["tb1"]["payload_sha256"] = "another-own-map"
    elif blocked == "monitor_not_ready":
        node.monitor_ready = False
    elif blocked == "nav_server_not_ready":
        node.navigation_clients["tb1"].server_is_ready = lambda: False
    elif blocked == "not_stepped":
        node.stepped_mode = False
    elif blocked == "stopped":
        node.stop_requested = True
    elif blocked == "already_started":
        node.started_at = clock[0]
    node.publish_initial_inputs_ready(clock[0])
    assert not acknowledgments and not node.initial_inputs_ready
    assert not any(kind == "initial_inputs_ready" for kind, _ in node.test_records)
    assert not node.test_starts and not node.test_observations


def test_initial_input_ack_is_once_only_and_does_not_start_encode_or_dispatch():
    node, clock, _ = ready_adapter()
    acknowledgments = []
    node.initial_inputs_ready_pub.publish = acknowledgments.append
    node.state["robots"][0].update({
        "tf_source_stamp": 1.9, "tf_validity_stamp": 2.1, "tf_validity_lead_sec": .2,
    })
    original_state, original_metadata = copy.deepcopy(node.state), copy.deepcopy(node.map_metadata)
    original_snapshot = copy.deepcopy(node.snapshot)
    node.maintain()
    assert len(acknowledgments) == 1 and node.initial_inputs_ready
    payload = json.loads(acknowledgments[0].data)
    assert payload["schema"] == "mr3-initial-inputs-ready-v1" and payload["epoch"] == node.epoch
    assert payload["stamp"] == clock[0] == 2. and payload["state_sequence"] == 10
    assert payload["map_payload_sha256"] == node.map_digest
    assert payload["map_source_stamp"] == 1. and payload["map_received_stamp"] == 1.5
    assert payload["map_sources"] == original_metadata["map_sources"]
    assert payload["robots"][0]["tf_source_stamp"] == 1.9
    assert payload["robots"][0]["tf_validity_stamp"] == 2.1
    assert payload["robots"][0]["tf_validity_lead_sec"] == .2
    assert "tf_source_stamp" not in payload["robots"][1]
    assert node.state == original_state and node.map_metadata == original_metadata
    assert node.snapshot == original_snapshot and node.sequence == 0 and node.encoding is None
    assert node.started_at is None and not node.test_starts and not node.test_observations
    assert not node.events and not node.transport.pending_count and node.dispatcher.closed
    assert not any(client.goals for client in node.navigation_clients.values())
    assert node.test_records == [("initial_inputs_ready", payload)]
    clock[0] = 2.02
    node.maintain()
    assert len(acknowledgments) == 1 and len(node.test_records) == 1


def test_initial_input_ack_waits_for_volatile_state_receipt_before_physics_can_pause():
    node, clock, _ = ready_adapter()
    acknowledgments = []
    node.initial_inputs_ready_pub.publish = acknowledgments.append
    node.state = None
    node.maintain()
    assert not acknowledgments and node.started_at is None
    node.receive_states(message(state(clock[0], sequence=10)))
    node.maintain()
    assert len(acknowledgments) == 1 and node.state["sequence"] == 10
    assert node.started_at is None and not node.test_starts and not node.test_observations


def request(node, request_id="step0", target=2000000000, **fields):
    node.receive_snapshot_request(message({
        "epoch": node.epoch, "request_id": request_id, "target_time_ns": target, **fields,
    }))


def test_explicit_snapshot_completes_while_paused_without_new_state_slot():
    node, clock, responses = ready_adapter()
    request(node)
    node.poll_snapshot()
    assert node.encoding is not None
    node.finish_observation()
    response = json.loads(responses[-1].data)
    assert response["ok"] and response["target_time_ns"] == 2000000000
    assert response["watermarks"]["state_sequence"] == 10
    assert response["watermarks"]["map_payload_sha256"] == node.map_digest
    assert response["snapshot"]["source_stamp"] == clock[0] == 2.
    assert response["snapshot"]["map_version"] == 2
    assert response["snapshot"]["map"]["source_age_sec"] == 1.
    assert response["snapshot"]["map"]["received_age_sec"] == .5
    assert node.state["sequence"] == 10
    assert node.state["map_payload_sha256"] == "older-map"
    assert not node.transport.pending_count


def test_duplicate_snapshot_request_is_cached_and_new_id_needs_new_physics_time():
    node, _, responses = ready_adapter()
    request(node)
    node.poll_snapshot()
    node.finish_observation()
    original = responses[-1].data
    sequence = node.sequence
    request(node)
    assert responses[-1].data == original and node.sequence == sequence
    request(node, "fake-step-at-same-time")
    assert json.loads(responses[-1].data)["error"] == "snapshot_target_not_advanced"
    assert node.sequence == sequence


def test_snapshot_waits_for_new_source_watermark_and_times_out_without_advancing():
    node, clock, responses = ready_adapter()
    request(node, minimum_state_sequence=10)
    node.poll_snapshot()
    assert node.encoding is None and not responses
    node.pending_snapshot["requested_wall"] -= 11.
    node.poll_snapshot()
    response = json.loads(responses[-1].data)
    assert response["error"] == "snapshot_watermark_timeout"
    assert response["diagnostics"]["state_sequence"] == 10
    assert not response["diagnostics"]["state_watermark_satisfied"]
    assert clock[0] == 2. and node.sequence == 0


def test_missing_state_snapshot_timeout_reports_actual_clock_and_matching_maps():
    node, _, responses = ready_adapter()
    node.state = None
    request(node, expected_map_sha256=node.map_digest, minimum_state_sequence=9)
    node.pending_snapshot["requested_wall"] -= 11.
    node.poll_snapshot()
    response = json.loads(responses[-1].data)
    diagnostics = response["diagnostics"]
    assert response["error"] == "snapshot_watermark_timeout"
    assert diagnostics["actual_clock_ns"] == 2000000000
    assert diagnostics["state_sequence"] is None
    assert not diagnostics["state_received"] and not diagnostics["states_fresh"]
    assert not diagnostics["state_watermark_satisfied"]
    assert diagnostics["expected_map_matches"] and diagnostics["map_inputs_match"]
    assert all(entry["received"] and entry["matches"]
               for entry in diagnostics["local_maps"].values())
    assert diagnostics["monitor_ready"] and diagnostics["started_at"] is None
    assert all(diagnostics["navigation_servers_ready"].values())
    assert node.started_at is None and node.state is None and node.encoding is None


def test_snapshot_waits_for_exact_drain_map_hash_instead_of_old_complete_pair():
    node, _, responses = ready_adapter()
    request(node, expected_map_sha256="1" * 64)
    node.poll_snapshot()
    assert node.encoding is None and not responses
    node.pending_snapshot["expected_map_sha256"] = node.map_digest
    node.poll_snapshot()
    node.finish_observation()
    assert json.loads(responses[-1].data)["watermarks"]["map_payload_sha256"] == node.map_digest


def test_action_rejection_keeps_safe_identity_and_malformed_json_has_none():
    node, _, _ = ready_adapter()
    node.receive_action(message({
        "epoch": "old", "command_id": 44, "observation_sequence": 12}))
    assert node.test_records[-1][1] == {
        "reason": "wrong_epoch", "command_id": 44, "observation_sequence": 12}
    node.receive_action(SimpleNamespace(data="[malformed"))
    assert node.test_records[-1][1]["command_id"] is None
    assert node.test_records[-1][1]["observation_sequence"] is None


def test_missed_target_does_not_fake_old_snapshot_time():
    node, _, responses = ready_adapter()
    request(node, target=1000000000)
    node.poll_snapshot()
    assert json.loads(responses[-1].data)["error"] == "snapshot_target_already_passed"
    assert node.encoding is None


def test_clock_advance_during_encoding_discards_old_snapshot_instead_of_publishing_it():
    node, clock, responses = ready_adapter()
    request(node)
    node.poll_snapshot()
    clock[0] = 2.02
    node.finish_observation()
    assert json.loads(responses[-1].data)["error"] == "clock_advanced_during_snapshot"
    assert not node.test_observations


def test_terminal_snapshot_preserves_stale_ages_without_relaxing_execution_safety():
    node, clock, responses = ready_adapter()
    node.started_at = 1.
    clock[0] = 3.
    node.monitor_ready = False
    node.receive_task_terminal(message({
        "epoch": node.epoch, "end_sim_time_sec": 3., "termination_reason": "collision"}))
    request(node, target=3000000000, allow_terminal=True, minimum_state_sequence=9)
    node.poll_snapshot()
    node.finish_observation()
    response = json.loads(responses[-1].data)
    assert response["ok"]
    assert response["snapshot"]["source_stamp"] == 3.
    assert all(not robot["fresh"] for robot in response["snapshot"]["robots"])
    assert all(robot["source_age_sec"] == 1. for robot in response["snapshot"]["robots"])
    assert response["snapshot"]["joint_action_mask"][888]
    assert sum(response["snapshot"]["joint_action_mask"]) == 1
    assert node.stop_requested and not node.events


def test_allow_terminal_cannot_bypass_missing_freshness_before_a_real_stop():
    node, clock, responses = ready_adapter()
    clock[0] = 3.
    request(node, target=3000000000, allow_terminal=True)
    node.poll_snapshot()
    assert node.encoding is None and not responses
    assert node.started_at is None


def test_normal_closure_and_preauthorized_snapshot_cannot_bypass_state_freshness():
    node, clock, responses = ready_adapter()
    node.started_at = 1.
    node.stop_requested = True
    clock[0] = 3.
    request(node, target=3000000000, allow_terminal=True)
    node.poll_snapshot()
    assert not node.terminal_snapshot_allowed()
    assert node.encoding is None and not responses
    assert node.task_terminal_notice is None


def test_terminal_notice_arriving_during_snapshot_wait_unblocks_without_file_or_new_state():
    node, clock, responses = ready_adapter()
    node.started_at = 1.
    node.monitor_ready = False
    clock[0] = 3.
    request(node, target=3000000000, allow_terminal=True, minimum_state_sequence=9)
    node.poll_snapshot()
    assert node.encoding is None and not responses and not node.stop_requested
    node.receive_task_terminal(message({
        "epoch": node.epoch, "end_sim_time_sec": 3., "termination_reason": "collision"}))
    node.maintain()
    node.finish_observation()
    response = json.loads(responses[-1].data)
    assert response["ok"] and node.stop_requested and node.dispatcher.stopped
    assert response["snapshot"]["source_stamp"] == 3.
    assert all(robot["source_stamp"] == 2. and robot["source_age_sec"] == 1.
               for robot in response["snapshot"]["robots"])
    assert node.state["sequence"] == 10 and node.started_at == 1.
    assert not node.test_starts


def test_future_terminal_notice_waits_for_real_clock_before_stopping_or_snapshot_override():
    node, clock, responses = ready_adapter()
    node.started_at = 1.
    node.monitor_ready = False
    notice = {"epoch": node.epoch, "end_sim_time_sec": 2.02,
              "termination_reason": "collision_monitoring_interrupted"}
    node.receive_task_terminal(message(notice))
    request(node, target=2020000000, allow_terminal=True, minimum_state_sequence=9)
    node.maintain()
    assert node.pending_task_terminal_notice == notice and node.task_terminal_notice is None
    assert not node.stop_requested and not node.dispatcher.stopped
    assert node.encoding is None and not responses
    clock[0] = 2.02
    node.maintain()
    node.finish_observation()
    assert node.task_terminal_notice == notice and node.pending_task_terminal_notice is None
    assert node.stop_requested and node.dispatcher.stopped
    assert json.loads(responses[-1].data)["ok"]
    assert node.state["robots"][0]["source_stamp"] == 2.


def test_terminal_notice_still_waits_for_the_drained_state_sequence():
    node, _, responses = ready_adapter()
    node.started_at = 1.
    node.monitor_ready = False
    node.receive_task_terminal(message({
        "epoch": node.epoch, "end_sim_time_sec": 2., "termination_reason": "collision"}))
    request(node, allow_terminal=True, minimum_state_sequence=10)
    node.poll_snapshot()
    assert node.encoding is None and not responses
    node.receive_states(message(state(2., sequence=11)))
    node.poll_snapshot()
    node.finish_observation()
    assert json.loads(responses[-1].data)["watermarks"]["state_sequence"] == 11


@pytest.mark.parametrize("changes", (
    {"epoch": "other-episode"}, {"termination_reason": "training_external_truncation"},
    {"termination_reason": "shutdown"}, {"end_sim_time_sec": True},
    {"end_sim_time_sec": float("nan")}, {"end_sim_time_sec": .5}, {"grid": [0, 1]},
))
def test_invalid_or_other_epoch_terminal_notice_cannot_stop_or_relax_snapshot(changes):
    node, _, _ = ready_adapter()
    node.started_at = 1.
    notice = {"epoch": node.epoch, "end_sim_time_sec": 2., "termination_reason": "collision"}
    notice.update(changes)
    node.receive_task_terminal(message(notice))
    assert node.task_terminal_notice is None and node.pending_task_terminal_notice is None
    assert not node.stop_requested and not node.dispatcher.stopped


def test_terminal_notice_cannot_release_or_start_an_unstarted_episode():
    node, _, _ = ready_adapter()
    node.receive_task_terminal(message({
        "epoch": node.epoch, "end_sim_time_sec": 2., "termination_reason": "collision"}))
    assert node.started_at is None and node.task_terminal_notice is None
    assert not node.stop_requested and not node.test_starts and not node.test_observations


def test_map_completion_metadata_does_not_resend_or_refresh_state_sources():
    node = bridge()
    node.map_executor = ControlledExecutor()
    node.local_maps = {"tb1": grid([0, -1, 100], stamp=1)}
    node.local_map_versions = {"tb1": 1}
    node.publish_maps = lambda: None
    IdealInformation.publish_maps(node)
    node.map_executor.complete_next()
    node.finish_maps()
    metadata = json.loads(node.map_metadata_publisher.messages[-1].data)
    assert metadata["map_sources"]["tb1"]["source_stamp"] == 1.
    assert metadata["map_sources"]["tb1"]["received_stamp"] == 2.
    assert not node.state_publisher.messages and node.state_sequence == 0
    node.finish_maps()
    assert len(node.map_metadata_publisher.messages) == 1


def drain_bridge():
    node = bridge()
    responses = []
    ready = {"map": False, "state": False}
    node.stepped_mode = True
    node.pending_drain = None
    node.drain_responses = {}
    node.drain_timeout_sec = 10.
    node.drain_publisher = SimpleNamespace(publish=responses.append)
    node.map_timer = SimpleNamespace(is_ready=lambda: ready["map"])
    node.state_timer = SimpleNamespace(is_ready=lambda: ready["state"])
    node.get_clock = lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=2000000000))
    for name in ("receive_drain_request", "poll_drain", "maintain_deliveries"):
        setattr(node, name, MethodType(getattr(IdealInformation, name), node))
    return node, ready, responses


def test_information_barrier_waits_for_due_simulation_slots_and_existing_map_worker():
    node, ready, responses = drain_bridge()
    node.map_executor = ControlledExecutor()
    node.local_maps = {"tb1": grid([0, -1, 100])}
    node.local_map_versions = {"tb1": 1}
    IdealInformation.publish_maps(node)
    payload = {"epoch": node.epoch, "request_id": "drain1", "target_time_ns": 2000000000}
    node.receive_drain_request(message(payload))
    node.maintain_deliveries()
    assert not responses
    node.map_executor.complete_next()
    ready["map"] = True
    node.maintain_deliveries()
    assert not responses
    ready["map"] = False
    ready["state"] = True
    node.maintain_deliveries()
    assert not responses
    ready["state"] = False
    node.maintain_deliveries()
    reply = json.loads(responses[-1].data)
    assert reply["ok"] and reply["map_payload_sha256"] == node.map_payload_sha256
    assert reply["state_sequence"] == 0
    assert not node.state_publisher.messages
    assert node.received.get("map", "tb1").source_stamp == 1.
    assert node.received.get("map", "tb1").received_stamp == 2.
    count = node.map_diagnostics["submitted"]
    node.receive_drain_request(message(payload))
    assert node.map_diagnostics["submitted"] == count
    assert len(responses) == 2


def test_information_barrier_has_bounded_wall_failure_without_inventing_a_map():
    node, _, responses = drain_bridge()
    node.receive_drain_request(message({
        "epoch": node.epoch, "request_id": "drain1", "target_time_ns": 2000000000}))
    node.pending_drain["requested_wall"] -= 11.
    node.poll_drain()
    assert json.loads(responses[-1].data)["error"] == "information_drain_wall_timeout"
    assert node.map_version == 0 and not node.state_publisher.messages
