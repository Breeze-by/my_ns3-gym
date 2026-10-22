"""Disabled prospective child: one direct original audit_episode call only."""
import argparse
import cProfile
from decimal import Decimal
import hashlib
import os
from pathlib import Path
import pstats
import resource
import signal
import sys
import time
import traceback

from . import profile_common_v1 as common


class ProfileInterrupted(RuntimeError):
    pass


def run(scope_path, scope_sha, execution_freeze, output, deadline_ns):
    started, cpu_start = time.monotonic_ns(), time.process_time_ns()
    profile, result, error, calls = cProfile.Profile(), None, None, 0
    stats_path = output / 'runtime.pstats'
    stats_path.open('xb').close()  # Exclusively claimed; never overwrite an earlier run.
    summary = dict(schema='mr3-single-ep-runtime-profile-child-v1', passed=False, partial=True,
        native_evidence_freeze=common.EVIDENCE_FREEZE, profiling_execution_freeze=execution_freeze,
        episode=str(common.EPISODE), child_identity=common.identity(os.getpid()),
        actual_argv=sys.argv, interpreter=sys.executable, python_version=sys.version,
        cwd=str(Path.cwd()), actual_audit_episode_calls=0, signal_received=None,
        no_new_native_or_scientific_qualification=True, models_loaded=False, gpu_calls=0, optimizer_updates=0)

    def terminate(number, _frame):
        summary['signal_received'] = signal.Signals(number).name
        raise ProfileInterrupted('profiling child received ' + summary['signal_received'])

    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    try:
        common.require(Path.cwd() == common.W and Path(sys.executable).resolve() == Path('/usr/bin/python3').resolve(),
                       'system interpreter/canonical cwd required')
        guard = common.read_json(output / 'guard_identity.json')
        child = summary['child_identity']
        common.require(child['parent'] == guard['pid'] and child['group'] == child['session'] == child['pid'],
                       'profiling child was not spawned by the saved guard into its owned session')
        scope_binding = common.bind(scope_path, deadline_ns=deadline_ns)
        common.require(scope_binding['sha256'] == scope_sha, 'scope changed since guard admission')
        scope = common.read_json(scope_path)
        common.validate_scope(scope)
        common.bind(scope['interpreter']['path'], scope['interpreter'], deadline_ns)
        evidence = {row['path']: row for row in scope['evidence_sources']}
        for name in (common.RUNTIME, common.SUPPORT, common.INIT):
            common.bind(common.ROOT / name, evidence[name], deadline_ns)
        from mr3_learning import audit_reach_runtime as runtime
        common.require(Path(runtime.__file__).resolve() == common.ROOT / common.RUNTIME,
                       'runtime import did not resolve to canonical original reader')
        summary['runtime_module_path'] = str(Path(runtime.__file__).resolve())
        metadata = common.read_json(next(spec['path'] for spec in scope['inputs']
                                        if spec['logical_name'] == 'metadata.json'))
        common.require(metadata['epoch'] == scope['epoch'] and metadata['freeze'] == common.EVIDENCE_FREEZE
            and metadata.get('safety_contract') == 'mr3-reach-v1'
            and metadata.get('seed_rule') == 'exact-point-bridge-v2'
            and metadata.get('start_graph_rule') == 'point-attachment-3x3-v1'
            and metadata.get('reach_geometry_rule') == 'cone-support-v2', 'fixed episode declarations differ')
        common.remaining(deadline_ns)
        summary.update(profile_started_monotonic_ns=time.monotonic_ns(), epoch=scope['epoch'])
        profile.enable()
        try:
            calls += 1
            result = runtime.audit_episode(common.EPISODE, expected_freeze=common.EVIDENCE_FREEZE)
        finally:
            profile.disable()
            summary['profile_ended_monotonic_ns'] = time.monotonic_ns()
        common.require(type(result) is dict and result.get('passed') is True
            and result.get('epoch') == scope['epoch'] and result.get('freeze') == common.EVIDENCE_FREEZE
            and result.get('independent_necessary_replay') is True
            and result.get('continuous_physical_model_proved') is False,
            'original runtime returned FAIL/incomplete; no profile-completion PASS')
        common.require(set(result['artifact_proof']) == set(common.INPUTS), 'original report input set differs')
        for spec in scope['inputs']:
            proof = result['artifact_proof'][spec['logical_name']]
            common.require(proof['path'] == spec['path'] and proof['sha256'] == spec['sha256'],
                           'original runtime artifact proof differs from fixed input binding')
        common.require(set(result['source_proof']) == common.EVIDENCE_SOURCES - {common.INIT},
                       'original runtime source proof set differs')
        helper = sys.modules.get('mr3_learning.reach_support_replay')
        summary['independent_support_module_path'] = None if helper is None else str(Path(helper.__file__).resolve())
        common.require(helper is None or Path(helper.__file__).resolve() == common.ROOT / common.SUPPORT,
                       'independent support import resolved outside canonical source')
        forbidden = sorted(name for name in sys.modules if name.split('.')[0] in
            {'torch', 'rclpy', 'multi_robot_exploration', 'numpy', 'scipy', 'gymnasium', 'sb3_contrib'})
        summary['unexpected_application_imports'] = forbidden
        common.require(not forbidden, 'application/model dependency imported during stdlib-only profile')
        summary['partial'] = False
    except BaseException as caught:
        error = caught
        summary['exception'] = dict(type=type(caught).__name__, message=str(caught), traceback=traceback.format_exc())
    finally:
        profile.disable()
        summary['actual_audit_episode_calls'] = calls
        try:
            if calls:
                profile.dump_stats(str(stats_path))
                stats = pstats.Stats(profile)
                rows = [dict(filename=filename, line=line, function=function, primitive_calls=cc,
                    total_calls=nc, self_seconds=tt, cumulative_seconds=ct)
                    for (filename, line, function), (cc, nc, tt, ct, _) in stats.stats.items()]
                summary['top_self'] = sorted(rows, key=lambda r: r['self_seconds'], reverse=True)[:40]
                summary['top_cumulative'] = sorted(rows, key=lambda r: r['cumulative_seconds'], reverse=True)[:40]
                summary['target_call_count'] = sum(row['total_calls'] for row in rows
                    if row['filename'] == str(common.ROOT / common.RUNTIME) and row['function'] == 'audit_episode')
                summary['forbidden_run_dispatch_calls'] = sum(row['total_calls'] for row in rows
                    if row['filename'] == str(common.ROOT / common.RUNTIME)
                    and row['function'] in ('audit', 'audit_episode_set'))
            summary['pstats'] = common.bind(stats_path)
            if result is not None:
                common.write(output / 'runtime_result.json', result)
            summary.update(ended_monotonic_ns=time.monotonic_ns(), started_monotonic_ns=started,
                process_cpu_seconds=str(Decimal(time.process_time_ns() - cpu_start) / 10**9),
                wall_seconds=str(Decimal(time.monotonic_ns() - started) / 10**9),
                peak_self_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
            summary['passed'] = (error is None and not summary['partial'] and calls == 1
                and summary.get('target_call_count') == 1 and summary.get('forbidden_run_dispatch_calls') == 0
                and summary['signal_received'] is None)
            common.write(output / 'child_summary.json', summary)
        except BaseException:
            # Preserve pstats/console prefixes. Never synthesize a completed report.
            traceback.print_exc()
            if error is None:
                raise
    if error is not None:
        raise error
    return 0 if summary['passed'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scope', type=Path, required=True)
    parser.add_argument('--scope-sha256', required=True)
    parser.add_argument('--execution-freeze', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--deadline-ns', type=int, required=True)
    args = parser.parse_args()
    return run(args.scope, args.scope_sha256, args.execution_freeze, args.output, args.deadline_ns)


if __name__ == '__main__':
    raise SystemExit(main())
