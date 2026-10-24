"""Paused state commits exercise real publication methods without ROS/native startup."""

import copy
import json
from types import SimpleNamespace, MethodType

import pytest
from std_msgs.msg import String

from multi_robot_exploration.mr3_information import IdealInformation, payload_digest
from test_mr3_information import (
    Publisher, input_odom, input_rows, input_tf, state_input_bridge,
)


def request(node, operation="commit", identifier="phase1", target=None):
    value = {"schema": "mr3-state-phase-request-v1", "epoch": node.epoch,
             "request_id": identifier, "operation": operation,
             "target_time_ns": node.clock_ns if target is None else target}
    node.receive_state_phase_request(String(data=json.dumps(value)))
    return value


def ack(node):
    return json.loads(node.state_phase_publisher.messages[-1].data)


def fresh(node, tf_source=None):
    for name in node.names:
        IdealInformation.receive_local_odom(node, name, input_odom(node.clock_ns - 10_000_000))
        IdealInformation.receive_local_tf(node, name, input_tf(
            node.clock_ns - 100_000_000 if tf_source is None else tf_source))


def test_takeover_acks_real_callback_without_state_or_side_publication():
    node = state_input_bridge()
    request(node, operation="takeover")
    assert node.state_phase_controlled and ack(node)["ok"]
    assert ack(node)["operation"] == "takeover"
    assert ack(node)["state_sequence"] is None and ack(node)["bundle_sha256"] is None
    assert ack(node)["robots"] == {}
    assert not node.state_publisher.messages
    assert not any(p.messages for p in node.odom_publishers.values())


def test_paused_commit_waits_for_late_causal_tf_and_publishes_once_without_clock_advance():
    node = state_input_bridge()
    node.clock_ns = 74_340_000_000
    fresh(node, tf_source=73_795_000_000)
    request(node)
    assert node.pending_state_phase is not None
    assert node.state_sequence == 0 and not node.state_phase_publisher.messages
    assert not input_rows(node, "state_selection")
    for name in node.names:
        IdealInformation.receive_local_tf(node, name, input_tf(74_195_000_000))
    node.poll_state_phase()
    assert node.clock_ns == 74_340_000_000
    assert node.pending_state_phase is None and node.state_sequence == 1
    assert ack(node)["ok"] and ack(node)["clock_ns"] == node.clock_ns
    assert all(item["tf_source_ns"] == 74_195_000_000 for item in ack(node)["robots"].values())
    assert len(node.state_publisher.messages) == 1


def test_commit_acks_exact_published_bundle_envelopes_side_hashes_and_publish_windows():
    node = state_input_bridge()
    fresh(node)
    request(node)
    value = ack(node)
    publication = input_rows(node, "state_publish")[-1]["payload"]
    bundle = json.loads(node.state_publisher.messages[-1].data)
    assert value["bundle_sha256"] == payload_digest(bundle)
    assert value["state_sequence"] == publication["message"]["sequence"]
    assert (value["side_publish_started_wall_monotonic_ns"]
            <= value["bundle_publish_started_wall_monotonic_ns"]
            <= value["bundle_publish_completed_wall_monotonic_ns"])
    for name, binding in value["robots"].items():
        envelope = publication["envelopes"][name]
        assert binding["sequence"] == envelope["sequence"]
        assert binding["version"] == envelope["version"]
        assert binding["source_stamp"] == envelope["source_stamp"]
        assert binding["odom_sha256"] == payload_digest(envelope["payload"]["odometry"])
        assert binding["tf_sha256"] == payload_digest(envelope["payload"]["transform"])
    assert value["scope"] == "actual_state_and_side_publish_calls_returned"


def test_controlled_timer_and_duplicate_request_cannot_replace_committed_bundle():
    node = state_input_bridge()
    fresh(node)
    value = request(node)
    original = copy.deepcopy(ack(node))
    for name in node.names:
        IdealInformation.receive_local_tf(node, name, input_tf(node.clock_ns - 1))
    IdealInformation.publish_states(node)
    node.receive_state_phase_request(String(data=json.dumps(value)))
    assert ack(node) == original
    assert node.state_sequence == 1 and len(node.state_publisher.messages) == 1
    assert all(len(p.messages) == 1 for p in node.odom_publishers.values())
    assert input_rows(node, "state_phase_ack")[-1]["payload"]["cached"] is True


