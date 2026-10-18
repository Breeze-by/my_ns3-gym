"""Read-only dissection of the saved failed capture; no consumer or /proc rerun."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A25 = W / 'report/assets/20261018_mr3_p2a0_v25_smoother'
EP = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v25_interface/worker0/episode001_open_101'
D = Path(__file__).parent
bindings = {}
start = time.monotonic()


def read(path):
    path = Path(path)
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read()
        after = os.fstat(stream.fileno())
    identity = lambda value: [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]
    assert identity(before) == identity(after) == identity(path.stat())
    bindings[str(path)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'stat': identity(after)}
    return raw


def js(path):
    return json.loads(read(path))


proof_path = Path('/tmp/mr3_p2a0_v25_interface_smoother_mapping_035.json')
monitor_path = Path('/tmp/mr3_p2a0_v25_interface_process_monitor_035.json')
proof, monitor = js(proof_path), js(monitor_path)
source_path = A25 / 'independent/mr3_v25_smoother_custody_v1.py'
source = read(source_path)
assert hashlib.sha256(source).hexdigest() == proof['producer_source_sha256'] == '6edeb3a7e814fb024594be724ef98dce39e1d23a84af5d34d6d6faac0b5cb88b'
metadata, supervisor = js(EP / 'metadata.json'), js(EP / 'supervisor_metadata.json')
shutdown = js(EP / 'nav2_shutdown.json')
native_stop, supervisor_stop = js(EP / 'native_stop.json'), js(EP / 'supervisor_shutdown.json')
assert proof['monitor'] == {'path': str(monitor_path), 'sha256': bindings[str(monitor_path)]['sha256']}
assert proof['freeze'] == monitor['freeze'] == metadata['freeze']
assert proof['episodes'][0]['metadata_sha256'] == bindings[str(EP / 'metadata.json')]['sha256']
assert proof['episodes'][0]['supervisor_metadata_sha256'] == bindings[str(EP / 'supervisor_metadata.json')]['sha256']
assert proof['errors'] == ['process/ancestry/maps changed during capture']
assert proof['episodes'][0]['processes'] == {}
smooth = [row for row in monitor['owned_current_processes']
          if row['argv'] and Path(row['argv'][0]).name == 'velocity_smoother']
assert len(smooth) == 3
source_lines = source.decode().splitlines()
report = {
    'schema': 'mr3-v25-capture035-saved-input-review-v1',
    'freeze': proof['freeze'],
    'scope': 'Only saved immutable035/source/small identity and shutdown records. No new consumer, live /proc read, fixture, test, ROS/DDS or native execution.',
    'original_verdict_preserved': {'capture_passed': proof['passed'], 'errors': proof['errors'],
        'meaning': 'The formal mandatory failure is retained. Earlier successful captures do not erase this recorded error.'},
    'proved_from_saved_inputs': [
        'The producer is exact frozen6ede and proof035 references exact original monitor035 bytes.',
        'Episode epoch/worker/run-dir and two metadata SHA fields match saved immutable originals.',
        'Original monitor035 recorded all three actual smoother processes with canonical executable argv and their saved PID/start.',
        'The original A13 supplement recorded this exact worker active and all three controllers complete at its own capture.',
        'Only the compound post-check error is recorded; there is no failing robot or failing subcondition recorded.',
        'Process result insertion occurs after the compound check; processes={} therefore has no saved before/after maps or process/ancestry detail for the throwing candidate.'],
    'control_flow_implications_if_exact_source': [
        'At least one candidate reached source395–401; earlier fixed executable/core file path/hash/inode checks and before core map_lines validation succeeded for that candidate.',
        'after was neither None nor samePID/start with stateZ; those branches return pending at388–391.',
        'At least one compound conjunct evaluated false. With short-circuit evaluation, later conjuncts may not have been evaluated.',
        'The first original candidate is tb1; this does not prove tb1 threw, because earlier candidates can be skipped if gone/Z/no longer descendant before another candidate reaches this check.'],
    'compound_conjuncts_and_observability': [
        {'source_line': 395, 'condition': 'pair(after)==pair(identity)', 'native035_after_value_saved': False,
         'possible_failure_scope': 'PID reuse/identity change; a real hard custody failure cannot be waived'},
        {'source_line': 396, 'condition': 'entire fresh /proc/PID/maps bytes == maps_raw', 'native035_after_value_saved': False,
         'possible_failure_scope': 'Could be relevant core mapping change or unrelated heap/stack/anonymous VMA changes; no before/after smoother maps retained to distinguish'},
        {'source_line': 397, 'condition': 'fresh /proc/PID/cmdline bytes == raw_argv', 'native035_after_value_saved': False,
         'possible_failure_scope': 'Actual command/exec/closing state transition; no postvalue retained'},
        {'source_line': 398, 'condition': 'fresh /proc/PID/exe resolved target equals fixed executable', 'native035_after_value_saved': False,
         'possible_failure_scope': 'Executable identity change; must remain hard unless proven same-identity close without credit'},
        {'source_line': 399, 'condition': 'fresh /proc/PID/exe inode equals previously proved inode', 'native035_after_value_saved': False,
         'possible_failure_scope': 'Executable inode identity change; cannot assume harmless'},
        {'source_line': 400, 'condition': 'after ancestor chain equal by original identity_equal', 'native035_after_value_saved': False,
         'possible_failure_scope': 'Parent/worker disappearance/Z, reparenting or reuse; exact cause unavailable'}],
    'timing': {'original_monitor_wall_ns': monitor['wall_monotonic_ns'],
        'smoother_proof_wall_ns': proof['wall_monotonic_ns'],
        'nav2_shutdown_started_ns': shutdown['started_wall_monotonic_ns'],
        'nav2_shutdown_completed_ns': shutdown['completed_wall_monotonic_ns'],
        'capture_write_after_original_monitor_sec': (proof['wall_monotonic_ns'] - monitor['wall_monotonic_ns']) / 1e9,
        'shutdown_complete_after_original_monitor_sec': (shutdown['completed_wall_monotonic_ns'] - monitor['wall_monotonic_ns']) / 1e9,
        'proof_write_after_shutdown_complete_sec': (proof['wall_monotonic_ns'] - shutdown['completed_wall_monotonic_ns']) / 1e9,
        'smoother_finalized_response_end_ns': {row['robot']: next(state['completed_wall_monotonic_ns'] for state in row['states'] if state['node'] == 'velocity_smoother') for row in shutdown['robots']},
        'interpretation': 'The aggregate capture interval overlaps the final Nav2 shutdown/finalization boundary; this is temporal support for a lifecycle race hypothesis, not a unique branch diagnosis.'},
    'saved_actual_smoother_candidates_in_order': smooth,
    'saved_worker_identity': supervisor['worker_identity'],
    'small_closed_facts': {'native_stop': native_stop,
        'worker_returncode': supervisor_stop['worker_returncode'],
        'forced_shutdown': supervisor_stop['forced_shutdown'], 'failed_sample': supervisor_stop['failed_sample']},
    'not_proved': ['No unique heap VMA change or parent-chain closure cause is established.',
        'No actual identity/core/executable mismatch is excluded solely by previous complete captures.',
        'No retrospective PASS, changed formal verdict or proof replacement is warranted.'],
    'future_only_after_root_closed_GO': 'A small isolated fakeproc counterexample could test fullmaps equality under unrelated VMA change, and a separate one could test same-identity ancestor closing. Such CPU cases would establish a possible consumer false rejection, not identify which native035 branch fired. No such fixture was executed in this review.',
    'source_excerpt': {'path': str(source_path), 'first_line': 359, 'last_line': 415,
        'text': '\n'.join(f'{i + 1}: {source_lines[i]}' for i in range(358, 415))},
    'input_bindings': bindings,
    'argv': sys.argv, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'wall_seconds': time.monotonic() - start, 'writer_status': 'STOP after result exclusive write'}
for path, expected in list(bindings.items()):
    assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == expected['sha256']
    value = Path(path).stat()
    assert [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns] == expected['stat']
result = D / 'review_v1.json'
with result.open('x') as stream:
    json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
    stream.write('\n')
print(json.dumps({'path': str(result), 'sha256': hashlib.sha256(result.read_bytes()).hexdigest()}))
