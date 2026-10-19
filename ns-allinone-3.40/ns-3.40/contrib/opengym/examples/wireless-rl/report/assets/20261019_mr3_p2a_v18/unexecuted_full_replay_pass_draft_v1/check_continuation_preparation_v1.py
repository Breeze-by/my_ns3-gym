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
RUNTIME_PACKAGE = ROS/'src/multi_robot_exploration/multi_robot_exploration'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def git(*args):
    return subprocess.check_output(['git', *map(str, args)], cwd=ROOT)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def check_cpu(inputs, wait_math, name, expected_sources, argv, cwd, expected_seconds=None):
    directory = A/'checks'/name
    value = inputs.document(directory/'actual_wait.json')
    seconds = wait_math(value, 0, WAIT_SCHEMA)
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
        proof = inputs.file(path, True)
        require(all(proof[key] == row[key] for key in ('sha256','bytes')),
                'CPU source is not current/index bytes: '+str(path))
        snapshot = directory/'source_snapshots'/f'{ordinal:02d}_{path.name}'
        snapshots.add(snapshot.name)
        require(inputs.raw(snapshot) == inputs.raw(path), 'CPU ordinal snapshot differs: '+str(snapshot))
    require({p.name for p in (directory/'source_snapshots').iterdir()} == snapshots,
            'missing/extra ordinal source snapshot: '+name)
    console = directory/'console.log'
    proof = inputs.file(console, True)
    require(value['console']['path'] == str(console)
            and all(proof[key] == value['console'][key] for key in ('sha256','bytes')),
            'CPU console raw bytes differ: '+name)
    inputs.file(directory/'actual_runner.py', True)
    return value, inputs.raw(console), {'seconds':str(seconds),'source_count':len(rows),
        'actual_wait_sha256':inputs.file(directory/'actual_wait.json', True)['sha256'],
        'console_sha256':proof['sha256']}


def check_cpu_evidence(inputs, wait_math, parse):
    paths = [ROS/'src/multi_robot_exploration'/name for name in (
        'multi_robot_exploration/mr3_reach_runtime.py', 'multi_robot_exploration/motion_safety.py',
        'multi_robot_exploration/mr3_drive_phase.py', 'test/test_mr3_reach_runtime_independent.py',
        'test/test_motion_safety_reach.py', 'test/test_mr3_drive_phase.py', 'test/test_mr3_motion_control.py')]
    command = ['/bin/bash','-c',
        'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B -m pytest -q test/test_mr3_reach_runtime_independent.py test/test_motion_safety_reach.py test/test_mr3_drive_phase.py test/test_mr3_motion_control.py',
        'mr3-same-tick-regression',str(ROS)]
    _, console, unit = check_cpu(inputs, wait_math, 'same_tick_runtime_cpu_attempt_v1', paths,
        command, ROS/'src/multi_robot_exploration', '24.300563445')
    require(re.search(rb'\b127 passed\b', console), 'actual unit console lacks 127 passed')

    script = A/'closed_prewarm_replay_v1.py'
    dependencies = [RUNTIME_PACKAGE/(name+'.py') for name in (
        'mr3_reach_runtime','mr3_episode','mr3_drive_phase','mr3_safety_intent',
        'mr3_reach_geometry','mr3_velocity_metric','motion_safety','__init__')]
    command = ['/bin/bash','-c',
        'source /opt/ros/humble/setup.bash; source "$1/install/setup.bash"; exec /usr/bin/python3 -B "$2" --output "$3"',
        'mr3-closed-prewarm',str(ROS),str(script),str(REPLAY_OUTPUT)]
    wait, console, cpu = check_cpu(inputs, wait_math, 'closed_prewarm_cpu_attempt_v1',
        [script,*dependencies], command, W)
    result_path = A/'closed_prewarm_replay_result_v1.json'
    result_raw = inputs.raw(result_path)
    require(result_raw == inputs.raw(REPLAY_OUTPUT, False), 'canonical replay result differs from actual /tmp output')
    result = parse(result_raw)
    require(result.get('schema') == 'mr3-v18-closed-prewarm-replay-v1'
            and result.get('passed') is True and result.get('full_suffix_scanned') is True
            and result.get('scientific_pass_claimed') is False and result.get('native_admission') is False
            and result.get('old_native_failure_reclassified') is False
            and all(type(result.get(key)) is int and result[key] == 0
                    for key in ('new_native_runs','gpu_calls','optimizer_steps'))
            and result.get('continuous_physical_model_proved') is False and result.get('errors') == [],
            'replay result is not a successful CPU-only complete trace replay')
    start, end = result['started_monotonic_ns'], result['ended_monotonic_ns']
    require(type(start) is int and type(end) is int
            and wait['started_monotonic_ns'] <= start < end <= wait['ended_monotonic_ns'],
            'replay internal clocks are outside the actual child wait')
    summary = parse(console.decode().splitlines()[-1])
    require(summary.get('schema') == result['schema'] and summary.get('passed') is True
            and summary.get('full_suffix_scanned') is True and summary.get('first_fault') is None
            and summary.get('error_count') == 0 and summary.get('errors') == []
            and summary.get('output') == str(REPLAY_OUTPUT), 'actual replay console does not match output')
    sources = result['runtime_source_bindings']
    require(len(sources) == len(dependencies) and {row['path'] for row in sources} == set(map(str,dependencies)),
            'replay current runtime/caller source inventory differs')
    for row in sources:
        proof = inputs.file(row['path'], True)
        require(all(proof[key] == row[key] for key in ('sha256','bytes')), 'replay source differs from current/index')
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
            and replay['first_original_fault'] is not None and replay['error_count'] == 0
            and replay['errors'] == [] and replay['release_calls'] == replay['nonzero_publications'] == 0
            and set(replay['actual_shutdown_stop_sources']) == {'tb1','tb2','tb3'},
            'replay omitted HOLD/STOP closure, inherited an old fault or retained a new fault')
    cpu.update(result_sha256=sha(result_raw), full_trace_records=162691, full_trace_bytes=390357682,
        raw_trace_rehashed_by_this_checker=False, scope='CPU replay only; no native/scientific credit')
    return {'targeted_tests':unit,'closed_prewarm_replay':cpu}


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


def check_plan(inputs, path, expected_sha):
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
    replay = plan['preparation_readonly_replay_requirement']
    for key, path in (('entry',A/'closed_prewarm_replay_v1.py'),
                      ('actual_cpu_wait',A/'checks/closed_prewarm_cpu_attempt_v1/actual_wait.json'),
                      ('result',A/'closed_prewarm_replay_result_v1.json')):
        require(replay[key]['path'] == str(path.relative_to(ROOT))
                and replay[key]['sha256'] == inputs.file(path,True)['sha256'], 'plan borrows a different replay proof')
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
        metrics['plan'] = check_plan(inputs,args.plan,args.plan_sha)
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
