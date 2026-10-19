"""CPU counterexamples for the exact gentle-turn deployment profile; no ROS calls."""
import copy
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from mr3_learning import audit_nav2_parameters as entry


ORIGINAL_SHA = '9eb963457a8dc8297e4686004ea08c7a06e1e0e9ede7cd795ba9505da9d8f701'
FUNCTION_SHA = {
    'decode_parameters': '3c7786ad5c5ff803fb5e81dd748ff4b13c81265fd5bc1c31303a12566a41d05b',
    'validate_parameters': 'dbd6d73cf3b5901c561406747875a154ce569ae181506677f7e96645dff3a2da',
    'validate_status': 'bdfb7a33a896ef9e40f0ff0a119e996f71d6a5fbecfa1f26754854c7014fb0f0',
    'collect': '0fffee9308fb51dff163b546b8f90dfc6c54dfda592fd8ff93f1b7bd28a0f25e',
}
DECLARED = {
    ('controller_server', 'FollowPath.rotate_to_heading_angular_vel'): (3, .3),
    ('controller_server', 'FollowPath.max_angular_accel'): (3, 1.),
    ('controller_server', 'FollowPath.max_vel_theta'): (3, .3),
    ('controller_server', 'FollowPath.acc_lim_theta'): (3, 1.),
    ('velocity_smoother', 'max_velocity'): (8, [.2, 0., .3]),
    ('velocity_smoother', 'min_velocity'): (8, [-.2, 0., -.3]),
    ('velocity_smoother', 'max_accel'): (8, [.5, 0., 1.]),
    ('behavior_server', 'max_rotational_vel'): (3, .3),
    ('behavior_server', 'min_rotational_vel'): (3, .15),
    ('behavior_server', 'rotational_acc_lim'): (3, 1.),
}
YAML_SHA = (
    '8854aac6fe3083aa1156072830358e9331f0e0a45144ab3df499f743a37c1b8a',
    '9c7a0f9c197c5b3eedc3567c0b70d4920a5ca8cc6057b5059f5c5844ab275386',
    '8794b037c1ef31f57c8d99ab05c57a646afe6653717c2f21100e00b6a5435fae',
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def yaml_relative(robot):
    return Path('ros2_ws/ros2-multi-robot-automap/src/multi_robot/params') / f'nav2_params_tb{robot}_0.yaml'


def responses(module, kind):
    return [{'name': name, 'type': item[0], 'value': copy.deepcopy(item[1])}
            for name, item in module.EXPECTED[kind].items()]


class ExactParameterProfile(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        for relative in (entry.LEGACY_RELATIVE, *(yaml_relative(n) for n in (1, 2, 3))):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((entry.WORKSPACE / relative).read_bytes())

    def original(self):
        path = self.root / entry.LEGACY_RELATIVE
        self.assertEqual(sha(path.read_bytes()), ORIGINAL_SHA)
        spec = importlib.util.spec_from_file_location('original_parameters_cpu_test', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_only_ten_typed_facts_change_and_all_original_functions_match(self):
        old = self.original()
        new, proof = entry.load_profile(self.root)
        self.assertEqual(set(new.EXPECTED), set(old.EXPECTED))
        actual_changes = {}
        for kind, original in old.EXPECTED.items():
            self.assertEqual(list(new.EXPECTED[kind]), list(original))
            for name, typed_value in original.items():
                observed = new.EXPECTED[kind][name]
                if observed != typed_value:
                    actual_changes[kind, name] = observed
                else:
                    self.assertEqual(observed, typed_value)
            new.validate_parameters(kind, responses(new, kind))
        self.assertEqual(actual_changes, DECLARED)
        self.assertEqual(new.EXPECTED['controller_server']['FollowPath.decel_lim_theta'], (3, -3.2))
        self.assertEqual(new.EXPECTED['velocity_smoother']['max_decel'], (8, [-.5, 0., -3.2]))
        self.assertEqual(proof['unchanged_function_sha256'], FUNCTION_SHA)
        for name, expected in FUNCTION_SHA.items():
            self.assertEqual(sha(inspect.getsource(getattr(new, name)).encode()), expected)
            self.assertEqual(sha(inspect.getsource(getattr(old, name)).encode()), expected)

    def test_typed_scalar_array_and_unchanged_deceleration_mismatches_fail(self):
        module, _ = entry.load_profile(self.root)
        cases = (
            ('controller_server', 'FollowPath.max_vel_theta', 'type', 2),
            ('controller_server', 'FollowPath.max_vel_theta', 'value', .8),
            ('velocity_smoother', 'max_velocity', 'type', 9),
            ('velocity_smoother', 'max_accel', 'value', [.5, 0., 3.2]),
            ('controller_server', 'FollowPath.decel_lim_theta', 'value', -1.),
            ('velocity_smoother', 'max_decel', 'value', [-.5, 0., -1.]),
        )
        for kind, name, field, wrong in cases:
            with self.subTest(kind=kind, name=name, field=field):
                rows = responses(module, kind)
                next(row for row in rows if row['name'] == name)[field] = wrong
                with self.assertRaisesRegex(ValueError, 'typed value differs'):
                    module.validate_parameters(kind, rows)
        for parameter in (SimpleNamespace(type=3, double_value=True),
                          SimpleNamespace(type=8, double_array_value=[.5, float('nan'), 1.])):
            with self.subTest(parameter=parameter), self.assertRaisesRegex(ValueError, 'nonfinite parameter'):
                module.decode_parameters(['bad'], [parameter])

    def test_original_same_epoch_exact_release_healthy_status_gate_is_retained(self):
        old = self.original()
        new, _ = entry.load_profile(self.root)
        status = {'schema': 'mr3-motion-safety-status-v1', 'epoch': 'cpu-epoch', 'clock_ns': 123,
                  'ready': True, 'completion_scope': 'publication_and_local_topic_receipt',
                  'decision_sequences': {'tb1': 1, 'tb2': 2, 'tb3': 3}}
        for module in (old, new):
            module.validate_status(status, 'cpu-epoch', 123)
            for field, wrong in (('epoch', 'stale'), ('clock_ns', 124), ('ready', False),
                                 ('completion_scope', 'published_only'),
                                 ('decision_sequences', {'tb1': 1, 'tb2': 2}),
                                 ('decision_sequences', {'tb1': 1, 'tb2': 2, 'tb3': True})):
                with self.subTest(module=module.PROFILE, field=field, wrong=wrong):
                    bad = copy.deepcopy(status)
                    bad[field] = wrong
                    with self.assertRaisesRegex(ValueError, 'same-epoch exact healthy reset-release'):
                        module.validate_status(bad, 'cpu-epoch', 123)

    def test_fresh_private_modules_cannot_contaminate_other_loads_or_original(self):
        first, _ = entry.load_profile(self.root)
        second, _ = entry.load_profile(self.root)
        self.assertIsNot(first, second)
        self.assertIsNot(first.validate_parameters.__globals__, second.validate_parameters.__globals__)
        first.EXPECTED['velocity_smoother']['max_velocity'][1][2] = 99.
        first.EXPECTED['controller_server']['FollowPath.max_vel_theta'] = (3, 99.)
        third, _ = entry.load_profile(self.root)
        for module in (second, third):
            self.assertEqual(module.EXPECTED['velocity_smoother']['max_velocity'], (8, [.2, 0., .3]))
            self.assertEqual(module.EXPECTED['controller_server']['FollowPath.max_vel_theta'], (3, .3))
        self.assertEqual(self.original().EXPECTED['velocity_smoother']['max_velocity'], (8, [.2, 0., .8]))

    def test_all_three_exact_thirteen_line_yaml_inverses_reject_extra_or_missing_edits(self):
        bindings = entry.yaml_bindings(self.root)
        self.assertEqual([row['inverse_original_sha256'] for row in bindings], list(YAML_SHA))
        self.assertEqual([row['changed_lines'] for row in bindings], [13, 13, 13])
        self.assertTrue(all(row['exact_inverse'] for row in bindings))
        for robot, binding in enumerate(bindings, 1):
            path = self.root / yaml_relative(robot)
            original = path.read_bytes()
            self.assertEqual(binding['sha256'], sha(original))
            self.assertEqual(binding['bytes'], len(original))
            self.assertNotEqual(binding['sha256'], binding['inverse_original_sha256'])
            for invalid in (original + b'\n# undeclared extra source byte\n',
                            original.replace(b'rotate_to_heading_angular_vel: 0.3',
                                             b'rotate_to_heading_angular_vel: 0.8')):
                with self.subTest(robot=robot, invalid_sha=sha(invalid)):
                    path.write_bytes(invalid)
                    with self.assertRaisesRegex(ValueError, 'YAML'):
                        entry.yaml_bindings(self.root)
            path.write_bytes(original)

    def test_wrong_immutable_helper_sha_is_rejected_before_execution(self):
        path = self.root / entry.LEGACY_RELATIVE
        path.write_bytes(path.read_bytes() + b'\nraise RuntimeError("must never execute")\n')
        with self.assertRaisesRegex(ValueError, 'immutable nine-node parameter reader differs'):
            entry.load_profile(self.root)

    def test_provenance_identifies_actual_entry_original_reader_and_complete_profile(self):
        module, proof = entry.load_profile(self.root)
        actual_entry = Path(entry.__file__).resolve()
        self.assertEqual(proof['effective_entry'], {'path': str(actual_entry), 'sha256': sha(actual_entry.read_bytes())})
        self.assertEqual(proof['immutable_reader'], {'path': str(entry.LEGACY_RELATIVE), 'sha256': ORIGINAL_SHA})
        definition = proof['profile_definition']
        self.assertEqual(definition['selection'], 'gentle_turn_v1')
        self.assertEqual(definition['profile'], 'mr3-nav2-shim-dwb-030-a1-v1')
        self.assertEqual(definition['expected_typed_parameters'], module.EXPECTED)
        self.assertEqual(len(definition['changed_typed_facts']), 10)
        self.assertEqual({(row['node_kind'], row['name']): (row['type'], row['new'])
                          for row in definition['changed_typed_facts']}, DECLARED)
        raw = json.dumps(definition, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        self.assertEqual(proof['profile_sha256'], sha(raw))
        self.assertEqual(proof['yaml_sources'], entry.yaml_bindings(self.root))
        self.assertEqual(set(module.EXPECTED), {'controller_server', 'velocity_smoother', 'behavior_server'})
        self.assertIn('recoveries_server', proof['scope'])


if __name__ == '__main__':
    unittest.main()
