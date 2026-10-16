"""Offline V6 pilot component/identity audit, preserving the native-stop failure."""

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


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def ns(value):
    value = Decimal(str(value)) * 1_000_000_000
    assert value.is_finite() and value == value.to_integral_value()
    return int(value)


def proc(pid):
    try:
        rest = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        return None
    return {'pid': pid, 'start_ticks': int(rest[19]), 'state': rest[0]}


def main(output=None):
    summary = load(RUN / 'summary.json')
    assert summary['freeze'] == FREEZE and summary['completed'] is False
    assert summary['optimizer_updates'] == 0 and not (RUN / 'final.zip').exists()
    phase, base, auditor, command, scalar, proof = load_native_gates(ROOT, FREEZE)
    assert len(proof) == 49
    result = {'schema': 'mr3-independent-v6-pilot-closure-review-v1', 'freeze': FREEZE,
              'source_proof': proof, 'episodes': [], 'review_errors': [],
              'review_wall_monotonic_ns': time.monotonic_ns(),
              'run_outcome': {key: summary[key] for key in ('error', 'error_type',
                  'completed', 'cleanup_errors', 'optimizer_updates', 'native_api_records',
                  'native_recorded_decisions', 'native_effective_sim_seconds',
                  'native_physical_sim_seconds', 'collector_observed_decisions',
                  'collector_observed_api_records', 'wall_sec_including_all_attempts')},
              'final_checkpoint_present': False, 'policy_validation_permitted': False,
              'strict95_task_success_credit': 0,
              'scope': 'Component audit only. Native infrastructure failure remains FAIL; '
                       'no source/native/learner edits, training, inference or process control.'}
    all_ids, parents = {}, set()
    total_api = total_decisions = effective_ns = physical_ns = 0
    for index in range(4):
        directory = RUN / f'native/round0000/worker{index}/episode001_open_101'
        native_meta = load(directory / 'metadata.json')
        epoch = native_meta['epoch']
        transitions = lines(directory / 'transitions.jsonl')
        evaluation = load(directory / (epoch + '.json'))
        shutdown = load(directory / 'supervisor_shutdown.json')
        supervisor = load(directory / 'supervisor_metadata.json')
        nav2 = load(directory / 'nav2_shutdown.json')
        parents.add(supervisor['worker_identity']['parent'])
        row = {'worker': index, 'epoch': epoch, 'directory': str(directory),
               'components': {}, 'component_exceptions': {}}
        result['episodes'].append(row)
        for name, operation in (
            ('native', lambda: phase.corrected_audit(base, auditor, command, [directory])),
            ('scalar', lambda: scalar.audit_episode(directory, FREEZE)),
            ('evaluator_phase', lambda: audit_episode(directory))):
            try:
                row['components'][name] = operation()
            except Exception as error:
                row['component_exceptions'][name] = repr(error)
        decisions, api = native_decisions(directory)
        total_api += api
        total_decisions += len(decisions)
        effective_ns += sum(ns(step['info']['dt']) for step in transitions[1:])
        physical_ns += sum(ns(step['info'].get('physical_dt', step['info']['dt']))
                           for step in transitions[1:])
        identities = {(entry['pid'], entry['start_ticks']): entry
                      for entry in shutdown['owned_processes_seen']}
        worker = supervisor['worker_identity']
        identities[(worker['pid'], worker['start_ticks'])] = worker
        id_checks = []
        for pid, start in sorted(identities):
            now = proc(pid)
            value = {'pid': pid, 'start_ticks': start, 'current': now,
                     'same_owned_identity_exists': now is not None and now['start_ticks'] == start}
            id_checks.append(value)
            all_ids[(pid, start)] = value
        states = [(robot['robot'], state['node'], state['state'])
                  for robot in nav2['robots'] for state in robot['states']]
        nav2_complete = (not nav2['failures'] and nav2['epoch'] == epoch
                        and len(states) == 18 and len(nav2['robots']) == 3
                        and all(state == {'id': 4, 'label': 'finalized'} for _, _, state in states)
                        and all(robot['shutdown']['response']['success'] is True
                                for robot in nav2['robots'])
                        and nav2['goal_ownership_closed']['pending_goal_count'] == 0)
        contacts = evaluation['contact_monitor_summary']
        counts = {name: len(parts) for name, parts in contacts['components'].items()}
        last = transitions[-1]
        frozen = ns(evaluation['end_sim_time_sec'])
        physical = ns(last['snapshot']['source_stamp'])
        lag = physical - frozen
        row.update(api_records=api, native_decisions=len(decisions),
                   last_dt_ns=ns(last['info']['dt']),
                   effective_ns=sum(ns(step['info']['dt']) for step in transitions[1:]),
                   last_physical_dt_ns=ns(last['info'].get('physical_dt', last['info']['dt'])),
                   frozen_terminal_time_ns=frozen, last_sample_physical_time_ns=physical,
                   observed_terminal_lag_ns=lag, terminal_bound_pass=0 <= lag <= 20_000_000,
                   contact_component_counts=counts, contacts_fresh=contacts['fresh'],
                   contacts_ever_unhealthy=contacts['ever_unhealthy'],
                   collision_events=evaluation['collision_events'],
                   actual_nav2_finalization_pass=nav2_complete, finalized_states=states,
                   goal_ownership_closed=nav2['goal_ownership_closed'],
                   supervisor_verdict={key: shutdown[key] for key in ('worker_returncode',
                       'forced_shutdown', 'failed_sample', 'remaining_owned_processes',
                       'remaining_owned_zombies')},
                   saved_identity_checks=id_checks,
                   worker_summary_present=(directory / 'summary.json').exists(),
                   native_stop_receipt_present=(directory / 'native_stop.json').exists(),
                   control_failure=evaluation['control_failure'],
                   task={key: evaluation[key] for key in ('success', 'termination_reason',
                       'elapsed_sim_time_sec', 'correct_free_coverage_ratio', 'map_quality_pass',
                       'robot_participation_pass', 'navigation_protocol_closed')})
        native_pass = row['components'].get('native', {}).get('passed', False)
        scalar_pass = not row['components'].get('scalar', {'errors': ['missing']})['errors']
        ack_pass = row['components'].get('evaluator_phase', {}).get('passed', False)
        clean = (shutdown['worker_returncode'] == 0 and shutdown['forced_shutdown'] is False
                 and shutdown['failed_sample'] is False)
        row['valid_closed_native_episode'] = (native_pass and scalar_pass and ack_pass and clean
                                              and nav2_complete and row['terminal_bound_pass'])
        row['classification'] = ('infrastructure-invalid native stop; frozen timeout retained '
                                 'without valid returned terminal/learning credit' if index == 0
                                 else 'genuine peer-envelope task failure' if index in (1, 2)
                                 else 'genuine300s timeout task failure')
        assert evaluation['success'] is False
        if index == 0:
            assert not native_pass and not clean
        else:
            if not row['valid_closed_native_episode']:
                result['review_errors'].append(f'worker{index}: unexpected closed-native failure')
        names = ('metadata.json', 'transitions.jsonl', 'physics.jsonl', 'adapter.jsonl',
                 'launch.log', 'evaluator_phase_worker.jsonl', 'evaluator_phase_evaluator.jsonl',
                 'supervisor_metadata.json', 'supervisor_shutdown.json', 'nav2_shutdown.json',
                 'summary.json', 'native_stop.json', epoch + '.json')
        row['artifact_sha256'] = {name: sha(directory / name) for name in names
                                  if (directory / name).exists()}
    parent_checks = [{'pid': pid, 'current': proc(pid)} for pid in sorted(parents)]
    identities_absent = all(not item['same_owned_identity_exists'] for item in all_ids.values())
    parents_absent = all(item['current'] is None for item in parent_checks)
    assert identities_absent and parents_absent
    assert total_api == total_decisions == summary['native_api_records'] == 718
    assert effective_ns == physical_ns == ns(summary['native_effective_sim_seconds'])
    assert total_api - summary['collector_observed_api_records'] == 1
    result.update(unique_saved_identity_count=len(all_ids), all_saved_identities_absent=identities_absent,
                  parent_pid_checks=parent_checks, all_parents_absent=parents_absent,
                  native_api_records=total_api, native_decisions=total_decisions,
                  effective_time_ns=effective_ns, physical_time_ns=physical_ns,
                  raw_minus_returned_api_records=1,
                  missing_returned_sample_scope='worker0 final300th native transition is recorded '
                      'before shutdown raises; it is absent from collector returns. No trained rollout exists.',
                  source_receipts={'metadata.json': sha(RUN / 'metadata.json'),
                                   'summary.json': sha(RUN / 'summary.json')},
                  reproducible_script_sha256=sha(Path(__file__).resolve()),
                  review_completed=True, pilot_verdict='FAIL_INFRASTRUCTURE',
                  no_additional_unexpected_component_failure=not result['review_errors'])
    output = Path(output) if output else RUN / 'independent_pilot_closure_review_v6.json'
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(output), 'sha256': sha(output),
                      'review_errors': result['review_errors'], 'saved_identities': len(all_ids),
                      'parents': parent_checks, 'classification': [
                          {'worker': row['worker'], 'native_pass': row['components'].get(
                              'native', {}).get('passed'), 'valid': row['valid_closed_native_episode'],
                           'terminal_lag_ns': row['observed_terminal_lag_ns'],
                           'classification': row['classification']} for row in result['episodes']]}))


if __name__ == '__main__':
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
