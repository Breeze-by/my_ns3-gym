"""Peer geometry, final-command ownership and fail-closed callback fixtures."""

import ast
import copy
from collections import deque
import json
import io
import math
from pathlib import Path
import time
from types import SimpleNamespace

from geometry_msgs.msg import Twist
import pytest
import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from std_msgs.msg import Header, String
import yaml

from multi_robot_exploration.motion_safety import MotionSafety
from multi_robot_exploration.mr3_motion_safety import (
    BRAKING_DECEL_MPS2, COMMAND_TURN_LIMIT, ROBOTS, TURN_STOP_PADDING_SEC, guard_motion,
    maximum_heading_projection, valid_state,
)


def state(name, x, y, yaw=0., v=0., w=0., stamp=1.):
    return {"name": name, "epoch": "episode", "valid": True, "x": x, "y": y,
            "yaw": yaw, "v": v, "w": w, "source_stamp": stamp}


def evaluate(states, name, request, now=1.):
    peers = {peer: value for peer, value in states.items() if peer != name}
    return guard_motion(request, states[name], peers, now, "episode")


def test_initial_three_robot_pose_allows_departure_and_rotation_without_hidden_steering():
    states = {"tb1": state("tb1", 0., -.45), "tb2": state("tb2", 0., .45),
              "tb3": state("tb3", .45, 0.)}
    assert evaluate(states, "tb3", [.26, 0.])["output"] == [.26, 0.]
    for name in ("tb1", "tb2"):
        result = evaluate(states, name, [.26, 0.])
        assert not result["allow"] and result["output"] == [0., 0.]
        assert result["reason"] == "peer_braking_nonclosing"
    for name in ROBOTS:
        assert evaluate(states, name, [0., .8])["output"] == [0., .8]
    states["tb3"]["x"] = 2.
    assert evaluate(states, "tb1", [.26, 0.])["output"] == [.26, 0.]


def test_stationary_bypass_parallel_and_reverse_departure_are_permitted_when_clear():
    states = {"tb1": state("tb1", 0., 0.), "tb2": state("tb2", 0., .65),
              "tb3": state("tb3", 4., 4.)}
    assert evaluate(states, "tb1", [.2, 0.])["allow"]
    assert evaluate(states, "tb2", [.2, 0.])["allow"]
    states["tb2"].update(x=.65, y=0.)
    assert evaluate(states, "tb1", [-.2, 0.])["output"] == [-.2, 0.]
    states["tb1"].update(x=-1.)
    states["tb2"].update(x=0., y=1.)
    for index in range(101):
        states["tb1"]["x"] = -1. + index * .02
        assert evaluate(states, "tb1", [.2, 0.])["allow"]


def test_measured_pending_motion_and_full_turn_interval_are_checked_before_new_cmd():
    states = {"tb1": state("tb1", 0., 0., v=.26), "tb2": state("tb2", .7, 0.),
              "tb3": state("tb3", 4., 4.)}
    assert not evaluate(states, "tb1", [-.2, 0.])["allow"]
    states["tb1"].update(v=0., yaw=math.pi / 2)
    assert evaluate(states, "tb1", [.2, 0.])["allow"]
    turning = evaluate(states, "tb1", [.2, .8])
    assert turning["output"] == [0., .8]
    assert turning["reason"] == "linear_brake_preserve_requested_turn"
    # Independently sample every heading; the analytic envelope must cover it.
    for heading in (-math.pi, -.3, 0., .8, math.pi):
        bound = maximum_heading_projection(.4, -.2, heading, .7)
        samples = [.4 * math.cos(heading - .7 + i * 1.4 / 1000)
                   - .2 * math.sin(heading - .7 + i * 1.4 / 1000) for i in range(1001)]
        assert bound >= max(samples) - 1e-12


