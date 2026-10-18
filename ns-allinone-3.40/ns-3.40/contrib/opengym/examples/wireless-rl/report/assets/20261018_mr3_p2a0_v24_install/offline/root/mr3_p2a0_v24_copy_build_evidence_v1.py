import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
A = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install'
B = Path('/tmp/mr3_p2a0_v24_canonical_build_independent_review_v1')
h = json.loads((B / 'handoff_v1.json').read_text())
assert h['passed'] and h['all_source_input_final_sha_stat_stable']
selected = [(Path(h['archive_path']), 'originals.tar.gz', h['archive_sha256']), (Path(h['manifest_path']), 'manifest_v1.json', h['manifest_sha256']), (Path(h['review_path']), 'review_v1.json', h['review_sha256']), (B / 'handoff_v1.json', 'handoff_v1.json', None)]
for source, name, expected in selected:
    raw = source.read_bytes()
    if expected:
        assert hashlib.sha256(raw).hexdigest() == expected
    destination = A / 'offline/build' / name
    assert not destination.exists()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    assert destination.read_bytes() == raw
print(json.dumps({'copied': len(selected), 'actual_library_sha256': h['actual_library_sha256'], 'native': False}))
