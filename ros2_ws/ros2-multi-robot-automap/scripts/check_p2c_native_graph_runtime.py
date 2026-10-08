#!/usr/bin/env python3
"""Actual DDS observer graph capture; synthetic endpoints, no task experiment."""
import argparse,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
assert not a.output.exists()
os.environ['ROS_DOMAIN_ID']='216'
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage
from multi_robot_exploration.bypass_audit import expected_runtime_nodes,manifest_path,split_node_name
from p2c_native_graph import native_tf_ingress_audit

rclpy.init();nodes={};publishers=[];child=None
qos=QoSProfile(depth=20,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
root=Path(__file__).resolve().parents[1];graph=a.output.with_suffix('.graph.json');trace=a.output.with_suffix('.events.jsonl')
assert not graph.exists() and not trace.exists()
def add(full):
 name,namespace=split_node_name(full);n=Node(name,namespace=namespace);nodes[full]=n;return n
def battery(robot):
 n=add(f'/{robot}/battery_manager');n.create_subscription(TFMessage,f'/{robot}/battery/source_tf',lambda m:None,20)
 pub=n.create_publisher(String,f'/{robot}/battery_state',qos);pub.publish(String(data=json.dumps(dict(mode='ACTIVE',return_count=0,charge_count=0))));publishers.append(pub)
def spin_for(seconds):
 deadline=time.monotonic()+seconds
 while time.monotonic()<deadline:
  for n in nodes.values():rclpy.spin_once(n,timeout_sec=.005)
  if child is not None:assert child.poll() is None,'observer exited early'
try:
 for name in expected_runtime_nodes(json.loads(manifest_path().read_text()),2):add(name)
 for robot in ('tb1','tb2'):
  n=add(f'/{robot}/gateway_tf_ingress')
  n.create_subscription(TFMessage,f'/{robot}/tf',lambda m:None,20)
  n.create_publisher(TFMessage,f'/{robot}/battery/source_tf',1)
  n.create_publisher(TFMessage,f'/{robot}/gateway/source_tf',1)
 battery('tb1')
 env=os.environ.copy();env['P3B5_OBSERVER_OWNER_PID']=str(os.getpid())
 command=[sys.executable,str(root/'scripts/observe_p3b5.py'),'--output',str(trace),'--robot-count','2','--native-tf-graph-output',str(graph)]
 child=subprocess.Popen(command,env=env)
 spin_for(3.);assert not graph.exists(),'incomplete native graph accepted'
 battery('tb2');leak=nodes['/headquarters_control'].create_subscription(TFMessage,'/tb2/battery/source_tf',lambda m:None,20)
 spin_for(4.);assert not graph.exists(),'AP native input leak accepted'
 nodes['/headquarters_control'].destroy_subscription(leak)
 deadline=time.monotonic()+8.
 while time.monotonic()<deadline and not graph.exists():spin_for(.1)
 assert graph.exists(),'complete native graph was not captured'
 audit=native_tf_ingress_audit(json.loads(graph.read_text()),2,True)
 out=dict(status='PASS',scope='Synthetic actual DDS graph endpoints; no Gazebo task or wireless measurements',domain=216,
  missing_native_rejected=True,ap_leak_rejected=True,complete_graph=audit,observer_command=command,
  observer_sha256=hashlib.sha256((root/'scripts/observe_p3b5.py').read_bytes()).hexdigest(),
  reader_sha256=hashlib.sha256((root/'scripts/p2c_native_graph.py').read_bytes()).hexdigest(),graph_sha256=hashlib.sha256(graph.read_bytes()).hexdigest())
finally:
 if child is not None:
  child.send_signal(signal.SIGINT);child.wait(timeout=10);assert child.returncode==0
 for n in nodes.values():n.destroy_node()
 rclpy.shutdown()
a.output.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out))