def test_source_yaw_age_and_unobserved_pending_turn_cannot_use_old_zero_angular_speed():
    states = {"tb1": state("tb1", 0., 0., stamp=.8),
              "tb2": state("tb2", -.2, .65), "tb3": state("tb3", 4., 4.)}
    # The old zero-turn assumption has a positive non-closing margin despite
    # the missing .20 s of possible heading change.
    assert -maximum_heading_projection(-.2, .65, 0., 0.) - .3 * .2 > 0
    result = evaluate(states, "tb1", [.2, 0.])
    assert not result["allow"] and result["reason"] == "peer_braking_nonclosing"
    direction = result["near_peer_checks"][0]["direction_checks"][0]
    assert direction["source_yaw_uncertainty_rad"] == pytest.approx(.24)
    states["tb1"]["source_stamp"] = .95
    states["tb2"].update(x=-.1, y=.7)
    # Even adding yaw age alone misses angular velocity gained since that
    # old zero-w measurement. The pending-turn envelope must also reject it.
    assert -maximum_heading_projection(-.1, .7, 0., 1.2 * .05) - .3 * .05 > 0
    result = evaluate(states, "tb1", [.26, 0.])
    assert not result["allow"]
    direction = result["near_peer_checks"][0]["direction_checks"][0]
    assert direction["turn_bound_radps"] == pytest.approx(.35)
    assert direction["horizon_sec"] == pytest.approx(.78)
    states["tb1"]["source_stamp"] = 1.
    assert evaluate(states, "tb1", [.26, 0.])["allow"]


def test_turn_coupling_padding_is_explicit_in_both_stop_reserve_and_heading_horizon():
    states = {"tb1": state("tb1", 0., 0.), "tb2": state("tb2", -.8, 0.),
              "tb3": state("tb3", 4., 4.)}
    result = evaluate(states, "tb1", [.2, 0.])
    check = result["near_peer_checks"][0]
    assert TURN_STOP_PADDING_SEC == .02
    assert check["near"]
    assert check["body_margin_m"] == pytest.approx(.28)
    assert check["body_margin_m"] - check["braking_zone_margin_m"] == pytest.approx(.288)
    assert check["direction_checks"][0]["horizon_sec"] == pytest.approx(.78)


def test_odom_angular_age_is_distinct_from_older_geometry_and_yaw_source_age():
    states = {"tb1": state("tb1", 0., 0., stamp=.8),
              "tb2": state("tb2", -.8, 0.), "tb3": state("tb3", 4., 4.)}
    states["tb1"].update(odom_source_stamp=.98, tf_source_stamp=.8)
    result = evaluate(states, "tb1", [.2, .1])
    assert result["allow"]
    direction = result["near_peer_checks"][0]["direction_checks"][0]
    assert direction["geometry_source_stamp"] == .8
    assert direction["geometry_source_age_sec"] == pytest.approx(.2)
    assert direction["angular_velocity_source_stamp"] == .98
    assert direction["angular_velocity_source_age_sec"] == pytest.approx(.02)
    assert direction["source_yaw_uncertainty_rad"] == pytest.approx(.24)
    assert direction["turn_bound_radps"] == pytest.approx(.14)
    assert direction["heading_half_angle_rad"] == pytest.approx(.24 + .14 * .78)
    # A newer odometry measurement cannot make an old TF pose/yaw look fresh.
    states["tb1"]["tf_source_stamp"] = .499
    assert not evaluate(states, "tb1", [.2, .1])["allow"]


