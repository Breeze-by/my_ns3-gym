import hashlib
import json
from pathlib import Path
ROOT=Path('/home/zhuyulab/ns3-workspace')
P=Path('/tmp/mr3_p2a0_v22_matrix_proposal_v3')
raw=(P/'handoff_v3.json').read_bytes()
assert hashlib.sha256(raw).hexdigest()=='c4e4f6f5c3a1ef76f8ea6fd7e21134171fced26f812cc0986581ccd677e28ede'
h=json.loads(raw);assert h['source_writers_stopped'] and not h['actual_native_admission_granted']
assert len(h['files'])==11
for row in h['files']:
    raw=Path(row['source']).read_bytes();target=ROOT/row['canonical']
    assert hashlib.sha256(raw).hexdigest()==row['sha256']
    assert len(raw)==row['bytes'] and not target.exists(),target
    target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    assert target.read_bytes()==raw
proof={'schema':'mr3-v22-root-matrix-promotion-v3','handoff':str(P/'handoff_v3.json'),'source_writers_stopped':True,'files':h['files'],'native_calls':0}
Path('/tmp/mr3_p2a0_v22_matrix_promotion_v3.json').write_text(json.dumps(proof,indent=2)+'\n')
print('Promoted10 source/config files plus exact ready plan5a14; actual admission remains false.')
