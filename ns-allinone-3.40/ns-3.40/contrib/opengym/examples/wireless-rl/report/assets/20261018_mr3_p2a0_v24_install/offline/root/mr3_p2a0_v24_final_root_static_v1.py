import ast
import gzip
import hashlib
import json
from pathlib import Path
import re

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = W / 'report/assets/20261018_mr3_p2a0_v24_install'
sha = lambda b: hashlib.sha256(b).hexdigest()
raw = (A / 'predeclared_plan_v24.json').read_bytes()
assert sha(raw) == 'd682f40c01a660f598cdf6c81d9faa640c25af1ba87d9e96e56701bb2fec4ffc'
p = json.loads(raw)
old = json.loads((W / 'report/assets/20261018_mr3_p2a0_v23_entry/predeclared_plan_v23.json').read_bytes())
assert p['readiness']['status'] == 'ready' and p['readiness']['pending_bindings'] == []
before = {x['path']: x['sha256'] for x in old['independent_source_bindings']}
bindings = {x['path']: x['sha256'] for x in p['independent_source_bindings']}
assert len(before) == 198 and len(bindings) == 210 and set(before) <= set(bindings)
changed = {path for path in before if before[path] != bindings[path]}
assert changed == {'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_ray_box_corrector.cpp', 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_ppo.py'}
for path, digest in bindings.items():
    assert sha((ROOT / path).read_bytes()) == digest, path
assert p['max_api_records'] == old['max_api_records'] == 608
assert p['max_submitted_script_decisions'] == old['max_submitted_script_decisions'] == 596
assert p['prior_engineering_cost']['wall_seconds'] == 71.97839368507266
assert len(p['stages']) == 4
mandatory = []
for index, (previous, current) in enumerate(zip(old['stages'], p['stages'])):
    assert current['stage'] == previous['stage'] == ('interface', 'terminal', 'reset', 'deadline')[index]
    assert current['required_audits'] == previous['required_audits']
    assert current['required_audit_receipts'] == [v.replace('mr3_p2a0_v23_', 'mr3_p2a0_v24_') for v in previous['required_audit_receipts']]
    mandatory.append(len(current['required_audit_receipts']))
    a, b = previous['command'][:], current['command'][:]
    for flag in ('--base-domain', '--base-port', '--run-id'):
        pos = a.index(flag) + 1
        a[pos] = b[pos]
    assert a == b, current['stage']
    assert b[b.index('--base-domain') + 1] == ('198', '200', '202', '206')[index]
    assert b[b.index('--base-port') + 1] == ('13701', '13711', '13721', '13731')[index]
assert mandatory == [10, 7, 10, 7]
assert p['native_ray_box_correction']['actual_library_sha256'] == '782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8'
assert p['native_ray_box_correction']['required_actual_install_iteration'] is None
assert p['native_ray_box_correction']['required_actual_install_iteration_available'] is False
actual = (ROS / 'install/multi_robot/lib/libmr3_ray_box_corrector.so').read_bytes()
assert gzip.decompress((A / 'binary/libmr3_ray_box_corrector.so.gz').read_bytes()) == actual
assert sha(actual) == p['native_ray_box_correction']['actual_library_sha256']
python_files = list((A / 'independent').glob('*.py'))
for path in python_files:
    ast.parse(path.read_text(), filename=str(path))
json_files = list(A.rglob('*.json'))
for path in json_files:
    json.loads(path.read_text())
documents = [ROOT / 'AGENTS.md', ROS / 'AGENTS.md', ROS / 'user_guide.md', ROS / 'launch_commands.md'] + [W / name for name in ('AGENTS.md', 'RESEARCH_PLAN.md', 'IMPLEMENTATION_PLAN.md', 'MR3_ENV_CONTRACT.md', 'report/README.md', 'report/20261018_mr3_p2a0_v24_install.md')]
link_count = 0
for path in documents:
    for target in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', path.read_text()):
        if target.startswith(('http:', 'https:', '#', 'app:', 'mailto:')):
            continue
        target = target.split('#')[0]
        if not target:
            continue
        assert (path.parent / target).exists(), (str(path), target)
        link_count += 1
result = {'schema': 'mr3-v24-root-final-static-only-v1', 'passed': True, 'scope': 'Worktree source/JSON/AST/links and explicit original matrix invariants only, not frozen preflight or native execution.', 'plan_sha256': sha(raw), 'bindings': len(bindings), 'old_exact': 196, 'old_explicit_changed': sorted(changed), 'new': len(set(bindings) - set(before)), 'mandatory_receipts': mandatory, 'python_AST': len(python_files), 'parsed_JSON': len(json_files), 'document_links': link_count, 'actual_library_sha256': sha(actual)}
Path('/tmp/mr3_p2a0_v24_final_root_static_v1.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
