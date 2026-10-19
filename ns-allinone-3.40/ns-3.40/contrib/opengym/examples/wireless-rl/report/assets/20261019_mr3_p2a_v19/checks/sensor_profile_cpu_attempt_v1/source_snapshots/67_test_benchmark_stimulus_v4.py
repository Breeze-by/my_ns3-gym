"""CPU-only received-snapshot selectors and immutable physics-method fixtures."""
import ast
import importlib.util
import itertools
import hashlib
import inspect
from pathlib import Path
import unittest

from mr3_learning import benchmark

BASE = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
WIRELESS = BASE / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
PHYSICS = (WIRELESS / 'report/assets/20261017_mr3_p2a0_v3/independent/'
           'mr3_independent_physics_review.py')
NAMES = ('tb1', 'tb2', 'tb3')
choose = benchmark.probe_action_v4
submit = benchmark.record_probe_v4_submission
LEGACY_AST_SHA256 = {'_probe_goal_order': 'a454a4021c8b969b21fa76d85a00b35fb4a661adef8f12b2515aaf1cbbccd5b2', 'probe_action': 'f8a58cee4dfc005f962236d6f9f667c0971dc6a5097ea265774b7a15f8acbe57', 'probe_action_v3': '1501380795c46c32d02995506e1ca1605a77b6647130b57ba23ba5386b28d1e5'}


def snapshot(t, *, speed=0., path=0., active=True, waiting=True):
    robots = []
    for index, name in enumerate(NAMES):
        robots.append({'name': name, 'x': 0., 'y': index * 2., 'yaw': 0.,
                       'epoch': 'fixture', 'fresh': True, 'valid': True, 'v': speed, 'w': 0.,
                       'source_stamp': t + 1., 'odom_source_stamp': t + 1.,
                       'activity': {'estimated_path_m': path, 'path_observation_complete': True},
                       'navigation': {'phase': 'active' if active else 'idle', 'owned': active,
                                      'goal_id': 'goal-' + name if active else None,
                                      'accepted_goal_count': 1 if active else 0}})
    per = [[True] * 10 for _ in NAMES]
    if not waiting:
        per = [[False] * 8 + [True, False] for _ in NAMES]
    joint = [all(per[i][value] for i, value in enumerate(choices))
             for choices in itertools.product(range(10), repeat=3)]
    return {'epoch': 'fixture', 'sequence': int(t * 10) + 1, 'digest': 'fixture-' + str(t),
            'task_elapsed_sec': t, 'robots': robots, 'per_robot_action_mask': per,
            'joint_action_mask': joint,
            'candidates': [{'x': 2. + i * .5, 'y': float(i),
                            'path_distances_m': [2. + i] * 3} for i in range(8)]}


def result(snap, action, **extra):
    return {'epoch': snap['epoch'], 'command': {
        'epoch': snap['epoch'], 'observation_sequence': snap['sequence'],
        'observation_digest': snap['digest'], 'action': action, 'command_id': snap['sequence']},
        **extra}


