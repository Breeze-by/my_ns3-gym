#!/usr/bin/env python3
"""Actual isolated ROS protocol probe with a simulated clock; no task truth."""
import argparse
import json
import os
from pathlib import Path
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    import rclpy
    from rclpy.executors import SingleThreadedExecutor
    from rclpy.node import Node
    from rclpy.parameter import Parameter
    from rosgraph_msgs.msg import Clock
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String
    from rcl_interfaces.srv import SetParametersAtomically
    from multi_robot_exploration.ideal_gateway import IdealGateway
    from multi_robot_exploration.gateway_metrics import LedgerMetrics

    rclpy.init(args=["--ros-args", "-p", "use_sim_time:=true", "-p", "robot_count:=1",
        "-p", "admission_protocol:=true", "-p", f"ledger_path:={args.output/'ledger.jsonl'}"])
    gateway, injector = IdealGateway(), Node("p3c5_probe")
    executor = SingleThreadedExecutor()
    executor.add_node(gateway)
    executor.add_node(injector)
    clock = injector.create_publisher(Clock, "/clock", 10)
    odom = injector.create_publisher(Odometry, "/tb1/odom", 10)
    received, observations = [], []
    injector.create_subscription(Odometry, "/gateway/received/tb1/odom", received.append, 10)
    injector.create_subscription(String, "/gateway/admission_observation", lambda m: observations.append(json.loads(m.data)), 10)
    when = 10.0

    def spin():
        end = time.monotonic()+.025
        while time.monotonic() < end:
            executor.spin_once(timeout_sec=.002)

    def advance(seconds):
        nonlocal when
        for _ in range(round(seconds/.05)):
            when += .05
            message = Clock()
            message.clock.sec, message.clock.nanosec = divmod(round(when*1e9), 10**9)
            clock.publish(message)
            spin()

    def pose():
        message = Odometry()
        message.header.stamp.sec, message.header.stamp.nanosec = divmod(round(when*1e9), 10**9)
        message.pose.pose.orientation.w = 1.0
        odom.publish(message)
        spin()

    def configure(delay):
        request = SetParametersAtomically.Request(parameters=[Parameter(k, value=v).to_parameter_msg()
            for k, v in {"network_mode": "fault", "uplink_delay_sec": delay, "downlink_delay_sec": delay}.items()])
        response = gateway.configure_callback(request, SetParametersAtomically.Response())
        assert response.result.successful, response.result.reason

    try:
        advance(.5)
        pose()
        advance(.5)
        assert len(received) == 1
        configure(.5)
        pose()
        advance(2.5)
        assert len(received) == 2
        configure(2.0)
        pose()
        advance(7)
        assert len(received) == 2, "source TTL must expire before delayed grant/data"
        assert observations and all(o["remote_current_queue"] is None for o in observations)
        pose()
        advance(.1)
        assert gateway.endpoint_queues["tb1"].pending
    finally:
        # Match actual launch SIGINT ordering: context stops before node cleanup.
        rclpy.shutdown()
        gateway.destroy_node()
        injector.destroy_node()
        executor.shutdown()
    records = [json.loads(line) for line in (args.output/"ledger.jsonl").read_text().splitlines()]
    engine = LedgerMetrics()
    for event in records:
        engine.ingest(event)
    audit = engine.audit()
    assert audit["status"] == "PASS", audit["errors"]
    assert any(e["event"] == "local_discard" and e["reason"] == "source_expired" for e in records)
    assert any(e["event"] == "admission_release" and e["local_wait_sec"] >= 1 for e in records)
    assert records[-1]["event"] == "gateway_stop"
    assert any(e["event"] == "local_discard" and e["reason"] == "episode_closed" for e in records)
    result = {"status": "PASS", "ros_domain_id": os.environ.get("ROS_DOMAIN_ID"),
        "actual_ros_delivery_count": len(received), "delivered_only_observation_samples": len(observations),
        "source_ttl_not_renewed": True, "real_delayed_grant_wait": True, "conservation": audit}
    result["actual_context_shutdown_closes_pending_queue"] = True
    (args.output/"checks.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps({key: result[key] for key in ("status", "actual_ros_delivery_count", "delivered_only_observation_samples")}))


if __name__ == "__main__":
    main()
