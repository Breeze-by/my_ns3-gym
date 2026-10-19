#!/usr/bin/python3
"""Closed V18 evidence only; no runtime/reader imports or scientific credit.

This independently substitutes the recorded HOLD inputs into the frozen disk
equations.  It also inventories every motion/information record and measures
the source-header refreshes actually present in the information callback log.
It never runs the tracker, a simulator, a scientific consumer, or a ROS node.
"""
import argparse
from collections import Counter
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET


ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = Path('ros2_ws/ros2-multi-robot-automap')
EPISODE = ROS / 'log/mr3_p2a_reach_v18/mr3_p2a_reach_v18_interface/worker0/episode001_open_101'
FREEZE = 'ed2306e9fa100f6ada4ab6496a53a3bd08e58017'
SCHEMA = 'mr3-v18-initial-hold-source-cadence-forensics-v1'
ROBOTS = ('tb1', 'tb2', 'tb3')
REASON = 'initial HOLD has no complete pair certificate'
SOURCE_BASE = ROS / 'src/multi_robot_exploration/multi_robot_exploration'
SOURCES = {
    str(SOURCE_BASE / 'mr3_reach_geometry.py'): 'cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a',
    str(SOURCE_BASE / 'mr3_reach_runtime.py'): 'c17d008905364616c4027aeb1b6c180e7f4d0b522e310e242659a08cf376eb9e',
    str(SOURCE_BASE / 'mr3_information.py'): 'a426aa11faf082445e3cf69572fd56819376c89fcdf64a4a54e9848156517f63',
    str(SOURCE_BASE / 'motion_safety.py'): '60005f800760ee7adc58e32cc2e93cea40f30241bda195e79f7f048fe1b20549',
    str(SOURCE_BASE / 'mr3_episode.py'): '9145d2ad23789b252e32f0afdfe18cf2eeec8e2c7e9ca7e89127a532288e411b',
    str(ROS / 'src/slam_toolbox/src/slam_toolbox_multirobot.cpp'): 'f90148d03c6dbfa38a959d9950d1a9a1edc1499fdf7d8bf67cbac6659f8beb43',
    str(ROS / 'src/slam_toolbox/src/slam_toolbox_common.cpp'): '3b1323d284cb1e05c171199f3c9b8eca3cefbb775c6350bb0e84d695c9d62309',
    str(ROS / 'src/slam_toolbox/launch/online_async_multirobot_launch.py'): '5a87151b80ed9724e7f74ba954fb216ac655e279c7e8016c56c7685942fe6b1e',
    str(ROS / 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py'): '28b81c0df46753ab8058c0a05353cb8701bc3b67f422475ed31bf8fb62464051',
    str(ROS / 'src/slam_toolbox/config/mapper_params_online_multi_async.yaml'): '3ca81b5afb628d5787e60a266c6dc375a26f6b6a5c4fef70bd8a5261dc8dbb17',
    str(ROS / 'src/multi_robot/models/turtlebot3_waffle/model.sdf'): 'c8131da065085475bdb0ce1e4c3abfc8c009811af6851fadf1fc33bd38b1d8a1',
    str(ROS / 'scripts/mr3_env_worker.py'): 'fa9ec0ab25d36f724f4460abd94615ad101e21389ed9343966ca03fff2bec8ab',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def pairs_no_duplicates(items):
    result = {}
    for key, value in items:
        require(key not in result, 'duplicate JSON member: ' + key)
        result[key] = value
    return result


def parse(raw):
    return json.loads(raw, object_pairs_hook=pairs_no_duplicates,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + value)))


def proof(path):
    path = Path(path)
    before = path.stat()
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            'input changed while hashing: ' + str(path))
    return {'path': str(path.resolve()), 'sha256': digest.hexdigest(), 'bytes': after.st_size,
            'dev': after.st_dev, 'inode': after.st_ino, 'mtime_ns': after.st_mtime_ns}


def exact(value):
    require(type(value) in (int, float) and math.isfinite(value), 'invalid numeric evidence')
    return Q.from_float(value) if type(value) is float else Q(value)


