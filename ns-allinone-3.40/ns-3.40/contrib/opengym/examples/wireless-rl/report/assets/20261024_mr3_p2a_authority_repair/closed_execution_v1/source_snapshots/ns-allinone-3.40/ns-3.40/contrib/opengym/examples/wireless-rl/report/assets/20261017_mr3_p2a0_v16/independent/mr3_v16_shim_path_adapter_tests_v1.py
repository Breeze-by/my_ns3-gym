"""Only versioned binary-proof path changes; exercise the real immutable reader."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

ROOT = Path('/home/zhuyulab/ns3-workspace')
A13 = ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
              'report/assets/20261017_mr3_p2a0_v13/independent')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


C = module('v16_closure_adapter', Path(__file__).with_name(
    'mr3_v16_multiepoch_closure_binary_review_v1.py'))
F = module('immutable_v13_saved_fixture', A13 / 'mr3_v13_shim_mapping_review_v1_tests.py')


class ShimPathAdapterTests(unittest.TestCase):
    def setUp(self):
        self.case = F.ReviewTests('test_complete_correct_saved_original_and_exact_episode')
        self.case.setUp()
        self.addCleanup(self.case.doCleanups)
        self.reader = F.R
        self.default = self.reader.BINARY
        self.assertEqual(self.default, Path('/tmp/mr3_p2a0_v13_binaryproof.json'))

    def call(self):
        self.case.save()
        result = C.call_shim_review(self.reader, self.case.f.root, self.case.prefix,
                                    self.case.base['freeze'], Path.read_bytes)
        self.assertEqual(self.reader.BINARY, self.default)
        return result

    def use_v16(self):
        argv = self.case.wrapper['shim_mapping']['base_monitor']['actual_argv']
        argv[argv.index('--binary-proof') + 1] = '/tmp/mr3_p2a0_v16_binaryproof.json'

    def test_actual_old_reader_accepts_exact_new_v16_proof_path(self):
        self.use_v16()
        self.assertTrue(self.call()['passed'])

    def test_old_v13_path_cannot_substitute_for_new_actual_cli(self):
        self.assertFalse(self.call()['passed'])

    def test_binary_path_adapter_does_not_relax_typed_original_base_equality(self):
        self.use_v16()
        self.case.base['typed_original'] = False
        self.case.save_base()
        self.case.wrapper['typed_original'] = 0
        self.assertFalse(self.call()['passed'])

    def test_exception_also_restores_original_reader_global(self):
        self.use_v16()
        with patch.object(self.reader, 'review', side_effect=RuntimeError('explicit test fault')):
            with self.assertRaisesRegex(RuntimeError, 'explicit test fault'):
                self.call()
        self.assertEqual(self.reader.BINARY, self.default)


if __name__ == '__main__':
    unittest.main(verbosity=2)
