import hashlib,json,subprocess,sys,time
from pathlib import Path
root=Path('/home/zhuyulab/ns3-workspace')
w=root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
freeze='d41485dfd93797026316806916e127eb5101f3b8'
stage=sys.argv[1]
assert stage in ('terminal','reset','deadline')
prefix='/tmp/mr3_p2a0_v8_'+stage
launch=json.loads(Path(prefix+'_launch.json').read_text())
assert launch['status']=='completed' and launch['passed'] is True and launch['freeze']==freeze
run=root/('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v8_'+stage)
commands=[('full_audit',[sys.executable,'-m','mr3_learning.audit_preparation',str(run),'--freeze',freeze,'--output',prefix+'_full_audit.json']),('drive_review_v1',['/usr/bin/python3',str(w/'report/assets/20261017_mr3_p2a0_v7/independent/mr3_independent_drive_trace_v4.py'),str(run),'--freeze',freeze,'--binary-proof','/tmp/mr3_p2a0_v8_binaryproof.json','--output',prefix+'_drive_review_v1.json'])]
records=[]
for name,argv in commands:
 console=Path(prefix+'_'+name+'_console.log')
 output=Path(prefix+'_'+name+'.json')
 assert not output.exists() and not console.exists()
 started=time.monotonic()
 with console.open('x') as stream:
  code=subprocess.run(argv,cwd=w,stdout=stream,stderr=subprocess.STDOUT).returncode
 record=dict(name=name,command_argv=argv,cwd=str(w),returncode=code,wall_seconds=time.monotonic()-started,console=str(console),console_sha256=hashlib.sha256(console.read_bytes()).hexdigest())
 if output.exists():
  record.update(output=str(output),output_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),passed=json.loads(output.read_text()).get('passed') is True)
 else: record['passed']=False
 records.append(record)
 print(json.dumps(record),flush=True)
 if code or not record['passed']: break
receipt=dict(schema='mr3-p2a0-v8-root-audit-execution-v1',freeze=freeze,stage=stage,passed=len(records)==2 and all(r['returncode']==0 and r['passed'] for r in records),records=records)
with Path(prefix+'_root_audit_execution_v1.json').open('x') as output: json.dump(receipt,output,indent=2)
sys.exit(0 if receipt['passed'] else 1)
