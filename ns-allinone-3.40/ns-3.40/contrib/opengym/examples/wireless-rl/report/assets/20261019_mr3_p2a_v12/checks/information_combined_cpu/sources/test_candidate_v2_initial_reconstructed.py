"""CPU differential and fail-closed checks for the two independent oracles."""
import copy
import importlib.util
import random
import unittest


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


candidate = load('combined_candidate_cpu', '/tmp/mr3_information_combined_candidate_v2.py')
selection_tests = load('unchanged_three_key_cpu_tests', '/tmp/test_mr3_information_three_key_candidate_v1.py')


class CombinedTests(selection_tests.ThreeKeyTests):
    def setUp(self):
        self.host, self.original, self.proof = candidate.build_candidate()

    def test_exact_two_method_source_inverse_and_append_only_references(self):
        self.assertTrue(self.proof['whole_original_source_inverse_exact'])
        self.assertEqual(self.proof['whole_original_inverse_sha256'], candidate.RAW_SHA)
        self.assertEqual(self.proof['admitted_fixed_source_references'], [203, 306, 315])
        self.assertEqual(self.proof['only_method_replacements'], ['LedgerReplay.selection', 'LedgerReplay.expected_latest'])

    def test_six_stream_prefixes_return_identical_original_objects_without_state_mutation(self):
        replay = self.host.LedgerReplay('cpu')
        original = self.host.RawReplay.expected_latest
        rng = random.Random(261019)
        keys = list(replay.admitted)
        queries = 0
        for prefix in range(301):
            if prefix:
                key = rng.choice(keys)
                source = rng.choice((-10, -1, 0, 1, 10, 10**30, rng.randrange(-100, 101)))
                seq = rng.choice((prefix, 10**40 + prefix))
                item = {'source_ns': source, 'sequence': seq, 'prefix': prefix}
                replay.admitted[key].append(item)
                if prefix % 17 == 0:
                    replay.admitted[key].append(dict(item, exact_tie_second=True))
            before = copy.deepcopy({name: getattr(replay, name) for name in ('raw', 'pending', 'current', 'admitted', 'selections', 'counts')})
            for kind, robot in keys:
                for clock in (-11, -1, 0, 1, 10, 10**30 - 1, 10**30, rng.randrange(-110, 111)):
                    self.assertIs(replay.expected_latest(kind, robot, clock), original(replay, kind, robot, clock))
                    queries += 1
            self.assertEqual(before, {name: getattr(replay, name) for name in before})
        self.assertEqual(queries, 14448)

    def test_append_after_same_clock_query_and_earliest_exact_tie(self):
        replay = self.host.LedgerReplay('cpu')
        a = {'source_ns': 9, 'sequence': 10, 'name': 'first'}
        b = {'source_ns': 9, 'sequence': 10, 'name': 'same_key_later'}
        c = {'source_ns': 9, 'sequence': 11, 'name': 'greater_seq'}
        replay.admitted['tf', 'tb1'].append(a)
        self.assertIs(replay.expected_latest('tf', 'tb1', 9), a)
        replay.admitted['tf', 'tb1'].append(b)
        self.assertIs(replay.expected_latest('tf', 'tb1', 9), a)
        replay.admitted['tf', 'tb1'].append(c)
        self.assertIs(replay.expected_latest('tf', 'tb1', 9), c)
        self.assertIsNone(replay.expected_latest('tf', 'tb1', 8))

    def test_future_source_cannot_hide_original_promotion_failure(self):
        errors = []
        for cls in (self.host.RawReplay, self.host.LedgerReplay):
            replay = cls('cpu')
            item = {'source_ns': 10, 'sequence': 1}
            replay.admitted['tf', 'tb1'].append(item)
            replay.current['tf', 'tb1'] = item
            with self.assertRaisesRegex(ValueError, 'promotion differs from admitted callback prefix') as result:
                replay.promote('tf', 'tb1', 9)
            errors.append((type(result.exception), str(result.exception)))
        self.assertEqual(*errors)

    def tf_ingress(self):
        raw = {'header': {'stamp': {'sec': 1, 'nanosec': 0}, 'frame_id': 'map'},
               'child_frame_id': 'odom',
               'transform': {'translation': {'x': 0.0, 'y': 0.0, 'z': 0.0},
                             'rotation': {'x': 0.0, 'y': 0.0, 'z': 0.0, 'w': 1.0}}}
        return {'robot': 'tb1', 'input_sequence': 1, 'raw': raw,
                'raw_sha256': self.host.digest(raw), 'source_ns': 800_000_000,
                'admission': 'queued', 'matched_input_sequence': None}

    def test_original_real_ingress_errors_keep_exact_type_message_and_state(self):
        cases = [('input_sequence', 1.0), ('input_sequence', True), ('input_sequence', 2),
                 ('source_ns', 800_000_000.0), ('admission', 'ignored_pending_order')]
        for field, bad in cases:
            outcomes = []
            for cls in (self.host.RawReplay, self.host.LedgerReplay):
                replay = cls('cpu')
                replay.lead_ns = 200_000_000
                value = self.tf_ingress()
                value[field] = bad
                with self.assertRaises(ValueError) as result:
                    replay.ingress('tf', value, 1_000_000_000)
                outcomes.append((type(result.exception), str(result.exception), copy.deepcopy(replay.__dict__)))
            self.assertEqual(*outcomes)
        outcomes = []
        for cls in (self.host.RawReplay, self.host.LedgerReplay):
            replay = cls('cpu')
            replay.lead_ns = 200_000_000
            first = self.tf_ingress()
            replay.ingress('tf', first, 1_000_000_000)
            duplicate = copy.deepcopy(first)
            duplicate['input_sequence'] = 2  # Original expected ignored_pending_order, not queued.
            with self.assertRaisesRegex(ValueError, 'incorrect ingress admission') as result:
                replay.ingress('tf', duplicate, 1_000_000_000)
            outcomes.append((type(result.exception), str(result.exception), copy.deepcopy(replay.__dict__)))
        self.assertEqual(*outcomes)

    def test_real_record_still_rejects_noninteger_query_clock_before_dispatch(self):
        outcomes = []
        for cls in (self.host.RawReplay, self.host.LedgerReplay):
            replay = cls('cpu')
            row = {'schema': self.host.SCHEMA, 'epoch': 'cpu', 'record_sequence': 1,
                   'clock_ns': 1.5, 'wall_monotonic_ns': 1, 'kind': 'tf_ingress', 'payload': self.tf_ingress()}
            with self.assertRaisesRegex(ValueError, 'clock_ns must be an integer') as result:
                replay.record(row)
            outcomes.append((type(result.exception), str(result.exception), copy.deepcopy(replay.__dict__)))
        self.assertEqual(*outcomes)


if __name__ == '__main__':
    unittest.main(verbosity=2)
