"""Check ideal action deliveries, input boundaries and exclusive ownership."""

from collections import deque
from concurrent.futures import Future as EncodingFuture
import json
import math
from types import MethodType, SimpleNamespace

from builtin_interfaces.msg import Time
from nav_msgs.msg import OccupancyGrid
import pytest
from rclpy.task import Future
from std_msgs.msg import Header, String

from multi_robot_exploration.mr3_adapter import MR3Adapter, ROBOTS
from multi_robot_exploration.mr3_owner import acquire_navigation_owner
from multi_robot_exploration.mr3_protocol import GoalDispatcher
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore


def message(payload):
    result = String()
    result.data = json.dumps(payload)
    return result


def stamp(now):
    return Time(sec=int(now), nanosec=round((now - int(now)) * 1e9))


def state(now=1.0, sequence=1, epoch="episode-a"):
    return {
        "epoch": epoch, "sequence": sequence, "map_version": 1,
        "map_source_stamp": now, "map_received_stamp": now, "map_sources": {},
        "robots": [
            {"name": name, "epoch": epoch, "sequence": sequence, "version": sequence,
             "x": float(index), "y": 0.0, "yaw": 0.0, "v": 0.0, "w": 0.0,
             "valid": True, "source_stamp": now, "received_stamp": now}
            for index, name in enumerate(ROBOTS)
        ],
    }


class Client:
    def __init__(self):
        self.goals = []
        self.responses = []

    def server_is_ready(self):
        return True

    def send_goal_async(self, goal):
        self.goals.append(goal)
        response = Future()
        self.responses.append(response)
        return response


class Handle:
    accepted = True

    def __init__(self):
        self.goal_id = SimpleNamespace(uuid=[1] * 16)
        self.result = Future()
        self.cancel = Future()
        self.cancel_calls = 0

    def get_result_async(self):
        return self.result

    def cancel_goal_async(self):
        self.cancel_calls += 1
        return self.cancel


def make_adapter(started=True):
    clock = [1.0]
    records, stopped, failures, starts, observations = [], [], [], [], []
    events = deque()

    def encode(function, *args, **kwargs):
        future = EncodingFuture()
        future.set_result(function(*args, **kwargs))
        return future

    node = SimpleNamespace(
        epoch="episode-a", events=events,
        dispatcher=GoalDispatcher("episode-a", events.append),
        transport=IdealTransport("episode-a"), received=ReceivedStore("episode-a"),
        navigation_clients={name: Client() for name in ROBOTS}, handles={},
        now=lambda: clock[0],
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(
            to_msg=lambda: stamp(clock[0]), nanoseconds=round(clock[0] * 1e9))),
        record=lambda kind, payload: records.append((kind, payload)),
        started_at=1.0 if started else None, stop_requested=False, stop_acknowledged=False,
        pending_stop=None, map_digest=None, local_maps={}, local_map_digests={},
        encoder=SimpleNamespace(submit=encode), encoding=None,
        stepped_mode=False, pending_snapshot=None, encoding_request=None, map_metadata=None,
        initial_inputs_ready=False,
        task_terminal_notice=None, pending_task_terminal_notice=None,
        initial_inputs_ready_pub=SimpleNamespace(publish=lambda msg: None),
        snapshot_responses={}, snapshot_timeout_sec=10., last_snapshot_target_ns=None,
        snapshot_response_pub=SimpleNamespace(publish=lambda msg: None),
        last_command_id=-1, last_command_payload=None, last_state_sequence=-1,
        command_receipt=None, sequence=0, last_heartbeat=-math.inf,
        receipt_metadata={name: {} for name in ROBOTS},
        history={name: deque(maxlen=16) for name in ROBOTS},
        state=state(), snapshot=None, map=None, monitor_ready=True,
        stop_pub=SimpleNamespace(publish=stopped.append),
        failure_pub=SimpleNamespace(publish=failures.append),
        start_pub=SimpleNamespace(publish=starts.append),
        observation_pub=SimpleNamespace(publish=observations.append),
        get_node_names_and_namespaces=lambda: [],
    )
    for name, method in vars(MR3Adapter).items():
        if callable(method) and name not in ("__init__", "now", "record", "destroy_node"):
            setattr(node, name, MethodType(method, node))
    node.test_records = records
    node.test_stopped = stopped
    node.test_failures = failures
    node.test_starts = starts
    node.test_observations = observations
    refresh_snapshot(node)
    return node, clock


