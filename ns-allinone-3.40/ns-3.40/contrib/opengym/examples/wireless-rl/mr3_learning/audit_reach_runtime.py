"""Independent necessary replay of the explicit mr3-reach-v1 execution chain.

No production tracker, guard, geometry or wire parser is imported. Exact
arithmetic checks observed implications; it cannot prove continuous dynamics,
WORLD/heading calibration, future confinement, or native admission by itself.
Old profile/source/schema artifacts cannot acquire credit from this reader.
"""
from bisect import bisect_left, bisect_right
from decimal import Decimal
from fractions import Fraction as Q
from functools import lru_cache
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess

from . import initial_encoder_replay as encoder_replay
from .motion_authority_profile import selected_motion_authority_profile


ROBOTS = ("tb1", "tb2", "tb3")
CONTRACT = "mr3-reach-v1"
DEFAULT_GEOMETRY_RULE = "binary-cone-v1"
SUPPORT_GEOMETRY_RULE = "cone-support-v2"
R, D, H = Q(39, 5000), Q(18, 125), 780_000_000
RAW, ACT, PUB = 20_000_000, 34_000_000, 940_000_000
PURE = "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/"
NATIVE = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/"
ENCODER_HEADER_SOURCE = NATIVE+"include/multi_robot/mr3_initial_zero_encoder_servo.hpp"
ENCODER_REPLAY_SOURCE = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/initial_encoder_replay.py"
SOURCES = tuple(PURE+name for name in (
    "motion_safety.py", "mr3_reach_runtime.py", "mr3_reach_geometry.py",
    "mr3_velocity_metric.py", "mr3_safety_intent.py", "mr3_information.py",
    "peer_obstacles.py", "mr3_control_phase.py", "mr3_motion_control.py",
    "mr3_drive_phase.py", "mr3_episode.py", "mr3_motion_safety.py")) + (
        NATIVE+"src/mr3_gazebo_diff_drive.cpp", NATIVE+"CMakeLists.txt",
        NATIVE+"include/multi_robot/mr3_drive_feed.hpp",
        NATIVE+"include/multi_robot/paired_wheel_slew.hpp",
        NATIVE+"include/multi_robot/mr3_drive_target.hpp",
        NATIVE+"include/multi_robot/mr3_odometry_json.hpp",
        ENCODER_HEADER_SOURCE, ENCODER_REPLAY_SOURCE)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def geometry_rule(metadata):
    rule = metadata.get("reach_geometry_rule", DEFAULT_GEOMETRY_RULE)
    require(type(rule) is str and rule in (DEFAULT_GEOMETRY_RULE, SUPPORT_GEOMETRY_RULE),
            "unknown reach geometry rule")
    require(rule == DEFAULT_GEOMETRY_RULE or metadata.get("safety_contract") == CONTRACT,
            "support geometry requires the explicit reach contract")
    return rule


def selected_actuation_profile(metadata, *, required=False):
    profile = metadata.get("actuation_profile")
    if profile is None and not required:
        return None  # Historical/raw synthetic branch keeps its original law.
    require(type(profile) is str and profile == encoder_replay.PROFILE
            and metadata.get("safety_contract") == CONTRACT,
            "missing or unknown selected Reach actuation profile")
    return profile


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def decode_text(text):
    require(type(text) is str, "raw wire JSON is missing")
    def unique(items):
        result = {}
        for key,value in items:
            require(key not in result,"duplicate wire JSON member")
            result[key]=value
        return result
    value=json.loads(text,object_pairs_hook=unique,
                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite wire JSON")))
    canonical(value)
    return value


def same(a, b):
    return canonical(a) == canonical(b)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


@lru_cache(maxsize=4096, typed=True)
def _number_fraction(value):
    return Q.from_float(value) if type(value) is float else Q(value)


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "nonfinite/non-numeric scalar")
    return _number_fraction(value)


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "invalid integer identity")
    return value


def fields(value, expected):
    require(type(value) is dict and set(value) == set(expected), "wire fields differ")


def sec_ns(value):
    result = Decimal(str(value))*1_000_000_000
    require(result.is_finite() and result == result.to_integral_value(), "nonexact clock")
    return int(result)


def state_ns(value):
    """The producer's declared float-to-ns conversion, never an age epsilon.

    Safety ages below come from the original integer headers. Float metadata
    is checked against those headers after the same public timestamp encoding.
    """
    number(value)
    require(value >= 0,"negative reported source timestamp")
    return round(value*1_000_000_000)


def source(raw):
    stamp = raw["header"]["stamp"]
    fields(stamp, ("sec", "nanosec"))
    sec, nano = integer(stamp["sec"]), integer(stamp["nanosec"])
    require(nano < 1_000_000_000, "noncanonical source stamp")
    return sec*1_000_000_000+nano


def vector(value, keys=("x", "y", "z")):
    fields(value, keys)
    return tuple(number(value[k]) for k in keys)


def raw_check(raw):
    fields(raw, ("header", "child_frame_id", "pose", "twist"))
    source(raw)
    require(type(raw["header"]["frame_id"]) is str and raw["header"]["frame_id"]
            and type(raw["child_frame_id"]) is str and raw["child_frame_id"], "raw frame missing")
    for key in ("pose", "twist"):
        fields(raw[key], (key, "covariance"))
        require(type(raw[key]["covariance"]) is list and len(raw[key]["covariance"]) == 36,
                "complete raw covariance missing")
        for v in raw[key]["covariance"]:
            number(v)
    vector(raw["pose"]["pose"]["position"])
    vector(raw["pose"]["pose"]["orientation"], ("x", "y", "z", "w"))
    vector(raw["twist"]["twist"]["linear"])
    vector(raw["twist"]["twist"]["angular"])


def xy(raw):
    return vector(raw["pose"]["pose"]["position"])[:2]


def axis(raw):
    x, y, z, w = vector(raw["pose"]["pose"]["orientation"], ("x", "y", "z", "w"))
    result = 1-2*(y*y+z*z), 2*(w*z+x*y)
    require(sum(v*v for v in result) > 0, "undefined physical heading")
    return result


def target_check(value, epoch, robot):
    fields(value, ("schema", "epoch", "robot", "clock_ns", "decision_sequence", "linear_x", "angular_z"))
    require(value["schema"] == "mr3-drive-target-v1" and value["epoch"] == epoch
            and value["robot"] == robot, "target identity differs")
    integer(value["clock_ns"]); integer(value["decision_sequence"], 1)
    require(abs(number(value["linear_x"])) <= Q.from_float(.20)
            and abs(number(value["angular_z"])) <= Q.from_float(.8), "target hard bounds")


def calibration_check(value, raw, epoch, robot):
    fields(value, ("schema", "epoch", "robot", "source_clock_ns", "publication_sequence",
                   "coefficient_c", "coefficient_s", "odometry", "conversion_contract", "producer_frame"))
    require(value["schema"] == "mr3-odom-calibration-v1" and value["epoch"] == epoch
            and value["robot"] == robot and value["source_clock_ns"] == source(raw)
            and same(value["odometry"], raw), "calibration/raw source or complete payload differs")
    require(value["conversion_contract"] == "float32-trig-binary64-rn-v1"
            and value["producer_frame"] == "world-common-model-origin-v1", "unreviewed calibration model")
    integer(value["source_clock_ns"]); integer(value["publication_sequence"], 1)
    c, s = (number(value[k]) for k in ("coefficient_c", "coefficient_s"))
    require(c*c+s*s > 0 and abs(c) <= 1 and abs(s) <= 1, "invalid conversion coefficients")
    for key in ("coefficient_c", "coefficient_s"):
        f = value[key]
        require(struct.unpack("!f", struct.pack("!f", f))[0] == f,
                "coefficient is not an actual promoted binary32 value")


def intent_check(value, epoch, robot):
    fields(value,("schema","epoch","robot","intent_sequence","source_clock_ns","role",
                  "anchor","admitted_signs","lineage","target"))
    require(value["schema"]=="mr3-safety-intent-v1" and value["epoch"]==epoch and value["robot"]==robot,
            "intent owner/schema differs")
    sequence=integer(value["intent_sequence"],1);clock=integer(value["source_clock_ns"])
    signs=value["admitted_signs"]
    require(type(signs) is list and all(type(s) is int and s in (-1,1) for s in signs)
            and len(signs)==len(set(signs))<=2,"invalid intent signed family")
    target_check(value["target"],epoch,robot)
    require(value["target"]["clock_ns"]<=clock,"intent target is future")
    anchor=value["anchor"]
    if anchor is not None:
        fields(anchor,("source_clock_ns","odometry"));raw_check(anchor["odometry"])
        require(source(anchor["odometry"])==integer(anchor["source_clock_ns"])<=clock,"intent historical anchor differs")
    role,lineage=value["role"],value["lineage"]
    if role=="HOLD":
        fields(lineage,("release_clock_ns",))
        require(not signs and value["target"]["linear_x"]==value["target"]["angular_z"]==0,"HOLD is not full zero")
        if lineage["release_clock_ns"] is None:require(anchor is None,"pre-release anchor invented")
        else:require(anchor is not None and anchor["source_clock_ns"]<=integer(lineage["release_clock_ns"])<=clock,
                     "released HOLD lost anchor lineage")
    elif role in ("D","X","N"):
        keys={"anchor_intent_sequence"}
        if role!="D":keys.add("transition_intent_sequence")
        if role=="N":keys.update(("actuation_sequence","actuation_source_clock_ns","causal_source_clock_ns","cmd_seq"))
        fields(lineage,keys)
        require(anchor is not None and integer(lineage["anchor_intent_sequence"],1)<=sequence,"active anchor lineage differs")
        if role=="D":require(not signs and value["target"]["linear_x"]==0,"D is not zero-linear")
        else:
            require(lineage["anchor_intent_sequence"]<integer(lineage["transition_intent_sequence"],1)<=sequence and signs,
                    "X/N bypassed preannounced transition lineage")
            v=value["target"]["linear_x"]
            require(v==0 or (1 if v>0 else -1) in signs,"target escaped fixed signed family")
        if role=="N":
            integer(lineage["actuation_sequence"],1);integer(lineage["cmd_seq"],1)
            require(anchor["source_clock_ns"]<=integer(lineage["actuation_source_clock_ns"])
                    <integer(lineage["causal_source_clock_ns"])<=clock,"N lacks strict post-actual source")
    else:
        require(role=="STOP","unknown intent role")
        fields(lineage,("previous_intent_sequence","previous_role"))
        require(integer(lineage["previous_intent_sequence"],1)<sequence and lineage["previous_role"] in ("HOLD","D","X","N")
                and value["target"]["linear_x"]==value["target"]["angular_z"]==0,"STOP lineage or zero differs")
        require(not signs if lineage["previous_role"] in ("HOLD","D") else bool(signs),"STOP changed signed debt")
        require(anchor is not None or lineage["previous_role"]=="HOLD","STOP erased protected anchor")


