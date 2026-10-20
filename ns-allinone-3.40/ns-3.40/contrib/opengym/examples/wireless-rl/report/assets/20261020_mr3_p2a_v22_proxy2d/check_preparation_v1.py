"""Static preparation evidence only; never launches a proxy/native environment."""
import ast
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

A = Path(__file__).resolve().parent
W = A.parents[2]
sys.path.insert(0, str(W))

from mr3_learning.proxy2d_activity import source_paths
from mr3_learning.supervisor import WORKSPACE as ROOT
plan = json.loads((A / "predeclared_plan_v1.json").read_text())
assert set(plan["source_bindings"]) == {str(p.relative_to(ROOT)) for p in source_paths()}
for name, digest in plan["source_bindings"].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
    if name.endswith(".py"):
        ast.parse((ROOT / name).read_text())
index = json.loads((A / "cpu_preparation_index_v1.json").read_text())
assert sum(index["final_distinct_checks"].values()) == index["final_total"] == 106
assert index["engineering_charge_seconds"] == "0"
for item in index["records"]:
    assert hashlib.sha256((W / item["path"]).read_bytes()).hexdigest() == item["sha256"]
assert not plan["qualification"] and not plan["training_eligible"]
assert plan["groups"] == [1, 4] and plan["max_env_step_attempts"] == 9000
assert sum(plan["phase_seconds"].values()) == plan["activity_seconds"] == 3600
assert not Path(plan["output"]).exists(), "formal activity has already started"
prior = subprocess.check_output(["git", "show", "HEAD:" + str((W / "log.md").relative_to(ROOT))], cwd=ROOT)
assert (W / "log.md").read_bytes().startswith(prior), "experiment history changed"
names = subprocess.check_output(["git", "diff", "--name-only"], cwd=ROOT, text=True).splitlines()
names += [str((W / "report/20261020_mr3_p2a_v22_proxy2d.md").relative_to(ROOT))]
links = 0
for name in names:
    path = ROOT / name
    if path.suffix != ".md":
        continue
    for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
        target = target.strip("<>").split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        if ":" in target and target.rsplit(":", 1)[-1].isdigit():
            target = target.rsplit(":", 1)[0]
        assert (path.parent / target).exists(), (name, target)
        links += 1
result = {"passed": True, "scope": "static CPU preparation only", "bound_sources": len(plan["source_bindings"]),
          "relative_links": links, "formal_activity_started": False, "final_fixture_checks": 106}
output = A / "preparation_static_result_v1.json"
with output.open("x") as stream:
    stream.write(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
