"""Read-only V9 failed-reset provenance; no native/control calls or task PASS."""
import collections
import datetime
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

RUN = Path(sys.argv[1])
PREFIX = Path('/tmp') / sys.argv[2]
FREEZE = sys.argv[3]
BINDINGS = {}
ERRORS = []
FACT_ERRORS = []
ROBOTS = ('tb1', 'tb2', 'tb3')


def check(value, message, facts=False):
    if not value:
        (FACT_ERRORS if facts else ERRORS).append(message)


def bind(path):
    raw = path.read_bytes()
    BINDINGS[str(path)] = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
    return raw


def js(path):
    return json.loads(bind(path))


def rows(path):
    before = bind(path)
    for line in before.splitlines():
        if line:
            yield json.loads(line)
    check(hashlib.sha256(path.read_bytes()).hexdigest() == BINDINGS[str(path)]['sha256'],
          'input changed while reading ' + str(path), True)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def walk_ids(value, saved):
    if isinstance(value, dict):
        if type(value.get('pid')) is int and type(value.get('start_ticks')) is int:
            saved[(value['pid'], value['start_ticks'])] = value
        for child in value.values():
            walk_ids(child, saved)
    elif isinstance(value, list):
        for child in value:
            walk_ids(child, saved)


launch = js(Path(str(PREFIX) + '_launch.json'))
summary = js(RUN / 'benchmark_summary.json')
binary = js(Path('/tmp/mr3_p2a0_v9_binaryproof.json'))
check(launch['freeze'] == summary['freeze'] == binary['freeze'] == FREEZE, 'freeze differs', True)
check(launch['returncode'] == 0, 'launcher returned nonzero')
check(summary['passed'] is True, 'benchmark passed false')
episodes = sorted(RUN.glob('worker*/episode*'))
check(len(episodes) == 1, 'unexpected attempt count', True)
ep = episodes[0]
meta = js(ep / 'metadata.json')
epoch = meta['epoch']
shutdown = js(ep / 'supervisor_shutdown.json')
infra = js(ep / 'infrastructure_failure.json')
check(meta['freeze'] == FREEZE and shutdown['epoch'] == epoch, 'episode identity differs', True)
check(shutdown['worker_returncode'] == 0 and shutdown['forced_shutdown'] is False
      and shutdown['failed_sample'] is False, 'strict supervisor closure failed')
log = bind(ep / 'launch.log').decode()
starts = {int(pid): name for name, pid in re.findall(
    r'\[INFO\] \[([^]]+)\]: process started with pid \[(\d+)\]', log)}
clean = {int(pid): name for name, pid in re.findall(
    r'\[INFO\] \[([^]]+)\]: process has finished cleanly \[pid (\d+)\]', log)}
check(bool(starts) and starts.keys() == clean.keys(), 'native started/clean-exit sets differ')
missing = [name for name in ('native_stop.json', 'nav2_shutdown.json',
                            'reset.info.json', 'actual_nav2_parameters.json')
           if not (ep / name).exists()]
for name in missing:
    ERRORS.append('required successful-reset/closure artifact unavailable: ' + name)
check(summary['valid_transitions'] > 0, 'no returned valid transitions')
params = {'available': (ep / 'actual_nav2_parameters.json').exists(),
          'scope': 'not reached; no actual nine-node parameter PASS inferred'}