def source_ns(value):
    # Frozen mr3_episode.timestamp_ns rounds the original endpoint, then subtracts.
    exact(value)
    return round(value * 1_000_000_000)


def stamp_ns(value):
    require(type(value['sec']) is int and type(value['nanosec']) is int, 'invalid stamp')
    return value['sec'] * 1_000_000_000 + value['nanosec']


def iter_records(path, epoch, counts):
    previous = 0
    with path.open('rb') as stream:
        for line, raw in enumerate(stream, 1):
            row = parse(raw)
            sequence = row['record_sequence']
            require(type(sequence) is int and sequence > previous, 'nonincreasing record sequence')
            require(row['epoch'] == epoch, 'foreign epoch in ' + str(path))
            previous = sequence
            counts[row['kind']] += 1
            yield line, row


def reference(path, line, row):
    return {'path': str(path), 'line': line, 'record_sequence': row['record_sequence'],
            'clock_ns': row.get('clock_ns'), 'sim_time_sec': row.get('sim_time_sec'),
            'wall_monotonic_ns': row['wall_monotonic_ns']}


def hold_geometry(states, clock):
    # Frozen equations: r=.25, g=.02, V=.3, R=.01*.78, each HOLD reach=2R.
    body, gap, speed, radius = Q(1, 4), Q(1, 50), Q(3, 10), Q(39, 5000)
    base = 2 * body + gap + 4 * radius
    result = []
    for left, right in (('tb1', 'tb2'), ('tb1', 'tb3'), ('tb2', 'tb3')):
        a, b = states[left], states[right]
        ages = [clock - source_ns(item['source_stamp']) for item in (a, b)]
        require(all(0 <= age <= 500_000_000 for age in ages), 'unexpected stale/future source')
        require(all(item['safety']['intent']['role'] == 'HOLD' for item in (a, b)), 'not two delivered HOLD intents')
        uncertainty = speed * Q(sum(ages), 1_000_000_000)
        required = base + uncertainty
        frames = {}
        for frame in ('map', 'raw'):
            aa = a if frame == 'map' else a['odometry']['pose']['pose']['position']
            bb = b if frame == 'map' else b['odometry']['pose']['pose']['position']
            delta = [exact(bb[key]) - exact(aa[key]) for key in ('x', 'y')]
            squared = sum(value * value for value in delta)
            distance = math.sqrt(float(squared))
            frames[frame] = {'delta_exact': list(map(str, delta)), 'distance_squared_exact': str(squared),
                'required_centre_distance_exact_m': str(required),
                'squared_margin_exact_m2': str(squared - required * required),
                'necessary_condition_met': squared >= required * required,
                'distance_m_display': distance, 'margin_m_display': distance - float(required),
                'max_sum_age_seconds_display': (distance - float(base)) / float(speed)}
        result.append({'robots': [left, right], 'source_ages_ns': ages,
            'uncertainty_exact_m': str(uncertainty), 'frames': frames,
            'map_and_raw_necessary': all(item['necessary_condition_met'] for item in frames.values())})
    return result


