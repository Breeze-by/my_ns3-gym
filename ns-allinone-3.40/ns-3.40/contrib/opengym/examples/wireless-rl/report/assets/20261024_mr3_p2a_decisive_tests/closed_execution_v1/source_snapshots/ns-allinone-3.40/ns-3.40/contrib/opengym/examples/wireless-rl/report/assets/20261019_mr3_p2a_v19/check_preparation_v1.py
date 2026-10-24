"""Standard-library V19 preparation evidence gate; never a scientific consumer.

verify_preparation_evidence() is shared by the generator and frozen preflight.
Historical V18 bytes keep their failure/source scope. Only fresh actual CPU
receipts are checked against current source. A new full native qualification
is still mandatory.
"""
import argparse
import ast
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import runpy
import subprocess
import time
from urllib.parse import unquote,urlsplit

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT/'ros2_ws/ros2-multi-robot-automap'
A = Path(__file__).resolve().parent
PRIOR = W/'report/assets/20261019_mr3_p2a_v18'
CLOSED = PRIOR/'closed_execution'
BASE = 'ed2306e9fa100f6ada4ab6496a53a3bd08e58017'
HELPER = W/'report/assets/20261019_mr3_p2a_v17/check_closed_preparation_v1.py'
HELPER_SHA = '940dd0b8ff5e68b53e35f6d9299e79d2798c8d42c8c66d52d1194a65be808d9e'
WAIT_SCHEMA = 'mr3-v15-finite-preparation-actual-child-wait-v1'
SCHEMA = 'mr3-v19-preparation-integrity-v1'
FORENSIC_V1_SCHEMA = 'mr3-v18-initial-hold-source-cadence-forensics-v1'
FORENSIC_SCHEMA = 'mr3-v18-initial-hold-source-cadence-forensics-v2'
FORENSIC_V1_SHA = 'ffd03c7d339ab591121a0bcab4673a0cba7600dac6abd578bd71c7c816d41f35'
FORENSIC_SHA = 'b5936b846193f280b3134215485ff167f3672a71dcead5d696f1428f9247ce00'
SENSOR_PROFILE = {
    'name':'mr3-reach-lidar-20hz-v1','sensor':'hls_lfcd_lds',
    'scope':'Generated SDF for explicitly selected reach profile only',
    'native_scan_update_rate_hz':20,'base_and_legacy_scan_update_rate_hz':5,
    'original_source_timestamps_retained':True,'observation_distribution_changed':True,
    'geometry_and_physical_safety_thresholds_changed':False,
    'full_new_same_freeze_qualification_required':True}
P = ROS/'src/multi_robot_exploration/multi_robot_exploration'
FORENSIC_SOURCES = (
    *(P/name for name in ('mr3_reach_geometry.py','mr3_reach_runtime.py','mr3_information.py',
                         'motion_safety.py','mr3_episode.py')),
    ROS/'src/slam_toolbox/src/slam_toolbox_multirobot.cpp',
    ROS/'src/slam_toolbox/src/slam_toolbox_common.cpp',
    ROS/'src/slam_toolbox/launch/online_async_multirobot_launch.py',
    ROS/'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py',
    ROS/'src/slam_toolbox/config/mapper_params_online_multi_async.yaml',
    ROS/'src/multi_robot/models/turtlebot3_waffle/model.sdf',
    ROS/'scripts/mr3_env_worker.py')


def require(value,reason):
    if not value:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(*args):
    return subprocess.check_output(['git',*map(str,args)],cwd=ROOT)


def load_helpers():
    require(sha(HELPER.read_bytes()) == HELPER_SHA,'immutable standard-library packaging helper differs')
    return runpy.run_path(str(HELPER))


def spec(inputs,path):
    path = Path(path); value = inputs.file(path,path.is_relative_to(ROOT))
    return {'path':str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
            'sha256':value['sha256'],'bytes':value['bytes']}


def copies(inputs):
    pairs = []
    for name,original in (
        ('matrix',Path('/tmp/mr3_p2a_reach_v18_matrix')),
        ('matrix_outer',Path('/tmp/mr3_p2a_reach_v18_matrix_wait')),
        ('preflight_outer',Path('/tmp/mr3_p2a_reach_v18_preflight_wait')),
        ('absence_outer',Path('/tmp/mr3_p2a_reach_v18_absence_wait'))):
        current = CLOSED/name
        left = {p.relative_to(current) for p in current.rglob('*') if p.is_file()}
        right = {p.relative_to(original) for p in original.rglob('*') if p.is_file()}
        require(left == right and left,'closed original/canonical inventory differs: '+name)
        pairs.extend((current/rel,original/rel) for rel in sorted(left))
    pairs.extend(((CLOSED/'preflight.json',Path('/tmp/mr3_p2a_reach_v18_preflight.json')),
                  (CLOSED/'external_absence.json',Path('/tmp/mr3_p2a_reach_v18_absence.json'))))
    for current,original in pairs:
        require(inputs.raw(current) == inputs.raw(original,False),'closed canonical copy differs from actual original: '+str(current))
    return len(pairs)


