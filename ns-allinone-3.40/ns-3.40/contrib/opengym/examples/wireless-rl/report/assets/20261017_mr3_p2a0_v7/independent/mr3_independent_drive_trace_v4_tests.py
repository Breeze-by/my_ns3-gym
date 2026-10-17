"""Synthetic mutations only: independent driver trace audit, no ROS/native load."""
import copy
from fractions import Fraction
import gzip
import importlib.util
import json
import math
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    'drive_audit', Path(__file__).with_name('mr3_independent_drive_trace_v4.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
FREEZE = 'a'*40
EPOCH = 'synthetic-algebra-only'


def fixture(name, compiled, library, command_times=None):
    guard_times = list(range(20_000_000, 201_000_000, 20_000_000))
    command_times = guard_times if command_times is None else command_times
    guards = [{'clock_ns': stamp, 'output': [.1, .2], 'decision_sequence': index,
               'line': index} for index, stamp in enumerate(guard_times, 1)]
    config = {'kind': 'configuration', 'library_filename': 'libmr3_gazebo_diff_drive.so',
              'loaded_library_path': str(library), 'upstream_source_sha256': M.UPSTREAM_SHA,
              'wheel_order': ['right', 'left'],
              'joint_names': ['wheel_right_joint', 'wheel_left_joint'],
              'wheel_separation_m': [.287], 'wheel_diameter_m': [.066],
              'max_acceleration_mps2': 1., 'max_torque_nm': 20., 'update_rate_hz': 30.,
              'odometry_source': 1, 'num_wheel_pairs': 1, 'actuation_algorithm': M.ALGORITHM,
              'command_mode': 'tagged', 'command_topic': f'/{name}/mr3_drive/target',
              'status_topic': f'/{name}/mr3_drive/status', **compiled, 'sim_time_ns': 0}
    rows = [config]
    for sequence, stamp in enumerate(command_times, 1):
        rows.append({'kind': 'command_received', 'cmd_seq': sequence, 'desired_v': .1,
                     'desired_w': .2, 'sim_time_ns': stamp,
                     'target_decision_sequence': guard_times.index(stamp)+1,
                     'target_clock_ns': stamp})
        rows.append({'kind': 'status_publish', 'cmd_seq': sequence, 'desired_v': .1,
                     'desired_w': .2, 'sim_time_ns': stamp,
                     'target_decision_sequence': guard_times.index(stamp)+1,
                     'target_clock_ns': stamp,
                     'scope': 'target_storage_and_status_publication',
                     'status': {'schema': 'mr3-drive-target-consumed-v1', 'epoch': EPOCH,
                                'robot': name, 'clock_ns': stamp,
                                'decision_sequence': guard_times.index(stamp)+1,
                                'source_clock_ns': stamp, 'cmd_seq': sequence,
                                'linear_x': .1, 'angular_z': .2}})
    for sequence, stamp in enumerate(range(34_000_000, 205_000_000, 34_000_000), 1):
        command_sequence = sum(clock <= stamp for clock in command_times)
        target_clock = max(clock for clock in command_times if clock <= stamp)
        desired = [.1+.2*.287/2, .1-.2*.287/2]
        budget = Fraction.from_float(.034)
        nominal = min(Fraction(1), budget/max(Fraction.from_float(x) for x in desired))
        alpha = float(nominal)
        while (Fraction.from_float(alpha) > nominal or any(
                Fraction.from_float(alpha*x) > budget for x in desired)):
            alpha = math.nextafter(alpha, 0.)
        rows.append({'kind': 'actuation', 'actuation_seq': sequence, 'pair_index': 0,
                     'cmd_seq': command_sequence, 'desired_v': .1, 'desired_w': .2,
                     'dt_ns': 34_000_000, 'dt_sec': .034, 'current_rim_mps': [0., 0.],
                     'desired_rim_mps': desired, 'applied_rim_mps': [alpha*x for x in desired],
                     'alpha': alpha, 'max_acceleration_mps2': 1., 'sim_time_ns': stamp})
        rows[-1].update(target_decision_sequence=guard_times.index(target_clock)+1,
                        target_clock_ns=target_clock)
    rows.sort(key=lambda row: row['sim_time_ns'])
    for index, row in enumerate(rows, 1):
        row.update(schema='mr3-drive-actuation-v2', epoch=EPOCH, robot=name, record_sequence=index)
    return rows, guards


class DriveMutationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root/'run/worker0/episode001_open_101'
        self.directory.mkdir(parents=True)
        self.source_raw = {path: ('synthetic '+key).encode() for key, path in M.SOURCE_PATHS.items()}
        self.compiled = {key: M.sha(self.source_raw[path]) for key, path in M.SOURCE_PATHS.items()}
        self.library = self.root/'libmr3_gazebo_diff_drive.so'
        self.library.write_bytes(b'not executable, synthetic binary hash fixture only')
        self.binary = {'library_path': str(self.library)}
        self.rows, self.guards = {}, {}
        for name in M.ROBOTS:
            self.rows[name], self.guards[name] = fixture(name, self.compiled, self.library)
        self.old_model = b'''<sdf version="1.6"><model name="turtlebot3_waffle"><link name="base"><mass>1.372</mass></link><plugin name="turtlebot3_diff_drive" filename="libgazebo_ros_diff_drive.so"><update_rate>30</update_rate><wheel_separation>0.287</wheel_separation><wheel_diameter>0.066</wheel_diameter><max_wheel_acceleration>1.0</max_wheel_acceleration><max_wheel_torque>20</max_wheel_torque><odometry_source>1</odometry_source></plugin></model></sdf>'''
        self.template = self.old_model.replace(b'libgazebo_ros_diff_drive.so',
                                               b'libmr3_gazebo_diff_drive.so').replace(
                                                   b'</plugin>', b'<mr3_audit_path/><mr3_epoch/><mr3_tagged_commands>true</mr3_tagged_commands></plugin>')
        self.proof = {'schema': 'mr3-drive-binary-binding-v1', 'freeze': FREEZE,
                      'library_path': str(self.library), 'library_sha256': M.sha(self.library.read_bytes()),
                      **self.compiled}
        self.proof_path = self.root/'proof.json'
        self.write_all()

    def json_file(self, path, value):
        path.write_text(json.dumps(value)+'\n')

    def lines_file(self, path, values):
        path.write_text(''.join(json.dumps(row)+'\n' for row in values))

    def write_all(self):
        self.json_file(self.proof_path, self.proof)
        self.json_file(self.directory/'metadata.json', {'epoch': EPOCH, 'freeze': FREEZE,
                       'command': ['mr3_audit_path:='+str(self.directory/'adapter.jsonl')]})
        self.json_file(self.directory/'summary.json', {'scope': 'synthetic only'})
        self.json_file(self.directory.parent.parent/'benchmark_metadata.json', {
            'freeze': FREEZE, 'terminal_probe': False, 'workers': 1, 'steps_per_episode': 20,
            'schedule': [['open', 101]], 'preparation_motion_probe': True})
        self.lines_file(self.directory/'transitions.jsonl', [
            {'kind': 'reset', 'info': {'epoch': EPOCH, 'release_time_ns': 100_000_000}},
            {'kind': 'step', 'info': {'dt': .104, 'reason': 'external_truncation'},
             'terminated': False, 'truncated': True}])
        physics = [{'epoch': EPOCH, 'request_id': f'q{index}', 'step_ns': 1_000_000,
                    'start_time_ns': start*1_000_000, 'end_time_ns': min(start+20, 204)*1_000_000,
                    'steps': min(20, 204-start), 'start_iterations': start,
                    'end_iterations': min(start+20, 204), 'ok': True, 'paused': True}
                   for index, start in enumerate(range(100, 204, 20), 1)]
        self.lines_file(self.directory/'physics.jsonl', physics)
        phase = []
        def event(kind, clock, **fields):
            phase.append({'kind': kind, 'epoch': EPOCH, 'wall_monotonic_ns': len(phase)+1,
                          'worker_clock_ns': clock, 'worker_physical_ns': clock, **fields})
        for physical in physics:
            clock = physical['start_time_ns']
            receipts = {name: copy.deepcopy(next(row['status'] for row in self.rows[name]
                                                 if row['kind'] == 'status_publish' and
                                                 row['sim_time_ns'] == clock))
                        for name in M.ROBOTS}
            expected = {'schema': 'mr3-motion-safety-status-v1', 'epoch': EPOCH,
                        'clock_ns': clock, 'ready': True,
                        'completion_scope': 'publication_and_local_topic_receipt',
                        'decision_sequences': {name: status['decision_sequence']
                                               for name, status in receipts.items()},
                        'outputs': {name: {'linear_x': status['linear_x'], 'angular_z': status['angular_z']}
                                    for name, status in receipts.items()}}
            for status in receipts.values():
                event('ack_received', clock, topic_robot=status['robot'], ack=status)
            event('ack_consumed', clock, expected_motion=expected, receipts=receipts)
            event('advance_permitted', clock, request_id=physical['request_id'],
                  steps=physical['steps'], start_time_ns=clock,
                  expected_motion=expected, receipts=receipts)
            event('physics_completed', physical['end_time_ns'], receipt=physical)
        self.lines_file(self.directory/'drive_phase_worker.jsonl', phase)
        first = next(row for row in phase if row['kind'] == 'ack_consumed')
        transitions = [json.loads(line) for line in (self.directory/'transitions.jsonl').read_text().splitlines()]
        transitions[0]['info'].update(initial_motion_status=first['expected_motion'],
                                      initial_drive_receipts=first['receipts'],
                                      drive_phase_protocol='mr3-drive-target-consumed-v1')
        self.lines_file(self.directory/'transitions.jsonl', transitions)
        motion = []
        for name in M.ROBOTS:
            for decision in self.guards[name]:
                motion.append({'schema': 'mr3-motion-safety-v1', 'epoch': EPOCH, 'kind': 'decision',
                               'payload': {'robot': name, 'clock_ns': decision['clock_ns'],
                                           'decision_sequence': decision['decision_sequence'],
                                           'decision': {'output': decision['output']}}})
        motion.sort(key=lambda row: row['payload']['clock_ns'])
        for sequence, row in enumerate(motion, 1):
            row['record_sequence'] = sequence
        self.lines_file(self.directory/'motion_safety.jsonl', motion)
        publications = []
        for index, row in enumerate(motion, 1):
            source = row['payload']
            target = {'schema': 'mr3-drive-target-v1', 'epoch': EPOCH, 'robot': source['robot'],
                      'clock_ns': source['clock_ns'], 'decision_sequence': source['decision_sequence'],
                      'linear_x': source['decision']['output'][0], 'angular_z': source['decision']['output'][1]}
            publications.append({'schema': 'mr3-drive-target-publication-v1', 'epoch': EPOCH,
                                 'record_sequence': index, 'wall_monotonic_ns': index,
                                 'target_json': json.dumps(target, sort_keys=True, allow_nan=False)})
        self.lines_file(self.directory/'drive_targets.jsonl', publications)
        topology = {'schema': 'mr3-drive-topology-v1', 'epoch': EPOCH, 'clock_ns': 80_000_000,
                    'publishers': {}, 'target_subscribers': {}, 'legacy_subscribers': {}}
        def endpoint(owner, index, topic_type='std_msgs/msg/String'):
            return {'namespace': owner[0], 'node': owner[1], 'topic_type': topic_type,
                    'endpoint_gid': format(index, '048x')}
        for index, name in enumerate(M.ROBOTS):
            target, status = f'/{name}/mr3_drive/target', f'/{name}/mr3_drive/status'
            driver = ('/'+name, 'turtlebot3_diff_drive')
            topology['publishers'][target] = [endpoint(('/', 'motion_safety'), 3*index+1)]
            topology['publishers'][status] = [endpoint(driver, 3*index+2)]
            topology['target_subscribers'][target] = [endpoint(driver, 3*index+3)]
            topology['legacy_subscribers'][f'/{name}/cmd_vel'] = [
                endpoint(('/', 'motion_safety'), index+100, 'geometry_msgs/msg/Twist')]
        self.json_file(self.directory/'drive_topology.json', topology)
        (self.directory/'launch.log').write_text(''.join(
            'MR3_ORDERED_SHUTDOWN '+json.dumps({
                'event': 'process_started', 'epoch': EPOCH,
                'argv': ['/opt/ros/humble/lib/gazebo_ros/spawn_entity.py',
                         '-file', str(self.directory/f'drive_model_{name}.sdf'),
                         '-entity', name, '-robot_namespace', '/'+name]})+'\n'
            for name in M.ROBOTS))
        for name in M.ROBOTS:
            self.lines_file(self.directory/f'drive_{name}.jsonl', self.rows[name])
            effective = self.template.replace(b'<mr3_audit_path/>',
                f'<mr3_audit_path>{self.directory}/drive_{name}.jsonl</mr3_audit_path>'.encode()).replace(
                    b'<mr3_epoch/>', f'<mr3_epoch>{EPOCH}</mr3_epoch>'.encode())
            (self.directory/f'drive_model_{name}.sdf').write_bytes(effective)

    def blob(self, freeze, path):
        if path == M.MODEL:
            return self.old_model if freeze == M.BASELINE else self.template
        return self.source_raw[path]

    def review(self, archived=False):
        with patch.object(M, 'ROOT', self.root), patch.object(M, 'git_blob', side_effect=self.blob):
            return M.review(self.directory, FREEZE, self.proof_path, archived)

    def core(self, rows=None, guards=None, release=100_000_000, final=204_000_000, terminal=False,
             initial_receipt=None):
        return M.robot_audit(self.rows['tb1'] if rows is None else rows,
                             self.guards['tb1'] if guards is None else guards,
                             'tb1', EPOCH, release, final, 1_000_000, self.compiled,
                             self.binary, terminal, initial_receipt)

    def first_act(self):
        return next(row for row in self.rows['tb1'] if row['kind'] == 'actuation')

    def phase_core(self, records=None, physics=None):
        def load(name):
            return [json.loads(line) for line in (self.directory/name).read_text().splitlines()]
        statuses = {name: {row['target_decision_sequence']: dict(row['status'], trace_line=line)
                          for line, row in enumerate(self.rows[name], 1)
                          if row['kind'] == 'status_publish'} for name in M.ROBOTS}
        return M.drive_phase(load('drive_phase_worker.jsonl') if records is None else records,
                             load('physics.jsonl') if physics is None else physics,
                             EPOCH, 100_000_000, self.guards, statuses,
                             load('transitions.jsonl')[0]['info']['initial_motion_status'],
                             load('transitions.jsonl')[0]['info']['initial_drive_receipts'])

    def phase_rows(self):
        return [json.loads(line) for line in (self.directory/'drive_phase_worker.jsonl').read_text().splitlines()]

    def phase_renumber(self, rows):
        for index, row in enumerate(rows, 1):
            row['wall_monotonic_ns'] = index
        return rows

    def test_worker_phase_binds_all_actual_advances(self):
        result = self.phase_core()
        self.assertTrue(result['passed'])
        self.assertEqual(result['positive_task_cleanup_advances'], 6)
        self.assertEqual(result['permitted_advances'], 6)

    def test_missing_actual_phase_receipt_or_consumption_permission_or_completion_fails(self):
        for kind in ('ack_received', 'ack_consumed', 'advance_permitted', 'physics_completed'):
            with self.subTest(kind=kind):
                rows = self.phase_rows()
                rows.remove(next(row for row in rows if row['kind'] == kind))
                with self.assertRaises(ValueError):
                    self.phase_core(rows)

    def test_worker_ack_cannot_invent_native_status_identity_value_or_time(self):
        for field, value in [('epoch', 'wrong'), ('robot', 'tb2'), ('clock_ns', 99_000_000),
                             ('decision_sequence', 6), ('source_clock_ns', 99_000_000),
                             ('cmd_seq', 6), ('linear_x', .11), ('angular_z', .21), ('cmd_seq', True)]:
            with self.subTest(field=field, value=value):
                rows = self.phase_rows()
                rows[0]['ack'][field] = value
                with self.assertRaises(ValueError):
                    self.phase_core(rows)

    def test_worker_phase_must_use_exact_expected_motion_and_three_roles(self):
        for mutation in ('source_sequence', 'source_value', 'clock', 'receipt_value', 'missing_role'):
            with self.subTest(mutation=mutation):
                rows = self.phase_rows()
                row = next(row for row in rows if row['kind'] == 'ack_consumed')
                if mutation == 'source_sequence':
                    row['expected_motion']['decision_sequences']['tb1'] += 1
                elif mutation == 'source_value':
                    row['expected_motion']['outputs']['tb1']['linear_x'] += .001
                elif mutation == 'clock':
                    row['expected_motion']['clock_ns'] += 1_000_000
                elif mutation == 'receipt_value':
                    row['receipts']['tb1']['linear_x'] += .001
                else:
                    row['receipts'].pop('tb2')
                with self.assertRaises(ValueError):
                    self.phase_core(rows)

    def test_worker_advance_cannot_precede_ack_or_completion_precede_permission(self):
        for mutation in ('advance_before_ack', 'completion_before_permission'):
            with self.subTest(mutation=mutation):
                rows = self.phase_rows()
                if mutation == 'advance_before_ack':
                    row = next(row for row in rows if row['kind'] == 'advance_permitted')
                    rows.remove(row)
                    rows.insert(0, row)
                else:
                    rows[4], rows[5] = rows[5], rows[4]
                with self.assertRaises(ValueError):
                    self.phase_core(self.phase_renumber(rows))

    def test_worker_advance_cannot_change_request_id_steps_start_or_actual_completion(self):
        for mutation in ('request_id', 'steps', 'start_time_ns', 'completion'):
            with self.subTest(mutation=mutation):
                rows = self.phase_rows()
                row = next(row for row in rows if row['kind'] == 'advance_permitted')
                if mutation == 'request_id':
                    row['request_id'] = 'q999'
                elif mutation in ('steps', 'start_time_ns'):
                    row[mutation] += 1
                else:
                    next(row for row in rows if row['kind'] == 'physics_completed')['receipt']['end_iterations'] += 1
                with self.assertRaises(ValueError):
                    self.phase_core(rows)

    def test_exact_cached_status_may_be_reobserved_and_consumed_without_fake_physical_credit(self):
        rows = self.phase_rows()
        rows.insert(1, copy.deepcopy(rows[0]))
        row = next(row for row in rows if row['kind'] == 'ack_consumed')
        rows.insert(rows.index(row)+1, copy.deepcopy(row))
        result = self.phase_core(self.phase_renumber(rows))
        self.assertTrue(result['passed'])
        self.assertEqual(result['actual_subscription_statuses'], 18)
        self.assertEqual(result['consumed_barriers'], 7)

    def test_old_cached_ack_cannot_replace_a_newer_actual_drive_receipt(self):
        for mutation in ('consume_old', 'received_regression'):
            with self.subTest(mutation=mutation):
                rows = self.phase_rows()
                future = copy.deepcopy(rows[6])
                rows.insert(3, future)
                if mutation == 'received_regression':
                    rows.insert(4, copy.deepcopy(rows[0]))
                with self.assertRaisesRegex(ValueError, 'old cached|regressed'):
                    self.phase_core(self.phase_renumber(rows))

    def test_missing_worker_phase_file_fails_whole_episode(self):
        (self.directory/'drive_phase_worker.jsonl').unlink()
        result = self.review()
        self.assertFalse(result['passed'])
        self.assertFalse(result['episodes'][0]['driver_consumption_phase']['passed'])

    def test_publication_ledger_exactly_covers_guard_decisions_and_protocol_fields(self):
        def load(name):
            return [json.loads(line) for line in (self.directory/name).read_text().splitlines()]
        guards = M.guard_outputs(load('motion_safety.jsonl'), EPOCH, 100_000_000)
        original = load('drive_targets.jsonl')
        self.assertEqual(M.target_publications(original, guards, EPOCH)['publications'], 30)
        for mutation in ('missing', 'duplicate', 'robot', 'sequence', 'value', 'extra', 'duplicate_key', 'record_sequence'):
            with self.subTest(mutation=mutation):
                rows = copy.deepcopy(original)
                target = json.loads(rows[0]['target_json'])
                if mutation == 'missing':
                    rows.pop()
                elif mutation == 'duplicate':
                    rows[1]['target_json'] = rows[0]['target_json']
                elif mutation == 'record_sequence':
                    rows[0]['record_sequence'] = True
                elif mutation == 'duplicate_key':
                    rows[0]['target_json'] = rows[0]['target_json'][:-1]+', "robot": "tb1"}'
                else:
                    if mutation == 'robot':
                        target['robot'] = 'tb2'
                    elif mutation == 'sequence':
                        target['decision_sequence'] += 1
                    elif mutation == 'value':
                        target['angular_z'] += .01
                    else:
                        target['extra'] = 'not protocol'
                    rows[0]['target_json'] = json.dumps(target)
                with self.assertRaises(ValueError):
                    M.target_publications(rows, guards, EPOCH)

    def test_topology_requires_actual_unique_target_status_endpoints_and_no_legacy_driver(self):
        topology = json.loads((self.directory/'drive_topology.json').read_text())
        self.assertEqual(M.drive_topology(topology, EPOCH, 100_000_000)['native_endpoints'], 9)
        target, status = '/tb1/mr3_drive/target', '/tb1/mr3_drive/status'
        for mutation in ('missing', 'duplicate', 'owner', 'type', 'gid', 'duplicate_gid', 'legacy', 'future'):
            with self.subTest(mutation=mutation):
                row = copy.deepcopy(topology)
                if mutation == 'missing':
                    row['publishers'].pop(target)
                elif mutation == 'duplicate':
                    row['publishers'][target].append(copy.deepcopy(row['publishers'][target][0]))
                elif mutation == 'owner':
                    row['publishers'][target][0]['node'] = 'other'
                elif mutation == 'type':
                    row['publishers'][target][0]['topic_type'] = 'geometry_msgs/msg/Twist'
                elif mutation == 'gid':
                    row['publishers'][target][0]['endpoint_gid'] = '0'*48
                elif mutation == 'duplicate_gid':
                    row['publishers'][status][0]['endpoint_gid'] = row['publishers'][target][0]['endpoint_gid']
                elif mutation == 'legacy':
                    row['legacy_subscribers']['/tb1/cmd_vel'][0].update(namespace='/tb1', node='turtlebot3_diff_drive')
                else:
                    row['clock_ns'] = 101_000_000
                with self.assertRaises(ValueError):
                    M.drive_topology(row, EPOCH, 100_000_000)

    def test_missing_publication_or_topology_source_fails_whole_episode(self):
        for name in ('drive_targets.jsonl', 'drive_topology.json'):
            with self.subTest(name=name):
                path = self.directory/name
                raw = path.read_bytes()
                path.unlink()
                try:
                    result = self.review()
                    self.assertFalse(result['passed'])
                    self.assertIn('FileNotFoundError', result['episodes'][0]['error'])
                finally:
                    path.write_bytes(raw)

    def test_worker_topic_robot_binding_and_paused_boundary_are_mandatory(self):
        for mutation in ('topic', 'consume_clock', 'advance_physics'):
            with self.subTest(mutation=mutation):
                rows = self.phase_rows()
                if mutation == 'topic':
                    rows[0]['topic_robot'] = 'tb2'
                elif mutation == 'consume_clock':
                    next(row for row in rows if row['kind'] == 'ack_consumed')['worker_clock_ns'] += 1
                else:
                    next(row for row in rows if row['kind'] == 'advance_permitted')['worker_physical_ns'] += 1
                with self.assertRaises(ValueError):
                    self.phase_core(rows)

    def test_reset_initial_receipts_must_be_actual_consumed_release_ack(self):
        path = self.directory/'transitions.jsonl'
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[0]['info']['initial_drive_receipts']['tb1']['cmd_seq'] += 1
        self.lines_file(path, rows)
        result = self.review()
        self.assertFalse(result['passed'])
        self.assertIn('initial', result['episodes'][0]['robots']['tb1']['error'])

    def renumber(self, rows):
        for index, row in enumerate(rows, 1):
            row['record_sequence'] = index
        return rows

    def test_tagged_target_must_bind_unique_guard_identity_and_not_just_equal_twist(self):
        for mutation in ('duplicate', 'wrong_guard', 'future', 'rewind', 'bool'):
            with self.subTest(mutation=mutation):
                rows = copy.deepcopy(self.rows['tb1'])
                targets = [row for row in rows if row['kind'] == 'command_received']
                if mutation == 'duplicate':
                    targets[1]['target_decision_sequence'] = targets[0]['target_decision_sequence']
                elif mutation == 'wrong_guard':
                    targets[0]['target_decision_sequence'] = 2
                elif mutation == 'future':
                    targets[0]['target_clock_ns'] += 1_000_000
                elif mutation == 'rewind':
                    targets[1]['target_clock_ns'] = 0
                else:
                    targets[0]['target_decision_sequence'] = True
                with self.assertRaises(ValueError):
                    self.core(rows)

    def test_consumed_status_is_exact_storage_publication_not_a_synthetic_receipt(self):
        for mutation in ('missing', 'before_receive', 'sequence', 'source', 'value', 'scope', 'bool'):
            with self.subTest(mutation=mutation):
                rows = copy.deepcopy(self.rows['tb1'])
                status = next(row for row in rows if row['kind'] == 'status_publish')
                if mutation == 'missing':
                    rows.remove(status)
                elif mutation == 'before_receive':
                    index = rows.index(status)
                    rows[index-1], rows[index] = rows[index], rows[index-1]
                elif mutation == 'sequence':
                    status['status']['decision_sequence'] += 1
                elif mutation == 'source':
                    status['status']['source_clock_ns'] += 1
                elif mutation == 'value':
                    status['status']['linear_x'] += .001
                elif mutation == 'scope':
                    status['scope'] = 'physical_actuation_ack'
                else:
                    status['status']['cmd_seq'] = True
                with self.assertRaises(ValueError):
                    self.core(self.renumber(rows))

    def test_actuation_must_use_latest_tagged_target_identity(self):
        for field in ('target_decision_sequence', 'target_clock_ns'):
            with self.subTest(field=field):
                rows = copy.deepcopy(self.rows['tb1'])
                next(row for row in rows if row['kind'] == 'actuation')[field] += 1
                with self.assertRaisesRegex(ValueError, 'target identity'):
                    self.core(rows)

    def test_guard_source_age_is_bounded_even_when_driver_receipt_is_fresh(self):
        rows, guards = fixture('tb1', self.compiled, self.library, command_times=[20_000_000])
        guards = [dict(guards[0], clock_ns=0)]
        rows = [row for row in rows if row['kind'] != 'actuation' or row['sim_time_ns'] >= 170_000_000]
        for row in rows:
            if row['kind'] in ('command_received', 'status_publish'):
                row['sim_time_ns'], row['target_clock_ns'] = 160_000_000, 0
                if row['kind'] == 'status_publish':
                    row['status'].update(clock_ns=160_000_000, source_clock_ns=0)
            elif row['kind'] == 'actuation':
                row['target_clock_ns'] = 0
                row['actuation_seq'] -= 4
        rows.sort(key=lambda row: row['sim_time_ns'])
        with self.assertRaisesRegex(ValueError, 'latest actual guard target missing/stale'):
            self.core(self.renumber(rows), guards, release=160_000_000)

    def test_only_proven_zero_before_initial_storage_at_same_release_is_prewarm(self):
        for mutation in ('valid', 'wrong_initial_seq', 'wrong_order', 'nonzero',
                         'source_started', 'missing_source_phase', 'after_release'):
            with self.subTest(mutation=mutation):
                rows, guards = fixture('tb1', self.compiled, self.library, command_times=[20_000_000])
                nonzero = mutation == 'nonzero'
                guards = [dict(guards[0], clock_ns=0, started=False,
                               output=[.1, .2] if nonzero else [0., 0.]),
                          {'clock_ns': 204_000_000, 'started': False, 'output': [0., 0.],
                           'decision_sequence': 2, 'line': 2}]
                for row in rows:
                    if row['kind'] in ('command_received', 'status_publish', 'actuation'):
                        row['target_clock_ns'] = 0
                        if not nonzero:
                            row.update(desired_v=0., desired_w=0.)
                    if row['kind'] == 'status_publish':
                        row['status']['source_clock_ns'] = 0
                        if not nonzero:
                            row['status'].update(linear_x=0., angular_z=0.)
                    if row['kind'] == 'actuation' and not nonzero:
                        row.update(desired_rim_mps=[0., 0.], applied_rim_mps=[0., 0.], alpha=1.)
                command = copy.deepcopy(next(row for row in rows if row['kind'] == 'command_received'))
                command.update(cmd_seq=2, desired_v=0., desired_w=0., target_decision_sequence=2,
                               target_clock_ns=204_000_000, sim_time_ns=204_000_000)
                status = copy.deepcopy(next(row for row in rows if row['kind'] == 'status_publish'))
                status.update(cmd_seq=2, desired_v=0., desired_w=0., target_decision_sequence=2,
                              target_clock_ns=204_000_000, sim_time_ns=204_000_000)
                status['status'].update(cmd_seq=2, decision_sequence=2, linear_x=0., angular_z=0.,
                                        clock_ns=204_000_000, source_clock_ns=204_000_000)
                initial = copy.deepcopy(status['status'])
                anchor = rows[-1]
                rows.extend([command, status])
                late = copy.deepcopy(anchor)
                late.update(cmd_seq=2, desired_v=0., desired_w=0., target_decision_sequence=2,
                            target_clock_ns=204_000_000, sim_time_ns=238_000_000, actuation_seq=7,
                            desired_rim_mps=[0., 0.], applied_rim_mps=[0., 0.], alpha=1.)
                rows.append(late)
                final = 238_000_000
                if mutation == 'wrong_initial_seq':
                    initial['cmd_seq'] = 1
                elif mutation == 'wrong_order':
                    rows.remove(anchor)
                    rows.insert(rows.index(status)+1, anchor)
                elif mutation == 'source_started':
                    guards[0]['started'] = True
                elif mutation == 'missing_source_phase':
                    guards[0].pop('started')
                elif mutation == 'after_release':
                    for sequence, clock in enumerate(range(272_000_000, 375_000_000, 34_000_000), 8):
                        rows.append(dict(late, actuation_seq=sequence, sim_time_ns=clock))
                    final = 374_000_000
                self.renumber(rows)
                if mutation == 'valid':
                    result = self.core(rows, guards, release=204_000_000, final=final, initial_receipt=initial)
                    self.assertEqual(len(result['pre_initial_storage_zero_prewarm_anchors']), 1)
                    self.assertFalse(result['pre_initial_storage_zero_prewarm_anchors'][0]['sampled_response_credit'])
                else:
                    with self.assertRaises(ValueError):
                        self.core(rows, guards, release=204_000_000, final=final, initial_receipt=initial)

    def test_only_proven_initial_boundary_prewarm_commands_may_have_old_zero_source(self):
        for mutation in ('valid_same_clock', 'valid_before_clock', 'nonzero', 'started',
                         'missing_phase', 'missing_initial', 'after_initial', 'clock_after_release',
                         'task_stale'):
            with self.subTest(mutation=mutation):
                rows, _ = fixture('tb1', self.compiled, self.library, command_times=[20_000_000])
                old_output = [.1, .2] if mutation == 'nonzero' else [0., 0.]
                guards = [{'clock_ns': 0, 'decision_sequence': 1, 'line': 1,
                           'output': old_output, 'started': False},
                          {'clock_ns': 204_000_000, 'decision_sequence': 2, 'line': 2,
                           'output': [0., 0.], 'started': False}]
                old_command = next(row for row in rows if row['kind'] == 'command_received')
                old_status = next(row for row in rows if row['kind'] == 'status_publish')
                for row in rows:
                    if row['kind'] in ('command_received', 'status_publish', 'actuation'):
                        row['target_clock_ns'] = 0
                    if row['kind'] in ('command_received', 'status_publish'):
                        row.update(sim_time_ns=204_000_000, desired_v=old_output[0], desired_w=old_output[1])
                    if row['kind'] == 'status_publish':
                        row['status'].update(clock_ns=204_000_000, source_clock_ns=0,
                                              linear_x=old_output[0], angular_z=old_output[1])
                    if row['kind'] == 'actuation':
                        if row['sim_time_ns'] < 204_000_000:
                            row.update(cmd_seq=0, target_decision_sequence=0)
                        if row['sim_time_ns'] < 204_000_000 or mutation != 'nonzero':
                            row.update(desired_v=0., desired_w=0., desired_rim_mps=[0., 0.],
                                       applied_rim_mps=[0., 0.], alpha=1.)
                command = dict(old_command, cmd_seq=2, desired_v=0., desired_w=0.,
                               target_decision_sequence=2, target_clock_ns=204_000_000)
                status = copy.deepcopy(old_status)
                status.update(cmd_seq=2, desired_v=0., desired_w=0., target_decision_sequence=2,
                              target_clock_ns=204_000_000)
                status['status'].update(cmd_seq=2, decision_sequence=2, source_clock_ns=204_000_000,
                                        linear_x=0., angular_z=0.)
                initial = copy.deepcopy(status['status'])
                anchor = rows[-1]
                rows.extend([command, status])
                late = dict(anchor, cmd_seq=2, desired_v=0., desired_w=0., target_decision_sequence=2,
                            target_clock_ns=204_000_000, sim_time_ns=238_000_000, actuation_seq=7,
                            desired_rim_mps=[0., 0.], applied_rim_mps=[0., 0.], alpha=1.)
                rows.append(late)
                final = 238_000_000
                if mutation == 'valid_before_clock':
                    old_command['sim_time_ns'] = old_status['sim_time_ns'] = 203_000_000
                    old_status['status']['clock_ns'] = 203_000_000
                elif mutation == 'started':
                    guards[0]['started'] = True
                elif mutation == 'missing_phase':
                    guards[0].pop('started')
                elif mutation == 'missing_initial':
                    initial = None
                elif mutation == 'after_initial':
                    rows.remove(command)
                    rows.remove(status)
                    rows.insert(rows.index(old_command), status)
                    rows.insert(rows.index(status), command)
                elif mutation == 'clock_after_release':
                    old_command['sim_time_ns'] = old_status['sim_time_ns'] = anchor['sim_time_ns'] = 205_000_000
                    old_status['status']['clock_ns'] = 205_000_000
                elif mutation == 'task_stale':
                    guards.append({'clock_ns': 205_000_000, 'decision_sequence': 3, 'line': 3,
                                   'output': [0., 0.], 'started': True})
                    rows.append(dict(command, cmd_seq=3, target_decision_sequence=3,
                                     target_clock_ns=205_000_000, sim_time_ns=400_000_000))
                    final = 400_000_000
                rows.sort(key=lambda row: row['sim_time_ns'])
                self.renumber(rows)
                if mutation.startswith('valid_'):
                    result = self.core(rows, guards, release=204_000_000, final=final, initial_receipt=initial)
                    self.assertEqual(len(result['pre_initial_storage_zero_prewarm_commands']), 1)
                    self.assertFalse(result['pre_initial_storage_zero_prewarm_commands'][0]['task_input_credit'])
                    self.assertFalse(result['pre_initial_storage_zero_prewarm_commands'][0]['sampled_response_credit'])
                    self.assertEqual(result['maximum_task_exact_guard_to_receive_ns'], 0)
                elif mutation == 'task_stale':
                    with self.assertRaisesRegex(ValueError, 'guard-to-drive target delay exceeds160ms'):
                        self.core(rows, guards, release=204_000_000, final=final, initial_receipt=initial)
                else:
                    with self.assertRaises(ValueError):
                        self.core(rows, guards, release=204_000_000, final=final, initial_receipt=initial)

    def test_legacy_twist_trace_cannot_supply_tagged_matrix_credit(self):
        for mutation in ('schema', 'mode', 'status_topic', 'compiled_target_contract_sha256'):
            with self.subTest(mutation=mutation):
                rows = copy.deepcopy(self.rows['tb1'])
                if mutation == 'schema':
                    rows[0]['schema'] = 'mr3-drive-actuation-v1'
                elif mutation == 'mode':
                    rows[0]['command_mode'] = 'twist'
                else:
                    rows[0][mutation] = 'wrong'
                with self.assertRaises(ValueError):
                    self.core(rows)

    def test_prerelease_rejection_retains_state_and_task_rejection_fails(self):
        for mutation in ('valid_prerelease', 'retained_identity', 'during_task'):
            with self.subTest(mutation=mutation):
                rows = copy.deepcopy(self.rows['tb1'])
                rejected = {'schema': 'mr3-drive-actuation-v2', 'epoch': EPOCH, 'robot': 'tb1',
                            'kind': 'target_rejected', 'reason': 'synthetic invalid target',
                            'raw_target': '{}', 'retained_cmd_seq': 0,
                            'retained_target_decision_sequence': 0, 'retained_target_clock_ns': 0,
                            'sim_time_ns': 1_000_000}
                if mutation == 'retained_identity':
                    rejected['retained_cmd_seq'] = 1
                elif mutation == 'during_task':
                    rejected['sim_time_ns'] = 101_000_000
                rows.append(rejected)
                rows.sort(key=lambda row: row['sim_time_ns'])
                self.renumber(rows)
                if mutation == 'valid_prerelease':
                    self.assertTrue(self.core(rows)['passed'])
                else:
                    with self.assertRaises(ValueError):
                        self.core(rows)

    def test_all_three_valid_and_no_world_body_credit(self):
        result = self.review()
        self.assertTrue(result['passed'])
        self.assertTrue(all(row['passed'] for row in result['episodes'][0]['robots'].values()))
        self.assertFalse(result['world_body_response_credit'])
        self.assertTrue(result['binary']['current_binary_verified'])

    def test_real_alignment_shape_is_continuous_and_release_is_an_actual_boundary(self):
        def row(start, end):
            return {'epoch': EPOCH, 'ok': True, 'paused': True, 'step_ns': 1_000_000,
                    'start_time_ns': start*1_000_000, 'end_time_ns': end*1_000_000,
                    'steps': end-start, 'start_iterations': start, 'end_iterations': end}
        alignment = [row(87, 87)] + [row(i, i+1) for i in range(87, 100)]
        records = alignment + [row(100, 120), row(120, 140)]
        self.assertEqual(M.physics_bounds(records, EPOCH, 100_000_000), (140_000_000, 1_000_000))
        for mutation in ('gap', 'rewind', 'iterations', 'cross_release'):
            with self.subTest(mutation=mutation):
                bad = copy.deepcopy(records)
                if mutation == 'gap':
                    bad.pop(3)
                elif mutation == 'rewind':
                    bad[3], bad[4] = bad[4], bad[3]
                elif mutation == 'iterations':
                    bad[-1]['start_iterations'] += 1
                    bad[-1]['end_iterations'] += 1
                else:
                    bad = alignment[:-1] + [row(99, 120)]
                with self.assertRaises(ValueError):
                    M.physics_bounds(bad, EPOCH, 100_000_000)

    def test_only_prerelease_duplicate_zero_guard_clocks_are_legal(self):
        def records(clock=20_000_000, output=None):
            return [{'schema': 'mr3-motion-safety-v1', 'epoch': EPOCH, 'kind': 'decision',
                     'record_sequence': index, 'payload': {'robot': 'tb1', 'clock_ns': clock,
                     'decision_sequence': index, 'decision': {'output': [0., 0.] if output is None else output}}}
                    for index in (1, 2)]
        self.assertEqual(len(M.guard_outputs(records(), EPOCH, 100_000_000)['tb1']), 2)
        for mutation in ('decision_sequence', 'record_sequence', 'nonzero', 'task', 'rewind'):
            with self.subTest(mutation=mutation):
                bad = records()
                if mutation in ('decision_sequence', 'record_sequence'):
                    target = bad[1]['payload'] if mutation == 'decision_sequence' else bad[1]
                    target[mutation] = 1
                elif mutation == 'nonzero':
                    bad = records(output=[.1, 0.])
                elif mutation == 'task':
                    bad = records(clock=100_000_000)
                else:
                    bad[1]['payload']['clock_ns'] -= 1_000_000
                with self.assertRaises(ValueError):
                    M.guard_outputs(bad, EPOCH, 100_000_000)
    def test_qos_one_can_skip_guard_publications_without_fabricating_ack(self):
        rows, guards = fixture('tb1', self.compiled, self.library,
                               command_times=[20_000_000, 60_000_000, 100_000_000, 140_000_000, 180_000_000])
        result = self.core(rows, guards)
        self.assertTrue(result['passed'])
        self.assertEqual(result['commands_received'], 5)
        self.assertEqual(len(guards), 10)

    def test_missing_one_robot_trace_fails_whole_episode(self):
        (self.directory/'drive_tb2.jsonl').unlink()
        result = self.review()
        self.assertFalse(result['passed'])
        self.assertFalse(result['episodes'][0]['robots']['tb2']['passed'])

    def test_epoch_record_sequence_clock_and_types_mutations(self):
        for field, value in [('epoch', 'wrong'), ('robot', 'tb2'), ('record_sequence', 500),
                             ('record_sequence', True), ('sim_time_ns', -1)]:
            with self.subTest(field=field, value=value):
                rows = copy.deepcopy(self.rows['tb1'])
                rows[1][field] = value
                with self.assertRaises(ValueError):
                    self.core(rows)

    def test_wrong_compiled_source_and_physical_configuration(self):
        for field, value in [('compiled_source_sha256', 'b'*64), ('wheel_order', ['left', 'right']),
                             ('wheel_separation_m', [.3]), ('wheel_diameter_m', [.07]),
                             ('max_acceleration_mps2', 2.), ('max_torque_nm', 21.),
                             ('update_rate_hz', 31.), ('num_wheel_pairs', 2), ('odometry_source', 0),
                             ('command_topic', '/tb2/cmd_vel')]:
            with self.subTest(field=field):
                rows = copy.deepcopy(self.rows['tb1']); rows[0][field] = value
                with self.assertRaisesRegex(ValueError, 'configuration'):
                    self.core(rows)

    def test_latest_received_sequence_and_value_not_a_synthetic_command(self):
        self.first_act()['cmd_seq'] = 0
        with self.assertRaisesRegex(ValueError, 'locked latest'):
            self.core()

    def test_missing_guard_source_and_future_guard_source_rejected(self):
        for guards in ([], [{**row, 'clock_ns': row['clock_ns']+300_000_000}
                            for row in self.guards['tb1']]):
            with self.subTest(guards=guards):
                with self.assertRaisesRegex(ValueError, 'exactly bind unique guard'):
                    self.core(guards=guards)

    def test_latest_received_command_cannot_be_held_stale_after_release(self):
        rows, guards = fixture('tb1', self.compiled, self.library, command_times=[20_000_000])
        with self.assertRaisesRegex(ValueError, 'received command missing/stale'):
            self.core(rows, guards)

    def test_first_dt_does_not_assume_configuration_clock_is_last_update(self):
        rows = copy.deepcopy(self.rows['tb1'])
        rows[0]['sim_time_ns'] = 1_000_000
        self.assertTrue(self.core(rows)['passed'])

    def test_delayed_first_prerelease_update_keeps_task_cadence_strict(self):
        rows = copy.deepcopy(self.rows['tb1'])
        rows[0]['sim_time_ns'] = 1_000_000
        rows = [row for row in rows if not (
            row['kind'] == 'actuation' and row['actuation_seq'] == 1)]
        for index, row in enumerate(rows, 1):
            row['record_sequence'] = index
            if row['kind'] == 'actuation':
                row['actuation_seq'] -= 1
                if row['actuation_seq'] == 1:
                    row['dt_ns'], row['dt_sec'] = 68_000_000, .068
                    budget = Fraction.from_float(row['dt_sec'])
                    desired = row['desired_rim_mps']
                    nominal = min(Fraction(1), budget/max(
                        Fraction.from_float(value) for value in desired))
                    alpha = float(nominal)
                    while (Fraction.from_float(alpha) > nominal or any(
                            Fraction.from_float(alpha*value) > budget for value in desired)):
                        alpha = math.nextafter(alpha, 0.)
                    row['alpha'] = alpha
                    row['applied_rim_mps'] = [alpha*value for value in desired]
        self.assertTrue(self.core(rows)['passed'])
        with self.assertRaisesRegex(ValueError, 'configured30Hz'):
            self.core(rows, release=60_000_000)

    def test_received_command_outside_limits_rejected(self):
        row = next(row for row in self.rows['tb1'] if row['kind'] == 'command_received')
        row['desired_w'] = .81
        with self.assertRaisesRegex(ValueError, 'outside limits'):
            self.core()

    def test_wrong_right_left_body_transform(self):
        self.first_act()['desired_rim_mps'].reverse()
        with self.assertRaisesRegex(ValueError, 'RIGHT/LEFT'):
            self.core()

    def test_common_fraction_and_nominal_fraction_required(self):
        self.first_act()['alpha'] = .5
        with self.assertRaisesRegex(ValueError, 'nominal fraction'):
            self.core()

    def test_applied_value_must_use_one_common_alpha(self):
        self.first_act()['applied_rim_mps'][1] += 1e-6
        with self.assertRaisesRegex(ValueError, 'common-alpha'):
            self.core()

    def test_one_binary64_ulp_over_budget_is_not_a_math_tolerance(self):
        self.first_act()['applied_rim_mps'][0] = math.nextafter(.034, math.inf)
        with self.assertRaisesRegex(ValueError, 'budget exceeded exactly'):
            self.core()

    def test_different_source_successor_dt_rejected(self):
        row = [r for r in self.rows['tb1'] if r['kind'] == 'actuation'][1]
        row['sim_time_ns'] += 1_000_000
        with self.assertRaisesRegex(ValueError, 'actual source successors'):
            self.core()

    def test_wrong_30hz_tick_dt_and_nonfinite_current_rejected(self):
        for mutate in ('dt', 'nonfinite'):
            with self.subTest(mutate=mutate):
                rows = copy.deepcopy(self.rows['tb1'])
                row = next(r for r in rows if r['kind'] == 'actuation')
                if mutate == 'dt':
                    row['dt_ns'], row['dt_sec'] = 50_000_000, .05
                else:
                    row['current_rim_mps'][0] = float('nan')
                with self.assertRaises(ValueError):
                    self.core(rows)

    def test_task_reset_rejected(self):
        row = self.rows['tb1'][-1]
        row.update(kind='reset', cmd_seq=10, target_reset=True, desired_v=0., desired_w=0.,
                   internal_instruction_rim_mps=[0., 0.])
        with self.assertRaisesRegex(ValueError, 'reset at/after release'):
            self.core()

    def test_terminal_near_prerelease_sample_no_response_credit(self):
        rows = [row for row in self.rows['tb1'] if row['sim_time_ns'] <= 100_000_000]
        result = self.core(rows, release=100_000_000, final=101_000_000, terminal=True)
        self.assertTrue(result['passed'])
        self.assertFalse(result['sampled_response_credit'])
        self.assertTrue(result['terminal_protocol_only_exception'])
        with self.assertRaisesRegex(ValueError, 'ordinary fixture lacks'):
            self.core(rows, release=100_000_000, final=101_000_000, terminal=False)
        with self.assertRaisesRegex(ValueError, 'coverage'):
            self.core(rows, release=100_000_000, final=250_000_000, terminal=True)

    def test_exact_terminal_fixture_dispatch(self):
        benchmark = {'freeze': FREEZE, 'terminal_probe': True, 'workers': 1,
                     'steps_per_episode': 4, 'schedule': [['open', 101], ['open', 101]]}
        steps = [{'info': {'dt': dt, 'reason': 'navigation_failure'},
                  'terminated': i == 3, 'truncated': False}
                 for i, dt in enumerate((1., 1., 1., .02))]
        self.assertTrue(M.terminal_fixture(benchmark, steps, FREEZE))
        benchmark['steps_per_episode'] = 20
        self.assertFalse(M.terminal_fixture(benchmark, steps, FREEZE))

    def test_effective_model_physics_and_epoch_mutations(self):
        for replacement in ((b'<mass>1.372</mass>', b'<mass>9</mass>'),
                            (EPOCH.encode(), b'wrong-epoch')):
            with self.subTest(replacement=replacement):
                p = self.directory/'drive_model_tb1.sdf'; original = p.read_bytes()
                p.write_bytes(original.replace(*replacement))
                self.assertFalse(self.review()['passed'])
                p.write_bytes(original)

    def test_wrong_binary_or_wrong_proof_compiled_source_rejected(self):
        for field in ('library_sha256', 'compiled_helper_sha256'):
            with self.subTest(field=field):
                original = self.proof[field]; self.proof[field] = '0'*64
                self.json_file(self.proof_path, self.proof)
                with self.assertRaises(ValueError):
                    self.review()
                self.proof[field] = original

    def test_gzip_logs_and_explicit_archived_binary_mode(self):
        p = self.directory/'drive_tb3.jsonl'
        p.with_suffix('.jsonl.gz').write_bytes(gzip.compress(p.read_bytes(), mtime=0)); p.unlink()
        archive = self.root/'binary.so.gz'
        archive.write_bytes(gzip.compress(self.library.read_bytes(), mtime=0))
        self.proof.update(archived_library_gzip='binary.so.gz',
                          archived_library_encoded_sha256=M.sha(archive.read_bytes()))
        self.json_file(self.proof_path, self.proof)
        self.library.write_bytes(b'changed current build')
        with self.assertRaisesRegex(ValueError, 'actual library SHA'):
            self.review()
        result = self.review(archived=True)
        self.assertTrue(result['passed'])
        self.assertFalse(result['binary']['current_binary_verified'])
        self.assertEqual(result['binary']['mode'], 'archived_binary_replay')

    def test_input_mutation_detected_at_end(self):
        original = M.Inputs.verify_unchanged
        def change_before_final_check(inputs):
            p = self.directory/'metadata.json'; p.write_bytes(p.read_bytes()+b' ')
            return original(inputs)
        with patch.object(M.Inputs, 'verify_unchanged', change_before_final_check):
            with self.assertRaisesRegex(ValueError, 'input changed during audit'):
                self.review()

    def test_selected_gzip_archive_restores_original_absolute_paths_from_manifest(self):
        archive = self.root/'binary.so.gz'
        archive.write_bytes(gzip.compress(self.library.read_bytes(), mtime=0))
        self.proof.update(archived_library_gzip='binary.so.gz',
                          archived_library_encoded_sha256=M.sha(archive.read_bytes()))
        self.json_file(self.proof_path, self.proof)
        packed = self.root/'selected'
        shutil.copytree(self.directory.parent.parent, packed)
        selected = packed/'worker0/episode001_open_101'
        model = selected/'drive_model_tb2.sdf'
        original = model.read_bytes()
        model.with_suffix('.sdf.gz').write_bytes(gzip.compress(original, mtime=0)); model.unlink()
        self.json_file(packed/'manifest.json', {'source': str(self.directory.parent.parent)})
        with patch.object(M, 'ROOT', self.root), patch.object(M, 'git_blob', side_effect=self.blob):
            result = M.review(selected, FREEZE, self.proof_path, archived=True)
            self.assertTrue(result['passed'])
            self.assertEqual(result['episodes'][0]['original_episode_directory'], str(self.directory))
            self.assertFalse(M.review(selected, FREEZE, self.proof_path, archived=False)['passed'])
        self.assertEqual(gzip.decompress(model.with_suffix('.sdf.gz').read_bytes()), original)
        self.json_file(packed/'manifest.json', {'source': str(self.root/'different-source')})
        with patch.object(M, 'ROOT', self.root), patch.object(M, 'git_blob', side_effect=self.blob):
            self.assertFalse(M.review(selected, FREEZE, self.proof_path, archived=True)['passed'])

    def test_actual_spawn_must_load_the_exact_effective_file(self):
        path = self.directory/'launch.log'
        path.write_text(path.read_text().replace('drive_model_tb1.sdf', 'other_model.sdf'))
        self.assertFalse(self.review()['passed'])


if __name__ == '__main__':
    unittest.main()