def residual_squared_upper(raw, calibration, signs):
    """Independent A^-1 projection and outward RN operation enclosure."""
    require(tuple(signs) in ((), (1,), (-1,), (1, -1), (-1, 1)), "invalid fixed signs")
    c, s = number(calibration["coefficient_c"]), number(calibration["coefficient_s"])
    bx, by, _ = vector(raw["twist"]["twist"]["linear"])
    hx, hy = axis(raw)
    u, eta = Q(1, 2**53), Q(1, 2**1075)
    error = (2*u+u*u)*Q(3, 10)*(abs(c)+abs(s))+(3+2*u)*eta
    q, h2 = c*c+s*s, hx*hx+hy*hy
    # WORLD=A^T*b/q. Projection on h and its perpendicular is computed
    # directly, independently of the producer's residual implementation.
    forward_terms = hx*c+hy*s, -hx*s+hy*c
    side_terms = -hy*c+hx*s, hy*s+hx*c
    forward = forward_terms[0]*bx+forward_terms[1]*by
    side = side_terms[0]*bx+side_terms[1]*by
    fe = error*sum(abs(v) for v in forward_terms)
    se = error*sum(abs(v) for v in side_terms)
    wrong = max(Q(0), -(forward-fe) if -1 not in signs else Q(0),
                forward+fe if 1 not in signs else Q(0))
    lateral = abs(side)+se
    return (wrong*wrong+lateral*lateral)/(q*q*h2)


@lru_cache(maxsize=256)
def trig_bounds(angle):
    """Taylor/Lagrange bounds, rather than the production alternating kernel."""
    require(0 <= angle <= Q(192, 125), "unreviewed heading cone")
    sine = sum(((-1)**k)*angle**(2*k+1)/math.factorial(2*k+1) for k in range(21))
    cosine = sum(((-1)**k)*angle**(2*k)/math.factorial(2*k) for k in range(21))
    # Degree41 cosine and degree42 sine omit their zero parity terms.
    # The respective Lagrange remainders have degrees42/43; derivatives<=1.
    return (cosine-angle**42/math.factorial(42),
            sine+angle**43/math.factorial(43))


def nonclosing(direction, bearing, phi, uncertainty):
    dot = sum(a*b for a, b in zip(direction, bearing))
    if dot >= 0:
        return False
    cosine_lower, sine_upper = trig_bounds(phi)
    if cosine_lower <= 0:
        return False
    cross = direction[0]*bearing[1]-direction[1]*bearing[0]
    upper = dot*cosine_lower+abs(cross)*sine_upper
    return upper <= 0 and upper*upper >= uncertainty*uncertainty*sum(v*v for v in direction)


def intent_role(intent):
    return intent["lineage"]["previous_role"] if intent["role"] == "STOP" else intent["role"]


def state_geometry(state, clock, epoch):
    require(state["epoch"] == epoch and state["name"] in ROBOTS and state.get("valid") is True,
            "invalid received geometric state")
    raw = state["odometry"]; raw_check(raw)
    safety = state["safety"]; fields(safety, ("intent", "calibration"))
    calibration_check(safety["calibration"], raw, epoch, state["name"])
    intent = safety["intent"]
    intent_check(intent,epoch,state["name"])
    require(intent["schema"] == "mr3-safety-intent-v1" and intent["epoch"] == epoch
            and intent["robot"] == state["name"] and 0 <= clock-intent["source_clock_ns"] <= 500_000_000,
            "received intent identity/age differs")
    tf_source = source({"header":state["transform"]["header"]})-200_000_000
    oldest = min(source(raw),tf_source)
    require(state_ns(state["source_stamp"]) == oldest and state_ns(state["odom_source_stamp"]) == source(raw)
            and state_ns(state["tf_source_stamp"]) == tf_source
            and 0 <= clock-oldest <= 500_000_000, "geometric source age differs")
    role = intent_role(intent)
    require(role in ("HOLD", "D", "X", "N"), "unknown delivered reach")
    q = 4*R if role == "X" else 2*R
    raw_axis = axis(raw)
    x, y, z, w = vector(state["transform"]["transform"]["rotation"], ("x", "y", "z", "w"))
    tc, ts = 1-2*(y*y+z*z), 2*(w*z+x*y)
    rotation=state["transform"]["transform"]["rotation"]
    angle=math.atan2(2*(rotation["w"]*rotation["z"]+rotation["x"]*rotation["y"]),
                     1-2*(rotation["y"]**2+rotation["z"]**2))
    p=raw["pose"]["pose"]["position"];t=state["transform"]["transform"]["translation"]
    expected=(t["x"]+math.cos(angle)*p["x"]-math.sin(angle)*p["y"],
              t["y"]+math.sin(angle)*p["x"]+math.cos(angle)*p["y"])
    require((number(state["x"]),number(state["y"])) == tuple(number(v) for v in expected),
            "map point is not its delivered original raw/TF projection")
    mapped = tc*raw_axis[0]-ts*raw_axis[1], ts*raw_axis[0]+tc*raw_axis[1]
    signs = tuple(intent["admitted_signs"])
    require(not signs if role in ("HOLD", "D") else bool(signs), "reach signed family differs")
    return raw, q, role, signs, (raw_axis, mapped), clock-oldest


def independent_pair(own, peer, clock, epoch, *, reach_geometry_rule=DEFAULT_GEOMETRY_RULE):
    geometry_rule({"reach_geometry_rule": reach_geometry_rule, "safety_contract": CONTRACT})
    left, right = state_geometry(own, clock, epoch), state_geometry(peer, clock, epoch)
    uncertainty = Q(3, 10)*Q(left[5]+right[5], 10**9)
    bearings = (tuple(b-a for a, b in zip(xy(left[0]), xy(right[0]))),
                (number(peer["x"])-number(own["x"]), number(peer["y"])-number(own["y"])))
    results = []
    for frame, bearing in enumerate(bearings):
        margin = Q(13, 25)+uncertainty+left[1]+right[1]
        for row, toward in ((left, bearing), (right, tuple(-v for v in bearing))):
            if row[2] in ("HOLD", "D"):
                continue
            phi = Q(6, 5)*(Q(row[5], 10**9)+Q(39, 50))
            if reach_geometry_rule == SUPPORT_GEOMETRY_RULE:
                from .reach_support_replay import direction_support_upper
                margin += max(direction_support_upper(toward,
                    tuple(sign*x for x in row[4][frame]), phi, uncertainty, D) for sign in row[3])
            elif not all(nonclosing(tuple(sign*x for x in row[4][frame]), toward, phi, uncertainty)
                         for sign in row[3]):
                margin += D
        results.append(sum(v*v for v in bearing) >= margin*margin)
    return all(results)


def admitted_command(decision, own, delivered_self, peers, clock, epoch, *,
                     reach_geometry_rule=DEFAULT_GEOMETRY_RULE):
    """Check exact request preservation or the narrowly authorized D filter.

    Component filtering consumes the complete old fixed-disk certificate. It
    cannot create a turn, alter its sign, announce X, or move the old anchor.
    The rejected larger transition certificate is diagnostic, never a reason
    to accept a smaller certificate without independently checking both frames.
    """
    output = decision["decision"]["output"]
    if same(output, [0., 0.]):
        return  # A safe full zero needs no Nav2 request.
    request = decision["request"]
    require(request is not None and request.get("supported") is True
            and request.get("publisher_identity", {}).get("valid") is True,
            "admitted motion has no supported real Nav2 request")
    require(0 <= clock-state_ns(request["received_stamp"]) <= 200_000_000,
            "admitted motion reused an expired/future Nav2 request")
    canonical_request = []
    for value, cap in zip((request["v"], request["w"]), (.20, .8)):
        number(value)
        if abs(value) > cap:
            require(abs(value) == math.nextafter(cap, math.inf), "command exceeds one-ULP normalization")
            value = math.copysign(cap, value)
        canonical_request.append(float(value))
    if same(output, canonical_request):
        return
    emitted, local, received = (decision["intent"], own["safety"]["intent"],
                                delivered_self["safety"]["intent"])
    evidence = decision["decision"].get("component_filter", {})
    require(canonical_request[0] != 0 and canonical_request[1] != 0
            and same(output, [0., canonical_request[1]])
            and all(v["role"] == "D" and not v["admitted_signs"] for v in (emitted, local, received))
            and same(emitted["anchor"], local["anchor"]) and same(local["anchor"], received["anchor"])
            and same(evidence.get("canonical_input"), canonical_request)
            and type(evidence.get("rejected_transition_checks")) is dict
            and decision["decision"].get("reason") == "linear_brake_preserve_requested_turn"
            and all(independent_pair(own, peer, clock, epoch,
                **({"reach_geometry_rule": reach_geometry_rule}
                   if reach_geometry_rule != DEFAULT_GEOMETRY_RULE else {})) for peer in peers.values()),
            "guard invented a command or filtered without the complete unchanged D certificate")


