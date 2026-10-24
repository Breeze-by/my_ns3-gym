"""Independent stdlib audit of saved driver inputs and rim instructions; no ROS imports."""
import argparse
import copy
from fractions import Fraction
import gzip
import hashlib
import io
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROBOTS = ('tb1', 'tb2', 'tb3')
BASELINE = '57b7c7f372aef4d84acd25fcd97a9944fa1fe9bb'
MODEL = 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/models/turtlebot3_waffle/model.sdf'
SOURCE_PATHS = {
    'compiled_source_sha256': 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_gazebo_diff_drive.cpp',
    'compiled_header_sha256': 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_gazebo_diff_drive.hpp',
    'compiled_helper_sha256': 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/paired_wheel_slew.hpp',
    'compiled_target_contract_sha256': 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_drive_target.hpp',
}
MAX_DELAY_NS = 160_000_000
MAX_GAP_NS = 100_000_000
MATH_TOL = 1e-12
ALGORITHM = 'measured_joint_rim_paired_common_fraction_v1'
UPSTREAM_SHA = '7a6ef5eb9b48292f1b4f3d9a16907815d5d5a751e0a5635a1cac84315b95b498'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def integer(value):
    return type(value) is int


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def pair(value, label):
    require(type(value) is list and len(value) == 2 and all(number(x) for x in value), label)
    return value


def fraction(value):
    return Fraction.from_float(float(value))


def seconds_ns(value):
    require(number(value), 'invalid finite simulation seconds')
    return round(value * 10**9)


class Inputs:
    def __init__(self):
        self.bindings = {}

    def capture(self, path):
        path = Path(path)
        if not path.exists():
            path = Path(str(path) + '.gz')
        raw = path.read_bytes()
        binding = {'bytes': len(raw), 'sha256': sha(raw)}
        require(str(path) not in self.bindings or self.bindings[str(path)] == binding,
                'input changed between reads: ' + str(path))
        self.bindings[str(path)] = binding
        return path, raw

    def raw(self, path):
        actual, raw = self.capture(path)
        return gzip.decompress(raw) if actual.suffix == '.gz' else raw

    def json(self, path):
        return json.loads(self.raw(path))

    def lines(self, path):
        actual, raw = self.capture(path)
        stream = io.BytesIO(raw)
        if actual.suffix == '.gz':
            stream = gzip.GzipFile(fileobj=stream, mode='rb')
        with stream:
            for index, raw in enumerate(stream, 1):
                require(raw.endswith(b'\n'), f'incomplete JSONL {actual}:{index}')
                require(bool(raw.strip()), f'empty JSONL record {actual}:{index}')
                yield json.loads(raw)

    def verify_unchanged(self):
        for path, expected in self.bindings.items():
            raw = Path(path).read_bytes()
            require(expected == {'bytes': len(raw), 'sha256': sha(raw)},
                    'input changed during audit: ' + path)


def git_blob(freeze, relative):
    return subprocess.check_output(['git', 'show', f'{freeze}:{relative}'], cwd=ROOT)


def source_bindings(freeze):
    require(type(freeze) is str and re.fullmatch('[0-9a-f]{40}', freeze), 'exact commit SHA required')
    return {key: sha(git_blob(freeze, path)) for key, path in SOURCE_PATHS.items()}


def binary_binding(proof, freeze, compiled, inputs, archived=False):
    require(proof['schema'] == 'mr3-drive-binary-binding-v1' and proof['freeze'] == freeze,
            'binary proof schema/freeze mismatch')
    require(all(proof[key] == value for key, value in compiled.items()),
            'binary proof compiled sources differ from exact Git objects')
    path = Path(proof['library_path'])
    require(path.is_absolute(), 'binary proof library path must be absolute')
    require(type(proof['library_sha256']) is str and
            re.fullmatch('[0-9a-f]{64}', proof['library_sha256']), 'invalid library SHA')
    if archived:
        relative = Path(proof['archived_library_gzip'])
        require(not relative.is_absolute() and '..' not in relative.parts, 'invalid archive path')
        encoded_path = ROOT / relative
        require(encoded_path.resolve().is_relative_to(ROOT), 'archive outside repository')
        _, encoded = inputs.capture(encoded_path)
        require(sha(encoded) == proof['archived_library_encoded_sha256'],
                'archived encoded library SHA mismatch')
        raw = gzip.decompress(encoded)
    else:
        require(path.resolve() == path, 'current library path is not canonical')
        _, raw = inputs.capture(path)
    require(sha(raw) == proof['library_sha256'], 'actual library SHA differs from binary proof')
    return {'library_path': str(path), 'library_sha256': proof['library_sha256'],
            'compiled_sources': compiled, 'mode': 'archived_binary_replay' if archived else
            'current_canonical_binary_verified', 'current_binary_verified': not archived,
            'loaded_library_still_in_process_proven': False}


def physics_bounds(records, epoch, release):
    require(bool(records), 'missing physics records')
    step = records[0]['step_ns']
    require(integer(step) and step > 0, 'invalid physical tick')
    previous = records[0]['start_time_ns']
    previous_iterations = records[0]['start_iterations']
    require(integer(previous) and 0 <= previous <= release and
            integer(previous_iterations) and previous_iterations >= 0,
            'invalid initial physical alignment boundary')
    release_hit = previous == release
    for row in records:
        require(row['epoch'] == epoch and row['ok'] is True and row['paused'] is True,
                'physics epoch/ack mismatch')
        require(all(integer(row[key]) for key in ('start_time_ns', 'end_time_ns', 'steps',
                                                  'start_iterations', 'end_iterations', 'step_ns')),
                'noninteger physics record')
        require(row['step_ns'] == step and row['steps'] >= 0 and
                row['start_time_ns'] == previous and
                row['start_iterations'] == previous_iterations and
                row['end_time_ns'] - row['start_time_ns'] == row['steps'] * step and
                row['end_iterations'] - row['start_iterations'] == row['steps'],
                'discontinuous/inconsistent actual physics steps')
        previous = row['end_time_ns']
        previous_iterations = row['end_iterations']
        release_hit = release_hit or previous == release
    require(release_hit, 'release does not coincide with an actual physics boundary')
    return previous, step