def refresh_snapshot(node, legal=(88, 888, 999)):
    node.snapshot = {
        "sequence": node.sequence + 1, "digest": "saved-observation-digest",
        "robots": [{"name": name, "navigation": navigation}
                   for name, navigation in node.dispatcher.navigation().items()],
        "candidates": [{"x": 5.0 + index, "y": 0.0} for index in range(8)],
        "joint_action_mask": [action in legal for action in range(1000)],
    }


def command(node, action=88, command_id=1, **changes):
    payload = {
        "epoch": node.epoch, "command_id": command_id,
        "observation_sequence": node.snapshot["sequence"],
        "observation_digest": node.snapshot["digest"],
        "created_at": node.now(), "expires_at": node.now() + 2.0, "action": action,
    }
    payload.update(changes)
    return message(payload)


def advance(node, clock, now, fresh=True):
    clock[0] = now
    if fresh:
        node.state = state(now, sequence=int(now * 1000))
    node.maintain()


def accepted_goal(node, clock):
    node.receive_action(command(node))
    node.maintain()
    assert len(node.navigation_clients["tb1"].goals) == 1
    goal_id = node.dispatcher.navigation()["tb1"]["goal_id"]
    handle = Handle()
    node.navigation_clients["tb1"].responses[0].set_result(handle)
    assert node.dispatcher.navigation()["tb1"]["phase"] == "accepting"
    advance(node, clock, 1.1)
    assert node.dispatcher.navigation()["tb1"]["phase"] == "active"
    return goal_id, handle


def test_navigation_owner_lock_excludes_other_mode_and_releases(monkeypatch):
    monkeypatch.setenv("ROS_DOMAIN_ID", "212")
    first = acquire_navigation_owner()
    try:
        with pytest.raises(RuntimeError, match="already has a goal owner"):
            acquire_navigation_owner()
    finally:
        first.close()
    acquire_navigation_owner().close()


@pytest.mark.parametrize("changes,reason", [
    ({"epoch": "old-episode"}, "wrong_epoch"),
    ({"expires_at": 1.0}, "expired_or_invalid_command_time"),
    ({"created_at": 1.1}, "expired_or_invalid_command_time"),
    ({"expires_at": 4.0}, "expired_or_invalid_command_time"),
    ({"observation_digest": "changed"}, "stale_observation"),
    ({"observation_sequence": 0}, "stale_observation"),
    ({"action": True}, "invalid_joint_action"),
    ({"action": 1000}, "invalid_joint_action"),
    ({"action": 0}, "masked_action"),
])
def test_invalid_joint_action_never_reaches_native_client(changes, reason):
    node, _ = make_adapter()
    node.receive_action(command(node, **changes))
    assert node.test_records[-1] == ("action_rejected", {
        "reason": reason, "command_id": 1,
        "observation_sequence": changes.get("observation_sequence", 1)})
    assert node.dispatcher.closed
    assert not node.events
    assert not any(client.goals for client in node.navigation_clients.values())


def test_navigation_change_invalidates_saved_action_before_any_robot_is_submitted():
    node, _ = make_adapter()
    node.dispatcher.submit("tb2", "GOAL", 1., 1, 0, 3., goal={"x": 7., "y": 0.})
    count = len(node.events)
    node.receive_action(command(node))
    assert node.test_records[-1][1]["reason"] == "navigation_changed_since_observation"
    assert len(node.events) == count
    assert node.dispatcher.navigation()["tb1"]["goal_id"] is None


