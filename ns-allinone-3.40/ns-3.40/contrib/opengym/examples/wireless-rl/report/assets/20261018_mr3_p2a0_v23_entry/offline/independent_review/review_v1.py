"""Static closed-evidence/interpreter review, not a new dependency or native probe."""
import ast
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
P = Path('/tmp/mr3_p2a0_v23_entry_proposal_v1')
OLD = W / 'report/assets/20261018_mr3_p2a0_v22_ray_box'
OUT = Path(__file__).parent
LEARNER = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
INPUTS = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stat(path):
    value = path.stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def read(path):
    path = Path(path).absolute()
    before = stat(path)
    raw = path.read_bytes()
    assert stat(path) == before
    row = dict(path=str(path), sha256=sha(raw), bytes=len(raw), stat=before)
    assert str(path) not in INPUTS or INPUTS[str(path)] == row
    INPUTS[str(path)] = row
    return raw


def js(path):
    return json.loads(read(path))


def dump(node):
    return ast.dump(node, include_attributes=False)


def methods(raw):
    return {node.name: node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef)}


began = time.monotonic()
plan_raw = read(P / 'predeclared_plan_v23.json')
plan = json.loads(plan_raw)
assert sha(plan_raw) == '28b190af13c408f5ed0da243ccf4b3d25e4460a8f14b60d9af295cf5015cae07'
old = js(OLD / 'predeclared_plan_v22.json')
old_pins = {row['path']: row['sha256'] for row in old['independent_source_bindings']}
pins = {row['path']: row['sha256'] for row in plan['independent_source_bindings']}
assert len(old_pins) == 191 and len(pins) == len(plan['independent_source_bindings']) == 198
assert all(pins[path] == value for path, value in old_pins.items())
new_paths = set(pins) - set(old_pins)
assert len(new_paths) == 7
new_sha = {}
for path, expected in pins.items():
    source = P / 'independent' / Path(path).name if path in new_paths else ROOT / path
    assert sha(read(source)) == expected, path
    if path in new_paths:
        new_sha[Path(path).name] = expected
hard = ['robots_per_environment', 'max_api_records', 'max_submitted_script_decisions',
        'max_total_wall_seconds', 'pilot_budget_unchanged', 'unchanged_gates',
        'physical_response_criteria', 'angular_interface_criteria', 'angular_reset_criteria',
        'settled_turn_criteria', 'full_execution_model_failfast', 'api_budget_breakdown']
assert all(plan[key] == old[key] for key in hard)
assert plan['max_total_wall_seconds'] == 18000
assert plan['prior_entry_cost']['wall_seconds'] == 0.24578428314998746
assert 18000 - plan['prior_entry_cost']['wall_seconds'] == 17999.75421571685
assert plan['native_admission_granted'] is False
counts, command_roles = [], []
for current, prior in zip(plan['stages'], old['stages']):
    assert current['stage'] == prior['stage']
    assert current['command'][0] == LEARNER
    command_roles.append(dict(stage=current['stage'], benchmark_interpreter=current['command'][0]))
    assert [value.replace('mr3_p2a0_v23_', 'mr3_p2a0_v22_') for value in current['required_audit_receipts']] == prior['required_audit_receipts']
    assert current['wall_ceiling_seconds'] == prior['wall_ceiling_seconds']
    counts.append(len(current['required_audit_receipts']))