def terminal_fixture(benchmark, steps, freeze):
    return (benchmark['freeze'] == freeze and benchmark.get('terminal_probe') is True and
            integer(benchmark.get('workers')) and integer(benchmark.get('steps_per_episode')) and
            benchmark.get('workers') == 1 and benchmark.get('steps_per_episode') == 4 and
            benchmark.get('schedule') == [['open', 101], ['open', 101]] and
            not any(benchmark.get(key, False) for key in (
                'preparation_motion_probe', 'deadline_probe', 'fault_probe')) and
            len(steps) == 4 and [seconds_ns(row['info']['dt']) for row in steps[:3]] == [10**9]*3 and
            seconds_ns(steps[-1]['info']['dt']) in (0, 20_000_000) and
            steps[-1]['terminated'] is True and steps[-1]['truncated'] is False and
            steps[-1]['info'].get('reason') == 'navigation_failure')


def guard_outputs(records, epoch, release):
    outputs = {name: [] for name in ROBOTS}
    for index, row in enumerate(records, 1):
        require(row['schema'] == 'mr3-motion-safety-v1' and row['epoch'] == epoch and
                integer(row['record_sequence']) and row['record_sequence'] == index,
                'guard log schema/epoch/record sequence')
        if row['kind'] != 'decision':
            continue
        value = row['payload']
        name = value['robot']
        require(name in ROBOTS and integer(value['clock_ns']) and value['clock_ns'] >= 0,
                'invalid guard source identity/clock')
        require(integer(value['decision_sequence']) and
                value['decision_sequence'] == len(outputs[name]) + 1,
                'guard publication decision sequence')
        output = pair(value['decision']['output'], 'invalid final guard output')
        require(abs(output[0]) <= .26 and abs(output[1]) <= .8, 'guard output outside command limits')
        if outputs[name]:
            prior = outputs[name][-1]
            require(value['clock_ns'] >= prior['clock_ns'], 'guard source clock rewind')
            if value['clock_ns'] == prior['clock_ns']:
                require(value['clock_ns'] < release and output == prior['output'] == [0., 0.],
                        'same-clock guard output is not a prerelease duplicate zero')
        outputs[name].append({'clock_ns': value['clock_ns'], 'output': output,
                              'started': value.get('started'),
                              'decision_sequence': value['decision_sequence'], 'line': index})
    return outputs


def physical_model(element):
    element = copy.deepcopy(element)
    for plugin in element.findall('.//plugin'):
        if plugin.get('name') == 'turtlebot3_diff_drive':
            plugin.set('filename', 'libgazebo_ros_diff_drive.so')
            for tag in ('mr3_audit_path', 'mr3_epoch', 'mr3_tagged_commands'):
                for child in plugin.findall(tag):
                    plugin.remove(child)
    def tree(node):
        return (node.tag, sorted(node.attrib.items()), (node.text or '').strip(),
                tuple(tree(child) for child in node))
    return tree(element)


def target_publications(records, guards, epoch):
    expected = sorted((dict(row, robot=name) for name in ROBOTS for row in guards[name]),
                      key=lambda row: row['line'])
    require(len(records) == len(expected), 'target publication ledger does not cover every guard decision once')
    previous_wall = -1
    for index, (row, source) in enumerate(zip(records, expected), 1):
        require(row['schema'] == 'mr3-drive-target-publication-v1' and row['epoch'] == epoch and
                integer(row['record_sequence']) and row['record_sequence'] == index and
                integer(row['wall_monotonic_ns']) and row['wall_monotonic_ns'] >= previous_wall and
                type(row['target_json']) is str, 'target publication ledger identity/sequence')
        previous_wall = row['wall_monotonic_ns']
        def unique_object(pairs):
            require(len({key for key, _ in pairs}) == len(pairs), 'duplicate target JSON object key')
            return dict(pairs)
        target = json.loads(row['target_json'], object_pairs_hook=unique_object)
        require(type(target) is dict and set(target) == {
                    'schema', 'epoch', 'robot', 'clock_ns', 'decision_sequence', 'linear_x', 'angular_z'} and
                integer(target['clock_ns']) and integer(target['decision_sequence']) and
                number(target['linear_x']) and number(target['angular_z']),
                'published target is not exact seven-field typed protocol')
        require(target == {'schema': 'mr3-drive-target-v1', 'epoch': epoch, 'robot': source['robot'],
                           'clock_ns': source['clock_ns'], 'decision_sequence': source['decision_sequence'],
                           'linear_x': source['output'][0], 'angular_z': source['output'][1]},
                'published target does not exactly bind corresponding guard decision')
    return {'passed': True, 'publications': len(records),
            'scope': 'Every logged guard decision has one exact seven-field native target publication; no delivery ACK inferred from publish alone'}


