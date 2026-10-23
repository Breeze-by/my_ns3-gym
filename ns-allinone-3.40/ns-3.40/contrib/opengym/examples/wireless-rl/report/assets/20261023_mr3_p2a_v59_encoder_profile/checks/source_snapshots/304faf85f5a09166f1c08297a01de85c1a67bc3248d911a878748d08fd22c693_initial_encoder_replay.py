"""Disabled independent initial-zero encoder motor-law replay.

No production helper, wire parser, NumPy, simulator or controller is imported.
Callers must separately prove source/loaded ELF, episode profile, actual native
coverage and physical body response. These functions never alter input rows.
"""
from fractions import Fraction as Q
import json
import math
import re

PROFILE = "initial-zero-encoder-hold-v1"
ALGORITHM = "initial_zero_encoder_hold_then_paired_common_fraction_v1"
OLD_ALGORITHM = "measured_joint_rim_paired_common_fraction_v1"
PERIOD_NS = 34_000_000
RADIUS = 0.033
SEPARATION = 0.287
GAIN = 1.0
FEEDBACK_LIMIT = 0.005
CAPTURE_LIMIT = 0.01
MATH_TOL = 1e-12  # Unchanged independent drive-v4 equation residual bound.
TARGET_FIELDS = {"schema", "epoch", "robot", "clock_ns", "decision_sequence", "linear_x", "angular_z"}
APPLIED_FIELDS = {"schema", "epoch", "robot", "source_clock_ns", "actuation_sequence", "cmd_seq", "dt_ns", "target", "pairs"}
PAIR_FIELDS = {"pair_index", "current_rim_mps", "desired_rim_mps", "applied_rim_mps", "alpha", "max_acceleration_mps2"}
CONFIG_VALUES = {
    "actuation_profile": PROFILE,
    "position_gain_per_second": 1.0,
    "feedback_rim_limit_mps": 0.005,
    "capture_rim_limit_mps": 0.01,
    "capture_consecutive_samples": 3,
    "update_period_ns": PERIOD_NS,
    "reference_capture_count_limit": 1,
    "reference_lifetime": "one fresh plugin object/epoch; Reset does not rearm",
    "received_nonzero_latch": "first successfully validated stored target; not consumption",
    "paired_alpha_target": "encoder servo_desired_rim_mps while armed; body desired after disarm",
    "applied_desired_rim_semantics": "unchanged original body request transform",
    "encoder_source": "local wheel Position/GetVelocity; no unwrap, snap or body-pose feedback",
}
STATE_FIELDS = {
    "actuation_profile", "q_rad", "qd_radps", "body_desired_rim_mps", "servo_desired_rim_mps", "current_rim_mps",
    "update_performed", "armed_before", "armed", "reference_valid_before", "reference_valid", "reference_before_rad",
    "reference_rad", "capture_count_before", "capture_count", "rest_samples_before", "rest_samples",
    "feedback_active", "captured_this_update", "first_nonzero_received_cmd_seq", "first_nonzero_received_clock_ns",
    "first_nonzero_received_target", "written_motor_target_radps", "readback_motor_target_radps",
    "left_SetParam_returned", "right_SetParam_returned",
    "genuine_target_available", "waiting_for_genuine_target", "genuine_target_cmd_seq", "genuine_consumed_target",
}


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def equal(value, expected, message):
    require(canonical(value) == canonical(expected), message)


def integer(value, minimum=0):
    require(type(value) is int and value >= minimum, "invalid typed integer")
    return value


def boolean(value):
    require(type(value) is bool, "invalid boolean state")
    return value


def number(value):
    require(type(value) in (int, float) and math.isfinite(value), "nonfinite or nonnumeric motor value")
    return float(value)


def pair(value):
    require(type(value) is list and len(value) == 2, "RIGHT/LEFT pair required")
    return [number(x) for x in value]


def exact_pair(value, expected, message):
    require(pair(value) == expected, message)


def target(value, epoch, robot, receive_clock):
    require(type(value) is dict and set(value) == TARGET_FIELDS, "target fields differ")
    require(value["schema"] == "mr3-drive-target-v1" and value["epoch"] == epoch and value["robot"] == robot,
            "target identity differs")
    require(integer(value["clock_ns"]) <= receive_clock, "future stored target")
    integer(value["decision_sequence"], 1)
    require(abs(number(value["linear_x"])) <= .20 and abs(number(value["angular_z"])) <= .8,
            "target exceeds unchanged bounds")
    return value