def closed_history(inputs,base):
    parse,wait_math = base['parse'],base['wait_math']
    copied = copies(inputs)
    manifest = inputs.document(CLOSED/'native_closed_manifest_v1.json')
    require(inputs.file(CLOSED/'native_closed_manifest_v1.json',True)['sha256'] ==
            '8361f6206e721bd415557193e7613c10adb5141e2249d2d39bebfe162b23abb6',
            'original full-byte closure manifest changed')
    rows = manifest['source_files']; archive = CLOSED/'native_closed_v1.tar.xz'
    require(manifest['schema'] == 'mr3-v18-closed-native-byte-archive-v1' and manifest['source_freeze'] == BASE
            and len(rows) == len({r['path'] for r in rows}) == 123
            and sum(r['bytes'] for r in rows) == manifest['source_bytes'] == 231835013
            and manifest['all_archived_bytes_replayed'] is True and manifest['source_unchanged'] is True
            and manifest['scientific_pass_claimed'] is False and manifest['native_experiment_reexecuted'] is False,
            'historical closed native archive scope/inventory differs')
    require(all(not Path(r['path']).is_absolute() and '..' not in Path(r['path']).parts
                and re.fullmatch('[0-9a-f]{64}',r['sha256']) for r in rows),'invalid native archive member declaration')
    proof = inputs.file(archive,True)
    require(proof['bytes'] == manifest['archive']['bytes'] == 10730740
            and proof['sha256'] == manifest['archive']['sha256'] ==
            '20dab3a2675d005b3e857b7765b119c11b0ba1365e0b47622388e5635ed3b956', 'historical archive actual bytes differ')
    failure = manifest['first_failure']['record']
    require(failure['record_sequence'] == 43180 and failure['kind'] == 'reach_model_failure'
            and failure['payload']['robot'] == 'tb1' and failure['payload']['clock_ns'] == 39220000000
            and failure['payload']['reason'] == 'initial HOLD has no complete pair certificate', 'historical first failure changed')
    fees = [wait_math(inputs.document(CLOSED/name/'actual_wait.json'),code,'mr3-reach-outer-actual-wait-v1')
            for name,code in (('matrix_outer',1),('absence_outer',0))]
    require(fees == [Decimal('178.458480158'),Decimal('0.183465165')],'actual outer fee facts differ')
    accounting = inputs.document(CLOSED/'engineering_accounting_v1.json')
    require(inputs.file(CLOSED/'engineering_accounting_v1.json',True)['sha256'] ==
            'aa9cb9a27ae101cf3002d6f47115609263e01e0d95494f97ff36292452de48cb',
            'original closed engineering ledger changed')
    used = Decimal('32494.9044856606018')+sum(fees); remaining = Decimal('52000')-used
    require(accounting['schema'] == 'mr3-v18-closed-actual-engineering-accounting-v1'
            and accounting['source_freeze'] == BASE and accounting['opening_used_wall_seconds'] == '32494.9044856606018'
            and Decimal(accounting['engineering_ceiling_wall_seconds']) == Decimal('52000')
            and Decimal(accounting['charged_this_version_seconds']) == sum(fees) == Decimal('178.641945323')
            and Decimal(accounting['cumulative_used_seconds']) == used == Decimal('32673.5464309836018')
            and Decimal(accounting['remaining_seconds']) == remaining == Decimal('19326.4535690163982')
            and accounting['qualification_passed'] is False and accounting['policy_stage_started'] is False
            and accounting['cpu_preparation_charged_to_native'] is False,'historical engineering accounting differs')
    require(len(accounting['actual_outer_fees']) == 2,'historical fee set differs')
    for fee,name,seconds,code in zip(accounting['actual_outer_fees'],('matrix_outer','absence_outer'),fees,(1,0)):
        path = CLOSED/name/'actual_wait.json'
        require(fee['path'] == str(path.relative_to(ROOT)) and fee['sha256'] == inputs.file(path,True)['sha256']
                and fee['actual_waited'] is True and fee['scope'] == 'engineering'
                and type(fee['actual_returncode']) is int and fee['actual_returncode'] == code
                and Decimal(fee['seconds']) == seconds
                and fee['charge_once_outer_includes_all_submitted_children'] is True,'fee is not bound once to its actual outer wait')
    absence = inputs.document(CLOSED/'external_absence.json')
    require(absence['schema'] == 'mr3-reach-external-process-absence-v1' and absence['passed'] is True
            and absence['all_saved_identities_absent'] is True and absence['scientific_pass_claimed'] is False
            and all(not absence[k] for k in ('present','unreadable','errors','pids_without_saved_start')),
            'original external absence did not close')
    identities = [(r['pid'],r['start_ticks']) for r in absence['identities']]
    require(len(identities) == len(set(identities)) == absence['identity_count'] == 49,'historical saved identity inventory differs')
    for pid,start in identities:
        require(type(pid) is int and type(start) is int and min(pid,start)>0,'invalid saved PID/start')
        try:
            suffix = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
            require(int(suffix[19]) != start,'saved identity present, including zombie: '+str(pid))
        except (FileNotFoundError,ProcessLookupError):pass
    summary = inputs.document(CLOSED/'matrix/summary.json')
    require(summary['freeze'] == BASE and summary['passed'] is False
            and summary['all_submitted_children_waited'] is True and summary['gpu_calls'] == summary['optimizer_steps'] == 0
            and [r['status'] for r in summary['stages']] == ['FAIL','SKIPPED','SKIPPED','SKIPPED'], 'old no-retry outcome changed')
    preflight = inputs.document(CLOSED/'preflight.json'); oldwait = inputs.document(CLOSED/'preflight_outer/actual_wait.json')
    oldseconds = wait_math(oldwait,0,'mr3-reach-outer-actual-wait-v1')
    require(oldseconds == Decimal('27.954691015') and oldwait['scope'] == 'cpu'
            and preflight['schema'] == 'mr3-reach-preflight-v1' and preflight['passed'] is True
            and preflight['freeze'] == BASE and preflight['plan_sha256'] ==
            '29294bba562f6e249166d6ffc4b4c20cc602f005d10d3c7f11ee598c9f1adb49','historical V18 preflight facts differ')
    for row in oldwait['source_before']:
        path = Path(row['path']); require(path.is_relative_to(ROOT),'old CPU source is outside canonical root')
        original = git('show',BASE+':'+str(path.relative_to(ROOT)))
        require(sha(original) == row['sha256'] and len(original) == row['bytes'],'historical preflight source pin differs')
    return {'source_freeze':BASE,'native_failure_retained':True,'first_failure_record_sequence':43180,
        'copied_original_files':copied,'archive':spec(inputs,archive),'native_files':123,'native_bytes':231835013,
        'saved_identities_absent':49,'charged_seconds':str(sum(fees)),'cumulative_used_seconds':str(used),
        'engineering_remaining_seconds':str(remaining),'old_preflight':{'passed':True,'seconds':str(oldseconds),
        'scope':'Historical V18 source/build/dispatch CPU preparation only; no V19 source or native credit'}}


