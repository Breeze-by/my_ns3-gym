#!/usr/bin/python3
"""Finite descriptive extraction of one CLOSED V41 interface episode.

No ROS/learner import, map/blob decoding, physics verdict, replay or simulation.
The external owner must first establish closure, freeze/custody and an actual-wait
budget. This reader cannot establish closure merely from the selected log files.
Only episode001_open_101 under worker0 is supported, with reset + 32 real steps.

Logger facts: adapter has stamp/epoch/kind/payload but NO wall time or record
sequence. Drive/independent-odometry have sim_time_ns + record_sequence but NO
wall time. MotionSafety has sim_time_sec + wall_monotonic_ns + record_sequence.
Those missing clocks stay absent; cross-file same-tick causality is unresolved.
"""
import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import stat
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
P = ROS / 'src/multi_robot_exploration/multi_robot_exploration'
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
EVIDENCE_FREEZE = '47224c51c1c525c55093dce26b374d1ccb07eb06'
ROBOTS = ('tb1', 'tb2', 'tb3')
SOURCE_PATHS = (
    P / 'mr3_adapter.py', P / 'motion_safety.py', P / 'mr3_reach_runtime.py',
    P / 'mr3_reach_geometry.py', P / 'mr3_protocol.py',
    ROS / 'scripts/mr3_env_worker.py',
    ROS / 'src/multi_robot/src/mr3_gazebo_diff_drive.cpp',
    ROS / 'src/multi_robot/params/nav2_params_tb3_0.yaml',
    W / 'mr3_learning/benchmark.py',
    W / 'report/assets/20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py',
)
MIB = 1024 * 1024
MAX_READ_WALL_NS = 580 * 1_000_000_000
MAX_LINE_BYTES = 16 * MIB
MAX_TOTAL_INPUT_BYTES = 1024 * MIB
MAX_OUTPUT_BYTES = 4 * MIB
MAX_SELECTED_BYTES = 3 * MIB
MAX_SELECTED_ROWS = 2200
BEFORE_NS, AFTER_NS = 120_000_000, 900_000_000
# Fixed caps, not user-extensible. Hitting one is an incomplete extraction.
INPUT_LIMITS = {
    'transitions.jsonl': (33, 128 * MIB),
    'adapter.jsonl': (100_000, 256 * MIB),
    'motion_safety.jsonl': (250_000, 512 * MIB),
    **{f'drive_{r}.jsonl': (250_000, 128 * MIB) for r in ROBOTS},
    **{f'odometry_{r}.jsonl': (100_000, 64 * MIB) for r in ROBOTS},
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def sec_ns(value):
    require(type(value) in (int, float) and math.isfinite(value), 'nonfinite/invalid seconds')
    return round(value * 1_000_000_000)


def stat_record(value):
    return {k: getattr(value, 'st_' + k) for k in ('dev', 'ino', 'size', 'mtime_ns', 'ctime_ns')}


def identity():
    tail = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
    return {'pid': os.getpid(), 'parent': os.getppid(), 'group': os.getpgrp(),
            'session': os.getsid(0), 'start_ticks': int(tail[19])}


def source_records():
    records = []
    for path in (*SOURCE_PATHS, Path(__file__).resolve()):
        before = stat_record(path.stat())
        data = path.read_bytes()
        after = stat_record(path.stat())
        require(before == after and len(data) == before['size'], 'source changed during read')
        records.append({'path': str(path), 'sha256': digest(data), 'bytes': len(data),
                        'stat_before': before, 'stat_after': after})
    return records


def take(mapping, keys):
    return {key: mapping[key] for key in keys if isinstance(mapping, dict) and key in mapping}


class Extractor:
    def __init__(self, directory, result):
        self.directory, self.result = directory, result
        self.deadline_ns = result["started_monotonic_ns"] + MAX_READ_WALL_NS
        self.epoch = None
        self.task_start_ns = self.task_end_ns = None
        self.bytes_read = self.selected_bytes = self.selected_rows = 0
        self.channel_counts, self.dropped = Counter(), Counter()
        self.cancel_clocks = {robot: [] for robot in ROBOTS}
        self.target_sequences = {robot: set() for robot in ROBOTS}
        self.stats = {robot: {'reach_decisions': 0, 'reason_counts': Counter(),
                             'role_counts': Counter(), 'request_positive_v': 0,
                             'request_negative_v': 0, 'output_negative_v': 0,
                             'request_turn_only': 0, 'output_positive_v': 0,
                             'output_turn_only': 0, 'positive_request_linear_veto': 0,
                             'maximum_abs_request_v': 0., 'maximum_abs_request_w': 0.,
                             'maximum_abs_output_v': 0., 'maximum_abs_output_w': 0.}
                      for robot in ROBOTS}
        self.reason_seen = {robot: set() for robot in ROBOTS}
        self.non_task_reach_counts = Counter()

    def select(self, channel, entry, cap):
        # Omissions are explicit; no truncated row or implicit complete-window claim.
        size = len(canonical(entry))
        if (self.channel_counts[channel] >= cap or self.selected_rows >= MAX_SELECTED_ROWS
                or self.selected_bytes + size > MAX_SELECTED_BYTES):
            self.dropped[channel] += 1
            return False
        self.result.setdefault('selected', {}).setdefault(channel, []).append(entry)
        self.channel_counts[channel] += 1
        self.selected_rows += 1
        self.selected_bytes += size
        return True

    def rows(self, filename):
        """One binary streaming pass: full original SHA + physical-line references."""
        path = self.directory / filename
        require(not path.is_symlink() and path.resolve().parent == self.directory,
                'input symlink/escape rejected')
        max_rows, max_bytes = INPUT_LIMITS[filename]
        path_before = path.stat()
        require(stat.S_ISREG(path_before.st_mode), 'input is not a regular file')
        require(path_before.st_size <= max_bytes, f'{filename}: byte cap')
        proof = {'path': str(path), 'stat_before': stat_record(path_before),
                 'bytes': 0, 'rows': 0, 'complete': False, 'kind_counts': {}}
        self.result['inputs'].append(proof)
        hasher, kinds, shapes = hashlib.sha256(), Counter(), {}
        with path.open('rb') as source:
            require(stat_record(os.fstat(source.fileno())) == proof['stat_before'],
                    'input changed between stat/open')
            line_number = 0
            while True:
                require(time.monotonic_ns() < self.deadline_ns, "580s bounded reader deadline")
                raw = source.readline(MAX_LINE_BYTES + 1)
                if not raw:
                    break
                line_number += 1
                require(line_number <= max_rows, f'{filename}: physical-row cap')
                require(len(raw) <= MAX_LINE_BYTES and raw.endswith(b'\n'),
                        f'{filename}: oversized/unterminated line')
                proof['bytes'] += len(raw)
                self.bytes_read += len(raw)
                require(proof['bytes'] <= max_bytes and self.bytes_read <= MAX_TOTAL_INPUT_BYTES,
                        'input byte cap')
                hasher.update(raw)
                row = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(
                    ValueError('nonfinite JSON: ' + value)))
                require(type(row) is dict, 'JSONL row is not an object')
                kind = row.get('kind', '<missing>')
                require(type(kind) is str and len(kind) <= 120, 'invalid kind')
                require(kind in kinds or len(kinds) < 64, 'too many input kinds')
                kinds[kind] += 1
                if kind not in shapes:
                    payload = row.get('payload')
                    shapes[kind] = {
                        'row_keys_first_32': [key[:120] for key in sorted(row)[:32]],
                        'payload_type': type(payload).__name__,
                        'payload_keys_first_32': ([key[:120] for key in sorted(payload)[:32]]
                                                 if isinstance(payload, dict) else None)}
                proof['rows'] += 1
                yield row, {'file': filename, 'line_1based': line_number,
                            'raw_line_sha256': digest(raw), 'raw_line_bytes': len(raw)}
            proof['stat_after_fd'] = stat_record(os.fstat(source.fileno()))
        proof['stat_after_path'] = stat_record(path.stat())
        require(proof['stat_before'] == proof['stat_after_fd'] == proof['stat_after_path'],
                f'{filename}: changed during consumption')
        require(proof['bytes'] == proof['stat_before']['size'], 'incomplete input byte count')
        proof.update(sha256=hasher.hexdigest(), complete=True, kind_counts=dict(kinds),
                     kind_key_shapes=shapes)

    def check_epoch(self, row):
        require(row.get('epoch') == self.epoch, 'source epoch mismatch')

    def in_window(self, robot, clock):
        return any(cancel - BEFORE_NS <= clock <= cancel + AFTER_NS
                   for cancel in self.cancel_clocks[robot])

    def snapshot_summary(self, snapshot):
        require(type(snapshot) is dict and snapshot.get('epoch') == self.epoch,
                'snapshot epoch mismatch')
        robots = snapshot.get('robots')
        require(type(robots) is list and [r.get('name') for r in robots] == list(ROBOTS),
                'snapshot requires ordered three robots')
        return {**take(snapshot, ('epoch', 'sequence', 'digest', 'task_elapsed_sec',
                                'candidate_version', 'candidate_rule')),
                'robots': [{**take(robot, ('name', 'x', 'y', 'yaw', 'v', 'w', 'fresh', 'valid',
                                           'source_stamp', 'received_stamp', 'odom_source_stamp',
                                           'path_map_available', 'path_map_source')),
                            'navigation': take(robot.get('navigation'),
                                ('phase', 'owned', 'goal_id', 'goal', 'accepted_goal_count',
                                 'requested_at', 'accepted_at', 'commitment_until',
                                 'commitment_remaining_sec', 'lease_until', 'cancel_requested',
                                 'cancel_started_at', 'stop_reason', 'last_terminal', 'failure')),
                            'activity': take(robot.get('activity'),
                                ('estimated_path_m', 'path_observation_complete'))}
                           for robot in robots]}

    def transitions(self):
        previous, steps = None, 0
        for row, ref in self.rows('transitions.jsonl'):
            kind, snapshot, info = row.get('kind'), row.get('snapshot'), row.get('info')
            require(type(info) is dict, 'missing transition info')
            if previous is None:
                require(kind == 'reset' and info.get('scene') == 'open' and info.get('seed') == 101,
                        'requires first reset open101')
                self.epoch = info.get('epoch')
                require(type(self.epoch) is str and self.epoch, 'invalid reset epoch')
                require(type(info.get('release_time_ns')) is int, 'missing release clock')
                self.result['episode'] = {'epoch': self.epoch, 'scene': 'open', 'seed': 101,
                                          'release_time_ns': info['release_time_ns']}
                self.task_start_ns = info['release_time_ns']
                self.select('transition_reset', {'ref': ref, 'snapshot': self.snapshot_summary(snapshot)}, 1)
            else:
                require(kind == 'step' and info.get('epoch') == self.epoch, 'non-step/epoch in interface')
                steps += 1
                command = info.get('command')
                require(type(command) is dict and type(command.get('action')) is int
                        and 0 <= command['action'] < 1000, 'requires actual step command')
                require(command.get('epoch') == self.epoch
                        and command.get('observation_sequence') == previous.get('sequence')
                        and command.get('observation_digest') == previous.get('digest'),
                        'step command does not bind preceding snapshot')
                action = command['action']
                choices = (action // 100, action // 10 % 10, action % 10)
                goals = []
                for robot, choice in zip(ROBOTS, choices):
                    goal = (take(previous['candidates'][choice],
                                 ('index', 'x', 'y', 'valid', 'reachable', 'path_distances_m'))
                            if choice < 8 else None)
                    goals.append({'robot': robot, 'choice': choice,
                                  'kind': 'GOAL' if choice < 8 else 'KEEP' if choice == 8 else 'WAIT',
                                  'selected_candidate': goal})
                elapsed = previous.get('task_elapsed_sec')
                self.select('probe_steps', {'ref': ref, 'step_1based': steps,
                    'command': command, 'selected_actions': goals,
                    'before_snapshot': self.snapshot_summary(previous),
                    'after_snapshot': self.snapshot_summary(snapshot),
                    'source_rule_conditions': {
                        'bounded_deadline': 10. <= elapsed < 13. or elapsed >= 28.,
                        'goal_window': elapsed < 1.5 or 13. <= elapsed < 26.,
                        'scope': 'condition only; producer reason/baseline-path diagnostics not read'},
                    'result': take(row, ('reward', 'terminated', 'truncated')),
                    'info': take(info, ('dt', 'physical_dt', 'reason', 'action_submitted'))}, 32)
            previous = snapshot
        require(steps == 32, 'requires exactly 32 returned interface steps')
        self.result['episode']['returned_steps'] = steps
        self.task_end_ns = self.task_start_ns + sec_ns(previous['task_elapsed_sec'])
        self.result['episode']['last_returned_clock_ns'] = self.task_end_ns

    def adapter(self):
        for row, ref in self.rows('adapter.jsonl'):
            self.check_epoch(row)
            kind, payload = row.get('kind'), row.get('payload')
            if not isinstance(payload, dict):
                # Unexpected/unused kinds are described by kind_key_shapes.
                require(kind not in ('native_send', 'native_cancel', 'protocol', 'action',
                                     'action_rejected', 'delivery'), 'selected adapter payload not object')
                continue
            if kind == 'native_cancel':
                robot = payload.get('robot')
                require(robot in ROBOTS, 'cancel robot invalid')
                self.cancel_clocks[robot].append(sec_ns(row.get('stamp')))
                require(len(self.cancel_clocks[robot]) <= 8, 'more than 8 native cancels per robot')
            keep = kind in ('native_send', 'native_cancel', 'protocol', 'action', 'action_rejected',
                            'rpc_error', 'edge_goal_not_sent', 'task_start')
            if kind == 'delivery':
                keep = payload.get('stream') in ('command', 'receipt')
            if keep:
                self.select('adapter_events', {'ref': ref, 'row': row}, 400)
        self.result['cancel_clocks_ns'] = self.cancel_clocks

    @staticmethod
    def state_summary(state):
        if not isinstance(state, dict):
            return {'observed_type': type(state).__name__}
        safety = state.get('safety')
        return {**take(state, ('name', 'epoch', 'x', 'y', 'yaw', 'source_stamp', 'received_stamp')),
                'intent': take(safety.get('intent') if isinstance(safety, dict) else None,
                    ('role', 'intent_sequence', 'source_clock_ns', 'admitted_signs', 'lineage'))}

    def motion(self):
        for row, ref in self.rows('motion_safety.jsonl'):
            self.check_epoch(row)
            kind, payload = row.get('kind'), row.get('payload')
            if not isinstance(payload, dict):
                require(kind not in ('reach_decision', 'actual_cmd_vel', 'own_odom'),
                        'selected motion payload not object')
                continue
            robot = payload.get('robot')
            if robot not in ROBOTS:
                continue
            clock = sec_ns(row.get('sim_time_sec'))
            if kind == 'reach_decision':
                decision, request = payload.get('decision'), payload.get('request')
                require(type(decision) is dict, 'missing reach decision')
                request = request if isinstance(request, dict) else {}
                output = decision.get('output')
                require(type(output) is list and len(output) == 2, 'invalid output')
                reason = decision.get('reason', '<missing>')
                role = (payload.get('intent') or {}).get('role', '<missing>')
                require(type(reason) is str and len(reason) <= 120
                        and type(role) is str and len(role) <= 24, 'unbounded decision label')
                v, w = request.get('v'), request.get('w')
                task = self.task_start_ns <= clock <= self.task_end_ns
                if task:
                    stats = self.stats[robot]
                    require(reason in stats['reason_counts'] or len(stats['reason_counts']) < 48,
                            'too many reach reasons')
                    stats['reach_decisions'] += 1
                    stats['reason_counts'][reason] += 1
                    stats['role_counts'][role] += 1
                    if type(v) in (int, float) and type(w) in (int, float):
                        stats['request_positive_v'] += v > 0
                        stats['request_negative_v'] += v < 0
                        stats['request_turn_only'] += v == 0 and w != 0
                        stats['positive_request_linear_veto'] += v > 0 and output[0] == 0
                        stats['maximum_abs_request_v'] = max(stats['maximum_abs_request_v'], abs(v))
                        stats['maximum_abs_request_w'] = max(stats['maximum_abs_request_w'], abs(w))
                    stats['output_positive_v'] += output[0] > 0
                    stats['output_negative_v'] += output[0] < 0
                    stats['output_turn_only'] += output[0] == 0 and output[1] != 0
                    stats['maximum_abs_output_v'] = max(stats['maximum_abs_output_v'], abs(output[0]))
                    stats['maximum_abs_output_w'] = max(stats['maximum_abs_output_w'], abs(output[1]))
                else:
                    self.non_task_reach_counts[robot] += 1
                key = (task, reason, role, v == 0, w == 0)
                representative = key not in self.reason_seen[robot] and len(self.reason_seen[robot]) < 24
                if representative:
                    self.reason_seen[robot].add(key)
                if representative or self.in_window(robot, clock):
                    selected = {'ref': ref, **take(row, ('epoch', 'kind', 'sim_time_sec',
                        'wall_monotonic_ns', 'record_sequence')),
                        **take(payload, ('robot', 'clock_ns', 'decision_sequence', 'request',
                                         'decision', 'intent', 'ready', 'started', 'phase_kind')),
                        'tracker': take(payload.get('tracker'), ('role', 'fault', 'permanent_stop',
                            'raw_samples', 'applied_samples', 'cumulative_path_diagnostic_m',
                            'backup_from_clock_ns', 'backup_zero_sequence', 'finite_stop_path_lower_m',
                            'continuous_physical_model_proved')),
                        'own_state': self.state_summary(payload.get('own_state')),
                        'received_peers': {name: self.state_summary(state) for name, state in
                                           (payload.get('received_peers') or {}).items()},
                        'in_task_interval': task,
                        'selection': 'first_signature' if representative else 'cancel_window'}
                    if self.select('reach_' + robot, selected, 160):
                        seq = payload.get('decision_sequence')
                        if type(seq) is int and (representative or clock in self.cancel_clocks[robot]):
                            self.target_sequences[robot].add(seq)
            elif kind == 'actual_cmd_vel':
                same_clock = clock in self.cancel_clocks[robot]
                if same_clock or self.in_window(robot, clock):
                    self.select(('sameclock_actual_' if same_clock else 'window_actual_') + robot,
                                {'ref': ref, 'row': row}, 96 if same_clock else 140)
            elif kind == 'own_odom' and self.in_window(robot, clock):
                self.select('received_raw_odom_' + robot, {'ref': ref, 'row': row}, 140)
        self.result['reach_statistics'] = self.stats
        self.result['reach_statistics_scope'] = 'release <= logged sim clock <= last returned sample clock'
        self.result['non_task_reach_decision_counts'] = dict(self.non_task_reach_counts)

    def driver(self, robot):
        seen = set()
        for row, ref in self.rows('drive_' + robot + '.jsonl'):
            self.check_epoch(row)
            require(row.get('robot') == robot, 'drive robot mismatch')
            kind, clock = row.get('kind'), row.get('sim_time_ns')
            require(type(clock) is int, 'drive sim_time_ns absent')
            seq = row.get('target_decision_sequence')
            # Native storage/status retain complete original rows in cancel windows.
            # For actuation, first real actuation per selected target/pair is enough
            # for lineage description, NOT a full 160ms/plant audit.
            keep = kind in ('target_rejected', 'configuration')
            keep = keep or (kind in ('command_received', 'status_publish') and self.in_window(robot, clock))
            signature = (seq, row.get('pair_index'))
            if kind == 'actuation' and seq in self.target_sequences[robot] and signature not in seen:
                keep = True
                seen.add(signature)
            if keep:
                self.select('driver_' + robot, {'ref': ref, 'row': row}, 256)

    def publisher_odometry(self, robot):
        for row, ref in self.rows('odometry_' + robot + '.jsonl'):
            self.check_epoch(row)
            require(row.get('robot') == robot, 'publisher odometry robot mismatch')
            clock = row.get('source_clock_ns', row.get('sim_time_ns'))
            require(type(clock) is int, 'publisher odometry clock absent')
            if self.in_window(robot, clock):
                self.select('publisher_raw_odom_' + robot, {'ref': ref, 'row': row}, 140)

    def run(self):
        self.transitions()
        self.adapter()
        self.motion()
        for robot in ROBOTS:
            self.driver(robot)
            self.publisher_odometry(robot)
        groups = []
        selected = self.result.get('selected', {})
        for event in selected.get('adapter_events', []):
            cancel = event['row']
            if cancel.get('kind') != 'native_cancel':
                continue
            robot = cancel['payload']['robot']
            clock = sec_ns(cancel['stamp'])
            same = [entry for entry in selected.get('sameclock_actual_' + robot, [])
                    if sec_ns(entry['row']['sim_time_sec']) == clock]
            same.sort(key=lambda entry: (entry['row'].get('wall_monotonic_ns', 10**30),
                       entry['row'].get('record_sequence', 10**30), entry['ref']['line_1based']))
            groups.append({'robot': robot, 'clock_ns': clock,
                'native_cancel_ref': event['ref'],
                'native_cancel_original_clock_fields': take(cancel,
                    ('stamp', 'wall_monotonic_ns', 'record_sequence')),
                'sameclock_actual_refs_in_motion_wall_sequence_order': [
                    {'ref': entry['ref'], **take(entry['row'],
                        ('sim_time_sec', 'wall_monotonic_ns', 'record_sequence'))} for entry in same],
                'cross_file_cancel_vs_actual_order': 'not established: adapter lacks wall/record sequence'})
        self.result['cancel_sameclock_groups'] = groups


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode-directory', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    directory = args.episode_directory.resolve(strict=True)
    require(directory.name == 'episode001_open_101' and directory.parent.name == 'worker0',
            'only V41 interface worker0 episode001_open_101 is supported')
    require(args.output.resolve() not in [directory / name for name in INPUT_LIMITS],
            'output overlaps input')
    started = time.monotonic_ns()
    result = {'schema': 'mr3-v41-closed-native-descriptive-extract-v1',
              'evidence_freeze': EVIDENCE_FREEZE, 'identity': identity(),
              'episode_directory': str(directory), 'started_monotonic_ns': started,
              'inputs': [], 'errors': [], 'extraction_complete': False,
              'physics_verdict_recomputed': False, 'qualification_credit': False,
              'closure_proof_external_required': True,
              'limits': {'input_limits': INPUT_LIMITS, 'max_total_input_bytes': MAX_TOTAL_INPUT_BYTES,
                         'max_line_bytes': MAX_LINE_BYTES, 'max_selected_rows': MAX_SELECTED_ROWS,
                         'max_selected_bytes': MAX_SELECTED_BYTES, 'max_output_bytes': MAX_OUTPUT_BYTES,
                         'per_cancel_window_ns': [-BEFORE_NS, AFTER_NS],
                         'channel_caps': {'probe_steps': 32, 'adapter_events': 400,
                                          'reach_per_robot': 160, 'sameclock_actual_per_robot': 96,
                                          'window_actual_per_robot': 140, 'driver_per_robot': 256,
                                          'received_or_publisher_odom_per_robot': 140}},
              'limitations': [
                  'Current source hashes must additionally be bound to the external execution freeze.',
                  'Input is read once: full raw SHA/bytes plus stat/fstat before/after; not two SHA passes.',
                  'Adapter has no wall time/sequence; drive/odom have no wall time. No clocks invented.',
                  'Physical line number is file order, not a cross-file execution timestamp.',
                  'Same-tick native-cancel versus final-Twist causality may remain unresolved.',
                  'Only selected closed interface episode; no inference about unrun matrix roles.',
                  'No benchmark producer diagnostics, local Nav2 path or unsaved controller internals read.',
                  'No map/blob decompression, source import, scalar/tensor replay, physics or safety re-verdict.',
                  'Windows and representative driver samples are descriptive, not complete plant qualification.',
              ]}
    extractor = Extractor(directory, result)
    # Claim exclusively before reading any evidence. Never overwrite a failed attempt.
    with args.output.open('xb') as output:
        try:
            result['sources_before'] = source_records()
            extractor.run()
            result['extraction_complete'] = True
        except Exception as error:
            result['errors'].append(type(error).__name__ + ': ' + str(error))
        finally:
            try:
                result['sources_after'] = source_records()
                result['sources_unchanged'] = result.get('sources_before') == result['sources_after']
                require(result['sources_unchanged'], 'source hash/metadata changed')
            except Exception as error:
                result['errors'].append('source finalization: ' + repr(error))
            result['selection_counts'] = dict(extractor.channel_counts)
            result['selection_dropped_counts'] = dict(extractor.dropped)
            result['selected_rows'] = extractor.selected_rows
            result['selected_payload_bytes'] = extractor.selected_bytes
            result['input_bytes_read'] = extractor.bytes_read
            result['ended_monotonic_ns'] = time.monotonic_ns()
            result['all_inputs_stable_complete'] = (len(result['inputs']) == len(INPUT_LIMITS)
                and all(proof.get('complete') is True for proof in result['inputs']))
            result['descriptive_selection_complete'] = not extractor.dropped
            result['passed_extraction_only'] = (result['extraction_complete']
                and result['all_inputs_stable_complete'] and not result['errors'])
            encoded = canonical(result) + b'\n'
            if len(encoded) > MAX_OUTPUT_BYTES:
                # Preserve the input/source receipts and the precise failure; never
                # silently truncate arbitrary JSON or publish a misleading success.
                result.pop('selected', None)
                result['errors'].append('output cap exceeded; selected payload omitted in its entirety')
                result['passed_extraction_only'] = False
                encoded = canonical(result) + b'\n'
            require(len(encoded) <= MAX_OUTPUT_BYTES, 'receipt alone exceeds output cap')
            output.write(encoded)
            output.flush()
            os.fsync(output.fileno())
    print(json.dumps({'output': str(args.output), 'identity': result['identity'],
                      'passed_extraction_only': result['passed_extraction_only'],
                      'selected_rows': result['selected_rows'], 'errors': result['errors']}))
    return 0 if result['passed_extraction_only'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
