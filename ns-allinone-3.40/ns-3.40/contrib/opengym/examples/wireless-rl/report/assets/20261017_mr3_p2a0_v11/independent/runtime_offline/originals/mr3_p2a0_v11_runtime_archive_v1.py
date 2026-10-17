"""Lossless V11 runtime fix offline custody; original V10 outcomes untouched."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
DEST = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/independent/runtime_offline'
DEST.mkdir(parents=True, exist_ok=False)
entries = []

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def save(source, relative):
    raw = source.read_bytes()
    compressed = source.suffix == '.log'
    encoded = gzip.compress(raw, mtime=0) if compressed else raw
    target = DEST / (str(relative) + ('.gz' if compressed else ''))
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as output:
        output.write(encoded)
    stored = target.read_bytes()
    decoded = gzip.decompress(stored) if compressed else stored
    assert decoded == raw and source.read_bytes() == raw
    entries.append({'source': str(source), 'artifact': str(target.relative_to(DEST)),
                    'encoding': 'gzip' if compressed else 'identity',
                    'raw_bytes': len(raw), 'raw_sha256': sha(raw),
                    'encoded_bytes': len(encoded), 'encoded_sha256': sha(encoded),
                    'decoded_sha256': sha(decoded)})

for source in sorted(Path('/tmp').glob('mr3_p2a0_v11_runtime_*')):
    if source.is_file() and source.suffix != '.pyc':
        save(source, Path('originals') / source.name)
for source in [Path('/tmp/mr3_p2a0_v11_control_wrapper_runtime_review_v1.json')]:
    save(source, Path('originals') / source.name)
for path, folder in [('/tmp/mr3_p2a0_v11_runtime_v10_source_baseline_v1', 'frozen_v10_sources'),
                     ('/tmp/mr3_p2a0_v11_runtime_final_sources_v1', 'final_sources')]:
    base = Path(path)
    for source in sorted(base.rglob('*')):
        if source.is_file() and source.suffix != '.pyc':
            save(source, Path(folder) / source.relative_to(base))
result = {'schema': 'mr3-offline-originals-custody-v1', 'passed': True,
          'scope': 'Minimal peer ACK QoS and pre-release adapter closure CPU fixes; no simulator or training',
          'archive_command': ['/usr/bin/python3', '/tmp/mr3_p2a0_v11_runtime_archive_v1.py'],
          'previous_failed_freeze': '631d8c35c43fdb7ed45e984376543e55395066ef',
          'initial_red': '7 FAIL/1 PASS retained: 2 actual production defects plus5 test assertions incorrectly treating declared default-liveliness WARNING as ERROR. Corrected tests require native graph-resolved OK for5 pairs and real delivery on3 ACK channels.',
          'final_cpu': '67 PASS (6 actual-code endpoint QoS/delivery +61 complete adapter tests), style/diff PASS; source before/after equal',
          'history_limit': 'Initial QoS test SHA retained in red receipt but intermediate bytes were not saved. Final test bytes are not attributed to red. The three old tracked files are exact frozen V10 Git objects; the new QoS test did not exist at that freeze.',
          'new_native_credit': False, 'entries': entries}
output = DEST / 'originals_manifest_v1.json'
output.write_text(json.dumps(result, indent=2) + '\n')
for entry in entries:
    stored = (DEST / entry['artifact']).read_bytes()
    decoded = gzip.decompress(stored) if entry['encoding'] == 'gzip' else stored
    assert sha(stored) == entry['encoded_sha256']
    assert sha(decoded) == entry['decoded_sha256'] == entry['raw_sha256']
print(json.dumps({'passed': True, 'manifest': str(output), 'sha256': sha(output.read_bytes()),
                  'files': len(entries), 'raw_bytes': sum(e['raw_bytes'] for e in entries),
                  'encoded_bytes': sum(e['encoded_bytes'] for e in entries)}))
