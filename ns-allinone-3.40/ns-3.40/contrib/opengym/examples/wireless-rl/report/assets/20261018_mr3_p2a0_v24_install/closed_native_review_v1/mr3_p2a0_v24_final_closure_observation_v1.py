"""Read closed V24 receipts and saved identities; start no audit or native child."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
RUN = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v24_interface'
EP = RUN / 'worker0/episode001_open_101'
PREFIX = Path('/tmp')
INPUTS = {}


def signature(path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def raw(path):
    path = Path(path)
    before = signature(path)
    data = path.read_bytes()
    assert signature(path) == before
    record = dict(path=str(path), bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), stat=before)
    assert str(path) not in INPUTS or INPUTS[str(path)] == record
    INPUTS[str(path)] = record
    return data


def load(path):
    return json.loads(raw(path))


def present(saved):
    try:
        p = Path('/proc') / str(saved['pid']) / 'stat'
        value = p.read_text().rsplit(') ', 1)[1].split()
        actual = dict(start_ticks=int(value[19]), state=value[0])
    except FileNotFoundError:
        actual = None
    return dict(saved=saved, current=actual,
                saved_identity_absent=actual is None or actual['start_ticks'] != saved['start_ticks'])


started = time.monotonic()
launch = load(PREFIX / 'mr3_p2a0_v24_interface_launch.json')
audit = load(PREFIX / 'mr3_p2a0_v24_interface_audit_execution_v1.json')
ledger = [json.loads(line) for line in raw(PREFIX / 'mr3_p2a0_v24_remaining_matrix_v1.jsonl').splitlines()]
watch = load(PREFIX / 'mr3_p2a0_v24_cross_stage_mapping_summary_v1.json')
supervisor = load(EP / 'supervisor_shutdown.json')
native_stop = load(EP / 'native_stop.json')
native_summary = load(EP / 'summary.json')
cleanup = load(EP / 'infrastructure_cleanup.json')
benchmark = load(RUN / 'benchmark_summary.json')
preflight = load(PREFIX / 'mr3_p2a0_v24_source_preflight.json')
corrector_rows = [json.loads(line) for line in raw(EP / 'ray_box_corrector.jsonl').splitlines()]
native_ids = {(row['pid'], row['start_ticks']): row for row in supervisor['owned_processes_seen']}
all_ids = dict(native_ids)
identity_origins = []
for name, item in [('benchmark', launch['benchmark_parent']), ('launcher', launch['launcher_identity'])]:
    all_ids[(item['pid'], item['start_ticks'])] = item
    identity_origins.append(dict(origin=name, identity=item))
for row in ledger:
    for key in ('controller_identity', 'child_identity'):
        if key in row:
            item = row[key]
            all_ids[(item['pid'], item['start_ticks'])] = item
            identity_origins.append(dict(origin=row['event'] + ':' + key, identity=item))
observations = [present(all_ids[key]) for key in sorted(all_ids)]
assert all(row['saved_identity_absent'] for row in observations)
assert audit['all_submitted_jobs_finished'] is True and audit['runner_errors'] == []
assert len(audit['commands']) == 11 and all(type(row['returncode']) is int for row in audit['commands'])
assert len(audit['receipts']) == 10
receipt_results = []
for row in audit['receipts']:
    value = load(Path(row['path']))
    assert INPUTS[row['path']]['sha256'] == row['sha256']
    assert value['passed'] is row['passed']
    receipt_results.append(dict(path=row['path'], sha256=row['sha256'], passed=row['passed']))
skip = ledger[-1]
assert skip['event'] == 'version_failed_later_stages_skip'
assert skip['later_stages'] == ['terminal', 'reset', 'deadline']
runtime_checks = []
for path, binding in preflight['source_bindings'].items():
    data = raw(ROOT / path)
    runtime_checks.append(dict(path=path, expected=binding['sha256'], actual=hashlib.sha256(data).hexdigest()))
assert all(row['expected'] == row['actual'] for row in runtime_checks)
environment = dict(os.environ, GIT_OPTIONAL_LOCKS='0')
head = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, env=environment, text=True, capture_output=True, check=True)
status = subprocess.run(['git', 'status', '--porcelain'], cwd=ROOT, env=environment, text=True, capture_output=True, check=True)
assert head.stdout.strip() == launch['freeze'] == preflight['freeze']
for path, record in INPUTS.items():
    assert signature(Path(path)) == record['stat']
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == record['sha256']
final = dict(
    schema='mr3-v24-final-closure-observation-data-v1', observation_completed=True,
    overall_stage_passed=False, freeze=launch['freeze'], plan_sha256=audit['plan_sha256'],
    utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    source_scope='Read-only closed receipts, source SHA/stat, Git read-only queries and fresh /proc saved identity absence. No formal CLI, test, SDK, DDS, probe, signal or native started.',
    native_unique_saved_count=len(native_ids), saved_union_count=len(observations),
    saved_union_fresh_absent=True, identity_observations=observations, identity_origins=identity_origins,
    watcher=dict(summary=watch, session_exit0_source='Root reported session34679 exit0; summary is completed. No watcher PID/start tuple occurs in retrieved start/summary originals, so no invented tuple enters the saved union.'),
    formal=dict(all_submitted_jobs_finished=True, runner_errors=[], submitted_commands=11,
                command_pass=sum(row['passed'] is True for row in audit['commands']),
                command_fail=sum(row['passed'] is False for row in audit['commands']),
                mandatory_receipts=10, mandatory_pass=sum(row['passed'] is True for row in receipt_results),
                mandatory_fail=sum(row['passed'] is False for row in receipt_results),
                aggregate_passed=audit['passed'], receipts=receipt_results,
                child_identity_scope='Original scheduler saves actual subprocess returncodes and waits, but no per-leaf PID/start tuples. The saved audit-stage child identity is checked fresh absent; no leaf identity is fabricated.'),
    skipped_stages=skip['later_stages'], final_parent_event=skip,
    native=dict(launch_passed=launch['passed'], launch_returncode=launch['returncode'],
                supervisor_forced_shutdown=supervisor['forced_shutdown'], supervisor_failed_sample=supervisor['failed_sample'],
                worker_returncode=supervisor['worker_returncode'], native_stop=native_stop,
                cleanup_passed=cleanup['passed'], summary=native_summary, valid_transitions=benchmark['valid_transitions']),
    corrector=dict(installed=next(row for row in corrector_rows if row['kind'] == 'installed'),
                   lifetime_summary=next(row for row in corrector_rows if row['kind'] == 'process_lifetime_summary')),
    accounting=dict(prior_engineering_debit=launch['budget']['prior_engineering_wall_seconds'],
                    native_launch_receipt_wall_seconds=launch['wall_duration_sec'],
                    native_receipt_cumulative_wall_seconds=launch['cumulative_wall_seconds'],
                    parent_command_intervals=[dict(operation=row['operation'], wall_seconds=row['wall_seconds']) for row in ledger if row['event'] == 'command_completed'],
                    scope='Native receipt cumulative value is preserved. Parent wrapper intervals and parallel audit jobs are separate measurements, not additive duplicates or a changed charging policy.'),
    source=dict(runtime_paths_checked=len(runtime_checks), current_sha_matches_actual_preflight=True,
                runtime_checks=runtime_checks, head=head.stdout.strip(), git_porcelain=status.stdout,
                git_read_commands=[head.args, status.args]),
    inputs=list(INPUTS.values()), all_inputs_final_sha_stat_stable=True,
    wall_seconds=time.monotonic() - started)
out = PREFIX / 'mr3_p2a0_v24_final_closure_observation_v1.json'
with out.open('x') as stream:
    json.dump(final, stream, indent=2)
    stream.write('\n')
print(json.dumps(dict(output=str(out), sha256=hashlib.sha256(out.read_bytes()).hexdigest(),
                     native_saved=len(native_ids), all_saved=len(observations),
                     mandatory_pass=final['formal']['mandatory_pass'], mandatory_fail=final['formal']['mandatory_fail'],
                     runtime_sources=len(runtime_checks), inputs=len(INPUTS), wall_seconds=final['wall_seconds'])))
