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
    'drive_audit', Path(__file__).with_name('mr3_independent_drive_trace_v2.py'))
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
              'command_topic': f'/{name}/cmd_vel', **compiled, 'sim_time_ns': 0}
    rows = [config]
    for sequence, stamp in enumerate(command_times, 1):
        rows.append({'kind': 'command_received', 'cmd_seq': sequence, 'desired_v': .1,
                     'desired_w': .2, 'sim_time_ns': stamp})
    for sequence, stamp in enumerate(range(34_000_000, 205_000_000, 34_000_000), 1):
        command_sequence = sum(clock <= stamp for clock in command_times)
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
    rows.sort(key=lambda row: row['sim_time_ns'])
    for index, row in enumerate(rows, 1):
        row.update(schema='mr3-drive-actuation-v1', epoch=EPOCH, robot=name, record_sequence=index)
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
                                                   b'</plugin>', b'<mr3_audit_path/><mr3_epoch/></plugin>')
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
        self.lines_file(self.directory/'physics.jsonl', [
            {'epoch': EPOCH, 'step_ns': 1_000_000, 'start_time_ns': 100_000_000,
             'end_time_ns': 204_000_000, 'steps': 104, 'start_iterations': 100,
             'end_iterations': 204, 'ok': True, 'paused': True}])
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

    def core(self, rows=None, guards=None, release=100_000_000, final=204_000_000, terminal=False):
        return M.robot_audit(self.rows['tb1'] if rows is None else rows,
                             self.guards['tb1'] if guards is None else guards,
                             'tb1', EPOCH, release, final, 1_000_000, self.compiled,
                             self.binary, terminal)

    def first_act(self):
        return next(row for row in self.rows['tb1'] if row['kind'] == 'actuation')

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
                with self.assertRaisesRegex(ValueError, 'ordered final-guard'):
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