def test_callbacks_update_backend_only_after_delivery_and_preserve_event_fields():
    node, clock = make_adapter()
    goal_id, handle = accepted_goal(node, clock)
    goal = node.navigation_clients["tb1"].goals[0]
    assert goal.pose.header.frame_id == "map"
    assert goal.pose.pose.position.x == 5.0 and goal.pose.pose.position.y == 0.0
    assert goal.pose.pose.orientation.w == 1.0
    deliveries = [payload for kind, payload in node.test_records if kind == "delivery"]
    command_delivery = next(row for row in deliveries if row["stream"] == "command")
    assert command_delivery["payload"]["goal_id"] == goal_id
    assert command_delivery["payload"]["command_id"] == 1
    assert command_delivery["payload"]["observation_version"] == 1
    receipt = next(row for row in deliveries if row["stream"] == "receipt")
    assert receipt["payload"]["type"] == "accept"
    assert receipt["source_stamp"] == 1.0 and receipt["received_stamp"] == 1.1
    handle.result.set_result(SimpleNamespace(status=4))
    assert not node.dispatcher.closed
    advance(node, clock, 1.35)
    assert node.dispatcher.closed
    assert node.dispatcher.navigation()["tb1"]["last_terminal"] == "SUCCEEDED"


def test_duplicate_action_and_keep_do_not_submit_again_or_renew_by_callback():
    node, clock = make_adapter()
    original = command(node)
    node.receive_action(original)
    node.receive_action(original)
    node.maintain()
    assert len(node.navigation_clients["tb1"].goals) == 1
    handle = Handle()
    node.navigation_clients["tb1"].responses[0].set_result(handle)
    advance(node, clock, 1.1)
    refresh_snapshot(node)
    node.receive_action(command(node, 888, 2))
    advance(node, clock, 1.2)
    assert len(node.navigation_clients["tb1"].goals) == 1
    assert not handle.cancel_calls


def test_lease_heartbeats_cover_pending_acceptance_without_duplicate_goals():
    node, clock = make_adapter()
    node.receive_action(command(node))
    node.maintain()
    for index in range(1, 31):
        advance(node, clock, round(1 + .1 * index, 3))
    assert not node.dispatcher.failed
    assert node.dispatcher.navigation()["tb1"]["phase"] == "accepting"
    assert node.dispatcher.navigation()["tb1"]["lease_until"] > 4.
    assert len(node.navigation_clients["tb1"].goals) == 1


def test_task_stop_requires_real_terminal_and_never_acknowledges_cancel_response_alone():
    node, clock = make_adapter()
    _, handle = accepted_goal(node, clock)
    request = Header(stamp=stamp(1.1), frame_id="map")
    node.receive_stop(request)
    advance(node, clock, 1.15)
    assert handle.cancel_calls == 1
    handle.cancel.set_result(SimpleNamespace(
        goals_canceling=[SimpleNamespace(goal_id=handle.goal_id)]))
    advance(node, clock, 1.4)
    assert not node.test_stopped and not node.dispatcher.closed
    handle.result.set_result(SimpleNamespace(status=5))
    advance(node, clock, 1.65)
    assert node.dispatcher.closed and len(node.test_stopped) == 1
    assert json.loads(node.test_stopped[0].data)["pending_goal_count"] == 0
    advance(node, clock, 1.7)
    assert len(node.test_stopped) == 1


def test_queued_goal_stopped_before_delivery_never_executes():
    node, clock = make_adapter()
    node.receive_action(command(node))
    clock[0] = 1.05
    node.receive_stop(Header(stamp=stamp(1.05), frame_id="map"))
    advance(node, clock, 1.1)
    advance(node, clock, 1.4)
    assert not any(client.goals for client in node.navigation_clients.values())
    assert node.dispatcher.closed
    assert not node.dispatcher.failed
    assert len(node.test_stopped) == 1


def test_queued_goal_expired_before_delivery_never_executes_and_failure_is_retained():
    node, clock = make_adapter()
    node.receive_action(command(node, expires_at=1.2))
    advance(node, clock, 1.3)
    advance(node, clock, 1.6)
    assert not any(client.goals for client in node.navigation_clients.values())
    assert node.dispatcher.failed
    assert node.dispatcher.closed
    assert node.test_failures


