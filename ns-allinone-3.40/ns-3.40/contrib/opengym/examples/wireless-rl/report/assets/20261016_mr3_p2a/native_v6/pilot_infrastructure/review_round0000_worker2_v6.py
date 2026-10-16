"""CPU/offline review of the closed V6 worker2 episode; no live-run control."""

from decimal import Decimal
import hashlib
import json
from pathlib import Path
import time

from mr3_learning.audit_ppo import load_native_gates, native_decisions
from mr3_learning.audit_evaluator_phase import audit_episode


ROOT = Path('/home/zhuyulab/ns3-workspace')
RUN = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot'
FREEZE = 'af37b2aaa3cb9980434f7f16c1f52dec2506319d'


def require(value, message):
    if not value:
        raise ValueError(message)


def load(path):
    return json.loads(path.read_text())


def lines(path):
    return [json.loads(row) for row in path.read_text().splitlines() if row.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ns(value):
    value = Decimal(str(value)) * 1_000_000_000
    require(value.is_finite() and value == value.to_integral_value(), 'invalid exact ns')
    return int(value)


def proc(pid):
    try:
        rest = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return None
    return {'pid': pid, 'start_ticks': int(rest[19]), 'state': rest[0]}


def main(output=None):
    directory = RUN / 'native/round0000/worker2/episode001_open_101'
    # Never ask an immutable native auditor to interpret an active prefix as closed.
    require((directory / 'summary.json').exists()
            and (directory / 'supervisor_shutdown.json').exists(), 'episode not closed')
    phase, base, auditor, command, scalar, proof = load_native_gates(ROOT, FREEZE)
    require(len(proof) == 49, 'unexpected V6 source proof')
    metadata = load(directory / 'metadata.json')
    epoch = metadata['epoch']
    evaluation = load(directory / (epoch + '.json'))
    transitions = lines(directory / 'transitions.jsonl')
    adapter = lines(directory / 'adapter.jsonl')
    shutdown = load(directory / 'supervisor_shutdown.json')
    nav2 = load(directory / 'nav2_shutdown.json')
    result = {'schema': 'mr3-independent-v6-closed-episode-review-v1', 'freeze': FREEZE,
              'directory': str(directory), 'epoch': epoch, 'errors': [],
              'source_proof': proof, 'read_only_review_wall_monotonic_ns': time.monotonic_ns(),
              'scope': 'One closed native episode only; other workers and optimization '
                       'remain outside this receipt. Genuine task failure retained.'}

    def check(label, function):
        try:
            return function()
        except Exception as error:
            result['errors'].append(label + ': ' + repr(error))
            return None

    result['native'] = check('native/contact/clock/command/protocol', lambda:
        phase.corrected_audit(base, auditor, command, [directory]))
    result['scalar'] = check('causal scalar', lambda: scalar.audit_episode(directory, FREEZE))
    result['evaluator_phase'] = check('exact evaluator ACK', lambda: audit_episode(directory))
    check('native verdict', lambda: require(result['native']['passed'],
          str(result['native'].get('errors'))))
    check('scalar verdict', lambda: require(not result['scalar']['errors'],
          str(result['scalar']['errors'])))
    decisions, api_count = native_decisions(directory)
    last = transitions[-1]
    physical_end = ns(last['snapshot']['source_stamp'])
    frozen_end = ns(evaluation['end_sim_time_sec'])
    reward_end = ns(last['info']['reward_diagnostics']['effective_step_end'])
    lag = physical_end - frozen_end
    check('natural terminal bound', lambda: require(
        metadata['freeze'] == FREEZE and metadata['terminal_probe'] is False
        and last['terminated'] is True and last['truncated'] is False
        and last['info']['reason'] == 'navigation_failure' and reward_end == frozen_end
        and 0 <= lag <= 20_000_000, 'natural frozen terminal exceeds strict20ms boundary'))
    cause = json.loads(evaluation['control_failure'])
    check('actual peer-envelope failure', lambda: require(cause == {
        'component': 'peer_obstacles', 'reason': 'peer_body_envelopes_overlap'}
        and evaluation['success'] is False and evaluation['termination_reason'] ==
        'navigation_failure', 'failure cause/task verdict differs'))
    components = evaluation['contact_monitor_summary']['components']
    counts = {name: len(parts) for name, parts in components.items()}
    check('18 fresh contact streams', lambda: require(
        counts == {'tb1': 6, 'tb2': 6, 'tb3': 6}
        and evaluation['collision_monitoring_fresh'] is True
        and evaluation['contact_monitor_summary']['ever_unhealthy'] is False
        and evaluation['collision_events'] == 0, 'contact stream/freshness failure'))
    states = [(robot['robot'], row['node'], row['state'])
              for robot in nav2['robots'] for row in robot['states']]
    check('actual Nav2 shutdown', lambda: require(
        nav2['epoch'] == epoch and not nav2['failures'] and len(states) == 18
        and all(state == {'id': 4, 'label': 'finalized'} for _, _, state in states)
        and len(nav2['robots']) == 3
        and all(robot['shutdown']['response']['success'] is True for robot in nav2['robots'])
        and nav2['goal_ownership_closed']['epoch'] == epoch
        and nav2['goal_ownership_closed']['pending_goal_count'] == 0,
        'actual managed-node finalization or goal ownership closure failed'))
    identities = {(entry['pid'], entry['start_ticks']): entry
                  for entry in shutdown['owned_processes_seen']}
    worker = load(directory / 'supervisor_metadata.json')['worker_identity']
    identities[(worker['pid'], worker['start_ticks'])] = worker
    identity_checks = []
    for pid, start in sorted(identities):
        now = proc(pid)
        identity_checks.append({'pid': pid, 'start_ticks': start, 'current': now,
                               'same_owned_identity_exists': now is not None
                               and now['start_ticks'] == start})
    check('exact saved PID/start closure', lambda: require(
        shutdown['epoch'] == epoch and shutdown['worker_returncode'] == 0
        and shutdown['failed_sample'] is False and shutdown['forced_shutdown'] is False
        and not shutdown['remaining_owned_processes']
        and not shutdown['remaining_owned_zombies']
        and all(not row['same_owned_identity_exists'] for row in identity_checks),
        'owned identity remains or cleanup failed'))
    safety = [row for row in adapter if row['kind'] == 'safety_stop']
    unsent = [row for row in adapter if row['kind'] == 'edge_goal_not_sent']
    result.update(decisions=len(decisions), api_records=api_count,
                  effective_time_ns=sum(ns(row['dt']) for row in decisions),
                  final_physical_time_ns=physical_end, frozen_terminal_time_ns=frozen_end,
                  final_reward_effective_time_ns=reward_end, terminal_lag_ns=lag,
                  last_transition_dt_ns=ns(last['info']['dt']),
                  last_transition_physical_dt_ns=ns(last['info']['physical_dt']),
                  contact_component_counts=counts, collision_events=evaluation['collision_events'],
                  safety_stops=safety, edge_goal_not_sent=unsent, failure_cause=cause,
                  actual_finalized_managed_nodes=states,
                  goal_ownership_closed=nav2['goal_ownership_closed'],
                  owned_identity_checks=identity_checks,
                  task={key: evaluation[key] for key in ('success', 'termination_reason',
                      'elapsed_sim_time_sec', 'correct_free_coverage_ratio', 'map_quality_pass',
                      'robot_participation_pass', 'navigation_protocol_closed')},
                  strict_task_success_credit=False)
    names = ('metadata.json', 'summary.json', 'transitions.jsonl', 'physics.jsonl',
             'adapter.jsonl', 'launch.log', 'evaluator_phase_worker.jsonl',
             'evaluator_phase_evaluator.jsonl', 'supervisor_metadata.json',
             'supervisor_shutdown.json', 'nav2_shutdown.json', epoch + '.json')
    result['artifact_sha256'] = {name: sha(directory / name) for name in names}
    result['repro_script_sha256'] = sha(Path(__file__).resolve())
    result['passed'] = not result['errors']
    output = Path(output) if output else RUN / 'round0000_worker2_native_review_v6.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'errors': result['errors'],
                      'decisions': len(decisions), 'api': api_count, 'lag_ns': lag,
                      'owned_identities': len(identity_checks), 'output': str(output),
                      'sha256': sha(output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    import sys
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else None))
