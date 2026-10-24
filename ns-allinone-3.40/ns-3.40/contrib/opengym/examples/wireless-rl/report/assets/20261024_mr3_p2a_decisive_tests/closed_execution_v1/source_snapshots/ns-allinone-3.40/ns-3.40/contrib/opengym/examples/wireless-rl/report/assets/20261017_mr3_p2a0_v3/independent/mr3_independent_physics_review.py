"""Independent raw-odom, observed-final-Twist and strict-close consumer; no ROS imports."""
import argparse
from bisect import bisect_left, bisect_right
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROBOTS=("tb1","tb2","tb3")
HORIZON_NS=780000000
PATH_BOUND_M=.144
MIN_COMMAND_SPAN_NS=100000000
MIN_INITIAL_SPEED=.05
REST_SPEED=.01
MAX_SOURCE_GAP_NS=100000000

def read(path,lines=False):
    path=Path(path)
    if not path.exists():path=Path(str(path)+".gz")
    data=path.read_bytes()
    if path.suffix==".gz":data=gzip.decompress(data)
    return [json.loads(x)for x in data.splitlines()if x.strip()]if lines else json.loads(data)

def ns(value):
    if type(value)not in(int,float)or not math.isfinite(value):raise ValueError("invalid timestamp")
    return round(value*1000000000)

def source_ns(header):
    s=header["stamp"]
    if type(s["sec"])is not int or type(s["nanosec"])is not int or not 0<=s["nanosec"]<1000000000:raise ValueError("invalid source stamp")
    return s["sec"]*1000000000+s["nanosec"]

def finite_vector(vector):
    values=[vector[k]for k in("x","y","z")]
    if any(type(v)not in(int,float)or not math.isfinite(v)for v in values):raise ValueError("nonfinite raw vector")
    return values

def identity_present(saved):
    try:
        s=(Path("/proc")/str(saved["pid"])/"stat").read_text().rsplit(")",1)[1].split()
        return int(s[19])==saved["start_ticks"]
    except(OSError,ValueError,IndexError):return False

def close_audit(episode,epoch):
    shutdown=read(episode/"supervisor_shutdown.json");summary=read(episode/"summary.json");nav=read(episode/"nav2_shutdown.json");native=read(episode/"native_stop.json")
    launch=(episode/"launch.log")
    if not launch.exists():text=gzip.decompress(Path(str(launch)+".gz").read_bytes()).decode(errors="replace")
    else:text=launch.read_text(errors="replace")
    marker="MR3_ORDERED_SHUTDOWN ";events=[json.loads(line.split(marker,1)[1])for line in text.splitlines()if marker in line]
    started={r["process_start_index"]:r for r in events if r.get("event")=="process_started"}
    exited={r["process_start_index"]:r for r in events if r.get("event")=="process_exited"}
    # The producer calls its launch-start event process_start; support its exact schema.
    if not started:started={r["process_start_index"]:r for r in events if r.get("event")=="process_start"}
    missing=[i for i in started if i not in exited]
    bad_exits=[r for r in exited.values()if r.get("returncode")!=0]
    live=[r for r in shutdown["owned_processes_seen"]if identity_present(r)]
    finalized=[(r["robot"],s["node"],s["state"]["id"])for r in nav["robots"]for s in r["states"]]
    errors=[]
    checks={"epoch":shutdown["epoch"]==summary["epoch"]==nav["epoch"]==epoch,"worker_return0":shutdown["worker_returncode"]==0,"no_forced":shutdown["forced_shutdown"]is False,"not_failed_sample":shutdown["failed_sample"]is False,"no_recorded_remaining":not shutdown["remaining_owned_processes"]and not shutdown["remaining_owned_zombies"],"no_live_saved_identity":not live,"launch_return0":summary["launch_returncode"]==0 and not summary["native_failures"],"native_server_clean":native["returncode"]==0 and native["server_clean_exit_recorded"]is True,"nav_finalized":not nav["failures"]and len(nav["robots"])==3 and all(r["shutdown"]["response"]["success"]is True for r in nav["robots"])and finalized and all(s[2]==4 for s in finalized),"ordered_complete":any(r.get("event")=="complete"and r.get("epoch")==epoch for r in events),"all_started_exited_zero":bool(started)and not missing and not bad_exits}
    errors=[k for k,v in checks.items()if not v]
    return {"passed":not errors,"errors":errors,"checks":checks,"processes_seen":len(shutdown["owned_processes_seen"]),"started_processes":len(started),"exited_processes":len(exited),"still_present_saved_identities":live,"finalized_nodes":finalized}