def test_actual_nav2_node_parameters_share_the_guard_command_limits():
    component = Path(__file__).resolve().parents[2] / "multi_robot"
    assert COMMAND_TURN_LIMIT == .8
    sources = [component / "config/nav2_params.yaml"] + [
        component / "params" / f"nav2_params_{name}_0.yaml" for name in ROBOTS]
    for source in sources:
        params = yaml.safe_load(source.read_text())
        controller = params["controller_server"]["ros__parameters"]["FollowPath"]
        behavior = params["behavior_server"]["ros__parameters"]
        smoother = params["velocity_smoother"]["ros__parameters"]
        assert controller["max_vel_x"] == controller["max_speed_xy"] == .26
        assert controller["max_vel_theta"] == behavior["max_rotational_vel"] == .8
        assert smoother["max_velocity"] == [.26, 0., .8]
        assert smoother["min_velocity"] == [-.26, 0., -.8]
        assert smoother["smoothing_frequency"] == 20. and smoother["feedback"] == "OPEN_LOOP"
        assert smoother["use_sim_time"] is True and behavior["use_sim_time"] is True
    # The canonical top-level launch selects these per-robot files; checking
    # config/nav2_params.yaml alone would miss the actual native input.
    top = ast.parse((component / "launch/gazebo_multirobot_mapping_with_nav2.launch.py")
                    .read_text())
    selections = [node.value for node in ast.walk(top) if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "params_file"
                          for target in node.targets)
                  and isinstance(node.value, ast.Call)
                  and isinstance(node.value.func, ast.Attribute)
                  and node.value.func.attr == "join"]
    assert len(selections) == 1
    selection = selections[0].args
    assert isinstance(selection[0], ast.Name) and selection[0].id == "multi_robot_share"
    assert isinstance(selection[1], ast.Constant) and selection[1].value == "params"
    assert isinstance(selection[2], ast.JoinedStr)
    assert ast.dump(selection[2]) == ast.dump(ast.parse(
        'f"nav2_params_{robot_name}_0.yaml"', mode="eval").body)
    # Check the node keys against both real launch branches, rather than the
    # obsolete recoveries_server compatibility section alone.
    launch = ast.parse((component / "launch/nav2_bringup/navigation_launch.py").read_text())
    bindings = []
    for call in ast.walk(launch):
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
            continue
        if call.func.id not in ("Node", "ComposableNode"):
            continue
        keywords = {item.arg: item.value for item in call.keywords}
        # The standalone controller uses its executable's default node name;
        # the composed controller and both other nodes declare explicit names.
        name = keywords.get("name", keywords.get("executable"))
        if isinstance(name, ast.Constant) and name.value in (
                "controller_server", "behavior_server", "velocity_smoother"):
            configured = keywords["parameters"]
            assert isinstance(configured, ast.List) and len(configured.elts) == 1
            assert isinstance(configured.elts[0], ast.Name)
            assert configured.elts[0].id == "configured_params"
            bindings.append((call.func.id, name.value))
    assert sorted(bindings) == sorted((kind, name)
                                      for kind in ("Node", "ComposableNode")
                                      for name in ("controller_server", "behavior_server",
                                                   "velocity_smoother"))


@pytest.mark.parametrize("fault", ["stale", "future", "epoch", "missing", "invalid", "speed"])
def test_missing_stale_future_wrong_epoch_or_unbounded_state_stops(fault):
    states = {name: state(name, index * 3., 0.) for index, name in enumerate(ROBOTS)}
    if fault == "stale":
        states["tb2"]["source_stamp"] = .499
    elif fault == "future":
        states["tb2"]["source_stamp"] = 1.001
    elif fault == "epoch":
        states["tb2"]["epoch"] = "old"
    elif fault == "missing":
        del states["tb2"]
    elif fault == "invalid":
        states["tb2"]["x"] = float("nan")
    else:
        states["tb2"]["v"] = .31
    result = evaluate(states, "tb1", [.2, 0.])
    assert not result["allow"] and result["output"] == [0., 0.]


@pytest.mark.parametrize("command", [[.261, 0.], [0., 1.], [float("nan"), 0.]])
def test_requested_speed_turn_and_nonfinite_limits_are_not_clipped_into_new_actions(command):
    states = {name: state(name, index * 3., 0.) for index, name in enumerate(ROBOTS)}
    result = evaluate(states, "tb1", command)
    assert result["reason"] == "unsupported_command" and result["output"] == [0., 0.]


@pytest.mark.parametrize("sign", [-1., 1.])
def test_only_one_ulp_outward_endpoints_are_canonicalized_to_hard_limits(sign):
    states = {name: state(name, index * 3., 0.) for index, name in enumerate(ROBOTS)}
    # This v is an actual v2 Nav2 smoother callback, not a broad epsilon case.
    captured_v = sign * 0.26000000000000006
    adjacent_w = sign * math.nextafter(.8, math.inf)
    result = evaluate(states, "tb1", [captured_v, adjacent_w])
    assert result["allow"] and result["output"] == [sign * .26, sign * .8]
    assert result["command_normalization"] == {
        "schema": "mr3-command-one-ulp-v1", "input": [captured_v, adjacent_w],
        "canonical": [sign * .26, sign * .8], "normalized_axes": ["v", "w"]}
    assert abs(result["output"][0]) <= .26 and abs(result["output"][1]) <= .8
    for axis, limit in enumerate((.26, .8)):
        command = [0., 0.]
        command[axis] = sign * math.nextafter(math.nextafter(limit, math.inf), math.inf)
        rejected = evaluate(states, "tb1", command)
        assert not rejected["allow"] and rejected["reason"] == "unsupported_command"
        assert rejected["output"] == [0., 0.]


