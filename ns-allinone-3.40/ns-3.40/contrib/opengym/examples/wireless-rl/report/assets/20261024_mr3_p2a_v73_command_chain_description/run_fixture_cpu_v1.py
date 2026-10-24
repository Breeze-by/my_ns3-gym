"""Artificial-only runner: never consumer main or real input."""
import importlib.util,json,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location("v73_toy_tests",HERE/"test_describe_motion_chain_v1.py")
t=importlib.util.module_from_spec(s);s.loader.exec_module(t)
r=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(t))
v=dict(schema="mr3-v73-artificial-motion-chain-tests-v1",passed=r.wasSuccessful(),tests=r.testsRun,failures=len(r.failures),errors=len(r.errors),skipped=len(r.skipped),identity=t.m.self_identity(),actual_argv=sys.argv,consumer_main_invoked=False,actual_original_inputs_opened=0,engineering_added_seconds="0",scientific_credit=False)
with (HERE/"fixture_result_v1.json").open("x") as f:json.dump(v,f,indent=2);f.write("\n")
raise SystemExit(0 if v["passed"] else 1)
