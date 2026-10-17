import ast
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path("/home/zhuyulab/ns3-workspace")
W=ROOT/"ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
BASE="ba018fe3122c478836eb4e5da9c14306cd832c1b"
sha=lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
files=[W/"mr3_learning"/p for p in ["audit_controlled_physics.py","audit_preparation.py","audit_ppo.py","tests/test_audit_controlled_physics.py","tests/test_audit_controlled_readiness.py"]]
before={str(p.relative_to(ROOT)):sha(p) for p in files}
checks=[]
def original(p):
    return subprocess.check_output(["git","show",BASE+":"+str(p.relative_to(ROOT))],cwd=ROOT)

immutable=[ROOT/"ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py",W/"report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py",W/"report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v3.py"]
for p in immutable:
    checks.append({"check":"immutable original native/contact source unchanged","path":str(p.relative_to(ROOT)),"passed":p.read_bytes()==original(p),"sha256":sha(p)})
shared=files[0]
old={x.name:ast.dump(x,include_attributes=False) for x in ast.parse(original(shared)).body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
new={x.name:ast.dump(x,include_attributes=False) for x in ast.parse(shared.read_bytes()).body if isinstance(x,(ast.FunctionDef,ast.ClassDef))}
for name,value in old.items():
    checks.append({"check":"preexisting shared function AST unchanged","function":name,"passed":new.get(name)==value})
prep=files[1]
def fn(raw,name): return next(ast.dump(x,include_attributes=False) for x in ast.parse(raw).body if isinstance(x,ast.FunctionDef) and x.name==name)
checks.append({"check":"capacity exclusion rule AST unchanged","passed":fn(original(prep),"exclude_preparation_capacity_comparison")==fn(prep.read_bytes(),"exclude_preparation_capacity_comparison")})
fail=Path("/tmp/mr3_p2a0_v11_interface_full_audit.json")
checks.append({"check":"original V11 formal FAIL unchanged","passed":sha(fail)=="eef4cb52dd5c88bbff9f341c7af139f53bb5dbf4fd8f6060d9543881758d8740" and json.loads(fail.read_text())["passed"] is False,"sha256":sha(fail)})
after={str(p.relative_to(ROOT)):sha(p) for p in files}
report={"schema":"mr3-readiness-independent-readonly-review-v2","passed":all(x["passed"] for x in checks) and before==after,"source_before":before,"source_after":after,"source_unchanged":before==after,"checks":checks,"code_review":{"controlled_declarations":"Actual stored modern metadata must typed-canonically match call metadata before dispatch; exact controlled protocol plus new handshake required; true legacy result delegates original unchanged.","prewarm":"Original W7 ACK is a named subpredicate invoked only after actual controlled release proof; metadata is a copied view, raw file remains unchanged.","T0":"Three actual takeover requests/callbacks/publications/receipts, original zero completion, native command/status storage and actual 20-tick bootstrap retained.","T1":"Actual state+six side peer callbacks and publish windows, guard provenance replay and local receipts, three native stored targets, evaluator LIVE before first actual normal task advance, adapter projected state/task/snapshot/completion, seq0 release watermark.","map_boundary":"Snapshot request expected-map SHA, response watermarks, snapshot version and seq0 bind independently of earlier state bundle map. Later same-clock map delivery is permitted.","cache":"Additional raw input hashes captured before parsing and checked at end/reuse, motion proof also checked.","restoration":"Both native readiness and physics hooks restored in finally, including second installer exception.","DDS_window":"Receipt bounded by publish start; legitimate delivery before publish return remains permitted."},"development_findings":{"resolved":["Actual reward/evaluator/task_start field names corrected after early draft review.","Adapter state_update checked as actual source-defined projection rather than whole state bundle.","Mixed/missing controlled handshake cannot silently delegate optional legacy readiness.","Second installer failure restores first installed physics hook.","Initial LIVE consume explicitly precedes first normal task quantum.","Map atomics not invented across earlier state commit and later snapshot."],"withdrawn_inference":"Reviewer initially inferred no map fields in full state bundle from adapter projection. Direct actual state_publish sequence713 contains map_payload_sha256 and map_version; this inference was withdrawn before final review."},"limits":["Read-only code/AST/byte review only; no repeated full native audit or simulator/control call.","Focused tests and real closed-V11 composition diagnostic are runtime agent executions, not independently rerun here.","Raw monitor Bool and initial reward_ready packets are not archived; only source-bound ACK/worker/seq0 implication, no packet provenance claim.","Original V11 formal FAIL/contact-derived unavailable proof remains FAIL; this prospective observer change provides no new native, 95%, PPO or phase acceptance credit."]}
Path("/tmp/mr3_p2a0_v12_readiness_independent_review_v2.json").write_text(json.dumps(report,indent=2)+"\n")
print(json.dumps({"passed":report["passed"],"source_sha":before,"checks":checks}))
raise SystemExit(0 if report["passed"] else 1)
