"""Received-state peer braking gate; it never chooses exploration or steering.

The near region reserves both robots' bounded reaction and stopping travel.
Inside it, every robot must contribute non-closing motion for every peer
position in the source-age uncertainty disk and every heading in its bounded
turn/braking interval. This is a shared guard contract, not a promise against
an unguarded peer, unbounded localization jumps or invalid actuator bounds.
Reaction/stopping reserve covers in-flight motion. A zero linear output is a
braking request; a delayed zero-twist source does not establish current rest.
"""

from collections import deque
import hashlib
import json
import math

from multi_robot_exploration.mr3_episode import elapsed_ns, timestamp_ns


ROBOTS = ("tb1", "tb2", "tb3")
BODY_RADIUS_M = .25  # Existing Waffle full-body disk; actual collision radius < .238 m.
COMMAND_SPEED_LIMIT = .26
MEASURED_SPEED_BOUND = .30
COMMAND_TURN_LIMIT = .8
MEASURED_TURN_BOUND = 1.2
TURN_ACCEL_BOUND_RADPS2 = 7.0  # 2 * model wheel-rim 1 m/s² / .287 m wheel separation.
SOURCE_MAX_AGE_SEC = .5
REACTION_SEC = .16
BRAKING_DECEL_MPS2 = .5
TURN_STOP_PADDING_SEC = .02
GEOMETRY_MARGIN_M = .02
PERIOD_SEC = .02
COMMAND_TIMEOUT_SEC = .2
REST_SPEED_BOUND = .01
STOP_HORIZON_SEC = REACTION_SEC + MEASURED_SPEED_BOUND / BRAKING_DECEL_MPS2 + TURN_STOP_PADDING_SEC
SETTLE_PUBLICATION_SEC = STOP_HORIZON_SEC + REACTION_SEC
REST_SOURCE_GAP_NS = 100_000_000
REST_DRIFT_BUDGET_M = REST_SPEED_BOUND * STOP_HORIZON_SEC


