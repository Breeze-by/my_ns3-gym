"""Artificial byte/Git fixtures only. No activity, real archive, gzip or raw input."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('mr3_v52_overlay_fixture', '/tmp/mr3_p2a_v52_packed_overlay_v1.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class PackedOverlayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='mr3-v52-packed-overlay-artificial-')
        self.addCleanup(temporary.cleanup)
        self.repo = Path(temporary.name)
        subprocess.run(['git', 'init', '--quiet', str(self.repo)], check=True, timeout=10)
        self.asset = self.repo / 'asset'
        self.archive = self.asset / 'closed_execution'
        (self.archive / 'native').mkdir(parents=True)
        self.contents = {'native/[giant]* ? #!.gz': b'not-a-valid-gzip:opaque-33-bytes!!!',
                         'native/[giant]*x ? #!.gz': b'x',
                         'equal.bin': b'0123456789abcdef', 'small.bin': b'short', 'empty.bin': b''}
        self.entries = []
        for relative, raw in self.contents.items():
            path = self.archive / relative
            path.write_bytes(raw)
            self.entries.append({'canonical': str(path.relative_to(self.asset)),
                'canonical_bytes': len(raw), 'canonical_sha256': hashlib.sha256(raw).hexdigest(),
                'original': '/nonexistent-raw-must-never-open/' + path.name,
                'original_bytes': 999, 'original_sha256': 'a' * 64, 'codec': 'gzip-mtime0-lossless',
                'source_stat_stable': True, 'decoded_bytes_verified': True})
        self.inventory_path = self.asset / 'closed_inventory_v1.json'
        self.inventory = {'schema': 'mr3-v52-closed-byte-archive-draft-v2', 'freeze': module.FREEZE,
            'byte_archive_complete': True, 'archive_mode': 'closed',
            'closed_saved_identity_inventory_claimed': True, 'files': len(self.entries),
            'entries': self.entries, 'fixture_only': True}
        self.write(self.inventory_path, self.inventory)
        self.inventory_sha = module.digest(self.inventory_path)[0]
        self.wait_path = self.repo / 'toy_collector_actual_wait.json'
        self.wait = {'schema': 'mr3-reach-outer-actual-wait-v1', 'scope': 'cpu',
            'actual_waited': True, 'actual_returncode': 0, 'passed': True, 'errors': [],
            'source_unchanged': True, 'started_monotonic_ns': 1, 'ended_monotonic_ns': 1000000001,
            'actual_child_wait_seconds': '1', 'actual_argv': ['/usr/bin/python3', '-B',
                str(module.COLLECTOR), '--freeze', module.FREEZE, '--mode', 'closed'],
            'source_before': [{'path': str(module.COLLECTOR), 'sha256': module.COLLECTOR_SHA}],
            'coordinator_identity': {'pid': 900001, 'start_ticks': 11},
            'child_identity': {'pid': 900002, 'start_ticks': 12}}
        self.wait['source_after'] = self.wait['source_before']
        self.write(self.wait_path, self.wait)
        self.splitter = module.load_pinned(module.SPLITTER, module.SPLITTER_SHA, '_fixture_original_splitter')
        self.copier = module.load_pinned(module.COPIER, module.COPIER_SHA, '_fixture_original_absence')
        self.copier.require_absent = Mock()  # Never look up toy PIDs in real /proc.
        self.addCleanup(patch.stopall)
        patch.object(module, 'MAX_PACKED', 16).start()  # Tiny artificial size, CLI remains64MiB.
        patch.object(module, 'load_pinned', side_effect=lambda path, *args:
            self.splitter if path == module.SPLITTER else self.copier).start()
        for owner, name in [(gzip, 'open'), (gzip, 'GzipFile'), (tarfile, 'open')]:
            patch.object(owner, name, side_effect=AssertionError('decode/recompress forbidden')).start()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value) + '\n')

    def build(self, sha=None):
        return module.build_overlay(self.asset, self.repo, sha or self.inventory_sha, self.wait_path)

    def test_binary_roundtrip_size_boundary_exact_ignore_and_originals_retained(self):
        manifest = self.build()
        self.assertEqual(manifest['replacement_file_count'], 1)
        self.copier.require_absent.assert_any_call(self.wait['coordinator_identity'])
        self.copier.require_absent.assert_any_call(self.wait['child_identity'])
        row = manifest['representations'][0]
        self.assertEqual([p['offset'] for p in row['parts']], list(range(0, row['packed_bytes'], 16)))
        self.assertTrue(all(0 < p['bytes'] <= 16 for p in row['parts']))
        output = self.repo / 'restored-packed.gz'
        receipt = module.restore(self.asset / 'packed_overlay_v1/manifest.json', row['canonical'], output)
        self.assertEqual(output.read_bytes(), self.contents['native/[giant]* ? #!.gz'])
        self.assertEqual(receipt['sha256'], row['packed_sha256'])
        self.assertFalse(receipt['decoded'])
        for name, raw in self.contents.items():
            self.assertEqual((self.archive / name).read_bytes(), raw)
        self.assertEqual(module.digest(self.inventory_path)[0], self.inventory_sha)
        paths = [self.archive / name for name in self.contents]
        actual_ignored = module.ignored(self.repo, paths)
        self.assertEqual(actual_ignored, {b'asset/closed_execution/native/[giant]* ? #!.gz'})
        dry = module.git(self.repo, 'add', '-n', '--', 'asset')
        self.assertNotIn(b'add \'asset/closed_execution/native/[giant]* ? #!.gz\'', dry.stdout)
        self.assertIn(b'packed_overlay_v1/manifest.json', dry.stdout)
        self.assertIn(b'closed_inventory_v1.json', dry.stdout)

    def test_unfinished_failed_or_present_collector_rejected_before_outputs(self):
        for field, value in [('actual_waited', False), ('actual_waited', None),
                             ('actual_returncode', 1), ('source_unchanged', False)]:
            self.write(self.wait_path, dict(self.wait, **{field: value}))
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.build()
        self.write(self.wait_path, self.wait)
        self.copier.require_absent.side_effect = ValueError('saved collector is Z')
        with self.assertRaisesRegex(ValueError, 'collector is Z'):
            self.build()
        self.assertFalse((self.asset / 'packed_overlay_v1').exists())
        self.assertFalse((self.archive / '.gitignore').exists())

    def test_wrong_inventory_sha_and_escaping_path_are_rejected(self):
        with self.assertRaisesRegex(ValueError, 'inventory SHA'):
            self.build('0' * 64)
        value = copy.deepcopy(self.inventory)
        value['entries'][0]['canonical'] = 'closed_execution/../escape.gz'
        self.write(self.inventory_path, value)
        with self.assertRaisesRegex(ValueError, 'escaping inventory path'):
            self.build(module.digest(self.inventory_path)[0])
        self.assertFalse((self.archive / '.gitignore').exists())

    def test_extra_canonical_file_is_rejected_without_hidden_ignore(self):
        (self.archive / 'unexpected.bin').write_bytes(b'x')
        with self.assertRaisesRegex(ValueError, 'full file membership'):
            self.build()
        self.assertFalse((self.archive / '.gitignore').exists())

    def test_already_tracked_large_blob_is_rejected(self):
        path = self.archive / 'native/[giant]* ? #!.gz'
        module.git(self.repo, 'add', '-f', '--', str(path.relative_to(self.repo)))
        with self.assertRaisesRegex(ValueError, 'already tracked'):
            self.build()
        self.assertFalse((self.archive / '.gitignore').exists())

    def test_corrupt_new_part_fails_before_exclusion_and_keeps_partial(self):
        split = self.splitter.split_archive
        def corrupt(source, target):
            rows = split(source, target)
            (target / rows[0]['path']).write_bytes(b'!' * rows[0]['bytes'])
            return rows
        self.splitter.split_archive = corrupt
        with self.assertRaisesRegex(ValueError, 'part is corrupt'):
            self.build()
        self.assertFalse((self.archive / '.gitignore').exists())
        self.assertTrue((self.asset / 'packed_overlay_v1/failure.json').exists())
        self.assertTrue((self.archive / 'native/[giant]* ? #!.gz').exists())

    def test_original_packed_change_is_detected_before_exclusion(self):
        split = self.splitter.split_archive
        def change(source, target):
            rows = split(source, target)
            source.write_bytes(b'changed-by-artificial-fixture')
            return rows
        self.splitter.split_archive = change
        with self.assertRaisesRegex(ValueError, 'archive/inventory changed'):
            self.build()
        self.assertFalse((self.archive / '.gitignore').exists())

    def test_restore_rejects_tampered_part_and_does_not_overwrite(self):
        manifest = self.build()
        row = manifest['representations'][0]
        part = self.asset / row['parts'][0]['path']
        part.write_bytes(b'corrupt')
        target = self.repo / 'partial-retained.gz'
        with self.assertRaisesRegex(ValueError, 'part bytes/hash changed'):
            module.restore(self.asset / 'packed_overlay_v1/manifest.json', row['canonical'], target)
        target.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):
            module.restore(self.asset / 'packed_overlay_v1/manifest.json', row['canonical'], target)
        self.assertEqual(target.read_bytes(), b'existing')


if __name__ == '__main__':
    unittest.main()
