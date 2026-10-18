#!/usr/bin/env python3
"""Read-only extraction of preserved V7 rows; writes only a new /tmp report.

No ROS/native process is launched. Use a distinct --output on a repeat run.
"""
import argparse
import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
REL = Path('ros2_ws/ros2-multi-robot-automap')
EP = ROOT / REL / 'log/mr3_ppo/mr3_p2a_v7_minimal/native/round0000/worker0/episode001_open_101'
FREEZE = '8d7f19fc8225eae0ccdc6609b828ee8e832f7c93'
EPOCH = 'round0000_w0_e1_71c66e9e'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load_rows(path):
    data = path.read_bytes()
    return data, [
        {'line_1based': i, 'raw_line_sha256_with_newline': sha(line),
         'raw': json.loads(line)}
        for i, line in enumerate(data.splitlines(keepends=True), 1)
    ]


def source(rel, ranges):
    spec = FREEZE + ':' + rel
    frozen = subprocess.check_output(['git', 'show', spec], cwd=ROOT)
    current = (ROOT / rel).read_bytes()
    lines = frozen.decode().splitlines()
    return {
        'path': str(ROOT / rel), 'freeze_git_spec': spec,
        'freeze_git_object': subprocess.check_output(
            ['git', 'rev-parse', spec], cwd=ROOT, text=True).strip(),
        'freeze_sha256': sha(frozen), 'worktree_sha256': sha(current),
        'worktree_equals_freeze': current == frozen,
        'excerpts': [
            {'first_line_1based': a, 'last_line_1based': b,
             'lines': [{'line_1based': n, 'text': lines[n - 1]}
                       for n in range(a, b + 1)]}
            for a, b in ranges
        ],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path,
                        default=Path('/tmp/mr3_p2a_v8_v7_brake_order_review_v1.json'))
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    inputs = {}
    rows = {}
    for name in ('metadata.json', 'drive_tb3.jsonl', 'motion_safety.jsonl'):
        p = EP / name
        data = p.read_bytes()
        inputs[name] = {'path': str(p), 'size_bytes': len(data), 'sha256': sha(data)}
        if name.endswith('.jsonl'):
            _, rows[name] = load_rows(p)
    metadata = json.loads((EP / 'metadata.json').read_bytes())
    assert metadata['freeze'] == FREEZE and metadata['epoch'] == EPOCH
    drive = rows['drive_tb3.jsonl']
    config = drive[0]
    assert config['raw']['kind'] == 'configuration'
    assert config['raw']['wheel_order'] == ['right', 'left']
    assert config['raw']['odometry_source'] == 1
    selected_drive = [r for r in drive if 54000000000 <= r['raw'].get('sim_time_ns', -1) <= 54200000000]
    actuation = []
    for r in selected_drive:
        v = r['raw']
        if v['kind'] != 'actuation':
            continue
        c, d, a = v['current_rim_mps'], v['desired_rim_mps'], v['applied_rim_mps']
        actuation.append({
            'line_1based': r['line_1based'], 'record_sequence': v['record_sequence'],
            'actuation_sequence': v['actuation_seq'], 'sim_time_ns': v['sim_time_ns'],
            'cmd_seq': v['cmd_seq'], 'target_clock_ns': v['target_clock_ns'],
            'target_decision_sequence': v['target_decision_sequence'],
            'current_common_rim_mps': (c[0] + c[1]) / 2,
            'current_right_minus_left_rim_mps': c[0] - c[1],
            'desired_common_rim_mps': (d[0] + d[1]) / 2,
            'desired_right_minus_left_rim_mps': d[0] - d[1],
            'applied_common_rim_mps': (a[0] + a[1]) / 2,
            'applied_right_minus_left_rim_mps': a[0] - a[1],
            'current_to_desired_delta_mps': [d[i] - c[i] for i in (0, 1)],
            'current_to_applied_delta_mps': [a[i] - c[i] for i in (0, 1)],
            'nominal_max_absolute_delta_mps': v['max_acceleration_mps2'] * v['dt_sec'],
            'interpretation': 'Rim-pair algebra only; no no-slip body-velocity inference.',
        })
    selected_motion = []
    odometry = []
    for r in rows['motion_safety.jsonl']:
        v = r['raw']
        p = v.get('payload', {})
        if p.get('robot') != 'tb3':
            continue
        keep = v['record_sequence'] in (70882, 70942, 70969)
        if v['kind'] == 'own_odom':
            m = p['message']
            stamp = m['header']['stamp']
            ns = stamp['sec'] * 10**9 + stamp['nanosec']
            keep = 54000000000 <= ns <= 54200000000
            if keep:
                t = m['twist']['twist']
                odometry.append({
                    'line_1based': r['line_1based'], 'record_sequence': v['record_sequence'],
                    'input_sequence': p['input_sequence'], 'source_clock_ns': ns,
                    'guard_log_sim_time_sec': v['sim_time_sec'],
                    'wall_monotonic_ns': v['wall_monotonic_ns'],
                    'linear_body_x_mps': t['linear']['x'],
                    'linear_body_y_mps': t['linear']['y'],
                    'planar_speed_mps': math.hypot(t['linear']['x'], t['linear']['y']),
                    'angular_z_radps': t['angular']['z'],
                    'position': m['pose']['pose']['position'],
                    'orientation': m['pose']['pose']['orientation'],
                })
        if keep:
            selected_motion.append(r)
    sources = [
        source(str(REL / 'src/multi_robot/src/mr3_gazebo_diff_drive.cpp'),
               [(105, 125), (580, 675), (678, 691), (812, 826)]),
        source(str(REL / 'src/multi_robot/include/multi_robot/paired_wheel_slew.hpp'),
               [(13, 95)]),
    ]
    assert sources[0]['freeze_sha256'] == config['raw']['compiled_source_sha256']
    assert sources[1]['freeze_sha256'] == config['raw']['compiled_helper_sha256']
    by_act = {r['raw'].get('actuation_seq'): r for r in selected_drive if r['raw']['kind'] == 'actuation'}
    assert by_act[1481]['raw']['cmd_seq'] == 2516
    assert by_act[1481]['raw']['desired_w'] == 0.0
    assert by_act[1482]['raw']['cmd_seq'] == 2517
    assert by_act[1482]['raw']['desired_w'] == 0.8
    assert [x['input_sequence'] for x in odometry] == list(range(1478, 1484))
    report = {
        'schema': 'mr3-p2a-v8-v7-brake-order-readonly-review-v1',
        'scope': 'Preserved original V7 episode only; no new native run, optimizer, pilot charge, or full audit.',
        'freeze': FREEZE, 'epoch': EPOCH, 'robot': 'tb3', 'episode_dir': str(EP),
        'selection': {'drive_sim_clock_ns_inclusive': [54000000000, 54200000000],
                      'own_odom_source_clock_ns_inclusive': [54000000000, 54200000000],
                      'additional_motion_record_sequences': [70882, 70942, 70969]},
        'inputs': inputs, 'driver_configuration_raw': config,
        'source_provenance_and_exact_freeze_excerpts': sources,
        'original_selected_drive_rows': selected_drive,
        'original_selected_motion_rows': selected_motion,
        'derived_rim_pair_table': actuation, 'derived_odom_table': odometry,
        'proven_conclusions': [
            {
                'id': 'zero_consumed_at_wheel_update',
                'claim': 'The 54.12 zero was not merely stored between wheel updates. The driver wheel-update path consumed cmd2516 at 54.121 and issued paired zero-directed slew targets.',
                'references': ['drive_tb3.jsonl:6512 (command_received)',
                               'drive_tb3.jsonl:6514 (actuation_seq1481, cmd2516, decision2704, target54.12)'],
                'numerical_evidence': {'current_rim_mps': [0.14558845683182123, -0.1279456367594322],
                    'desired_rim_mps': [0.0, 0.0], 'alpha': 0.23353499817142526,
                    'issued_applied_rim_mps': [0.11158845683182124, -0.09806585271277637]},
            },
            {
                'id': 'odom_precedes_same_update_wheel_write',
                'claim': 'OnUpdate samples world odometry, publishes the odom message, then selects the command, reads joint-rim feedback and calls wheel SetParam. Thus the first violating odom stamped54.155 precedes that same update\'s resumed pure-turn target write.',
                'references': ['mr3_gazebo_diff_drive.cpp:599-608,631-642,659-672',
                               'motion_safety.jsonl:70968 (source54.155, input1482)',
                               'drive_tb3.jsonl:6515 (resume stored54.14, cmd2517)',
                               'drive_tb3.jsonl:6517 (resume wheel update54.155, actuation1482)'],
                'implication': 'The first54.155 speed breach cannot have been produced by the new wheel write issued later in that same update. This does not isolate the cause among earlier actuation/history or braking-phase plant response.',
            },
            {
                'id': 'measured_feedback_zero_slew_has_nonzero_common_component',
                'claim': 'The stateless common-fraction limiter starts from unequal measured joint-rim feedback. When desired rims are both zero, one shared alpha shrinks both measured values; it does not impose equal wheel magnitudes or zero mean rim speed during deceleration.',
                'references': ['paired_wheel_slew.hpp:19-22,40-62',
                               'mr3_gazebo_diff_drive.cpp:636-662', 'drive_tb3.jsonl:6514'],
                'numerical_evidence': {'max_acceleration_mps2': 1.0, 'dt_sec': 0.034,
                    'right_delta_mps': -0.03399999999999999,
                    'left_delta_mps': 0.02987978404665584,
                    'issued_common_rim_mps': 0.006761302059522432,
                    'issued_right_minus_left_rim_mps': 0.20965430954459763},
                'implication': 'The original zero consumed a real paired braking step with unequal issued rim magnitudes. This algebra alone does not prove body drift, slip, actuator dynamics or solver cause.',
            },
            {
                'id': 'real_world_velocity_contract_counterexample',
                'claim': 'The source54.155 body velocity is read from the native model WorldLinearVel and yaw-rotated into base_footprint. The recorded planar norm0.02020358683181293 exceeds the unchanged0.01 settled-turn bound; it is not inferred from received-map/TF displacement.',
                'references': ['driver_configuration odometry_source1 = WORLD',
                               'mr3_gazebo_diff_drive.cpp:812-825',
                               'motion_safety.jsonl:70968', 'motion_safety.jsonl:70969'],
                'numerical_evidence': {'linear_x_mps': 0.019766829596618123,
                    'linear_y_mps': 0.004178201595048607,
                    'planar_speed_mps': 0.02020358683181293,
                    'angular_z_radps': 0.9257677498590783,
                    'settled_turn_speed_bound_mps': 0.01},
            },
            {
                'id': 'resume_slew_is_symmetric_but_not_prior_body_measurement',
                'claim': 'At54.155 the measured rim pair already has common component0.01379669701396559. The resumed requested v0,w0.8 fits the per-wheel slew budget (alpha1) and issues symmetric rims[0.1148,-0.1148]. Neither the symmetric new target nor its stored command retroactively changes the preceding body-velocity sample.',
                'references': ['drive_tb3.jsonl:6517', 'motion_safety.jsonl:70968'],
            },
        ],
        'limitations_and_unproven_claims': [
            'SetParam calls and the following actuation audit show the driver issued targets. Return values are not audited; this artifact does not independently prove successful physics-engine target acceptance, exact torque, tracking or no slip.',
            'The drive audit contains no per-record wall timestamp. Cross-file causal ordering here is established by exact source-time and verified driver source call order, not by comparing cross-file record_sequence values.',
            'A source-stamped odom message can be received while the guard log clock still shows an earlier paused boundary; this does not invert the driver\'s internal sample-before-write order.',
            'Observed rim feedback asymmetry predates the zero pulse; it is not evidence that the paired limiter violated its common-fraction formula or per-wheel1m/s^2 bound.',
            'Body planar velocity and averaged joint-rim velocity are distinct native measurements. Their difference does not, by itself, establish slip, contact impulse, caster, solver, controller, geometry or friction root cause.',
            'Temporal adjacency to a consumed braking step is not a controlled demonstration that braking causes the violation or that continuous pure turn would pass.',
            'No-contact records, if present elsewhere, cannot serve as proof that the settled-turn model or all safety gates pass.',
            'This original V7 model-failure evidence and its historical8optimizer updates remain unchanged. No repair, full-gate PASS, reliability or P2A completion is claimed.',
        ],
        'targeted_next_comparison': {
            'goal': 'Compare continuous requested v0,w0.8 with an actually guard-authorized and driver-consumed v0,w0.8 -> v0,w0 -> v0,w0.8 pulse, using the new explicit smoother-boundary diagnostic interface and independent validity evidence.',
            'strict_requirements': ['new freeze for new code/native claims', 'three robots and18contacts',
                'unchanged guard100ms/rest0.01/drift0.0078/deceleration0.50/95percent/300s contracts',
                'real20ms phase, actual smoother publication, actual guard request/decision and actual native storage plus wheel-actuation consumption',
                'a guard-rejected or unconsumed planned pulse is INCOMPLETE; planned waveform cannot replace actual trace'],
            'causal_claim_boundary': 'A controlled valid comparison may narrow effects of the input waveform; native evidence is required before any repair claim. Changing actual drive dynamics requires an independent gate.',
        },
        'extractor': {'path': str(Path(__file__).resolve()),
                      'sha256': sha(Path(__file__).read_bytes()),
                      'invocation': 'PYTHONNOUSERSITE=1 /usr/bin/python3 ' + str(Path(__file__).resolve()) + ' --output NEW.json'},
    }
    with args.output.open('x') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'size_bytes': args.output.stat().st_size,
                      'sha256': sha(args.output.read_bytes()),
                      'selected_drive_rows': len(selected_drive),
                      'selected_odom_rows': len(odometry),
                      'selected_motion_rows': len(selected_motion)}, sort_keys=True))


if __name__ == '__main__':
    main()
