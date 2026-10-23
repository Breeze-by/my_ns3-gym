"""Fixed V62 diagnostic parent; complete measured fee, no policy entry.

The benchmark retains its original finite reset/step/owned-close guards and
1500-second cooperative allocation. 1800 is the complete measured fee gate,
not a hard real-time promise. All submitted children are really waited.
"""
import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261024_mr3_p2a_v62_process_profile'
STATE = Path('/tmp/mr3_p2a_v62_parent_v1')
SCOPE = A / 'scope_v1.json'
PROFILE = 'mr3-p2a-v62-open101-8step-cprofile-v1'
LEARNER_PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
RUN = Path('/tmp/mr3_p2a_v62_open101_8step_profile_v1')
CAP = Decimal('1800')
HELPERS = W / 'report/assets/20261024_mr3_p2a_v61_cancel_forensics/run_cancel_forensics_v1.py'
LEDGER = W / 'report/assets/20261024_mr3_p2a_v61_cancel_forensics/closure_ledger_v1.json'
LEDGER_SHA = '6e9e808a36533cd08ce1986a98c9a3065bbf769fe78ddf340f08539c898f8d53'


def helpers():
    spec = importlib.util.spec_from_file_location('_v62_immutable_metadata_primitives', HELPERS)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def verify(h, scope, freeze):
    h.clean_freeze(freeze)
    h.require(h.git_bytes(freeze, str(SCOPE.relative_to(ROOT)), time.monotonic()+20) == SCOPE.read_bytes(),
              'V62 scope differs from its exact source freeze')
    h.require(scope['schema'] == 'mr3-v62-fixed-process-profile-scope-v1'
              and scope['diagnostic_profile'] == PROFILE and scope['run_root'] == str(RUN)
              and scope['admitted'] is True and scope['scientific_qualification'] is False
              and scope['capacity_qualified'] is False and scope['optimizer_updates'] == 0,
              'Not the admitted fixed zero-learning V62 diagnostic')
    h.require(scope['resource'] == dict(parent_cap_seconds=1800, native_allocation_seconds=1500,
              close_reserve_seconds=120, review_max_seconds=300), 'V62 resource declaration differs')
    result = []
    for is_git, rows in ((True, scope['source_bindings']), (False, scope['library_bindings'])):
        for row in rows:
            actual = h.proof(Path(row['path']))
            h.require(actual == row, 'V62 source/library byte drift: ' + row['path'])
            if is_git:
                relative = str(Path(row['path']).relative_to(ROOT))
                h.require(h.sha(h.git_bytes(freeze, relative, time.monotonic()+20)) == row['sha256'],
                          'V62 source not in current Git: ' + relative)
            result.append(actual)
    return result


