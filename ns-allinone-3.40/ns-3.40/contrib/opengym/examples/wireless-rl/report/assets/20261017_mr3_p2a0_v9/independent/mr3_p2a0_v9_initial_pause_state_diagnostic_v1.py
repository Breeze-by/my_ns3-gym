"""Closed failed-reset provenance diagnostic; no truth, control or criterion changes."""
import hashlib
import json
from pathlib import Path

EP = Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v9_interface/worker0/episode001_open_101')
OUT = Path('/tmp/mr3_p2a0_v9_initial_pause_state_diagnostic_v1.json')
assert not OUT.exists()
bindings = {}


def read(name, lines=False):
    path = EP / name
    raw = path.read_bytes()
    bindings[str(path)] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    assert not lines or not raw or raw.endswith(b'\n')
    return [json.loads(line) for line in raw.splitlines()] if lines else json.loads(raw)


metadata = read('metadata.json')
physics = read('physics.jsonl', True)
motion = read('motion_safety.jsonl', True)
ledger = read('information_states.jsonl', True)
phase = read('motion_phase_worker.jsonl', True)
failure = read('infrastructure_failure.json')
closure = read('supervisor_shutdown.json')
transition = (EP / 'transitions.jsonl').read_bytes()
assert transition == b'' and not (EP / 'summary.json').exists()
initial = next(row for row in reversed(phase) if row['kind'] == 'ack_consumed')
clock = initial['ack']['clock_ns']
assert clock == physics[-1]['end_time_ns'] == 74_340_000_000
published = next(row for row in reversed(ledger) if row['kind'] == 'state_publish')
received = next(row for row in reversed(motion) if row['kind'] == 'received_states')
assert published['payload']['message'] == received['payload']
selections = {row['payload']['robot']: row for row in ledger if row['kind'] == 'state_selection'}
ingress = {(row['kind'], row['payload']['robot'], row['payload']['input_sequence']): row
           for row in ledger if row['kind'].endswith('_ingress')}
diagnostics = {}
for name in ('tb1', 'tb2', 'tb3'):
    selection = selections[name]
    value = selection['payload']
    decision = next(row for row in reversed(motion)
                    if row['kind'] == 'decision' and row['payload']['robot'] == name)
    selected = {kind: ingress[kind + '_ingress', name, value[kind + '_input_sequence']]
                for kind in ('odom', 'tf')}
    later = [row for row in ledger if row['kind'] == 'tf_ingress'
             and row['payload']['robot'] == name and row['payload']['admission'] == 'queued'
             and row['record_sequence'] > selection['record_sequence']
             and row['payload']['source_ns'] > value['tf_source_ns']
             and row['payload']['source_ns'] <= clock]
    robot = next(item for item in received['payload']['robots'] if item['name'] == name)
    diagnostics[name] = {'selection': selection, 'selected_raw_ingress': selected,
                         'first_newer_eligible_tf_after_selection': later[0] if later else None,
                         'actual_last_guard': decision,
                         'received_source_age_at_paused_boundary_ns': clock - round(robot['source_stamp'] * 1e9),
                         'received_valid_field': robot['valid'],
                         'own_source_age_ns': clock - round(decision['payload']['own_state']['source_stamp'] * 1e9)}
for path, value in bindings.items():
    raw = Path(path).read_bytes()
    assert len(raw) == value['bytes'] and hashlib.sha256(raw).hexdigest() == value['sha256']
result = {'schema': 'mr3-p2a0-v9-initial-pause-state-diagnostic-v1', 'freeze': metadata['freeze'],
          'epoch': metadata['epoch'], 'passed': False, 'task_release_occurred': False,
          'transition_rows': 0, 'initial_phase_status': initial,
          'warmup_physics': physics, 'latest_hub_publication': published,
          'latest_actual_motion_received': received, 'robots': diagnostics,
          'state_input_failures': [row for row in ledger if row['kind'] == 'state_input_failure'],
          'failure': failure, 'forced_shutdown': closure['forced_shutdown'],
          'remaining_owned_processes': closure['remaining_owned_processes'],
          'remaining_owned_zombies': closure['remaining_owned_zombies'],
          'source_watermark_limit': 'latest callback prefix at selection is not a claim that newer raw data had already arrived',
          'interpretation': 'Paused release correctly refused the stale received tb2 state; newer eligible hub TF arrived after last timer selection. No task or input-replay credit.',
          'inputs': bindings, 'jobs': {'native_starts': 0, 'ROS_messages': 0, 'services': 0, 'repository_writes': 0}}
OUT.write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
print(json.dumps({'output': str(OUT), 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
                  'clock_ns': clock, 'robots': {name: {
                      'received_age_ns': value['received_source_age_at_paused_boundary_ns'],
                      'own_age_ns': value['own_source_age_ns'],
                      'newer_tf_after_selection': value['first_newer_eligible_tf_after_selection']['record_sequence']
                      if value['first_newer_eligible_tf_after_selection'] else None}
                      for name, value in diagnostics.items()}}, indent=2))
