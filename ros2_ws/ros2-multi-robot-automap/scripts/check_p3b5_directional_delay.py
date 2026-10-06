#!/usr/bin/env python3
"""Audit independently delayed TASK pairs without changing the v106 gate."""
import argparse
import json
import shlex
from pathlib import Path

from check_p3b5_gate import (
    CORE_KEYS, ROOT, Snapshot, bootstrap, episode_ok, ledger_audit,
    load, runtime_violations, same_candidate, sha,
)
from run_p2d_baseline import file_digest
from run_p3b5_tasks import ledger_metrics, tdi


def validate_declaration(config):
    cases = config['cases']
    assert len(cases) == 4 and len({c['id'] for c in cases}) == 4
    assert {(c['direction'], c['delay_sec']) for c in cases} == {
        (direction, delay) for direction in ('uplink', 'downlink') for delay in (.5, 2.)}
    for case in cases:
        profile = config['profiles'][case['profile']]
        expected = {direction + '_delay_sec': case['delay_sec'] if direction == case['direction'] else 0.
                    for direction in ('uplink', 'downlink')}
        assert profile == expected, 'Delay must affect exactly one direction'
        contract = case['frozen_contract']
        scenario = config['scenarios'][case['scenario']]
        assert contract['world'] == scenario['world']
        assert contract['target'] == [scenario['target_x'], scenario['target_y']]
        assert contract['robot_count'] == scenario['robot_count']
        assert contract['gazebo_seed'] == scenario['seed']
        assert contract['battery_config']['initial_energy'] == scenario['energy']
        assert contract['battery_config']['capacity'] == 100
        assert contract['mission_mode'] == case['mode'] == 'rally'
        assert contract['episode_horizon_sec'] == config['duration_sec'] == 300
        assert contract['fault_seed'] == config['fault_seed'] == 17011
        assert contract['ttl_sec_by_type'] == config['ttl_sec_by_type']
        assert contract['navigation_deadline_sec'] == 90
        assert contract['retry'] == {'ack_timeout_sec': 1., 'max_retries': 2}
        assert contract['queue_capacity'] == 0
        for direction in ('uplink', 'downlink'):
            assert contract[direction + '_fault'] == {
                'loss_rate': 0., 'delay_sec': expected[direction + '_delay_sec']}


def delay_audit(path, direction, delay):
    latencies = []
    for line in path.open():
        event = json.loads(line)
        if event['event'] == 'delivered' and event['direction'] == direction:
            latency = event['time'] - event['tx_time']
            assert latency + 1e-8 >= delay, 'Configured delay was bypassed'
            latencies.append(latency)
    assert latencies, 'No actual delayed delivery evidence'
    return {'direction': direction, 'configured_delay_sec': delay,
            'delivery_attempt_count': len(latencies), 'minimum_tx_delivery_sec': min(latencies)}


def target_audit(row, scenario):
    """Bind the configured target without inventing an undetected observation."""
    command = shlex.split(row['command'])
    expected = [scenario['target_x'], scenario['target_y']]
    for option, coordinate in zip(('--target-x', '--target-y'), expected):
        assert command.count(option) == 1
        assert float(command[command.index(option) + 1]) == coordinate
    result = row['result']
    observed = [result['target_x'], result['target_y']]
    if result['target_found']:
        assert observed == expected
    else:
        assert observed == [None, None] and result['time_to_detect_sec'] is None