def test_state_sequence_and_epoch_cannot_roll_back_received_state_or_history():
    node, _ = make_adapter()
    node.state = None
    node.receive_states(message(state(1., 10)))
    node.receive_states(message(state(.9, 9)))
    assert node.state["sequence"] == 10
    node.receive_states(message(state(1., 11, "old-epoch")))
    assert node.state["sequence"] == 10
    assert all(history[-1]["source_stamp"] == 1. for history in node.history.values())


@pytest.mark.parametrize("source_stamp", [0.1, 2.0])
def test_initial_state_valid_flag_cannot_bypass_stamp_freshness(source_stamp):
    node, _ = make_adapter(started=False)
    grid = OccupancyGrid()
    grid.header.frame_id = "map"
    grid.info.resolution = .1
    grid.info.width = grid.info.height = 20
    grid.info.origin.orientation.w = 1.
    grid.data = [0] * 400
    node.map = grid
    node.state = state(source_stamp)
    node.publish_observation()
    assert node.started_at is None
    assert not node.test_starts


def test_map_bytes_and_metadata_must_match_before_task_start():
    node, _ = make_adapter(started=False)
    grid = OccupancyGrid()
    grid.header.frame_id = "map"
    grid.info.resolution = .1
    grid.info.width = grid.info.height = 20
    grid.info.origin.orientation.w = 1.
    grid.data = [0] * 400
    node.receive_map(grid)
    node.state["map_payload_sha256"] = "different-map-payload"
    node.publish_observation()
    assert node.started_at is None and not node.test_observations
    node.state["map_payload_sha256"] = node.map_digest
    for name in ROBOTS:
        node.receive_local_map(name, grid)
        node.state["map_sources"][name] = {
            "payload_sha256": node.local_map_digests[name], "source_stamp": 1.,
            "received_stamp": 1., "version": 1, "sequence": 1,
        }
    node.publish_observation()
    node.finish_observation()
    assert node.started_at == 1.0 and len(node.test_observations) == 1
    assert json.loads(node.test_observations[0].data)["map_version"] == 1


def test_stale_received_state_cancels_owned_navigation_and_stops_renewing_lease():
    node, clock = make_adapter()
    _, handle = accepted_goal(node, clock)
    advance(node, clock, 1.7, fresh=False)
    assert node.stop_requested
    assert handle.cancel_calls == 1
    assert node.test_failures


def test_invalid_stop_epoch_window_cannot_cancel_current_task():
    node, _ = make_adapter()
    for request in (Header(stamp=stamp(.9), frame_id="map"),
                    Header(stamp=stamp(2.), frame_id="map"),
                    Header(stamp=stamp(1.), frame_id="odom")):
        node.receive_stop(request)
    assert not node.stop_requested


def test_future_stop_request_is_applied_once_simulation_clock_catches_up():
    node, clock = make_adapter()
    _, handle = accepted_goal(node, clock)
    node.receive_stop(Header(stamp=stamp(1.5), frame_id="map"))
    advance(node, clock, 1.4)
    assert not node.stop_requested and not handle.cancel_calls
    advance(node, clock, 1.5)
    assert node.stop_requested and handle.cancel_calls == 1


def test_native_rpc_error_keeps_unknown_owner_for_late_result_closure():
    node, _ = make_adapter()
    node.receive_action(command(node))
    node.maintain()
    node.navigation_clients["tb1"].responses[0].set_exception(RuntimeError("transport failure"))
    assert node.stop_requested and not node.dispatcher.closed
    assert any(kind == "rpc_error" for kind, _ in node.test_records)


def test_cancel_response_matches_real_numpy_uuid_arrays_without_ambiguous_truth():
    import numpy as np

    node, clock = make_adapter()
    goal_id, handle = accepted_goal(node, clock)
    handle.goal_id.uuid = np.arange(16, dtype=np.uint8)
    node.stop_requested = True
    node.dispatcher.safety_stop(node.now(), "test_cancel")
    advance(node, clock, 1.15)
    handle.cancel.set_result(SimpleNamespace(goals_canceling=[SimpleNamespace(
        goal_id=SimpleNamespace(uuid=np.arange(16, dtype=np.uint8)))]))
    advance(node, clock, 1.4)
    receipts = [payload["payload"] for kind, payload in node.test_records
                if kind == "delivery" and payload["stream"] == "receipt"]
    assert any(receipt["type"] == "cancel" and receipt["goal_id"] == goal_id
               and receipt["value"] is True for receipt in receipts)
    assert not any(kind == "rpc_error" for kind, _ in node.test_records)


