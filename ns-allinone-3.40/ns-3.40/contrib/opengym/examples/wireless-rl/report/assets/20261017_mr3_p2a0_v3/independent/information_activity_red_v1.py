"""Run the new integration test against the exact failed native producer Git bytes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType

ROOT = Path("/home/zhuyulab/ns3-workspace")
FREEZE = "96c201e0e258bd0fe192fc03c6716fc694b7a9b7"
RELATIVE = "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_information.py"
raw = subprocess.check_output(["git", "show", FREEZE + ":" + RELATIVE], cwd=ROOT)
name = "multi_robot_exploration.mr3_information"
module = ModuleType(name)
module.__file__ = str(ROOT / RELATIVE)
module.__package__ = "multi_robot_exploration"
sys.modules[name] = module
exec(compile(raw, FREEZE + ":" + RELATIVE, "exec"), module.__dict__)
print(json.dumps({"producer_freeze": FREEZE, "producer_sha256": hashlib.sha256(raw).hexdigest(),
                  "source": RELATIVE, "scope": "detached old producer CPU integration regression"}))
import pytest
sys.exit(pytest.main(["-q", "/tmp/test_mr3_information_activity.py"]))
