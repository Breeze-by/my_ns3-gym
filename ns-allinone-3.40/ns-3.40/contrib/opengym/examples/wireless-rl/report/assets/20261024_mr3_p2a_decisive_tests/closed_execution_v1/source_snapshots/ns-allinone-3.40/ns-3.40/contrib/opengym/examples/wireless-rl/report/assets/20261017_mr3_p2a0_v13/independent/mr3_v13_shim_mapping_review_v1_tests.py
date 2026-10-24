"""Synthetic saved-monitor mutations; no native observer or closure credit."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


R = module('review', 'mr3_v13_shim_mapping_review_v1.py')
MT = module('monitor_tests', 'mr3_readonly_v13_drive_shim_process_monitor_v2_tests.py')
M = MT.M


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = MT.Fixture(Path(self.temp.name))
        self.prefix = self.f.root / 'fixture'
        self.path = self.f.root / 'fixture_process_monitor_001.json'
        self.support = self.f.root / 'fixture_process_monitor_001_support'
        self.support.mkdir()
        self.base = copy.deepcopy(self.f.base)
        self.base['run'] = str(self.f.root)
        self.binding = {'path': str(R.BINDING), 'sha256': 'a' * 64, 'files': self.f.binding['files']}
        self.wrapper = copy.deepcopy(self.base)
        self.wrapper['shim_mapping'] = {
            'schema': 'mr3-v13-shim-mapping-supplement-v2',
            'binding': copy.deepcopy(self.binding), 'producer_source': str(R.MONITOR.resolve()),
            'producer_source_sha256': R.digest(R.MONITOR.read_bytes()),
            'episodes': M.inspect_episodes(self.base, self.f.binding, self.f.proc),
            'base_monitor': {'source': str(R.BASE), 'sha256': R.BASE_SHA,
                             'returncode': 0, 'stdout_sha256': R.digest(b'synthetic stdout'),
                             'stderr_sha256': R.digest(b''), 'actual_argv': [
                                 '/usr/bin/python3', str(R.BASE), str(self.f.root), '--launch',
                                 str(self.prefix) + '_launch.json', '--binary-proof', str(R.BINARY),
                                 '--output', str(self.support / 'drive_base.json')]}}
        (self.support / 'base.stdout').write_bytes(b'synthetic stdout')
        (self.support / 'base.stderr').write_bytes(b'')
        self.save_base()
        self.save()
        self.addCleanup(mock.patch.stopall)
        mock.patch.object(R, 'LIBRARY', self.f.library).start()
        expected = dict(R.EXPECTED, library=self.f.library_proof['sha256'])
        mock.patch.object(R, 'EXPECTED', expected).start()
        mock.patch.object(R, 'binding_inputs', return_value=self.binding).start()

    def save_base(self):
        raw = (json.dumps(self.base, indent=2) + '\n').encode()
        (self.support / 'drive_base.json').write_bytes(raw)
        self.wrapper['shim_mapping']['base_monitor']['output_sha256'] = R.digest(raw)

    def save(self):
        self.path.write_text(json.dumps(self.wrapper, indent=2) + '\n')

    def review(self):
        self.save()
        return R.review(self.f.root, self.prefix, self.base['freeze'], Path.read_bytes)

    def selected(self):
        return self.wrapper['shim_mapping']['episodes'][0]

    def test_complete_correct_saved_original_and_exact_episode(self):
        result = self.review()
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['episodes'][0]['complete_captures']), 1)

    def test_original_drive_fields_cannot_be_changed_in_wrapper(self):
        self.wrapper['extra_drive_claim'] = True
        self.assertFalse(self.review()['passed'])

    def test_json_type_change_cannot_hide_behind_bool_integer_equality(self):
        self.base['boolean_field'] = True
        self.save_base()
        self.wrapper['boolean_field'] = 1
        self.assertFalse(self.review()['passed'])

    def test_original_raw_sha_mismatch(self):
        (self.support / 'drive_base.json').write_text(json.dumps(self.base) + ' \n')
        self.assertFalse(self.review()['passed'])

    def test_original_console_binding_required(self):
        (self.support / 'base.stdout').write_bytes(b'not the original console')
        self.assertFalse(self.review()['passed'])

    def test_actual_original_cli_must_target_same_run(self):
        self.wrapper['shim_mapping']['base_monitor']['actual_argv'][2] = '/tmp/another-run'
        self.assertFalse(self.review()['passed'])

    def test_original_source_pin_cannot_be_relabelled(self):
        self.wrapper['shim_mapping']['base_monitor']['sha256'] = '0' * 64
        self.assertFalse(self.review()['passed'])

    def test_new_producer_source_hash_must_match(self):
        self.wrapper['shim_mapping']['producer_source_sha256'] = '0' * 64
        self.assertFalse(self.review()['passed'])

    def test_capture_binding_must_match_frozen_installed_source_binding(self):
        self.wrapper['shim_mapping']['binding']['sha256'] = 'b' * 64
        self.assertFalse(self.review()['passed'])

    def test_no_active_complete_proof_is_missing_evidence(self):
        self.selected()['complete'] = False
        self.assertFalse(self.review()['passed'])

    def test_saved_metadata_bytes_must_be_same_as_native(self):
        self.selected()['metadata_sha256'] = '0' * 64
        self.assertFalse(self.review()['passed'])

    def test_same_worker_cannot_be_claimed_for_cloned_episode(self):
        import shutil
        second = self.f.root / 'worker4/episode018_open_801'
        shutil.copytree(self.f.ep, second)
        cloned = copy.deepcopy(self.selected())
        cloned['directory'] = str(second)
        self.wrapper['shim_mapping']['episodes'].append(cloned)
        result = self.review()
        self.assertFalse(result['passed'])
        self.assertTrue(result['episodes'][0]['passed'])
        self.assertFalse(result['episodes'][1]['passed'])

    def test_actual_worker_run_dir_is_required(self):
        self.selected()['worker_actual_argv'][-1] = '/tmp/another-episode'
        self.assertFalse(self.review()['passed'])

    def test_worker_pid_start_cannot_be_borrowed(self):
        self.selected()['worker_identity']['start_ticks'] += 1
        self.assertFalse(self.review()['passed'])

    def test_boolean_pid_cannot_equal_real_integer_pid(self):
        self.selected()['controllers']['tb1']['identity']['pid'] = True
        self.assertFalse(self.review()['passed'])

    def test_actual_controller_namespace_must_match_role(self):
        self.selected()['controllers']['tb1']['argv'][3] = '__ns:=/tb3'
        self.assertFalse(self.review()['passed'])

    def test_missing_controller_role_rejected(self):
        self.selected()['controllers'].pop('tb3')
        self.assertFalse(self.review()['passed'])

    def test_controller_parent_chain_cannot_jump_workers(self):
        self.selected()['controllers']['tb1']['ancestor_chain'][0]['parent'] = self.f.parent['pid']
        self.assertFalse(self.review()['passed'])

    def test_actual_map_raw_fields_and_claim_must_match(self):
        self.selected()['controllers']['tb1']['mappings'][0]['inode'] += 1
        self.assertFalse(self.review()['passed'])

    def test_missing_raw_map_record_cannot_be_replaced_with_valid_flag(self):
        self.selected()['controllers']['tb1']['shim_maps_lines'] = []
        self.assertFalse(self.review()['passed'])

    def test_wrong_library_hash_rejected(self):
        self.selected()['controllers']['tb1']['mappings'][0]['sha256'] = '0' * 64
        self.assertFalse(self.review()['passed'])

    def test_incomplete_startup_does_not_replace_or_invalidate_real_complete_capture(self):
        second_path = self.f.root / 'fixture_process_monitor_002.json'
        second_support = self.f.root / 'fixture_process_monitor_002_support'
        second_support.mkdir()
        import shutil
        for filename in ('drive_base.json', 'base.stdout', 'base.stderr'):
            shutil.copyfile(self.support / filename, second_support / filename)
        pending = copy.deepcopy(self.wrapper)
        pending['shim_mapping']['episodes'][0]['complete'] = False
        pending['shim_mapping']['base_monitor']['actual_argv'][-1] = str(second_support / 'drive_base.json')
        second_path.write_text(json.dumps(pending))
        result = self.review()
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['episodes'][0]['rejected_captures']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
