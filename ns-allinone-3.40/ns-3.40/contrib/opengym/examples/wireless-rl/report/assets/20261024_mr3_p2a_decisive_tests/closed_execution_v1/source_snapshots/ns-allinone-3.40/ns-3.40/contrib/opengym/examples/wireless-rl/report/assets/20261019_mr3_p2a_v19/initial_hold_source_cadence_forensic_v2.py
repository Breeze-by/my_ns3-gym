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
SCHEMA = 'mr3-v18-initial-hold-source-cadence-forensics-v2'
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


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def prior_attempt():
    directory = Path(__file__).resolve().parent
    script = directory/'initial_hold_source_cadence_forensic_v1.py'
    result_path = directory/'initial_hold_source_cadence_forensic_failed_result_v1.json'
    wait_path = directory/'checks/initial_hold_forensic_cpu_attempt_v1/actual_wait.json'
    original = Path('/tmp/mr3_p2a_v19_initial_hold_source_cadence_forensic_v1.json')
    expected = ((script,'ffd03c7d339ab591121a0bcab4673a0cba7600dac6abd578bd71c7c816d41f35'),
        (result_path,'5b25465b4336b1fa0930b8a62762a9293f3d0ef78c06097d14591280426dd6c0'),
        (wait_path,'4e7d1706746930918c649789d5dabb8bc93292a95e914778e103dc0a3d954fe4'))
    bindings = [proof(path) for path,_ in expected]
    require(all(row['sha256'] == item[1] for row,item in zip(bindings,expected)),
            'original failed forensic source/result/wait changed')
    raw = result_path.read_bytes()
    require(raw == original.read_bytes(),'original failed forensic canonical/tmp bytes differ')
    result,wait = parse(raw),parse(wait_path.read_bytes())
    require(result['passed'] is False and result['errors'] == [{'type':'KeyError','message':"'transform'"}]
            and result['schema'] == 'mr3-v18-initial-hold-source-cadence-forensics-v1'
            and result['native_admission'] is False and result['scientific_qualification'] is False
            and result['source_before'] == result['source_after']
            and result['source_before']['sha256'] == expected[0][1],
            'original forensic FAIL was reclassified')
    require(wait['schema'] == 'mr3-v15-finite-preparation-actual-child-wait-v1'
            and wait['actual_waited'] is True and wait['actual_returncode'] == 1 and wait['passed'] is False
            and wait['actual_argv'] == ['/usr/bin/python3','-B',str(script),'--output',str(original)]
            and wait['source_unchanged'] is True and wait['source_before'] == wait['source_after']
            and wait['actual_child_wait_seconds'] == '7.071966402'
            and wait['ended_monotonic_ns']-wait['started_monotonic_ns'] == 7_071_966_402,
            'original forensic actual failed CPU wait differs')
    return {'source':bindings[0],'canonical_result':bindings[1],'actual_cpu_wait':bindings[2],
        'original_output':proof(original),'passed':False,'actual_returncode':1,
        'errors':result['errors'],'failure_retained':True,'native_admission':False}


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


