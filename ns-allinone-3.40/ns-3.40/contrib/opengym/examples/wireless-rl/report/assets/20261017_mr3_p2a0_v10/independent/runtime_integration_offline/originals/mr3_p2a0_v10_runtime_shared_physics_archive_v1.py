"""Supplementary custody; previous runtime_offline inventory is immutable."""
import gzip
import hashlib
import json
from pathlib import Path

BASE = Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent')
DEST = BASE / 'runtime_integration_offline'
DEST.mkdir(exist_ok=False)
prior = BASE / 'runtime_offline/originals_manifest_v1.json'
assert hashlib.sha256(prior.read_bytes()).hexdigest() == '32613f9f143b05ea93e2f7374de21fc3ad398961b4abea4a48b18aa9db0cbc64'
entries = []

def save(source, relative):
    raw = source.read_bytes()
    compressed = source.suffix == '.log'
    encoded = gzip.compress(raw, mtime=0) if compressed else raw
    destination = DEST / (str(relative) + ('.gz' if compressed else ''))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        stream.write(encoded)
    stored = destination.read_bytes()
    decoded = gzip.decompress(stored) if compressed else stored
    assert decoded == raw and source.read_bytes() == raw
    entries.append({'source': str(source), 'artifact': str(destination.relative_to(DEST)),
                    'encoding': 'gzip' if compressed else 'identity', 'raw_bytes': len(raw),
                    'raw_sha256': hashlib.sha256(raw).hexdigest(),
                    'encoded_bytes': len(encoded),
                    'encoded_sha256': hashlib.sha256(encoded).hexdigest(),
                    'decoded_sha256': hashlib.sha256(decoded).hexdigest()})

for source in sorted(Path('/tmp').glob('mr3_p2a0_v10_runtime_shared_physics_*')):
    if source.is_file() and source.suffix != '.pyc':
        save(source, Path('originals') / source.name)
for directory, relative in [
        (Path('/tmp/mr3_p2a0_v10_shared_physics_before_v1'), 'before_sources'),
        (Path('/tmp/mr3_p2a0_v10_runtime_shared_physics_final_sources_v1'), 'final_sources')]:
    for source in sorted(directory.rglob('*')):
        if source.is_file() and source.suffix != '.pyc':
            save(source, Path(relative) / source.relative_to(directory))
manifest = {'schema': 'mr3-offline-originals-custody-v1', 'passed': True,
            'scope': 'Shared engineering/PPO physics audit integration only; no native/GPU/training',
            'prior_runtime_manifest_unchanged_sha256': hashlib.sha256(prior.read_bytes()).hexdigest(),
            'check_results': {'focused_01': '21 PASS', 'style_01': '4 style errors retained',
                             'focused_02': '21 PASS', 'style_02': 'PASS',
                             'focused_03': '22 PASS', 'style_03': 'PASS', 'AST_static_v1': 'PASS'},
            'source_history': 'Exact pre-extraction four files and final six files retained. Intermediate initial-style-failure source bytes were not separately saved; its original commands, stdout and receipt remain. Final snapshots are not attributed to earlier iterations.',
            'new_test_coverage': '5 tests: stdlib/no-cycle/re-export; episode-entry unchanged math/capacity/legacy/unknown; actual PPO call AST plus full consumer and W7 physics with finally success/error restoration; original tick math rejection; new learner Git/worktree source binding rejection.',
            'frozen_helper_claim': 'Synthetic fixtures inject only the actual pure helper at the frozen-source loader seam; no claim of committed synthetic source identity.',
            'entries': entries}
output = DEST / 'originals_manifest_v1.json'
output.write_text(json.dumps(manifest, indent=2) + '\n')
for item in entries:
    raw = (DEST / item['artifact']).read_bytes()
    decoded = gzip.decompress(raw) if item['encoding'] == 'gzip' else raw
    assert hashlib.sha256(raw).hexdigest() == item['encoded_sha256']
    assert hashlib.sha256(decoded).hexdigest() == item['raw_sha256'] == item['decoded_sha256']
print(json.dumps({'passed': True, 'manifest': str(output),
                  'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                  'files': len(entries), 'raw_bytes': sum(item['raw_bytes'] for item in entries),
                  'encoded_bytes': sum(item['encoded_bytes'] for item in entries)}))