class SettledTurnTracker:
    """Own issued targets and complete local odometry, never peer raw sensors.

    Qualification requires .94 s of zero-line publications and three later
    fresh rest samples. The separate native audit must establish <=.16 s
    actual storage latency and >=.78 s of stored zero-line history. Continued
    <=.01 m/s and total centre travel <=.0078 m throughout the uninterrupted
    zero-line segment are explicit conditional plant invariants, not theorems
    inferred from past samples. Sampled odometry chords are necessary checks,
    not a proof of the continuous path bound.
    """

    def __init__(self):
        self.zero_since_ns = None
        self.last_zero_decision_sequence = None
        self.active_since_ns = None
        self.active_anchor_source_ns = None
        self.active_path_m = 0.
        self.samples = deque(maxlen=3)
        self.latest = None
        self.last_output_clock_ns = None
        self.last_output_sequence = None
        self.release_ns = None

    def release(self, clock_ns):
        """Start qualification after the worker's initial stored-zero barrier."""
        if (type(clock_ns) is not int or clock_ns < 0 or self.release_ns is not None
                or self.active_since_ns is not None):
            raise ValueError("invalid or repeated settled turn release")
        self.release_ns = clock_ns
        if self.zero_since_ns is not None:
            self.zero_since_ns = max(self.zero_since_ns, clock_ns)
        self.samples.clear()

    def output(self, linear, clock_ns, sequence):
        if (type(clock_ns) is not int or clock_ns < 0 or type(sequence) is not int
                or sequence <= 0 or not math.isfinite(linear)
                or (self.last_output_clock_ns is not None
                    and clock_ns < self.last_output_clock_ns)
                or (self.last_output_sequence is not None
                    and sequence <= self.last_output_sequence)):
            raise ValueError("settled turn output clock or sequence regressed")
        self.last_output_clock_ns = clock_ns
        self.last_output_sequence = sequence
        if linear != 0.:
            self.zero_since_ns = None
            self.last_zero_decision_sequence = None
            self.active_since_ns = None
            self.active_anchor_source_ns = None
            self.active_path_m = 0.
            self.samples.clear()
        else:
            if self.zero_since_ns is None:
                self.zero_since_ns = clock_ns
            if clock_ns < self.zero_since_ns:
                raise ValueError("settled turn output clock regressed")
            self.last_zero_decision_sequence = sequence

    def observe(self, payload, sequence):
        stamp = payload["header"]["stamp"]
        if (type(stamp["sec"]) is not int or type(stamp["nanosec"]) is not int
                or stamp["sec"] < 0 or not 0 <= stamp["nanosec"] < 1_000_000_000):
            raise ValueError("invalid settled turn odometry stamp")
        source_ns = stamp["sec"] * 1_000_000_000 + stamp["nanosec"]
        if source_ns <= 0:
            raise ValueError("empty settled turn odometry")
        # Odometry can reach this callback before its /clock callback (the
        # native 20 ms quantum commonly does so). Retain its real source;
        # certificate() and valid_state() reject use before that clock arrives.
        linear = payload["twist"]["twist"]["linear"]
        position = payload["pose"]["pose"]["position"]
        if any(type(linear[key]) not in (int, float) or not math.isfinite(linear[key])
               or type(position[key]) not in (int, float) or not math.isfinite(position[key])
               for key in ("x", "y", "z")):
            raise ValueError("nonfinite settled turn odometry")
        speed = math.hypot(linear["x"], linear["y"])
        encoded = json.dumps(payload, sort_keys=True, allow_nan=False, separators=(",", ":"))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        sample = {"source_ns": source_ns, "input_sequence": sequence,
                  "planar_speed_mps": speed, "odom_sha256": digest}
        if self.latest is not None:
            previous, previous_payload = self.latest
            if source_ns < previous["source_ns"]:
                raise ValueError("settled turn odometry source regressed")
            if source_ns == previous["source_ns"]:
                if digest != previous["odom_sha256"]:
                    raise ValueError("conflicting settled turn odometry source")
                return
            if (payload["header"]["frame_id"] != previous_payload["header"]["frame_id"]
                    or payload["child_frame_id"] != previous_payload["child_frame_id"]):
                raise ValueError("settled turn odometry frame changed")
            gap = source_ns - previous["source_ns"]
            if gap > REST_SOURCE_GAP_NS:
                self.samples.clear()
                if self.active_since_ns is not None:
                    raise ValueError("active settled turn odometry gap")
        # Check before discarding qualification: a breach is a real model failure.
        if self.active_since_ns is not None and speed > REST_SPEED_BOUND:
            raise ValueError("active settled turn drift bound exceeded")
        if self.active_since_ns is not None:
            previous_position = self.latest[1]["pose"]["pose"]["position"]
            chord = math.hypot(
                position["x"] - previous_position["x"],
                position["y"] - previous_position["y"])
            self.active_path_m += chord
            if chord / ((source_ns - self.latest[0]["source_ns"]) / 1e9) > REST_SPEED_BOUND:
                raise ValueError("active settled turn chord speed bound exceeded")
            if self.active_path_m > REST_DRIFT_BUDGET_M:
                raise ValueError("active settled turn total drift budget exceeded")
        self.latest = (sample, payload)
        if (self.zero_since_ns is None
                or source_ns < self.zero_since_ns + timestamp_ns(SETTLE_PUBLICATION_SEC)
                or speed > REST_SPEED_BOUND):
            self.samples.clear()
        else:
            self.samples.append(sample)

    def certificate(self, now_ns):
        if self.latest is None:
            return None
        age = now_ns - self.latest[0]["source_ns"]
        if age < 0:
            return None
        if age > REST_SOURCE_GAP_NS:
            self.samples.clear()
            if self.active_since_ns is not None:
                raise ValueError("active settled turn source unavailable")
        if len(self.samples) != 3 or self.zero_since_ns is None:
            return None
        if now_ns - self.samples[0]["source_ns"] > REST_SOURCE_GAP_NS:
            return None
        return {"schema": "mr3-settled-turn-v1", "zero_since_ns": self.zero_since_ns,
                "last_zero_decision_sequence": self.last_zero_decision_sequence,
                "samples": list(self.samples), "active_since_ns": self.active_since_ns,
                "active_anchor_source_ns": self.active_anchor_source_ns,
                "active_path_m": self.active_path_m}

    def activate(self, now_ns):
        if self.certificate(now_ns) is None:
            raise ValueError("settled turn activation lacks certificate")
        if self.active_since_ns is None:
            self.active_since_ns = now_ns
            self.active_anchor_source_ns = self.latest[0]["source_ns"]