def cpu_receipt(inputs,base,name,code=0,current=True):
    directory = A/'checks'/name
    wait = inputs.document(directory/'actual_wait.json')
    seconds = base['wait_math'](wait,code,WAIT_SCHEMA)
    require(wait['native_admission'] is False and wait['explicit_env'] == {
        'PYTHONNOUSERSITE':'1','PYTHONDONTWRITEBYTECODE':'1','PYTHONPATH':None},'fresh CPU scope/environment differs')
    rows = wait['source_before']; names = [row['path'] for row in rows]
    require(len(names) == len(set(names)) and rows,'fresh CPU source inventory is empty/duplicate')
    snapshots = set()
    for ordinal,row in enumerate(rows):
        path = Path(row['path']); require(path.is_relative_to(ROOT),'fresh source is outside canonical workspace')
        snapshot = directory/'source_snapshots'/f'{ordinal:02d}_{path.name}';snapshots.add(snapshot.name)
        raw = inputs.raw(snapshot)
        require(sha(raw) == row['sha256'] and len(raw) == row['bytes'],
                'CPU exact source/ordinal snapshot differs: '+str(path))
        if current:require(raw == inputs.raw(path),'fresh CPU source is not current: '+str(path))
    require({p.name for p in (directory/'source_snapshots').iterdir()} == snapshots,'fresh CPU snapshot inventory differs')
    console = directory/'console.log'; raw_console = inputs.raw(console)
    require(wait['console']['path'] == str(console) and wait['console']['sha256'] == sha(raw_console)
            and wait['console']['bytes'] == len(raw_console),'fresh CPU actual console SHA/bytes differs')
    inputs.file(directory/'actual_runner.py',True)
    return wait,raw_console,seconds


