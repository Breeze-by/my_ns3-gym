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
parser.add_argument("--native-tf-graph-output",type=Path)
parser.add_argument("--navigation-input-output",type=Path)
args=parser.parse_args()
args.output.parent.mkdir(parents=True,exist_ok=True)
rclpy.init()
node=Node("p3b5_read_only_observer",parameter_overrides=[Parameter("use_sim_time",value=True)])
navigation_capture=None
if args.navigation_input_output:
    from p2c_navigation_capture import NavigationCapture
    navigation_capture=NavigationCapture(node,args.navigation_input_output,args.robot_count)
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
if args.native_tf_graph_output:
    from p2c_native_graph import complete_native_graph
    from rclpy.clock import Clock,ClockType
    graph_saved=False
    def save_native_graph():
        global graph_saved
        if graph_saved or not all(f'/tb{i}/battery_state' in last for i in range(1,args.robot_count+1)):
            return
        try:snapshot=complete_native_graph(node,args.robot_count)
        except AssertionError:return  # Discovery is incomplete; never fabricate absent endpoints.
        snapshot['observer_time']=node.get_clock().now().nanoseconds/1e9
        args.native_tf_graph_output.write_text(json.dumps(snapshot,indent=2,sort_keys=True)+'\n')
        graph_saved=True
        print('NATIVE_GRAPH_SAVED',flush=True)
    node.create_timer(2.,save_native_graph,clock=Clock(clock_type=ClockType.STEADY_TIME))
print("READY",flush=True)
try: rclpy.spin(node)
except (KeyboardInterrupt, ExternalShutdownException): pass
finally:
    if navigation_capture is not None: navigation_capture.close()
    node.destroy_node()
    if rclpy.ok(): rclpy.shutdown()
