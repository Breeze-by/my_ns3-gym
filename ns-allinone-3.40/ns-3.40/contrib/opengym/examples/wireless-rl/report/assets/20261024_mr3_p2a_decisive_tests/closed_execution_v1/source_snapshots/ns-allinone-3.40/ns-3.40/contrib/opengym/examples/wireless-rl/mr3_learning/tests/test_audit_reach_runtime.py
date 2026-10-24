"""Independent artifact attacks; no production tracker or guard is an oracle."""
import copy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from mr3_learning import audit_reach_runtime as a


EPOCH, BEGIN, END = "independent-reach-reader", 1_000_000_000, 1_200_000_000
POSITIONS = {"tb1": (0.,0.), "tb2": (3.,0.), "tb3": (0.,3.)}


def raw(clock, robot="tb1", *, velocity=(0.,0.), xy=None):
    x,y = POSITIONS[robot] if xy is None else xy
    return {"header":{"stamp":{"sec":clock//10**9,"nanosec":clock%10**9},"frame_id":"odom"},
        "child_frame_id":"base_footprint", "pose":{"pose":{"position":{"x":x,"y":y,"z":0.},
        "orientation":{"x":0.,"y":0.,"z":0.,"w":1.}},"covariance":[0.]*36},
        "twist":{"twist":{"linear":{"x":velocity[0],"y":velocity[1],"z":0.},
        "angular":{"x":0.,"y":0.,"z":0.}},"covariance":[0.]*36}}


def target(robot, clock, seq, v=0., w=0.):
    return {"schema":"mr3-drive-target-v1","epoch":EPOCH,"robot":robot,"clock_ns":clock,
            "decision_sequence":seq,"linear_x":v,"angular_z":w}


def calibration(message, robot, seq):
    return {"schema":"mr3-odom-calibration-v1","epoch":EPOCH,"robot":robot,
        "source_clock_ns":a.source(message),"publication_sequence":seq,"coefficient_c":1.,
        "coefficient_s":0.,"odometry":copy.deepcopy(message),
        "conversion_contract":"float32-trig-binary64-rn-v1","producer_frame":"world-common-model-origin-v1"}


def intent(robot, clock, sequence, value):
    return {"schema":"mr3-safety-intent-v1","epoch":EPOCH,"robot":robot,"intent_sequence":sequence,
        "source_clock_ns":clock,"role":"HOLD","anchor":{"source_clock_ns":BEGIN,"odometry":raw(BEGIN,robot)},
        "admitted_signs":[],"lineage":{"release_clock_ns":BEGIN},"target":copy.deepcopy(value)}


def state(robot, clock, owner):
    message = raw(clock,robot)
    x,y=POSITIONS[robot]
    return {"epoch":EPOCH,"name":robot,"valid":True,"x":x,"y":y,"v":0.,"w":0.,"yaw":0.,
        "source_stamp":clock/10**9,"odom_source_stamp":clock/10**9,"tf_source_stamp":clock/10**9,
        "odometry":message,"transform":{"header":{"stamp":{"sec":(clock+200_000_000)//10**9,
            "nanosec":(clock+200_000_000)%10**9},"frame_id":"map"},
        "child_frame_id":"odom","transform":{"translation":{"x":0.,"y":0.,"z":0.},
        "rotation":{"x":0.,"y":0.,"z":0.,"w":1.}}},
        "safety":{"intent":copy.deepcopy(owner),"calibration":calibration(message,robot,(clock-BEGIN)//a.RAW+1)}}


def fixture():
    """Declared three-robot HOLD artifacts; no actual source/native credit."""
    metadata={"epoch":EPOCH,"safety_contract":a.CONTRACT,"quantum_steps":20,
        "execution_phase_protocol":"mr3-controlled-execution-phase-v2",
        "reset_handshake":"paused-controlled-state-peer-guard-storage-v2"}
    clocks=list(range(BEGIN,END+a.RAW,a.RAW))
    targets={n:[target(n,BEGIN,1)]+[target(n,t,k+2) for k,t in enumerate(clocks)] for n in a.ROBOTS}
    drivers,odoms={},{}
    for n in a.ROBOTS:
        config={"schema":"mr3-drive-actuation-v2","epoch":EPOCH,"robot":n,"kind":"configuration",
            "command_mode":"tagged","update_rate_hz":30,"actuation_algorithm":"measured_joint_rim_paired_common_fraction_v1",
            "max_acceleration_mps2":1.0,"num_wheel_pairs":1,"sim_time_ns":BEGIN-1}
        events=[]
        for t in targets[n]:
            events.append((t["clock_ns"],1,t["decision_sequence"],{"schema":"mr3-drive-actuation-v2",
                "epoch":EPOCH,"robot":n,"kind":"command_received","sim_time_ns":t["clock_ns"],
                "cmd_seq":t["decision_sequence"],"target_decision_sequence":t["decision_sequence"],
                "target_clock_ns":t["clock_ns"],"desired_v":0.,"desired_w":0.}))
        for k,t in enumerate(range(BEGIN+7_000_000,END+1,a.ACT),1):
            chosen=max((v for v in targets[n] if v["clock_ns"]<=t),key=lambda v:v["decision_sequence"])
            events.append((t,0,k,{"schema":"mr3-drive-actuation-v2","epoch":EPOCH,"robot":n,
                "kind":"actuation","sim_time_ns":t,"actuation_seq":k,"pair_index":0,
                "cmd_seq":chosen["decision_sequence"],"target_decision_sequence":chosen["decision_sequence"],
                "target_clock_ns":chosen["clock_ns"],"desired_v":0.,"desired_w":0.,"dt_ns":a.ACT,
                "current_rim_mps":[0.,0.],"desired_rim_mps":[0.,0.],"applied_rim_mps":[0.,0.],
                "alpha":1.0,"max_acceleration_mps2":1.0}))
        rows=[config]+[e[3] for e in sorted(events,key=lambda e:e[:3])]
        for k,row in enumerate(rows,1):row["record_sequence"]=k
        drivers[n]=rows
        odoms[n]=[{"schema":"mr3-world-odometry-publication-v1","epoch":EPOCH,"robot":n,
            "kind":"configuration","record_sequence":1,"provider":"WORLD","period_ns":a.RAW,
            "phase":"world_update_begin_before_actuation"}]
        for k,t in enumerate(clocks,1):
            odoms[n].append({"schema":"mr3-world-odometry-publication-v1","epoch":EPOCH,"robot":n,
                "kind":"publication","record_sequence":k+1,"publication_sequence":k,"source_clock_ns":t,
                "sim_time_ns":t,"odometry":raw(t,n),"odom_published":True,"odom_tf_published":True,
                "publication_scope":"actual_publisher_calls_returned_not_delivery"})
    motion=[]
    def record(kind,payload,clock):
        i=len(motion)+1
        motion.append({"schema":"mr3-motion-safety-v1","epoch":EPOCH,"record_sequence":i,
            "kind":kind,"sim_time_sec":clock/10**9,"wall_monotonic_ns":10**12+i*10,"payload":copy.deepcopy(payload)})
    def feed(n,kind,message,clock):
        suffix={"calibration":"odometry_calibration","storage":"status","applied":"applied"}[kind]
        gid=("%02x"%(a.ROBOTS.index(n)+1))*24
        identity={"scope":"graph_at_callback","packet_publisher_gid_available":False,"error":None,
            "topic":f"/{n}/mr3_drive/{suffix}","valid":True,
            "endpoints":[{"node_namespace":"/"+n,"node_name":"turtlebot3_diff_drive","topic_type":"std_msgs/msg/String","endpoint_gid":gid}]}
        record("reach_driver_ingress",{"robot":n,"kind":kind,"message":message,
            "raw_json":a.canonical(message),"publisher_identity":identity},clock)
    def publish(n,value,clock):
        record("reach_intent_publish",{"robot":n,"intent":value,"payload_sha256":a.digest(value),
            "scope":"actual_publisher_call_returned_not_delivery"},clock)
    def receipt(value):
        return {"schema":"mr3-drive-target-consumed-v1","epoch":EPOCH,"robot":value["robot"],
            "clock_ns":value["clock_ns"],"source_clock_ns":value["clock_ns"],
            "decision_sequence":value["decision_sequence"],"cmd_seq":value["decision_sequence"],"linear_x":0.,"angular_z":0.}
    record("configuration",{"robots":list(a.ROBOTS),"controlled_execution":True,"safety_contract":a.CONTRACT},BEGIN)
    current={}
    for n in a.ROBOTS:
        record("own_odom",{"robot":n,"input_sequence":1,"message":raw(BEGIN,n)},BEGIN)
        record("own_tf",{"robot":n,"input_sequence":1,
            "message":state(n,BEGIN,intent(n,BEGIN,1,targets[n][0]))["transform"]},BEGIN)
        feed(n,"calibration",calibration(raw(BEGIN,n),n,1),BEGIN)
        current[n]=intent(n,BEGIN,1,targets[n][0]);publish(n,current[n],BEGIN)
        feed(n,"storage",receipt(targets[n][0]),BEGIN)
    physics,worker,control,information=[],[],[],[]
    previous=BEGIN-1
    for k,t in enumerate(clocks):
        if k:
            for n in a.ROBOTS:
                record("own_odom",{"robot":n,"input_sequence":k+1,"message":raw(t,n)},t)
                record("own_tf",{"robot":n,"input_sequence":k+1,
                    "message":state(n,t,current[n])["transform"]},t)
                feed(n,"calibration",calibration(raw(t,n),n,k+1),t)
        for n in a.ROBOTS:
            for row in drivers[n]:
                if row["kind"]=="actuation" and previous<row["sim_time_ns"]<=t:
                    chosen=targets[n][row["target_decision_sequence"]-1]
                    message={"schema":"mr3-drive-applied-v1","epoch":EPOCH,"robot":n,
                        "source_clock_ns":row["sim_time_ns"],"actuation_sequence":row["actuation_seq"],
                        "cmd_seq":row["cmd_seq"],"dt_ns":a.ACT,"target":chosen,"pairs":[{field:row[field] for field in
                        ("pair_index","current_rim_mps","desired_rim_mps","applied_rim_mps","alpha","max_acceleration_mps2")}]}
                    feed(n,"applied",message,t)
        bundle={"epoch":EPOCH,"sequence":k+1,"robots":[state(n,t,current[n]) for n in a.ROBOTS],
            "safety_contract":a.CONTRACT}
        table={v["name"]:v["safety"] for v in bundle["robots"]}
        bundle["safety_table_sha256"]=a.digest(table)
        information.append({"kind":"state_publish","payload":{"message":copy.deepcopy(bundle)}})
        record("reach_state_ingress",{"message":bundle,"raw_json":a.canonical(bundle),
            "publisher_identity":{"scope":"graph_at_callback","packet_publisher_gid_available":False,
                "error":None,"topic":"/mr3/received/states","valid":True,"endpoints":[{
                "node_namespace":"/","node_name":"mr3_information","topic_type":"std_msgs/msg/String",
                "endpoint_gid":"ee"*24}]}},t)
        record("received_states",bundle,t)
        statuses,outputs,refs={},{},{}
        for n in a.ROBOTS:
            value=targets[n][k+1]
            current[n]=intent(n,t,k+2,value);publish(n,current[n],t)
            selected=next(v for v in bundle["robots"] if v["name"]==n)
            record("reach_decision",{"robot":n,"clock_ns":t,"decision_sequence":value["decision_sequence"],
                "intent":current[n],"own_state":selected,"received_peers":{v["name"]:v for v in bundle["robots"] if v["name"]!=n},
                "request":None,"decision":{"allow":False,"reason":"reach_hold","output":[0.,0.]},
                "started":True,"ready":True,"safety_table_sha256":bundle["safety_table_sha256"]},t)
            statuses[n]=receipt(value);outputs[n]={"linear_x":0.,"angular_z":0.}
            refs[n]={"intent_sequence":current[n]["intent_sequence"],"payload_sha256":a.digest(current[n])}
        for n in a.ROBOTS:feed(n,"storage",statuses[n],t)
        if t<END:
            request_id="boundary"+str(t)
            status={"schema":"mr3-motion-safety-status-v2","epoch":EPOCH,"clock_ns":t,"ready":True,
                "safety_contract":a.CONTRACT,"safety_table_sha256":bundle["safety_table_sha256"],"intent_refs":refs,
                "decision_sequences":{n:statuses[n]["decision_sequence"] for n in a.ROBOTS},"outputs":outputs}
            physical={"request_id":"q"+str(k),"epoch":EPOCH,"steps":20,"step_ns":1_000_000,
                "start_time_ns":t,"end_time_ns":t+a.RAW,"paused":True,"ok":True}
            physics.append(physical)
            worker.append({"kind":"advance_permitted","epoch":EPOCH,"request_id":physical["request_id"],
                "steps":20,"start_time_ns":t,"expected_motion":status,"receipts":statuses,
                "control_request_id":request_id,"wall_monotonic_ns":10**15+t})
            common={"epoch":EPOCH,"ok":True,"request_id":request_id,"clock_ns":t,"target_time_ns":t}
            sa=dict(common,schema="mr3-state-phase-ack-v2")
            pa=dict(common,schema="mr3-peer-phase-ack-v2",state_commit=copy.deepcopy(sa))
            ma=dict(common,schema="mr3-motion-control-ack-v2",status=copy.deepcopy(status))
            for component,ack in (("state",sa),("peer",pa),("motion",ma)):
                control.append({"kind":"ack_consumed","component":component,"ack":ack})
        previous=t
    return dict(metadata=metadata,motion=motion,drivers=drivers,odometry_rows=odoms,physics=physics,
                drive_worker=worker,control_worker=control,information=information,release_ns=BEGIN)


def stop_trace(end_offset, behavior):
    """Direct declared native trace isolates stop algebra from wire-shape gates.

    Qualified D at .98s, X at1.00s, real motion at1.027s, N at1.04s,
    full-zero storage at1.06s. A tiny1.10s target is overwritten at1.12s
    before its next actual write1.129s. It never ends the actual zero segment.
    """
    clocks=list(range(BEGIN,BEGIN+end_offset+a.RAW,a.RAW))
    targets={}
    raw_rows={}
    for k,t in enumerate(clocks):
        offset=t-BEGIN
        v=.1 if offset in (1_020_000_000,1_040_000_000) else (1e-300 if offset==1_100_000_000 else 0.)
        targets[k+1]=target("tb1",t,k+1,v)
        position,velocity=(0.,0.),(0.,0.)
        if behavior=="deadline" and offset>=1_060_000_000:
            position=(.0004*((offset-1_060_000_000)//a.RAW+1),0.);velocity=(.02,0.)
        elif behavior=="terminal" and offset>=1_120_000_000:
            position=(.00018*((offset-1_120_000_000)//a.RAW+1),0.);velocity=(.009,0.)
        elif behavior=="tail" and offset>=2_000_000_000:
            count=(offset-2_000_000_000)//a.RAW
            position=(.0001 if count%2==0 else 0.,0.)
            velocity=(.005 if count%2==0 else -.005,0.)
        raw_rows[t]={"source_clock_ns":t,"odometry":raw(t,xy=position,velocity=velocity)}
    events=[]
    for seq,value in targets.items():
        events.append((value["clock_ns"],1,seq,{"kind":"command_received","cmd_seq":seq,
            "sim_time_ns":value["clock_ns"],"target_clock_ns":value["clock_ns"],"target_decision_sequence":seq}))
    acts={}
    for seq,t in enumerate(range(BEGIN+7_000_000,clocks[-1]+1,a.ACT),1):
        chosen=max((v for v in targets.values() if v["clock_ns"]<=t),key=lambda v:v["decision_sequence"])
        row={"kind":"actuation","sim_time_ns":t,"pair_index":0,"cmd_seq":chosen["decision_sequence"],
            "target_decision_sequence":chosen["decision_sequence"],"actuation_seq":seq,
            "desired_v":chosen["linear_x"],"desired_w":0.}
        acts[seq]=[row];events.append((t,0,seq,row))
    records=[copy.deepcopy(e[3]) for e in sorted(events,key=lambda e:e[:3])]
    for k,row in enumerate(records,1):row["record_sequence"]=k
    native={"records":records,"odometry":raw_rows,"actuations":acts}
    stream={"raw":{},"calibration":{},"applied":{},"storage":{},"intent":{}}
    for seq,pairs in acts.items():
        p=pairs[0];arrival=(p["sim_time_ns"]-BEGIN+a.RAW-1)//a.RAW
        stream["applied"][seq]=(10*arrival+2,{"source_clock_ns":p["sim_time_ns"],"cmd_seq":p["cmd_seq"],
            "target":copy.deepcopy(targets[p["target_decision_sequence"]])})
    for k,t in enumerate(clocks):
        value=targets[k+1];message=raw_rows[t]["odometry"]
        stream["raw"][t]=[(10*k+1,message)]
        stream["calibration"][t]=(10*k+1,calibration(message,"tb1",k+1))
        stream["storage"][k+1]=(10*k+6,{"clock_ns":t,"cmd_seq":k+1,"linear_x":value["linear_x"],"angular_z":0.})
        declared=intent("tb1",t,k+1,value)
        offset=t-BEGIN
        if offset>=980_000_000:
            declared["anchor"]={"source_clock_ns":BEGIN+980_000_000,
                "odometry":raw_rows[BEGIN+980_000_000]["odometry"]}
            declared["role"]="D"
            declared["lineage"]={"anchor_intent_sequence":50}
        if offset>=1_000_000_000:
            declared.update(role="X",admitted_signs=[1])
            declared["lineage"]["transition_intent_sequence"]=51
        if offset>=1_040_000_000:
            declared["role"]="N"
            seq,pairs=max(((seq,p) for seq,p in acts.items() if p[0]["sim_time_ns"]<t),key=lambda p:p[1][0]["sim_time_ns"])
            p=pairs[0]
            declared["lineage"].update(actuation_sequence=seq,actuation_source_clock_ns=p["sim_time_ns"],
                causal_source_clock_ns=t,cmd_seq=p["cmd_seq"])
        stream["intent"][k+1]=(10*k+5,declared)
    return stream,native,clocks[-1]


class ReachAuditTests(unittest.TestCase):
    def test_declared_full_chain_passes_only_necessary_conditional_replay(self):
        result=a._audit_records(**fixture())
        self.assertTrue(result["passed"])
        self.assertFalse(result["continuous_physical_model_proved"])
        self.assertEqual(result["controlled_quanta"],10)

    def test_legacy_profile_and_old_schema_never_inherit_new_credit(self):
        for key,value in (("safety_contract","legacy"),("execution_phase_protocol","mr3-controlled-execution-phase-v1")):
            data=fixture();data["metadata"][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):a._audit_records(**data)

    def test_complete_payload_calibration_mutation_is_rejected(self):
        data=fixture()
        row=next(v for v in data["motion"] if v["kind"]=="reach_driver_ingress" and v["payload"]["kind"]=="calibration")
        row["payload"]["message"]["odometry"]["twist"]["covariance"][0]=.1
        with self.assertRaises(ValueError):a._audit_records(**data)

    def test_future_healthy_end_cannot_hide_an_intermediate_native_speed_peak(self):
        data=fixture();clock=BEGIN+40_000_000
        # Alter all bindings consistently: this defeats shape/equality-only readers.
        for rows in (data["odometry_rows"]["tb1"],):
            for row in rows:
                if row.get("source_clock_ns")==clock:row["odometry"]["twist"]["twist"]["linear"]["y"]=.02
        for row in data["motion"]:
            p=row["payload"]
            if row["kind"]=="own_odom" and p["robot"]=="tb1" and a.source(p["message"])==clock:
                p["message"]["twist"]["twist"]["linear"]["y"]=.02
            if row["kind"]=="reach_driver_ingress" and p["kind"]=="calibration" and p["robot"]=="tb1" and p["message"]["source_clock_ns"]==clock:
                p["message"]["odometry"]["twist"]["twist"]["linear"]["y"]=.02
                p["raw_json"]=a.canonical(p["message"])
        native=a.native_index(data["drivers"],data["odometry_rows"],EPOCH)
        streams=a.ingress_index(data["motion"],native,EPOCH)
        with self.assertRaisesRegex(ValueError,"residual/rest"):
            a.replay_robot("tb1",streams["tb1"],native["tb1"],EPOCH,BEGIN,END)

    def test_actual_pair_mutation_or_storage_substitution_has_no_native_credit(self):
        for kind in ("applied","storage"):
            data=fixture()
            row=next(v for v in data["motion"] if v["kind"]=="reach_driver_ingress" and v["payload"]["kind"]==kind)
            if kind=="applied":row["payload"]["message"]["pairs"][0]["applied_rim_mps"][0]=.1
            else:row["payload"]["message"]["cmd_seq"]+=100
            with self.subTest(kind=kind),self.assertRaises(ValueError):a._audit_records(**data)

    def test_one_missing_raw_receipt_is_not_inferred_from_its_calibration_copy(self):
        data=fixture()
        index=next(i for i,v in enumerate(data["motion"]) if v["kind"]=="own_odom" and v["payload"]["robot"]=="tb1")
        data["motion"].pop(index)
        for k,row in enumerate(data["motion"],1):row["record_sequence"]=k
        with self.assertRaises(ValueError):a._audit_records(**data)

    def test_actual_physical_tail_and_storage_before_each_advance_are_mandatory(self):
        for mutation in ("tail","storage","phase"):
            data=fixture()
            if mutation=="tail":
                data["physics"][-1]["end_time_ns"]+=a.RAW
            elif mutation=="storage":
                data["drive_worker"][0]["receipts"].pop("tb3")
            else:
                data["control_worker"][0]["ack"]["schema"]="mr3-state-phase-ack-v1"
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):a._audit_records(**data)

    def test_changed_graph_gid_and_zero_gid_are_rejected(self):
        for changed in ("00"*24,"fe"*24):
            data=fixture()
            rows=[v for v in data["motion"] if v["kind"]=="reach_driver_ingress" and v["payload"]["robot"]=="tb1" and v["payload"]["kind"]=="calibration"]
            rows[1]["payload"]["publisher_identity"]["endpoints"][0]["endpoint_gid"]=changed
            with self.subTest(gid=changed),self.assertRaises(ValueError):a._audit_records(**data)

    def test_two_frame_pair_math_cannot_mix_directions_and_scalar_distance(self):
        owner=intent("tb1",BEGIN,1,target("tb1",BEGIN,1))
        left=state("tb1",BEGIN,owner)
        right=state("tb2",BEGIN,intent("tb2",BEGIN,1,target("tb2",BEGIN,1)))
        self.assertTrue(a.independent_pair(left,right,BEGIN,EPOCH))
        for frame in ("map","raw"):
            p=copy.deepcopy(right)
            if frame=="map":p["x"],p["y"]=.54,0.
            else:
                p["odometry"]["pose"]["pose"]["position"]["x"]=.54
                p["safety"]["calibration"]["odometry"]=copy.deepcopy(p["odometry"])
                p["safety"]["intent"]["anchor"]["odometry"]=copy.deepcopy(p["odometry"])
            raw_x=p["odometry"]["pose"]["pose"]["position"]["x"]
            p["transform"]["transform"]["translation"]["x"]=p["x"]-raw_x
            p["x"]=p["transform"]["transform"]["translation"]["x"]+raw_x
            with self.subTest(frame=frame):self.assertFalse(a.independent_pair(left,p,BEGIN,EPOCH))

    def test_wrong_sign_longitudinal_is_part_of_full_two_dimensional_residual(self):
        message=raw(BEGIN,velocity=(-.02,0.));c=calibration(message,"tb1",1)
        self.assertGreater(a.residual_squared_upper(message,c,(1,)),a.Q(1,100)**2)
        self.assertLess(a.residual_squared_upper(message,c,(-1,)),a.Q(1,100)**2)

    def test_boolean_identity_cannot_equal_a_native_integer(self):
        for component in ("native", "motion", "storage", "applied"):
            data=fixture()
            if component=="native":data["drivers"]["tb1"][0]["record_sequence"]=True
            elif component=="motion":data["motion"][0]["record_sequence"]=True
            else:
                row=next(v for v in data["motion"] if v["kind"]=="reach_driver_ingress"
                         and v["payload"]["kind"]==component)
                key="cmd_seq" if component=="storage" else "actuation_sequence"
                row["payload"]["message"][key]=True
                row["payload"]["raw_json"]=a.canonical(row["payload"]["message"])
            with self.subTest(component=component),self.assertRaisesRegex(ValueError,"integer identity"):
                a._audit_records(**data)

    def test_D_filter_keeps_only_original_turn_under_both_complete_disk_frames(self):
        def disk_state(robot, position):
            value=intent(robot,BEGIN,2,target(robot,BEGIN,2))
            value.update(role="D",lineage={"anchor_intent_sequence":2})
            selected=state(robot,BEGIN,value)
            selected["odometry"]=raw(BEGIN,robot,xy=position)
            selected["safety"]["calibration"]=calibration(selected["odometry"],robot,1)
            selected["safety"]["intent"]["anchor"]["odometry"]=copy.deepcopy(selected["odometry"])
            selected["x"],selected["y"]=position
            return selected
        own=disk_state("tb1",(0.,0.))
        peers={"tb2":disk_state("tb2",(-.56,0.)),"tb3":disk_state("tb3",(0.,3.))}
        for w in (-.3,.3):
            emitted=copy.deepcopy(own["safety"]["intent"])
            emitted.update(intent_sequence=3,target=target("tb1",BEGIN,3,0.,w))
            decision={"intent":emitted,"request":{"v":.1,"w":w,"supported":True,
                "received_stamp":BEGIN/10**9,"publisher_identity":{"valid":True}},"decision":{"output":[0.,w],
                "reason":"linear_brake_preserve_requested_turn","component_filter":{
                "canonical_input":[.1,w],"rejected_transition_checks":{}}}}
            with self.subTest(w=w):
                a.admitted_command(decision,own,own,peers,BEGIN,EPOCH)
            for attack in ("reverse_turn","invent_turn","received_HOLD","new_anchor","raw_close","map_close"):
                d,local,received,p=map(copy.deepcopy,(decision,own,own,peers))
                if attack=="reverse_turn":d["decision"]["output"][1]=-w
                elif attack=="invent_turn":d["request"]["w"]=0.
                elif attack=="received_HOLD":received["safety"]["intent"]["role"]="HOLD"
                elif attack=="new_anchor":d["intent"]["anchor"]["odometry"]["pose"]["pose"]["position"]["x"]+=.001
                else:
                    close=p["tb2"]
                    if attack=="raw_close":
                        close["odometry"]["pose"]["pose"]["position"]["x"]=-.54
                        close["safety"]["calibration"]["odometry"]=copy.deepcopy(close["odometry"])
                        close["safety"]["intent"]["anchor"]["odometry"]=copy.deepcopy(close["odometry"])
                    else:close["x"]=-.54
                    rx=close["odometry"]["pose"]["pose"]["position"]["x"]
                    close["transform"]["transform"]["translation"]["x"]=close["x"]-rx
                    close["x"]=close["transform"]["transform"]["translation"]["x"]+rx
                with self.subTest(w=w,attack=attack),self.assertRaises(ValueError):
                    a.admitted_command(d,local,received,p,BEGIN,EPOCH)

    def test_partial_or_duplicate_json_tail_does_not_receive_a_verdict(self):
        with tempfile.TemporaryDirectory() as temporary:
            p=Path(temporary)/"records.jsonl"
            for payload in (b'{"x":1}',b'{"x":1,"x":2}\n'):
                p.write_bytes(payload)
                with self.subTest(payload=payload),self.assertRaises(ValueError):a.Inputs().read(Path(temporary),p.name,True)

    def test_unconsumed_normal_tiny_target_cannot_restart_global_stop_H(self):
        stream,native,end=stop_trace(1_860_000_000,"deadline")
        self.assertFalse(any(p[0]["desired_v"]==1e-300 for p in native["actuations"].values()))
        with self.assertRaisesRegex(ValueError,"stop deadline"):
            a.replay_robot("tb1",stream,native,EPOCH,BEGIN,end)

    def test_unconsumed_normal_tiny_target_cannot_erase_fixed_terminal_disk(self):
        stream,native,end=stop_trace(2_000_000_000,"terminal")
        self.assertFalse(any(p[0]["desired_v"]==1e-300 for p in native["actuations"].values()))
        with self.assertRaisesRegex(ValueError,"fixed terminal obligation"):
            a.replay_robot("tb1",stream,native,EPOCH,BEGIN,end)

    def test_finite_H_D_does_not_become_an_infinite_terminal_L1_budget(self):
        stream,native,end=stop_trace(32_000_000_000,"tail")
        result=a.replay_robot("tb1",stream,native,EPOCH,BEGIN,end)
        self.assertGreater(result["cumulative_path_diagnostic_m"],float(a.D))
        self.assertTrue(result["open_terminal_promise"])

    def test_CLI_report_refuses_overwrite_before_reading_any_episode(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/"report.json";output.write_text("preserved failure\n")
            with mock.patch.object(a,"audit_episode") as reader,contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(a.main([temporary,"--output",str(output)]),1)
                reader.assert_not_called()
            self.assertEqual(output.read_text(),"preserved failure\n")

    def test_CLI_failure_writes_false_report_and_returns_real_nonzero(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/"new-failure.json"
            with mock.patch.object(a,"audit_episode",side_effect=ValueError("retained source violation")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(a.main([temporary,"--output",str(output)]),1)
            result=json.loads(output.read_text())
            self.assertFalse(result["passed"])
            self.assertFalse(result["continuous_physical_model_proved"])
            self.assertIn("retained source violation",result["error"])

    def test_CLI_new_report_records_only_a_successful_necessary_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/"new-report.json"
            result={"passed":True,"independent_necessary_replay":True,"continuous_physical_model_proved":False}
            with mock.patch.object(a,"audit_episode",return_value=result),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(a.main([temporary,"--freeze","f"*40,"--output",str(output)]),0)
            self.assertEqual(json.loads(output.read_text()),result)


if __name__=="__main__":unittest.main(verbosity=2)