def audit(base, summaries, config_path):
    config = load(config_path)
    validate_declaration(config)
    assert base['status'] == 'PASS' and base['all_gate_unique_episode_count'] == 57
    cases = {c['id']: c for c in config['cases']}
    pairs, episodes, reference = {}, {}, summaries[0]['manifest']
    for summary in summaries:
        assert summary['config'] == config
        same_candidate(summary['manifest'], reference)
        assert summary['manifest']['generated_at_utc'] >= config['declared_at_utc']
        assert summary['manifest']['source_digests']['scenario_config'] == file_digest(config_path)
        for key in CORE_KEYS:
            assert summary['manifest']['source_digests'][key] == base['task_core_source_digests'][key], key
        assert not (pairs.keys() & summary['pairs'].keys()), 'Repeated supplementary case'
        pairs.update(summary['pairs'])
        assert not (episodes.keys() & summary['episodes'].keys()), 'Repeated original episode'
        episodes.update(summary['episodes'])
    assert pairs.keys() == cases.keys() and len(episodes) == 6
    bypass = load(ROOT/'src/multi_robot_exploration/config/p3a_forbidden_bypasses.json')
    audited = {}
    for identity, row in episodes.items():
        assert not row['infrastructure_failure'] and not row['operational_failure']
        assert row['episode_started'] and row['runner_returncode'] == row['observer_returncode'] == 0
        result = row['result']
        assert result['mission_mode'] == 'rally'
        assert result['collision_monitoring_active'] and result['collision_events'] == 0
        assert result['battery_minimum_energy'] > 0 and not result['failed_robots']
        assert result['elapsed_sim_time_sec'] <= 300.6
        directory = Path(row['result_path']).parent
        assert load(Path(row['result_path'])) == result
        for field, name in [('result_sha256', identity+'.json'), ('graph_sha256', 'graph.json'),
                            ('safety_events_sha256', 'safety_events.jsonl')]:
            assert row[field] == file_digest(directory/name)
        assert row['communication']['ledger_sha256'] == file_digest(directory/'ledger.jsonl')
        assert not runtime_violations(Snapshot(load(directory/'graph.json')['nodes']), bypass, result['robot_count'])
        if result['success']:
            episode_ok(result)
        else:
            assert result['task_phase'] != 'COMPLETE' and result['completion_time_sec'] is None
        audited[identity] = {'command': row['command'], 'result': result,
            'result_path': row['result_path'],
            'content_sha256': {name: sha(directory/name) for name in
                (identity+'.json', 'graph.json', 'ledger.jsonl', 'safety_events.jsonl')},
            'ledger_audit': ledger_audit(directory/'ledger.jsonl'),
            'communication': ledger_metrics(directory/'ledger.jsonl', result['start_sim_time_sec'], result['end_sim_time_sec'])}
    rows, values = [], []
    for case_id, pair in pairs.items():
        ideal, fault = (episodes[pair[mode]] for mode in ('ideal', 'fault'))
        case = cases[case_id]
        assert ideal['settings'] == fault['settings']
        assert fault['profile'] == config['profiles'][case['profile']]
        for row in (ideal, fault):
            result, scenario = row['result'], config['scenarios'][case['scenario']]
            assert result['world_file'].endswith(scenario['world'])
            assert result['gazebo_seed'] == scenario['seed'] and result['robot_count'] == scenario['robot_count']
            target_audit(row, scenario)
        ir, fr = ideal['result'], fault['result']
        value = tdi(ir, fr)
        if value is not None:
            s = case['frozen_contract']
            cluster = json.dumps([s['world'], s['robot_count'], s['gazebo_seed'], s['battery_config']['initial_energy']])
            values.append((cluster, value))
        rows.append({'case_id': case_id, **pair, 'tdi': value,
                     'ideal_status': ir['termination_reason'], 'fault_status': fr['termination_reason'],
                     'delay_audit': delay_audit(Path(fault['result_path']).parent/'ledger.jsonl', case['direction'], case['delay_sec'])})
    return {'status': 'PASS', 'scope': 'Four additional independently delayed TASK pairs; original57 unchanged',
            'config': config, 'manifest': reference, 'supplementary_unique_episodes': len(episodes),
            'paired_results': rows, 'tdi': bootstrap(values), 'episodes': audited}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', required=True, type=Path)
    parser.add_argument('--config', required=True, type=Path)
    parser.add_argument('--summaries', nargs='+', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(load(args.base), [load(path) for path in args.summaries], args.config)
    report['base_report'] = {'path': str(args.base), 'content_sha256': sha(args.base)}
    report['summary_evidence'] = [{'path': str(path), 'content_sha256': sha(path)} for path in args.summaries]
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({'status': report['status'], 'episodes': report['supplementary_unique_episodes'], 'tdi': report['tdi']}))


if __name__ == '__main__':
    main()
