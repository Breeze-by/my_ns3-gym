"""Represent observed peer bodies in a dedicated Nav2 obstacle layer."""

import copy
import hashlib
import json
import math
from pathlib import Path
import struct
import time

from action_msgs.msg import GoalStatus, GoalStatusArray
from nav_msgs.msg import Odometry
import numpy as np
import rclpy
from rclpy.clock import Clock, ClockType
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan, PointCloud2, PointField
from std_msgs.msg import Header, String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.mr3_information import (
    odom_payload, publisher_graph_identity, transform_payload, uses_reach_contract,
)
from multi_robot_exploration.mr3_safety_intent import (
    parse_json, payload_sha256, validate_intent_refs, validate_safety,
)

from multi_robot_exploration.control import (
    PEER_BODY_RADIUS_M, peer_safety_radius, quaternion_yaw, transform_point_2d,
)


BEAM_COUNT = 2048
MAX_RANGE_M = 20.0


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def payload_sha(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def stamp_ns(stamp):
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def message_header(message):
    return {"frame_id": message.header.frame_id,
            "stamp": {"sec": message.header.stamp.sec,
                      "nanosec": message.header.stamp.nanosec}}


def obstacle_payload(message, kind):
    """Bind actual ROS output fields without encoding infinity as JSON NaN."""
    if kind == "scan":
        ranges = list(message.ranges)
        return {"header": message_header(message),
                **{key: getattr(message, key) for key in (
                    "angle_min", "angle_max", "angle_increment", "time_increment", "scan_time",
                    "range_min", "range_max")},
                "range_count": len(ranges),
                "all_ranges_positive_infinity": all(value == math.inf for value in ranges),
                "ranges_sha256": hashlib.sha256(struct.pack("<" + "f" * len(ranges),
                                                            *ranges)).hexdigest(),
                "intensities": list(message.intensities)}
    return {"header": message_header(message), "height": message.height, "width": message.width,
            "fields": [{"name": field.name, "offset": field.offset,
                        "datatype": field.datatype, "count": field.count}
                       for field in message.fields],
            "is_bigendian": message.is_bigendian, "point_step": message.point_step,
            "row_step": message.row_step, "is_dense": message.is_dense,
            "data_bytes": len(message.data),
            "data_sha256": hashlib.sha256(bytes(message.data)).hexdigest()}


def body_points(peers):
    """Fill observed (x, y, source_age) peer disks with dense marking points."""
    groups = []
    for x, y, age in peers:
        radius = peer_safety_radius(age)
        offsets = np.arange(-radius, radius + 0.025, 0.025)
        dx, dy = np.meshgrid(offsets, offsets)
        inside = dx * dx + dy * dy <= radius * radius
        groups.append(np.column_stack((x + dx[inside], y + dy[inside], np.zeros(inside.sum()))))
    return np.concatenate(groups).astype("<f4") if groups else np.empty((0, 3), dtype="<f4")


def overlap_diagnostic(poses, odometry, transforms, now, tf_source_lead):
    """Retain the exact received inputs of the existing centre-distance gate.

    This is evidence, not a predictive collision check. Received ROS messages
    do not carry the transport epoch/sequence, and their stamps need not match.
    """
    def vector(message, axes):
        return {axis: (getattr(message, axis) if math.isfinite(getattr(message, axis)) else None)
                for axis in axes}

    pairs = []
    names = list(poses)
    for index, name in enumerate(names):
        for other in names[index + 1:]:
            distance = math.hypot(poses[other][0] - poses[name][0],
                                  poses[other][1] - poses[name][1])
            if distance < 2 * PEER_BODY_RADIUS_M:
                pairs.append({"robots": [name, other], "centre_distance_m": distance,
                              "threshold_m": 2 * PEER_BODY_RADIUS_M})
    if not pairs:
        return None
    inputs = {}
    for name, (x, y, yaw, _) in poses.items():
        odom = odometry[name]
        transform = transforms[name]
        odom_stamp = odom.header.stamp.sec + odom.header.stamp.nanosec / 1e9
        tf_stamp = transform.header.stamp.sec + transform.header.stamp.nanosec / 1e9
        position, orientation = odom.pose.pose.position, odom.pose.pose.orientation
        translation, rotation = transform.transform.translation, transform.transform.rotation
        inputs[name] = {
            "estimated_map_pose": {"x": x, "y": y, "yaw": yaw},
            "odom_stamp_sec": odom_stamp, "odom_source_age_sec": now - odom_stamp,
            "tf_validity_stamp_sec": tf_stamp, "tf_source_stamp_sec": tf_stamp - tf_source_lead,
            "tf_source_age_sec": now - (tf_stamp - tf_source_lead),
            "odom_frame": odom.header.frame_id, "odom_child_frame": odom.child_frame_id,
            "tf_frame": transform.header.frame_id, "tf_child_frame": transform.child_frame_id,
            "odom_position": vector(position, ("x", "y", "z")),
            "odom_orientation": vector(orientation, ("x", "y", "z", "w")),
            "tf_translation": vector(translation, ("x", "y", "z")),
            "tf_rotation": vector(rotation, ("x", "y", "z", "w")),
            "odom_twist": {
                kind: vector(getattr(odom.twist.twist, kind), ("x", "y", "z"))
                for kind in ("linear", "angular")},
        }
    return {
        "schema": "mr3-peer-overlap-inputs-v1", "observation_sim_time_sec": now,
        "body_radius_m": PEER_BODY_RADIUS_M, "tf_source_lead_sec": tf_source_lead,
        "pairs": pairs, "received_inputs": inputs,
        "transport_epoch_missing": True, "transport_sequence_missing": True,
        "nonfinite_auxiliary_components_encoded_as_null": True,
        "scope": "received odom/TF gate inputs; no truth or actual-contact assertion",
    }


class PeerObstacles(Node):
    def __init__(self):
        super().__init__("peer_obstacles")
        count = self.declare_parameter("robot_count", 3).value
        if not 1 <= count <= 4:
            raise ValueError("robot_count must be between 1 and 4")
        self.names = [f"tb{i}" for i in range(1, count + 1)]
        self.transforms = {}
        self.odometry = {}
        self.mission_started = False
        self.failed = False
        self.stepped_mode = self.declare_parameter("stepped_mode", False).value
        self.safety_contract = self.declare_parameter("safety_contract", "legacy").value
        if (self.safety_contract not in ("legacy", "mr3-reach-v1")
                or uses_reach_contract(self) and (not self.stepped_mode or count != 3)):
            raise ValueError("mr3-reach-v1 peer input requires stepped three-robot execution")
        self.epoch = self.declare_parameter("episode_epoch", "mr3-p1b").value
        self.phase_controlled = False
        self.phase_pending = None
        self.phase_cache = {}
        self.phase_last_clock = None
        self.phase_commit_sequence = 0
        self.phase_record_sequence = 0
        self.phase_input_sequences = {(kind, name): 0 for kind in ("odom", "tf")
                                      for name in self.names}
        self.phase_input_cache = {(kind, name): [] for kind in ("odom", "tf")
                                  for name in self.names}
        self.phase_bundles = []
        self.phase_bundle_publisher_gid = None
        self.phase_input_topics = {}
        self.phase_audit = None
        self.tf_source_lead_sec = self.declare_parameter("tf_source_lead_sec", 0.).value
        self.publishers_by_robot = {
            name: self.create_publisher(LaserScan, f"/{name}/peer_obstacles", 1)
            for name in self.names
        }
        self.body_publishers = {
            name: self.create_publisher(PointCloud2, f"/{name}/peer_footprints", 1)
            for name in self.names
        }
        self.failure_publisher = self.create_publisher(
            String, "/exploration_failure",
            QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
        )
        self.inputs = []
        task_release_start = self.declare_parameter("task_release_start", False).value
        if task_release_start:
            self.inputs.append(self.create_subscription(
                Header, "/exploration_start", self.receive_release,
                QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL),
            ))
        for name in self.names:
            odom_subscription = self.create_subscription(
                Odometry, f"/{name}/odom", lambda msg, name=name: self.receive_odom(msg, name), 1)
            tf_subscription = self.create_subscription(
                TFMessage, f"/{name}/tf", lambda msg, name=name: self.receive_tf(msg, name), 20)
            self.inputs.extend([odom_subscription, tf_subscription])
            self.phase_input_topics["odom", name] = odom_subscription.topic_name
            self.phase_input_topics["tf", name] = tf_subscription.topic_name
            if not task_release_start:
                self.inputs.append(self.create_subscription(
                    GoalStatusArray, f"/{name}/navigate_to_pose/_action/status",
                    self.receive_status, 10,
                ))
        self.timer = self.create_timer(0.1, self.publish_obstacles)
        audit_path = self.declare_parameter("phase_audit_path", "").value
        if audit_path:
            self.phase_audit = Path(audit_path).open("x", buffering=1)
        if self.stepped_mode:
            if self.names != ["tb1", "tb2", "tb3"]:
                raise ValueError("stepped peer phases require exactly three robots")
            self.phase_ack_pub = self.create_publisher(
                String, "/mr3/peer_phase_ack",
                QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                           reliability=ReliabilityPolicy.RELIABLE))
            self.inputs.extend([
                self.create_subscription(String, "/mr3/peer_phase_request",
                                         self.receive_phase_request, 10),
                self.create_subscription(String, "/mr3/received/states",
                                         self.receive_state_bundle, 10),
            ])
            self.phase_timer = self.create_timer(
                .02, self.poll_phase, clock=Clock(clock_type=ClockType.STEADY_TIME))
        topics = {kind + ":" + name: topic
                  for (kind, name), topic in self.phase_input_topics.items()}
        self.record_phase("configuration", {"stepped_mode": self.stepped_mode,
                                            "tf_source_lead_sec": self.tf_source_lead_sec,
                                            "input_topics": topics})

    def record_phase(self, kind, payload):
        if getattr(self, "phase_audit", None) is None:
            return
        self.phase_record_sequence += 1
        self.phase_audit.write(canonical({
            "schema": ("mr3-peer-phase-audit-v2" if uses_reach_contract(self)
                       else "mr3-peer-phase-audit-v1"), "epoch": self.epoch,
            "record_sequence": self.phase_record_sequence, "kind": kind,
            "clock_ns": self.get_clock().now().nanoseconds,
            "wall_monotonic_ns": time.monotonic_ns(), "payload": payload}) + "\n")

    def capture_input(self, kind, name, message, raw):
        key = kind, name
        self.phase_input_sequences[key] += 1
        value = {"robot": name, "input_sequence": self.phase_input_sequences[key],
                 "raw": raw, "raw_sha256": payload_sha(raw),
                 "received_wall_monotonic_ns": time.monotonic_ns()}
        value["topic"] = self.phase_input_topics[key]
        self.phase_input_cache[key].append((value, copy.deepcopy(message)))
        self.phase_input_cache[key] = self.phase_input_cache[key][-32:]
        self.record_phase("received_" + kind, value)

    def receive_state_bundle(self, message):
        graph = None
        try:
            value = (parse_json(message.data) if uses_reach_contract(self)
                     else json.loads(message.data))
            if (value["epoch"] != self.epoch or len(value["robots"]) != 3
                    or {row["name"] for row in value["robots"]} != set(self.names)
                    or type(value["sequence"]) is not int or value["sequence"] < 1):
                raise ValueError("state bundle epoch/identity")
            row = {"message": value, "message_sha256": payload_sha(value),
                   "received_wall_monotonic_ns": time.monotonic_ns()}
            if uses_reach_contract(self):
                graph = publisher_graph_identity(
                    self, "/mr3/received/states", "mr3_information", "/",
                    getattr(self, "phase_bundle_publisher_gid", None))
                row["publisher_identity"] = graph
                if not graph["valid"]:
                    raise ValueError("received state publisher graph identity unavailable or changed")
                self.safety_bundle_evidence(value)
                self.phase_bundle_publisher_gid = graph["endpoints"][0]["endpoint_gid"]
            self.phase_bundles.append(row)
            self.phase_bundles = self.phase_bundles[-32:]
            self.record_phase("received_state_bundle", row)
        except (KeyError, ValueError, TypeError) as error:
            self.record_phase("invalid_state_bundle", {
                "reason": str(error),
                **({"raw_json": message.data, "publisher_identity": graph}
                   if uses_reach_contract(self) else {}),
            })

    def safety_bundle_evidence(self, bundle, clock_ns=None):
        if bundle.get("safety_contract") != "mr3-reach-v1":
            raise ValueError("received bundle lacks the explicit reach contract")
        table = {}
        for row in bundle["robots"]:
            name = row["name"]
            if name not in self.names or name in table or row.get("epoch") != self.epoch:
                raise ValueError("received safety table has invalid robot/epoch identities")
            table[name] = validate_safety(
                row["safety"], epoch=self.epoch, robot=name,
                selected_odom=row["odometry"], now_ns=clock_ns)
        if set(table) != set(self.names):
            raise ValueError("received safety table is incomplete")
        references = validate_intent_refs(bundle["intent_refs"], robots=self.names)
        actual = {name: {"intent_sequence": value["intent"]["intent_sequence"],
                         "payload_sha256": payload_sha256(value["intent"])}
                  for name, value in table.items()}
        digest = payload_sha256(table)
        if references != actual or bundle.get("safety_table_sha256") != digest:
            raise ValueError("received safety table digest/intent refs differ from actual payload")
        return {"safety_contract": "mr3-reach-v1", "safety_table_sha256": digest,
                "intent_refs": references}

    def receive_phase_request(self, message):
        request = None
        try:
            request = (parse_json(message.data) if uses_reach_contract(self)
                       else json.loads(message.data))
            version = 2 if uses_reach_contract(self) else 1
            if (not self.stepped_mode or request["schema"] != f"mr3-peer-phase-request-v{version}"
                    or request["epoch"] != self.epoch
                    or type(request["request_id"]) is not str or not request["request_id"]
                    or type(request["target_time_ns"]) is not int
                    or request["target_time_ns"] < 0
                    or request["operation"] not in ("takeover", "commit")):
                raise ValueError("invalid peer phase request")
            if uses_reach_contract(self):
                fields = {"schema", "epoch", "request_id", "target_time_ns", "operation"}
                if request["operation"] == "commit":
                    fields.add("state_commit")
                if set(request) != fields:
                    raise ValueError("invalid reach peer phase request fields")
            encoded = canonical(request)
            cached = self.phase_cache.get(request["request_id"])
            if cached is not None:
                if cached[0] != encoded:
                    raise ValueError("peer phase request identity conflict")
                self.publish_phase_ack(cached[1], "cached_ack_published")
                return
            if self.phase_pending is not None:
                if canonical(self.phase_pending["request"]) == encoded:
                    return
                raise ValueError("peer phase busy")
            if (self.phase_last_clock is not None
                    and request["target_time_ns"] <= self.phase_last_clock):
                raise ValueError("peer phase target clock not strictly newer")
            if request["operation"] == "commit":
                self.validate_state_commit(request)
                if any(self.phase_input_topics[kind, name]
                       != f"/mr3/received/{name}/{kind}"
                       for kind in ("odom", "tf") for name in self.names):
                    raise ValueError("peer side subscriptions do not use received-only topics")
                if not self.phase_controlled:
                    raise ValueError("peer phase takeover required before commit")
            else:
                if self.phase_controlled or "state_commit" in request:
                    raise ValueError("peer phase takeover is unique and has no state commit")
                self.phase_controlled = True
                timer = getattr(self, "timer", None)
                if timer is not None:
                    timer.cancel()
                self.record_phase("controlled", request)
            self.phase_pending = {"request": request, "requested_wall": time.monotonic()}
            self.record_phase("request_received", request)
            self.poll_phase()
        except (KeyError, ValueError, TypeError, OverflowError) as error:
            if isinstance(request, dict):
                self.phase_response(request, False, error=str(error), cache=False)
            else:
                self.record_phase("invalid_phase_request", {"reason": str(error)})

    def validate_state_commit(self, request):
        state = request["state_commit"]
        target = request["target_time_ns"]
        version = 2 if uses_reach_contract(self) else 1
        if (state["schema"] != f"mr3-state-phase-ack-v{version}" or state["epoch"] != self.epoch
                or state["request_id"] != request["request_id"] or state["ok"] is not True
                or state["operation"] != "commit"
                or type(state["target_time_ns"]) is not int or state["target_time_ns"] != target
                or type(state["clock_ns"]) is not int or state["clock_ns"] != target
                or type(state["state_sequence"]) is not int or state["state_sequence"] < 1
                or state["scope"] != "actual_state_and_side_publish_calls_returned"
                or set(state["robots"]) != set(self.names)
                or self.tf_source_lead_sec != .2):
            raise ValueError("invalid state commit identity/scope")
        for field in ("side_publish_started_wall_monotonic_ns",
                      "bundle_publish_started_wall_monotonic_ns"):
            if type(state[field]) is not int or state[field] <= 0:
                raise ValueError("invalid state publication start identity")
        digests = [state["bundle_sha256"]] + [
            row[key] for row in state["robots"].values()
            for key in ("odom_sha256", "tf_sha256")]
        if uses_reach_contract(self):
            if state.get("safety_contract") != "mr3-reach-v1":
                raise ValueError("state commit safety contract differs")
            validate_intent_refs(state["intent_refs"], robots=self.names)
            digests += [state["safety_table_sha256"]]
            digests += [row["safety_sha256"] for row in state["robots"].values()]
        for digest in digests:
            if (type(digest) is not str or len(digest) != 64
                    or any(char not in "0123456789abcdef" for char in digest)):
                raise ValueError("invalid state payload digest")
        for name, row in state["robots"].items():
            if (row["odom_topic"] != f"/mr3/received/{name}/odom"
                    or row["tf_topic"] != f"/mr3/received/{name}/tf"
                    or any(type(row[key]) is not int or row[key] <= 0
                           for key in ("sequence", "version", "source_ns", "odom_source_ns",
                                       "tf_source_ns"))
                    or row["source_ns"] != min(row["odom_source_ns"], row["tf_source_ns"])
                    or not 0 <= target - row["source_ns"] <= 500_000_000):
                raise ValueError("invalid state side references/source age")

    def publish_phase_ack(self, response, kind="ack_published"):
        started = time.monotonic_ns()
        self.phase_ack_pub.publish(String(data=canonical(response)))
        completed = time.monotonic_ns()
        self.record_phase(kind, {"ack": response,
                                 "publish_started_wall_monotonic_ns": started,
                                 "publish_completed_wall_monotonic_ns": completed})

    def phase_response(self, request, ok, cache=True, **details):
        version = 2 if uses_reach_contract(self) else 1
        response = {"schema": f"mr3-peer-phase-ack-v{version}", "epoch": self.epoch,
                    "request_id": request.get("request_id"),
                    "target_time_ns": request.get("target_time_ns"),
                    "operation": request.get("operation"),
                    "clock_ns": self.get_clock().now().nanoseconds, "ok": ok, **details}
        if uses_reach_contract(self):
            response.update({"safety_contract": "mr3-reach-v1",
                             "intent_refs": details.get("intent_refs"),
                             "safety_table_sha256": details.get("safety_table_sha256")})
        self.publish_phase_ack(response)
        if cache and isinstance(request.get("request_id"), str):
            self.phase_cache[request["request_id"]] = (canonical(request), response)
            while len(self.phase_cache) > 32:
                del self.phase_cache[next(iter(self.phase_cache))]
        return response

    def matching_inputs(self, request):
        state = request["state_commit"]
        bundles = [row for row in self.phase_bundles
                   if row["message_sha256"] == state["bundle_sha256"]
                   and row["message"]["sequence"] == state["state_sequence"]
                   and row["received_wall_monotonic_ns"]
                   >= state["bundle_publish_started_wall_monotonic_ns"]]
        if not bundles:
            return None
        bundle = bundles[-1]
        safety = None
        if uses_reach_contract(self):
            safety = self.safety_bundle_evidence(bundle["message"], request["target_time_ns"])
            if any(canonical(safety[key]) != canonical(state[key]) for key in safety):
                raise ValueError("actual received safety table differs from state commit")
        rows = {row["name"]: row for row in bundle["message"]["robots"]}
        selected, refs = {}, {}
        for name in self.names:
            expected = state["robots"][name]
            row = rows[name]
            if (row["epoch"] != self.epoch or row["valid"] is not True
                    or canonical(row["sequence"]) != canonical(expected["sequence"])
                    or canonical(row["version"]) != canonical(expected["version"])
                    or round(row["source_stamp"] * 1e9) != expected["source_ns"]
                    or round(row["odom_source_stamp"] * 1e9) != expected["odom_source_ns"]
                    or round(row["tf_source_stamp"] * 1e9) != expected["tf_source_ns"]):
                raise ValueError("actual received bundle differs from state commit")
            if uses_reach_contract(self) and payload_sha256(row["safety"]) != expected["safety_sha256"]:
                raise ValueError("actual received robot safety payload differs from state commit")
            for kind in ("odom", "tf"):
                matches = [item for item in self.phase_input_cache[kind, name]
                           if item[0]["raw_sha256"] == expected[kind + "_sha256"]
                           and item[0]["received_wall_monotonic_ns"]
                           >= state["side_publish_started_wall_monotonic_ns"]]
                if not matches:
                    return None
                value, message = matches[-1]
                source = stamp_ns(message.header.stamp) - (200_000_000 if kind == "tf" else 0)
                if source != expected[kind + "_source_ns"]:
                    raise ValueError("actual side source differs from state commit")
                selected[kind, name] = message
                refs[kind + ":" + name] = {key: value[key] for key in (
                    "input_sequence", "raw_sha256", "received_wall_monotonic_ns")}
        refs["bundle"] = {"state_sequence": state["state_sequence"],
                          "message_sha256": bundle["message_sha256"],
                          "received_wall_monotonic_ns": bundle["received_wall_monotonic_ns"]}
        if safety is not None:
            refs["safety"] = safety
            refs["bundle"]["publisher_identity"] = copy.deepcopy(bundle["publisher_identity"])
        return selected, refs

    def poll_phase(self):
        pending = self.phase_pending
        if pending is None:
            return
        request = pending["request"]
        target = request["target_time_ns"]
        now = self.get_clock().now().nanoseconds
        error = None
        if now > target:
            error = "peer phase target clock passed"
        elif time.monotonic() - pending["requested_wall"] >= 10.:
            error = "peer phase wall timeout waiting for actual inputs"
        if error is not None:
            self.phase_pending = None
            self.phase_response(request, False, error=error)
            return
        if now != target:
            return
        if request["operation"] == "takeover":
            self.phase_pending = None
            self.phase_response(request, True, scope="automatic_obstacle_timer_disabled")
            return
        try:
            matching = self.matching_inputs(request)
            if matching is None:
                return
            selected, refs = matching
            self.record_phase("inputs_matched", {"request": request, "inputs": refs})
            outputs = self._publish_inputs(
                {name: selected["odom", name] for name in self.names},
                {name: selected["tf", name] for name in self.names}, target, capture=True)
            if outputs is None or self.get_clock().now().nanoseconds != target:
                raise ValueError("peer obstacle geometry failed or phase clock changed")
            self.phase_commit_sequence += 1
            state = request["state_commit"]
            self.record_phase("obstacles_published", {"request_id": request["request_id"],
                                                      "publications": outputs})
            self.phase_pending = None
            self.phase_last_clock = target
            self.phase_response(request, True, commit_sequence=self.phase_commit_sequence,
                                state_commit=copy.deepcopy(state),
                                state_sequence=state["state_sequence"],
                                bundle_sha256=state["bundle_sha256"],
                                inputs=refs, publications=outputs,
                                obstacle_publication_sha256=payload_sha(outputs),
                                 **({key: copy.deepcopy(refs["safety"][key]) for key in
                                     ("safety_contract", "safety_table_sha256", "intent_refs")}
                                    if uses_reach_contract(self) else {}),
                                scope="actual_obstacle_publish_calls_returned")
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            self.phase_pending = None
            self.phase_response(request, False, error=str(error))

    def destroy_node(self):
        if self.phase_audit is not None:
            self.phase_audit.close()
        return super().destroy_node()

    def receive_release(self, message):
        if message.frame_id == "map":
            self.mission_started = True

    def receive_odom(self, message, name):
        self.odometry[name] = message
        if getattr(self, "stepped_mode", False):
            self.capture_input("odom", name, message, odom_payload(message))

    def receive_tf(self, message, name):
        for transform in message.transforms:
            if (
                transform.header.frame_id.lstrip("/") == "map"
                and transform.child_frame_id.lstrip("/") == "odom"
            ):
                self.transforms[name] = transform
                if getattr(self, "stepped_mode", False):
                    self.capture_input("tf", name, transform, transform_payload(transform))

    def receive_status(self, message):
        if any(status.status in (
            GoalStatus.STATUS_ACCEPTED, GoalStatus.STATUS_EXECUTING, GoalStatus.STATUS_CANCELING,
        ) for status in message.status_list):
            self.mission_started = True

    def publish_obstacles(self):
        if getattr(self, "phase_controlled", False):
            return
        capture = bool(getattr(self, "stepped_mode", False)
                       and getattr(self, "phase_audit", None) is not None)
        outputs = PeerObstacles._publish_inputs(
            self, self.odometry, self.transforms, self.get_clock().now().nanoseconds,
            capture=capture)
        if capture and outputs is not None:
            self.record_phase("warmup_obstacles_published", {"publications": outputs})
        return outputs

    def _publish_inputs(self, odometry_inputs, transform_inputs, clock_ns, capture=False):
        now = clock_ns / 1e9
        publications = []
        poses = {}
        for name in self.names:
            odometry = odometry_inputs.get(name)
            transform = transform_inputs.get(name)
            if odometry is None or transform is None:
                break
            stamp = odometry.header.stamp.sec + odometry.header.stamp.nanosec / 1e9
            tf_stamp = transform.header.stamp.sec + transform.header.stamp.nanosec / 1e9
            lead = getattr(self, "tf_source_lead_sec", 0.)
            tf_source = tf_stamp - lead
            if lead > 0:
                source_ns = stamp_ns(transform.header.stamp) - round(lead * 1e9)
                healthy = (stamp_ns(odometry.header.stamp) > 0
                           and 0 <= clock_ns - stamp_ns(odometry.header.stamp) <= 500_000_000
                           and 0 <= clock_ns - source_ns <= 500_000_000)
            else:
                healthy = stamp > 0 and now - stamp <= .5 and now - tf_source <= .5
            if not healthy:
                break
            position = odometry.pose.pose.position
            x, y = transform_point_2d(position.x, position.y, transform.transform)
            yaw = quaternion_yaw(odometry.pose.pose.orientation) + quaternion_yaw(
                transform.transform.rotation
            )
            if not all(math.isfinite(v) for v in (x, y, yaw)):
                break
            poses[name] = (x, y, yaw, min(stamp, tf_source) if lead > 0 else stamp)
        if len(poses) != len(self.names):
            if self.mission_started and not self.failed:
                message = String()
                message.data = json.dumps({
                    "component": "peer_obstacles", "reason": "peer_state_unavailable",
                })
                self.failure_publisher.publish(message)
                self.get_logger().error("Peer odom/TF unavailable; obstacle publication stopped")
                self.failed = True
            return
        if self.failed:
            return
        diagnostic = overlap_diagnostic(poses, odometry_inputs, transform_inputs, now, lead)
        if diagnostic is not None:
            message = String()
            message.data = json.dumps({
                "component": "peer_obstacles", "reason": "peer_body_envelopes_overlap",
                "diagnostic": diagnostic,
            }, allow_nan=False)
            self.failure_publisher.publish(message)
            self.failed = True
            return
        for name, (x, y, yaw, _) in poses.items():
            peers = []
            for other, (px, py, _, stamp) in poses.items():
                if other == name:
                    continue
                dx, dy = px - x, py - y
                peers.append((
                    math.cos(yaw) * dx + math.sin(yaw) * dy,
                    -math.sin(yaw) * dx + math.cos(yaw) * dy,
                    now - stamp,
                ))
            message = LaserScan()
            message.header.frame_id = "base_link"
            message.header.stamp = odometry_inputs[name].header.stamp
            message.angle_min = -math.pi
            message.angle_increment = 2 * math.pi / BEAM_COUNT
            message.angle_max = message.angle_min + (BEAM_COUNT - 1) * message.angle_increment
            message.range_min = 0.01
            message.range_max = MAX_RANGE_M
            # Clearing is confined to the separate peer layer. Static and real
            # lidar evidence remain in their own max-combined layers.
            message.ranges = [math.inf] * BEAM_COUNT
            started = time.monotonic_ns() if capture else None
            self.publishers_by_robot[name].publish(message)
            if capture:
                payload = obstacle_payload(message, "scan")
                publications.append({"robot": name, "kind": "scan",
                                     "topic": f"/{name}/peer_obstacles", "payload": payload,
                                     "message_sha256": payload_sha(payload),
                                     "publish_started_wall_monotonic_ns": started,
                                     "publish_completed_wall_monotonic_ns": time.monotonic_ns()})
            points = body_points(peers)
            cloud = PointCloud2()
            cloud.header = message.header
            cloud.height = 1
            cloud.width = len(points)
            cloud.fields = [
                PointField(name=field, offset=offset, datatype=PointField.FLOAT32, count=1)
                for field, offset in (("x", 0), ("y", 4), ("z", 8))
            ]
            cloud.point_step = 12
            cloud.row_step = 12 * len(points)
            cloud.is_dense = True
            cloud.data = points.tobytes()
            started = time.monotonic_ns() if capture else None
            self.body_publishers[name].publish(cloud)
            if capture:
                payload = obstacle_payload(cloud, "cloud")
                publications.append({"robot": name, "kind": "cloud",
                                     "topic": f"/{name}/peer_footprints", "payload": payload,
                                     "message_sha256": payload_sha(payload),
                                     "publish_started_wall_monotonic_ns": started,
                                     "publish_completed_wall_monotonic_ns": time.monotonic_ns()})
        return publications


def main(args=None):
    rclpy.init(args=args)
    node = PeerObstacles()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
