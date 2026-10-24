"""Artificial-only suite runner. It never calls the real consumer main."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location('v72_descriptor_tests',HERE/'test_describe_probe_v1.py')
t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(t))
value=dict(schema='mr3-v72-artificial-descriptor-cpu-result-v1',passed=r.wasSuccessful(),tests=r.testsRun,
    failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),identity=t.m.self_identity(),actual_argv=sys.argv,
    actual_consumer_main_invoked=False,original_inputs_opened_by_this_suite=0,native_or_scientific_credit=False)
with (HERE/'fixture_result_v1.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
raise SystemExit(0 if value['passed'] else 1)