def analyse(root, episode, previous_attempt):
    metadata_path = episode / 'metadata.json'
    metadata = parse(metadata_path.read_bytes())
    require(metadata['freeze'] == FREEZE and metadata['safety_contract'] == 'mr3-reach-v1', 'wrong original run')
    require(metadata['scene'] == 'open' and metadata['seed'] == 101, 'unexpected original slot')
    epoch = metadata['epoch']
    motion_path, info_path = episode / 'motion_safety.jsonl', episode / 'information_states.jsonl'
    prior_paths = [Path(row['path']) for key,row in previous_attempt.items() if isinstance(row,dict) and 'path' in row]
    input_paths = [metadata_path, motion_path, info_path] + [episode / ('drive_model_' + robot + '.sdf') for robot in ROBOTS]
    before = [proof(path) for path in input_paths]
    prior_before = [proof(path) for path in prior_paths]
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
    latest_received = latest_ingress = selected_received = selected_ingress = None
    own_tf_inputs = {}
    failures, releases, prior_decisions = [], [], {}
    for line, row in iter_records(motion_path, epoch, motion_counts):
        kind, payload = row['kind'], row['payload']
        ref = reference(motion_path, line, row)
        if first_failure is None and kind == 'own_tf':
            key = payload['robot'],payload['input_sequence']
            require(key not in own_tf_inputs,'duplicate original Motion own-TF input identity')
            own_tf_inputs[key] = {'reference':ref,'payload':payload}
        if first_failure is None and kind == 'reach_state_ingress':
            latest_ingress = {'reference':ref,'payload':payload}
        if first_failure is None and kind == 'received_states':
            require(latest_ingress is not None
                    and canonical(latest_ingress['payload']['message']) == canonical(payload)
                    and canonical(parse(latest_ingress['payload']['raw_json'])) == canonical(payload),
                    'actual Motion received bundle lacks identical raw callback ingress')
            latest_received = {'reference':ref,'message':payload}
        if kind == 'reach_model_failure':
            captured = {'reference': ref, 'payload': payload}
            failures.append(captured)
            if first_failure is None:
                first_failure = captured
                selected_received,selected_ingress = latest_received,latest_ingress
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
    require(selected_received is not None and selected_ingress is not None,
            'no actual received bundle before the first failure')
    bundle = selected_received['message']
    require(bundle['epoch'] == epoch and selected_received['reference']['record_sequence'] < 43180
            and selected_ingress['reference']['record_sequence'] < selected_received['reference']['record_sequence']
            and selected_ingress['payload']['publisher_identity']['valid'] is True,
            'actual preceding Motion bundle identity/order differs')
    bundle_robots = {state['name']:state for state in bundle['robots']}
    require(len(bundle['robots']) == len(bundle_robots) == 3 and set(bundle_robots) == set(ROBOTS),
            'actual Motion bundle does not contain exact three robots')
    decision = first_decision['payload']
    clock = decision['clock_ns']
    states = {'tb1': decision['own_state'], **decision['received_peers']}
    require(set(states) == set(ROBOTS), 'missing same-bundle robot')
    require(all(state['epoch'] == epoch and state['name'] == robot for robot, state in states.items()), 'foreign state')
    require(decision['started'] is True and decision['decision']['reason'] == 'reach_model_failure'
            and decision['decision']['output'] == [0.0, 0.0], 'unexpected failure action')
    peers_before = canonical(decision['received_peers'])
    require(set(decision['received_peers']) == {'tb2','tb3'}
            and all(canonical(state) == canonical(bundle_robots[name])
                    for name,state in decision['received_peers'].items()),
            'original first-decision peers differ from the actual preceding received bundle')
    require(all('transform' not in state for state in decision['received_peers'].values()),
            'original missing peer transform was silently replaced')
    own_tf_provenance = own_tf_inputs.get(('tb1',decision['own_state']['input_sequences']['tf']))
    require(own_tf_provenance is not None
            and canonical(own_tf_provenance['payload']['message']) == canonical(decision['own_state']['transform'])
            and own_tf_provenance['reference']['record_sequence'] < first_failure['reference']['record_sequence'],
            'original own-state TF lacks exact actual Motion ingress provenance')
    information_counts = Counter()
    admissions = {robot: Counter() for robot in ROBOTS}
    tf_counts = Counter()
    source_first = {robot: {} for robot in ROBOTS}
    previous_received_source = {}
    source_backsteps = {robot: [] for robot in ROBOTS}
    selected_tf_refs = {robot: [] for robot in ROBOTS}
    selection_refs = {robot: [] for robot in ROBOTS}
    tf_inputs,odom_inputs,selections,sends = {},{},{},{}
    matching_publications = []
    for line, row in iter_records(info_path, epoch, information_counts):
        payload = row['payload']
        ref = reference(info_path,line,row)
        if row['kind'] == 'odom_ingress':
            key = payload['robot'],payload['input_sequence']
            require(key not in odom_inputs,'duplicate original odom input sequence')
            odom_inputs[key] = {'reference':ref,'payload':payload}
        if row['kind'] == 'state_selection':
            selections.setdefault((payload['cycle_id'],payload['robot']),[]).append({'reference':ref,'payload':payload})
        if row['kind'] == 'state_send':
            envelope = payload['envelope']
            sends.setdefault((payload['robot'],envelope['sequence']),[]).append({'reference':ref,'payload':payload})
        if row['kind'] == 'state_publish' and canonical(payload['message']) == canonical(bundle):
            require(payload['message_sha256'] == digest(bundle),'actual Information bundle digest differs')
            matching_publications.append({'reference':ref,'payload':payload})
        if row['kind'] == 'tf_ingress':
            robot = payload['robot']
            require(robot in ROBOTS, 'unexpected TF robot')
            source = payload['source_ns']
            require(type(source) is int and stamp_ns(payload['raw']['header']['stamp']) - 200_000_000 == source,
                    'ingress header/source mismatch')
            key = robot,payload['input_sequence']
            require(key not in tf_inputs,'duplicate original TF input sequence')
            require(payload['raw_sha256'] == digest(payload['raw']),'original TF ingress raw SHA differs')
            tf_inputs[key] = {'reference':ref,'payload':payload}
            tf_counts[robot] += 1
            admissions[robot][payload['admission']] += 1
            ref = {**reference(info_path, line, row), 'input_sequence': payload['input_sequence'],
                   'source_ns': source, 'header_stamp': payload['raw']['header']['stamp'],
                   'admission': payload['admission']}
            if robot in previous_received_source and source < previous_received_source[robot]:
                source_backsteps[robot].append({**ref, 'previous_received_source_ns': previous_received_source[robot]})
            previous_received_source[robot] = source
            source_first[robot].setdefault(source, ref)
        if row['kind'] == 'state_selection' and abs(row['clock_ns'] - clock) <= 20_000_000:
            selection_refs[payload['robot']].append({'reference': reference(info_path, line, row), 'payload': payload})
    require(len(matching_publications) == 1,'exact actual Information publication of Motion bundle is unknown/ambiguous')
    publication = matching_publications[0]
    published = publication['payload']
    require(published['message']['sequence'] == bundle['sequence'] and published['message']['epoch'] == epoch
            and published['publish_started_wall_monotonic_ns'] <= selected_ingress['reference']['wall_monotonic_ns']
            <= selected_received['reference']['wall_monotonic_ns']
            and canonical(selected_ingress['payload']['message']) == canonical(bundle),
            'Information publication/Motion reception order or whole content differs')
    side_rows = published['side_publications']
    side = {item['robot']:item for item in side_rows}
    require(len(side_rows) == len(side) == 3 and set(side) == set(ROBOTS)
            and set(published['envelopes']) == set(ROBOTS), 'incomplete original envelope/side publication set')
    envelope_provenance = {}
    peer_tf_provenance = {}
    for robot in ROBOTS:
        envelope = published['envelopes'][robot]
        require(type(envelope) is dict and envelope['epoch'] == epoch and envelope['stream'] == 'state'
                and envelope['source'] == robot and envelope['sequence'] == bundle_robots[robot]['sequence']
                and envelope['version'] == bundle_robots[robot]['version']
                and envelope['source_stamp'] == bundle_robots[robot]['source_stamp']
                and envelope['received_stamp'] == bundle_robots[robot]['received_stamp'],
                'actual envelope/robot identity differs: '+robot)
        send_rows = sends.get((robot,envelope['sequence']),[])
        require(len(send_rows) == 1,'actual state_send identity is unknown/ambiguous: '+robot)
        send = send_rows[0]; sent = send['payload']['envelope']
        require(canonical({key:value for key,value in sent.items() if key != 'received_stamp'})
                == canonical({key:value for key,value in envelope.items() if key != 'received_stamp'})
                and sent['received_stamp'] is None
                and send['payload']['payload_sha256'] == digest(sent['payload'])
                and send['payload']['cycle_id'] == published['cycle_id'],
                'state_send and actual received envelope differ: '+robot)
        selected_rows = selections.get((send['payload']['cycle_id'],robot),[])
        require(len(selected_rows) == 1,'actual source selection is unknown/ambiguous: '+robot)
        selection = selected_rows[0]; chosen = selection['payload']
        require(chosen['skip_reason'] is None,'selected original envelope was not actually admitted: '+robot)
        tf = tf_inputs.get((robot,chosen['tf_input_sequence']))
        odom = odom_inputs.get((robot,chosen['odom_input_sequence']))
        require(tf is not None and odom is not None,'selected original input ingress is unknown: '+robot)
        content = envelope['payload']
        transform = content['transform']
        require(canonical(tf['payload']['raw']) == canonical(transform)
                and tf['payload']['raw_sha256'] == digest(transform) == side[robot]['tf_sha256']
                and tf['payload']['admission'] == 'queued'
                and chosen['tf_source_ns'] == tf['payload']['source_ns']
                and chosen['tf_source_ns'] == stamp_ns(transform['header']['stamp'])-200_000_000
                and chosen['odom_source_ns'] == odom['payload']['source_ns']
                and chosen['odom_source_ns'] == stamp_ns(content['odometry']['header']['stamp'])
                and canonical(odom['payload']['raw']) == canonical(content['odometry'])
                and odom['payload']['raw_sha256'] == digest(content['odometry']) == side[robot]['odom_sha256']
                and odom['payload']['admission'] == 'queued'
                and side[robot]['envelope_sequence'] == envelope['sequence'],
                'actual admitted TF/odom/side publication provenance differs: '+robot)
        require(tf['reference']['record_sequence'] < selection['reference']['record_sequence']
                and odom['reference']['record_sequence'] < selection['reference']['record_sequence']
                < send['reference']['record_sequence'] < publication['reference']['record_sequence']
                and selection['reference']['wall_monotonic_ns'] <= send['reference']['wall_monotonic_ns']
                <= published['publish_started_wall_monotonic_ns'],
                'actual admitted source/selection/send/publication order differs: '+robot)
        expected_row = {key:value for key,value in content.items() if key != 'transform'}
        expected_row.update(epoch=epoch,sequence=envelope['sequence'],version=envelope['version'],
            source_stamp=envelope['source_stamp'],received_stamp=envelope['received_stamp'],
            valid=(envelope['source_stamp'] > 0 and 0 <= publication['reference']['clock_ns']
                -source_ns(envelope['source_stamp']) <= 500_000_000))
        require(canonical(expected_row) == canonical(bundle_robots[robot]),
                'original envelope payload does not explain original published robot row: '+robot)
        chain = {'envelope_sequence':envelope['sequence'],'envelope_version':envelope['version'],
            'envelope_source_stamp':envelope['source_stamp'],'envelope_payload_sha256':digest(content),
            'state_send':send,'state_selection':selection,'tf_ingress':tf,'odom_ingress':odom,
            'side_publication':side[robot],'transform':transform,'transform_sha256':digest(transform),
            'original_published_robot_sha256':digest(bundle_robots[robot])}
        envelope_provenance[robot] = chain
        if robot in decision['received_peers']:
            peer_tf_provenance[robot] = chain
    states_summary = {}
    for robot,state in states.items():
        odom = state['odometry']
        transform = (state['transform'] if robot == 'tb1' else peer_tf_provenance[robot]['transform'])
        raw_source = stamp_ns(odom['header']['stamp'])
        validity = stamp_ns(transform['header']['stamp'])
        tf_source = source_ns(state['tf_source_stamp'])
        require(raw_source == source_ns(state['odom_source_stamp']), 'raw source mismatch')
        require(validity-200_000_000 == tf_source and state['tf_validity_lead_sec'] == 0.2,'TF provenance mismatch')
        require(source_ns(state['tf_validity_stamp']) == validity
                and source_ns(state['source_stamp']) == min(raw_source,tf_source),'minimum-source mismatch')
        intent = state['safety']['intent']
        require(intent['lineage']['release_clock_ns'] == 39_200_000_000,'unexpected release clock')
        require(canonical(state['safety']['calibration']['odometry']) == canonical(odom),'calibration is not selected raw')
        for (name,_),item in tf_inputs.items():
            if name == robot and canonical(item['payload']['raw']) == canonical(transform):
                selected_tf_refs[robot].append({**item['reference'],**{key:item['payload'][key]
                    for key in ('input_sequence','source_ns','admission')},'header_stamp':transform['header']['stamp']})
        states_summary[robot] = {'map_xy':[state['x'],state['y']],'raw_xyz':odom['pose']['pose']['position'],
            'source_stamp_original':state['source_stamp'],'minimum_source_ns':source_ns(state['source_stamp']),
            'odom_source_ns':raw_source,'tf_source_ns':tf_source,'tf_validity_ns':validity,
            'minimum_source_age_ns':clock-source_ns(state['source_stamp']),'odom_age_ns':clock-raw_source,
            'intent':intent,'raw_linear':odom['twist']['twist']['linear'],'raw_angular':odom['twist']['twist']['angular'],
            'transform_present_in_original_decision':('transform' in state),
            'tf_provenance_scope':('original_own_state' if robot == 'tb1' else 'separate_actual_envelope_evidence_only')}
    require(canonical(decision['received_peers']) == peers_before,
            'forensic analysis mutated original peer content')
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
    prior_after = [proof(path) for path in prior_paths]
    source_after = [proof(root / path) for path in SOURCES]
    require(before == after and prior_before == prior_after and source_before == source_after,
            'evidence/source changed during analysis')
    return {'passed': True, 'errors': [], 'epoch': epoch, 'inputs_before': before, 'inputs_after': after,
        'current_sources_before': source_before, 'current_sources_after': source_after,
        'prior_attempt':previous_attempt,'prior_inputs_before':prior_before,'prior_inputs_after':prior_after,
        'frozen_source_proofs': frozen, 'motion_kind_counts_whole_trace': dict(motion_counts),
        'information_kind_counts_whole_trace': dict(information_counts),
        'first_failure': first_failure, 'all_model_failures': failures,
        'first_decision': first_decision, 'prior_decisions': prior_decisions, 'release_records': releases,
        'motion_received_bundle_before_first_failure':selected_received,
        'motion_raw_bundle_ingress':selected_ingress,
        'matched_information_publication':publication,
        'actual_envelope_source_provenance':envelope_provenance,
        'peer_tf_provenance':peer_tf_provenance,
        'own_tf_provenance':own_tf_provenance,
        'original_received_peers_sha256':digest(decision['received_peers']),
        'original_received_peers_unchanged':True,
        'peer_wire_transform_missing_preserved':True,
        'peer_fields_added_or_reconstructed':False,
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
        result['prior_attempt'] = prior_attempt()
        result.update(analyse(args.root.resolve(), args.episode or args.root / EPISODE,result['prior_attempt']))
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
