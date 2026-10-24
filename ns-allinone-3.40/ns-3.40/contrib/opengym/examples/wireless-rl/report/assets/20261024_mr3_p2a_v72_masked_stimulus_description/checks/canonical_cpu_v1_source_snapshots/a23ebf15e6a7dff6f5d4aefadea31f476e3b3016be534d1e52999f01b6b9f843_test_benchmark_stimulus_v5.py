"""CPU only: pure isolated namespaces, old-equivalence and original snapshots."""
from pathlib import Path
import unittest
import ast
import hashlib
import inspect

from mr3_learning import benchmark
from mr3_learning.tests.test_benchmark_stimulus_v4 import (
    LEGACY_AST_SHA256, snapshot, result,
)

ROOT = next(parent for parent in Path(__file__).resolve().parents if (parent / ".git").exists())
SELECTORS = {'_probe_goal_order', 'probe_action', 'probe_action_v3', 'probe_action_v4',
             'probe_action_v5', '_probe_nonapproaching_goal_action', 'record_probe_v4_submission'}
NEW = {name: getattr(benchmark, name) for name in SELECTORS}


def prepared_second(selector='probe_action_v5'):
    diagnostics = {}
    first = snapshot(10., active=False)
    action = NEW[selector](first, diagnostics)
    NEW['record_probe_v4_submission'](diagnostics, result(first, action))
    start = snapshot(13., active=False)
    action = NEW[selector](start, diagnostics)
    NEW['record_probe_v4_submission'](diagnostics, result(start, action))
    return diagnostics