def drive_topology(row, epoch, release):
    require(row['schema'] == 'mr3-drive-topology-v1' and row['epoch'] == epoch and
            integer(row['clock_ns']) and 0 <= row['clock_ns'] <= release,
            'native drive topology schema/epoch/pre-release source clock')
    targets = {f'/{name}/mr3_drive/target' for name in ROBOTS}
    statuses = {f'/{name}/mr3_drive/status' for name in ROBOTS}
    require(set(row['publishers']) == targets | statuses and
            set(row['target_subscribers']) == targets and
            set(row['legacy_subscribers']) == {f'/{name}/cmd_vel' for name in ROBOTS},
            'native drive topology topic roles differ from exact three robots')
    gids = set()
    def endpoint(value, owner, topic_type, unique=True):
        require(type(value) is dict and set(value) == {'namespace', 'node', 'topic_type', 'endpoint_gid'} and
                type(value['namespace']) is str and type(value['node']) is str and
                value['topic_type'] == topic_type and type(value['endpoint_gid']) is str and
                re.fullmatch('[0-9a-f]{48}', value['endpoint_gid']) and int(value['endpoint_gid'], 16) != 0,
                'native drive topology endpoint lacks actual DDS identity/type')
        if owner is not None:
            require((value['namespace'], value['node']) == owner, 'unexpected native drive endpoint owner')
        if unique:
            require(value['endpoint_gid'] not in gids, 'native drive endpoints reuse a DDS GID')
            gids.add(value['endpoint_gid'])
    for name in ROBOTS:
        driver = ('/'+name, 'turtlebot3_diff_drive')
        target, status = f'/{name}/mr3_drive/target', f'/{name}/mr3_drive/status'
        for entries, owner in ((row['publishers'][target], ('/', 'motion_safety')),
                               (row['publishers'][status], driver),
                               (row['target_subscribers'][target], driver)):
            require(type(entries) is list and len(entries) == 1, 'native drive endpoint is not unique')
            endpoint(entries[0], owner, 'std_msgs/msg/String')
        legacy = row['legacy_subscribers'][f'/{name}/cmd_vel']
        require(type(legacy) is list, 'legacy drive subscriber graph malformed')
        for value in legacy:
            endpoint(value, None, 'geometry_msgs/msg/Twist', unique=False)
            require((value['namespace'], value['node']) != driver,
                    'tagged native driver still consumes untagged Twist')
    return {'passed': True, 'native_endpoints': len(gids), 'source_clock_ns': row['clock_ns'],
            'scope': 'Discovered pre-release DDS endpoint owners/GIDs only; no per-message GID provenance claim'}


def check_model(raw, old_raw, epoch, robot, original_directory):
    document = ET.fromstring(raw)
    require(physical_model(document) == physical_model(ET.fromstring(old_raw)),
            'effective model changes original physical/link/collision attributes')
    plugins = document.findall(".//plugin[@name='turtlebot3_diff_drive']")
    require(len(plugins) == 1, 'effective model drive plugin count')
    plugin = plugins[0]
    require(plugin.findtext('mr3_tagged_commands') == 'true',
            'effective model must enable tagged drive commands')
    require(plugin.get('filename') == 'libmr3_gazebo_diff_drive.so', 'wrong effective driver library')
    for tag in ('mr3_audit_path', 'mr3_epoch'):
        require(len(plugin.findall(tag)) == 1, 'effective model duplicate/missing audit tags')
    require(plugin.findtext('mr3_epoch') == epoch and plugin.findtext('mr3_audit_path') ==
            str(original_directory / f'drive_{robot}.jsonl'), 'effective model epoch/audit path mismatch')


