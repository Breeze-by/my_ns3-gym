"""Read-only staged V18 packaging checks; no research consumer is executed.

The expected plan SHA is a CLI input so the plan can bind this helper without
a self-reference. CPU receipts remain CPU evidence; the failed V17 native
attempt and its original bytes are preserved.
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
from urllib.parse import unquote, urlsplit

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT/'ros2_ws/ros2-multi-robot-automap'
A = Path(__file__).resolve().parent
PRIOR = W/'report/assets/20261019_mr3_p2a_v17'
CLOSED = PRIOR/'closed_execution'
BASE = '023e488811743b3f325538d2854205466925c5c4'
SCHEMA = 'mr3-v18-continuation-preparation-integrity-v1'
WAIT_SCHEMA = 'mr3-v15-finite-preparation-actual-child-wait-v1'
REPLAY_OUTPUT = Path('/tmp/mr3_p2a_reach_v18_closed_prewarm_replay.json')
TRACE_SHA = '7f26ab78d030bd65ae9a97544a2f10538ec67e918808c821a0159c155d57ed1d'
PRIOR_HELPER_SHA = '940dd0b8ff5e68b53e35f6d9299e79d2798c8d42c8c66d52d1194a65be808d9e'
STATIC_HELPER_SHA = '9390062d1dfe47e14fa71792048a486498d35fa3988e502ab259984ea695b75c'
RUNTIME_PACKAGE = ROS/'src/multi_robot_exploration/multi_robot_exploration'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], cwd=ROOT)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_spec(inputs,path):
    path = Path(path)
    proof = inputs.file(path,path.is_relative_to(ROOT) and not path.is_relative_to(ROS/'log'))
    return {'path':str(path.relative_to(ROOT)),'sha256':proof['sha256']}


def result_execution(inputs,wait_math,parse,name,script_name,result_name,output_name,schema):
    """Bind a real CPU result to its command, source snapshots and canonical copy."""
    directory = A/'checks'/name
    value = inputs.document(directory/'actual_wait.json')
    script, output = A/script_name, Path('/tmp')/output_name
    command = value['actual_argv']
    direct = ['/usr/bin/python3','-B',str(script),'--output',str(output)]
    wrapper = ['/bin/bash','-c',
        'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B "$2" --output "$3"']
    is_burst = script_name == 'ros_storage_queue_burst_v1.py'
    expected_command = [*wrapper,'mr3-storage-queue-burst',str(ROS),str(script),str(output)] if is_burst else direct
    require(command == expected_command,
            'unexpected actual finite CPU entry/output command: '+name)
    sources = [Path(row['path']) for row in value['source_before']]
    dependencies = [RUNTIME_PACKAGE/(name+'.py') for name in (
        'motion_safety','mr3_reach_runtime','mr3_episode','mr3_drive_phase','mr3_safety_intent',
        'mr3_reach_geometry','mr3_velocity_metric','__init__')]
    expected_sources = [script,*dependencies] if is_burst else [script,RUNTIME_PACKAGE/'motion_safety.py',
        ROS/'src/multi_robot/src/mr3_gazebo_diff_drive.cpp',ROS/'scripts/mr3_env_worker.py',
        CLOSED/'native_closed_manifest_v1.json',A/'closed_prewarm_replay_failed_result_v1.json',
        A/'checks/closed_prewarm_cpu_attempt_v1/actual_wait.json']
    require(sources == expected_sources, 'actual CPU source inventory/order differs: '+name)
    wait,console,cpu = check_cpu(inputs,wait_math,name,sources,command,W)
    canonical = A/result_name
    raw = inputs.raw(canonical)
    require(raw == inputs.raw(output,False), 'CPU canonical result is not the actual original output: '+name)
    result = parse(raw)
    require(result.get('schema') == schema and result.get('passed') is True
            and result.get('scientific_pass_claimed') is False and result.get('native_admission') is False
            and result.get('gpu_calls') == 0 and result.get('errors') == [],
            'actual prospective CPU result did not pass in its limited scope: '+name)
    start,end = result['started_monotonic_ns'],result['ended_monotonic_ns']
    require(type(start) is int and type(end) is int
            and wait['started_monotonic_ns'] <= start < end <= wait['ended_monotonic_ns'],
            'internal execution clocks lie outside the actual child wait: '+name)
    summary = parse(console.decode().splitlines()[-1])
    require(summary.get('schema') == schema and summary.get('passed') is True
            and summary.get('errors') == [] and summary.get('output') == str(output),
            'actual console differs from canonical output: '+name)
    cpu.update(passed=True,entry=file_spec(inputs,script),
        actual_cpu_wait=file_spec(inputs,directory/'actual_wait.json'),result=file_spec(inputs,canonical),
        actual_output_path=str(output),actual_output_sha256=sha(raw),native_or_qualification_credit=False)
    return result,wait,cpu


def check_forensic(inputs,wait_math,parse):
    result,wait,cpu = result_execution(inputs,wait_math,parse,'missing_storage_forensic_cpu_attempt_v1',
        'missing_storage_receipt_review_v1.py','missing_storage_receipt_review_result_v1.json',
        'mr3_p2a_reach_v18_missing_storage_review.json','mr3-v18-missing-storage-receipt-review-v1')
    require(result.get('old_native_failure_reclassified') is False
            and result.get('old_replay_failure_reclassified') is False
            and result.get('new_native_runs') == result.get('tracker_calls') == 0
            and result.get('source_freeze') == BASE
            and result.get('epoch') == 'mr3_p2a_reach_v17_interface_w0_e1_72f1a48b',
            'forensic PASS reclassified old failure or exceeds original evidence scope')
    findings = result['findings']; robots = findings['robots']
    require(set(robots) == {'tb1','tb2','tb3'}, 'forensics omitted a robot')
    for robot,row in robots.items():
        require(row['missing_from_motion_count'] == len(row['missing_from_motion_cmd_sequences']) == 833
                and row['missing_from_worker_count'] == len(row['missing_from_worker_cmd_sequences'])
                    == {'tb1':10,'tb2':8,'tb3':10}[robot]
                and row['received_motion_mismatch_count'] == row['received_worker_mismatch_count'] == 0
                and row['matching_motion_receipt_count'] == 0 and row['native_original_status_lines']
                and row['worker_original_receipt_lines'], 'original missing receipt evidence differs: '+robot)
    qos = findings['qos_source_evidence']
    waited = {row['path']:row for row in wait['source_before']}
    for name,depth in (('native_publisher',1),('motion_subscriber',256),('worker_subscriber',1)):
        row = qos[name]; source = Path(row['path'])
        require(row['historical']['depth'] == 1 and row['current']['depth'] == depth
                and row['current_source_sha256'] == inputs.file(source,True)['sha256']
                and str(source) in waited and waited[str(source)]['sha256'] == row['current_source_sha256'],
                'actual forensic source inventory/QoS differs: '+name)
    prior = findings['preserved_failed_replay']
    require(prior['passed'] is False and prior['actual_returncode'] == 1
            and Decimal(prior['actual_child_wait_seconds']) == Decimal('269.896902167')
            and prior['full_suffix_scanned'] is True and prior['new_faults'] == {}
            and prior['first_fault'] is None and prior['closed_tail_error_count'] == 3,
            'forensics did not preserve original complete failed replay')
    cpu.update(missing_motion_receipts_per_robot=833,missing_worker_receipts={'tb1':10,'tb2':8,'tb3':10},old_failure_reclassified=False,
        scope='Original missing-data forensics only; no old receipt reconstruction or native credit')
    return cpu


def check_burst(inputs,wait_math,parse):
    result,wait,cpu = result_execution(inputs,wait_math,parse,'ros_storage_queue_cpu_attempt_v1',
        'ros_storage_queue_burst_v1.py','ros_storage_queue_burst_result_v1.json',
        'mr3_p2a_reach_v18_ros_storage_queue_burst.json','mr3-v18-ros-storage-queue-burst-v1')
    require(Decimal(cpu['seconds']) <= 45 and result['actual_internal_wall_ns'] ==
            result['ended_monotonic_ns']-result['started_monotonic_ns'] <= 45_000_000_000
            and result.get('general_losslessness_proved') is False
            and result.get('old_missing_ack_reconstructed') is False
            and result.get('native_runs') == result.get('optimizer_steps') == 0
            and result['ros_domain_id'] == result['actual_context_domain_id'] == 222
            and result['declared_burst_size'] == 128
            and result['production_builder'] == 'multi_robot_exploration.motion_safety.storage_receipt_qos',
            'real ROS burst exceeded finite scope or bound')
    for name,depth in (('publisher',1),('legacy',1),('reach',256)):
        require(result['configured_actual_entities'][name]['qos']['depth'] == depth,
                'actual ROS entity QoS depth differs: '+name)
    expected = list(range(1,129)); ids = result['received_ids']; legacy = ids['legacy']
    require(ids['reach'] == expected and 0 < len(legacy) < 128 and legacy[-1] == 128
            and legacy == sorted(set(legacy)), 'actual delayed queue contrast did not hold')
    publications = result['publications']; delayed = result['delayed_spin_started_wall_monotonic_ns']
    require([row['id'] for row in publications] == expected
            and all(row['all_acked'] is True and row['matched_subscriptions'] == 2
                    and row['publish_started_wall_monotonic_ns'] <= row['publish_completed_wall_monotonic_ns']
                    <= row['wait_for_all_acked_started_wall_monotonic_ns']
                    <= row['wait_for_all_acked_completed_wall_monotonic_ns'] <= delayed for row in publications),
            'actual matched burst publications/acknowledgments incomplete')
    for arm,rows in result['callbacks'].items():
        require([row['id'] for row in rows] == ids[arm]
                and all(row['valid'] is True and row['callback_wall_monotonic_ns'] >= delayed
                        and row['message'] == publications[row['id']-1]['message']
                        and row['raw_json'] == publications[row['id']-1]['raw_json'] for row in rows),
                'actual delayed callbacks differ from whole published synthetic ACKs')
    rows = result['source_before']
    require(len(rows) == 6 and result['source_unchanged'] is True and rows == result['source_after'],
            'burst runtime dependencies were not bound unchanged')
    waited = {row['path']:row for row in wait['source_before']}
    for row in rows:
        proof = inputs.file(row['path'],Path(row['path']).is_relative_to(ROOT))
        require(all(proof[key] == row[key] for key in ('sha256','bytes'))
                and (not Path(row['path']).is_relative_to(ROOT) or (row['path'] in waited
                    and all(waited[row['path']][key] == row[key] for key in ('sha256','bytes')))),
                'burst actual dependency omitted by external wait/current source')
    cleanup = result['cleanup']
    require(len(cleanup) == 5 and sum(row['operation'] == 'destroy_node' and row.get('completed') is True for row in cleanup) == 3
            and any(row['operation'] == 'executor_shutdown' and row.get('returned') is True for row in cleanup)
            and any(row['operation'] == 'rclpy_shutdown' and row.get('context_ok_after') is False for row in cleanup)
            and all(not row.get('error') for row in cleanup), 'actual ROS cleanup incomplete')
    cpu.update(reach_received=128,legacy_received=len(legacy),scope='Finite matched real DDS CPU burst only; no general losslessness/native credit')
    return cpu


def check_cpu(inputs, wait_math, name, expected_sources, argv, cwd, expected_seconds=None,
              returncode=0, historical=False):
    directory = A/'checks'/name
    value = inputs.document(directory/'actual_wait.json')
    seconds = wait_math(value, returncode, WAIT_SCHEMA)
    require(value.get('native_admission') is False and value['actual_argv'] == argv
            and value['cwd'] == str(cwd)
            and value.get('explicit_env') == {
                'PYTHONNOUSERSITE':'1', 'PYTHONDONTWRITEBYTECODE':'1', 'PYTHONPATH':None},
            'CPU actual command/environment/scope differs: '+name)
    if expected_seconds is not None:
        require(seconds == Decimal(expected_seconds), 'actual CPU seconds differ: '+name)
    rows = value['source_after']
    require([row['path'] for row in rows] == [str(path) for path in expected_sources],
            'CPU source inventory/order differs: '+name)
    snapshots = set()
    for ordinal, (path, row) in enumerate(zip(expected_sources, rows)):
        snapshot = directory/'source_snapshots'/f'{ordinal:02d}_{path.name}'
        snapshots.add(snapshot.name)
        proof = inputs.file(snapshot, True)
        require(all(proof[key] == row[key] for key in ('sha256','bytes')),
                'CPU ordinal snapshot differs from actual source: '+str(snapshot))
        if not historical or path.name != 'motion_safety.py':
            require(inputs.raw(snapshot) == inputs.raw(path, path.is_relative_to(ROOT)),
                    'CPU source is not current/index bytes: '+str(path))
    require({p.name for p in (directory/'source_snapshots').iterdir()} == snapshots,
            'missing/extra ordinal source snapshot: '+name)
    console = directory/'console.log'
    proof = inputs.file(console, True)
    require(value['console']['path'] == str(console)
            and all(proof[key] == value['console'][key] for key in ('sha256','bytes')),
            'CPU console raw bytes differ: '+name)
    inputs.file(directory/'actual_runner.py', True)
    return value, inputs.raw(console), {'seconds':str(seconds),'source_count':len(rows),
        'actual_returncode':returncode, 'historical_source_snapshot':historical,
        'actual_wait_sha256':inputs.file(directory/'actual_wait.json', True)['sha256'],
        'console_sha256':proof['sha256']}


def check_cpu_evidence(inputs, wait_math, parse):
    paths = [ROS/'src/multi_robot_exploration'/name for name in (
        'multi_robot_exploration/mr3_reach_runtime.py', 'multi_robot_exploration/motion_safety.py',
        'multi_robot_exploration/mr3_drive_phase.py', 'test/test_mr3_reach_runtime_independent.py',
        'test/test_motion_safety_reach.py', 'test/test_mr3_drive_phase.py', 'test/test_mr3_motion_control.py',
        'test/test_mr3_phase_qos.py')]
    command = ['/bin/bash','-c',
        'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B -m pytest -q test/test_mr3_reach_runtime_independent.py test/test_motion_safety_reach.py test/test_mr3_drive_phase.py test/test_mr3_motion_control.py test/test_mr3_phase_qos.py',
        'mr3-storage-queue-regression',str(ROS)]
    _, console, unit = check_cpu(inputs, wait_math, 'storage_queue_runtime_cpu_attempt_v1', paths,
        command, ROS/'src/multi_robot_exploration','23.374654579')
    matches = re.findall(rb'\b([1-9][0-9]*) passed\b', console)
    require(matches == [b'140'] and not re.search(rb'\b[0-9]+ (?:failed|errors?|skipped|xfailed|xpassed)\b',console,re.I),
            'fresh target console must contain one positive all-passed summary without skipped/failed tests')
    unit['passed_tests'] = int(matches[0])

    script = A/'closed_prewarm_replay_v1.py'
    dependencies = [RUNTIME_PACKAGE/(name+'.py') for name in (
        'mr3_reach_runtime','mr3_episode','mr3_drive_phase','mr3_safety_intent',
        'mr3_reach_geometry','mr3_velocity_metric','motion_safety','__init__')]
    command = ['/bin/bash','-c',
        'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B "$2" --output "$3"',
        'mr3-closed-prewarm',str(ROS),str(script),str(REPLAY_OUTPUT)]
    wait, console, cpu = check_cpu(inputs, wait_math, 'closed_prewarm_cpu_attempt_v1',
        [script,*dependencies], command, W, '269.896902167', returncode=1, historical=True)
    require(inputs.file(A/'checks/closed_prewarm_cpu_attempt_v1/actual_wait.json',True)['sha256'] ==
            '79121be04ac8864db8ff211866af488f9c83553e769b1574eac462fb7cdb9543',
            'original failed replay wait changed')
    result_path = A/'closed_prewarm_replay_failed_result_v1.json'
    result_raw = inputs.raw(result_path)
    require(result_raw == inputs.raw(REPLAY_OUTPUT, False), 'canonical replay result differs from actual /tmp output')
    result = parse(result_raw)
    require(sha(result_raw) == '71c948d53ac902173a9615a0a0f02fc0d7fd1797310bee562c3352e8a1ab72db'
            and result.get('schema') == 'mr3-v18-closed-prewarm-replay-v1'
            and result.get('passed') is False and result.get('full_suffix_scanned') is True
            and result.get('scientific_pass_claimed') is False and result.get('native_admission') is False
            and result.get('old_native_failure_reclassified') is False
            and all(type(result.get(key)) is int and result[key] == 0
                    for key in ('new_native_runs','gpu_calls','optimizer_steps'))
            and result.get('continuous_physical_model_proved') is False and result.get('errors') == [],
            'original failed CPU replay bytes/scope were changed')
    start, end = result['started_monotonic_ns'], result['ended_monotonic_ns']
    require(type(start) is int and type(end) is int
            and wait['started_monotonic_ns'] <= start < end <= wait['ended_monotonic_ns'],
            'replay internal clocks are outside the actual child wait')
    summary = parse(console.decode().splitlines()[-1])
    require(summary.get('schema') == result['schema'] and summary.get('passed') is False
            and summary.get('full_suffix_scanned') is True and summary.get('first_fault') is None
            and summary.get('error_count') == 3 and summary.get('errors') == []
            and summary.get('output') == str(REPLAY_OUTPUT), 'actual replay console does not match output')
    sources = result['runtime_source_bindings']
    require(len(sources) == len(dependencies) and {row['path'] for row in sources} == set(map(str,dependencies)),
            'replay current runtime/caller source inventory differs')
    for row in sources:
        waited = [item for item in wait['source_before'] if item['path'] == row['path']]
        require(len(waited) == 1 and all(waited[0][key] == row[key] for key in ('sha256','bytes')),
                'old replay dependency differs from its historical actual CPU source')
    trace = result['trace']
    require(trace['source_freeze'] == BASE and trace['sha256'] == TRACE_SHA
            and trace['bytes'] == 390357682 and trace['records'] == trace['last_record_sequence'] == 162691
            and trace['epoch'] == 'mr3_p2a_reach_v17_interface_w0_e1_72f1a48b'
            and trace['manifest_path'] == str(CLOSED/'native_closed_manifest_v1.json'),
            'replay trace origin/complete byte identity differs')
    manifest = inputs.document(CLOSED/'native_closed_manifest_v1.json')
    relative = 'mr3_p2a_reach_v17_interface/worker0/episode001_open_101/motion_safety.jsonl'
    matches = [row for row in manifest['source_files'] if row['path'] == relative]
    require(len(matches) == 1 and all(matches[0][key] == trace[key] for key in ('sha256','bytes')),
            'replay trace is not the original closed archive member')
    require(Path(trace['path']) == Path(manifest['source_root'])/relative,
            'replay trace path is not the original native member')
    trace_inputs = [row for row in result['input_bindings'] if row['path'] == trace['path']]
    require(len(trace_inputs) == 1 and all(trace_inputs[0][key] == trace[key] for key in ('sha256','bytes')),
            'actual replay output did not bind its full original trace')
    for row in result['input_bindings']:
        if row['path'] == trace['path']:
            continue  # Already fully hashed by the actual replay; bind its archived member, not another raw scan.
        path = Path(row['path'])
        proof = inputs.file(path, path.is_relative_to(ROOT) and not path.is_relative_to(ROS/'log'))
        require(all(proof[key] == row[key] for key in ('sha256','bytes')), 'replay supporting input changed')
    replay = result['replay']
    require(replay['new_faults'] == {} and replay['first_fault'] is None
            and replay['first_original_fault'] is not None and replay['error_count'] == 3
            and len(replay['errors']) == 3
            and {row['robot'] for row in replay['errors']} == {'tb1','tb2','tb3'}
            and all(row['phase'] == 'closed_tail' and row['reason'] ==
                    'required causal event/metadata remains unresolved' for row in replay['errors'])
            and all(replay['pending'][robot]['causal_count'] > 0 for robot in ('tb1','tb2','tb3'))
            and replay['release_calls'] == replay['nonzero_publications'] == 0
            and set(replay['actual_shutdown_stop_sources']) == {'tb1','tb2','tb3'},
            'original incomplete causal suffix or failed result was changed')
    cpu.update(result_sha256=sha(result_raw), full_trace_records=162691, full_trace_bytes=390357682,
        raw_trace_rehashed_by_this_checker=False, passed=False, old_input_ineligible=True,
        native_or_qualification_credit=False,
        entry=file_spec(inputs,script), actual_cpu_wait=file_spec(inputs,A/'checks/closed_prewarm_cpu_attempt_v1/actual_wait.json'),
        result=file_spec(inputs,result_path),
        scope='Original full CPU replay remains FAIL; missing old receipts cannot be repaired by new source')
    unit.update(passed=True,actual_cpu_wait=file_spec(inputs,A/'checks/storage_queue_runtime_cpu_attempt_v1/actual_wait.json'))
    forensic = check_forensic(inputs,wait_math,parse)
    burst = check_burst(inputs,wait_math,parse)
    return {'scope':'prospective_source_preparation_only','passed':True,
        'scientific_pass_claimed':False,'native_admission':False,'native_or_qualification_credit':False,
        'targeted_tests':unit,'closed_prewarm_replay':cpu,'missing_receipt_forensics':forensic,
        'real_ros_queue_burst':burst,'fresh_full_native_qualification_required':True}


def verify_preparation_evidence():
    """Generator entry: the same checks, current files before staging is required."""
    prior_path = PRIOR/'check_closed_preparation_v1.py'
    before = prior_path.read_bytes()
    require(sha(before) == PRIOR_HELPER_SHA, 'original CPU packaging dependency SHA differs before loading')
    prior = runpy.run_path(str(prior_path))
    class CurrentInputs(prior['Inputs']):
        def file(self,path,staged=False):
            return super().file(path,False)
    inputs = CurrentInputs()
    require(inputs.raw(prior_path) == before, 'CPU packaging dependency changed while loading')
    proof = check_cpu_evidence(inputs,prior['wait_math'],prior['parse'])
    inputs.finish()
    artifacts = sorted(path for path in inputs.bindings
        if path.is_relative_to(ROOT) and not path.is_relative_to(ROS/'log'))
    return proof,artifacts


def check_copies(inputs):
    directories = {'matrix':Path('/tmp/mr3_p2a_reach_v17_matrix'),
        'matrix_outer':Path('/tmp/mr3_p2a_reach_v17_matrix_wait'),
        'preflight_outer':Path('/tmp/mr3_p2a_reach_v17_preflight_wait'),
        'absence_outer':Path('/tmp/mr3_p2a_reach_v17_absence_wait')}
    pairs = []
    for name, original in directories.items():
        current = CLOSED/name
        left = {p.relative_to(current) for p in current.rglob('*') if p.is_file()}
        right = {p.relative_to(original) for p in original.rglob('*') if p.is_file()}
        require(left == right and left, 'closed original/copy inventory differs: '+name)
        pairs.extend((current/relative, original/relative) for relative in sorted(left))
    pairs.extend(((CLOSED/'preflight.json',Path('/tmp/mr3_p2a_reach_v17_preflight.json')),
                  (CLOSED/'external_absence.json',Path('/tmp/mr3_p2a_reach_v17_absence.json'))))
    for current, original in pairs:
        require(inputs.raw(current) == inputs.raw(original,False), 'closed original/copy bytes differ: '+str(current))
    return len(pairs)


def check_archive(inputs):
    manifest = inputs.document(CLOSED/'native_closed_manifest_v1.json')
    rows = manifest['source_files']
    require(manifest['schema'] == 'mr3-v17-closed-native-byte-archive-v1' and manifest['source_freeze'] == BASE
            and len(rows) == len({row['path'] for row in rows}) == 461
            and sum(row['bytes'] for row in rows) == manifest['source_bytes'] == 789023247,
            'original archive manifest inventory/totals differ')
    require(all(not Path(row['path']).is_absolute() and '..' not in Path(row['path']).parts
                and re.fullmatch('[0-9a-f]{64}',row['sha256']) for row in rows), 'malformed original archive member')
    require(manifest.get('all_archived_bytes_replayed') is True and manifest.get('source_unchanged') is True
            and manifest.get('scientific_pass_claimed') is False and manifest.get('native_experiment_reexecuted') is False,
            'original archive scope/source facts differ')
    archive = CLOSED/'native_closed_v1.tar.xz'
    proof = inputs.file(archive, True)
    require(manifest['archive']['path'] == str(archive) and proof['bytes'] == 36583984
            and proof['sha256'] == '56d99b24bb0b9a7e994259e8c103f43fd2d705672845750f324741796890307b'
            and all(proof[key] == manifest['archive'][key] for key in ('sha256','bytes')),
            'original archive current/index SHA/bytes differ')
    return {'source_files':461,'source_bytes':789023247,'compressed_bytes':36583984,
            'archive_sha256':proof['sha256'],'decompressed_by_this_checker':False}


def check_accounting_and_absence(inputs, wait_math):
    accounting = inputs.document(CLOSED/'engineering_accounting_v1.json')
    fees = [wait_math(inputs.document(CLOSED/name/'actual_wait.json'), code,
                      'mr3-reach-outer-actual-wait-v1')
            for name,code in (('matrix_outer',1),('absence_outer',0))]
    require(fees == [Decimal('449.21890062'),Decimal('0.191114003')], 'original actual fee waits differ')
    total = sum(fees); used = Decimal('32045.4944710376018')+total; remaining = Decimal('52000')-used
    require(accounting['schema'] == 'mr3-v17-closed-actual-engineering-accounting-v1'
            and accounting['source_freeze'] == BASE and accounting['opening_used_wall_seconds'] == '32045.4944710376018'
            and Decimal(accounting['engineering_ceiling_wall_seconds']) == 52000
            and total == Decimal(accounting['charged_this_version_seconds']) == Decimal('449.410014623')
            and used == Decimal(accounting['cumulative_used_seconds']) == Decimal('32494.9044856606018')
            and remaining == Decimal(accounting['remaining_seconds']) == Decimal('19505.0955143393982')
            and accounting.get('qualification_passed') is False and accounting.get('policy_stage_started') is False
            and accounting.get('cpu_preparation_charged_to_native') is False
            and accounting['pilot_remaining_decisions'] == 1870
            and accounting['pilot_remaining_seconds'] == '2905.9547395464029'
            and accounting['final_only_validation_count_unchanged'] == 3, 'accounting arithmetic/scope differs')
    require(len(accounting['actual_outer_fees']) == 2, 'fee receipt set differs')
    for row,name,code,seconds in zip(accounting['actual_outer_fees'],('matrix_outer','absence_outer'),(1,0),fees):
        path = CLOSED/name/'actual_wait.json'
        require(row['path'] == str(path.relative_to(ROOT)) and row['sha256'] == inputs.file(path,True)['sha256']
                and row['actual_returncode'] == code and row['actual_waited'] is True
                and Decimal(row['seconds']) == seconds and row['charge_once_outer_includes_all_submitted_children'] is True,
                'fee does not bind once to its original actual wait')
    value = inputs.document(CLOSED/'external_absence.json')
    require(value['schema'] == 'mr3-reach-external-process-absence-v1' and value.get('passed') is True
            and value.get('all_saved_identities_absent') is True and value.get('scientific_pass_claimed') is False
            and not any(value.get(key) for key in ('present','unreadable','errors','pids_without_saved_start')),
            'original external absence did not close')
    pairs = [(row['pid'],row['start_ticks']) for row in value['identities']]
    require(len(pairs) == len(set(pairs)) == value['identity_count'] == 48, 'saved identity inventory differs')
    reused = []
    for pid,start in pairs:
        require(type(pid) is int and pid > 0 and type(start) is int and start > 0, 'invalid saved PID/start')
        try:
            fields = (Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split()
            current = int(fields[19])
            require(current != start, 'saved identity still present, including zombie: '+str(pid))
            reused.append({'pid':pid,'saved_start_ticks':start,'current_start_ticks':current,'state':fields[0]})
        except (FileNotFoundError,ProcessLookupError):
            pass
    summary = inputs.document(CLOSED/'matrix/summary.json')
    require(summary['freeze'] == BASE and summary.get('passed') is False
            and summary.get('all_submitted_children_waited') is True
            and [s['status'] for s in summary['stages']] == ['FAIL','SKIPPED','SKIPPED','SKIPPED'],
            'original V17 no-retry failure was changed')
    return {'charged_seconds':str(total),'cumulative_used_seconds':str(used),'remaining_seconds':str(remaining),
            'ceiling_seconds':'52000','saved_identities_absent':48,'same_pid_different_start':reused}


def check_plan(inputs, path, expected_sha, preparation):
    require(path.resolve() == A/'predeclared_plan_v1.json', 'wrong continuation plan path')
    require(inputs.file(path,True)['sha256'] == expected_sha, 'explicit expected whole plan SHA differs')
    plan = inputs.document(path)
    require(plan['schema'] == 'mr3-reach-preparation-plan-v1' and plan['safety_contract'] == 'mr3-reach-v1'
            and plan['role_registry']['mandatory_roles'] == 30 and plan['role_registry']['old_profile_credit_reused'] is False,
            'new four-stage thirty-role qualification scope differs')
    sources = plan['source_bindings']
    require(type(sources) is dict and sources, 'plan source inventory missing')
    for name,digest in sources.items():
        source = Path(name) if Path(name).is_absolute() else ROOT/name
        require(source.is_relative_to(ROOT) and inputs.file(source,True)['sha256'] == digest,
                'plan current/index source binding differs: '+name)
    require(str(Path(__file__).resolve().relative_to(ROOT)) in sources, 'plan did not bind this checker source')
    binding_path = Path(plan['custody_binding'])
    require(binding_path == A/'native_custody_binding_v1.json', 'wrong continuation custody binding path')
    binding = inputs.document(binding_path)
    libraries, binaries = plan['library_bindings'], binding['binaries']
    require(len(binaries) == len(libraries) == 10 and {r['path'] for r in binaries.values()} == set(libraries),
            'ten-ELF inventory differs')
    for row in binaries.values():
        path = Path(row['path']); proof = inputs.file(path)
        require(str(path.resolve(strict=True)) == row['resolved_path']
                and proof['sha256'] == row['sha256'] == libraries[str(path)] and proof['bytes'] == row['bytes'],
                'actual installed ELF SHA/bytes/resolution differs: '+str(path))
    budget = plan['budget']
    require(budget['engineering_used_at_plan_entry_seconds'] == '32494.9044856606018'
            and budget['engineering_remaining_seconds'] == '19505.0955143393982'
            and budget['approved_cumulative_engineering_seconds'] == '52000'
            and Decimal(budget['matrix_wall_seconds']) == 18000
            and budget['external_final_and_accounting_reservation_seconds'] == '300'
            and budget['full_minimum_reservation_available_at_plan_entry'] is False,
            'plan opening budget differs from actual closed accounting')
    condition = plan['post_qualification']['fresh_minimum']['engineering_balance_condition']
    require(condition['minimum_stage_reservation_seconds'] == '1800'
            and condition['external_reserve_initial_seconds'] == '300'
            and condition['admit_only_if'] == 'actual_engineering_remaining_seconds >= 1800 + unused_external_reserve_seconds',
            'minimum must remain conditional on actual matrix savings and unspent external reserve')
    require(plan['prospective_preparation_requirement'] == preparation,
            'plan prospective CPU proof differs from complete recomputed actual receipts')
    for dependency in (PRIOR/'check_closed_preparation_v1.py',
                       W/'report/assets/20261019_mr3_p2a_v16/check_preparation_v1.py'):
        require(sources[str(dependency.relative_to(ROOT))] == inputs.file(dependency,True)['sha256'],
                'executed historical packaging dependency is unbound')
    return {'plan_sha256':expected_sha,'current_and_staged_sources':len(sources),'actual_elf_count':10,
            'minimum_admitted_by_this_checker':False}


def check_production_and_history(inputs, static):
    roots = [str((ROS/'src').relative_to(ROOT)),str((ROS/'scripts').relative_to(ROOT)),
             str((W/'mr3_learning').relative_to(ROOT))]
    allowed = {str((ROS/'src/multi_robot_exploration'/name).relative_to(ROOT)) for name in (
        'multi_robot_exploration/mr3_reach_runtime.py','multi_robot_exploration/motion_safety.py',
        'test/test_mr3_reach_runtime_independent.py','test/test_motion_safety_reach.py')}
    for staged in (False,True):
        args = ['diff']+(['--cached'] if staged else [])+['--name-only',BASE,'--',*roots]
        require(set(git(*args).decode().splitlines()) == allowed, 'production diff exceeds the four reviewed repair files')
    require(not git('ls-files','--others','--exclude-standard','--',*roots), 'untracked production source was added')
    old = [str(path) for path in static['OLD_ASSETS']]
    for staged in (False,True):
        args = ['diff']+(['--cached'] if staged else [])+['--name-only',BASE,'--',*old]
        require(not git(*args), 'previously checked old original asset bytes changed')
    require(not git('ls-files','--others','--exclude-standard','--',*old), 'new untracked file entered old original assets')
    return {'production_changed_paths':sorted(allowed),'driver_worker_drive_phase_all_learner_readers_unchanged':True,
            'old_assets_have_no_current_or_index_diff':True,'old_assets_rehashed_individually':False}


def selected_syntax_and_links(selected, inputs, static):
    result = {'python':0,'json':0,'local_markdown_links':0}
    for relative in sorted(selected):
        path = ROOT/relative
        if not path.is_file():
            continue
        raw = inputs.raw(path)
        if path.suffix == '.py':
            ast.parse(raw, filename=str(path)); result['python'] += 1
        elif path.suffix == '.json':
            static['decode'](raw); result['json'] += 1
        elif path.suffix == '.md':
            if path == W/'log.md':
                old = git('show',BASE+':'+str(path.relative_to(ROOT)))
                require(raw.startswith(old), 'shared log prefix was edited instead of appended')
                raw = raw[len(old):]
            for target in static['markdown_targets'](raw.decode()):
                parts = urlsplit(target)
                if not target or target.startswith('#') or parts.scheme not in ('','file'):
                    continue
                local = Path(unquote(parts.path)); local = local if local.is_absolute() else path.parent/local
                require(local.exists(), 'broken selected Markdown link: '+str(path)+' -> '+target)
                result['local_markdown_links'] += 1
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--plan-sha',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{64}',args.plan_sha), 'exact expected plan SHA required')
    require(not args.output.exists() and args.output.resolve().is_relative_to(Path('/tmp')), 'exclusive /tmp output required')
    started = time.monotonic_ns(); metrics = {}; errors = []; inputs = None
    index_before = sha(git('ls-files','--stage','-z'))
    try:
        # These historical packaging helpers execute no main/consumer on load.
        prior_path = PRIOR/'check_closed_preparation_v1.py'
        static_path = W/'report/assets/20261019_mr3_p2a_v16/check_preparation_v1.py'
        prior_raw, static_raw = prior_path.read_bytes(), static_path.read_bytes()
        require(sha(prior_raw) == PRIOR_HELPER_SHA and sha(static_raw) == STATIC_HELPER_SHA,
                'original packaging dependency SHA differs before loading')
        prior = runpy.run_path(str(prior_path)); static = runpy.run_path(str(static_path))
        inputs = prior['Inputs']()
        for path, raw in ((prior_path,prior_raw),(static_path,static_raw)):
            require(inputs.raw(path) == raw, 'packaging helper changed while loading')
        inputs.file(Path(__file__).resolve(),True)
        selected = static['selected_files'](True)
        metrics['cpu'] = check_cpu_evidence(inputs,prior['wait_math'],prior['parse'])
        metrics['closed_raw_files_compared'] = check_copies(inputs)
        metrics['archive'] = check_archive(inputs)
        metrics['accounting_and_absence'] = check_accounting_and_absence(inputs,prior['wait_math'])
        metrics['plan'] = check_plan(inputs,args.plan,args.plan_sha,metrics['cpu'])
        metrics['production_and_history'] = check_production_and_history(inputs,static)
        metrics['selected_artifacts'] = static['artifact_sanity'](selected,inputs.raw,True)
        metrics['selected_syntax_and_links'] = selected_syntax_and_links(selected,inputs,static)
        inputs.finish()
        require(sha(git('ls-files','--stage','-z')) == index_before, 'Git index changed during packaging check')
    except (OSError,ValueError,KeyError,TypeError,IndexError,SyntaxError,subprocess.SubprocessError) as error:
        errors.append(type(error).__name__+': '+str(error))
    result = {'schema':SCHEMA,'passed':not errors,'scope':'staged_packaging_integrity_only',
        'scientific_pass_claimed':False,'native_admission':False,'native_runs':0,'gpu_calls':0,'optimizer_steps':0,
        'started_monotonic_ns':started,'ended_monotonic_ns':time.monotonic_ns(),
        'expected_plan_sha256':args.plan_sha,'metrics':metrics,'errors':errors,
        'input_bindings':list(inputs.bindings.values()) if inputs else [],
        'git_index_source_bindings_checked':len(inputs.index) if inputs else 0,
        'git_index_inventory_sha256':index_before}
    with args.output.open('x') as stream:
        json.dump(result,stream,indent=2); stream.write('\n')
    print(json.dumps({'schema':SCHEMA,'passed':result['passed'],'metrics':metrics,'errors':errors,'output':str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
