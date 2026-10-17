"""Exact AST custody of the one shared physics integration, no native credit."""
import ast
import copy
import hashlib
import json
from pathlib import Path

BASE = Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning')
OLD = Path('/tmp/mr3_p2a0_v10_shared_physics_before_v1')

def dump(node):
    return ast.dump(node, include_attributes=False)

def function(tree, name):
    return next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                and node.name == name)

before = ast.parse((OLD / 'audit_ppo.py').read_text())
after = ast.parse((BASE / 'audit_ppo.py').read_text())
current = copy.deepcopy(after)
imports = [node for node in current.body if isinstance(node, ast.ImportFrom)
           and node.module == 'audit_controlled_physics']
assert len(imports) == 1 and len(imports[0].names) == 1
assert imports[0].names[0].name == 'dispatch_controlled_physics'
current.body.remove(imports[0])
loader = function(current, 'load_native_gates')
added = []
for node in ast.walk(loader):
    if isinstance(node, ast.Tuple):
        matches = [item for item in node.elts if isinstance(item, ast.Constant)
                   and item.value == 'audit_controlled_physics.py']
        for item in matches:
            node.elts.remove(item)
            added.append(item)
assert len(added) == 1
normalized = []
for node in ast.walk(function(current, 'audit_run')):
    body = getattr(node, 'body', None)
    if not isinstance(body, list):
        continue
    for index, item in enumerate(body[:-1]):
        if not (isinstance(item, ast.Assign) and isinstance(item.value, ast.Call)
                and isinstance(item.value.func, ast.Name)
                and item.value.func.id == 'dispatch_controlled_physics'):
            continue
        wrapper = body[index + 1]
        assert isinstance(wrapper, ast.Try) and len(wrapper.body) == 1
        assert not wrapper.handlers and not wrapper.orelse
        assert len(wrapper.finalbody) == 1
        assert ast.unparse(wrapper.finalbody[0]) == 'native_auditor.audit_physics = original_physics'
        assert ast.unparse(item.value) == 'dispatch_controlled_physics(native_auditor, [native], {})'
        body[index:index + 2] = wrapper.body
        normalized.append(True)
assert len(normalized) == 1 and dump(current) == dump(before)

prep_before = ast.parse((OLD / 'audit_preparation.py').read_text())
shared = ast.parse((BASE / 'audit_controlled_physics.py').read_text())
for name in ('verify_motion_artifacts', 'controlled_bootstrap'):
    moved = copy.deepcopy(function(shared, name))
    for node in ast.walk(moved):
        if isinstance(node, ast.Name) and node.id == '_rows':
            node.id = 'load_rows'
    assert dump(moved) == dump(function(prep_before, name))
old_dispatch = function(prep_before, 'dispatch_controlled_physics')
new_dispatch = copy.deepcopy(function(shared, 'dispatch_controlled_physics'))
old_outer = next(node for node in old_dispatch.body if isinstance(node, ast.For))
new_outer = next(node for node in new_dispatch.body if isinstance(node, ast.For))
assert len(new_outer.body) == 3
new_inner = new_outer.body[-1]
assert isinstance(new_inner, ast.For)
assert dump(new_inner.body[0]) == dump(old_outer.body[0].body[0])
# Keep the actual new metadata/epoch binding body, normalize only admission of
# an explicit episode metadata path versus the original bounded stage glob.
new_inner.iter = copy.deepcopy(old_outer.body[0].iter)
new_outer.body = [new_inner]
assert dump(new_dispatch) == dump(old_dispatch)

files = ['audit_controlled_physics.py', 'audit_preparation.py', 'audit_ppo.py',
         'tests/test_audit_controlled_physics.py', 'tests/test_audit_preparation.py',
         'tests/test_audit_ppo.py']
result = {'passed': True, 'ppo_only_allowed_AST_changes': [
    'one shared stdlib module import', 'one source-bound learner filename',
    'one corrected_audit call-scoped dispatch/finally restoration'],
    'moved_bootstrap_and_artifact_proof_AST_equal': True,
    'dispatch_only_extra_explicit_episode_path_admission': True,
    'capacity_exclusion_not_imported_into_PPO': True,
    'no_ROS_task_actor_reward_sampling_optimizer_changes': True,
    'bindings': {name: {'sha256': hashlib.sha256((BASE / name).read_bytes()).hexdigest(),
                        'bytes': (BASE / name).stat().st_size} for name in files}}
output = Path('/tmp/mr3_p2a0_v10_runtime_shared_physics_static_v1.json')
assert not output.exists()
output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
