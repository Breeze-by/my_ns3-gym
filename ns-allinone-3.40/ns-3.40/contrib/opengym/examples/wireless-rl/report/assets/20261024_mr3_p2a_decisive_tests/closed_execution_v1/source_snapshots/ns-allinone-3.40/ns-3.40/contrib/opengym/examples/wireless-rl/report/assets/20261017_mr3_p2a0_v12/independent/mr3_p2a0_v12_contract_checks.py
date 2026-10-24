"""Verify consumer-only readiness integration and unchanged production contracts."""
import ast
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
BASE = 'ba018fe3122c478836eb4e5da9c14306cd832c1b'
A = W / 'report/assets/20261017_mr3_p2a0_v12'


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def original(p):
    return subprocess.check_output(['git', 'show', BASE + ':' + str(p.relative_to(ROOT))],
                                   cwd=ROOT).decode()


old_block = """            original_physics = dispatch_controlled_physics(native_auditor, [native], {})
            try:
                row["native"] = phase.corrected_audit(base, native_auditor, command, [native])
            finally:
                native_auditor.audit_physics = original_physics"""
new_block = """            motion_cache = {}
            original_readiness = native_auditor.audit_initial_inputs_ready
            original_physics = dispatch_controlled_physics(native_auditor, [native], motion_cache)
            try:
                dispatch_controlled_readiness(native_auditor, [native], motion_cache)
                row["native"] = phase.corrected_audit(base, native_auditor, command, [native])
            finally:
                native_auditor.audit_physics = original_physics
                native_auditor.audit_initial_inputs_ready = original_readiness"""
p = W / 'mr3_learning/audit_ppo.py'
s = p.read_text()
assert s.count(new_block) == 1
s = s.replace(new_block, old_block)
new_import = ('from .audit_controlled_physics import dispatch_controlled_physics, '
              'dispatch_controlled_readiness')
assert s.count(new_import) == 1
s = s.replace(new_import, 'from .audit_controlled_physics import dispatch_controlled_physics')
assert ast.dump(ast.parse(s)) == ast.dump(ast.parse(original(p)))
p = W / 'mr3_learning/audit_preparation.py'
s = p.read_text()
for line in (
        '    original_readiness = native.audit_initial_inputs_ready',
        '        dispatch_controlled_readiness(native, [directory], motion_cache)',
        '        native.audit_initial_inputs_ready = original_readiness'):
    assert s.count(line + '\n') == 1
    s = s.replace(line + '\n', '')
s = s.replace(('dispatch_controlled_physics, dispatch_controlled_readiness, '
               'verify_motion_artifacts'),
              'dispatch_controlled_physics, verify_motion_artifacts')
assert ast.dump(ast.parse(s)) == ast.dump(ast.parse(original(p)))
p = W / 'mr3_learning/audit_controlled_physics.py'
old_tree, new_tree = ast.parse(original(p)), ast.parse(p.read_text())
old_functions = {n.name: ast.dump(n) for n in old_tree.body if isinstance(n, ast.FunctionDef)}
new_functions = {n.name: ast.dump(n) for n in new_tree.body if isinstance(n, ast.FunctionDef)}
for name, code in old_functions.items():
    assert code == new_functions[name], 'existing physics/provenance function changed: ' + name
allowed = {str((W / 'mr3_learning' / n).relative_to(ROOT)) for n in (
    'audit_ppo.py', 'audit_preparation.py', 'audit_controlled_physics.py')}
pref = W / ('report/assets/20261017_mr3_p2a0_v11/independent/native_originals_v1/'
            'mr3_p2a0_v11_source_preflight.json.gz')
proof = json.loads(gzip.decompress(pref.read_bytes()))
assert proof['freeze'] == BASE and proof['passed'] is True
unchanged = []
for name in proof['source_bindings']:
    if name in allowed:
        continue
    p = ROOT / name
    frozen = subprocess.check_output(['git', 'show', BASE + ':' + name], cwd=ROOT)
    assert p.read_bytes() == frozen, name
    unchanged.append(name)
sys.path.insert(0, str(W))
audit = importlib.import_module('mr3_learning.audit_ppo')
reviewed = {**audit.EVALUATOR_PHASE_PINS, **audit.PREPARATION_RUNTIME_PINS,
            **audit.EXECUTION_CONFIG_PINS}
for name, digest in reviewed.items():
    assert sha(ROOT / name) == digest, name
assert sha(W / 'MR3_ENV_CONTRACT.md') == audit.ENV_DOCUMENT_SHA256
plan = json.loads((A / 'predeclared_plan_v12.json').read_text())
for binding in plan['independent_source_bindings']:
    assert sha(ROOT / binding['path']) == binding['sha256'], binding['path']
base_plan = json.loads((W / 'report/assets/20261017_mr3_p2a0_v11/'
                       'predeclared_plan_v11.json').read_text())
for key in ('unchanged_gates', 'pilot_budget_unchanged', 'max_total_wall_seconds',
            'max_api_records', 'max_submitted_script_decisions'):
    assert plan[key] == base_plan[key], key
paths = [ROOT / 'AGENTS.md', W / 'AGENTS.md', W / 'IMPLEMENTATION_PLAN.md',
         W / 'RESEARCH_PLAN.md', W / 'report/README.md',
         W / 'report/20261017_mr3_p2a0_v11.md', W / 'report/20261017_mr3_p2a0_v12.md',
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
result = dict(passed=True, schema='mr3-p2a0-v12-static-v1', base=BASE,
              source_bindings=len(plan['independent_source_bindings']), links=links,
              reviewed_pins=len(reviewed), unchanged_production_source=unchanged,
              existing_physics_functions_unchanged=list(old_functions),
              exact_policy_and_preparation_readiness_integration_only=True,
              scope='CPU/static only; no new native or policy credit')
p = Path(sys.argv[1])
with p.open('x') as output:
    output.write(json.dumps(result, indent=2) + '\n')
print(json.dumps({'passed': True, 'production_sources_unchanged': len(unchanged),
                  'pins': len(reviewed), 'links': len(links)}))
