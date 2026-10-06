#!/usr/bin/env python3
"""Apply atomic communication faults now, or follow a simulation-time schedule."""

import argparse
import json
import math
from pathlib import Path
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rcl_interfaces.srv import SetParametersAtomically
from std_msgs.msg import String
from multi_robot_exploration.gateway_config import FAULT_DEFAULTS, updated_configuration


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--set", nargs="*", default=[], metavar="NAME=JSON")
    parser.add_argument("--expected-revision", type=int)
    parser.add_argument("--schedule", type=Path, help="JSON [{after_sec, parameters}] relative to gateway mission epoch")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--timeout", type=float, default=900)
    args = parser.parse_args()
    if args.schedule and args.set:
        parser.error("use either --set or --schedule")
    try:
        schedule = json.loads(args.schedule.read_text()) if args.schedule else [{"after_sec": None, "parameters":
            {item.split("=", 1)[0]: json.loads(item.split("=", 1)[1]) for item in args.set}}]
    except (ValueError, IndexError, OSError) as error:
        parser.error(str(error))
    if not isinstance(schedule, list) or not schedule:
        parser.error("schedule must be a non-empty list")
    previous = 0
    try:
        for entry in schedule:
            after = entry.get("after_sec")
            if args.schedule and (type(after) not in (float, int) or not math.isfinite(after) or after < previous):
                raise ValueError("schedule times must be finite, non-negative and ordered")
            if after is not None:
                previous = after
            if entry["parameters"]:
                updated_configuration(FAULT_DEFAULTS, entry["parameters"])
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        parser.error(str(error))
    if args.output and args.output.exists():
        parser.error("output exists; never overwrite evidence")
    rclpy.init()
    node = Node("gateway_configure_cli", parameter_overrides=[Parameter("use_sim_time", value=True)])
    client = node.create_client(SetParametersAtomically, "/gateway/configure")
    state, sample = {}, {}
    qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    def receive_state(message):
        update = json.loads(message.data)
        if update["revision"] >= state.get("revision", -1):
            state.update(update)
    node.create_subscription(String, "/gateway/fault_configuration", receive_state, qos)
    node.create_subscription(String, "/gateway/metrics", lambda m: sample.update(json.loads(m.data)), qos)
    deadline, index, pending, request_record = time.monotonic()+args.timeout, 0, None, None
    failed = False

    def record(data):
        print(json.dumps(data, sort_keys=True), flush=True)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            with args.output.open("a") as stream:
                stream.write(json.dumps(data, sort_keys=True)+"\n")

    try:
        while rclpy.ok() and index < len(schedule) and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.1)
            if pending is not None:
                if not pending.done():
                    continue
                response = pending.result().result
                record({"event": "configuration_response", "request": request_record,
                        "successful": response.successful, "reason": response.reason,
                        "observer_sim_time": node.get_clock().now().nanoseconds/1e9})
                if not response.successful:
                    failed = True
                    break
                state.update(json.loads(response.reason))
                index += 1
                pending = None
                continue
            entry = schedule[index]
            after = entry.get("after_sec")
            if not state or not client.service_is_ready() or (after is not None and sample.get("elapsed_sim_time", -1) < after):
                continue
            values = dict(entry["parameters"])
            values["expected_revision"] = args.expected_revision if args.expected_revision is not None else int(state["revision"])
            request = SetParametersAtomically.Request(parameters=[Parameter(name, value=value).to_parameter_msg() for name, value in values.items()])
            request_record = {"index": index, "planned_after_sec": after, "parameters": values,
                              "request_sim_time": node.get_clock().now().nanoseconds/1e9}
            record({"event": "configuration_request", **request_record})
            pending = client.call_async(request)
        if index < len(schedule):
            failed = True
            record({"event": "configuration_schedule_incomplete", "applied": index, "planned": len(schedule)})
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