class Inputs:
    def __init__(self):
        self.proof, self.stats = {}, {}

    @staticmethod
    def stat(path):
        s = path.stat()
        return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns

    def read(self, directory, name, lines=False):
        path = directory/name
        if not path.exists():
            path = Path(str(path)+".gz")
        before = self.stat(path)
        raw = path.read_bytes()
        require(before == self.stat(path), "artifact changed during read")
        decoded = gzip.decompress(raw) if path.suffix == ".gz" else raw
        def unique(items):
            # JSON object keys are already builtin strings and all values have
            # been decoded before this hook. Keep the original generic error.
            result = dict(items)
            require(len(result) == len(items), "duplicate JSON member")
            return result
        def parse(raw):
            value = json.loads(raw, object_pairs_hook=unique,
                               parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))
            canonical(value)
            return value
        if lines:
            require(not decoded or decoded.endswith(b"\n"), "incomplete JSONL tail")
            value = [parse(row) for row in decoded.splitlines() if row.strip()]
        else:
            value = parse(decoded)
        self.proof[name] = {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                            "decoded_sha256": hashlib.sha256(decoded).hexdigest()}
        self.stats[path] = before
        return value

    def close(self):
        require(all(self.stat(path) == before for path, before in self.stats.items()),
                "bound artifact changed before verdict")


def source_proof(root, freeze, *, reach_geometry_rule=DEFAULT_GEOMETRY_RULE, motion_authority_profile=None):
    geometry_rule({"reach_geometry_rule": reach_geometry_rule, "safety_contract": CONTRACT})
    require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze), "exact new source freeze required")
    proof = {}
    reader = str(Path(__file__).resolve().relative_to(root))
    extra = ("ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py",
             NATIVE+"launch/gazebo_multirobot_mapping_with_nav2.launch.py", reader)
    if motion_authority_profile is not None:
        selected_motion_authority_profile(dict(safety_contract=CONTRACT,
            motion_authority_profile=motion_authority_profile), required=True)
        extra += (PURE+"mr3_adapter.py", PURE+"mr3_protocol.py", PURE+"mr3_motion_authority.py",
            str(Path(__file__).resolve().relative_to(root).parent/"motion_authority_audit.py"),
            str(Path(__file__).resolve().relative_to(root).parent/"motion_authority_profile.py"))
    if reach_geometry_rule == SUPPORT_GEOMETRY_RULE:
        extra += (PURE+"mr3_reach_support.py", str(Path(__file__).with_name(
            "reach_support_replay.py").resolve().relative_to(root)))
    for name in SOURCES+extra:
        payload = subprocess.check_output(["git", "show", freeze+":"+name], cwd=root)
        require(payload == (root/name).read_bytes(), "current source differs from declared freeze: "+name)
        proof[name] = {"git_source": freeze+":"+name, "sha256": hashlib.sha256(payload).hexdigest()}
    require(b"mr3-drive-applied-v1" in (root/(NATIVE+"include/multi_robot/mr3_drive_feed.hpp")).read_bytes()
            and b"mr3-reach-v1" in (root/(PURE+"mr3_reach_runtime.py")).read_bytes(),
            "old source cannot acquire reach-profile credit")
    return proof


def graph_identity(value, robot, kind, stable):
    if kind == "state":
        topic,node,namespace = "/mr3/received/states","mr3_information","/"
    else:
        suffix = {"calibration": "odometry_calibration", "applied": "applied", "storage": "status"}[kind]
        topic,node,namespace = f"/{robot}/mr3_drive/{suffix}","turtlebot3_diff_drive","/"+robot
    require(value.get("scope") == "graph_at_callback" and value.get("valid") is True
            and value.get("packet_publisher_gid_available") is False and value.get("error") is None
            and value.get("topic") == topic and len(value.get("endpoints", [])) == 1,
            "native feed lacks a unique callback graph publisher")
    endpoint = value["endpoints"][0]
    require(endpoint.get("node_namespace") == namespace and endpoint.get("node_name") == node
            and endpoint.get("topic_type") == "std_msgs/msg/String"
            and type(endpoint.get("endpoint_gid")) is str
            and re.fullmatch(r"(?:[0-9a-f]{2}){16,}", endpoint["endpoint_gid"])
            and int(endpoint["endpoint_gid"], 16) != 0, "wrong native feed graph identity")
    key = robot, kind
    require(key not in stable or stable[key] == endpoint, "native feed graph GID changed")
    stable[key] = endpoint


def native_index(drivers, odometry_rows, epoch, *, actuation_profile=None, encoder_helper_sha256=None):
    """Index actual producer calls and the unchanged v2 wheel audit."""
    require(actuation_profile is None or actuation_profile == encoder_replay.PROFILE,
            "unknown actual actuator profile")
    algorithm = (encoder_replay.OLD_ALGORITHM if actuation_profile is None else encoder_replay.ALGORITHM)
    result = {}
    for robot in ROBOTS:
        drive, odoms = drivers[robot], odometry_rows[robot]
        require(drive and odoms, "native producer artifacts missing")
        cfg, ocfg = drive[0], odoms[0]
        require(cfg.get("schema") == "mr3-drive-actuation-v2" and cfg.get("kind") == "configuration"
                and cfg.get("command_mode") == "tagged" and cfg.get("update_rate_hz") == 30
                and cfg.get("actuation_algorithm") == algorithm
                and number(cfg.get("max_acceleration_mps2")) == 1
                and type(cfg.get("num_wheel_pairs")) is int and cfg["num_wheel_pairs"] > 0,
                "unreviewed native actuator configuration")
        require(ocfg.get("schema") == "mr3-world-odometry-publication-v1"
                and ocfg.get("kind") == "configuration" and ocfg.get("provider") == "WORLD"
                and ocfg.get("period_ns") == RAW
                and ocfg.get("phase") == "world_update_begin_before_actuation",
                "old or unreviewed odometry configuration")
        commands, acts, raw = {}, {}, {}
        command_records, command_values = [], []
        for i, row in enumerate(drive, 1):
            integer(row.get("record_sequence"), 1)
            require(row.get("epoch") == epoch and row.get("robot") == robot
                    and row.get("record_sequence") == i, "native drive custody gap")
            if row["kind"] == "command_received":
                seq = integer(row["cmd_seq"], 1)
                require(seq == len(commands)+1, "native command sequence gap")
                commands[seq] = row
                command_records.append(row["record_sequence"])
                command_values.append(row)
            elif row["kind"] == "actuation":
                seq = integer(row["actuation_seq"], 1)
                acts.setdefault(seq, []).append(row)
        previous = None
        for seq, pairs in acts.items():
            require([p["pair_index"] for p in pairs] == list(range(cfg["num_wheel_pairs"]))
                    and len({p["sim_time_ns"] for p in pairs}) == 1
                    and len({p["cmd_seq"] for p in pairs}) == 1, "native wheel pair phase incomplete")
            current = pairs[0]
            require(current["dt_ns"] == ACT and (previous is None or
                    seq == previous["actuation_seq"]+1
                    and current["sim_time_ns"]-previous["sim_time_ns"] == ACT),
                    "native actual actuation cadence changed")
            if current["cmd_seq"]:
                command = commands.get(current["cmd_seq"])
                require(command is not None and command["record_sequence"] < current["record_sequence"],
                        "actuation has no earlier native command")
                latest = bisect_left(command_records, current["record_sequence"]) - 1
                require(command_values[latest]["cmd_seq"] == current["cmd_seq"],
                        "native actuation did not select the latest stored command")
            previous = current
        previous_source = None
        for i, row in enumerate(odoms, 1):
            integer(row.get("record_sequence"), 1)
            require(row.get("epoch") == epoch and row.get("robot") == robot
                    and row.get("record_sequence") == i, "native odometry custody gap")
            if row["kind"] != "publication":
                continue
            clock = integer(row["source_clock_ns"])
            integer(row["publication_sequence"], 1)
            raw_check(row["odometry"])
            require(row["publication_sequence"] == len(raw)+1 and clock == source(row["odometry"])
                    and row["sim_time_ns"] == clock and row["odom_published"] is True
                    and row["odom_tf_published"] is True
                    and row["publication_scope"] == "actual_publisher_calls_returned_not_delivery"
                    and (previous_source is None or clock-previous_source == RAW),
                    "native complete20ms publication sequence differs")
            raw[clock] = row
            previous_source = clock
        result[robot] = {"configuration": cfg, "odometry_configuration": ocfg,
                         "commands": commands, "actuations": acts, "odometry": raw,
                         "records": drive}
        if actuation_profile is not None:
            result[robot]["initial_encoder_motor_replay"] = encoder_replay.replay_native_drive(
                drive, profile=actuation_profile, epoch=epoch, robot=robot,
                helper_sha256=encoder_helper_sha256)
    return result


