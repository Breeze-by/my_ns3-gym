"""Read-only partial-data diagnostics using the exact predeclared frozen consumer."""
import hashlib,importlib.util,json
from pathlib import Path
import sys,time

root=Path("/home/zhuyulab/ns3-workspace")
consumer=root/"ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v3/independent/mr3_independent_physics_review.py"
assert hashlib.sha256(consumer.read_bytes()).hexdigest()=="2516e394f60eac5dd24fd66b51c4c48fc37245090eb1626ebe1c7a3a23f8bafb"
spec=importlib.util.spec_from_file_location("frozen_independent_physics_live",consumer);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
run=Path(sys.argv[1]);output=Path(sys.argv[2]);result={"schema":"mr3-frozen-physics-live-diagnostic-v1","run":str(run),"wall_monotonic_ns":time.monotonic_ns(),"episodes":[],"scope":"partial live inputs; missing/pending may resolve later; only observed violations are alerts, no acceptance credit"}
def rows(path):
 if not path.exists():return[]
 raw=path.read_bytes();lines=raw.splitlines()
 if raw and not raw.endswith(b"\n"):lines=lines[:-1]
 return[json.loads(line)for line in lines if line.strip()]
for ep in sorted(run.glob("worker*/episode*")):
 if(ep/"supervisor_shutdown.json").exists():result["episodes"].append({"directory":str(ep),"stage":"closed; use full frozen consumer"});continue
 transitions=rows(ep/"transitions.jsonl")
 if not transitions:result["episodes"].append({"directory":str(ep),"stage":"startup before returned reset"});continue
 try:
  metadata=json.loads((ep/"metadata.json").read_bytes());release=transitions[0]["info"]["release_time_ns"];physics=rows(ep/"physics.jsonl");end=physics[-1]["end_time_ns"];odom={name:[]for name in module.ROBOTS};commands={name:[]for name in module.ROBOTS}
  for row in rows(ep/"motion_safety.jsonl"):
   if row["epoch"]!=metadata["epoch"]:raise ValueError("epoch mismatch")
   p=row["payload"]
   if row["kind"]=="own_odom":
    m=p["message"];linear=module.finite_vector(m["twist"]["twist"]["linear"]);angular=module.finite_vector(m["twist"]["twist"]["angular"]);position=module.finite_vector(m["pose"]["pose"]["position"])
    odom[p["robot"]].append({"source_ns":module.source_ns(m["header"]),"xy":position[:2],"planar_speed":module.math.hypot(*linear[:2]),"angular_norm":module.math.sqrt(sum(x*x for x in angular)),"abs_wz":abs(angular[2]),"frames":[m["header"]["frame_id"],m["child_frame_id"]]})
   elif row["kind"]=="actual_cmd_vel":
    t=p["twist"];commands[p["robot"]].append({"clock_ns":module.ns(row["sim_time_sec"]),"v":t["linear"]["x"],"w":t["angular"]["z"]})
  cancel=module.native_cancel_events(rows(ep/"adapter.jsonl"),metadata["epoch"])
  robots={name:module.robot_physics(odom[name],commands[name],release,end,cancel[name])for name in module.ROBOTS}
  summary={name:{k:v[k]for k in("errors","maximum_planar_speed_task","maximum_angular_norm_task","maximum_raw_odom_chord_speed_task","maximum_task_source_gap_ns","bound_violation_counts","eligible_stop_events","credited_sampled_stop_events","native_cancel_events","eligible_cancel_stop_events","credited_cancel_stop_events")}for name,v in robots.items()}
  for name,v in robots.items():summary[name]["observed_stop_bound_violations"]=[e for e in v["stop_responses"]+v["cancel_stop_responses"]if e.get("eligible")and(e.get("observed_nonrest_beyond_horizon")or e["status"]=="observed_bound_violation")]
  result["episodes"].append({"directory":str(ep),"stage":"active returned reset","last_returned_snapshot":transitions[-1]["snapshot"]["source_stamp"],"physics_end_ns":end,"robots":summary})
 except(Exception)as error:result["episodes"].append({"directory":str(ep),"diagnostic_error":repr(error)})
with output.open("x")as f:f.write(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