def robot_audit(records, guards, name, epoch, release, final, step, compiled, binary, terminal,
                initial_receipt=None):
    require(bool(records), name + ': empty drive trace')
    config = records[0]
    expected = {'library_filename': 'libmr3_gazebo_diff_drive.so',
                'loaded_library_path': binary['library_path'], 'upstream_source_sha256': UPSTREAM_SHA,
                'wheel_order': ['right', 'left'],
                'joint_names': ['wheel_right_joint', 'wheel_left_joint'],
                'wheel_separation_m': [.287], 'wheel_diameter_m': [.066],
                'max_acceleration_mps2': 1., 'max_torque_nm': 20., 'update_rate_hz': 30.,
                'odometry_source': 1, 'num_wheel_pairs': 1, 'actuation_algorithm': ALGORITHM,
                'command_mode': 'tagged',
                'command_topic': f'/{name}/mr3_drive/target',
                'status_topic': f'/{name}/mr3_drive/status', **compiled}
    require(config['kind'] == 'configuration' and all(config.get(k) == v for k, v in expected.items()),
            name + ': driver configuration/compiled identity mismatch')
    require(all(number(config[key]) for key in (
                'max_acceleration_mps2', 'max_torque_nm', 'update_rate_hz')) and
            all(integer(config[key]) for key in ('odometry_source', 'num_wheel_pairs')),
            name + ': malformed physical configuration types')
    latest = (0, 0., 0., config['sim_time_ns'], 0, 0)
    cmd_seq, act_seq, previous_clock, previous_act = 0, 0, None, None
    guard_by_sequence = {row['decision_sequence']: row for row in guards}
    initial_command_line = None
    if initial_receipt is not None:
        require(type(initial_receipt) is dict and integer(initial_receipt.get('cmd_seq')),
                name + ': malformed initial driver receipt identity')
        initial = [(index, row) for index, row in enumerate(records, 1)
                   if row['kind'] == 'command_received' and row['cmd_seq'] == initial_receipt['cmd_seq']]
        require(len(initial) == 1 and initial_receipt.get('clock_ns') == release and
                initial_receipt.get('source_clock_ns') == release,
                name + ': initial driver storage is not at exact release')
        initial_command_line, command = initial[0]
        require(command['sim_time_ns'] == release and
                command['target_decision_sequence'] == initial_receipt['decision_sequence'] and
                command['target_clock_ns'] == release and
                command['desired_v'] == initial_receipt['linear_x'] and
                command['desired_w'] == initial_receipt['angular_z'],
                name + ': initial storage receipt does not match actual command')
    previous_target_sequence, previous_target_clock = 0, 0
    pending_status = None
    published_statuses = {}
    marker_clock = config['sim_time_ns']
    actuation, matched, reset_count, post_final_zero, prewarm_anchors = [], [], 0, 0, []
    prewarm_commands = []
    maximum_budget_ratio, max_math_residual = Fraction(0), 0.
    for line, row in enumerate(records, 1):
        prefix = f'{name} drive line{line}: '
        require(row['schema'] == 'mr3-drive-actuation-v2' and row['epoch'] == epoch and
                row['robot'] == name and integer(row['record_sequence']) and
                row['record_sequence'] == line, prefix + 'identity/sequence')
        clock = row['sim_time_ns']
        require(integer(clock) and clock >= 0 and clock % step == 0, prefix + 'nonphysical source clock')
        kind = row['kind']
        require(kind in ('configuration', 'reset', 'command_received', 'actuation',
                         'status_publish', 'target_rejected'),
                prefix + 'unknown record kind')
        if clock > final:
            require(kind in ('command_received', 'actuation', 'status_publish') and
                    row.get('desired_v') == row.get('desired_w') == 0.,
                    prefix + 'nonzero execution outside recorded final physics boundary')
            post_final_zero += 1
        if kind == 'reset':
            require(clock < release, prefix + 'reset at/after release')
            require(integer(row['cmd_seq']) and row['cmd_seq'] == cmd_seq and
                    row['target_reset'] is True and
                    row['desired_v'] == row['desired_w'] == 0. and
                    row['internal_instruction_rim_mps'] == [0., 0.], prefix + 'reset provenance')
            require(integer(row['target_decision_sequence']) and integer(row['target_clock_ns']) and
                    (row['target_decision_sequence'], row['target_clock_ns']) == latest[4:] and
                    latest[1:3] == (0., 0.) and pending_status is None,
                    prefix + 'reset changes tagged target identity or nonzero provenance')
            previous_act = None
            marker_clock = clock
            reset_count += 1
        else:
            require(previous_clock is None or clock >= previous_clock, prefix + 'source clock rewind')
        previous_clock = clock
        if kind == 'configuration':
            require(line == 1, prefix + 'duplicate configuration')
        elif kind == 'command_received':
            require(pending_status is None, prefix + 'new target arrived before prior status publication')
            require(integer(row['cmd_seq']) and row['cmd_seq'] == cmd_seq + 1,
                    prefix + 'command sequence')
            v, w = row['desired_v'], row['desired_w']
            require(number(v) and number(w) and abs(v) <= .26 and abs(w) <= .8,
                    prefix + 'received command outside limits')
            target_sequence, target_clock = row['target_decision_sequence'], row['target_clock_ns']
            require(integer(target_sequence) and target_sequence > previous_target_sequence and
                    integer(target_clock) and previous_target_clock <= target_clock <= clock,
                    prefix + 'target sequence/source clock invalid or regressed')
            source = guard_by_sequence.get(target_sequence)
            require(source is not None and source['clock_ns'] == target_clock and
                    source['output'] == [v, w], prefix + 'target does not exactly bind unique guard decision')
            prewarm_command = (initial_command_line is not None and line < initial_command_line and
                               row['cmd_seq'] < initial_receipt['cmd_seq'] and clock <= release and
                               [v, w] == [0., 0.] and source.get('started') is False)
            if prewarm_command:
                prewarm_commands.append({'line': line, 'receive_ns': clock, 'cmd_seq': row['cmd_seq'],
                                         'target_decision_sequence': target_sequence,
                                         'guard_source_ns': target_clock,
                                         'initial_command_line': initial_command_line,
                                         'initial_cmd_seq': initial_receipt['cmd_seq'],
                                         'task_input_credit': False, 'sampled_response_credit': False})
            else:
                require(clock-target_clock <= MAX_DELAY_NS, prefix + 'guard-to-drive target delay exceeds160ms')
            matched.append({'cmd_seq': row['cmd_seq'], 'receive_ns': clock,
                            'guard_decision_sequence': target_sequence,
                            'guard_source_ns': target_clock, 'guard_line': source['line'],
                            'exact_delivery_delay_ns': clock-target_clock,
                            'pre_initial_storage_prewarm': prewarm_command,
                            'output': [v, w]})
            cmd_seq = row['cmd_seq']
            latest = (cmd_seq, v, w, clock, target_sequence, target_clock)
            previous_target_sequence, previous_target_clock = target_sequence, target_clock
            pending_status = latest
        elif kind == 'status_publish':
            require(pending_status is not None, prefix + 'status publication has no pending received target')
            require(all(integer(row[key]) for key in (
                        'cmd_seq', 'target_decision_sequence', 'target_clock_ns')) and
                    number(row['desired_v']) and number(row['desired_w']),
                    prefix + 'invalid status publication field types')
            require(row['cmd_seq'] == latest[0] and row['desired_v'] == latest[1] and
                    row['desired_w'] == latest[2] and row['target_decision_sequence'] == latest[4] and
                    row['target_clock_ns'] == latest[5], prefix + 'status publication differs from latest target')
            expected_status = {'schema': 'mr3-drive-target-consumed-v1', 'epoch': epoch,
                               'robot': name, 'clock_ns': clock, 'decision_sequence': latest[4],
                               'source_clock_ns': latest[5], 'cmd_seq': latest[0],
                               'linear_x': latest[1], 'angular_z': latest[2]}
            require(type(row['status']) is dict and
                    all(integer(row['status'].get(key)) for key in (
                        'clock_ns', 'decision_sequence', 'source_clock_ns', 'cmd_seq')) and
                    number(row['status'].get('linear_x')) and number(row['status'].get('angular_z')),
                    prefix + 'invalid consumed status field types')
            require(row['status'] == expected_status and
                    row['scope'] == 'target_storage_and_status_publication',
                    prefix + 'status payload/scope differs from actual storage record')
            require(clock >= latest[3], prefix + 'status publication precedes target receipt')
            published_statuses[latest[4]] = dict(expected_status, trace_line=line)
            pending_status = None
        elif kind == 'target_rejected':
            require(clock < release or clock > final, prefix + 'rejected target during task')
            require(type(row.get('reason')) is str and 'raw_target' in row,
                    prefix + 'target rejection lacks raw provenance')
            require(all(integer(row.get(key)) for key in (
                        'retained_cmd_seq', 'retained_target_decision_sequence', 'retained_target_clock_ns')) and
                    (row['retained_cmd_seq'], row['retained_target_decision_sequence'],
                     row['retained_target_clock_ns']) == (latest[0], latest[4], latest[5]),
                    prefix + 'rejected target changes retained command identity')
        elif kind == 'actuation':
            require(pending_status is None, prefix + 'actuation interleaves uncompleted target callback')
            require(integer(row['actuation_seq']) and row['actuation_seq'] == act_seq + 1 and
                    integer(row['pair_index']) and row['pair_index'] == 0,
                    prefix + 'actuation sequence/pair')
            act_seq += 1
            require(integer(row['cmd_seq']) and number(row['desired_v']) and
                    number(row['desired_w']) and
                    (row['cmd_seq'], row['desired_v'], row['desired_w']) == latest[:3],
                    prefix + 'actuation does not consume locked latest received command')
            require(integer(row['target_decision_sequence']) and integer(row['target_clock_ns']) and
                    (row['target_decision_sequence'], row['target_clock_ns']) == latest[4:],
                    prefix + 'actuation target identity differs from locked latest received command')
            dt_ns, dt = row['dt_ns'], row['dt_sec']
            require(integer(dt_ns) and dt_ns > 0 and number(dt) and dt > 0 and
                    abs(dt - dt_ns / 1e9) <= MATH_TOL, prefix + 'invalid source dt')
            require(Fraction(dt_ns, 10**9) >= Fraction(1, 30),
                    prefix + 'not the configured30Hz physical-tick cadence')
            if previous_act is None and clock < release:
                require(0 <= clock-dt_ns <= marker_clock <= clock,
                        prefix + 'initial prerelease dt does not bracket configuration/reset')
            else:
                require(Fraction(dt_ns, 10**9) < Fraction(1, 30) + Fraction(step, 10**9),
                        prefix + 'not the configured30Hz physical-tick cadence')
            if previous_act is not None:
                require(clock - previous_act == dt_ns, prefix + 'dt differs from actual source successors')
            previous_act = clock
            require(number(row['max_acceleration_mps2']) and row['max_acceleration_mps2'] == 1.,
                    prefix + 'changed wheel acceleration')
            current = pair(row['current_rim_mps'], prefix + 'current rim')
            desired = pair(row['desired_rim_mps'], prefix + 'desired rim')
            applied = pair(row['applied_rim_mps'], prefix + 'applied rim')
            v, w = row['desired_v'], row['desired_w']
            transform = [v + w * .287 / 2, v - w * .287 / 2]
            require(all(abs(a-b) <= MATH_TOL for a, b in zip(desired, transform)),
                    prefix + 'body-to-RIGHT/LEFT desired rim transform')
            alpha = row['alpha']
            require(number(alpha) and 0 <= alpha <= 1, prefix + 'invalid common alpha')
            budget = fraction(1.) * fraction(dt)
            largest = max(abs(fraction(d)-fraction(c)) for c, d in zip(current, desired))
            nominal = Fraction(1) if largest <= budget else budget/largest
            require(fraction(alpha) <= nominal and abs(float(nominal)-alpha) <= MATH_TOL,
                    prefix + 'common alpha is not nominal fraction rounded inward')
            for c, d, a in zip(current, desired, applied):
                residual = abs(a - (c + alpha*(d-c)))
                max_math_residual = max(max_math_residual, residual)
                require(residual <= MATH_TOL, prefix + 'not one common-alpha convex step')
                require(min(fraction(c), fraction(d)) <= fraction(a) <= max(fraction(c), fraction(d)),
                        prefix + 'wheel instruction outside convex segment')
                delta = abs(fraction(a)-fraction(c))
                require(delta <= budget, prefix + 'wheel acceleration budget exceeded exactly')
                maximum_budget_ratio = max(maximum_budget_ratio, delta/budget)
            prewarm_anchor = (clock == release and initial_command_line is not None and
                              line < initial_command_line and latest[0] < initial_receipt['cmd_seq'] and
                              [v, w] == [0., 0.] and
                              guard_by_sequence.get(latest[4], {}).get('started') is False)
            if prewarm_anchor:
                prewarm_anchors.append({'line': line, 'source_ns': clock, 'cmd_seq': latest[0],
                                       'target_decision_sequence': latest[4],
                                       'initial_command_line': initial_command_line,
                                       'initial_cmd_seq': initial_receipt['cmd_seq'],
                                       'sampled_response_credit': False})
            if release <= clock <= final and not prewarm_anchor:
                require(latest[0] > 0 and 0 <= clock-latest[3] <= MAX_DELAY_NS,
                        prefix + 'latest actual received command missing/stale at actuation')
                require(0 <= clock-latest[5] <= MAX_DELAY_NS,
                        prefix + 'latest actual guard target missing/stale at actuation')
            actuation.append({'source_ns': clock, 'cmd_seq': row['cmd_seq'], 'dt_ns': dt_ns,
                              'target_decision_sequence': latest[4], 'target_clock_ns': latest[5],
                              'receive_age_ns': clock-latest[3], 'target_age_ns': clock-latest[5],
                              'line': line})
    require(pending_status is None, name + ': received target lacks status publication')
    require(bool(matched), name + ': no actual received final-guard command')
    before = [row for row in actuation if row['source_ns'] <= release]
    post = [row for row in actuation if release < row['source_ns'] <= final]
    covered = ([before[-1]] if before else []) + post
    require(bool(covered), name + ': missing release/final rim samples')
    require(abs(covered[0]['source_ns']-release) <= MAX_GAP_NS and
            0 <= final-covered[-1]['source_ns'] <= MAX_GAP_NS and
            all(b['source_ns']-a['source_ns'] <= MAX_GAP_NS for a, b in zip(covered, covered[1:])),
            name + ': incomplete100ms release/final/source coverage')
    require(terminal or bool(post), name + ': ordinary fixture lacks postrelease actuation')
    return {'passed': True, 'record_count': len(records), 'commands_received': cmd_seq,
            'actuations': act_seq, 'pre_release_resets': reset_count,
            'post_final_zero_rows_outside_task_credit': post_final_zero,
            'pre_initial_storage_zero_prewarm_anchors': prewarm_anchors,
            'pre_initial_storage_zero_prewarm_commands': prewarm_commands,
            'postrelease_actuation_samples': len(post), 'sampled_response_credit': bool(post),
            'terminal_protocol_only_exception': terminal and not post,
            'first_coverage_sample': covered[0], 'last_coverage_sample': covered[-1],
            'maximum_exact_wheel_budget_fraction': str(maximum_budget_ratio),
            'maximum_math_equation_residual': max_math_residual,
            'maximum_exact_guard_to_receive_ns': max(row['exact_delivery_delay_ns'] for row in matched),
            'maximum_task_exact_guard_to_receive_ns': max((row['exact_delivery_delay_ns'] for row in matched
                if release <= row['receive_ns'] <= final and not row['pre_initial_storage_prewarm']), default=None),
            'maximum_task_latest_receive_age_ns': max((row['receive_age_ns'] for row in post), default=None),
            'maximum_task_guard_target_age_ns': max((row['target_age_ns'] for row in post), default=None),
            'exact_received_targets': matched,
            '_published_statuses': published_statuses,
            'world_body_response_credit': False,
            'scope': 'Unique tagged guard decision to actual target storage/status publication and locked-latest rim instructions; status publication is not physical actuation ACK or world-body safety proof'}