@pytest.mark.parametrize("change,error", [
    ({"target_time_ns": 2_020_000_000}, "state_phase_request_id_conflict"),
    ({"request_id": "other"}, "state_phase_clock_already_committed"),
])
def test_commit_identity_conflicts_do_not_republish(change, error):
    node = state_input_bridge()
    fresh(node)
    value = request(node)
    value.update(change)
    node.receive_state_phase_request(String(data=json.dumps(value)))
    assert not ack(node)["ok"] and ack(node)["error"] == error
    assert node.state_sequence == 1


def test_later_commit_at_new_clock_uses_new_side_publication_window_even_for_same_raw():
    node = state_input_bridge()
    fresh(node)
    request(node)
    previous = ack(node)
    node.clock_ns += 20_000_000
    request(node, identifier="phase2")
    latest = ack(node)
    assert latest["state_sequence"] == 2
    assert latest["robots"]["tb1"]["odom_sha256"] == previous["robots"]["tb1"]["odom_sha256"]
    assert (latest["side_publish_started_wall_monotonic_ns"]
            > previous["bundle_publish_completed_wall_monotonic_ns"])


def test_commit_waits_for_exact_node_clock_and_cannot_publish_in_future():
    node = state_input_bridge()
    fresh(node)
    target = node.clock_ns + 20_000_000
    request(node, target=target)
    assert not node.state_phase_publisher.messages and node.state_sequence == 0
    node.clock_ns = target
    node.poll_state_phase()
    assert ack(node)["ok"] and ack(node)["clock_ns"] == target


@pytest.mark.parametrize("reason", ["timeout", "passed"])
def test_unavailable_commit_fails_boundedly_and_stops_future_progress(reason):
    node = state_input_bridge()
    request(node)
    if reason == "timeout":
        node.pending_state_phase["requested_wall"] -= 11.
    else:
        node.clock_ns += 1
    node.poll_state_phase()
    assert not ack(node)["ok"]
    assert ack(node)["error"] == ("state_phase_wall_timeout" if reason == "timeout"
                                  else "state_phase_target_passed")
    assert node.clock_failed and node.map_failure_publisher.messages
    assert node.state_sequence == 0


@pytest.mark.parametrize("field,value", [
    ("epoch", "other"), ("target_time_ns", True), ("operation", "unknown"),
    ("schema", "unknown"), ("request_id", ""),
])
def test_invalid_phase_request_is_rejected_without_publication(field, value):
    node = state_input_bridge()
    data = {"schema": "mr3-state-phase-request-v1", "epoch": node.epoch,
            "request_id": "phase", "operation": "commit", "target_time_ns": node.clock_ns}
    data[field] = value
    node.receive_state_phase_request(String(data=json.dumps(data)))
    assert not ack(node)["ok"] and node.state_sequence == 0


def test_nonstepped_rejects_phase_and_retains_periodic_publication():
    node = state_input_bridge()
    node.stepped_mode = False
    fresh(node)
    request(node)
    assert not ack(node)["ok"] and not node.state_phase_controlled
    IdealInformation.publish_states(node)
    assert node.state_sequence == 1


def test_controlled_snapshot_drain_reuses_commit_without_late_state_publication():
    node = state_input_bridge()
    fresh(node)
    request(node)
    original = ack(node)
    node.pending_drain = {"epoch": node.epoch, "request_id": "drain",
                          "target_time_ns": node.clock_ns, "requested_wall": 10**20}
    node.drain_timeout_sec = 10.
    node.drain_responses = {}
    node.drain_publisher = Publisher()
    node.map_payload_sha256 = "mapsha"
    node.map_timer = SimpleNamespace(is_ready=lambda: False)
    node.state_timer = SimpleNamespace(is_ready=lambda: True)
    node.poll_drain = MethodType(IdealInformation.poll_drain, node)
    for name in node.names:
        IdealInformation.receive_local_tf(node, name, input_tf(node.clock_ns - 1))
    node.poll_drain()
    response = json.loads(node.drain_publisher.messages[-1].data)
    assert response["ok"] and response["state_sequence"] == original["state_sequence"]
    assert response["state_bundle_sha256"] == original["bundle_sha256"]
    assert node.state_sequence == 1 and len(node.state_publisher.messages) == 1


def drain_ready_node():
    node = state_input_bridge()
    fresh(node)
    request(node)
    node.pending_drain = None
    node.drain_responses = {}
    node.drain_timeout_sec = 10.
    node.drain_publisher = Publisher()
    node.map_payload_sha256 = "mapsha"
    node.map_timer = SimpleNamespace(is_ready=lambda: False)
    node.state_timer = SimpleNamespace(is_ready=lambda: True)
    node.poll_drain = MethodType(IdealInformation.poll_drain, node)
    node.receive_drain_request = MethodType(IdealInformation.receive_drain_request, node)
    return node


