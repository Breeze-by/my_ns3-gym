"""Read-only actual Nav2 parameter gate at an exact paused reset release."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys
import time

PROFILE = 'mr3-nav2-shim-dwb-020-v1'
EXPECTED = {'controller_server': {'FollowPath.max_vel_theta': (3, 0.8),
                       'FollowPath.max_vel_x': (3, 0.2),
                       'FollowPath.max_speed_xy': (3, 0.2),
                       'FollowPath.min_vel_x': (3, 0.0),
                       'FollowPath.max_vel_y': (3, 0.0),
                       'use_sim_time': (1, True),
                       'controller_frequency': (3, 10.0),
                       'controller_plugins': (9, ['FollowPath']),
                       'FollowPath.plugin': (4,
                                             'nav2_rotation_shim_controller::RotationShimController'),
                       'FollowPath.primary_controller': (4, 'dwb_core::DWBLocalPlanner'),
                       'FollowPath.angular_dist_threshold': (3, 0.5),
                       'FollowPath.angular_disengage_threshold': (3, 0.5),
                       'FollowPath.forward_sampling_distance': (3, 0.3),
                       'FollowPath.rotate_to_heading_angular_vel': (3, 0.8),
                       'FollowPath.max_angular_accel': (3, 3.2),
                       'FollowPath.simulate_ahead_time': (3, 1.0),
                       'FollowPath.rotate_to_goal_heading': (1, False),
                       'FollowPath.closed_loop': (1, True),
                       'FollowPath.acc_lim_x': (3, 0.5),
                       'FollowPath.decel_lim_x': (3, -0.5),
                       'FollowPath.acc_lim_theta': (3, 3.2),
                       'FollowPath.decel_lim_theta': (3, -3.2),
                       'FollowPath.min_speed_xy': (3, 0.0),
                       'FollowPath.min_speed_theta': (3, 0.0),
                       'FollowPath.critics': (9,
                                              ['RotateToGoal',
                                               'Oscillation',
                                               'BaseObstacle',
                                               'GoalAlign',
                                               'PathAlign',
                                               'PathDist',
                                               'GoalDist']),
                       'FollowPath.BaseObstacle.scale': (3, 0.02),
                       'FollowPath.PathAlign.scale': (3, 32.0),
                       'FollowPath.PathAlign.forward_point_distance': (3, 0.1),
                       'FollowPath.GoalAlign.scale': (3, 24.0),
                       'FollowPath.GoalAlign.forward_point_distance': (3, 0.1),
                       'FollowPath.PathDist.scale': (3, 32.0),
                       'FollowPath.GoalDist.scale': (3, 24.0),
                       'FollowPath.RotateToGoal.scale': (3, 32.0),
                       'FollowPath.RotateToGoal.slowing_factor': (3, 5.0),
                       'FollowPath.RotateToGoal.lookahead_time': (3, -1.0),
                       'goal_checker.xy_goal_tolerance': (3, 0.1),
                       'goal_checker.yaw_goal_tolerance': (3, 3.14),
                       'progress_checker.required_movement_radius': (3, 0.15),
                       'progress_checker.movement_time_allowance': (3, 15.0)},
 'behavior_server': {'max_rotational_vel': (3, 0.8),
                     'min_rotational_vel': (3, 0.4),
                     'rotational_acc_lim': (3, 3.2),
                     'use_sim_time': (1, True)},
 'velocity_smoother': {'max_velocity': (8, [0.2, 0.0, 0.8]),
                       'min_velocity': (8, [-0.2, 0.0, -0.8]),
                       'feedback': (4, 'OPEN_LOOP'),
                       'smoothing_frequency': (3, 20.0),
                       'use_sim_time': (1, True),
                       'max_accel': (8, [0.5, 0.0, 3.2]),
                       'max_decel': (8, [-0.5, 0.0, -3.2])}}
TYPE_FIELDS = {1: "bool_value", 3: "double_value", 4: "string_value",
               8: "double_array_value", 9: "string_array_value"}


def require(value, message):
    if not value:
        raise ValueError(message)


def decode_parameters(names, values):
    require(len(names) == len(values), "GetParameters response length mismatch")
    result = []
    for name, parameter in zip(names, values):
        kind = int(parameter.type)
        require(kind in TYPE_FIELDS, name + ": missing or unsupported parameter type")
        value = getattr(parameter, TYPE_FIELDS[kind])
        if kind in (8, 9):
            value = list(value)
        if kind == 9:
            require(all(type(item) is str for item in value), name + ": nonstring array")
        if kind in (3, 8):
            numbers = [value] if kind == 3 else value
            require(all(type(item) in (int, float) and math.isfinite(item) for item in numbers),
                    name + ": nonfinite parameter")
        result.append({"name": name, "type": kind, "type_field": TYPE_FIELDS[kind], "value": value})
    return result


def validate_parameters(node_kind, response):
    expected = EXPECTED[node_kind]
    require([row["name"] for row in response] == list(expected), "parameter order/name mismatch")
    for row in response:
        kind, value = expected[row["name"]]
        require(row["type"] == kind and row["value"] == value,
                node_kind + "/" + row["name"] + ": actual typed value differs from frozen expectation")


def validate_status(status, epoch, release):
    require(status.get("schema") == "mr3-motion-safety-status-v1"
            and status.get("epoch") == epoch and status.get("clock_ns") == release
            and status.get("ready") is True
            and status.get("completion_scope") == "publication_and_local_topic_receipt"
            and set(status.get("decision_sequences", {})) == {"tb1", "tb2", "tb3"}
            and all(type(value) is int and value > 0 for value in status["decision_sequences"].values()),
            "readback requires same-epoch exact healthy reset-release motion completion")


def collect(epoch, release, timeout, result):
    # ROS imports are local so the immutable matching rules also have stdlib tests.
    import rclpy
    from rclpy.context import Context
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import QoSProfile, DurabilityPolicy, ReliabilityPolicy
    from rcl_interfaces.srv import GetParameters
    from std_msgs.msg import String

    context = Context()
    node = executor = None
    deadline = time.monotonic() + timeout
    callback_errors = []
    statuses = result.setdefault("motion_status_receipts", [])
    result["cleanup"] = {"executor_shutdown": False, "node_destroyed": False, "context_shutdown": False}
    try:
        rclpy.init(args=[], context=context)
        node = Node("mr3_actual_nav2_parameters_v13", context=context)
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)

        def received_status(message):
            try:
                value = json.loads(message.data)
                validate_status(value, epoch, release)
                statuses.append({"receipt_wall_monotonic_ns": time.monotonic_ns(), "status": value})
            except (ValueError, TypeError, KeyError) as error:
                callback_errors.append(repr(error))

        qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                         reliability=ReliabilityPolicy.RELIABLE)
        node.create_subscription(String, "/motion_safety/status", received_status, qos)

        def wait_until(predicate, label):
            while not predicate():
                require(not callback_errors, "motion status changed/invalid: " + repr(callback_errors))
                remaining = deadline - time.monotonic()
                require(remaining > 0, "finite wall guard expired: " + label)
                executor.spin_once(timeout_sec=min(.05, remaining))
            require(not callback_errors, "motion status changed/invalid: " + repr(callback_errors))

        wait_until(lambda: bool(statuses), "paused reset status")
        for robot in ("tb1", "tb2", "tb3"):
            for kind, expectations in EXPECTED.items():
                fully_qualified = "/" + robot + "/" + kind
                service = fully_qualified + "/get_parameters"
                client = node.create_client(GetParameters, service)
                wait_until(client.service_is_ready, service)
                names = list(expectations)
                request_wall = time.monotonic_ns()
                future = client.call_async(GetParameters.Request(names=names))
                wait_until(future.done, service + " response")
                response = future.result()
                require(response is not None, service + ": missing response")
                typed = decode_parameters(names, response.values)
                result["nodes"].append({"node": fully_qualified, "service": service,
                    "request_wall_monotonic_ns": request_wall,
                    "response_wall_monotonic_ns": time.monotonic_ns(),
                    "epoch": epoch, "source_clock_ns": release, "typed_parameters": typed})
                validate_parameters(kind, typed)
        executor.spin_once(timeout_sec=0.)
        require(not callback_errors, "motion status changed/invalid: " + repr(callback_errors))
        require(len(result["nodes"]) == 9, "all nine actual Nav2 nodes required")
    finally:
        cleanup_errors = []
        for key, action in (
                ("executor_shutdown", lambda: executor.shutdown(timeout_sec=1.) if executor else True),
                ("node_destroyed", lambda: node.destroy_node() if node else None),
                ("context_shutdown", lambda: rclpy.shutdown(context=context) if context.ok() else None)):
            try:
                value = action()
                result["cleanup"][key] = value is not False
            except Exception as error:
                cleanup_errors.append(key + ": " + repr(error))
        result["cleanup"]["context_shutdown"] = not context.ok()
        result["cleanup_errors"] = cleanup_errors
        require(not cleanup_errors and all(result["cleanup"].values()),
                "readback node cleanup failed: " + repr(cleanup_errors))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode_directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--wall-timeout-sec", type=float, default=30.)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists")
    if not (math.isfinite(args.wall_timeout_sec) and 0 < args.wall_timeout_sec <= 60):
        parser.error("wall timeout must be finite and at most 60 seconds")
    result = {"schema": "mr3-actual-nav2-parameter-readback-v2", "profile": PROFILE, "passed": False,
              "freeze": args.freeze, "episode_directory": str(args.episode_directory),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "nodes": [], "errors": [], "expected_typed_parameters": EXPECTED,
              "scope": "GetParameters read-only actual responses from nine namespaced nodes; "
                       "source clock is durable same-epoch motion completion matched to paused reset release; "
                       "no parameter writes, control publications or physical stepping"}
    started = time.monotonic()
    try:
        require(re.fullmatch(r"[0-9a-f]{40}", args.freeze), "exact source freeze required")
        metadata = json.loads((args.episode_directory / "metadata.json").read_bytes())
        require(metadata["freeze"] == args.freeze, "episode metadata freeze mismatch")
        transition_path = args.episode_directory / "transitions.jsonl"
        reset = json.loads(transition_path.read_text().splitlines()[0])
        require(reset["kind"] == "reset" and reset["snapshot"]["epoch"] == metadata["epoch"],
                "original returned reset binding missing")
        release = reset["info"]["release_time_ns"]
        require(type(release) is int and release > 0, "invalid reset release source clock")
        result.update(epoch=metadata["epoch"], source_clock_ns=release,
                      metadata_sha256=hashlib.sha256((args.episode_directory / "metadata.json").read_bytes()).hexdigest(),
                      reset_transition_sha256=hashlib.sha256(transition_path.read_bytes()).hexdigest())
        collect(metadata["epoch"], release, args.wall_timeout_sec, result)
        result["passed"] = True
    except Exception as error:
        result["errors"].append(repr(error))
    result["wall_duration_sec"] = time.monotonic() - started
    with args.output.open("x") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "nodes": len(result["nodes"]),
                      "errors": result["errors"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
