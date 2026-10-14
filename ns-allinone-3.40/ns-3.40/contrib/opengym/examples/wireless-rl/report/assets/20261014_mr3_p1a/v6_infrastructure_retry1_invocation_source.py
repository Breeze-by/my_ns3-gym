from pathlib import Path
import datetime,hashlib,json,os,shlex,subprocess
root=Path('/home/zhuyulab/ns3-workspace')
ros=root/'ros2_ws/ros2-multi-robot-automap'
b=root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
a=b/'report/assets/20261014_mr3_p1a'
p=a/'v6_open303_infrastructure_retry1_predeclaration.json'
d=json.loads(p.read_text()); case=d['case'];sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
assert d['maximum_additional_attempts']==1
freeze=subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()
assert freeze==d['source_freeze']==subprocess.check_output(['git','rev-parse','origin/main'],cwd=root,text=True).strip()
prefixes=['ros2_ws/ros2-multi-robot-automap/src','ros2_ws/ros2-multi-robot-automap/scripts']
assert not subprocess.check_output(['git','diff','HEAD','--',*prefixes],cwd=root)
assert not subprocess.check_output(['git','ls-files','--others','--exclude-standard','--',*prefixes],cwd=root)
manifest=a/'runtime_component_manifest_matrix6.json';assert sha(manifest)==d['unchanged']['runtime_component_manifest_sha256']
for item in json.loads(manifest.read_text())['files']:assert sha(Path(item['path']))==item['sha256'],item['path']
for name,h in d['original_evidence_sha256'].items():assert sha(root/name)==h,name
env=dict(os.environ,ROS_DOMAIN_ID=str(case['ros_domain_id']),GAZEBO_MASTER_URI=f"http://127.0.0.1:{case['gazebo_port']}")
env.update(case['environment'])
record=dict(recorded_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),source_freeze=freeze,predeclaration_sha256=sha(p),predeclaration=str(p),case=case,runtime_component_manifest_sha256=sha(manifest),selected_environment={k:env.get(k) for k in ('RMW_IMPLEMENTATION','ROS_LOCALHOST_ONLY','ROS_DOMAIN_ID','GAZEBO_MASTER_URI','FASTRTPS_DEFAULT_PROFILES_FILE','SKIP_DEFAULT_XML','PYTHONNOUSERSITE','TURTLEBOT3_MODEL')},attempt_number=1,maximum_attempts=1)
with (a/(case['run_id']+'_invocation.json')).open('x') as f:json.dump(record,f,indent=2);f.write('\n')
with (b/'log.md').open('a') as f:f.write('\n### MR3-P1A supplemental pure-infrastructure replay '+case['run_id']+'\n\n- Freeze '+freeze+' still committed/pushed; original all9 remain. MaximumONE, accept any valid task result and never rerun mission failure. Full source+installed manifest and original evidence SHA verified. Exact environment='+json.dumps(record['selected_environment'],sort_keys=True)+'.\n- Command (canonical ROS root):\n\n```bash\n'+shlex.join(case['command'])+'\n```\n\n- Result pending. Runtime/source/physics/task/quality/contact/safety gates unchanged, no new middleware maintenance.\n')
rc=subprocess.run(case['command'],env=env,cwd=ros).returncode
result_path=Path(case['command'][-1])/case['run_id']/'summary.json'
result=json.loads(result_path.read_text()) if result_path.exists() else {}
with (b/'log.md').open('a') as f:f.write('\n- Supplemental replay finished '+datetime.datetime.now(datetime.timezone.utc).isoformat()+'; rc='+str(rc)+'; result='+str(result_path)+'; episodes='+json.dumps([{k:r.get(k) for k in ('gazebo_seed','success','termination_reason','runner_returncode','native_control_failure')} for r in result.get('episodes',[])],sort_keys=True)+'. Exactly one replay completed; original shutdown SIGSEGV retained, no root-cause cure or original9 clean claim.\n')
raise SystemExit(rc)
