"""The adapter's unique final Twist publisher with received-peer braking guards."""

from collections import deque
import hashlib
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
    COMMAND_TIMEOUT_SEC, PERIOD_SEC, ROBOTS, SettledTurnTracker, guard_motion,
    measured_velocity_error, valid_state,
)
from multi_robot_exploration.mr3_motion_control import MotionControlPhase


class MotionSafety(Node):
    """Three logical local gates; robot i never reads another robot's raw state."""

    def __init__(self):
        super().__init__("motion_safety")
        self.epoch = self.declare_parameter("episode_epoch", "").value
        stepped = self.declare_parameter("stepped_mode", False).value
        audit_path = self.declare_parameter("audit_path", "").value
        diagnostic_enabled = self.declare_parameter("mr3_diagnostic_enabled", False).value
        if not self.epoch:
            raise ValueError("motion safety requires an episode epoch")
        if type(diagnostic_enabled) is not bool or (diagnostic_enabled and not stepped):
            raise ValueError("diagnostic request receipts require explicit stepped execution")
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
        self.own_input_history = {
            name: {kind: deque(maxlen=256) for kind in ("odom", "tf")} for name in ROBOTS}
        self.issued_motion = set()
        self.completed_motion = {}
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
        self.normal_control_model_fault = None
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.outputs = {name: self.create_publisher(Twist, f"/{name}/cmd_vel", 20)
                        for name in ROBOTS}
        self.drive_targets = {
            name: self.create_publisher(String, f"/{name}/mr3_drive/target", durable)
            for name in ROBOTS}
        self.ready_pub = self.create_publisher(Bool, "/motion_safety/ready", durable)
        self.status_pub = self.create_publisher(String, "/motion_safety/status", durable)
        self.failure_pub = self.create_publisher(String, "/exploration_failure", durable)
        self.diagnostic_receipt_pub = (
            self.create_publisher(String, "/motion_safety/diagnostic_request_receipt", 20)
            if diagnostic_enabled else None)
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
        self.control_phase = MotionControlPhase(self) if stepped else None
        self.record("configuration", {
            "robots": list(ROBOTS),
            "input_topics": [f"/{name}/cmd_vel_unguarded" for name in ROBOTS],
            "output_topics": [f"/{name}/cmd_vel" for name in ROBOTS],
            "source_scope": "each own local odom/TF plus received peer states only",
            "twist_source_stamp_available": False,
            "own_input_selection": "latest_causal_v1",
            "controlled_execution": stepped,
            "diagnostic_request_receipts": diagnostic_enabled,
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
        self.own_input_history[name]["odom"].append(
            (self.input_sequences[name]["odom"], message))
        payload = odom_payload(message)
        self.record("own_odom", {"robot": name,
                                 "input_sequence": self.input_sequences[name]["odom"],
                                 "message": payload})
        try:
            self.settled_turn[name].observe(payload, self.input_sequences[name]["odom"])
        except (ValueError, KeyError, TypeError) as error:
            self.halted = "settled_turn_model_failure"
            self.record("settled_turn_model_failure", {"robot": name, "reason": str(error)})
            self.stop_controlled()

    def receive_tf(self, message, name):
        for transform in message.transforms:
            if (transform.header.frame_id.lstrip("/") == "map"
                    and transform.child_frame_id.lstrip("/") == "odom"):
                self.transforms[name] = transform
                self.input_sequences[name]["tf"] += 1
                self.own_input_history[name]["tf"].append(
                    (self.input_sequences[name]["tf"], transform))
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
        if getattr(self, "diagnostic_receipt_pub", None) is not None and name == "tb3":
            # This ACK is emitted by the real consuming callback. Twist has no
            # source epoch/sequence: the worker pairs this observed input with
            # its single in-flight, epoch-bound smoother service publication.
            receipt = {"schema": "mr3-guard-diagnostic-receipt-v1", "epoch": self.epoch,
                       "robot": name, "clock_ns": self.get_clock().now().nanoseconds,
                       "input_sequence": request["sequence"], "v": request["v"],
                       "w": request["w"], "supported": supported,
                       "publisher_identity": request["publisher_identity"],
                       "scope": "real_guard_request_callback; graph_at_callback_identity; "
                                "not_guard_decision_or_driver_storage"}
            self.diagnostic_receipt_pub.publish(String(data=json.dumps(receipt, allow_nan=False)))
            self.record("diagnostic_request_receipt", receipt)

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
        else:
            self.stop_controlled()

    def publish_completed_status(self, clock_ns):
        for key, status in list(self.pending_status.items()):
            if (status["clock_ns"] != clock_ns
                    or self.get_clock().now().nanoseconds != clock_ns
                    or not all(self.observed_sequences[name] >= status["decision_sequences"][name]
                               for name in ROBOTS)):
                continue
            kind = status.get("phase_kind", "normal")
            started = time.monotonic_ns()
            if kind == "normal":
                self.status_pub.publish(String(data=json.dumps(status)))
            else:
                self.control_phase.stop_publisher.publish(String(data=json.dumps(status)))
            if hasattr(self, "completed_motion"):
                self.completed_motion[(clock_ns, kind)] = status
                while len(self.completed_motion) > 128:
                    del self.completed_motion[next(iter(self.completed_motion))]
            self.pending_status.pop(key)
            self.record("output_completed", {
                "status": status, "publish_started_wall_monotonic_ns": started,
                "publish_completed_wall_monotonic_ns": time.monotonic_ns()})
        if getattr(self, "control_phase", None) is not None:
            self.control_phase.poll()

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
            release_ns = message.stamp.sec * 1_000_000_000 + message.stamp.nanosec
            try:
                for tracker in self.settled_turn.values():
                    tracker.release(release_ns)
            except ValueError as error:
                self.halted = "invalid_exploration_release"
                self.record("failure", {"data": str(error)})
                return
            self.started = True
            self.record("release", {"stamp": message.stamp.sec + message.stamp.nanosec / 1e9})

    def receive_stop(self, message):
        self.stop_time = self.now()
        self.record("stop_request", {"stamp": message.stamp.sec + message.stamp.nanosec / 1e9})
        self.stop_controlled()

    def receive_terminal(self, message):
        try:
            value = json.loads(message.data)
            if value["epoch"] == self.epoch:
                stamp = value["end_sim_time_sec"]
                if type(stamp) not in (int, float) or not math.isfinite(stamp):
                    raise ValueError("terminal time must be finite")
                self.stop_time = stamp
                self.record("terminal", value)
                self.stop_controlled()
        except (ValueError, KeyError, TypeError) as error:
            self.halted = "invalid_terminal_notice"
            self.record("invalid_terminal_notice", {"reason": str(error)})
            self.stop_controlled()

    def receive_failure(self, message):
        self.halted = self.halted or "external_safety_failure"
        self.record("failure", {"data": message.data})
        self.stop_controlled()

    def stop_controlled(self):
        if getattr(self, "control_phase", None) is not None:
            self.control_phase.ensure_stop()

    def local_state(self, name):
        if name not in self.odometry or name not in self.transforms:
            return None
        odometry, transform = self.odometry[name], self.transforms[name]
        sequences = {key: self.input_sequences[name][key] for key in ("odom", "tf")}
        if hasattr(self, "own_input_history"):
            now_ns = self.get_clock().now().nanoseconds
            for kind, lead in (("odom", 0), ("tf", 200_000_000)):
                eligible = [(sequence, item) for sequence, item
                            in self.own_input_history[name][kind]
                            if item.header.stamp.sec * 1_000_000_000
                            + item.header.stamp.nanosec - lead <= now_ns]
                if not eligible:
                    return None
                sequence, selected = max(eligible, key=lambda value: (
                    value[1].header.stamp.sec, value[1].header.stamp.nanosec, value[0]))
                sequences[kind] = sequence
                if kind == "odom":
                    odometry = selected
                else:
                    transform = selected
        if (odometry.header.frame_id.lstrip("/") != "odom"
                or odometry.child_frame_id.lstrip("/") not in ("base_footprint", "base_link")):
            return None
        for rotation in (odometry.pose.pose.orientation, transform.transform.rotation):
            values = [getattr(rotation, axis) for axis in ("x", "y", "z", "w")]
            if (not all(math.isfinite(value) for value in values)
                    or abs(sum(value * value for value in values) - 1.) > .01):
                return None
        value = state_payload(name, odometry, transform, .2)
        value.pop("odometry")
        value.pop("transform")
        value.update(epoch=self.epoch, valid=True,
                     source_stamp=min(value["odom_source_stamp"], value["tf_source_stamp"]),
                     input_sequences=sequences)
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
        phase = getattr(self, "control_phase", None)
        if phase is not None:
            if not phase.controlled:
                self.ensure_motion_output(self.get_clock().now().nanoseconds)
            return
        self.emit_motion()

    def normal_velocity_fault(self, clock_ns):
        """Normal-control eligibility, not task-body attribution from callback order.

        Called only by a controlled normal commit after its real state/peer
        dependencies match. Current selected own raw plus received peer raw
        must satisfy the declared body norms. After release, every retained
        causal own raw sample is checked as well, so a later healthy sample
        cannot hide an intermediate peak. Warmup callbacks never latch this
        fault. A terminal received later cannot convert a real negative ACK
        into training data; actual task source-window attribution stays offline.
        """
        if type(clock_ns) is not int or clock_ns < 0:
            raise ValueError("invalid normal model check clock")

        def source_ns(payload):
            stamp = payload["header"]["stamp"]
            if (type(stamp["sec"]) is not int or type(stamp["nanosec"]) is not int
                    or stamp["sec"] < 0 or not 0 <= stamp["nanosec"] < 1_000_000_000):
                raise ValueError("invalid normal model odometry source")
            return stamp["sec"] * 1_000_000_000 + stamp["nanosec"]

        def fault(name, role, error, raw, sequence, release_ns, state=None):
            try:
                digest = hashlib.sha256(json.dumps(
                    raw, sort_keys=True, separators=(",", ":"), allow_nan=False
                ).encode()).hexdigest()
            except (ValueError, TypeError):
                digest = None
            twist = raw.get("twist") if isinstance(raw, dict) else None
            twist = twist.get("twist") if isinstance(twist, dict) else None
            try:
                stamp = source_ns(raw)
            except (ValueError, KeyError, TypeError):
                stamp = None
            return {"schema": "mr3-normal-control-model-fault-v1",
                    "reason": error, "robot": name, "role": role,
                    "commit_clock_ns": clock_ns, "input_sequence": sequence,
                    "odom_source_ns": stamp,
                    "known_release_ns": release_ns,
                    "known_stop_time_ns": (None if self.stop_time is None
                                           else timestamp_ns(self.stop_time)),
                    "state_sequence": None if self.received is None
                    else self.received.get("sequence"),
                    "state_source_stamp": None if state is None else state.get("source_stamp"),
                    "twist": twist, "odom_payload_sha256": digest,
                    "classification": "normal_control_model_invalid_not_task_attributed",
                    "scope": "normal commit eligibility; task release/end attribution is offline"}

        states = {row["name"]: row for row in self.received["robots"]} if self.received else {}
        for name in ROBOTS:
            release_ns = self.settled_turn[name].release_ns if self.started else None
            own = self.local_state(name)
            selected_sequence = None if own is None else own["input_sequences"]["odom"]
            for sequence, message in self.own_input_history[name]["odom"]:
                stamp = message.header.stamp
                stamp_ns = stamp.sec * 1_000_000_000 + stamp.nanosec
                selected = sequence == selected_sequence
                historical = (release_ns is not None and release_ns <= stamp_ns <= clock_ns)
                if not selected and not historical:
                    continue
                if stamp_ns > clock_ns:
                    continue  # Retain future source; it is not a causal normal input yet.
                twist = {kind: {axis: getattr(getattr(message.twist.twist, kind), axis)
                                for axis in ("x", "y", "z")}
                         for kind in ("linear", "angular")}
                check = dict(own) if selected else {}
                check["odometry"] = {"twist": {"twist": twist}}
                error = measured_velocity_error(check, require_raw=True)
                if error is not None:
                    return fault(name, "selected_own" if selected else "own_history",
                                 error, odom_payload(message), sequence, release_ns, own)
            peer = states.get(name)
            if isinstance(peer, dict) and peer.get("epoch") == self.epoch:
                # Missing/future/stale state remains the existing readiness wait;
                # a received valid current-epoch raw model violation is explicit.
                stamps = [peer.get(key) for key in
                          ("source_stamp", "odom_source_stamp", "tf_source_stamp")]
                if (peer.get("valid") is True
                        and all(type(stamp) in (int, float) and math.isfinite(stamp)
                                and stamp > 0 for stamp in stamps)):
                    if any(not 0 <= elapsed_ns(stamp, clock_ns / 1e9) <= 500_000_000
                           for stamp in stamps):
                        continue
                    error = measured_velocity_error(peer, require_raw=True)
                    if error is not None:
                        return fault(name, "received_peer", error, peer.get("odometry"),
                                     peer.get("sequence"), release_ns, peer)
        return None

    def control_inputs_ready(self, clock_ns):
        now = clock_ns / 1e9
        states = {row["name"]: row for row in self.received["robots"]} if self.received else {}
        return (self.local_observers_ready() and self.topology_ready()
                and all(valid_state(self.local_state(name), now, self.epoch)
                        and valid_state(states.get(name), now, self.epoch, require_raw=True)
                        for name in ROBOTS))

    def ensure_motion_output(self, clock_ns, stop=False):
        key = (clock_ns, "stop" if stop else "normal")
        if key in self.issued_motion:
            return
        if self.get_clock().now().nanoseconds != clock_ns:
            raise ValueError("motion output clock differs from phase")
        self.emit_motion(stop=stop)

    def emit_motion(self, stop=False):
        clock_ns = self.get_clock().now().nanoseconds
        now = clock_ns / 1e9
        observers_ready = self.local_observers_ready()
        if not observers_ready and not self.observers_started and not stop:
            self.ready_pub.publish(Bool(data=False))
            self.record("output_observer_wait", {"clock_ns": clock_ns})
            return
        self.observers_started = True
        states = {row["name"]: row for row in self.received["robots"]} if self.received else {}
        own = {name: self.local_state(name) for name in ROBOTS}
        healthy = (observers_ready and self.topology_ready()
                   and all(valid_state(own[name], now, self.epoch)
                   and valid_state(states.get(name), now, self.epoch, require_raw=True)
                   for name in ROBOTS))
        if hasattr(self, "issued_motion"):
            self.issued_motion.add((clock_ns, "stop" if stop else "normal"))
        healthy = healthy and not stop
        ready = Bool(data=healthy)
        self.ready_pub.publish(ready)
        if self.started and not healthy and not stop and self.halted is None:
            self.halted = "motion_state_or_topology_unavailable"
        if (self.halted and self.halted != "normal_control_model_invalid"
                and self.started and not self.failure_sent):
            self.failure_sent = True
            self.failure_pub.publish(String(data=json.dumps({
                "component": "motion_safety", "reason": self.halted})))
        phase_outputs = {}
        for name in ROBOTS:
            peers = {peer: states.get(peer) for peer in ROBOTS if peer != name}
            request = self.requests.get(name)
            if stop:
                reason = self.halted or "controlled_stop"
            elif not healthy:
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
                                     "started": self.started, "ready": healthy,
                                     **({"phase_kind": "stop"} if stop else {})})
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
            status = {
                "schema": "mr3-motion-safety-status-v1", "epoch": self.epoch,
                "clock_ns": clock_ns, "ready": healthy,
                "completion_scope": "publication_and_local_topic_receipt",
                "decision_sequences": dict(self.decision_sequences), "outputs": phase_outputs}
            if stop:
                status["phase_kind"] = "stop"
            self.pending_status[(clock_ns, "stop" if stop else "normal")] = status
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
