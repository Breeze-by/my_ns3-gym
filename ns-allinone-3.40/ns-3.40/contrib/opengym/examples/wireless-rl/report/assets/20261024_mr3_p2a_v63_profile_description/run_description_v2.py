"""Fixed V63 parent: one two-profile description, complete measured fee only."""
import argparse
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A62 = W/'report/assets/20261024_mr3_p2a_v62_process_profile'
A63 = W/'report/assets/20261024_mr3_p2a_v63_profile_description'
G = '81e63f50699073286c9773dcb92106de63fdf4ca'
STATE = Path('/tmp/mr3_p2a_v63_parent_v2')
SCOPE, SPEC = A63/'scope_v2.json', A63/'spec_v1.json'
OUTPUT = Path('/tmp/mr3_p2a_v63_profile_description_v1.json')
CAP, WORK = Decimal('120'), Decimal('60')
ENTRY, CEILING = Decimal('109069.2799140716018'), Decimal('150000')


def primitives():
    # Import definitions only. Neither historical main/activity/budget is called.
    paths = [A62/'run_profile_v1.py', W/'report/assets/20261024_mr3_p2a_v61_cancel_forensics/run_cancel_forensics_v1.py']
    for source in paths:
        raw = source.read_bytes()
        frozen = subprocess.check_output(['git','show',G+':'+str(source.relative_to(ROOT))],cwd=ROOT)
        if raw != frozen:
            raise ValueError('historical pure primitive module differs from G')
    definition = importlib.util.spec_from_file_location('_v63_original_wait_primitives', paths[0])
    module = importlib.util.module_from_spec(definition)
    definition.loader.exec_module(module)
    return module.helpers(), module.wait_command


def verify(h, scope, freeze):
    h.clean_freeze(freeze)
    h.require(h.git_bytes(freeze,str(SCOPE.relative_to(ROOT)),time.monotonic()+20) == SCOPE.read_bytes(),
              'new scope bytes are not in the execution freeze')
    h.require(scope['schema'] == 'mr3-v63-partial-profile-scope-v2' and scope['admitted'] is True
              and scope['consumer_spec'] == str(SPEC) and scope['output'] == str(OUTPUT)
              and scope['resource']['complete_parent_wall_seconds'] == 120
              and scope['resource']['work_wall_seconds'] == 60
              and type(scope['resource']['complete_parent_wall_seconds']) is int
              and type(scope['resource']['work_wall_seconds']) is int
              and scope['scientific_qualification'] is False and scope['capacity_qualified'] is False
              and scope['old_FAIL_rejudged'] is False, 'not the admitted fixed V63 description')
    result=[]
    for git_bound, key in [(True,'source_bindings'),(False,'library_bindings'),(False,'metadata_bindings')]:
        for row in scope[key]:
            source = Path(row['path'])
            h.require(source.suffix != '.pstats', 'parent must not pre/post-read either original pstats')
            actual=h.proof(source)
            h.require(actual == row,'new source/library/metadata drift: '+str(source))
            if git_bound:
                h.require(h.sha(h.git_bytes(freeze,str(source.relative_to(ROOT)),time.monotonic()+20)) == row['sha256'],
                          'source is not in current execution freeze')
            result.append(actual)
    return result


