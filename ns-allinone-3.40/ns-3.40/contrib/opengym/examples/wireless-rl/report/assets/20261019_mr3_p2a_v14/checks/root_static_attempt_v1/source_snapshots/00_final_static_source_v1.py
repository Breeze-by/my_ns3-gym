"""Finite read-only consistency check, not a native/scientific consumer."""
from pathlib import Path
from decimal import Decimal
import ast
import hashlib
import json
import re
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261019_mr3_p2a_v14'
OPENING = 'a8e509726fa98cb9db1f01bc655e1b4eb8d63059'

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['rtk', 'proxy', 'git', *args], cwd=ROOT)

def load(path):
    return json.loads(path.read_text())

def same_blob(path, data):
    assert path.read_bytes() == data, str(path)

assert git('branch','--show-current').decode().strip() == 'main'
assert git('rev-parse','HEAD').decode().strip() == OPENING
json_count = ast_count = 0
for path in A.rglob('*'):
    assert not path.is_symlink()
    assert not {'__pycache__','build','install','native'}.intersection(path.relative_to(A).parts)
    if not path.is_file():
        continue
    assert path.stat().st_size < 5_000_000, str(path)
    if path.suffix == '.json':
        load(path); json_count += 1
    if path.suffix == '.py':
        ast.parse(path.read_text(), filename=str(path)); ast_count += 1

attempt_counts = {}
for name, count, rc in [('geometry_cpu_attempt_v1',19,0), ('geometry_cpu_attempt_v2',46,0),
                       ('handoff_cpu_attempt_v1',21,1), ('calibration_cpu_attempt_v1',12,0),
                       ('handoff_cpu_attempt_v2',34,1), ('combined_cpu_attempt_v1',92,0)]:
    directory = A/'checks'/name
    result = load(directory/'actual_wait.json')
    outer = load(directory/'root_actual_tool_receipt.json')
    assert result['actual_waited'] and result['source_unchanged']
    assert result['source_before'] == result['source_after']
    assert result['actual_returncode'] == outer['actual_tool_exit_code'] == rc
    console = directory/'console.log'
    assert sha(console) == result['console']['sha256']
    assert len(console.read_bytes()) == result['console']['bytes']
    assert int(re.search(r'Ran (\d+) tests', console.read_text())[1]) == count
    assert result['passed'] is (rc == 0)
    if rc == 0:
        assert console.read_text().rstrip().endswith('OK')
    for number, source in enumerate(result['source_before']):
        snapshot = directory/'source_snapshots'/f'{number:02d}_{Path(source["path"]).name}'
        assert sha(snapshot) == source['sha256'] and snapshot.stat().st_size == source['bytes']
        if name == 'combined_cpu_attempt_v1':
            assert sha(Path(source['path'])) == source['sha256']
    attempt_counts[name] = count

assert 'FAILED (failures=6)' in (A/'checks/handoff_cpu_attempt_v1/console.log').read_text()
assert 'FAILED (failures=2, errors=1)' in (A/'checks/handoff_cpu_attempt_v2/console.log').read_text()
copy_rows = []
for path in [A/'review_artifacts_copy_index_v2.json', A/'handoff_review_copy_index_v1.json',
             A/'delivery_design_originals/canonical_copy_index_v1.json',
             A/'checks/document_review_v1/copy_index.json',
             A/'checks/document_final_review_v1/copy_index.json']:
    copy_rows += load(path)['entries']
copy_rows.append(load(A/'scientific_contract_review_copy_v1.json'))
for row in copy_rows:
    path = ROOT/row['canonical']
    original = row['original']['path'] if isinstance(row['original'], dict) else row['original']
    assert sha(path) == row['sha256'] == sha(Path(original))
    assert path.stat().st_size == row['bytes']
candidate = A/'scientific_contract_candidate_v1.md'
review = load(A/'readonly_design_originals/mr3_p2a_v14_scientific_contract_independent_review_v1.json')
assert sha(candidate) == review['source']['sha256']
handoff_review = load(A/'readonly_design_originals/mr3_p2a_v14_handoff_independent_final_review_v1.json')
assert sha(A/'cpu/handoff_contract_v1.py') in json.dumps(handoff_review)

