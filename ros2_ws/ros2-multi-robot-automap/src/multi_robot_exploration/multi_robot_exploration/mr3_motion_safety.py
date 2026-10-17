"""Received-state peer braking gate; it never chooses exploration or steering.

The near region reserves both robots' bounded reaction and stopping travel.
Inside it, every robot must contribute non-closing motion for every peer
position in the source-age uncertainty disk and every heading in its bounded
turn/braking interval. This is a shared guard contract, not a promise against
an unguarded peer, unbounded localization jumps or invalid actuator bounds.
Reaction/stopping reserve covers in-flight motion. A zero linear output is a
braking request; a delayed zero-twist source does not establish current rest.
"""

import math

from multi_robot_exploration.mr3_episode import elapsed_ns, timestamp_ns


ROBOTS = ("tb1", "tb2", "tb3")
BODY_RADIUS_M = .25  # Existing Waffle full-body disk; actual collision radius < .238 m.
COMMAND_SPEED_LIMIT = .26
MEASURED_SPEED_BOUND = .30
COMMAND_TURN_LIMIT = 1.
MEASURED_TURN_BOUND = 1.2
TURN_ACCEL_BOUND_RADPS2 = 7.0  # 2 * model wheel-rim 1 m/s² / .287 m wheel separation.
SOURCE_MAX_AGE_SEC = .5
REACTION_SEC = .16
BRAKING_DECEL_MPS2 = .5
GEOMETRY_MARGIN_M = .02
PERIOD_SEC = .02
COMMAND_TIMEOUT_SEC = .2


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
    """Return only the unchanged requested differential-drive Twist or zero.

    Source-age expansion is separate from .16 s reaction: .10 s request,
    .02 s gate, 1/30 s actuator and the remaining command delivery allowance.
    Both actual and requested translational directions must be non-closing in
    a near region. Pure rotation is safe for the fixed circumscribed body disk.
    """
    result = {"allow": False, "reason": "state_unavailable", "output": [0., 0.],
              "minimum_margin_m": None, "body_margin_m": None,
              "braking_zone_margin_m": None, "near_peer_checks": []}
    if (type(now) not in (int, float) or not math.isfinite(now)
            or not valid_state(own, now, epoch) or set(peers) != set(ROBOTS) - {own.get("name")}
            or any(not valid_state(peer, now, epoch) for peer in peers.values())):
        return result
    valid_request = (isinstance(request, (list, tuple)) and len(request) == 2
                     and all(type(value) in (int, float) and math.isfinite(value)
                             for value in request))
    if (not valid_request or abs(request[0]) > COMMAND_SPEED_LIMIT
            or abs(request[1]) > COMMAND_TURN_LIMIT):
        result["reason"] = "unsupported_command"
        return result
    v, w = request
    own_age = elapsed_ns(own["source_stamp"], now) / 1e9
    body_margins, zone_margins, direction_margins = [], [], []
    for name, peer in peers.items():
        dx, dy = peer["x"] - own["x"], peer["y"] - own["y"]
        distance = math.hypot(dx, dy)
        uncertainty = MEASURED_SPEED_BOUND * (
            own_age + elapsed_ns(peer["source_stamp"], now) / 1e9)
        body_margin = distance - 2 * BODY_RADIUS_M - uncertainty - GEOMETRY_MARGIN_M
        braking_reserve = (2 * MEASURED_SPEED_BOUND * REACTION_SEC
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
            horizon = REACTION_SEC + MEASURED_SPEED_BOUND / BRAKING_DECEL_MPS2
            possible_turn = min(MEASURED_TURN_BOUND,
                                abs(own["w"]) + TURN_ACCEL_BOUND_RADPS2 * own_age)
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
    return result