def original_episode_directory(directory, declared, inputs, archived):
    actual = directory.resolve()
    if declared == actual:
        return actual
    require(archived, 'native episode audit directory does not equal actual episode')
    for ancestor in (actual, *actual.parents):
        manifest = ancestor/'manifest.json'
        if not manifest.exists() and not Path(str(manifest)+'.gz').exists():
            continue
        saved = inputs.json(manifest)
        if 'source' not in saved:
            continue
        source = Path(saved['source'])
        require(source.is_absolute(), 'archive manifest source is not absolute')
        restored = source/actual.relative_to(ancestor)
        require(restored == declared, 'archive source manifest does not restore original episode')
        return restored
    raise ValueError('archived selected episode lacks source manifest for original absolute paths')


def drive_phase(records, physics, epoch, release, guards, statuses, initial_motion, initial_receipts):
    """Bind actual subscription receipts to each permitted positive task advance."""
    physics_by_id = {row['request_id']: row for row in physics}
    require(len(physics_by_id) == len(physics), 'duplicate physics request identity')
    guard_by_sequence = {name: {row['decision_sequence']: row for row in guards[name]}
                         for name in ROBOTS}
    received, latest_received, consumed, permitted, completed = {}, {}, [], {}, {}
    previous_wall = -1

    def receipt(status, name):
        require(type(status) is dict and status.get('robot') == name and
                status.get('schema') == 'mr3-drive-target-consumed-v1' and status.get('epoch') == epoch,
                'worker drive receipt schema/epoch/robot mismatch')
        require(all(integer(status.get(key)) for key in (
                    'clock_ns', 'decision_sequence', 'source_clock_ns', 'cmd_seq')) and
                number(status.get('linear_x')) and number(status.get('angular_z')),
                'worker drive receipt field types')
        native = statuses[name].get(status['decision_sequence'])
        require(native is not None and status == {key: value for key, value in native.items()
                                                  if key != 'trace_line'},
                'worker drive receipt is not an actual published native storage status')
        return (name, status['decision_sequence'], status['cmd_seq'])

    def expected_bindings(expected, receipts):
        require(type(expected) is dict and expected.get('schema') == 'mr3-motion-safety-status-v1' and
                expected.get('epoch') == epoch and integer(expected.get('clock_ns')) and
                type(expected.get('ready')) is bool and
                expected.get('completion_scope') == 'publication_and_local_topic_receipt',
                'worker expected motion status schema/clock/scope')
        clock = expected['clock_ns']
        require(set(expected['decision_sequences']) == set(ROBOTS) and
                set(expected['outputs']) == set(ROBOTS) and set(receipts) == set(ROBOTS),
                'worker phase does not contain exact three target/receipt roles')
        for name in ROBOTS:
            sequence = expected['decision_sequences'][name]
            output = expected['outputs'][name]
            require(integer(sequence) and type(output) is dict and
                    set(output) == {'linear_x', 'angular_z'} and
                    number(output['linear_x']) and number(output['angular_z']),
                    'worker expected target field types')
            source = guard_by_sequence[name].get(sequence)
            require(source is not None and source['clock_ns'] == clock and
                    source['output'] == [output['linear_x'], output['angular_z']],
                    'worker expected target does not exactly bind guard decision')
            actual = receipts[name]
            key = receipt(actual, name)
            require(key in received and received[key] == actual,
                    'worker consumed receipt has no preceding actual subscription callback')
            require(latest_received.get(name) == actual,
                    'worker consumed old cached receipt after newer actual drive ACK')
            require(actual['clock_ns'] == actual['source_clock_ns'] == clock and
                    actual['decision_sequence'] == sequence and
                    actual['linear_x'] == output['linear_x'] and
                    actual['angular_z'] == output['angular_z'],
                    'worker consumed target is not exact same-clock/sequence/value')
        return clock

    for line, row in enumerate(records, 1):
        require(row['epoch'] == epoch and integer(row['wall_monotonic_ns']) and
                row['wall_monotonic_ns'] >= previous_wall and
                (row['worker_clock_ns'] is None or integer(row['worker_clock_ns'])) and
                (row['worker_physical_ns'] is None or integer(row['worker_physical_ns'])),
                f'worker drive phase line{line}: identity/clock order')
        previous_wall = row['wall_monotonic_ns']
        kind = row['kind']
        if kind == 'ack_received':
            status = row['ack']
            name = status['robot']
            require(name in ROBOTS and row.get('topic_robot') == name,
                    'worker drive receipt does not match subscribed topic robot')
            key = receipt(status, name)
            require(key not in received or received[key] == status,
                    'conflicting duplicate worker drive receipt')
            prior = latest_received.get(name)
            if prior is not None and prior != status:
                require(status['decision_sequence'] > prior['decision_sequence'] and
                        status['cmd_seq'] > prior['cmd_seq'] and
                        status['source_clock_ns'] >= prior['source_clock_ns'] and
                        status['clock_ns'] >= prior['clock_ns'],
                        'worker actual drive ACK sequence/source clock regressed')
            received[key] = status
            latest_received[name] = status
        elif kind == 'ack_consumed':
            clock = expected_bindings(row['expected_motion'], row['receipts'])
            require(row['worker_clock_ns'] == row['worker_physical_ns'] == clock,
                    'worker consumed target outside exact paused boundary')
            consumed.append((row['expected_motion'], row['receipts']))
        elif kind == 'advance_permitted':
            request = row['request_id']
            require(request in physics_by_id and request not in permitted and
                    integer(row['steps']) and row['steps'] > 0 and integer(row['start_time_ns']),
                    'worker advance has unknown/duplicate physics request')
            physics_row = physics_by_id[request]
            require(row['start_time_ns'] == physics_row['start_time_ns'] and
                    row['steps'] == physics_row['steps'] and
                    row['steps']*physics_row['step_ns'] <= 20_000_000,
                    'worker advance differs from actual physics request/20ms quantum')
            clock = expected_bindings(row['expected_motion'], row['receipts'])
            require(clock == row['start_time_ns'] and
                    row['worker_clock_ns'] == row['worker_physical_ns'] == clock and
                    (row['expected_motion'], row['receipts']) in consumed,
                    'physics advance has no preceding exact consumed target barrier')
            permitted[request] = {'line': line, 'clock_ns': clock}
        elif kind == 'physics_completed':
            physics_row = row['receipt']
            request = physics_row['request_id']
            require(request in physics_by_id and request not in completed and
                    physics_row == physics_by_id[request],
                    'worker physics completion differs from actual physical receipt')
            if physics_row['steps'] > 0 and physics_row['start_time_ns'] >= release:
                require(request in permitted, 'physics completed before actual target barrier permission')
            completed[request] = line
        else:
            raise ValueError('unknown worker drive phase kind: '+str(kind))
    task = [row for row in physics if row['steps'] > 0 and row['start_time_ns'] >= release]
    require(all(row['request_id'] in permitted and row['request_id'] in completed for row in task),
            'task/cleanup physics advance lacks exact actual target barrier/completion')
    require(all(request in completed for request in permitted), 'permitted physics request never completed')
    require(initial_motion.get('clock_ns') == release and
            any(json.dumps([motion, receipts], sort_keys=True, allow_nan=False) ==
                json.dumps([initial_motion, initial_receipts], sort_keys=True, allow_nan=False)
                for motion, receipts in consumed),
            'reset initial drive receipts were not actually consumed at exact release')
    return {'passed': True, 'records': len(records), 'actual_subscription_statuses': len(received),
            'consumed_barriers': len(consumed), 'positive_task_cleanup_advances': len(task),
            'permitted_advances': len(permitted), 'completed_physics_requests': len(completed),
            'scope': 'Actual target-storage subscription ACK before owned physics service request; no per-packet wheel-application ACK or world-body proof'}


