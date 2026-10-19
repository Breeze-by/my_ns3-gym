"""Static preparation proof; no simulator, ROS import, CUDA or scientific run."""
from pathlib import Path
from decimal import Decimal
import ast
import hashlib
import json
import re
import subprocess
import sys

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
A=Path(__file__).resolve().parent
output=Path(sys.argv[1]);assert not output.exists()
opening='1a5af58013f46f8638a2803e30f618eff044c4d6'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def binding(p):
    s=p.stat();return {'path':str(p),'real_path':str(p.resolve()),'bytes':s.st_size,'sha256':sha(p),'stat':[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]}
index=json.loads((A/'validation_index_v1.json').read_text())
for name in index['final_required']:
    row=next(x for x in index['runs'] if x['name']==name)
    p=A/row['receipt'];data=json.loads(p.read_text())
    assert sha(p)==row['receipt_sha256'] and data['passed'] and data['actual_waited'] and data['source_unchanged']
    for b in data['source_after']:assert sha(Path(b['path']))==b['sha256'],b['path']
oldlog=git('show',opening+':'+str((W/'log.md').relative_to(ROOT)))
assert (W/'log.md').read_bytes().startswith(oldlog)
prior_archive=json.loads(git('show',opening+':'+str((W/'report/ARCHIVE_INDEX.json').relative_to(ROOT))))
archive=json.loads((W/'report/ARCHIVE_INDEX.json').read_text())
assert all(archive[k]==v for k,v in prior_archive.items())
assert len(archive)==len(prior_archive)+1
assert not git('diff',opening,'--',str((W/'report/assets/20261019_mr3_p2a_v14').relative_to(ROOT)))
accept=json.loads((A/'contract_acceptance_v1.json').read_text())
assert sha(ROOT/accept['approved_candidate'])==accept['approved_candidate_sha256']
budget=json.loads((A/'engineering_budget_proposal_v1.json').read_text())
assert budget['status']=='SEALED_PROPOSAL_AWAITING_USER_APPROVAL' and not budget['budget_has_changed']
assert Decimal(budget['proposed_ceiling'])-Decimal(budget['used'])==Decimal(budget['available_if_approved'])
assert sum(Decimal(x['cap']) for x in budget['stages'])==Decimal('18000')
assert sum(Decimal(budget['proposed_reservations'][k]) for k in ('matrix_including_native_all_required_readers_and_closure','fresh_seed41_minimum_16_decisions_including_positive_optimizer_and_all_audits','external_final_absence_and_accounting_tail'))==Decimal('20100')
assert Decimal(budget['available_if_approved'])-Decimal('20100')==Decimal(budget['proposed_reservations']['unallocated_if_approved'])
jsons=asts=0
for p in A.rglob('*'):
    if p.suffix=='.json':json.loads(p.read_text());jsons+=1
    elif p.suffix=='.py':ast.parse(p.read_text(),filename=str(p));asts+=1
source_paths=[Path(x) for x in git('diff','--name-only').decode().splitlines() if x.endswith(('.py','.cpp','.hpp'))]
for base in (W/'mr3_learning',ROS/'src/multi_robot_exploration'):
    source_paths += [p.relative_to(ROOT) for p in base.rglob('*.py') if '__pycache__' not in p.parts]
source_paths += [p.relative_to(ROOT) for p in (ROS/'src/multi_robot/include/multi_robot').glob('*.hpp')]
source_paths=sorted(set(source_paths))
for rel in source_paths:
    if rel.suffix=='.py':ast.parse((ROOT/rel).read_text(),filename=str(rel));asts+=1
cpp=ROS/'src/multi_robot/src/mr3_gazebo_diff_drive.cpp';hdr=ROS/'src/multi_robot/include/multi_robot/mr3_drive_feed.hpp'
flags=ROS/'build/multi_robot/CMakeFiles/mr3_gazebo_diff_drive.dir/flags.make'
lib=ROS/'install/multi_robot/lib/libmr3_gazebo_diff_drive.so'
flagtext=flags.read_text();libbytes=lib.read_bytes()
for digest in (sha(cpp),sha(hdr)):
    assert digest in flagtext and digest.encode() in libbytes
assert '-fno-fast-math' in flagtext and '-ffp-contract=off' in flagtext
assert 'BUILD_TESTING:BOOL=ON' in (ROS/'build/multi_robot/CMakeCache.txt').read_text()
manifest={'schema':'mr3-v15-static-source-and-built-library-preparation-v1','opening_commit':opening,
    'scope':'Selected current production/test source inventory and actually built on-disk library; no live loaded-library/ELF custody or new native qualification.',
    'sources':[binding(ROOT/p) for p in source_paths], 'compiler_flags':binding(flags),
    'library':binding(lib),'compiled_source_sha256':sha(cpp),'compiled_feed_header_sha256':sha(hdr),
    'native_admission':False}
(output.parent/'source_binary_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
(output.parent/'actual_compile_flags.make').write_bytes(flags.read_bytes())
docs=[ROOT/'AGENTS.md',W/'AGENTS.md',W/'RESEARCH_PLAN.md',W/'IMPLEMENTATION_PLAN.md',W/'MR3_ENV_CONTRACT.md',W/'MR3_REACH_CONTRACT.md',W/'report/README.md',W/'report/20261019_mr3_p2a_v15.md',ROS/'user_guide.md',ROS/'launch_commands.md',A/'qualification_routing_review_v1.md']
links=[];broken=[]
for p in docs:
    for raw in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',p.read_text()):
        target=raw.strip().strip('<>')
        if target.startswith(('http:','https:','mailto:','#')):continue
        target=target.split('#',1)[0]
        dest=(p.parent/target).resolve()
        links.append([str(p.relative_to(ROOT)),target])
        if not dest.exists():broken.append([str(p.relative_to(ROOT)),target])
assert not broken,broken
assert subprocess.run(['git','diff','--check'],cwd=ROOT).returncode==0
result={'schema':'mr3-v15-static-preparation-review-v1','passed':True,'json_parsed':jsons,'ast_parsed':asts,
    'local_links_checked':len(links),'append_only_log':True,'old_archive_entries_unchanged':True,
    'old_v14_assets_unchanged':True,'actual_library_source_and_feed_sha_match':True,
    'source_manifest':binding(output.parent/'source_binary_manifest.json'),'source_scope':'CPU/build preparation only',
    'native_admission':False,'budget_changed':False}
with output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps(result))
