#!/usr/bin/env python3
"""Read preserved closed diagnostic rows and write a new /tmp analysis only."""
import argparse
import collections
import hashlib
import json
import math
from pathlib import Path

DEFAULT_EPISODE = Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_plant/mr3_p2a_v8_continuous/worker0/episode001_open_101')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def proof(path):
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def rows(path):
    with path.open('rb') as stream:
        for line, raw in enumerate(stream, 1):
            yield {'path': str(path), 'line_1based': line,
                   'raw_line_sha256_with_newline': sha(raw), 'raw': json.loads(raw)}


def sub(a, b):
    return [x - y for x, y in zip(a, b)]


def norm(a):
    return math.sqrt(sum(x * x for x in a))


def cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]]


def reference(row):
    x = row['raw']
    return {k: v for k, v in row.items() if k != 'raw'} | {
        k: x[k] for k in ('record_sequence', 'sim_time_ns', 'phase', 'actuation_seq') if k in x}


def body_longitudinal(velocity, quaternion_wxyz):
    w, x, y, z = quaternion_wxyz
    yaw = math.atan2(2 * (w * z + x * y), 1 - 2 * (y * y + z * z))
    return math.cos(yaw) * velocity[0] + math.sin(yaw) * velocity[1]


def metric_values(row):
    x = row['raw']
    model, canonical, base = x['model'], x['canonical'], x['base']
    out = {
        'model_planar_speed_mps': math.hypot(*model['world_linear_velocity_xyz'][:2]),
        'model_yaw_longitudinal_velocity_mps': body_longitudinal(
            model['world_linear_velocity_xyz'], model['world_pose']['quaternion_wxyz']),
        'model_angular_z_radps': model['world_angular_velocity_xyz'][2],
        'model_canonical_origin_velocity_difference_norm_mps': norm(sub(
            model['world_linear_velocity_xyz'], canonical['world_origin_linear_velocity_xyz'])),
        'model_canonical_origin_position_difference_norm_m': norm(sub(
            model['world_pose']['position_xyz'], canonical['world_pose']['position_xyz'])),
        'canonical_base_origin_velocity_difference_norm_mps': norm(sub(
            canonical['world_origin_linear_velocity_xyz'], base['world_origin_linear_velocity_xyz'])),
        'canonical_base_origin_position_difference_norm_m': norm(sub(
            canonical['world_pose']['position_xyz'], base['world_pose']['position_xyz'])),
    }
    for name, link in [('canonical', canonical), ('base', base)]:
        r = sub(link['world_cog_pose']['position_xyz'], link['world_pose']['position_xyz'])
        dv = sub(link['world_cog_linear_velocity_xyz'], link['world_origin_linear_velocity_xyz'])
        out[name + '_cog_point_velocity_identity_residual_norm_mps'] = norm(sub(
            dv, cross(link['world_angular_velocity_xyz'], r)))
        out[name + '_origin_planar_speed_mps'] = math.hypot(*link['world_origin_linear_velocity_xyz'][:2])
        out[name + '_cog_planar_speed_mps'] = math.hypot(*link['world_cog_linear_velocity_xyz'][:2])
        out[name + '_cog_origin_velocity_difference_norm_mps'] = norm(dv)
        out[name + '_cog_origin_position_difference_norm_m'] = norm(r)
    rim = [j['velocity_radps'] * .033 for j in x['joints_right_left']]
    target = [j['motor_velocity_target_radps'] * .033 for j in x['joints_right_left']]
    out['observer_measured_mean_rim_mps'] = sum(rim) / 2
    out['observer_motor_target_mean_rim_mps'] = sum(target) / 2
    out['observer_measured_wheel_kinematic_angular_radps'] = (rim[0] - rim[1]) / .287
    out['body_longitudinal_minus_measured_mean_rim_mps'] = out['model_yaw_longitudinal_velocity_mps'] - sum(rim) / 2
    return out


