import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v25_smoother'
S = pathlib.Path('/tmp/mr3_p2a0_v25_selected_closed_v1')
rows = []

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def copy(source, target, expected=None):
    source, target = pathlib.Path(source), pathlib.Path(target)
    assert target.is_relative_to(A) and source.is_file()
    digest = sha(source)
    if expected is not None:
        assert digest == expected, str(source)
    assert not target.exists(), str(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, target)
    assert sha(target) == digest
    rows.append({'source': str(source), 'canonical': str(target.relative_to(ROOT)),
                 'bytes': target.stat().st_size, 'sha256': digest})

handoff_path = pathlib.Path('/tmp/mr3_p2a0_v25_matrix_pack_execution_v1/handoff_final_v1.json')
assert sha(handoff_path) == '6aee7a6ced223a069f61c5e5829d9bf3cb2ea6f70bc97868f2fcef83b4e118a6'
h = json.loads(handoff_path.read_text())
assert h['source_status'] == h['metadata_status'] == 'STOP'
assert h['all_part_encoded_decoded_and_original_reassembly_SHA_verified']
copy(S / 'manifest.json', A / 'native/manifest.json', h['top_manifest']['sha256'])
copy(S / 'helper_configuration.json', A / 'native/helper_configuration.json')
part_count = 0
for group in (S / 'native/interface', S / 'metadata'):
    mp = group / 'manifest.json'
    manifest = json.loads(mp.read_text())
    prefix = ROOT / manifest['prospective_prefix']
    assert prefix.is_relative_to(A / 'native')
    copy(mp, prefix / 'manifest.json')
    for original in manifest['files']:
        for part in original['parts']:
            destination = ROOT / part['prospective_canonical']
            assert destination == prefix / part['selected']
            assert part['selected_bytes'] < 3_000_000
            copy(group / part['selected'], destination, part['selected_sha256'])
            part_count += 1
assert part_count == h['encoded_parts'] == 843
assert len(rows) == h['selected_tree_files_including_manifests'] == 847
assert sum(r['bytes'] for r in rows) == h['selected_tree_bytes_including_manifests']

support = A / 'closed_pack_support_v1'
copy(handoff_path, support / 'handoff_final_v1.json')
copy(h['execution']['path'], support / 'execution.json', h['execution']['sha256'])
copy(h['source_support']['manifest'], support / 'source_execution_support_manifest_v1.json',
     h['source_support']['manifest_sha256'])
copy(h['source_support']['tar'], support / 'originals.tar.gz', h['source_support']['encoded_sha256'])

ci = pathlib.Path('/tmp/mr3_p2a0_v25_capture_035_review_v1')
for name in ('review_v1.py', 'review_v1.json'):
    copy(ci / name, A / 'closed_capture_035_review_v1' / name)
assert sha(A / 'closed_capture_035_review_v1/review_v1.json') == 'c9860c131f9e101e3441d9f8b962b529ed152e29b8fdeb8c66b659a7824207c3'
ind = pathlib.Path('/tmp/mr3_p2a0_v25_capture_035_independent_review_v1')
for name in ('handoff_v1.json', 'review_v1.json', 'sealed_manifest_v1.json'):
    copy(ind / name, A / 'closed_capture_035_independent_review_v1' / name)
copy(str(ind) + '.tar.gz', A / 'closed_capture_035_independent_review_v1/originals.tar.gz',
     '132e187c55ff2be0182de26e334ba0a3889b4a328d4283d21494fcabc0a40610')
copy('/tmp/mr3_p2a0_v25_root_final_close_observation_v1.json',
     A / 'closed_observation/root_final_close_observation_v1.json')
copy(__file__, A / 'closed_observation/root_closed_copy_v1.py')
out = {'schema': 'mr3-v25-root-closed-copy-v1', 'passed': True,
       'source_freeze': '579f7ad21d33c6de9351eb5308f155f0fc903fd7',
       'encoded_copies_verified': True, 'packet_files': 847,
       'selected_packet_bytes': h['selected_tree_bytes_including_manifests'],
       'part_count': part_count, 'copied_files': len(rows), 'files': rows,
       'scope': 'Lossless selected-byte copy only. Original V25 FAIL and later SKIP retained. No native/formal rerun.'}
(A / 'closed_observation/root_closed_copy_receipt_v1.json').write_text(
    json.dumps(out, indent=2) + '\n')
print(json.dumps({k: v for k, v in out.items() if k != 'files'}))