assert counts == [10, 7, 10, 7]
raws = {path.name: read(path).decode() for path in (P / 'independent').glob('*.py')}
launch = raws['mr3_p2a0_v23_launch_stage.py']
audit = raws['mr3_p2a0_v23_audit_stage.py']
preflight = raws['mr3_p2a0_v23_buildproof_preflight.py']
parent = raws['mr3_p2a0_v23_run_matrix_v1.py']
watcher = raws['mr3_p2a0_v23_cross_stage_mapping_monitor_v1.py']
closure = raws['mr3_v23_multiepoch_closure_binary_review_v1.py']
assert 'command = [str(LEARNER_PYTHON), "-u", *specification["command"][1:]]' in launch
assert '[str(LEARNER_PYTHON), \'-m\', \'mr3_learning.audit_preparation\'' in audit
assert 'assert specification["command"][0] == str(LEARNER_PYTHON)' in launch
assert 'Path(sys.executable).resolve(strict=True) == LEARNER_PYTHON.resolve(strict=True)' in preflight
assert 'from mr3_learning.audit_ppo import load_native_gates' in preflight
assert 'load_native_gates(ROOT, freeze)' in preflight
assert "command = [sys.executable, str(A / 'independent' / coordinator_name), stage, freeze]" in parent
assert 'preceding_wall_seconds=elapsed, prior_entry_wall_seconds=PRIOR_ENTRY_WALL_SECONDS' in launch
assert 'elapsed = PRIOR_ENTRY_WALL_SECONDS' in launch
assert 'returncode=code, error=repr(error)' in launch
assert 'code = process.wait()' in launch
assert 'code = None' in launch
assert "command = ['/usr/bin/python3', str(script), str(directory)]" in audit
assert "command=['/usr/bin/python3',str(OBSERVER)" in watcher
assert 'mr3_p2a0_20261018_v23_{stage}' in watcher
assert 'mr3_v22_corrector_custody_v2.py' in preflight + watcher + closure
assert 'mr3_v23_corrector_custody' not in preflight + watcher + closure
# Parent remains the exact original stdlib orchestration after only version/path changes.
old_parent = read(OLD / 'independent/mr3_p2a0_v22_run_matrix_v1.py').decode()
restored_parent = parent.replace('20261018_mr3_p2a0_v23_entry', '20261018_mr3_p2a0_v22_ray_box')
restored_parent = restored_parent.replace('v23', 'v22').replace('V23', 'V22')
assert dump(ast.parse(restored_parent)) == dump(ast.parse(old_parent))
# Inspect actual learner/system boundary without importing any learner/ROS module.
supervisor = read(W / 'mr3_learning/supervisor.py').decode()
ipc = read(W / 'mr3_learning/ipc.py').decode()
package = read(W / 'mr3_learning/__init__.py').decode()
benchmark = read(W / 'mr3_learning/benchmark.py').decode()
full = read(W / 'mr3_learning/audit_preparation.py').decode()
env = read(W / 'mr3_learning/env.py').decode()
assert 'import gymnasium as gym' in env and 'from .env import MR3Env' in benchmark
assert 'from .audit_ppo import load_native_gates' in full
assert '&& exec /usr/bin/python3 "$1/scripts/mr3_env_worker.py"' in supervisor
assert 'source /opt/ros/humble/setup.bash' in supervisor
assert 'from .ipc import JsonLinePeer' in supervisor
assert all(not isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.parse(package).body)
for node in ast.parse(ipc).body:
    if isinstance(node, ast.Import):
        assert all(alias.name in ('json', 'os', 'selectors', 'time') for alias in node.names)
    assert not isinstance(node, ast.ImportFrom)
initial = read(P / 'initial_preflight_actual_probe_source_v1.py').decode()
initial_restored = preflight.replace("PROBE_PREFIX = Path('/tmp/mr3_p2a0_v23_preflight_learner_entry')\n", '')
initial_restored = initial_restored.replace("Path(str(PROBE_PREFIX) + '_probe_v1.json')", "Path('/tmp/mr3_p2a0_v23_learner_entry_probe_v1.json')")
initial_restored = initial_restored.replace("Path(str(PROBE_PREFIX) + '_' + label + '.stdout.log')", "Path('/tmp/mr3_p2a0_v23_learner_entry_' + label + '.stdout.log')")
initial_restored = initial_restored.replace("Path(str(PROBE_PREFIX) + '_' + label + '.stderr.log')", "Path('/tmp/mr3_p2a0_v23_learner_entry_' + label + '.stderr.log')")
assert initial_restored == initial
probe_receipt = js(P / 'actual_entry_probe_v1.json')
assert probe_receipt['passed'] is True and probe_receipt['source_sha256'] == sha(initial.encode())
probe = js(P / 'mr3_p2a0_v23_learner_entry_probe_v1.json')
assert sha(read(P / 'mr3_p2a0_v23_learner_entry_probe_v1.json')) == probe_receipt['probe']['sha256']
assert len(probe['commands']) == 3 and probe['passed'] is True
assert probe['environment_delta']['CUDA_VISIBLE_DEVICES'] == ''
for row in probe['commands']:
    assert row['argv'][0] == LEARNER and row['returncode'] == 0 and row['passed'] is True
    for stream in ('stdout', 'stderr'):
        raw = read(Path(row[stream]))
        assert sha(raw) == row[stream + '_sha256']
