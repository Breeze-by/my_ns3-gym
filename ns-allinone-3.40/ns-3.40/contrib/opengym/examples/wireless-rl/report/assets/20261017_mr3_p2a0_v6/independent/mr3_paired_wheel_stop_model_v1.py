"""Independent exact-rational finite wheel model; no body/native proof."""

from fractions import Fraction as F
import hashlib
import json
from pathlib import Path


def evaluate():
    speed, turn, half_base = F(".30"), F("1.2"), F(".1435")
    acceleration, dt, reaction, extra_phase = F(1), F(".034"), F(".16"), F(".034")
    max_rim = speed + half_base * turn
    # For desired zero, both wheels retain their ratio while the larger rim
    # magnitude loses a*dt each update. Body v and w therefore scale together.
    continuous_time = reaction + max_rim / acceleration
    continuous_path = reaction * speed + speed * max_rim / (2 * acceleration)
    # Hold old speed for each full update and add one extra frame on top of
    # reaction. Integral overestimate is at most v_max*dt (one whole interval).
    discrete_path_upper = continuous_path + speed * dt + speed * extra_phase
    discrete_time_upper = continuous_time + dt + extra_phase
    worst_path = worst_time = F(0)
    worst = None
    count = 0
    for v_index in range(-30, 31):
        for w_index in range(-24, 25):
            v, w = F(v_index, 100), F(w_index, 20)
            left, right = v - half_base * w, v + half_base * w
            path = elapsed = F(0)
            while left != 0 or right != 0:
                path += abs((left + right) / 2) * dt
                largest = max(abs(left), abs(right))
                alpha = min(F(1), acceleration * dt / largest)
                left *= 1 - alpha
                right *= 1 - alpha
                elapsed += dt
            total_path = speed * (reaction + extra_phase) + path
            total_time = reaction + extra_phase + elapsed
            if total_path > worst_path:
                worst_path = total_path
                worst = {"initial_v": float(v), "initial_w": float(w),
                         "path_with_extra_phase_m": float(total_path),
                         "time_with_extra_phase_sec": float(total_time)}
            worst_time = max(worst_time, total_time)
            count += 1
    return {
        "schema": "mr3-independent-paired-wheel-stop-model-v1",
        "passed": (discrete_path_upper < F(".144")
                   and discrete_time_upper < F(".78")
                   and worst_path <= discrete_path_upper and worst_time <= discrete_time_upper),
        "physical_evidence": False,
        "parameters": {"body_speed_bound_mps": float(speed),
                       "body_turn_bound_radps": float(turn), "wheel_separation_m": .287,
                       "rim_accel_mps2": float(acceleration), "update_dt_sec": float(dt),
                       "reaction_sec": float(reaction), "extra_phase_sec": float(extra_phase)},
        "bounds": {"maximum_initial_rim_mps": float(max_rim),
                   "continuous_stop_including_reaction_sec": float(continuous_time),
                   "continuous_path_including_reaction_m": float(continuous_path),
                   "conservative_discrete_time_sec": float(discrete_time_upper),
                   "conservative_discrete_path_m": float(discrete_path_upper),
                   "retained_task_time_envelope_sec": .78, "retained_path_envelope_m": .144},
        "finite_grid": {"initial_pairs": count, "maximum_path_m": float(worst_path),
                        "maximum_time_sec": float(worst_time), "worst_path_case": worst},
        "derivation": [
            "M=max(abs(left),abs(right)) <= abs(v)+(.287/2)*abs(w) <= .4722",
            "zero target: common alpha=min(1,a*dt/M), each rim and body v/w multiply by1-alpha",
            "continuous Tstop=M/a; integral abs(v)dt=abs(v0)*M/(2a)",
            "continuous with reaction: .16+.4722=.6322s and .048+.07083=.11883m",
            "holding old speed adds at most .30*.034; an additional full phase adds .0102m",
            "conservative finite-model .7002s/.13923m remain inside .78s/.144m"],
        "assumptions": [
            "ideal no-slip differential-drive mapping and instantaneous tracking of applied joint target",
            "source-current joint feedback is accurate; no stale accumulated instruction",
            "initial body abs(v)<=.30 and abs(w)<=1.2 at braking start; rim acceleration limit1",
            "sim-time wheel updates at most34ms; reaction within declared.16s; zero command retained",
            "numeric inward rounding may reduce alpha; negligible binary64 arithmetic must be audited separately"],
        "limitations": [
            "current joint target step bound is not a world body speed/acceleration guarantee",
            "torque, contact, slip and real tracking are omitted; native full-vector/stop audits remain mandatory",
            "global stop envelope is not a claim of instantaneous minimum body deceleration.5m/s2",
            "grid complements the closed-form upper bound and does not substitute native evidence"],
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }


if __name__ == "__main__":
    output = Path("/tmp/mr3_paired_wheel_stop_model_v1.json")
    if output.exists():
        raise SystemExit("output exists")
    result = evaluate()
    output.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "bounds": result["bounds"],
                      "grid": result["finite_grid"]}, indent=2))
