"""Read-only watcher bookkeeping fixtures; never invokes its subprocess capture."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


W = load('watcher', 'mr3_p2a0_v13_cross_stage_mapping_monitor_v1.py')
T = load('mapping_tests', 'mr3_readonly_v13_drive_shim_process_monitor_v2_tests.py')


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        run = self.root / 'mr3_p2a0_20261017_v13_interface'
        run.mkdir()
        self.f = T.Fixture(run)
        gazebo = self.f.add(88133, self.f.worker['pid'], ['gzserver'])
        self.document = copy.deepcopy(self.f.base)
        self.document['errors'] = []
        self.document['gazebo_mapped_libraries'] = [{
            'identity': gazebo, 'new_drive_mapped': True, 'old_system_drive_mapped': False,
            'identity_still_same_after_maps': True, 'mappings': [{'matches_declared_binary': True}]}]
        self.document['episodes'][0].update(
            drivers={name: {key: True for key in (
                'available', 'compiled_match', 'library_match', 'tagged_match')} for name in T.M.ROBOTS},
            evidence={name: {'valid': True} for name in (
                'drive_topology', 'model_tb1', 'model_tb2', 'model_tb3')})
        self.document['shim_mapping'] = {'episodes': T.M.inspect_episodes(
            self.f.base, self.f.binding, self.f.proc)}
        self.path = self.root / 'mr3_p2a0_v13_interface_process_monitor_001.json'
        self.addCleanup(patch.stopall)
        patch.object(W, 'TEMP', self.root).start()
        patch.object(W, 'BASE', self.root).start()
        patch.object(W, 'FREEZE', self.f.base['freeze']).start()
        patch.object(W, 'proofs', {stage: {} for stage in W.STAGES}).start()
        patch.object(W, 'processed', set()).start()

    def harvest(self):
        self.path.write_text(json.dumps(self.document))
        W.harvest('interface')
        return W.stage_summary('interface')

    def test_full_same_episode_three_controller_and_drive_proof_counted(self):
        summary = self.harvest()
        self.assertTrue(summary['each_actual_worker_active_mapping_observed'])
        self.assertFalse(summary['two_snapshot_preference_met'])
        self.assertEqual(summary['actual_workers'][0]['active_complete_proof_count'], 1)

    def test_no_shim_complete_is_not_proof(self):
        self.document['shim_mapping']['episodes'][0]['complete'] = False
        self.assertFalse(self.harvest()['each_actual_worker_active_mapping_observed'])

    def test_other_worker_cannot_substitute(self):
        self.document['shim_mapping']['episodes'][0]['worker_identity']['start_ticks'] += 1
        self.assertFalse(self.harvest()['each_actual_worker_active_mapping_observed'])

    def test_other_epoch_cannot_substitute(self):
        self.document['shim_mapping']['episodes'][0]['epoch'] = 'another-epoch'
        self.assertFalse(self.harvest()['each_actual_worker_active_mapping_observed'])

    def test_no_driver_proof_even_with_shim_remains_missing(self):
        self.document['gazebo_mapped_libraries'] = []
        self.assertFalse(self.harvest()['each_actual_worker_active_mapping_observed'])

    def test_wrong_freeze_is_rejected(self):
        self.document['freeze'] = 'b' * 40
        with self.assertRaises(AssertionError):
            self.harvest()


if __name__ == '__main__':
    unittest.main(verbosity=2)
