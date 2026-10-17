"""DATA review of the closed V22 pre-backend entry failure; no processes started."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import sys
import time

TMP = Path('/tmp')
ROOT = Path('/home/zhuyulab/ns3-workspace')
FREEZE = 'cdda62325c6322cf5322162c616bd9b699354665'
INPUTS = {}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def stat(path):
    value = path.stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def read(path):
    before = stat(path)
    raw = path.read_bytes()
    assert stat(path) == before
    INPUTS[str(path)] = dict(sha256=sha(raw), bytes=len(raw), stat=before)
    return raw


def proc(pid):
    path = Path('/proc') / str(pid) / 'stat'
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return None
    fields = raw[raw.rfind(')') + 2:].split()
    return dict(pid=pid, start_ticks=int(fields[19]), parent=int(fields[1]), state=fields[0], stat_raw=raw)


began = time.monotonic()
ledger = [json.loads(line) for line in read(TMP / 'mr3_p2a0_v22_remaining_matrix_v1.jsonl').splitlines()]
launch = json.loads(read(TMP / 'mr3_p2a0_v22_interface_launch.json'))
audit = json.loads(read(TMP / 'mr3_p2a0_v22_interface_audit_execution_v1.json'))
watcher = json.loads(read(TMP / 'mr3_p2a0_v22_cross_stage_mapping_summary_v1.json'))
watcher_start = json.loads(read(TMP / 'mr3_p2a0_v22_cross_stage_mapping_start_v1.json'))
preflight = json.loads(read(TMP / 'mr3_p2a0_v22_source_preflight.json'))
benchmark_error = read(TMP / 'mr3_p2a0_v22_interface_console.log').decode()
audit_error = read(TMP / 'mr3_p2a0_v22_interface_full_audit_console.log').decode()
assert all(row['freeze'] == FREEZE for row in ledger)
assert launch['freeze'] == audit['freeze'] == watcher['freeze'] == preflight['freeze'] == FREEZE
assert 'ModuleNotFoundError: No module named \'gymnasium\'' in benchmark_error
assert 'ModuleNotFoundError: No module named \'torch\'' in audit_error
assert launch['command_argv'][0] == '/usr/bin/python3'
assert launch['passed'] is False and audit['passed'] is False
assert audit['all_submitted_jobs_finished'] is True and audit['runner_errors'] == []
assert len(audit['commands']) == 7 and all(row['returncode'] == 1 for row in audit['commands'])
assert ledger[-1]['event'] == 'version_failed_later_stages_skip'
assert ledger[-1]['later_stages'] == ['terminal', 'reset', 'deadline']
saved = {}
for row in ledger:
    for key in ('controller_identity', 'child_identity'):
        value = row.get(key)
        if value:
            saved[(value['pid'], value['start_ticks'])] = value
for key in ('launcher_identity', 'benchmark_parent'):
    value = launch[key]
    saved[(value['pid'], value['start_ticks'])] = value
identities = []
for (pid, ticks), value in saved.items():
    current = proc(pid)
    same = current is not None and current['start_ticks'] == ticks
    identities.append(dict(saved=value, current=current, same_identity_present=same))
assert len(identities) == 4 and all(not row['same_identity_present'] for row in identities)
components = ['mr3_p2a0_v22_run_matrix_v1.py', 'mr3_p2a0_v22_launch_stage.py',
              'mr3_p2a0_v22_audit_stage.py', 'mr3_p2a0_v22_cross_stage_mapping_monitor_v1.py']
matching, proc_errors = [], []
for directory in Path('/proc').iterdir():
    if not directory.name.isdigit() or int(directory.name) == os.getpid():
        continue
    try:
        raw = (directory / 'cmdline').read_bytes()
        argv = raw.rstrip(b'\0').split(b'\0') if raw else []
        decoded = [value.decode(errors='replace') for value in argv]
        exact = any(Path(value).name in components for value in decoded)
        run_id = any('mr3_p2a0_20261018_v22_' in value for value in decoded)
        if exact or run_id:
            matching.append(dict(identity=proc(int(directory.name)), argv=decoded))
    except (FileNotFoundError, ProcessLookupError):
        pass
    except PermissionError as error:
        proc_errors.append(str(error))
runs = [ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0' /
        ('mr3_p2a0_20261018_v22_' + stage) for stage in ('interface', 'terminal', 'reset', 'deadline')]
run_facts = [dict(path=str(path), exists=path.exists()) for path in runs]
assert all(not row['exists'] for row in run_facts)
for row in audit['commands']:
    assert sha(read(Path(row['console']))) == row['console_sha256']
    if row.get('output_exists'):
        assert sha(read(Path(row['output']))) == row['output_sha256']
for row in INPUTS.values():
    assert len(row['sha256']) == 64
for path, expected in INPUTS.items():
    assert stat(Path(path)) == expected['stat'] and sha(Path(path).read_bytes()) == expected['sha256']
result = dict(schema='mr3-v22-prebackend-entry-failure-closure-data-review-v1',
              passed=False, review_completed=True, freeze=FREEZE,
              actual_stage_outcome='ENTRYFAIL before backend/worker/Gazebo; original failure preserved',
              native_runs=0, api_records=0, physics_steps=0,
              evidence_basis='benchmark failed while importing env.py/gymnasium, before benchmark main creates output/backend; all four actual run directories absent',
              saved_identity_count=len(identities), identities=identities,
              all_saved_identities_fresh_gone=True,
              current_matching_argv_processes=matching, current_proc_permission_errors=proc_errors,
              no_current_matching_execution_argv=not matching,
              exact_identity_coverage_limit='Only matrix/launcher/benchmark/audit coordinator PID/start saved. Seven formal subprocess records and watcher start omit their own PID/start, so no retrospective per-leaf identity inventory is claimed. Their completion uses actual wait returns / final watcher summary and root session exit evidence.',
              audit_submitted_commands=len(audit['commands']),
              audit_commands=[dict(label=row['label'], argv=row['argv'], returncode=row['returncode'],
                                   output_exists=row.get('output_exists'), passed=row['passed']) for row in audit['commands']],
              all_submitted_jobs_finished=True, runner_errors=[],
              required_receipts=len(audit['receipts']), required_passed=sum(row['passed'] is True for row in audit['receipts']),
              actual_missing_receipts=[row['path'] for row in audit['receipts'] if row['sha256'] is None],
              skipped_stages=ledger[-1]['later_stages'], run_directory_facts=run_facts,
              watcher_natural_finish=dict(closed_stages=watcher['closed_stages'], stop_reason=watcher['stop_reason'],
                                           wall_seconds=watcher['wall_seconds'], actual_worker_count=0),
              actual_wrong_interpreters=dict(parent=ledger[0]['argv'][0], benchmark=launch['command_argv'][0],
                                             full_audit=next(row['argv'][0] for row in audit['commands'] if row['label'] == 'full_audit')),
              cost=dict(native_wall_seconds=0, launcher_wrapper_wall_seconds=launch['wall_duration_sec'],
                        parent_launch_child_wall_seconds=next(row['wall_seconds'] for row in ledger if row.get('event') == 'command_completed' and row.get('operation') == 'launch'),
                        parent_audit_child_wall_seconds=next(row['wall_seconds'] for row in ledger if row.get('event') == 'command_completed' and row.get('operation') == 'audit')),
              prior_review_correction='The prior static coordinator review proved call structure but missed actual sys.executable inheritance: a system-Python parent selected system Python for benchmark and full audit. That review did not establish dependency-environment readiness and cannot be read as an end-to-end launch check.',
              scope='Read-only closed entry-failure facts and fresh /proc snapshot. No unit/math/import probe/SDK/ROS/DDS/native/formal execution, signals, retry or canonical edits.',
              capture_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), capture_monotonic_ns=time.monotonic_ns(),
              inputs=INPUTS, source_sha256=sha(Path(__file__).read_bytes()), argv=sys.argv,
              wall_seconds=time.monotonic()-began)
output = TMP / 'mr3_p2a0_v22_entry_failure_closure_review_v1.json'
with output.open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(review_completed=True, stage_passed=False, saved_identities_gone=len(identities),
                      matching_processes=len(matching), report=str(output), sha256=sha(output.read_bytes()))))