def measured_stop_response(ordered, clocks, clock, prior_span, next_nonzero, zero_w, category):
    k=bisect_right(clocks,clock)-1
    record={"event_clock_ns":clock,"zero_w":zero_w,"event_category":category,"prior_nonzero_command_span_ns":prior_span,"status":"insufficient_prior_movement","eligible":False}
    if k<0 or clock-ordered[k]["source_ns"]>MAX_SOURCE_GAP_NS:record["status"]="missing_fresh_stop_anchor";return record
    anchor=ordered[k];record["initial_observed_planar_speed"]=anchor["planar_speed"]
    if prior_span<MIN_COMMAND_SPAN_NS or anchor["planar_speed"]<MIN_INITIAL_SPEED:return record
    record["eligible"]=True;record["status"]="missing_rest_evidence"
    candidates=[s for s in ordered[k+1:]if clock<=s["source_ns"]<next_nonzero]
    rest_index=None
    for j in range(max(0,len(candidates)-2)):
        triple=candidates[j:j+3]
        if all(s["planar_speed"]<=REST_SPEED for s in triple):rest_index=j;break
    if rest_index is None:
        record["status"]="resumed_before_proven_rest"if next_nonzero<10**30 else"missing_rest_evidence"
        record["observed_nonrest_beyond_horizon"]=any(s["source_ns"]>clock+HORIZON_NS and s["planar_speed"]>REST_SPEED for s in candidates)
        return record
    rest=candidates[rest_index];record["rest_source_ns"]=rest["source_ns"];record["observed_latency_sec"]=(rest["source_ns"]-clock)/1e9
    # Interpolate a retrospective anchor from the bracketing raw positions;
    # polyline length is observed distance, not a continuous-path upper proof.
    if k+1>=len(ordered)or ordered[k+1]["source_ns"]-anchor["source_ns"]>MAX_SOURCE_GAP_NS:record["status"]="missing_dense_anchor";return record
    following=ordered[k+1];fraction=(clock-anchor["source_ns"])/(following["source_ns"]-anchor["source_ns"])
    point=[anchor["xy"][axis]+fraction*(following["xy"][axis]-anchor["xy"][axis])for axis in(0,1)]
    path=0.;last_clock=clock;maxgap=0
    for sample in candidates[:rest_index+1]:
        path+=math.dist(point,sample["xy"]);point=sample["xy"];maxgap=max(maxgap,sample["source_ns"]-last_clock);last_clock=sample["source_ns"]
    record["observed_odom_polyline_m"]=path;record["maximum_observation_gap_ns"]=maxgap
    record["observed_nonrest_beyond_horizon"]=any(s["source_ns"]>clock+HORIZON_NS and s["planar_speed"]>REST_SPEED for s in candidates[:rest_index])
    if maxgap>MAX_SOURCE_GAP_NS:record["status"]="insufficient_sample_continuity"
    elif path>PATH_BOUND_M or record["observed_nonrest_beyond_horizon"]:record["status"]="observed_bound_violation"
    elif rest["source_ns"]-clock>HORIZON_NS:record["status"]="sampling_boundary_unresolved"
    else:record["status"]="sampled_response_within_declared_bounds"
    return record

