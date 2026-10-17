import ast
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v21_ray'
plan = json.loads((A / 'predeclared_plan_v21_ray.json').read_text())
old = json.loads((A.parent / '20261018_mr3_p2a0_v20_sensor/predeclared_plan_v20_sensor.json').read_text())
bindings = {row['path']: row['sha256'] for row in plan['independent_source_bindings']}
assert len(bindings) == 173
assert all(bindings[row['path']] == row['sha256'] for row in old['independent_source_bindings'])
for name, digest in bindings.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
python_paths = list((A / 'independent').glob('*.py'))
for path in python_paths:
    ast.parse(path.read_text())
pre_path = A / 'independent/mr3_p2a0_v21_ray_preflight_v1.py'
spec = importlib.util.spec_from_file_location('v21_static_preflight', pre_path)
pre = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pre)
pre.validate_sensor_plan(plan)
for name, (old_digest, new_digest) in pre.RAY_EXECUTION_DELTAS.items():
    raw = (ROOT / name).read_bytes()
    normative = subprocess.check_output(['git', 'show', pre.RAY_NORMATIVE_FREEZE + ':' + name], cwd=ROOT)
    assert hashlib.sha256(raw).hexdigest() == new_digest
    assert hashlib.sha256(normative).hexdigest() == old_digest
    assert pre.project_ray_runtime(name, raw) == normative
receipt = json.loads((A / 'binary/receipt_v1.json').read_text())
encoded = (ROOT / receipt['archive']).read_bytes()
binary = Path(receipt['installed_source']).read_bytes()
assert gzip.decompress(encoded) == binary
assert hashlib.sha256(binary).hexdigest() == receipt['decoded_sha256']
assert hashlib.sha256(encoded).hexdigest() == receipt['encoded_sha256']
installed_launch = ROOT / 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/share/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'
source_launch = ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'
assert installed_launch.read_bytes() == source_launch.read_bytes()
changed = subprocess.check_output(['git', 'diff', '--name-only'], cwd=ROOT, text=True).splitlines()
links = 0
for name in changed + [str((W / 'report/20261018_mr3_p2a0_v21_ray.md').relative_to(ROOT))]:
    path = ROOT / name
    if path.suffix == '.md':
        for value in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            value = value.strip('<>').split('#')[0]
            if not value or ':' in value or '$' in value:
                continue
            assert (path.parent / unquote(value)).exists(), (name, value)
            links += 1
    if path.suffix == '.json':
        json.loads(path.read_text())
for path in A.rglob('*.json'):
    json.loads(path.read_text())
dry = subprocess.check_output(['git', 'add', '-n', '.'], cwd=ROOT, text=True)
Path('/tmp/mr3_p2a0_v21_add_dry_v1.txt').write_text(dry)
paths = [line[5:-1] for line in dry.splitlines()]
allowed = set(changed) | {str((W / 'report/20261018_mr3_p2a0_v21_ray.md').relative_to(ROOT)),
                          'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_ray_provenance_observer.cpp'}
assert all(name in allowed or name.startswith(str(A.relative_to(ROOT)) + '/') for name in paths)
assert not any('/build/' in name or '/install/' in name or '/log/' in name for name in paths)
result = {'schema': 'mr3-v21-root-precommit-static-v1', 'passed': True,
          'scope': '173 source hashes, actual copied Python syntax, fixed2file inverse bytes, source/binary/archive, JSON/links and actual staging whitelist. Not actual frozen Git admission/native.',
          'old160_exact': True, 'bindings': len(bindings), 'python_files': len(python_paths),
          'actual_installed_launch_equal': True, 'checked_local_links': links,
          'actual_add_dry_paths': len(paths), 'exact_whitelist': True,
          'final_plan_sha256': hashlib.sha256((A / 'predeclared_plan_v21_ray.json').read_bytes()).hexdigest()}
Path('/tmp/mr3_p2a0_v21_root_static_v1.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
