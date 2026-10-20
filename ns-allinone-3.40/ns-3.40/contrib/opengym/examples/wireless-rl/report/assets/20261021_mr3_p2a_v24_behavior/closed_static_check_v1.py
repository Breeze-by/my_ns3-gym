"""Closed evidence, accounting, source and documentation checks only."""
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261021_mr3_p2a_v24_behavior'
FREEZE = '9b33cf9b6ab491fd5e3b15269adb30d43be1354c'


def read(path):
    return json.loads(path.read_text())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def check_file(path, record):
    raw = path.read_bytes()
    assert len(raw) == record['bytes'] and sha(raw) == record['sha256'], str(path)


folder = A/'closed_run'
manifest = read(folder/'archive_manifest_v1.json')
digest = hashlib.sha256()
for record in manifest['parts']:
    check_file(folder/record['path'], record)
    digest.update((folder/record['path']).read_bytes())
assert digest.hexdigest() == manifest['archive_sha256']
for record in manifest['metadata']:
    check_file(folder/record['path'], record)
inventory = read(folder/'run_inventory_v1.json')
for relative, record in inventory['files'].items():
    check_file(Path(inventory['original_root'])/relative, record)
copies = read(folder/'auxiliary_copy_index_v1.json')
for record in copies['files']:
    check_file(Path(record['original']), record)
    check_file(folder/record['copy'], record)
for record in read(A/'failure_diagnostic/copy_index_v1.json')['files']:
    check_file(Path(record['original']), record)
    check_file(A/record['copy'], record)
verification = read(folder/'archive_verification_v1.json')
assert all(verification[key] is True for key in (
    'byte_verification_passed', 'run_originals_unchanged', 'auxiliary_originals_unchanged',
    'all_member_bytes_verified', 'all_auxiliary_copy_bytes_verified'))

ledger = read(A/'closed_metadata_v2/engineering_accounting_v1.json')
intervals = []
for item in ledger['outer_receipts']:
    path = Path(item['path'])
    assert sha(path.read_bytes()) == item['sha256']
    record = read(path)
    assert record['scope'] == 'engineering' and record['actual_waited'] and record['source_unchanged']
    start, end = record['started_monotonic_ns'], record['ended_monotonic_ns']
    assert Decimal(record['actual_child_wait_seconds']) == Decimal(end-start)/10**9
    intervals.append((start, end))
intervals.sort()
assert len(intervals) == 3
assert all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:]))
charge = Decimal(sum(end-start for start, end in intervals))/10**9
assert charge == Decimal(ledger['charge_seconds']) == Decimal('1371.868831523')
assert Decimal(intervals[-1][1]-intervals[0][0])/10**9 <= 3600
assert Decimal('44068.6680536126018') + charge == Decimal(ledger['cumulative_used_seconds'])
assert Decimal(52000)-Decimal(ledger['cumulative_used_seconds']) == Decimal('6559.4631148643982')
assert ledger['pilot_remaining_decisions'] == 1870
assert ledger['pilot_remaining_wall_seconds'] == '2905.9547395464029'
assert ledger['final_only_unused_seeds'] == [401, 402, 403]
absence = read(A/'closed_metadata_v2/saved_process_absence_v1.json')
assert absence['saved_identity_count'] == 20 and absence['passed']
assert not absence['present'] and not absence['unreadable'] and not absence['activity_passed']
for identity in absence['saved_identities']:
    try:
        raw = Path(f"/proc/{identity['pid']}/stat").read_text()
    except FileNotFoundError:
        continue
    assert int(raw[raw.rfind(')')+2:].split()[19]) != identity['start_ticks']

run = Path(inventory['original_root'])
activity = read(run/'activity_result.json')
audit = read(run/'independent_audit.json')
behavior = read(run/'behavior_report.json')
assert activity['freeze'] == audit['freeze'] == behavior['freeze'] == FREEZE
assert activity['source_unchanged'] is True
assert all(not value['passed'] for value in (activity, audit, behavior))
assert (audit['step_attempts'], audit['step_returns'], audit['step_errors']) == (544, 543, 1)
assert (audit['verified_action_count'], audit['verified_uniform_action_count'],
        audit['verified_actor_record_count'], audit['verified_step_return_count']) == (544, 544, 546, 543)