def robot_physics(samples,commands,release,end,cancels=None):
    ordered=[];errors=[]
    for sample in samples:
        if ordered and sample["source_ns"]<ordered[-1]["source_ns"]:errors.append("source_rewind")
        if ordered and sample["source_ns"]==ordered[-1]["source_ns"]:
            if sample!=ordered[-1]:errors.append("conflicting_duplicate_source")
            continue
        ordered.append(sample)
    task=[s for s in ordered if release<=s["source_ns"]<=end]
    clocks=[s["source_ns"]for s in ordered]
    def maximum(items,key):return max((s[key]for s in items),default=None)
    chords=[];gaps=[]
    for a,b in zip(task,task[1:]):
        dt=b["source_ns"]-a["source_ns"]
        if dt<=0:continue
        if a["frames"]!=b["frames"]:errors.append("odom_frame_changed");continue
        gaps.append(dt)
        chords.append({"start_source_ns":a["source_ns"],"end_source_ns":b["source_ns"],"speed_mps":math.dist(a["xy"],b["xy"])/(dt/1e9),"gap_ns":dt})
    violations={"planar_speed_over_.30":[s for s in task if s["planar_speed"]>.30],"angular_norm_over_1.2":[s for s in task if s["angular_norm"]>1.2],"chord_speed_over_.30":[s for s in chords if s["speed_mps"]>.30]}
    stops=[];active=None
    for i,command in enumerate(commands):
        clock=command["clock_ns"]
        if clock<release:continue
        if command["v"]!=0:
            if active is None:active=clock
            continue
        if active is None:continue
        begin=active;active=None
        next_nonzero=next((c["clock_ns"]for c in commands[i+1:]if c["v"]!=0),10**30)
        stops.append(measured_stop_response(ordered,clocks,clock,clock-begin,next_nonzero,command["w"],"A_final_linear_zero"))
    cancel_stops=[]
    for cancel in cancels or []:
        clock=cancel["clock_ns"]
        if clock<release:continue
        if not cancel["completion_evidence"]:
            cancel_stops.append({"event_category":"B_native_cancel_end_to_end","cancel_clock_ns":clock,"goal_id":cancel["goal_id"],"eligible":False,"status":"native_cancel_not_acknowledged"})
            continue
        prior_start=None
        for command in commands:
            if command["clock_ns"]>clock:break
            if command["v"]==0:prior_start=None
            elif prior_start is None:prior_start=command["clock_ns"]
        record={"event_category":"B_native_cancel_end_to_end","cancel_clock_ns":clock,"goal_id":cancel["goal_id"],"eligible":False,"status":"no_active_prior_linear_output"}
        if prior_start is None:cancel_stops.append(record);continue
        limit=cancel["new_goal_clock_ns"]
        post=[command for command in commands if command["clock_ns"]>=clock]
        first_zero=next((command["clock_ns"]for command in post if command["v"]==0),None)
        if first_zero is not None:
            resume=next((command["clock_ns"]for command in post if command["clock_ns"]>first_zero and command["v"]!=0),10**30)
            limit=min(limit,resume)
        record=measured_stop_response(ordered,clocks,clock,clock-prior_start,limit,None,"B_native_cancel_end_to_end")
        record.update(cancel_clock_ns=clock,goal_id=cancel["goal_id"],completion_evidence=cancel["completion_evidence"],new_goal_clock_ns=None if cancel["new_goal_clock_ns"]==10**30 else cancel["new_goal_clock_ns"])
        cancel_stops.append(record)
    eligible=[s for s in stops if s["eligible"]];credited=[s for s in eligible if s["status"]=="sampled_response_within_declared_bounds"]
    cancel_eligible=[s for s in cancel_stops if s["eligible"]]
    cancel_credited=[s for s in cancel_eligible if s["status"]=="sampled_response_within_declared_bounds"]
    combined=stops+cancel_stops
    return {"errors":errors,"raw_unique_odom_samples":len(ordered),"task_odom_samples":len(task),"maximum_planar_speed_all":maximum(ordered,"planar_speed"),"maximum_angular_norm_all":maximum(ordered,"angular_norm"),"maximum_abs_angular_z_all":maximum(ordered,"abs_wz"),"maximum_planar_speed_task":maximum(task,"planar_speed"),"maximum_angular_norm_task":maximum(task,"angular_norm"),"maximum_abs_angular_z_task":maximum(task,"abs_wz"),"maximum_raw_odom_chord_speed_task":maximum(chords,"speed_mps"),"maximum_task_source_gap_ns":max(gaps,default=None),"bound_violation_counts":{k:len(v)for k,v in violations.items()},"bound_violation_examples":{k:v[:3]for k,v in violations.items()},"linear_zero_events":len(stops),"eligible_stop_events":len(eligible),"credited_sampled_stop_events":len(credited),"maximum_credited_initial_planar_speed":max((s["initial_observed_planar_speed"]for s in credited),default=None),"maximum_cancel_credited_initial_planar_speed":max((s["initial_observed_planar_speed"]for s in cancel_credited),default=None),"hard_zero_evidence_complete":bool(credited),"cancel_end_to_end_evidence_complete":bool(cancel_credited),"native_cancel_events":len(cancel_stops),"eligible_cancel_stop_events":len(cancel_eligible),"credited_cancel_stop_events":len(cancel_credited),"cancel_stop_responses":cancel_stops,"physical_evidence_complete":bool(credited or cancel_credited)and not errors and not any(violations.values())and not any(s.get("observed_nonrest_beyond_horizon")or s["status"]=="observed_bound_violation"for s in combined),"stop_responses":stops,"scope":"finite sampled raw-odom response evidence at reported speed range; no continuous-path upper proof or claim that all zero commands are rest"}

