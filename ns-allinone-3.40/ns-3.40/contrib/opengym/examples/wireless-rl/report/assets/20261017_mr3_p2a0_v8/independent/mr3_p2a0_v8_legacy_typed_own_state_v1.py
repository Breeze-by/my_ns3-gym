"""Stream compatibility check of typed own-state reconstruction on fixed v7 raw data."""
from pathlib import Path
import hashlib
import json
import time
from mr3_learning.audit_motion import ROBOTS, own_state, same_json

W = Path.cwd()
source = W / "mr3_learning/audit_motion.py"
raw_path = Path("/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v7_interface/worker0/episode001_open_101/motion_safety.jsonl")
output = W / "report/assets/20261017_mr3_p2a0_v8/independent/legacy_v7_typed_own_state_v1.json"
sha = lambda data: hashlib.sha256(data).hexdigest()
before = sha(source.read_bytes())
start = time.monotonic()
sources = {name: {} for name in ROBOTS}
sequences = {name: {"odom": 0, "tf": 0} for name in ROBOTS}
checked = {name: 0 for name in ROBOTS}
errors = []
digest, size = hashlib.sha256(), 0
with raw_path.open("rb") as stream:
    for line, raw in enumerate(stream, 1):
        digest.update(raw)
        size += len(raw)
        row = json.loads(raw)
        value = row["payload"]
        if row["kind"] in ("own_odom", "own_tf"):
            name = value["robot"]
            key = "odom" if row["kind"] == "own_odom" else "tf"
            sources[name][key] = value["message"]
            sequences[name][key] = value["input_sequence"]
        elif row["kind"] == "decision":
            name = value["robot"]
            expected = own_state(name, sources[name], sequences[name], row["epoch"])
            checked[name] += 1
            if not same_json(value["own_state"], expected):
                errors.append({"line": line, "robot": name, "clock_ns": value["clock_ns"]})
after = sha(source.read_bytes())
result = {"schema": "mr3-v8-legacy-typed-own-state-compatibility-v1", "passed": not errors and before == after,
          "checked_decisions": checked, "errors": errors, "audit_source_before": before,
          "audit_source_after": after, "input": {"path": str(raw_path), "bytes": size,
          "sha256": digest.hexdigest()}, "wall_sec": time.monotonic() - start,
          "scope": "Old real v7 own-state input reconstruction and strict numeric JSON type/sign compatibility only; no new task or full audit acceptance."}
with output.open("x") as stream:
    json.dump(result, stream, indent=2)
    stream.write("\n")
print(json.dumps(result))
raise SystemExit(0 if result["passed"] else 1)
