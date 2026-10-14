from pathlib import Path
import datetime
import hashlib
import json
import os
import shlex
import subprocess
import sys

root = Path('/home/zhuyulab/ns3-workspace')
base = root / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
assets = base / 'report/assets/20261014_mr3_p1a'
plan = json.loads((assets / 'predeclared_native_plan.json').read_text())
case = (plan['contact_fixture_retries'][-1] if sys.argv[1] == 'fixture'
        else (plan['development_matrix_retries'][-1]['batches'][int(sys.argv[1])]
              if plan.get('development_matrix_retries')
              else plan['development_batches'][int(sys.argv[1])]))
assert not subprocess.check_output(['git', 'diff', '--',
    'ros2_ws/ros2-multi-robot-automap/src', 'ros2_ws/ros2-multi-robot-automap/scripts'], cwd=root)
freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
assert freeze == subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=root, text=True).strip()
environment = dict(os.environ, ROS_DOMAIN_ID=str(case['ros_domain_id']),
                   GAZEBO_MASTER_URI=f"http://127.0.0.1:{case['gazebo_port']}")
binding = {}
if sys.argv[1] != 'fixture' and plan['development_matrix_retries'][-1]['version'] == 4:
    manifest_path = assets / 'runtime_component_manifest_matrix4.json'
    manifest = json.loads(manifest_path.read_text())
    assert manifest['source_freeze'] == freeze
    for item in manifest['files']:
        assert hashlib.sha256(Path(item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
    binding = dict(runtime_component_manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                   runtime_component_manifest=str(manifest_path),
                   schedule=plan['development_matrix_retries'][-1]['schedule'])
with (assets / (case['run_id'] + '_invocation.json')).open('x') as output:
    json.dump(dict(case, source_freeze=freeze, **binding), output, indent=2)
with (base / 'log.md').open('a') as output:
    output.write('\n### MR3-P1A native attempt ' + case['run_id'] + '\n\n- Freeze: ' + freeze +
                 ' committed/pushed; fixed3robots, exact contract, no RL/network credit.\n' +
                 '- Environment: system ROS Humble; PYTHONNOUSERSITE=1; rmw_fastrtps_cpp; ROS_LOCALHOST_ONLY=1; ' +
                 'ROS_DOMAIN_ID=' + str(case['ros_domain_id']) + '; GAZEBO_MASTER_URI=' +
                 environment['GAZEBO_MASTER_URI'] + '.\n- Command (canonical ROS root):\n\n```bash\n' +
                 shlex.join(case['command']) + '\n```\n\n- Result pending at invocation; all native output retained.\n')
returncode = subprocess.run(case['command'], env=environment).returncode
result_path = (Path(case['output_dir']) / 'fixture_result.json' if sys.argv[1] == 'fixture'
               else Path(case['command'][-1]) / case['run_id'] / 'summary.json')
result = json.loads(result_path.read_text()) if result_path.exists() else {}
with (base / 'log.md').open('a') as output:
    output.write('\n- Finished ' + datetime.datetime.now(datetime.timezone.utc).isoformat() +
                 '; rc=' + str(returncode) + '; result=' + str(result_path) + '; success=' +
                 str(result.get('success')) + '; error=' + str(result.get('error')) +
                 '. All native JSON/log/failures retained.\n')
raise SystemExit(returncode)
