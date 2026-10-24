import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('tail_description', Path(__file__).with_name('describe.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SuffixTests(unittest.TestCase):
    def test_partial_first_line_is_excluded_and_offsets_are_original(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'rows.jsonl'
            raw = b'{"x":"long first row"}\n{"x":2}\n{"x":3}\n'
            path.write_bytes(raw)
            rows = list(module.suffix(path, 20))
            self.assertEqual([row[2]['x'] for row in rows], [2, 3])
            for offset, line, _ in rows:
                self.assertEqual(raw[offset:offset+len(line)], line)

    def test_incomplete_final_line_fails(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'rows.jsonl'; path.write_bytes(b'{"x":2}')
            with self.assertRaisesRegex(ValueError, 'incomplete'):
                list(module.suffix(path, 100))

    def test_wrong_input_hash_fails_before_description(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / 'summary.json'; path.write_text('{}')
            scope = dict(schema='fixture', prior_freeze='fixture', inputs=[dict(
                path=str(path), name=path.name, bytes=2, sha256='wrong', tail_bytes=2)])
            with self.assertRaises(AssertionError):
                module.run(scope, Path(root) / 'result.json')


if __name__ == '__main__':
    unittest.main()
