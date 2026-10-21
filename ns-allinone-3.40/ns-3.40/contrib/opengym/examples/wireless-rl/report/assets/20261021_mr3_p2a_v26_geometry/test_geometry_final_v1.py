"""Synthetic metadata rejection checks; no geometry, process or episode run."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('geometry_final_cpu', Path(__file__).with_name('geometry_final_v1.py'))
final = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final)


class FinalMetadataTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.source = self.directory / 'bound.py'
        self.source.write_bytes(b'artificial source')
        self.source_patch = patch.object(final, 'ROOT', self.directory)
        self.source_patch.start()
        self.addCleanup(self.source_patch.stop)
        self.outer = {'scope': 'engineering', 'passed': True, 'actual_waited': True,
                      'actual_returncode': 0, 'source_unchanged': True}
        self.guard = {'passed': True, 'actual_waited': True, 'actual_returncode': 0,
                      'source_unchanged': True, 'timed_out': False}
        self.geometry = {
            'schema': 'mr3-proxy2d-quality-geometry-v1', 'passed': True,
            'bound_bytes_unchanged': True, 'errors': [],
            'qualification': False, 'training_eligible': False, 'native_credit': False,
            'source_and_asset_bindings': {'bound.py': {
                'sha256': hashlib.sha256(self.source.read_bytes()).hexdigest(),
                'bytes': len(self.source.read_bytes())}},
            'scenes': [{'scene': name, 'truth_occupied_cell_count': 5,
                        'possible_endpoint_overlap_correct_occupied_cells': 3,
                        'conditional_occupied_iou_upper_enclosure': .6,
                        'solid_occupied_cells_outside_surface_enclosure': 2}
                       for name in ('open', 'rooms', 'corridors')],
        }

    def invoke(self):
        for name, value in (('outer.json', self.outer),
                            ('guard_receipt_v1.json', self.guard),
                            ('geometry_result.json', self.geometry)):
            (self.directory / name).write_text(json.dumps(value))
        output = self.directory / 'final.json'
        argv = ['geometry_final_v1.py', '--guard', str(self.directory),
                '--outer', str(self.directory / 'outer.json'), '--output', str(output)]
        with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
            code = final.main()
        return code, json.loads(output.read_text())

    def test_accepts_integral_complete_metadata_without_task_credit(self):
        code, result = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(result['passed'])
        self.assertFalse(result['qualification'])
        self.assertFalse(result['training_eligible'])

    def test_rejects_promoted_qualification(self):
        self.geometry['qualification'] = True
        code, result = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(result['passed'])

    def test_rejects_changed_bound_source_bytes(self):
        self.source.write_bytes(b'changed after binding')
        code, result = self.invoke()
        self.assertEqual(code, 1)
        self.assertFalse(result['passed'])

    def test_retains_main_failure_even_with_successful_geometry_metadata(self):
        self.outer['passed'] = False
        self.outer['actual_returncode'] = 1
        code, result = self.invoke()
        self.assertEqual(code, 1)
        self.assertIn('main actual-wait/source failure retained', result['errors'])

    def test_live_saved_process_is_not_absence_credit(self):
        self.outer['coordinator_identity'] = final.identity(__import__('os').getpid())
        code, result = self.invoke()
        self.assertEqual(code, 1)
        self.assertEqual(result['saved_processes'][0]['status'], 'present')


if __name__ == '__main__':
    unittest.main()