def actual_cpu(inputs,base,name,expected_tests=None,script=None,output=None,result=None,schema=None):
    directory = A/'checks'/name
    wait,raw_console,seconds = cpu_receipt(inputs,base,name)
    rows = wait['source_before'];names = [row['path'] for row in rows]
    if expected_tests is not None:
        require(expected_tests and SENSOR_ARGV,'fresh exact tests/command were not configured')
        require(wait['actual_argv'] == list(SENSOR_ARGV) and wait['cwd'] == str(W),
                'fresh actual ROS/conda finite CPU command/cwd differs')
        require(all(str(test) in names for test in expected_tests), 'actual selected test source omitted from snapshot inventory')
        expected_sources = {*map(str,(W/'mr3_learning').rglob('*.py')),*map(str,P.glob('*.py')),
                            *map(str,expected_tests),
                            str(ROS/'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'),
                            str(ROS/'src/multi_robot/models/turtlebot3_waffle/model.sdf')}
        require(set(names) == expected_sources,'fresh sensor/Information complete declared source inventory differs')
        passed = re.findall(rb'\b([1-9][0-9]*) passed\b',raw_console)
        unit = re.findall(rb'Ran ([1-9][0-9]*) tests in [0-9.]+s\s+OK\s*$',raw_console)
        require(len(passed) == len(unit) == 1
                and not re.search(rb'\b[0-9]+ (?:failed|errors?|skipped|xfailed|xpassed)\b|FAILED \(',raw_console,re.I),
                'fresh actual tests are not a positive all-passed result')
        require((int(passed[0]),int(unit[0]),len(rows),seconds) == (97,102,134,Decimal('67.038865175')),
                'final actual CPU v3 counts/source inventory/duration differ')
        details = {'pytest_passed':int(passed[0]),'unittest_passed':int(unit[0])}
    else:
        require(wait['actual_argv'] == ['/usr/bin/python3','-B',str(script),'--output',str(output)]
                and wait['cwd'] == str(ROOT) and str(script) in names,'fresh forensic actual command/entry differs')
        require(seconds == Decimal('17.16589449') and len(rows) == 13,
                'final actual forensic CPU v2 duration/source count differs')
        require(inputs.file(script,True)['sha256'] == FORENSIC_SHA,'forensic sealed helper changed')
        raw = inputs.raw(result);require(raw == inputs.raw(output,False),'fresh forensic canonical copy differs from actual original')
        data = base['parse'](raw)
        require(data['schema'] == schema and data['passed'] is True and data.get('native_admission') is False
                and data['errors'] == [] and data['actual_argv'] == [wait['actual_argv'][0],*wait['actual_argv'][2:]]
                and type(data['started_monotonic_ns']) is int and type(data['ended_monotonic_ns']) is int
                and wait['started_monotonic_ns'] <= data['started_monotonic_ns'] < data['ended_monotonic_ns'] <= wait['ended_monotonic_ns'],
                'fresh forensic result did not pass in its limited scope')
        summary = base['parse'](raw_console.decode().splitlines()[-1])
        require(summary['passed'] is True and summary['output'] == str(output),'forensic actual console/output differs')
        details = {'result':spec(inputs,result),'actual_output_path':str(output),'actual_output_sha256':sha(raw),'document':data}
    return {'passed':True,'seconds':str(seconds),'actual_cpu_wait':spec(inputs,directory/'actual_wait.json'),
        'source_inventory':[spec(inputs,Path(row['path'])) for row in rows],
        'native_or_qualification_credit':False,**details}


def retained_forensic_failure(inputs,base):
    name = 'initial_hold_forensic_cpu_attempt_v1'
    wait,console,seconds = cpu_receipt(inputs,base,name,1,False)
    script = A/'initial_hold_source_cadence_forensic_v1.py'
    original = Path('/tmp/mr3_p2a_v19_initial_hold_source_cadence_forensic_v1.json')
    canonical = A/'initial_hold_source_cadence_forensic_failed_result_v1.json'
    require(wait['actual_argv'] == ['/usr/bin/python3','-B',str(script),'--output',str(original)]
            and wait['cwd'] == str(ROOT) and seconds == Decimal('7.071966402'),
            'original forensic failed actual command/duration differs')
    raw = inputs.raw(canonical)
    require(raw == inputs.raw(original,False),'failed forensic original/canonical bytes differ')
    result = base['parse'](raw)
    require(result['schema'] == FORENSIC_V1_SCHEMA and result['freeze'] == BASE
            and result['passed'] is False and result['scientific_qualification'] is False
            and result['native_admission'] is False and result['original_failure_retained'] is True
            and result['errors'] == [{'message':"'transform'",'type':'KeyError'}]
            and result['source_before'] == result['source_after']
            and result['source_before']['sha256'] == FORENSIC_V1_SHA
            and result['source_before']['path'] == str(script)
            and result['actual_argv'] == [wait['actual_argv'][0],*wait['actual_argv'][2:]]
            and wait['started_monotonic_ns'] <= result['started_monotonic_ns'] < result['ended_monotonic_ns'] <= wait['ended_monotonic_ns'],
            'old forensic failure was changed/reclassified')
    summary = base['parse'](console.decode().splitlines()[-1])
    require(summary['passed'] is False and summary['output'] == str(original),
            'old forensic failed console/output differs')
    ownrow = wait['source_before'][0]
    require(ownrow['path'] == str(script) and all(ownrow[k] == result['source_before'][k] for k in ('sha256','bytes')),
            'old forensic entry is not bound to failed actual wait')
    require(inputs.file(script,True)['sha256'] == FORENSIC_V1_SHA,'original failed forensic helper changed')
    return {'passed':False,'retained':True,'seconds':str(seconds),'actual_returncode':1,
            'actual_wait':spec(inputs,A/'checks'/name/'actual_wait.json'),'result':spec(inputs,canonical),
            'error':{'type':'KeyError','message':"'transform'"},
            'scope':'Original failed CPU forensic attempt only; no current source qualification'}


