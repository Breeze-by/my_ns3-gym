#!/usr/bin/env python3
"""Isolated ROS/Qt integration probe; synthetic messages, no robot or Gazebo."""

import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src/multi_robot_exploration"))
from export_gateway_metrics import verify_live


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from nav_msgs.msg import Odometry, OccupancyGrid
    from rosgraph_msgs.msg import Clock
    from rcl_interfaces.srv import SetParametersAtomically
    from std_msgs.msg import String
    from python_qt_binding.QtWidgets import QApplication
    from multi_robot_exploration.ideal_gateway import IdealGateway
    from multi_robot_exploration.gateway_panel import GatewayPanel, MonitorNode, FaultControlNode, transient_qos

    rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true", "-p", "robot_count:=1",
                     "-p", f"ledger_path:={root / 'ledger.jsonl'}", "-p", "episode_id:=p3c_runtime",
                     "-p", "world:=synthetic_component", "-p", "mission_mode:=rally"])
    app = QApplication.instance() or QApplication([])
    gateway, monitor, controller = IdealGateway(), MonitorNode(), FaultControlNode()
    injector = Node("p3c_component_injector")
    clock = injector.create_publisher(Clock, "/clock", 10)
    phase = injector.create_publisher(String, "/task_state", transient_qos())
    odom = injector.create_publisher(Odometry, "/tb1/odom", 10)
    maps = injector.create_publisher(OccupancyGrid, "/tb1/map", transient_qos())
    executor = SingleThreadedExecutor()
    for node in (gateway, monitor, controller, injector):
        executor.add_node(node)
    panel = GatewayPanel(monitor, controller)
    panel.show()
    wall_start = time.monotonic()
    output = (root / "metrics_process.txt").open("w")
    child = subprocess.Popen(["ros2", "run", "multi_robot_exploration", "gateway_metrics", "--ros-args",
                              "-p", "use_sim_time:=true", "-p", "robot_count:=1",
                              "-p", f"output_dir:={root / 'metrics'}"], stdout=output, stderr=subprocess.STDOUT,
                             start_new_session=True)
    when, checks = 10.0, {}

    def spin(seconds=.12):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            executor.spin_once(timeout_sec=.002)
            app.processEvents()
        if child.poll() is not None:
            raise RuntimeError(f"metrics child exited early: {child.returncode}")

    def advance(delta=.25):
        nonlocal when
        when += delta
        message = Clock()
        message.clock.sec = int(when)
        message.clock.nanosec = round((when-int(when))*1e9)
        clock.publish(message)
        spin()

    def pose():
        message = Odometry()
        message.header.stamp.sec = int(when)
        message.header.stamp.nanosec = round((when-int(when))*1e9)
        message.pose.pose.orientation.w = 1.0
        odom.publish(message)
        spin()

    def configure(values, successful=True):
        request = SetParametersAtomically.Request(parameters=[Parameter(k, value=v).to_parameter_msg() for k, v in values.items()])
        future = controller.client.call_async(request)
        deadline = time.monotonic()+10
        while not future.done() and time.monotonic() < deadline:
            spin(.02)
        result = future.result().result
        assert result.successful == successful, result.reason
        return result

    try:
        deadline = time.monotonic()+15
        while (not controller.configuration or not controller.client.service_is_ready()) and time.monotonic() < deadline:
            advance()
        assert controller.configuration and controller.client.service_is_ready()
        phase.publish(String(data="EXPLORE"))
        spin()
        for _ in range(24):
            advance()
            pose()
        assert monitor.snapshot, "metrics never reached the actual Qt subscriber"
        checks["actual_metrics_subscription"] = True
        revision = gateway.configuration_revision
        configure({"uplink_loss_rate": 1.5, "downlink_delay_sec": .5}, False)
        configure({"navigation_command_deadline_sec": 999.0}, False)
        configure({"expected_revision": revision+1, "uplink_loss_rate": .5}, False)
        assert gateway.configuration_revision == revision
        assert gateway.transport_by_direction["downlink"].config.delay_sec == 0
        checks["atomic_invalid_and_stale_rejection"] = True
        native = injector.create_client(SetParametersAtomically, "/ideal_gateway/set_parameters_atomically")
        native.wait_for_service(timeout_sec=5)
        future = native.call_async(SetParametersAtomically.Request(parameters=[Parameter("uplink_loss_rate", value=.8).to_parameter_msg()]))
        deadline = time.monotonic()+10
        while not future.done() and time.monotonic() < deadline:
            spin(.02)
        assert not future.result().result.successful
        checks["startup_parameters_frozen"] = True
        panel.console.load()
        panel.console.editors["network_mode"].setCurrentText("fault")
        panel.console.editors["uplink_loss_rate"].setValue(100)
        panel.console.editors["uplink_delay_sec"].setValue(1)
        panel.console.apply_button.click()
        deadline = time.monotonic()+10
        while controller.pending and time.monotonic() < deadline:
            spin(.02)
        assert gateway.configuration_revision == revision+1
        checks["actual_qt_apply_and_service_ack"] = True
        advance(.25)
        pose()
        source = when
        configure({"uplink_loss_rate": 0.0, "uplink_delay_sec": 0.0})
        for _ in range(12):
            advance()
            pose()
        records = [json.loads(line) for line in (root / "ledger.jsonl").read_text().splitlines()]
        old_drops = [e for e in records if e.get("event") == "drop" and e.get("source_time") == source]
        assert any(e.get("reason") == "loss" and e.get("fault_revision") == revision+1 for e in old_drops)
        checks["in_flight_old_configuration_retained"] = True
        configure({"uplink_delay_sec": .8, "queue_capacity": 1, "duplicate_rate": 1.0})
        advance()
        pose()
        grid = OccupancyGrid()
        grid.header.stamp.sec = int(when)
        grid.header.stamp.nanosec = round((when-int(when))*1e9)
        grid.info.width = grid.info.height = 1
        grid.info.resolution = .05
        grid.data = [0]
        maps.publish(grid)
        spin()
        for _ in range(5):
            advance()
        configure({"queue_capacity": 4096, "uplink_delay_sec": 0.0, "duplicate_rate": 0.0})
        for _ in range(24):
            advance()
            pose()
        panel.refresh()
        panel.grab().save(str(root / "monitor.png"))
        for index, name in ((1, "details.png"), (2, "console.png")):
            panel.tabs.setCurrentIndex(index)
            app.processEvents()
            panel.grab().save(str(root / name))
        # Monitor has no application publishers/services; console only configures.
        publishers = {name: [topic for topic, _ in injector.get_publisher_names_and_types_by_node(name, "/")]
                      for name in ("gateway_monitor", "gateway_fault_console", "gateway_metrics")}
        checks["graph_publishers"] = publishers
        assert set(publishers["gateway_monitor"]) <= {"/rosout", "/parameter_events"}
        assert set(publishers["gateway_fault_console"]) <= {"/rosout", "/parameter_events"}
        assert set(publishers["gateway_metrics"]) <= {"/rosout", "/parameter_events", "/gateway/metrics"}
        before = len(monitor.snapshot["history"])
        live_size_before_close = (root / "metrics/live.jsonl").stat().st_size
        panel.close()
        executor.remove_node(monitor)
        monitor.destroy_node()
        for _ in range(12):
            advance()
            pose()
        checks["gui_closed_collection_continues"] = (root / "metrics/live.jsonl").stat().st_size > live_size_before_close
        assert checks["gui_closed_collection_continues"]
        assert before > 0
        records = [json.loads(line) for line in (root / "ledger.jsonl").read_text().splitlines()]
        assert any(e.get("reason") == "queue_overflow" for e in records)
        assert any(e.get("duplicate") for e in records)
        checks["actual_overflow_and_duplicate_events"] = True
        executor.remove_node(gateway)
        gateway.destroy_node()
        shutdown_start = time.monotonic()
        os.killpg(child.pid, signal.SIGINT)
        child.wait(timeout=5)
        checks["metrics_shutdown_wall_sec"] = time.monotonic()-shutdown_start
        assert child.returncode == 0
        checks["live_replay"] = verify_live(root / "metrics")
        summary = json.loads((root / "metrics/summary.json").read_text())
        assert summary["conservation"]["status"] == "PASS", summary["conservation"]["errors"]
        assert any(e.get("event") == "gateway_stop" for e in map(json.loads, (root / "metrics/inputs.jsonl").read_text().splitlines()))
        checks["full_ledger_conservation_and_closure"] = True
        checks["status"] = "PASS"
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGINT)
            try:
                child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
        output.close()
        checks.update(elapsed_wall_sec=time.monotonic()-wall_start, domain=os.environ.get("ROS_DOMAIN_ID"),
                      metrics_returncode=child.returncode)
        (root / "checks.json").write_text(json.dumps(checks, indent=2, sort_keys=True)+"\n")
        executor.shutdown()
        controller.destroy_node()
        injector.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    print(json.dumps(checks, sort_keys=True))


if __name__ == "__main__":
    main()