assert not audit['complete_full_behavior_diagnostic']
assert sorted(t for ep in audit['episodes'] for t in ep['raw_global_attempt_tickets']) == list(range(1, 545))
assert [ep['raw_counts']['step_return'] for ep in behavior['episodes']] == [205, 173, 165]
assert all(not ep['terminal_assessment']['full_task_terminal'] for ep in behavior['episodes'])
assert all(not ep['evaluator_recalculation']['errors'] for ep in behavior['episodes'])
assert sum(ep['evaluator_recalculation']['trace_matched_advance_count'] for ep in behavior['episodes']) == 543
for value in (activity, audit, behavior):
    assert all(value[key] is False for key in ('qualification', 'training_eligible', 'native_credit'))
extract = read(A/'failure_diagnostic/mr3_proxy2d_v24_failure_extract.json')
failure = extract['protocol_failures'][0]
assert failure['failure']['event']['reason'] == 'goal_lease_expired'
assert failure['failure']['clock_ns'] == 173100000000
assert failure['accept_receipts'][0]['clock_ns'] == 173500000000
assert extract['last_return']['terminated'] is False and extract['last_return']['reason'] is None
assert extract['last_attempt']['preceding_digest'] == extract['last_return']['digest']

plan = read(A/'full_behavior_plan_v1.json')
worker = 'ros2_ws/ros2-multi-robot-automap/scripts/mr3_proxy2d_worker.py'
assert len(plan['source_bindings']) == 112
for relative, expected in plan['source_bindings'].items():
    frozen = git('show', FREEZE+':'+relative)
    assert sha(frozen) == expected
    if relative != worker:
        assert (ROOT/relative).read_bytes() == frozen, relative
# The only post-run production change must be a tick at the actual advanced
# physical boundary. Compare full module ASTs after removing that one call.
old = ast.parse(git('show', FREEZE+':'+worker))
new = ast.parse((ROOT/worker).read_bytes())
klass = next(node for node in new.body if isinstance(node, ast.ClassDef) and node.name == 'ProxyWorker')
advance = next(node for node in klass.body if isinstance(node, ast.FunctionDef) and node.name == 'advance_quantum')
index = next(i for i, node in enumerate(advance.body)
             if ast.dump(node) == ast.dump(ast.parse('self.world.advance()').body[0]))
assert ast.dump(advance.body[index+1]) == ast.dump(ast.parse('self.dispatcher.tick(self.now)').body[0])
del advance.body[index+1]
assert ast.dump(old) == ast.dump(new), 'unexpected additional post-run execution change'
for relative in (
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_episode.py',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation_archive.py',
    str((W/'mr3_learning/observation.py').relative_to(ROOT)),
):
    assert (ROOT/relative).read_bytes() == git('show', 'c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90:'+relative)

changed = git('diff', '--name-only', 'HEAD').decode().splitlines()
links = 0
for relative in changed:
    path = ROOT/relative
    if path.suffix != '.md':
        continue
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
        if '://' in target or target.startswith(('#', 'mailto:')):
            continue
        target = target.split('#', 1)[0]
        if target:
            assert (path.parent/target.strip('<>')).exists(), (relative, target)
            links += 1
assert (W/'log.md').read_bytes().startswith(git('show', 'HEAD:'+str((W/'log.md').relative_to(ROOT))))
before = json.loads(git('show', 'HEAD:'+str((W/'report/ARCHIVE_INDEX.json').relative_to(ROOT))))
after = read(W/'report/ARCHIVE_INDEX.json')
assert all(after[key] == value for key, value in before.items() if key != 'mr3_p2a_v24_behavior_20261021')
assert git('rev-parse', 'p2c1/global-mission-20261012').decode().strip() == '8fe1495b6624cd9136f3ce160acaa274428e54ae'
result = {'passed': True, 'scope': __doc__, 'original_files': len(inventory['files']),
          'original_bytes': inventory['total_bytes'], 'auxiliary_files': len(copies['files']),
          'original_activity_failure_preserved': True, 'raw_attempts_returns_errors': [544, 543, 1],
          'engineering_charge_seconds': str(charge), 'remaining_engineering_seconds': ledger['remaining_seconds'],
          'saved_identities_absent': 20, 'relative_links': links,
          'post_run_production_change': 'one post-advance dispatcher.tick; full module AST proof',
          'other_bound_sources_unchanged': 111, 'log_append_only': True,
          'qualification': False, 'training_eligible': False, 'native_credit': False}
with (A/'closed_static_result_v1.json').open('x') as stream:
    stream.write(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