def check_actual_spawn(directory, original, epoch, inputs):
    observed = {}
    text = inputs.raw(directory/'launch.log').decode()
    for line in text.splitlines():
        marker = 'MR3_ORDERED_SHUTDOWN '
        if marker not in line:
            continue
        clean = re.sub(r'\x1b\[[0-9;]*m', '', line.split(marker, 1)[1])
        row = json.loads(clean)
        if row.get('event') not in ('process_started', 'process_start'):
            continue
        argv = row.get('argv', [])
        if not any(Path(arg).name == 'spawn_entity.py' for arg in argv):
            continue
        require(row['epoch'] == epoch and '-file' in argv and '-entity' in argv,
                'actual spawn event lacks same-epoch file/robot declaration')
        name = argv[argv.index('-entity')+1]
        require(name in ROBOTS and name not in observed, 'actual spawn robot missing/duplicated')
        path = argv[argv.index('-file')+1]
        require(path == str(original/f'drive_model_{name}.sdf'),
                'actual spawn did not load the archived effective model')
        require('-robot_namespace' in argv and argv[argv.index('-robot_namespace')+1] == '/'+name,
                'actual driver spawn namespace mismatch')
        observed[name] = path
    require(set(observed) == set(ROBOTS), 'missing actual three-robot effective SDF spawn events')
    return observed


