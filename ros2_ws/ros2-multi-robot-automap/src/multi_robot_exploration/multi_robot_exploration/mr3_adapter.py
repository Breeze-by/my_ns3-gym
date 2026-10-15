"""Ideal MR3 policy boundary; only explicit joint actions select exploration goals.

ROS action clients below are the ideal robot execution endpoints. Receipts pass
through the same ideal transport before updating the backend dispatcher. P3A
will split these endpoints and serialize bytes; this node claims no DDS isolation.
"""

from collections import deque
import json
import math
from pathlib import Path

from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid
import numpy as np
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from std_msgs.msg import Bool, Header, String

from multi_robot_exploration.mr3_observation import build_snapshot
from multi_robot_exploration.mr3_information import map_digest
from multi_robot_exploration.mr3_owner import acquire_navigation_owner
from multi_robot_exploration.mr3_protocol import GoalDispatcher
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore


ROBOTS = ("tb1", "tb2", "tb3")


class MR3Adapter(Node):
    def __init__(self):
        super().__init__("mr3_adapter")
        self.navigation_owner = acquire_navigation_owner()
        if self.declare_parameter("robot_count", 3).value != 3:
            raise ValueError("MR3 adapter requires exactly three robots")
        self.epoch = str(self.declare_parameter("episode_epoch", "mr3-p1b").value)
        self.require_monitor = self.declare_parameter("require_task_monitor_ready", False).value
        self.monitor_ready = not self.require_monitor
        audit_path = self.declare_parameter("audit_path", "").value
        self.audit_file = None
        if audit_path:
            Path(audit_path).parent.mkdir(parents=True, exist_ok=True)
            self.audit_file = open(audit_path, "x", buffering=1)
        self.events = deque()
        self.dispatcher = GoalDispatcher(
            self.epoch, self.events.append,
            response_timeout_sec=self.declare_parameter(
                "navigation_response_timeout_sec", 10.).value,
            cancel_timeout_sec=self.declare_parameter("navigation_cancel_timeout_sec", 10.).value,
            execution_timeout_sec=self.declare_parameter("goal_timeout_sec", 60.).value,
        )
        self.transport = IdealTransport(self.epoch)
        self.received = ReceivedStore(self.epoch)
        self.clients = {name: ActionClient(self, NavigateToPose, f"/{name}/navigate_to_pose")
                        for name in ROBOTS}
        self.handles = {}
        self.map = None
        self.map_digest = None
        self.state = None
        self.snapshot = None
        self.sequence = 0
        self.started_at = None
        self.stop_requested = False
        self.stop_acknowledged = False
        self.pending_stop = None
        self.last_command_id = -1
        self.command_receipt = None
        self.command_payload = None
        self.last_heartbeat = -math.inf
        self.receipt_metadata = {name: {} for name in ROBOTS}
        self.history = {name: deque(maxlen=16) for name in ROBOTS}
        task_qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.observation_pub = self.create_publisher(String, "/mr3/observation", 2)
        self.event_pub = self.create_publisher(String, "/mr3/events", 100)
        self.start_pub = self.create_publisher(Header, "/exploration_start", task_qos)
        self.stop_pub = self.create_publisher(String, "/exploration_stopped", task_qos)
        self.failure_pub = self.create_publisher(String, "/exploration_failure", task_qos)
        self.subscriptions_ = [
            self.create_subscription(
                OccupancyGrid, "/mr3/received/map", self.receive_map, task_qos),
            self.create_subscription(String, "/mr3/received/states", self.receive_states, 10),
            self.create_subscription(String, "/mr3/action", self.receive_action, 10),
            self.create_subscription(Bool, "/task_monitor_ready", self.receive_ready, task_qos),
            self.create_subscription(
                Header, "/exploration_stop_request", self.receive_stop, task_qos),
            self.create_subscription(
                String, "/exploration_failure", self.receive_failure, task_qos),
        ]
        self.timer = self.create_timer(.05, self.maintain)
        self.observation_timer = self.create_timer(1., self.publish_observation)

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def record(self, kind, payload):
        row = {"kind": kind, "stamp": self.now(), "epoch": self.epoch, "payload": payload}
        if self.audit_file:
            self.audit_file.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        if kind != "observation":
            message = String()
            message.data = json.dumps(row, sort_keys=True, allow_nan=False)
            self.event_pub.publish(message)

    def receive_map(self, message):
        self.map = message
        self.map_digest = map_digest(message)

    def receive_states(self, message):
        try:
            state = json.loads(message.data)
            if (state["epoch"] == self.epoch
                    and {r["name"] for r in state["robots"]} == set(ROBOTS)
                    and (self.state is None or state["sequence"] > self.state["sequence"])):
                self.state = state
                for robot in state["robots"]:
                    history = self.history[robot["name"]]
                    if robot["valid"] and (not history or
                                           robot["source_stamp"] > history[-1]["source_stamp"]):
                        history.append({key: robot[key] for key in ("x", "y", "source_stamp")})
        except (ValueError, KeyError, TypeError):
            self.record("invalid_state", {})

    def receive_ready(self, message):
        self.monitor_ready = bool(message.data)

    def receive_stop(self, message):
        stamp = message.stamp.sec + message.stamp.nanosec / 1e9
        if self.started_at is not None and stamp > self.now() and message.frame_id == "map":
            self.pending_stop = message
            return
        if self.started_at is not None and self.started_at <= stamp <= self.now() \
                and message.frame_id == "map":
            self.stop_requested = True
            self.dispatcher.safety_stop(self.now(), "task_stop")

    def receive_failure(self, message):
        self.record("safety_stop", {"reason": message.data})
        self.stop_requested = True
        self.dispatcher.safety_stop(self.now(), "external_safety_failure")

    def publish_observation(self):
        if self.map is None or self.state is None or not self.monitor_ready:
            return
        if self.map_digest != self.state.get("map_payload_sha256"):
            return
        robots = self.state["robots"]
        now = self.now()
        if self.started_at is None:
            if not self.states_fresh(now):
                return
            if not all(client.server_is_ready() for client in self.clients.values()):
                return
            if "/headquarters_control" in [
                "/" + n for n, _ in self.get_node_names_and_namespaces()
            ]:
                raise RuntimeError("Handcrafted controller present in adapter mode")
            self.started_at = now
            start = Header()
            start.stamp = self.get_clock().now().to_msg()
            start.frame_id = "map"
            self.start_pub.publish(start)
            self.record("task_start", {"start_sim_time_sec": now})
        navigation = self.dispatcher.navigation(now)
        robots = [{**robot, "navigation": {
            **navigation[robot["name"]], **self.receipt_metadata[robot["name"]],
            "last_failure": navigation[robot["name"]].get("failure"),
        }, "history": list(self.history[robot["name"]])} for robot in robots]
        self.sequence += 1
        self.snapshot = build_snapshot(
            np.asarray(self.map.data, dtype=np.int16).reshape(
                self.map.info.height, self.map.info.width),
            self.map.info.resolution,
            (self.map.info.origin.position.x, self.map.info.origin.position.y),
            robots, now, self.epoch, self.state["map_version"], self.sequence,
            map_source_stamp=self.state["map_source_stamp"],
            map_received_stamp=self.state["map_received_stamp"],
            map_sources=self.state["map_sources"], task_start=self.started_at,
        )
        self.record("observation", self.snapshot)
        message = String()
        message.data = json.dumps(self.snapshot, sort_keys=True, allow_nan=False)
        self.observation_pub.publish(message)

    def states_fresh(self, now):
        return self.state is not None and len(self.state["robots"]) == 3 and all(
            robot["valid"] and robot["source_stamp"] is not None
            and robot["received_stamp"] is not None
            and 0 <= now - robot["source_stamp"] <= .5
            and 0 <= now - robot["received_stamp"] <= .5
            for robot in self.state["robots"]
        )

    def receive_action(self, message):
        try:
            command = json.loads(message.data)
            now = self.now()
            if command["epoch"] != self.epoch:
                raise ValueError("wrong_epoch")
            command_id = command["command_id"]
            if type(command_id) is not int or command_id < 0:
                raise ValueError("invalid_command_id")
            if command_id == self.last_command_id:
                if json.dumps(command, sort_keys=True) != getattr(self, "command_payload", None):
                    raise ValueError("command_id_conflict")
                self.record("action_duplicate", self.command_receipt)
                return
            if command_id < self.last_command_id:
                raise ValueError("old_command")
            if self.stop_requested or self.started_at is None:
                raise ValueError("not_running")
            if not (all(math.isfinite(command[key]) for key in ("created_at", "expires_at"))
                    and command["created_at"] <= now < command["expires_at"]
                    and 0 < command["expires_at"] - command["created_at"] <= 2.):
                raise ValueError("expired_or_invalid_command_time")
            snapshot = self.snapshot
            if (command["observation_sequence"] != snapshot["sequence"]
                    or command["observation_digest"] != snapshot["digest"]):
                raise ValueError("stale_observation")
            action = command["action"]
            if type(action) is not int or not 0 <= action < 1000:
                raise ValueError("invalid_joint_action")
            if not snapshot["joint_action_mask"][action]:
                raise ValueError("masked_action")
            choices = (action // 100, action // 10 % 10, action % 10)
            navigation = self.dispatcher.navigation(now)
            for robot in snapshot["robots"]:
                old = robot["navigation"]
                current = navigation[robot["name"]]
                if any(old.get(key) != current.get(key) for key in ("phase", "goal_id")):
                    raise ValueError("navigation_changed_since_observation")
            results = {}
            for name, choice in zip(ROBOTS, choices):
                target = snapshot["candidates"][choice] if choice < 8 else None
                results[name] = self.dispatcher.submit(
                    name, "GOAL" if choice < 8 else "KEEP" if choice == 8 else "WAIT",
                    now, snapshot["sequence"], command_id, command["expires_at"],
                    goal={"x": target["x"], "y": target["y"]} if target else None,
                    command_epoch=self.epoch, created_at=command["created_at"],
                )
            self.last_command_id = command_id
            self.command_payload = json.dumps(command, sort_keys=True)
            self.command_receipt = {
                "command_id": command_id, "action": action, "results": results,
                "observation_sequence": snapshot["sequence"],
                "observation_digest": snapshot["digest"],
                "candidate_version": snapshot["candidate_version"], "choices": list(choices),
            }
            self.record("action", self.command_receipt)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            self.record("action_rejected", {"reason": str(error)})

    def receipt(self, kind, robot, goal_id, value):
        # Ideal receipt delivery: preserves source time and identity. P3A moves
        # this endpoint to the robot edge; no Future is exposed to the policy.
        now = self.now()
        self.transport.send("receipt", robot, {
            "type": kind, "robot": robot, "goal_id": goal_id, "value": value,
        }, source_stamp=now, now=now)

    def accepted(self, future, robot, goal_id):
        try:
            handle = future.result()
            if handle.accepted:
                self.handles[goal_id] = handle
                result = handle.get_result_async()
                result.add_done_callback(lambda f: self.completed(f, robot, goal_id))
            self.receipt("accept", robot, goal_id, bool(handle.accepted))
        except Exception as error:
            self.record("rpc_error", {"reason": repr(error), "goal_id": goal_id})
            self.dispatcher.safety_stop(self.now(), "accept_rpc_error")
            self.stop_requested = True

    def completed(self, future, robot, goal_id):
        try:
            self.receipt("result", robot, goal_id, int(future.result().status))
            self.handles.pop(goal_id, None)
        except Exception as error:
            self.record("rpc_error", {"reason": repr(error), "goal_id": goal_id})
            self.stop_requested = True
            self.dispatcher.safety_stop(self.now(), "result_rpc_error")

    def canceled(self, future, robot, goal_id):
        try:
            response = future.result()
            handle = self.handles.get(goal_id)
            accepted = handle is not None and any(
                entry.goal_id.uuid == handle.goal_id.uuid for entry in response.goals_canceling)
            self.receipt("cancel", robot, goal_id, accepted)
        except Exception as error:
            self.record("rpc_error", {"reason": repr(error), "goal_id": goal_id})

    def maintain(self):
        now = self.now()
        if self.started_at is None:
            return
        if self.pending_stop is not None:
            pending = self.pending_stop
            stamp = pending.stamp.sec + pending.stamp.nanosec / 1e9
            if stamp <= now:
                self.pending_stop = None
                self.receive_stop(pending)
        if not self.stop_requested and not self.states_fresh(now):
            self.stop_requested = True
            self.dispatcher.safety_stop(now, "received_state_stale")
            failure = String()
            failure.data = json.dumps({
                "component": "mr3_adapter", "reason": "received_state_stale"})
            self.failure_pub.publish(failure)
        if now - self.last_heartbeat >= .2 and not self.stop_requested:
            self.last_heartbeat = now
            for name, nav in self.dispatcher.navigation(now).items():
                if nav["goal_id"] and nav["phase"] in ("active", "accepting"):
                    self.transport.send("heartbeat", name, {
                        "goal_id": nav["goal_id"], "expires_at": now + 2.,
                    }, source_stamp=now, now=now)
        self.dispatcher.tick(now)
        while self.events:
            event = self.events.popleft()
            self.record("protocol", event)
            kind = event["type"]
            name, goal_id = event.get("robot"), event.get("goal_id")
            if kind in ("send_goal", "cancel_goal"):
                self.transport.send("command", name, event, source_stamp=event["stamp"], now=now)
            elif kind == "protocol_failure":
                self.stop_requested = True
                message = String()
                message.data = json.dumps(event)
                self.failure_pub.publish(message)
        for envelope in self.transport.deliver(self.received, now):
            self.record("delivery", envelope.to_dict())
            event = envelope.payload
            name = envelope.source
            goal_id = event.get("goal_id")
            if envelope.stream == "heartbeat":
                self.dispatcher.renew(name, goal_id, self.epoch, now, event["expires_at"])
            elif envelope.stream == "receipt":
                self.receipt_metadata[name] = {
                    "source_stamp": envelope.source_stamp,
                    "received_stamp": envelope.received_stamp,
                    "sequence": envelope.sequence,
                }
                callback = {
                    "accept": self.dispatcher.on_accept, "result": self.dispatcher.on_result,
                    "cancel": self.dispatcher.on_cancel_response,
                }[event["type"]]
                callback(name, goal_id, event["value"], now)
            elif event["type"] == "send_goal":
                navigation = self.dispatcher.navigation(now)[name]
                if self.dispatcher.stopped or navigation["cancel_requested"]:
                    self.record("edge_goal_not_sent", {"goal_id": goal_id, "reason": "stopped"})
                    self.dispatcher.on_result(name, goal_id, "CANCELED", now)
                    continue
                if event["expires_at"] <= now:
                    self.record("edge_goal_not_sent", {"goal_id": goal_id, "reason": "expired"})
                    self.dispatcher.on_accept(name, goal_id, False, now)
                    continue
                pose = PoseStamped()
                pose.header.frame_id = "map"
                pose.header.stamp = self.get_clock().now().to_msg()
                pose.pose.position.x = float(event["goal"]["x"])
                pose.pose.position.y = float(event["goal"]["y"])
                pose.pose.orientation.w = 1.
                goal = NavigateToPose.Goal()
                goal.pose = pose
                self.record("native_send", {"robot": name, "goal_id": goal_id,
                                            "command_id": event["command_id"]})
                self.clients[name].send_goal_async(goal).add_done_callback(
                    lambda future, name=name, goal_id=goal_id: self.accepted(future, name, goal_id))
            elif event["type"] == "cancel_goal" and goal_id in self.handles:
                self.handles[goal_id].cancel_goal_async().add_done_callback(
                    lambda future, name=name, goal_id=goal_id: self.canceled(future, name, goal_id))
        if now - self.started_at >= 300. and not self.stop_requested:
            self.stop_requested = True
            self.dispatcher.safety_stop(now, "task_deadline")
        if self.stop_requested and self.dispatcher.closed and not self.stop_acknowledged:
            self.stop_acknowledged = True
            payload = {"start_sim_time_sec": self.started_at, "stop_sim_time_sec": now,
                       "pending_goal_count": 0, "robot_names": list(ROBOTS),
                       "navigation_failure": self.dispatcher.failed}
            message = String()
            message.data = json.dumps(payload)
            self.stop_pub.publish(message)
            self.record("task_stopped", payload)

    def destroy_node(self):
        try:
            if self.audit_file:
                self.audit_file.close()
            return super().destroy_node()
        finally:
            self.navigation_owner.close()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = MR3Adapter()
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