def ingress_index(motion, native, epoch, *, reach_geometry_rule=DEFAULT_GEOMETRY_RULE):
    geometry_rule({"reach_geometry_rule": reach_geometry_rule, "safety_contract": CONTRACT})
    streams = {n: {"raw": {}, "tf": {}, "calibration": {}, "storage": {}, "applied": {},
                    "intent": {}, "requests": {}, "decisions": []} for n in ROBOTS}
    stable, received, state_ingress = {}, None, None
    raw_callback_counts = {n: 0 for n in ROBOTS}
    configuration = None
    for i, row in enumerate(motion, 1):
        integer(row.get("record_sequence"), 1)
        require(row.get("schema") == "mr3-motion-safety-v1" and row.get("epoch") == epoch
                and row.get("record_sequence") == i, "motion log schema/custody gap")
        kind, p = row["kind"], row["payload"]
        if kind == "configuration":
            require(configuration is None and p.get("safety_contract") == CONTRACT
                    and p.get("controlled_execution") is True and p.get("robots") == list(ROBOTS),
                    "old motion contract cannot supply reach credit")
            require(geometry_rule(p) == reach_geometry_rule,
                    "actual motion configuration geometry rule differs from episode metadata")
            configuration = p
        elif kind in ("reach_model_failure", "settled_turn_model_failure", "invalid_received_states",
                      "normal_control_model_invalid", "invalid_reach_driver_ingress"):
            raise ValueError("actual motion/model failure is retained, never PASS: "+kind)
        elif kind == "reach_state_ingress":
            require(same(decode_text(p["raw_json"]),p["message"]),"state ingress lost raw wire JSON")
            graph_identity(p["publisher_identity"],None,"state",stable)
            state_ingress=p["message"]
        elif kind == "received_states":
            require(state_ingress is not None and same(state_ingress,p),
                    "received bundle has no genuine stable Information subscription ingress")
            require(p.get("epoch") == epoch and p.get("safety_contract") == CONTRACT
                    and len(p["robots"]) == 3 and {v["name"] for v in p["robots"]} == set(ROBOTS),
                    "received team contract differs")
            table = {v["name"]: v["safety"] for v in p["robots"]}
            require(p.get("safety_table_sha256") == digest(table), "received safety table hash differs")
            received = p
        elif kind == "own_odom":
            robot = p["robot"]; stream = streams[robot]
            raw = p["message"]; raw_check(raw); clock = source(raw)
            seq = integer(p["input_sequence"], 1)
            require(seq == raw_callback_counts[robot]+1, "own raw callback sequence gap")
            require(clock in native[robot]["odometry"]
                    and same(raw, native[robot]["odometry"][clock]["odometry"]),
                    "own raw has no identical native publication")
            stream["raw"].setdefault(clock, []).append((i, raw))
            raw_callback_counts[robot] += 1
        elif kind == "own_tf":
            robot=p["robot"]; stream=streams[robot]
            seq=integer(p["input_sequence"],1)
            require(seq==len(stream["tf"])+1,"own TF callback sequence gap")
            stream["tf"][seq]=(i,p["message"])
        elif kind == "raw_request":
            robot, request = p["robot"], p["request"]
            seq = integer(request["sequence"], 1)
            require(seq == len(streams[robot]["requests"])+1, "real Nav2 request callback sequence gap")
            if request.get("supported") is True:
                twist = p["twist"]
                linear, angular = vector(twist["linear"]), vector(twist["angular"])
                require(linear[1:] == (0, 0) and angular[:2] == (0, 0)
                        and same([request["v"], request["w"]], [twist["linear"]["x"], twist["angular"]["z"]]),
                        "supported request differs from the complete real Twist")
            streams[robot]["requests"][seq] = i, request
        elif kind == "reach_driver_ingress":
            robot, feed, message = p["robot"], p["kind"], p["message"]
            require(same(decode_text(p["raw_json"]),message),"native ingress lost raw wire JSON")
            if message.get("epoch") != epoch:
                continue  # Retained ignored old input never supplies current credit.
            require(robot in ROBOTS and feed in ("calibration", "storage", "applied")
                    and message.get("epoch") == epoch and message.get("robot") == robot,
                    "native feed schema/owner differs")
            graph_identity(p["publisher_identity"], robot, feed, stable)
            stream = streams[robot]
            if feed == "calibration":
                clock = message["source_clock_ns"]
                require(clock in native[robot]["odometry"], "calibration has no native source")
                publication = native[robot]["odometry"][clock]
                calibration_check(message, publication["odometry"], epoch, robot)
                require(message["publication_sequence"] == publication["publication_sequence"],
                        "calibration native publication identity differs")
                key = clock
            elif feed == "storage":
                fields(message, ("schema", "epoch", "robot", "clock_ns", "decision_sequence",
                                 "source_clock_ns", "cmd_seq", "linear_x", "angular_z"))
                require(message["schema"] == "mr3-drive-target-consumed-v1", "storage schema differs")
                for name in ("clock_ns", "source_clock_ns"):
                    integer(message[name])
                for name in ("decision_sequence", "cmd_seq"):
                    integer(message[name], 1)
                command = native[robot]["commands"].get(message["cmd_seq"])
                require(command is not None and message["clock_ns"] == command["sim_time_ns"]
                        and message["decision_sequence"] == command["target_decision_sequence"]
                        and message["source_clock_ns"] == command["target_clock_ns"]
                        and same([message["linear_x"], message["angular_z"]],
                                 [command["desired_v"], command["desired_w"]]),
                        "storage has no identical native command callback")
                key = message["cmd_seq"]
            else:
                fields(message, ("schema", "epoch", "robot", "source_clock_ns", "actuation_sequence",
                                 "cmd_seq", "dt_ns", "target", "pairs"))
                require(message["schema"] == "mr3-drive-applied-v1", "applied schema differs")
                integer(message["source_clock_ns"])
                for name in ("actuation_sequence", "cmd_seq", "dt_ns"):
                    integer(message[name], 1)
                target_check(message["target"], epoch, robot)
                pairs = native[robot]["actuations"].get(message["actuation_sequence"])
                require(pairs is not None and message["source_clock_ns"] == pairs[0]["sim_time_ns"]
                        and message["cmd_seq"] == pairs[0]["cmd_seq"] and message["dt_ns"] == pairs[0]["dt_ns"],
                        "applied identity has no identical actual wheel update")
                wanted = [{k: q[k] for k in ("pair_index", "current_rim_mps", "desired_rim_mps",
                          "applied_rim_mps", "alpha", "max_acceleration_mps2")} for q in pairs]
                require(same(message["pairs"], wanted), "applied pair data differs from native writes")
                command = native[robot]["commands"][message["cmd_seq"]]
                t = message["target"]
                require(t["decision_sequence"] == command["target_decision_sequence"]
                        and t["clock_ns"] == command["target_clock_ns"]
                        and same([t["linear_x"], t["angular_z"]], [command["desired_v"], command["desired_w"]]),
                        "applied target differs from actual selected command")
                if "initial_encoder_motor_replay" in native[robot]:
                    encoder_replay.check_applied_receipt(message, native[robot]["initial_encoder_motor_replay"])
                key = message["actuation_sequence"]
            old = stream[feed].get(key)
            require(old is None or same(old[1], message), "native receipt identity changed")
            if old is None:
                stream[feed][key] = i, message
        elif kind == "reach_intent_publish":
            robot, intent = p["robot"], p["intent"]
            require(p["scope"] == "actual_publisher_call_returned_not_delivery"
                    and p["payload_sha256"] == digest(intent) and intent["schema"] == "mr3-safety-intent-v1"
                    and intent["epoch"] == epoch and intent["robot"] == robot, "intent publication custody differs")
            seq = integer(intent["intent_sequence"], 1)
            require(seq == len(streams[robot]["intent"])+1, "intent sequence gap/rewrite")
            target_check(intent["target"], epoch, robot)
            intent_check(intent,epoch,robot)
            streams[robot]["intent"][seq] = i, intent
        elif kind == "reach_decision":
            robot = p["robot"]
            integer(p["clock_ns"]); integer(p["decision_sequence"], 1)
            require(received is not None or not p["started"], "released decision lacks actual received bundle")
            streams[robot]["decisions"].append((i, p, copy_value(received)))
    require(configuration is not None, "new motion configuration missing")
    return streams


def copy_value(value):
    return json.loads(canonical(value))


