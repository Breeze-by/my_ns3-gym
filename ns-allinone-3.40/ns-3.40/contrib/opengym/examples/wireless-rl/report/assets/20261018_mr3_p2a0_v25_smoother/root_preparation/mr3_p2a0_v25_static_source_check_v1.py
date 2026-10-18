import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
A=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
sha=lambda b:hashlib.sha256(b).hexdigest()
plan=json.loads((A/'predeclared_plan_v25.json').read_text())
assert sha((A/'predeclared_plan_v25.json').read_bytes())=='27a5027c930e2d805187ea9e7d53fd16e797ab395c0931c4b76f707a1f6ae051'
assert plan['readiness']['status']=='ready' and not plan['new_source_bindings_pending']
for row in plan['independent_source_bindings']:assert sha((ROOT/row['path']).read_bytes())==row['sha256'],row['path']
manifest=json.loads((A/'source_manifest_v1.json').read_text())
package=ROS/'src/nav2_velocity_smoother'
assert {str(p.relative_to(package)) for p in package.rglob('*') if p.is_file()}==set(manifest['files'])
for name,row in manifest['files'].items():
    raw=(package/name).read_bytes();assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
env=(W/'MR3_ENV_CONTRACT.md').read_bytes()
old=subprocess.check_output(['git','show','94a5e26b99402e49b4e116931f8b8f625e603b0d:'+str((W/'MR3_ENV_CONTRACT.md').relative_to(ROOT))],cwd=ROOT)
assert env[:len(old)]==old and len(old)==50061 and len(env)-len(old)==2038
tree=ast.parse((W/'mr3_learning/audit_ppo.py').read_text())
constants={n.targets[0].id:ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id.startswith('ENV_')}
assert constants['ENV_DOCUMENT_SHA256']==sha(env)
assert constants['ENV_EXECUTION_APPENDIX_BYTES']==len(env)-40186
assert constants['ENV_EXECUTION_APPENDIX_SHA256']==sha(env[40186:])
build=json.loads((A/'build_evidence/build_receipt_v1.json').read_text())
for row in build['outputs']+build['previous_mr3_libraries']:
    raw=Path(row['path']).read_bytes();assert len(raw)==row['bytes'] and sha(raw)==row['sha256']
tracked=subprocess.check_output(['git','diff','--name-only'],cwd=ROOT,text=True).splitlines()
production=[x for x in tracked if not x.endswith('.md') and not x.endswith('report/ARCHIVE_INDEX.json')]
assert production==[str((W/'mr3_learning/audit_ppo.py').relative_to(ROOT))],production
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],cwd=ROOT,text=True).splitlines()
assert all((ROOT/p).is_relative_to(A) or (ROOT/p).is_relative_to(package) for p in untracked)
assert all(not any(x in Path(p).parts for x in ('__pycache__','install','build')) for p in untracked)
checked=[]
docs=[ROOT/p for p in tracked if p.endswith('.md')]+[W/'report/20261018_mr3_p2a0_v25_smoother.md',package/'README.md',package/'MR3_PROVENANCE.md']
for doc in docs:
    for target in re.findall(r'\]\(([^)]+)\)',doc.read_text()):
        target=target.split('#',1)[0].strip('<>')
        if not target or re.match(r'[a-zA-Z][a-zA-Z0-9+.-]*:',target):continue
        target=unquote(target)
        assert (doc.parent/target).exists(),(str(doc),target)
        checked.append([str(doc.relative_to(ROOT)),target])
assets=[p for p in A.rglob('*') if p.is_file()]
assert max(p.stat().st_size for p in assets)<3000000
report=dict(schema='mr3-v25-static-source-check-v1',passed=True,independent_bindings=len(plan['independent_source_bindings']),old_environment_exact_prefix_bytes=len(old),source_package_files=len(manifest['files']),unchanged_existing_libraries=len(build['previous_mr3_libraries']),links_checked=len(checked),assets_before_this_receipt=len(assets),max_asset_bytes=max(p.stat().st_size for p in assets),tracked_modifications=tracked,new_source_paths=untracked,scope='Static source/identity/links/artifact checks; no ROS/DDS/native or old test suites. Actual fresh freeze preflight remains required.')
(A/'root_preparation/static_source_check_v1.json').write_text(json.dumps(report,indent=2)+'\n')
(A/'root_preparation'/Path(__file__).name).write_bytes(Path(__file__).read_bytes())
print(json.dumps({k:v for k,v in report.items() if k not in ('tracked_modifications','new_source_paths')}))