@pytest.mark.parametrize("notice,allow,ready", [
    (None, True, False),
    ({"epoch": "episode-a", "end_sim_time_sec": 2.02,
      "termination_reason": "coverage_reached"}, False, False),
    ({"epoch": "episode-a", "end_sim_time_sec": 2.02,
      "termination_reason": "coverage_reached"}, True, True),
    ({"epoch": "other", "end_sim_time_sec": 2.02,
      "termination_reason": "coverage_reached"}, True, False),
    ({"epoch": "episode-a", "end_sim_time_sec": 2.04,
      "termination_reason": "coverage_reached"}, True, False),
])
def test_terminal_only_drain_needs_actual_matching_notice_and_never_refreshes_source(
        notice, allow, ready):
    node = drain_ready_node()
    original = copy.deepcopy(node.state_phase_last_commit)
    node.clock_ns += 20_000_000
    if notice:
        node.receive_state_terminal(String(data=json.dumps(notice)))
    data = {"epoch": node.epoch, "request_id": "drain", "target_time_ns": node.clock_ns,
            "allow_terminal": allow}
    node.receive_drain_request(String(data=json.dumps(data)))
    node.poll_drain()
    assert bool(node.drain_publisher.messages) is ready
    if ready:
        value = json.loads(node.drain_publisher.messages[-1].data)
        assert value["state_reuse_scope"] == "terminal_last_committed"
        assert value["state_commit_clock_ns"] == original["clock_ns"]
        assert value["state_sequence"] == original["state_sequence"]
        assert value["state_bundle_sha256"] == original["bundle_sha256"]
        assert value["terminal_notice"] == notice
    assert node.state_sequence == 1 and len(node.state_publisher.messages) == 1


def test_terminal_drain_cached_identity_cannot_be_reused_as_live_request():
    node = drain_ready_node()
    node.clock_ns += 20_000_000
    node.receive_state_terminal(String(data=json.dumps({
        "epoch": node.epoch, "end_sim_time_sec": 2.02, "termination_reason": "coverage_reached"})))
    data = {"epoch": node.epoch, "request_id": "drain", "target_time_ns": node.clock_ns,
            "allow_terminal": True}
    node.receive_drain_request(String(data=json.dumps(data)))
    node.poll_drain()
    assert json.loads(node.drain_publisher.messages[-1].data)["ok"]
    data["allow_terminal"] = False
    node.receive_drain_request(String(data=json.dumps(data)))
    failure = json.loads(node.drain_publisher.messages[-1].data)
    assert failure["error"] == "drain_request_id_conflict"


def test_publication_failure_clears_pending_and_explicitly_fails_closed():
    node = state_input_bridge()
    fresh(node)
    node.publish_states = lambda **kwargs: (_ for _ in ()).throw(ValueError("failed publish"))
    request(node)
    assert node.pending_state_phase is None and node.clock_failed
    assert not ack(node)["ok"] and "publication_failed" in ack(node)["error"]
    assert node.map_failure_publisher.messages


def test_real_terminal_cancels_waiting_commit_without_infrastructure_failure_or_new_bundle():
    node = drain_ready_node()
    original = copy.deepcopy(node.state_phase_last_commit)
    node.clock_ns += 600_000_000
    value = request(node, identifier="pending_stale")
    assert node.pending_state_phase is not None and node.state_sequence == 1
    notice = {"epoch": node.epoch, "end_sim_time_sec": node.clock_ns / 1e9,
              "termination_reason": "coverage_reached"}
    node.receive_state_terminal(String(data=json.dumps(notice)))
    cancelled = copy.deepcopy(ack(node))
    assert not cancelled["ok"] and cancelled["error"] == "state_phase_task_terminal"
    assert cancelled["terminal_notice"] == notice
    assert node.pending_state_phase is None and not node.clock_failed
    assert not node.map_failure_publisher.messages
    fresh(node)
    node.poll_state_phase()
    node.publish_states()
    node.receive_state_phase_request(String(data=json.dumps(value)))
    assert ack(node) == cancelled
    assert node.state_phase_last_commit == original
    assert node.state_sequence == 1
    node.receive_drain_request(String(data=json.dumps({
        "epoch": node.epoch, "request_id": "terminal", "target_time_ns": node.clock_ns,
        "allow_terminal": True})))
    node.poll_drain()
    assert json.loads(node.drain_publisher.messages[-1].data)["state_bundle_sha256"] == original[
        "bundle_sha256"]
