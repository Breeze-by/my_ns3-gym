"""Finite closed-original diagnosis, original delivered maps only."""
import gzip,hashlib,json,math,os,time
from collections import Counter
from pathlib import Path
import numpy as np
from mr3_learning.proxy2d_codec import decode_arrays
from multi_robot_exploration import mr3_observation as obs
A=Path(__file__).resolve().parent
R=next(p for p in A.parents if (p/'.git').exists())
RUN=R/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v31/karto_behavior_v1'
started=time.monotonic_ns();bound={}
def load(p,compressed=False):
 raw=p.read_bytes();key=str(p.resolve());value={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 assert bound.setdefault(key,value)==value
 return json.loads(gzip.decompress(raw) if compressed else raw)
def cell(entry,x,y):
 c=obs._cell(x,y,entry['resolution'],entry['origin'],entry['grid'].shape)
 return None if c is None else int(entry['grid'][c])
def diagnose(data,robot):
 name=robot['name'];pose=(robot['x'],robot['y']);rows=[]
 own=data['robot_maps'][name]
 fused=dict(grid=data['raw_grid'],resolution=data['resolution'],origin=data['origin'])
 for label,entry in (('navigation',data['navigation_maps'][name]),('own',own),('fused',fused)):
  grid=entry['grid'];res=entry['resolution'];origin=entry['origin']
  traversable,clearance=obs.native_traversable(grid,res)
  seed,offset,diag=obs._seed_diagnostics(grid,traversable,clearance,robot,res,origin)
  nearest=[]
  if seed is not None:
   row,col=seed;radius=math.ceil(.5/res)
   y0,y1=max(0,row-radius),min(grid.shape[0],row+radius+1)
   x0,x1=max(0,col-radius),min(grid.shape[1],col+radius+1)
   blocked=np.argwhere(grid[y0:y1,x0:x1]!=0)+[y0,x0]
   candidates=[]
   for r,c in blocked:
    x,y=origin[0]+(int(c)+.5)*res,origin[1]+(int(r)+.5)*res
    distance=math.dist((x,y),pose)
    candidates.append((distance,int(r),int(c),x,y))
   for distance,r,c,x,y in sorted(candidates)[:8]:
    nearest.append(dict(cell=[r,c],centre_xy=[x,y],distance_to_estimated_pose_m=distance,
      map_value=int(grid[r,c]),own_value=cell(own,x,y),fused_value=cell(fused,x,y)))
  rows.append(dict(source=label,diagnostics=diag,nearest_blocked_within_half_metre=nearest))
 return dict(name=name,estimated_pose_xy=list(pose),maps=rows)
report=load(RUN/'behavior_report.json');assert report['passed'] and report['bound_bytes_unchanged']
result=dict(schema='mr3-p2a-v31-finite-clearance-diagnostic-v1',passed=False,episodes=[],source_files={},
 qualification=False,training_eligible=False,policy_calls=0,optimizer_steps=0,
 limitation='Observed mask/clearance obstruction, not a causal counterfactual, a safe correction or RL impossibility proof.')
for episode in report['episodes']:
 directory=Path(episode['directory']);timeline=episode['verified_prefix_statistics']['candidate_map_timeline']
 selected={0,len(timeline)-1}
 first=next((i for i,row in enumerate(timeline) if all(v is not None for v in row['seed_rejections'])),None)
 if first is not None:selected.add(first)
 rows=[]
 raw=(directory/'trace.jsonl.gz').read_bytes();bound[str(directory/'trace.jsonl.gz')]={'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
 traces=[json.loads(line) for line in gzip.decompress(raw).splitlines()]
 actors=[row for row in traces if row['event'] in ('reset','step_return')]
 assert len(actors)==len(timeline)==301
 for index in sorted(selected):
  ref=actors[index]['actor_input_ref'];path=directory/ref['path']
  payload=load(path,compressed=True)
  assert hashlib.sha256(gzip.decompress(path.read_bytes())).hexdigest()==ref['sha256']
  data=decode_arrays(payload)
  states=[obs._robot_state(robot,data['now']) for robot in data['robots']]
  rows.append(dict(observation_index=index,elapsed_sec=timeline[index]['elapsed_sec'],
   actor_ref=ref,seed_rejections=timeline[index]['seed_rejections'],
   reachable=timeline[index]['reachable_candidates_by_robot'],
   legal_goal_actions=timeline[index]['legal_goal_actions_by_robot'],
   robot_diagnostics=[diagnose(data,robot) for robot in states]))
 hist={name:dict(Counter(str(row['seed_rejections'][i]) for row in timeline)) for i,name in enumerate(obs.ROBOT_NAMES)}
 result['episodes'].append(dict(scene=directory.name,observations=301,
  all_seed_rejected_observations=sum(all(v is not None for v in row['seed_rejections']) for row in timeline),
  no_legal_goal_observations=sum(not any(row['legal_goal_actions_by_robot']) for row in timeline),
  rejection_histogram=hist,selected=rows,final_metrics=episode['final_metrics'],
  final_paths=episode['final_physical_paths_m'],terminal=episode['terminal_assessment']))
assert sum(len(e['selected']) for e in result['episodes'])<=9
for path,v in bound.items():
 raw=Path(path).read_bytes();assert len(raw)==v['bytes'] and hashlib.sha256(raw).hexdigest()==v['sha256']
result['passed']=True;result['source_files']=bound;result['elapsed_seconds']=(time.monotonic_ns()-started)/1e9
fields=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
result['identity']=dict(pid=os.getpid(),parent=int(fields[1]),group=int(fields[2]),session=int(fields[3]),start_ticks=int(fields[19]))
with (A/'forensic_result_v1.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
print(json.dumps({'passed':True,'selected':sum(len(e['selected']) for e in result['episodes']),'seconds':result['elapsed_seconds']}))