# Exact own-output FIFO, independent of the absent task release.
queues = {name: collections.deque() for name in ROBOTS}
counts = {name: collections.Counter() for name in ROBOTS}
last_seq = {name: 0 for name in ROBOTS}
decisions = {}
latest = {}
previous_record = 0
for row in rows(ep / 'motion_safety.jsonl'):
    check(row['epoch'] == epoch and row['record_sequence'] == previous_record + 1,
          'motion record sequence/epoch differs', True)
    previous_record = row['record_sequence']
    payload = row['payload']
    name = payload.get('robot')
    if row['kind'] == 'decision':
        seq = payload['decision_sequence']
        check(seq == last_seq[name] + 1, 'decision sequence differs ' + name, True)
        last_seq[name] = seq
        counts[name]['decisions'] += 1
        counts[name]['ready_true' if payload['ready'] else 'ready_false'] += 1
        queues[name].append((seq, payload['decision']['output']))
        decisions[(name, seq)] = payload
        latest[name] = {'record_sequence': row['record_sequence'],
                        'clock_ns': payload['clock_ns'], 'ready': payload['ready'],
                        'reason': payload['decision']['reason'],
                        'own': {k: (payload['own_state'] or {}).get(k) for k in
                                ('source_stamp', 'tf_source_stamp', 'odom_source_stamp', 'valid')},
                        'peers': {peer: {k: (state or {}).get(k) for k in
                                       ('source_stamp', 'tf_source_stamp', 'odom_source_stamp',
                                        'received_stamp', 'valid', 'version')}
                                  for peer, state in payload['received_peers'].items()}}
    elif row['kind'] == 'actual_cmd_vel':
        counts[name]['actual_local_receipts'] += 1
        check(bool(queues[name]), 'unexpected actual output ' + name, True)
        if not queues[name]:
            continue
        seq, output = queues[name].popleft()
        twist = payload['twist']
        check(payload['observed_decision_sequence'] == seq
              and canonical([twist['linear']['x'], twist['angular']['z']]) == canonical(output),
              'actual output FIFO/value differs ' + name, True)
        check(all(twist[part][axis] == 0.0 for part, axes in
                  (('linear', ('y', 'z')), ('angular', ('x', 'y'))) for axis in axes),
              'unexpected nonplanar actual output ' + name, True)
        ident = payload['publisher_identity']
        endpoints = ident['endpoints']
        check(ident['valid'] is True and ident['scope'] == 'graph_at_callback'
              and len(endpoints) == 1 and endpoints[0]['namespace'] == '/'
              and endpoints[0]['node'] == 'motion_safety', 'actual publisher differs ' + name, True)
check(all(not q for q in queues.values()), 'unconsumed motion output FIFO', True)

# Actual native graph and spawned SDF identity. No parameter readback substitute.
topology = js(ep / 'drive_topology.json')
check(topology['epoch'] == epoch, 'drive topology epoch differs', True)
models = {}
configs = {}
drive = {}
for name in ROBOTS:
    driver = ('/' + name, 'turtlebot3_diff_drive')
    target = '/' + name + '/mr3_drive/target'
    status = '/' + name + '/mr3_drive/status'
    for entries, owner in ((topology['publishers'][target], ('/', 'motion_safety')),
                           (topology['publishers'][status], driver),
                           (topology['target_subscribers'][target], driver)):
        check(len(entries) == 1 and (entries[0]['namespace'], entries[0]['node']) == owner
              and entries[0]['topic_type'] == 'std_msgs/msg/String', 'drive endpoint differs ' + name, True)
    check(not any((x['namespace'], x['node']) == driver
                  for x in topology['legacy_subscribers']['/' + name + '/cmd_vel']),
          'tagged driver subscribes Twist ' + name, True)
    model_raw = bind(ep / ('drive_model_' + name + '.sdf'))
    plugin = ET.fromstring(model_raw).find(".//plugin[@name='turtlebot3_diff_drive']")
    models[name] = {'sha256': hashlib.sha256(model_raw).hexdigest(),
                    'filename': plugin.get('filename'), 'tagged': plugin.findtext('mr3_tagged_commands'),
                    'epoch': plugin.findtext('mr3_epoch'), 'audit_path': plugin.findtext('mr3_audit_path')}
    check(models[name]['filename'] == 'libmr3_gazebo_diff_drive.so'
          and models[name]['tagged'] == 'true' and models[name]['epoch'] == epoch
          and models[name]['audit_path'] == str(ep / ('drive_' + name + '.jsonl')),
          'actual SDF differs ' + name, True)
    stats = collections.Counter()
    source_ages = []
    for row in rows(ep / ('drive_' + name + '.jsonl')):
        stats[row['kind']] += 1
        if row['kind'] == 'configuration':
            keys = ('compiled_source_sha256', 'compiled_header_sha256', 'compiled_helper_sha256',
                    'compiled_target_contract_sha256')
            configs[name] = row
            check(row['schema'] == 'mr3-drive-actuation-v2' and row['command_mode'] == 'tagged'
                  and row['epoch'] == epoch and row['robot'] == name
                  and row['command_topic'] == target and row['status_topic'] == status
                  and row['loaded_library_path'] == binary['library_path']
                  and all(row[key] == binary[key] for key in keys), 'driver configuration differs ' + name, True)
        elif row['kind'] == 'command_received':
            key = (name, row['target_decision_sequence'])
            decision = decisions.get(key)
            check(decision is not None and decision['clock_ns'] == row['target_clock_ns']
                  and canonical(decision['decision']['output']) == canonical([row['desired_v'], row['desired_w']]),
                  'stored target lacks exact guard decision ' + name, True)
            source_ages.append(row['sim_time_ns'] - row['target_clock_ns'])
    drive[name] = {'kinds': dict(stats), 'stored_source_age_ns_max': max(source_ages, default=None),
                   'scope': 'pre-release only; no task160ms or braking credit'}

