"""Lossless selected offline originals only; never copy the V11 runtime payloads."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
TARGET = ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
                 'report/assets/20261017_mr3_p2a0_v12/independent/runtime_offline')
TEMP = Path('/tmp')
sha = lambda data: hashlib.sha256(data).hexdigest()
originals = set()
for entry in TEMP.glob('mr3_p2a0_v12_readiness*'):
    if entry.is_file():
        originals.add(entry)
    elif entry.is_dir():
        originals.update(path for path in entry.rglob('*')
                         if path.is_file() and path.suffix != '.pyc')
originals.add(TEMP / 'mr3_p2a0_v12_controlled_readiness_design_v1.json')
TARGET.mkdir(parents=True, exist_ok=True)
entries = []
for source in sorted(originals):
    raw = source.read_bytes()
    compress = source.suffix == '.log'
    relative = Path('originals') / source.relative_to(TEMP)
    if compress:
        relative = Path(str(relative) + '.gz')
    encoded = gzip.compress(raw, mtime=0) if compress else raw
    destination = TARGET / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        assert destination.read_bytes() == encoded, str(destination)
    else:
        with destination.open('xb') as stream:
            stream.write(encoded)
    selected = destination.read_bytes()
    decoded = gzip.decompress(selected) if compress else selected
    assert raw == decoded and source.read_bytes() == raw
    entries.append({'source': str(source), 'selected': str(relative),
                    'compression': 'gzip-mtime0' if compress else 'none',
                    'raw_bytes': len(raw), 'encoded_bytes': len(selected),
                    'raw_sha256': sha(raw), 'encoded_sha256': sha(selected),
                    'decoded_sha256': sha(decoded)})
manifest = {'schema': 'mr3-offline-originals-manifest-v1', 'passed': True,
            'scope': 'V12 working-readiness CPU/compatibility originals only; V11 formal FAIL '
                     'and native payloads remain in their original canonical archive',
            'entries': entries,
            'counts': {'originals': len(entries), 'raw_bytes': sum(e['raw_bytes'] for e in entries),
                       'encoded_bytes': sum(e['encoded_bytes'] for e in entries)},
            'verification': 'Every selected encoded byte, decoded original byte and still-existing '
                            '/tmp source byte was SHA256 checked; no raw native payload copied.'}
payload = (json.dumps(manifest, indent=2) + '\n').encode()
path = TARGET / 'originals_manifest_v1.json'
if path.exists():
    assert path.read_bytes() == payload
else:
    path.write_bytes(payload)
for entry in entries:
    selected = (TARGET / entry['selected']).read_bytes()
    decoded = gzip.decompress(selected) if entry['compression'].startswith('gzip') else selected
    assert sha(selected) == entry['encoded_sha256']
    assert sha(decoded) == entry['decoded_sha256'] == entry['raw_sha256']
receipt = {'passed': True, 'manifest': str(path), 'manifest_sha256': sha(payload),
           **manifest['counts'], 'all_source_selected_decoded_bytes_verified': True}
Path('/tmp/mr3_p2a0_v12_runtime_archive_receipt_v1.json').write_text(
    json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