@pytest.mark.parametrize("phase", ["accept", "result"])
def test_native_rpc_exception_latches_failure_without_releasing_owned_goal(phase):
    node, clock = make_adapter()
    if phase == "accept":
        node.receive_action(command(node))
        node.maintain()
        node.navigation_clients["tb1"].responses[0].set_exception(RuntimeError("RPC failure"))
    else:
        _, handle = accepted_goal(node, clock)
        handle.result.set_exception(RuntimeError("RPC failure"))
    assert node.stop_requested and node.dispatcher.failed
    assert not node.dispatcher.closed


def test_real_ros_adapter_constructs_and_releases_owner(monkeypatch):
    """Catch Node property/API collisions that protocol stand-ins cannot see."""
    import rclpy
    from rclpy.qos import DurabilityPolicy, ReliabilityPolicy
    from multi_robot_exploration.mr3_adapter import MR3Adapter
    monkeypatch.setenv("ROS_DOMAIN_ID", "181")
    rclpy.init()
    node = None
    try:
        node = MR3Adapter()
        assert set(node.navigation_clients) == set(ROBOTS)
        assert node.dispatcher.closed
        assert (node.initial_inputs_ready_pub.qos_profile.durability ==
                DurabilityPolicy.TRANSIENT_LOCAL)
        assert node.initial_inputs_ready_pub.qos_profile.reliability == ReliabilityPolicy.RELIABLE
        assert node.initial_inputs_ready_pub.qos_profile.depth == 1
        node.destroy_node()
        node = MR3Adapter()
        assert node.dispatcher.closed
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def test_scalar_task_terminal_requests_real_cancel_and_keeps_goal_owner_until_result():
    node, clock = make_adapter()
    node.stepped_mode = True
    goal_id, handle = accepted_goal(node, clock)
    notice = message({"epoch": node.epoch, "end_sim_time_sec": clock[0],
                      "termination_reason": "collision"})
    node.receive_task_terminal(notice)
    assert node.stop_requested and node.dispatcher.stopped
    assert node.dispatcher.navigation()["tb1"]["goal_id"] == goal_id
    node.maintain()
    assert handle.cancel_calls == 1 and not node.dispatcher.closed
    node.receive_task_terminal(notice)
    node.maintain()
    assert handle.cancel_calls == 1  # Repeated reliable notice cannot recancel the same owner.
    assert sum(kind == "task_terminal" for kind, _ in node.test_records) == 1


def test_adapter_deadline_uses_physical_nanoseconds_for_late_initial_clock_phase():
    node, clock = make_adapter()
    node.started_at = 212.06
    clock[0] = 512.06
    node.state = state(clock[0])
    assert clock[0] - node.started_at < 300.  # Binary floats straddle the exact task deadline.
    node.maintain()
    assert node.stop_requested and node.dispatcher.stopped


def test_encoding_in_flight_does_not_block_received_state_or_lease_service():
    node, clock = make_adapter()
    goal_id, _ = accepted_goal(node, clock)
    node.encoding = EncodingFuture()
    before = node.dispatcher.navigation()["tb1"]["lease_until"]
    advance(node, clock, 1.4)
    assert not node.stop_requested
    assert node.dispatcher.navigation()["tb1"]["goal_id"] == goal_id
    assert node.dispatcher.navigation()["tb1"]["lease_until"] > before
    assert not node.test_observations


def test_task_deadline_precedes_new_native_dispatch():
    node, clock = make_adapter()
    clock[0] = 301.
    node.state = state(301., sequence=2)
    refresh_snapshot(node)
    node.receive_action(command(node))
    node.maintain()
    assert node.stop_requested and node.dispatcher.closed
    assert not any(client.goals for client in node.navigation_clients.values())
    assert any(kind == "action_rejected" and data["reason"] == "task_deadline"
               for kind, data in node.test_records)
