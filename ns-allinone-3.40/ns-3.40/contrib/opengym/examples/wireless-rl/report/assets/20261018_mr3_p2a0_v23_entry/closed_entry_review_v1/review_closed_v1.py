"""Independent read-only V23 closed failure facts; no formal auditor rerun."""
from pathlib import Path
import hashlib
import json
import os
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
RUN = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v23_interface'
EP = RUN / 'worker0/episode001_open_101'
B = Path(__file__).resolve().parent
TEMP = Path('/tmp')
inputs = {}
sha = lambda raw: hashlib.sha256(raw).hexdigest()
def read(path):
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ino) == (after.st_size, after.st_mtime_ns, after.st_ino)
    inputs[str(path)] = {'sha256': sha(raw), 'bytes': len(raw), 'stat': [after.st_size, after.st_mtime_ns, after.st_ino]}
    return raw

def load(path):
    return json.loads(read(path))

started = time.monotonic()
launch = load(TEMP / 'mr3_p2a0_v23_interface_launch.json')
summary = load(RUN / 'benchmark_summary.json')
audit = load(TEMP / 'mr3_p2a0_v23_interface_audit_execution_v1.json')
ledger = [json.loads(line) for line in read(TEMP / 'mr3_p2a0_v23_remaining_matrix_v1.jsonl').splitlines()]
shutdown = load(EP / 'supervisor_shutdown.json')
cleanup = load(EP / 'infrastructure_cleanup.json')
watcher = load(TEMP / 'mr3_p2a0_v23_cross_stage_mapping_summary_v1.json')
configuration = [json.loads(line) for line in read(EP / 'ray_box_corrector.jsonl').splitlines()]
metadata = load(EP / 'metadata.json')
launch_lines = read(EP / 'launch.log').decode(errors='replace').splitlines()
selected = [{'line': n, 'text': line} for n, line in enumerate(launch_lines, 1)
            if 'ray-box installation requires unstarted ODE world' in line or
            ('process has died' in line and '[gzserver-5]' in line)]
formal = []
for row in audit['commands']:
    console = Path(row['console'])
    console_raw = read(console)
    assert sha(console_raw) == row['console_sha256']
    output = Path(row['output'])
    if row['output_exists']:
        raw = read(output)
        assert sha(raw) == row['output_sha256']
    else:
        assert not output.exists()
    formal.append({k: row.get(k) for k in ('label', 'argv', 'returncode', 'passed', 'output', 'output_exists', 'wall_seconds')})
assert len(formal) == 11 and all(row['returncode'] == 1 and row['passed'] is False for row in formal)
assert audit['all_submitted_jobs_finished'] is True and not audit['runner_errors']
assert len(audit['receipts']) == 10 and all(row['passed'] is False for row in audit['receipts'])
failed = ledger[-1]
assert failed['event'] == 'version_failed_later_stages_skip'
assert failed['later_stages'] == ['terminal', 'reset', 'deadline']
assert failed['native_ok'] is False and failed['audit_ok'] is False
saved = {}
def collect(value, source):
    if isinstance(value, dict):
        if type(value.get('pid')) is int and type(value.get('start_ticks')) is int:
            key = (value['pid'], value['start_ticks'])
            saved.setdefault(key, {'saved': value, 'sources': []})['sources'].append(source)
        for child in value.values():
            collect(child, source)
    elif isinstance(value, list):
        for child in value:
            collect(child, source)
for value, source in [(launch, 'launch'), (summary, 'summary'), (ledger, 'parent_ledger'), (shutdown, 'supervisor_shutdown')]:
    collect(value, source)
for path in sorted(TEMP.glob('mr3_p2a0_v23_interface_process_monitor_*.json')):
    collect(load(path), str(path))
identities = []
for (pid, old_start), row in sorted(saved.items()):
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        rest = raw[raw.rindex(')') + 2:].split()
        current = {'pid': pid, 'start_ticks': int(rest[19]), 'state': rest[0], 'parent': int(rest[1]), 'raw_stat': raw}
    except FileNotFoundError:
        current = None
    row.update(current=current, same_identity_present=current is not None and current['start_ticks'] == old_start)
    identities.append(row)
assert all(not row['same_identity_present'] for row in identities)
assert launch['returncode'] == 1 and launch['passed'] is False
assert summary['passed'] is False and summary['valid_transitions'] == 0
assert shutdown['failed_sample'] is True and shutdown['forced_shutdown'] is True
assert not shutdown['remaining_owned_processes'] and not shutdown['remaining_owned_zombies']
assert cleanup['passed'] is False and 'IPC response wall guard expired' in cleanup['cleanup_error']
assert len(configuration) == 1 and configuration[0]['kind'] == 'configuration'
assert launch['wall_duration_sec'] == 32.096621671225876
assert launch['budget']['prior_entry_wall_seconds'] == .24578428314998746
assert launch['cumulative_wall_seconds'] == 32.34240595437586
for name, binding in inputs.items():
    path = Path(name)
    assert sha(path.read_bytes()) == binding['sha256']
    stat = path.stat()
    assert [stat.st_size, stat.st_mtime_ns, stat.st_ino] == binding['stat']
result = {'schema': 'mr3-v23-closed-native-entry-independent-review-v1', 'passed': True,
          'freeze': metadata['freeze'], 'argv': [sys.executable, *sys.argv], 'cwd': os.getcwd(),
          'source_sha256': sha(Path(__file__).read_bytes()),
          'facts': {'native_stage_passed': False, 'reset_returned': False, 'valid_transitions': 0,
                    'actual_gazebo_abort_returncode': -6, 'corrector_kinds': ['configuration'],
                    'no_installed_credit': True, 'primary_cause_lines': selected,
                    'formal_jobs': 11, 'formal_real_exit1': 11, 'mandatory_receipts': 10,
                    'all_mandatory_failed': True, 'all_submitted_jobs_finished': True,
                    'later_stages_skip': failed['later_stages'], 'forced_shutdown': True,
                    'failed_sample': True, 'ordered_infrastructure_cleanup_passed': False,
                    'cleanup_error': cleanup['cleanup_error'], 'no_saved_owned_alive_or_zombie': True,
                    'native_stage_wall_seconds': launch['wall_duration_sec'],
                    'V22_entry_wall_seconds': launch['budget']['prior_entry_wall_seconds'],
                    'cumulative_charged_wall_seconds': launch['cumulative_wall_seconds'],
                    'remaining_18000_wall_seconds': 18000-launch['cumulative_wall_seconds']},
          'saved_identity_count': len(identities), 'fresh_identity_checks': identities,
          'formal_commands': formal, 'input_bindings': inputs, 'wall_seconds': time.monotonic()-started,
          'limitations': ['Fresh /proc checks cover exact saved PID/start identities only. Formal leaf child PID/start and watcher self identity were not saved, so this does not fabricate independent fresh leaf/watcher PID proof; parent wait/drain and watcher completion are original ledger facts.',
                         'No successful reset/task sample or physical PASS. Cleanup was forced and IPC cleanup failed; empty remaining-owned inventories do not relabel this as normal strict closure.',
                         'Existing audits were not rerun. No ROS/DDS/native, source change or canonical mutation.'],
          'scope': 'Independent closed accounting/identity/original verdict preservation only; review passed is not native/physics/task passed.'}
with (B / 'review_v1.json').open('x') as stream:
    stream.write(json.dumps(result, indent=2, allow_nan=False)+'\n')
print(json.dumps({'passed': True, 'saved_identity_count': len(identities), 'review': str(B / 'review_v1.json'), 'sha256': sha((B / 'review_v1.json').read_bytes()), 'facts': result['facts']}))
