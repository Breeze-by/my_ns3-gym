"""Versioned coordinator integration only; synthetic files, no processes/ROS/native.
Old full audit math/CLIs are retained. Actual proc/ledger rules are the separately
bound custody consumer's responsibility; this fixture checks that it is called.
"""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

HERE = Path(__file__).resolve().parent
BASE = Path('/tmp/mr3_p2a0_v20_matrix_draft_v2/independent')
ROOT = '/home/zhuyulab/ns3-workspace'
ASSET = ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
         'report/assets/20261018_mr3_p2a0_v22_ray_box/')


def tree(name):
    return ast.parse((HERE / name).read_text())


def function(parsed, name):
    return next(n for n in parsed.body if isinstance(n, ast.FunctionDef) and n.name == name)


def same(left, right):
    return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


def versioned_old(name):
    raw = (BASE / name.replace('v22', 'v20')).read_text()
    raw = raw.replace('20261018_mr3_p2a0_v20', '20261018_mr3_p2a0_v22_ray_box')
    return ast.parse(raw.replace('v20', 'v22').replace('V20', 'V22'))


class Integration(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_original_parent_audit_and_existing_binary_shim_checks_unchanged(self):
        for name in ('mr3_p2a0_v22_run_matrix_v1.py', 'mr3_p2a0_v22_audit_stage.py'):
            self.assertTrue(same(tree(name), versioned_old(name)), name)
        name = 'mr3_p2a0_v22_buildproof_preflight.py'
        for method in ('sha', 'git_bytes', 'check_binary', 'check_shim'):
            self.assertTrue(same(function(tree(name), method),
                                 function(versioned_old(name), method)), method)

    def test_forbidden_diagnostic_selector_rejected_by_actual_main_before_any_other_io(self):
        for name in ('mr3_p2a0_v22_buildproof_preflight.py', 'mr3_p2a0_v22_launch_stage.py'):
            for value in ('', '/tmp/old_diagnostic.json'):
                with self.subTest(name=name, value=value):
                    namespace = {'os': SimpleNamespace(environ={
                        'MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE': value})}
                    main = function(tree(name), 'main')
                    exec(compile(ast.Module(body=[copy.deepcopy(main)], type_ignores=[]),
                                 str(HERE / name), 'exec'), namespace)
                    with self.assertRaisesRegex(ValueError, 'production matrix forbids'):
                        namespace['main']()

    def test_launch_main_remains_exact_after_removing_only_new_environment_guard(self):
        name = 'mr3_p2a0_v22_launch_stage.py'
        actual = tree(name)
        main = function(actual, 'main')
        self.assertIsInstance(main.body[0], ast.If)
        self.assertIn('MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE', ast.unparse(main.body[0]))
        main.body.pop(0)
        self.assertTrue(same(actual, versioned_old(name)))

    def observer_namespace(self, code):
        asset = self.root / ASSET
        (asset / 'independent').mkdir(parents=True)
        module = asset / 'independent/mr3_v22_corrector_custody_v2.py'
        binding = asset / 'independent/mr3_v22_corrector_binding_v1.json'
        module.write_text(code)
        binding.write_text('{"synthetic":true}\n')
        rows = [{'path': str(path.relative_to(self.root)),
                 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in (module, binding)]
        (asset / 'predeclared_plan_v22.json').write_text(json.dumps({
            'independent_source_bindings': rows}))
        parsed = tree('mr3_p2a0_v22_cross_stage_mapping_monitor_v1.py')
        methods = [copy.deepcopy(function(parsed, name))
                   for name in ('load_checked_corrector', 'observe_corrector')]

        class RootOnlyFixture(ast.NodeTransformer):
            def visit_Constant(self, node):
                if node.value == ROOT:
                    return ast.copy_location(ast.Constant(value=str(self_root)), node)
                return node

        self_root = self.root
        methods = [RootOnlyFixture().visit(node) for node in methods]
        namespace = {'Path': Path, 'hashlib': hashlib, 'json': json,
                     'importlib': importlib, 'FREEZE': 'e' * 40,
                     'sha': lambda raw: hashlib.sha256(raw).hexdigest()}
        exec(compile(ast.fix_missing_locations(ast.Module(body=methods, type_ignores=[])),
                     '<exact watcher methods, fixture root only>', 'exec'), namespace)
        return namespace, module, binding

    def test_original_monitor_remains_unmodified_and_extra_proof_is_exclusive(self):
        code = "def observe(monitor, binding, freeze, read):\n    read(monitor)\n    return {'passed':True,'freeze':freeze,'monitor':str(monitor)}\n"
        ns, _, _ = self.observer_namespace(code)
        monitor = self.root / 'original_monitor.json'
        original = b'{"base":"unchanged"}\n'
        monitor.write_bytes(original)
        output = self.root / 'prefix_corrector_mapping_001.json'
        record = ns['observe_corrector'](monitor, output)
        self.assertTrue(record['passed'])
        self.assertEqual(monitor.read_bytes(), original)
        self.assertEqual(json.loads(output.read_bytes())['freeze'], 'e' * 40)
        with self.assertRaises(FileExistsError):
            ns['observe_corrector'](monitor, output)

    def test_observer_repeated_read_and_final_recheck_reject_changed_input(self):
        for repeated in (False, True):
            with self.subTest(repeated=repeated):
                # Give each source-bound miniature module its own fixture tree.
                for path in list(self.root.iterdir()):
                    if path.is_dir():
                        import shutil
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                code = ("from pathlib import Path\ndef observe(monitor,binding,freeze,read):\n"
                        "    raw=read(monitor)\n    monitor.write_bytes(raw+b'x')\n" +
                        ("    read(monitor)\n" if repeated else '') +
                        "    return {'passed':True}\n")
                ns, _, _ = self.observer_namespace(code)
                monitor = self.root / 'original.json'
                monitor.write_text('{"synthetic":true}')
                output = self.root / 'proof.json'
                with self.assertRaisesRegex(ValueError, 'input changed'):
                    ns['observe_corrector'](monitor, output)
                self.assertFalse(output.exists())

    def test_source_and_binding_hashes_required_before_extra_reader_executes(self):
        ns, module, binding = self.observer_namespace(
            "raise RuntimeError('must not execute modified binding')\n")
        binding.write_text('{"mutated":true}')
        with self.assertRaisesRegex(ValueError, 'binding/plan SHA differs'):
            ns['load_checked_corrector'](lambda path: Path(path).read_bytes())
        binding.write_text('{"synthetic":true}\n')
        module.write_text('raise RuntimeError("mutated source")\n')
        with self.assertRaisesRegex(ValueError, 'source/plan SHA differs'):
            ns['load_checked_corrector'](lambda path: Path(path).read_bytes())

    def test_nested_closure_custody_cannot_override_existing_failure_or_accept_typed_one(self):
        parsed = tree('mr3_v22_multiepoch_closure_binary_review_v1.py')
        main = function(parsed, 'main')
        start = next(i for i, node in enumerate(main.body) if isinstance(node, ast.Try)
                     and 'corrector_module, corrector_binding' in ast.unparse(node))
        end = next(i for i, node in enumerate(main.body[start:], start)
                   if isinstance(node, ast.Expr) and 'check(corrector_review.get' in ast.unparse(node))
        definitions = [copy.deepcopy(node) for node in main.body if isinstance(node, ast.FunctionDef)
                       and node.name in ('read', 'check')]
        for base_failed, extra in ((False, True), (True, True), (False, False), (False, 1)):
            with self.subTest(base_failed=base_failed, extra=extra):
                prefix = self.root / ('case' + str(base_failed) + str(type(extra)) + str(extra))
                ns = {'Path': Path, 'hashlib': hashlib, 'json': json,
                      'a': SimpleNamespace(run=self.root, freeze='e' * 40), 'prefix': prefix,
                      'bindings': {}, 'errors': ['old mandatory failure'] if base_failed else []}
                module = SimpleNamespace(review=lambda *args, value=extra: {'passed': value})
                ns['load_checked_corrector'] = lambda read: (module, self.root / 'binding.json')
                exec(compile(ast.Module(body=definitions + copy.deepcopy(main.body[start:end+1]),
                                         type_ignores=[]), '<exact nested closure block>', 'exec'), ns)
                self.assertEqual(not ns['errors'], not base_failed and extra is True)
                self.assertEqual(json.loads(ns['corrector_output'].read_bytes())['passed'], extra)

    def test_34_original_receipts_stage_workloads_and_pending_admission_preserved(self):
        plan = json.loads((HERE.parent / 'predeclared_plan_v22.json').read_bytes())
        old_raw = (BASE.parent / 'predeclared_plan_v20.json').read_text()
        old_raw = old_raw.replace('report/assets/20261018_mr3_p2a0_v20',
                                  'report/assets/20261018_mr3_p2a0_v22_ray_box')
        old = json.loads(old_raw.replace('v20', 'v22').replace('V20', 'V22'))
        self.assertEqual([len(stage['required_audit_receipts']) for stage in plan['stages']], [10, 7, 10, 7])
        for key in ('max_api_records', 'max_submitted_script_decisions', 'max_total_wall_seconds',
                    'unchanged_gates', 'physical_response_criteria', 'angular_interface_criteria',
                    'angular_reset_criteria', 'settled_turn_criteria', 'drive_contract'):
            self.assertEqual(plan[key], old[key], key)
        # Evaluate actual entrypoint guards against a detached pending view;
        # this test remains valid when root later marks the reviewed plan ready.
        pending = copy.deepcopy(plan)
        pending['readiness'] = {'status': 'draft_not_native_admission',
                                'pending_bindings': ['not frozen']}
        for name in ('mr3_p2a0_v22_buildproof_preflight.py', 'mr3_p2a0_v22_launch_stage.py',
                     'mr3_p2a0_v22_audit_stage.py', 'mr3_p2a0_v22_run_matrix_v1.py',
                     'mr3_p2a0_v22_cross_stage_mapping_monitor_v1.py'):
            guards = [node.test for node in ast.walk(function(tree(name), 'main'))
                      if isinstance(node, ast.Assert) and 'readiness' in ast.unparse(node.test)]
            guards += [node.args[0] for node in ast.walk(function(tree(name), 'main'))
                       if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                       and node.func.id == 'require' and node.args
                       and 'readiness' in ast.unparse(node.args[0])]
            self.assertEqual(len(guards), 1, name)
            self.assertFalse(eval(compile(ast.Expression(body=copy.deepcopy(guards[0])),
                                          '<actual pending admission guard>', 'eval'),
                                  {'plan': pending, 'STAGES': ('interface', 'terminal',
                                                              'reset', 'deadline')}), name)
        self.assertEqual(len(plan['stages']), 4)
        for new, prior in zip(plan['stages'], old['stages']):
            for flag in ('--steps', '--workers', '--schedule'):
                self.assertEqual(new['command'][new['command'].index(flag)+1],
                                 prior['command'][prior['command'].index(flag)+1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