def replay_robot(robot, stream, native, epoch, begin, end):
    pubs = {}
    declarations = list(stream["intent"].values())
    require(declarations, "real owner intents missing")
    stopped, prior_intent, fixed_signs, anchor_history = False, None, (), []
    for index, intent in declarations:
        intent_check(intent,epoch,robot)
        target = intent["target"]; seq = target["decision_sequence"]
        require(seq not in pubs or same(pubs[seq], target), "published target identity rewritten")
        pubs[seq] = target
        role = intent["role"]
        require(not stopped or role == "STOP", "permanent STOP resumed")
        if role == "STOP":
            require(prior_intent is not None and intent["lineage"]["previous_role"] == prior_intent["role"]
                    if not stopped else True, "STOP lost previous protected role")
            stopped = True
            require(target["linear_x"] == target["angular_z"] == 0, "STOP published nonzero")
        anchor = intent["anchor"]
        if anchor is not None:
            require(source(anchor["odometry"]) == anchor["source_clock_ns"]
                    and anchor["source_clock_ns"] <= intent["source_clock_ns"]
                    and anchor["source_clock_ns"] in stream["raw"], "anchor has no historical own source")
            require(any(i < index and same(raw, anchor["odometry"])
                        for i, raw in stream["raw"][anchor["source_clock_ns"]]),
                    "anchor is not its immutable earlier received raw payload")
        if anchor is not None and (not anchor_history or not same(anchor_history[-1][1], anchor)):
            require(role in ("HOLD", "D"), "anchor reset outside new qualification")
            anchor_history.append((intent["source_clock_ns"], anchor))
            if role == "D":
                clock = intent["source_clock_ns"]
                before = [p for p in pubs.values() if p["clock_ns"] <= clock]
                last_nonzero_seq = max((p["decision_sequence"] for p in before
                                        if p["linear_x"] != 0 or p["angular_z"] != 0), default=0)
                zero_since = max(begin, min(p["clock_ns"] for p in before
                                            if p["decision_sequence"] > last_nonzero_seq
                                            and p["linear_x"] == p["angular_z"] == 0))
                require(clock-zero_since >= PUB, "D omitted fresh zero-publication qualification")
                stored = [p for _, p in stream["storage"].values() if p["clock_ns"] <= clock]
                last_nonzero_cmd = max((p["cmd_seq"] for p in stored
                                        if p["linear_x"] != 0 or p["angular_z"] != 0), default=0)
                zero_stored = max(begin, min(p["clock_ns"] for p in stored
                                             if p["cmd_seq"] > last_nonzero_cmd
                                             and p["linear_x"] == p["angular_z"] == 0))
                require(clock-zero_stored >= H, "D omitted real zero-storage qualification")
                rest_sources = [s for s in sorted(native["odometry"]) if zero_since+PUB <= s <= clock]
                require(len(rest_sources) >= 3 and clock-rest_sources[-3] <= 100_000_000,
                        "D lacks three fresh later qualifying sources")
                for s in rest_sources[-3:]:
                    require(residual_squared_upper(native["odometry"][s]["odometry"],
                            stream["calibration"][s][1], ()) <= Q(1, 100)**2, "D qualifying raw is not rest")
                zero_actual = [pairs[0] for pairs in native["actuations"].values()
                               if pairs[0]["sim_time_ns"] < anchor["source_clock_ns"]]
                require(zero_actual and zero_actual[-1]["desired_v"] == zero_actual[-1]["desired_w"] == 0,
                        "D has no actual full-zero application and strictly later raw")
                if len(anchor_history) > 2:
                    previous = anchor_history[-2][0]
                    require(any(previous < p[0]["sim_time_ns"] < clock and p[0]["desired_v"] != 0
                                for p in native["actuations"].values()), "unconsumed tiny target reanchored D")
                fixed_signs = ()
        if role == "X":
            signs = tuple(intent["admitted_signs"])
            require(signs and (not fixed_signs or signs == fixed_signs), "preannounced signs changed")
            if not fixed_signs:
                require(prior_intent is not None and prior_intent["role"] == "D",
                        "X bypassed a qualified fixed disk")
                require(target["linear_x"] == target["angular_z"] == 0, "X first announcement is not full zero")
            fixed_signs = signs
        if role == "N":
            require(tuple(intent["admitted_signs"]) == fixed_signs and fixed_signs, "N changed its signed family")
            lineage = intent["lineage"]
            receipt = stream["applied"].get(lineage["actuation_sequence"])
            require(receipt is not None and receipt[0] < index
                    and receipt[1]["source_clock_ns"] == lineage["actuation_source_clock_ns"]
                    and receipt[1]["cmd_seq"] == lineage["cmd_seq"]
                    and lineage["actuation_source_clock_ns"] < lineage["causal_source_clock_ns"]
                    <= intent["source_clock_ns"], "N storage/same-stamp substituted for actual handoff")
            require(lineage["causal_source_clock_ns"] in stream["raw"]
                    and any(i < index for i, _ in stream["raw"][lineage["causal_source_clock_ns"]]),
                    "N has no actual strictly later received raw source")
            if prior_intent is None or prior_intent["role"] != "N":
                require(receipt[1]["target"]["linear_x"] != 0, "first N cites a zero application")
        prior_intent = intent

    # The complete declaration loop above has already validated every target.
    # Original event lookup selected related[-1] over this complete list, even
    # when several declarations cite the same sequence. Preserve that order.
    last_intent_for_target = {intent["target"]["decision_sequence"]: intent
                              for _, intent in declarations}

    for sequence,pairs in native["actuations"].items():
        p=pairs[0]
        if begin <= p["sim_time_ns"] <= end and p["cmd_seq"]:
            require(sequence in stream["applied"] and p["cmd_seq"] in stream["storage"],
                    "actual/source tail has no real applied and storage receipts")

    # Native order distinguishes a target stored before/after a same-tick wheel
    # write. Publication alone never cancels an already active stop obligation.
    event_list = [(s, 0, 0, "raw", row) for s, row in native["odometry"].items() if s <= end]
    event_list += [(row["sim_time_ns"], 1, row["record_sequence"], row["kind"], row)
                   for row in native["records"] if row["kind"] in ("command_received", "actuation")]
    anchor = next((a for clock, a in anchor_history if clock >= begin), None)
    require(anchor is not None, "released HOLD anchor missing")
    signs, actual_motion, first_motion, last_actual = (), False, None, None
    debt, last_motion_guard, previous_raw, previous_angular = None, None, None, None
    last_anchor_id, cumulative, chord_history = canonical(anchor), 0., []
    for clock, _, _, kind, row in sorted(event_list, key=lambda e: e[:3]):
        if clock > end:
            continue
        if kind == "command_received":
            target = pubs.get(row["target_decision_sequence"])
            require(target is not None and target["clock_ns"] == row["target_clock_ns"],
                    "native stored target lacks real owner publication")
            intent = last_intent_for_target[target["decision_sequence"]]
            if intent["role"] == "D" and canonical(intent["anchor"]) != last_anchor_id:
                anchor = intent["anchor"]; last_anchor_id = canonical(anchor)
                signs, actual_motion, first_motion, debt = (), False, None, None
            if intent["role"] == "X":
                signs = tuple(intent["admitted_signs"])
            moving = target["linear_x"] != 0 or target["angular_z"] != 0
            if moving:
                last_motion_guard = target["clock_ns"]
            elif actual_motion and debt is None:
                require(last_motion_guard is not None, "stop lacks previous guard origin")
                debt = {"origin": last_motion_guard, "zero_cmd": row["cmd_seq"],
                        "terminal": None, "resume": None,"path_lower":Q(0),"path_index":0}
        elif kind == "actuation":
            if row["pair_index"] != 0:
                continue
            if not row["cmd_seq"]:
                continue
            t = pubs[row["target_decision_sequence"]]
            moving = t["linear_x"] != 0 or t["angular_z"] != 0
            require(not moving or clock-t["clock_ns"] <= RAW, "actual nonzero missed 20ms renewal")
            if t["linear_x"] != 0:
                require((1 if t["linear_x"] > 0 else -1) in signs, "actual motion escaped announced signs")
                actual_motion = True
                first_motion = clock if first_motion is None else first_motion
            if debt is not None and moving and row["cmd_seq"] > debt["zero_cmd"]:
                debt["resume"] = clock
            last_actual = row
        else:
            raw = row["odometry"]
            if previous_raw is not None:
                d2 = sum((a-b)**2 for a, b in zip(xy(raw), xy(previous_raw)))
                cumulative += math.sqrt(float(d2))
                chord_history.append((source(previous_raw), clock, d2))
            if begin <= clock <= end:
                require(clock in stream["raw"] and clock in stream["calibration"],
                        "complete native source lacks both own raw and actual calibration receipts")
                calib = stream["calibration"][clock][1]
                require(residual_squared_upper(raw, calib, ()) <= Q(3, 10)**2, "physical planar speed certificate fails")
                angular = vector(raw["twist"]["twist"]["angular"])
                require(sum(v*v for v in angular) <= Q(6, 5)**2, "full angular norm exceeded")
                if previous_raw is not None and source(previous_raw) >= begin:
                    require(sum((a-b)**2 for a,b in zip(angular, previous_angular))
                            <= (7*Q(clock-source(previous_raw), 10**9))**2, "sampled angular acceleration exceeded")
                old_disk = first_motion is None or clock <= first_motion
                require(residual_squared_upper(raw, calib, () if old_disk else signs) <= Q(1, 100)**2,
                        "full physical signed residual/rest certificate fails")
                if old_disk:
                    require(sum((a-b)**2 for a,b in zip(xy(raw),xy(anchor["odometry"]))) <= R*R,
                            "fixed HOLD/D anchor disk exceeded")
                if previous_raw is not None:
                    speed = Q(1, 100) if old_disk and source(previous_raw) >= anchor["source_clock_ns"] else Q(3, 10)
                    require(d2 <= (speed*Q(clock-source(previous_raw), 10**9))**2, "sampled physical chord exceeded")
                if debt is not None and debt["resume"] is not None and clock > debt["resume"]:
                    debt = None  # Only an actually consumed successor and later raw retire the old debt.
                if debt is not None:
                    for start,stop,d in chord_history[debt["path_index"]:]:
                        if start >= debt["origin"] and stop <= debt["origin"]+H:
                            debt["path_lower"] += Q(math.isqrt((d.numerator*d.denominator) << 128), d.denominator << 64)
                    debt["path_index"]=len(chord_history)
                    require(debt["path_lower"] <= D, "sampled full-body stop path lower bound exceeded finite-H D")
                    rest = residual_squared_upper(raw, calib, ()) <= Q(1, 100)**2
                    if (debt["terminal"] is None and last_actual is not None
                            and last_actual["sim_time_ns"] < clock
                            and last_actual["desired_v"] == last_actual["desired_w"] == 0 and rest):
                        require(clock <= debt["origin"]+H, "terminal entry missed original global H")
                        debt["terminal"] = copy_value(raw)
                    require(debt["terminal"] is not None or clock <= debt["origin"]+H,
                            "stop deadline was restarted by unconsumed tiny target")
                    if debt["terminal"] is not None:
                        require(sum((a-b)**2 for a,b in zip(xy(raw),xy(debt["terminal"]))) <= R*R,
                                "unconsumed target erased fixed terminal obligation")
                previous_angular = angular
            else:
                previous_angular = vector(raw["twist"]["twist"]["angular"])
            previous_raw = raw
    require(previous_raw is not None and 0 <= end-source(previous_raw) < RAW,
            "final physical/raw tail is incomplete")
    require(last_actual is not None and 0 <= end-last_actual["sim_time_ns"] < ACT,
            "final actual actuation tail is incomplete")
    require(debt is None or debt["terminal"] is not None, "unclosed stop/terminal tail")
    return {"anchors": len(anchor_history), "cumulative_path_diagnostic_m": cumulative,
            "raw_sources": len(native["odometry"]), "actual_updates": len(native["actuations"]),
            "open_terminal_promise": debt is not None}