def test_one_ulp_normalization_preserves_geometry_rejection_and_original_input():
    states = {"tb1": state("tb1", 0., 0., v=.1), "tb2": state("tb2", .65, 0.),
              "tb3": state("tb3", 4., 4.)}
    captured = [.26000000000000006, .6842105263157895]
    original = list(captured)
    result = evaluate(states, "tb1", captured)
    assert captured == original
    assert not result["allow"] and result["reason"] == "peer_braking_nonclosing"
    assert result["output"] == [0., 0.]
    assert result["command_normalization"]["canonical"] == [.26, captured[1]]


@pytest.mark.parametrize("turn", [-.6842105263157895, .6842105263157895])
def test_captured_mixed_request_can_only_preserve_independently_safe_requested_turn(turn):
    states = {"tb1": state("tb1", 0., 0.), "tb2": state("tb2", .65, 0.),
              "tb3": state("tb3", 4., 4.)}
    request = [.26000000000000006, turn]
    result = evaluate(states, "tb1", request)
    assert result["allow"] and result["output"] == [0., turn]
    component = result["component_filter"]
    assert component["canonical_input"] == [.26, turn]
    assert component["rejected_mixed_decision"]["reason"] == "peer_braking_nonclosing"
    assert component["rejected_mixed_decision"]["output"] == [0., 0.]
    assert component["rotation_check"] == evaluate(states, "tb1", [0., turn])
    assert component["rotation_check"]["reason"] == "clear"
    assert component["rotation_check"]["component_filter"] is None
    assert request == [.26000000000000006, turn]


@pytest.mark.parametrize("fault", ["moving", "envelope", "stale", "two_ulps"])
def test_component_filter_never_bypasses_measured_motion_or_unavailable_geometry(fault):
    states = {"tb1": state("tb1", 0., 0.), "tb2": state("tb2", .65, 0.),
              "tb3": state("tb3", 4., 4.)}
    request = [.26, -.6842105263157895]
    if fault == "moving":
        states["tb1"]["v"] = .1
    elif fault == "envelope":
        states["tb2"]["x"] = .49
    elif fault == "stale":
        states["tb2"]["source_stamp"] = .499
    else:
        request[1] = math.nextafter(math.nextafter(.8, math.inf), math.inf)
    result = evaluate(states, "tb1", request)
    assert not result["allow"] and result["output"] == [0., 0.]
    assert result["component_filter"] is None


@pytest.mark.parametrize("crossing", [False, True])
def test_bounded_reaction_and_braking_headon_or_crossing_never_reaches_half_meter(crossing):
    states = {"tb1": state("tb1", -1., 0., v=.26),
              "tb2": state("tb2", 0. if crossing else 1., -1. if crossing else 0.,
                           yaw=math.pi / 2 if crossing else math.pi, v=.26),
              "tb3": state("tb3", 5., 5.)}
    commands = {"tb1": .26, "tb2": .26}
    delayed = {name: [] for name in commands}
    history = [copy.deepcopy(states)]
    minimum, stops = 10., 0
    dt = .001
    for index in range(5000):
        now = 1. + index * dt
        if index % 20 == 0:
            received = copy.deepcopy(history[max(0, len(history) - 151)])
            for name in commands:
                own = copy.deepcopy(states[name])
                own["source_stamp"] = now
                peers = {peer: row for peer, row in received.items() if peer != name}
                decision = guard_motion([.26, 0.], own, peers, now, "episode")
                stops += not decision["allow"]
                # Worst declared reaction delay, followed by minimum braking.
                delayed[name].append((index + 160, decision["output"][0]))
        for name in commands:
            while delayed[name] and delayed[name][0][0] <= index:
                _, commands[name] = delayed[name].pop(0)
            value = states[name]
            change = max(-BRAKING_DECEL_MPS2 * dt,
                         min(BRAKING_DECEL_MPS2 * dt, commands[name] - value["v"]))
            value["v"] += change
            value["x"] += value["v"] * math.cos(value["yaw"]) * dt
            value["y"] += value["v"] * math.sin(value["yaw"]) * dt
        for row in states.values():
            row["source_stamp"] = now
        history.append(copy.deepcopy(states))
        distance = math.hypot(states["tb1"]["x"] - states["tb2"]["x"],
                              states["tb1"]["y"] - states["tb2"]["y"])
        minimum = min(minimum, distance)
    assert stops > 0 and minimum > .5
    assert abs(states["tb1"]["v"]) < 1e-6 and abs(states["tb2"]["v"]) < 1e-6


