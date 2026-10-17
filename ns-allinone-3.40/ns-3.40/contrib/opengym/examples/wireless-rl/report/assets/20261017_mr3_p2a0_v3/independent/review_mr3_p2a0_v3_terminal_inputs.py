"""Read-only scalar/contact/received-activity native terminal review."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
BASE = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v3_terminal'
LEARNER = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
FREEZE = 'f9312e1ed245fb93af50614fd34c960870edb78d'
OUT = Path('/tmp/mr3_p2a0_v3_terminal_inputs_independent_review.json')
sys.path.insert(0, str(LEARNER))
from mr3_learning.audit_activity import audit_episode, audit_probe_activity


def read(path):
    return json.loads(path.read_text())


def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


result = {'schema': 'mr3-p2a0-v3-independent-terminal-input-review-v1',
          'freeze': FREEZE, 'directory': str(BASE), 'errors': [], 'episodes': [],
          'scope': 'actual received-odom availability, scalar terminal/ACK/contact/protocol evidence; '
                   'terminal failure injection, no 95%, movement, braking or PPO credit'}


def require(ok, message):
    if not ok:
        result['errors'].append(message)


def forbidden(value):
    if isinstance(value, dict):
        if set(value) & {'control_failure_truth_diagnostic', 'latest_model_state_diagnostic',
                         'latest_model_states'}:
            return True
        return any(forbidden(item) for item in value.values())
    return isinstance(value, list) and any(forbidden(item) for item in value)


metadata = read(BASE / 'benchmark_metadata.json')
require(metadata['freeze'] == FREEZE and metadata['workers'] == 1
        and metadata['robots_per_worker'] == 3 and metadata['terminal_probe'], 'benchmark identity')
paths = [
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/' + name
    for name in ('mr3_information.py', 'mr3_activity.py', 'mr3_adapter.py', 'mr3_protocol.py',
                 'mr3_motion_safety.py', 'motion_safety.py')]
paths.append('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
             'mr3_learning/audit_activity.py')
result['source_proof'] = {}
for relative in paths:
    raw = subprocess.check_output(['rtk', 'proxy', 'git', 'show', FREEZE + ':' + relative], cwd=ROOT)
    current = (ROOT / relative).read_bytes()
    require(raw == current, 'review worktree differs from native freeze: ' + relative)
    result['source_proof'][relative] = hashlib.sha256(raw).hexdigest()
directories = sorted(BASE.glob('worker*/episode*'))
require(len(directories) == 2, 'two actual terminal episodes required')
for index, directory in enumerate(directories):
    label = directory.name
    for name in ('summary.json', 'supervisor_shutdown.json', 'native_stop.json'):
        require((directory / name).exists(), label + ': not fully closed: ' + name)
    if not all((directory / name).exists() for name in
               ('summary.json', 'supervisor_shutdown.json', 'native_stop.json')):
        continue
    meta = read(directory / 'metadata.json')
    task = read(directory / (meta['epoch'] + '.json'))
    trans, adapter = rows(directory / 'transitions.jsonl'), rows(directory / 'adapter.jsonl')
    steps = [row for row in trans if row['kind'] == 'step']
    release = trans[0]['info']['release_time_ns']
    summary = read(directory / 'summary.json')
    supervisor = read(directory / 'supervisor_shutdown.json')
    require(meta['freeze'] == FREEZE and supervisor['worker_returncode'] == 0
            and not supervisor['forced_shutdown'] and not supervisor['failed_sample']
            and not supervisor['remaining_owned_processes']
            and not supervisor['remaining_owned_zombies'], label + ': strict supervised closure')
    require(summary['closed']['pending_goal_count'] == 0
            and summary['closed']['epoch'] == meta['epoch'], label + ': epoch ownership closure')
    integrity = audit_episode(directory)
    require(integrity['passed'] and integrity['integrity_passed']
            and integrity['availability_passed'], label + ': real received activity unavailable')
    initial = {r['name']: r['activity'] for r in trans[0]['snapshot']['robots']}
    valid_raw, anchors = dict.fromkeys(('tb1', 'tb2', 'tb3'), 0), {}
    for row in adapter:
        if row['kind'] != 'state_update':
            continue
        for robot in row['payload']['robots']:
            if robot['valid'] is not True:
                continue
            name, odom = robot['name'], robot.get('odometry')
            require(isinstance(odom, dict), label + ': valid state stripped original odometry')
            if not isinstance(odom, dict):
                continue
            stamp = odom['header']['stamp']
            source_ns = stamp['sec'] * 1000000000 + stamp['nanosec']
            require(source_ns == round(robot['odom_source_stamp'] * 1e9)
                    and bool(odom['header']['frame_id']) and bool(odom['child_frame_id']),
                    label + ': original received odom header/frame binding')
            valid_raw[name] += 1
            if source_ns >= release:
                anchors.setdefault(name, {'source_ns': source_ns,
                    'state_sequence': row['payload']['sequence'], 'original_header': odom['header'],
                    'child_frame_id': odom['child_frame_id']})
    require(all(valid_raw.values()) and len(anchors) == 3, label + ': three postrelease raw anchors')
    movement_gate_rejection = None
    try:
        audit_probe_activity(directory)
    except ValueError as error:
        movement_gate_rejection = str(error)
    require(movement_gate_rejection is not None, label + ': zero-motion terminal falsely passed probe gate')
    require(len(steps) == 4 and steps[-1]['terminated'] and not steps[-1]['truncated'],
            label + ': true terminal API result')
    expected_dt = .02 if index == 0 else 0.
    require(steps[-1]['info']['dt'] == expected_dt
            and steps[-1]['info']['physical_dt'] == expected_dt
            and (steps[-1]['info'].get('command') is not None) == (index == 0),
            label + ': short/zero boundary and command submission')
    if index == 1:
        require(steps[-1]['snapshot']['digest'] == steps[-2]['snapshot']['digest'],
                label + ': zero tail did not reuse exact observation')
    terminal = [row for row in adapter if row['kind'] in
                ('task_terminal_received', 'task_terminal')]
    require(len(terminal) == 2 and all(set(row['payload']) == {
        'epoch', 'end_sim_time_sec', 'termination_reason'}
        and row['payload']['epoch'] == meta['epoch']
        and row['payload']['end_sim_time_sec'] == task['end_sim_time_sec'] for row in terminal),
        label + ': scalar-only epoch terminal propagation')
    acks = [row['ack'] for row in rows(directory / 'evaluator_phase_worker.jsonl')
            if row['kind'] == 'ack_consumed']
    require(acks[-1]['evaluator_clock_ns'] == round(task['end_sim_time_sec'] * 1e9),
            label + ': final evaluator ACK clock')
    if index == 0:
        require(acks[-1]['status'] == 'TERMINAL'
                and acks[-1]['terminal']['end_sim_time_sec'] == task['end_sim_time_sec'],
                label + ': advancing terminal ACK')
    else:
        injection = rows(directory / 'diagnostic_failure.jsonl')
        require(acks[-1]['status'] == 'LIVE' and acks[-1]['terminal'] is None
                and injection[-1]['kind'] == 'terminal_received'
                and injection[-1]['end_sim_time_sec'] == task['end_sim_time_sec'],
                label + ': zero tail honest already-ACKed injection')
    monitor = task['contact_monitor_summary']
    components = [value for robot in monitor['components'].values() for value in robot.values()]
    require(len(components) == 18 and monitor['fresh'] and not monitor['ever_unhealthy']
            and not monitor['latched_issues'] and task['collision_monitoring_active']
            and task['collision_monitoring_fresh'] and task['collision_events'] == 0,
            label + ': sustained 18-component health')
    require(all(value['accepted_message_count'] > 0 and not value['health_reason']
                and value['source_age_sec'] <= .5 and value['receipt_age_sec'] <= .5
                for value in components), label + ': individual component source/receipt freshness')
    motion = rows(directory / 'motion_safety.jsonl')
    require(not any(forbidden(row['snapshot']) or forbidden(row['info'].get('reward_diagnostics', {}))
                    for row in trans) and not forbidden(motion), label + ': truth crossed input boundary')
    result['episodes'].append({'epoch': meta['epoch'], 'api_steps': len(steps),
        'commands': sum(row['info'].get('command') is not None for row in steps),
        'last_dt': expected_dt, 'task_termination': task['termination_reason'],
        'initial_activity': initial, 'postrelease_anchors': anchors,
        'valid_original_odom_records': valid_raw, 'activity_integrity': integrity,
        'strict_probe_rejection': movement_gate_rejection,
        'contact_components': len(components), 'all_contact_fresh': monitor['fresh'],
        'collision_events': task['collision_events'], 'goal_ownership_closed': summary['closed'],
        'frozen_task_navigation_closed': task['navigation_protocol_closed'],
        'artifact_sha256': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ('metadata.json', 'transitions.jsonl', 'adapter.jsonl',
                         'summary.json', 'supervisor_shutdown.json', meta['epoch'] + '.json')}})
result['passed'] = not result['errors'] and len(result['episodes']) == 2
OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print(json.dumps({'passed': result['passed'], 'errors': result['errors'], 'output': str(OUT)}))
