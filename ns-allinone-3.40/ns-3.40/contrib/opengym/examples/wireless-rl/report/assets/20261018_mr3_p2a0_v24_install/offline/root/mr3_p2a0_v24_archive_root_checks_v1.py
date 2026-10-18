import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
A = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install'
paths = [Path('/tmp') / name for name in ('mr3_p2a0_v24_prepare_canonical_build_v1.py', 'mr3_p2a0_v24_source_promotion_v1.json', 'mr3_p2a0_v24_prepare_binary_archive_v1.py', 'mr3_p2a0_v24_archive_actual_binary_v1.py', 'mr3_p2a0_v24_copy_build_evidence_v1.py', 'mr3_p2a0_v24_promote_fixed_sources_v1.py', 'mr3_p2a0_v24_fixed_source_promotion_v1.json', 'mr3_p2a0_v24_promote_final_environment_v1.py', 'mr3_p2a0_v24_final_environment_promotion_v1.json', 'mr3_p2a0_v24_run_canonical_audit_unit_v1.py')]
paths += [Path('/tmp/mr3_p2a0_v24_canonical_audit_unit_v1') / name for name in ('execution.json', 'stdout.txt', 'stderr.txt')]
records = []
for source in paths:
    raw = source.read_bytes()
    destination = A / 'offline/root' / (source.name if source.parent == Path('/tmp') else 'audit_unit_' + source.name)
    assert not destination.exists()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    assert destination.read_bytes() == raw
    records.append({'original': str(source), 'canonical': str(destination.relative_to(ROOT)), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
result = {'schema': 'mr3-v24-root-source-promotion-and-unit-custody-v1', 'files': records, 'scope': 'Preparation only. Unit16 belongs to e128/27df; later causal wording/3 literals have separate identity2 checks and final frozen preflight. No repeated unit or native.'}
(A / 'offline/root/custody_v1.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'files': len(records), 'bytes': sum(r['bytes'] for r in records)}))
