"""Check V25 CPU receipts, cache-only source change and repository handoff."""
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
BASE = '9edad01ccdb3a1adf2c20d22f62b7d4f3a4733ed'
ROS = 'ros2_ws/ros2-multi-robot-automap'
PKG = ROS + '/src/multi_robot_exploration/multi_robot_exploration/'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


index = read(A / 'cpu_validation_index_v1.json')
identities = 0
for check in index['checks']:
    receipt_path = A / check['receipt']
    receipt = read(receipt_path)
    assert receipt['scope'] == 'cpu' and receipt['passed']
    assert receipt['actual_waited'] and receipt['actual_returncode'] == 0
    assert receipt['source_unchanged'] and not receipt['errors']
    assert receipt['source_before'] == receipt['source_after']
    assert Decimal(receipt['actual_child_wait_seconds']) == (
        Decimal(receipt['ended_monotonic_ns'] - receipt['started_monotonic_ns']) / 10**9)
    for source in receipt['source_after']:
        assert sha(Path(source['path'])) == source['sha256'], source['path']
    console = receipt_path.with_name('console.log')
    assert sha(console) == receipt['console']['sha256']
    if 'pytest_passed' in check:
        assert re.search(r'\b' + str(check['pytest_passed']) + r' passed\b', console.read_text())
    for label in ('coordinator_identity', 'child_identity'):
        saved = receipt[label]
        path = Path('/proc') / str(saved['pid']) / 'stat'
        try:
            fields = path.read_text().rsplit(')', 1)[1].split()
        except FileNotFoundError:
            pass
        else:
            assert int(fields[19]) != saved['start_ticks'], (label, saved)
        identities += 1

# Full-module AST equality after restoring only the original cache key.
navigation_path = PKG + 'mr3_proxy2d_navigation.py'
old = ast.parse(git('show', BASE + ':' + navigation_path))
new = ast.parse((ROOT / navigation_path).read_bytes())


def key_assignment(module):
    return next(node for node in ast.walk(module) if isinstance(node, ast.Assign)
                and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == 'key')


assert ast.dump(key_assignment(new).value) != ast.dump(key_assignment(old).value)
key_assignment(new).value = key_assignment(old).value
assert ast.dump(new) == ast.dump(old), 'unexpected execution change beyond cache identity'
unchanged = (
    'mr3_observation.py', 'mr3_episode.py', 'mr3_observation_archive.py',
    'mr3_protocol.py', 'mr3_transport.py', 'mr3_information.py',
    'mr3_reach_geometry.py', 'mr3_proxy2d_world.py', 'mr3_proxy2d_reward.py',
    'mr3_task_contract.py', 'task_evaluator.py',
)
for filename in unchanged:
    relative = PKG + filename
    assert (ROOT / relative).read_bytes() == git('show', BASE + ':' + relative), relative
for relative in (ROS + '/scripts/mr3_proxy2d_worker.py',
                 str((W / 'mr3_learning/observation.py').relative_to(ROOT)),
                 str((W / 'mr3_learning/audit_proxy2d.py').relative_to(ROOT))):
    assert (ROOT / relative).read_bytes() == git('show', BASE + ':' + relative), relative
assert not git('diff', BASE, '--', str((W / 'report/assets/20261021_mr3_p2a_v24_behavior').relative_to(ROOT)))

mapping = read(A / 'mapping_quality_artificial_v1.json')
assert not mapping['production_modified'] and not mapping['thresholds_modified']
assert not mapping['actual_scene_impossibility_claim'] and not mapping['native_or_task_qualification']
assert mapping['thick_box']['occupied_cells'] == 697
assert mapping['thick_box']['surface_endpoint_cells'] == 112
assert mapping['thick_box']['tight_noiseless_endpoint_iou_upper_bound'] == 112 / 697
assert mapping['thin_box_control']['quality_only_pass']
assert mapping['positive_range_error']['two_measurement_metrics']['false_free_ratio'] == .04
for path, digest in mapping['source_sha256'].items():
    assert sha(Path(path)) == digest

timing = read(A / 'navigation_cache_artificial_v1.json')
assert timing['passed'] and len(timing['rounds']) == 6
assert all(timing[key] == 0 for key in (
    'worlds_created', 'nodes_created', 'episodes', 'policy_calls', 'gpu_calls', 'optimizer_steps'))
for sample in timing['rounds']:
    assert sample['full_velocity_blocked_and_field_outputs_equal']
    assert sample['requests_per_implementation'] == sample['original']['dijkstra_builds'] == 12
    assert sample['optimized']['dijkstra_builds'] == (1 if sample['case'] == 'timestamp_only' else 12)
assert not timing['qualification'] and not timing['training_eligible'] and not timing['native_credit']

scope = read(A / 'scope_acceptance_v1.json')
assert scope['engineering_remaining_seconds'] == '6559.4631148643982'
assert scope['new_formal_runs'] == scope['new_policy_calls'] == scope['new_optimizer_steps'] == scope['new_native_runs'] == 0
assert scope['pilot_remaining_decisions'] == 1870
assert scope['pilot_remaining_seconds'] == '2905.9547395464029'
assert scope['final_only_unused_seeds'] == [401, 402, 403]
assert not scope['qualification'] and not scope['training_eligible'] and not scope['native_credit']
assert (W / 'log.md').read_bytes().startswith(git('show', BASE + ':' + str((W / 'log.md').relative_to(ROOT))))
archive_path = str((W / 'report/ARCHIVE_INDEX.json').relative_to(ROOT))
before, after = json.loads(git('show', BASE + ':' + archive_path)), read(ROOT / archive_path)
assert all(after[key] == value for key, value in before.items())
assert git('rev-parse', 'p2c1/global-mission-20261012').decode().strip() == '8fe1495b6624cd9136f3ce160acaa274428e54ae'

documents = set(git('diff', '--name-only', BASE).decode().splitlines())
documents.add(str((W / 'report/20261021_mr3_p2a_v25_cpu.md').relative_to(ROOT)))
links = 0
for relative in documents:
    path = ROOT / relative
    if path.suffix != '.md':
        continue
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
        if '://' in target or target.startswith(('#', 'mailto:')):
            continue
        target = target.split('#', 1)[0].strip('<>')
        if target:
            assert (path.parent / target).exists(), (relative, target)
            links += 1
result = {
    'passed': True, 'scope': __doc__, 'cpu_checks': len(index['checks']),
    'saved_cpu_identities_absent': identities, 'relative_links': links,
    'production_change': 'Only the exact geometric cache key; full-module AST equality otherwise',
    'pure_actor_protocol_mapping_evaluator_and_prior_evidence_unchanged': True,
    'new_engineering_seconds': '0', 'remaining_engineering_seconds': '6559.4631148643982',
    'qualification': False, 'training_eligible': False, 'native_credit': False,
}
with (A / 'static_result_v1.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
