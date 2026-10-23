"""Only AST and artificial hook calls; original ROS source is never executed."""
import ast
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('fixed_integration_candidate', HERE/'fixed_integration_v1.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def methods(raw):
    tree = ast.parse(raw)
    return {cls.name+'.'+fn.name:ast.dump(fn) for cls in tree.body if isinstance(cls,ast.ClassDef)
            for fn in cls.body if isinstance(fn,ast.FunctionDef)}


class StaticIntegrationTests(unittest.TestCase):
    def test_two_fixed_source_projections_whole_inverse_and_only_owned_methods(self):
        for source, allowed in ((m.SUPERVISOR, 'Supervisor.reset'), (m.WORKER, 'Worker.__init__')):
            raw = m.bound_source(source)
            changed, edits = m.project(source, raw)
            inverse = changed.decode()
            for old, new in reversed(edits):
                inverse = inverse.replace(new, old)
            self.assertEqual(inverse.encode(), raw)
            original_methods, changed_methods = methods(raw), methods(changed)
            self.assertEqual({key for key in original_methods if original_methods[key] != changed_methods[key]}, {allowed})
            self.assertEqual(len(edits), 1 if source == m.SUPERVISOR else 2)
            ast.parse(changed)

    def test_adapter_transparent_arguments_return_exception_and_restoration(self):
        with tempfile.TemporaryDirectory(prefix='mr3-profile-hook-artificial-') as name:
            directory = Path(name)
            (directory/'profiles/adapter').mkdir(parents=True)
            source = directory/'artificial_adapter.py'
            source.write_text('# artificial only\n')
            value, error, seen = object(), RuntimeError('original hook exception'), []
            def original(*args, **kwargs):
                seen.append((args, kwargs))
                if kwargs.get('fail'):
                    raise error
                return value
            main = lambda: None
            module = SimpleNamespace(__file__=str(source), encode_snapshot=original, main=main)
            endpoint = SimpleNamespace(group='console_scripts',name='mr3_adapter',
                value='multi_robot_exploration.mr3_adapter:main',load=lambda:main)
            calls=[]
            def capture(lane, function, *args, **kwargs):
                calls.append((lane,function,args,kwargs))
                return function(*args, **kwargs)
            core = SimpleNamespace(PROGRAMS={'adapter':source}, SOURCES={'adapter':(source,'unused')},
                                   OWNED_EPISODE=directory, profiled_call=capture)
            def run(program, *, run_name):
                self.assertEqual(run_name, '__main__')
                self.assertIs(module.encode_snapshot(value, archive=value), value)
                with self.assertRaises(RuntimeError) as result:
                    module.encode_snapshot(value, fail=True)
                self.assertIs(result.exception, error)
                return {'original_program_return':value}
            m.install_role(core,'adapter')
            with mock.patch.object(m.importlib,'import_module',return_value=module), \
                 mock.patch.object(m,'REAL_RUN_PATH',side_effect=run), \
                 mock.patch.object(m,'bound_source',return_value=source.read_bytes()), \
                 mock.patch.object(m.importlib.metadata,'distribution',return_value=SimpleNamespace(entry_points=[endpoint])):
                result=core.runpy.run_path(str(source),run_name='__main__')
            self.assertIs(result['original_program_return'],value)
            self.assertIs(module.encode_snapshot,original)
            self.assertEqual([row[0] for row in calls],['encoder','encoder'])
            self.assertTrue(all(row[1] is original and row[2][0] is value for row in calls))
            self.assertIs(seen[0][1]['archive'],value)

    def test_worker_keeps_main_file_and_only_fixed_spin_and_prefix(self):
        raw=m.bound_source(m.WORKER)
        changed,_=m.project(m.WORKER,raw)
        tree=ast.parse(changed)
        threads=[node for node in ast.walk(tree) if isinstance(node,ast.Call)
                 and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name)
                 and node.func.value.id=='threading' and node.func.attr=='Thread']
        self.assertEqual(len(threads),1)
        keywords={item.arg:item.value for item in threads[0].keywords}
        self.assertEqual(ast.literal_eval(keywords['name']),'mr3_worker_ros')
        self.assertEqual(ast.literal_eval(keywords['daemon']),True)
        target=keywords['target']
        self.assertIsInstance(target,ast.Lambda)
        self.assertEqual(ast.literal_eval(target.body.args[0]),'ros_spin')
        self.assertEqual(target.body.args[1].id,'spin')
        self.assertEqual(len(target.body.args),2)
        self.assertIn('"--launch-prefix-filter", "^(motion_safety|mr3_adapter)$"',changed.decode())
        self.assertEqual(ast.dump(tree.body[-1]),ast.dump(ast.parse(raw).body[-1]))
        entry=ast.parse((HERE/'fixed_roles_entry_v1.py').read_bytes())
        self.assertIn("sys.path[0] = str(core.PROGRAMS[role].parent)", (HERE/'fixed_roles_entry_v1.py').read_text())
        self.assertIsInstance(entry.body[-1],ast.If)


if __name__ == '__main__':
    unittest.main()