def valid_settled_turn(own, now):
    """Validate the recorded own-only certificate; history is independently replayed."""
    value = own.get("settled_turn")
    if (not isinstance(value, dict) or value.get("schema") != "mr3-settled-turn-v1"
            or type(value.get("zero_since_ns")) is not int or value["zero_since_ns"] < 0
            or type(value.get("last_zero_decision_sequence")) is not int
            or value["last_zero_decision_sequence"] <= 0
            or not isinstance(value.get("samples"), list) or len(value["samples"]) != 3
            or type(own.get("odom_source_stamp")) not in (int, float)
            or not math.isfinite(own["odom_source_stamp"])
            or (value.get("active_since_ns") is not None and (
                type(value["active_since_ns"]) is not int
                or not value["zero_since_ns"] <= value["active_since_ns"] <= timestamp_ns(now)))
            or type(value.get("active_path_m")) not in (int, float)
            or not math.isfinite(value["active_path_m"])
            or not 0 <= value["active_path_m"] <= REST_DRIFT_BUDGET_M
            or type(own.get("planar_speed_mps")) not in (int, float)
            or not math.isfinite(own["planar_speed_mps"])
            or not abs(own["v"]) <= own["planar_speed_mps"] <= REST_SPEED_BOUND):
        return False
    now_ns = timestamp_ns(now)
    previous = None
    for sample in value["samples"]:
        if (not isinstance(sample, dict) or type(sample.get("source_ns")) is not int
                or not value["zero_since_ns"] + timestamp_ns(SETTLE_PUBLICATION_SEC)
                <= sample["source_ns"] <= now_ns
                or now_ns - sample["source_ns"] > REST_SOURCE_GAP_NS
                or type(sample.get("input_sequence")) is not int
                or sample["input_sequence"] <= 0
                or type(sample.get("planar_speed_mps")) not in (int, float)
                or not math.isfinite(sample["planar_speed_mps"])
                or not 0 <= sample["planar_speed_mps"] <= REST_SPEED_BOUND
                or not isinstance(sample.get("odom_sha256"), str)
                or len(sample["odom_sha256"]) != 64
                or any(character not in "0123456789abcdef"
                       for character in sample["odom_sha256"])):
            return False
        if previous is not None and (
                not 0 < sample["source_ns"] - previous["source_ns"] <= REST_SOURCE_GAP_NS
                or sample["input_sequence"] <= previous["input_sequence"]):
            return False
        previous = sample
    active = value.get("active_since_ns")
    anchor = value.get("active_anchor_source_ns")
    if (active is None and (anchor is not None or value["active_path_m"] != 0.)
            or active is not None and (type(anchor) is not int or not 0 < anchor <= active)):
        return False
    return (0 <= now_ns - previous["source_ns"] <= REST_SOURCE_GAP_NS
            and previous["source_ns"] == timestamp_ns(own["odom_source_stamp"])
            and previous["planar_speed_mps"] == own["planar_speed_mps"])


def valid_state(state, now, epoch):
    """Reject missing/nonfinite, cross-epoch, future and stale received inputs."""
    if (type(now) not in (int, float) or not math.isfinite(now) or now < 0
            or not isinstance(state, dict) or state.get("epoch") != epoch
            or state.get("valid") is not True):
        return False
    fields = ("x", "y", "yaw", "v", "w", "source_stamp")
    if any(type(state.get(key)) not in (int, float) or not math.isfinite(state[key])
           for key in fields):
        return False
    for key in ("odom_source_stamp", "tf_source_stamp"):
        if key in state and (type(state[key]) not in (int, float)
                             or not math.isfinite(state[key]) or state[key] <= 0
                             or not 0 <= elapsed_ns(state[key], now)
                             <= timestamp_ns(SOURCE_MAX_AGE_SEC)):
            return False
    return (state["source_stamp"] > 0
            and 0 <= elapsed_ns(state["source_stamp"], now) <= timestamp_ns(SOURCE_MAX_AGE_SEC)
            and abs(state["v"]) <= MEASURED_SPEED_BOUND
            and abs(state["w"]) <= MEASURED_TURN_BOUND)


