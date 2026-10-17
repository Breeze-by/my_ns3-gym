#!/usr/bin/python3
"""Pure fake-/proc and closed-byte mutations; no native/ROS/loader is invoked."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager

SOURCE = Path(__file__).with_name('mr3_v22_corrector_custody_v2.py')
spec = importlib.util.spec_from_file_location('corrector_custody', SOURCE)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
F = 'a' * 40


def dump(path, value):
    path.write_text(json.dumps(value, allow_nan=False) + '\n')


def encode(rows):
    return b''.join(h.canonical(row) + b'\n' for row in rows)


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mr3_v22_corrector_CPU_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / 'run'
        self.ep = self.run / 'worker0/episode001_open_101'
        self.ep.mkdir(parents=True)
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.prefix = self.root / 'stage'
        self.epoch = 'fixture_w0_e1'
        self.worker = {'pid': 100, 'parent': 50, 'start_ticks': 10, 'state': 'S'}
        self.launch = {'pid': 200, 'parent': 100, 'start_ticks': 20, 'state': 'S'}
        self.gz = {'pid': 300, 'parent': 200, 'start_ticks': 30, 'state': 'S'}
        for identity in [self.worker, self.launch, self.gz]:
            directory = self.proc / str(identity['pid'])
            directory.mkdir()
            fields = ['R', str(identity['parent'])] + ['0'] * 17 + [str(identity['start_ticks'])] + ['0'] * 8
            (directory / 'stat').write_text(str(identity['pid']) + ' (fake CPU process) ' + ' '.join(fields) + '\n')
        self.argv = ['/usr/bin/python3', str(h.WORKER), '--run-dir', str(self.ep)]
        (self.proc / '100/cmdline').write_bytes(('\0'.join(self.argv) + '\0').encode())
        self.sources = {}
        for index, key in enumerate(h.SOURCE_FIELDS):
            source = self.root / ('source' + str(index) + '.txt')
            source.write_text('explicit CPU fixture source' + str(index))
            self.sources[key] = {'path': str(source), 'sha256': h.sha(source.read_bytes())}
        self.library = self.root / 'fake_corrector.so'
        self.library.write_bytes(b'\x7fELF CPU fixture no load ' + b' '.join(v['sha256'].encode() for v in self.sources.values()))
        self.ode = self.root / 'fake_ode.so'
        self.ode.write_bytes(b'\x7fELF CPU fixture original ODE bytes')
        def library(path):
            return {'path': str(path), 'resolved': str(path.resolve()), 'sha256': h.sha(path.read_bytes()), 'bytes': path.stat().st_size}
        self.binding = {'schema': 'mr3-ray-box-corrector-binding-v1', 'status': 'ready',
            'monitor': {'path': str(h.MONITOR), 'sha256': h.MONITOR_SHA},
            'library': library(self.library), 'ode_library': library(self.ode),
            'sources': self.sources, 'ledger_filename': 'ray_box_corrector.jsonl',
            'world_names': {'open': 'p1c_open', 'rooms': 'p1c_rooms', 'corridors': 'p1c_corridors'}}
        receipt_path = self.root / 'binary_receipt.json'
        names = dict(zip(h.SOURCE_FIELDS, ('src/mr3_ray_box_corrector.cpp',
                     'src/mr3_ray_box_collision.cpp', 'include/multi_robot/mr3_ray_box_collision.hpp')))
        receipt = {'schema': 'mr3-v22-ray-box-actual-binary-custody-v1', 'passed': True,
                   'installed_library': self.binding['library'], 'actual_ode_library': self.binding['ode_library'],
                   'sources': {names[key]: value for key, value in self.sources.items()}}
        dump(receipt_path, receipt)
        self.binding['binary_receipt'] = {'path': str(receipt_path), 'sha256': h.sha(receipt_path.read_bytes())}
        self.binding_path = self.root / 'binding.json'
        dump(self.binding_path, self.binding)
        self.map_rows = []
        for i, path in enumerate([self.library, self.ode]):
            stat = path.stat()
            self.map_rows.append('%x-%x r-xp 00000000 %02x:%02x %d %s' % (
                4096 * (i + 1), 4096 * (i + 2), os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino, path.resolve()))
        self.maps_path = self.proc / '300/maps'
        self.maps_path.write_text('\n'.join(self.map_rows) + '\n')
        dump(self.ep / 'metadata.json', {'freeze': F, 'epoch': self.epoch, 'scene': 'open'})
        dump(self.ep / 'supervisor_metadata.json', {'epoch': self.epoch, 'worker_identity': self.worker})
        dump(self.ep / 'supervisor_shutdown.json', {'epoch': self.epoch, 'worker_returncode': 0,
            'forced_shutdown': False, 'failed_sample': False, 'remaining_owned_processes': [],
            'remaining_owned_zombies': [], 'owned_processes_seen': [self.worker, self.launch, self.gz]})
        self.monitor = {'schema': 'mr3-v9-readonly-drive-mapping-monitor-v1', 'freeze': F, 'errors': [],
            'episodes': [{'directory': str(self.ep)}],
            'owned_current_processes': [{'identity': identity} for identity in [self.worker, self.launch, self.gz]],
            'gazebo_mapped_libraries': [{'identity': self.gz, 'new_drive_mapped': True,
                'old_system_drive_mapped': False, 'identity_still_same_after_maps': True,
                'mappings': [{'matches_declared_binary': True}]}],
            'shim_mapping': {'producer_source': str(h.MONITOR), 'producer_source_sha256': h.MONITOR_SHA,
                'episodes': [{'directory': str(self.ep), 'epoch': self.epoch, 'active_worker': True,
                    'complete': True, 'worker_identity': self.worker, 'worker_actual_argv': self.argv}]}}
        self.monitor_path = self.root / 'monitor.json'
        dump(self.monitor_path, self.monitor)
        common = {'schema': 'mr3-ray-box-corrector-audit-v1', 'epoch': self.epoch, 'process_id': 300}
        self.config = dict(common, kind='configuration', plugin_type='SystemPlugin',
                           loaded_library_path=str(self.library.resolve()), actual_ode_library_path=str(self.ode.resolve()),
                           **{key: value['sha256'] for key, value in self.sources.items()})
        install = dict(common, kind='installed', world='p1c_open', world_clock_ns=0,
                       world_iterations=0, registered_pair=['dRayClass', 'dBoxClass'],
                       native_ode_quickstep_iterations=150, physics_max_step_size_sec=.001)
        counts = {'callback_calls': 20, 'hits': 2, 'misses': 18, 'nonzero_nearparallel_calls': 1, 'callback_errors': 0}
        self.rows = [self.config, install,
                     dict(common, kind='plugin_destructor_snapshot', **counts),
                     dict(common, kind='process_lifetime_summary', **counts)]
        self.ledger = self.ep / 'ray_box_corrector.jsonl'
        self.ledger.write_bytes(encode(self.rows))

    def observe(self):
        reader = h.Reader()
        result = h.observe(self.monitor_path, self.binding_path, F, reader, proc_root=self.proc)
        reader.finish()
        return result

    def full_review(self):
        proof = self.observe()
        self.assertTrue(proof['passed'], proof)
        dump(Path(str(self.prefix) + '_corrector_mapping_001.json'), proof)
        reader = h.Reader()
        result = h.review(self.run, self.prefix, F, self.binding_path, reader)
        reader.finish()
        return result

    def ledger_review(self, rows=None):
        return h.ledger_review(encode(self.rows if rows is None else rows), self.binding,
            self.epoch, 300, 'p1c_open', h.sha(encode([self.config])))

    def change_gz(self, state=None, start_ticks=None):
        path = self.proc / '300/stat'
        raw = path.read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        if state is not None:
            fields[0] = state
        if start_ticks is not None:
            fields[19] = str(start_ticks)
        path.write_text('300 (fake CPU process) ' + ' '.join(fields) + '\n')

    @contextmanager
    def after_header(self, callback):
        original = h.config_check
        def checked(*args, **kwargs):
            original(*args, **kwargs)
            callback()
        with patch.object(h, 'config_check', checked):
            yield

    def assert_pending_without_credit(self, result):
        self.assertFalse(result['passed'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(result['episodes'], [])
        self.assertEqual(len(result['pending']), 1)

    def save(self, index, proof):
        dump(Path(str(self.prefix) + '_corrector_mapping_%03d.json' % index), proof)

    def closed(self):
        reader = h.Reader()
        result = h.review(self.run, self.prefix, F, self.binding_path, reader)
        reader.finish()
        return result

    def test_same_identity_becomes_zombie_after_maps_has_no_credit(self):
        with self.after_header(lambda: self.change_gz(state='Z')):
            self.assert_pending_without_credit(self.observe())

    def test_final_identity_disappears_after_maps_has_no_credit(self):
        with self.after_header(lambda: (self.proc / '300/stat').unlink()):
            self.assert_pending_without_credit(self.observe())

    def test_reused_identity_even_zombie_remains_real_error(self):
        with self.after_header(lambda: self.change_gz(state='Z', start_ticks=999)):
            result = self.observe()
        self.assertFalse(result['passed'])
        self.assertEqual(result['episodes'], [])
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('changed during maps read', result['errors'][0]['error'])

    def test_permission_error_at_final_stat_is_not_shutdown_pending(self):
        original = h.proc_identity
        armed = [False]
        def read(pid, proc_root):
            if armed[0] and pid == 300:
                raise PermissionError('CPU denied actual stat')
            return original(pid, proc_root)
        with patch.object(h, 'proc_identity', read), self.after_header(lambda: armed.__setitem__(0, True)):
            result = self.observe()
        self.assertEqual(result['pending'], [])
        self.assertEqual(len(result['errors']), 1)
        self.assertIn('denied actual stat', result['errors'][0]['error'])

    def test_actual_hash_error_is_not_hidden_by_later_same_identity_zombie(self):
        def corrupt():
            self.library.write_bytes(self.library.read_bytes() + b'actual changed ELF')
            self.change_gz(state='Z')
        reader = h.Reader()
        with self.after_header(corrupt):
            result = h.observe(self.monitor_path, self.binding_path, F, reader, proc_root=self.proc)
        self.assertEqual(result['pending'], [])
        self.assertEqual(len(result['errors']), 1)
        self.assertEqual(result['episodes'], [])
        with self.assertRaisesRegex(ValueError, 'bound file changed before verdict'):
            reader.finish()

    def test_only_pending_proof_cannot_pass_whole_episode(self):
        with self.after_header(lambda: self.change_gz(state='Z')):
            proof = self.observe()
        self.save(1, proof)
        with self.assertRaisesRegex(ValueError, 'lacks corrector mapping proof'):
            self.closed()

    def test_prior_actual_mapping_survives_later_uncredited_close(self):
        actual = self.observe()
        self.assertTrue(actual['passed'])
        self.save(1, actual)
        with self.after_header(lambda: self.change_gz(state='Z')):
            pending = self.observe()
        self.assert_pending_without_credit(pending)
        self.save(2, pending)
        result = self.closed()
        self.assertTrue(result['passed'])
        self.assertEqual(len(result['episodes']), 1)

    def test_observed_error_stays_fatal_even_with_valid_and_later_pending_proofs(self):
        self.save(1, self.observe())
        original = self.ledger.read_bytes()
        rows = copy.deepcopy(self.rows)
        rows[0]['compiled_source_sha256'] = '0' * 64
        self.ledger.write_bytes(encode(rows))
        error = self.observe()
        self.assertEqual(len(error['errors']), 1)
        self.save(2, error)
        self.ledger.write_bytes(original)
        with self.after_header(lambda: self.change_gz(state='Z')):
            self.save(3, self.observe())
        with self.assertRaisesRegex(ValueError, 'mapping proof has real error'):
            self.closed()


if __name__ == '__main__':
    unittest.main()
