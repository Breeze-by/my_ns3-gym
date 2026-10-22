"""Fixed V51 outer actual-wait driver. Candidate only; no retry or reader dispatch."""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from . import profile_common_v1 as common

A = Path(__file__).resolve().parent
PACKAGE = 'report.assets.20261023_mr3_p2a_v51_runtime_profile'
CANONICAL_A = common.W / 'report/assets/20261023_mr3_p2a_v51_runtime_profile'
PREFIX = Path('/tmp/mr3_single_ep_runtime_profile_v51_driver_v1')
WORK = Path('/tmp/mr3_single_ep_runtime_profile_v51_work_v1')
OUTER = PREFIX / 'actual_profile_wait'
IMPORT_CHAIN = {str((common.W / 'mr3_learning' / name).relative_to(common.ROOT)) for name in (
    'reach_execution.py', 'preparation.py', 'native_custody.py', 'supervisor.py', 'ipc.py')}
ENV_POLICY = ('system Python; remove PYTHONPATH/PYTHONHOME/CONDA/ROS paths; hide CUDA; '
    'PYTHONNOUSERSITE=1; bytecode disabled; BLAS/OMP threads=1; no environment dump')


def same_identity(actual, expected):
    common.require(type(actual) is dict and type(expected) is dict and all(
        actual.get(key) == expected.get(key) for key in ('pid', 'start_ticks', 'parent', 'group', 'session')),
        'saved process identities differ')


def check_sources(scope, freeze, scope_path, deadline):
    """Bind every executed module and old source; no runtime/telemetry import."""
    rows = common.source_rows(scope, freeze, deadline)
    relative = str(scope_path.relative_to(common.ROOT))
    scope_binding = common.bind(scope_path, deadline_ns=deadline)
    frozen = subprocess.check_output(['git', 'show', freeze + ':' + relative], cwd=common.ROOT,
        timeout=common.remaining(deadline, 10))
    common.require(frozen == scope_path.read_bytes(), 'whole scope differs from execution Git freeze')
    execution = scope['execution_sources']
    names = [row['path'] for row in execution]
    required = IMPORT_CHAIN | {str((A / name).relative_to(common.ROOT)) for name in (
        'run_profile_v1.py', 'profile_guard_v3.py', 'profile_common_v1.py', 'runtime_child_v1.py')}
    common.require(len(names) == len(set(names)) and required <= set(names),
        'driver/profiler/outer import chain missing or duplicated in execution_sources')
    source_rows = [row for row in rows if row['source_role'] != 'interpreter'] + [scope_binding]
    paths = [row['path'] for row in source_rows]
    common.require(len(paths) == len(set(paths)), 'overlapping source registrations')
    return sorted(source_rows, key=lambda row: row['path']), scope_binding, rows