def historical_sensor_cpu(inputs,base):
    name = 'sensor_profile_cpu_attempt_v1'
    wait,console,seconds = cpu_receipt(inputs,base,name,0,False)
    command = 'set -e; source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; (cd "$1/src/multi_robot_exploration"; /usr/bin/python3 -B -m pytest -q test/test_mr3_drive_launch.py test/test_mr3_adapter_launch.py); cd "$2"; exec env -u PYTHONPATH /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest mr3_learning.tests.test_audit_action_trace mr3_learning.tests.test_reach_controlled_dispatch mr3_learning.tests.test_reach_preparation_entry mr3_learning.tests.test_audit_reach_cadence'
    require(wait['actual_argv'] == ['/bin/bash','-c',command,'mr3-lidar20hz-regression',str(ROS),str(W)]
            and wait['cwd'] == str(W) and seconds == Decimal('24.367975479')
            and re.search(rb'\b28 passed\b',console) and re.search(rb'Ran 42 tests in [0-9.]+s\s+OK\s*$',console),
            'original sensor CPU selected command/result differs')
    return {'passed':True,'retained':True,'seconds':str(seconds),'pytest_passed':28,'unittest_passed':42,
            'actual_wait':spec(inputs,A/'checks'/name/'actual_wait.json'),
            'scope':'Original sensor-generation CPU attempt only; not current Information source qualification'}


def retained_information_cpu_failure(inputs,base):
    name = 'sensor_information_cpu_attempt_v2'
    wait,console,seconds = cpu_receipt(inputs,base,name,1,False)
    require(wait['actual_argv'] == list(SENSOR_ARGV) and wait['cwd'] == str(W)
            and seconds == Decimal('58.060315136') and re.search(rb'\b97 passed\b',console)
            and re.search(rb'Ran 100 tests in [0-9.]+s\s+FAILED \(failures=7, errors=1\)\s*$',console),
            'original Information CPU v2 failure command/result differs')
    return {'passed':False,'retained':True,'seconds':str(seconds),'actual_returncode':1,
            'pytest_passed':97,'unittest_tests':100,'unittest_failures':7,'unittest_errors':1,
            'actual_wait':spec(inputs,A/'checks'/name/'actual_wait.json'),
            'scope':'Original failed production peer-control loader integration plus fixture CPU attempt; no current source qualification'}


