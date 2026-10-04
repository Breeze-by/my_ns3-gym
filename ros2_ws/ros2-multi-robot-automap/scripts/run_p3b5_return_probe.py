"""Pair runner plus isolated read-only physical observers; no task publications."""
import argparse,hashlib,json,os,signal,subprocess,sys,shlex
from pathlib import Path
from datetime import datetime,timezone
from run_p3b5_tasks import episode_domains
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--run-id',required=True)
p.add_argument('--ros-domain-base',type=int,default=90)
p.add_argument('--config',type=Path,default=Path(__file__).with_name('p3b5_return_probe_manifest.json'))
a=p.parse_args()
if not a.run_id or Path(a.run_id).name != a.run_id: p.error('run-id must be one directory name')
try:domains=episode_domains(a.ros_domain_base,2)
except ValueError as error:p.error(str(error))
base=root/'log/p3b5'/f'{a.run_id}_physics';base.mkdir(parents=True,exist_ok=False)
observer=Path(__file__).with_name('observe_p3b5_return_physics.py');config=a.config.resolve()
command=[sys.executable,str(root/'scripts/run_p3b5_tasks.py'),'--run-id',a.run_id,'--config',str(config),'--ros-domain-base',str(a.ros_domain_base)]
meta={'created_at_utc':datetime.now(timezone.utc).isoformat(),'runner_command':shlex.join(command),'config_content_sha256':hashlib.sha256(config.read_bytes()).hexdigest(),'config_source':config.read_text(),'config':json.loads(config.read_text()),'observer_content_sha256':hashlib.sha256(observer.read_bytes()).hexdigest(),'observer_source':observer.read_text(),'wrapper_content_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'gazebo_master_uri':os.environ.get('GAZEBO_MASTER_URI'),'cpu_affinity':sorted(os.sched_getaffinity(0)),'observers':[]}
processes=[];files=[];code=1
try:
 for label,domain in zip(('ideal','fault'),domains):
  out=base/(label+'.jsonl');log=base/(label+'.log');f=log.open('w');files.append(f)
  argv=[sys.executable,str(observer),'--output',str(out)];env=os.environ.copy();env['ROS_DOMAIN_ID']=str(domain)
  env['P3B5_OBSERVER_OWNER_PID']=str(os.getpid())
  process=subprocess.Popen(argv,env=env,stdout=f,stderr=subprocess.STDOUT);processes.append((label,process))
  meta['observers'].append({'mode':label,'ros_domain_id':str(domain),'command':shlex.join(argv),'output':str(out),'log':str(log),'pid':process.pid,'owner_pid':os.getpid()})
 (base/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
 code=subprocess.run(command,check=False).returncode
finally:
 for label,process in processes:
  if process.poll() is None:process.send_signal(signal.SIGINT)
  try:process.wait(timeout=10)
  except subprocess.TimeoutExpired:process.kill();process.wait()
  row=next(x for x in meta['observers'] if x['mode']==label);row['returncode']=process.returncode
  out=Path(row['output']);row['output_content_sha256']=hashlib.sha256(out.read_bytes()).hexdigest() if out.exists() else None
 for f in files:f.close()
 meta['runner_returncode']=code;meta['finished_at_utc']=datetime.now(timezone.utc).isoformat()
 (base/'metadata.json').write_text(json.dumps(meta,indent=2)+'\n')
sys.exit(code or next((row['returncode'] for row in meta['observers'] if row['returncode']), 0))
