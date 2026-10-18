import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
OUT=A/'deployment_checks';OUT.mkdir(exist_ok=False)
python='/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
checks=[('audit_ppo_units',[python,'-B','-m','unittest','mr3_learning.tests.test_audit_ppo']),
        ('canonical_manifest_deployment',[python,'-B',str(A/'independent/test_smoother_custody_v1.py'),'SourceAndWorkersTests.test_real_build_source_archive_read_only_binding'])]
env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',CUDA_VISIBLE_DEVICES='')
env.pop('PYTHONPATH',None)
sources=[W/'mr3_learning/audit_ppo.py',W/'mr3_learning/tests/test_audit_ppo.py',A/'independent/mr3_v25_smoother_custody_v1.py',A/'independent/test_smoother_custody_v1.py']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before={str(p):sha(p) for p in sources}
records=[]
for label,command in checks:
    t=time.monotonic()
    with (OUT/(label+'.stdout.txt')).open('xb') as out,(OUT/(label+'.stderr.txt')).open('xb') as err:
        result=subprocess.run(command,cwd=W,env=env,stdout=out,stderr=err)
    records.append(dict(label=label,argv=command,returncode=result.returncode,wall_seconds=time.monotonic()-t,
                        stdout_sha256=sha(OUT/(label+'.stdout.txt')),stderr_sha256=sha(OUT/(label+'.stderr.txt'))))
report=dict(schema='mr3-v25-root-canonical-deployment-checks-v1',checks=records,sources_before=before,
            sources_unchanged=all(sha(Path(p))==s for p,s in before.items()),
            scope='Original16 learning auditor units after actual new shared loader change plus one canonical-location real-build/source/archive test. Author21 not rerun. CPU only, no ROS/DDS/native/GPU.')
report['passed']=all(x['returncode']==0 for x in records) and report['sources_unchanged']
(OUT/'checks_v1.json').write_text(json.dumps(report,indent=2)+'\n')
(OUT/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
print(json.dumps(report))
raise SystemExit(0 if report['passed'] else 1)
