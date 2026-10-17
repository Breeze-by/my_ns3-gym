"""Read-only independent native terminal review; writes only /tmp output."""
import hashlib
import math
import json
from pathlib import Path
import subprocess
from mr3_v2_motion_review import review as review_motion
from mr3_v2_physical_review import review as review_physical

ROOT = Path('/home/zhuyulab/ns3-workspace')
BASE = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v2_reset'
FREEZE = '96c201e0e258bd0fe192fc03c6716fc694b7a9b7'
OUT = Path('/tmp/mr3_p2a0_v2_reset_independent_safety_review.json')
result = {'schema': 'mr3-p2a0-independent-reset-safety-review-v2',
          'freeze': FREEZE, 'directory': str(BASE), 'errors': [], 'episodes': [],
          'scope': 'read-only native closure, 18-source frozen health, task failure/truncation distinction and diagnostic isolation; no training/task-success credit'}

def require(ok, message):
    if not ok:
        result['errors'].append(message)

def read(path):
    return json.loads(path.read_text())

def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]

def identity(pid):
    try:
        raw = (Path('/proc') / str(pid) / 'stat').read_text()
    except FileNotFoundError:
        return None
    tail = raw[raw.rfind(')') + 2:].split()
    return {'state': tail[0], 'start_ticks': int(tail[19])}

def contains_key(value, keys):
    if isinstance(value, dict):
        return bool(set(value) & keys) or any(contains_key(v, keys) for v in value.values())
    if isinstance(value, list):
        return any(contains_key(v, keys) for v in value)
    return False

metadata = read(BASE / 'benchmark_metadata.json')
require(metadata['freeze'] == FREEZE and metadata['workers'] == 2
        and metadata['robots_per_worker'] == 3 and not metadata['terminal_probe'], 'benchmark binding')
