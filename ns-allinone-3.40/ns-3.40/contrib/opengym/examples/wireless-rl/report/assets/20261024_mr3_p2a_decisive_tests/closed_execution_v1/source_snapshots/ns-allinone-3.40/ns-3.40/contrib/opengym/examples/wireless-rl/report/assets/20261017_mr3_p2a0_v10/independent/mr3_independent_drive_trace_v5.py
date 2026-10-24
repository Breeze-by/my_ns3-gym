"""Pinned v4 drive physics/provenance plus permanent explicit zero-stop evidence."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

LEGACY = Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/'
              'examples/wireless-rl/report/assets/20261017_mr3_p2a0_v7/independent/'
              'mr3_independent_drive_trace_v4.py')
LEGACY_SHA = '6aa1a8409e031f225f0acb3a61ab2c9ec16a156cc85a430fd7069bdea411f35d'
if hashlib.sha256(LEGACY.read_bytes()).hexdigest() != LEGACY_SHA:
    raise ValueError('immutable drive-v4 SHA mismatch')
SPEC = importlib.util.spec_from_file_location('immutable_drive_v4', LEGACY)
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
require, integer, number, pair = BASE.require, BASE.integer, BASE.number, BASE.pair
ROBOTS = BASE.ROBOTS
OLD_EPISODE, OLD_PHASE, OLD_REVIEW = BASE.audit_episode, BASE.drive_phase, BASE.review


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def stop_status(status, guards, epoch):
    require(type(status) is dict and status.get('schema') == 'mr3-motion-safety-status-v1'
            and status.get('epoch') == epoch and status.get('phase_kind') == 'stop'
            and status.get('ready') is False and integer(status.get('clock_ns'))
            and status.get('completion_scope') == 'publication_and_local_topic_receipt',
            'invalid permanent-stop status')
    require(set(status['outputs']) == set(ROBOTS)
            and set(status['decision_sequences']) == set(ROBOTS), 'stop status three roles')
    selected = {}
    for name in ROBOTS:
        sequence = status['decision_sequences'][name]
        require(integer(sequence) and sequence > 0, 'stop decision sequence type')
        row = next((item for item in guards[name] if item['decision_sequence'] == sequence), None)
        require(row is not None and row.get('phase_kind') == 'stop'
                and row['clock_ns'] == status['clock_ns'] and row['output'] == [0., 0.],
                'stop status does not bind three actual stop decisions')
        output = status['outputs'][name]
        require(type(output) is dict and set(output) == {'linear_x', 'angular_z'}
                and number(output['linear_x']) and number(output['angular_z'])
                and output['linear_x'] == output['angular_z'] == 0., 'nonzero stop status')
        selected[name] = row
    return selected


def guard_outputs(records, epoch, release):
    outputs = {name: [] for name in ROBOTS}
    decisions, self_receipts, completed = {}, {}, set()
    cause, stopped = None, False
    for line, row in enumerate(records, 1):
        require(row['schema'] == 'mr3-motion-safety-v1' and row['epoch'] == epoch
                and integer(row['record_sequence']) and row['record_sequence'] == line,
                'guard log schema/epoch/record sequence')
        kind, value = row['kind'], row['payload']
        if kind in ('terminal', 'stop_request', 'failure', 'invalid_terminal_notice',
                    'settled_turn_model_failure', 'control_failure'):
            cause = line
        if kind == 'control_request' and value.get('operation') == 'stop':
            require(value.get('schema') == 'mr3-motion-control-request-v1'
                    and value.get('epoch') == epoch and isinstance(value.get('request_id'), str)
                    and value['request_id'] and integer(value.get('target_time_ns')),
                    'malformed explicit stop request')
            cause = line
        if kind == 'actual_cmd_vel':
            name, sequence = value['robot'], value.get('observed_decision_sequence')
            if sequence is None:
                cause = line
                continue
            source = decisions.get((name, sequence))
            if source is not None and source.get('phase_kind') == 'stop':
                require(integer(sequence) and source['line'] < line, 'stop self receipt identity/order')
                twist, identity = value['twist'], value['publisher_identity']
                require(set(twist) == {'linear', 'angular'} and all(
                    type(twist[axis]) is dict and set(twist[axis]) == {'x', 'y', 'z'}
                    and all(number(twist[axis][key]) and twist[axis][key] == 0.
                            for key in ('x', 'y', 'z')) for axis in ('linear', 'angular')),
                    'stop actual output is not whole zero Twist')
                require(identity.get('valid') is True and identity.get('scope') == 'graph_at_callback'
                        and identity.get('topic') == f'/{name}/cmd_vel'
                        and len(identity.get('endpoints', [])) == 1
                        and identity['endpoints'][0].get('namespace') == '/'
                        and identity['endpoints'][0].get('node') == 'motion_safety'
                        and identity['endpoints'][0].get('topic_type') == 'geometry_msgs/msg/Twist',
                        'stop local output callback graph identity')
                key = name, sequence
                require(key not in self_receipts, 'duplicate stop self receipt')
                self_receipts[key] = line
            continue
        if kind == 'output_completed' and value['status'].get('phase_kind') == 'stop':
            status = value['status']
            selected = stop_status(status, outputs, epoch)
            require(all((name, item['decision_sequence']) in self_receipts
                        for name, item in selected.items()), 'stop status precedes actual self receipts')
            start, end = (value['publish_started_wall_monotonic_ns'],
                          value['publish_completed_wall_monotonic_ns'])
            require(integer(start) and integer(end) and start <= end <= row['wall_monotonic_ns'],
                    'stop completed-status publication window')
            completed.update((name, item['decision_sequence']) for name, item in selected.items())
            continue
        if kind != 'decision':
            continue
        name = value['robot']
        require(name in ROBOTS and integer(value['clock_ns']) and value['clock_ns'] >= 0,
                'invalid guard source identity/clock')
        require(integer(value['decision_sequence'])
                and value['decision_sequence'] == len(outputs[name]) + 1,
                'guard publication decision sequence')
        output = pair(value['decision']['output'], 'invalid final guard output')
        require(abs(output[0]) <= .26 and abs(output[1]) <= .8, 'guard output outside command limits')
        is_stop = value.get('phase_kind') == 'stop'
        require('phase_kind' not in value or is_stop, 'unknown guard phase kind')
        if is_stop:
            require(cause is not None and cause < line and value.get('ready') is False
                    and output == [0., 0.], 'stop lacks prior cause or permanent zero/readyFalse')
            stopped = True
        else:
            require(not stopped, 'normal decision after permanent stop latch')
        if outputs[name]:
            prior = outputs[name][-1]
            require(value['clock_ns'] >= prior['clock_ns'], 'guard source clock rewind')
            if value['clock_ns'] == prior['clock_ns']:
                if is_stop:
                    require(prior.get('phase_kind') != 'stop', 'duplicate stop at same clock')
                else:
                    require(value['clock_ns'] < release and output == prior['output'] == [0., 0.],
                            'same-clock guard output is not a prerelease duplicate zero')
        result = {'clock_ns': value['clock_ns'], 'output': output,
                  'started': value.get('started'), 'decision_sequence': value['decision_sequence'],
                  'line': line, **({'phase_kind': 'stop'} if is_stop else {})}
        outputs[name].append(result)
        decisions[name, value['decision_sequence']] = result
    stop_keys = {key for key, row in decisions.items() if row.get('phase_kind') == 'stop'}
    require(stop_keys <= completed, 'stop decisions lack complete actual self receipt/status evidence')
    return outputs


def drive_phase(records, physics, epoch, release, guards, statuses, initial_motion, initial_receipts):
    by_sequence = {name: {row['decision_sequence']: row for row in guards[name]} for name in ROBOTS}
    for row in records:
        if row['kind'] not in ('ack_consumed', 'advance_permitted'):
            continue
        status = row['expected_motion']
        kinds = {by_sequence[name][status['decision_sequences'][name]].get('phase_kind')
                 for name in ROBOTS}
        if status.get('phase_kind') == 'stop':
            stop_status(status, guards, epoch)
            require(kinds == {'stop'}, 'driver barrier mixes normal/stop guard targets')
        else:
            require('phase_kind' not in status and kinds == {None},
                    'normal driver barrier was overwritten by stop targets')
    return OLD_PHASE(records, physics, epoch, release, guards, statuses,
                     initial_motion, initial_receipts)


def stop_worker_bindings(motion_phase, control_phase, guards, epoch):
    normal = {}
    for row in motion_phase:
        require(row['epoch'] == epoch, 'worker normal status epoch')
        if row['kind'] not in ('ack_received', 'ack_consumed'):
            raise ValueError('unknown worker normal motion phase record')
        status = row['ack']
        require('phase_kind' not in status, 'stop overwrote normal status channel')
        require(status.get('schema') == 'mr3-motion-safety-status-v1'
                and status.get('epoch') == epoch and integer(status.get('clock_ns'))
                and type(status.get('ready')) is bool
                and status.get('completion_scope') == 'publication_and_local_topic_receipt'
                and set(status['decision_sequences']) == set(ROBOTS)
                and set(status['outputs']) == set(ROBOTS), 'normal status identity/roles')
        for name in ROBOTS:
            source = next((item for item in guards[name] if item['decision_sequence']
                           == status['decision_sequences'][name]), None)
            require(source is not None and 'phase_kind' not in source
                    and source['clock_ns'] == status['clock_ns'], 'normal status binds stop/unknown target')
            output = status['outputs'][name]
            require(set(output) == {'linear_x', 'angular_z'}
                    and number(output['linear_x']) and number(output['angular_z'])
                    and [output['linear_x'], output['angular_z']] == source['output'],
                    'normal status changed actual guard output')
        prior = normal.get(status['clock_ns'])
        require(prior is None or canonical(prior) == canonical(status), 'normal status changed within clock')
        normal[status['clock_ns']] = status
    actual_control, observed = [], []
    for row in control_phase:
        require(row['epoch'] == epoch, 'worker stop status epoch')
        if row['kind'] == 'ack_received' and row.get('component') == 'motion':
            ack = row['ack']
            status = ack.get('status')
            if status is not None and status.get('phase_kind') == 'stop':
                require(ack.get('schema') == 'mr3-motion-control-ack-v1'
                        and ack.get('epoch') == epoch and ack.get('ok') is True
                        and ack.get('operation') in ('commit', 'stop')
                        and isinstance(ack.get('request_id'), str) and ack['request_id']
                        and integer(ack.get('clock_ns')) and integer(ack.get('target_time_ns'))
                        and ack['clock_ns'] == ack['target_time_ns'] == status['clock_ns'],
                        'stop control ACK identity/clock')
                stop_status(status, guards, epoch)
                actual_control.append(status)
        elif row['kind'] == 'stop_observed':
            status = row['status']
            stop_status(status, guards, epoch)
            origin = row.get('origin')
            require(origin in ('stop_topic', 'control_ack'), 'stop observation missing actual channel origin')
            if origin == 'control_ack':
                require(any(canonical(value) == canonical(status) for value in actual_control),
                        'control-derived stop observation has no actual control ACK callback')
            observed.append(status)
    require(observed, 'no actual worker stop notification/callback')
    return {'passed': True, 'normal_status_clocks': len(normal),
            'stop_notifications': len(observed),
            'scope': 'Actual callback channels remain distinct; storage and physics remain checked by pinned v4'}


def audit_episode(directory, freeze, compiled, binary, inputs, old_model, archived=False):
    result = OLD_EPISODE(directory, freeze, compiled, binary, inputs, old_model, archived)
    guards = guard_outputs(list(inputs.lines(directory/'motion_safety.jsonl')),
                           result['epoch'], result['release_ns'])
    if any(item.get('phase_kind') == 'stop' for rows in guards.values() for item in rows):
        result['permanent_stop_channel'] = stop_worker_bindings(
            list(inputs.lines(directory/'motion_phase_worker.jsonl')),
            list(inputs.lines(directory/'control_phase_worker.jsonl')), guards, result['epoch'])
    return result


BASE.guard_outputs, BASE.drive_phase, BASE.audit_episode = guard_outputs, drive_phase, audit_episode


def review(directory, freeze, proof_path, archived=False):
    result = OLD_REVIEW(directory, freeze, proof_path, archived)
    result['schema'] = 'mr3-independent-drive-trace-review-v5'
    result['immutable_physics_provenance_base'] = {'path': str(LEGACY), 'sha256': LEGACY_SHA}
    require(hashlib.sha256(LEGACY.read_bytes()).hexdigest() == LEGACY_SHA,
            'immutable drive-v4 changed during review')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--binary-proof', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--archived', action='store_true')
    args = parser.parse_args()
    require(not args.output.exists(), 'previous result cannot be overwritten')
    try:
        result = review(args.directory, args.freeze, args.binary_proof, args.archived)
    except Exception as error:
        result = {'schema': 'mr3-independent-drive-trace-review-v5', 'freeze': args.freeze,
                  'passed': False, 'error': repr(error), 'world_body_response_credit': False}
    result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