def check_closed(wait, guard, command, parent_start, parent_end, rc, wrapper, owner, scope, binding, sources):
    common.require(wait.get('schema') == 'mr3-reach-outer-actual-wait-v1'
        and wait.get('scope') == 'engineering' and wait.get('passed') is True
        and wait.get('actual_waited') is True and wait.get('actual_returncode') == rc == 0
        and wait.get('actual_argv') == command and wait.get('cwd') == str(common.W)
        and wait.get('source_unchanged') is True and wait.get('errors') == [], 'outer actual-wait receipt failed')
    same_identity(wait['coordinator_identity'], wrapper)
    same_identity(wait['child_identity'], guard['guard_identity'])
    common.require(wrapper['parent'] == owner['pid'], 'outer wrapper is not this driver owned child')
    common.require(parent_start <= wait['started_monotonic_ns'] <= guard['started_monotonic_ns']
        <= guard['ended_monotonic_ns'] <= wait['ended_monotonic_ns'] <= parent_end,
        'nested actual intervals do not lie inside parent actual wait')
    common.require(wait['source_before'] == wait['source_after'], 'outer source changed')
    expected = {row['path']: (row['bytes'], row['sha256']) for row in sources}
    actual = wait['source_before']
    common.require(len(actual) == len(expected) and {row['path']: (row['bytes'], row['sha256'])
        for row in actual} == expected, 'outer source set/bytes differ from full prospective source set')
    common.require(Decimal(wait['actual_child_wait_seconds']) == Decimal(
        wait['ended_monotonic_ns'] - wait['started_monotonic_ns']) / 10**9, 'outer duration is inconsistent')
    common.require(guard.get('schema') == 'mr3-single-ep-runtime-profile-guard-v3'
        and guard.get('passed') is True and guard.get('actual_waited') is True
        and guard.get('actual_returncode') == 0 and guard.get('received_parent_signals') == []
        and guard.get('errors') == [] and guard.get('timed_out') is False
        and guard.get('owned_group_members_after') == [], 'closed guard failed or received an interruption')
    common.require(guard.get('native_evidence_freeze') == common.EVIDENCE_FREEZE
        and guard.get('profiling_execution_freeze') == scope['_execution_freeze']
        and guard.get('fixed_episode') == str(common.EPISODE) and guard.get('scope') == binding,
        'guard native/execution freeze, episode or whole scope differs')
    common.require(guard.get('main_seconds') == 840 and guard.get('external_tail_seconds') == 60
        and guard.get('total_reservation_seconds') == 900
        and Decimal(guard['actual_guard_seconds']) == Decimal(
            guard['ended_monotonic_ns'] - guard['started_monotonic_ns']) / 10**9
        and Decimal(guard['actual_guard_seconds']) <= 840, 'guard actual duration/reservation differs')
    common.require(bool(guard['source_before']) and guard['source_before'] == guard['source_after']
        and bool(guard['closure_budget_refs_before'])
        and guard['closure_budget_refs_before'] == guard['closure_budget_refs_after'], 'guard bindings changed')
    proofs = guard['inputs_before']
    expected_inputs = {row['path']: (row['bytes'], row['sha256'], row['logical_name']) for row in scope['inputs']}
    common.require(len(proofs) == 14 and proofs == guard['inputs_after']
        and {row['path']: (row['bytes'], row['sha256'], row['logical_name']) for row in proofs} == expected_inputs,
        'guard fourteen original input proofs differ; no telemetry is reread by this driver')
    child = guard['child_summary']
    expected_child_argv = ['/usr/bin/python3', '-B', '-m', PACKAGE + '.runtime_child_v1',
        '--scope', str(A / 'scope_v1.json'), '--scope-sha256', binding['sha256'],
        '--execution-freeze', scope['_execution_freeze'], '--output', str(WORK),
        '--deadline-ns', str(guard['term_work_deadline_monotonic_ns'])]
    common.require(guard.get('actual_argv') == expected_child_argv, 'guard changed the fixed direct child argv')
    same_identity(child['child_identity'], guard['child_identity'])
    common.require(child.get('passed') is True and child.get('partial') is False
        and child.get('actual_audit_episode_calls') == child.get('target_call_count') == 1
        and child.get('forbidden_run_dispatch_calls') == 0 and child.get('signal_received') is None
        and child.get('native_evidence_freeze') == common.EVIDENCE_FREEZE
        and child.get('profiling_execution_freeze') == scope['_execution_freeze']
        and child.get('epoch') == scope['epoch'] and child.get('models_loaded') is False
        and child.get('gpu_calls') == child.get('optimizer_updates') == 0,
        'one complete original audit_episode call was not closed successfully')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    driver_started = time.monotonic_ns()
    PREFIX.mkdir(exist_ok=False)
    owner = common.identity(os.getpid())
    scope_path = A / 'scope_v1.json'
    command = ['/usr/bin/python3', '-B', '-m', PACKAGE + '.profile_guard_v3',
        '--scope', str(scope_path), '--execution-freeze', args.freeze, '--output', str(WORK)]
    entry = dict(schema='mr3-single-ep-runtime-profile-driver-entry-v1',
        native_evidence_freeze=common.EVIDENCE_FREEZE, profiling_execution_freeze=args.freeze,
        actual_driver_argv=[sys.executable, *sys.argv], cwd=str(Path.cwd()),
        clean_environment_policy=ENV_POLICY, driver_identity=owner, scope=str(scope_path),
        driver_started_monotonic_ns=driver_started, actual_wrapper_argv=None,
        fixed_guard_argv=command, main_seconds=840, total_reservation_seconds=900, tail_reservation_seconds=60,
        no_retry=True, no_warmup=True, external_driver_fresh_gone_review_required=True)
    common.write(PREFIX / 'entry.json', entry)
    child, wrapper, rc, parent_start, parent_end = None, None, None, None, None
    errors, received_signals, sources_before, sources_after = [], [], [], []
    scope, binding, argv, wait, guard, fee = None, None, None, None, None, Decimal(0)
    admitted_budget = None
    def interrupted(number, _frame):
        received_signals.append(dict(signal=signal.Signals(number).name, monotonic_ns=time.monotonic_ns()))
    previous = {number: signal.signal(number, interrupted) for number in (signal.SIGTERM, signal.SIGINT)}
    try:
        common.require(type(args.freeze) is str and re.fullmatch('[0-9a-f]{40}', args.freeze), 'exact execution freeze required')
        common.require(A == CANONICAL_A and __package__ == PACKAGE and Path.cwd() == common.W
            and Path(sys.executable).resolve() == Path('/usr/bin/python3').resolve(),
            'only canonical A51 package/cwd/system Python may execute this driver')
        common.require(not WORK.exists() and not WORK.is_symlink(), 'fixed guard output already exists; no retry/overwrite')
        scope = common.read_json(scope_path)
        common.validate_scope(scope)
        admitted_budget = dict(scope['budget_admission'])
        sources_before, binding, _ = check_sources(scope, args.freeze, scope_path, driver_started + 60_000_000_000)
        common.require(not received_signals, 'driver interrupted before actual submission')
        argv = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.reach_execution',
            '--scope', 'engineering', '--output', str(OUTER)]
        for row in sources_before:
            argv += ['--source', row['path']]
        argv += ['--', *command]
        common.write(PREFIX / 'submission.json', dict(actual_wrapper_argv=argv, fixed_guard_argv=command,
            driver_identity=owner, source_before=sources_before, scope=binding,
            budget_admission=scope['budget_admission'], clean_environment_policy=ENV_POLICY))
        # Exactly this complete parent interval is charged, never the nested
        # guard/reader durations again. Pre/post metadata spans are separate.
        parent_start = time.monotonic_ns()
        try:
            child = subprocess.Popen(argv, cwd=common.W, env=common.clean_environment())
            wrapper = common.identity(child.pid)
            common.write(PREFIX / 'wrapper_identity.json', wrapper)
        except BaseException as error:
            errors.append('submit/identity: ' + repr(error))
        finally:
            while child is not None and rc is None:
                try:
                    actual = child.wait()
                    common.require(type(actual) is int, 'wait returned no actual integer rc')
                    rc = actual
                except BaseException as error:
                    errors.append('actual wrapper wait interrupted; continuing: ' + repr(error))
            parent_end = time.monotonic_ns()
            fee = Decimal(parent_end - parent_start) / 10**9
        common.require(child is not None and type(rc) is int, 'wrapper was not actually submitted/reaped')
        wait = common.read_json(OUTER / 'actual_wait.json')
        guard = common.read_json(WORK / 'guard_receipt.json')
        check_closed(wait, guard, command, parent_start, parent_end, rc, wrapper, owner,
            dict(scope, _execution_freeze=args.freeze), binding, sources_before)
        common.require(fee <= 840, 'complete parent wait exceeds main840; full overrun charged FAIL')
        sources_after, after_binding, _ = check_sources(scope, args.freeze, scope_path, time.monotonic_ns() + 60_000_000_000)
        common.require(sources_before == sources_after and binding == after_binding, 'post-run whole source/scope changed')
    except BaseException as error:
        errors.append(repr(error))
    finally:
        # Record/defer TERM/INT throughout actual wait and cleanup; never let a
        # handler abandon a launched wrapper. No fabricated timeout/reap rc.
        while child is not None and rc is None:
            try:
                actual = child.wait()
                common.require(type(actual) is int, 'wait returned no actual integer rc')
                rc = actual
            except BaseException as error:
                errors.append('final actual wrapper wait interrupted; continuing: ' + repr(error))
        if parent_start is not None and parent_end is None:
            parent_end = time.monotonic_ns()
            fee = Decimal(parent_end - parent_start) / 10**9
        for number, handler in previous.items():
            signal.signal(number, handler)
    driver_metadata_end = time.monotonic_ns()
    budget = admitted_budget
    used = None if type(budget) is not dict else Decimal(budget['engineering_used_seconds']) + fee
    remaining = None if used is None else Decimal('75000') - used
    passed = (not errors and not received_signals and rc == 0 and fee <= 840
        and sources_before == sources_after and bool(sources_before) and remaining is not None and remaining >= 0)
    summary = dict(schema='mr3-single-ep-runtime-profile-driver-v1', passed=passed,
        native_evidence_freeze=common.EVIDENCE_FREEZE, profiling_execution_freeze=args.freeze,
        actual_driver_argv=[sys.executable, *sys.argv], cwd=str(Path.cwd()), clean_environment_policy=ENV_POLICY,
        driver_identity=owner, wrapper_identity=wrapper, guard_identity=None if guard is None else guard.get('guard_identity'),
        actual_wrapper_argv=argv, actual_guard_argv=command, actual_returncode=rc,
        actual_wrapper_waited=child is not None and type(rc) is int,
        received_parent_signals=received_signals, errors=errors,
        started_monotonic_ns=parent_start, ended_monotonic_ns=parent_end,
        actual_parent_wait_seconds=str(fee), engineering_added_seconds=str(fee),
        engineering_used_at_entry_seconds=None if type(budget) is not dict else budget['engineering_used_seconds'],
        engineering_cumulative_used_seconds=None if used is None else str(used),
        engineering_remaining_seconds=None if remaining is None else str(remaining),
        engineering_ceiling_seconds='75000', main_seconds=840, total_reservation_seconds=900,
        tail_reservation_seconds=60, tail_actual_seconds_not_invented=True,
        driver_started_monotonic_ns=driver_started, driver_metadata_end_monotonic_ns=driver_metadata_end,
        driver_metadata_span_seconds=str(Decimal(driver_metadata_end-driver_started) / 10**9),
        source_before=sources_before, source_after=sources_after, scope=binding,
        outer_actual_wait=str(OUTER / 'actual_wait.json'), guard_receipt=str(WORK / 'guard_receipt.json'),
        accounting='Only complete wrapper submission-to-real-wait parent interval charged; nested guard/reader not added. Entry/post metadata span recorded separately. Tail60 is reservation, not invented consumption; any overrun stays fully charged FAIL.',
        external_driver_fresh_gone_review_required=True, final_source_binding_review_required=True,
        closure_verdict='PENDING_EXTERNAL_DRIVER_FRESH_GONE', scientific_qualification_credit=False,
        old_failures_preserved=True, worlds=0, models_loaded=False, optimizer_updates=0, gpu_calls=0,
        no_retry=True, no_warmup=True)
    common.write(PREFIX / 'summary.json', summary)
    print(json.dumps({key: summary[key] for key in ('passed', 'actual_parent_wait_seconds', 'errors')}), flush=True)
    return 0 if passed and not received_signals else 1


if __name__ == '__main__':
    raise SystemExit(main())
