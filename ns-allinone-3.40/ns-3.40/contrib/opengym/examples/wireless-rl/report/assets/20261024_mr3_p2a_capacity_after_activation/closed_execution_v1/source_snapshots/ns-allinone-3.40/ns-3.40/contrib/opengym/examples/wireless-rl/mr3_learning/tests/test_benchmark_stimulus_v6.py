"""Pure CPU fixtures: late opportunity preserves source, masks and submitted WAIT contract."""
import ast
import copy
import hashlib
import inspect
import json
import math
import unittest

from mr3_learning import benchmark
from mr3_learning.tests.test_benchmark_stimulus_v4 import LEGACY_AST_SHA256, snapshot, result

choose = benchmark.probe_action_v6
submit = benchmark.record_probe_v4_submission


def after_first_wait(time=10.):
    diagnostics = {}
    snap = snapshot(time, active=False)
    action = choose(snap, diagnostics)
    submit(diagnostics, result(snap, action))
    return diagnostics


def is_goal(action):
    return any(choice < 8 for choice in (action // 100, action // 10 % 10, action % 10))


class StimulusV6Tests(unittest.TestCase):
    def test_legacy_rank_v2_v3_v5_and_submission_ast_unchanged(self):
        expected = dict(LEGACY_AST_SHA256,
                        record_probe_v4_submission='e79fb1a7deec5b5b579902d58d42dbe815f4d2d6b5e750a608e9feaff15bddaa')
        for name, digest in expected.items():
            tree = ast.parse(inspect.getsource(getattr(benchmark, name)))
            self.assertEqual(hashlib.sha256(ast.dump(tree.body[0]).encode()).hexdigest(), digest)
        source = ast.parse(inspect.getsource(benchmark.probe_action_v5)).body[0]
        self.assertEqual(ast.unparse(source.body[-1]),
                         'return probe_action_v4(snapshot, diagnostics, nonapproaching_goals=True)')

    def test_late15_and25_enable_goal26_disables_it(self):
        for elapsed, goal in ((15., True), (25., True), (26., False), (27., False)):
            diagnostics = after_first_wait()
            snap = snapshot(elapsed, active=False)
            chosen = choose(snap, diagnostics)
            self.assertEqual(is_goal(chosen), goal)
            self.assertTrue(snap['joint_action_mask'][chosen])
            self.assertEqual(bool(diagnostics.get('late_goal_decisions')), goal)

    def test_real_binary64_elapsed26_excluded_and15_included(self):
        at26 = 46.12 - 20.12
        at15 = 35.12 - 20.12
        self.assertLess(at26, 26.)
        self.assertEqual(round(at26 * 1e9), 26_000_000_000)
        self.assertFalse(is_goal(choose(snapshot(at26, active=False), after_first_wait())))
        diagnostics = after_first_wait()
        self.assertTrue(is_goal(choose(snapshot(at15, active=False), diagnostics)))
        self.assertEqual(diagnostics['late_goal_decisions'][0]['task_elapsed_sec'], at15)

    def test_late_outward_rank_keeps_original_time_and_independent_diagnostic(self):
        diagnostics = after_first_wait()
        snap = snapshot(22., active=False)
        before = json.dumps(snap, sort_keys=True)
        legal = [action for action, valid in enumerate(snap['joint_action_mask']) if valid
                 and all(choice < 9 for choice in (action // 100, action // 10 % 10, action % 10))
                 and benchmark._probe_nonapproaching_goal_action(snap, action)]
        expected = min(legal, key=lambda action: benchmark._probe_goal_order(snap, action, True))
        chosen = choose(snap, diagnostics)
        self.assertEqual(chosen, expected)
        self.assertEqual(json.dumps(snap, sort_keys=True), before)
        self.assertFalse(diagnostics.get('goal_decisions'))
        entry = diagnostics['late_goal_decisions'][-1]
        self.assertEqual(entry['task_elapsed_sec'], 22.)
        self.assertEqual(entry['snapshot_sequence'], snap['sequence'])
        self.assertEqual(entry['original_joint_allowed_actions'], 1000)
        self.assertEqual(entry['filtered_stimulus_allowed_actions'], len(legal))
        self.assertIn('not actor interface availability', entry['scope'])
        self.assertNotIn('selected_reverse_robots', entry)

    def test_original_early_windows_and_v5_diagnostics_are_exact(self):
        old, new = {}, {}
        for elapsed, active, waiting in ((0., False, True), (1., True, False),
                                         (10., False, True), (13., False, True),
                                         (14., True, False)):
            snap = snapshot(elapsed, active=active, waiting=waiting)
            old_action = benchmark.probe_action_v5(snap, old)
            new_action = choose(snap, new)
            self.assertEqual(old_action, new_action)
            self.assertEqual(old, new)
            submit(old, result(snap, old_action))
            submit(new, result(snap, new_action))
            self.assertEqual(old, new)

    def test_no_first_wait_or_unrecovered_received_state_cannot_goal(self):
        for failure in ('no_first_wait', 'hold_under3', 'active', 'stale', 'invalid',
                        'moving', 'nonfinite', 'bool_speed'):
            diagnostics = {} if failure == 'no_first_wait' else after_first_wait(
                12.5 if failure == 'hold_under3' else 10.)
            snap = snapshot(15., active=failure == 'active')
            for robot in snap['robots']:
                if failure == 'stale':
                    robot['fresh'] = False
                elif failure == 'invalid':
                    robot['valid'] = False
                elif failure == 'moving':
                    robot['v'] = .02
                elif failure == 'nonfinite':
                    robot['v'] = math.nan
                elif failure == 'bool_speed':
                    robot['v'] = True
            with self.subTest(failure=failure):
                self.assertEqual(choose(snap, diagnostics), 888)

    def test_latest25_goal_respects_masked5sec_then_wait30_and_hold31(self):
        diagnostics = after_first_wait()
        snap = snapshot(25., active=False)
        action = choose(snap, diagnostics)
        self.assertTrue(is_goal(action))
        submit(diagnostics, result(snap, action))
        for elapsed in (26., 27., 28., 29.):
            snap = snapshot(elapsed, active=True, waiting=False, speed=.2, path=.5)
            self.assertEqual(choose(snap, diagnostics), 888)
            submit(diagnostics, result(snap, 888))
            self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])
        snap = snapshot(30., active=True, speed=.2, path=.5)
        self.assertEqual(choose(snap, diagnostics), 999)
        self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])
        submit(diagnostics, result(snap, 999))
        self.assertEqual(set(diagnostics['v4_stimulus']['rounds']['second']['waits']),
                         {'tb1', 'tb2', 'tb3'})
        self.assertEqual(choose(snapshot(31., active=False), diagnostics), 999)
        self.assertEqual(32. - 30., 2.)

    def test_wait_submission_false_or_untyped_flag_never_latches(self):
        for flag in (False, 0, None):
            diagnostics = after_first_wait()
            snap = snapshot(28., active=True, speed=.2, path=.5)
            self.assertEqual(choose(snap, diagnostics), 999)
            if flag is False:
                submit(diagnostics, {'action_submitted': False})
                self.assertIsNone(diagnostics['v4_stimulus']['pending_submission'])
            else:
                with self.assertRaises(ValueError):
                    submit(diagnostics, result(snap, 999, action_submitted=flag))
            self.assertFalse(diagnostics['v4_stimulus']['rounds']['second']['waits'])

    def test_second_submitted_wait_stays_latched_during_late_window(self):
        diagnostics = after_first_wait()
        initial = snapshot(13., active=False)
        action = choose(initial, diagnostics)
        submit(diagnostics, result(initial, action))
        snap = snapshot(20., active=True, speed=.2, path=.5)
        self.assertEqual(choose(snap, diagnostics), 999)
        submit(diagnostics, result(snap, 999))
        self.assertEqual(choose(snapshot(23., active=False), diagnostics), 999)

    def test_original_false_goal_or_wait_mask_never_overridden(self):
        snap = snapshot(22., active=False)
        snap['joint_action_mask'] = [index == 888 for index in range(1000)]
        self.assertEqual(choose(snap, after_first_wait()), 888)
        snap['joint_action_mask'] = [False] * 1000
        with self.assertRaisesRegex(ValueError, 'never override a mask'):
            choose(snap, after_first_wait())

    def test_nonfinite_geometry_rejects_only_new_goal_and_no_global_mutation(self):
        snap = snapshot(22., active=False)
        snap['robots'][2]['x'] = math.inf
        diagnostics = after_first_wait()
        state = copy.deepcopy(snap)
        old = benchmark.probe_action_v5
        self.assertEqual(choose(snap, diagnostics), 888)
        self.assertEqual(snap, state)
        self.assertIs(benchmark.probe_action_v5, old)


if __name__ == '__main__':
    unittest.main(verbosity=2)
