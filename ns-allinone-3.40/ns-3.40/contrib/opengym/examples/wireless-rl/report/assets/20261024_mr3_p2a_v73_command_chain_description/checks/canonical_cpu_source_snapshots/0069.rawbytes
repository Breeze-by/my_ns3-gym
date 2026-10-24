"""Fixed one-stream received command-chain description. No control or physical verdict."""
import argparse,copy,hashlib,json,math,os,re,stat,subprocess,sys,time
from pathlib import Path
from decimal import Decimal
ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261024_mr3_p2a_v73_command_chain_description'
INPUT=ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v71/mr3_p2a_reach_v71_interface/worker0/episode001_open_101/motion_safety.jsonl'
OUTPUT=Path('/tmp/mr3_p2a_v73_command_chain_description_v1.json')
EVIDENCE_G='b3707dcf258c832f35ef60f47a5dc8dc52296629'
PREVIOUS_G='74c8f710114bac3c2c91a5a1df8ebc6c63ec7637'
EPOCH='mr3_p2a_reach_v71_interface_w0_e1_53a7eddb'
ROBOTS=('tb1','tb2','tb3')
SCHEMA='mr3-v73-fixed-motion-command-chain-description-v1'
SPEC_SCHEMA='mr3-v73-fixed-motion-command-chain-description-spec-v1'
STABLE=('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')
BEGIN_NS=39720000000
CLEANUP_NS=49720000000
END_NS=51720000000
LIMITS={'max_inputs':1,'max_encoded_bytes':536870912,'max_decoded_bytes':536870912,'max_line_bytes':8388608,'max_lines':2000000,'max_output_bytes':4194304,'max_selected_records':12000,'max_tick_rows':2400,'max_index_records':100000,'max_projected_index_bytes':134217728,'max_native_exemplars_per_robot':12,'max_error_examples':16,'max_kind_names':128}
INTERPRETATION_SOURCES={'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py': {'bytes': 58956, 'sha256': '65edd09d36b83081c17da7f3b46a0e69a81b972e99f8c669e173f7fba580a5f5'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_information.py': {'bytes': 70251, 'sha256': 'df40a2d3dbba04d123b59bb5c72394815c87dbdd7fe3d90a5ffb87c6d6b47fc1'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_authority.py': {'bytes': 18838, 'sha256': '3e7385710f2c1de53d79b94507ee156c4376e021690815e147f9c8e36553ad2a'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_runtime.py': {'bytes': 31562, 'sha256': '576c235901a51223f1d2723757f60c490045ba897d445d5c6fb3c739512a466b'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_safety_intent.py': {'bytes': 15514, 'sha256': '4d148ef0ad18c8474eaa0a6d898bf4e94177f4cd454ce5a2495d26c9b7ab75f1'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_episode.py': {'bytes': 1379, 'sha256': '9145d2ad23789b252e32f0afdfe18cf2eeec8e2c7e9ca7e89127a532288e411b'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py': {'bytes': 18129, 'sha256': '197ff4bfcca9f815e191dcddea7a2a6af46a033c68310e350b63ad9e48579a69'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_control_phase.py': {'bytes': 15078, 'sha256': '051b4e879daf8762af6f3252ca0e9c2857c0150ed7396eef9c9f2c523b992c85'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_drive_phase.py': {'bytes': 4429, 'sha256': '0525230f4719e7279826810f0c177f6a6317a961d50711ac76d8a0338f93d987'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_geometry.py': {'bytes': 9878, 'sha256': 'cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_velocity_metric.py': {'bytes': 5743, 'sha256': '0a7a4c9ee3de72c1fddaab2441d9bc7a8ad6c543725e8af0f6f18a6ed783fae5'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py': {'bytes': 25472, 'sha256': '06ca6ece92ca49072df9eedbdd5396148ca2e09d4f2560204448e460e3e73ae7'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_transport.py': {'bytes': 8466, 'sha256': '426d9b777c2150bb690de3266c973dedfc8fe8da3fa36c7bf37cbe3c31d70eca'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp': {'bytes': 49164, 'sha256': '89161707d2e11bb2c6748c410dbb9d485d90ae5ed4f01dafaa32043ffadb8f7e'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_gazebo_diff_drive.hpp': {'bytes': 3968, 'sha256': 'c86c9b3469e0d81c6a037840cb3c091411c023115c563f454d1ce4399ec08e64'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_drive_target.hpp': {'bytes': 2844, 'sha256': '4be4d77de247a5bcd427eb6948165e85098eb361030cf89d278d6df92e959d41'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_drive_feed.hpp': {'bytes': 5813, 'sha256': '693381dd6a7b4675e56b4a7da6d3ecf640bf85e9bef5775ff19785df3db5befa'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_odometry_json.hpp': {'bytes': 2043, 'sha256': '4b251bff9336a6005a4fff9b6a981286687e99cbff86bf8b3410163e32392c74'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/paired_wheel_slew.hpp': {'bytes': 3592, 'sha256': 'dca3dbaf01251cf7ffe167f1dabb23a45b4fc95d6ad317dcc3290ff50ecf9a1b'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_initial_zero_encoder_servo.hpp': {'bytes': 5117, 'sha256': '5db6b8d0885e667d158589aa02500617f3eede7391155cddaa1a5f366e1a4d52'}}

def require(value, message):
    if not value:
        raise ValueError(message)

def finite(value):
    return type(value) in (int, float) and math.isfinite(value)

def ns(value):
    require(finite(value) and value >= 0, 'invalid producer clock')
    return round(value*1e9)

def integer(value, low=0):
    require(type(value) is int and value >= low, 'invalid integer')
    return value

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def present(value, key):
    """Never turn absent, null, false, zero or an empty list into each other."""
    require(type(value) is dict,'field parent is not an object')
    return {'present':key in value, **({'value':copy.deepcopy(value[key])} if key in value else {})}

def self_identity():
    tail=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':os.getpid(),'parent':int(tail[1]),'group':int(tail[2]),'session':int(tail[3]),'start_ticks':int(tail[19])}

def fixed_file(path, limit, on_read=None):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.resolve(strict=True)==path,'noncanonical path')
    before=path.lstat();require(stat.S_ISREG(before.st_mode) and before.st_size<=limit,'not regular or over byte cap')
    with path.open('rb') as stream:
        require(tuple(getattr(os.fstat(stream.fileno()),k) for k in STABLE)==tuple(getattr(before,k) for k in STABLE),'opened identity differs')
        try:raw=stream.read(limit+1)
        except OSError:
            if on_read is not None:on_read(None)
            raise
        if on_read is not None:on_read(len(raw))
    require(len(raw)==before.st_size and tuple(getattr(path.lstat(),k) for k in STABLE)==tuple(getattr(before,k) for k in STABLE),'input changed')
    return raw,tuple(getattr(before,k) for k in STABLE)

def decode(raw):
    def unique(pairs):
        result={}
        for k,v in pairs:
            require(k not in result,"duplicate JSON member")
            result[k]=v
        return result
    def real(text):
        value=float(text);require(math.isfinite(value),"nonfinite JSON number");return value
    return json.loads(raw,object_pairs_hook=unique,parse_float=real,
        parse_constant=lambda _:(_ for _ in ()).throw(ValueError("nonfinite JSON constant")))


def vector(value):
    if value is None:return None
    require(type(value) is list and len(value)==2 and all(finite(v) for v in value),"invalid finite two-vector")
    return value


def sign_class(value):
    return "UNKNOWN" if not finite(value) else "zero" if value==0 else "positive" if value>0 else "negative"


def object_field(value,key):return value.get(key) if type(value) is dict else None


def counter():return {"records":0,"zero":0,"positive":0,"negative":0,"UNKNOWN":0,"forward_ge_0_08":0}


def count_v(out,value):
    out["records"]+=1;out[sign_class(value)]+=1
    if finite(value) and value>=.08:out["forward_ge_0_08"]+=1


class BoundExceeded(ValueError):pass


class Analyzer:
    """Bounded exact-key indexes, not a producer oracle or nearest-time matcher."""
    def __init__(self):
        self.raw={};self.decisions={};self.storage={};self.applied={};self.odom={}
        self.kinds={};self.errors=[];self.error_count=0;self.index_records=0;self.index_bytes=0
        self.selected=0;self.last_record_sequence=0;self.sequence_gaps=0;self.ignored_native_foreign_or_missing_epoch=0
        self.stats={n:{s:counter() for s in ("raw_received_v","effective_v","Reach_output_v","APPLIED_body_target_v","APPLIED_pair_rim_mean","EXACT_JOINED_APPLIED_body_target_v","EXACT_JOINED_APPLIED_pair_rim_mean")} for n in ROBOTS}
        self.reason_counts={n:{} for n in ROBOTS};self.authority_counts={n:{} for n in ROBOTS}
        self.native_callbacks={n:0 for n in ROBOTS};self.native_duplicates={n:0 for n in ROBOTS}
        self.odom_callbacks={n:0 for n in ROBOTS};self.odom_duplicates={n:0 for n in ROBOTS}
        self.unknown_generation="UNKNOWN_UNSTAMPED_TWIST"

    @staticmethod
    def in_window(clock):return BEGIN_NS<=clock<=END_NS

    def issue(self,ref,error):
        self.error_count+=1
        if len(self.errors)<LIMITS["max_error_examples"]:self.errors.append({"reference":ref,"error":str(error)})

    def insert(self,index,key,value):
        if key in index:
            if index is self.odom:
                require(index[key]["value"]["message_sha256"]==value["value"]["message_sha256"],"conflicting raw odom at exact source")
            else:
                require(canonical(index[key]["value"])==canonical(value["value"]),"conflicting exact stream identity")
            return False
        projected=len(canonical(value))
        if self.index_records+1>LIMITS["max_index_records"] or self.index_bytes+projected>LIMITS["max_projected_index_bytes"]:
            raise BoundExceeded("bounded exact-key index overflow")
        index[key]=value;self.index_records+=1;self.index_bytes+=projected
        return True

    def select(self):
        self.selected+=1
        if self.selected>LIMITS["max_selected_records"]:raise BoundExceeded("selected record bound exceeded")

    def feed(self,row,ref):
        require(type(row) is dict and row.get("schema")=="mr3-motion-safety-v1" and row.get("epoch")==EPOCH,"motion record schema/epoch differs")
        seq=integer(row.get("record_sequence"),1)
        require(seq>self.last_record_sequence,"record sequence duplicate/regression")
        if self.last_record_sequence and seq!=self.last_record_sequence+1:self.sequence_gaps+=1
        self.last_record_sequence=seq
        callback_ns=ns(row["sim_time_sec"]);kind=row.get("kind");payload=row.get("payload")
        require(type(kind) is str and type(payload) is dict,"record kind/payload type")
        if kind not in self.kinds and len(self.kinds)>=LIMITS["max_kind_names"]:raise BoundExceeded("kind count bound exceeded")
        self.kinds[kind]=self.kinds.get(kind,0)+1
        ref=dict(ref,record_sequence=seq,callback_clock_ns=callback_ns)
        if kind not in ("raw_request","reach_decision","reach_driver_ingress","own_odom"):return
        name=payload.get("robot");require(name in ROBOTS,"recognized stream robot differs")
        if kind=="raw_request":
            q=payload.get("request");require(type(q) is dict,"raw request object missing")
            input_seq=integer(q.get("sequence"),1);stamp=ns(q["received_stamp"])
            require(type(q.get("supported")) is bool,"raw supported type")
            v,w=q.get("v"),q.get("w")
            if q["supported"]:require(finite(v) and finite(w),"supported raw request nonfinite")
            item={"value":{"request_sha256":sha(canonical(q)),"v":v,"w":w,"received_ns":stamp,
                "supported":q["supported"],"publisher_valid":object_field(q.get("publisher_identity"),"valid")},"ref":ref}
            self.insert(self.raw,(name,input_seq),item)
            if self.in_window(stamp):self.select();count_v(self.stats[name]["raw_received_v"],v)
        elif kind=="reach_decision":
            clock=integer(payload.get("clock_ns"));decision_seq=integer(payload.get("decision_sequence"),1)
            q=payload.get("request");require(q is None or type(q) is dict,"decision request object type")
            qseq=None if q is None else integer(q.get("sequence"),1)
            effective=vector(payload.get("effective_request"));decision=payload.get("decision")
            require(type(decision) is dict,"Reach decision missing")
            output=vector(decision.get("output"));reason=decision.get("reason")
            require(reason is None or type(reason) is str,"reason type")
            permission=payload.get("motion_authority")
            require(permission is None or type(permission) is dict,"receiving authority object type")
            owner=None if permission is None else permission.get("owner")
            require(owner is None or type(owner) is dict,"receiving owner type")
            item={"value":{"clock_ns":clock,"decision_sequence":decision_seq,"request_sequence":qseq,
                "request_sha256":None if q is None else sha(canonical(q)),
                "request_received_ns":None if q is None else ns(q["received_stamp"]),
                "request_received_age_ns":None if q is None else clock-ns(q["received_stamp"]),
                "raw_vector":None if q is None or not(finite(q.get("v")) and finite(q.get("w"))) else [q["v"],q["w"]],
                "effective_request":effective,"output":output,"reason":reason,
                "receiving_permission":None if permission is None else permission.get("permission"),
                "receiving_state":None if permission is None else permission.get("state"),
                "authority_sequence":None if permission is None else permission.get("authority_sequence"),
                "recorded_receiving_owner":owner,"raw_goal_generation":None,
                "raw_goal_association":"UNKNOWN_UNSTAMPED_TWIST",
                "intent_role":object_field(payload.get("intent"),"role"),
                "tracker_role":object_field(payload.get("tracker"),"role"),
                "started":payload.get("started"),"ready":payload.get("ready")},"ref":ref}
            self.insert(self.decisions,(name,decision_seq,clock),item)
            if self.in_window(clock):
                self.select();count_v(self.stats[name]["effective_v"],None if effective is None else effective[0])
                count_v(self.stats[name]["Reach_output_v"],None if output is None else output[0])
                reason_key="UNKNOWN" if reason is None else reason
                require(len(self.reason_counts[name])<128 or reason_key in self.reason_counts[name],"reason dictionary bound")
                self.reason_counts[name][reason_key]=self.reason_counts[name].get(reason_key,0)+1
                state="UNKNOWN" if permission is None else str(permission.get("state","UNKNOWN"))
                self.authority_counts[name][state]=self.authority_counts[name].get(state,0)+1
        elif kind=="reach_driver_ingress":
            stream=payload.get("kind");message=payload.get("message")
            require(type(message) is dict,"driver feed message object")
            raw=payload.get("raw_json");require(type(raw) is str and canonical(decode(raw))==canonical(message),"wire JSON differs from logged native message")
            if message.get("epoch")!=EPOCH:
                self.ignored_native_foreign_or_missing_epoch+=1
                return  # Producer records this ingress before its own same-epoch early return.
            require(message.get("robot")==name,"same-epoch driver robot differs")
            publisher_valid=object_field(payload.get("publisher_identity"),"valid")
            if stream=="storage":
                require(message.get("schema")=="mr3-drive-target-consumed-v1","storage schema")
                ds=integer(message.get("decision_sequence"),1);source=integer(message.get("source_clock_ns"));cmd=integer(message.get("cmd_seq"),1)
                require(finite(message.get("linear_x")) and finite(message.get("angular_z")),"storage target nonfinite")
                self.insert(self.storage,(name,ds,source,cmd),{"value":dict(message,publisher_valid=publisher_valid),"ref":ref})
                if self.in_window(source):self.select()
            elif stream=="applied":
                require(message.get("schema")=="mr3-drive-applied-v1","APPLIED schema")
                source=integer(message.get("source_clock_ns"));act=integer(message.get("actuation_sequence"),1)
                integer(message.get("cmd_seq"),1);integer(message.get("dt_ns"),1)
                target=message.get("target");require(type(target) is dict and target.get("schema")=="mr3-drive-target-v1" and target.get("epoch")==EPOCH and target.get("robot")==name,"APPLIED target identity")
                integer(target.get("decision_sequence"),1);clock=integer(target.get("clock_ns"))
                require(clock<=source and finite(target.get("linear_x")) and finite(target.get("angular_z")),"APPLIED target endpoints")
                pairs=message.get("pairs");require(type(pairs) is list and len(pairs)==1,"fixed native pair count differs")
                pair=pairs[0];require(type(pair) is dict,"native pair object");require(type(pair.get("pair_index")) is int and pair["pair_index"]==0,"native pair index")
                for k in ("current_rim_mps","desired_rim_mps","applied_rim_mps"):vector(pair.get(k));require(pair.get(k) is not None,"native wheel vector missing")
                require(finite(pair.get("alpha")) and 0<=pair["alpha"]<=1 and finite(pair.get("max_acceleration_mps2")),"native limiter metadata")
                if self.in_window(source):
                    self.select();self.native_callbacks[name]+=1
                    inserted=self.insert(self.applied,(name,act,source),{"value":dict(message,publisher_valid=publisher_valid),"ref":ref})
                    if not inserted:self.native_duplicates[name]+=1
            elif stream!="calibration":raise ValueError("unknown native ingress stream")
        elif kind=="own_odom":
            message=payload.get("message");require(type(message) is dict,"own raw odom missing")
            h=message["header"]["stamp"];sec,nano=h["sec"],h["nanosec"]
            require(type(sec) is int and type(nano) is int and sec>=0 and 0<=nano<10**9,"odom integer source stamp")
            source=sec*10**9+nano;linear=message["twist"]["twist"]["linear"];angular=message["twist"]["twist"]["angular"]
            require(all(finite(v[k]) for v in (linear,angular) for k in ("x","y","z")),"raw odom nonfinite")
            if self.in_window(source):
                self.select();speed=math.hypot(linear["x"],linear["y"])
                value={"source_clock_ns":source,"input_sequence":payload.get("input_sequence"),
                    "planar_speed_mps":speed,"linear_xyz":[linear[k] for k in ("x","y","z")],
                    "angular_xyz":[angular[k] for k in ("x","y","z")],
                    "message_sha256":sha(canonical(message))}
                self.odom_callbacks[name]+=1
                if not self.insert(self.odom,(name,source),{"value":value,"ref":ref}):self.odom_duplicates[name]+=1

    def finish(self):
        ticks=[];join_counts={n:{} for n in ROBOTS}
        def note(name,status):join_counts[name][status]=join_counts[name].get(status,0)+1
        for (name,ds,clock),row in sorted(self.decisions.items(),key=lambda x:(x[0][2],x[0][0],x[0][1])):
            if not self.in_window(clock):continue
            value=row["value"];qseq=value["request_sequence"];raw=None if qseq is None else self.raw.get((name,qseq))
            status="UNKNOWN_ABSENT_REQUEST" if qseq is None else "UNKNOWN_MISSING_EXACT_RAW_REFERENCE" if raw is None else "EXACT_RAW_REQUEST" if raw["value"]["request_sha256"]==value["request_sha256"] else "CONFLICT_RAW_REQUEST"
            if raw is not None and status=="EXACT_RAW_REQUEST" and raw["ref"]["record_sequence"]>=row["ref"]["record_sequence"]:status="UNKNOWN_JOURNAL_CAUSAL_ORDER"
            note(name,status)
            ticks.append(dict(robot=name,**value,reference=row["ref"],raw_request_join=status,raw_request_reference=None if raw is None else raw["ref"]))
        if len(ticks)>LIMITS["max_tick_rows"]:raise BoundExceeded("control tick output bound exceeded")
        native={n:{"unique_APPLIED":0,"callback_records":self.native_callbacks[n],"exact_duplicates":self.native_duplicates[n],"target_join_counts":{},"storage_join_counts":{},"same_source_odom_count":0,"exemplars":{}} for n in ROBOTS}
        for (name,act,source),row in sorted(self.applied.items(),key=lambda x:(x[0][2],x[0][0],x[0][1])):
            value=row["value"];target=value["target"];key=(name,target["decision_sequence"],target["clock_ns"]);decision=self.decisions.get(key)
            expected=None if decision is None or decision["value"]["output"] is None else {"schema":"mr3-drive-target-v1","epoch":EPOCH,"robot":name,"clock_ns":key[2],"decision_sequence":key[1],"linear_x":decision["value"]["output"][0],"angular_z":decision["value"]["output"][1]}
            status="UNKNOWN_MISSING_EXACT_REACH_TARGET" if expected is None else "EXACT_REACH_TARGET_FIELDS" if canonical(expected)==canonical(target) else "CONFLICT_REACH_TARGET_FIELDS"
            if value.get("publisher_valid") is not True:status="UNKNOWN_NATIVE_PUBLISHER_IDENTITY"
            store=self.storage.get((name,key[1],key[2],value["cmd_seq"]))
            storage_status="UNKNOWN_MISSING_EXACT_STORAGE" if store is None else "EXACT_STORAGE_TARGET_FIELDS" if all(store["value"].get(k)==target[k] and type(store["value"].get(k)) is type(target[k]) for k in ("linear_x","angular_z")) else "CONFLICT_STORAGE_TARGET_FIELDS"
            if store is not None and store["value"].get("publisher_valid") is not True:storage_status="UNKNOWN_STORAGE_PUBLISHER_IDENTITY"
            pair=value["pairs"][0];rim_mean=sum(pair["applied_rim_mps"])/2
            require(finite(rim_mean),"native rim projection nonfinite")
            count_v(self.stats[name]["APPLIED_body_target_v"],target["linear_x"])
            count_v(self.stats[name]["APPLIED_pair_rim_mean"],rim_mean)
            if status=="EXACT_REACH_TARGET_FIELDS" and storage_status=="EXACT_STORAGE_TARGET_FIELDS":
                count_v(self.stats[name]["EXACT_JOINED_APPLIED_body_target_v"],target["linear_x"])
                count_v(self.stats[name]["EXACT_JOINED_APPLIED_pair_rim_mean"],rim_mean)
            out=native[name];out["unique_APPLIED"]+=1
            out["target_join_counts"][status]=out["target_join_counts"].get(status,0)+1
            out["storage_join_counts"][storage_status]=out["storage_join_counts"].get(storage_status,0)+1
            odom=self.odom.get((name,source));out["same_source_odom_count"]+=odom is not None
            example=dict(source_clock_ns=source,actuation_sequence=act,cmd_seq=value["cmd_seq"],target=target,
                actual_APPLIED_receipt_reference=row["ref"],Reach_target_join=status,
                Reach_reference=None if decision is None else decision["ref"],storage_join=storage_status,
                storage_reference=None if store is None else store["ref"],pair=pair,
                same_source_clock_odom=None if odom is None else odom,
                same_source_clock_is_not_proof_of_physical_effect=True,wheel_write_readback="UNKNOWN_NOT_IN_THIS_STREAM")
            tags=["first","last"]
            if target["linear_x"]>0:tags.append("first_positive_body_target")
            if rim_mean>0:tags.append("first_positive_rim_mean")
            if target["linear_x"]>0 and rim_mean>0 and status=="EXACT_REACH_TARGET_FIELDS" and storage_status=="EXACT_STORAGE_TARGET_FIELDS":tags.append("first_exact_joined_positive_target_and_rim")
            if status.startswith("UNKNOWN"):tags.append("first_unknown_target_join")
            if storage_status.startswith("UNKNOWN"):tags.append("first_unknown_storage_join")
            for tag in tags:
                if tag=="last" or tag not in out["exemplars"]:out["exemplars"][tag]=example
            if len(out["exemplars"])>LIMITS["max_native_exemplars_per_robot"]:raise BoundExceeded("native exemplar cap")
        odom_summary={}
        for name in ROBOTS:
            rows=[x for (n,_),x in self.odom.items() if n==name]
            odom_summary[name]=dict(unique_source_samples=len(rows),callback_records=self.odom_callbacks[name],exact_duplicate_messages=self.odom_duplicates[name],maximum_planar_speed_mps=max((x["value"]["planar_speed_mps"] for x in rows),default=None),
                maximum_abs_wz_radps=max((abs(x["value"]["angular_xyz"][2]) for x in rows),default=None),
                first=None if not rows else min(rows,key=lambda x:x["value"]["source_clock_ns"]),
                last=None if not rows else max(rows,key=lambda x:x["value"]["source_clock_ns"]),
                APPLIED_to_odom_causal_effect_join="UNKNOWN_NO_EXACT_EFFECT_REFERENCE")
        for streams in self.stats.values():
            for item in streams.values():item["availability"]="OBSERVED" if item["records"] else "UNKNOWN_ABSENT_OR_NO_EXACT_JOIN"
        raw_examples={n:{} for n in ROBOTS}
        for (name,sequence),row in sorted(self.raw.items(),key=lambda x:(x[1]["value"]["received_ns"],x[0])):
            if not self.in_window(row["value"]["received_ns"]):continue
            e=raw_examples[name];item=dict(input_sequence=sequence,**row)
            e.setdefault("first",item);e["last"]=item
            if finite(row["value"].get("v")) and row["value"]["v"]>0:e.setdefault("first_positive",item)
        return dict(raw_received_exemplars=raw_examples,robot_stream_counts=self.stats,Reach_reason_counts=self.reason_counts,receiving_state_counts=self.authority_counts,
            exact_raw_join_counts=join_counts,control_tick_rows=ticks,native_received_APPLIED=native,raw_own_odom=odom_summary,
            record_kind_counts=self.kinds,ignored_native_foreign_or_missing_epoch=self.ignored_native_foreign_or_missing_epoch,record_sequence_gap_count=self.sequence_gaps,semantic_error_count=self.error_count,
            semantic_error_examples=self.errors,indexed_records=self.index_records,indexed_projected_bytes=self.index_bytes,selected_records=self.selected,
            raw_goal_generation="UNKNOWN_UNSTAMPED_TWIST",adapter_publication_or_goal_owner_cross_stream_join="UNKNOWN_SINGLE_STREAM_ONLY",
            native_receipt_scope="logged original native message/rawJSON plus graph-at-callback identity; no packet authentication or loadedELF proof",
            physical_stop_or_continuous_bounds_replayed=False,actual_wheel_SetParam_or_readback_checked=False)

def analyze_stream(stream,*,expected_bytes,expected_sha256,deadline_ns,on_read=None):
    analyzer=Analyzer();digest=hashlib.sha256();count=lines=parse_errors=0;errors=[];complete=False;tail=True;stop=None
    while True:
        if time.monotonic_ns()>deadline_ns:stop="work deadline";break
        line=stream.readline(LIMITS["max_line_bytes"]+1)
        if not line:complete=True;break
        count+=len(line);digest.update(line);lines+=1;tail=line.endswith(b"\n")
        if on_read is not None:on_read(len(line))
        if count>LIMITS["max_encoded_bytes"] or lines>LIMITS["max_lines"] or len(line)>LIMITS["max_line_bytes"]:
            stop="input byte/line resource bound";break
        ref={"line":lines,"line_bytes":len(line),"line_sha256":sha(line)}
        try:
            require(bool(line.strip()),"blank JSONL row")
            row=decode(line)
        except (ValueError,TypeError,UnicodeError) as error:
            parse_errors+=1
            if len(errors)<LIMITS["max_error_examples"]:errors.append({"line":lines,"error":str(error)})
            continue
        try:analyzer.feed(row,ref)
        except BoundExceeded as error:stop=str(error);break
        except (ValueError,KeyError,TypeError,OverflowError) as error:analyzer.issue(ref,error)
    try:description=analyzer.finish()
    except BoundExceeded as error:description={};stop=str(error)
    except (ValueError,KeyError,TypeError,OverflowError) as error:description={};stop="finish: "+str(error)
    actual_sha=digest.hexdigest()
    passed=(complete and tail and stop is None and parse_errors==0 and analyzer.error_count==0
        and count==expected_bytes and actual_sha==expected_sha256)
    description.update(passed=passed,description_status="COMPLETE" if passed else "INCOMPLETE",
        complete_input_read=complete,raw_input_bytes_read=count,raw_input_bytes_read_known=True,
        input_hash_domain="whole_original_encoded_file" if complete else "returned_prefix_only",
        actual_input_sha256=actual_sha,input_size_matches_pin=count==expected_bytes,input_SHA_matches_pin=complete and actual_sha==expected_sha256,
        parsed_jsonl_rows=lines-parse_errors,observed_jsonl_lines=lines,parse_errors=parse_errors,parse_error_examples=errors,
        complete_newline_tail=tail,resource_or_finish_failure=stop)
    return description


def validate_admission(spec,freeze):
    require(spec.get("schema")==SPEC_SCHEMA,"fixed spec schema")
    require(spec.get("admitted") is True and type(spec.get("admitted")) is bool,"unadmitted single motion description")
    require(type(freeze) is str and re.fullmatch("[0-9a-f]{40}",freeze)
        and spec.get("execution_freeze")=="CLI_EXACT_PUSHED_FREEZE","exact new CLI freeze required")
    require(canonical(spec.get("activity_to_describe"))==canonical({"freeze":EVIDENCE_G,"actual_returncode":1}),"original native activity identity")
    require(canonical(spec.get("identity"))==canonical({"epoch":EPOCH,"original_freeze":EVIDENCE_G,"worker_id":0,"episode_index":1,"scene":"open","seed":101}),"fixed motion episode identity")
    rows=spec.get("inputs");require(type(rows) is list and len(rows)==1 and rows[0].get("path")==str(INPUT),"only one fixed original motion input")
    row=rows[0]
    require(row.get("encoding")=="plain" and type(row.get("expected_bytes")) is int and row["expected_bytes"]==507221955
        and row.get("expected_sha256")=="f27397fad35ca23d6957c6c41121fc548f3f4718ecbbfc90d906ddb064f7cd08"
        and row.get("max_encoded_bytes")==LIMITS["max_encoded_bytes"] and row.get("max_decoded_bytes")==LIMITS["max_decoded_bytes"],"fixed original motion pin/cap")
    require(canonical(spec.get("analysis_window_ns"))==canonical({"begin":BEGIN_NS,"cleanup_boundary":CLEANUP_NS,"observation_end":END_NS}),"fixed received-only selection window")
    require(canonical(spec.get("aggregate_limits"))==canonical(LIMITS) and type(spec.get("work_seconds")) is int and spec["work_seconds"]==240
        and type(spec.get("parent_seconds")) is int and spec["parent_seconds"]==300,"fixed prospective resource limits")
    require(canonical(spec.get("output"))==canonical({"path":str(OUTPUT),"native_or_physics_or_qualification_credit":False}),"fixed descriptive output")


def main(argv=None):
    began=time.monotonic_ns();identity=self_identity()
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--freeze",required=True)
    parser.add_argument("--spec",type=Path,required=True);parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv);require(args.output==OUTPUT and not OUTPUT.exists(),"exclusive fixed output required")
    result=dict(schema=SCHEMA,passed=False,description_status="INCOMPLETE",identity=identity,actual_argv=list(sys.argv),
        raw_input_bytes_read=0,raw_input_bytes_read_known=True,native_or_physics_or_qualification_credit=False,
        original_activity_passed={"present":False},original_evidence_freeze=EVIDENCE_G,
        original_FAIL_preserved=None,previous_description_passed=None,previous_description_execution_freeze=None,
        prior_consumption_disclosure="Original motion file was opaquely archived/hashed/restored. No claim of first byte read. This fixed standalone semantic description was not executed during preparation.")
    checked={};input_before=None
    try:
        require(Path(__file__).resolve()==A/"describe_motion_chain_v1.py" and args.spec==A/"description_spec_v1.json","canonical consumer/spec only")
        spec_raw,spec_stamp=fixed_file(args.spec,262144);spec=decode(spec_raw);validate_admission(spec,args.freeze)
        git=lambda *x:subprocess.check_output(["git",*x],cwd=ROOT,timeout=15)
        require(git("rev-parse","HEAD").decode().strip()==args.freeze==git("rev-parse","origin/main").decode().strip()
            and not git("status","--porcelain","--untracked-files=all"),"clean exact pushed freeze required")
        bindings=spec["source_bindings"]
        wanted={r["path"]:{"bytes":r["bytes"],"sha256":r["sha256"]} for r in bindings if r["path"] in INTERPRETATION_SOURCES}
        require(wanted==INTERPRETATION_SOURCES and len(bindings)==len(INTERPRETATION_SOURCES)+1
            and len({r["path"] for r in bindings})==len(bindings),"complete explicit interpretation/consumer source closure")
        for row in bindings:
            path=ROOT/row["path"];raw,stamp=fixed_file(path,1048576)
            require(len(raw)==row["bytes"] and sha(raw)==row["sha256"] and raw==git("show",args.freeze+":"+row["path"]),"current/newGit interpretation pin")
            checked[path]=(raw,stamp)
        require(str((A/"describe_motion_chain_v1.py").relative_to(ROOT)) in {r["path"] for r in bindings},"consumer source pin absent")
        require(spec_raw==git("show",args.freeze+":"+str(args.spec.relative_to(ROOT))),"actual spec absent from freeze")
        metadata={}
        for key in ("inventory","previous_accounting","fixed_input_reference"):
            row=spec[key];path=Path(row["path"]);raw,stamp=fixed_file(path,2097152)
            require(len(raw)==row["bytes"] and sha(raw)==row["sha256"] and raw==git("show",args.freeze+":"+str(path.relative_to(ROOT))),"closed metadata current/newGit pin")
            metadata[key]=decode(raw);checked[path]=(raw,stamp)
        ledger=metadata["previous_accounting"]
        require(ledger.get("passed") is True and ledger.get("activity_passed") is True and ledger.get("description_passed") is True
            and ledger.get("execution_freeze")==PREVIOUS_G and ledger.get("original_activity_execution_freeze")==EVIDENCE_G
            and ledger.get("original_activity_passed")=={"present":True,"value":False}
            and ledger.get("scientific_qualification_credit") is False
            and ledger.get("engineering_cumulative_seconds")=="112586.9296634976018","actual prior description ledger is not the original native result")
        result.update(original_activity_passed=ledger["original_activity_passed"],original_FAIL_preserved=True,
            previous_description_passed=ledger["description_passed"],previous_description_execution_freeze=ledger["execution_freeze"])
        refs=metadata["fixed_input_reference"];row=spec["inputs"][0]
        require(refs.get("schema")=="mr3-v73-fixed-input-references-from-actual-v71-archive-v1"
            and refs.get("evidence_freeze")==EVIDENCE_G and refs.get("inventory")==spec["inventory"]
            and type(refs.get("inputs")) is list and len(refs["inputs"])==1,"fixed original reference schema/scope")
        reference=refs["inputs"][0]
        require((reference.get("original_path"),reference.get("original_bytes"),reference.get("original_sha256"))
            ==(str(INPUT),row["expected_bytes"],row["expected_sha256"]),"original motion reference pin")
        entries=[x for x in metadata["inventory"]["entries"] if x.get("original")==str(INPUT)]
        require(len(entries)==1 and entries[0]["original_bytes"]==row["expected_bytes"]
            and entries[0]["original_sha256"]==row["expected_sha256"],"sole actual inventory membership")
        saved=entries[0]["source_stat_before"]
        require(entries[0]["source_stat_stable"] is True and saved==entries[0]["source_stat_after"]
            and saved==reference["original_source_stat_before"]==reference["original_source_stat_after"],"saved original identity differs")
        require(INPUT.resolve(strict=True)==INPUT and stat.S_ISREG(INPUT.lstat().st_mode),"fixed original/parent symlink forbidden")
        input_before=INPUT.lstat();require(tuple(getattr(input_before,k) for k in STABLE)==tuple(saved[k[3:]] for k in STABLE),"actual original identity changed")
        def note(count):result["raw_input_bytes_read"]+=count
        fd=os.open(INPUT,os.O_RDONLY|os.O_NOFOLLOW)
        with os.fdopen(fd,"rb") as stream:
            require(tuple(getattr(os.fstat(stream.fileno()),k) for k in STABLE)==tuple(getattr(input_before,k) for k in STABLE),"opened original identity differs")
            try:value=analyze_stream(stream,expected_bytes=row["expected_bytes"],expected_sha256=row["expected_sha256"],deadline_ns=began+240*10**9,on_read=note)
            except OSError:
                result["raw_input_bytes_read_known"]=False;raise
            require(tuple(getattr(os.fstat(stream.fileno()),k) for k in STABLE)==tuple(getattr(input_before,k) for k in STABLE),"opened original changed")
        result.update(value)
        result.update(passed_scope="complete bounded single-stream description; UNKNOWN/CONFLICT joins are retained, not physical or runtime-gate credit",execution_freeze=args.freeze,spec_sha256=sha(spec_raw),source_bindings=bindings,
            input_proofs=[{"path":str(INPUT),"bytes":value["raw_input_bytes_read"],"sha256":value["actual_input_sha256"]}])
    except Exception as error:result.update(passed=False,error=repr(error),description_status="INCOMPLETE")
    finally:
        try:
            for path,(_,stamp) in checked.items():require(tuple(getattr(path.lstat(),k) for k in STABLE)==stamp,"bound source/metadata changed")
            if input_before is not None:require(tuple(getattr(INPUT.lstat(),k) for k in STABLE)==tuple(getattr(input_before,k) for k in STABLE),"original poststat changed")
            if "spec_raw" in locals():require(args.spec.read_bytes()==spec_raw,"actual spec changed")
        except Exception as error:result.update(passed=False,postcheck_error=repr(error),description_status="INCOMPLETE_POSTCHECK")
        result["actual_work_seconds"]=(time.monotonic_ns()-began)/1e9
        if result["actual_work_seconds"]>240:result.update(passed=False,description_status="INCOMPLETE_WORK_CAP")
        raw=canonical(result)+b"\n"
        if len(raw)>LIMITS["max_output_bytes"]:
            result.pop("control_tick_rows",None);result.update(passed=False,description_status="INCOMPLETE_OUTPUT_CAP",omitted_result_bytes=len(raw));raw=canonical(result)+b"\n"
        require(len(raw)<=LIMITS["max_output_bytes"],"bounded failure output exceeds output cap")
        with OUTPUT.open("xb") as stream:stream.write(raw)
    return 0 if result["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
