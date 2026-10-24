"""Additional .20-cap mutations; inherited v5 math/phase suite runs separately."""
import copy
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('drive_v6', Path(__file__).with_name('mr3_independent_drive_trace_v6.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
FREEZE = 'a' * 40
EPOCH = 'synthetic-only-no-native'


def fixture(directory):
    data = {'metadata.json': {'freeze': FREEZE, 'epoch': EPOCH}}
    data['motion_safety.jsonl'] = [{'kind': 'decision', 'epoch': EPOCH,
        'payload': {'robot': name, 'request': [math.nextafter(.2, math.inf), 0.],
            'decision': {'output': [.2, .8]}}} for name in M.ROBOTS]
    data['drive_targets.jsonl'] = [{'epoch': EPOCH, 'target_json': json.dumps({
        'schema': 'mr3-drive-target-v1', 'epoch': EPOCH, 'robot': name,
        'clock_ns': 20_000_000, 'decision_sequence': 1, 'linear_x': .2, 'angular_z': .8})}
        for name in M.ROBOTS]
    for name in M.ROBOTS:
        data['drive_' + name + '.jsonl'] = [
            {'kind': kind, 'epoch': EPOCH, 'desired_v': .2, 'desired_w': .8}
            for kind in ('command_received', 'actuation')]
    write_fixture(directory, data)
    return data


def write_fixture(directory, data):
    for filename, value in data.items():
        raw = (json.dumps(value) + '\n' if filename.endswith('.json') else
               ''.join(json.dumps(row) + '\n' for row in value)).encode()
        (directory / filename).write_bytes(raw)


class CapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.data = fixture(self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def audit(self):
        inputs = M.BASE.Inputs()
        result = M.audit_cap_episode(self.directory, FREEZE, inputs)
        inputs.verify_unchanged()
        return result

    def test_exact_boundary_passes_and_raw_request_is_not_normalized_or_rejected(self):
        before = {p: p.read_bytes() for p in self.directory.iterdir()}
        result = self.audit()
        self.assertTrue(result['passed'])
        self.assertEqual(result['max_abs_final_linear_by_robot'], dict.fromkeys(M.ROBOTS, .2))
        self.assertEqual(before, {p: p.read_bytes() for p in self.directory.iterdir()})

    def test_final_guard_one_ulp_outside_rejected_both_signs(self):
        for sign in (1., -1.):
            data = copy.deepcopy(self.data)
            data['motion_safety.jsonl'][0]['payload']['decision']['output'][0] = sign * math.nextafter(.2, math.inf)
            write_fixture(self.directory, data)
            with self.assertRaisesRegex(ValueError, 'exceeds .20/.8'):
                self.audit()

    def test_final_target_publication_one_ulp_outside_rejected(self):
        target = json.loads(self.data['drive_targets.jsonl'][1]['target_json'])
        target['linear_x'] = math.nextafter(.2, math.inf)
        self.data['drive_targets.jsonl'][1]['target_json'] = json.dumps(target)
        write_fixture(self.directory, self.data)
        with self.assertRaisesRegex(ValueError, 'exceeds .20/.8'):
            self.audit()

    def test_native_received_and_actuation_one_ulp_outside_rejected(self):
        for index in (0, 1):
            data = copy.deepcopy(self.data)
            data['drive_tb3.jsonl'][index]['desired_v'] = math.nextafter(.2, math.inf)
            write_fixture(self.directory, data)
            with self.assertRaisesRegex(ValueError, 'exceeds .20/.8'):
                self.audit()

    def test_angular_one_ulp_is_still_rejected(self):
        self.data['drive_tb2.jsonl'][0]['desired_w'] = math.nextafter(.8, math.inf)
        write_fixture(self.directory, self.data)
        with self.assertRaisesRegex(ValueError, 'exceeds .20/.8'):
            self.audit()

    def test_zero_cleanup_and_negative_exact_limit_pass(self):
        for row in self.data['motion_safety.jsonl']:
            row['payload']['decision']['output'] = [-.2, -.8]
        for name in M.ROBOTS:
            self.data['drive_' + name + '.jsonl'].append(
                {'kind': 'command_received', 'epoch': EPOCH, 'desired_v': 0., 'desired_w': 0.})
        write_fixture(self.directory, self.data)
        self.assertTrue(self.audit()['passed'])

    def test_nonfinite_and_bool_final_values_rejected(self):
        for value in (True, float('nan'), float('inf')):
            data = copy.deepcopy(self.data)
            data['drive_tb1.jsonl'][0]['desired_v'] = value
            write_fixture(self.directory, data)
            with self.assertRaises(ValueError):
                self.audit()

    def test_missing_role_or_file_fails(self):
        self.data['drive_tb3.jsonl'] = []
        write_fixture(self.directory, self.data)
        with self.assertRaisesRegex(ValueError, 'missing actual'):
            self.audit()
        (self.directory / 'drive_tb3.jsonl').unlink()
        with self.assertRaises(FileNotFoundError):
            self.audit()

    def test_gzip_selected_originals_are_read_without_rewrite(self):
        for p in list(self.directory.iterdir()):
            Path(str(p) + '.gz').write_bytes(gzip.compress(p.read_bytes(), mtime=0))
            p.unlink()
        self.assertTrue(self.audit()['passed'])

    def test_original_full_review_is_called_and_fail_preserved(self):
        # Actual immutable review executes; only its source lookup raises a deliberate
        # boundary sentinel. No substitute original success/math result is claimed.
        with patch.object(M.OLD.BASE, 'source_bindings', side_effect=ValueError('original source gate failed')) as source:
            result = M.review(self.directory, FREEZE, Path('/not/a/proof'))
        source.assert_called_once_with(FREEZE)
        self.assertFalse(result['passed'])
        self.assertFalse(result['immutable_v5_result']['passed'])
        self.assertIn('original source gate failed', result['immutable_v5_result']['error'])
        self.assertTrue(result['final_command_cap']['passed'])

    def test_pass_requires_original_typed_pass_and_cap_pass(self):
        # Narrow composition test: fake original result does not stand for a native audit.
        original = {'passed': True, 'episodes': [], 'preserved_original_field': ['unchanged']}
        with patch.object(M.OLD, 'review', return_value=original) as call:
            result = M.review(self.directory, FREEZE, Path('/mock-proof'))
        call.assert_called_once_with(self.directory, FREEZE, Path('/mock-proof'), False)
        self.assertTrue(result['passed'])
        self.assertIs(result['immutable_v5_result'], original)
        self.data['drive_tb1.jsonl'][0]['desired_v'] = .21
        write_fixture(self.directory, self.data)
        with patch.object(M.OLD, 'review', return_value=original):
            self.assertFalse(M.review(self.directory, FREEZE, Path('/mock-proof'))['passed'])
        original['passed'] = 1
        write_fixture(self.directory, fixture(self.directory))
        with patch.object(M.OLD, 'review', return_value=original):
            self.assertFalse(M.review(self.directory, FREEZE, Path('/mock-proof'))['passed'])

    def test_base_and_addition_must_bind_identical_input_bytes(self):
        original = {'passed': True, 'inputs': {str(self.directory / 'motion_safety.jsonl'):
            {'bytes': 1, 'sha256': '0' * 64}}}
        with patch.object(M.OLD, 'review', return_value=original):
            result = M.review(self.directory, FREEZE, Path('/mock-proof'))
        self.assertFalse(result['passed'])
        self.assertIn('input bytes differ', result['final_command_cap']['error'])

    def test_legacy_bytes_and_math_functions_remain_original(self):
        self.assertEqual(hashlib.sha256(M.LEGACY.read_bytes()).hexdigest(), M.LEGACY_SHA)
        self.assertIs(M.OLD.BASE.robot_audit, M.BASE.robot_audit)
        self.assertEqual(M.BASE.MATH_TOL, 1e-12)


if __name__ == '__main__':
    unittest.main(verbosity=2)
