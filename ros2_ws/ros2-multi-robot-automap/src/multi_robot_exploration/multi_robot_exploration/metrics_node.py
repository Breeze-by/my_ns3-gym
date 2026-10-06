"""Read-only gateway ledger monitor; GUI presence never determines accounting."""

import json
import csv
from pathlib import Path
import time

from nav_msgs.msg import Odometry
from gazebo_msgs.msg import ContactsState
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from .gateway_metrics import LedgerMetrics, event_stamp
from .metrics_io import save_final, flatten


class MetricsNode(Node):
    def __init__(self):
        super().__init__("gateway_metrics")
        self.robot_count = int(self.declare_parameter("robot_count", 2).value)
        self.output_dir = str(self.declare_parameter("output_dir", "").value)
        self.start_wall_time = time.time()
        self.result_path = str(self.declare_parameter("result_path", "").value)
        self.metrics = LedgerMetrics()
        self.ledger = None
        self.partial = ""
        self.last_sample = -1.0
        self.latest_phase = "WAITING"
        self.robots = {}
        self.samples = []
        self.history = []
        self.inputs = None
        self.saved_samples = None
        self.csv_stream = None
        self.csv_writer = None
        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.publisher = self.create_publisher(String, "/gateway/metrics", qos)
        self.create_subscription(String, "/gateway/fault_configuration", self.configuration_callback, qos)
        self.create_subscription(String, "/task_state", self.phase_callback, qos)
        self.create_subscription(String, "/robot_failure", lambda m: self.task_event("robot_failure", m), qos)
        for index in range(1, self.robot_count + 1):
            name = f"tb{index}"
            self.create_subscription(String, f"/{name}/battery_state", lambda m, n=name: self.battery_callback(m, n), qos)
            self.create_subscription(Odometry, f"/gateway/received/{name}/odom", lambda m, n=name: self.pose_callback(m, n), 10)
            self.create_subscription(ContactsState, f"/{name}/collision", lambda m, n=name: self.collision_callback(m, n), 10)
        self.timer = self.create_timer(0.2, self.poll)

    def now(self):
        return self.get_clock().now().nanoseconds / 1e9

    def configuration_callback(self, message):
        config = json.loads(message.data)
        if self.ledger is None:
            path = Path(config["ledger_path"])
            if not path.exists():
                return
            directory = Path(self.output_dir) if self.output_dir else path.with_name(path.stem + "_metrics")
            directory.mkdir(parents=True, exist_ok=False)
            self.directory = directory
            self.inputs = (directory / "inputs.jsonl").open("w", buffering=1)
            for event in self.metrics.events:
                self.inputs.write(json.dumps(event, sort_keys=True) + "\n")
            self.saved_samples = (directory / "live.jsonl").open("w", buffering=1)
            self.csv_stream = (directory / "live_windows.csv").open("w", newline="", buffering=1)
            self.ledger = path.open()
            self.get_logger().info(f"Read-only gateway metrics: {directory}")

    def ingest(self, event):
        self.metrics.ingest(event)
        if self.inputs:
            self.inputs.write(json.dumps(event, sort_keys=True) + "\n")

    def phase_callback(self, message):
        if message.data != self.latest_phase:
            self.latest_phase = message.data
            self.ingest({"event": "task_phase", "phase": message.data, "event_time": self.now()})

    def task_event(self, kind, message):
        self.ingest({"event": kind, "data": json.loads(message.data), "event_time": self.now()})

    def battery_callback(self, message, name):
        data = json.loads(message.data)
        state = self.robots.setdefault(name, {})
        previous = state.get("battery", {})
        if any(previous.get(key) != data.get(key) for key in ("mode", "return_count", "charge_count")):
            self.ingest({"event": "battery_transition", "robot": name, "data": data,
                         "event_time": float(data.get("stamp_sec", self.now()))})
        state["battery"] = data

    def pose_callback(self, message, name):
        state = self.robots.setdefault(name, {})
        state["pose"] = [message.pose.pose.position.x, message.pose.pose.position.y]
        state["velocity"] = [message.twist.twist.linear.x, message.twist.twist.angular.z]
        state["pose_source_time"] = message.header.stamp.sec + message.header.stamp.nanosec / 1e9

    def collision_callback(self, message, name):
        state = self.robots.setdefault(name, {})
        if message.states and not state.get("contacting", False):
            self.ingest({"event": "collision", "robot": name, "event_time": self.now()})
        state["contacting"] = bool(message.states)

    def task_result(self):
        path = Path(self.result_path) if self.result_path else None
        if path and path.is_file() and path.stat().st_mtime >= self.start_wall_time:
            try:
                result = json.loads(path.read_text())
            except json.JSONDecodeError:
                # The independent evaluator may still be writing its result.
                return None
            if result["episode_id"] == self.metrics.context.get("episode_id"):
                return result
        return None

    def read_ledger(self):
        if self.ledger is None:
            return
        self.partial += self.ledger.read()
        lines = self.partial.split("\n")
        self.partial = lines.pop()
        for line in lines:
            if line:
                self.ingest(json.loads(line))

    def poll(self):
        self.read_ledger()
        if not self.inputs:
            return
        ticks = self.metrics.queue_ticks
        if not ticks:
            return
        when = event_stamp(ticks[-1])
        start = self.metrics.context.get("episode_start_sim_time")
        if start is None or when <= self.last_sample:
            return
        self.last_sample = when
        rows = [self.metrics.report(max(start, when - 1), when, direction) for direction in ("uplink", "downlink")]
        type_rows = [self.metrics.report(max(start, when - 1), when, *key) for key in sorted({key[:2] for key in self.metrics.routes})]
        stream_rows = [self.metrics.report(max(start, when - 1), when, *key) for key in sorted(self.metrics.routes)]
        self.history.extend(rows)
        self.history = [r for r in self.history if r["sim_time"] >= when - 120]
        snapshot = {"sim_time": when, "elapsed_sim_time": when - start, "ledger_record_count": len(self.metrics.events),
                    "context": self.metrics.context, "phase": self.latest_phase, "robots": self.robots,
                    "window": rows, "cumulative": [self.metrics.report(start, when, d) for d in ("uplink", "downlink")],
                    "streams": [self.metrics.report(start, when, *key) for key in sorted(self.metrics.routes)],
                    "by_type_window": type_rows, "by_stream_window": stream_rows,
                    "timeline": self.metrics.timeline[-100:], "history": self.history,
                    "output_dir": str(self.directory)}
        snapshot["task_result"] = self.task_result()
        data = json.dumps(snapshot, sort_keys=True, allow_nan=False)
        self.saved_samples.write(data + "\n")
        self.samples.extend(rows + type_rows + stream_rows)
        for row in rows + type_rows + stream_rows:
            values = flatten(row)
            if self.csv_writer is None:
                self.csv_writer = csv.DictWriter(self.csv_stream, fieldnames=sorted(values))
                self.csv_writer.writeheader()
            self.csv_writer.writerow(values)
        self.publisher.publish(String(data=data))

    def finish(self):
        if not self.inputs:
            return
        # The launch sends SIGINT to both processes. Drain the gateway's final
        # file writes after DDS shutdown; this is wall-time cleanup, not a metric.
        for _ in range(10):
            self.read_ledger()
            if any(e.get("event") == "gateway_stop" for e in self.metrics.events):
                break
            time.sleep(0.1)
        result = self.task_result()
        end = result["end_sim_time_sec"] if result else None
        save_final(self.metrics, self.directory, end=end, result=result, sampled_rows=self.samples)
        self.inputs.close()
        self.saved_samples.close()
        self.csv_stream.close()
        self.ledger.close()


def main(args=None):
    rclpy.init(args=args)
    node = MetricsNode()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.finish()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