def _phase_consumptions(consumed, component, request_id, indices):
    """Per-call index only after the original component is actually requested.

    Preserve all duplicates and their original order. Non-string IDs keep the
    original equality scan, including list/dict IDs and bool/int equality. A
    malformed ACK in an unused component is never inspected ahead of its gate.
    """
    if type(request_id) is not str:
        return [row for row in consumed if row.get("component") == component
                and row["ack"]["request_id"] == request_id]
    if component not in indices:
        groups, string_only = {}, True
        for row in consumed:
            if row.get("component") == component:
                value = row["ack"]["request_id"]
                if type(value) is str:
                    groups.setdefault(value, []).append(row)
                else:
                    string_only = False
        indices[component] = groups if string_only else None
    groups = indices[component]
    if groups is None:
        return [row for row in consumed if row.get("component") == component
                and row["ack"]["request_id"] == request_id]
    return groups.get(request_id, [])


def _audit_records(metadata, motion, drivers, odometry_rows, physics, drive_worker,
                   control_worker, information, release_ns, *, initial_encoder_helper_sha256=None,
                   authority_adapter_rows=None, authority_transitions=None, original_protocol_class=None):
    """Artifact replay core; synthetic tests supply declared data, not Git credit."""
    epoch = metadata["epoch"]
    rule = geometry_rule(metadata)
    geometry_kwargs = {"reach_geometry_rule": rule} if rule != DEFAULT_GEOMETRY_RULE else {}
    require(metadata.get("safety_contract") == CONTRACT and metadata.get("quantum_steps") == 20
            and metadata.get("execution_phase_protocol") == "mr3-controlled-execution-phase-v2"
            and metadata.get("reset_handshake") == "paused-controlled-state-peer-guard-storage-v2",
            "old profile/schema cannot acquire reach-runtime credit")
    integer(release_ns)
    advancing = [p for p in physics if p.get("steps", 0) > 0 and p["start_time_ns"] >= release_ns]
    require(advancing, "positive controlled physical observation window missing")
    end = advancing[-1]["end_time_ns"]
    cursor = release_ns
    for p in advancing:
        require(p["epoch"] == epoch and p.get("paused") is True and p.get("ok") is True
                and p["steps"] == 20 and p["step_ns"] == 1_000_000
                and p["start_time_ns"] == cursor and p["end_time_ns"] == cursor+RAW,
                "physical clock did not follow contiguous20ms paused quanta")
        cursor = p["end_time_ns"]
    actuation = selected_actuation_profile(metadata)
    motor_kwargs = ({"actuation_profile": actuation, "encoder_helper_sha256": initial_encoder_helper_sha256}
                    if actuation is not None else {})
    native = native_index(drivers, odometry_rows, epoch, **motor_kwargs)
    streams = ingress_index(motion, native, epoch, **geometry_kwargs)
    authority_profile = selected_motion_authority_profile(metadata)
    authority_summary = authority_context = None
    if authority_profile is not None:
        from . import motion_authority_audit
        require(authority_adapter_rows is not None and authority_transitions is not None
                and original_protocol_class is not None, "new authority profile lacks complete independent callback/owner replay inputs")
        authority_summary, authority_context = motion_authority_audit.replay_motion(motion,native,epoch,release_ns)
    information_bundles = {digest(row["payload"]["message"]):row for row in information
                           if row.get("kind") == "state_publish"}
    groups = {}
    missing_index = len(motion) + 1
    for robot in ROBOTS:
        raw_times = raw_required = None
        act_times = act_required = None
        # Header parsing stays at the original TF gate; an unused malformed tail
        # or future callback must not become an error at index construction.
        tf_callbacks = iter(streams[robot]["tf"].values())
        next_tf = next(tf_callbacks, None)
        tf_keys, tf_values = [], []
        for index, decision, bundle in streams[robot]["decisions"]:
            clock = decision["clock_ns"]
            phase_kind = decision.get("phase_kind", "normal")
            require(phase_kind in ("normal", "stop"), "unknown decision phase")
            group = groups.setdefault((clock,phase_kind), {})
            require(robot not in group, "duplicate robot decision at one physical clock")
            group[robot] = decision
            target = decision["intent"]["target"]
            require(target["decision_sequence"] == decision["decision_sequence"]
                    and target["clock_ns"] == clock and same(decision["decision"]["output"],
                    [target["linear_x"], target["angular_z"]]), "decision lost exact published target")
            known = streams[robot]["intent"].get(decision["intent"]["intent_sequence"])
            require(known is not None and known[0] < index and same(known[1], decision["intent"]),
                    "decision intent was not actually published")
            if not release_ns <= clock <= end:
                continue
            normal_ready = phase_kind == "normal" and decision.get("ready") is True
            if normal_ready:
                if raw_required is None:
                    # Native raw sources are integer and increasing. Missing
                    # receipts remain requirements until the original gate.
                    raw_times, raw_required = [], [0]
                    for s in native[robot]["odometry"]:
                        if s >= release_ns:
                            rows = streams[robot]["raw"].get(s)
                            calibration = streams[robot]["calibration"].get(s)
                            needed = (missing_index if rows is None or calibration is None else
                                      max(min(i for i, _ in rows), calibration[0]))
                            raw_times.append(s)
                            raw_required.append(max(raw_required[-1], needed))
                require(raw_required[bisect_right(raw_times, clock)] < index,
                        "normal decision closed before an actual causal raw/calibration source")
            if act_required is None or not normal_ready:
                # Preserve the original complete loop before indexing: even a
                # STOP/nonready decision compares timestamps before its phase.
                for seq, pairs in native[robot]["actuations"].items():
                    p = pairs[0]
                    if (release_ns <= p["sim_time_ns"] <= clock and p["cmd_seq"]
                            and phase_kind == "normal" and decision.get("ready") is True):
                        require(seq in streams[robot]["applied"] and streams[robot]["applied"][seq][0] < index,
                                "normal decision closed before a real causal application receipt")
                if normal_ready:
                    # Only a successful original scan establishes that every
                    # actual timestamp is comparable before building its index.
                    act_times, act_required = [], [0]
                    for seq, pairs in native[robot]["actuations"].items():
                        p = pairs[0]
                        if p["sim_time_ns"] >= release_ns and p["cmd_seq"]:
                            receipt = streams[robot]["applied"].get(seq)
                            needed = missing_index if receipt is None else receipt[0]
                            act_times.append(p["sim_time_ns"])
                            act_required.append(max(act_required[-1], needed))
            else:
                require(act_required[bisect_right(act_times, clock)] < index,
                        "normal decision closed before a real causal application receipt")
            if decision.get("started") is True and phase_kind == "normal":
                require(bundle is not None and digest(bundle) in information_bundles,
                        "guard received bundle has no actual Information publication")
                require(decision["safety_table_sha256"] == bundle["safety_table_sha256"],
                        "three-guard view substituted a safety table")
                states = {p["name"]:p for p in bundle["robots"]}
                for n,state in states.items():
                    incoming=state["safety"]["intent"]
                    original=streams[n]["intent"].get(incoming["intent_sequence"])
                    require(original is not None and original[0] < index and same(original[1],incoming),
                            "received mode has no identical actual owner publication")
                    s=source(state["odometry"])
                    require(s in native[n]["odometry"] and same(state["odometry"],native[n]["odometry"][s]["odometry"])
                            and s in streams[n]["calibration"]
                            and same(state["safety"]["calibration"],streams[n]["calibration"][s][1]),
                            "received raw/calibration was not the actual native measurement")
                peers = decision["received_peers"]
                require(set(peers) == set(ROBOTS)-{robot}
                        and all(same(peers[n], states[n]) for n in peers), "guard bypassed actually received peers")
                own = decision["own_state"]
                own_source = source(own["odometry"])
                require(own["name"] == robot and own["epoch"] == epoch and own_source <= clock
                        and own_source in streams[robot]["raw"]
                        and same(own["odometry"], native[robot]["odometry"][own_source]["odometry"])
                        and same(own["safety"]["calibration"], streams[robot]["calibration"][own_source][1]),
                        "guard selected unreceived own raw/calibration")
                while next_tf is not None and next_tf[0] < index:
                    key = source({"header": next_tf[1]["header"]}), next_tf[0]
                    position = bisect_right(tf_keys, key)
                    tf_keys.insert(position, key)
                    tf_values.insert(position, next_tf)
                    next_tf = next(tf_callbacks, None)
                position = bisect_right(tf_keys, (clock + 200_000_000, missing_index)) - 1
                require(position >= 0 and same(tf_values[position][1], own["transform"]),
                        "guard selected unreceived/noncausal own TF")
                state_geometry(own,clock,epoch)
                if decision["decision"]["allow"]:
                    require(all(independent_pair(own, peer, clock, epoch, **geometry_kwargs) for peer in peers.values()),
                            "independently recomputed raw/map pair envelope denies admitted motion")
                    if not same(decision["decision"]["output"], [0., 0.]):
                        request = decision["request"]
                        observed = streams[robot]["requests"].get(request["sequence"])
                        require(observed is not None and observed[0] < index and same(observed[1], request),
                                "nonzero decision has no identical actual Nav2 request callback")
                        identity = request["publisher_identity"]
                        endpoints = identity.get("endpoints", [])
                        require(identity.get("scope") == "graph_at_callback"
                                and identity.get("topic") == f"/{robot}/cmd_vel_unguarded"
                                and len(endpoints) == 1 and endpoints[0].get("namespace") == "/"+robot
                                and endpoints[0].get("node") == "velocity_smoother"
                                and endpoints[0].get("topic_type") == "geometry_msgs/msg/Twist",
                                "nonzero request is not the real local Nav2 smoother graph")
                    if authority_profile is not None:
                        permission = authority_context["gates"][robot].decision_permissions.get(decision["decision_sequence"])
                        require(permission is not None and permission["permission"] == "normal_reach"
                                or same(decision["decision"]["output"],[0.,0.]),
                                "guard motion bypassed independently reconstructed receiving authority")
                    admitted_command(decision, own, states[robot], peers, clock, epoch, **geometry_kwargs)
                else:
                    require(decision["decision"]["output"] == [0.,0.], "denied guard issued motion")
            if decision["intent"]["role"] in ("HOLD","STOP"):
                require(target["linear_x"] == target["angular_z"] == 0, "HOLD/STOP output is not full zero")

    advances = {p["request_id"]:p for p in drive_worker if p.get("kind") == "advance_permitted"}
    consumed = [p for p in control_worker if p.get("kind") == "ack_consumed"]
    phase_indices = {}  # Private to this immutable replay, never shared across roles/calls.
    for physical in advancing:
        require(physical["request_id"] in advances, "physical advance lacked its actual worker storage barrier")
        permitted = advances[physical["request_id"]]
        clock, expected = physical["start_time_ns"], permitted["expected_motion"]
        require(permitted["epoch"] == epoch and permitted["steps"] == 20
                and permitted["start_time_ns"] == clock and expected["clock_ns"] == clock
                and expected["schema"] == "mr3-motion-safety-status-v2"
                and expected["safety_contract"] == CONTRACT and set(permitted["receipts"]) == set(ROBOTS)
                and set(groups.get((clock,expected.get("phase_kind","normal")),{})) == set(ROBOTS),
                "advance lacked a fresh joint20ms reach status")
        decisions = groups[clock,expected.get("phase_kind","normal")]
        require(len({d["safety_table_sha256"] for d in decisions.values()}) == 1
                and expected["safety_table_sha256"] == decisions[ROBOTS[0]]["safety_table_sha256"],
                "joint guards did not use one frozen safety table")
        for name in ROBOTS:
            ack = permitted["receipts"][name]
            d = decisions[name]
            require(ack["schema"] == "mr3-drive-target-consumed-v1" and ack["epoch"] == epoch
                    and ack["robot"] == name and ack["clock_ns"] == ack["source_clock_ns"] == clock
                    and ack["decision_sequence"] == d["decision_sequence"] == expected["decision_sequences"][name]
                    and same([ack["linear_x"],ack["angular_z"]], d["decision"]["output"])
                    and same(expected["outputs"][name], {"linear_x":ack["linear_x"],"angular_z":ack["angular_z"]}),
                    "three exact current storage ACKs missing before advance")
            require(expected["intent_refs"][name] == {
                "intent_sequence":d["intent"]["intent_sequence"],"payload_sha256":digest(d["intent"])},
                "worker motion status substituted owner intent references")
            actual = streams[name]["storage"].get(ack["cmd_seq"])
            require(actual is not None and same(actual[1],ack)
                    and motion[actual[0]-1]["wall_monotonic_ns"] <= permitted["wall_monotonic_ns"],
                    "worker substituted an unreceived storage ACK")
        request_id = permitted["control_request_id"]
        required_components = ("motion",) if expected.get("phase_kind") == "stop" else ("state","peer","motion")
        phases = {component:_phase_consumptions(consumed, component, request_id, phase_indices)
                  for component in required_components}
        require(all(len(v)==1 for v in phases.values()), "actual state/peer/motion phase consumption missing")
        for component in required_components:
            ack=phases[component][0]["ack"]
            schema = "mr3-motion-control-ack-v2" if component == "motion" else f"mr3-{component}-phase-ack-v2"
            require(ack["schema"] == schema and ack["epoch"] == epoch and ack["ok"] is True
                    and ack["target_time_ns"] == ack["clock_ns"] == clock, "old or mismatched phase ACK")
        motion_ack=phases["motion"][0]["ack"]
        require(same(motion_ack["status"],expected),"actual motion phase status differs")
        if expected.get("phase_kind") == "stop":
            require(expected.get("ready") is False and all(v=={"linear_x":0.,"angular_z":0.}
                    for v in expected["outputs"].values()),"STOP status claimed readiness or motion")
        else:
            require(same(phases["peer"][0]["ack"]["state_commit"],phases["state"][0]["ack"]),
                    "actual joint phase dependency lineage differs")
    robots = {n:replay_robot(n,streams[n],native[n],epoch,release_ns,end) for n in ROBOTS}
    if authority_profile is not None:
        adapter_proof = motion_authority_audit.replay_adapter(authority_adapter_rows,authority_transitions,
            epoch,authority_context,original_protocol_class)
        authority_summary.update(schema="mr3-independent-motion-authority-episode-v1",passed=True,
            epoch=epoch,adapter=adapter_proof,original_reach_mathematics_passed=True,
            original_global_stop_debts_and_fixed_radius_passed=True)
    return {"passed":True,"contract":CONTRACT,"epoch":epoch,"window_ns":[release_ns,end],
            **({"motion_authority_profile": authority_profile,
                "independent_motion_authority_replay_passed": True,
                "motion_authority_replay": authority_summary} if authority_profile is not None else {}),
            **geometry_kwargs,
            **({"geometry_certificate_semantics":"conditional sufficient separation; unchanged remaining runtime necessities"}
               if geometry_kwargs else {}),
            **({"actuation_profile": actuation,
                "initial_encoder_compound_replay_passed": all(
                    native[name]["initial_encoder_motor_replay"]["passed"] is True for name in ROBOTS),
                "initial_encoder_motor_replay": {name: {key: value for key, value in
                    native[name]["initial_encoder_motor_replay"].items() if key != "actuations"}
                    for name in ROBOTS}} if actuation is not None else {}),
            "robots":robots,"controlled_quanta":len(advancing),
            "independent_necessary_replay":True,"continuous_physical_model_proved":False,
            "scope":"complete observed source/calibration/application/anchor/stop/pair and20ms barrier necessities; "
                    "callback graph identity only, not packet provenance; continuous plant, WORLD/heading "
                    "calibration, global stop envelopes and future terminal confinement remain conditional; "
                    "separate loaded-ELF/build custody audits remain required"}