def wait_command(h, argv, console, *, stop_deadline=None):
    started, errors, signals = time.monotonic_ns(), [], []
    saved, rc = None, None
    env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    env.pop('PYTHONPATH', None)
    env.pop('PYTHONHOME', None)
    with console.open('x') as output:
        child = subprocess.Popen(argv, cwd=W, env=env,
            stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            saved = h.identity(child.pid)
        except BaseException as error:
            errors.append('identity capture gap: '+repr(error))
        interrupted = False
        while True:
            try:
                rc = child.wait(timeout=.1)
                break
            except subprocess.TimeoutExpired:
                if stop_deadline is not None and not interrupted and time.monotonic() >= stop_deadline:
                    # Metadata/profile reader only; it cannot start native children.
                    # Keep the main benchmark on its original owned-close path.
                    interrupted = True
                    errors.append('Reader deadline triggered; a later rc0 cannot erase this failure')
                    for number in (2, 15, 9):
                        try:
                            if saved is not None and h.current(saved) is not None:
                                signals.append(dict(signal=number, sent=h.owned_signal(saved, number),
                                                    monotonic_ns=time.monotonic_ns()))
                            rc = child.wait(timeout=10)
                            break
                        except subprocess.TimeoutExpired:
                            pass
                        except BaseException as error:
                            errors.append('Reader escalation/wait: '+repr(error))
                    if rc is not None:
                        break
            except BaseException as error:
                errors.append(repr(error))
                # Never replace an outstanding wait with a guessed exit code.
        return dict(actual_argv=argv, identity=saved, actual_waited=True,
            actual_returncode=rc, started_monotonic_ns=started,
            ended_monotonic_ns=time.monotonic_ns(), wait_errors=errors, signals=signals,
            deadline_triggered=interrupted)


def main():
    entered = time.monotonic_ns()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    h, scope, bootstrap, owner, used, ceiling = None, None, None, None, None, None
    started, complete_fee_known = entered, False
    errors, before, after, launch, review = [], [], [], None, None
    actual_review = {}
    try:
        h = helpers()
        bootstrap = h.read(STATE / 'pre_exec_ancestry_v1.json')
        owner = h.identity(os.getpid())
        h.require(bootstrap['execution_freeze'] == args.freeze
                  and h.same(bootstrap['bootstrap_identity'], owner), 'Real bootstrap/exec identity mismatch')
        candidate_start = bootstrap['complete_parent_started_monotonic_ns']
        h.require(type(candidate_start) is int and 0 < candidate_start <= entered, 'Invalid original bootstrap start')
        started = candidate_start
        complete_fee_known = True
        previous_raw = LEDGER.read_bytes()
        h.require(hashlib.sha256(previous_raw).hexdigest() == LEDGER_SHA, 'Canonical actual entry ledger changed')
        previous = h.read(LEDGER)
        h.require(previous['passed'] is True, 'Canonical entry ledger is not actually closed')
        used, ceiling = (Decimal(previous[k]) for k in ('engineering_cumulative_seconds', 'engineering_ceiling_seconds'))
        scope = h.read(SCOPE)
        before = verify(h, scope, args.freeze)
        h.require(h.proof(LEDGER) == scope['previous_accounting']
                  and used == Decimal(scope['engineering_entry_seconds'])
                  and ceiling == Decimal(scope['engineering_ceiling_seconds'])
                  and ceiling-used >= CAP, 'V62 complete reservation not funded')
        argv = [LEARNER_PYTHON, '-B', '-m',
                'report.assets.20261024_mr3_p2a_v62_process_profile.fixed_profile_launcher_v1',
                '--freeze', args.freeze]
        h.require(scope['expected_launcher_argv_template'] == argv[:-1]+['__EXECUTION_FREEZE__'],
                  'V62 fixed launcher template differs')
        h.write(STATE / 'entry.json', dict(schema='mr3-v62-profile-parent-entry-v1',
            freeze=args.freeze, driver_identity=owner, bootstrap_identity=bootstrap['bootstrap_identity'],
            observed_nonowned_ancestors=bootstrap['observed_ancestors'],
            complete_parent_started_monotonic_ns=started, actual_expected_launcher_argv=argv,
            source_before=before, no_automatic_retry=True))
        launch = wait_command(h, argv, STATE/'native.log')
        h.write(STATE/'execution.json', dict(schema='mr3-v62-profile-execution-v1', launcher=launch))
        remaining = CAP - h.elapsed(started, time.monotonic_ns())
        review_allowance = min(240., float(remaining)-60.)
        if review_allowance > 0:
            review_argv = ['/usr/bin/python3', '-B', str(A/'review_profile_v1.py'),
                '--freeze', args.freeze, '--scope', str(SCOPE), '--run', str(RUN),
                '--driver', str(STATE), '--output', str(STATE/'profile_review_v1.json')]
            review = wait_command(h, review_argv, STATE/'review.log',
                stop_deadline=time.monotonic()+review_allowance)
            h.write(STATE/'review_execution.json', review)
        else:
            errors.append('No review admission after reserving 60s for escalation/post-source; no retry')
    except BaseException as error:
        errors.append(dict(type=type(error).__name__, reason=repr(error)))
    finally:
        if h is not None and scope is not None:
            try:
                after = verify(h, scope, args.freeze)
            except BaseException as error:
                errors.append(dict(type=type(error).__name__, reason='post-source: '+repr(error)))
        try:
            if h is not None and (STATE/'profile_review_v1.json').exists():
                actual_review = h.read(STATE/'profile_review_v1.json')
        except BaseException as error:
            errors.append(dict(type=type(error).__name__, reason='partial/invalid review: '+repr(error)))
    ended = time.monotonic_ns()
    fee = Decimal(ended-started) / 10**9
    passed = (complete_fee_known and not errors and bool(before) and before == after and launch is not None
        and launch['actual_waited'] and launch['actual_returncode'] == 0 and not launch['wait_errors']
        and review is not None and review['actual_waited'] and review['actual_returncode'] == 0
        and not review['wait_errors'] and actual_review.get('passed') is True and fee <= CAP)
    summary = dict(schema='mr3-v62-profile-parent-result-v1', passed=passed,
        execution_freeze=args.freeze, driver_identity=owner, errors=errors,
        started_monotonic_ns=started, ended_monotonic_ns=ended,
        actual_parent_seconds=str(fee) if complete_fee_known else None,
        observed_driver_lower_bound_seconds=None if complete_fee_known else str(fee),
        complete_parent_fee_known=complete_fee_known,
        engineering_entry_seconds=str(used) if used is not None else None,
        engineering_added_seconds=str(fee) if complete_fee_known else None,
        engineering_cumulative_seconds=str(used+fee) if complete_fee_known and used is not None else None,
        engineering_ceiling_seconds=str(ceiling) if ceiling is not None else None,
        engineering_remaining_seconds=str(ceiling-used-fee) if complete_fee_known and used is not None and ceiling is not None else None,
        pilot_added_seconds='0', validation_added_seconds='0',
        source_before=before, source_after=after, launcher=launch, review_execution=review,
        post_source_check_attempted=h is not None and scope is not None,
        source_and_cleanup_tail_is_shared_not_hard_realtime=True,
        actual_tool_reap_and_driver_freshgone_required_externally=True,
        scientific_qualification=False, capacity_qualified=False, optimizer_updates=0, P2A_complete=False)
    # Failure settlement does not depend on re-importing a broken helper/scope.
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE/'summary.json').open('x') as stream:
        json.dump(summary, stream, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({k:summary[k] for k in ('passed','actual_parent_seconds','engineering_cumulative_seconds')}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
