"""Paused guard commits and a separate, permanently latched zero-stop channel."""

from collections import OrderedDict
import copy
import hashlib
import json
import re
from time import monotonic, monotonic_ns

from rclpy.clock import Clock, ClockType
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import String

from multi_robot_exploration.mr3_control_phase import canonical, WALL_GUARD_SEC


class MotionControlPhase:
    """One real guard commit per clock, after actual received dependencies.

    Emergency stops have their own status and can only publish zero. They never
    replace a normal ACK or certify missing state as safe.
    """

    def __init__(self, node):
        self.node = node
        self.controlled = False
        self.stopping = False
        self.polling = False
        self.pending = None
        self.responses = OrderedDict()
        self.dependencies = {"state": OrderedDict(), "peer": OrderedDict()}
        self.normal_clocks = set()
        durable = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.publisher = node.create_publisher(String, "/motion_safety/control_ack", durable)
        self.stop_publisher = node.create_publisher(String, "/motion_safety/stop_status", durable)
        self.subscriptions = [node.create_subscription(
            String, "/motion_safety/control_request", self.receive_request, 10)]
        for component, topic in (("state", "/mr3/state_phase_ack"),
                                 ("peer", "/mr3/peer_phase_ack")):
            self.subscriptions.append(node.create_subscription(
                String, topic,
                lambda message, component=component: self.receive_dependency(message, component),
                10))
        self.timer = node.create_timer(
            .02, self.poll, clock=Clock(clock_type=ClockType.STEADY_TIME))

    def record(self, kind, payload):
        self.node.record("control_" + kind, payload)

    def receive_dependency(self, message, component):
        try:
            value = json.loads(message.data)
            if not isinstance(value, dict):
                raise ValueError("dependency ACK must be an object")
            if value.get("epoch") != self.node.epoch:
                return
            key = value["request_id"]
            if not isinstance(key, str) or not key:
                raise ValueError("invalid dependency request identity")
            previous = self.dependencies[component].get(key)
            if previous is not None and canonical(previous) != canonical(value):
                raise ValueError("actual dependency ACK changed")
            self.dependencies[component][key] = value
            while len(self.dependencies[component]) > 64:
                self.dependencies[component].popitem(last=False)
            self.record("dependency", {"component": component, "value": value})
            self.poll()
        except (ValueError, KeyError, TypeError) as error:
            self.node.halted = self.node.halted or "invalid_control_dependency"
            self.record("failure", {"error": str(error)})
            self.ensure_stop()

    def receive_request(self, message):
        request = None
        try:
            request = json.loads(message.data)
            if not isinstance(request, dict):
                raise ValueError("motion control request must be an object")
            if request.get("epoch") != self.node.epoch:
                return
            if (request.get("schema") != "mr3-motion-control-request-v1"
                    or not isinstance(request.get("request_id"), str)
                    or not request["request_id"]
                    or type(request.get("target_time_ns")) is not int
                    or request["target_time_ns"] < 0
                    or request.get("operation") not in ("takeover", "commit", "stop")):
                raise ValueError("invalid motion control request")
            key = request["request_id"]
            self.record("request", request)
            previous = self.responses.get(key)
            if previous is not None:
                if canonical(previous[0]) != canonical(request):
                    raise ValueError("motion control request identity changed")
                self.publish_ack(previous[1], cached=True)
                return
            if self.pending is not None:
                if canonical(self.pending["request"]) == canonical(request):
                    self.poll()
                    return
                if request["operation"] != "stop":
                    raise ValueError("overlapping motion control requests")
                self.record("abandoned", self.pending["request"])
            self.pending = {"request": copy.deepcopy(request), "started": monotonic(),
                            "issued": False}
            if request["operation"] == "takeover":
                if self.node.started or self.controlled:
                    raise ValueError("motion takeover is only available before release")
                self.controlled = True
                self.node.timer.cancel()
            elif request["operation"] == "stop":
                self.controlled = True
                self.stopping = True
                self.node.timer.cancel()
            elif not self.controlled and request["operation"] != "stop":
                raise ValueError("motion control has not taken over")
            self.poll()
        except (ValueError, KeyError, TypeError) as error:
            self.record("failure", {"request": request, "error": str(error)})
            self.node.halted = "invalid_motion_control_request"
            self.ensure_stop()
            if self.pending is not None:
                self.finish(error=str(error))

    def ensure_stop(self):
        if not self.controlled:
            return
        self.stopping = True
        clock = self.node.get_clock().now().nanoseconds
        self.node.ensure_motion_output(clock, stop=True)

    def dependency_ready(self, request):
        target, key = request["target_time_ns"], request["request_id"]
        state, peer = request.get("state_commit"), request.get("peer_commit")
        if not isinstance(state, dict) or not isinstance(peer, dict):
            raise ValueError("normal commit requires state and obstacle receipts")
        for component, expected in (("state", state), ("peer", peer)):
            actual = self.dependencies[component].get(key)
            if actual is None:
                return False
            if canonical(actual) != canonical(expected):
                raise ValueError("request substituted an unreceived dependency")
            if (actual.get("schema") != "mr3-" + component + "-phase-ack-v1"
                    or actual.get("epoch") != self.node.epoch or actual.get("request_id") != key
                    or actual.get("operation") != "commit" or actual.get("ok") is not True
                    or type(actual.get("target_time_ns")) is not int
                    or actual["target_time_ns"] != target
                    or type(actual.get("clock_ns")) is not int or actual["clock_ns"] != target):
                raise ValueError("dependency clock/operation differs")
        if (state.get("scope") != "actual_state_and_side_publish_calls_returned"
                or peer.get("scope") != "actual_obstacle_publish_calls_returned"
                or canonical(peer.get("state_commit")) != canonical(state)
                or type(state.get("state_sequence")) is not int or state["state_sequence"] <= 0
                or type(peer.get("state_sequence")) is not int
                or type(peer.get("commit_sequence")) is not int or peer["commit_sequence"] <= 0
                or not isinstance(state.get("bundle_sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", state["bundle_sha256"]) is None
                or peer.get("state_sequence") != state.get("state_sequence")
                or peer.get("bundle_sha256") != state.get("bundle_sha256")):
            raise ValueError("obstacle receipt belongs to another state")
        received = self.node.received
        if received is None:
            return False
        digest = hashlib.sha256(canonical(received).encode()).hexdigest()
        return (type(state.get("state_sequence")) is int
                and received.get("sequence") == state["state_sequence"]
                and digest == state.get("bundle_sha256"))

    def poll(self):
        if self.polling:
            return
        self.polling = True
        try:
            self.poll_once()
        finally:
            self.polling = False

    def poll_once(self):
        pending = self.pending
        if pending is None:
            return
        request = pending["request"]
        target, operation = request["target_time_ns"], request["operation"]
        now = self.node.get_clock().now().nanoseconds
        try:
            if now > target or monotonic() - pending["started"] >= WALL_GUARD_SEC:
                raise ValueError("motion control clock passed or wall timeout")
            if now < target:
                return
            stop = operation == "stop" or (operation == "commit" and (
                self.stopping or self.node.halted is not None or self.node.stop_time is not None
                and now >= round(self.node.stop_time * 1e9)))
            if stop:
                self.stopping = True
                self.node.ensure_motion_output(target, stop=True)
            elif operation == "takeover":
                if self.stopping or self.node.halted is not None:
                    raise ValueError("motion takeover was stopped")
                self.node.ensure_motion_output(target, stop=False)
            elif not pending["issued"]:
                if (target in self.normal_clocks
                        or (target, "normal") in self.node.issued_motion):
                    raise ValueError("normal clock already committed")
                if (not self.dependency_ready(request)
                        or not self.node.control_inputs_ready(target)):
                    if self.node.halted:
                        self.ensure_stop()
                    return
                self.normal_clocks.add(target)
                pending["issued"] = True
                self.node.ensure_motion_output(target, stop=False)
                self.record("commit", {"request": request})
            status = self.node.completed_motion.get((target, "stop" if stop else "normal"))
            if status is None:
                return
            if status.get("decision_sequences") != self.node.decision_sequences:
                return
            if operation == "takeover" and any(
                    canonical(output) != canonical({"linear_x": 0., "angular_z": 0.})
                    for output in status["outputs"].values()):
                raise ValueError("takeover requires actual pre-release zero outputs")
            self.finish(status=status)
        except (ValueError, KeyError, TypeError) as error:
            self.node.halted = self.node.halted or "motion_control_phase_failed"
            self.record("failure", {"request": request, "error": str(error)})
            self.ensure_stop()
            self.finish(error=str(error))

    def finish(self, status=None, error=None):
        if self.pending is None:
            return
        request = self.pending["request"]
        value = {"schema": "mr3-motion-control-ack-v1", "epoch": self.node.epoch,
                 "request_id": request["request_id"], "target_time_ns": request["target_time_ns"],
                 "clock_ns": self.node.get_clock().now().nanoseconds,
                 "operation": request["operation"], "ok": error is None}
        if error is None:
            value["status"] = copy.deepcopy(status)
        else:
            value["error"] = error
        self.responses[request["request_id"]] = (copy.deepcopy(request), value)
        while len(self.responses) > 64:
            self.responses.popitem(last=False)
        self.pending = None
        self.record("ack", value)
        self.publish_ack(value)

    def publish_ack(self, value, cached=False):
        started = monotonic_ns()
        self.publisher.publish(String(data=canonical(value)))
        self.record("cached_ack_published" if cached else "ack_published", {
            "ack": value, "publish_started_wall_monotonic_ns": started,
            "publish_completed_wall_monotonic_ns": monotonic_ns()})
