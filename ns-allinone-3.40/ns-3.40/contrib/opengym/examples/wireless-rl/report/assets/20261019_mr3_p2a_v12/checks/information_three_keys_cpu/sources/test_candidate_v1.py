"""Short CPU counterexamples for the single same-cycle clock-oracle rewrite."""
import importlib.util
from pathlib import Path
import random
import unittest

spec = importlib.util.spec_from_file_location('three_key_candidate_cpu', '/tmp/mr3_information_three_key_candidate_v1.py')
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def selection(robot='tb1', cycle=1):
    return {'cycle_id': cycle, 'robot': robot, 'skip_reason': 'missing_odom',
            'odom_input_sequence': None, 'odom_source_ns': None,
            'tf_input_sequence': None, 'tf_source_ns': None,
            'pending_odom_input_sequences': [], 'pending_tf_input_sequences': []}


class ThreeKeyTests(unittest.TestCase):
    def setUp(self):
        self.host, self.original, self.proof = candidate.build_candidate()

    def test_exact_method_ast_changes_only_the_one_declared_expression(self):
        self.assertTrue(self.proof['method_ast_reverts_exactly'])
        self.assertNotEqual(self.proof['original_selection_sha256'], self.proof['candidate_selection_sha256'])
        self.assertEqual(candidate.sha(candidate.HOST), candidate.HOST_SHA)

    def test_all_valid_prefix_subsets_and_wrong_clock_match_original_boolean(self):
        rng = random.Random(41)
        rows = {}
        for cycle in range(1, 201):
            for robot in self.host.ROBOTS:
                if rng.randrange(3):
                    rows[cycle, robot] = {'clock_ns': cycle * 20_000_000}
            for query in (cycle, max(1, cycle // 2), cycle + 1):
                for clock in (query * 20_000_000, query * 20_000_000 + 1):
                    original = all(v['clock_ns'] == clock for (number, _), v in rows.items() if number == query)
                    fast = all(rows[query, robot]['clock_ns'] == clock for robot in self.host.ROBOTS if (query, robot) in rows)
                    self.assertEqual(original, fast)

    def test_full_selection_method_keeps_original_state_for_valid_rows(self):
        old, new = self.host.RawReplay('cpu'), self.host.LedgerReplay('cpu')
        for cycle in range(1, 21):
            for robot in self.host.ROBOTS:
                row = selection(robot, cycle)
                self.original(old, row, cycle * 20_000_000)
                new.selection(row, cycle * 20_000_000)
                self.assertEqual(old.selections, new.selections)
                self.assertEqual(old.pending, new.pending)
                self.assertEqual(old.counts, new.counts)
            old.last_published_cycle = new.last_published_cycle = cycle

    def test_wrong_same_cycle_clock_is_still_rejected_before_insertion(self):
        for cls in (self.host.RawReplay, self.host.LedgerReplay):
            replay = cls('cpu')
            replay.selections[1, 'tb2'] = {'clock_ns': 100}
            with self.assertRaisesRegex(ValueError, 'first capture clocks differ'):
                replay.selection(selection(), 101)
            self.assertNotIn((1, 'tb1'), replay.selections)

    def test_unknown_robot_and_duplicate_keys_are_rejected_by_unchanged_preconditions(self):
        for cls in (self.host.RawReplay, self.host.LedgerReplay):
            with self.assertRaisesRegex(ValueError, 'duplicate/invalid selection'):
                cls('cpu').selection(selection('tb4'), 1)
            replay = cls('cpu')
            replay.selections[1, 'tb1'] = {'clock_ns': 1}
            with self.assertRaisesRegex(ValueError, 'duplicate/invalid selection'):
                replay.selection(selection(), 1)

    def test_real_fast_selection_never_traverses_historical_items(self):
        class Counted(dict):
            traversed = 0
            def items(self):
                for value in super().items():
                    self.traversed += 1
                    yield value
        for cls, fast in ((self.host.RawReplay, False), (self.host.LedgerReplay, True)):
            replay = cls('cpu')
            replay.selections = Counted({(cycle, robot): {'clock_ns': cycle}
                for cycle in range(1, 2001) for robot in self.host.ROBOTS})
            replay.last_published_cycle = 2000
            replay.selection(selection(cycle=2001), 2001)
            self.assertEqual(replay.selections.traversed, 0 if fast else 6000)


if __name__ == '__main__':
    unittest.main(verbosity=2)
