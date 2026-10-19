#!/usr/bin/python3
"""Closed-file extraction and arithmetic only; no runtime/audit imports or simulations."""
import hashlib,json,math,sys,time
from pathlib import Path
ROOT=Path('/home/zhuyulab/ns3-workspace')
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
RUN=ROS/'log/mr3_ppo/mr3_p2a_v13_minimal'
EP=RUN/'native/round0000/worker0/episode001_open_101'
OUT=Path('/tmp/mr3_p2a_v13_minimum_failure_sequence_forensic_v1.json')
MD=OUT.with_suffix('.md')
MATH=Path('/tmp/mr3_p2a_v13_minimum_measurement_contract_review_v1.json')
EXPECTED_MATH='11dbbac3c9fd1d3c72eb842f63a38926bf6fb1eb152c25d45451f67b0d81a1e5'
def proof(p):
 b=p.read_bytes();s=p.stat()
 return {'path':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'stat':{'dev':s.st_dev,'inode':s.st_ino,'size':s.st_size,'mtime_ns':s.st_mtime_ns}}
def rows(p):
 with p.open() as f:
  for line,s in enumerate(f,1):yield {'line':line,'record':json.loads(s)}
def ns(msg):
 h=msg['header']['stamp'];return h['sec']*10**9+h['nanosec']