def main(argv=None):
    observed = time.monotonic_ns()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',required=True)
    args=parser.parse_args(argv)
    h, wait = None, None
    errors, before, after, scope = [], [], [], None
    started, owner, consumer, closed, entry_verified = None, None, None, {}, False
    post_source_check_attempted=False
    try:
        h, wait = primitives()
        owner=h.identity(os.getpid())
        bootstrap=h.read(STATE/'pre_exec_ancestry_v1.json')
        value=bootstrap.get('complete_parent_started_monotonic_ns')
        h.require(type(value) is int and 0 < value <= observed,'bootstrap complete-parent start is unknown')
        h.require(bootstrap['execution_freeze'] == args.freeze and h.same(bootstrap['bootstrap_identity'],owner),
                  'real bootstrap/exec PID/start differs')
        started=value
        scope=h.read(SCOPE)
        before=verify(h,scope,args.freeze)
        previous_path=Path(scope['previous_accounting']['path'])
        h.require(previous_path == A63/'closure_ledger_v1.json'
                  and h.proof(previous_path) == scope['previous_accounting'], 'actual V63 v1 admission closure ledger pin differs')
        previous=h.read(previous_path)
        h.require(previous['passed'] is True
                  and Decimal(previous['engineering_cumulative_seconds']) == ENTRY
                  and Decimal(previous['engineering_ceiling_seconds']) == CEILING
                  and Decimal(scope['engineering_entry_seconds']) == ENTRY
                  and Decimal(scope['engineering_ceiling_seconds']) == CEILING
                  and CEILING-ENTRY >= CAP, 'new complete120 reservation is not funded by actual V63 v1 closure')
        entry_verified=True
        h.require(not OUTPUT.exists(),'description output exists; no retry or reuse')
        command=['/usr/bin/python3','-B',str(A63/'describe_partial_profiles_v1.py'),
                 '--freeze',args.freeze,'--spec',str(SPEC),'--output',str(OUTPUT)]
        h.require(scope['expected_consumer_argv_template'] == [value if value != args.freeze else '__EXECUTION_FREEZE__' for value in command],
                  'fixed consumer argv template differs')
        h.write(STATE/'entry.json',dict(schema='mr3-v63-description-parent-entry-v2',freeze=args.freeze,
            driver_identity=owner,bootstrap_identity=bootstrap['bootstrap_identity'],
            observed_nonowned_ancestors=bootstrap['observed_ancestors'],
            complete_parent_started_monotonic_ns=started,actual_expected_consumer_argv=command,
            source_before=before,no_automatic_retry=True,native_started=False))
        # The imported, already tested wait primitive really reaps this one
        # Popen-owned CPU descriptor, including deadline/exception paths.
        deadline=min(time.monotonic()+float(WORK), started/1e9+90)
        consumer=wait(h,command,STATE/'consumer.log',stop_deadline=deadline)
        h.write(STATE/'execution.json',dict(schema='mr3-v63-description-execution-v2',consumer=consumer))
        h.require(consumer['actual_waited'] and consumer['actual_returncode'] == 0
                  and not consumer['wait_errors'] and not consumer['deadline_triggered'],
                  'descriptor did not finish cleanly within the work allocation')
        closed=h.read(OUTPUT)
        h.require(closed['schema'] == 'mr3-v63-partial-profile-description-v1'
                  and closed['passed'] is True and closed['description_complete'] is True
                  and closed['execution_freeze'] == args.freeze and len(closed['profiles']) == 2
                  and closed['profile_bytes_read'] == 894940
                  and closed['old_activity_passed'] is False and closed['old_FAIL_rejudged'] is False
                  and closed['scientific_qualification'] is False and closed['capacity_qualified'] is False
                  and closed['root_cause'] == 'UNKNOWN', 'actual fixed description proof differs')
    except BaseException as error:
        errors.append(dict(type=type(error).__name__,reason=repr(error)))
    finally:
        post_source_check_attempted=True
        try:
            if h is None:
                raise ValueError('pure source verifier unavailable after primitive import failure')
            after=verify(h,scope,args.freeze)
        except BaseException as error:
            errors.append(dict(type=type(error).__name__,reason='post-source check: '+repr(error)))
    ended=time.monotonic_ns()
    fee=Decimal(ended-started)/10**9 if started is not None else None
    passed=(not errors and bool(before) and before == after and fee is not None and fee <= CAP
            and consumer is not None and consumer['actual_waited'] and consumer['actual_returncode'] == 0
            and not consumer['wait_errors'] and closed.get('passed') is True)
    summary=dict(schema='mr3-v63-description-parent-result-v2',passed=passed,execution_freeze=args.freeze,
        driver_identity=owner,errors=errors,started_monotonic_ns=started,ended_monotonic_ns=ended,
        complete_parent_fee_known=fee is not None,actual_parent_seconds=None if fee is None else str(fee),
        observed_driver_lower_bound_seconds=str(Decimal(ended-observed)/10**9),
        engineering_entry_verified=entry_verified,engineering_entry_seconds=str(ENTRY),
        engineering_added_seconds=None if fee is None else str(fee),engineering_ceiling_seconds=str(CEILING),
        engineering_cumulative_seconds=str(ENTRY+fee) if entry_verified and fee is not None else None,
        engineering_remaining_seconds=str(CEILING-ENTRY-fee) if entry_verified and fee is not None else None,
        pilot_added_seconds='0',validation_added_seconds='0',source_before=before,source_after=after,
        post_source_check_attempted=post_source_check_attempted,consumer=consumer,
        actual_tool_reap_and_driver_freshgone_required_externally=True,
        scientific_qualification=False,capacity_qualified=False,old_FAIL_rejudged=False,
        root_cause='UNKNOWN',native_runs=0,model_runs=0,P2A_complete=False)
    if h is None:
        with (STATE/'summary.json').open('x') as output:
            json.dump(summary,output,indent=2,allow_nan=False)
            output.write('\n')
    else:
        h.write(STATE/'summary.json',summary)
    print(json.dumps({key:summary[key] for key in ('passed','complete_parent_fee_known','actual_parent_seconds')}))
    return 0 if passed else 1


if __name__=='__main__':
    raise SystemExit(main())