def audit_episode(directory, expected_freeze=None):
    directory = Path(directory)
    inputs = Inputs()
    metadata = inputs.read(directory,"metadata.json")
    actuation = selected_actuation_profile(metadata, required=True)
    authority = selected_motion_authority_profile(metadata, required=True)
    supervisor = inputs.read(directory, "supervisor_metadata.json")
    require(supervisor.get("epoch") == metadata.get("epoch")
            and selected_actuation_profile(supervisor, required=True) == actuation
            and selected_motion_authority_profile(supervisor, required=True) == authority,
            "supervisor and native selected actuation profiles differ")
    rule = geometry_rule(metadata)
    geometry_kwargs = {"reach_geometry_rule": rule} if rule != DEFAULT_GEOMETRY_RULE else {}
    if geometry_kwargs:
        supervisor = inputs.read(directory, "supervisor_metadata.json")
        require(supervisor.get("epoch") == metadata["epoch"] and geometry_rule(supervisor) == rule,
                "supervisor geometry rule differs from native episode metadata")
    freeze = metadata["freeze"]
    require(expected_freeze is None or freeze == expected_freeze, "episode source freeze differs")
    root = Path(__file__).resolve().parents[7]
    sources = source_proof(root,freeze, motion_authority_profile=authority, **geometry_kwargs)
    transitions = inputs.read(directory,"transitions.jsonl",True)
    resets = [v for v in transitions if v.get("kind") == "reset"]
    require(len(resets)==1, "exactly one actual reset/release required")
    drivers = {n:inputs.read(directory,"drive_"+n+".jsonl",True) for n in ROBOTS}
    odometry = {n:inputs.read(directory,"odometry_"+n+".jsonl",True) for n in ROBOTS}
    driver_sha = sources[NATIVE+"src/mr3_gazebo_diff_drive.cpp"]["sha256"]
    feed_sha = sources[NATIVE+"include/multi_robot/mr3_drive_feed.hpp"]["sha256"]
    for n in ROBOTS:
        cfg, ocfg = drivers[n][0],odometry[n][0]
        for config in (cfg,ocfg):
            require(config.get("compiled_source_sha256") == driver_sha
                    and config.get("compiled_drive_feed_sha256") == feed_sha,
                    "loaded native source/feed header does not match exact new freeze")
        require(cfg.get("native_feeds_enabled") is True
                and cfg.get("applied_feed_schema") == "mr3-drive-applied-v1"
                and cfg.get("applied_feed_scope") == "all_wheel_SetParam_calls_returned_true; not_body_response"
                and cfg.get("odometry_calibration_schema") == "mr3-odom-calibration-v1",
                "old native producer has no qualified actual feed contract")
    result = _audit_records(metadata,inputs.read(directory,"motion_safety.jsonl",True),drivers,odometry,
        inputs.read(directory,"physics.jsonl",True),inputs.read(directory,"drive_phase_worker.jsonl",True),
        inputs.read(directory,"control_phase_worker.jsonl",True),inputs.read(directory,"information_states.jsonl",True),
        resets[0]["info"]["release_time_ns"],
        initial_encoder_helper_sha256=sources[ENCODER_HEADER_SOURCE]["sha256"],
        authority_adapter_rows=inputs.read(directory,"adapter.jsonl",True),
        authority_transitions=transitions,
        original_protocol_class=__import__(__package__+".motion_authority_audit",fromlist=["original_protocol_class"]).original_protocol_class(root))
    inputs.close()
    result.update(source_proof=sources,artifact_proof=inputs.proof,freeze=freeze)
    return result