def analyse(root, episode):
    metadata_path = episode / 'metadata.json'
    metadata = parse(metadata_path.read_bytes())
    require(metadata['freeze'] == FREEZE and metadata['safety_contract'] == 'mr3-reach-v1', 'wrong original run')
    require(metadata['scene'] == 'open' and metadata['seed'] == 101, 'unexpected original slot')
    epoch = metadata['epoch']
    motion_path, info_path = episode / 'motion_safety.jsonl', episode / 'information_states.jsonl'
    input_paths = [metadata_path, motion_path, info_path] + [episode / ('drive_model_' + robot + '.sdf') for robot in ROBOTS]
    before = [proof(path) for path in input_paths]
    source_before = [proof(root / path) for path in SOURCES]
    frozen, frozen_texts = [], {}
    for relative, expected in SOURCES.items():
        argv = ['git', 'show', FREEZE + ':' + relative]
        child = subprocess.run(argv, cwd=root, capture_output=True, check=False)
        require(child.returncode == 0, 'cannot read frozen source: ' + relative)
        actual = hashlib.sha256(child.stdout).hexdigest()
        require(actual == expected, 'frozen source pin mismatch: ' + relative)
        frozen_texts[relative] = child.stdout.decode('utf-8')
        frozen.append({'path': relative, 'freeze': FREEZE, 'sha256': actual,
                       'actual_argv': argv, 'returncode': child.returncode})
    require(metadata['command'][:4] == ['ros2', 'launch', 'multi_robot',
                                      'gazebo_multirobot_mapping_with_nav2.launch.py'], 'different actual root launch')
    root_launch = str(ROS / 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py')
    slam_launch = str(ROS / 'src/slam_toolbox/launch/online_async_multirobot_launch.py')
    require('online_async_multirobot_launch.py' in frozen_texts[root_launch]
            and "executable='multirobot_slam_toolbox_node'" in frozen_texts[slam_launch]
            and 'mapper_params_online_multi_async.yaml' in frozen_texts[slam_launch], 'frozen launch chain mismatch')
    motion_counts = Counter()
    first_failure = first_decision = None
    failures, releases, prior_decisions = [], [], {}
    for line, row in iter_records(motion_path, epoch, motion_counts):
        kind, payload = row['kind'], row['payload']
        ref = reference(motion_path, line, row)
        if kind == 'reach_model_failure':
            captured = {'reference': ref, 'payload': payload}
            failures.append(captured)
            if first_failure is None:
                first_failure = captured
        if kind == 'reach_release_ready':
            releases.append({'reference': ref, 'payload': payload})
        if kind == 'reach_decision':
            if first_failure is None:
                prior_decisions[payload['robot']] = {'reference': ref, 'payload': payload}
            elif first_decision is None and payload['robot'] == first_failure['payload']['robot']:
                first_decision = {'reference': ref, 'payload': payload}
    require(first_failure is not None and first_decision is not None, 'missing actual failure/decision')
    require(first_failure['reference']['record_sequence'] == 43180
            and first_failure['payload'] == {'schema': 'mr3-reach-runtime-fault-v1', 'robot': 'tb1',
                'reason': REASON, 'clock_ns': 39_220_000_000}, 'unexpected first failure')
    require(first_decision['reference']['record_sequence'] == 43182, 'unexpected first failed decision')
    decision = first_decision['payload']
    clock = decision['clock_ns']
    states = {'tb1': decision['own_state'], **decision['received_peers']}
    require(set(states) == set(ROBOTS), 'missing same-bundle robot')
    require(all(state['epoch'] == epoch and state['name'] == robot for robot, state in states.items()), 'foreign state')
    require(decision['started'] is True and decision['decision']['reason'] == 'reach_model_failure'
            and decision['decision']['output'] == [0.0, 0.0], 'unexpected failure action')
    states_summary = {}
    for robot, state in states.items():
        odom, transform = state['odometry'], state['transform']
        raw_source = stamp_ns(odom['header']['stamp'])
        validity = stamp_ns(transform['header']['stamp'])
        tf_source = source_ns(state['tf_source_stamp'])
        require(raw_source == source_ns(state['odom_source_stamp']), 'raw source mismatch')
        require(validity - 200_000_000 == tf_source and state['tf_validity_lead_sec'] == 0.2, 'TF provenance mismatch')
        require(source_ns(state['source_stamp']) == min(raw_source, tf_source), 'minimum-source mismatch')
        intent = state['safety']['intent']
        require(intent['lineage']['release_clock_ns'] == 39_200_000_000, 'unexpected release clock')
        require(state['safety']['calibration']['odometry'] == odom, 'calibration is not selected raw')
        states_summary[robot] = {'map_xy': [state['x'], state['y']], 'raw_xyz': odom['pose']['pose']['position'],
            'source_stamp_original': state['source_stamp'], 'minimum_source_ns': source_ns(state['source_stamp']),
            'odom_source_ns': raw_source, 'tf_source_ns': tf_source, 'tf_validity_ns': validity,
            'minimum_source_age_ns': clock - source_ns(state['source_stamp']), 'odom_age_ns': clock - raw_source,
            'intent': intent, 'raw_linear': odom['twist']['twist']['linear'],
            'raw_angular': odom['twist']['twist']['angular']}
    information_counts = Counter()
    admissions = {robot: Counter() for robot in ROBOTS}
    tf_counts = Counter()
    source_first = {robot: {} for robot in ROBOTS}
    previous_received_source = {}
    source_backsteps = {robot: [] for robot in ROBOTS}
    selected_tf_refs = {robot: [] for robot in ROBOTS}
    selection_refs = {robot: [] for robot in ROBOTS}
    for line, row in iter_records(info_path, epoch, information_counts):
        payload = row['payload']
        if row['kind'] == 'tf_ingress':
            robot = payload['robot']
            require(robot in ROBOTS, 'unexpected TF robot')
            source = payload['source_ns']
            require(type(source) is int and stamp_ns(payload['raw']['header']['stamp']) - 200_000_000 == source,
                    'ingress header/source mismatch')
            tf_counts[robot] += 1
            admissions[robot][payload['admission']] += 1
            ref = {**reference(info_path, line, row), 'input_sequence': payload['input_sequence'],
                   'source_ns': source, 'header_stamp': payload['raw']['header']['stamp'],
                   'admission': payload['admission']}
            if robot in previous_received_source and source < previous_received_source[robot]:
                source_backsteps[robot].append({**ref, 'previous_received_source_ns': previous_received_source[robot]})
            previous_received_source[robot] = source
            source_first[robot].setdefault(source, ref)
            if payload['raw'] == states[robot]['transform']:
                selected_tf_refs[robot].append(ref)
        if row['kind'] == 'state_selection' and abs(row['clock_ns'] - clock) <= 20_000_000:
            selection_refs[payload['robot']].append({'reference': reference(info_path, line, row), 'payload': payload})
    cadence = {}
    for robot in ROBOTS:
        ordered = sorted(source_first[robot])
        require(len(ordered) > 2, 'insufficient recorded source renewals')
        selected_source = states_summary[robot]['tf_source_ns']
        require(selected_source in source_first[robot], 'selected source header absent from actual information ingress')
        intervals = Counter(b - a for a, b in zip(ordered, ordered[1:]))
        cadence[robot] = {'tf_ingress_count': tf_counts[robot], 'admission_counts': dict(admissions[robot]),
            'unique_source_count': len(ordered), 'first_source_ns': ordered[0], 'last_source_ns': ordered[-1],
            'positive_source_interval_ns_histogram': {str(key): value for key, value in sorted(intervals.items())},
            'most_common_source_interval_ns': intervals.most_common(1)[0][0],
            'received_source_backsteps': source_backsteps[robot],
            'first_occurrences_near_failure': [source_first[robot][source] for source in ordered
                                               if clock - 1_000_000_000 <= source <= clock + 1_000_000_000],
            'selected_transform_exact_match_count': len(selected_tf_refs[robot]),
            'selected_transform_first_match': selected_tf_refs[robot][0] if selected_tf_refs[robot] else None,
            'selected_transform_last_match': selected_tf_refs[robot][-1] if selected_tf_refs[robot] else None,
            'selected_source_header_first_occurrence': source_first[robot][selected_source],
            'selection_refs_near_failure': selection_refs[robot]}
    rates = {}
    for robot in ROBOTS:
        sensors = ET.fromstring((episode / ('drive_model_' + robot + '.sdf')).read_bytes()).findall(
            "./model/link[@name='base_scan']/sensor[@name='hls_lfcd_lds']")
        require(len(sensors) == 1 and sensors[0].attrib.get('type') == 'ray', 'ambiguous actual laser')
        rates[robot] = sensors[0].findtext('update_rate')
        require(rates[robot] == '5', 'original actual laser was not 5 Hz')
    geometry = hold_geometry(states, clock)
    require([row['map_and_raw_necessary'] for row in geometry] == [True, False, False], 'unexpected independent geometry')
    after = [proof(path) for path in input_paths]
    source_after = [proof(root / path) for path in SOURCES]
    require(before == after and source_before == source_after, 'evidence/source changed during analysis')
    return {'passed': True, 'errors': [], 'epoch': epoch, 'inputs_before': before, 'inputs_after': after,
        'current_sources_before': source_before, 'current_sources_after': source_after,
        'frozen_source_proofs': frozen, 'motion_kind_counts_whole_trace': dict(motion_counts),
        'information_kind_counts_whole_trace': dict(information_counts),
        'first_failure': first_failure, 'all_model_failures': failures,
        'first_decision': first_decision, 'prior_decisions': prior_decisions, 'release_records': releases,
        'first_failure_states': states_summary, 'independent_hold_pair_substitution': geometry,
        'actual_generated_laser_rate_hz': rates, 'tf_source_cadence': cadence,
        'launch_source_provenance': {'actual_episode_launch_argv': metadata['command'],
            'frozen_root_launch': root_launch, 'frozen_slam_launch': slam_launch,
            'selected_executable': 'multirobot_slam_toolbox_node',
            'selected_callback_source': str(ROS / 'src/slam_toolbox/src/slam_toolbox_multirobot.cpp'),
            'scope': 'actual episode argv and exact frozen launch source chain; no new ELF or live custody credit'},
        'equations': {'R': '39/5000', 'each_hold_buffer': '39/2500', 'no_age_pair_base': '689/1250',
            'required': '689/1250 + (3/10)*(age_left_ns+age_right_ns)/1000000000',
            'comparison': 'exact binary64 XY distance squared >= exact required squared',
            'ages': 'same clock-round(min(odom_source,tf_header-.2)*1e9) in BOTH frames'},
        'source_line_references': {'geometry': 'mr3_reach_geometry.py:191-237',
            'pair_age_binding': 'mr3_reach_runtime.py:101-120',
            'release_local_only': 'mr3_reach_runtime.py:390-410; motion_safety.py:255-270',
            'first_postrelease_pair_check': 'mr3_reach_runtime.py:427-438',
            'state_minimum': 'mr3_information.py:188-210,1190-1192',
            'scan_header_before_processing': 'slam_toolbox_multirobot.cpp:17-43',
            'selected_slam_executable': 'online_async_multirobot_launch.py:33-42',
            'tf_header_from_scan_header': 'slam_toolbox_common.cpp:268-290'},
        'interpretation': {
            'first_failure_is_missing_initial_geometric_certificate': True,
            'actual_plant_dynamic_counterexample_established_by_this_analysis': False,
            'initial_release_checks_only_local_raw_model_not_joint_pair_geometry': True,
            'source_age_below_half_second_does_not_imply_pair_margin': True,
            'release_phase_alignment_alone_does_not_prove_recurring_hold': True,
            'tf_publish_period_is_not_scan_source_refresh_period': True,
            'scan_header_is_stored_before_getOdomPose_and_addScan': True,
            'every_TF_source_header_does_not_prove_a_new_accepted_graph_update': True,
            'prospective_20Hz_changes_real_sensor_observation_distribution': True,
            'prospective_20Hz_requires_fresh_freeze_and_full_native_qualification': True}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--episode', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Refuse overwrite before reading even the first original evidence file.
    require(not args.output.exists(), 'output already exists: ' + str(args.output))
    started = time.monotonic_ns()
    self_before = proof(Path(__file__))
    result = {'schema': SCHEMA, 'freeze': FREEZE, 'scope': 'closed_evidence_forensics_only',
              'original_failure_retained': True, 'scientific_qualification': False,
              'native_admission': False, 'passed_meaning': 'successful read-only forensic extraction only'}
    rc = 0
    try:
        result.update(analyse(args.root.resolve(), args.episode or args.root / EPISODE))
    except Exception as error:
        rc = 1
        result.update(passed=False, errors=[{'type': type(error).__name__, 'message': str(error)}])
    result.update(started_monotonic_ns=started, ended_monotonic_ns=time.monotonic_ns(),
                  actual_argv=[sys.executable, *sys.argv], source_before=self_before, source_after=proof(Path(__file__)))
    if result['source_before'] != result['source_after']:
        rc = 1
        result['passed'] = False
        result['errors'].append({'type': 'ValueError', 'message': 'helper source changed during analysis'})
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'schema': SCHEMA, 'passed': result['passed'], 'output': str(args.output),
                      'scientific_qualification': False, 'native_admission': False}))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