def common_fraction(current, desired, applied, alpha, dt):
    """Original independent drive-v4 algebra and exact acceleration budget.

    The endpoint passed here is the independently reconstructed servo target,
    never a rewritten nominal body target. No production C++ function is used.
    """
    current, desired, applied = pair(current), pair(desired), pair(applied)
    alpha, dt = number(alpha), number(dt)
    require(0 <= alpha <= 1 and dt > 0, "invalid common alpha/time")
    budget = Q.from_float(1.0) * Q.from_float(dt)
    largest = max(abs(Q.from_float(d)-Q.from_float(c)) for c, d in zip(current, desired))
    nominal = Q(1) if largest <= budget else budget/largest
    require(Q.from_float(alpha) <= nominal and abs(float(nominal)-alpha) <= MATH_TOL,
            "common alpha is not nominal rounded inward")
    for c, d, a in zip(current, desired, applied):
        require(abs(a-(c+alpha*(d-c))) <= MATH_TOL, "not one common-alpha convex step")
        require(min(Q.from_float(c), Q.from_float(d)) <= Q.from_float(a) <= max(Q.from_float(c), Q.from_float(d)),
                "motor instruction outside exact segment")
        require(abs(Q.from_float(a)-Q.from_float(c)) <= budget,
                "exact wheel acceleration budget exceeded")


def _state_fields(value, state, suffix=""):
    boolean(value["armed"+suffix]); boolean(value["reference_valid"+suffix])
    require(value["armed"+suffix] == state["armed"] and
            value["reference_valid"+suffix] == state["valid"], "encoder state/arming changed")
    exact_pair(value["reference"+suffix+"_rad"], state["reference"], "encoder reference refreshed or changed")
    require(integer(value["capture_count"+suffix]) == state["count"] and
            integer(value["rest_samples"+suffix]) == state["rest"], "encoder state counter changed")