def sha_obj(d):return hashlib.sha256(json.dumps(d,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def select(d,keys):return {k:d[k] for k in keys if k in d}
started=time.monotonic_ns()
assert not OUT.exists() and not MD.exists()
raws=[EP/n for n in ['motion_safety.jsonl','odometry_tb3.jsonl','drive_tb3.jsonl','driver_odometry_receipts.jsonl','drive_targets.jsonl','control_phase_worker.jsonl','physics.jsonl','metadata.json','summary.json','native_stop.json','round0000_w0_e1_e154087c.json','transitions.jsonl']]
raws += [RUN/'summary.json',RUN/'failed_collection_0000.json',MATH]
sources=[ROS/'src/multi_robot_exploration/multi_robot_exploration/motion_safety.py',ROS/'src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py',ROS/'src/multi_robot/src/mr3_gazebo_diff_drive.cpp']
initial={str(p):proof(p) for p in raws+sources}
assert initial[str(MATH)]['sha256']==EXPECTED_MATH
math_report=json.loads(MATH.read_text())
for q in math_report['data_sources']:
 assert proof(Path(q['path']))['sha256']==q['sha256'],q['path']
motion=[];failure=None;prior=None
for item in rows(EP/'motion_safety.jsonl'):
 d=item['record'];k=d['kind'];a=d['payload']
 if failure is None and k=='settled_turn_model_failure':failure=item;trigger=prior
 if d['record_sequence']>=107840 and d['record_sequence']<=107915:motion.append(item)
 prior=item
assert failure['line']==107887
assert trigger['record']['kind']=='own_odom' and trigger['record']['payload']['robot']=='tb3'
message=trigger['record']['payload']['message'];source_ns=ns(message)
last_allowed=max((x for x in motion if x['record']['kind']=='decision' and x['record']['payload']['robot']=='tb3' and x['record']['payload']['decision']['allow'] and x['line']<failure['line']),key=lambda x:x['line'])
first_stop=min((x for x in motion if x['record']['kind']=='decision' and x['record']['payload']['robot']=='tb3' and x['record']['payload']['decision']['output']==[0.0,0.0] and x['line']>failure['line']),key=lambda x:x['line'])
seq=first_stop['record']['payload']['decision_sequence'];anchor=last_allowed['record']['payload']['own_state']['settled_turn']['active_anchor_source_ns']
drive=list(rows(EP/'drive_tb3.jsonl'))
first_stored_stop=next(x for x in drive if x['record']['kind']=='command_received' and x['record'].get('target_decision_sequence')==seq)
first_actual_stop=next(x for x in drive if x['record']['kind']=='actuation' and x['record']['sim_time_ns']>=first_stored_stop['record']['sim_time_ns'])
last_actual_before=max((x for x in drive if x['record']['kind']=='actuation' and x['record']['sim_time_ns']<=source_ns),key=lambda x:x['record']['sim_time_ns'])
assert first_stored_stop['record']['desired_v']==0 and first_stored_stop['record']['desired_w']==0
assert first_actual_stop['record']['desired_v']==0 and first_actual_stop['record']['desired_w']==0
assert source_ns<first_stored_stop['record']['sim_time_ns']<first_actual_stop['record']['sim_time_ns']
active_act=[x for x in drive if x['record']['kind']=='actuation' and anchor<=x['record']['sim_time_ns']<=source_ns]
runs=[]
for x in drive:
 d=x['record']
 if d['kind']!='command_received' or not anchor<=d['sim_time_ns']<=source_ns:continue
 key=[d['desired_v'],d['desired_w']]
 if not runs or runs[-1]['target']!=key:runs.append({'target':key,'start_storage_ns':d['sim_time_ns'],'last_storage_ns':d['sim_time_ns'],'first_line':x['line'],'last_line':x['line'],'message_count':1})
 else:runs[-1].update(last_storage_ns=d['sim_time_ns'],last_line=x['line'],message_count=runs[-1]['message_count']+1)
native=next(x for x in rows(EP/'odometry_tb3.jsonl') if x['record'].get('kind')=='publication' and ns(x['record']['odom'])==source_ns)
received=next(x for x in rows(EP/'driver_odometry_receipts.jsonl') if x['record'].get('robot')=='tb3' and x['record'].get('kind')=='odom' and ns(x['record']['message'])==source_ns)
assert native['record']['odom']==received['record']['message']==message
zero_publication=next(x for x in rows(EP/'drive_targets.jsonl') if (lambda a:a['robot']=='tb3' and a['decision_sequence']==seq)(json.loads(x['record']['target_json'])))
selected_motion=[x for x in motion if x['line'] in [last_allowed['line'],trigger['line'],failure['line'],first_stop['line'],107897,107904,107907]]
physics=[x for x in rows(EP/'physics.jsonl') if 56960000000<=x['record']['end_time_ns']<=57020000000]
control=[x for x in rows(EP/'control_phase_worker.jsonl') if x['record'].get('component')=='motion' and x['record'].get('kind')=='ack_consumed' and 56980000000<=x['record'].get('worker_physical_ns',0)<=57000000000]
eval_data=json.loads((EP/'round0000_w0_e1_e154087c.json').read_text());native_summary=json.loads((EP/'summary.json').read_text());ppo=json.loads((RUN/'summary.json').read_text());failed=json.loads((RUN/'failed_collection_0000.json').read_text())
monitor=eval_data['contact_monitor_summary']
contact={'source':'isolated evaluator summary, not a newly run contact audit','collision_events':eval_data['collision_events'],'collision_duration_sec':eval_data['collision_duration_sec'],'active':eval_data['collision_monitoring_active'],'fresh':eval_data['collision_monitoring_fresh'],'component_count_per_robot':eval_data['contact_component_count_per_robot'],'filtered_support_count':monitor['filtered_support_count'],'ever_unhealthy':monitor['ever_unhealthy'],'tb3_components':monitor['components']['tb3'],'limitation':'Zero recorded non-support collision events does not prove wheel/ground force symmetry, no slip, no solver effect, or continuous safety.'}
for p in raws+sources:assert initial[str(p)]==proof(p),str(p)
a=math_report['closed_data_arithmetic'];speed=message['twist']['twist']['linear']
result={'schema':'mr3-v13-minimum-closed-data-failure-sequence-forensic-v1','scope':'Read-only extraction/arithmetic; no formal audit or scientific PASS; original failure unchanged','runtime_freeze':'0063aa233ba3008ddcc1eb09ea8068112eea3965','episode':str(EP),'inputs':list(initial.values()),'inputs_unchanged_after_read':True,'script_identity':proof(Path(__file__)),'measurement_review':{'artifact_sha256':EXPECTED_MATH,'measurement_contract':math_report['measurement_contract'],'closed_data_arithmetic':a},'first_failure':failure,'trigger_own_odom':trigger,'trigger_source_ns':source_ns,'trigger_planar_speed_mps':math.hypot(speed['x'],speed['y']),'last_allowed_decision':last_allowed,'first_stop_decision':first_stop,'first_stop_target_publication':zero_publication,'last_actual_before_failure_sample':last_actual_before,'first_stop_storage':first_stored_stop,'first_actual_stop_response':first_actual_stop,'native_publication':native,'independent_packet_receipt':received,'trigger_payload_equal_at_three_boundaries':True,'trigger_payload_canonical_sha256':sha_obj(message),'selected_motion_raw':selected_motion,'physics_quantum_context':physics,'worker_ack_context':control,'active_storage_target_runs':runs,'active_actuation_checks':{'count':len(active_act),'all_desired_linear_zero':all(x['record']['desired_v']==0 for x in active_act),'all_alpha_one':all(x['record']['alpha']==1 for x in active_act),'all_applied_pair_means_zero':all(sum(x['record']['applied_rim_mps'])/2==0 for x in active_act),'last_stop_actuation_pair_mean':sum(first_actual_stop['record']['applied_rim_mps'])/2},'timing':{'trigger_source_leads_guard_node_clock_ns':source_ns-round(trigger['record']['sim_time_sec']*1e9),'guard_own_receipt_to_failure_wall_sec':(failure['record']['wall_monotonic_ns']-trigger['record']['wall_monotonic_ns'])/1e9,'failure_to_stop_target_publication_wall_sec':(zero_publication['record']['wall_monotonic_ns']-failure['record']['wall_monotonic_ns'])/1e9,'trigger_source_to_stop_storage_sim_sec':(first_stored_stop['record']['sim_time_ns']-source_ns)/1e9,'trigger_source_to_first_actual_stop_sim_sec':(first_actual_stop['record']['sim_time_ns']-source_ns)/1e9,'first_stored_stop_command_itself_used_at_next_wheel_update':first_stored_stop['record']['cmd_seq']==first_actual_stop['record']['cmd_seq'],'note':'Driver has physical timestamps, not wall stamps. First stop target was stored, then superseded by next zero target before first wheel update. Source56.995 is within completed physical quantum56.98→57.0; ROS /clock callback may trail native odometry delivery.'},'contact_summary_only':contact,'native_summary':select(native_summary,['epoch','reason','closed','transition_count','failures','launch_returncode','native_failures','wall_duration_sec','cleanup_wall_sec']),'evaluator_terminal':select(eval_data,['termination_reason','failure_reason','control_failure','end_sim_time_sec','elapsed_sim_time_sec','nav_aborted','nav_canceled','success','correct_coverage_ratio']),'ppo_summary':ppo,'failed_collection_metadata':failed,'source_line_references':[{'path':str(sources[0]),'ranges':[[148,162],[319,321],[329,341],[546,567]],'meaning':'Own odometry is logged before observe; exception halts and emits stop; causal decision own-state excludes future source stamps; target publication retains decision reference.'},{'path':str(sources[1]),'ranges':[[76,94],[98,150],[178,183]],'meaning':'Only nonzero linear output resets uninterrupted segment; raw XY chords accumulate and failure raises before latest commit.'},{'path':str(sources[2]),'ranges':[[624,739],[894,908]],'meaning':'Measured wheel feedback paired actuation; WORLD odometry producer.'}],'conclusions':{'first_failed_predicate':'active settled turn total drift budget exceeded; not planar-speed or chord-speed limit','cumulative_path_m':a['path_m'],'budget_m':0.01*0.78,'overshoot_m':a['path_m']-0.01*0.78,'last_safe_cumulative_path_m':last_allowed['record']['payload']['own_state']['settled_turn']['active_path_m'],'latest_certificate_source_stale_after_raise':'observe increments active_path then raises before latest=sample; later snapshot may still carry56.975 while true triggering own input2592/source56.995 is independently recorded. This does not remove measured crossing.','plant_evidence':'Small real sampled raw-model-origin XY motion persisted under issued symmetric zero-centre wheel commands. Native producer and delivered odometry match. API reference point/base origin and xy speed interpretation match contract.','not_supported_causes':['SLAM/map→odom correction as the cumulative path source','CoG/reference-point velocity substitution','linear.z included in planar norm','postfailure braking command caused the earlier path crossing','native Nav2 abort as first cause: evaluator nav_aborted=0 and control_failure names motion_safety'],'mechanism_unknown':['Why physical wheel/ground dynamics sustain nonzero centre motion despite symmetric issued rims','Exact force/slip/ODE constraint contribution: no 1ms body/contact-force observer trace in this normal episode','Whether any prospective physical-control fix would satisfy total path during all long zero-linear segments'],'candidate_implication':'A smaller angular-speed/acceleration profile alone supplies no mathematical whole-segment path bound over arbitrarily long active zero-linear intervals; this episode contains angular reversals and zero-angular pulses without linear reset. Any repair must retain original limits and be validated prospectively; no proposed change is verified here.','training_eligibility':'Model-invalid closed round was rejected before buffer/GAE/optimizer; real native terminal and failed-collection evidence remain. No scientific or95% credit.'},'cpu_started_monotonic_ns':started,'cpu_completed_monotonic_ns':time.monotonic_ns()}
result['cpu_duration_sec']=(result['cpu_completed_monotonic_ns']-started)/1e9
with OUT.open('x') as f:json.dump(result,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')
text=f"""# V13 minimum closed-data sequence forensics (no scientific PASS)

- First failure: tb3, motion_safety.jsonl line/seq107887, node clock56.98; active total XY path exceeded .0078m. Trigger is preceding own_odom line107886/input2592/source56.995, planar speed{result['trigger_planar_speed_mps']:.17g}m/s, angular_z{message['twist']['twist']['angular']['z']:.17g}.
- Anchor45.275→56.995:587 samples/586 chords/11.72s; path{a['path_m']:.17g}m, net displacement{a['net_xy_displacement_m']:.17g}m. Max planar speed{a['planar_speed_mps']['maximum']:.17g}m/s and max chord speed{a['chord_speed_mps']['maximum']:.17g}m/s are below .01.
- Last allowed decision2848 has path .0077842378100595406. Failing sample adds .000015898523731588608m. Certificate latest remains56.975 after observe raises before latest assignment; independently saved true triggering source is56.995.
- Segment includes +.3, zero, −.3, zero, +.3 angular targets; zero-linear output is uninterrupted. Angular stop/reversal does not reset the original tracker. All345 actual updates before crossing have alpha1, desired linear0 and symmetric issued rims (mean0). Actual joint rim feedback is slightly asymmetric; force/slip cause is unknown.
- Ordering: sample56.995 → first zero stored56.999 (cmd2590/decision2849) → next zero stored57.0 (cmd2591/decision2850) → actual wheel update57.005 using cmd2591. The first zero was stored but itself superseded before wheel update. First braking issued mean{result['active_actuation_checks']['last_stop_actuation_pair_mean']:.17g} is after failure, not evidence of its cause.
- Exact triggering odom payload matches native publication, independent packet receipt, and guard receive. Physics records are1ms step/20ms quantum receipts, not1ms body-velocity/force measurements. Source56.995 lies within physical quantum56.98→57.0 while /clock callback lags.
- Native summary: launch_returncode0, no native_failures,16 transitions; evaluator explicitly control_failure motion_safety/settled_turn_model_failure, nav_aborted0. Recorded18-stream monitor is fresh with zero non-support collision events; that does not establish no wheel/ground contact force or no solver effects.
- This is a real model-invariant violation with clean native shutdown; PPO admission correctly rejects the round before optimizer. .3 profile is not proved fixed; no retries, thresholds, source, native, or formal audits were changed/run.

Artifact: {OUT}; script/inputs/source SHA and exact raw records embedded. Independent measurement review: {MATH} SHA{EXPECTED_MATH}.
"""
with MD.open('x') as f:f.write(text)
print(json.dumps({'output':proof(OUT),'markdown':proof(MD),'cpu_duration_sec':result['cpu_duration_sec']},sort_keys=True))
