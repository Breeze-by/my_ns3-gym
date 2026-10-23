"""Strict shared wire parsing for the received-only MR3 reach contract.

These functions validate structure, identity and causal timestamps. They do
not prove publisher provenance, delivery, immutable history, a physical model
or an actual command application. Callers own those independent obligations.
``now_ns=None`` supports parsing a queued future message; causal consumption
must validate again with the actual clock. Returned objects are detached JSON
copies, so later mutation of a received object cannot alter admitted data.
"""
import hashlib
import json
import math
import struct


INITIAL_ENCODER_ACTUATION_PROFILE = "initial-zero-encoder-hold-v1"


def actuation_profile_for_safety_contract(safety_contract):
    if type(safety_contract) is not str or safety_contract not in ("legacy", "mr3-reach-v1"):
        raise ValueError("unknown safety contract for the actuator")
    return INITIAL_ENCODER_ACTUATION_PROFILE if safety_contract == "mr3-reach-v1" else None


ROBOTS = ("tb1", "tb2", "tb3")
SOURCE_MAX_NS = 500_000_000
INTENT_SCHEMA = "mr3-safety-intent-v1"
APPLIED_SCHEMA = "mr3-drive-applied-v1"
CALIBRATION_SCHEMA = "mr3-odom-calibration-v1"
TARGET_SCHEMA = "mr3-drive-target-v1"
CONVERSION_CONTRACT = "float32-trig-binary64-rn-v1"
PRODUCER_FRAME = "world-common-model-origin-v1"


def _json_value(value):
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float and math.isfinite(value):
        return
    if type(value) is list:
        for item in value:
            _json_value(item)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _json_value(item)
        return
    raise ValueError("expected finite JSON values with string object keys")


