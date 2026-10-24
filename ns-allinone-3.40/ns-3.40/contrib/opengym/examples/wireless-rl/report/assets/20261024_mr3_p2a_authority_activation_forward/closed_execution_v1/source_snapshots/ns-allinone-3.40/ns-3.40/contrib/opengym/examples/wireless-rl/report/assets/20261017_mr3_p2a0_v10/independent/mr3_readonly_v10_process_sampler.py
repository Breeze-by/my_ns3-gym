"""Finite read-only process/binary sampler; no ROS API, signals or control IPC."""
import argparse,hashlib,json,subprocess,time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--prefix',required=True);p.add_argument('--max-wall-sec',type=float,required=True);p.add_argument('--interval-sec',type=float,default=45.);a=p.parse_args();prefix=Path('/tmp')/a.prefix;started=time.monotonic();index=10
while time.monotonic()-started<=a.max_wall_sec:
    launch_path=Path(str(prefix)+'_launch.json')
    try:launch=json.loads(launch_path.read_bytes())
    except (FileNotFoundError,ValueError) as error:
        event={'kind':'launch_receipt_temporarily_unavailable','error':repr(error),'wall_monotonic_ns':time.monotonic_ns()}
        with Path(str(prefix)+'_process_sampler_events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
        time.sleep(min(5.,a.interval_sec));continue
    output=Path(str(prefix)+'_process_monitor_'+str(index).zfill(3)+'.json');console=Path(str(prefix)+'_process_monitor_'+str(index).zfill(3)+'_console.log');command=['/usr/bin/python3','/tmp/mr3_readonly_v10_drive_process_monitor.py',str(a.run),'--launch',str(launch_path),'--binary-proof','/tmp/mr3_p2a0_v10_binaryproof.json','--output',str(output)]
    result=subprocess.run(command,capture_output=True,text=True);raw=(result.stdout+result.stderr).encode()
    with console.open('xb') as f:f.write(raw)
    event={'kind':'capture','index':index,'command':command,'exit_code':result.returncode,'wall_monotonic_ns':time.monotonic_ns(),'output':str(output),'console':str(console),'console_sha256':hashlib.sha256(raw).hexdigest()}
    if output.exists():
        d=json.loads(output.read_bytes());event.update(owned_current=len(d['owned_current_processes']),errors=d['errors'],output_sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    with Path(str(prefix)+'_process_sampler_events.jsonl').open('a') as f:f.write(json.dumps(event)+'\n')
    print(json.dumps(event),flush=True)
    if result.returncode!=0:raise RuntimeError('read-only sampler failed; preserved console '+str(console))
    if launch.get('status') in ('completed','failed'):
        print(json.dumps({'kind':'launcher_completed','returncode':launch.get('returncode'),'status':launch.get('status'),'monitor_scope':'closure remains pending final owned-ledger verification'}),flush=True);break
    index+=1;time.sleep(a.interval_sec)
else:
    raise RuntimeError('read-only sampler wall ceiling reached; native was not modified')
