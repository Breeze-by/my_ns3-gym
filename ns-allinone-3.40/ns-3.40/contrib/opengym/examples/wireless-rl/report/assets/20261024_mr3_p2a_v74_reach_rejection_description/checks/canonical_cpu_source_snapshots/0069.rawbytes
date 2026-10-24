"""Fixed tb3 received Reach rejection description. No mathematical or physical verdict."""
import argparse,copy,hashlib,json,math,os,re,stat,subprocess,sys,time
from pathlib import Path
from decimal import Decimal
ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261024_mr3_p2a_v74_reach_rejection_description'
INPUT=ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v71/mr3_p2a_reach_v71_interface/worker0/episode001_open_101/motion_safety.jsonl'
OUTPUT=Path('/tmp/mr3_p2a_v74_reach_rejection_description_v1.json')
EVIDENCE_G='b3707dcf258c832f35ef60f47a5dc8dc52296629'
PREVIOUS_G='45396954ed2612980859cff4629af1e6a662114c'
EPOCH='mr3_p2a_reach_v71_interface_w0_e1_53a7eddb'
ROBOTS=('tb1','tb2','tb3')
SCHEMA='mr3-v74-fixed-reach-rejection-description-v1'
SPEC_SCHEMA='mr3-v74-fixed-reach-rejection-description-spec-v1'
STABLE=('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')
BEGIN_NS=44720000000
CLEANUP_NS=49720000000
END_NS=49720000000
LIMITS={'max_inputs': 1, 'max_encoded_bytes': 536870912, 'max_decoded_bytes': 536870912, 'max_line_bytes': 8388608, 'max_lines': 2000000, 'max_output_bytes': 4194304, 'max_selected_records': 12, 'max_candidate_records': 1024, 'max_candidate_bytes': 33554432, 'max_values_per_margin': 1024, 'max_error_examples': 16, 'max_kind_names': 128}
INTERPRETATION_SOURCES={'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/motion_safety.py': {'bytes': 58956, 'sha256': '65edd09d36b83081c17da7f3b46a0e69a81b972e99f8c669e173f7fba580a5f5'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_information.py': {'bytes': 70251, 'sha256': 'df40a2d3dbba04d123b59bb5c72394815c87dbdd7fe3d90a5ffb87c6d6b47fc1'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_authority.py': {'bytes': 18838, 'sha256': '3e7385710f2c1de53d79b94507ee156c4376e021690815e147f9c8e36553ad2a'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_runtime.py': {'bytes': 31562, 'sha256': '576c235901a51223f1d2723757f60c490045ba897d445d5c6fb3c739512a466b'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_safety_intent.py': {'bytes': 15514, 'sha256': '4d148ef0ad18c8474eaa0a6d898bf4e94177f4cd454ce5a2495d26c9b7ab75f1'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_episode.py': {'bytes': 1379, 'sha256': '9145d2ad23789b252e32f0afdfe18cf2eeec8e2c7e9ca7e89127a532288e411b'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py': {'bytes': 18129, 'sha256': '197ff4bfcca9f815e191dcddea7a2a6af46a033c68310e350b63ad9e48579a69'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_control_phase.py': {'bytes': 15078, 'sha256': '051b4e879daf8762af6f3252ca0e9c2857c0150ed7396eef9c9f2c523b992c85'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_drive_phase.py': {'bytes': 4429, 'sha256': '0525230f4719e7279826810f0c177f6a6317a961d50711ac76d8a0338f93d987'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_geometry.py': {'bytes': 9878, 'sha256': 'cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_velocity_metric.py': {'bytes': 5743, 'sha256': '0a7a4c9ee3de72c1fddaab2441d9bc7a8ad6c543725e8af0f6f18a6ed783fae5'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py': {'bytes': 25472, 'sha256': '06ca6ece92ca49072df9eedbdd5396148ca2e09d4f2560204448e460e3e73ae7'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_transport.py': {'bytes': 8466, 'sha256': '426d9b777c2150bb690de3266c973dedfc8fe8da3fa36c7bf37cbe3c31d70eca'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp': {'bytes': 49164, 'sha256': '89161707d2e11bb2c6748c410dbb9d485d90ae5ed4f01dafaa32043ffadb8f7e'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_gazebo_diff_drive.hpp': {'bytes': 3968, 'sha256': 'c86c9b3469e0d81c6a037840cb3c091411c023115c563f454d1ce4399ec08e64'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_drive_target.hpp': {'bytes': 2844, 'sha256': '4be4d77de247a5bcd427eb6948165e85098eb361030cf89d278d6df92e959d41'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_drive_feed.hpp': {'bytes': 5813, 'sha256': '693381dd6a7b4675e56b4a7da6d3ecf640bf85e9bef5775ff19785df3db5befa'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_odometry_json.hpp': {'bytes': 2043, 'sha256': '4b251bff9336a6005a4fff9b6a981286687e99cbff86bf8b3410163e32392c74'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/paired_wheel_slew.hpp': {'bytes': 3592, 'sha256': 'dca3dbaf01251cf7ffe167f1dabb23a45b4fc95d6ad317dcc3290ff50ecf9a1b'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_initial_zero_encoder_servo.hpp': {'bytes': 5117, 'sha256': '5db6b8d0885e667d158589aa02500617f3eede7391155cddaa1a5f366e1a4d52'}, 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_reach_support.py': {'bytes': 12236, 'sha256': 'dc32cb48831dc333a9a4674ee83cce940e35a655a1b1fb9c5e6ba9b10be13966'}}

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
    """Original logged certificates only. No geometry evaluation or cross-row join."""
    def __init__(self):
        self.kinds={};self.errors=[];self.error_count=0;self.last_record_sequence=0;self.sequence_gaps=0
        self.rows=[];self.candidate_bytes=0;self.tb3_window_ticks=0;self.reason_counts={}
        self.unavailable_request_or_output_ticks=0;self.nonrejected_window_ticks=0;self.aggregates={}

    def issue(self,ref,error):
        self.error_count+=1
        if len(self.errors)<LIMITS['max_error_examples']:self.errors.append({'reference':ref,'error':str(error)})

    def tally(self,table,key,value,seq):
        encoded=canonical(value)
        values=table.setdefault(key,{})
        if encoded not in values:
            if len(values)>=LIMITS['max_values_per_margin']:raise BoundExceeded('typed field value aggregation bound')
            values[encoded]={'original_field':value,'count':0,'first_record_sequence':seq,'last_record_sequence':seq}
        values[encoded]['count']+=1;values[encoded]['last_record_sequence']=seq

    def aggregate_checks(self,label,checks,seq):
        table=self.aggregates.setdefault(label,{'check_map_presence':{},'peers':{}})
        self.tally(table['check_map_presence'],'field',checks,seq) if not checks['present'] or type(checks.get('value')) is not dict else None
        if not checks['present'] or type(checks.get('value')) is not dict:return
        for peer,certificate in checks['value'].items():
            require(peer in ('tb1','tb2'),'unexpected peer key in tb3 certificate')
            require(type(certificate) is dict,'peer certificate is not object')
            a=table['peers'].setdefault(peer,{'records':0,'necessary_fields':{},'actual_margin_fields':{}});a['records']+=1
            for key in ('geometric_necessary','geometric_sufficient','legacy_hard_gates_passed','common_world_odom_calibrated'):
                self.tally(a['necessary_fields'],key,present(certificate,key),seq)
            for key in ('ages_ns','uncertainty_m'):
                self.tally(a['actual_margin_fields'],key,present(certificate,key),seq)
            for frame in ('map','raw'):
                f=certificate.get(frame)
                if type(f) is not dict:
                    self.tally(a['necessary_fields'],frame+'.frame',present(certificate,frame),seq);continue
                for key in ('reported_normal_defined','separation_sufficient_under_declared_sets','map_closed_set','raw_closed_set'):
                    if key in f or key in ('reported_normal_defined','separation_sufficient_under_declared_sets'):
                        self.tally(a['necessary_fields'],frame+'.'+key,present(f,key),seq)
                for key in ('distance_norm_bounds_m','required_centre_distance_upper_bounds_m','squared_slack_bounds_m2','base_reserve_m'):
                    self.tally(a['actual_margin_fields'],frame+'.'+key,present(f,key),seq)

    def feed(self,row,ref):
        require(type(row) is dict and row.get('schema')=='mr3-motion-safety-v1' and row.get('epoch')==EPOCH,'motion record schema/epoch differs')
        seq=integer(row.get('record_sequence'),1)
        require(seq>self.last_record_sequence,'record sequence duplicate/regression')
        if self.last_record_sequence and seq!=self.last_record_sequence+1:self.sequence_gaps+=1
        self.last_record_sequence=seq
        callback_ns=ns(row['sim_time_sec']);kind=row.get('kind');p=row.get('payload')
        require(type(kind) is str and type(p) is dict,'record kind/payload type')
        if kind not in self.kinds and len(self.kinds)>=LIMITS['max_kind_names']:raise BoundExceeded('kind count bound exceeded')
        self.kinds[kind]=self.kinds.get(kind,0)+1
        if kind!='reach_decision' or p.get('robot')!='tb3':return
        clock=integer(p.get('clock_ns'));integer(p.get('decision_sequence'),1)
        if not BEGIN_NS<=clock<END_NS:return
        self.tb3_window_ticks+=1
        require(type(p.get('decision')) is dict,'decision not object')
        d=p['decision'];reason=d.get('reason');require(type(reason) is str,'decision reason not string')
        if reason not in self.reason_counts and len(self.reason_counts)>=128:raise BoundExceeded('window reason count bound')
        self.reason_counts[reason]=self.reason_counts.get(reason,0)+1
        effective=vector(p.get('effective_request'));output=vector(d.get('output'))
        if effective is None or output is None:
            self.unavailable_request_or_output_ticks+=1;return
        # Fixed received predicate: requested forward translation suppressed to zero.
        # This is a logged control choice, not a claim about physical dynamics.
        if not (effective[0]>0 and output[0]==0):self.nonrejected_window_ticks+=1;return
        if len(self.rows)>=LIMITS['max_candidate_records']:raise BoundExceeded('candidate record cap')
        size=len(canonical(row))
        if self.candidate_bytes+size>LIMITS['max_candidate_bytes']:raise BoundExceeded('full candidate payload byte cap')
        if reason not in {x['row']['payload']['decision']['reason'] for x in self.rows} and len({x['row']['payload']['decision']['reason'] for x in self.rows})>=9:
            raise BoundExceeded('reason coverage cannot fit fixed twelve sample rule')
        reference=dict(ref,record_sequence=seq,callback_clock_ns=callback_ns,decision_clock_ns=clock,decision_sequence=p['decision_sequence'])
        self.rows.append({'reference':reference,'row':row});self.candidate_bytes+=size
        self.aggregate_checks('decision.reach_pair_checks',present(d,'reach_pair_checks'),seq)
        cf=d.get('component_filter')
        rejected=present(cf,'rejected_transition_checks') if type(cf) is dict else {'present':False}
        self.aggregate_checks('decision.component_filter.rejected_transition_checks',rejected,seq)

    @staticmethod
    def export(table):
        if isinstance(table,dict):
            if table and all(isinstance(k,bytes) for k in table):return [table[k] for k in sorted(table)]
            return {k:Analyzer.export(v) for k,v in table.items()}
        return table

    def finish(self):
        positions={};n=len(self.rows)
        if n:
            for label,i in (('first',0),('middle',(n-1)//2),('last',n-1)):positions.setdefault(i,[]).append(label)
            seen=set()
            for i,r in enumerate(self.rows):
                reason=r['row']['payload']['decision']['reason']
                if reason not in seen:positions.setdefault(i,[]).append('first_reason:'+reason);seen.add(reason)
        if len(positions)>LIMITS['max_selected_records']:raise BoundExceeded('fixed sample union cap')
        samples=[dict(selection_labels=positions[i],**self.rows[i]) for i in sorted(positions)]
        return dict(selection_scope={'robot':'tb3','begin_inclusive_ns':BEGIN_NS,'end_exclusive_ns':END_NS,
                'predicate':'effective_request[0] > 0 AND decision.output[0] == 0',
                'fixed_sample_rule':'first occurrence per reason plus global first/lower-middle/last; deduplicated original journal order; at most twelve'},
            tb3_window_decisions=self.tb3_window_ticks,window_reason_counts=self.reason_counts,
            unavailable_request_or_output_ticks=self.unavailable_request_or_output_ticks,
            other_window_decisions=self.nonrejected_window_ticks,candidate_records=n,candidate_payload_bytes=self.candidate_bytes,
            selected_records=len(samples),rejection_samples=samples,per_peer_original_check_aggregates=self.export(self.aggregates),
            pair_check_field_semantics={
                'linear_brake_preserve_requested_turn':{'decision.reach_pair_checks':'returned current-D checks',
                    'decision.component_filter.rejected_transition_checks':'actual rejected prospective-X checks'},
                'reach_transition_envelope':{'decision.reach_pair_checks':'actual rejected prospective-X checks',
                    'decision.component_filter.rejected_transition_checks':'normally absent; do not fabricate'},
                'other_reason':'UNKNOWN; retain actual literal fields'},
            record_kind_counts=self.kinds,record_sequence_gap_count=self.sequence_gaps,semantic_error_count=self.error_count,semantic_error_examples=self.errors,
            sample_context_scope='entire original reach_decision record from the same JSONL line; no nearest-time, cross-row, or inferred peer context',
            certificate_scope='actual logged historical admission fields; cone-support-v2 is conditional sufficient separation; rational strings and log intervals are unmodified',
            raw_goal_generation='UNKNOWN_UNSTAMPED_TWIST',physical_root_cause='UNKNOWN',
            physical_stop_or_continuous_bounds_replayed=False,mathematical_pair_checks_replayed=False,
            actual_wheel_SetParam_or_readback_checked=False,old_FAIL_rejudged=False)

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
        prior_consumption_disclosure="Original motion was opaquely archived and completely described by V73. This new bounded-field descriptor has not run on the original during preparation; no first-read claim.")
    checked={};input_before=None
    try:
        require(Path(__file__).resolve()==A/"describe_reach_rejection_v1.py" and args.spec==A/"description_spec_v1.json","canonical consumer/spec only")
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
        require(str((A/"describe_reach_rejection_v1.py").relative_to(ROOT)) in {r["path"] for r in bindings},"consumer source pin absent")
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
            and ledger.get("engineering_cumulative_seconds")=="112639.6725192646018","actual prior description ledger is not the original native result")
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
            result.pop("rejection_samples",None);result.pop("per_peer_original_check_aggregates",None);result.update(passed=False,description_status="INCOMPLETE_OUTPUT_CAP",omitted_result_bytes=len(raw));raw=canonical(result)+b"\n"
        require(len(raw)<=LIMITS["max_output_bytes"],"bounded failure output exceeds output cap")
        with OUTPUT.open("xb") as stream:stream.write(raw)
    return 0 if result["passed"] else 1


if __name__=="__main__":raise SystemExit(main())
