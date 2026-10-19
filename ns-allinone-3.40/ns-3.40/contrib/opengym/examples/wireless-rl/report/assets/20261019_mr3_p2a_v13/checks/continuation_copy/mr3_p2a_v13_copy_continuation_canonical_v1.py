from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path('/home/zhuyulab/ns3-workspace')
ASSETS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v13'
PACKET = Path('/tmp/mr3_p2a_v13_continuation_closed_packet_attempt_v1')
rows = []

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1 << 20), b''):
            h.update(part)
    return h.hexdigest()

def copy(source, relative, *, expected=None, scope):
    source = Path(source)
    assert source.is_file() and not source.is_symlink(), str(source)
    before = source.stat()
    digest = sha(source)
    if expected:
        assert before.st_size == expected['bytes'], str(source)
        assert digest == expected['sha256'], str(source)
    dest = ASSETS / relative
    assert not dest.exists(), str(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, dest)
    assert dest.stat().st_size == before.st_size and sha(dest) == digest
    after = source.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino)
    rows.append({'source': str(source), 'canonical': str(dest.relative_to(ROOT)), 'bytes': before.st_size,
                 'sha256': digest, 'scope': scope})

for p in sorted(PACKET.rglob('*')):
    if p.is_file():
        copy(p, Path('closed_continuation') / p.relative_to(PACKET), scope='Full closed byte packet including all seven parts and complete external checks tree')
assert len(rows) == 24

selection = json.loads(Path('/tmp/mr3_p2a_v13_continuation_closed_selection_v1.json').read_text())
manifest = json.loads((PACKET / 'manifest.json').read_text())
members = {x['original_path']: x for x in manifest['files']}
for row in selection['files']:
    if row['group'] == 'external_actual_closed':
        p = Path(row['path'])
        copy(p, Path('continuation_receipts') / p.name, expected=members[str(p)],
             scope='Byte-identical small review copy; authoritative original is also SHA-bound inside closed_continuation packet')

copy('/tmp/mr3_p2a_v13_runtime_restore_main_actual_tool_v1.json',
     Path('continuation_receipts/mr3_p2a_v13_runtime_restore_main_actual_tool_v1.json'),
     scope='Actual checkout restore after the archive source-stability boundary')

forensic_list = Path('/tmp/mr3_p2a_v13_minimum_forensic_small_packet_sources_v1.json')
forensic = json.loads(forensic_list.read_text())
for row in forensic['small_artifacts']:
    p = Path(row['path'])
    group = 'official_source_snapshots' if p.parent.name == 'mr3_p2a0_v13_stop_point_review_v1' else 'originals'
    copy(p, Path('closed_minimum_forensics') / group / p.name, expected=row,
         scope='Closed read-only CPU diagnosis or its immutable source/draft provenance; no new science consumer')
copy(forensic_list, Path('closed_minimum_forensics/mr3_p2a_v13_minimum_forensic_small_packet_sources_v1.json'),
     scope='Exact small artifact selection and large raw/source SHA references')

for name, digest in [
    ('mr3_p2a_v13_prospective_safety_contract_review_v1.md', '3e3c96aa61baf4a66f5817225346ce4f0ef9bc1cb4e44c4fde004bad2868a0b3'),
    ('mr3_p2a_v13_prospective_safety_contract_review_v1.index.json', '71f854c73ba26806d213356bf8042c1eb4359e7e690e1b676fd2ba7144517f10'),
]:
    p = Path('/tmp') / name
    copy(p, Path('contract_review_only') / name, expected={'bytes': p.stat().st_size, 'sha256': digest},
         scope='Prospective math review only; no production contract change or new native authorization')

for name in ['mr3_p2a_v13_root_manifest_display_control_error_v1.json', 'mr3_p2a_v13_copy_continuation_canonical_v1.py']:
    copy(Path('/tmp') / name, Path('checks/continuation_copy') / name,
         scope='Canonical copy CPU control provenance; not a scientific run')

index = {'schema': 'mr3-v13-continuation-canonical-copy-index-v1',
         'runtime_freeze': '0063aa233ba3008ddcc1eb09ea8068112eea3965',
         'scope': 'Byte-identical copies only after all native/scientific/archival scopes closed. No native rerun, scientific consumer, training or contract change.',
         'packet_manifest_sha256': sha(PACKET / 'manifest.json'),
         'copied_files': len(rows), 'copied_bytes': sum(r['bytes'] for r in rows), 'files': rows}
out = ASSETS / 'continuation_canonical_copy_index_v1.json'
assert not out.exists()
out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'copied_files': len(rows), 'copied_bytes': index['copied_bytes'], 'index': str(out), 'sha256': sha(out)}))