def summarize(samples, values):
    if not samples:
        return {'count': 0}
    result = {'count': len(samples), 'metrics': {}}
    for key in values[0]:
        lo = min(range(len(values)), key=lambda i: values[i][key])
        hi = max(range(len(values)), key=lambda i: values[i][key])
        ab = max(range(len(values)), key=lambda i: abs(values[i][key]))
        result['metrics'][key] = {
            'minimum': values[lo][key], 'minimum_reference': reference(samples[lo]),
            'maximum': values[hi][key], 'maximum_reference': reference(samples[hi]),
            'maximum_absolute': abs(values[ab][key]), 'maximum_absolute_reference': reference(samples[ab]),
            'mean': math.fsum(x[key] for x in values) / len(values),
            'rms': math.sqrt(math.fsum(x[key] * x[key] for x in values) / len(values)),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', type=Path, default=DEFAULT_EPISODE)
    parser.add_argument('--output', type=Path,
                        default=Path('/tmp/mr3_p2a_v8_continuous_physical_review_v1.json'))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    ep = args.episode
    metadata = json.loads((ep / 'metadata.json').read_bytes())
    summary = json.loads((ep / 'summary.json').read_bytes())
    probe = json.loads((ep.parent.parent / 'plant_probe_summary.json').read_bytes())
    assert metadata['plant_stimulus_arm'] == 'continuous'
    epoch = metadata['epoch']
    assert summary['epoch'] == epoch
    start = round(summary['closed']['start_sim_time_sec'] * 1e9)
    end = round(summary['closed']['stop_sim_time_sec'] * 1e9)
    wave = probe['waveform']
    turn_start = start + wave['turn_start_ns']
    turn_end = start + wave['turn_end_ns']
    phys = []
    configuration = None
    for row in rows(ep / 'physics_tb3.jsonl'):
        x = row['raw']
        if x['kind'] == 'configuration':
            configuration = row
        if x['kind'] == 'sample' and start < x['sim_time_ns'] <= end:
            assert x['epoch'] == epoch
            # Preserve all velocity/pose/joint fields. Contact records are deliberately
            # not reinterpreted here; independent closure/validity gates own that scope.
            row['raw'] = {k: v for k, v in x.items()
                          if k not in ('contacts', 'native_ode', 'solver_diagnostics_world_scope')}
            phys.append(row)
    assert configuration is not None
    assert len(phys) == 8000
    paired = collections.defaultdict(list)
    for row in phys:
        paired[row['raw']['pair_sequence']].append(row)
    assert len(paired) == 4000
    before, after = {}, {}
    for values in paired.values():
        assert len(values) == 2
        a, b = values
        assert a['raw']['phase'] == 'before_physics_after_collision'
        assert b['raw']['phase'] == 'world_update_end_after_physics_and_pose_propagation'
        assert a['raw']['sim_time_ns'] == b['raw']['sim_time_ns']
        before[a['raw']['sim_time_ns']] = a
        after[b['raw']['sim_time_ns']] = b
    assert sorted(before) == list(range(start + 1000000, end + 1, 1000000))
    values = [metric_values(x) for x in phys]
    groups = {
        'full_task_window_both_phases': [i for i in range(len(phys))],
        'before_physics_only': [i for i, x in enumerate(phys) if x['raw']['phase'] == 'before_physics_after_collision'],
        'after_physics_only': [i for i, x in enumerate(phys) if x['raw']['phase'] == 'world_update_end_after_physics_and_pose_propagation'],
        'request_turn_window_both_phases': [i for i, x in enumerate(phys) if turn_start < x['raw']['sim_time_ns'] <= turn_end],
        'stationary_prefix_both_phases': [i for i, x in enumerate(phys) if x['raw']['sim_time_ns'] <= turn_start],
        'zero_suffix_both_phases': [i for i, x in enumerate(phys) if x['raw']['sim_time_ns'] > turn_end],
    }
    stats = {name: summarize([phys[i] for i in indices], [values[i] for i in indices])
             for name, indices in groups.items()}
    drive_rows = list(rows(ep / 'drive_tb3.jsonl'))
    drive_configuration = drive_rows[0]
    assert drive_configuration['raw']['kind'] == 'configuration'
    assert drive_configuration['raw']['wheel_order'] == ['right', 'left']
    assert drive_configuration['raw']['wheel_diameter_m'] == [.066]
    assert drive_configuration['raw']['wheel_separation_m'] == [.287]
    all_acts = [x for x in drive_rows if x['raw']['kind'] == 'actuation']
    acts = [x for x in all_acts if start < x['raw']['sim_time_ns'] <= end]
    act_values = []
    joined = []
    for row in acts:
        x = row['raw']
        cur, desired, applied = x['current_rim_mps'], x['desired_rim_mps'], x['applied_rim_mps']
        cm, dm, am = sum(cur) / 2, sum(desired) / 2, sum(applied) / 2
        av = {
            'current_mean_rim_mps': cm, 'issued_mean_rim_mps': am,
            'current_abs_right_minus_abs_left_rim_mps': abs(cur[0]) - abs(cur[1]),
            'issued_abs_right_minus_abs_left_rim_mps': abs(applied[0]) - abs(applied[1]),
            'wheel_derived_current_angular_radps': (cur[0] - cur[1]) / .287,
            'wheel_derived_issued_angular_radps': (applied[0] - applied[1]) / .287,
            'alpha': x['alpha'],
            'common_fraction_mean_identity_error_mps': am - ((1 - x['alpha']) * cm + x['alpha'] * dm),
        }
        act_values.append(av)
        obs = before[x['sim_time_ns']]
        y = obs['raw']
        rim = [j['velocity_radps'] * .033 for j in y['joints_right_left']]
        target = [j['motor_velocity_target_radps'] * .033 for j in y['joints_right_left']]
        joined.append({
            'driver_reference': reference(row), 'observer_before_reference': reference(obs),
            'observer_after_reference': reference(after[x['sim_time_ns']]),
            'driver_current_rim_mps': cur, 'observer_measured_rim_mps': rim,
            'driver_applied_rim_mps': applied, 'observer_motor_target_rim_mps': target,
            'max_abs_feedback_difference_mps': max(abs(cur[i] - rim[i]) for i in (0, 1)),
            'max_abs_target_readback_difference_mps': max(abs(applied[i] - target[i]) for i in (0, 1)),
            'observer_model_before_world_linear_velocity_xyz': y['model']['world_linear_velocity_xyz'],
            'observer_model_after_world_linear_velocity_xyz': after[x['sim_time_ns']]['raw']['model']['world_linear_velocity_xyz'],
        })
    # Whole-window time integral of the held target mean is a command/kinematic
    # accounting quantity only, not a contribution decomposition of actual body travel.
    held_rows = [x for x in all_acts if x['raw']['sim_time_ns'] <= end]
    signed_integral = absolute_integral = 0.0
    for i, row in enumerate(held_rows):
        t0 = max(start, row['raw']['sim_time_ns'])
        t1 = min(end, held_rows[i + 1]['raw']['sim_time_ns'] if i + 1 < len(held_rows) else end)
        if t1 > t0:
            mean = sum(row['raw']['applied_rim_mps']) / 2
            signed_integral += mean * (t1 - t0) / 1e9
            absolute_integral += abs(mean) * (t1 - t0) / 1e9
    selected_indices = set()
    for key in values[0]:
        selected_indices.add(max(range(len(values)), key=lambda i: abs(values[i][key])))
    selected_physics = [phys[i] for i in sorted(selected_indices)]
    transitions = []
    old_w = None
    for i, row in enumerate(acts):
        if row['raw']['desired_w'] != old_w:
            transitions.append({'new_desired_w': row['raw']['desired_w'],
                                'first_update_and_next_three': acts[i:i+4]})
            old_w = row['raw']['desired_w']
    turn_acts = [x for x in acts if x['raw']['desired_w'] == .8]
    zero_acts = [i for i, x in enumerate(acts) if x['raw']['desired_w'] == 0]
    turn_indices = [i for i, x in enumerate(acts) if x['raw']['desired_w'] == .8]
    after_rows = [after[t] for t in sorted(after)]
    chord = math.fsum(math.hypot(*sub(after_rows[i]['raw']['model']['world_pose']['position_xyz'],
                                    after_rows[i-1]['raw']['model']['world_pose']['position_xyz'])[:2])
                      for i in range(1, len(after_rows)))
    speed_sum = math.fsum(math.hypot(*row['raw']['model']['world_linear_velocity_xyz'][:2]) * .001
                          for row in after_rows)
    data = {
        'schema': 'mr3-p2a-v8-continuous-passive-physical-readonly-review-v1',
        'scope': 'Read-only independent descriptive extraction of the closed continuous arm, not a rerun of formal validity/closure audits and not a scientific causal or P2A acceptance claim.',
        'episode_directory': str(ep), 'epoch': epoch, 'freeze': metadata['freeze'],
        'arm': 'continuous',
        'task_window': {'start_exclusive_ns': start, 'end_inclusive_ns': end,
            'task_span_sec': (end-start)/1e9, 'pairs': len(paired), 'samples_both_phases': len(phys),
            'exact_1ms_pair_clock_coverage': True, 'request_turn_start_ns': turn_start,
            'request_turn_end_ns': turn_end, 'requested_turn_duration_sec': (turn_end-turn_start)/1e9,
            'first_turn_wheel_update_ns': turn_acts[0]['raw']['sim_time_ns'],
            'last_turn_wheel_update_ns': turn_acts[-1]['raw']['sim_time_ns'],
            'first_zero_wheel_update_after_turn_ns': transitions[-1]['first_update_and_next_three'][0]['raw']['sim_time_ns']},
        'observer_configuration': configuration,
        'driver_configuration': drive_configuration,
        'observation_statistics': stats,
        'observed_model_planar_samples_gt_unchanged_01_bound': sum(
            x['model_planar_speed_mps'] > .01 for x in values),
        'driver_actuation_statistics': {
            'whole_window': summarize(acts, act_values),
            'turn_desired_updates': summarize([acts[i] for i in turn_indices], [act_values[i] for i in turn_indices]),
            'zero_desired_updates': summarize([acts[i] for i in zero_acts], [act_values[i] for i in zero_acts]),
            'desired_w_counts': {str(k): v for k,v in collections.Counter(x['raw']['desired_w'] for x in acts).items()},
            'whole_window_held_issued_mean_integral_m_kinematic_only': signed_integral,
            'whole_window_held_abs_issued_mean_integral_m_kinematic_only': absolute_integral,
            'maximum_joined_feedback_difference_mps': max(x['max_abs_feedback_difference_mps'] for x in joined),
            'maximum_joined_motor_target_readback_difference_mps': max(x['max_abs_target_readback_difference_mps'] for x in joined),
        },
        'descriptive_path_quantities': {
            'after_phase_sampled_planar_chord_sum_m': chord,
            'after_phase_1ms_rectangle_speed_sum_m': speed_sum,
            'scope': 'Sampled descriptions only. Chord sum omits the unknown exact boundary-start chord and neither value certifies continuous path or cause.'},
        'driver_waveform_transition_raw_rows': transitions,
        'driver_observer_same_clock_join_rows': joined,
        'all_selected_driver_actuation_raw_rows': acts,
        'selected_extreme_observer_raw_fields': selected_physics,
        'selected_extreme_observer_field_omissions': ['contacts', 'native_ode', 'solver_diagnostics_world_scope'],
        'interpretation': [
            'The native observer identifies canonical=tb3::base_footprint. Model/canonical velocity and origin pose are identical throughout this window; canonical CoG and origin also coincide.',
            'The base_link CoG can move much faster in the plane than its origin while their measured full3D rigid-point velocity identity residual is near floating precision. This verifies the expected CoG/origin distinction in this arm; it does not reclassify V7.',
            'Nonzero measured rim asymmetry and nonzero issued mean rim components occur despite requested v=0, particularly during acceleration and final braking. Their signed value and scale are descriptive; neither is an additive causal decomposition of actual body speed.',
            'At model-planar-speed peak the actual motor target mean, measured rim mean, yaw-longitudinal model velocity and full world vectors are preserved in the referenced observer raw fields, so target symmetry can be checked without assuming no slip.',
            'This arm has4seconds total observation but only1.54seconds requested turn, with a stationary prefix and final zero suffix. It uses the sparse far-peer from-rest fixture; V7 first failure came after about3.075seconds active settled turn in a different near-peer navigation history.',
            'This arm alone does not isolate pulse effects. If the paired pulse arm also remains below.01, the original V7model counterexample is still not reproduced; no driver or model repair is demonstrated.',
            'Axis GetForce and retained contact records are not treated as independent solver reaction or absence-of-contact proof. Native gates,18contact streams,3robots and original.01/.0078/.50/95percent/300s requirements remain authoritative.',
        ],
        'comparison_to_preserved_v7_only': {
            'original_freeze': '8d7f19fc8225eae0ccdc6609b828ee8e832f7c93',
            'original_zero_update_reference': 'drive_tb3.jsonl:6514,actuation1481,source54.121',
            'original_zero_current_mean_rim_mps': .008821410036194507,
            'original_zero_issued_mean_rim_mps': .006761302059522432,
            'original_first_failure_body_planar_mps': .02020358683181293,
            'scope': 'Historical values are comparison anchors, not a matched same-freeze/geometry/state counterfactual. No historical FAIL or optimizer history is changed.'},
        'input_proof': [proof(ep/name) for name in (
            'metadata.json','summary.json','plant_fixture_binding.json','physics_diagnostic_binding.json',
            'physics_tb3.jsonl','drive_tb3.jsonl','plant_stimulus_worker.jsonl','drive_model_tb3.sdf')] +
            [proof(ep.parent.parent / 'plant_probe_summary.json')],
        'extractor_proof': proof(Path(__file__).resolve()),
    }
    with args.output.open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': proof(args.output),
        'max_model_planar_mps': stats['full_task_window_both_phases']['metrics']['model_planar_speed_mps']['maximum'],
        'max_driver_abs_issued_mean_mps': data['driver_actuation_statistics']['whole_window']['metrics']['issued_mean_rim_mps']['maximum_absolute'],
        'max_base_cog_identity_residual_mps': stats['full_task_window_both_phases']['metrics']['base_cog_point_velocity_identity_residual_norm_mps']['maximum']}))


if __name__ == '__main__':
    main()
