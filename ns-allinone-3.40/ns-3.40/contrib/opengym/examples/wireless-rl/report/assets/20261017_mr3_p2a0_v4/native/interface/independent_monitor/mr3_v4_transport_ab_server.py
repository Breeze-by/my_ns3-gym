"""Native-profile single latched status + nine GetParameters CPU fixture."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument("directory", type=Path)
parser.add_argument("--parameter-script", type=Path, required=True)
args = parser.parse_args()
root = Path("/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap")
sys.path.insert(0, str(root / "scripts"))
from ros_smoke_test import configure_mr3_transport_environment
transport = configure_mr3_transport_environment()
spec = importlib.util.spec_from_file_location("frozen_parameter_rules", args.parameter_script)
rules = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rules)
import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import String

context = Context()
rclpy.init(args=[], context=context)
executor = SingleThreadedExecutor(context=context)
nodes = []
receipt = {"schema": "mr3-native-profile-status-service-cpu-v1", "transport": transport,
           "ROS_DOMAIN_ID": os.environ.get("ROS_DOMAIN_ID"), "pid": os.getpid(),
           "status_publication_count": 0, "errors": [], "cleanup": {}}
try:
    for robot in ("tb1", "tb2", "tb3"):
        for kind, expectations in rules.EXPECTED.items():
            node = Node(kind, namespace="/" + robot, context=context)
            for name, (_, value) in expectations.items():
                if node.has_parameter(name):
                    assert all(r.successful for r in node.set_parameters([Parameter(name, value=value)]))
                else:
                    node.declare_parameter(name, value)
            nodes.append(node)
            executor.add_node(node)
    status = Node("motion_safety", context=context)
    nodes.append(status)
    executor.add_node(status)
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL,
                     reliability=ReliabilityPolicy.RELIABLE)
    publisher = status.create_publisher(String, "/motion_safety/status", qos)
    payload = {"schema": "mr3-motion-safety-status-v1", "epoch": "transport_ab_fixture",
               "clock_ns": 1000000000, "ready": True,
               "completion_scope": "publication_and_local_topic_receipt",
               "decision_sequences": {"tb1": 1, "tb2": 1, "tb3": 1}}
    publisher.publish(String(data=json.dumps(payload)))
    receipt["status_publication_count"] = 1
    receipt["single_status"] = payload
    (args.directory / "server_ready.json").write_text(json.dumps(receipt, indent=2) + "\n")
    deadline = time.monotonic() + 50
    while not (args.directory / "stop_server").exists() and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=.05)
    receipt["stopped_by_owned_stop_file"] = (args.directory / "stop_server").exists()
except Exception as error:
    receipt["errors"].append(repr(error))
    raise
finally:
    receipt["cleanup"]["executor_shutdown"] = executor.shutdown(timeout_sec=1.)
    for node in nodes:
        node.destroy_node()
    receipt["cleanup"]["all_nodes_destroyed"] = True
    rclpy.shutdown(context=context)
    receipt["cleanup"]["context_shutdown"] = not context.ok()
    (args.directory / "server_final.json").write_text(json.dumps(receipt, indent=2) + "\n")
