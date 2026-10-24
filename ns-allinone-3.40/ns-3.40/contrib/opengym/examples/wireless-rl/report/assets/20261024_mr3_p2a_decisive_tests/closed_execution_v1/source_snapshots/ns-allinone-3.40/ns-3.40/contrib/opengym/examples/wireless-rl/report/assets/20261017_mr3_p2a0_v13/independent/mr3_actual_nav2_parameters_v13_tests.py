"""CPU-only actual-profile and typed readback checks; no native execution credit."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from types import SimpleNamespace
import yaml

ROOT = Path('/home/zhuyulab/ns3-workspace')
OUT = Path(__file__).resolve().parent
MANIFEST = {'base_freeze': '6b1b4a0108351f5bfb70ec0c96ba895248d4f7a8',
            'readback_source_sha256': 'fe0a91eec1aaf6d45bc3aedd4de9223b53e77721be878136a96d02ef1bd5c0ae'}
SPEC = importlib.util.spec_from_file_location('actual_profile_readback', OUT / 'mr3_actual_nav2_parameters_v13.py')
READBACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(READBACK)


def get_parameter(config, name):
    if name in config:
        return config[name]
    first, remaining = name.split('.', 1)
    return get_parameter(config[first], remaining)


def old_and_new(robot):
    path = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/params/nav2_params_' + robot + '_0.yaml'
    old = subprocess.check_output(['git', 'show', MANIFEST['base_freeze'] + ':' + path], cwd=ROOT)
    new = (ROOT / path).read_bytes()
    return yaml.safe_load(old), yaml.safe_load(new)


def typed_rows(kind):
    return [{'name': name, 'type': type_id, 'type_field': READBACK.TYPE_FIELDS[type_id],
             'value': copy.deepcopy(value)} for name, (type_id, value) in READBACK.EXPECTED[kind].items()]


class ProfileTests(unittest.TestCase):
    def test_exact_only_declared_yaml_changes_all_three(self):
        for robot in ('tb1', 'tb2', 'tb3'):
            old, new = old_and_new(robot)
            baseline = copy.deepcopy(old)
            controller = baseline['controller_server']['ros__parameters']['FollowPath']
            controller.update(plugin='nav2_rotation_shim_controller::RotationShimController',
                primary_controller='dwb_core::DWBLocalPlanner', angular_dist_threshold=.5,
                angular_disengage_threshold=.5, forward_sampling_distance=.3,
                rotate_to_heading_angular_vel=.8, max_angular_accel=3.2,
                simulate_ahead_time=1., rotate_to_goal_heading=False, closed_loop=True,
                max_vel_x=.2, max_speed_xy=.2, acc_lim_x=.5, decel_lim_x=-.5)
            smoother = baseline['velocity_smoother']['ros__parameters']
            smoother.update(max_velocity=[.2, 0., .8], min_velocity=[-.2, 0., -.8],
                max_accel=[.5, 0., 3.2], max_decel=[-.5, 0., -3.2])
            self.assertEqual(new, baseline)

    def test_generic_config_retains_dwb_and_only_changes_declared_command_profile(self):
        path = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/nav2_params.yaml'
        old = yaml.safe_load(subprocess.check_output(
            ['git', 'show', MANIFEST['base_freeze'] + ':' + path], cwd=ROOT))
        new = yaml.safe_load((ROOT / path).read_bytes())
        expected = copy.deepcopy(old)
        controller = expected['controller_server']['ros__parameters']['FollowPath']
        controller.update(max_vel_x=.2, max_speed_xy=.2, acc_lim_x=.5, decel_lim_x=-.5)
        expected['velocity_smoother']['ros__parameters'].update(
            max_velocity=[.2, 0., .8], min_velocity=[-.2, 0., -.8],
            max_accel=[.5, 0., 3.2], max_decel=[-.5, 0., -3.2])
        self.assertEqual(new, expected)
        self.assertEqual(controller['plugin'], 'dwb_core::DWBLocalPlanner')
        self.assertNotIn('primary_controller', controller)

    def test_all_actual9_expected_values_match_each_draft(self):
        for robot in ('tb1', 'tb2', 'tb3'):
            _, new = old_and_new(robot)
            for kind, expected in READBACK.EXPECTED.items():
                config = new[kind]['ros__parameters']
                for name, (_, value) in expected.items():
                    self.assertEqual(get_parameter(config, name), value, (robot, kind, name))
                READBACK.validate_parameters(kind, typed_rows(kind))

    def test_old_cap_default_shim_and_critic_mutations_fail(self):
        for name, mutation in [('FollowPath.max_vel_x', .26),
                ('FollowPath.rotate_to_heading_angular_vel', 1.8),
                ('FollowPath.forward_sampling_distance', .5),
                ('FollowPath.angular_dist_threshold', .785),
                ('FollowPath.primary_controller', 'another/controller'),
                ('FollowPath.acc_lim_x', 2.5),
                ('FollowPath.GoalAlign.scale', 23.),
                ('FollowPath.critics', ['PathDist'])]:
            rows = typed_rows('controller_server')
            next(row for row in rows if row['name'] == name)['value'] = mutation
            with self.assertRaises(ValueError, msg=name):
                READBACK.validate_parameters('controller_server', rows)

    def test_missing_field_or_wrong_parameter_type_fails(self):
        rows = typed_rows('controller_server')
        with self.assertRaises(ValueError):
            READBACK.validate_parameters('controller_server', rows[:-1])
        rows[0]['type'] = 4
        with self.assertRaises(ValueError):
            READBACK.validate_parameters('controller_server', rows)

    def test_smoother_acceleration_and_angular_caps_mutations_fail(self):
        for name, mutation in [('max_accel', [2.5, 0., 3.2]),
                ('max_decel', [-2.5, 0., -3.2]), ('max_velocity', [.2, 0., 1.8]),
                ('feedback', 'CLOSED_LOOP')]:
            rows = typed_rows('velocity_smoother')
            next(row for row in rows if row['name'] == name)['value'] = mutation
            with self.assertRaises(ValueError, msg=name):
                READBACK.validate_parameters('velocity_smoother', rows)

    def test_string_array_readback_decode_and_nonstring_rejection(self):
        self.assertEqual(READBACK.decode_parameters(['controller_plugins'],
            [SimpleNamespace(type=9, string_array_value=['FollowPath'])])[0]['value'], ['FollowPath'])
        with self.assertRaises(ValueError):
            READBACK.decode_parameters(['controller_plugins'],
                [SimpleNamespace(type=9, string_array_value=[False])])

    def test_no_readback_rpc_or_time_scope_changes(self):
        original = ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
            'report/assets/20261017_mr3_p2a0_v4/independent/mr3_actual_nav2_parameters_v4.py')
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), MANIFEST['readback_source_sha256'])
        old = original.read_text()
        new = (OUT / 'mr3_actual_nav2_parameters_v13.py').read_text()
        def function(text, name, end):
            return text[text.index('def ' + name):text.index(end, text.index('def ' + name))]
        self.assertEqual(function(old, 'validate_status', '\n\ndef collect'),
                         function(new, 'validate_status', '\n\ndef collect'))
        old_collect = function(old, 'collect', '\n\ndef main')
        self.assertEqual(old_collect.replace('Node("mr3_actual_nav2_parameters",',
                                             'Node("mr3_actual_nav2_parameters_v13",'),
                         function(new, 'collect', '\n\ndef main'))

    def test_declared_speed_is_not_misrepresented_as_plugin_absolute_bound(self):
        target, actual_w, accel, dt = .8, 1.2, 3.2, .1
        command = max(actual_w - accel * dt, min(target, actual_w + accel * dt))
        self.assertGreater(command, target)
        self.assertAlmostEqual(command, .88)
        # This is the official algorithm arithmetic, not an actual native observation.


if __name__ == '__main__':
    unittest.main(verbosity=2)