def forensic_contract(inputs,base,data,cpu):
    require(data['freeze'] == BASE and data['scope'] == 'closed_evidence_forensics_only'
            and data['original_failure_retained'] is True and data['scientific_qualification'] is False,
            'forensics reclassified or rescoped the old failure')
    helper = A/'initial_hold_source_cadence_forensic_v2.py'
    own = data['source_before']
    require(own == data['source_after'] and own['path'] == str(helper)
            and own['sha256'] == FORENSIC_SHA and own['bytes'] == inputs.file(helper,True)['bytes'],
            'forensic entry source was not stable and sealed')
    current = data['current_sources_before']
    require(current == data['current_sources_after']
            and [row['path'] for row in current] == list(map(str,FORENSIC_SOURCES)),
            'forensic twelve-current-source inventory/stability differs')
    inventory = {str(ROOT/row['path']) if not Path(row['path']).is_absolute() else row['path']:row
                 for row in cpu['source_inventory']}
    require(set(inventory) == {str(helper),*map(str,FORENSIC_SOURCES)},
            'forensic actual CPU wait did not snapshot exactly helper and twelve source dependencies')
    for row in [own,*current]:
        require(all(row[key] == inventory[row['path']][key] for key in ('sha256','bytes')),
                'forensic current source differs from actual CPU snapshot: '+row['path'])
        require(all(type(row[key]) is int and row[key] >= 0 for key in ('dev','inode','mtime_ns')),
                'forensic source stat evidence malformed')
    prior = data['prior_attempt']
    require(prior['passed'] is False and prior['actual_returncode'] == 1
            and prior['failure_retained'] is True and prior['native_admission'] is False
            and prior['errors'] == [{'type':'KeyError','message':"'transform'"}],
            'forensic v2 did not retain actual failed v1')
    prior_rows = [prior[key] for key in ('source','canonical_result','actual_cpu_wait','original_output')]
    require(data['prior_inputs_before'] == data['prior_inputs_after'] == prior_rows,
            'forensic v1 original four-input inventory/stability differs')
    expected_prior = [A/'initial_hold_source_cadence_forensic_v1.py',
        A/'initial_hold_source_cadence_forensic_failed_result_v1.json',
        A/'checks/initial_hold_forensic_cpu_attempt_v1/actual_wait.json',
        Path('/tmp/mr3_p2a_v19_initial_hold_source_cadence_forensic_v1.json')]
    for row,path in zip(prior_rows,expected_prior):
        actual = inputs.file(path,path.is_relative_to(ROOT))
        require(row['path'] == str(path) and all(row[k] == actual[k] for k in ('sha256','bytes')),
                'forensic v2 prior attempt binding differs: '+str(path))
    frozen = data['frozen_source_proofs']
    require([row['path'] for row in frozen] == [str(p.relative_to(ROOT)) for p in FORENSIC_SOURCES],
            'forensic old source inventory differs')
    for row in frozen:
        require(row['freeze'] == BASE and row['actual_argv'] == ['git','show',BASE+':'+row['path']]
                and row['returncode'] == 0 and sha(git('show',BASE+':'+row['path'])) == row['sha256'],
                'forensic old source is not the original Git freeze')
    original = data['inputs_before']
    episode = ROS/'log/mr3_p2a_reach_v18/mr3_p2a_reach_v18_interface/worker0/episode001_open_101'
    expected = [episode/name for name in ('metadata.json','motion_safety.jsonl','information_states.jsonl',
                                         'drive_model_tb1.sdf','drive_model_tb2.sdf','drive_model_tb3.sdf')]
    require(original == data['inputs_after'] and [row['path'] for row in original] == list(map(str,expected)),
            'forensic historical raw evidence inventory/stability differs')
    manifest = inputs.document(CLOSED/'native_closed_manifest_v1.json')
    members = {row['path']:row for row in manifest['source_files']}
    for row,path in zip(original,expected):
        archived = members[str(path.relative_to(Path(manifest['source_root'])))]
        require(all(row[key] == archived[key] for key in ('sha256','bytes')),
                'forensic input differs from closed full-byte archive manifest: '+str(path))
    failure,decision = data['first_failure'],data['first_decision']
    require(failure['reference']['record_sequence'] == 43180
            and failure['payload'] == manifest['first_failure']['record']['payload']
            and decision['reference']['record_sequence'] == 43182,
            'forensic first failure/decision differs from retained failure')
    pairs = data['independent_hold_pair_substitution']
    require([row['robots'] for row in pairs] == [['tb1','tb2'],['tb1','tb3'],['tb2','tb3']]
            and [row['map_and_raw_necessary'] for row in pairs] == [True,False,False]
            and data['actual_generated_laser_rate_hz'] == dict.fromkeys(('tb1','tb2','tb3'),'5'),
            'forensic old HOLD substitution/generated sensor facts differ')
    require(set(data['tf_source_cadence']) == {'tb1','tb2','tb3'}
            and data['interpretation']['actual_plant_dynamic_counterexample_established_by_this_analysis'] is False
            and data['interpretation']['prospective_20Hz_changes_real_sensor_observation_distribution'] is True
            and data['interpretation']['prospective_20Hz_requires_fresh_freeze_and_full_native_qualification'] is True,
            'forensic interpretation overclaims physical/new-source qualification')
    original_peers = data['first_decision']['payload']['received_peers']
    require(data['original_received_peers_unchanged'] is True
            and data['peer_wire_transform_missing_preserved'] is True
            and data['peer_fields_added_or_reconstructed'] is False
            and set(original_peers) == {'tb2','tb3'}
            and all('transform' not in peer for peer in original_peers.values())
            and sha(json.dumps(original_peers,sort_keys=True,separators=(',',':'),allow_nan=False).encode())
                == data['original_received_peers_sha256']
            and set(data['actual_envelope_source_provenance']) == {'tb1','tb2','tb3'}
            and set(data['peer_tf_provenance']) == {'tb2','tb3'},
            'forensic v2 altered missing original wire fields or lacks actual source provenance')
    for robot,chain in data['peer_tf_provenance'].items():
        envelope = data['matched_information_publication']['payload']['envelopes'][robot]
        require(chain == data['actual_envelope_source_provenance'][robot]
                and chain['transform'] == envelope['payload']['transform'],
                'forensic transform did not come from original actual Information envelope')
    records = sum(data['motion_kind_counts_whole_trace'].values())
    unique = {robot:row['unique_source_count'] for robot,row in data['tf_source_cadence'].items()}
    require(records == 46135 and unique == {'tb1':196,'tb2':186,'tb3':181}
            and all(row['most_common_source_interval_ns'] == 200000000
                    and sum(row['positive_source_interval_ns_histogram'].values()) == row['unique_source_count']-1
                    for row in data['tf_source_cadence'].values()),
            'forensic whole-trace/source-cadence facts differ')
    return {'retained_failure_record':43180,'first_postfailure_decision_record':43182,
            'old_generated_sensor_rate_hz':5,'raw_archive_inputs':6,'current_sources':12,
            'motion_records':records,'unique_tf_sources':unique,'modal_tf_source_interval_ns':200000000,
            'old_frozen_sources':12,'old_source_scope':'Historical V18 only; not a V19 source qualification'}