def node_fixture():
    clock = [1_000_000_000]
    events = []
    states = {name: state(name, index * 3., 0.) for index, name in enumerate(ROBOTS)}
    node = SimpleNamespace(
        epoch="episode", received={"robots": list(states.values())}, started=False,
        drive_audit=io.StringIO(), drive_record_sequence=0,
        halted=None, stop_time=None, failure_sent=False,
        decision_sequences=dict.fromkeys(ROBOTS, 0),
        pending_outputs={name: deque() for name in ROBOTS},
        observed_sequences=dict.fromkeys(ROBOTS, 0), pending_status={}, observers_started=False,
        requests={name: {"v": .2, "w": 0., "supported": True, "received_stamp": 1.,
                         "sequence": 1, "publisher_identity": {"valid": True}}
                  for name in ROBOTS},
        local_state=lambda name: states[name], topology_ready=lambda: True,
        local_observers_ready=lambda: True,
        get_clock=lambda: SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=clock[0])),
        now=lambda: clock[0] / 1e9,
        record=lambda kind, payload: events.append((kind, copy.deepcopy(payload))),
        ready_pub=SimpleNamespace(publish=lambda msg: events.append(("ready", msg.data))),
        failure_pub=SimpleNamespace(publish=lambda msg: events.append(("failure_pub", msg.data))),
        status_pub=SimpleNamespace(publish=lambda msg: events.append(
            ("status", json.loads(msg.data)))),
        outputs={name: SimpleNamespace(publish=lambda msg, name=name: events.append(
            ("output", name, msg.linear.x, msg.angular.z))) for name in ROBOTS},
        drive_targets={name: SimpleNamespace(publish=lambda msg, name=name: events.append(
            ("drive_target", name, json.loads(msg.data)))) for name in ROBOTS})
    node.publish_completed_status = lambda clock_ns: MotionSafety.publish_completed_status(
        node, clock_ns)
    node.twist = MotionSafety.twist
    node.publisher_identity = lambda *args: {"scope": "graph_at_callback", "valid": True,
                                             "endpoints": [{"endpoint_gid": "010203"}]}
    return node, clock, events


def test_ready_precedes_release_and_exact_status_follows_all_actual_publish_calls():
    node, _, events = node_fixture()
    MotionSafety.tick(node)
    assert ("ready", True) in events
    assert all(event[2:] == (0., 0.) for event in events if event[0] == "output")
    assert not any(event[0] == "status" for event in events)
    for name in ROBOTS:
        MotionSafety.receive_actual(node, Twist(), name)
    status = events[-1]
    assert status[0] == "status" and status[1]["clock_ns"] == 1_000_000_000
    assert status[1]["decision_sequences"] == {name: 1 for name in ROBOTS}
    assert status[1]["completion_scope"] == "publication_and_local_topic_receipt"
    targets = {row[1]: row[2] for row in events if row[0] == "drive_target"}
    assert set(targets) == set(ROBOTS)
    for name, target in targets.items():
        assert target == {"schema": "mr3-drive-target-v1", "epoch": "episode", "robot": name,
                          "clock_ns": status[1]["clock_ns"], "decision_sequence": 1,
                          **status[1]["outputs"][name]}
    records = [json.loads(line) for line in node.drive_audit.getvalue().splitlines()]
    assert [row["record_sequence"] for row in records] == [1, 2, 3]
    assert [json.loads(row["target_json"]) for row in records] == list(targets.values())
    node.started = True
    events.clear()
    MotionSafety.tick(node)
    assert all(event[2:] == (.2, 0.) for event in events if event[0] == "output")


def test_cancel_timeout_terminal_and_unhealthy_topology_emit_zero_without_resume_bypass():
    node, clock, events = node_fixture()
    node.started = True
    clock[0] += 201_000_000
    MotionSafety.tick(node)
    assert all(event[2:] == (0., 0.) for event in events if event[0] == "output")
    node, clock, events = node_fixture()
    node.started = True
    MotionSafety.receive_stop(node, Header())
    MotionSafety.tick(node)
    assert all(event[2:] == (0., 0.) for event in events if event[0] == "output")
    node, clock, events = node_fixture()
    node.started = True
    MotionSafety.receive_terminal(node, String(data=json.dumps({
        "epoch": "episode", "end_sim_time_sec": 1.})))
    MotionSafety.tick(node)
    assert all(event[2:] == (0., 0.) for event in events if event[0] == "output")
    node, clock, events = node_fixture()
    node.started = True
    node.topology_ready = lambda: False
    MotionSafety.tick(node)
    assert node.halted and any(event[0] == "failure_pub" for event in events)
    node.topology_ready = lambda: True
    events.clear()
    MotionSafety.tick(node)
    assert all(event[2:] == (0., 0.) for event in events if event[0] == "output")


