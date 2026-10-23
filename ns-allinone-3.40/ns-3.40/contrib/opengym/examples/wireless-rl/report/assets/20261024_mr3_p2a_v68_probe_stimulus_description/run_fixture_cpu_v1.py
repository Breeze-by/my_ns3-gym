"""Run only the fixed artificial stdlib suite; never invoke the real consumer."""
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('test_fixed_description',HERE/'test_describe_probe_v1.py')
test=importlib.util.module_from_spec(spec);spec.loader.exec_module(test)
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test))
value={'schema':'mr3-v68-artificial-description-cpu-result-v1','passed':result.wasSuccessful(),
    'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),
    'identity':test.m.self_identity(),'actual_argv':sys.argv,'original_input_files_opened':0,
    'actual_consumer_main_invoked':False,'native_or_scientific_credit':False}
with (HERE/'fixture_result_v1.json').open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
raise SystemExit(0 if value['passed'] else 1)
