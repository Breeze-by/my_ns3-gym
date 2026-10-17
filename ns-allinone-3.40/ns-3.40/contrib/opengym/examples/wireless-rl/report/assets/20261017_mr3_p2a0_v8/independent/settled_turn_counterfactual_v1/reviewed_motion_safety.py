"""The adapter's unique final Twist publisher with received-peer braking guards."""

from collections import deque
import json
import math
from pathlib import Path
import time

from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, Header, String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.mr3_information import odom_payload, state_payload, transform_payload
from multi_robot_exploration.mr3_episode import elapsed_ns, timestamp_ns
from multi_robot_exploration.mr3_motion_safety import (
    COMMAND_TIMEOUT_SEC, PERIOD_SEC, ROBOTS, SettledTurnTracker, guard_motion, valid_state,
)


class MotionSafety(Node):
    """Three logical local gates; robot i never reads another robot's raw state."""

    def __init__(self):
        super().__init__("motion_safety")
        self.epoch = self.declare_parameter("episode_epoch", "").value
        audit_path = self.declare_parameter("audit_path", "").value
        if not self.epoch:
            raise ValueError("motion safety requires an episode epoch")
        self.audit = None
        self.drive_audit = None
        if audit_path:
            Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
            self.audit = Path(audit_path).open("x", buffering=1)
            self.drive_audit = Path(audit_path).with_name("drive_targets.jsonl").open(
                "x", buffering=1)
        self.drive_record_sequence = 0
        self.record_sequence = 0
        self.odometry, self.transforms, self.requests = {}, {}, {}
        self.settled_turn = {name: SettledTurnTracker() for name in ROBOTS}
        self.input_sequences = {name: {"odom": 0, "tf": 0, "request": 0} for name in ROBOTS}
        self.decision_sequences = dict.fromkeys(ROBOTS, 0)
        self.pending_outputs = {name: deque() for name in ROBOTS}
        self.observed_sequences = dict.fromkeys(ROBOTS, 0)
        self.pending_status = {}
        self.observers_started = False
        self.received = None
        self.started = False
        self.stop_time = None
        self.halted = None
        self.failure_sent = False
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.outputs = {name: self.create_publisher(Twist, f"/{name}/cmd_vel", 20)
                        for name in ROBOTS}
        self.drive_targets = {
            name: self.create_publisher(String, f"/{name}/mr3_drive/target", durable)
            for name in ROBOTS}
        self.ready_pub = self.create_publisher(Bool, "/motion_safety/ready", durable)
        self.status_pub = self.create_publisher(String, "/motion_safety/status", durable)
        self.failure_pub = self.create_publisher(String, "/exploration_failure", durable)
        self.inputs = []
        for name in ROBOTS:
            self.inputs.extend([
                self.create_subscription(Odometry, f"/{name}/odom",
                                         lambda msg, name=name: self.receive_odom(msg, name), 10),
                self.create_subscription(TFMessage, f"/{name}/tf",
                                         lambda msg, name=name: self.receive_tf(msg, name), 20),
                self.create_subscription(
                    Twist, f"/{name}/cmd_vel_unguarded",
                    lambda msg, name=name: self.receive_request(msg, name), 20),
                self.create_subscription(
                    Twist, f"/{name}/cmd_vel",
                    lambda msg, name=name: self.receive_actual(msg, name), 20),
            ])
        self.inputs.extend([
            self.create_subscription(String, "/mr3/received/states", self.receive_states, 10),
            self.create_subscription(Header, "/exploration_start", self.receive_start, durable),
            self.create_subscription(Header, "/exploration_stop_request", self.receive_stop,
                                     durable),
            self.create_subscription(String, "/mr3/task_terminal", self.receive_terminal, durable),
            self.create_subscription(String, "/exploration_failure", self.receive_failure,
                                     durable),
        ])
        self.timer = self.create_timer(PERIOD_SEC, self.tick)
        self.record("configuration", {
            "robots": list(ROBOTS),
            "input_topics": [f"/{name}/cmd_vel_unguarded" for name in ROBOTS],
            "output_topics": [f"/{name}/cmd_vel" for name in ROBOTS],
            "source_scope": "each own local odom/TF plus received peer states only",
            "twist_source_stamp_available": False,
            "settled_turn_contract": "mr3-settled-turn-v1; own zero publications .94s, "
            "three later fresh rest samples; conditional persistent planar speed<=.01m/s "
            "and whole zero-segment centre path<=.0078m, never reset by repeated grants; "
            "independent actual zero storage>=.78s and full160ms driver audit required",
            "publisher_identity_scope": "graph_at_callback; packet MessageInfo unavailable "
            "on installed Humble",
        })

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def record(self, kind, payload):
        if self.audit is None:
            return

        def finite_json(value):
            if isinstance(value, dict):
                return {key: finite_json(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [finite_json(item) for item in value]
            return None if isinstance(value, float) and not math.isfinite(value) else value

        self.record_sequence += 1
        self.audit.write(json.dumps({
            "schema": "mr3-motion-safety-v1", "epoch": self.epoch,
            "record_sequence": self.record_sequence, "kind": kind,
            "sim_time_sec": self.now(), "wall_monotonic_ns": time.monotonic_ns(),
            "payload": finite_json(payload)}, allow_nan=False, separators=(",", ":")) + "\n")

    @staticmethod
    def twist(message):
        return {axis: {key: getattr(getattr(message, axis), key) for key in ("x", "y", "z")}
                for axis in ("linear", "angular")}

    def receive_odom(self, message, name):
        self.odometry[name] = message
        self.input_sequences[name]["odom"] += 1
        payload = odom_payload(message)
        self.record("own_odom", {"robot": name,
                                 "input_sequence": self.input_sequences[name]["odom"],
                                 "message": payload})
        try:
            self.settled_turn[name].observe(payload, self.input_sequences[name]["odom"])
        except (ValueError, KeyError, TypeError) as error:
            self.halted = "settled_turn_model_failure"
            self.record("settled_turn_model_failure", {"robot": name, "reason": str(error)})

    def receive_tf(self, message, name):
        for transform in message.transforms:
            if (transform.header.frame_id.lstrip("/") == "map"
                    and transform.child_frame_id.lstrip("/") == "odom"):
                self.transforms[name] = transform
                self.input_sequences[name]["tf"] += 1
                self.record("own_tf", {"robot": name,
                                       "input_sequence": self.input_sequences[name]["tf"],
                                       "message": transform_payload(transform)})

    def publisher_identity(self, topic, namespace, node):
        entries = self.get_publishers_info_by_topic(topic)
        valid = (len(entries) == 1 and entries[0].node_namespace == namespace
                 and entries[0].node_name == node)
        return {"scope": "graph_at_callback", "topic": topic, "valid": valid,
                "endpoints": [{"namespace": row.node_namespace, "node": row.node_name,
                               "endpoint_gid": bytes(row.endpoint_gid).hex(),
                               "topic_type": row.topic_type} for row in entries]}

    def receive_request(self, message, name):
        fields = self.twist(message)
        supported = all(math.isfinite(value) for vector in fields.values()
                        for value in vector.values())
        supported = supported and all(fields[axis][key] == 0 for axis, key in
                                      (("linear", "y"), ("linear", "z"),
                                       ("angular", "x"), ("angular", "y")))
        self.input_sequences[name]["request"] += 1
        request = {"v": message.linear.x if supported else None,
                   "w": message.angular.z if supported else None,
                   "received_stamp": self.now(), "sequence": self.input_sequences[name]["request"],
                   "publisher_identity": self.publisher_identity(
                       f"/{name}/cmd_vel_unguarded", f"/{name}", "velocity_smoother"),
                   "supported": supported}
        self.requests[name] = request
        self.record("raw_request", {"robot": name, "request": request,
                                    "twist": fields if supported else None})

    def receive_actual(self, message, name):
        fields = self.twist(message)
        identity = self.publisher_identity(f"/{name}/cmd_vel", "/", "motion_safety")
        pending = self.pending_outputs[name]
        observed = None
        supported = all(fields[axis][key] == 0 for axis, key in
                        (("linear", "y"), ("linear", "z"),
                         ("angular", "x"), ("angular", "y")))
        if (identity["valid"] and supported and pending
                and [message.linear.x, message.angular.z] == pending[0]["output"]):
            output = pending.popleft()
            observed = output["sequence"]
            self.observed_sequences[name] = observed
        else:
            self.halted = "motion_output_observation_mismatch"
        self.record("actual_cmd_vel", {"robot": name, "twist": fields,
                                       "publisher_identity": identity,
                                       "observed_decision_sequence": observed})
        if observed is not None:
            self.publish_completed_status(output["clock_ns"])

    def publish_completed_status(self, clock_ns):
        status = self.pending_status.get(clock_ns)
        if (status is not None and self.get_clock().now().nanoseconds == clock_ns
                and all(self.observed_sequences[name] >= status["decision_sequences"][name]
                        for name in ROBOTS)):
            self.status_pub.publish(String(data=json.dumps(status)))
            self.pending_status.pop(clock_ns)

    def local_observers_ready(self):
        return all(self.outputs[name].get_subscription_count() > 0 and any(
            row.node_namespace == "/" and row.node_name == "motion_safety"
            for row in self.get_subscriptions_info_by_topic(f"/{name}/cmd_vel"))
            for name in ROBOTS)

    def receive_states(self, message):
        try:
            value = json.loads(message.data)
            if (value["epoch"] != self.epoch or len(value["robots"]) != 3
                    or set(row["name"] for row in value["robots"]) != set(ROBOTS)):
                raise ValueError("received state epoch/robot identity mismatch")
            self.received = value
            self.record("received_states", value)
        except (ValueError, KeyError, TypeError) as error:
            self.received = None
            self.record("invalid_received_states", {"reason": str(error)})

    def receive_start(self, message):
        if message.frame_id == "map":
            self.started = True
            self.record("release", {"stamp": message.stamp.sec + message.stamp.nanosec / 1e9})

    def receive_stop(self, message):
        self.stop_time = self.now()
        self.record("stop_request", {"stamp": message.stamp.sec + message.stamp.nanosec / 1e9})

    def receive_terminal(self, message):
        try:
            value = json.loads(message.data)
            if value["epoch"] == self.epoch:
                stamp = value["end_sim_time_sec"]
                if type(stamp) not in (int, float) or not math.isfinite(stamp):
                    raise ValueError("terminal time must be finite")
                self.stop_time = stamp
                self.record("terminal", value)
        except (ValueError, KeyError, TypeError) as error:
            self.halted = "invalid_terminal_notice"
            self.record("invalid_terminal_notice", {"reason": str(error)})

    def receive_failure(self, message):
        self.halted = "external_safety_failure"
        self.record("failure", {"data": message.data})

    def local_state(self, name):
        if name not in self.odometry or name not in self.transforms:
            return None
        odometry, transform = self.odometry[name], self.transforms[name]
        if (odometry.header.frame_id.lstrip("/") != "odom"
                or odometry.child_frame_id.lstrip("/") not in ("base_footprint", "base_link")):
            return None
        for rotation in (odometry.pose.pose.orientation, transform.transform.rotation):
            values = [getattr(rotation, axis) for axis in ("x", "y", "z", "w")]
            if (not all(math.isfinite(value) for value in values)
                    or abs(sum(value * value for value in values) - 1.) > .01):
                return None
        value = state_payload(name, self.odometry[name], self.transforms[name], .2)
        value.pop("odometry")
        value.pop("transform")
        value.update(epoch=self.epoch, valid=True,
                     source_stamp=min(value["odom_source_stamp"], value["tf_source_stamp"]),
                     input_sequences={key: self.input_sequences[name][key]
                                      for key in ("odom", "tf")})
        value["planar_speed_mps"] = math.hypot(odometry.twist.twist.linear.x,
                                               odometry.twist.twist.linear.y)
        try:
            value["settled_turn"] = self.settled_turn[name].certificate(
                self.get_clock().now().nanoseconds)
        except ValueError as error:
            self.halted = "settled_turn_model_failure"
            self.record("settled_turn_model_failure", {"robot": name, "reason": str(error)})
            return None
        return value

    def topology_ready(self):
        expected = [("/", "motion_safety")]
        return all([(row.node_namespace, row.node_name) for row in
                    self.get_publishers_info_by_topic(f"/{name}/cmd_vel")] == expected
                   for name in ROBOTS)

    def tick(self):
        clock_ns = self.get_clock().now().nanoseconds
        now = clock_ns / 1e9
        observers_ready = self.local_observers_ready()
        if not observers_ready and not self.observers_started:
            self.ready_pub.publish(Bool(data=False))
            self.record("output_observer_wait", {"clock_ns": clock_ns})
            return
        self.observers_started = True
        states = {row["name"]: row for row in self.received["robots"]} if self.received else {}
        own = {name: self.local_state(name) for name in ROBOTS}
        healthy = (observers_ready and self.topology_ready()
                   and all(valid_state(own[name], now, self.epoch)
                   and valid_state(states.get(name), now, self.epoch) for name in ROBOTS))
        ready = Bool(data=healthy)
        self.ready_pub.publish(ready)
        if self.started and not healthy and self.halted is None:
            self.halted = "motion_state_or_topology_unavailable"
        if self.halted and self.started and not self.failure_sent:
            self.failure_sent = True
            self.failure_pub.publish(String(data=json.dumps({
                "component": "motion_safety", "reason": self.halted})))
        phase_outputs = {}
        for name in ROBOTS:
            peers = {peer: states.get(peer) for peer in ROBOTS if peer != name}
            request = self.requests.get(name)
            if not healthy:
                reason = "state_or_topology_unavailable"
            elif not self.started:
                reason = "before_release"
            elif self.halted or (self.stop_time is not None
                                 and clock_ns >= timestamp_ns(self.stop_time)):
                reason = self.halted or "task_stopped"
            elif (request is None
                  or not 0 <= elapsed_ns(request["received_stamp"], now)
                  <= timestamp_ns(COMMAND_TIMEOUT_SEC)):
                reason = "command_timeout"
            elif not request["publisher_identity"]["valid"]:
                reason = "command_publisher_unavailable"
            elif not request["supported"]:
                reason = "unsupported_command"
            else:
                reason = None
            if reason is None:
                decision = guard_motion([request["v"], request["w"]], own[name], peers,
                                        now, self.epoch)
            else:
                decision = {"allow": False, "reason": reason,
                            "output": [0., 0.], "minimum_margin_m": None}
            self.decision_sequences[name] += 1
            rotation = (decision.get("component_filter") or {}).get("rotation_check", {})
            if (decision["reason"] == "settled_turn_drift_reserve"
                    or rotation.get("reason") == "settled_turn_drift_reserve"):
                self.settled_turn[name].activate(clock_ns)
            self.settled_turn[name].output(decision["output"][0], clock_ns,
                                           self.decision_sequences[name])
            self.record("decision", {"robot": name, "clock_ns": clock_ns,
                                     "decision_sequence": self.decision_sequences[name],
                                     "request": request, "own_state": own[name],
                                     "received_peers": peers, "decision": decision,
                                     "started": self.started, "ready": healthy})
            self.pending_outputs[name].append({"sequence": self.decision_sequences[name],
                                               "clock_ns": clock_ns,
                                               "output": decision["output"]})
            output = Twist()
            output.linear.x, output.angular.z = decision["output"]
            self.outputs[name].publish(output)
            target = {"schema": "mr3-drive-target-v1", "epoch": self.epoch, "robot": name,
                      "clock_ns": clock_ns, "decision_sequence": self.decision_sequences[name],
                      "linear_x": output.linear.x, "angular_z": output.angular.z}
            encoded = json.dumps(target, sort_keys=True, allow_nan=False)
            self.drive_targets[name].publish(String(data=encoded))
            if self.drive_audit is not None:
                self.drive_record_sequence += 1
                self.drive_audit.write(json.dumps({
                    "schema": "mr3-drive-target-publication-v1", "epoch": self.epoch,
                    "record_sequence": self.drive_record_sequence,
                    "wall_monotonic_ns": time.monotonic_ns(), "target_json": encoded,
                }, sort_keys=True, allow_nan=False) + "\n")
            phase_outputs[name] = {"linear_x": output.linear.x, "angular_z": output.angular.z}
        if self.get_clock().now().nanoseconds == clock_ns:
            self.pending_status = {clock_ns: {
                "schema": "mr3-motion-safety-status-v1", "epoch": self.epoch,
                "clock_ns": clock_ns, "ready": healthy,
                "completion_scope": "publication_and_local_topic_receipt",
                "decision_sequences": dict(self.decision_sequences), "outputs": phase_outputs}}
            self.publish_completed_status(clock_ns)
        else:
            self.record("clock_changed_during_decision", {"decision_clock_ns": clock_ns})


def main(args=None):
    rclpy.init(args=args)
    node = MotionSafety()
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        executor.shutdown(timeout_sec=5.)
        if node.audit is not None:
            node.audit.close()
        if node.drive_audit is not None:
            node.drive_audit.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