def native_cancel_events(adapter,epoch):
    cancels={name:[]for name in ROBOTS};sent={}
    for index,row in enumerate(adapter):
        event=row["payload"]
        if row["kind"]=="native_send":sent[event["goal_id"]]=(event["robot"],index)
        elif row["kind"]=="native_cancel":
            name,goal=event["robot"],event["goal_id"]
            if row["epoch"]!=epoch or goal not in sent or sent[goal][0]!=name:raise ValueError("native cancel lacks original same-epoch native goal send")
            clock=ns(row["stamp"])
            if event.get("scope")!="native_cancel_call_attempt"or ns(event["stamp"])!=clock or name not in ROBOTS or type(goal)is not str or not goal:raise ValueError("native cancel call-attempt typed identity mismatch")
            replacement=min((ns(r["stamp"])for r in adapter[index+1:]if r["kind"]=="native_send"and r["payload"]["robot"]==name),default=10**30)
            evidence=[]
            for receipt in adapter[index+1:]:
                if receipt["kind"]!="delivery"or receipt["payload"].get("stream")!="receipt":continue
                wrapper=receipt["payload"];value=wrapper["payload"]
                if (receipt["epoch"]==epoch and wrapper["epoch"]==epoch and wrapper["source"]==name
                    and value.get("robot")==name and value.get("goal_id")==goal
                    and ns(receipt["stamp"])>=ns(wrapper["source_stamp"])>=clock
                    and type(wrapper["sequence"])is int and wrapper["sequence"]>0
                    and((value.get("type")=="cancel"and value.get("value")is True)
                        or(value.get("type")=="result"and value.get("value")==5))):
                    evidence.append({"kind":value["type"],"value":value["value"],"received_clock_ns":ns(receipt["stamp"]),"source_clock_ns":ns(wrapper["source_stamp"]),"delivery_sequence":wrapper["sequence"]})
            cancels[name].append({"clock_ns":clock,"goal_id":goal,"new_goal_clock_ns":replacement,"completion_evidence":evidence})
    return cancels

def audit_episode(episode):
    metadata=read(episode/"metadata.json");transitions=read(episode/"transitions.jsonl",True);epoch=metadata["epoch"];release=transitions[0]["info"]["release_time_ns"];physics=read(episode/"physics.jsonl",True);end=physics[-1]["end_time_ns"]
    odom={name:[]for name in ROBOTS};commands={name:[]for name in ROBOTS}
    for row in read(episode/"motion_safety.jsonl",True):
        if row["epoch"]!=epoch:raise ValueError("motion epoch mismatch")
        p=row["payload"]
        if row["kind"]=="own_odom":
            m=p["message"];linear=finite_vector(m["twist"]["twist"]["linear"]);angular=finite_vector(m["twist"]["twist"]["angular"]);position=finite_vector(m["pose"]["pose"]["position"])
            odom[p["robot"]].append({"source_ns":source_ns(m["header"]),"xy":position[:2],"planar_speed":math.hypot(*linear[:2]),"angular_norm":math.sqrt(sum(x*x for x in angular)),"abs_wz":abs(angular[2]),"frames":[m["header"]["frame_id"],m["child_frame_id"]]})
        elif row["kind"]=="actual_cmd_vel":
            v=p["twist"];commands[p["robot"]].append({"clock_ns":ns(row["sim_time_sec"]),"v":v["linear"]["x"],"w":v["angular"]["z"]})
    adapter=read(episode/"adapter.jsonl",True)
    cancels=native_cancel_events(adapter,epoch)
    robots={name:robot_physics(odom[name],commands[name],release,end,cancels[name])for name in ROBOTS};closure=close_audit(episode,epoch)
    return {"directory":str(episode),"epoch":epoch,"closure":closure,"robots":robots,"physical_evidence_complete":all(r["physical_evidence_complete"]for r in robots.values()),"passed":closure["passed"]and all(r["physical_evidence_complete"]for r in robots.values())}

def main():
    p=argparse.ArgumentParser();p.add_argument("directory",type=Path);p.add_argument("--output",type=Path,required=True);args=p.parse_args()
    if args.output.exists():p.error("output exists")
    episodes=sorted(args.directory.glob("worker*/episode*"))
    if not episodes and(args.directory/"metadata.json").exists():episodes=[args.directory]
    rows=[]
    for ep in episodes:
        try:rows.append(audit_episode(ep))
        except(Exception)as e:rows.append({"directory":str(ep),"passed":False,"error":repr(e)})
    result={"schema":"mr3-independent-raw-physics-closure-review-v1","passed":bool(rows)and all(r["passed"]for r in rows),"episodes":rows,"criteria":{"linear_stop_horizon_sec":.78,"observed_path_bound_m_per_robot":.144,"minimum_prior_nonzero_output_span_sec":.10,"minimum_initial_observed_planar_speed_mps":.05,"rest_planar_speed_mps":.01,"rest_consecutive_samples":3,"maximum_source_gap_sec":.10},"scope":"independent source-time sampled physical/strict-close evidence; A final-linear-zero and B actual-native-cancel end-to-end remain separate. Meaningful evidence in either is reported by type, never native-cancel as sudden-zero proof. Missing meaningful segments never PASS; sampled norms/chords do not prove continuous truth","script_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    with args.output.open("x")as f:f.write(json.dumps(result,indent=2)+"\n")
    print(json.dumps({"passed":result["passed"],"episodes":len(rows),"output":str(args.output)}));return 0 if result["passed"]else 1

if __name__=="__main__":sys.exit(main())
