"""Verify closed geometry evidence, sources, accounting and handoff; no geometry replay."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
FREEZE = '89a1b0543c5445bb5815162ae4ef07f1f7c728c0'


def read(path):
    return json.loads(path.read_text())


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


copies = read(A / 'evidence_copy_index_v1.json')
assert copies['original_files'] == len(copies['files']) == 13
for row in copies['files']:
    raw = (A / row['copy']).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
    assert raw == Path(row['original']).read_bytes()
assert sum(row['bytes'] for row in copies['files']) == copies['total_bytes']
plan = read(A / 'predeclared_plan_v1.json')
assert len(plan['source_bindings']) == 20
for relative, record in plan['source_bindings'].items():
    raw = (ROOT / relative).read_bytes()
    assert len(raw) == record['bytes'] and hashlib.sha256(raw).hexdigest() == record['sha256']
    assert raw == git('show', FREEZE + ':' + relative)
geometry = read(A / 'closed_execution/guard/geometry_result.json')
assert geometry['passed'] and not geometry['errors'] and geometry['bound_bytes_unchanged']
assert geometry['freeze'] == FREEZE
assert len(geometry['source_and_asset_bindings']) == 14
assert [row['scene'] for row in geometry['scenes']] == ['open', 'rooms', 'corridors']
assert [row['truth_occupied_cell_count'] for row in geometry['scenes']] == [5964, 6176, 5296]
assert [row['possible_endpoint_overlap_correct_occupied_cells'] for row in geometry['scenes']] == [2328, 2992, 2720]
for row in geometry['scenes']:
    assert row['conditional_occupied_iou_upper_enclosure'] >= .2
    assert not row['conditional_enclosure_below_declared_gate']
    assert not row['denominator_modified'] and not row['actual_noisy_proxy_task_impossibility_claim']
    assert row['conditional_occupied_iou_upper_enclosure'] == row['roi_origin_front_face']['conditional_occupied_iou_upper_enclosure']
assert all(geometry[key] == 0 for key in ('worlds_created', 'nodes_created', 'episodes', 'actor_calls',
    'reward_replays', 'policy_calls', 'gpu_calls', 'optimizer_steps'))
assert not geometry['qualification'] and not geometry['training_eligible'] and not geometry['native_credit']

outer_paths = [A / 'closed_execution' / name / 'actual_wait.json' for name in ('main_outer', 'final_outer')]
outers = [read(path) for path in outer_paths]
for path, outer in zip(outer_paths, outers):
    assert outer['scope'] == 'engineering' and outer['passed'] and outer['source_unchanged']
    assert outer['actual_returncode'] == 0 and outer['actual_waited'] and not outer['errors']
    assert outer['source_before'] == outer['source_after']
    assert hashlib.sha256(path.with_name('console.log').read_bytes()).hexdigest() == outer['console']['sha256']
assert len(outers[0]['source_before']) == 21
assert outers[0]['ended_monotonic_ns'] <= outers[1]['started_monotonic_ns']
charge = Decimal(sum(row['ended_monotonic_ns'] - row['started_monotonic_ns'] for row in outers)) / 10**9
ledger = read(A / 'closed_metadata/engineering_accounting_v1.json')
assert str(charge) == ledger['charged_seconds'] == '4.886817531'
assert Decimal(ledger['entry_seconds']) + charge == Decimal(ledger['cumulative_seconds'])
assert Decimal(ledger['ceiling_seconds']) - Decimal(ledger['cumulative_seconds']) == Decimal(ledger['remaining_seconds'])
assert ledger['remaining_seconds'] == '6554.5762973333982'
assert Decimal(ledger['full_start_to_final_end_seconds']) < 120
assert ledger['pilot_remaining_decisions'] == 1870
assert ledger['pilot_remaining_seconds'] == '2905.9547395464029'
assert ledger['final_only_unused_seeds'] == [401, 402, 403]
assert read(A / 'closed_execution/final.json')['passed']
saved = read(A / 'closed_metadata/saved_process_absence_v1.json')
assert saved['passed'] and saved['total_saved_identities'] == 7
for row in saved['records']:
    value = row['saved_identity']
    try:
        current = (Path('/proc') / str(value['pid']) / 'stat').read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        pass
    else:
        assert int(current[19]) != value['start_ticks'], value
for folder in ('ros2_ws/ros2-multi-robot-automap/src', 'ros2_ws/ros2-multi-robot-automap/scripts',
               str((W / 'mr3_learning').relative_to(ROOT))):
    assert not git('diff', FREEZE, '--', folder)
assert (W / 'log.md').read_bytes().startswith(git('show', FREEZE + ':' + str((W / 'log.md').relative_to(ROOT))))
archive = str((W / 'report/ARCHIVE_INDEX.json').relative_to(ROOT))
before, after = json.loads(git('show', FREEZE + ':' + archive)), read(ROOT / archive)
assert all(after[key] == value for key, value in before.items() if key != 'mr3_p2a_v26_geometry_20261021')
assert git('rev-parse', 'p2c1/global-mission-20261012').decode().strip() == '8fe1495b6624cd9136f3ce160acaa274428e54ae'
links = 0
for relative in git('diff', '--name-only', FREEZE).decode().splitlines():
    path = ROOT / relative
    if path.suffix != '.md':
        continue
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
        if '://' not in target and not target.startswith(('#', 'mailto:')):
            target = target.split('#', 1)[0].strip('<>')
            if target:
                assert (path.parent / target).exists(), (relative, target)
                links += 1
result = {'passed': True, 'scope': __doc__, 'source_bindings': 20, 'consumer_bindings': 14,
          'original_files_copied_exactly': 13, 'saved_identities_absent': 7,
          'engineering_charge_seconds': str(charge), 'remaining_seconds': ledger['remaining_seconds'],
          'relative_links': links, 'runtime_and_prior_evidence_unchanged': True,
          'log_append_only': True, 'qualification': False, 'training_eligible': False, 'native_credit': False}
with (A / 'closed_static_result_v1.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
