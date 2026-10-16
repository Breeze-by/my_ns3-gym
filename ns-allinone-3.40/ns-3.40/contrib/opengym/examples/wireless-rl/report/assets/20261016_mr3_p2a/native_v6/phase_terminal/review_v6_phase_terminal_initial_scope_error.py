"""Independent CPU/offline V6 terminal benchmark review; never launches ROS."""

import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess
import time

from mr3_learning.audit_ppo import load_native_gates
from mr3_learning.audit_evaluator_phase import audit_episode


ROOT = Path('/home/zhuyulab/ns3-workspace')
FREEZE = 'af37b2aaa3cb9980434f7f16c1f52dec2506319d'
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(row) for row in path.read_text().splitlines() if row.strip()]


def ns(value):
    result = Decimal(str(value)) * 1_000_000_000
    require(result.is_finite() and result == result.to_integral_value(),
            'nonintegral/nonfinite native ns')
    return int(result)


def current_identity(pid):
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return None
    return {'pid': pid, 'start_ticks': int(fields[19]), 'state': fields[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    directory = args.directory.resolve()
    summary = load(directory / 'benchmark_summary.json')
    metadata = load(directory / 'benchmark_metadata.json')
    require(summary['freeze'] == metadata['freeze'] == FREEZE, 'wrong native source freeze')
    phase, base, auditor, command, scalar, proof = load_native_gates(ROOT, FREEZE)
    require(len(proof) == 49, 'unexpected V6 source proof size')
    relative = 'mr3_learning/benchmark.py'
    frozen = subprocess.check_output(['git', 'show', FREEZE + ':' +
        str((WIRELESS / relative).relative_to(ROOT))], cwd=ROOT)
    require((WIRELESS / relative).read_bytes() == frozen, 'benchmark source differs from freeze')
    proof[str((WIRELESS / relative).relative_to(ROOT))] = {
        'sha256': hashlib.sha256(frozen).hexdigest(), 'git_source': FREEZE + ':' +
        str((WIRELESS / relative).relative_to(ROOT))}
    result = {'schema': 'mr3-independent-v6-terminal-review-v1', 'freeze': FREEZE,
              'source_proof': proof, 'episodes': [], 'errors': [],
              'review_wall_monotonic_ns': time.monotonic_ns(),
              'training_updates': 0, 'actor_policy_inference_calls': 0,
              'strict_95_percent_success_credit': 0,
              'scope': 'Scripted sampling/reset/ACK/shutdown engineering probe only; '
                       'injected task failures, no training or mapping success claim.',
              'source_receipts': {name: sha(directory / name) for name in
                                  ('benchmark_metadata.json', 'benchmark_summary.json')}}

    def check(label, operation):
        try:
            return operation()
        except Exception as error:
            result['errors'].append(label + ': ' + repr(error))
            return None

    check('benchmark verdict', lambda: require(summary['passed'] is True,
                                               'benchmark declared failure'))
    check('scripted probe metadata', lambda: require(
        metadata['kind'] == 'scripted_p1c_sampling_not_rl' and metadata['workers'] == 1
        and metadata['robots_per_worker'] == 3 and metadata['terminal_probe'] is True
        and metadata['steps_per_episode'] == 4 and metadata['schedule'] == [['open', 101]] * 2,
        'wrong prospectively declared probe'))
    episodes = [entry for worker in summary['workers_results'] for entry in worker['episodes']]
    check('episode count', lambda: require(len(episodes) == 2, 'two episodes required'))
    all_identities = {}
    total_effective_ns = total_physical_ns = api_records = submitted_decisions = 0
    for index, episode in enumerate(episodes):
        native = Path(episode['output_directory'])
        native_meta = load(native / 'metadata.json')
        epoch = native_meta['epoch']
        rows = lines(native / 'transitions.jsonl')
        steps = rows[1:]
        evaluation = load(native / (epoch + '.json'))
        shutdown = load(native / 'supervisor_shutdown.json')
        nav2 = load(native / 'nav2_shutdown.json')
        row = {'directory': str(native), 'epoch': epoch, 'index': index,
               'native': check(epoch + ' original native gates', lambda:
                   phase.corrected_audit(base, auditor, command, [native])),
               'scalar': check(epoch + ' causal scalar', lambda:
                   scalar.audit_episode(native, FREEZE)),
               'evaluator_phase': check(epoch + ' ACK receipts', lambda: audit_episode(native))}
        result['episodes'].append(row)
        check(epoch + ' native verdict', lambda: require(row['native']['passed'],
              str(row['native'].get('errors'))))
        check(epoch + ' scalar verdict', lambda: require(not row['scalar']['errors'],
              str(row['scalar']['errors'])))
        expected = [1_000_000_000] * 3 + [20_000_000 if index == 0 else 0]
        actual = [ns(step['info']['dt']) for step in steps]
        physical = [ns(step['info']['physical_dt']) for step in steps]
        submitted = [step['info'].get('action_submitted', True) for step in steps]
        check(epoch + ' source and terminal samples', lambda: require(
            native_meta['freeze'] == FREEZE and native_meta['terminal_probe'] is True
            and len(steps) == 4 and actual == expected and physical == expected
            and all(not step['terminated'] and not step['truncated'] for step in steps[:3])
            and steps[-1]['terminated'] is True and steps[-1]['truncated'] is False
            and steps[-1]['info']['reason'] == 'navigation_failure'
            and submitted == [True, True, True, index == 0],
            'short/zero submitted-action terminal sampling differs'))
        if index == 1:
            check(epoch + ' no-action zero tail', lambda: require(
                steps[-1]['info']['command'] is None
                and steps[-1]['info']['terminal_observation_reused'] is True
                and steps[-1]['snapshot'] == steps[-2]['snapshot']
                and steps[-1]['info']['watermarks'] == steps[-2]['info']['watermarks'],
                'zero no-action tail does not reuse settled snapshot/watermarks'))
        contact = evaluation['contact_monitor_summary']
        components = contact['components']
        component_counts = {robot: len(values) for robot, values in components.items()}
        check(epoch + ' 18 contact streams', lambda: require(
            set(component_counts) == {'tb1', 'tb2', 'tb3'}
            and all(count == 6 for count in component_counts.values())
            and contact['fresh'] is True and contact['ever_unhealthy'] is False
            and evaluation['collision_monitoring_fresh'] is True
            and evaluation['collision_events'] == 0, 'contact coverage/freshness failed'))
        finalized = [(robot['robot'], state['node'], state['state'])
                     for robot in nav2['robots'] for state in robot['states']]
        check(epoch + ' actual Nav2 finalization', lambda: require(
            nav2['epoch'] == epoch and not nav2['failures'] and len(finalized) == 18
            and len(nav2['robots']) == 3 and all(state['id'] == 4
                and state['label'] == 'finalized' for _, _, state in finalized)
            and all(robot['shutdown']['response']['success'] is True for robot in nav2['robots'])
            and nav2['goal_ownership_closed']['pending_goal_count'] == 0
            and evaluation['navigation_protocol_closed'] is True,
            'actual managed-node shutdown or goal ownership closure failed'))
        identities = {(entry['pid'], entry['start_ticks']): entry
                      for entry in shutdown['owned_processes_seen']}
        initial_identity = load(native / 'supervisor_metadata.json')['worker_identity']
        identities[(initial_identity['pid'], initial_identity['start_ticks'])] = initial_identity
        identity_checks = []
        for key, entry in sorted(identities.items()):
            now = current_identity(entry['pid'])
            same = now is not None and now['start_ticks'] == entry['start_ticks']
            identity_checks.append({'pid': entry['pid'], 'start_ticks': entry['start_ticks'],
                                    'same_owned_identity_exists': same, 'current': now})
            all_identities[key] = identity_checks[-1]
        check(epoch + ' saved identity absence', lambda: require(
            shutdown['epoch'] == epoch and shutdown['worker_returncode'] == 0
            and shutdown['forced_shutdown'] is False and shutdown['failed_sample'] is False
            and not shutdown['remaining_owned_processes']
            and not shutdown['remaining_owned_zombies']
            and all(not entry['same_owned_identity_exists'] for entry in identity_checks),
            'owned PID/start identity remains or closure failed'))
        check(epoch + ' task meaning', lambda: require(
            evaluation['success'] is False
            and evaluation['termination_reason'] == 'navigation_failure'
            and episode['terminated'] is True and episode['truncated'] is False,
            'injected task failure was granted task success credit'))
        row.update(dt_ns=actual, physical_dt_ns=physical, action_submitted=submitted,
                   component_counts=component_counts, collision_events=evaluation['collision_events'],
                   collision_monitoring_fresh=evaluation['collision_monitoring_fresh'],
                   finalized_managed_node_count=len(finalized), finalized_states=finalized,
                   owned_identity_checks=identity_checks,
                   task={key: evaluation[key] for key in ('success', 'termination_reason',
                       'elapsed_sim_time_sec', 'correct_free_coverage_ratio', 'map_quality_pass',
                       'robot_participation_pass', 'navigation_protocol_closed')})
        names = ('metadata.json', 'transitions.jsonl', 'physics.jsonl', 'adapter.jsonl',
                 'evaluator_phase_worker.jsonl', 'evaluator_phase_evaluator.jsonl',
                 'supervisor_metadata.json', 'supervisor_shutdown.json', 'nav2_shutdown.json',
                 'diagnostic_failure.jsonl', epoch + '.json')
        row['artifact_sha256'] = {name: sha(native / name) for name in names}
        total_effective_ns += sum(actual)
        total_physical_ns += sum(physical)
        api_records += len(steps)
        submitted_decisions += sum(submitted)
    result.update(api_records=api_records, submitted_scripted_decisions=submitted_decisions,
                  effective_time_ns=total_effective_ns, physical_sample_time_ns=total_physical_ns,
                  exact_owned_identity_count=len(all_identities),
                  all_saved_owned_identities_absent=all(not item['same_owned_identity_exists']
                                                       for item in all_identities.values()),
                  wall_sec_including_all_attempts=summary['wall_sec_including_all_attempts'])
    result['repro_script_sha256'] = sha(Path(__file__).resolve())
    result['passed'] = not result['errors']
    output = args.output or directory / 'independent_review_v6.json'
    with output.open('x') as sink:
        json.dump(result, sink, indent=2)
        sink.write('\n')
    print(json.dumps({'passed': result['passed'], 'errors': result['errors'],
                      'output': str(output), 'sha256': sha(output),
                      'identities': len(all_identities), 'api_records': api_records,
                      'submitted_decisions': submitted_decisions,
                      'effective_time_ns': total_effective_ns}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
