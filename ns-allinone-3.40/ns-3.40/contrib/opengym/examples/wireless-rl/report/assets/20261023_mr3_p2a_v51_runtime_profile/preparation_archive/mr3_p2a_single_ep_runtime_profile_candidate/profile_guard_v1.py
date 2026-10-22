"""Disabled prospective 840s parent guard for one fixed closed-EP profile.

Install with its two siblings in a new canonical report package and seal it.
This draft has not imported the reader or consumed any runtime evidence.
"""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import signal
import re
import subprocess
import sys
import time

from . import profile_common_v1 as common


def stop_and_wait(child, errors, signals):
    """A26 owned-session TERM10/KILL5/actual-wait pattern; no fabricated rc."""
    def send(number):
        try:
            os.killpg(child.pid, number)
            signals.append(dict(signal=signal.Signals(number).name, monotonic_ns=time.monotonic_ns()))
        except ProcessLookupError:
            pass
        except OSError as error:
            errors.append('group signal: ' + repr(error))
            try:
                child.send_signal(number)
            except ProcessLookupError:
                pass
            except OSError as direct_error:
                errors.append('direct signal: ' + repr(direct_error))
    send(signal.SIGTERM)
    try:
        return child.wait(timeout=10.)
    except subprocess.TimeoutExpired:
        send(signal.SIGKILL)
    try:
        return child.wait(timeout=5.)
    except subprocess.TimeoutExpired:
        errors.append('owned child exceeded KILL reap allowance; full overrun charged FAIL')
        return child.wait()  # Never abandon an unreaped child to fit the ceiling.


def group_members(group):
    rows = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():
            continue
        try:
            row = common.identity(int(path.name))
            if row['group'] == group:
                rows.append(row)  # Z is present, never described as gone.
        except (FileNotFoundError, ProcessLookupError):
            pass
    return sorted(rows, key=lambda row: (row['pid'], row['start_ticks']))


def parent_admission(scope, deadline_ns):
    refs = {}
    for name in ('closed_inventory', 'closed_review', 'budget_admission_ref'):
        spec = scope[name]
        refs[name] = common.bind(spec['path'], spec, deadline_ns)
    inventory = common.read_json(scope['closed_inventory']['path'])
    review = common.read_json(scope['closed_review']['path'])
    budget = common.read_json(scope['budget_admission_ref']['path'])
    common.require(budget == scope['budget_admission'], 'actual budget admission bytes differ')
    common.require(inventory.get('freeze') == common.EVIDENCE_FREEZE
        and inventory.get('byte_archive_complete') is True,
        'complete V50 original-byte inventory is required, irrespective of scientific verdict')
    common.require(review.get('freeze') == common.EVIDENCE_FREEZE
        and review.get('parent_coordinators_actual_waited_and_fresh_gone') is True
        and review.get('closed_archive_eligible') is True
        and review.get('bound_inputs_stable') is True and review.get('metadata_membership_stable') is True,
        'fully reaped, stable original evidence closure is required before profiling')
    entries = {row['original']: row for row in inventory['entries']}
    common.require(len(entries) == len(inventory['entries']), 'duplicate original names in byte inventory')
    for spec in scope['inputs']:
        row = entries[spec['path']]
        common.require(row['original_bytes'] == spec['bytes'] and row['original_sha256'] == spec['sha256'],
                       'fixed original input does not match its canonical byte inventory')
    return refs