def run_workers(directory):
    """Worker directories distinguish a RUN from the original EP CLI shape."""
    return sorted(path for path in Path(directory).glob("worker*") if path.is_dir())


def discover_attempts(directory):
    """Include incomplete attempt directories; a missing metadata is a FAIL."""
    directory = Path(directory)
    workers = run_workers(directory)
    if not workers:
        return [directory] if (directory / "metadata.json").is_file() else []
    attempts = []
    for worker in workers:
        episodes = sorted(path for path in worker.glob("episode*") if path.is_dir())
        attempts.extend(episodes or [worker])
    return attempts


def audit_episode_set(directory, expected_freeze, episode_auditor, *, schema):
    """Shared run discovery only; each independent reader keeps its own math."""
    directory = Path(directory).resolve()
    result = {"schema": schema, "directory": str(directory), "freeze": expected_freeze,
              "safety_contract": CONTRACT, "passed": False, "errors": [], "episodes": [],
              "continuous_physical_model_proved": False}
    attempts = discover_attempts(directory)
    if not attempts:
        result["errors"].append("no actual episode attempts found")
    if run_workers(directory) and (directory / "metadata.json").exists():
        result["errors"].append("ambiguous EP and RUN layout; top-level metadata cannot hide child attempts")
    if expected_freeze is not None and (type(expected_freeze) is not str
            or re.fullmatch(r"[0-9a-f]{40}", expected_freeze) is None):
        result["errors"].append("exact source freeze required")
    common_freeze = expected_freeze
    common_geometry_rule = None
    epochs, resolved = set(), set()
    metadata_inputs = {}
    summary_path = directory / "benchmark_summary.json"
    if summary_path.is_file():
        try:
            raw = summary_path.read_bytes(); metadata_inputs[summary_path] = raw
            summary = decode_text(raw.decode())
            common_geometry_rule = geometry_rule(summary)
            declared = [Path(row["output_directory"]).resolve()
                        for worker in summary["workers_results"] for row in worker["episodes"]]
            require(len(declared) == len(set(declared))
                    and set(declared) == {path.resolve() for path in attempts},
                    "declared native episode attempt is missing or unlisted")
        except (OSError, ValueError, TypeError, KeyError) as error:
            result["errors"].append("benchmark episode inventory: "+str(error))
    for episode in attempts:
        row = {"directory": str(episode), "passed": False, "errors": []}
        result["episodes"].append(row)
        try:
            require(episode.resolve() not in resolved, "episode path aliases another attempt")
            resolved.add(episode.resolve())
            if episode != directory:
                require(re.fullmatch(r"worker[0-9]+", episode.parent.name) is not None
                        and episode.name.startswith("episode"), "worker has no valid episode attempt")
            path = episode / "metadata.json"
            raw = path.read_bytes(); metadata_inputs[path] = raw
            metadata = decode_text(raw.decode())
            rule = geometry_rule(metadata)
            if common_geometry_rule is None:
                common_geometry_rule = rule
            require(rule == common_geometry_rule, "reach geometry rule differs across episode attempts/benchmark")
            if rule != DEFAULT_GEOMETRY_RULE:
                row["reach_geometry_rule"] = rule
            epoch, freeze = metadata["epoch"], metadata["freeze"]
            row.update(epoch=epoch, freeze=freeze, metadata_sha256=hashlib.sha256(raw).hexdigest())
            require(type(epoch) is str and bool(epoch) and epoch not in epochs,
                    "empty or duplicate episode epoch")
            epochs.add(epoch)
            require(type(freeze) is str and re.fullmatch(r"[0-9a-f]{40}", freeze) is not None,
                    "episode exact freeze missing")
            if common_freeze is None:
                common_freeze = freeze
            require(freeze == common_freeze, "episode source freeze differs across attempts")
            require(metadata.get("safety_contract") == CONTRACT
                    and metadata.get("execution_phase_protocol") == "mr3-controlled-execution-phase-v2"
                    and metadata.get("reset_handshake") == "paused-controlled-state-peer-guard-storage-v2",
                    "episode is not the explicit reach/v2 profile")
            report = episode_auditor(episode, common_freeze)
            row["result"] = report
            require(type(report) is dict and report.get("passed") is True and not report.get("errors"),
                    "independent episode audit failed")
            require(report.get("epoch") == epoch and report.get("freeze") == freeze,
                    "episode report identity differs from original metadata")
            if "reach_geometry_rule" in report:
                require(geometry_rule({"safety_contract": CONTRACT,
                    "reach_geometry_rule": report["reach_geometry_rule"]}) == rule,
                    "episode report geometry rule differs from native metadata")
            row["passed"] = True
        except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError, OverflowError) as error:
            row["errors"].append(str(error))
            result["errors"].append(str(episode)+": "+str(error))
    if discover_attempts(directory) != attempts:
        result["errors"].append("episode attempt membership changed during audit")
    for path, raw in metadata_inputs.items():
        try:
            require(path.read_bytes() == raw, "episode metadata changed during audit: "+str(path))
        except (OSError, ValueError) as error:
            result["errors"].append(str(error))
    result.update(freeze=common_freeze, attempted_episodes=len(attempts),
                  passed=bool(attempts) and not result["errors"]
                  and all(row["passed"] for row in result["episodes"]))
    if common_geometry_rule is not None and common_geometry_rule != DEFAULT_GEOMETRY_RULE:
        result["reach_geometry_rule"] = common_geometry_rule
    if result["passed"] and all(row.get("result", {}).get("actuation_profile") == encoder_replay.PROFILE
            and row["result"].get("initial_encoder_compound_replay_passed") is True
            for row in result["episodes"]):
        result.update(actuation_profile=encoder_replay.PROFILE, initial_encoder_compound_replay_passed=True)
    return result


def audit(directory, expected_freeze=None):
    result = audit_episode_set(directory, expected_freeze, audit_episode,
                               schema="mr3-reach-runtime-run-audit-v1")
    result.update(contract=CONTRACT, independent_necessary_replay=result["passed"] and all(
        row.get("result", {}).get("independent_necessary_replay") is True for row in result["episodes"]))
    if result["passed"] and not result["independent_necessary_replay"]:
        result["passed"] = False
        result["errors"].append("episode result lacks independent necessary replay")
    return result


def main(argv=None):
    import argparse
    import sys
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode",type=Path)
    parser.add_argument("--freeze",default=None)
    parser.add_argument("--output",type=Path,default=None,
                        help="new report path; existing files are never overwritten")
    args=parser.parse_args(argv)
    output = None
    try:
        if args.output is not None:
            output = args.output.open("x", encoding="utf-8")
    except OSError as error:
        print(json.dumps({"passed":False,"error":str(error),"error_type":type(error).__name__},
                         allow_nan=False), file=sys.stderr)
        return 1
    try:
        result = (audit(args.episode,args.freeze) if run_workers(args.episode)
                  else audit_episode(args.episode,args.freeze))
        code = 0 if result.get("passed") is True else 1
    except Exception as error:
        result = {"passed":False,"contract":CONTRACT,"independent_necessary_replay":False,
                  "continuous_physical_model_proved":False,"error_type":type(error).__name__,
                  "error":str(error)}
        code = 1
    payload = json.dumps(result,indent=2,allow_nan=False)+"\n"
    try:
        if output is not None:
            with output:
                output.write(payload)
        print(payload, end="")
    except OSError as error:
        print(str(error), file=sys.stderr)
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
