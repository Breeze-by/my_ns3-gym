"""Bounded V24 tb2 actual-chain extraction; no formal consumer or production imports."""
from pathlib import Path
import gzip
import hashlib
import json
import math
import os
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
EP = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v24_interface/worker0/episode001_open_101'
B = Path(__file__).resolve().parent
START, END = 55_000_000_000, 57_200_000_000
sha = lambda raw: hashlib.sha256(raw).hexdigest()
canonical = lambda value: json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
inputs = {}
selected = {}
started = time.monotonic()

def scan(path, wanted):
    before = path.stat()
    digest = hashlib.sha256()
    rows = []
    offset = 0
    with path.open('rb') as stream:
        for line_number, raw in enumerate(stream, 1):
            digest.update(raw)
            if wanted(raw):
                row = json.loads(raw)
                rows.append({'offset':offset,'line_number':line_number,'bytes':len(raw),
                             'sha256':sha(raw),'row':row,'raw':raw})
            offset += len(raw)
    after = path.stat()
    assert (before.st_size,before.st_mtime_ns,before.st_ino)==(after.st_size,after.st_mtime_ns,after.st_ino)
    inputs[str(path)] = {'sha256':digest.hexdigest(),'bytes':offset,
                         'stat':[after.st_size,after.st_mtime_ns,after.st_ino],
                         'scope':'single stream SHA plus same stat; selected original bytes re-seek verified at end'}
    return rows

motion_path = EP/'motion_safety.jsonl'
motion = scan(motion_path, lambda raw:any(x in raw for x in
              (b'"sim_time_sec":55.',b'"sim_time_sec":56.',b'"sim_time_sec":57.')))
motion = [item for item in motion if START <= round(item['row']['sim_time_sec']*1e9) <= END]
faults = [item for item in motion if item['row']['kind']=='normal_control_model_invalid']
assert len(faults)==1
fault = faults[0]['row']['payload']
assert fault['robot']=='tb2' and fault['reason']=='measured_angular_speed_exceeded'
decisions = [item for item in motion if item['row']['kind']=='decision'and item['row']['payload']['robot']=='tb2']
request_sequences = {item['row']['payload']['request']['sequence'] for item in decisions if item['row']['payload']['request'] is not None}
motion_selected = []
for item in motion:
    row,payload = item['row'],item['row']['payload']
    if row['kind']=='normal_control_model_invalid' or (
       row['kind']=='own_odom'and payload.get('robot')=='tb2'and payload.get('input_sequence')==fault['input_sequence']) or (
       row['kind']in('decision','actual')and payload.get('robot')=='tb2') or (
       row['kind']=='raw_request'and payload.get('robot')=='tb2'and payload['request']['sequence']in request_sequences) or (
       row['kind']in('control_failure','control_ack','control_ack_published')and round(row['sim_time_sec']*1e9)==fault['commit_clock_ns']):
        motion_selected.append(item)
own = next(item for item in motion_selected if item['row']['kind']=='own_odom')
assert sha(canonical(own['row']['payload']['message'])) == fault['odom_payload_sha256']
assert own['row']['record_sequence'] < faults[0]['row']['record_sequence']

drive_path = EP/'drive_tb2.jsonl'
drive_all = scan(drive_path, lambda raw:True)
configuration = drive_all[0]['row']
sep, radius = configuration['wheel_separation_m'][0], configuration['wheel_diameter_m'][0]/2
assert configuration['wheel_order']==['right','left']
latest=None
actuation=[]
zero_before=None
for item in drive_all:
    row=item['row']
    if row['kind']=='command_received':
        latest=row
        if row['sim_time_ns']<START and row['desired_v']==0 and row['desired_w']==0:zero_before=item
    elif row['kind']=='actuation'and START<=row['sim_time_ns']<=END:
        assert latest is not None and row['cmd_seq']==latest['cmd_seq']
        assert all(row[key]==latest[key]for key in ('desired_v','desired_w','target_clock_ns','target_decision_sequence'))
        current,applied,desired=(row[key]for key in ('current_rim_mps','applied_rim_mps','desired_rim_mps'))
        actuation.append({'sim_time_ns':row['sim_time_ns'],'cmd_seq':row['cmd_seq'],
            'target_clock_ns':row['target_clock_ns'],'target_decision_sequence':row['target_decision_sequence'],
            'desired_v':row['desired_v'],'desired_w':row['desired_w'],
            'current_rim_mps':current,'applied_rim_mps':applied,'desired_rim_mps':desired,
            'current_joint_radps':[v/radius for v in current],
            'applied_joint_command_radps':[v/radius for v in applied],
            'wheel_current_yaw_proxy_radps':(current[0]-current[1])/sep,
            'wheel_applied_yaw_proxy_radps':(applied[0]-applied[1])/sep,
            'wheel_desired_yaw_radps':(desired[0]-desired[1])/sep,
            'row_sha256':item['sha256'],'source_line':item['line_number'],'source_offset':item['offset']})
drive_selected=[item for item in drive_all if item['row']['kind']=='configuration'or START<=item['row']['sim_time_ns']<=END]
if zero_before:drive_selected.append(zero_before)
drive_selected.sort(key=lambda item:item['offset'])
commands=[item['row']for item in drive_selected if item['row']['kind']=='command_received'and START<=item['row']['sim_time_ns']<=END]
assert all(abs(row['desired_w'])<=.8 and abs(row['desired_v'])<=.2 for row in commands)
peak_clock=fault['odom_source_ns']
same_clock=[row for row in actuation if row['sim_time_ns']==peak_clock]
closest=sorted(actuation,key=lambda row:abs(row['sim_time_ns']-peak_clock))[:3]

