"""Actual actuator-target versus earlier final guard value compatibility."""
import argparse
from bisect import bisect_right
import hashlib
import json
from pathlib import Path


def rows(path):
    with path.open() as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    transitions = list(rows(args.episode/'transitions.jsonl'))
    release = transitions[0]['info']['release_time_ns']
    task_end = release + sum(round(row['info']['dt']*1e9) for row in transitions if row['kind'] == 'step')
    by_robot = {name: [] for name in ('tb1', 'tb2', 'tb3')}
    for row in rows(args.episode/'motion_safety.jsonl'):
        if row['kind'] == 'decision':
            v = row['payload']
            by_robot[v['robot']].append({'clock': v['clock_ns'],
                'value': tuple(v['decision']['output']), 'decision_sequence': v['decision_sequence'],
                'record_sequence': row['record_sequence']})
    result = {}
    for name, guards in by_robot.items():
        times = [row['clock'] for row in guards]
        lookup = {}
        for row in guards:
            lookup.setdefault(row['value'], []).append(row)
        value_times = {value: [r['clock'] for r in group] for value, group in lookup.items()}
        actual = list(rows(args.episode/f'drive_{name}.jsonl'))
        observations, missing, active = [], [], []
        commands = [row for row in actual if row['kind'] == 'command_received']
        matched_prefix, index, first_failure = {}, 0, None
        for row in commands:
            receive, value = row['sim_time_ns'], (row['desired_v'], row['desired_w'])
            found = None
            while index < len(guards):
                source = guards[index]
                if source['clock'] < receive-160_000_000:
                    index += 1
                    continue
                if source['clock'] > receive:
                    break
                index += 1
                if source['value'] == value:
                    found = source
                    break
            if found is None:
                first_failure = {'original_command': row, 'next_guard_index': index}
                break
            matched_prefix[row['cmd_seq']] = dict(found, receive=receive)
        fixed_prefix = []
        for row in actual:
            if row['kind'] != 'actuation':
                continue
            stamp, value = row['sim_time_ns'], (row['desired_v'], row['desired_w'])
            position = bisect_right(value_times.get(value, []), stamp)-1
            latest_index = bisect_right(times, stamp)-1
            latest = guards[latest_index] if latest_index >= 0 else None
            scope = 'task' if release <= stamp <= task_end else ('cleanup' if stamp > task_end else 'warmup')
            if position < 0:
                observation = {'actuation': row, 'scope': scope, 'compatible_age_ns': None,
                               'latest_final_guard': latest}
                missing.append(observation)
            else:
                source = lookup[value][position]
                observation = {'actuation': row, 'scope': scope,
                    'most_recent_same_value_guard': source, 'latest_final_guard': latest,
                    'compatible_age_ns': stamp-source['clock'],
                    'latest_guard_has_different_value': latest['value'] != value if latest else None}
                observations.append(observation)
                if scope == 'task':
                    active.append(observation)
            match = matched_prefix.get(row['cmd_seq'])
            if match:
                fixed_prefix.append({'actuation_ns': stamp, 'cmd_seq': row['cmd_seq'], 'scope': scope,
                    'source_clock_ns': match['clock'], 'receive_ns': match['receive'],
                    'guard_to_receive_ns': match['receive']-match['clock'],
                    'receive_to_actuation_ns': stamp-match['receive'],
                    'total_compatible_age_ns': stamp-match['clock']})
        violations = [row for row in active if row['compatible_age_ns'] > 160_000_000]
        missing_task = [row for row in missing if row['scope'] == 'task']
        result[name] = {'fixed_consumer_matcher_prefix_commands': len(matched_prefix),
            'fixed_consumer_matcher_first_failure': first_failure,
            'fixed_match_prefix_max_total': max(fixed_prefix, key=lambda r:r['total_compatible_age_ns']) if fixed_prefix else None,
            'fixed_match_prefix_task_actuation_count': sum(r['scope']=='task' for r in fixed_prefix),
            'task_actuation_count': len(active)+len(missing_task),
            'task_latest_equal_value_max_compatible_age_ns': max((r['compatible_age_ns'] for r in active), default=None),
            'task_latest_equal_value_max_original': max(active, key=lambda r:r['compatible_age_ns']) if active else None,
            'task_nonzero_target_max_compatible_age_ns': max((r['compatible_age_ns'] for r in active if any((r['actuation']['desired_v'],r['actuation']['desired_w']))), default=None),
            'task_no_equal_value_prior_source': missing_task,
            'task_equal_value_age_over160ms': violations,
            'all_missing_equal_value_count': len(missing),
            'scope': 'Latest prior equal value is a value-state compatibility lower bound on packet age, not an identified packet. Fixed original greedy matcher prefix is preserved separately and stops at its first failure.'}
    output = {'schema':'mr3-v6-drive-value-state-latency-v1', 'episode':str(args.episode),
              'release_ns':release,'task_end_ns':task_end,'robots':result,
              'inputs':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in
                  [args.episode/'motion_safety.jsonl',args.episode/'transitions.jsonl',
                   *(args.episode/f'drive_{n}.jsonl' for n in by_robot)]},
              'frozen_consumer_whole_result':'FAIL retained; no native gate changed',
              'scope':'Read-only posthoc latency diagnostics; no per-packet identity or physical stop proof.'}
    with args.output.open('x') as stream:
        json.dump(output,stream,indent=2);stream.write('\n')
    print(json.dumps({n:{k:v for k,v in s.items() if k in ('task_actuation_count',
        'task_latest_equal_value_max_compatible_age_ns','task_nonzero_target_max_compatible_age_ns',
        'fixed_consumer_matcher_prefix_commands','fixed_match_prefix_task_actuation_count')}
        | {'over160ms':len(s['task_equal_value_age_over160ms']),
           'missing_prior_value':len(s['task_no_equal_value_prior_source'])}
        for n,s in result.items()}))


if __name__ == '__main__':
    main()
