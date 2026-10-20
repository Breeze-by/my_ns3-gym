"""Static pre-freeze checks only; no simulator or historical audit replay."""
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from mr3_learning import proxy2d_performance as activity
from mr3_learning.audit_proxy2d import _activity_contract

ROOT, W, A = activity.ROOT, activity.W, activity.B


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def function(text, name):
    node = next(value for value in ast.parse(text).body
                if isinstance(value, ast.FunctionDef) and value.name == name)
    return ast.get_source_segment(text, node)


plan = json.loads(activity.plan_path('full_behavior').read_text())
spec = plan['activity_spec']
contract = _activity_contract({'activity_spec': spec, 'activity_kind': 'full_behavior',
    'profile_enabled': False, 'scheduled_cells': spec['cells']})
assert contract['worker_cells'] == [[[["open", 101]], [["rooms", 101]], [["corridors", 101]]]]
assert plan['group_wall_seconds'] == contract['group_wall_seconds'] == [2100]
assert spec['max_attempts'] == 900 and spec['steps_per_episode'] == 300
assert spec['activity_seconds'] == 3600
assert plan['phase_seconds'] == activity.PHASES['full_behavior']
assert sum(plan['phase_seconds'].values()) + 120 + 180 == 3530
assert Decimal(plan['engineering_entry_used_seconds']) == Decimal('44068.6680536126018')
assert Decimal(plan['engineering_entry_used_seconds']) + 3600 <= 52000
assert plan['source_bindings'] == activity.activity_bindings('full_behavior')
for key in ('qualification', 'training_eligible', 'native_credit'):
    assert plan[key] is False
for relative, expected in plan['source_bindings'].items():
    path = ROOT/relative
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == expected
    if path.suffix == '.py':
        tree = ast.parse(raw)
        if 'proxy2d' in path.name and 'test' not in path.parts and 'tests' not in path.parts:
            for node in ast.walk(tree):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                assert not any(name.split('.')[0] in {'torch', 'tensorflow', 'stable_baselines3', 'sb3_contrib'}
                               for name in names), relative
for relative in (
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_episode.py',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_observation_archive.py',
    str((W/'mr3_learning/observation.py').relative_to(ROOT)),
):
    assert (ROOT/relative).read_bytes() == git('show', 'c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90:'+relative)
auditor = W/'mr3_learning/audit_proxy2d.py'
assert function(auditor.read_text(), '_duration') == function(
    git('show', 'HEAD:'+str(auditor.relative_to(ROOT))).decode(), '_duration')
changed = set(git('diff', '--name-only', 'HEAD').decode().splitlines())
changed.add(str((W/'report/20261021_mr3_p2a_v24_behavior.md').relative_to(ROOT)))
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
assert git('rev-parse', 'p2c1/global-mission-20261012').decode().strip() == '8fe1495b6624cd9136f3ce160acaa274428e54ae'
result = {'passed': True, 'scope': __doc__, 'source_bindings': len(plan['source_bindings']),
          'independent_fixed_spec_agrees': True, 'relative_links': links,
          'original_pure_actor_episode_bytes_unchanged': True,
          'strict_duration_function_unchanged': True, 'log_append_only': True,
          'qualification': False, 'training_eligible': False, 'native_credit': False}
with (A/'preparation_static_result_v1.json').open('x') as stream:
    stream.write(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
