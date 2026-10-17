"""Verify the v11 narrow repair, unchanged gates and exact declared consumers."""
import ast
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
BASE = '631d8c35c43fdb7ed45e984376543e55395066ef'
A = W / 'report/assets/20261017_mr3_p2a0_v11'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def original(path):
    return subprocess.check_output(['git', 'show', BASE + ':' + str(path.relative_to(ROOT))],
                                   cwd=ROOT)


sys.path.insert(0, str(W))
audit = importlib.import_module('mr3_learning.audit_ppo')
path = W / 'mr3_learning/audit_ppo.py'
old, new = ast.parse(original(path)), ast.parse(path.read_text())
for tree in (old, new):
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'PREPARATION_RUNTIME_PINS'
                        for t in n.targets))
    node.value = ast.Constant('ONLY-REVIEWED-RUNTIME-PINS')
assert ast.dump(old) == ast.dump(new), 'policy/objective/consumer logic changed'
protocol_path = W / 'mr3_learning/audit_protocol.py'
protocol_old = ast.parse(original(protocol_path))
protocol_new = ast.parse(protocol_path.read_text())
for tree in (protocol_old, protocol_new):
    node = next(n for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == 'PINS' for t in n.targets))
    node.value = ast.Constant('EXACT-REVIEWED-ADAPTER-PIN')
assert ast.dump(protocol_old) == ast.dump(protocol_new), 'unsent proof logic changed'

reviewed = {**audit.EVALUATOR_PHASE_PINS, **audit.PREPARATION_RUNTIME_PINS,
            **audit.EXECUTION_CONFIG_PINS}
for name, digest in reviewed.items():
    assert sha(ROOT / name) == digest, name
assert sha(W / 'MR3_ENV_CONTRACT.md') == audit.ENV_DOCUMENT_SHA256
unchanged = [W / n for n in ('MR3_TASK_CONTRACT.md', 'MR3_ENV_CONTRACT.md',
                             'MR3_ADAPTER_CONTRACT.md', 'mr3_learning/ppo.py',
                             'mr3_learning/model.py', 'mr3_learning/benchmark.py',
                             'mr3_learning/audit_motion.py',
                             'mr3_learning/audit_controlled_physics.py',
                             'mr3_learning/audit_preparation.py')]
pkg = ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/'
pkg /= 'multi_robot_exploration'
unchanged += [pkg / n for n in (
    'mr3_reward.py', 'mr3_observation.py', 'mr3_protocol.py',
    'motion_safety.py', 'mr3_motion_safety.py', 'mr3_information.py',
    'mr3_control_phase.py', 'mr3_motion_control.py', 'task_evaluator.py')]
for path in unchanged:
    assert path.read_bytes() == original(path), path
plan = json.loads((A / 'predeclared_plan_v11.json').read_text())
for binding in plan['independent_source_bindings']:
    assert sha(ROOT / binding['path']) == binding['sha256'], binding['path']
base_plan = json.loads((W / 'report/assets/20261017_mr3_p2a0_v10/'
                       'predeclared_plan_v10.json').read_text())
for key in ('unchanged_gates', 'pilot_budget_unchanged', 'max_total_wall_seconds',
            'max_api_records', 'max_submitted_script_decisions'):
    assert plan[key] == base_plan[key], key
paths = [ROOT / 'AGENTS.md', W / 'AGENTS.md', W / 'IMPLEMENTATION_PLAN.md',
         W / 'RESEARCH_PLAN.md', W / 'report/README.md',
         W / 'report/20261017_mr3_p2a0_v10.md', W / 'report/20261017_mr3_p2a0_v11.md',
         ROOT / 'ros2_ws/ros2-multi-robot-automap/AGENTS.md',
         ROOT / 'ros2_ws/ros2-multi-robot-automap/user_guide.md',
         ROOT / 'ros2_ws/ros2-multi-robot-automap/launch_commands.md']
links = []
for path in paths:
    for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
        if target.startswith(('http:', 'https:', '#', 'app:', 'plugin:')):
            continue
        assert (path.parent / target.split('#', 1)[0]).exists(), (path, target)
        links.append([str(path.relative_to(ROOT)), target])
result = dict(passed=True, schema='mr3-p2a0-v11-static-v1', base=BASE,
              reviewed_pins=len(reviewed),
              source_bindings=len(plan['independent_source_bindings']),
              links=links, unchanged=[str(p.relative_to(ROOT)) for p in unchanged],
              only_audit_pin_ast_change=True, scope='CPU/static only, no native credit')
p = Path(sys.argv[1])
with p.open('x') as output:
    output.write(json.dumps(result, indent=2) + '\n')
print(json.dumps({'passed': True, 'reviewed_pins': len(reviewed), 'links': len(links)}))
