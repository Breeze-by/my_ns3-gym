import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
A = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install'
names = ('mr3_p2a0_v24_archive_root_checks_v1.py', 'mr3_p2a0_v24_update_current_docs_v1.py', 'mr3_p2a0_v24_prepare_report_log_v1.py', 'mr3_p2a0_v24_promote_matrix_v1.py', 'mr3_p2a0_v24_final_matrix_promotion_v1.json', 'mr3_p2a0_v24_promote_final_plan_v2.py', 'mr3_p2a0_v24_final_plan_promotion_v2.json', 'mr3_p2a0_v24_copy_final_preparation_v1.py', 'mr3_p2a0_v24_final_root_static_v1.py', 'mr3_p2a0_v24_final_root_static_v1.json')
records = []
for name in names:
    source = Path('/tmp') / name
    raw = source.read_bytes()
    destination = A / 'offline/root' / name
    assert not destination.exists()
    destination.write_bytes(raw)
    assert destination.read_bytes() == raw
    records.append({'original': str(source), 'canonical': str(destination.relative_to(ROOT)), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
(A / 'offline/root/final_static_custody_v2.json').write_text(json.dumps({'schema': 'mr3-v24-root-final-static-custody-v2', 'files': records, 'scope': 'Static/promotion/text/archive preparation only; no native or sourcefreezed admission.'}, indent=2) + '\n')
print(json.dumps({'files': len(records), 'bytes': sum(x['bytes'] for x in records)}))
