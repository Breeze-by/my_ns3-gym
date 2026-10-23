import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time
import unittest

ROOT = Path("/home/zhuyulab/ns3-workspace")
W = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(W))
sources = [*OUT.glob("*.py"), W / "mr3_learning/audit_reach_sensor_model.py",
           W / "mr3_learning/reach_gates.py", W / "mr3_learning/audit_action_trace.py",
           W / "mr3_learning/reach_audit_projection.py", W / "mr3_learning/supervisor.py",
           W / "mr3_learning/native_custody_reach.py",
           W / "mr3_learning/tests/test_audit_action_trace.py",
           ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot/models/turtlebot3_waffle/model.sdf"]


def hashes():
    return [{"path":str(path),"sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(set(sources))]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


before = hashes()
started = time.monotonic_ns()
sensor = load("mr3_learning._v60_sensor_candidate", OUT / "audit_reach_sensor_model.py")
tests = load("_v60_sensor_artificial_tests", OUT / "test_initial_encoder_sensor_inverse_v1.py")
tests.sensor = sensor
tests.old.sensor_audit = sensor
suite = unittest.TestSuite([
    unittest.defaultTestLoader.loadTestsFromTestCase(tests.old.ReachSensorModelTests),
    unittest.defaultTestLoader.loadTestsFromTestCase(tests.InitialEncoderSensorInverseTests)])
with (OUT / "artificial_cpu_console_v2.log").open("x") as stream:
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
after = hashes()
ended = time.monotonic_ns()
report = {"schema":"mr3-v60-sensor-inverse-artificial-cpu-v1",
          "passed":result.wasSuccessful() and before == after,
          "tests_run":result.testsRun,"failures":len(result.failures),"errors":len(result.errors),
          "source_before":before,"source_after":after,"source_unchanged":before == after,
          "started_monotonic_ns":started,"ended_monotonic_ns":ended,
          "wall_seconds":str((ended-started)/10**9),"python":sys.executable,
          "argv":sys.argv,"pid":os.getpid(),"native_inputs_opened":False,
          "native_or_qualification_credit":False}
(OUT / "artificial_cpu_result_v2.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({k:v for k,v in report.items() if k not in ("source_before","source_after")}))
raise SystemExit(0 if report["passed"] else 1)
