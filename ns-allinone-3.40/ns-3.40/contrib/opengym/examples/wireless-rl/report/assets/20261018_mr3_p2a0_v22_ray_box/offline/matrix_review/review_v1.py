"""Read-only V22 final coordinator/plan identity and structure review."""
import ast
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
FINAL = Path('/tmp/mr3_p2a0_v22_matrix_proposal_v3')
OLD = Path('/tmp/mr3_p2a0_v22_matrix_proposal_v2')
BASE = Path('/tmp/mr3_p2a0_v20_matrix_draft_v2/independent')
OUT = Path(__file__).parent
INPUTS = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def status(path):
    value = path.stat()
    return dict(device=value.st_dev, inode=value.st_ino, size=value.st_size,
                mtime_ns=value.st_mtime_ns, ctime_ns=value.st_ctime_ns)


def read(path):
    path = Path(path).absolute()
    before = status(path)
    raw = path.read_bytes()
    assert status(path) == before, str(path)
    record = dict(path=str(path), bytes=len(raw), sha256=sha(raw), stat=before)
    assert str(path) not in INPUTS or INPUTS[str(path)] == record, str(path)
    INPUTS[str(path)] = record
    return raw


def js(path):
    return json.loads(read(path))


def tree(raw):
    return ast.parse(raw)


def dump(node):
    return ast.dump(node, include_attributes=False)


def method(parsed, name):
    return next(node for node in parsed.body if isinstance(node, ast.FunctionDef) and node.name == name)


def calls(parsed, name):
    return [node for node in ast.walk(parsed) if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name) and node.func.id == name]


def command_normalized(command):
    value = [part.replace('mr3_p2a0_20261018_v22_', 'mr3_p2a0_20261017_v17_') for part in command]
    for flag in ('--base-domain', '--base-port'):
        value[value.index(flag) + 1] = '<new isolation allocation>'
    return value