def maximum_heading_projection(dx, dy, heading, half_angle):
    """Exact maximum dot product over the complete closed heading interval."""
    bearing = math.atan2(dy, dx)
    difference = math.atan2(math.sin(bearing - heading), math.cos(bearing - heading))
    distance = math.hypot(dx, dy)
    if half_angle >= math.pi or abs(difference) <= half_angle:
        return distance
    return max(dx * math.cos(heading - half_angle) + dy * math.sin(heading - half_angle),
               dx * math.cos(heading + half_angle) + dy * math.sin(heading + half_angle))


def guard_motion(request, own, peers, now, epoch):
    """Return a bounded differential-drive request or zero.

    Nav2's smoother can round a declared endpoint one binary64 neighbour
    outward. Only that exact adjacent value is canonicalized to the endpoint;
    a second neighbour or any larger excess remains unsupported. Original
    callback values and explicit normalization metadata remain auditable.

    A rejected mixed request may retain only its requested angular component,
    after independently passing this same complete gate with zero linear speed.
    The .5 m/s² parameter describes a global stopping envelope, not an
    instantaneous centre-speed deceleration guarantee. Independent bounded
    wheel analysis gives .6157 s worst stop time; .16 s reaction plus that
    time is covered by the .78 s horizon with .02 s coupling padding. Native
    motion still has to validate the declared speed/actuator model bounds.

    Source-age expansion is separate from .16 s reaction: .10 s request,
    .02 s gate, 1/30 s actuator and the remaining command delivery allowance.
    Both actual and requested translational directions must be non-closing in
    a near region. Pure rotation is safe for the fixed circumscribed body disk.
    """
    result = {"allow": False, "reason": "state_unavailable", "output": [0., 0.],
              "minimum_margin_m": None, "body_margin_m": None,
              "braking_zone_margin_m": None, "near_peer_checks": [],
              "command_normalization": None, "component_filter": None}
    if (type(now) not in (int, float) or not math.isfinite(now)
            or not valid_state(own, now, epoch) or set(peers) != set(ROBOTS) - {own.get("name")}
            or any(not valid_state(peer, now, epoch) for peer in peers.values())):
        return result
    valid_request = (isinstance(request, (list, tuple)) and len(request) == 2
                     and all(type(value) in (int, float) and math.isfinite(value)
                             for value in request))
    if not valid_request:
        result["reason"] = "unsupported_command"
        return result
    canonical, normalized_axes = [], []
    for axis, value, limit in zip(("v", "w"), request,
                                  (COMMAND_SPEED_LIMIT, COMMAND_TURN_LIMIT)):
        if abs(value) > limit:
            if abs(value) != math.nextafter(limit, math.inf):
                result["reason"] = "unsupported_command"
                return result
            value = math.copysign(limit, value)
            normalized_axes.append(axis)
        canonical.append(value)
    if normalized_axes:
        result["command_normalization"] = {
            "schema": "mr3-command-one-ulp-v1", "input": list(request),
            "canonical": canonical, "normalized_axes": normalized_axes,
        }
    v, w = canonical
    own_age = elapsed_ns(own["source_stamp"], now) / 1e9
    # Position/yaw use the older odom/TF source. Angular velocity comes from
    # odometry, so pending acceleration starts at that measurement's own time.
    odom_source_stamp = own.get("odom_source_stamp", own["source_stamp"])
    odom_age = elapsed_ns(odom_source_stamp, now) / 1e9
    body_margins, zone_margins, direction_margins = [], [], []
    for name, peer in peers.items():
        dx, dy = peer["x"] - own["x"], peer["y"] - own["y"]
        distance = math.hypot(dx, dy)
        uncertainty = MEASURED_SPEED_BOUND * (
            own_age + elapsed_ns(peer["source_stamp"], now) / 1e9)
        body_margin = distance - 2 * BODY_RADIUS_M - uncertainty - GEOMETRY_MARGIN_M
        braking_reserve = (2 * MEASURED_SPEED_BOUND * (REACTION_SEC + TURN_STOP_PADDING_SEC)
                           + MEASURED_SPEED_BOUND ** 2 / BRAKING_DECEL_MPS2)
        zone_margin = body_margin - braking_reserve
        check = {"peer": name, "centre_distance_m": distance,
                 "source_uncertainty_m": uncertainty, "body_margin_m": body_margin,
                 "braking_zone_margin_m": zone_margin, "near": zone_margin <= 0,
                 "direction_checks": []}
        body_margins.append(body_margin)
        zone_margins.append(zone_margin)
        if zone_margin <= 0:
            # A zero command cannot remove the already-moving body's stopping
            # distance. Check the measured direction as well as the new request.
            # The delayed twist may predate acceleration under an earlier
            # command. Reserve the full declared speed bound, even for a small
            # current request and an old zero-speed observation.
            horizon = (REACTION_SEC + MEASURED_SPEED_BOUND / BRAKING_DECEL_MPS2
                       + TURN_STOP_PADDING_SEC)
            possible_turn = min(MEASURED_TURN_BOUND,
                                abs(own["w"]) + TURN_ACCEL_BOUND_RADPS2 * odom_age)
            turn_bound = max(abs(w), possible_turn)
            half_angle = MEASURED_TURN_BOUND * own_age + turn_bound * horizon
            directions = {math.copysign(1., value) for value in (v, own["v"])
                          if abs(value) > 1e-4}
            for sign in sorted(directions):
                heading = own["yaw"] + (math.pi if sign < 0 else 0.)
                projection = maximum_heading_projection(dx, dy, heading, half_angle)
                margin = -projection - uncertainty
                direction_margins.append(margin)
                check["direction_checks"].append({
                    "sign": sign, "horizon_sec": horizon, "turn_bound_radps": turn_bound,
                    "geometry_source_stamp": own["source_stamp"],
                    "geometry_source_age_sec": own_age,
                    "angular_velocity_source_stamp": odom_source_stamp,
                    "angular_velocity_source_age_sec": odom_age,
                    "source_yaw_uncertainty_rad": MEASURED_TURN_BOUND * own_age,
                    "heading_half_angle_rad": half_angle,
                    "maximum_projection_m": projection, "nonclosing_margin_m": margin})
        result["near_peer_checks"].append(check)
    result.update(body_margin_m=min(body_margins), braking_zone_margin_m=min(zone_margins),
                  minimum_margin_m=min(body_margins + direction_margins))
    if min(body_margins) < 0:
        result["reason"] = "peer_uncertainty_envelope"
    elif direction_margins and min(direction_margins) < -1e-12:
        result["reason"] = "peer_braking_nonclosing"
    else:
        result.update(allow=True, reason="clear", output=[float(v), float(w)])
    if (result["reason"] == "peer_braking_nonclosing" and v == 0. and w != 0.
            and valid_settled_turn(own, now)):
        own_reserve = REST_DRIFT_BUDGET_M
        peer_reserve = (MEASURED_SPEED_BOUND * (REACTION_SEC + TURN_STOP_PADDING_SEC)
                        + MEASURED_SPEED_BOUND ** 2 / (2 * BRAKING_DECEL_MPS2))
        required_margin = own_reserve + peer_reserve
        if min(body_margins) >= required_margin:
            result.update(allow=True, reason="settled_turn_drift_reserve", output=[0., float(w)],
                          minimum_margin_m=min(body_margins) - required_margin,
                          settled_turn_check={
                              "schema": "mr3-settled-turn-check-v1",
                              "certificate": own["settled_turn"],
                              "horizon_sec": STOP_HORIZON_SEC,
                              "own_drift_reserve_m": own_reserve,
                              "peer_braking_reserve_m": peer_reserve,
                              "required_body_margin_m": required_margin})
    if result["reason"] == "peer_braking_nonclosing" and v != 0. and w != 0.:
        # Preserve only Nav2's requested angular direction, after a separate
        # full check of the braking request. v=0 cannot enter this branch, so
        # this is a single additional check rather than recursive steering.
        rotation = guard_motion([0., w], own, peers, now, epoch)
        if rotation["allow"] and rotation["reason"] in ("clear", "settled_turn_drift_reserve"):
            filtered = dict(rotation)
            filtered.update(
                reason="linear_brake_preserve_requested_turn",
                command_normalization=result["command_normalization"],
                component_filter={
                    "schema": "mr3-linear-brake-requested-turn-v1",
                    "canonical_input": canonical,
                    "rejected_mixed_decision": result,
                    "rotation_check": rotation,
                })
            return filtered
    return result