def audit_episode(directory, freeze, compiled, binary, inputs, old_model, archived=False):
    metadata = inputs.json(directory/'metadata.json')
    require(metadata['freeze'] == freeze, 'episode freeze mismatch')
    epoch = metadata['epoch']
    require((directory/'summary.json').exists() or (directory/'summary.json.gz').exists(),
            'episode not closed')
    inputs.json(directory/'summary.json')
    transitions = inputs.lines(directory/'transitions.jsonl')
    reset = next(transitions)
    require(reset['kind'] == 'reset' and reset['info']['epoch'] == epoch,
            'missing original same-epoch reset')
    release = reset['info']['release_time_ns']
    require(integer(release) and release >= 0, 'invalid exact reset release')
    steps = [{'info': {'dt': row['info']['dt'], 'reason': row['info'].get('reason')},
              'terminated': row['terminated'], 'truncated': row['truncated']}
             for row in transitions if row['kind'] == 'step']
    physics = list(inputs.lines(directory/'physics.jsonl'))
    final, tick = physics_bounds(physics, epoch, release)
    benchmark = inputs.json(directory.parent.parent/'benchmark_metadata.json')
    require(benchmark['freeze'] == freeze, 'benchmark freeze mismatch')
    terminal = terminal_fixture(benchmark, steps, freeze)
    require(terminal or bool(steps), 'ordinary fixture has no returned step/failed reset prefix')
    originals = [arg.split(':=', 1)[1] for arg in metadata['command']
                 if arg.startswith('mr3_audit_path:=')]
    require(len(originals) == 1 and bool(originals[0]), 'missing native audit directory declaration')
    original_directory = original_episode_directory(
        directory, Path(originals[0]).parent, inputs, archived)
    actual_spawn = check_actual_spawn(directory, original_directory, epoch, inputs)
    guards = guard_outputs(inputs.lines(directory/'motion_safety.jsonl'), epoch, release)
    publication_proof = target_publications(list(inputs.lines(directory/'drive_targets.jsonl')),
                                           guards, epoch)
    topology_proof = drive_topology(inputs.json(directory/'drive_topology.json'), epoch, release)
    robots = {}
    for name in ROBOTS:
        try:
            check_model(inputs.raw(directory/f'drive_model_{name}.sdf'), old_model, epoch, name,
                        original_directory)
            robots[name] = robot_audit(list(inputs.lines(directory/f'drive_{name}.jsonl')),
                                       guards[name], name, epoch, release, final, tick, compiled,
                                       binary, terminal, reset['info']['initial_drive_receipts'][name])
        except Exception as error:
            robots[name] = {'passed': False, 'error': repr(error), 'world_body_response_credit': False}
    phase = {'passed': False, 'error': 'native storage/actuation evidence failed before worker phase audit'}
    if all(row['passed'] for row in robots.values()):
        statuses = {name: robots[name]['_published_statuses'] for name in ROBOTS}
        try:
            phase = drive_phase(list(inputs.lines(directory/'drive_phase_worker.jsonl')),
                                physics, epoch, release, guards, statuses,
                                reset['info']['initial_motion_status'], reset['info']['initial_drive_receipts'])
            require(reset['info']['drive_phase_protocol'] == 'mr3-drive-target-consumed-v1',
                    'reset drive protocol mismatch')
        except Exception as error:
            phase = {'passed': False, 'error': repr(error)}
    for row in robots.values():
        row.pop('_published_statuses', None)
    return {'directory': str(directory), 'epoch': epoch, 'release_ns': release, 'final_physics_ns': final,
            'physical_tick_ns': tick, 'returned_steps': len(steps), 'exact_terminal_fixture': terminal,
            'original_episode_directory': str(original_directory),
            'actual_spawn_model_files': actual_spawn,
            'passed': all(row['passed'] for row in robots.values()) and phase['passed'],
            'robots': robots, 'driver_consumption_phase': phase,
            'target_publication_ledger': publication_proof, 'native_drive_topology': topology_proof,
            'world_body_response_credit': False}