trans_path=EP/'transitions.jsonl'
trans=scan(trans_path,lambda raw:True)
actions=[]
for item in trans:
    row=item['row'];command=row.get('info',{}).get('command')
    if not isinstance(command,dict):continue
    snap=row.get('snapshot',{})
    elapsed=snap.get('task_elapsed_sec')
    actions.append({'kind':row['kind'],'returned_elapsed_sec':elapsed,'command':command,
                    'source_line':item['line_number'],'source_offset':item['offset'],'row_sha256':item['sha256']})
transition_selected=[item for item in trans if item['row'].get('kind')=='step'and item['row'].get('snapshot',{}).get('task_elapsed_sec',-1)>=10]

for label,path,rows in [('motion_tb2_window',motion_path,motion_selected),('drive_tb2_window',drive_path,drive_selected),('returned_actions10_14',trans_path,transition_selected)]:
    raw=b''.join(item['raw']for item in rows)
    out=B/(label+'.jsonl.gz')
    with out.open('xb')as dest:
        with gzip.GzipFile(fileobj=dest,mode='wb',filename='',mtime=0)as stream:stream.write(raw)
    assert gzip.decompress(out.read_bytes())==raw
    selected[label]={'source':str(path),'path':str(out),'encoded_sha256':sha(out.read_bytes()),
        'raw_sha256':sha(raw),'raw_bytes':len(raw),'rows':[ {k:v for k,v in item.items()if k not in('raw','row')} | {'kind':item['row']['kind'],'record_sequence':item['row'].get('record_sequence')}for item in rows]}
    with path.open('rb')as stream:
        for item in rows:
            stream.seek(item['offset']);assert stream.read(item['bytes'])==item['raw']
for path,binding in inputs.items():
    stat=Path(path).stat();assert [stat.st_size,stat.st_mtime_ns,stat.st_ino]==binding['stat']

math_source=ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py'
source_files=[math_source,math_source.with_name('motion_safety.py'),math_source.with_name('mr3_motion_control.py'),
              ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp']
source_proof={str(p):{'sha256':sha(p.read_bytes()),'bytes':p.stat().st_size}for p in source_files}
body=fault['twist'];turn=math.sqrt(sum(body['angular'][axis]**2 for axis in ('x','y','z')))
linear=math.hypot(body['linear']['x'],body['linear']['y'])
zero_after=[row for row in commands if row['sim_time_ns']>=fault['commit_clock_ns']and row['desired_v']==0 and row['desired_w']==0]
result={'schema':'mr3-v24-bounded-tb2-control-actuation-trigger-v1','freeze':'5d684c46f9f99a867a94f1fed8c52e923e2486ef',
 'argv':[sys.executable,*sys.argv],'cwd':os.getcwd(),'script_sha256':sha(Path(__file__).read_bytes()),
 'scope':'Closed existing log extraction, same actualtb2 window55–57.2; no formal consumer rerun, tests, ROS/DDS/SDK/native or source/physics change.',
 'source_files':source_proof,'input_bindings':inputs,'selected_originals':selected,
 'fault_original':{k:v for k,v in faults[0].items()if k!='raw'},
 'raw_own_original':{k:v for k,v in own.items()if k!='raw'},
 'trigger_math':{'full_angular_norm_radps':turn,'original_limit_radps':1.2,'over_by_radps':turn-1.2,
   'planar_norm_mps':linear,'original_planar_limit_mps':.30,'source_age_ns':fault['commit_clock_ns']-fault['odom_source_ns'],
   'commit_task_elapsed_ns':fault['commit_clock_ns']-fault['known_release_ns'],
   'classification':'Actual fresh selectedown raw angularnorm gate, not stale/geometry/acceleration predicate; physical mechanism remains separately interpreted.'},
 'driver_configuration':configuration,'actual_incoming_commands':{'count':len(commands),'max_abs_v':max(abs(row['desired_v'])for row in commands),'max_abs_w':max(abs(row['desired_w'])for row in commands),'caps_pass':True},
 'latest_received_tuple_matches_every_window_actuation':True,'actuation':actuation,'same_clock_peak_actuation':same_clock,
 'nearest_peak_actuations':closest,'last_zero_storage_before_window':None if zero_before is None else zero_before['row'],
 'first_zero_storage_after_fault':zero_after[0]if zero_after else None,'actual_returned_action_records':actions,
 'formulas':{'body_norm':'sqrt(wx**2+wy**2+wz**2), measured_velocity_error>1.2 withnoepsilon, mr3_motion_safety.py:238–288',
    'wheel_proxy':'(rim_right-rim_left)/wheel_separation; joint radps=rim/radius; desiredrim=v±w*separation/2',
    'caution':'Wheelkinematic proxy is descriptive, not rigid no-slip identity or bodybound theorem. Same-clock odom and actuation are actual callbackvalues; this extraction does not prove unique contact/solver/slip cause.'},
 'wall_seconds':time.monotonic()-started}
with (B/'chain_review_v1.json').open('x')as stream:stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'review':str(B/'chain_review_v1.json'),'sha256':sha((B/'chain_review_v1.json').read_bytes()),
 'fault':result['trigger_math'],'configuration':{k:configuration[k]for k in('max_acceleration_mps2','max_torque_nm','wheel_separation_m','wheel_diameter_m','update_rate_hz')},
 'commandcaps':result['actual_incoming_commands'],'peakactuation':same_clock,'zeroafter':result['first_zero_storage_after_fault'],
 'actions':[{k:r[k]for k in('returned_elapsed_sec','command')}for r in actions[-6:]],'wall_seconds':result['wall_seconds']}))
