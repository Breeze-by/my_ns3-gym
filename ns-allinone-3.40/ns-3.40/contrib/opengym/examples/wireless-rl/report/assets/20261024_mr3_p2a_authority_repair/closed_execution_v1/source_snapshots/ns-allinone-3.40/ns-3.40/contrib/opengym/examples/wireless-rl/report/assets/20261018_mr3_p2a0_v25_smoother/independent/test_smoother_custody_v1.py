import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

D = Path(__file__).parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, D / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


m = load('custody', 'mr3_v25_smoother_custody_v1.py')
h = load('workers', 'mr3_v25_stage_worker_bindings_v1.py')
FREEZE = 'a' * 40


def manifest_path(directory=None):
    directory = D if directory is None else directory
    local = directory / 'source_manifest_v1.json'
    return local if local.exists() else directory.parent / 'source_manifest_v1.json'


class Fixture:
    def __init__(self, root):
        self.root = root
        self.proc = root / 'proc'
        self.run = root / 'run'
        self.episode = self.run / 'worker0/episode001_open_101'
        self.episode.mkdir(parents=True)
        self.binding_path = root / 'binding.json'
        self.binding_path.write_text('{}')
        self.worker = self.identity(101, 1, 1001)
        self.parent = self.identity(102, 101, 1002)
        self.argv = ['/usr/bin/python3', str(m.ROS / 'scripts/mr3_env_worker.py'),
                     '--run-dir', str(self.episode)]
        self.binding = {'installed': {}}
        for name in ('executable', 'core'):
            path = root / ('velocity_smoother' if name == 'executable' else 'libvelocity_smoother_core.so')
            path.write_bytes(b'\x7fELF' + name.encode())
            path.chmod(0o755)
            self.binding['installed'][name] = {'path': str(path), 'resolved': str(path),
                                               'bytes': path.stat().st_size, 'sha256': m.sha(path.read_bytes())}
        self.write_process(self.worker, self.argv)
        self.write_process(self.parent, ['ros2', 'launch'])
        self.inventory = [{'identity': self.worker, 'argv': self.argv},
                          {'identity': self.parent, 'argv': ['ros2', 'launch']}]
        for index, robot in enumerate(m.ROBOTS):
            identity = self.identity(110 + index, 102, 1010 + index)
            argv = [self.binding['installed']['executable']['path'], '--ros-args', '-r', '__ns:=/' + robot]
            self.write_process(identity, argv, executable=True)
            self.inventory.append({'identity': identity, 'argv': argv})
        (self.episode / 'metadata.json').write_text(json.dumps({'freeze': FREEZE, 'epoch': 'epoch1'}))
        (self.episode / 'supervisor_metadata.json').write_text(json.dumps({'epoch': 'epoch1', 'worker_identity': self.worker}))
        self.monitor_path = root / 'monitor.json'
        self.monitor = {'freeze': FREEZE, 'errors': [], 'owned_current_processes': self.inventory,
            'shim_mapping': {'producer_source': str(m.MONITOR), 'producer_source_sha256': m.MONITOR_SHA,
                'episodes': [{'directory': str(self.episode), 'epoch': 'epoch1', 'active_worker': True,
                    'complete': True, 'worker_identity': self.worker, 'worker_actual_argv': self.argv}]}}
        self.save_monitor()

    @staticmethod
    def identity(pid, parent, start):
        return {'pid': pid, 'parent': parent, 'start_ticks': start, 'state': 'S',
                'group': 101, 'session': 101}

    def write_process(self, identity, argv, executable=False, state='S'):
        directory = self.proc / str(identity['pid'])
        directory.mkdir(parents=True, exist_ok=True)
        fields = ['0'] * 22
        fields[0], fields[1], fields[2], fields[3], fields[19] = state, str(identity['parent']), '101', '101', str(identity['start_ticks'])
        (directory / 'stat').write_text(str(identity['pid']) + ' (fixture) ' + ' '.join(fields))
        (directory / 'cmdline').write_bytes(('\0'.join(argv) + '\0').encode())
        if executable:
            (directory / 'exe').symlink_to(self.binding['installed']['executable']['path'])
            core = Path(self.binding['installed']['core']['path'])
            stat = core.stat()
            (directory / 'maps').write_text('1000-2000 r-xp 0000 %02x:%02x %d %s\n' %
                (os.major(stat.st_dev), os.minor(stat.st_dev), stat.st_ino, core))

    def save_monitor(self):
        self.monitor_path.write_text(json.dumps(self.monitor))

    def observe(self):
        with patch.object(m, 'load_binding', return_value=self.binding):
            return m.observe(self.monitor_path, self.binding_path, FREEZE, m.Reader(), self.proc)

    def save_proof(self, proof):
        prefix = self.root / 'stage'
        Path(str(prefix) + '_smoother_mapping_001.json').write_text(json.dumps(proof))
        return prefix

    def review(self, proof):
        prefix = self.save_proof(proof)
        with patch.object(m, 'load_binding', return_value=self.binding):
            return m.review(self.run, prefix, FREEZE, self.binding_path, m.Reader())


class CustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = Fixture(Path(self.temp.name))

    def test_actual_three_namespaces_and_nested_closed_review(self):
        proof = self.f.observe()
        self.assertTrue(proof['passed'])
        self.assertTrue(self.f.review(proof)['passed'])
        self.assertEqual(set(proof['episodes'][0]['processes']), set(m.ROBOTS))

    def test_r_state_is_valid(self):
        identity = self.f.inventory[-1]['identity']
        path = self.f.proc / str(identity['pid']) / 'stat'
        path.write_text(path.read_text().replace(') S ', ') R '))
        self.assertTrue(self.f.observe()['passed'])

    def test_r_to_s_during_capture_preserves_identity(self):
        original = m.file_proof
        count = 0
        def switch(value, read):
            nonlocal count
            result = original(value, read)
            count += 1
            if count == 4:
                path = self.f.proc / '110/stat'
                path.write_text(path.read_text().replace(') S ', ') R '))
            return result
        with patch.object(m, 'file_proof', side_effect=switch):
            self.assertTrue(self.f.observe()['passed'])

    def test_wrong_worker_episode_rejected(self):
        path = self.f.proc / '101/cmdline'
        path.write_bytes(path.read_bytes().replace(b'episode001', b'episode002'))
        proof = self.f.observe()
        self.assertFalse(proof['passed'])
        self.assertTrue(proof['errors'])

    def test_same_worker_z_empty_cmdline_pending(self):
        path = self.f.proc / '101/stat'
        path.write_text(path.read_text().replace(') S ', ') Z '))
        (self.f.proc / '101/cmdline').write_bytes(b'')
        proof = self.f.observe()
        self.assertFalse(proof['passed'])
        self.assertEqual(proof['errors'], [])
        self.assertEqual(proof['episodes'][0]['processes'], {})

    def test_reused_worker_z_empty_cmdline_hard_error(self):
        path = self.f.proc / '101/stat'
        path.write_text(path.read_text().replace('1001', '9999').replace(') S ', ') Z '))
        (self.f.proc / '101/cmdline').write_bytes(b'')
        self.assertTrue(self.f.observe()['errors'])

    def test_underlay_executable_rejected(self):
        argv = self.f.inventory[-1]['argv']
        argv[0] = '/opt/ros/humble/lib/nav2_velocity_smoother/velocity_smoother'
        (self.f.proc / '112/cmdline').write_bytes(('\0'.join(argv) + '\0').encode())
        self.f.save_monitor()
        self.assertFalse(self.f.observe()['passed'])

    def test_wrong_namespace_or_inode_rejected(self):
        path = self.f.proc / '112/maps'
        fields = path.read_text().split()
        fields[4] = str(int(fields[4]) + 1)
        path.write_text(' '.join(fields) + '\n')
        self.assertTrue(self.f.observe()['errors'])

    def test_wrong_or_deleted_core_rejected(self):
        path = self.f.proc / '112/maps'
        path.write_text(path.read_text().rstrip() + ' (deleted)\n')
        self.assertTrue(self.f.observe()['errors'])

    def test_reused_pid_rejected(self):
        path = self.f.proc / '112/stat'
        path.write_text(path.read_text().replace('1012', '9999'))
        self.assertTrue(self.f.observe()['errors'])

    def test_reused_pid_already_z_is_hard_error(self):
        path = self.f.proc / '112/stat'
        path.write_text(path.read_text().replace('1012', '9999').replace(') S ', ') Z '))
        self.assertTrue(self.f.observe()['errors'])

    def test_closing_z_after_maps_pending_without_credit(self):
        original = m.file_proof
        count = 0
        def closing(value, read):
            nonlocal count
            result = original(value, read)
            count += 1
            if count == 4:
                path = self.f.proc / '110/stat'
                path.write_text(path.read_text().replace(') S ', ') Z '))
            return result
        with patch.object(m, 'file_proof', side_effect=closing):
            proof = self.f.observe()
        self.assertFalse(proof['passed'])
        self.assertEqual(proof['errors'], [])
        self.assertNotIn('tb1', proof['episodes'][0]['processes'])

    def test_hash_error_not_swallowed_by_closing_z(self):
        original = m.file_proof
        count = 0
        def closing(value, read):
            nonlocal count
            count += 1
            if count == 3:
                Path(value['path']).write_bytes(b'\x7fELFwrong')
                path = self.f.proc / '110/stat'
                path.write_text(path.read_text().replace(') S ', ') Z '))
            return original(value, read)
        with patch.object(m, 'file_proof', side_effect=closing):
            proof = self.f.observe()
        self.assertTrue(proof['errors'])

    def test_saved_typed_and_borrowed_episode_proof_rejected(self):
        proof = self.f.observe()
        proof['episodes'][0]['worker_identity']['start_ticks'] = True
        with self.assertRaises(ValueError):
            self.f.review(proof)

    def test_missing_new_episode_cannot_borrow_first_capture(self):
        proof = self.f.observe()
        second = self.f.run / 'worker0/episode002_open_101'
        second.mkdir()
        (second / 'metadata.json').write_text(json.dumps({'freeze': FREEZE, 'epoch': 'epoch2'}))
        (second / 'supervisor_metadata.json').write_text(json.dumps({'epoch': 'epoch2', 'worker_identity': self.f.worker}))
        with self.assertRaises(ValueError):
            self.f.review(proof)