def test_raw_and_final_twist_callbacks_keep_graph_publisher_and_receipt_order():
    node, _, events = node_fixture()
    node.input_sequences = {name: {"request": 0} for name in ROBOTS}
    node.twist = MotionSafety.twist
    message = Twist()
    message.linear.x = .2
    node.publisher_identity = lambda *args: {"scope": "graph_at_callback", "valid": True,
                                             "endpoints": [{"endpoint_gid": "010203"}]}
    MotionSafety.receive_request(node, message, "tb1")
    node.pending_outputs["tb1"].append({"output": [.2, 0.], "sequence": 1,
                                        "clock_ns": 1_000_000_000})
    MotionSafety.receive_actual(node, message, "tb1")
    assert [event[0] for event in events] == ["raw_request", "actual_cmd_vel"]
    assert node.requests["tb1"]["publisher_identity"]["endpoints"][0]["endpoint_gid"] == "010203"
    assert node.requests["tb1"]["received_stamp"] == 1.


def test_recovered_nanosecond_endpoints_do_not_add_freshness_or_timeout_tolerance():
    value = state("tb1", 0., 0., stamp=1.2 - .2)
    value["tf_source_stamp"] = 1.2 - .2
    assert valid_state(value, 1., "episode")
    value["tf_source_stamp"] = 1.000000001
    assert not valid_state(value, 1., "episode")
    value["tf_source_stamp"] = .5
    assert valid_state(value, 1., "episode")
    value["tf_source_stamp"] = .499999999
    assert not valid_state(value, 1., "episode")
    node, clock, events = node_fixture()
    node.started = True
    clock[0] = 1_200_000_000
    MotionSafety.tick(node)
    assert all(event[2:] == (.2, 0.) for event in events if event[0] == "output")
    events.clear()
    clock[0] += 1
    MotionSafety.tick(node)
    assert all(event[2:] == (0., 0.) for event in events if event[0] == "output")


@pytest.mark.parametrize("repetition", range(3))
def test_installed_humble_executor_delivers_one_argument_callbacks_with_graph_identity(repetition):
    """Real DDS CPU exchange: no simulation, fake executor or MessageInfo adapter."""
    rclpy.init(args=["--ros-args", "-p", "episode_epoch:=cpu_callback_test"])
    node = MotionSafety()
    source = Node("velocity_smoother", namespace="/tb1")
    publisher = source.create_publisher(Twist, "/tb1/cmd_vel_unguarded", 20)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    executor.add_node(source)
    events = []
    node.record = lambda kind, payload: events.append((kind, payload))
    message = Twist()
    message.linear.x = .2
    try:
        deadline = time.monotonic() + 5.
        while time.monotonic() < deadline:
            publisher.publish(message)
            executor.spin_once(timeout_sec=.02)
            if (any(kind == "raw_request" for kind, _ in events)
                    and any(kind == "actual_cmd_vel" for kind, _ in events)):
                break
        raw = next(payload for kind, payload in events if kind == "raw_request")
        actual = next(payload for kind, payload in events if kind == "actual_cmd_vel")
        assert raw["request"]["publisher_identity"]["valid"]
        assert raw["request"]["publisher_identity"]["scope"] == "graph_at_callback"
        assert actual["publisher_identity"]["valid"]
        node.timer.cancel()
        deadline = time.monotonic() + 2.
        while any(node.pending_outputs.values()) and time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.02)
        assert all(not pending for pending in node.pending_outputs.values())
        assert all(node.observed_sequences[name] == node.decision_sequences[name] > 0
                   for name in ROBOTS)
        assert node.halted is None
        print(json.dumps({"repetition": repetition, "decisions": node.decision_sequences,
                          "actual_observed": node.observed_sequences,
                          "pending": {name: len(queue) for name, queue
                                      in node.pending_outputs.items()},
                          "scope": "real Humble DDS; graph_at_callback; zero output; no sim"}))
    finally:
        executor.shutdown()
        source.destroy_node()
        node.destroy_node()
        rclpy.shutdown()
