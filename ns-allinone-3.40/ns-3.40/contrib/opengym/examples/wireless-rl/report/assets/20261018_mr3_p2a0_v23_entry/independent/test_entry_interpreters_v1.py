"""Only new V23 interpreter/receipt/budget boundary tests; no native or ROS."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
OLD = W / 'report/assets/20261018_mr3_p2a0_v22_ray_box'
NEW = W / 'report/assets/20261018_mr3_p2a0_v23_entry'
LEARNER = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'


def load(name):
    path = HERE / name
    spec = importlib.util.spec_from_file_location('fixture_' + name.replace('.', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EntryBoundary(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)

    def test_exact_learner_constants_and_all_other_system_commands_remain(self):
        launch = load('mr3_p2a0_v23_launch_stage.py')
        audit = load('mr3_p2a0_v23_audit_stage.py')
        preflight = load('mr3_p2a0_v23_buildproof_preflight.py')
        self.assertEqual([str(m.LEARNER_PYTHON) for m in (launch, audit, preflight)], [LEARNER] * 3)
        source = (HERE / 'mr3_p2a0_v23_audit_stage.py').read_text()
        self.assertIn("submit('full_audit', [str(LEARNER_PYTHON), '-m'", source)
        self.assertNotIn("submit('full_audit', [sys.executable", source)
        old = (OLD / 'independent/mr3_p2a0_v22_audit_stage.py').read_text()
        self.assertEqual(source.count("'/usr/bin/python3'"), old.count("'/usr/bin/python3'"))
        for path in HERE.glob('mr3*py'):
            self.assertNotIn('mr3_p2a0_20261018_v22_', path.read_text(), str(path))
        parent = (HERE / 'mr3_p2a0_v23_run_matrix_v1.py').read_text()
        self.assertIn('command = [sys.executable,', parent)
        self.assertNotIn('LEARNER_PYTHON', parent)

    def test_actual_argparse_help_returns_before_environment_construction(self):
        for filename in ('benchmark.py', 'audit_preparation.py'):
            source = W / 'mr3_learning' / filename
            parsed = ast.parse(source.read_bytes())
            main = next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
            parse = next(n.lineno for n in ast.walk(main) if isinstance(n, ast.Call)
                         and isinstance(n.func, ast.Attribute) and n.func.attr == 'parse_args')
            effects = [n.lineno for n in ast.walk(main) if isinstance(n, ast.Call) and
                       ((isinstance(n.func, ast.Name) and n.func.id in ('MR3Env', 'MR3Supervisor', 'audit'))
                        or (isinstance(n.func, ast.Attribute) and n.func.attr in ('reset', 'step')))]
            self.assertTrue(all(parse < line for line in effects), filename)

    def fixture_launcher(self):
        m = load('mr3_p2a0_v23_launch_stage.py')
        m.TEMP = self.directory
        m.ASSET = self.directory / 'asset'
        m.ASSET.mkdir()
        m.WIRELESS = self.directory
        freeze = 'e' * 40
        specification = {'stage': 'interface', 'command': [LEARNER, '-m', 'mr3_learning.benchmark'],
                         'run_directory': str(self.directory / 'run_not_created'),
                         'wall_ceiling_seconds': 1800, 'required_audit_receipts': []}
        plan = {'schema': 'mr3-p2a0-predeclaration-v23', 'readiness': {'status': 'ready', 'pending_bindings': []},
                'stages': [specification], 'max_total_wall_seconds': 18000,
                'prior_entry_cost': {'wall_seconds': .24578428314998746}}
        raw = (json.dumps(plan) + '\n').encode()
        (m.ASSET / 'predeclared_plan_v23.json').write_bytes(raw)
        (self.directory / 'mr3_p2a0_v23_source_preflight.json').write_text(json.dumps({
            'passed': True, 'freeze': freeze, 'plan_sha256': hashlib.sha256(raw).hexdigest()}))
        return m, plan, freeze

    def test_real_prior_entry_cost_subtracted_before_first_stage(self):
        m, plan, freeze = self.fixture_launcher()
        _, budget = m.launch_admission(plan, 'interface', freeze)
        self.assertEqual(budget['preceding_wall_seconds'], .24578428314998746)
        self.assertEqual(budget['remaining_before_stage_seconds'], 18000 - .24578428314998746)
        plan['prior_entry_cost']['wall_seconds'] = 0
        with self.assertRaises(AssertionError):
            m.launch_admission(plan, 'interface', freeze)

    def test_actual_failed_main_receipt_always_has_observed_returncode(self):
        for spawned, actual in ((False, None), (True, 1), (True, 0)):
            with self.subTest(spawned=spawned, actual=actual):
                child_dir = self.directory / ('case' + str(spawned) + str(actual))
                child_dir.mkdir()
                previous = self.directory
                self.directory = child_dir
                m, _, freeze = self.fixture_launcher()
                self.directory = previous
                calls = []
                process = SimpleNamespace(pid=12345, wait=lambda: actual)
                def popen(command, **kwargs):
                    calls.append(command)
                    if not spawned:
                        raise OSError('synthetic spawn failure')
                    return process
                def git(command, **kwargs):
                    return '' if command[1] == 'status' else freeze + '\n'
                supervisor = SimpleNamespace(process_identity=lambda pid: {'pid': pid, 'start_ticks': 1})
                with patch.object(m.sys, 'argv', ['launcher', 'interface', freeze]), \
                        patch.object(m.subprocess, 'check_output', git), \
                        patch.object(m.subprocess, 'Popen', popen), \
                        patch.dict(m.sys.modules, {'mr3_learning.supervisor': supervisor}), \
                        patch.dict(m.os.environ, {}, clear=True):
                    with self.assertRaises((OSError, FileNotFoundError)):
                        m.main()
                record = json.loads((child_dir / 'mr3_p2a0_v23_interface_launch.json').read_bytes())
                self.assertIn('returncode', record)
                self.assertEqual(record['returncode'], actual)
                self.assertFalse(record['passed'])
                self.assertEqual(record['status'], 'failed')
                self.assertEqual(calls[0][0], LEARNER)
                if actual == 1:
                    self.assertEqual(record['primary_failure'], 'benchmark_returncode_nonzero')

    def test_probe_failure_keeps_real_exit_console_and_stops_without_retry(self):
        m = load('mr3_p2a0_v23_buildproof_preflight.py')
        m.PROBE_PREFIX = self.directory / 'probe'
        result = SimpleNamespace(returncode=3, stdout=b'', stderr=b'original missing dependency')
        with patch.object(m.subprocess, 'run', return_value=result) as invoked:
            with self.assertRaisesRegex(ValueError, 'reachability failed'):
                m.learner_entry_probe('e' * 40)
        self.assertEqual(invoked.call_count, 1)
        record = json.loads((self.directory / 'probe_probe_v1.json').read_bytes())
        self.assertFalse(record['passed'])
        self.assertEqual(record['commands'][0]['returncode'], 3)
        self.assertEqual(Path(record['commands'][0]['stderr']).read_bytes(), result.stderr)
        environment = invoked.call_args.kwargs['env']
        self.assertEqual(environment['CUDA_VISIBLE_DEVICES'], '')
        self.assertEqual(environment['PYTHONNOUSERSITE'], '1')
        self.assertNotIn('PYTHONPATH', environment)

    def test_new_loader_really_loads_immutable_a22_helper_and_binding(self):
        raw = (HERE / 'mr3_v23_multiepoch_closure_binary_review_v1.py').read_text()
        parsed = ast.parse(raw)
        method = next(n for n in parsed.body if isinstance(n, ast.FunctionDef)
                      and n.name == 'load_checked_corrector')
        namespace = {'Path': Path, 'hashlib': hashlib, 'json': json, 'importlib': importlib}
        exec(compile(ast.Module(body=[copy.deepcopy(method)], type_ignores=[]),
                     '<actual new loader>', 'exec'), namespace)
        final_plan_path = NEW / 'predeclared_plan_v23.json'
        def read(path):
            return (HERE.parent / 'predeclared_plan_v23.json').read_bytes() if path == final_plan_path else path.read_bytes()
        module, binding_path = namespace['load_checked_corrector'](read)
        self.assertEqual(Path(module.__file__), OLD / 'independent/mr3_v22_corrector_custody_v2.py')
        self.assertEqual(hashlib.sha256(read(Path(module.__file__))).hexdigest(),
                         '862e5b9aa674258975b5ac913d61125bc4b97d036cd6dec08d6296037619386d')
        self.assertEqual(binding_path, OLD / 'independent/mr3_v22_corrector_binding_v1.json')
        self.assertEqual(hashlib.sha256(read(binding_path)).hexdigest(),
                         '95ec473d92cde38674c5d17fa691e29ac68eb5a2eeef9823e4f0af36be1a986e')
        actual = module.load_binding(binding_path, read)
        self.assertEqual(actual['library']['sha256'],
                         '7be79c7f3d2cac53a9d1692aa868d91d4b9977e2b7541203ce4ffe90c605a08f')


if __name__ == '__main__':
    unittest.main(verbosity=2)