class SourceAndWorkersTests(unittest.TestCase):
    def test_runtime_resolution_uses_sanitized_system_ros_env_and_rejects_underlay(self):
        binding = json.loads((D / 'mr3_v25_smoother_binding_v1.json').read_bytes())
        data = {'package_prefix': str(m.ROS / 'install/nav2_velocity_smoother'),
                'executable': binding['installed']['executable']['path'], 'interpreter': '/usr/bin/python3',
                'ldd_returncode': 0, 'ldd_stderr': '',
                'ldd_stdout': 'libvelocity_smoother_core.so => ' + binding['installed']['core']['path'] + ' (0xabcd)\n'}
        def run(command, **kwargs):
            self.assertEqual(command[:2], ['/usr/bin/bash', '--noprofile'])
            self.assertNotIn('CONDA_PREFIX', kwargs['env'])
            self.assertNotIn('PYTHONPATH', kwargs['env'])
            self.assertEqual(kwargs['env']['PYTHONNOUSERSITE'], '1')
            return SimpleNamespace(returncode=0, stdout=json.dumps(data).encode(), stderr=b'')
        with patch.object(m.subprocess, 'run', side_effect=run):
            self.assertTrue(m.runtime_resolution(binding)['passed'])
            data['package_prefix'] = '/opt/ros/humble'
            with self.assertRaises(ValueError):
                m.runtime_resolution(binding)

    def test_fixed_two_timer_inverse_and_extra_edit_rejected(self):
        raw = (m.ROS / 'src/nav2_velocity_smoother/src/velocity_smoother.cpp').read_bytes()
        self.assertEqual(m.sha(m.inverse_cpp(raw)), m.UPSTREAM_CPP_SHA)
        with self.assertRaises(ValueError):
            m.inverse_cpp(raw + b'\n// unreviewed extra edit\n')

    def test_real_build_source_archive_read_only_binding(self):
        binding = D / 'mr3_v25_smoother_binding_v1.json'
        manifest = manifest_path()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'independent').mkdir()
            (root / 'source_manifest_v1.json').write_text('{}')
            self.assertEqual(manifest_path(root / 'independent'), root / 'source_manifest_v1.json')
        actual = m.ASSET / 'independent/mr3_v25_smoother_binding_v1.json'
        actual_manifest = m.ASSET / 'source_manifest_v1.json'
        reader = m.Reader()
        def read(path):
            return reader(binding if path == actual else manifest if path == actual_manifest else path)
        value = m.load_binding(actual, read)
        self.assertEqual(value['installed']['core']['sha256'], 'ceedf1b35cc501e9caa655c5b0a66f538395893664ec683a6290760f37d60b52')
        reader.finish()
        def bad_read(path):
            raw = read(path)
            if path == actual:
                value = json.loads(raw)
                value['installed']['core']['sha256'] = '0' * 64
                return json.dumps(value).encode()
            return raw
        with self.assertRaises(ValueError):
            m.load_binding(actual, bad_read)

    def test_frozen_build_uses_exact_git_bytes_with_no_native_or_ros_call(self):
        actual = m.ASSET / 'independent/mr3_v25_smoother_binding_v1.json'
        manifest = m.ASSET / 'source_manifest_v1.json'
        reader = m.Reader()
        def read(path):
            return reader(D / 'mr3_v25_smoother_binding_v1.json' if path == actual
                          else manifest_path() if path == manifest else path)
        def git(command, **kwargs):
            self.assertEqual(command[:2], ['git', 'show'])
            return read(m.ROOT / command[2].split(':', 1)[1])
        with patch.object(m.subprocess, 'check_output', side_effect=git), \
                patch.object(m, 'runtime_resolution', return_value={'passed': True, 'scope': 'CPU fixture'}):
            proof = m.verify_frozen_build(m.ROOT, FREEZE, actual, read)
        self.assertIn(str(actual.relative_to(m.ROOT)), proof)
        reader.finish()
        with patch.object(m.subprocess, 'check_output', return_value=b'wrong frozen Git blob'):
            with self.assertRaises(ValueError):
                m.verify_frozen_build(m.ROOT, FREEZE, actual, read)

    def test_worker_binding_derived_from_actual_argv_and_stale_declared_rejected(self):
        stage = {'command': ['python', '-m', 'mr3_learning.benchmark', '--workers', '2',
                             '--base-domain', '202', '--base-port', '13721']}
        stage['worker_bindings'] = h.derive_worker_bindings(stage)
        self.assertEqual(h.validate_worker_bindings(stage)[1]['domain'], 203)
        stage['worker_bindings'][0]['domain'] = 192
        with self.assertRaises(ValueError):
            h.validate_worker_bindings(stage)

    def test_worker_duplicate_cli_and_typed_false_metadata_rejected(self):
        stage = {'command': ['python', '--workers', '1', '--base-domain', '202', '--base-port', '13721']}
        stage['worker_bindings'] = h.derive_worker_bindings(stage)
        stage['worker_bindings'][0]['worker_id'] = False
        with self.assertRaises(ValueError):
            h.validate_worker_bindings(stage)
        stage['command'] += ['--base-domain', '202']
        with self.assertRaises(ValueError):
            h.derive_worker_bindings(stage)


if __name__ == '__main__':
    unittest.main()
