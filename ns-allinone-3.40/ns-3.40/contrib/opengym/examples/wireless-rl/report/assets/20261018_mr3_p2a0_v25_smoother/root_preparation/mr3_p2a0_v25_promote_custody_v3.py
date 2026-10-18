import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
SOURCE=Path('/tmp/mr3_p2a0_v25_smoother_custody_proposal_v3')
sha=lambda b:hashlib.sha256(b).hexdigest()
handoff=json.loads((SOURCE/'handoff_v3.json').read_text())
assert handoff['source_status']=='STOP' and handoff['checks']['passed']
destinations={
    'mr3_v25_smoother_custody_v1.py':A/'independent/mr3_v25_smoother_custody_v1.py',
    'mr3_v25_stage_worker_bindings_v1.py':A/'independent/mr3_v25_stage_worker_bindings_v1.py',
    'test_smoother_custody_v1.py':A/'independent/test_smoother_custody_v1.py',
    'source_manifest_v1.json':A/'source_manifest_v1.json',
    'mr3_v25_smoother_binding_v1.json':A/'independent/mr3_v25_smoother_binding_v1.json',
    'audit_ppo.proposed_v25.py':W/'mr3_learning/audit_ppo.py',
}
assert sha((W/'mr3_learning/audit_ppo.py').read_bytes())=='cc467064ab66e04507ed4d4e805a4e23cdf09b3716fd85517ebb34fe7b2de521'
records=[]
for row in handoff['files']:
    raw=Path(row['source']).read_bytes()
    assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
    dest=destinations.pop(row['name'])
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.name!='audit_ppo.py':assert not dest.exists()
    dest.write_bytes(raw)
    assert dest.read_bytes()==raw
    records.append(dict(source=row['source'],canonical=str(dest.relative_to(ROOT)),sha256=sha(raw),bytes=len(raw)))
assert not destinations
source=Path('/tmp/mr3_p2a0_v25_smoother_custody_offline_v1')
dest=A/'admission_preparation_v1';dest.mkdir()
for name,expected in [('manifest.json','01da7a678dd9d4d694480d67472694b5b32a99b924a04a48d4106fe6970aafe7'),('originals.tar.gz','f101aba1c29600b7d4d57ecfc459a2d059bdf1237c32f253c581f28284dce7d8')]:
    raw=(source/name).read_bytes();assert sha(raw)==expected
    (dest/name).write_bytes(raw)
shutil.copyfile(Path('/tmp/mr3_p2a0_v25_smoother_custody_proposal_v1/handoff_v1.json'),dest/'handoff_v1.json')
dest=A/'admission_preparation_v3';dest.mkdir()
shutil.copyfile(SOURCE/'handoff_v3.json',dest/'handoff_v3.json')
(A/'root_preparation/custody_promotion_receipt_v3.json').write_text(json.dumps(dict(schema='mr3-v25-custody-promotion-v3',files=records),indent=2)+'\n')
shutil.copyfile(Path(__file__),A/'root_preparation'/Path(__file__).name)
print(json.dumps(dict(promoted=len(records),auditor_sha256=sha((W/'mr3_learning/audit_ppo.py').read_bytes()))))
