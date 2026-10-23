"""Artificial root-wait proof fixtures. Never read live activity/proc inputs."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path('/tmp/mr3_p2a_v52_review_closed_draft_v2.py')
spec = importlib.util.spec_from_file_location('mr3_v52_closure_draft_fixture', SCRIPT)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RootToolWaitProofTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mr3-v52-toolwait-artificial-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.driver = self.root / 'fixture_driver'
        self.driver.mkdir()
        self.launch_path = self.root / (module.PREFIX + '_launch_v1.json')
        self.live_path = self.root / (module.PREFIX + '_live_ancestor_observation_v1.json')
        self.wait_path = self.root / 'artificial_actual_tool_wait.json'
        self.saved = {'pid': 900001, 'parent': 900002, 'start_ticks': 101}
        self.ancestor = {'pid': 900002, 'parent': 900003, 'start_ticks': 100}
        self.entry = {'driver_identity': dict(self.saved)}
        self.summary = {'passed': True}
        self.launch = {'schema': 'mr3-v52-actual-root-launch-declaration-v1',
            'freeze': module.FREEZE, 'cwd': str(module.W), 'declared_monotonic_ns': 1000,
            'argv': ['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python', '-B', '-m',
                'report.assets.20261023_mr3_p2a_v52_qualification.execute_chain_v1',
                '--freeze', module.FREEZE]}
        self.live = {'schema': 'mr3-v52-live-owned-ancestor-observation-v1',
            'original_entry': str(self.driver / 'entry.json'),
            'observed_monotonic_ns': 2000, 'saved_driver_identity': dict(self.saved),
            'live_driver_identity': dict(self.saved),
            'actually_observed_tool_ancestor': dict(self.ancestor),
            'relationship_confirmed_while_alive': True, 'no_missing_start_reconstruction': True}
        self.write(self.launch_path, self.launch)
        self.write(self.live_path, self.live)
        self.wait = {'schema': 'mr3-v52-root-tool-actual-wait-v1', 'tool_session_id': 70032,
            'actual_waited': True, 'actual_returncode_observed': 0,
            'launch_declaration': self.proof(self.launch_path),
            'live_ancestor_observation': self.proof(self.live_path)}
        self.write(self.wait_path, self.wait)
        self.addCleanup(patch.stopall)
        patch.object(module, 'ACTUAL_TOOL_WAIT', self.wait_path, create=True).start()
        patch.object(module, 'load_identity_helper', return_value=object()).start()
        self.observe = patch.object(module, 'observe', return_value={
            'original_identity_gone': True, 'observation': 'artificial-only'}).start()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value) + '\n')

    @staticmethod
    def proof(path):
        raw = path.read_bytes()
        return {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}

    def invoke(self):
        review = module.Review()
        required = {(self.saved['pid'], self.saved['start_ticks']): dict(self.saved)}
        result = module.verify_root_tool_wait(review, self.driver, self.entry, self.summary, required)
        gates = module.archive_gate_results(review.parent_wait_proof_valid, required,
            review.bound_inputs_stable, True, review.errors, True)
        return review, required, result, gates

    def test_artificial_true_wait_retains_original_pairs_and_allows_proof(self):
        review, required, result, gates = self.invoke()
        self.assertTrue(review.parent_wait_proof_valid)
        self.assertEqual(review.errors, [])
        self.assertTrue(gates['archive_evidence_preservation_admissible'])
        self.assertTrue(gates['closed_archive_eligible'])
        self.assertEqual(result[0], self.wait)
        self.assertEqual(set(review.documents), {str(self.wait_path), str(self.launch_path), str(self.live_path)})
        self.assertIn((self.ancestor['pid'], self.ancestor['start_ticks']), required)
        self.observe.assert_called_once_with(self.ancestor['pid'], self.ancestor['start_ticks'])

    def test_false_or_null_wait_is_rejected_before_observation(self):
        for value in (False, None):
            with self.subTest(value=value):
                self.write(self.wait_path, dict(self.wait, actual_waited=value))
                with self.assertRaisesRegex(ValueError, 'actual tool wait'):
                    self.invoke()
        self.observe.assert_not_called()

    def test_null_or_boolean_return_code_is_rejected(self):
        for value in (None, True):
            with self.subTest(value=value):
                self.write(self.wait_path, dict(self.wait, actual_returncode_observed=value))
                with self.assertRaisesRegex(ValueError, 'actual tool wait'):
                    self.invoke()
        self.observe.assert_not_called()

    def test_actual_return_mismatch_invalidates_both_archive_modes(self):
        self.write(self.wait_path, dict(self.wait, actual_returncode_observed=1))
        review, _, _, gates = self.invoke()
        self.assertFalse(review.parent_wait_proof_valid)
        self.assertIn('root actual return contradicts completed driver result', review.errors)
        self.assertFalse(gates['archive_evidence_preservation_admissible'])
        self.assertFalse(gates['closed_archive_eligible'])

    def test_bad_launch_or_live_sha_and_bytes_invalidate_parent_proof(self):
        for key in ('launch_declaration', 'live_ancestor_observation'):
            for field, bad in (('sha256', '0' * 64), ('bytes', self.wait[key]['bytes'] + 1)):
                value = copy.deepcopy(self.wait)
                value[key][field] = bad
                self.write(self.wait_path, value)
                with self.subTest(key=key, field=field):
                    review, _, _, gates = self.invoke()
                    self.assertTrue(review.errors)
                    self.assertFalse(review.parent_wait_proof_valid)
                    self.assertFalse(gates['archive_evidence_preservation_admissible'])
                    self.assertFalse(gates['closed_archive_eligible'])

    def test_different_same_object_driver_identity_is_rejected(self):
        live = copy.deepcopy(self.live)
        live['live_driver_identity']['start_ticks'] += 1
        self.write(self.live_path, live)
        self.write(self.wait_path, dict(self.wait, live_ancestor_observation=self.proof(self.live_path)))
        with self.assertRaisesRegex(ValueError, 'actual live driver/ancestor'):
            self.invoke()
        self.observe.assert_not_called()

    def test_missing_actual_ancestor_binding_is_rejected(self):
        live = copy.deepcopy(self.live)
        live.pop('actually_observed_tool_ancestor')
        self.write(self.live_path, live)
        self.write(self.wait_path, dict(self.wait, live_ancestor_observation=self.proof(self.live_path)))
        with self.assertRaisesRegex(ValueError, 'actual live driver/ancestor'):
            self.invoke()
        self.observe.assert_not_called()

    def test_present_or_z_ancestor_is_rejected(self):
        self.observe.return_value = {'original_identity_gone': False, 'state': 'Z'}
        with self.assertRaisesRegex(ValueError, 'tool ancestor still exists/Z'):
            self.invoke()


if __name__ == '__main__':
    unittest.main()