preflight = read(ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v2/source_preflight_v1.json')
require(preflight['passed'] and preflight['freeze'] == FREEZE, 'original native start source binding')
result['source_preflight_scope'] = 'frozen Git bytes bind to native-start preflight; worktree may already contain subsequent v3 repairs'
result['source_proof'] = {}
for path in ['ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py',
             'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py',
             'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py',
             'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/observation.py']:
    frozen = subprocess.run(['rtk', 'proxy', 'git', 'show', FREEZE + ':' + path], cwd=ROOT,
                            check=True, stdout=subprocess.PIPE).stdout
    current = (ROOT / path).read_bytes()
    require(hashlib.sha256(frozen).hexdigest() == preflight['source_bindings'][path]['sha256'], 'frozen/native start source differs: ' + path)
    result['source_proof'][path] = {'sha256': hashlib.sha256(frozen).hexdigest(),
                                  'worktree_identical': current == frozen}
dirs = sorted(BASE.glob('worker*/episode*'))
require(len(dirs) == 2, 'stopped v2 should retain its two actual reset episodes')
owned = {}
for index, directory in enumerate(dirs):
    label = str(directory.relative_to(BASE))
    for name in ['summary.json', 'supervisor_shutdown.json', 'native_stop.json']:
        require((directory / name).exists(), f'{label}: missing {name}')
    if not all((directory / x).exists() for x in ['summary.json', 'supervisor_shutdown.json', 'native_stop.json']):
        continue
    meta, summary = read(directory / 'metadata.json'), read(directory / 'summary.json')
    supervisor, stop = read(directory / 'supervisor_shutdown.json'), read(directory / 'native_stop.json')
    task = read(directory / (meta['epoch'] + '.json'))
    nav = read(directory / 'nav2_shutdown.json')
    trans = rows(directory / 'transitions.jsonl')
    steps = [row for row in trans if row['kind'] == 'step']
    log = (directory / 'launch.log').read_text()
    ordered = [(n, json.loads(line.split('MR3_ORDERED_SHUTDOWN ', 1)[1]))
               for n, line in enumerate(log.splitlines(), 1) if 'MR3_ORDERED_SHUTDOWN {' in line]
    exits = [(n, row) for n, row in ordered if row['event'] == 'process_exited']
    signals = [(n, row) for n, row in ordered if row['event'] == 'signal']
    complete = [row for _, row in ordered if row['event'] == 'complete']
    require(meta['freeze'] == FREEZE, f'{label}: worker freeze')
    require(summary['launch_returncode'] == 0 and not summary['native_failures'],
            f'{label}: strict native worker closure')
    require(summary['failures'] == ([task['control_failure']] if task['control_failure'] else []),
            f'{label}: original task failure retained distinctly from native failures')
    require(supervisor['worker_returncode'] == 0 and not supervisor['forced_shutdown']
            and not supervisor['failed_sample'] and not supervisor['remaining_owned_processes']
            and not supervisor['remaining_owned_zombies'], f'{label}: supervisor cleanup')
    require(stop['returncode'] == 0 and stop['server_clean_exit_recorded'], f'{label}: native stop')
    require(len(complete) == 1 and complete[0]['server_returncode'] == 0
            and complete[0]['stop_cli_returncode'] == 0, f'{label}: ordered complete')
    require(all(row['returncode'] == 0 for _, row in exits), f'{label}: nonzero process exit')
    require(not any(row['event'] in {'error', 'failed'} for _, row in ordered), f'{label}: ordered error')
    for signal_index, (line, row) in enumerate(signals):
        require(row['signal'] == 'SIGINT', f'{label}: non-SIGINT controlled shutdown')
        paired = [(n, event) for n, event in exits
                  if event['pid'] == row['pid'] and event.get('signal_sequence') == row['signal_sequence']]
        require(len(paired) == 1 and paired[0][0] > line, f'{label}: signal exit pairing')
        if signal_index + 1 < len(signals) and paired:
            require(paired[0][0] < signals[signal_index + 1][0], f'{label}: nonserial ROS stop')
    slam = [(n, row) for n, row in exits if row['process_name'].startswith('multirobot_slam_toolbox_node-')]
    unregister = [(n, line) for n, line in enumerate(log.splitlines(), 1)
                  if 'Unregistering sensor:' in line]
    require(len(slam) == 3 and len(unregister) == 3, f'{label}: three SLAM destructor/unregister witnesses')
    require(not any(token in log for token in ['karto::Exception', 'terminate called', "sending signal 'SIGKILL'", "sending signal 'SIGTERM'",
                                             'MR3_GAZEBO_NATIVE_STOP_ERROR']), f'{label}: native abort/forced marker')
    finalized = [(robot['robot'], state['node'], state['state'])
                 for robot in nav['robots'] for state in robot['states']]
    require(nav['success'] and not nav['failures'] and len(finalized) == 18
            and all(x[2] == {'id': 4, 'label': 'finalized'} for x in finalized), f'{label}: 18 Nav2 finalized')
    require(summary['closed']['pending_goal_count'] == 0, f'{label}: goal ownership')
    monitor = task['contact_monitor_summary']
    components = [(name, part, value) for name, robot in monitor['components'].items()
                  for part, value in robot.items()]
    require(task['collision_monitoring_fresh'] and task['collision_monitoring_active']
            and task['collision_events'] == 0 and monitor['fresh'] and not monitor['ever_unhealthy']
            and not monitor['latched_issues'] and len(components) == 18, f'{label}: contact summary')
    require(all(value['accepted_message_count'] > 0 and not value['health_reason']
                and value['source_age_sec'] <= .5 and value['receipt_age_sec'] <= .5
                for _, _, value in components), f'{label}: individual component health')
    require(1 <= len(steps) <= 16, f'{label}: original returned step count')
    expected = steps[-1]['info']['dt']
    require(0 < expected <= 1 and steps[-1]['info']['physical_dt'] == expected,
            f'{label}: real final interval')
    diag = task.get('control_failure_truth_diagnostic')
    peer_review = None
    if diag is not None:
        require(diag['latest_model_states']['source_stamp_missing']
                and set(diag['latest_model_states']['poses']) == {'tb1', 'tb2', 'tb3'}, f'{label}: truth receipt scope')
    if task['control_failure'] and json.loads(task['control_failure']).get('reason') == 'peer_body_envelopes_overlap':
        failure = json.loads(task['control_failure'])
        require(failure['reason'] == 'peer_body_envelopes_overlap', f'{label}: unexpected failure reason')
        evidence = failure['diagnostic']
        require(task['termination_reason'] == 'navigation_failure' and steps[-1]['terminated']
                and not task['navigation_protocol_closed'], f'{label}: preserve genuine safety task failure')
        def yaw(q):
            return math.atan2(2 * (q['w'] * q['z'] + q['x'] * q['y']),
                              1 - 2 * (q['y'] * q['y'] + q['z'] * q['z']))
        actual = {}
        for name, data in evidence['received_inputs'].items():
            angle = yaw(data['tf_rotation'])
            x, y = data['odom_position']['x'], data['odom_position']['y']
            computed = {'x': data['tf_translation']['x'] + math.cos(angle)*x - math.sin(angle)*y,
                        'y': data['tf_translation']['y'] + math.sin(angle)*x + math.cos(angle)*y,
                        'yaw': yaw(data['odom_orientation']) + angle}
            require(all(math.isclose(value, data['estimated_map_pose'][key], abs_tol=1e-12)
                        for key, value in computed.items()), f'{label}: exact received pose reconstruction {name}')
            require(0 <= data['odom_source_age_sec'] <= .5 and 0 <= data['tf_source_age_sec'] <= .5,
                    f'{label}: received input freshness {name}')
            require(math.isclose(data['tf_validity_stamp_sec'] - evidence['tf_source_lead_sec'],
                                 data['tf_source_stamp_sec'], abs_tol=1e-12), f'{label}: tf source lead {name}')
            actual[name] = computed
        pair_rows = []
        for pair in evidence['pairs']:
            a, b = pair['robots']
            computed_distance = math.hypot(actual[a]['x'] - actual[b]['x'], actual[a]['y'] - actual[b]['y'])
            require(computed_distance == pair['centre_distance_m'] and computed_distance < pair['threshold_m'] == .5,
                    f'{label}: exact strict overlap pair reconstruction')
            truth = diag['latest_model_states']['poses']
            physical_distance = math.hypot(truth[a]['position']['x'] - truth[b]['position']['x'],
                                           truth[a]['position']['y'] - truth[b]['position']['y'])
            pair_rows.append({'robots': [a,b], 'recomputed_received_distance_m': computed_distance,
                              'physical_cache_distance_m': physical_distance})
        peer_review = {'received_inputs_recomputed': True, 'pairs': pair_rows,
                       'observation_sim_time_sec': evidence['observation_sim_time_sec'],
                       'failure_received_sim_time_sec': diag['failure_received_sim_time_sec'],
                       'physical_cache_received_sim_time_sec': diag['latest_model_states']['received_sim_time_sec'],
                       'physical_cache_source_stamp_missing': True,
                       'genuine_task_failure_preserved': True, 'evidence': evidence}
    forbidden = {'control_failure_truth_diagnostic', 'latest_model_state_diagnostic', 'latest_model_states'}
    require(not any(contains_key(row['snapshot'], forbidden) or
                    contains_key(row['info'].get('reward_diagnostics', {}), forbidden)
                    for row in trans), f'{label}: truth diagnostic in actor/reward')
    phase = rows(directory / 'evaluator_phase_worker.jsonl')
    acks = [row['ack'] for row in phase if row['kind'] == 'ack_consumed']
    effective_end = steps[-1]['info']['reward_diagnostics']['effective_step_end']
    require(acks[-1]['evaluator_clock_ns'] == round(effective_end * 1e9), f'{label}: final phase/effective boundary')
    terminal_events = [row for row in rows(directory / 'adapter.jsonl')
                       if row['kind'] in {'task_terminal_received', 'task_terminal'}]
    if steps[-1]['terminated']:
        require(acks[-1]['status'] == 'TERMINAL' and acks[-1]['terminal']['end_sim_time_sec'] == effective_end,
                f'{label}: task terminal ACK')
        require(len(terminal_events) == 2 and all(set(row['payload']) == {
            'epoch', 'end_sim_time_sec', 'termination_reason'}
            and row['payload']['end_sim_time_sec'] == task['end_sim_time_sec']
            for row in terminal_events), f'{label}: scalar-only terminal notice')
    else:
        require(acks[-1]['status'] == 'LIVE' and acks[-1]['terminal'] is None
                and task['termination_reason'] == 'training_external_truncation'
                and task['navigation_protocol_closed'] and not terminal_events,
                f'{label}: external cut remains distinct from task failure')
    for item in supervisor['owned_processes_seen']:
        owned[(item['pid'], item['start_ticks'])] = item
    motion = review_motion(directory, meta, trans, require)
    physical = review_physical(directory)
    final_activity = {r['name']: r['activity'] for r in trans[-1]['snapshot']['robots']}
    raw_states = [r for r in rows(directory / 'adapter.jsonl') if r['kind'] == 'state_update']
    activity_missing = {name: sum(r['payload']['robots'][i].get('odometry') is None for r in raw_states) for i,name in enumerate(('tb1','tb2','tb3'))}
    result['episodes'].append({'directory': str(directory), 'epoch': meta['epoch'], 'motion': motion, 'physical': physical, 'final_actor_activity': final_activity, 'raw_state_updates': len(raw_states), 'raw_odom_missing_counts': activity_missing,
        'task_terminal': task['termination_reason'], 'frozen_navigation_protocol_closed': task['navigation_protocol_closed'],
        'dt_last': expected, 'command_last_present': steps[-1]['info'].get('command') is not None,
        'api_steps': len(steps), 'script_decisions': sum(row['info'].get('command') is not None for row in steps),
        'contact_components': len(components), 'contact_fresh': monitor['fresh'], 'collision_events': task['collision_events'],
        'nav2_finalized': len(finalized), 'slam_exit_witnesses': slam, 'slam_unregister_witnesses': unregister,
        'serial_ros_signals': len(signals), 'ordered_complete': complete[0] if complete else None,
        'truth_diagnostic': diag, 'peer_failure_review': peer_review, 'task_success': task['success'],
        'original_worker_task_failures': summary['failures'], 'original_native_failures': summary['native_failures'],
        'artifact_sha256': {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
            for name in ['metadata.json', 'summary.json', 'supervisor_shutdown.json', 'native_stop.json',
                         'nav2_shutdown.json', 'transitions.jsonl', 'launch.log', meta['epoch'] + '.json']}})
result['owned_identity_absence'] = []
for (pid, start), saved in sorted(owned.items()):
    current = identity(pid)
    same = current is not None and current['start_ticks'] == start
    require(not same, f'owned process still exists: {pid}/{start}')
    result['owned_identity_absence'].append({'pid': pid, 'start_ticks': start, 'current': current,
                                             'same_owned_identity_exists': same})
result['owned_identity_count'] = len(owned)
result['task_failure_count'] = sum(x['task_terminal'] == 'navigation_failure' for x in result['episodes'])
result['external_truncation_count'] = sum(x['task_terminal'] == 'training_external_truncation' for x in result['episodes'])
result['native_closure_passed'] = not result['errors'] and len(result['episodes']) == 2
result['passed'] = False
result['preparation_errors'] = ['declared eight-episode matrix stopped after two actual episodes', 'all received activity unavailable because broadcast state stripped original odometry; each robot movement criterion unproven']
result['benchmark_parent_captured'] = read(Path('/tmp/mr3_p2a0_v2_reset_parent_identity_captured.json'))
for saved in result['benchmark_parent_captured']:
    current = identity(saved['pid'])
    same = current is not None and current['start_ticks'] == saved['start_ticks']
    require(not same, 'benchmark parent still exists')
    result['owned_identity_absence'].append({'pid': saved['pid'], 'start_ticks': saved['start_ticks'], 'current': current, 'same_owned_identity_exists': same})
result['owned_identity_count'] = len(result['owned_identity_absence'])
OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print(json.dumps({'passed': result['passed'], 'native_closure_passed': result['native_closure_passed'], 'errors': result['errors'], 'output': str(OUT),
                  'episodes': len(result['episodes']), 'owned_identity_count': len(owned)}, ensure_ascii=False))
