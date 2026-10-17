from collections import deque
import json
from pathlib import Path
import sys,time

run=Path(sys.argv[1]);output=Path(sys.argv[2]);robots=("tb1","tb2","tb3")
def rows(path):
    if not path.exists():return []
    raw=path.read_bytes();lines=raw.splitlines()
    if raw and not raw.endswith(b"\n"):lines=lines[:-1]
    return [json.loads(line)for line in lines if line.strip()]
def read(path):return json.loads(path.read_bytes())
result={"schema":"mr3-readonly-terminal-live-review-v1","run":str(run),"wall_monotonic_ns":time.monotonic_ns(),"episodes":[],"scope":"live diagnostics; pending at snapshot is not failure; final full audits remain required; no braking credit"}
pattern=sys.argv[3]if len(sys.argv)>3 else"worker*/episode*"
for ep in sorted(run.glob(pattern)):
    errors=[];queues={name:deque()for name in robots};sequences=dict.fromkeys(robots,0);actual=dict.fromkeys(robots,0);nonzero=dict.fromkeys(robots,0);maxv=dict.fromkeys(robots,0.);maxw=dict.fromkeys(robots,0.);decisions={};gids={name:set()for name in robots};previous=0
    for row in rows(ep/"motion_safety.jsonl"):
        if row["record_sequence"]!=previous+1:errors.append("motion record sequence")
        previous=row["record_sequence"];p=row["payload"]
        if row["kind"]=="decision":
            name=p["robot"];sequence=p["decision_sequence"]
            if sequence!=sequences[name]+1:errors.append("decision sequence "+name)
            sequences[name]=sequence;queues[name].append((sequence,p["decision"]["output"]));decisions[(name,sequence)]={"clock":p["clock_ns"],"actual_wall":None,"ready":p["ready"]}
        elif row["kind"]=="actual_cmd_vel":
            name=p["robot"];twist=p["twist"];pair=[twist["linear"]["x"],twist["angular"]["z"]];actual[name]+=1;maxv[name]=max(maxv[name],abs(pair[0]));maxw[name]=max(maxw[name],abs(pair[1]));nonzero[name]+=bool(pair[0])
            identity=p["publisher_identity"]
            if identity["scope"]!="graph_at_callback"or identity["valid"]is not True or len(identity["endpoints"])!=1:errors.append("actual identity "+name)
            else:
                endpoint=identity["endpoints"][0]
                if(endpoint["namespace"],endpoint["node"])!=("/","motion_safety"):errors.append("actual publisher "+name)
                gids[name].add(endpoint["endpoint_gid"])
            if not queues[name]:errors.append("actual without decision "+name);continue
            sequence,pair_expected=queues[name].popleft()
            if pair!=pair_expected or p["observed_decision_sequence"]!=sequence:errors.append("actual FIFO value/sequence "+name)
            decisions[(name,sequence)]["actual_wall"]=row["wall_monotonic_ns"]
    if(ep/"motion_topology.json").exists():
        topology=read(ep/"motion_topology.json")
        for name in robots:
            entries=topology["endpoints"][f"/{name}/cmd_vel"]
            if len(entries)!=1 or any(gid!=entries[0]["endpoint_gid"]for gid in gids[name]):errors.append("startup topology GID "+name)
    phases=rows(ep/"motion_phase_worker.jsonl");consumed=[];pending_phase=0;received={}
    for row in phases:
        ack=row["ack"];clock=ack["clock_ns"]
        if row["kind"]=="ack_received":received[clock]=ack
        elif row["kind"]=="ack_consumed":
            if received.get(clock)!=ack or row["worker_clock_ns"]!=clock or row["worker_physical_ns"]!=clock:errors.append("motion phase consumed exact clock")
            consumed.append(clock)
        for name,sequence in ack["decision_sequences"].items():
            decision=decisions.get((name,sequence))
            if decision is None or decision["actual_wall"]is None:pending_phase+=1;continue
            if decision["clock"]!=clock or decision["actual_wall"]>row["wall_monotonic_ns"]:errors.append("ACK before same-clock actual FIFO "+name)
        if ack.get("completion_scope")!="publication_and_local_topic_receipt":errors.append("motion completion scope")
    events=[]
    if(ep/"launch.log").exists():
        marker="MR3_ORDERED_SHUTDOWN "
        events=[json.loads(line.split(marker,1)[1])for line in(ep/"launch.log").read_text(errors="replace").splitlines()if marker in line]
    bad=[r for r in events if r.get("event")=="process_exited"and r.get("returncode")!=0]
    errors.extend("native nonzero exit "+str(r.get("process_name"))+":"+str(r.get("returncode"))for r in bad)
    row={"directory":str(ep),"decision_sequences":sequences,"actual_counts":actual,"pending_FIFO":{n:len(q)for n,q in queues.items()},"maximum_actual_abs_linear":maxv,"maximum_actual_abs_angular":maxw,"nonzero_actual_linear_counts":nonzero,"motion_phase_consumed_count":len(consumed),"last_consumed_clock_ns":consumed[-1]if consumed else None,"phase_refs_not_yet_seen_in_motion_snapshot":pending_phase,"native_started":sum(r.get("event")=="process_started"for r in events),"native_exited":sum(r.get("event")=="process_exited"for r in events),"native_complete":any(r.get("event")=="complete"for r in events),"errors":sorted(set(errors))}
    if(ep/"supervisor_shutdown.json").exists():
        proof=read(ep/"supervisor_shutdown.json");row["shutdown"]={k:proof[k]for k in("worker_returncode","forced_shutdown","failed_sample","remaining_owned_processes","remaining_owned_zombies")}
    result["episodes"].append(row)
result["benchmark_summary_exists"]=(run/"benchmark_summary.json").exists()
with output.open("x")as f:f.write(json.dumps(result,indent=2)+"\n")
print(json.dumps(result,indent=2))
