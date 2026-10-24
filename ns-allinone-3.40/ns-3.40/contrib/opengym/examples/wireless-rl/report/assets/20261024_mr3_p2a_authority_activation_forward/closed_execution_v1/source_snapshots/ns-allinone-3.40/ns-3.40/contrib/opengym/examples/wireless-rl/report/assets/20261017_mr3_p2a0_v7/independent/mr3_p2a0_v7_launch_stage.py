import sys,json,subprocess,time,datetime,os
from pathlib import Path
root=Path('/home/zhuyulab/ns3-workspace')
w=root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
sys.path.insert(0,str(w))
from mr3_learning.supervisor import process_identity
stage,freeze=sys.argv[1:]
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==freeze
assert not subprocess.check_output(['git','status','--porcelain'],cwd=root,text=True)
plan=json.loads((w/'report/assets/20261017_mr3_p2a0_v7/predeclared_plan_v7.json').read_text())
s=next(x for x in plan['stages'] if x['stage']==stage)
cmd=[sys.executable,'-u',*s['command'][1:]]
receipt=Path('/tmp/mr3_p2a0_v7_'+stage+'_launch.json')
assert not receipt.exists()
console=Path('/tmp/mr3_p2a0_v7_'+stage+'_console.log')
started=time.monotonic()
with console.open('x') as output:
 process=subprocess.Popen(cmd,cwd=w,stdout=output,stderr=subprocess.STDOUT)
 record={'schema':'mr3-p2a0-native-launch-v1','freeze':freeze,'stage':stage,'command_argv':cmd,'cwd':str(w),'benchmark_parent':process_identity(process.pid),'launcher_identity':process_identity(os.getpid()),'start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'start_monotonic':started,'console':str(console)}
 receipt.write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps(record),flush=True)
 code=process.wait()
record.update(returncode=code,wall_duration_sec=time.monotonic()-started,end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),benchmark_parent_after=process_identity(process.pid))
receipt.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps(record),flush=True)
sys.exit(code)
