"""Static archive, credit, fee and documentation checks; no experiment replay."""
import ast
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

A = Path(__file__).resolve().parent
W = A.parents[2]
ROOT = W.parents[5]
FREEZE = '1dc2a1f601693f542479f9b6b7c54c69519b5460'
def read(path):
    return json.loads(path.read_text())
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

manifest = read(A / 'archive_manifest_v1.json')
verification = read(A / 'archive_verification_v1.json')
archive = hashlib.sha256()
for part in manifest['parts']:
    path = A / part['path']
    assert path.stat().st_size == part['bytes'] and sha(path) == part['sha256']
    archive.update(path.read_bytes())
assert archive.hexdigest() == manifest['archive_sha256'] == verification['archive_sha256']
assert verification['byte_verification_passed'] and verification['run_originals_unchanged']
for item in manifest['metadata']:
    assert sha(A / item['path']) == item['sha256']
inventory = read(A / 'run_inventory_v1.json')
run = Path(inventory['original_root'])
for name, record in inventory['files'].items():
    path = run / name
    assert path.is_file() and not path.is_symlink()
    assert sha(path) == record['sha256'] and path.stat().st_size == record['bytes']
assert len(inventory['files']) == verification['run_file_count'] == 323
for record in read(A / 'auxiliary_copy_index_v1.json')['files']:
    assert sha(A / record['copy']) == sha(Path(record['original'])) == record['sha256']
aux = A / 'closed_execution/aux'
assert not read(aux / 'activity_result.json')['passed']
assert read(aux / 'conformity.json')['passed'] and read(aux / 'conformity_independent.json')['passed']
formal = read(aux / 'independent_audit.json')
assert not formal['passed'] and formal['step_attempts'] == formal['step_returns'] == 284
assert formal['episodes'][0]['errors'] == ['transition physical/reward time differs']
assert len(formal['episodes'][0]['actor_records']) == 4
assert formal['uniform_actions_independently_replayed'] == 284  # preserved wrong original claim
forensic = read(aux / 'mr3_proxy2d_v22_forensics_v1.json')
assert forensic['formal_claim_is_not_full_trace_validation'] and len(forensic['strict_duration_failures']) == 2
assert forensic['all_attempts_within_group_and_collection']
assert forensic['all_physical_clock_deltas_exactly_1e9ns'] and forensic['all_reward_dt_exactly_one']
ledger = read(A / 'engineering_accounting_v1.json')
assert ledger['charge_seconds'] == '1781.490347088'
assert Decimal(ledger['cumulative_used_seconds']) + Decimal(ledger['remaining_seconds']) == Decimal(52000)
assert Decimal(ledger['entry_used_seconds']) + Decimal(ledger['charge_seconds']) == Decimal(ledger['cumulative_used_seconds'])
assert read(A / 'saved_process_absence_v1.json')['saved_identity_count'] == 17
assert read(A / 'saved_process_absence_v1.json')['passed']
changed = []
for name, digest in read(A / 'predeclared_plan_v1.json')['source_bindings'].items():
    frozen = subprocess.check_output(['git', 'show', FREEZE + ':' + name], cwd=ROOT)
    assert hashlib.sha256(frozen).hexdigest() == digest
    if sha(ROOT / name) != digest:
        changed.append(name)
assert {Path(name).name for name in changed} == {'audit_proxy2d.py', 'mr3_proxy2d_worker.py'}
for case in ('worker_integer_clock_cpu_v2', 'audit_verified_prefix_cpu_v1'):
    receipt = read(A / 'checks' / case / 'actual_wait.json')
    if receipt['schema'] == 'mr3-reach-outer-actual-wait-v1':
        assert receipt['scope'] == 'cpu' and receipt['actual_returncode'] == 0 and receipt['source_unchanged']
        for source in receipt['source_after']:
            assert sha(Path(source['path'])) == source['sha256']
    else:
        assert receipt['schema'] == 'mr3-proxy2d-pure-fixture-cpu-actual-wait-v1'
        assert receipt['returncode'] == 0 and receipt['source_bytes_unchanged'] and receipt['actual_waited']
        for name, digest in receipt['source_sha256'].items():
            assert sha(ROOT / name) == digest
names = subprocess.check_output(['git', 'diff', '--name-only'], cwd=ROOT, text=True).splitlines()
links = 0
for name in names:
    path = ROOT / name
    if path.suffix == '.py':
        ast.parse(path.read_text())
    if path.suffix != '.md':
        continue
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        target = target.strip('<>').split('#', 1)[0]
        if not target or '://' in target or target.startswith('mailto:'):
            continue
        if ':' in target and target.rsplit(':', 1)[-1].isdigit():
            target = target.rsplit(':', 1)[0]
        assert (path.parent / target).exists(), (name, target)
        links += 1
prior = subprocess.check_output(['git', 'show', FREEZE + ':' + str((W / 'log.md').relative_to(ROOT))], cwd=ROOT)
assert (W / 'log.md').read_bytes().startswith(prior)
result = {'passed': True, 'scope': 'static archive/credit/fee/link checks only; no world or formal reader replay',
          'original_fail_preserved': True, 'archive_files': 323, 'relative_links': links,
          'post_activity_source_changes': changed, 'qualification': False}
with (A / 'closed_static_result_v1.json').open('x') as stream:
    stream.write(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
