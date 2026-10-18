import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
H = Path('/tmp/mr3_p2a0_v24_matrix_proposal_v1/handoff_final_v1.json')
raw = H.read_bytes()
assert hashlib.sha256(raw).hexdigest() == 'b852d9eac5f20bf0d96eef71ba2b67b1b11d18b7d68ec22f33b0d09a8517ab96'
h = json.loads(raw)
assert h['source_STOP'] and h['metadata_STOP'] and not h['actual_native_admission']
records = []
for row in h['promotion_list']:
    source, destination = Path(row['source']), Path(row['destination'])
    data = source.read_bytes()
    assert len(data) == row['bytes'] and hashlib.sha256(data).hexdigest() == row['sha256']
    exists = destination.exists()
    if exists:
        assert destination.read_bytes() == data, 'Never silently overwrite existing promotion: ' + str(destination)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        assert destination.read_bytes() == data
    records.append({'path': str(destination.relative_to(ROOT)), 'sha256': row['sha256'], 'already_identical': exists})
result = {'schema': 'mr3-v24-root-final-matrix-promotion-v1', 'files': records, 'copied': sum(not r['already_identical'] for r in records), 'native': False, 'plan_sha256': h['plan_sha256']}
Path('/tmp/mr3_p2a0_v24_final_matrix_promotion_v1.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