physics = list(rows(ep / 'physics.jsonl'))
phases = list(rows(ep / 'motion_phase_worker.jsonl'))
consumed = [x for x in phases if x['kind'] == 'ack_consumed']
phase_counts = collections.Counter(x['kind'] for x in rows(ep / 'drive_phase_worker.jsonl'))
check(bool(consumed) and consumed[-1]['ack']['clock_ns'] == physics[-1]['end_time_ns'],
      'last warmup motion ACK differs from last physical clock', True)

# Fresh exact identities include actual saved shutdown and live observer unions.
spec = importlib.util.spec_from_file_location('monitor', '/tmp/mr3_readonly_v9_drive_process_monitor.py')
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)
saved = {}
for obj in (launch, shutdown):
    walk_ids(obj, saved)
monitors = []
for path in sorted(Path('/tmp').glob(PREFIX.name + '_process_monitor_*.json')):
    obj = js(path)
    monitors.append({'path': str(path), 'mapped_libraries': obj.get('gazebo_mapped_libraries', [])})
    walk_ids(obj, saved)
identities = [{'saved': value, 'current': observer.proc_identity(value['pid']),
               'same_identity_present': observer.same(value) is not None} for value in saved.values()]
gone = all(not x['same_identity_present'] for x in identities)
check(gone, 'an actual saved PID/start remains', True)
library_sha = hashlib.sha256(bind(Path(binary['library_path']))).hexdigest()
check(library_sha == binary['library_sha256'], 'current library changed', True)
mapped = [g for mon in monitors for g in mon['mapped_libraries']
          if g['new_drive_mapped'] and not g['old_system_drive_mapped']
          and g['identity_still_same_after_maps'] and g['mappings']
          and all(m['matches_declared_binary'] for m in g['mappings'])]
check(bool(mapped), 'no live matching mapped-library observation', True)
result = {
    'schema': 'mr3-v9-failed-reset-closure-binary-review-v1', 'passed': not (ERRORS or FACT_ERRORS),
    'freeze': FREEZE, 'run': str(RUN), 'epoch': epoch,
    'capture_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'startup_error': infra, 'launch_returncode': launch['returncode'],
    'launch_wall_sec': launch['wall_duration_sec'], 'returned_resets': 0,
    'valid_transitions': summary['valid_transitions'],
    'strict_native_closure_passed': not any('closure' in x or 'clean-exit' in x or 'artifact' in x for x in ERRORS),
    'supervisor': {k: v for k, v in shutdown.items() if k != 'owned_processes_seen'},
    'native_started': len(starts), 'native_clean_exits': len(clean),
    'native_started_without_clean_exit_record': {str(k): v for k, v in starts.items() if k not in clean},
    'unavailable_success_artifacts': missing, 'actual_parameters': params,
    'all_saved_identities_gone': gone, 'saved_identity_count': len(saved), 'identities': identities,
    'actual_binary_provenance_passed': bool(mapped) and library_sha == binary['library_sha256'],
    'library_actual_sha256': library_sha, 'live_mapped_observations': mapped,
    'models': models, 'configurations': configs,
    'nine_native_endpoints_checked': True,
    'motion_fifo': {'counts': {k: dict(v) for k, v in counts.items()}, 'pending': {k: len(v) for k, v in queues.items()},
                    'latest_decisions': latest},
    'drive_target_observation': drive,
    'warmup_physics': {'rows': len(physics), 'physical_steps': sum(x['steps'] for x in physics),
                       'first_clock_ns': physics[0]['start_time_ns'], 'last_clock_ns': physics[-1]['end_time_ns'],
                       'motion_ack_consumed_count': len(consumed), 'final_motion_ack': consumed[-1],
                       'drive_phase_kind_counts': dict(phase_counts)},
    'provenance_fact_checks_passed': not FACT_ERRORS, 'errors': ERRORS, 'fact_errors': FACT_ERRORS,
    'bindings': BINDINGS, 'reviewer_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'scope': 'Failed reset is retained as overall FAIL. Actual saved union absence and provenance facts do not supply strict native closure, parameter readback, released task, movement, body bounds or response credit.'}
out = Path(str(PREFIX) + '_closure_binary_review_v1.json')
with out.open('x') as handle:
    json.dump(result, handle, indent=2)
    handle.write('\n')
print(json.dumps({k: result[k] for k in ('passed', 'saved_identity_count', 'all_saved_identities_gone',
                                        'strict_native_closure_passed', 'actual_binary_provenance_passed',
                                        'provenance_fact_checks_passed', 'native_started', 'native_clean_exits',
                                        'errors', 'fact_errors')}))