def review(directory, freeze, proof_path, archived=False):
    inputs = Inputs()
    compiled = source_bindings(freeze)
    proof = inputs.json(proof_path)
    binary = binary_binding(proof, freeze, compiled, inputs, archived)
    old_model = git_blob(BASELINE, MODEL)
    # A changed frozen template is rejected as well as any changed effective copy.
    require(physical_model(ET.fromstring(git_blob(freeze, MODEL))) ==
            physical_model(ET.fromstring(old_model)), 'frozen model changes original physical model')
    directory = Path(directory)
    episodes = ([directory] if (directory/'metadata.json').exists() or
                (directory/'metadata.json.gz').exists() else sorted(directory.glob('worker*/episode*')))
    require(bool(episodes), 'no native episode directories')
    results = []
    for episode in episodes:
        try:
            results.append(audit_episode(episode, freeze, compiled, binary, inputs, old_model, archived))
        except Exception as error:
            results.append({'directory': str(episode), 'passed': False, 'error': repr(error),
                            'world_body_response_credit': False})
    inputs.verify_unchanged()
    return {'schema': 'mr3-independent-drive-trace-review-v4', 'freeze': freeze,
            'passed': all(row['passed'] for row in results), 'episodes': results, 'binary': binary,
            'inputs': inputs.bindings, 'compiled_git_sources': {
                key: {'path': SOURCE_PATHS[key], 'sha256': value} for key, value in compiled.items()},
            'math_equation_absolute_rounding_tolerance': MATH_TOL,
            'wheel_budget_comparison': 'Fraction of exact binary64 maxa1*dt_sec; no epsilon',
            'world_body_response_credit': False,
            'scope': 'Independent driver receipt/provenance and paired-rim instruction audit only. Existing raw whole-body/angular/acceleration, activity, contact, clock and closure gates remain mandatory. No actor or truth imported.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--binary-proof', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--archived', action='store_true')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output exists; previous failures cannot be overwritten')
    try:
        result = review(args.directory, args.freeze, args.binary_proof, args.archived)
    except Exception as error:
        result = {'schema': 'mr3-independent-drive-trace-review-v4', 'passed': False,
                  'freeze': args.freeze, 'error': repr(error), 'world_body_response_credit': False}
    result['script_sha256'] = sha(Path(__file__).read_bytes())
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
