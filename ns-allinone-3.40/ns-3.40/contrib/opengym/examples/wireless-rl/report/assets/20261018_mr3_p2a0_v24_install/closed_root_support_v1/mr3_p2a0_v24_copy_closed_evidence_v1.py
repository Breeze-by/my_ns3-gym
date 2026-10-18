import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v24_install'
S = Path('/tmp/mr3_p2a0_v24_selected_closed_v1')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
assert sha((S / 'manifest.json').read_bytes()) == '3c776e11e35edce7862b6ad483a411212588682e66695991b0bcdd8ed1187ba8'
assert not (A / 'native').exists()
records = []

def copy(source, destination, expected=None):
    assert destination.is_relative_to(A)
    raw = source.read_bytes()
    digest = sha(raw)
    if expected:
        assert digest == expected, str(source)
    assert not destination.exists(), str(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    assert destination.read_bytes() == raw
    records.append({'source': str(source), 'canonical': str(destination.relative_to(ROOT)), 'sha256': digest, 'bytes': len(raw)})

selected = set()
for group in (S / 'native/interface', S / 'metadata'):
    manifest = json.loads((group / 'manifest.json').read_text())
    assert manifest['passed'] and manifest['source_end_sha_and_stat_verified']
    prefix = ROOT / manifest['prospective_prefix']
    assert prefix.is_relative_to(A / 'native')
    for original in manifest['files']:
        for part in original['parts']:
            source = group / part['selected']
            destination = ROOT / part['prospective_canonical']
            assert destination == prefix / part['selected']
            assert source.stat().st_size == part['selected_bytes']
            copy(source, destination, part['selected_sha256'])
            selected.add(source)
    copy(group / 'manifest.json', prefix / 'manifest.json')
    selected.add(group / 'manifest.json')
for name in ('manifest.json', 'helper_configuration.json'):
    copy(S / name, A / 'native' / name)
    selected.add(S / name)
assert selected == {p for p in S.rglob('*') if p.is_file()}
assert len(selected) == 522

support = Path('/tmp/mr3_p2a0_v24_closed_pack_support_v1')
for name in ('manifest_v1.json', 'handoff_v1.json', 'originals.tar.gz'):
    copy(support / name, A / 'closed_pack_support_v1' / name)
closure = Path('/tmp')
for name in ('mr3_p2a0_v24_final_closure_observation_v1.py', 'mr3_p2a0_v24_final_closure_observation_v1.json', 'mr3_p2a0_v24_final_closure_observation_v1_handoff.json', 'mr3_p2a0_v24_runtime_install_observation_v1.json', 'mr3_p2a0_v24_runtime_native_close_observation_v1.json'):
    copy(closure / name, A / 'closed_native_review_v1' / name)
chain = Path('/tmp/mr3_p2a0_v24_model_fault_review_v1')
h = json.loads((chain / 'handoff_v1.json').read_text())
assert h['inputs_stat_sha_verified'] and h['writer_status'].startswith('STOP')
for row in h['files']:
    copy(Path(row['path']), A / 'closed_control_forensic_v1' / row['name'], row['sha256'])
copy(chain / 'handoff_v1.json', A / 'closed_control_forensic_v1/handoff_v1.json', '3399db99907b48fa4c9ab428cb25d31ca1df3a724c65ea0e20413d6a564ab416')
body = Path('/tmp/mr3_p2a0_v24_body_trigger_independent_v1')
for name in ('manifest_v1.json', 'handoff_v1.json', 'originals.tar.gz', 'raw_guard_smoother_review_v2.json'):
    copy(body / name, A / 'closed_body_review_v1' / name)
result = {'schema': 'mr3-v24-root-closed-evidence-copy-v1', 'native_selected_files': len(selected), 'files': records, 'scope': 'Original V24 failure, partial14 valid transitions and later3SKIP preserved. Each encoded part copied to its exact declared prospective_canonical path, not a guessed nested native directory. No simulator/test replay.'}
(A / 'closed_copy_receipt_v1.json').write_text(json.dumps(result, indent=2) + '\n')
Path('/tmp/mr3_p2a0_v24_closed_root_copy_summary_v1.json').write_text(json.dumps({'files': len(records), 'bytes': sum(r['bytes'] for r in records), 'native_selected_files': len(selected)}, indent=2) + '\n')
print(json.dumps({'files': len(records), 'bytes': sum(r['bytes'] for r in records), 'native_selected_files': len(selected)}))
