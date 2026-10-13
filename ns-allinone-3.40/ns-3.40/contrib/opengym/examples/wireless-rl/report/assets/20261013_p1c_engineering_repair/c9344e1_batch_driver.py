"""Run the predeclared engineering regression cases on one clean freeze."""
import datetime
import json
import os
from pathlib import Path
import subprocess

root = Path.cwd()
audit = root / 'log/p1c_repair_local_20261014'
audit.mkdir(parents=True, exist_ok=False)
source = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
assert not subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
records = []
failed = False
cases = [('4r_motion', 4, 'my_world.world', 'motion'),
         ('2r_original', 2, 'my_world.world', 'task'),
         ('3r_rooms', 3, 'p1c_rooms.world', 'task'),
         ('3r_corridors', 3, 'p1c_corridors.world', 'task'),
         ('4r_plain', 4, 'my_world.world', 'plain')]
for i, (case, count, world, mode) in enumerate(cases):
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == source
    env = os.environ.copy()
    env.update(ROS_DOMAIN_ID=str(194 + i), GAZEBO_MASTER_URI=f'http://127.0.0.1:{11763+i}')
    run_id = '20261014_p1c_repair_local_' + case
    if mode == 'task':
        out = root / 'log/ideal_baseline' / run_id
        command = ['/usr/bin/python3', 'scripts/run_ideal_baseline.py', '--world', world,
                   '--robot-count', str(count), '--seeds', '101', '--duration', '180',
                   '--coverage-threshold', '0.90', '--startup-timeout', '300',
                   '--evaluation-wait-timeout', '360', '--message-timeout', '90',
                   '--shutdown-timeout', '60', '--run-id', run_id]
    else:
        out = audit / run_id
        out.mkdir()
        command = ['/usr/bin/python3', 'scripts/ros_smoke_test.py', '--robot-count', str(count),
                   '--world', world, '--gazebo-seed', '101', '--startup-timeout', '300',
                   '--message-timeout', '90', '--shutdown-timeout', '60',
                   '--log-dir', str(out / 'launch_logs')]
        if mode == 'motion':
            command += ['--evaluation-duration', '20', '--coverage-threshold', '0.90',
                        '--evaluation-wait-timeout', '360', '--evaluation-output-dir',
                        str(out / 'episodes'), '--episode-id', run_id]
    record = {'case': case, 'source_commit': source, 'command': command,
              'ros_localhost_only': env['ROS_LOCALHOST_ONLY'],
              'rmw_implementation': env['RMW_IMPLEMENTATION'],
              'ros_domain_id': env['ROS_DOMAIN_ID'], 'gazebo_master_uri': env['GAZEBO_MASTER_URI'],
              'output_dir': str(out), 'started_wall_time': datetime.datetime.now().isoformat()}
    records.append(record)
    (audit / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
    print('START', case, flush=True)
    with (audit / (run_id + '.console.log')).open('x') as console:
        process = subprocess.Popen(command, stdout=console, stderr=subprocess.STDOUT,
                                   text=True, env=env)
        rc = process.wait()
    record.update(returncode=rc, finished_wall_time=datetime.datetime.now().isoformat())
    print('FINISH', case, 'return', rc, flush=True)
    results = []
    for path in out.rglob('*.json'):
        item = json.loads(path.read_text())
        if 'schema_version' in item:
            results.append(item)
    if results:
        result = results[0]
        summary = {k: result[k] for k in ('termination_reason', 'elapsed_sim_time_sec',
                                         'correct_free_coverage_ratio', 'observed_accuracy',
                                         'collision_events', 'collision_monitoring_active',
                                         'control_failure', 'total_path_length_m')}
        summary['paths'] = {n: r['path_length_m'] for n, r in result['robots'].items()}
        record['native_summary'] = summary
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    (audit / 'commands.json').write_text(json.dumps(records, indent=2) + '\n')
    failed |= rc != 0
    if mode == 'motion':
        if (rc or not results or result['termination_reason'] not in ('timeout', 'coverage_reached')
                or result['collision_events'] or not result['collision_monitoring_active']
                or not all(r['path_length_m'] > .25 for r in result['robots'].values())):
            print('Motion/closure gate FAIL; later cases not run', flush=True)
            raise SystemExit(1)
print('BATCH COMPLETE', 'FAIL' if failed else 'PASS', flush=True)
raise SystemExit(1 if failed else 0)
