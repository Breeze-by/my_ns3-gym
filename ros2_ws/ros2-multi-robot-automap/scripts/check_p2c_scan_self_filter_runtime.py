#!/usr/bin/env python3
"""Isolated conditional native SLAM replay; never launches a task or navigation."""
import argparse,base64,bisect,gzip,hashlib,json,math,os,signal,subprocess,time
from pathlib import Path
import numpy as np
import rclpy,yaml
from rclpy.serialization import deserialize_message,serialize_message
from rclpy.qos import QoSProfile,ReliabilityPolicy,DurabilityPolicy
from rosidl_runtime_py.utilities import get_message
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import LaserScan
from tf2_msgs.msg import TFMessage
from nav_msgs.msg import OccupancyGrid
from multi_robot_exploration import control as c
from p2c_scan_self_filter import noise_associated_mask, physical_body_box, physical_range_uncertainty

a=argparse.ArgumentParser(description=__doc__);a.add_argument('--output',type=Path,required=True);a.add_argument('--stop',type=float,required=True);a.add_argument('--original',type=Path,required=True);a.add_argument('--baseline-binary-dir',type=Path,required=True);a.add_argument('--robot',default='tb2',choices=['tb1','tb2','tb3','tb4']);a=a.parse_args()
assert os.environ.get('ROS_DOMAIN_ID') in ('216','217'), 'use an isolated component domain'
original=json.loads((a.original/'summary.json').read_text())
snapshot=json.loads((a.baseline_binary_dir/'manifest.json').read_text());assert snapshot['commit']==original['git_commit']
for row in snapshot['files']:assert hashlib.sha256(Path(row['saved']).read_bytes()).hexdigest()==row['sha256']
a.output.mkdir(exist_ok=False)
root=a.original.resolve()
source=root/'navigation_inputs.jsonl.gz';classes={};scans=[];tf=[];static=[];odometry=[]
def stamp(h):return h.stamp.sec+h.stamp.nanosec/1e9
with gzip.open(source,'rt') as f:
 for i,line in enumerate(f):
  e=json.loads(line);topic=e['topic']
  if topic not in [f'/{a.robot}/{suffix}' for suffix in ('scan','tf','tf_static','odom')]:continue
  raw=base64.b64decode(e['cdr']);msg=deserialize_message(raw,classes.setdefault(e['type'],get_message(e['type'])))
  if topic.endswith('scan'):
   if stamp(msg.header)<=a.stop:scans.append((stamp(msg.header),i,msg,raw))
  elif topic.endswith('odom'):
   p=msg.pose.pose;odometry.append((stamp(msg.header),p.position.x,p.position.y,c.quaternion_yaw(p.orientation)))
  elif topic.endswith('tf_static'):static.append(msg)
  else:
   useful=[t for t in msg.transforms if t.header.frame_id!='map' and t.child_frame_id!='map']
   if useful:
    out=TFMessage();out.transforms=useful;tf.append((max(stamp(t.header) for t in useful),i,out))
scans.sort(key=lambda row:row[0]);tf.sort(key=lambda row:row[0]);odometry.sort()
print('Loaded',len(scans),'scans and',len(tf),'native non-map TF records',flush=True)
# Rectangle is the strict intersection of the original SDF/URDF chassis XY boxes.
box=physical_body_box();laser=(-.064,0.,0.);masked=[]
for at,index,msg,raw in scans:
 ranges=np.asarray(msg.ranges);angles=msg.angle_min+np.arange(len(ranges))*msg.angle_increment
 with np.errstate(invalid='ignore'):x=laser[0]+ranges*np.cos(angles);y=laser[1]+ranges*np.sin(angles)
 mask=noise_associated_mask(msg,box,laser,physical_range_uncertainty())
 if mask.any():masked.append(dict(source=at,capture_index=index,beams=np.flatnonzero(mask).tolist(),ranges=ranges[mask].tolist(),base_endpoints=np.column_stack((x[mask],y[mask])).tolist()))

params=yaml.safe_load(Path('src/slam_toolbox/config/mapper_params_online_multi_async.yaml').read_text());params=next(iter(params.values()))['ros__parameters'];assert np.allclose(params['scan_self_filter_body_box'],box,rtol=0,atol=1e-15)
old_config=subprocess.check_output(['git','show',original['git_commit']+':ros2_ws/ros2-multi-robot-automap/src/slam_toolbox/config/mapper_params_online_multi_async.yaml'],text=True)
old_params=next(iter(yaml.safe_load(old_config).values()))['ros__parameters'];assert {k:v for k,v in params.items() if k not in ('scan_self_filter_body_box','scan_self_filter_range_uncertainty_m')}=={k:v for k,v in old_params.items() if k not in ('scan_self_filter_body_box','scan_self_filter_range_uncertainty_m')}
params['use_sim_time']=True;old_params['use_sim_time']=True
processes={};logs={};maps={};transforms={};counts={};streams={};commands={}
rclpy.init();node=rclpy.create_node('p2c_native_scan_replay');qos=QoSProfile(depth=100,reliability=ReliabilityPolicy.RELIABLE);latched=QoSProfile(depth=100,reliability=ReliabilityPolicy.RELIABLE,durability=DurabilityPolicy.TRANSIENT_LOCAL)
clock=node.create_publisher(Clock,'/clock',qos);pubs={}
original_scan_hashes={hashlib.sha256(raw).hexdigest() for _,_,_,raw in scans};received_cdr={'raw':0,'body_filtered':0}
def on_scan_cdr(label,data):
 assert hashlib.sha256(data).hexdigest() in original_scan_hashes,'scan CDR changed during replay'
 received_cdr[label]+=1
