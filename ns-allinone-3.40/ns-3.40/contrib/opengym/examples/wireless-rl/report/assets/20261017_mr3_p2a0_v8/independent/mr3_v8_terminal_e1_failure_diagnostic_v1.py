"""Read-only exact failure provenance, using only recorded local/received inputs."""
from pathlib import Path
import hashlib,importlib,json,sys
root=Path('/home/zhuyulab/ns3-workspace'); pkg=root/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration';sys.path.insert(0,str(pkg));helper=importlib.import_module('multi_robot_exploration.mr3_motion_safety')
ep=root/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v8_terminal/worker0/episode001_open_101';path=ep/'motion_safety.jsonl';rawsha=hashlib.sha256();size=0;release=None;last_inputs={n:{} for n in helper.ROBOTS};received=None;window=[];fatal=None;counts={};invalid=[]
for line in path.open('rb'):
 rawsha.update(line);size+=len(line);r=json.loads(line);kind=r['kind'];counts[kind]=counts.get(kind,0)+1;v=r['payload']
 if kind in ('own_odom','own_tf'):last_inputs[v['robot']][kind]=r
 if kind=='received_states':received=r
 if kind=='release':release=helper.timestamp_ns(v['stamp'])
 if kind=='decision' and release is not None and v['clock_ns']<=release+100000000:
  now=v['clock_ns']/1e9;n=v['robot'];own=v['own_state'];peers=v['received_peers']; states={'own':own,**peers};valid={key:helper.valid_state(state,now,r['epoch']) for key,state in states.items()};ages={key:{field:helper.elapsed_ns(state[field],now) for field in ('source_stamp','odom_source_stamp','tf_source_stamp') if field in state} for key,state in states.items() if isinstance(state,dict)}
  entry={'record_sequence':r['record_sequence'],'sim_time_sec':r['sim_time_sec'],'decision':v,'valid_state_by_input':valid,'source_ages_ns':ages,'last_local_inputs':dict(last_inputs[n]),'last_received_record':received}
  window.append(entry)
  if not all(valid.values()):invalid.append({'record_sequence':r['record_sequence'],'robot':n,'clock_ns':v['clock_ns'],'valid':valid,'source_ages_ns':ages})
 if kind in ('failure','settled_turn_model_failure','terminal'): 
  if fatal is None and kind in ('failure','settled_turn_model_failure'):fatal=r
out={'schema':'mr3-v8-terminal-e1-failure-provenance-v1','freeze':'d41485dfd93797026316806916e127eb5101f3b8','epoch':window[0]['decision']['own_state']['epoch'],'release_ns':release,'first_recorded_failure':fatal,'kinds':counts,'invalid_recorded_state_inputs':invalid,'window':window,'motion_raw':{'path':str(path),'bytes':size,'sha256':rawsha.hexdigest()},'helper_path':str(Path(helper.__file__).resolve()),'helper_sha256':hashlib.sha256(Path(helper.__file__).read_bytes()).hexdigest(),'analysis_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'Exact recorded decision+raw-local+received-state input provenance and frozen pure valid_state replay. No sensors/truth were injected, no controls, no native retry; valid_state failure is sufficient to make health false but does not itself establish graph status.'}
target=Path('/tmp/mr3_p2a0_v8_terminal_e1_failure_provenance_v1.json');target.write_text(json.dumps(out,indent=2)+'\n');print(json.dumps({k:out[k] for k in ('release_ns','first_recorded_failure','kinds','invalid_recorded_state_inputs')},ensure_ascii=False))
