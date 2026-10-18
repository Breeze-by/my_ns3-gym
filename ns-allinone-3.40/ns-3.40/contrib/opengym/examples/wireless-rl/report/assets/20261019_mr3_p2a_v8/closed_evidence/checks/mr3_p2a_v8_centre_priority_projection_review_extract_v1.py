#!/usr/bin/env python3
"""Exact rational algebra/grid review only; no native or production mutation."""
import argparse
from fractions import Fraction as F
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
EP = ROS / 'log/mr3_ppo/mr3_p2a_v7_minimal/native/round0000/worker0/episode001_open_101'


def digest(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def number(value):
    return {'exact_rational': str(value), 'float_display': float(value)}


def clamp(value, lower, upper):
    return min(max(value, lower), upper)


def project(v, w, requested_v, requested_w, a, dt, b):
    """Exact real/rational formula; not a binary64 implementation candidate."""
    assert a > 0 and dt >= 0 and b > 0
    h = a * dt
    dv = clamp(requested_v - v, -h, h)
    remaining = h - abs(dv)
    dw = clamp(requested_w - w, -2 * remaining / b, 2 * remaining / b)
    return v + dv, w + dw


def selected_row(path, line):
    raw = path.read_bytes().splitlines(keepends=True)[line - 1]
    return {'path': str(path), 'line_1based': line,
            'raw_line_sha256_with_newline': hashlib.sha256(raw).hexdigest(),
            'raw': json.loads(raw)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=Path('/tmp/mr3_p2a_v8_centre_priority_projection_review_v1.json'))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    # Grid matches the original IdealNoSlipZeroTargetFitsRetainedGlobalStopEnvelope
    # input ranges, with exact declared-decimal rather than rounded binary64 arithmetic.
    a, dt, b = F(1), F(34, 1000), F(287, 1000)
    vmax, wmax, reaction = F(30, 100), F(12, 10), F(16, 100)
    path_limit, horizon = F(144, 1000), F(78, 100)
    h = a * dt
    max_path = max_elapsed = F(0)
    max_frames = 0
    checked_updates = 0
    cases = []
    for linear in range(-30, 31):
        for angular in range(-24, 25):
            v, w = F(linear, 100), F(angular, 20)
            initial = [v, w]
            path, elapsed = vmax * (reaction + dt), reaction + dt
            frames = 0
            while v != 0 or w != 0:
                assert frames < 64
                path += abs(v) * dt
                right, left = v + b * w / 2, v - b * w / 2
                nv, nw = project(v, w, F(0), F(0), a, dt, b)
                nr, nl = nv + b * nw / 2, nv - b * nw / 2
                assert abs(nr - right) <= h and abs(nl - left) <= h
                assert abs(nw - w) <= 2 * h / b
                assert abs(nv) <= abs(v) and abs(nw) <= abs(w)
                assert v * nv >= 0 and w * nw >= 0
                assert max(abs(nr), abs(nl)) == max(max(abs(right), abs(left)) - h, F(0))
                v, w = nv, nw
                frames += 1
                checked_updates += 1
                elapsed += dt
            assert path <= path_limit and elapsed <= horizon
            max_path, max_elapsed, max_frames = max(max_path, path), max(max_elapsed, elapsed), max(max_frames, frames)
            cases.append({'initial_v': str(initial[0]), 'initial_w': str(initial[1]),
                          'frames': frames, 'path_m': str(path), 'elapsed_sec': str(elapsed)})
    sweep_sha = hashlib.sha256(json.dumps(cases, sort_keys=True, separators=(',', ':')).encode()).hexdigest()

    drive = EP / 'drive_tb3.jsonl'
    motion = EP / 'motion_safety.jsonl'
    zero = selected_row(drive, 6514)
    raw = zero['raw']
    r, l = map(F.from_float, raw['current_rim_mps'])
    old_r, old_l = map(F.from_float, raw['applied_rim_mps'])
    native_dt = F.from_float(raw['dt_sec'])
    native_b = F.from_float(.287)
    v, w = (r + l) / 2, (r - l) / native_b
    exact_v, exact_w = project(v, w, F(0), F(0), F(1), native_dt, native_b)
    exact_r, exact_l = exact_v + native_b * exact_w / 2, exact_v - native_b * exact_w / 2
    # This particular represented binary64 symmetric point is strictly feasible;
    # it is not a general proof that naive rounding of the formula is safe.
    candidate_r = F.from_float(.11158845683182124)
    candidate_l = -candidate_r
    assert abs(candidate_r - r) <= native_dt and abs(candidate_l - l) <= native_dt
    c_v, c_w = (candidate_r + candidate_l) / 2, (candidate_r - candidate_l) / native_b

    report = {
        'schema': 'mr3-p2a-v8-centre-priority-wheel-projection-algebra-review-v1',
        'scope': 'Read-only source/raw extraction and exact rational CPU enumeration. No native run, runtime edit, library rebuild, driver implementation, optimizer or plant-fix credit.',
        'native_evidence_freeze': '8d7f19fc8225eae0ccdc6609b828ee8e832f7c93',
        'epoch': 'round0000_w0_e1_71c66e9e',
        'coordinate_convention': {'rims': ['right', 'left'],
            'v': '(R+L)/2', 'w': '(R-L)/b', 'b_m': number(b)},
        'candidate_definition_exact_arithmetic': {
            'feasible_set': '|R_next-R_current|<=h and |L_next-L_current|<=h; h=a*dt',
            'equivalent_body_twist_set': '|delta_v| + (b/2)*|delta_w| <= h',
            'objective': 'Lexicographically minimize absolute requested centre-v error, then absolute requested angular-w error; squared errors give the same scalar projections.',
            'formula': ['delta_v=clip(requested_v-current_v,-h,+h)',
                        'remaining_H=h-abs(delta_v)',
                        'delta_w=clip(requested_w-current_w,-2*remaining_H/b,+2*remaining_H/b)',
                        'v_next=current_v+delta_v; w_next=current_w+delta_w',
                        'R_next=v_next+b*w_next/2; L_next=v_next-b*w_next/2'],
            'domain': 'Finite quantities, a>0, dt>=0, b>0. Existing a==0 disabled-limiter semantics and invalid-input handling would need explicit retention if implementation is authorized.',
        },
        'proofs_and_inherited_assumptions': [
            {'claim': 'Individual wheel slew bound retained in the same measured-current-to-issued-target sense as the original helper.',
             'proof': 'max(abs(delta_R),abs(delta_L))=abs(delta_v)+(b/2)*abs(delta_w)<=h.',
             'limitation': 'This is not a bound on actual joint acceleration, consecutive issued-target increments, real body acceleration or tracking error when measured feedback differs from the preceding target.'},
            {'claim': 'Wheel-derived angular change per dt is <=2a/b =6.968641114982578...rad/s^2, below the retained7 bound.',
             'exact_bound': number(2*a/b),
             'limitation': 'Applying this bound to actual body angular velocity requires the same ideal no-slip/actuation tracking assumptions as the original wheel-derived contract and independent native checks.'},
            {'claim': 'Both v_next and w_next are between current and requested values; a feasible requested_v is attained exactly.',
             'proof': 'Each coordinate uses a scalar clamp toward its requested value. For fixed delta_v the residual diamond budget gives the full feasible angular interval.'},
            {'claim': 'For zero v/w targets, absolute centre v decreases by min(h,abs(v)); wheel infinity norm decreases by min(h,max(abs(R),abs(L))).',
             'proof': 'max(abs(R),abs(L))=abs(v)+(b/2)*abs(w). Translation takes min(h,abs(v)) first; angular reduction uses any remaining budget. Their weighted sum therefore drops by h until zero.'},
            {'claim': 'The retained .50m/s^2 braking reserve is conservative in the ideal self-feedback zero-target command/joint model.',
             'proof': 'Projected abs(v) decays by a*dt with a=1 until zero. Under abs(v)<=.30, abs(w)<=1.2, b=.287, dt=.034, initial maximum rim norm<=.4722m/s, hence at most14 updates. Including original .16s plus one34ms-frame reaction yields .67s<.78s. Left-held-speed centre path is maximal at abs(v)=.30 and is .108384m<.144m; a more conservative integral bound is .30*(.16+.034)+.30^2/(2*1)+.30*.034=.1134m<.144m.',
             'limitation': 'These are conditional ideal-model calculations only; they do not establish the actual body .50 braking, .01 rest or .0078 drift invariants.'},
        ],
        'exact_rational_grid_check': {
            'cases': len(cases), 'checked_updates': checked_updates,
            'linear_grid': 'linear=-30..30, initial_v=linear/100m/s',
            'angular_grid': 'angular=-24..24, initial_w=angular/20rad/s',
            'parameters': {k: number(x) for k,x in [('wheel_a_mps2',a),('dt_sec',dt),('separation_m',b),('reaction_sec',reaction),('path_limit_m',path_limit),('horizon_sec',horizon)]},
            'all_exact_wheel_step_bounds_pass': True,
            'all_exact_turn_step_bounds_pass': True,
            'all_zero_target_coordinate_monotonicity_pass': True,
            'all_max_rim_norm_reduction_identities_pass': True,
            'all_path_and_horizon_limits_pass': True,
            'maximum_frames': max_frames, 'maximum_path_m': number(max_path),
            'maximum_elapsed_sec': number(max_elapsed),
            'canonical_all_case_results_sha256': sweep_sha,
            'interpretation': 'Rational arithmetic on declared decimal parameters reproduces the original ideal proof grid scope; it does not execute a binary64 candidate or simulate Gazebo physics.'},
        'v7_exact_binary64_input_example': {
            'original_zero_update': zero,
            'followup_resume_update': selected_row(drive,6517),
            'prior_source_odom': selected_row(motion,70900),
            'first_failure_source_odom': selected_row(motion,70968),
            'first_model_failure': selected_row(motion,70969),
            'original_issued_mean_rim_mps': number((old_r+old_l)/2),
            'real_formula_exact_output': {'right': number(exact_r),'left': number(exact_l),'v':number(exact_v),'w':number(exact_w)},
            'one_verified_representable_symmetric_point': {
                'right': number(candidate_r),'left': number(candidate_l),'mean_v':number(c_v),'wheel_kinematic_w':number(c_w),
                'right_delta':number(candidate_r-r),'left_delta':number(candidate_l-l),
                'each_abs_delta_le_exact_binary64_input_budget': True,
                'exact_binary64_input_budget':number(native_dt),
                'wheel_kinematic_angular_change_rate':number((c_w-w)/native_dt)},
            'causal_limit': 'The zero was genuinely consumed at54.121. The first violating body odom sample54.155 precedes that same update\'s resumed wheel write. This example distinguishes original and candidate issued targets but does not prove that either target causes or eliminates the native violation.'},
        'tradeoffs_and_necessary_future_checks': [
            'The original algorithm keeps the whole body-twist command on one common-fraction segment from measured current to requested; the candidate sacrifices that segment/curvature property to prioritize centre translation.',
            'A coordinate-wise body-twist monotone projection can move an individual wheel past its own target. Example R=.2,L=0,zero target,a=1,dt=.034: candidate R=.166,L=-.034; its wheel bounds hold and mean v decays faster, but the left wheel reverses relative to its own zero target. Original R=.166,L=0 does not reverse that wheel.',
            'At V7zero the symmetric feasible point leaves more wheel-derived yaw than original (.7776199082 versus .7305028207rad/s), while cancelling issued mean rim speed. This can change rotational duration, contact forces and slip; a real body benefit is unproven.',
            'Naive binary64 evaluation of the real formula is not automatically safe. Directed inward feasible bounds/output rounding and exact Fraction tests against the existing tiny-current/native-boundary regressions are necessary before any implementation; the one represented V7point is not a general floating-point proof.',
            'Normal target transitions, reversal, disabled-limit semantics, dt0, nonfinite/overflow, arbitrary finite feedback, actual wheel/status causality and unchanged three-robot18contact/body gates need independent verification if a production change is later authorized.',
            'The .01/.0078/.50/95percent/300s contracts and sensing/guard causal requirements remain unchanged. Wait for valid continuous/pulse observer results before deciding whether the driver candidate is warranted.',
        ],
        'input_provenance': [digest(EP/'metadata.json'),digest(drive),digest(motion),
            digest(ROS/'src/multi_robot/include/multi_robot/paired_wheel_slew.hpp'),
            digest(ROS/'src/multi_robot/test/test_paired_wheel_slew.cpp'),
            digest(ROS/'src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py')],
        'extractor':digest(Path(__file__).resolve()),
        'reproduce':'PYTHONNOUSERSITE=1 /usr/bin/python3 '+str(Path(__file__).resolve())+' --output NEW.json',
    }
    with args.output.open('x') as stream:
        json.dump(report,stream,indent=2,allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output':digest(args.output),'cases':len(cases),'checked_updates':checked_updates,
                      'max_path_m':float(max_path),'max_elapsed_sec':float(max_elapsed),'max_frames':max_frames}))


if __name__ == '__main__':
    main()