def evidence(inputs,base):
    history = closed_history(inputs,base)
    preserved = {'sensor_profile_cpu_v1':historical_sensor_cpu(inputs,base),
                 'sensor_information_cpu_v2':retained_information_cpu_failure(inputs,base),
                 'initial_hold_forensic_cpu_v1':retained_forensic_failure(inputs,base)}
    # These declarations are sealed against the actual finite runner below.
    tests = SENSOR_TESTS
    sensor = actual_cpu(inputs,base,'sensor_information_cpu_attempt_v3',expected_tests=tests)
    forensic = actual_cpu(inputs,base,'initial_hold_forensic_cpu_attempt_v2',
        script=A/'initial_hold_source_cadence_forensic_v2.py',
        output=Path('/tmp/mr3_p2a_v19_initial_hold_source_cadence_forensic_v2.json'),
        result=A/'initial_hold_source_cadence_forensic_result_v2.json',schema=FORENSIC_SCHEMA)
    data = forensic.pop('document')
    forensic['bounded_facts'] = forensic_contract(inputs,base,data,forensic)
    return {'schema':'mr3-v19-prospective-source-preparation-v1','passed':True,
        'scientific_pass_claimed':False,'native_admission':False,'native_or_qualification_credit':False,
        'qualification_passed':False,
        'fresh_full_native_qualification_required':True,'old_source_credit_reused':False,
        'scope':'Historical closed failure preservation plus fresh finite CPU source/profile checks and read-only forensics; no native or continuous physical credit',
        'failed_predecessor':history,'preserved_preparation_attempts':preserved,
        'sensor_profile_cpu':sensor,'initial_hold_forensics':forensic}


SENSOR_TESTS = (
    *(ROS/'src/multi_robot_exploration/test'/name for name in ('test_mr3_drive_launch.py',
        'test_mr3_adapter_launch.py','test_mr3_information_reach.py',
        'test_mr3_reach_runtime_independent.py','test_motion_safety_reach.py')),
    *(W/'mr3_learning/tests'/name for name in ('test_audit_action_trace.py','test_audit_reach_information.py',
        'test_audit_reach_peer_control.py','test_audit_reach_runtime.py','test_reach_controlled_dispatch.py',
        'test_reach_preparation_entry.py','test_audit_reach_cadence.py')))
SENSOR_ARGV = ('/bin/bash','-c',
    'set -e; source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; (cd "$1/src/multi_robot_exploration"; /usr/bin/python3 -B -m pytest -q test/test_mr3_drive_launch.py test/test_mr3_adapter_launch.py test/test_mr3_information_reach.py test/test_mr3_reach_runtime_independent.py test/test_motion_safety_reach.py); cd "$2"; exec env -u PYTHONPATH /home/zhuyulab/miniconda3/envs/ns3gym/bin/python -B -m unittest mr3_learning.tests.test_audit_action_trace mr3_learning.tests.test_audit_reach_information mr3_learning.tests.test_audit_reach_peer_control mr3_learning.tests.test_audit_reach_runtime mr3_learning.tests.test_reach_controlled_dispatch mr3_learning.tests.test_reach_preparation_entry mr3_learning.tests.test_audit_reach_cadence',
    'mr3-lidar20hz-information-regression',str(ROS),str(W))


def verify_preparation_evidence():
    """Generator/preflight entry; current bytes suffice before Git staging."""
    base = load_helpers()
    class CurrentInputs(base['Inputs']):
        def file(self,path,staged=False):return super().file(path,False)
    inputs = CurrentInputs();inputs.file(HELPER);inputs.file(Path(__file__).resolve())
    proof = evidence(inputs,base);inputs.finish()
    artifacts = sorted(path for path in inputs.bindings if path.is_relative_to(ROOT) and not path.is_relative_to(ROS/'log'))
    return proof,artifacts


