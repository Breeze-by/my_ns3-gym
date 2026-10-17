"""Read-only selected raw V9 failed-startup evidence, without formal task credit."""
import collections
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
EP = ROOT / ('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/'
             'mr3_p2a0_20261017_v9_interface/worker0/episode001_open_101')
FREEZE = '26534fae40409e266376baf0995fb15dc0223e4b'
OUT = Path('/tmp/mr3_p2a0_v9_interface_initial_ready_forensics_v1.json')


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def stream(path):
    with path.open() as handle:
        for line, text in enumerate(handle, 1):
            if text.strip():
                yield line, json.loads(text)


paths = [EP / name for name in ('metadata.json', 'information_states.jsonl',
         'motion_safety.jsonl', 'motion_phase_worker.jsonl', 'physics.jsonl',
         'motion_topology.json', 'adapter.jsonl', 'supervisor_shutdown.json')]
paths = [p for p in paths if p.exists()]
bindings = {str(p): {'sha256': sha(p), 'bytes': p.stat().st_size} for p in paths}
meta = json.loads((EP / 'metadata.json').read_text())
assert meta['freeze'] == FREEZE
selected_info = []
last_pub = None
counts = collections.Counter()
last_future_odom_example = {}
for line, row in stream(EP / 'information_states.jsonl'):
    kind, value = row['kind'], row['payload']
    counts[kind] += 1
    take = ((kind in ('state_selection', 'state_send', 'state_publish')
             and value.get('cycle_id') == 716)
            or (kind == 'tf_ingress' and value['robot'] == 'tb2'
                and value['input_sequence'] in (5173, 5176))
            or (kind == 'odom_ingress' and value['robot'] == 'tb3'
                and value['input_sequence'] in (1486, 1487)))
    if take:
        selected_info.append({'line': line, 'row': row})
    if kind == 'state_publish':
        last_pub = row
    if kind == 'odom_ingress' and value['source_ns'] > row['clock_ns']:
        last_future_odom_example[value['robot']] = {'line': line, 'row': row}
assert last_pub['payload']['cycle_id'] == 716
motion_counts = collections.Counter()
last_decisions = {}
last_received = None
selected_motion = []
for line, row in stream(EP / 'motion_safety.jsonl'):
    motion_counts[row['kind']] += 1
    if row['kind'] == 'decision':
        last_decisions[row['payload']['robot']] = {'line': line, 'row': row}
    elif row['kind'] == 'received_states':
        last_received = {'line': line, 'row': row}
    elif row['kind'] in ('release', 'failure', 'settled_turn_model_failure'):
        selected_motion.append({'line': line, 'row': row})
acks = [item for _, item in stream(EP / 'motion_phase_worker.jsonl')]
consumed = [item for item in acks if item['kind'] == 'ack_consumed']
ack = consumed[-1]
assert ack['ack']['clock_ns'] == 74_340_000_000 and ack['ack']['ready'] is False
assert motion_counts['release'] == 0 and motion_counts['settled_turn_model_failure'] == 0
age = {}
for name, selected in last_decisions.items():
    value = selected['row']['payload']
    assert value['clock_ns'] == 74_340_000_000 and value['ready'] is False
    assert value['started'] is False
    own = value['own_state']
    age[name] = {'own_ages_ns': {
        key: value['clock_ns'] - round(own[key] * 1e9)
        for key in ('source_stamp', 'odom_source_stamp', 'tf_source_stamp')},
        'peer_ages_ns': {peer: {key: value['clock_ns'] - round(state[key] * 1e9)
            for key in ('source_stamp', 'odom_source_stamp', 'tf_source_stamp')}
            for peer, state in value['received_peers'].items()}}
assert age['tb1']['peer_ages_ns']['tb2']['source_stamp'] == 545_000_000
pub = next(item['row'] for item in selected_info if item['row']['kind'] == 'state_publish')
late_tf = next(item['row'] for item in selected_info if item['row']['kind'] == 'tf_ingress'
               and item['row']['payload']['input_sequence'] == 5176)
assert late_tf['record_sequence'] > pub['record_sequence']
assert late_tf['clock_ns'] == pub['clock_ns'] == 74_320_000_000
assert late_tf['payload']['source_ns'] == 74_195_000_000
sources = []
for name in ('src/multi_robot_exploration/multi_robot_exploration/mr3_information.py',
             'src/multi_robot_exploration/multi_robot_exploration/motion_safety.py',
             'scripts/mr3_env_worker.py'):
    path = ROOT / 'ros2_ws/ros2-multi-robot-automap' / name
    rel = str(path.relative_to(ROOT))
    frozen = subprocess.run(['git', 'show', FREEZE + ':' + rel], cwd=ROOT,
                            check=True, capture_output=True).stdout
    assert hashlib.sha256(frozen).hexdigest() == sha(path)
    sources.append({'path': str(path), 'sha256': sha(path), 'matches_freeze_git_bytes': True})
for path, expected in bindings.items():
    assert sha(Path(path)) == expected['sha256']
result = {'schema': 'mr3-v9-initial-ready-forensics-v1', 'freeze': FREEZE,
          'epoch': meta['epoch'], 'overall_stage_passed': False,
          'diagnostic_selected_raw_consistency_passed': True,
          'returned_reset_count': 0, 'returned_step_count': 0,
          'scope': 'failed pre-release warmup only; no formal complete-episode consumer, '
                   'task physical/angular/settled/95percent credit, or native retry',
          'inputs': bindings, 'source_bindings': sources,
          'info_kind_counts': dict(counts), 'motion_kind_counts': dict(motion_counts),
          'selected_information_rows': selected_info,
          'latest_future_odom_ingress_examples': last_future_odom_example,
          'last_motion_decisions': last_decisions, 'independent_age_recomputation': age,
          'last_actual_received_bundle': last_received, 'other_motion_failures': selected_motion,
          'actual_consumed_initial_motion_ack': ack,
          'findings': [
              'Last cycle716 selected TB2 causal odom74.313 and then-latest accepted TF73.795; skip_reason=None.',
              'Actual TB2 fresh TF74.195 ingress5176 arrived after cycle716 actual publication27218, at the same74.32clock.',
              'No later actual state publication occurred before closure; fresh TF remained pending while physics paused74.34.',
              'At74.34 received TB2 TF/source age545ms exceeded unchanged500ms, independently sufficient to make global readyFalse.',
              'All last own odom/TF ages were nonfuture and below500ms; no settled model failure or task release occurred.',
              'Cycle716 TB3 selected causal odom73.982 and retained future input1487; no new latest-only future discard is shown.',
              'Topology snapshot at73.7 records unique motion_safety outputs; per-decision topology is not separately recorded.',
              'Current worker forbids changed motion ACK within oneclock; paused source flushing alone is not an authorized sameclock phase replay.'
          ]}
OUT.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + '\n')
print(json.dumps({'output': str(OUT), 'sha256': sha(OUT), 'overall_stage_passed': False,
                  'diagnostic_selected_raw_consistency_passed': True}))
