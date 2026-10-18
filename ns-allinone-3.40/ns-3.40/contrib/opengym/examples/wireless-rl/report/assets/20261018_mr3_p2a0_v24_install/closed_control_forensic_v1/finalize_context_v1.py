import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time

D = Path('/tmp/mr3_p2a0_v24_model_fault_review_v1')
ROS = Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap')
EP = ROS / 'log/mr3_p2a0/mr3_p2a0_20261018_v24_interface/worker0/episode001_open_101'
started = time.monotonic()
bindings = {}


def stable(path):
    path = Path(path)
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    assert (before.st_size, before.st_mtime_ns, before.st_ino) == (
        after.st_size, after.st_mtime_ns, after.st_ino)
    bindings[str(path)] = {
        'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw),
        'stat': [after.st_size, after.st_mtime_ns, after.st_ino]}
    return raw


def write(name, value):
    with (D / name).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')


report = json.loads(stable(D / 'chain_review_v1.json'))
drive = [json.loads(line) for line in gzip.decompress(
    stable(D / 'drive_tb2_window.jsonl.gz')).splitlines()]
parameters = json.loads(stable(EP / 'actual_nav2_parameters.json'))
node = next(n for n in parameters['nodes'] if n['node'] == '/tb2/velocity_smoother')
write('actual_tb2_smoother_excerpt_v1.json', {
    'scope': 'Actual reset-hook parameter response, not an acceleration guarantee',
    'passed': parameters['passed'], 'epoch': parameters['epoch'], 'node': node,
    'input': bindings[str(EP / 'actual_nav2_parameters.json')]})

cpp = ROS / 'src/multi_robot/src/mr3_gazebo_diff_drive.cpp'
helper = ROS / 'src/multi_robot/include/multi_robot/paired_wheel_slew.hpp'
excerpts = {}
for path, windows in ((cpp, ((590, 691), (812, 825))), (helper, ((1, 105),))):
    raw = stable(path)
    lines = raw.decode().splitlines()
    excerpts[str(path)] = {
        'binding': bindings[str(path)],
        'windows': [{'first_line': first, 'last_line': min(last, len(lines)),
                     'text': '\n'.join(f'{i + 1}: {lines[i]}'
                                       for i in range(first - 1, min(last, len(lines))))}
                    for first, last in windows]}
write('driver_source_excerpts_v1.json', excerpts)

commands = [row for row in drive if row['kind'] == 'command_received']
first_mixed = next(row for row in commands
                   if row['sim_time_ns'] >= 55000000000 and row['desired_v'] > 0)
previous = next(row for row in commands if row['cmd_seq'] == first_mixed['cmd_seq'] - 1)
dt = (first_mixed['target_clock_ns'] - previous['target_clock_ns']) / 1e9
assert dt > 0
peak = report['same_clock_peak_actuation'][0]
raw_body = report['raw_own_original']
write('context_summary_v1.json', {
    'schema': 'mr3-v24-bounded-actuation-context-v1',
    'freeze': report['freeze'],
    'scope': 'Posthoc closed-log description only; no formal rerun or repair validation',
    'base_report': {'path': str(D / 'chain_review_v1.json'),
                    **bindings[str(D / 'chain_review_v1.json')]},
    'trigger_math': report['trigger_math'],
    'driver_configuration': report['driver_configuration'],
    'all_incoming_targets_within_caps': report['actual_incoming_commands'],
    'all_window_actuations_match_latest_received_tuple':
        report['latest_received_tuple_matches_every_window_actuation'],
    'phase': {
        'actual_second_goal_command': next(row for row in report['actual_returned_action_records']
                                           if row['command']['created_at'] == 55.0),
        'pure_turn_desired': {'first_actuation_ns': 55574000000,
                              'last_actuation_ns': 56662000000, 'v': 0.0, 'w': -0.8},
        'first_forward_mixed_command': first_mixed,
        'immediately_previous_command': previous,
        'observed_target_delta': {'target_clock_dt_sec': dt,
            'dv_over_dt_mps2': (first_mixed['desired_v'] - previous['desired_v']) / dt,
            'dw_over_dt_radps2': (first_mixed['desired_w'] - previous['desired_w']) / dt,
            'scope': 'Actual received target finite difference, not measured body acceleration'},
        'nonzero_angular_signs': sorted(set(math.copysign(1, row['desired_w'])
                                          for row in commands if row['desired_w'] != 0)),
        'first_fault_zero_storage': report['first_zero_storage_after_fault']},
    'same_clock_peak_actuation': peak,
    'raw_body_source_ref': raw_body,
    'interpretation': [
        'The angular violation occurs during pure-CW to forward-CW transition, while demanded yaw magnitude is decreasing; this window has no demanded angular sign reversal.',
        'The first zero storage is at 56.98 after the 56.968 odometry sample, so it cannot be the preceding cancel cause of that sample.',
        'Current wheel yaw proxy and actual body yaw exceed 1.2 while desired yaw is -0.378947; applied wheel yaw proxy remains -1.101559 because the limiter starts from measured current wheel rims.',
        'The paired rim limiter bounds its instruction displacement from measured joint speed; it does not establish the measured body yaw limit.',
        'WorldAngularVel().Z is copied directly to odometry angular.z; float yaw conversion is only used for linear x/y.',
        'Actual OPEN_LOOP smoother settings are nominal .5/3.2 at 20Hz; observed received target differences do not obey those values as a sim-time target-slew theorem.',
        'This evidence does not uniquely separate contact, slip, servo or numerical dynamics and does not prove a new angular cap or new ramp sufficient.'],
    'prospective_repair_comparison_scope': [
        'A smaller angular command cap is the narrower profile change but must be consistent across Shim, DWB, smoother, guard and actual parameter/source audit; its body-bound sufficiency still needs the new same-freeze full matrix.',
        'An actual sim-time target ramp would address the observed 20ms target jumps explicitly, but is a larger actuator/control contract change with new initial/reset/stop treatment; a nominal smoother readback alone cannot supply that proof.',
        'No change to measured .30/1.2/7 bounds, original stopping test, goal selection or failure attribution is implied.'],
    'additional_bindings': bindings,
    'argv': sys.argv, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'wall_seconds': time.monotonic() - started})

for name in ('actual_tb2_smoother_excerpt_v1.json', 'driver_source_excerpts_v1.json',
             'context_summary_v1.json'):
    stable(D / name)
files = []
for path in sorted(D.iterdir()):
    if path.is_file():
        raw = stable(path)
        files.append({'path': str(path), 'name': path.name,
                      'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
write('handoff_v1.json', {
    'schema': 'mr3-v24-model-fault-posthoc-handoff-v1',
    'freeze': report['freeze'], 'writer_status': 'STOP after this exclusive handoff write',
    'files': files, 'files_count': len(files), 'bytes': sum(row['bytes'] for row in files),
    'self_excluded': True,
    'scope': 'All files are TMP posthoc evidence; original initial extraction failure is retained. No native/formal rerun, canonical edit or repair validation.',
    'inputs_stat_sha_verified': True,
    'original_large_inputs': report['input_bindings'],
    'no_additional_large_raw_scan': True})
print(json.dumps({'handoff': str(D / 'handoff_v1.json'),
                  'sha256': hashlib.sha256((D / 'handoff_v1.json').read_bytes()).hexdigest(),
                  'files': len(files), 'bytes': sum(row['bytes'] for row in files)}))