def plan_check(inputs,path,digest,proof):
    require(digest and inputs.file(path,True)['sha256'] == digest,'actual plan SHA differs')
    plan = inputs.document(path)
    require(plan['prospective_preparation_requirement'] == proof,'plan preparation proof differs from current actual evidence')
    require(plan['sensor_source_profile'] == SENSOR_PROFILE,'plan real sensor profile declaration differs')
    for name,expected in plan['source_bindings'].items():
        source = Path(name) if Path(name).is_absolute() else ROOT/name
        require(inputs.file(source,True)['sha256'] == expected,'current/staged frozen source differs: '+name)
    binding = inputs.document(Path(plan['custody_binding']))
    require(len(binding['binaries']) == len(plan['library_bindings']) == 10,'ten-ELF inventory differs')
    for row in binding['binaries'].values():
        current = inputs.file(Path(row['path']))
        require(current['sha256'] == row['sha256'] == plan['library_bindings'][row['path']]
                and current['bytes'] == row['bytes'] and str(Path(row['path']).resolve(strict=True)) == row['resolved_path'],
                'actual native ELF differs: '+row['path'])
    return {'plan_sha256':digest,'frozen_source_count':len(plan['source_bindings']),'actual_elf_count':10}


def syntax_links(inputs,staged):
    selected = set(git('diff',*(['--cached'] if staged else []),'--name-only',BASE).decode().splitlines())
    if not staged:selected.update(git('ls-files','--others','--exclude-standard').decode().splitlines())
    asts = jsons = links = 0
    parse_json = load_helpers()['parse']
    for name in sorted(selected):
        path = ROOT/name
        require(not name.startswith(('ros2_ws/ros2-multi-robot-automap/build/','ros2_ws/ros2-multi-robot-automap/install/',
                                     'ros2_ws/ros2-multi-robot-automap/log/'))
                and path.suffix not in ('.so','.o','.a','.elf','.pt','.pth','.ckpt','.bag','.db3','.mcap'), 'unintended generated/runtime/ELF artifact selected: '+name)
        if not path.is_file():continue
        raw = inputs.raw(path,staged)
        if path.suffix == '.py':ast.parse(raw,filename=str(path));asts += 1
        elif path.suffix == '.json':parse_json(raw);jsons += 1
        elif path.suffix == '.md':
            text = raw.decode()
            if path == W/'log.md':
                prefix = git('show',BASE+':'+name);require(raw.startswith(prefix),'shared log lost its historical prefix');text = raw[len(prefix):].decode()
            text = re.sub(r'```.*?```|`[^`]*`','',text,flags=re.S)
            targets = re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',text)
            targets += re.findall(r'^\s*\[[^\]]+\]:\s*(\S+)',text,flags=re.M)
            for target in targets:
                target = target.strip().split(' "',1)[0].strip('<>')
                parsed = urlsplit(target)
                if parsed.scheme or not parsed.path:continue
                require((path.parent/unquote(parsed.path)).resolve().exists(),'broken active local Markdown link: '+name+' -> '+target);links += 1
    require(subprocess.run(['git','diff','--check'],cwd=ROOT).returncode == 0,'working diff check failed')
    if staged:require(subprocess.run(['git','diff','--cached','--check'],cwd=ROOT).returncode == 0,'staged diff check failed')
    return {'selected_files':len(selected),'ast_parsed':asts,'json_parsed':jsons,'local_links_checked':links}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--plan',type=Path)
    parser.add_argument('--plan-sha256')
    parser.add_argument('--staged',action='store_true')
    args = parser.parse_args();require(not args.output.exists(),'exclusive output exists')
    require(args.output.resolve().is_relative_to(Path('/tmp')),'output must be outside freeze in /tmp')
    started = time.monotonic_ns();base = load_helpers();index = sha(git('ls-files','--stage','-z'))
    class CliInputs(base['Inputs']):
        def file(self,path,staged=False):return super().file(path,args.staged and staged)
    inputs = CliInputs();metrics = {};errors = []
    try:
        inputs.file(HELPER,args.staged);inputs.file(Path(__file__).resolve(),args.staged)
        proof = evidence(inputs,base);metrics['preparation_evidence'] = proof
        if args.plan:metrics['plan'] = plan_check(inputs,args.plan,args.plan_sha256,proof)
        metrics['static'] = syntax_links(inputs,args.staged);inputs.finish()
        require(sha(git('ls-files','--stage','-z')) == index,'Git index changed during checker')
    except (OSError,ValueError,KeyError,TypeError,IndexError,ArithmeticError,SyntaxError,subprocess.SubprocessError) as error:
        errors.append(type(error).__name__+': '+str(error))
    result = {'schema':SCHEMA,'passed':not errors,'scientific_pass_claimed':False,'native_admission':False,
        'qualification_passed':False,'fresh_full_native_qualification_required':True,'native_runs':0,'gpu_calls':0,
        'started_monotonic_ns':started,'ended_monotonic_ns':time.monotonic_ns(),
        'staged_bytes_checked':args.staged,'metrics':metrics,'errors':errors,'input_bindings':list(inputs.bindings.values())}
    with args.output.open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps({'schema':SCHEMA,'passed':result['passed'],'errors':errors,'output':str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
