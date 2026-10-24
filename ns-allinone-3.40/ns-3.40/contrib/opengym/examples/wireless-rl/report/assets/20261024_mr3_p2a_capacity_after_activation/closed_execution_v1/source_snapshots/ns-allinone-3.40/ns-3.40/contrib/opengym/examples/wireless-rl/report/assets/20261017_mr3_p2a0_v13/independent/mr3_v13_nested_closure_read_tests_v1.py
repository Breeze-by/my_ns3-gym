"""Actual closure main/read with an explicit no-episode nested-read fixture.

The small substitute supplement exercises only the closure's passed read callback.
It supplies no native/source/body proof. Full supplement semantics have separate
frozen tests and independent review; no native process or subprocess is started.
"""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE = Path(os.environ.get('MR3_CLOSURE_TEST_SOURCE', str(Path(__file__).with_name(
    'mr3_v13_multiepoch_closure_binary_review_v1.py'))))
FREEZE = 'a' * 40


class NestedClosureReadTests(unittest.TestCase):
    def exercise(self, mutation):
        with tempfile.TemporaryDirectory(prefix='mr3v13_nested_read_') as temporary:
            root = Path(temporary)
            run = root / 'run'
            run.mkdir()
            source = root / 'closure_fixture.py'
            source.write_bytes(SOURCE.read_bytes())
            raw = b'{"value":false}\n'
            input_path = root / 'typed_input.json'
            input_path.write_bytes(raw)
            helper = root / 'mr3_v13_shim_mapping_review_v1.py'
            # This is an explicit read-callback stub, never a fake native verdict.
            code = "def review(run, prefix, freeze, read):\n"
            code += "    path = run.parent / 'typed_input.json'\n"
            code += "    original = read(path)\n"
            if mutation == 'repeat_typed':
                code += "    try:\n"
                code += "        path.write_bytes(b'{\\\"value\\\":0}\\n')\n"
                code += "        read(path)\n"
                code += "    finally:\n"
                code += "        path.write_bytes(original)\n"
            elif mutation == 'after_last_read':
                code += "    path.write_bytes(b'{\\\"value\\\":0}\\n')\n"
            else:
                code += "    assert read(path) == original\n"
            code += "    return {'passed': True, 'fixture_only': 'nested read callback'}\n"
            helper.write_text(code)
            identity = {'pid': 1000000001, 'start_ticks': 19, 'parent': 1000000002}
            (root / 'fixture_launch.json').write_text(json.dumps({
                'freeze': FREEZE, 'returncode': 0, 'benchmark_parent': identity,
                'launcher_identity': dict(identity, pid=1000000003)}))
            library = root / 'synthetic_library.so'
            library.write_bytes(b'explicit synthetic bytes, not a loaded ELF')
            (root / 'mr3_p2a0_v13_binaryproof.json').write_text(json.dumps({
                'freeze': FREEZE, 'library_path': str(library),
                'library_sha256': hashlib.sha256(library.read_bytes()).hexdigest()}))
            module = types.ModuleType('actual_closure_fixture')
            module.__file__ = str(source)
            exec(compile(source.read_bytes(), str(SOURCE), 'exec'), module.__dict__)

            def selected_path(value):
                if str(value) == '/tmp':
                    return root
                if str(value) == '/tmp/mr3_p2a0_v13_binaryproof.json':
                    return root / 'mr3_p2a0_v13_binaryproof.json'
                return Path(value)

            module.Path = selected_path
            argv = ['closure', str(run), '--prefix', 'fixture', '--freeze', FREEZE,
                    '--expected-episodes', '0']
            with patch.object(sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()):
                module.main()
            result = json.loads((root / 'fixture_closure_binary_review_v1.json').read_bytes())
            supplement = json.loads((root / 'fixture_shim_mapping_review_v1.json').read_bytes())
            return result, supplement, result['bindings'][str(input_path)], raw

    def test_unchanged_repeated_read_is_allowed(self):
        result, supplement, binding, raw = self.exercise('stable')
        self.assertTrue(result['passed'])
        self.assertTrue(supplement['passed'])
        self.assertEqual(binding['sha256'], hashlib.sha256(raw).hexdigest())

    def test_same_path_false_to_zero_then_restore_is_rejected_at_second_read(self):
        result, supplement, binding, raw = self.exercise('repeat_typed')
        self.assertFalse(result['passed'])
        self.assertFalse(supplement['passed'])
        self.assertIn('changed across reads', supplement['errors'][0])
        self.assertEqual(binding['sha256'], hashlib.sha256(raw).hexdigest())

    def test_change_after_last_nested_read_is_rejected_before_final_verdict(self):
        result, supplement, binding, raw = self.exercise('after_last_read')
        self.assertTrue(supplement['passed'])
        self.assertFalse(result['passed'])
        self.assertTrue(any('bound input changed before final verdict' in item for item in result['errors']))
        self.assertEqual(binding['sha256'], hashlib.sha256(raw).hexdigest())


if __name__ == '__main__':
    unittest.main(verbosity=2)
