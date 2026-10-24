#!/usr/bin/env python3
"""Independent explicit information-phase audit, extending the pinned v1 raw replay."""

import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

LEGACY = Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/'
              'examples/wireless-rl/report/assets/20261017_mr3_p2a0_v9/independent/'
              'mr3_independent_information_v1.py')
LEGACY_SHA = 'ba3e89fa6feda9406f984310adccf17c2f0638644fd0d26f0c2e9040ec0e7653'
if hashlib.sha256(LEGACY.read_bytes()).hexdigest() != LEGACY_SHA:
    raise ValueError('immutable information-v1 source SHA mismatch')
SPEC = importlib.util.spec_from_file_location('immutable_information_v1', LEGACY)
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
require, integer, canonical = BASE.require, BASE.integer, BASE.canonical
digest, ROBOTS, SCHEMA = BASE.digest, BASE.ROBOTS, BASE.SCHEMA
RawReplay = BASE.LedgerReplay


class LedgerReplay(RawReplay):
    def __init__(self, epoch):
        super().__init__(epoch)
        self.controlled = False
        self.phase_pending = None
        self.phase_requests = {}
        self.phase_request_walls = {}
        self.phase_acks = {}
        self.phase_candidate = None
        self.phase_duplicate_ack = None
        self.last_committed_clock = None
        self.phase_commits = []
        self.terminal_notice = None
        self.drain_requests = {}
        self.drain_acks = {}

    def record(self, row):
        kind = row['kind']
        if kind not in ('state_phase_request', 'state_phase_ack', 'state_terminal_received',
                        'state_drain_request', 'state_drain_ack'):
            if kind == 'state_publish' and self.controlled:
                pending = self.phase_pending
                require(pending is not None and pending['operation'] == 'commit',
                        'unrequested controlled publication')
                require(row['clock_ns'] == pending['target_time_ns'],
                        'controlled publication at different phase clock')
                require(self.phase_candidate is None, 'multiple publications for one phase')
            super().record(row)
            if kind == 'state_publish' and self.controlled:
                value = row['payload']
                start = integer(value['side_publish_started_wall_monotonic_ns'], 'side start', 1)
                require(self.phase_request_walls[self.phase_pending['request_id']] <= start
                        <= value['publish_started_wall_monotonic_ns'],
                        'side publication window after bundle publication')
                require(all(robot['valid'] is True for robot in value['message']['robots']),
                        'committed phase includes invalid state')
                for envelope in value['envelopes'].values():
                    require(envelope is not None and envelope['source_stamp'] > 0,
                            'phase lacks actual delivered source')
                    age = row['clock_ns'] - round(envelope['source_stamp'] * 1e9)
                    require(0 <= age <= 500_000_000, 'phase source age outside original500ms')
                self.phase_candidate = copy.deepcopy(row)
            return
        require(row['schema'] == SCHEMA and row['epoch'] == self.epoch,
                'phase ledger schema/epoch')
        require(type(row['record_sequence']) is int
                and row['record_sequence'] == self.sequence + 1, 'phase ledger sequence gap')
        self.sequence += 1
        clock = integer(row['clock_ns'], 'phase row clock')
        wall = integer(row['wall_monotonic_ns'], 'phase row wall', 1)
        require(wall >= self.last_wall, 'phase ledger wall regressed')
        self.last_wall = wall
        self.counts[kind] += 1
        require(self.config is not None, 'phase before configuration')
        if kind == 'state_phase_request':
            self.request(row['payload'], clock, wall)
        elif kind == 'state_phase_ack':
            self.ack(row['payload'], clock, wall)
        elif kind == 'state_terminal_received':
            self.terminal(row['payload'])
        elif kind == 'state_drain_request':
            self.drain_request(row['payload'])
        else:
            self.drain_ack(row['payload'], clock, wall)

    def terminal(self, payload):
        notice = payload['notice']
        require(set(notice) == {'epoch', 'end_sim_time_sec', 'termination_reason'}
                and notice['epoch'] == self.epoch, 'terminal notice identity')
        require(type(payload['duplicate']) is bool
                and payload['duplicate'] == (self.terminal_notice is not None),
                'terminal duplicate flag')
        BASE.seconds_ns(notice['end_sim_time_sec'])
        require(notice['termination_reason'] in {
            'timeout', 'navigation_failure', 'collision', 'collision_monitoring_interrupted',
            'map_contract_error', 'pose_discontinuity', 'task_gate_regressed_during_closure',
            'navigation_closure_timeout', 'navigation_closure_invalid', 'coverage_reached'},
            'terminal notice reason')
        require(self.terminal_notice is None
                or canonical(self.terminal_notice) == canonical(notice), 'terminal notice changed')
        self.terminal_notice = copy.deepcopy(notice)

    def drain_request(self, payload):
        request = copy.deepcopy(payload['request'])
        require(request['epoch'] == self.epoch and isinstance(request['request_id'], str)
                and request['request_id'], 'drain request identity')
        integer(request['target_time_ns'], 'drain target')
        request.setdefault('allow_terminal', False)
        require(type(request['allow_terminal']) is bool, 'drain allow_terminal type')
        previous = self.drain_requests.get(request['request_id'])
        require(previous is None or canonical(previous) == canonical(request), 'drain request changed')
        self.drain_requests[request['request_id']] = request

    def drain_ack(self, payload, clock, wall):
        ack = payload['ack']
        require(ack['ok'] is True and ack['epoch'] == self.epoch, 'drain failed/epoch')
        request = self.drain_requests.get(ack['request_id'])
        require(request is not None and type(ack['target_time_ns']) is int
                and ack['target_time_ns'] == request['target_time_ns'], 'unbound drain ACK')
        require(type(payload['cached']) is bool, 'drain cached flag')
        start = integer(payload['publish_started_wall_monotonic_ns'], 'drain publish start', 1)
        end = integer(payload['publish_completed_wall_monotonic_ns'], 'drain publish completed', 1)
        require(start <= end <= wall, 'drain publish window')
        if payload['cached']:
            require(canonical(self.drain_acks.get(ack['request_id'])) == canonical(ack),
                    'cached drain ACK changed')
            return
        require(clock == request['target_time_ns'], 'drain ACK clock mismatch')
        if self.controlled:
            require(self.phase_commits, 'controlled drain lacks real commit')
            commit = self.phase_commits[-1]
            require(type(ack['state_sequence']) is int
                    and ack['state_sequence'] == commit['state_sequence']
                    and ack['state_bundle_sha256'] == commit['bundle_sha256']
                    and type(ack['state_commit_clock_ns']) is int
                    and ack['state_commit_clock_ns'] == commit['clock_ns'],
                    'drain changed latest actual committed state')
            if commit['clock_ns'] == request['target_time_ns']:
                require(ack['state_reuse_scope'] == 'exact_commit', 'normal drain scope')
            else:
                require(request['allow_terminal'] is True and self.terminal_notice is not None,
                        'stale drain has no actual terminal callback')
                require(commit['clock_ns'] < request['target_time_ns']
                        and BASE.seconds_ns(self.terminal_notice['end_sim_time_sec'])
                        <= request['target_time_ns'], 'terminal reuse clock interval')
                require(ack['state_reuse_scope'] == 'terminal_last_committed'
                        and canonical(ack['terminal_notice']) == canonical(self.terminal_notice),
                        'terminal drain notice changed')
                self.counts['terminal_only_state_reuse'] += 1
        self.drain_acks[ack['request_id']] = copy.deepcopy(ack)

    def request(self, payload, clock, wall):
        value = payload['request']
        require(set(value) == {'schema', 'epoch', 'request_id', 'operation', 'target_time_ns'},
                'phase request exact fields')
        require(value['schema'] == 'mr3-state-phase-request-v1' and value['epoch'] == self.epoch,
                'phase request schema/epoch')
        require(isinstance(value['request_id'], str) and value['request_id'], 'phase request id')
        require(value['operation'] in ('takeover', 'commit'), 'phase operation')
        target = integer(value['target_time_ns'], 'phase target')
        require(type(payload['duplicate']) is bool, 'phase duplicate flag type')
        identifier = value['request_id']
        previous = self.phase_requests.get(identifier)
        if previous is not None:
            require(payload['duplicate'] is True and canonical(previous) == canonical(value),
                    'conflicting/undeclared duplicate phase request')
            if identifier in self.phase_acks:
                self.phase_duplicate_ack = identifier
            else:
                require(self.phase_pending == value, 'duplicate phase is not pending')
            return
        require(clock <= target, 'phase request after target clock')
        require(payload['duplicate'] is False and self.phase_pending is None,
                'new phase overlaps pending phase')
        if value['operation'] == 'commit':
            require(self.last_committed_clock is None or target > self.last_committed_clock,
                    'new phase request rewrites committed clock')
        self.controlled = True
        self.phase_requests[identifier] = copy.deepcopy(value)
        self.phase_request_walls[identifier] = wall
        self.phase_pending = copy.deepcopy(value)
        self.phase_candidate = None

    def ack(self, payload, clock, row_wall):
        ack = payload['ack']
        require(ack['schema'] == 'mr3-state-phase-ack-v1' and ack['epoch'] == self.epoch,
                'phase ACK schema/epoch')
        require(type(ack['ok']) is bool, 'phase ACK ok type')
        identifier = ack['request_id']
        request = self.phase_requests.get(identifier)
        require(request is not None, 'phase ACK has no actual request')
        require(type(payload['cached']) is bool, 'phase ACK cached type')
        require(ack['operation'] == request['operation']
                and type(ack['target_time_ns']) is int
                and ack['target_time_ns'] == request['target_time_ns'], 'phase ACK request mismatch')
        require(type(ack['clock_ns']) is int, 'phase ACK clock type')
        started = integer(payload['publish_started_wall_monotonic_ns'], 'ACK start', 1)
        completed = integer(payload['publish_completed_wall_monotonic_ns'], 'ACK completed', 1)
        require(started <= completed <= row_wall, 'ACK publish window')
        require(self.phase_request_walls[identifier] <= started,
                'ACK publish predates actual request callback')
        if payload['cached']:
            require(self.phase_duplicate_ack == identifier
                    and canonical(self.phase_acks.get(identifier)) == canonical(ack),
                    'cached phase ACK not exact previous ACK')
            self.phase_duplicate_ack = None
            return
        require(self.phase_pending == request and identifier not in self.phase_acks,
                'new phase ACK not actual pending request')
        require(clock == ack['clock_ns'], 'new phase ACK row clock mismatch')
        if ack['ok'] is False:
            require(ack.get('error') == 'state_phase_task_terminal'
                    and ack.get('scope') == 'terminal_cancelled_uncommitted_state_phase',
                    'producer phase failed')
            require(request['operation'] == 'commit' and self.phase_candidate is None
                    and self.terminal_notice is not None,
                    'terminal cancellation has no actual terminal/uncommitted request')
            require(canonical(ack['terminal_notice']) == canonical(self.terminal_notice)
                    and BASE.seconds_ns(self.terminal_notice['end_sim_time_sec'])
                    <= request['target_time_ns'] and clock <= request['target_time_ns'],
                    'terminal cancellation notice/clock mismatch')
            self.phase_acks[identifier] = copy.deepcopy(ack)
            self.phase_pending = None
            self.counts['terminal_cancelled_state_commits'] += 1
            return
        require(ack['clock_ns'] == ack['target_time_ns'],
                'phase ACK not at exact target clock')
        if ack['operation'] == 'takeover':
            require(self.phase_candidate is None and ack['state_sequence'] is None
                    and ack['bundle_sha256'] is None and ack['robots'] == {},
                    'takeover falsely claims state publication')
            require(ack['scope'] == 'periodic_state_publication_disabled', 'takeover scope')
            self.counts['takeover_acks'] += 1
        else:
            self.commit(ack, started)
            self.last_committed_clock = ack['clock_ns']
            self.phase_commits.append(copy.deepcopy(ack))
            self.counts['state_commit_acks'] += 1
        self.phase_acks[identifier] = copy.deepcopy(ack)
        self.phase_pending = None
        self.phase_candidate = None

    def commit(self, ack, ack_started):
        row = self.phase_candidate
        require(row is not None, 'commit ACK without actual state publication')
        value = row['payload']
        require(ack['scope'] == 'actual_state_and_side_publish_calls_returned', 'commit scope')
        require(type(ack['state_sequence']) is int
                and ack['state_sequence'] == value['message']['sequence']
                and ack['bundle_sha256'] == value['message_sha256'], 'phase bundle binding')
        windows = {'side_publish_started_wall_monotonic_ns': 'side_publish_started_wall_monotonic_ns',
                   'bundle_publish_started_wall_monotonic_ns': 'publish_started_wall_monotonic_ns',
                   'bundle_publish_completed_wall_monotonic_ns': 'publish_completed_wall_monotonic_ns'}
        for key, source in windows.items():
            require(type(ack[key]) is int and ack[key] == value[source], 'phase publication window binding')
        require(ack['bundle_publish_completed_wall_monotonic_ns'] <= ack_started,
                'ACK before state bundle publish returned')
        require(set(ack['robots']) == set(ROBOTS), 'phase ACK missing robot')
        sides = {item['robot']: item for item in value['side_publications']}
        for name in ROBOTS:
            envelope, binding = value['envelopes'][name], ack['robots'][name]
            expected = {'sequence': envelope['sequence'], 'version': envelope['version'],
                        'source_stamp': envelope['source_stamp'],
                        'source_ns': round(envelope['source_stamp'] * 1e9),
                        'odom_source_ns': round(envelope['payload']['odom_source_stamp'] * 1e9),
                        'tf_source_ns': round(envelope['payload']['tf_source_stamp'] * 1e9),
                        **{key: sides[name][key] for key in
                           ('odom_topic', 'tf_topic', 'odom_sha256', 'tf_sha256')}}
            require(canonical(binding) == canonical(expected), 'phase side/envelope raw binding')

    def finish(self):
        result = super().finish()
        require(self.phase_pending is None and self.phase_duplicate_ack is None,
                'unfinished explicit information phase')
        require(self.counts['takeover_acks'] > 0 and self.counts['state_commit_acks'] > 0,
                'missing explicit takeover/commit availability')
        return result


BASE.LedgerReplay = LedgerReplay


def audit(directory, freeze):
    result = BASE.audit(directory, freeze)
    result['schema'] = 'mr3-independent-information-review-v2'
    result['consumer_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result['immutable_raw_replay'] = {'path': str(LEGACY), 'sha256': LEGACY_SHA}
    result['criteria'].update({'explicit_state_phase_request_to_real_publication': True,
                               'controlled_periodic_publication_forbidden': True,
                               'duplicate_request_preserves_committed_bundle': True})
    if hashlib.sha256(LEGACY.read_bytes()).hexdigest() != LEGACY_SHA:
        result['passed'] = False
        result['errors'].append('immutable raw replay changed during audit')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    require(not args.output.exists(), 'output must be a new file')
    result = audit(args.directory, args.freeze)
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
