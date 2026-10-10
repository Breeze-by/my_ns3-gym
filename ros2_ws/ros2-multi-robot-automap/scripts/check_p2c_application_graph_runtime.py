#!/usr/bin/env python3
"""Actual delayed DDS endpoint discovery; read-only observer, zero navigation goals."""
import argparse,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();assert not a.output.exists()
os.environ['ROS_DOMAIN_ID']='216'
import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient
from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
from nav2_msgs.action import NavigateToPose
from nav_msgs.msg import OccupancyGrid,Odometry
from rosgraph_msgs.msg import Clock
from std_msgs.msg import String
from gazebo_msgs.msg import ContactsState
from tf2_msgs.msg import TFMessage
from multi_robot_exploration.bypass_audit import expected_runtime_nodes,manifest_path,split_node_name
from p2c_native_graph import application_graph_audit,native_tf_ingress_audit
from check_p3c_gate import monitor_graph_audit

root=Path(__file__).resolve().parents[1];rclpy.init();nodes={};children=[];subscriptions={};publishers=[]
qos=QoSProfile(depth=20,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
def add(full):
 if full not in nodes:
  name,namespace=split_node_name(full);nodes[full]=Node(name,namespace=namespace)
 return nodes[full]
def sub(full,kind,topic):
 handle=add(full).create_subscription(kind,topic,lambda m:None,10);subscriptions[full,topic]=handle;return handle
def pub(full,kind,topic):
 handle=add(full).create_publisher(kind,topic,qos if kind is String else 10);publishers.append(handle);return handle
def spin_for(seconds):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  for node in nodes.values():rclpy.spin_once(node,timeout_sec=.002)
  assert all(child.poll() is None for child in children),'observer exited early'
def launch(label,complete):
 prefix=a.output.with_name(a.output.stem+'_'+label);native=prefix.with_suffix('.native.json');canonical=prefix.with_suffix('.graph.json');events=prefix.with_suffix('.events.jsonl');log=prefix.with_suffix('.log')
 assert not any(p.exists() for p in (native,canonical,events,log))
 command=[sys.executable,str(root/'scripts/observe_p3b5.py'),'--output',str(events),'--robot-count','2','--native-tf-graph-output',str(native)]
 if complete:command+=['--application-graph-output',str(canonical)]
 env=os.environ.copy();env['P3B5_OBSERVER_OWNER_PID']=str(os.getpid())
 with log.open('w') as stream:child=subprocess.Popen(command,env=env,cwd=root,stdout=stream,stderr=subprocess.STDOUT)
 children.append(child);return child,native,canonical,events,command
def close(child):
 child.send_signal(signal.SIGINT);child.wait(timeout=10);assert child.returncode==0;children.remove(child)
def wait_graph(path):
 deadline=time.monotonic()+10.
 while time.monotonic()<deadline and not path.exists():spin_for(.1)
 assert path.exists(),'complete graph was not captured'
try:
 for full in expected_runtime_nodes(json.loads(manifest_path().read_text()),2):add(full)
 hq='/headquarters_control';merge='/merge_map'
 for robot in ('tb1','tb2'):
  ingress=f'/{robot}/gateway_tf_ingress';battery=f'/{robot}/battery_manager'
  sub(ingress,TFMessage,f'/{robot}/tf');pub(ingress,TFMessage,f'/{robot}/battery/source_tf');pub(ingress,TFMessage,f'/{robot}/gateway/source_tf')
  sub(battery,TFMessage,f'/{robot}/battery/source_tf');pub(battery,String,f'/{robot}/battery_state').publish(String(data=json.dumps(dict(mode='ACTIVE',return_count=0,charge_count=0))))
  for suffix,kind in (('odom',Odometry),('map',OccupancyGrid),('tf',TFMessage),('battery_state',String)):sub(hq,kind,f'/gateway/received/{robot}/{suffix}')
  pub(hq,String,f'/gateway/request/{robot}/charge');sub(merge,OccupancyGrid,f'/gateway/received/{robot}/map')
  ActionClient(add(hq),NavigateToPose,f'/gateway/{robot}/navigate_to_pose')
 for topic,kind in (('/clock',Clock),('/merge_map',OccupancyGrid),('/gateway/received/target_detection',String),('/gateway/received/target_observation',String),('/gateway/received/battery_failure',String)):sub(hq,kind,topic)
 pub(hq,String,'/gateway/consumed');pub(hq,String,'/task_state');pub(merge,OccupancyGrid,'/merge_map')
 probe=pub('/tb1/battery_manager',String,'/tb1/battery_return_audit')
 legacy,native,_,_,legacy_command=launch('legacy_contract',False);wait_graph(native)
 assert '/gateway_metrics' not in json.loads(native.read_text())['nodes']
 try:monitor_graph_audit(json.loads(native.read_text()));raise AssertionError('legacy partial graph unexpectedly passed')
 except KeyError:pass
 close(legacy)
 child,native,canonical,events,command=launch('complete',True);stages=[]
 def reject(stage):
  probe.publish(String(data=json.dumps(dict(event='component_graph_probe',stage=stage))));spin_for(3.)
  assert not native.exists() and not canonical.exists(),stage;stages.append(stage)
 reject('missing_metrics')
 metrics='/gateway_metrics';pub(metrics,String,'/gateway/metrics')
 for topic,kind in (('/clock',Clock),('/task_state',String),('/robot_failure',String),('/gateway/fault_configuration',String)):sub(metrics,kind,topic)
 for robot in ('tb1','tb2'):
  sub(metrics,String,f'/{robot}/battery_state');sub(metrics,ContactsState,f'/{robot}/collision')
  if robot=='tb1':sub(metrics,Odometry,f'/gateway/received/{robot}/odom')
 reject('missing_metrics_endpoint');sub(metrics,Odometry,'/gateway/received/tb2/odom')
 add(hq).destroy_subscription(subscriptions[hq,'/gateway/received/tb2/tf']);reject('missing_ap_endpoint')
 sub(hq,TFMessage,'/gateway/received/tb2/tf');illegal=ActionClient(add(metrics),NavigateToPose,'/tb2/navigate_to_pose');reject('metrics_action_client');illegal.destroy()
 illegal=pub(metrics,String,'/task_state');reject('metrics_control_publisher');add(metrics).destroy_publisher(illegal)
 illegal=sub(hq,TFMessage,'/tb2/battery/source_tf');reject('ap_native_tf_leak');add(hq).destroy_subscription(illegal)
 wait_graph(canonical);assert native.read_bytes()==canonical.read_bytes();snapshot=json.loads(canonical.read_text())
 audit=application_graph_audit(snapshot,2);ingress=native_tf_ingress_audit(snapshot,2,True)
 probe.publish(String(data=json.dumps(dict(event='component_graph_probe',stage='after_complete'))));spin_for(.5);close(child)
 rows=[json.loads(line) for line in events.read_text().splitlines()];received={e['data'].get('stage') for e in rows if isinstance(e['data'],dict) and e['data'].get('event')=='component_graph_probe'}
 assert set(stages)|{'after_complete'}<=received
 result=dict(status='PASS',scope='Actual DDS endpoint discovery and real read-only observer; synthetic application nodes, no Gazebo task, no navigation goals or source changes',rejected_stages=stages,delivery_continued=True,legacy_partial_snapshot_rejected_by_monitor=True,legacy_command=legacy_command,observer_command=command,application_audit=audit,native_audit=ingress,canonical_graph_sha256=hashlib.sha256(canonical.read_bytes()).hexdigest(),actual_navigation_goals=0,all_owned_closed=True)
finally:
 for child in list(children):close(child)
 for node in nodes.values():node.destroy_node()
 if rclpy.ok():rclpy.shutdown()
result.update(observer_sha256=hashlib.sha256((root/'scripts/observe_p3b5.py').read_bytes()).hexdigest(),reader_sha256=hashlib.sha256((root/'scripts/p2c_native_graph.py').read_bytes()).hexdigest())
a.output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
