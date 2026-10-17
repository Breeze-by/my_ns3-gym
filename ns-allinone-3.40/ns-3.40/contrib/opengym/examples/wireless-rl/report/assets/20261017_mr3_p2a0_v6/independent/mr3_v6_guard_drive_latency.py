"""Value-compatible FIFO latency bounds; no packet identity is inferred."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time


def rows(path):
    with path.open() as stream:
        return [json.loads(line) for line in stream if line.endswith('\n') and line.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('episode', type=Path)
    p.add_argument('--consumer', type=Path, required=True)
    p.add_argument('--binary-proof', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location('frozen_driver_consumer', args.consumer)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    traces = {name: rows(args.episode/f'drive_{name}.jsonl') for name in module.ROBOTS}
    transitions = rows(args.episode/'transitions.jsonl')
    release = transitions[0]['info']['release_time_ns']
    guard_rows = rows(args.episode/'motion_safety.jsonl')
    guard_index_note = None
    try:
        guards = module.guard_outputs(guard_rows, traces['tb1'][0]['epoch'])
    except ValueError as error:
        assert str(error) == 'guard source clock rewind'
        guards = {name: [] for name in module.ROBOTS}
        duplicates = []
        for index, row in enumerate(guard_rows, 1):
            assert row['record_sequence'] == index
            assert row['schema'] == 'mr3-motion-safety-v1' and row['epoch'] == traces['tb1'][0]['epoch']
            if row['kind'] != 'decision':
                continue
            value = row['payload']; name = value['robot']; clock = value['clock_ns']
            assert value['decision_sequence'] == len(guards[name])+1
            output = value['decision']['output']
            if guards[name]:
                assert clock >= guards[name][-1]['clock_ns']
                if clock == guards[name][-1]['clock_ns']:
                    assert clock < release and output == guards[name][-1]['output'] == [0., 0.]
                    duplicates.append({'robot': name, 'clock_ns': clock, 'line': index})
            guards[name].append({'clock_ns': clock, 'output': output,
                'decision_sequence': value['decision_sequence'], 'line': index})
        guard_index_note = {'original_frozen_guard_outputs_rejected': str(error),
            'diagnostic_only_same_clock_prerelease_zero_pairs': duplicates,
            'native_rows_dropped_or_changed': False,
            'whole_frozen_consumer_result': 'FAIL retained; diagnostic calls unchanged robot_audit only'}
    final = max(row['sim_time_ns'] for values in traces.values() for row in values)
    proof = json.loads(args.binary_proof.read_bytes())
    compiled = {key: proof[key] for key in module.SOURCE_PATHS}
    results = {}
    for name, values in traces.items():
        audit = module.robot_audit(values, guards[name], name, values[0]['epoch'], release,
                                   final, 1_000_000, compiled, proof, False)
        matched = {row['cmd_seq']: row for row in audit['ordered_guard_subsequence']}
        observations = []
        for row in values:
            if row['kind'] != 'actuation' or row['cmd_seq'] == 0:
                continue
            source = matched[row['cmd_seq']]
            observations.append({'actuation_ns': row['sim_time_ns'], 'cmd_seq': row['cmd_seq'],
                'desired': [row['desired_v'], row['desired_w']],
                'guard_source_ns': source['guard_source_ns'], 'receive_ns': source['receive_ns'],
                'guard_to_receive_ns': source['compatible_delay_ns'],
                'receive_to_actuation_ns': row['sim_time_ns']-source['receive_ns'],
                'guard_to_actuation_ns': row['sim_time_ns']-source['guard_source_ns'],
                'task': row['sim_time_ns'] >= release, 'original_actuation': row})
        task = [row for row in observations if row['task']]
        nonzero = [row for row in task if any(row['desired'])]
        commands = [row for row in values if row['kind'] == 'command_received']
        latest_use = {}
        for row in values:
            if row['kind'] == 'actuation' and row['sim_time_ns'] >= release:
                latest_use[row['cmd_seq']] = max(row['sim_time_ns'], latest_use.get(row['cmd_seq'], 0))

        def feasible(total_limit):
            index, assignment = 0, []
            for command in commands:
                receive, sequence = command['sim_time_ns'], command['cmd_seq']
                lower = receive-module.MAX_DELAY_NS
                if sequence in latest_use:
                    lower = max(lower, latest_use[sequence]-total_limit)
                found = None
                while index < len(guards[name]):
                    guard = guards[name][index]
                    if guard['clock_ns'] > receive:
                        break
                    index += 1
                    if guard['clock_ns'] >= lower and guard['output'] == [command['desired_v'], command['desired_w']]:
                        found = guard
                        break
                if found is None:
                    return False, {'cmd_seq': sequence, 'receive_ns': receive,
                                   'last_task_use_ns': latest_use.get(sequence), 'required_lower_ns': lower}
                assignment.append({'cmd_seq': sequence, 'guard_source_ns': found['clock_ns'],
                                   'guard_decision_sequence': found['decision_sequence']})
            return True, assignment

        low, high = 0, 1_000_000_000
        assert feasible(high)[0]
        while low < high:
            middle = (low+high)//2
            if feasible(middle)[0]:
                high = middle
            else:
                low = middle+1
        possible, witness = feasible(160_000_000)
        results[name] = {'unchanged_robot_audit_subroutine_passed_with_diagnostic_guard_index': audit['passed'],
            'actual_receipt_count': len(commands), 'task_actuation_count': len(task),
            'fixed_earliest_compatible_match_max_total_all': max(observations, key=lambda row: row['guard_to_actuation_ns']),
            'fixed_earliest_compatible_match_max_total_task': max(task, key=lambda row: row['guard_to_actuation_ns']) if task else None,
            'fixed_earliest_compatible_match_max_total_nonzero_task': max(nonzero, key=lambda row: row['guard_to_actuation_ns']) if nonzero else None,
            'task_fixed_match_over160ms_count': sum(row['guard_to_actuation_ns'] > 160_000_000 for row in task),
            'minimum_feasible_max_task_total_age_ns_over_all_ordered_value_compatible_assignments': low,
            'exists_ordered_value_matching_with_total_task_age_le160ms': possible,
            'witness_or_first_impossible_command': witness,
            'scope': 'Fixed consumer uses earliest compatible FIFO value matches. Repeated equal commands do not reveal packet identity; the feasible-assignment bound is a necessary observable compatibility check, not proof of the real packet source timestamp.'}
    result = {'schema': 'mr3-v6-guard-drive-compatible-latency-v1',
        'capture_wall_monotonic_ns': time.monotonic_ns(), 'episode': str(args.episode),
        'epoch': traces['tb1'][0]['epoch'], 'release_ns': release, 'prefix_final_ns': final,
        'frozen_consumer_path': str(args.consumer), 'frozen_consumer_sha256': hashlib.sha256(args.consumer.read_bytes()).hexdigest(),
        'robots': results, 'diagnostic_guard_index_note': guard_index_note, 'scope': 'Offline value/sequence-compatible latency inference on captured complete-line prefix only. No per-packet MessageInfo identity or physical braking/body proof. No frozen gate or source changed.'}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({name: {key: value for key, value in stats.items() if key in (
        'minimum_feasible_max_task_total_age_ns_over_all_ordered_value_compatible_assignments',
        'exists_ordered_value_matching_with_total_task_age_le160ms', 'task_fixed_match_over160ms_count')}
        for name, stats in results.items()}))


if __name__ == '__main__':
    main()