raw_index = load(A/'closed_data_only/mr3_p2a_v14_v13_minimum_lateral_artifact_index_v1.json')
manifest_path = W/'report/assets/20261019_mr3_p2a_v13/closed_continuation/manifest.json'
assert sha(manifest_path) == 'c0ce1e52e2132408c42ca99d7e6e0661259f67abc52055d2c8729cdbb87f61ee'
manifest = {r['original_path']: r for r in load(manifest_path)['files']}
for row in raw_index['six_raw_references']:
    path = Path(row['path']); before=path.stat()
    assert row['sha256'] == sha(path) == manifest[row['path']]['sha256']
    assert row['bytes'] == path.stat().st_size == manifest[row['path']]['bytes']
    after=path.stat()
    assert (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns,before.st_ctime_ns) == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns)

rel_log = str((W/'log.md').relative_to(ROOT))
old_log = git('show', OPENING+':'+rel_log)
assert (W/'log.md').read_bytes().startswith(old_log)
archive_path = W/'report/ARCHIVE_INDEX.json'
old_archive=json.loads(git('show',OPENING+':'+str(archive_path.relative_to(ROOT))))
archive=load(archive_path)
assert {k:v for k,v in archive.items() if k!='mr3_p2a_v14_contract_math_cpu_20261019'} == old_archive
env_path=W/'MR3_ENV_CONTRACT.md'
old_env=git('show',OPENING+':'+str(env_path.relative_to(ROOT))).decode()
new_env=env_path.read_text(); header=new_env.split('\n\n',2)
assert header[0]+'\n\n'+header[2] == old_env
for path in ['ros2_ws/ros2-multi-robot-automap/src', 'ros2_ws/ros2-multi-robot-automap/scripts',
             str((W/'mr3_learning').relative_to(ROOT))]:
    assert not git('diff',OPENING,'--name-only','--',path).strip()
assert Decimal('31596.4775930946018')+Decimal('2403.5224069053982') == Decimal('34000')
status=load(A/'status_and_follow_on_v1.json')
assert status['final_isolated_cpu_methods']==92 and status['new_native_runs']==status['new_gpu_calls']==0
assert not status['p2a_completed'] and not status['production_contract_enabled']

docs = [ROOT/'AGENTS.md', W/'AGENTS.md', W/'RESEARCH_PLAN.md', W/'IMPLEMENTATION_PLAN.md',
        W/'MR3_ENV_CONTRACT.md', W/'report/README.md', W/'report/20261019_mr3_p2a_v14.md',candidate,
        ROOT/'ros2_ws/ros2-multi-robot-automap/AGENTS.md',
        ROOT/'ros2_ws/ros2-multi-robot-automap/user_guide.md',
        ROOT/'ros2_ws/ros2-multi-robot-automap/launch_commands.md']
links=0
for path in docs:
    if path==candidate or path.name=='20261019_mr3_p2a_v14.md':
        content=path.read_text()
    else:
        diff=git('diff','--unified=0','--',str(path.relative_to(ROOT))).decode()
        content='\n'.join(line[1:] for line in diff.splitlines() if line.startswith('+') and not line.startswith('+++'))
    assert 'PENDING_ACTUAL_FINAL_CHECK' not in content
    for ref in re.findall(r'\[[^\]]*\]\(([^\n)]+)\)',content):
        if ref.startswith(('http://','https://','mailto:','#')):
            continue
        target=ref.strip('<>').split('#',1)[0]
        assert (path.parent/target).resolve().exists(), (path,ref)
        links += 1

result={'schema':'mr3-v14-root-final-static-review-v1','passed':True,
        'scope':'Read-only artifact/document/source consistency only; no unit rerun, native/scientific role, GPU or production enablement.',
        'json_parsed':json_count,'python_ast_parsed':ast_count,'exact_copy_originals':len(copy_rows),
        'cpu_attempt_counts':attempt_counts,'final_current_source_files':9,'new_or_full_document_links':links,
        'v13_canonical_raw_references_sha_checked':6,'original_log_append_only':True,
        'old_archive_entries_preserved':True,'production_source_diff_empty':True,
        'environment_normative_text_unchanged':True,'native_admission':False}
Path(sys.argv[1]).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False))
