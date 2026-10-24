"""Synthetic proc fixtures only: no native process, ROS calls or mapping credit."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('monitor', Path(__file__).with_name(
    'mr3_readonly_v13_drive_shim_process_monitor_v2.py'))
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class Fixture:
    def __init__(self, root):
        self.root = root
        self.proc = root / 'proc'
        self.proc.mkdir()
        self.ep = root / 'worker3/episode017_rooms_801'
        self.ep.mkdir(parents=True)
        self.library = root / 'libnav2_rotation_shim_controller.so'
        self.library.write_bytes(b'synthetic mapped ELF, not a real shared object')
        self.library_proof = {'resolved': str(self.library.resolve()),
                              'sha256': hashlib.sha256(self.library.read_bytes()).hexdigest()}
        self.binding = {'files': {'library': self.library_proof}}
        self.base = {'freeze': 'a' * 40, 'episodes': [{'directory': str(self.ep)}],
                     'owned_current_processes': []}
        self.parent = self.add(57003, 1, ['python', 'benchmark.py'])
        self.worker = self.add(
            24029, 57003, ['/usr/bin/python3', str(M.WORKER), '--run-dir', str(self.ep)])
        self.controllers = {}
        for i, robot in enumerate(M.ROBOTS):
            self.controllers[robot] = self.add(69010 + 157 * i, self.worker['pid'], [
                '/opt/ros/humble/lib/nav2_controller/controller_server', '--ros-args',
                '-r', '__ns:=/' + robot, '--params-file', '/tmp/synthetic_params'])
            self.maps(self.controllers[robot]['pid'])
        (self.ep / 'metadata.json').write_text(json.dumps({'freeze': self.base['freeze'], 'epoch': 'e17'}))
        self.supervisor = {'epoch': 'e17', 'worker_identity': self.worker, 'command': [
            '/usr/bin/bash', '--noprofile', '--norc', '-c', 'synthetic fixture only',
            'mr3-worker', str(M.ROS), str(self.ep)]}
        self.save_supervisor()

    def add(self, pid, parent, argv):
        directory = self.proc / str(pid)
        directory.mkdir()
        identity = {'pid': pid, 'parent': parent, 'group': 60, 'session': 60,
                    'start_ticks': pid * 100 + 7, 'state': 'R'}
        self.stat(identity)
        self.command(pid, argv)
        self.base['owned_current_processes'].append({'identity': identity, 'argv': argv})
        return identity

    def command(self, pid, argv):
        (self.proc / str(pid) / 'cmdline').write_bytes(('\0'.join(argv) + '\0').encode())

    def stat(self, identity):
        fields = ['0'] * 50
        fields[0] = identity['state']
        for i, key in ((1, 'parent'), (2, 'group'), (3, 'session'), (19, 'start_ticks')):
            fields[i] = str(identity[key])
        (self.proc / str(identity['pid']) / 'stat').write_text(
            str(identity['pid']) + ' (synthetic process) ' + ' '.join(fields))

    def maps(self, pid, path=None, inode=None, device=None, suffix=''):
        path = path or self.library
        stat = path.stat()
        device = device or f'{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}'
        inode = stat.st_ino if inode is None else inode
        (self.proc / str(pid) / 'maps').write_text(
            f'1000-2000 r-xp 00000000 {device} {inode} {path}{suffix}\n')

    def save_supervisor(self):
        (self.ep / 'supervisor_metadata.json').write_text(json.dumps(self.supervisor))

    def inspect(self):
        return M.inspect_episodes(self.base, self.binding, self.proc)[0]


class MappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.f = Fixture(Path(self.temp.name))

    def test_valid_three_arbitrary_pids_and_source_identity(self):
        row = self.f.inspect()
        self.assertTrue(row['complete'])
        self.assertEqual(set(row['controllers']), set(M.ROBOTS))
        for name, controller in row['controllers'].items():
            self.assertEqual(controller['robot'], name)
            self.assertEqual(controller['ancestor_chain'][-1]['pid'], self.f.worker['pid'])
            self.assertTrue(controller['mappings'][0]['sha256'])

    def test_scheduling_state_change_is_not_pid_reuse(self):
        for row in self.f.base['owned_current_processes']:
            self.f.stat(dict(row['identity'], state='S'))
        self.assertTrue(self.f.inspect()['complete'])

    def test_missing_controller_stays_pending(self):
        self.f.base['owned_current_processes'].pop()
        self.assertFalse(self.f.inspect()['complete'])

    def test_wrong_namespace(self):
        row = self.f.base['owned_current_processes'][-1]
        row['argv'][3] = '__ns:=/tb4'
        self.f.command(row['identity']['pid'], row['argv'])
        self.assertFalse(self.f.inspect()['complete'])

    def test_duplicate_controller_role_rejected(self):
        row = self.f.base['owned_current_processes'][-1]
        row['argv'][3] = '__ns:=/tb1'
        self.f.command(row['identity']['pid'], row['argv'])
        result = self.f.inspect()
        self.assertFalse(result['complete'])
        self.assertIn('duplicate', result['errors'][0])

    def test_conflicting_namespace_remaps_rejected(self):
        row = self.f.base['owned_current_processes'][-1]
        row['argv'] += ['-r', '__ns:=/tb2']
        self.f.command(row['identity']['pid'], row['argv'])
        self.assertFalse(self.f.inspect()['complete'])

    def test_controller_from_other_worker_cannot_fill_role(self):
        controller = self.f.controllers['tb3']
        other = self.f.add(99112, self.f.parent['pid'], ['python', 'other-worker'])
        changed = dict(controller, parent=other['pid'])
        self.f.stat(changed)
        self.f.base['owned_current_processes'][4]['identity'] = changed
        self.assertFalse(self.f.inspect()['complete'])

    def test_reparented_controller_cannot_reuse_captured_ancestry(self):
        controller = self.f.controllers['tb1']
        self.f.stat(dict(controller, parent=self.f.parent['pid']))
        self.assertFalse(self.f.inspect()['complete'])

    def test_worker_pid_reuse_cannot_borrow_old_episode(self):
        self.f.stat(dict(self.f.worker, start_ticks=self.f.worker['start_ticks'] + 1))
        row = self.f.inspect()
        self.assertFalse(row['complete'])
        self.assertFalse(row['active_worker'])

    def test_controller_pid_reuse(self):
        row = self.f.controllers['tb2']
        self.f.stat(dict(row, start_ticks=row['start_ticks'] + 1))
        self.assertFalse(self.f.inspect()['complete'])

    def test_actual_commandline_change_not_captured_identity(self):
        row = self.f.controllers['tb1']
        self.f.command(row['pid'], ['controller_server', '--ros-args', '-r', '__ns:=/tb1'])
        self.assertFalse(self.f.inspect()['complete'])

    def test_library_wrong_bytes(self):
        self.f.library.write_bytes(b'changed ELF bytes')
        self.assertFalse(self.f.inspect()['complete'])

    def test_map_inode_wrong(self):
        self.f.maps(self.f.controllers['tb2']['pid'], inode=1)
        self.assertFalse(self.f.inspect()['complete'])

    def test_map_device_wrong(self):
        self.f.maps(self.f.controllers['tb2']['pid'], device='ff:ff')
        self.assertFalse(self.f.inspect()['complete'])

    def test_deleted_mapping_is_not_current_disk_proof(self):
        self.f.maps(self.f.controllers['tb2']['pid'], suffix=' (deleted)')
        self.assertFalse(self.f.inspect()['complete'])

    def test_map_unexpected_path_even_equal_bytes(self):
        foreign = self.f.root / 'foreign/libnav2_rotation_shim_controller.so'
        foreign.parent.mkdir()
        foreign.write_bytes(self.f.library.read_bytes())
        self.f.maps(self.f.controllers['tb2']['pid'], path=foreign)
        self.assertFalse(self.f.inspect()['complete'])

    def test_worker_freeze_epoch_and_inventory_binding(self):
        for key, value in [('freeze', 'b' * 40), ('epoch', 'other-epoch')]:
            with self.subTest(key=key):
                original = json.loads((self.f.ep / 'metadata.json').read_bytes())
                (self.f.ep / 'metadata.json').write_text(json.dumps(dict(original, **{key: value})))
                self.assertFalse(self.f.inspect()['complete'])
                (self.f.ep / 'metadata.json').write_text(json.dumps(original))
        self.f.base['owned_current_processes'].remove(self.f.base['owned_current_processes'][1])
        self.assertFalse(self.f.inspect()['complete'])

    def test_cloned_epoch_directory_cannot_borrow_live_worker(self):
        import shutil
        cloned = self.f.root / 'worker4/episode018_open_801'
        shutil.copytree(self.f.ep, cloned)
        self.f.base['episodes'].append({'directory': str(cloned)})
        rows = M.inspect_episodes(self.f.base, self.f.binding, self.f.proc)
        self.assertTrue(rows[0]['complete'])
        self.assertFalse(rows[1]['complete'])
        self.assertIn('not this episode', rows[1]['errors'][0])

    def test_saved_worker_command_cannot_name_another_episode(self):
        self.f.supervisor['command'][-1] = '/tmp/another-episode'
        self.f.save_supervisor()
        self.assertFalse(self.f.inspect()['complete'])

    def test_new_episode_requires_its_own_worker(self):
        old = self.f.inspect()
        self.assertTrue(old['complete'])
        self.f.supervisor['worker_identity'] = dict(self.f.worker, start_ticks=700)
        self.f.save_supervisor()
        self.assertFalse(self.f.inspect()['complete'])

    def test_pid_reuse_during_maps_capture(self):
        original = M.proc_identity
        counter = {}
        pid = self.f.controllers['tb1']['pid']

        def changing(target, proc_root):
            result = original(target, proc_root)
            counter[target] = counter.get(target, 0) + 1
            if target == pid and counter[target] >= 4:
                return dict(result, start_ticks=result['start_ticks'] + 1)
            return result
        with mock.patch.object(M, 'proc_identity', side_effect=changing):
            self.assertFalse(self.f.inspect()['complete'])

    def test_path_stat_and_hashed_bytes_cannot_be_from_different_files(self):
        replacement = self.f.root / 'replacement.so'
        replacement.write_bytes(b'replacement bytes B')
        before = self.f.library.read_bytes()
        original = M.stable_file
        switched = False

        def switch_after_read(path):
            nonlocal switched
            result = original(path)
            if Path(path) == self.f.library and not switched:
                switched = True
                replacement.replace(self.f.library)
                self.f.maps(self.f.controllers['tb1']['pid'])
            return result

        with mock.patch.object(M, 'stable_file', side_effect=switch_after_read):
            self.assertFalse(self.f.inspect()['complete'])
        self.assertNotEqual(before, self.f.library.read_bytes())

    def test_binding_rejects_changed_declared_sha_and_extra_role(self):
        source = Path(__file__).with_name('mr3_v13_shim_binding_v1.json')
        original = json.loads(source.read_bytes())
        self.assertEqual(set(M.check_binding(source)['files']), set(M.EXPECTED))
        target = self.f.root / 'binding.json'
        changed = copy.deepcopy(original)
        changed['files']['library']['sha256'] = '0' * 64
        target.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            M.check_binding(target)
        changed = copy.deepcopy(original)
        changed['files']['unexpected'] = changed['files']['header']
        target.write_text(json.dumps(changed))
        with self.assertRaises(ValueError):
            M.check_binding(target)


if __name__ == '__main__':
    unittest.main(verbosity=2)