def replay_native_drive(records, *, profile, epoch, robot, helper_sha256):
    """Check one complete source-ordered driver trace for the explicit new law.

    A None/missing profile is not accepted here. The legacy caller branch must
    execute its existing native reader unchanged instead of silently calling
    this function or bypassing the new law for a selected new Reach profile.
    """
    require(profile == PROFILE and type(profile) is str, "missing or unknown encoder profile")
    require(type(epoch) is str and epoch and robot in ("tb1", "tb2", "tb3"), "bad episode identity")
    require(type(helper_sha256) is str and re.fullmatch("[0-9a-f]{64}", helper_sha256),
            "expected source-bound encoder helper SHA required")
    require(type(records) is list and records, "native encoder records missing")
    state = {"armed": True, "valid": False, "count": 0, "rest": 0, "reference": [0.0, 0.0]}
    first = {"seq": 0, "clock": 0, "target": None}
    configurations = 0
    commands, actuations = {}, {}
    pending = None
    previous_clock, previous_act_clock = -1, None
    previous_target = None
    genuine_target = None
    def first_fields(value):
        require(integer(value["first_nonzero_received_cmd_seq"]) == first["seq"] and
                integer(value["first_nonzero_received_clock_ns"]) == first["clock"],
                "first received nonzero identity changed")
        equal(value["first_nonzero_received_target"], first["target"], "first received nonzero target changed")
    for position, row in enumerate(records, 1):
        require(type(row) is dict and row.get("schema") == "mr3-drive-actuation-v2" and
                row.get("epoch") == epoch and row.get("robot") == robot and
                integer(row.get("record_sequence"), 1) == position, "native record identity/sequence gap")
        clock = integer(row.get("sim_time_ns"))
        require(clock >= previous_clock, "native clock regressed within encoder epoch")
        previous_clock = clock
        kind = row.get("kind")
        if pending is not None:
            require(kind == "command_received", "receive latch not followed by its actual stored command")
        if position == 1:
            require(kind == "configuration" and row.get("actuation_algorithm") == ALGORITHM and
                    row.get("command_mode") == "tagged" and integer(row.get("num_wheel_pairs"), 1) == 1 and
                    number(row.get("update_rate_hz")) == 30 and number(row.get("max_acceleration_mps2")) == 1 and
                    number(row.get("max_torque_nm")) == 20 and row.get("wheel_diameter_m") == [.066] and
                    row.get("wheel_separation_m") == [.287], "unreviewed compound actuator configuration")
            continue
        require(kind != "configuration", "duplicate original actuator configuration")
        if kind == "initial_encoder_configuration":
            require(configurations == 0 and not commands and not actuations, "late or repeated encoder configuration")
            for key, expected in CONFIG_VALUES.items():
                equal(row.get(key), expected, "encoder configuration differs: "+key)
            require(row.get("compiled_encoder_servo_sha256") == helper_sha256,
                    "loaded encoder helper differs from source-bound SHA")
            configurations += 1
        elif kind == "initial_encoder_receive":
            require(configurations == 1 and row.get("actuation_profile") == PROFILE,
                    "receive latch lacks matching selected profile")
            seq = integer(row["cmd_seq"], 1)
            require(seq == len(commands)+1, "receive latch command sequence gap")
            stored = target(row["stored_target"], epoch, robot, clock)
            if previous_target is not None:
                require(stored["decision_sequence"] > previous_target["decision_sequence"] and
                        stored["clock_ns"] >= previous_target["clock_ns"], "accepted target regressed")
            if stored["linear_x"] != 0 or stored["angular_z"] != 0:
                state["armed"], state["rest"] = False, 0
                if first["seq"] == 0:
                    first = {"seq": seq, "clock": clock, "target": stored}
            _state_fields(row, state)
            first_fields(row)
            require(row.get("scope") == "validated_target_storage_and_receive_latch; no consumption_or_wheel_write_claim",
                    "receive latch mislabels consumption")
            pending = {"seq": seq, "target": stored, "clock": clock}
        elif kind == "command_received":
            require(pending is not None and integer(row["cmd_seq"], 1) == pending["seq"] and clock == pending["clock"],
                    "stored command lacks its real receive-latch event")
            stored = pending["target"]
            require(number(row["desired_v"]) == number(stored["linear_x"]) and
                    number(row["desired_w"]) == number(stored["angular_z"]) and
                    integer(row["target_decision_sequence"], 1) == stored["decision_sequence"] and
                    integer(row["target_clock_ns"]) == stored["clock_ns"], "stored target/command identity changed")
            commands[pending["seq"]] = {"row": row, "target": stored}
            previous_target = stored
            genuine_target = stored
            pending = None
        elif kind == "actuation":
            require(configurations == 1 and integer(row.get("pair_index")) == 0, "missing encoder event or unexpected wheel pair")
            seq, cmd_seq = integer(row["actuation_seq"], 1), integer(row["cmd_seq"])
            require(seq == len(actuations)+1 and cmd_seq == len(commands), "actuation sequence/latest stored target differs")
            require(integer(row["dt_ns"], 1) == PERIOD_NS and
                    (previous_act_clock is None or clock-previous_act_clock == PERIOD_NS), "not actual contiguous34ms updates")
            dt = number(row["dt_sec"])
            require(dt > 0 and abs(dt-PERIOD_NS/1e9) <= MATH_TOL and number(row["max_acceleration_mps2"]) == 1,
                    "new actuator cadence or unchanged acceleration differs")
            previous_act_clock = clock
            selected = genuine_target
            latest = commands[cmd_seq]["target"] if cmd_seq else None
            v, w = number(row["desired_v"]), number(row["desired_w"])
            require((selected is None and v == w == 0 and
                     integer(row["target_decision_sequence"]) == (latest["decision_sequence"] if latest else 0) and
                     integer(row["target_clock_ns"]) == (latest["clock_ns"] if latest else 0)) or
                    (selected is not None and v == number(selected["linear_x"]) and w == number(selected["angular_z"]) and
                     row["target_decision_sequence"] == selected["decision_sequence"] and row["target_clock_ns"] == selected["clock_ns"]),
                    "actuation did not consume its actual latest stored target")
            value = row.get("initial_encoder_hold")
            require(type(value) is dict and set(value) == STATE_FIELDS and value["actuation_profile"] == PROFILE,
                    "encoder actuation evidence fields/profile missing")
            _state_fields(value, state, "_before")
            first_fields(value)
            available = selected is not None
            require(boolean(value["genuine_target_available"]) == available and
                    boolean(value["waiting_for_genuine_target"]) == (state["armed"] and not available) and
                    integer(value["genuine_target_cmd_seq"]) == (cmd_seq if available else 0),
                    "genuine target availability or storage identity changed")
            equal(value["genuine_consumed_target"], selected, "genuine selected target changed")
            q, qd = pair(value["q_rad"]), pair(value["qd_radps"])
            current = [x*RADIUS for x in qd]
            body = [v+w*SEPARATION/2.0, v-w*SEPARATION/2.0]
            for data, expected, message in ((row["current_rim_mps"], current, "native current encoder rim mismatch"),
                    (value["current_rim_mps"], current, "encoder event current rim mismatch"),
                    (row["desired_rim_mps"], body, "original APPLIED desired rim is not original body target"),
                    (value["body_desired_rim_mps"], body, "encoder body desired changed")):
                exact_pair(data, expected, message)
            captured = False
            if state["armed"] and available:
                require(v == w == 0 and boolean(value["update_performed"]), "received nonzero escaped permanent latch")
                if not state["valid"]:
                    state["rest"] = state["rest"]+1 if max(map(abs, current)) <= CAPTURE_LIMIT else 0
                    if state["rest"] == 3:
                        state.update(valid=True, count=1, reference=q)
                        captured = True
                raw_feedback = [RADIUS*(r-a)*GAIN for r, a in zip(state["reference"], q)] if state["valid"] else body
                require(all(math.isfinite(x) for x in raw_feedback), "derived servo target is nonfinite")
                effective = [max(-FEEDBACK_LIMIT, min(FEEDBACK_LIMIT, x)) for x in raw_feedback] if state["valid"] else body
            else:
                require(boolean(value["update_performed"]) is False, "disarmed or implicit-zero controller reentered update")
                effective = body
            _state_fields(value, state)
            require(boolean(value["captured_this_update"]) == captured and
                    boolean(value["feedback_active"]) == (state["armed"] and state["valid"] and available),
                    "encoder reference recaptured or feedback state changed")
            exact_pair(value["servo_desired_rim_mps"], effective, "independent P/clamp target differs")
            applied = pair(row["applied_rim_mps"])
            common_fraction(current, effective, applied, row["alpha"], dt)
            written = [x/RADIUS for x in applied]
            exact_pair(value["written_motor_target_radps"], written, "actual written motor target differs")
            exact_pair(value["readback_motor_target_radps"], written, "actual motor readback differs")
            require(value["left_SetParam_returned"] is True and value["right_SetParam_returned"] is True,
                    "actual motor write failed")
            actuations[seq] = {"source_clock_ns": clock, "cmd_seq": cmd_seq, "dt_ns": PERIOD_NS,
                "target": json.loads(canonical(selected)), "pair": json.loads(canonical({key: row[key] for key in PAIR_FIELDS})),
                "state": json.loads(canonical(state)), "first_nonzero_received_cmd_seq": first["seq"]}
        elif kind == "reset":
            require(row.get("target_reset") is True, "unknown native reset semantics")
            genuine_target = None  # The real driver clears its target; encoder state persists.
        elif type(kind) is str and kind.startswith("initial_encoder_"):
            raise ValueError("unknown initial encoder event")
        # Other original audit events retain their original independent predicates.
    require(pending is None and configurations == 1 and commands and actuations, "incomplete encoder/command/actuation trace")
    return {"schema": "mr3-independent-initial-encoder-motor-replay-v1", "profile": PROFILE,
            "epoch": epoch, "robot": robot, "helper_sha256": helper_sha256,
            "passed": True, "command_count": len(commands), "actuation_count": len(actuations),
            "reference_capture_count": state["count"], "first_nonzero_received_cmd_seq": first["seq"],
            "actuations": actuations, "fixed_R_or_continuous_physics_proved": False}


def check_applied_receipt(message, replay):
    require(type(message) is dict and set(message) == APPLIED_FIELDS and
            message["schema"] == "mr3-drive-applied-v1" and message["epoch"] == replay["epoch"] and
            message["robot"] == replay["robot"], "APPLIED exact shape/profile identity differs")
    row = replay["actuations"].get(integer(message["actuation_sequence"], 1))
    require(row is not None and row["cmd_seq"] > 0 and row["target"] is not None, "APPLIED has no actual source-checked motor write")
    require(integer(message["source_clock_ns"]) == row["source_clock_ns"] and integer(message["cmd_seq"], 1) == row["cmd_seq"] and
            integer(message["dt_ns"], 1) == row["dt_ns"], "APPLIED motor clock/sequence differs")
    equal(message["target"], row["target"], "APPLIED original target changed")
    equal(message["pairs"], [row["pair"]], "APPLIED producer/received motor fields differ")
    return True