def run(scope_path, execution_freeze, output):
    started = time.monotonic_ns()
    work_deadline, main_deadline = started + 810_000_000_000, started + 840_000_000_000
    common.require(output.is_absolute() and output.parent == Path('/tmp')
        and output.name.startswith('mr3_single_ep_runtime_profile_') and not output.is_symlink(),
        'one new exclusive /tmp/mr3_single_ep_runtime_profile_* output directory required')
    output.mkdir(exist_ok=False)
    child, saved, rc, waited, timed_out = None, None, None, False, False
    errors, signals = [], []
    before, after, inputs_before, inputs_after, refs_before, refs_after = [], [], [], [], {}, {}
    scope, scope_binding, command = None, None, None
    child_started, child_ended, members, child_summary = None, None, None, None
    owner = common.identity(os.getpid())
    common.write(output / 'guard_identity.json', owner)
    try:
        common.require(Path.cwd() == common.W and Path(sys.executable).resolve() == Path('/usr/bin/python3').resolve(),
                       'canonical W/system Python required')
        common.require(__package__ and __package__.startswith('report.assets.'),
                       'guard must be installed under a new source-sealed canonical report package')
        common.require(type(execution_freeze) is str and re.fullmatch('[0-9a-f]{40}', execution_freeze),
                       'exact future profiling execution freeze required')
        relative = scope_path.resolve(strict=True).relative_to(common.ROOT)
        scope_binding = common.bind(scope_path, deadline_ns=work_deadline)
        scope = common.read_json(scope_path)
        common.validate_scope(scope)
        # The scope cannot self-hash inside itself; independently compare its
        # entire current bytes against the future execution Git blob here.
        raw = subprocess.check_output(['git', 'show', execution_freeze + ':' + str(relative)],
            cwd=common.ROOT, timeout=common.remaining(work_deadline, 10))
        common.require(raw == scope_path.read_bytes(), 'scope differs from profiling execution Git freeze')
        expected_new = {str(path.resolve().relative_to(common.ROOT)) for path in (
            Path(__file__), Path(common.__file__), Path(__file__).with_name('runtime_child_v1.py'))}
        common.require(expected_new <= {row['path'] for row in scope['execution_sources']},
                       'three actual profiling source modules are not execution-bound')
        before = common.source_rows(scope, execution_freeze, work_deadline)
        refs_before = parent_admission(scope, work_deadline)
        inputs_before = common.input_rows(scope, work_deadline)
        common.require(not any(path.is_dir() for path in common.EPISODE.glob('worker*'))
            and common.EPISODE.name == 'episode001_open_101', 'RUN/worker input is forbidden')
        command = ['/usr/bin/python3', '-B', '-m', __package__ + '.runtime_child_v1',
            '--scope', str(scope_path), '--scope-sha256', scope_binding['sha256'],
            '--execution-freeze', execution_freeze, '--output', str(output), '--deadline-ns', str(work_deadline)]
        with (output / 'child_console.log').open('xb') as console:
            child_started = time.monotonic_ns()
            child = subprocess.Popen(command, cwd=common.W, env=common.clean_environment(),
                stdout=console, stderr=subprocess.STDOUT, start_new_session=True)
            saved = common.identity(child.pid)
            common.require(saved['group'] == saved['session'] == child.pid and saved['parent'] == owner['pid'],
                           'new child ownership/session identity differs')
            common.write(output / 'child_identity.json', saved)
            try:
                rc = child.wait(timeout=common.remaining(work_deadline))
            except subprocess.TimeoutExpired:
                timed_out = True
                rc = stop_and_wait(child, errors, signals)
            waited, child_ended = True, time.monotonic_ns()
    except BaseException as error:
        errors.append(repr(error))
    finally:
        if child is not None and not waited:
            try:
                rc = stop_and_wait(child, errors, signals)
                waited, child_ended = True, time.monotonic_ns()
            except BaseException as error:
                errors.append('actual owned-child wait failed: ' + repr(error))
    if saved is not None:
        try:
            members = group_members(saved['group'])
            common.require(not members, 'owned session still has live/Z members after actual child wait')
        except (OSError, ValueError, IndexError) as error:
            errors.append('owned group close: ' + repr(error))
    if scope is not None:
        try:
            common.require(common.bind(scope_path, scope_binding, main_deadline) == scope_binding,
                           'scope changed during profiling')
            after = common.source_rows(scope, execution_freeze, main_deadline)
            refs_after = parent_admission(scope, main_deadline)
            inputs_after = common.input_rows(scope, main_deadline)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
            errors.append('post-profile binding: ' + repr(error))
    artifacts = []
    for name in ('runtime.pstats', 'runtime_result.json', 'child_summary.json', 'child_console.log'):
        path = output / name
        if path.is_file():
            try:
                artifacts.append(common.bind(path, deadline_ns=main_deadline))
            except (OSError, ValueError) as error:
                errors.append('output binding: ' + repr(error))
    if (output / 'child_summary.json').is_file():
        try:
            child_summary = common.read_json(output / 'child_summary.json')
        except (OSError, ValueError) as error:
            errors.append('child summary: ' + repr(error))
    ended = time.monotonic_ns()
    result = dict(schema='mr3-single-ep-runtime-profile-guard-v1',
        native_evidence_freeze=common.EVIDENCE_FREEZE, profiling_execution_freeze=execution_freeze,
        fixed_episode=str(common.EPISODE), scope=scope_binding, guard_identity=owner, child_identity=saved,
        actual_argv=command, cwd=str(common.W), environment_policy='clean system stdlib only; no ROS/conda path injection',
        actual_waited=waited, actual_returncode=rc, timed_out=timed_out, signals=signals,
        started_monotonic_ns=started, ended_monotonic_ns=ended,
        actual_guard_seconds=str(Decimal(ended - started) / 10**9),
        child_started_monotonic_ns=child_started, child_ended_monotonic_ns=child_ended,
        actual_child_wait_seconds=None if child_ended is None else str(Decimal(child_ended-child_started) / 10**9),
        main_seconds=840, external_tail_seconds=60, total_reservation_seconds=900,
        term_work_deadline_monotonic_ns=work_deadline, main_deadline_monotonic_ns=main_deadline,
        internal_guard_cleanup_reserve_seconds=30, term_grace_seconds=10, kill_reap_allowance_seconds=5,
        source_before=before, source_after=after, inputs_before=inputs_before, inputs_after=inputs_after,
        closure_budget_refs_before=refs_before, closure_budget_refs_after=refs_after,
        owned_group_members_after=members, output_artifacts=artifacts, child_summary=child_summary, errors=errors,
        no_new_native_or_scientific_qualification=True, optimizer_updates=0, gpu_calls=0,
        sampling_or_record_truncation=False, retries=0, warmup_calls=0,
        no_cold_disk_timing_claimed=True,
        accounting='Root must charge the complete outer parent actual-wait interval and real external tail union, not this nested child interval. Any overrun remains fully charged FAIL; OS-blocked I/O or reap can exceed nominal bounds.')
    result['passed'] = (waited and rc == 0 and not timed_out and not errors and ended <= main_deadline
        and bool(before) and before == after and bool(inputs_before) and inputs_before == inputs_after
        and bool(refs_before) and refs_before == refs_after and members == []
        and type(child_summary) is dict and child_summary.get('passed') is True
        and child_summary.get('actual_audit_episode_calls') == 1)
    common.write(output / 'guard_receipt.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', type=Path, required=True)
    parser.add_argument('--execution-freeze', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    def interrupted(number, _frame):
        raise RuntimeError('profiler guard received ' + signal.Signals(number).name)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    result = run(args.scope, args.execution_freeze, args.output)
    print(json.dumps({key: result[key] for key in ('passed', 'actual_returncode', 'actual_guard_seconds')}), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