class StimulusV5Tests(unittest.TestCase):
    def test_v2_v3_and_submission_functions_ast_unchanged(self):
        expected = dict(LEGACY_AST_SHA256, record_probe_v4_submission='e79fb1a7deec5b5b579902d58d42dbe815f4d2d6b5e750a608e9feaff15bddaa')
        for name, value in expected.items():
            node = ast.parse(inspect.getsource(getattr(benchmark, name))).body[0]
            self.assertEqual(hashlib.sha256(ast.dump(node).encode()).hexdigest(), value)

    def test_toward_goal_is_filtered_and_v4_default_still_selects_it(self):
        snap = snapshot(0., active=False)
        snap['candidates'][0].update(x=0., y=1.)
        snap['joint_action_mask'] = [index in (88, 888) for index in range(1000)]
        self.assertEqual(NEW['probe_action_v4'](snap, {}), 88)
        self.assertEqual(NEW['probe_action_v5'](snap, {}), 888)

    def test_nonapproach_subset_allows_two_goal_opportunity(self):
        snap = snapshot(0., active=False)
        for index, xy in enumerate(((0., 1.), (2., 0.), (2., 2.), (2., 4.))):
            snap['candidates'][index].update(x=xy[0], y=xy[1])
        snap['joint_action_mask'] = [index in (111, 128, 888) for index in range(1000)]
        self.assertEqual(NEW['probe_action_v4'](snap, {}), 111)
        diagnostics = {}
        self.assertEqual(NEW['probe_action_v5'](snap, diagnostics), 128)
        entry = diagnostics['goal_decisions'][-1]
        self.assertEqual(entry['max_legal_goal_components'], 2)
        self.assertEqual(entry['original_joint_allowed_actions'], 3)
        self.assertEqual(entry['filtered_stimulus_allowed_actions'], 2)
        self.assertEqual(entry['new_goal_filter'], 'received_straight_nonapproach_v1')
        self.assertIn('not actor interface availability', entry['scope'])

    def test_zero_margin_is_allowed_and_negative_not_rounded_up(self):
        snap = snapshot(0., active=False)
        snap['candidates'][0].update(x=2., y=0.)
        self.assertTrue(NEW['_probe_nonapproaching_goal_action'](snap, 88))
        snap['candidates'][0]['y'] = 1e-15
        self.assertFalse(NEW['_probe_nonapproaching_goal_action'](snap, 88))

    def test_unknown_stale_invalid_or_nonfinite_peer_disables_new_goal_only(self):
        for key, value in (('fresh', False), ('valid', False), ('x', float('nan')),
                           ('y', True), ('x', float('inf'))):
            with self.subTest(key=key, value=value):
                snap = snapshot(0., active=False)
                snap['robots'][2][key] = value
                snap['joint_action_mask'] = [index in (88, 888, 999) for index in range(1000)]
                self.assertFalse(NEW['_probe_nonapproaching_goal_action'](snap, 88))
                self.assertTrue(NEW['_probe_nonapproaching_goal_action'](snap, 888))
                self.assertTrue(NEW['_probe_nonapproaching_goal_action'](snap, 999))
                self.assertEqual(NEW['probe_action_v5'](snap, {}), 888)

    def test_nonfinite_goal_zero_length_and_coincident_peer_rejected(self):
        for fault in ('nan', 'bool', 'zero_length', 'coincident_peer'):
            snap = snapshot(0., active=False)
            if fault == 'nan':
                snap['candidates'][0]['x'] = float('nan')
            elif fault == 'bool':
                snap['candidates'][0]['x'] = True
            elif fault == 'zero_length':
                snap['candidates'][0].update(x=snap['robots'][0]['x'], y=snap['robots'][0]['y'])
            else:
                snap['robots'][1].update(x=snap['robots'][0]['x'], y=snap['robots'][0]['y'])
            with self.subTest(fault=fault):
                self.assertFalse(NEW['_probe_nonapproaching_goal_action'](snap, 88))

    def test_finite_input_overflow_cannot_hide_invalid_peer_pair(self):
        cases = (
            ((0., 0.), (1e308, 0.), (0., 1.), (-1e308, 0.)),
            ((0., 0.), (1e308, 0.), (1e308, 0.), (0., 1.)),
            ((0., 0.), (1e-300, 0.), (-1e-300, 0.), (0., 1.)),
            ((1e308, 0.), (-1e308, 0.), (0., 1.), (0., -1.)),
            ((0., 0.), (10 ** 400, 0.), (0., 1.), (-1., 0.)),
        )
        for own, goal, peer2, peer3 in cases:
            with self.subTest(own=own, goal=goal):
                snap = snapshot(0., active=False)
                for robot, xy in zip(snap['robots'], (own, peer2, peer3)):
                    robot.update(x=xy[0], y=xy[1])
                snap['candidates'][0].update(x=goal[0], y=goal[1])
                self.assertFalse(NEW['_probe_nonapproaching_goal_action'](snap, 88))

    def test_false_joint_goal_and_five_second_wait_masks_never_overridden(self):
        snap = snapshot(0., active=False)
        snap['joint_action_mask'] = [index == 888 for index in range(1000)]
        self.assertEqual(NEW['probe_action_v5'](snap, {}), 888)
        diagnostics = prepared_second()
        snap = snapshot(15., speed=.2, path=.4, waiting=False)
        self.assertEqual(NEW['probe_action_v5'](snap, diagnostics), 888)
        NEW['record_probe_v4_submission'](diagnostics, result(snap, 888))
        self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])

    def test_explicit_false_flag_does_not_latch_and_wrong_types_fail(self):
        for flag in (False, 0, None):
            diagnostics = prepared_second()
            snap = snapshot(19., speed=.2, path=1.)
            action = NEW['probe_action_v5'](snap, diagnostics)
            self.assertEqual(action, 999)
            if flag is False:
                receipt = result(snap, action, action_submitted=flag)
                NEW['record_probe_v4_submission'](diagnostics, receipt)
            else:
                with self.assertRaises(ValueError):
                    receipt = result(snap, action, action_submitted=flag)
                    NEW['record_probe_v4_submission'](diagnostics, receipt)
            self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])

    def test_three_second_hold_and_initial_wait_are_still_required(self):
        self.assertEqual(NEW['probe_action_v5'](snapshot(13., active=False), {}), 888)
        diagnostics = {}
        first = snapshot(11., active=False)
        action = NEW['probe_action_v5'](first, diagnostics)
        NEW['record_probe_v4_submission'](diagnostics, result(first, action))
        early = snapshot(13., active=False)
        action = NEW['probe_action_v5'](early, diagnostics)
        self.assertEqual(action, 888)
        NEW['record_probe_v4_submission'](diagnostics, result(early, action))
        ready = snapshot(14., active=False)
        self.assertNotEqual(NEW['probe_action_v5'](ready, diagnostics), 888)

    def test_no_global_monkeypatch_and_two_versions_are_independent(self):
        old_state, new_state = {}, {}
        snap = snapshot(0., active=False)
        snap['candidates'][0].update(x=0., y=1.)
        snap['joint_action_mask'] = [index in (88, 888) for index in range(1000)]
        before = dict(NEW)
        a = NEW['probe_action_v4'](snap, old_state)
        b = NEW['probe_action_v5'](snap, new_state)
        self.assertEqual((a, b), (88, 888))
        self.assertEqual(before, NEW)
        self.assertNotIn('new_goal_filter', old_state['v4_stimulus']['pending_submission'])
        self.assertEqual(new_state['v4_stimulus']['pending_submission']['new_goal_filter'],
                         'received_straight_nonapproach_v1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
