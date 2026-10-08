#!/usr/bin/env python3
"""Read-only evaluator-side timing trace; never publishes into control."""
import argparse, json
from pathlib import Path
from observer_lifetime import bind_to_owner
bind_to_owner()
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.parameter import Parameter
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import String

parser=argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--robot-count", type=int, required=True)
args=parser.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True)
rclpy.init()
node=Node("p3b5_read_only_observer",parameter_overrides=[Parameter("use_sim_time",value=True)])
qos=QoSProfile(depth=20, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)
last={}

def record(topic,message):
    data=message.data
    try: data=json.loads(data)
    except (ValueError,TypeError): pass
    if topic.endswith("battery_state") and isinstance(data, dict):
        key=(data.get("mode"),data.get("return_count"),data.get("charge_count"))
        if last.get(topic)==key: return
        last[topic]=key
    event={"topic":topic,"observer_time":node.get_clock().now().nanoseconds/1e9,"data":data}
    with args.output.open("a") as stream: stream.write(json.dumps(event,sort_keys=True)+"\n")

for topic in ["/robot_failure","/task_state","/rally_assignments",*(f"/tb{i}/battery_state" for i in range(1,args.robot_count+1))]:
    node.create_subscription(String,topic,lambda m,t=topic: record(t,m),qos)
audit_qos=QoSProfile(depth=100,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
for i in range(1,args.robot_count+1):
    topic=f'/tb{i}/battery_return_audit'
    node.create_subscription(String,topic,lambda m,t=topic: record(t,m),audit_qos)
print("READY",flush=True)
try: rclpy.spin(node)
except (KeyboardInterrupt, ExternalShutdownException): pass
finally:
    node.destroy_node()
    if rclpy.ok(): rclpy.shutdown()
