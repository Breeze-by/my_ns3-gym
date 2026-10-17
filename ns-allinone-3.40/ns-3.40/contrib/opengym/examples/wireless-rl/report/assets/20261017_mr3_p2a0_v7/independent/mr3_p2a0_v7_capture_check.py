import sys,subprocess,json,time,hashlib,gzip
from pathlib import Path
root=Path('/home/zhuyulab/ns3-workspace')
asset=root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v7'
label=sys.argv[1];cmd=sys.argv[2:]
paths=sorted(set(subprocess.check_output(['git','diff','--name-only'],cwd=root,text=True).splitlines()+subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=root,text=True).splitlines()))
paths=[p for p in paths if '/report/assets/' not in p]
def hashes():
 return {p:hashlib.sha256((root/p).read_bytes()).hexdigest() for p in paths if (root/p).is_file()}
before=hashes();start=time.monotonic();r=subprocess.run(cmd,capture_output=True,text=True);elapsed=time.monotonic()-start
raw=(r.stdout+r.stderr).encode();log=asset/(label+'.log.gz');log.write_bytes(gzip.compress(raw,mtime=0))
result={'schema':'mr3-p2a0-check-v1','command':cmd,'cwd':str(Path.cwd()),'python':sys.executable,'exit_code':r.returncode,'wall_seconds':elapsed,'source_before':before,'source_after':hashes(),'stdout_stderr_gzip':log.name,'decoded_sha256':hashlib.sha256(raw).hexdigest(),'stdout_tail':(r.stdout+r.stderr)[-3000:]}
(asset/(label+'.json')).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ('command','exit_code','wall_seconds','stdout_tail')}));sys.exit(r.returncode)
