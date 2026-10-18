"""One external CPU full comparison; original scientific sources/gates stay intact."""
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import traceback
from types import ModuleType
ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
FREEZE = '2500e9e7837a9efc208772d5dc6cf0373ebcb551'
ASSETS = W / 'report/assets/20261019_mr3_p2a_v11'
PREFIX = Path('/tmp/mr3_p2a_v11_motion_memo_full_candidate')

def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''): digest.update(block)
    return digest.hexdigest()

def stat(path):
    s = Path(path).stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]

def write(path, value):
    with Path(path).open('x') as stream: json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')

def git(relative):
    return subprocess.check_output(['git', 'show', FREEZE + ':' + relative], cwd=ROOT)

start = time.monotonic_ns()
record = {'schema': 'mr3-motion-memo-single-full-cpu-comparison-v1', 'freeze': FREEZE,
    'started_wall_monotonic_ns': start, 'actual_full_calls': 0,
    'scope': 'External CPU optimization diagnostic only. Original formal full PASS remains unchanged. Candidate code is not misrepresented by the unchanged formal source_proof fields; its separate actual source identity and one-block proof are explicit here. No new native/GPU or scientific credit.',
    'process_identity': {'pid': __import__('os').getpid()}, 'passed': False, 'errors': []}
original_files = []
source_files = []
try:
    pack = ASSETS / 'closed_evidence/manifest.json'
    manifest = json.loads(pack.read_text())
    for item in manifest['files']:
        if item['source_origin'] != 'actual_closed_file': continue
        path = Path(item['original_path'])
        assert stat(path) == item['source_stat'], str(path)
        assert sha(path) == item['sha256'], str(path)
        original_files.append((path, stat(path), item['sha256']))
    plan_path = ASSETS / 'predeclared_plan_v11.json'
    plan = json.loads(git(str(plan_path.relative_to(ROOT))))
    for relative, digest in plan['source_bindings'].items():
        path = ROOT / relative
        assert sha(path) == digest and hashlib.sha256(git(relative)).hexdigest() == digest, relative
        source_files.append((path, stat(path), digest))
    record['before'] = {'actual_closed_files_SHA_stat_verified': len(original_files),
                        'plan_frozen_source_files_SHA_stat_verified': len(source_files),
                        'original_manifest_sha256': sha(pack)}
    cpu_path = Path('/tmp/mr3_p2a_v11_motion_memo_cpu_v1.json')
    cpu = json.loads(cpu_path.read_text()); assert cpu['passed']
    candidate_path = Path(cpu['candidate_path']); candidate = candidate_path.read_bytes()
    original = git(cpu['source'])
    assert sha(candidate_path) == cpu['candidate_source_sha256']
    assert hashlib.sha256(original).hexdigest() == cpu['original_source_sha256']
    constants = {}
    for node in ast.parse(Path('/tmp/mr3_p2a_v11_motion_memo_cpu_v1.py').read_text()).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in ('OLD','NEW'):
            constants[node.targets[0].id] = ast.literal_eval(node.value).encode()
    assert candidate.count(constants['NEW']) == 1
    assert candidate.replace(constants['NEW'], constants['OLD']) == original
    record['candidate_source'] = {'path': str(candidate_path), 'sha256': sha(candidate_path),
        'original_git_source': FREEZE + ':' + cpu['source'], 'original_sha256': hashlib.sha256(original).hexdigest(),
        'only_single_selected_own_block_replaced': True, 'exact_inverse_whole_source_bytes_equal': True,
        'cpu_proof_path': str(cpu_path), 'cpu_proof_sha256': sha(cpu_path)}
    sys.path.insert(0, str(W))
    from mr3_learning import audit_preparation, audit_controlled_physics, audit_motion
    assert audit_preparation.audit_motion is audit_motion.audit_episode
    assert audit_controlled_physics.audit_motion is audit_motion.audit_episode
    proposed = ModuleType('mr3_learning.audit_motion_memo_candidate')
    proposed.__file__ = str(ROOT / cpu['source'])
    proposed.__package__ = 'mr3_learning'
    exec(compile(candidate, proposed.__file__, 'exec'), proposed.__dict__)
    audit_preparation.audit_motion = proposed.audit_episode
    audit_controlled_physics.audit_motion = proposed.audit_episode
    record['private_process_binding_changes'] = ['audit_preparation.audit_motion', 'audit_controlled_physics.audit_motion']
    native = Path(plan['stages'][0]['run_directory'])
    baseline_path = Path('/tmp/mr3_p2a_v11_matrix_evidence/interface/full_result.json')
    baseline = json.loads(baseline_path.read_text())
    assert baseline['passed'] is True and baseline['freeze'] == FREEZE
    record['baseline'] = {'path': str(baseline_path), 'sha256': sha(baseline_path), 'passed': baseline['passed']}
    call_start = time.monotonic_ns()
    record['actual_full_calls'] += 1
    result = audit_preparation.audit(native, ROOT, FREEZE)
    record['audit_wall_seconds'] = str(Decimal(time.monotonic_ns()-call_start)/Decimal(10**9))
    result_path = Path(str(PREFIX) + '_result_v1.json')
    write(result_path, result)
    record['result'] = {'path': str(result_path), 'sha256': sha(result_path), 'passed': result['passed']}
    record['entire_result_dict_equal_to_formal_full'] = result == baseline
    canonical = lambda value: json.dumps(value, sort_keys=True, allow_nan=False, separators=(',', ':')).encode()
    record['canonical_result_bytes_equal'] = canonical(result) == canonical(baseline)
    record['passed'] = result['passed'] is True and result == baseline
except Exception as error:
    record['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
finally:
    try:
        for path, signature, digest in original_files + source_files:
            assert stat(path) == signature and sha(path) == digest, str(path)
        record['after'] = {'all_before_bound_source_original_and_library_SHA_stat_stable': True,
                           'actual_closed_files': len(original_files), 'plan_frozen_sources': len(source_files)}
    except Exception as error:
        record['passed'] = False
        record['errors'].append({'type': type(error).__name__, 'message': str(error), 'traceback': traceback.format_exc()})
    record['ended_wall_monotonic_ns'] = time.monotonic_ns()
    record['complete_script_wall_seconds'] = str(Decimal(record['ended_wall_monotonic_ns']-start)/Decimal(10**9))
    write(str(PREFIX) + '_receipt_v1.json', record)
print(json.dumps({key: record.get(key) for key in ['passed','actual_full_calls','audit_wall_seconds','complete_script_wall_seconds','entire_result_dict_equal_to_formal_full','canonical_result_bytes_equal','before','after','errors']}))
raise SystemExit(0 if record['passed'] else 1)
