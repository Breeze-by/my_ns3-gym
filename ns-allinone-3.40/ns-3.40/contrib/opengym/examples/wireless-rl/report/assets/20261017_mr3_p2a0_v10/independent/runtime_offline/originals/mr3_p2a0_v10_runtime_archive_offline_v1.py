"""Lossless custody of V10 runtime-agent offline originals, no evidence rewriting."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
DEST = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/runtime_offline'
DEST.mkdir(parents=True, exist_ok=True)
entries = []

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def archive(source, relative):
    raw = source.read_bytes()
    compress = source.suffix in ('.log', '.txt')
    encoded = gzip.compress(raw, mtime=0) if compress else raw
    target = DEST / (str(relative) + ('.gz' if compress else ''))
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.read_bytes() != encoded:
            raise ValueError('refusing to overwrite differing canonical bytes: ' + str(target))
    else:
        with target.open('xb') as stream:
            stream.write(encoded)
    saved = target.read_bytes()
    decoded = gzip.decompress(saved) if compress else saved
    if decoded != raw or saved != encoded or source.read_bytes() != raw:
        raise ValueError('custody mismatch: ' + str(source))
    entries.append({'source': str(source), 'artifact': str(target.relative_to(DEST)),
                    'encoding': 'gzip' if compress else 'identity',
                    'raw_bytes': len(raw), 'raw_sha256': sha(raw),
                    'encoded_bytes': len(encoded), 'encoded_sha256': sha(encoded),
                    'decoded_sha256': sha(decoded), 'source_rechecked': True})

sources = sorted(p for p in Path('/tmp').glob('mr3_p2a0_v10_runtime*')
                 if p.is_file() and p.suffix != '.pyc')
for source in sources:
    archive(source, Path('originals') / source.name)
fixture = Path('/tmp/mr3_p2a0_v10_runtime_bootstrap_fixture_v1')
assert fixture.is_dir()
for source in sorted(fixture.rglob('*')):
    if source.is_file() and source.suffix != '.pyc':
        archive(source, Path('final_synthetic_bootstrap') / source.relative_to(fixture))
final = json.loads(Path('/tmp/mr3_p2a0_v10_runtime_source_final_v2.json').read_text())
for relative, expected in final['bindings'].items():
    source = ROOT / relative
    if sha(source.read_bytes()) != expected['sha256']:
        raise ValueError('source changed after final handoff: ' + relative)
    archive(source, Path('final_sources') / relative)
manifest = {
 'schema': 'mr3-offline-originals-custody-v1', 'passed': True,
 'scope': 'V10 runtime worker/control/evaluator and conda engineering audits; no native/training credit',
 'original_check_results_unmodified': True,
 'historical_source_availability': {
   'final_snapshot': 'final_sources contains only source bytes from runtime_source_final_v2',
   'earlier_iterations': 'Earlier check commands, stdout, and receipts retained; full earlier source bytes were not separately snapshotted and are unavailable. Final source bytes must not be attributed to prior checks.',
   'initial_receipt_encoding': 'Original focused_05, motion_audit_focused_03, style_04 JSON with literal backslash-n trailer are retained byte-exact alongside explicit encoding_corrected_v1 receipts; originals are not replaced.',
   'fixture_history': 'Temporary per-test directories were removed by unittest context managers. final_synthetic_bootstrap is a separately declared post-check export from final test source, not a reconstruction of earlier failed fixtures.'},
 'source_snapshot': '/tmp/mr3_p2a0_v10_runtime_source_final_v2.json',
 'entries': entries}
manifest_path = DEST / 'originals_manifest_v1.json'
raw = (json.dumps(manifest, indent=2) + '\n').encode()
if manifest_path.exists():
    if manifest_path.read_bytes() != raw:
        raise ValueError('manifest already exists with different bytes')
else:
    manifest_path.write_bytes(raw)
for entry in entries:
    stored = (DEST / entry['artifact']).read_bytes()
    decoded = gzip.decompress(stored) if entry['encoding'] == 'gzip' else stored
    assert sha(stored) == entry['encoded_sha256']
    assert sha(decoded) == entry['decoded_sha256'] == entry['raw_sha256']
print(json.dumps({'passed': True, 'manifest': str(manifest_path),
                  'sha256': sha(raw), 'files': len(entries),
                  'raw_bytes': sum(item['raw_bytes'] for item in entries),
                  'encoded_bytes': sum(item['encoded_bytes'] for item in entries)}))