assert probe['commands'][0]['import_details']['interpreter'] == LEARNER
assert js(P / 'entry_boundary_checks_v2.json')['passed'] is True
assert js(P / 'style_v3.json')['returncode'] == 0
for path, record in INPUTS.items():
    assert stat(Path(path)) == record['stat'] and sha(Path(path).read_bytes()) == record['sha256']
result = dict(schema='mr3-v23-entry-boundary-independent-review-v1', passed=True, blockers=[],
              plan_sha256=sha(plan_raw), source_sha256=new_sha, input_count=len(INPUTS),
              all_input_final_sha_stat_stable=True, inputs=list(INPUTS.values()),
              old191_bindings_path_sha_unchanged=True, new_bindings=7, actual_unique_bindings=198,
              original_mandatory_counts=counts, hard_gate_fields_unchanged=hard,
              interpreter_roles=dict(preflight='Fixed ns3gym outer executable guard before shared loader imports torch; fixed ns3gym child import/help probes.',
                                     parent_and_coordinators='System Python permitted: only stdlib plus supervisor.process_identity -> stdlib IPC; parent is exact mechanically versioned old AST.',
                                     benchmark='Fixed absolute ns3gym path independent of parent sys.executable; imports env/gymnasium.',
                                     full_audit='Fixed absolute ns3gym path independent of parent sys.executable; imports audit_ppo/torch.',
                                     original_independent_readers='Original explicitly system-Python commands remain unchanged.',
                                     ROS_worker='Existing supervisor sanitizes conda paths and sources ROS/Gazebo; exec /usr/bin/python3 worker unchanged.'),
              actual_preparation_probe=dict(source_sha256=probe_receipt['source_sha256'], three_calls_passed=True,
                                            scope='Recorded author calls only; only helper invoked under system outer to launch fixed conda children. Not a complete final preflight. Final preflight main requires conda outer. Probe-to-final difference is exclusively output naming.'),
              launch_failure_returncode='Actual child code initialized None; real wait result retained even when later summary read fails. No missing returncode key or forced success.',
              budgets=dict(total_ceiling_seconds=18000, prior_real_entry_debit=0.24578428314998746, opening_remaining=17999.75421571685,
                           stage_ceilings_unchanged=True, no_timeout_signal_or_retry=True),
              retained_custody='All original A22 helper862e/binding95ec/actual7be-source3 identities retained under old paths; new watcher discovers actual V23 runs.',
              prior_review_correction='V22 static review missed sys.executable dependency-environment propagation. Its original report stays unchanged; this review specifically examines concrete interpreter command construction and records the actual three preparation probes without rerunning them.',
              scope='Read-only source/AST/receipts/hash/stat review; no unit/import/CLI-help/geometry/math/SDK/ROS/DDS/native/formal calls or canonical changes.',
              pending='Root promotion, clean pushed new exact40 preflight and future full native matrix remain required; no native PASS inferred.',
              argv=sys.argv, wall_seconds=time.monotonic()-began)
output = OUT / 'review_v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(passed=True, path=str(output), sha256=sha(output.read_bytes()), inputs=len(INPUTS), wall_seconds=result['wall_seconds'])))