def main():
    began = time.monotonic()
    handoff = js(FINAL / 'handoff_v3.json')
    manifest = js(FINAL / 'manifest_v3.json')
    plan_raw = read(FINAL / 'predeclared_plan_v22.json')
    plan = json.loads(plan_raw)
    assert sha(plan_raw) == '5a14e14dd7183e36233add6ee9faf0b6b28604453d01608304fb78f162ada889'
    for row in handoff['files']:
        raw = read(row['source'])
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    assert handoff['source_writers_stopped'] is True
    assert plan['readiness']['status'] == 'ready' and plan['readiness']['pending_bindings'] == []
    assert plan['native_admission_granted'] is False
    assert plan['readiness']['native_admission_requires_clean_pushed_exact40_preflight'] is True
    prior_plan = js(W / 'report/assets/20261017_mr3_p2a0_v17/predeclared_plan_v17.json')
    hard_keys = ['robots_per_environment', 'max_api_records', 'max_submitted_script_decisions',
                 'max_total_wall_seconds', 'pilot_budget_unchanged', 'unchanged_gates',
                 'physical_response_criteria', 'angular_interface_criteria', 'angular_reset_criteria',
                 'settled_turn_criteria', 'full_execution_model_failfast', 'api_budget_breakdown']
    assert all(plan[key] == prior_plan[key] for key in hard_keys)
    assert (plan['max_api_records'], plan['max_submitted_script_decisions'],
            plan['max_total_wall_seconds']) == (608, 596, 18000)
    counts, stages = [], []
    for actual, old in zip(plan['stages'], prior_plan['stages']):
        assert actual['stage'] == old['stage']
        assert actual['wall_ceiling_seconds'] == old['wall_ceiling_seconds']
        assert command_normalized(actual['command']) == command_normalized(old['command'])
        actual_required = [value.replace('mr3_p2a0_v22_', 'mr3_p2a0_v17_')
                           for value in actual['required_audit_receipts']]
        assert actual_required == old['required_audit_receipts']
        counts.append(len(actual_required))
        command = actual['command']
        stages.append(dict(stage=actual['stage'], workers=command[command.index('--workers') + 1],
                           schedule=command[command.index('--schedule') + 1],
                           steps=command[command.index('--steps') + 1],
                           domain=command[command.index('--base-domain') + 1],
                           port=command[command.index('--base-port') + 1],
                           wall_ceiling_seconds=actual['wall_ceiling_seconds']))
    assert counts == [10, 7, 10, 7] and sum(counts) == 34
    bindings = {row['path']: row['sha256'] for row in plan['independent_source_bindings']}
    assert len(bindings) == len(plan['independent_source_bindings']) == 191
    baseline_path = ROOT / plan['historical_bindings_scope']['baseline_plan']
    baseline_raw = read(baseline_path)
    assert sha(baseline_raw) == plan['historical_bindings_scope']['baseline_plan_sha256']
    baseline = {row['path']: row['sha256'] for row in json.loads(baseline_raw)['independent_source_bindings']}
    assert len(baseline) == 173
    authorized = {row['path']: row for row in plan['historical_bindings_scope']['authorized_current_auditor_test_updates']}
    assert len(authorized) == 2
    assert all(bindings[path] == digest for path, digest in baseline.items() if path not in authorized)
    assert all(baseline[path] == row['before_sha256'] and bindings[path] == row['sha256']
               for path, row in authorized.items())
    new_rows = {row['path']: row for row in plan['historical_bindings_scope']['new_bindings']}
    assert set(new_rows) == set(bindings) - set(baseline) and len(new_rows) == 18
    prospective = {row['canonical']: Path(row['source']) for row in handoff['files']}
    for path, expected in bindings.items():
        source = prospective.get(path, ROOT / path)
        assert sha(read(source)) == expected, path
    names = ['mr3_p2a0_v22_buildproof_preflight.py', 'mr3_p2a0_v22_launch_stage.py',
             'mr3_p2a0_v22_audit_stage.py', 'mr3_p2a0_v22_run_matrix_v1.py',
             'mr3_p2a0_v22_cross_stage_mapping_monitor_v1.py',
             'mr3_v22_multiepoch_closure_binary_review_v1.py']
    trees, deltas = {}, {}
    for name in names:
        actual, old = read(FINAL / 'independent' / name), read(OLD / 'independent' / name)
        restored = actual.replace(b'mr3_v22_corrector_custody_v2.py', b'mr3_v22_corrector_custody_v1.py')
        assert restored == old, name
        deltas[name] = dict(sha256=sha(actual), bytes=len(actual),
                            v2_delta='Only custody module filename v1 to v2' if actual != old else 'Byte-identical')
        trees[name] = tree(actual)
    # Existing pre-V22 four-stage orchestration remains whole-AST identical.
    for name in ('mr3_p2a0_v22_audit_stage.py', 'mr3_p2a0_v22_run_matrix_v1.py'):
        old = read(BASE / name.replace('v22', 'v20')).decode()
        old = old.replace('20261018_mr3_p2a0_v20', '20261018_mr3_p2a0_v22_ray_box')
        old = old.replace('v20', 'v22').replace('V20', 'V22')
        assert dump(tree(old)) == dump(trees[name])
    preflight = trees['mr3_p2a0_v22_buildproof_preflight.py']
    pm = method(preflight, 'main')
    assert len(calls(pm, 'load_native_gates')) == 1
    gate_call = calls(pm, 'load_native_gates')[0]
    assert ast.unparse(gate_call) == 'load_native_gates(ROOT, freeze)'
    assert any(isinstance(node, ast.ImportFrom) and node.module == 'mr3_learning.audit_ppo'
               and any(alias.name == 'load_native_gates' for alias in node.names) for node in ast.walk(pm))
    assert any(isinstance(node, ast.Assert) and '@{u}' in ast.unparse(node) for node in ast.walk(pm))
    assert any(isinstance(node, ast.Assert) and 'source not clean' in ast.unparse(node) for node in ast.walk(pm))
    assert 'MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE' in ast.unparse(pm.body[0])
    lm = method(trees['mr3_p2a0_v22_launch_stage.py'], 'main')
    assert 'MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE' in ast.unparse(lm.body[0])
    # No original native-math consumer source is changed by this coordinator.
    physical_path = W / 'report/assets/20261017_mr3_p2a0_v17/independent/mr3_independent_physics_matrix_v17.py'
    physical = read(physical_path).decode()
    assert '2516e394f60eac5dd24fd66b51c4c48fc37245090eb1626ebe1c7a3a23f8bafb' in physical
    assert 'len(report["episodes"]) == 8' in physical
    assert 'event.get("observed_nonrest_beyond_horizon") is True' in physical
    assert 'eligible response violated stop bound' in physical
    assert 'if not row["A"] and not row["B"]:' in physical
    assert 'no meaningful A or B stop across the complete reset matrix' in physical
    helper = read(FINAL / 'independent/mr3_v22_corrector_custody_v2.py').decode()
    assert sha(helper.encode()) == '862e5b9aa674258975b5ac913d61125bc4b97d036cd6dec08d6296037619386d'
    helper_old = read(OLD / 'independent/mr3_v22_corrector_custody_v1.py').decode()
    old_tree, helper_tree = tree(helper_old), tree(helper)
    old_methods = {node.name: node for node in old_tree.body if isinstance(node, ast.FunctionDef)}
    new_methods = {node.name: node for node in helper_tree.body if isinstance(node, ast.FunctionDef)}
    changed = [name for name in old_methods if dump(old_methods[name]) != dump(new_methods[name])]
    assert changed == ['observe']
    for literal in ('owned gzserver changed before maps read', 'owned gzserver changed during maps read',
                    'same owned gzserver became zombie after maps read; no mapping credit',
                    'owned gzserver disappeared after maps read; no mapping credit',
                    'worker argv does not identify this episode', 'mapped corrector proof borrowed a different actual worker/episode',
                    'actual corrected gzserver missing from owned shutdown identities'):
        assert literal in helper
    checks = js(FINAL / 'final_checks_v4.json')
    assert checks['passed'] is True
    draft = read(FINAL / 'plan_draft_before_source_ready_v3.json')
    assert sha(draft) == checks['plan_sha256']
    pre_ready = json.loads(draft)
    ready_delta = [key for key in plan if plan[key] != pre_ready.get(key)]
    assert set(ready_delta) == {'readiness', 'v22_preparation', 'conditional_engineering_matrix_authorized', 'actual_native_admission_requires'}
    assert plan['independent_source_bindings'] == pre_ready['independent_source_bindings']
    for path, record in INPUTS.items():
        assert status(Path(path)) == record['stat'] and sha(Path(path).read_bytes()) == record['sha256']
    result = dict(schema='mr3-v22-matrix-coordinators-independent-review-v1', passed=True, blockers=[],
                  plan_sha256=sha(plan_raw), source_manifest_sha256=sha(read(FINAL / 'manifest_v3.json')),
                  source_handoff_sha256=sha(read(FINAL / 'handoff_v3.json')),
                  original_mandatory_receipts=counts, original_total_mandatory=34,
                  hard_gate_fields_exact_to_frozen_A17=hard_keys,
                  budgets=dict(api=608, script_decisions=596, native_wall_seconds=18000), stages=stages,
                  binding_counts=dict(old_baseline=173, old_unchanged=171, authorized_current=2, appended=18, actual_unique=191),
                  all_binding_sha_checked=True, six_coordinator_v2_to_v3_deltas=deltas,
                  audit_and_parent_whole_ast_mechanical_equal_to_prior_draft=True,
                  shared_loader_actual_call='preflight main imports current mr3_learning.audit_ppo.load_native_gates and calls (ROOT, actual clean pushed HEAD)',
                  reset_semantics='Exactly8 EP32, retained raw per-episode physical report, mandatory unchanged A17 pooled per-robot A OR B; every eligible bound/nonrest/raw/closure failure remains fatal; all8 input leaves and per-EP FIFO independently checked.',
                  lifecycle='Parent waits finite launch then audit, actual verdict requires every formal hash/PASS. Failed launch still gets formal diagnosis once. All submitted audit futures drain; no later-stage retry. Watcher naturally stops on stage failure/parent skip/all stages closed; original /proc helper timeout applies only to owned read-only subprocess, never native.',
                  pid_start_helper_custody='Original immutable A13 monitor and Shim source/binding retained; new live supplement binds exact system-Python worker argv/run-dir, PID/start/ancestry, corrector+ODE actual inode/device maps, config epoch/PID/source3. Closed supplement rereads all proofs and requires exact shutdown identity; no fixed identity count.',
                  closing_race_delta='Only helper observe changed: file/ELF errors checked first; same-identity Z/disappearance pending with no credit; PID reuse mismatch still fatal. No closed ledger, compiled source, parameter or original math relaxation.',
                  final_ready_metadata_after_cpu=dict(cpu_checked_plan_sha256=checks['plan_sha256'], final_plan_sha256=sha(plan_raw),
                                                      only_changed_top_fields=ready_delta, bindings_and_code_unchanged=True),
                  native_admission_granted=False,
                  scope='Read-only source/AST/bindings/plan review. No unit, math, SDK, DDS/ROS, compiler, native or formal runs. Actual exact40 runtime source preflight and every native/formal result remain future requirements.',
                  all_input_final_sha_stat_stable=True, inputs=list(INPUTS.values()),
                  argv=sys.argv, executable=sys.executable, cwd=os.getcwd(), wall_seconds=time.monotonic()-began)
    path = OUT / 'review_v1.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(passed=True, path=str(path), sha256=sha(path.read_bytes()),
                          inputs=len(INPUTS), wall_seconds=result['wall_seconds'])))


if __name__ == '__main__':
    main()
