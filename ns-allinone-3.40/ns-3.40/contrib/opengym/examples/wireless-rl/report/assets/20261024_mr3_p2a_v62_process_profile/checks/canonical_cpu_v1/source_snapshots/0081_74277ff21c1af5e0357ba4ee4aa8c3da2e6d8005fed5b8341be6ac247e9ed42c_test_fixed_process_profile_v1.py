"""Three small synthetic groups. No ROS, World, model or old evidence input."""
import hashlib
import json
import os
from pathlib import Path
import pstats
import signal
import subprocess
import sys
import tempfile
import time
import unittest

HERE = Path(__file__).resolve().parent
RESULTS = []


def identity(pid):
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        return dict(pid=pid, parent=int(fields[1]), group=int(fields[2]), session=int(fields[3]), start_ticks=int(fields[19]))
    except FileNotFoundError:
        return None


class FixedProfileArtificialTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='mr3-profile-artificial-')
        self.root = Path(self.temp.name)
        self.serial = 0
    def tearDown(self):
        self.temp.cleanup()
    @classmethod
    def tearDownClass(cls):
        destination = HERE / 'artificial_cpu_v3/toy_process_results.json'
        destination.open('x').write(json.dumps(dict(synthetic_only=True, real_waits=RESULTS), indent=2) + '\n')
    def launch(self, role, body, *, fault=None, extra='', terminate=False):
        self.serial += 1
        case = self.root / str(self.serial)
        case.mkdir()
        (case / 'profiles').mkdir()
        program = case / 'toy_program.py'
        program.write_text(body)
        digest = hashlib.sha256(program.read_bytes()).hexdigest()
        parameter = case / 'launch_params_toy.yaml'
        parameter.write_text('/**:\n  ros__parameters:\n    use_sim_time: true\n')
        argv = ([str(program), '--run-dir', str(case)] if role == 'worker' else
                [str(program), '--ros-args', '-r', '__node:=' + ('motion_safety' if role == 'motion_safety' else 'mr3_adapter'),
                 '--params-file', str(parameter)])
        if fault == 'program': argv[0] += '.wrong'
        if fault == 'worker_argv': argv[-1] += '_wrong'
        if fault == 'remap': argv[3] = 'other:=target'
        if fault == 'params_missing': argv = argv[:-2]
        if fault == 'params_symlink':
            link = case / 'parameter_alias.yaml'
            link.symlink_to(parameter)
            argv[-1] = str(link)
        runner = case / 'synthetic_runner.py'
        runner.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,' + repr(str(HERE)) + ')\n'
            'import fixed_process_profile_v1 as m\n'
            'm.OWNED_EPISODE=Path(' + repr(str(case)) + ')\n'
            'm.PROGRAMS={key:Path(' + repr(str(program)) + ') for key in m.PROGRAMS}\n'
            'm.PROGRAM_SHA256={key:' + repr('0'*64 if fault == 'source' else digest) + ' for key in m.PROGRAMS}\n'
            'm.SOURCES={key:(Path(' + repr(str(program)) + '),' + repr(digest) + ') for key in m.PROGRAMS}\n'
            + extra + '\nm.run_role(' + repr(role) + ',' + repr(argv) + ')\n')
        child = subprocess.Popen([sys.executable, '-B', str(runner)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        saved = identity(child.pid)
        self.assertIsNotNone(saved)
        if terminate:
            deadline = time.monotonic() + 5
            marker = case / 'target_entered'
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue(marker.exists())
            child.send_signal(signal.SIGTERM)  # This Popen-owned artificial child only.
        out, err = child.communicate(timeout=10)
        current = identity(child.pid)
        self.assertTrue(current is None or current['start_ticks'] != saved['start_ticks'])
        RESULTS.append(dict(role=role, actual_argv=[sys.executable, '-B', str(runner)],
            saved_identity=saved, actual_waited=True, actual_returncode=child.returncode,
            saved_identity_fresh_gone=True, toy_source_sha256=hashlib.sha256(program.read_bytes()).hexdigest(),
            stdout=out.decode(), stderr=err.decode()))
        return child.returncode, case / 'profiles' / role, case

    def test_real_rc_exception_dump_error_and_signal_are_preserved(self):
        code, output, _ = self.launch('motion_safety', 'raise SystemExit(7)\n')
        self.assertEqual(code, 7)
        self.assertEqual(json.loads((output / 'finished.json').read_text())['target_outcome']['exit_code_repr'], '7')
        code, output, _ = self.launch('motion_safety', 'raise RuntimeError("original target fault")\n')
        self.assertEqual(code, 1)
        self.assertEqual(json.loads((output / 'finished.json').read_text())['target_outcome']['kind'], 'RuntimeError')
        extra = 'def broken(self):\n    raise OSError("artificial dump failure")\nm.Capture.finish=broken\n'
        code, output, _ = self.launch('motion_safety', 'raise SystemExit(7)\n', extra=extra)
        self.assertEqual(code, 7)
        self.assertEqual(json.loads((output / 'profile_dump_error.json').read_text())['target_outcome']['kind'], 'SystemExit')
        body = 'from pathlib import Path\nimport time\nPath(__file__).with_name("target_entered").write_text("yes")\nwhile True: time.sleep(.02)\n'
        code, output, _ = self.launch('motion_safety', body, terminate=True)
        self.assertEqual(code, -signal.SIGTERM)
        self.assertTrue((output / 'started.json').is_file())
        self.assertFalse((output / 'finished.json').exists())

    def test_three_main_and_two_thread_profiles_are_independent(self):
        paths = []
        for role, lane in (('motion_safety', None), ('adapter', 'encoder'), ('worker', 'ros_spin')):
            body = 'import fixed_process_profile_v1 as m\nimport threading\ndef lane_work():\n    return sum(i*i for i in range(20))\n'
            if lane:
                body += 'def threaded():\n    m.profiled_call(' + repr(lane) + ',lane_work)\nt=threading.Thread(target=threaded)\nt.start()\nt.join()\n'
            code, output, _ = self.launch(role, body)
            self.assertEqual(code, 0)
            result = json.loads((output / 'finished.json').read_text())
            self.assertTrue(result['profile_complete'])
            self.assertFalse(result['scientific_qualification'])
            for item in result['parameters']:
                self.assertEqual(hashlib.sha256(Path(item['snapshot']).read_bytes()).hexdigest(), item['sha256'])
            expected = {'main'} | ({lane} if lane else set())
            self.assertEqual({row['lane'] for row in result['profiles']}, expected)
            for row in result['profiles']:
                path = Path(row['path'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row['sha256'])
                stats = pstats.Stats(str(path)).stats
                if lane:
                    contains_work = any(key[2] == 'lane_work' for key in stats)
                    self.assertEqual(contains_work, row['lane'] == lane)
                paths.append(str(path))
            if lane:
                self.assertEqual(len({row['thread_ident'] for row in result['profiles']}), 2)
        self.assertEqual(len(set(paths)), 5)

    def test_fixed_role_source_program_arguments_and_parameter_inputs_reject(self):
        for role, fault in (('unknown', None), ('motion_safety', 'source'), ('motion_safety', 'program'),
                            ('worker', 'worker_argv'), ('motion_safety', 'remap'),
                            ('motion_safety', 'params_missing'), ('motion_safety', 'params_symlink')):
            with self.subTest(role=role, fault=fault):
                code, _, case = self.launch(role, 'from pathlib import Path\nPath(__file__).with_name("ran").write_text("bad")\n',
                                            fault=fault)
                self.assertNotEqual(code, 0)
                self.assertFalse((case / 'ran').exists())


if __name__ == '__main__':
    unittest.main()
