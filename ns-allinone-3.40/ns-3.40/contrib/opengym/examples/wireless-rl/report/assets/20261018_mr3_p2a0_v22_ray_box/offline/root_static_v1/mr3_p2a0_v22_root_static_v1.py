import ast
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v22_ray_box'
OUT=Path('/tmp/mr3_p2a0_v22_root_static_v1')
assert not OUT.exists()
OUT.mkdir()
plan=json.loads((A/'predeclared_plan_v22.json').read_bytes())
old=json.loads((A.parent/'20261018_mr3_p2a0_v21_ray/predeclared_plan_v21_ray.json').read_bytes())
bindings={row['path']:row['sha256'] for row in plan['independent_source_bindings']}
assert len(bindings)==len(plan['independent_source_bindings'])
changed_old=[]
for row in old['independent_source_bindings']:
    assert row['path'] in bindings,row['path']
    if row['sha256']!=bindings[row['path']]:changed_old.append(row['path'])
assert sorted(changed_old)==sorted(str((W/p).relative_to(ROOT)) for p in ['mr3_learning/audit_ppo.py','mr3_learning/tests/test_audit_ppo.py'])
for relative,digest in bindings.items():
    assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()==digest,relative
assert plan['readiness']['status']=='ready' and not plan['readiness']['pending_bindings']
assert [r['stage'] for r in plan['stages']]==['interface','terminal','reset','deadline']
assert plan['max_api_records']==608 and plan['max_submitted_script_decisions']==596 and plan['max_total_wall_seconds']==18000
assert [len(r['required_audit_receipts']) for r in plan['stages']]==[10,7,10,7]
py=list((A/'independent').glob('*.py'))
for p in py:ast.parse(p.read_bytes())
binary=json.loads((A/'binary/receipt_v1.json').read_bytes())
installed=ROOT/'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_ray_box_corrector.so'
raw=installed.read_bytes()
assert hashlib.sha256(raw).hexdigest()=='7be79c7f3d2cac53a9d1692aa868d91d4b9977e2b7541203ce4ffe90c605a08f'
assert gzip.decompress((A/'binary/libmr3_ray_box_corrector.so.gz').read_bytes())==raw
source=ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'
installedlaunch=ROOT/'ros2_ws/ros2-multi-robot-automap/install/multi_robot/share/multi_robot/launch'/source.name
assert source.read_bytes()==installedlaunch.read_bytes()
changed=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
report=str((W/'report/20261018_mr3_p2a0_v22_ray_box.md').relative_to(ROOT))
links=0
for name in changed+[report]:
    path=ROOT/name
    if path.suffix=='.md':
        for value in re.findall(r'\]\(([^)]+)\)',path.read_text()):
            value=value.strip('<>').split('#')[0]
            if not value or ':' in value or '$' in value:continue
            assert (path.parent/unquote(value)).exists(),(name,value)
            links+=1
    if path.suffix=='.json':json.loads(path.read_bytes())
for path in A.rglob('*.json'):json.loads(path.read_bytes())
check=subprocess.run(['git','diff','--check'],cwd=ROOT,capture_output=True)
(OUT/'diff_check.stdout').write_bytes(check.stdout);(OUT/'diff_check.stderr').write_bytes(check.stderr)
assert check.returncode==0
dry=subprocess.check_output(['git','add','-n','.'],cwd=ROOT,text=True)
(OUT/'add_dry.txt').write_text(dry)
paths=[line[5:-1] for line in dry.splitlines()]
allowed=set(changed)|{report,
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_ray_box_corrector.cpp',
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_ray_box_collision.cpp',
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_ray_box_collision.hpp',
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/vendor/mr3_ray_box_corrector/LICENSE-BSD.TXT'}
assert all(name in allowed or name.startswith(str(A.relative_to(ROOT))+'/') for name in paths)
assert not any('/build/' in name or '/install/' in name or '/log/' in name for name in paths)
result={'schema':'mr3-v22-root-precommit-static-v1','passed':True,'scope':'Actual current source hashes, Python AST, final library gzip equality, installed launch equality, JSON/local links and actual staging whitelist. No cleanfreeze source admission/native.', 'source_bindings':len(bindings),'old173_unchanged':171,'old173_explicit_revised':changed_old,'python_files':len(py),'actual_local_links':links,'actual_add_dry_paths':len(paths),'paths':paths,'plan_sha256':hashlib.sha256((A/'predeclared_plan_v22.json').read_bytes()).hexdigest()}
(OUT/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='paths'}))
