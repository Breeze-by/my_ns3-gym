"""Reviewed v8 execution pins and unchanged non-pin policy/reward audit logic."""
import ast
import hashlib
import importlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path("/home/zhuyulab/ns3-workspace")
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
BASE = "01cfa040dcb73f8931dd11d66b69ce765cb8412f"
REL = str((WIRELESS / "mr3_learning/audit_ppo.py").relative_to(ROOT))
sys.path.insert(0, str(WIRELESS))
audit = importlib.import_module("mr3_learning.audit_ppo")
old_raw = subprocess.check_output(["git", "show", BASE + ":" + REL], cwd=ROOT)
old_tree, new_tree = ast.parse(old_raw), ast.parse((ROOT / REL).read_text())

def find(tree, name):
    return next(n.value for n in tree.body if isinstance(n, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == name for t in n.targets))

def pins(node):
    return {getattr(audit, k.left.id) + ast.literal_eval(k.right): ast.literal_eval(v)
            for k, v in zip(node.keys, node.values)}

old_pins = pins(find(old_tree, "PREPARATION_RUNTIME_PINS"))
new_pins = pins(find(new_tree, "PREPARATION_RUNTIME_PINS"))
assert old_pins.keys() == new_pins.keys()
allowed = {audit.ROS + "src/multi_robot_exploration/multi_robot_exploration/" + n
           for n in ("motion_safety.py", "mr3_motion_safety.py")}
assert {p for p in new_pins if new_pins[p] != old_pins[p]} == allowed
old_exec = pins(find(old_tree, "EXECUTION_CONFIG_PINS"))
new_exec = pins(find(new_tree, "EXECUTION_CONFIG_PINS"))
assert old_exec.keys() == new_exec.keys()
assert {p for p in new_exec if new_exec[p] != old_exec[p]} == {
    str((WIRELESS / "MR3_ADAPTER_CONTRACT.md").relative_to(ROOT))}
for tree in (old_tree, new_tree):
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in (
                "ENV_DOCUMENT_SHA256", "PREPARATION_RUNTIME_PINS", "EXECUTION_CONFIG_PINS") for t in n.targets):
            n.value = ast.Constant("REVIEWED-PIN-ONLY")
assert ast.dump(old_tree) == ast.dump(new_tree)
reviewed = {**audit.EVALUATOR_PHASE_PINS, **audit.PREPARATION_RUNTIME_PINS,
            **audit.EXECUTION_CONFIG_PINS}
for name, digest in reviewed.items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
assert hashlib.sha256((WIRELESS / "MR3_ENV_CONTRACT.md").read_bytes()).hexdigest() == audit.ENV_DOCUMENT_SHA256
unchanged = [audit.REWARD_SOURCE, audit.OBSERVATION_SOURCE,
             str((WIRELESS / "MR3_TASK_CONTRACT.md").relative_to(ROOT)),
             str((WIRELESS / "mr3_learning/ppo.py").relative_to(ROOT)),
             str((WIRELESS / "mr3_learning/model.py").relative_to(ROOT))]
for name in unchanged:
    assert (ROOT / name).read_bytes() == subprocess.check_output(
        ["git", "show", BASE + ":" + name], cwd=ROOT), name
paths = [ROOT / "AGENTS.md", ROOT / "ros2_ws/ros2-multi-robot-automap/AGENTS.md",
         ROOT / "ros2_ws/ros2-multi-robot-automap/user_guide.md",
         ROOT / "ros2_ws/ros2-multi-robot-automap/launch_commands.md"]
paths += [WIRELESS / n for n in ("AGENTS.md", "RESEARCH_PLAN.md", "IMPLEMENTATION_PLAN.md",
          "MR3_ENV_CONTRACT.md", "MR3_ADAPTER_CONTRACT.md", "report/README.md",
          "report/20261017_mr3_p2a0_v7.md", "report/20261017_mr3_p2a0_v8.md")]
links = []
for path in paths:
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
        if target.startswith(("http:", "https:", "#", "app:", "plugin:")):
            continue
        dest = target.split("#", 1)[0]
        assert (path.parent / dest).exists(), (str(path), target)
        links.append([str(path.relative_to(ROOT)), target])
result = dict(schema="mr3-p2a0-v8-contract-static-v1", passed=True,
              base_source_freeze=BASE, source_status="precommit working bytes; no native credit",
              audit_sha256=hashlib.sha256((ROOT / REL).read_bytes()).hexdigest(),
              env_sha256=audit.ENV_DOCUMENT_SHA256, reviewed_pins=reviewed,
              non_pin_audit_ast_unchanged=True, unchanged_task_actor_reward=unchanged, links=links)
out = Path(sys.argv[1]); assert not out.exists()
out.write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(dict(passed=True, reviewed_pins=len(reviewed), links=len(links))))