def canonical_json(value):
    _json_value(value)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def payload_sha256(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def parse_json(text):
    """Reject duplicate members and nonfinite JSON before a schema is parsed."""
    if type(text) is not str:
        raise ValueError("JSON text must be a string")
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON member")
            result[key] = value
        return result
    def constant(_):
        raise ValueError("nonfinite JSON constant")
    value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
    _json_value(value)
    return value


def _copy(value):
    return json.loads(canonical_json(value))


def _fields(value, fields):
    if type(value) is not dict or set(value) != set(fields):
        raise ValueError("unexpected wire object fields")


def _integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError("invalid integer identity or timestamp")
    return value


def _number(value):
    if type(value) not in (int, float):
        raise ValueError("expected a finite numeric scalar, not a boolean")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("numeric scalar exceeds the finite wire range")
    return value


def _string(value):
    if type(value) is not str or not value:
        raise ValueError("missing string identity")


def _digest(value):
    if (type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ValueError("invalid SHA256 reference")


def _identity(value, schema, epoch, robot):
    _string(epoch)
    if robot not in ROBOTS or value["schema"] != schema or value["epoch"] != epoch or value["robot"] != robot:
        raise ValueError("wrong safety schema, epoch or robot")


def _causal(source, now_ns, max_age_ns):
    _integer(source); _integer(max_age_ns)
    if now_ns is not None:
        _integer(now_ns)
        if not 0 <= now_ns-source <= max_age_ns:
            raise ValueError("future or stale safety evidence")


def _stamp(value):
    _fields(value, ("sec", "nanosec"))
    _integer(value["sec"]); _integer(value["nanosec"])
    if value["nanosec"] >= 1_000_000_000:
        raise ValueError("noncanonical nanosecond timestamp")
    return value["sec"]*1_000_000_000+value["nanosec"]


def _vector(value, dimensions=("x", "y", "z")):
    _fields(value, dimensions)
    for component in value.values():
        _number(component)


def _covariance(value):
    if type(value) is not list or len(value) != 36:
        raise ValueError("complete 36-component covariance required")
    for component in value:
        _number(component)


def validate_odometry(value):
    """Validate the entire existing odom_payload structure, without TF truth."""
    _fields(value, ("header", "child_frame_id", "pose", "twist"))
    _fields(value["header"], ("stamp", "frame_id"))
    _stamp(value["header"]["stamp"]); _string(value["header"]["frame_id"])
    _string(value["child_frame_id"])
    _fields(value["pose"], ("pose", "covariance"))
    _fields(value["pose"]["pose"], ("position", "orientation"))
    _vector(value["pose"]["pose"]["position"])
    _vector(value["pose"]["pose"]["orientation"], ("x", "y", "z", "w"))
    _covariance(value["pose"]["covariance"])
    _fields(value["twist"], ("twist", "covariance"))
    _fields(value["twist"]["twist"], ("linear", "angular"))
    _vector(value["twist"]["twist"]["linear"])
    _vector(value["twist"]["twist"]["angular"])
    _covariance(value["twist"]["covariance"])
    return _copy(value)


def odometry_source_ns(value):
    validate_odometry(value)
    return _stamp(value["header"]["stamp"])


def validate_target(value, *, epoch, robot, now_ns=None):
    _fields(value, ("schema", "epoch", "robot", "clock_ns", "decision_sequence", "linear_x", "angular_z"))
    _identity(value, TARGET_SCHEMA, epoch, robot)
    _integer(value["clock_ns"]); _integer(value["decision_sequence"], 1)
    if now_ns is not None:
        _integer(now_ns)
        if value["clock_ns"] > now_ns:
            raise ValueError("future target")
    if abs(_number(value["linear_x"])) > .20 or abs(_number(value["angular_z"])) > .8:
        raise ValueError("target exceeds unchanged drive bounds")
    return _copy(value)


def _anchor(value, source_clock_ns):
    _fields(value, ("source_clock_ns", "odometry"))
    _integer(value["source_clock_ns"])
    if (odometry_source_ns(value["odometry"]) != value["source_clock_ns"]
            or value["source_clock_ns"] > source_clock_ns):
        raise ValueError("anchor is not its historical causal odometry")


def _signs(value):
    if (type(value) is not list or len(value) > 2
            or any(type(x) is not int or x not in (-1, 1) for x in value)
            or len(set(value)) != len(value)):
        raise ValueError("explicit duplicate-free admitted signed family required")


def validate_intent(value, *, epoch, robot, now_ns=None, max_age_ns=SOURCE_MAX_NS):
    _fields(value, ("schema", "epoch", "robot", "intent_sequence", "source_clock_ns",
                    "role", "anchor", "admitted_signs", "lineage", "target"))
    _identity(value, INTENT_SCHEMA, epoch, robot)
    sequence = _integer(value["intent_sequence"], 1)
    source = _integer(value["source_clock_ns"])
    _causal(source, now_ns, max_age_ns)
    role, anchor, signs, lineage, target = (value[key] for key in
                                          ("role", "anchor", "admitted_signs", "lineage", "target"))
    if role not in ("HOLD", "D", "X", "N", "STOP"):
        raise ValueError("unknown safety intent role")
    _signs(signs)
    if anchor is not None:
        _anchor(anchor, source)
    if target is not None:
        validate_target(target, epoch=epoch, robot=robot, now_ns=source)
    if role == "HOLD":
        _fields(lineage, ("release_clock_ns",))
        release = lineage["release_clock_ns"]
        if release is None:
            if anchor is not None:
                raise ValueError("pre-release HOLD cannot invent an anchor")
        else:
            _integer(release)
            if anchor is None or not anchor["source_clock_ns"] <= release <= source or target is None:
                raise ValueError("post-release HOLD needs its fixed causal anchor and zero target")
        if signs or target is not None and (target["linear_x"] != 0 or target["angular_z"] != 0):
            raise ValueError("HOLD is a full-zero request, not an admitted signed family")
    elif role in ("D", "X", "N"):
        keys = {"anchor_intent_sequence"}
        if role != "D":
            keys.add("transition_intent_sequence")
        if role == "N":
            keys.update(("actuation_sequence", "actuation_source_clock_ns", "causal_source_clock_ns", "cmd_seq"))
        _fields(lineage, keys)
        if anchor is None or target is None:
            raise ValueError("active reach needs its historical anchor and exact target")
        anchor_sequence = _integer(lineage["anchor_intent_sequence"], 1)
        if anchor_sequence > sequence:
            raise ValueError("future anchor lineage")
        if role == "D":
            if signs or target["linear_x"] != 0:
                raise ValueError("D requires a zero-linear target and no signed sector")
        else:
            transition_sequence = _integer(lineage["transition_intent_sequence"], 1)
            if not anchor_sequence < transition_sequence <= sequence or not signs:
                raise ValueError("incomplete disk-to-normal lineage or signed family")
            velocity = target["linear_x"]
            if velocity != 0 and (1 if velocity > 0 else -1) not in signs:
                raise ValueError("target changes its announced signed family")
        if role == "N":
            _integer(lineage["actuation_sequence"], 1); _integer(lineage["cmd_seq"], 1)
            applied = _integer(lineage["actuation_source_clock_ns"])
            causal = _integer(lineage["causal_source_clock_ns"])
            if not anchor["source_clock_ns"] <= applied < causal <= source:
                raise ValueError("normal reach lacks strict post-actuation causal source")
            _causal(causal, now_ns, max_age_ns)
    else:
        _fields(lineage, ("previous_intent_sequence", "previous_role"))
        previous = _integer(lineage["previous_intent_sequence"], 1)
        previous_role = lineage["previous_role"]
        if previous >= sequence or previous_role not in ("HOLD", "D", "X", "N"):
            raise ValueError("STOP must retain its actual previous reach role")
        if target is not None and (target["linear_x"] != 0 or target["angular_z"] != 0):
            raise ValueError("STOP only permits a full-zero target")
        if previous_role in ("D", "X", "N") and anchor is None:
            raise ValueError("STOP cannot erase the previous protected anchor")
        if (previous_role in ("HOLD", "D") and signs
                or previous_role in ("X", "N") and not signs):
            raise ValueError("STOP cannot replace the previous signed family")
    return _copy(value)


def validate_calibration(value, *, epoch, robot, now_ns=None, max_age_ns=SOURCE_MAX_NS):
    _fields(value, ("schema", "epoch", "robot", "source_clock_ns", "publication_sequence",
                    "coefficient_c", "coefficient_s", "odometry", "conversion_contract", "producer_frame"))
    _identity(value, CALIBRATION_SCHEMA, epoch, robot)
    _causal(value["source_clock_ns"], now_ns, max_age_ns)
    _integer(value["publication_sequence"], 1)
    c, s = (_number(value[key]) for key in ("coefficient_c", "coefficient_s"))
    if (abs(c) > 1 or abs(s) > 1 or c*c+s*s == 0
            or any(struct.unpack("!f", struct.pack("!f", x))[0] != x for x in (c, s))
            or value["conversion_contract"] != CONVERSION_CONTRACT or value["producer_frame"] != PRODUCER_FRAME
            or odometry_source_ns(value["odometry"]) != value["source_clock_ns"]):
        raise ValueError("calibration does not describe the exact WORLD odometry conversion")
    return _copy(value)


def validate_native_applied(value, *, epoch, robot, now_ns=None, max_age_ns=SOURCE_MAX_NS):
    """Parse an actual tagged application receipt, never a precommand fiction.

    Finite pair fields do not prove the paired-slew algorithm, a body velocity
    or stream completeness. Runtime checks must establish those separately.
    """
    _fields(value, ("schema", "epoch", "robot", "source_clock_ns", "actuation_sequence", "cmd_seq", "dt_ns", "target", "pairs"))
    _identity(value, APPLIED_SCHEMA, epoch, robot)
    _causal(value["source_clock_ns"], now_ns, max_age_ns)
    _integer(value["actuation_sequence"], 1); _integer(value["cmd_seq"], 1); _integer(value["dt_ns"], 1)
    validate_target(value["target"], epoch=epoch, robot=robot, now_ns=value["source_clock_ns"])
    pairs = value["pairs"]
    if type(pairs) is not list or not pairs:
        raise ValueError("actual wheel pairs required")
    for index, pair in enumerate(pairs):
        _fields(pair, ("pair_index", "current_rim_mps", "desired_rim_mps", "applied_rim_mps", "alpha", "max_acceleration_mps2"))
        if _integer(pair["pair_index"]) != index:
            raise ValueError("wheel pair identity changed or is incomplete")
        for key in ("current_rim_mps", "desired_rim_mps", "applied_rim_mps"):
            if type(pair[key]) is not list or len(pair[key]) != 2:
                raise ValueError("RIGHT/LEFT wheel array required")
            for number in pair[key]:
                _number(number)
        if not 0 <= _number(pair["alpha"]) <= 1 or _number(pair["max_acceleration_mps2"]) < 0:
            raise ValueError("invalid finite paired-slew parameters")
    return _copy(value)


def validate_safety(value, *, epoch, robot, selected_odom, now_ns=None, max_age_ns=SOURCE_MAX_NS):
    _fields(value, ("intent", "calibration"))
    intent = validate_intent(value["intent"], epoch=epoch, robot=robot, now_ns=now_ns, max_age_ns=max_age_ns)
    calibration = validate_calibration(value["calibration"], epoch=epoch, robot=robot, now_ns=now_ns, max_age_ns=max_age_ns)
    selected = validate_odometry(selected_odom)
    if canonical_json(calibration["odometry"]) != canonical_json(selected):
        raise ValueError("calibration must bind the exact selected raw odometry")
    if intent["role"] == "N" and intent["lineage"]["causal_source_clock_ns"] > odometry_source_ns(selected):
        raise ValueError("normal causal source is newer than the delivered measurement")
    anchor = intent["anchor"]
    if anchor is not None and (anchor["odometry"]["header"]["frame_id"] != selected["header"]["frame_id"]
                               or anchor["odometry"]["child_frame_id"] != selected["child_frame_id"]):
        raise ValueError("historical anchor and current measurement changed frames")
    return {"intent": intent, "calibration": calibration}


def validate_intent_refs(value, *, robots):
    if (not isinstance(robots, (tuple, list)) or len(robots) != 3
            or any(type(name) is not str for name in robots) or set(robots) != set(ROBOTS)):
        raise ValueError("the exact three-robot team is required")
    _fields(value, robots)
    for reference in value.values():
        _fields(reference, ("intent_sequence", "payload_sha256"))
        _integer(reference["intent_sequence"], 1); _digest(reference["payload_sha256"])
    return _copy(value)
