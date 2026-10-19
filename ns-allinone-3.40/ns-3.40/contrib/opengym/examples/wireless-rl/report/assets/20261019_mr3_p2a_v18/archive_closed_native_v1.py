"""Package the closed V18 FAIL and actual accounting; no scientific execution."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
SOURCE = ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v18'
OUT = Path(__file__).resolve().parent/'closed_execution'
ARCHIVE = OUT/'native_closed_v1.tar.xz'
MANIFEST = OUT/'native_closed_manifest_v1.json'
FREEZE = 'ed2306e9fa100f6ada4ab6496a53a3bd08e58017'
OPENING = Decimal('32494.9044856606018')
CEILING = Decimal('52000')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b''):
            digest.update(chunk)
    return digest.hexdigest()


def proof(path):
    return {'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}


def exclusive(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')


def wait_fact(path,expected_code):
    value = json.loads(path.read_bytes())
    require(value['schema'] == 'mr3-reach-outer-actual-wait-v1' and value['scope'] == 'engineering'
            and value['actual_waited'] is True and type(value['actual_returncode']) is int
            and value['actual_returncode'] == expected_code and value['source_unchanged'] is True
            and value['source_before'] == value['source_after']
            and value['passed'] is (expected_code == 0) and not value['errors'],
            'outer actual wait facts differ: '+str(path))
    start,end = value['started_monotonic_ns'],value['ended_monotonic_ns']
    require(type(start) is int and type(end) is int and 0 < start < end,'outer actual ns clocks invalid')
    seconds = Decimal(end-start)/10**9
    require(seconds == Decimal(str(value['actual_child_wait_seconds'])),'outer fee differs from actual ns clocks')
    return value,seconds


def main():
    started = time.monotonic_ns()
    require(not OUT.exists(),'closed evidence destination already exists; never overwrite')
    matrix = Path('/tmp/mr3_p2a_reach_v18_matrix')
    summary = json.loads((matrix/'summary.json').read_bytes())
    require(summary['freeze'] == FREEZE and summary['all_submitted_children_waited'] is True
            and summary['gpu_calls'] == summary['optimizer_steps'] == 0,
            'matrix is not the actual closed V18 zero-GPU attempt')
    require([(row['stage'],row['status']) for row in summary['stages']] == [
        ('interface','FAIL'),('terminal','SKIPPED'),('reset','SKIPPED'),('deadline','SKIPPED')],
        'original failure/later skipped stages changed')
    absence = json.loads(Path('/tmp/mr3_p2a_reach_v18_absence.json').read_bytes())
    require(absence['passed'] is True and absence['all_saved_identities_absent'] is True
            and not any(absence[key] for key in ('present','unreadable','errors','pids_without_saved_start')),
            'external absence did not close')
    matrix_wait,matrix_seconds = wait_fact(Path('/tmp/mr3_p2a_reach_v18_matrix_wait/actual_wait.json'),1)
    absence_wait,absence_seconds = wait_fact(Path('/tmp/mr3_p2a_reach_v18_absence_wait/actual_wait.json'),0)
    require(matrix_seconds == Decimal('178.458480158') and absence_seconds == Decimal('0.183465165'),
            'actual V18 fees differ from retained waits')
    OUT.mkdir()
    copies = []
    for name,original in (
        ('matrix',matrix),('matrix_outer',Path('/tmp/mr3_p2a_reach_v18_matrix_wait')),
        ('preflight_outer',Path('/tmp/mr3_p2a_reach_v18_preflight_wait')),
        ('absence_outer',Path('/tmp/mr3_p2a_reach_v18_absence_wait'))):
        target = OUT/name
        original_files = sorted(path for path in original.rglob('*') if path.is_file())
        original_proofs = {str(path.relative_to(original)):proof(path) for path in original_files}
        shutil.copytree(original,target)
        require(sorted(str(path.relative_to(target)) for path in target.rglob('*') if path.is_file()) == sorted(original_proofs),
                'closed auxiliary tree copy inventory differs: '+name)
        for relative,before in original_proofs.items():
            current = proof(target/relative)
            require(all(current[key] == before[key] for key in ('sha256','bytes'))
                    and proof(original/relative) == before,'closed auxiliary copy/original changed: '+relative)
            copies.append({'path':current['path'],'original_path':before['path'],
                           'sha256':current['sha256'],'bytes':current['bytes']})
    for name,original in (('preflight.json',Path('/tmp/mr3_p2a_reach_v18_preflight.json')),
                          ('external_absence.json',Path('/tmp/mr3_p2a_reach_v18_absence.json'))):
        before = proof(original);target = OUT/name;shutil.copyfile(original,target)
        after = proof(target)
        require(all(after[key] == before[key] for key in ('sha256','bytes')) and proof(original) == before,
                'closed auxiliary JSON changed: '+name)
        copies.append({'path':str(target),'original_path':str(original),'sha256':after['sha256'],'bytes':after['bytes']})
    files = sorted(path for path in SOURCE.rglob('*') if path.is_file())
    require(files and all(not path.is_symlink() for path in files),'native source is empty or contains unhandled symlinks')
    rows = [{'path':str(path.relative_to(SOURCE)),'bytes':path.stat().st_size,'sha256':sha(path)} for path in files]
    with tarfile.open(ARCHIVE,'x:xz',preset=1) as tar:
        for path in files:tar.add(path,arcname=str(path.relative_to(SOURCE)),recursive=False)
    with tarfile.open(ARCHIVE,'r:xz') as tar:
        members = tar.getmembers()
        require([member.name for member in members] == [row['path'] for row in rows],'archive exact member inventory differs')
        for member,row in zip(members,rows):
            require(member.isfile(),'archive contains an unhandled non-file member')
            digest,size = hashlib.sha256(),0
            with tar.extractfile(member) as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):
                    digest.update(chunk);size += len(chunk)
            require(digest.hexdigest() == row['sha256'] and size == row['bytes'],
                    'full archive byte readback differs: '+member.name)
    for path,row in zip(files,rows):
        require(path.stat().st_size == row['bytes'] and sha(path) == row['sha256'],'native source changed: '+str(path))
    require(sorted(str(path.relative_to(SOURCE)) for path in SOURCE.rglob('*') if path.is_file()) == [row['path'] for row in rows],
            'native source file set changed')
    failure = None
    motion = SOURCE/'mr3_p2a_reach_v18_interface/worker0/episode001_open_101/motion_safety.jsonl'
    with motion.open('rb') as stream:
        for line_number,raw in enumerate(stream,1):
            if b'"kind":"reach_model_failure"' in raw:
                value = json.loads(raw)
                failure = {'path':str(motion.relative_to(SOURCE)),'line_number':line_number,
                           'line_sha256':hashlib.sha256(raw).hexdigest(),'record':value};break
    require(failure is not None and failure['record']['payload']['reason'] == 'initial HOLD has no complete pair certificate'
            and failure['record']['record_sequence'] == 43180,'first actual V18 failure differs')
    manifest = {'schema':'mr3-v18-closed-native-byte-archive-v1','source_freeze':FREEZE,'source_root':str(SOURCE),
        'source_files':rows,'source_bytes':sum(row['bytes'] for row in rows),'archive':proof(ARCHIVE),
        'all_archived_bytes_replayed':True,'source_unchanged':True,'scientific_pass_claimed':False,
        'native_experiment_reexecuted':False,'closed_auxiliary_copies':copies,'first_failure':failure}
    exclusive(MANIFEST,manifest)
    charged = matrix_seconds+absence_seconds;used = OPENING+charged;remaining = CEILING-used
    require(used == Decimal('32673.5464309836018') and remaining == Decimal('19326.4535690163982'),
            'actual cumulative accounting differs')
    fees = []
    for name,value,seconds in (('matrix_outer',matrix_wait,matrix_seconds),('absence_outer',absence_wait,absence_seconds)):
        path = OUT/name/'actual_wait.json'
        fees.append({'path':str(path.relative_to(ROOT)),'sha256':sha(path),'scope':'engineering',
            'actual_returncode':value['actual_returncode'],'actual_waited':True,'seconds':str(seconds),
            'charge_once_outer_includes_all_submitted_children':True})
    accounting = {'schema':'mr3-v18-closed-actual-engineering-accounting-v1','source_freeze':FREEZE,
        'opening_used_wall_seconds':str(OPENING),'engineering_ceiling_wall_seconds':str(CEILING),
        'actual_outer_fees':fees,'charged_this_version_seconds':str(charged),'cumulative_used_seconds':str(used),
        'remaining_seconds':str(remaining),'cpu_preparation_charged_to_native':False,
        'pilot_remaining_decisions':1870,'pilot_remaining_seconds':'2905.9547395464029',
        'final_only_validation_count_unchanged':3,'all_old_failures_preserved':True,
        'qualification_passed':False,'policy_stage_started':False}
    exclusive(OUT/'engineering_accounting_v1.json',accounting)
    ended = time.monotonic_ns()
    print(json.dumps({'schema':'mr3-v18-closed-packaging-completion-v1','passed_byte_integrity':True,
        'native_files':len(rows),'source_bytes':manifest['source_bytes'],'archive':manifest['archive'],
        'copied_auxiliary_files':len(copies),'external_saved_identity_count':absence['identity_count'],
        'charged_engineering_seconds':str(charged),'cumulative_used_seconds':str(used),'remaining_seconds':str(remaining),
        'packaging_started_monotonic_ns':started,'packaging_ended_monotonic_ns':ended,
        'packaging_cpu_wall_seconds':str(Decimal(ended-started)/10**9),
        'scientific_pass_claimed':False,'native_experiment_reexecuted':False}))


if __name__ == '__main__':
    main()
