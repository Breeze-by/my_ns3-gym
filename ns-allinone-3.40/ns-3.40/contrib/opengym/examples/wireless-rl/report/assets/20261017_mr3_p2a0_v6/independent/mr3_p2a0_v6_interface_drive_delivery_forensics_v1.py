"""Read-only v6 receipt age forensics; no control, no task PASS assertion."""
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
EP = ROOT / ('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/'
             'mr3_p2a0_20261017_v6_interface/worker0/episode001_open_101')
OUTPUT = Path('/tmp/mr3_p2a0_v6_interface_drive_delivery_forensics_v1.json')
bindings = {}


def rows(name):
    path = EP / name
    raw = path.read_bytes()
    bindings[str(path)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
    assert raw.endswith(b'\n')
    return [json.loads(line) for line in raw.splitlines()]


transitions = rows('transitions.jsonl')
release = transitions[0]['info']['release_time_ns']
physics = rows('physics.jsonl')
final = physics[-1]['end_time_ns']
previous = physics[0]['start_time_ns']
previous_iterations = physics[0]['start_iterations']
physics_errors = []
boundaries = {previous}
for line, row in enumerate(physics, 1):
    if not (row['start_time_ns'] == previous and
            row['start_iterations'] == previous_iterations and
            row['end_time_ns']-row['start_time_ns'] == row['steps']*row['step_ns'] and
            row['end_iterations']-row['start_iterations'] == row['steps']):
        physics_errors.append({'line': line, 'row': row})
    previous, previous_iterations = row['end_time_ns'], row['end_iterations']
    boundaries.add(previous)

robots = {}
for name in ('tb1', 'tb2', 'tb3'):
    records = rows(f'drive_{name}.jsonl')
    latest = None
    failures = []
    samples = []
    for line, row in enumerate(records, 1):
        if row['kind'] == 'command_received':
            latest = (line, row)
        elif row['kind'] == 'actuation' and release <= row['sim_time_ns'] <= final:
            assert latest is not None
            command_line, command = latest
            assert row['cmd_seq'] == command['cmd_seq']
            assert (row['desired_v'], row['desired_w']) == (command['desired_v'], command['desired_w'])
            sample = {'actuation_line': line, 'source_ns': row['sim_time_ns'],
                      'command_line': command_line, 'cmd_seq': command['cmd_seq'],
                      'command_received_ns': command['sim_time_ns'],
                      'receive_age_ns': row['sim_time_ns']-command['sim_time_ns'],
                      'desired_vw': [row['desired_v'], row['desired_w']]}
            samples.append(sample)
            if sample['receive_age_ns'] > 160_000_000:
                failures.append(sample)
    robots[name] = {'task_actuation_samples': len(samples),
                    'over_160ms_count': len(failures),
                    'over_160ms_nonzero_count': sum(x['desired_vw'] != [0., 0.] for x in failures),
                    'maximum_receive_age_sample': max(samples, key=lambda x: x['receive_age_ns']),
                    'violations': failures}

for path, binding in bindings.items():
    raw = Path(path).read_bytes()
    assert len(raw) == binding['bytes'] and hashlib.sha256(raw).hexdigest() == binding['sha256']
result = {'schema': 'mr3-v6-drive-delivery-forensics-v1',
          'freeze': '448ceb6a26e9fef1f1c47e26292ba64c1b93c732',
          'episode': str(EP), 'release_ns': release, 'final_physics_ns': final,
          'physics_rows': len(physics), 'physics_continuity_errors': physics_errors,
          'release_is_actual_physics_boundary': release in boundaries,
          'first_physics_row': physics[0],
          'pre_release_alignment_rows': sum(row['end_time_ns'] <= release for row in physics),
          'robots': robots, 'inputs': bindings,
          'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
          'scope': 'Exact local driver receipt age diagnostic on release<=source<=final, including nonzero retained commands. It neither relaxes160ms nor proves a causal mechanism, safe response, fresh packet identity, or overall task PASS.'}
with OUTPUT.open('x') as stream:
    json.dump(result, stream, indent=2, allow_nan=False)
    stream.write('\n')
print(json.dumps({'output': str(OUTPUT), 'sha256': hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),
                  'robots': {name: {key: value for key, value in robot.items() if key != 'violations'}
                             for name, robot in robots.items()}}, indent=2))
