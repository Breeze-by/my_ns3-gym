"""Static AST/hash only; no candidate import or active/native input/proc read."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).parent
OLD = Path('/tmp/mr3_p2a_single_ep_runtime_profile_candidate')
preserved = json.loads((OUT / 'v1_preservation_manifest.json').read_text())
for row in preserved['sources']:
    raw = Path(row['path']).read_bytes()
    if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise ValueError('V1 original changed: ' + row['path'])
rows = []
for name in ('profile_common_v1.py', 'runtime_child_v1.py', 'profile_guard_v2.py'):
    path = OUT / name
    raw = path.read_bytes()
    ast.parse(raw, filename=str(path))
    rows.append(dict(candidate_path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                     syntax_AST_parsed=True, imported_or_executed=False))
for name in ('profile_common_v1.py', 'runtime_child_v1.py'):
    if (OUT / name).read_bytes() != (OLD / name).read_bytes():
        raise ValueError('unexpected change outside parent guard: ' + name)
before, after = (OLD / 'profile_guard_v1.py').read_text(), (OUT / 'profile_guard_v2.py').read_text()
(OUT / 'guard_v1_to_v2.diff').write_text(''.join(difflib.unified_diff(before.splitlines(keepends=True),
    after.splitlines(keepends=True), fromfile=str(OLD / 'profile_guard_v1.py'),
    tofile=str(OUT / 'profile_guard_v2.py'))))
scope = json.loads((OUT / 'scope_TEMPLATE_NOT_ADMITTED.json').read_text())
scope['execution_sources'] = [dict(path='REPLACE_WITH_NEW_CANONICAL_REPORT_PACKAGE/' + Path(row['candidate_path']).name,
    bytes=row['bytes'], sha256=row['sha256']) for row in rows]
(OUT / 'scope_TEMPLATE_NOT_ADMITTED.json').write_text(json.dumps(scope, indent=2) + '\n')
old_inventory = json.loads((OLD / 'static_source_inventory_v1.json').read_text())
(OUT / 'static_source_inventory_v2.json').write_text(json.dumps(dict(
    schema='mr3-single-ep-runtime-profile-static-inventory-v2',
    evidence_freeze=old_inventory['evidence_freeze'], candidate_sources=rows,
    evidence_sources=old_inventory['evidence_sources'], evidence_source_verification_repeated=False,
    evidence_source_proof_origin=str(OLD / 'static_source_inventory_v1.json'),
    v1_all_original_hashes_preserved=True, common_and_child_byte_identical_to_v1=True,
    reviewed_v1_blocker='guard_final_cleanup_can_be_interrupted_before_actual_reap',
    v2_fix='Parent TERM/INT only records. Main polls for stop; cleanup defers signals, retries wait exceptions, and cannot finish without an actual integer child.wait return.',
    runtime_inputs_read=False, proc_read=False, candidate_or_reader_imported_or_executed=False,
    tests_run=False, execution_source_seal_pending=True, native_or_training_credit=False), indent=2) + '\n')

