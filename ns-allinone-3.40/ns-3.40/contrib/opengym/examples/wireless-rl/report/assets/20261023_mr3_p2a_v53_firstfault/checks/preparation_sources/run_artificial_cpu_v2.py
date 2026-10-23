"""Only fixed synthetic CPU unittest modules; never invokes native inputs."""
import importlib.util
from pathlib import Path
import unittest

here = Path(__file__).resolve().parent
suite = unittest.TestSuite()
for name in ('test_firstfault_extract_v2', 'test_run_firstfault_v1'):
    spec = importlib.util.spec_from_file_location(name, here / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
assert suite.countTestCases() == 21
result = unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
