import collections
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
RUN = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v8_terminal'
EP = RUN / 'worker0/episode001_open_101'
FREEZE = 'd41485dfd93797026316806916e127eb5101f3b8'
OUT = Path('/tmp/mr3_p2a0_v8_terminal_e1_safety_source_forensics_v1.json')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def rows(path):
    return [(i, json.loads(line)) for i, line in enumerate(path.read_text().splitlines(), 1)]

def ns(value):
    return int(round(value * 1_000_000_000))

inputs = [EP / x for x in ('metadata.json', 'summary.json', 'motion_safety.jsonl',
                          'adapter.jsonl', 'physics.jsonl', 'transitions.jsonl',
                          'launch.log', 'native_stop.json', 'nav2_shutdown.json',
                          'supervisor_shutdown.json')]
inputs.append(RUN / 'benchmark_summary.json')
bindings = {str(p): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in inputs}
meta = json.loads((EP / 'metadata.json').read_text())
assert meta['freeze'] == FREEZE
motion = rows(EP / 'motion_safety.jsonl')
adapter = rows(EP / 'adapter.jsonl')
counts = collections.Counter(row['kind'] for _, row in motion)
selected = []
callback = {}
for line, row in motion:
    kind, value = row['kind'], row['payload']
    if kind in ('own_odom', 'own_tf'):
        stamp = value['message']['header']['stamp']
        stamp_ns = stamp['sec'] * 1_000_000_000 + stamp['nanosec']
        callback[(value['robot'], kind)] = {
            'line': line, 'record_sequence': row['record_sequence'],
            'callback_clock_ns': ns(row['sim_time_sec']), 'header_stamp_ns': stamp_ns,
            'header_minus_callback_ns': stamp_ns - ns(row['sim_time_sec'])}
    take = (kind in ('release', 'failure', 'settled_turn_model_failure', 'terminal',
                     'stop_request') or
            (kind == 'received_states' and 67.9 <= row['sim_time_sec'] <= 68.11) or
            (kind == 'decision' and 68.04 <= row['sim_time_sec'] <= 68.11))
    if not take:
        continue
    item = {'line': line, 'row': row}
    if kind == 'received_states':
        item['raw_own_callbacks_prior_to_received'] = {
            robot + ':' + source: state for (robot, source), state in callback.items()}
    if kind == 'decision':
        def ages(state):
            return {key: ns(row['sim_time_sec']) - ns(state[key])
                    for key in ('source_stamp', 'odom_source_stamp', 'tf_source_stamp')}
        item['own_ages_ns'] = ages(value['own_state'])
        item['received_peer_ages_ns'] = {key: ages(state)
                                        for key, state in value['received_peers'].items()}
        item['states_with_age_gate_failures'] = {
            key: {stamp: age for stamp, age in ages(state).items()
                  if not 0 <= age <= 500_000_000}
            for key, state in value['received_peers'].items()
            if any(not 0 <= age <= 500_000_000 for age in ages(state).values())}
    selected.append(item)
selected_adapter = [{'line': line, 'row': row} for line, row in adapter
                    if row['kind'] in ('task_start', 'safety_stop', 'task_terminal_received',
                                       'task_terminal', 'task_stopped')]
source_paths = [ROOT / ('ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/'
                       'multi_robot_exploration/' + name + '.py')
                for name in ('mr3_information', 'motion_safety', 'mr3_motion_safety',
                             'peer_obstacles')]
source_bindings = []
for path in source_paths:
    rel = str(path.relative_to(ROOT))
    frozen = subprocess.run(['git', 'show', FREEZE + ':' + rel], cwd=ROOT,
                            capture_output=True, check=True).stdout
    assert hashlib.sha256(frozen).hexdigest() == sha(path)
    source_bindings.append({'path': str(path), 'sha256': sha(path),
                            'matches_freeze_git_bytes': True})
assert counts['settled_turn_model_failure'] == 0
activations = [row for _, row in motion if row['kind'] == 'decision' and
               (row['payload']['decision'].get('reason') == 'settled_turn_drift_reserve' or
                row['payload']['decision'].get('component_filter', {})
                .get('rotation_check', {}).get('reason') == 'settled_turn_drift_reserve')]
assert not activations
bad = [item for item in selected if item['row']['kind'] == 'decision' and
       item['row']['payload']['clock_ns'] == 68_100_000_000]
assert len(bad) == 3 and all(not item['row']['payload']['ready'] for item in bad)
fresh = [item for item in selected if item['row']['kind'] == 'received_states' and
         ns(item['row']['sim_time_sec']) == 68_100_000_000]
assert len(fresh) == 1
assert all(item['row']['record_sequence'] < fresh[0]['row']['record_sequence'] for item in bad)
assert any(item['states_with_age_gate_failures'].get('tb3', {}).get('source_stamp')
           == 520_000_000 for item in bad)
findings = {
    'overall_terminal_stage_passed': False,
    'premature_first_step_dt_ns': 60_000_000,
    'observed_trigger': 'received tb3 state source67.58 at safety clock68.10; age.52 exceeds unchanged.5 gate',
    'same_clock_new_delivery_record_sequence': fresh[0]['row']['record_sequence'],
    'old_input_decision_record_sequences': [item['row']['record_sequence'] for item in bad],
    'settled_turn_activation_count': len(activations),
    'settled_turn_model_failure_count': counts['settled_turn_model_failure'],
    'settled_turn_new_tracker_causal_failure_established': False,
    'proven': [
        'At68.08 old tb3 received source age.50 remained eligible; at68.10 age.52 was rejected.',
        'Three readyFalse decisions preceded same-clock fresh received_states45433.',
        'No settled_turn grant or model failure occurred.',
        'Adapter reports peer_obstacles peer_state_unavailable then motion_safety unavailable.',
        'Raw motion subscriber saw odometry headers ahead of its callback clock, including tb3 68.002 at68.00.'
    ],
    'inference_not_proven': [
        'Information producer may skip a state when latest raw odometry is future: receive_local_odom overwrites latest; publish_states skips when max source>now.',
        'Motion subscriber callback order does not prove the information producer received identical messages in identical order; producer per-callback trace is absent.'
    ],
    'criteria_unchanged': True,
    'scope': 'read-only causal evidence; formal settled integrity PASS/no-use does not cover terminal FAIL; no source or gate edits; no native retry'
}
for path, expected in bindings.items():
    assert sha(Path(path)) == expected['sha256']
result = {'schema': 'mr3-v8-terminal-source-forensics-v1', 'freeze': FREEZE,
          'episode': str(EP), 'epoch': meta['epoch'], 'inputs': bindings,
          'source_bindings': source_bindings, 'motion_kind_counts': dict(counts),
          'findings': findings, 'selected_motion_rows': selected,
          'selected_adapter_rows': selected_adapter,
          'summary': json.loads((EP / 'summary.json').read_text())}
OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
print(json.dumps({'output': str(OUT), 'sha256': sha(OUT),
                  'findings': findings}, indent=2, sort_keys=True))
