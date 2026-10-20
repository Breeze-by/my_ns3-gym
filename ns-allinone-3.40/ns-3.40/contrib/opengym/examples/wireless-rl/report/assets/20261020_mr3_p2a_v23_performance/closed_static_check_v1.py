"""Finite archival/source/document checks; no world or actor/audit replay."""
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261020_mr3_p2a_v23_performance'
FREEZE = '2e8fcac9439a1a53e3913e45abccdc0b6645825d'


def read(path):
    return json.loads(path.read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def check_file(path, expected):
    data = path.read_bytes()
    assert len(data) == expected['bytes'] and sha(data) == expected['sha256'], str(path)


counts = {}
for kind in ('profile', 'short'):
    folder = A / (kind + '_closed')
    manifest = read(folder / 'archive_manifest_v1.json')
    digest = hashlib.sha256()
    for item in manifest['parts']:
        check_file(folder / item['path'], item)
        digest.update((folder / item['path']).read_bytes())
    assert digest.hexdigest() == manifest['archive_sha256']
    for item in manifest['metadata']:
        check_file(folder / item['path'], item)
    verification = read(folder / 'archive_verification_v1.json')
    for key in ('byte_verification_passed', 'run_originals_unchanged',
                'auxiliary_originals_unchanged', 'all_member_bytes_verified',
                'all_auxiliary_copy_bytes_verified'):
        assert verification[key] is True
    inventory = read(folder / 'run_inventory_v1.json')
    for relative, item in inventory['files'].items():
        check_file(Path(inventory['original_root']) / relative, item)
    copies = read(folder / 'auxiliary_copy_index_v1.json')
    for item in copies['files']:
        check_file(folder / item['copy'], item)
        check_file(Path(item['original']), item)
    counts[kind] = {'original_files': len(inventory['files']),
                    'original_bytes': inventory['total_bytes'],
                    'auxiliary_files': len(copies['files'])}

entry = Decimal('43261.8239849376018')
charges = []
identity_keys = set()
for kind, limit in (('profile', 600), ('short', 1800)):
    ledger = read(A / (kind + '_metadata/engineering_accounting_v1.json'))
    intervals = []
    for item in ledger['outer_receipts']:
        path = Path(item['path'])
        assert sha(path.read_bytes()) == item['sha256']
        record = read(path)
        start, end = record['started_monotonic_ns'], record['ended_monotonic_ns']
        assert record['scope'] == 'engineering' and record['actual_waited']
        assert record['source_unchanged'] and record['actual_returncode'] == 0
        assert Decimal(record['actual_child_wait_seconds']) == Decimal(end-start)/10**9
        intervals.append((start, end))
    intervals.sort()
    assert all(left[1] <= right[0] for left, right in zip(intervals, intervals[1:]))
    assert Decimal(intervals[-1][1]-intervals[0][0])/10**9 <= limit
    charge = Decimal(sum(end-start for start, end in intervals))/10**9
    assert charge == Decimal(ledger['charge_seconds'])
    assert entry == Decimal(ledger['entry_used_seconds'])
    entry += charge
    assert entry == Decimal(ledger['cumulative_used_seconds'])
    assert Decimal(52000)-entry == Decimal(ledger['remaining_seconds'])
    assert ledger['pilot_remaining_decisions'] == 1870
    assert ledger['pilot_remaining_wall_seconds'] == '2905.9547395464029'
    assert ledger['final_only_unused_seeds'] == [401, 402, 403]
    charges.append(charge)
    absence = read(A / (kind + '_metadata/saved_process_absence_v1.json'))
    assert absence['passed'] and absence['activity_passed']
    assert not absence['present'] and not absence['unreadable']
    assert absence['saved_identity_count'] == (14 if kind == 'profile' else 73)
    for identity in absence['saved_identities']:
        pid, ticks = identity['pid'], identity['start_ticks']
        identity_keys.add((pid, ticks))
        path = Path(f'/proc/{pid}/stat')
        try:
            raw = path.read_text()
        except FileNotFoundError:
            continue
        fields = raw[raw.rfind(')')+2:].split()
        assert int(fields[19]) != ticks, (pid, ticks, fields[0])
assert sum(charges) == Decimal('806.844068675')
assert entry == Decimal('44068.6680536126018') and len(identity_keys) == 87

run = Path(read(A / 'short_closed/archive_manifest_v1.json')['original_run'])
activity, audit = read(run/'activity_result.json'), read(run/'independent_audit.json')
assert activity['passed'] and audit['passed'] and not activity['errors'] and not audit['errors']
assert activity['freeze'] == audit['freeze'] == FREEZE
assert audit['complete_short_capacity_matrix']
assert len(audit['episodes']) == 30
assert sum(v['step_attempts'] for v in audit['episodes']) == 240
assert sum(v['verified_step_return_count'] for v in audit['group_capacity']) == 240
assert sum(v['verified_actor_record_count'] for v in audit['group_capacity']) == 270
assert [v['workers'] for v in audit['group_capacity']] == [1, 4]
for value in (activity, audit):
    for key in ('qualification', 'training_eligible', 'native_credit'):
        assert value[key] is False
assert activity['policy_calls'] == activity['gpu_calls'] == activity['optimizer_steps'] == 0
pair = read(A/'short_closed/closed_execution/aux/mr3_proxy2d_v23_pair_v1.json')
assert pair['passed'] and len(pair['comparisons']) == 9
for item in pair['input_bindings']:
    check_file(Path(item['path']), item)
    assert sha(Path(item['audit_path']).read_bytes()) == item['audit_sha256']

plan = read(A/'short_capacity_plan_v1.json')
assert len(plan['source_bindings']) == 110
for relative, digest in plan['source_bindings'].items():
    assert sha((ROOT/relative).read_bytes()) == digest, relative
    assert sha(git('show', FREEZE+':'+relative)) == digest, relative
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
        if not target:
            continue
        assert (path.parent / target.strip('<>')).exists(), (relative, target)
        links += 1
log_relative = str((W/'log.md').relative_to(ROOT))
assert (W/'log.md').read_bytes().startswith(git('show', 'HEAD:'+log_relative))
archive_relative = str((W/'report/ARCHIVE_INDEX.json').relative_to(ROOT))
before = json.loads(git('show', 'HEAD:'+archive_relative))
after = read(W/'report/ARCHIVE_INDEX.json')
assert all(after[key] == value for key, value in before.items())
assert git('rev-parse', 'p2c1/global-mission-20261012').decode().strip() == '8fe1495b6624cd9136f3ce160acaa274428e54ae'
for path in (A/'close_activity_v2.py', Path(__file__)):
    ast.parse(path.read_text(), filename=str(path))
result = {'passed': True, 'scope': __doc__, 'archives': counts,
          'bound_source_files_unchanged': 110, 'pure_actor_episode_bytes_unchanged': True,
          'relative_links_checked': links, 'log_append_only': True,
          'all_prior_archive_index_records_preserved': True,
          'engineering_charge_seconds': str(sum(charges)),
          'cumulative_engineering_seconds': str(entry),
          'remaining_engineering_seconds': str(Decimal(52000)-entry),
          'saved_activity_identities_absent': len(identity_keys),
          'qualification': False, 'training_eligible': False, 'native_credit': False}
with (A/'closed_static_result_v1.json').open('x') as stream:
    stream.write(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
