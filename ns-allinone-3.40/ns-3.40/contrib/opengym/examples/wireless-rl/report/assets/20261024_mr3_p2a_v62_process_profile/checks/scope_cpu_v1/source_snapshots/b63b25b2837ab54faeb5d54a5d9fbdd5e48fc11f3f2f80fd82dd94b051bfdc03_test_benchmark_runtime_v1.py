"""Real fixed Conda imports only; no sampler, ROS, native or model executes."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest

import fixed_profile_launcher_v1 as launcher

HERE = Path(__file__).resolve().parent


def identity(pid):
    try:
        values = Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()
        return dict(pid=pid, parent=int(values[1]), group=int(values[2]), session=int(values[3]),
                    start_ticks=int(values[19]))
    except (FileNotFoundError, ProcessLookupError):
        return None


class BenchmarkRuntimeTests(unittest.TestCase):
    def test_system_python_cannot_enter_the_benchmark_launcher(self):
        self.assertNotEqual(Path(sys.executable).resolve(), launcher.LEARNER_PYTHON.resolve())
        with self.assertRaisesRegex(ValueError, 'fixed ns3gym benchmark interpreter required'):
            launcher.main(['--freeze', 'a' * 40])

    def test_real_conda_imports_benchmark_and_passes_only_the_interpreter_guard(self):
        script = ('import sys\nfrom pathlib import Path\n'
                  'sys.path.insert(0,' + repr(str(HERE)) + ')\n'
                  'import fixed_profile_launcher_v1 as launcher\n'
                  'assert Path(sys.executable).resolve() == launcher.LEARNER_PYTHON.resolve()\n'
                  'original_file = launcher.__file__\n'
                  'for fixture_path in (original_file, str(launcher.ROOT / "synthetic_canonical_path_only.py")):\n'
                  '    launcher.__file__ = fixture_path\n'
                  '    try:\n        launcher.main(["--freeze", "a"*40])\n'
                  '    except ValueError as error:\n'
                  '        assert any(value in str(error) for value in ("only a new canonical frozen diagnostic launcher", "exact clean pushed diagnostic source freeze required")), str(error)\n'
                  '    else:\n        raise AssertionError("fixture reached execution")\n'
                  'launcher.__file__ = original_file\n'
                  'sys.path.insert(0,' + repr(str(launcher.W)) + ')\n'
                  'from mr3_learning import benchmark\n'
                  'assert callable(benchmark.main)\nprint("FIXED_BENCHMARK_IMPORT_ONLY_PASS")\n')
        argv = [str(launcher.LEARNER_PYTHON), '-B', '-c', script]
        env = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
        env.pop('PYTHONPATH', None)
        env.pop('PYTHONHOME', None)
        started = time.monotonic_ns()
        child = subprocess.Popen(argv, cwd=launcher.W, env=env,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        saved = identity(child.pid)
        self.assertIsNotNone(saved)
        stdout, stderr = child.communicate(timeout=20)
        current = identity(child.pid)
        gone = current is None or current['start_ticks'] != saved['start_ticks']
        value = dict(synthetic_import_only=True, actual_argv=argv, saved_identity=saved,
                     actual_waited=True, actual_returncode=child.returncode,
                     started_monotonic_ns=started, ended_monotonic_ns=time.monotonic_ns(),
                     current_identity=current, saved_identity_fresh_gone=gone,
                     stdout=stdout.decode(), stderr=stderr.decode())
        (HERE / 'artificial_cpu_v3/benchmark_runtime_import_wait_v1.json').open('x').write(
            json.dumps(value, indent=2) + '\n')
        self.assertEqual(child.returncode, 0, value)
        self.assertTrue(gone)
        self.assertIn('FIXED_BENCHMARK_IMPORT_ONLY_PASS', stdout.decode())


if __name__ == '__main__':
    unittest.main()