class StimulusTests(unittest.TestCase):
    def second_round(self):
        diagnostics = {}
        first = snapshot(10., active=False)
        first_action = choose(first, diagnostics)
        submit(diagnostics, result(first, first_action))
        snap = snapshot(13., active=False)
        action = choose(snap, diagnostics)
        submit(diagnostics, result(snap, action))
        return diagnostics

    def test_old_v2_v3_functions_unchanged(self):
        for name, expected in LEGACY_AST_SHA256.items():
            node = ast.parse(inspect.getsource(getattr(benchmark, name))).body[0]
            self.assertEqual(hashlib.sha256(ast.dump(node).encode()).hexdigest(), expected)

    def test_masked_wait_never_triggers_or_latches_during_commitment(self):
        diagnostics = self.second_round()
        snap = snapshot(15., speed=.19, path=.4, waiting=False)
        self.assertEqual(choose(snap, diagnostics), 888)
        self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])
        submit(diagnostics, result(snap, 888))
        self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])

    def test_legal_moving_wait_latches_only_after_actual_submission(self):
        diagnostics = self.second_round()
        snap = snapshot(19., speed=.19, path=.5)
        self.assertEqual(choose(snap, diagnostics), 999)
        self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])
        submit(diagnostics, result(snap, 999))
        self.assertEqual(set(diagnostics['v4_stimulus']['rounds']['second']['waits']), set(NAMES))
        after = snapshot(20., active=False)
        self.assertEqual(choose(after, diagnostics), 999)

    def test_not_submitted_and_exception_do_not_latch(self):
        diagnostics = self.second_round()
        snap = snapshot(19., speed=.19, path=.5)
        choose(snap, diagnostics)
        submit(diagnostics, {'action_submitted': False})
        self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])
        choose(snapshot(20., speed=.19, path=.6), diagnostics)
        self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])
        with self.assertRaisesRegex(ValueError, 'unresolved'):
            choose(snapshot(21.), diagnostics)

    def test_explicit_nonbool_submission_flags_never_latch(self):
        for flag in (0, 1, None, "true"):
            with self.subTest(flag=flag):
                diagnostics = self.second_round()
                snap = snapshot(19., speed=.19, path=.5)
                choose(snap, diagnostics)
                with self.assertRaisesRegex(ValueError, "must be bool"):
                    submit(diagnostics, result(snap, 999, action_submitted=flag))
                self.assertFalse(diagnostics["v4_stimulus"]["rounds"]["second"]["waits"])

    def test_second_goal_without_submitted_first_wait_is_missing(self):
        diagnostics = {}
        snap = snapshot(13., active=False)
        self.assertEqual(choose(snap, diagnostics), 888)
        self.assertFalse(diagnostics["v4_stimulus"]["rounds"]["second"]["waits"])

    def test_wrong_or_untyped_returned_command_never_latches(self):
        for key, value in (('action', 998), ('epoch', 'wrong'),
                           ('observation_digest', 'wrong'), ('observation_sequence', False),
                           ('command_id', False)):
            with self.subTest(key=key):
                diagnostics = self.second_round()
                snap = snapshot(19., speed=.19, path=.5)
                choose(snap, diagnostics)
                receipt = result(snap, 999)
                receipt['command'][key] = value
                with self.assertRaises(ValueError):
                    submit(diagnostics, receipt)
                self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])

    def test_stale_nonfinite_incomplete_or_inactive_is_not_motion_trigger(self):
        mutations = (('fresh', False), ('valid', False), ('v', float('nan')),
                     ('v', True), ('v', .079), ('navigation', {'phase': 'idle'}),
                     ('activity', {'estimated_path_m': .5, 'path_observation_complete': False}))
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                diagnostics = self.second_round()
                snap = snapshot(19., speed=.19, path=.5)
                for robot in snap['robots']:
                    robot[key] = value
                self.assertEqual(choose(snap, diagnostics), 888)

    def test_single_robot_wait_and_joint_mask_are_respected(self):
        diagnostics = self.second_round()
        snap = snapshot(19., speed=0., path=.5)
        snap['robots'][1]['v'] = .19
        self.assertEqual(choose(snap, diagnostics), 898)
        self.assertTrue(snap['joint_action_mask'][898])

    def test_deadline_is_finite_and_missing_motion_is_recorded(self):
        diagnostics = {}
        snap = snapshot(10., speed=.02, path=.01)
        self.assertEqual(choose(snap, diagnostics), 999)
        pending = diagnostics['v4_stimulus']['pending_submission']
        self.assertEqual(pending['received_motion_robots'], [])
        self.assertEqual(set(pending['reasons'].values()), {'bounded_deadline'})
        submit(diagnostics, result(snap, 999))
        self.assertEqual(choose(snapshot(12., active=False), diagnostics), 999)

    def test_second_opportunity_waits_for_three_seconds_and_received_rest(self):
        diagnostics = {}
        first = snapshot(11., speed=.02)
        action = choose(first, diagnostics)
        submit(diagnostics, result(first, action))
        early = snapshot(13., active=False)
        self.assertEqual(choose(early, diagnostics), 888)
        submit(diagnostics, result(early, 888))
        not_rest = snapshot(14., speed=.02, active=False)
        self.assertEqual(choose(not_rest, diagnostics), 888)
        submit(diagnostics, result(not_rest, 888))
        # A separate legal fixture reaches three seconds with received rest in the goal window.
        diagnostics = {}
        action = choose(first, diagnostics)
        submit(diagnostics, result(first, action))
        ready = snapshot(14., active=False)
        chosen = choose(ready, diagnostics)
        choices = (chosen // 100, chosen // 10 % 10, chosen % 10)
        self.assertEqual(sum(choice < 8 for choice in choices), 3)

    def test_mask_contradiction_is_rejected_not_forced(self):
        diagnostics = self.second_round()
        snap = snapshot(19., speed=.19, path=.5)
        snap['joint_action_mask'] = [False] * 1000
        snap['joint_action_mask'][888] = True
        with self.assertRaisesRegex(ValueError, 'no legal joint'):
            choose(snap, diagnostics)
        self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])

    def test_original_physics_equations_credit_sustained_zero_and_reject_resume(self):
        spec = importlib.util.spec_from_file_location('immutable_physics', PHYSICS)
        physics = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(physics)
        samples = []
        for index in range(21):
            speed = .12 if index <= 5 else .06 if index == 6 else 0.
            samples.append({'source_ns': index * 100000000, 'xy': [min(index, 7) * .006, 0.],
                            'planar_speed': speed, 'angular_norm': 0., 'abs_wz': 0.,
                            'frames': ['odom', 'base_footprint']})
        commands = [{'clock_ns': 0, 'v': .12, 'w': 0.},
                    {'clock_ns': 520000000, 'v': 0., 'w': 0.}]
        cancels = [{'clock_ns': 500000000, 'goal_id': 'synthetic',
                    'new_goal_clock_ns': 10**30, 'completion_evidence': [{'synthetic': True}]}]
        accepted = physics.robot_physics(samples, commands, 0, 2000000000, cancels)
        self.assertTrue(accepted['hard_zero_evidence_complete'])
        self.assertTrue(accepted['cancel_end_to_end_evidence_complete'])
        resumed = physics.robot_physics(samples, commands + [
            {'clock_ns': 600000000, 'v': .12, 'w': 0.}], 0, 2000000000, cancels)
        self.assertFalse(resumed['physical_evidence_complete'])
        self.assertEqual(resumed['stop_responses'][0]['status'], 'resumed_before_proven_rest')


if __name__ == '__main__':
    unittest.main(verbosity=2)