def on_map(label,msg):
 maps[label]=msg;counts[label]=counts.get(label,0)+1
 streams[label].write(json.dumps(dict(type='nav_msgs/msg/OccupancyGrid',cdr=base64.b64encode(serialize_message(msg)).decode()))+'\n')
def on_tf(label,msg):
 for t in msg.transforms:
  if t.header.frame_id=='map' and t.child_frame_id=='odom':transforms[label]=t
try:
 for label in ['raw','body_filtered']:
  prefix='/p2c_replay_'+label
  param_path=a.output/(label+'_params.yaml');param_path.write_text(yaml.safe_dump({prefix+'/slam_toolbox':{'ros__parameters':old_params if label=='raw' else params}}))
  log=(a.output/(label+'_node.log')).open('x');logs[label]=log
  binary=a.baseline_binary_dir/'multirobot_slam_toolbox_node' if label=='raw' else Path('install/slam_toolbox/lib/slam_toolbox/multirobot_slam_toolbox_node')
  cmd=[str(binary.resolve()),'--ros-args','--params-file',str(param_path.resolve()),'-r','__ns:='+prefix,'-r','/map:='+prefix+'/map','-r','/map_metadata:='+prefix+'/map_metadata','-r','/tf:='+prefix+'/tf','-r','/tf_static:='+prefix+'/tf_static'];commands[label]=cmd
  streams[label]=gzip.open(a.output/(label+'_maps.jsonl.gz'),'xt')
  env=os.environ.copy()
  if label=='raw':env['LD_LIBRARY_PATH']=str(a.baseline_binary_dir.resolve())+':'+env.get('LD_LIBRARY_PATH','')
  processes[label]=subprocess.Popen(cmd,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,env=env)
  pubs[label]=(node.create_publisher(LaserScan,prefix+'/scan',qos),node.create_publisher(TFMessage,prefix+'/tf',qos),node.create_publisher(TFMessage,prefix+'/tf_static',latched))
  node.create_subscription(LaserScan,prefix+'/scan',lambda data,name=label:on_scan_cdr(name,data),qos,raw=True)
  node.create_subscription(OccupancyGrid,prefix+'/map',lambda msg,name=label:on_map(name,msg),latched)
  node.create_subscription(TFMessage,prefix+'/tf',lambda msg,name=label:on_tf(name,msg),qos)
 deadline=time.monotonic()+15
 while time.monotonic()<deadline and any(pubs[label][0].get_subscription_count()<2 for label in pubs):rclpy.spin_once(node,timeout_sec=.1)
 assert all(pubs[label][0].get_subscription_count()>=2 for label in pubs),'SLAM scan subscribers missing'
 for _,_,static_pub in pubs.values():
  for msg in static:static_pub.publish(msg)
 for _ in range(10):rclpy.spin_once(node,timeout_sec=.05)
 cursor=0;begin=time.monotonic()
 for number,(at,index,msg,raw) in enumerate(scans):
  while cursor<len(tf) and tf[cursor][0]<=at+.12:
   for _,tf_pub,_ in pubs.values():tf_pub.publish(tf[cursor][2])
   cursor+=1
  clk=Clock();clk.clock.sec=int(at);clk.clock.nanosec=round((at-int(at))*1e9);clock.publish(clk)
  for _ in range(3):rclpy.spin_once(node,timeout_sec=.005)
  pubs['raw'][0].publish(raw);pubs['body_filtered'][0].publish(raw)
  until=time.monotonic()+.05
  while time.monotonic()<until:rclpy.spin_once(node,timeout_sec=.005)
  assert all(p.poll() is None for p in processes.values()),'SLAM replay child exited'
  if number%250==0:print('Replayed',number,'at',at,'map counts',counts,flush=True)
 flush_until=time.monotonic()+4.5
 while time.monotonic()<flush_until:rclpy.spin_once(node,timeout_sec=.1)
 assert all(count==len(scans) for count in received_cdr.values()),('missing original CDR reception',received_cdr)
 assert set(maps)==set(pubs) and set(transforms)==set(pubs),'Missing replay map or map TF'
 at=scans[-1][0];k=bisect.bisect_right(odometry,(at,float('inf'),float('inf'),float('inf')))-1;odom=odometry[k];results={}
 for label,msg in maps.items():
  t=transforms[label];angle=c.quaternion_yaw(t.transform.rotation);dx=t.transform.translation.x;dy=t.transform.translation.y
  position=(math.cos(angle)*odom[1]-math.sin(angle)*odom[2]+dx,math.sin(angle)*odom[1]+math.cos(angle)*odom[2]+dy)
  home_state=original['result']['robots'][a.robot];hx=home_state['battery_charge_x'];hy=home_state['battery_charge_y']
  # Native battery charging coordinates are fixed in map, not odometry.
  home=(hx,hy)
  grid=np.asarray(msg.data,dtype=np.int16).reshape(msg.info.height,msg.info.width);origin=(msg.info.origin.position.x,msg.info.origin.position.y);cell=c.world_to_grid(*position,msg.info.resolution,*origin);r,col=cell
  distance,path=c.known_return_route(grid,msg.info.resolution,origin,position,home,.8,include_route=True)
  results[label]=dict(source=stamp(msg.header),position=position,home=home,cell=cell,value=int(grid[cell]),window=grid[r-4:r+5,col-4:col+5].tolist(),qualified_return_distance=distance,return_path=path,map_tf=dict(x=dx,y=dy,yaw=angle))
  (a.output/(label+'_final_map.json')).write_text(json.dumps(dict(cdr=base64.b64encode(serialize_message(msg)).decode(),type='nav_msgs/msg/OccupancyGrid'))+'\n')
 import re
 for log in logs.values():log.flush()
 (a.output/'probe_results.json').write_text(json.dumps(dict(results=results,
     reference_commit=original['git_commit'],robot=a.robot,
     current_filter_header_sha256=hashlib.sha256(Path('src/slam_toolbox/include/slam_toolbox/scan_self_filter.hpp').read_bytes()).hexdigest(),
     scope='Unclassified conditional map metrics, retained even when the comparison assertion fails.'),indent=2)+'\n')
 native_masks=[(float(at),int(count)) for at,count in re.findall(r'SCAN_SELF_FILTER source=([\d.]+) frame=base_scan removed=(\d+)',(a.output/'body_filtered_node.log').read_text())]
 expected_masks={round(row['source'],9):len(row['beams']) for row in masked}
 assert native_masks and all(expected_masks.get(round(at,9))==count for at,count in native_masks),'native C++/original CDR mask mismatch'
 assert results['raw']['qualified_return_distance'] is None and results['body_filtered']['qualified_return_distance'] is not None, 'raw failure and prospective path not reproduced'
 assert math.dist(results['body_filtered']['return_path'][-1],results['body_filtered']['home'])<=.8
 summary=dict(status='PASS',exact_original_cdr_received=received_cdr,baseline_snapshot=snapshot,native_cpp_mask_witnesses=len(native_masks),native_cpp_removed_returns=sum(count for _,count in native_masks),scope='Conditional native SLAM DDS replay with original scan/source headers, native odometry TF and original parameters. Synthetic replay clock derived from source headers; receipt scheduling and historical scan graph are not the original task. No task causal success claim.',source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),original_commit=original['git_commit'],robot=a.robot,range_uncertainty_m=physical_range_uncertainty(),current_scan_filter_header_sha256=hashlib.sha256(Path('src/slam_toolbox/include/slam_toolbox/scan_self_filter.hpp').read_bytes()).hexdigest(),current_slam_cpp_sha256=hashlib.sha256(Path('src/slam_toolbox/src/slam_toolbox_multirobot.cpp').read_bytes()).hexdigest(),scan_count=len(scans),clock_stop=at,wall_sec=time.monotonic()-begin,chassis_box=box,laser_to_base=laser,masked_scans=masked,total_masked_beams=sum(len(row['beams']) for row in masked),results=results,commands=commands,environment={k:os.environ.get(k) for k in ['ROS_DOMAIN_ID','RMW_IMPLEMENTATION']},params=params)
 (a.output/'result.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(dict(status=summary['status'],exact_original_cdr_received=received_cdr,native_cpp_mask_witnesses=summary['native_cpp_mask_witnesses'],native_cpp_removed_returns=summary['native_cpp_removed_returns'],map_results={label:{k:r[k] for k in ['source','value','qualified_return_distance','map_tf']} for label,r in results.items()})),flush=True)
finally:
 for p in processes.values():
  if p.poll() is None:os.killpg(p.pid,signal.SIGINT)
 for label,p in processes.items():
  try:p.wait(timeout=15)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait();print('cleanup SIGKILL',label,flush=True)
  print('child closed',label,p.pid,p.returncode,flush=True)
 for stream in streams.values():stream.close()
 for stream in logs.values():stream.close()
 node.destroy_node();rclpy.shutdown()
