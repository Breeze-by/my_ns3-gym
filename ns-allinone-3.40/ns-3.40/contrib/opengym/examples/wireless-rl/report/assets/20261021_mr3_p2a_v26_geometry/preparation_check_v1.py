"""Source, metadata and document checks only; no actual geometry evaluation."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
BASE = '6e0b7316ac1683bff139311d960f3f58b3f7b376'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def read(path):
    return json.loads(path.read_text())


plan = read(A / 'predeclared_plan_v1.json')
assert len(plan['source_bindings']) == 20
for relative, record in plan['source_bindings'].items():
    path = ROOT / relative
    raw = path.read_bytes()
    assert len(raw) == record['bytes'] and hashlib.sha256(raw).hexdigest() == record['sha256'], relative
    if path.suffix == '.py':
        ast.parse(raw)
index = read(A / 'cpu_preparation_index_v1.json')
assert [row['passed_cases'] for row in index['checks']] == [21, 10, 5]
for row in index['checks']:
    receipt = read(A / row['receipt'])
    assert receipt['scope'] == 'cpu' and receipt['passed'] and receipt['actual_waited']
    assert receipt['actual_returncode'] == 0 and receipt['source_unchanged'] and not receipt['errors']
    for source in receipt['source_after']:
        assert hashlib.sha256(Path(source['path']).read_bytes()).hexdigest() == source['sha256']
    console = (A / row['receipt']).with_name('console.log')
    assert hashlib.sha256(console.read_bytes()).hexdigest() == receipt['console']['sha256']
    assert re.search(r'\b(?:' + str(row['passed_cases']) + r' passed|Ran ' + str(row['passed_cases']) + r' tests)\b', console.read_text())
for folder in ('ros2_ws/ros2-multi-robot-automap/src', 'ros2_ws/ros2-multi-robot-automap/scripts',
               str((W / 'mr3_learning').relative_to(ROOT))):
    # New standalone diagnostic/tests may be untracked; every existing byte is unchanged.
    assert not git('diff', BASE, '--', folder), folder
for scene in plan['scenes']:
    asset = ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot'
    contract = read(asset / f'config/mr3_p1a/{scene}.json')
    assert hashlib.sha256((asset / f'worlds/p1c_{scene}.world').read_bytes()).hexdigest() == contract['world_sha256']
    assert contract['robots'] == ['tb1', 'tb2', 'tb3'] and contract['resolution'] == .05
    assert contract['coverage_threshold'] == .95 and contract['max_duration_sec'] == 300
    assert contract['quality']['min_occupied_iou'] == .2
    assert contract['quality']['max_false_free_ratio'] == .02
assert (W / 'log.md').read_bytes().startswith(git('show', BASE + ':' + str((W / 'log.md').relative_to(ROOT))))
archive = str((W / 'report/ARCHIVE_INDEX.json').relative_to(ROOT))
before, after = json.loads(git('show', BASE + ':' + archive)), read(ROOT / archive)
assert all(after[key] == value for key, value in before.items())
assert git('rev-parse', 'p2c1/global-mission-20261012').decode().strip() == '8fe1495b6624cd9136f3ce160acaa274428e54ae'
documents = set(git('diff', '--name-only', BASE).decode().splitlines())
documents.add(str((W / 'report/20261021_mr3_p2a_v26_geometry.md').relative_to(ROOT)))
links = 0
for relative in documents:
    path = ROOT / relative
    if path.suffix != '.md':
        continue
    for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
        if '://' not in target and not target.startswith(('#', 'mailto:')):
            target = target.split('#', 1)[0].strip('<>')
            if target:
                assert (path.parent / target).exists(), (relative, target)
                links += 1
result = {'passed': True, 'scope': __doc__, 'source_bindings': 20,
          'cpu_cases': [21, 10, 5], 'existing_production_unchanged': True,
          'original_task_contracts_unchanged': True, 'relative_links': links,
          'log_append_only': True, 'old_archive_entries_preserved': True,
          'qualification': False, 'training_eligible': False, 'native_credit': False}
with (A / 'preparation_static_result_v1.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(result))
