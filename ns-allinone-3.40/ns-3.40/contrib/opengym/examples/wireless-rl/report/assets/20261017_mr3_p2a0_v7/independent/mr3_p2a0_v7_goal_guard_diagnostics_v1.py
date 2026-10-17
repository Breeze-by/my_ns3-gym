"""Read-only received-state/goal and final-guard prefix forensics; no truth/control."""
import argparse
from collections import Counter, defaultdict
import hashlib
import io
import json
import math
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('episode', type=Path)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
assert not args.output.exists()
bindings = {}


def read(path, jsonl=False):
    with path.open('rb') as stream:
        raw = stream.read(path.stat().st_size)
    complete = raw[:raw.rfind(b'\n')+1] if jsonl else raw
    bindings[str(path)] = {'complete_prefix_bytes': len(complete),
                           'sha256': hashlib.sha256(complete).hexdigest(),
                           'captured_bytes': len(raw), 'omitted_partial_tail_bytes': len(raw)-len(complete)}
    return complete


def angle(value):
    return math.atan2(math.sin(value), math.cos(value))


def relative(robot):
    nav = robot['navigation']
    x, y = nav.get('goal_x'), nav.get('goal_y')
    result = {'goal_id': nav.get('goal_id'), 'phase': nav.get('phase'), 'goal_xy': [x, y],
              'estimated_pose': [robot['x'], robot['y'], robot['yaw']],
              'received_activity': robot['activity']}
    if x is not None and y is not None:
        dx, dy = x-robot['x'], y-robot['y']
        result.update(distance_m=math.hypot(dx, dy), relative_bearing_rad=angle(math.atan2(dy, dx)-robot['yaw']))
    return result


ep = args.episode.resolve()
metadata = json.loads(read(ep/'metadata.json'))
transitions = [json.loads(line) for line in read(ep/'transitions.jsonl', True).splitlines()]
assert transitions[0]['kind'] == 'reset'
release = transitions[0]['info']['release_time_ns']
snapshots = [row['snapshot'] for row in transitions]
counts, stages, metrics = defaultdict(Counter), defaultdict(lambda: defaultdict(Counter)), defaultdict(Counter)
last, first_examples = {}, defaultdict(dict)
raw = read(ep/'motion_safety.jsonl', True)
for line, encoded in enumerate(io.BytesIO(raw), 1):
    row = json.loads(encoded)
    assert row['epoch'] == metadata['epoch'] and row['record_sequence'] == line
    if row['kind'] != 'decision' or row['payload']['clock_ns'] < release:
        continue
    value = row['payload']
    name, clock = value['robot'], value['clock_ns']
    elapsed = (clock-release)/1e9
    stage = ('initial_goal' if elapsed < 1.5 else 'first_keep' if elapsed < 10 else
             'intentional_wait' if elapsed < 13 else 'second_goal' if elapsed < 15 else 'second_keep')
    decision, request, own = value['decision'], value['request'], value['own_state']
    reason, output = decision['reason'], decision['output']
    counts[name][reason] += 1
    stages[name][stage][reason] += 1
    metrics[name]['decisions'] += 1
    if request:
        metrics[name]['nonzero_linear_requests'] += abs(request['v']) > .001
        metrics[name]['nonzero_angular_requests'] += abs(request['w']) > .001
        metrics[name]['zero_linear_angular_requests'] += abs(request['v']) <= .001 and abs(request['w']) > .001
        metrics[name]['linear_request_suppressed'] += abs(request['v']) > .001 and abs(output[0]) <= .001
        metrics[name]['angular_request_suppressed'] += abs(request['w']) > .001 and abs(output[1]) <= .001
    metrics[name]['nonzero_linear_outputs'] += abs(output[0]) > .001
    metrics[name]['nonzero_angular_outputs'] += abs(output[1]) > .001
    sample = {'guard_line': line, 'decision_sequence': value['decision_sequence'], 'clock_ns': clock,
              'task_elapsed_sec': elapsed, 'stage': stage,
              'request': None if request is None else {key: request[key] for key in ('v', 'w', 'received_stamp')},
              'estimated_own': None if own is None else {key: own.get(key) for key in
                  ('x', 'y', 'yaw', 'v', 'w', 'source_stamp', 'odom_source_stamp')},
              'decision': decision}
    last[name] = sample
    first_examples[name].setdefault(reason, sample)
for path, binding in bindings.items():
    with Path(path).open('rb') as stream:
        assert hashlib.sha256(stream.read(binding['complete_prefix_bytes'])).hexdigest() == binding['sha256']
result = {'schema': 'mr3-v7-received-goal-guard-diagnostics-v1', 'freeze': metadata['freeze'],
          'epoch': metadata['epoch'], 'episode': str(ep), 'release_ns': release,
          'episode_closed_at_capture': (ep/'summary.json').exists(),
          'latest_snapshot_sequence': snapshots[-1]['sequence'],
          'latest_snapshot_task_elapsed_sec': snapshots[-1]['task_elapsed_sec'],
          'latest_snapshot_targets': {row['name']: relative(row) for row in snapshots[-1]['robots']},
          'guard_reasons': counts, 'phase_guard_reasons': stages, 'guard_metrics': metrics,
          'last_guard_decisions': last, 'first_examples_by_reason': first_examples,
          'inputs': bindings, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'scope': 'Immutable complete prefixes of actual received state/owned target and final guard records only; no truth, policy advice, control, physics/safety PASS or gate change. Intentional WAIT timeout is separately staged.'}
with args.output.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({'output': str(args.output), 'sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                  'closed': result['episode_closed_at_capture'], 'task_elapsed_sec': result['latest_snapshot_task_elapsed_sec'],
                  'metrics': metrics}, indent=2))
