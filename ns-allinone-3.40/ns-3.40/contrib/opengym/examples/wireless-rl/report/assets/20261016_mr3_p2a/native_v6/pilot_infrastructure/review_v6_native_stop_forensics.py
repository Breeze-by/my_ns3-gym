"""Read-only exact V6 shutdown cause ordering; no replay or gate replacement."""

import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path('/home/zhuyulab/ns3-workspace')
RUN = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v6_pilot'
NATIVE = RUN / 'native/round0000/worker0/episode001_open_101'
FREEZE = 'af37b2aaa3cb9980434f7f16c1f52dec2506319d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    log = (NATIVE / 'launch.log').read_text()
    records = []
    for number, line in enumerate(log.splitlines(), 1):
        marker = 'MR3_ORDERED_SHUTDOWN '
        if marker in line:
            records.append({'line': number, **json.loads(line.split(marker, 1)[1])})
    errors = [row for row in records if row['event'] == 'error']
    assert len(errors) == 1 and errors[0]['reason'] == 'nonzero_process_exit'
    failure = errors[0]
    assert failure['process_name'] == 'multirobot_slam_toolbox_node-7'
    assert failure['pid'] == 1438806 and failure['returncode'] == -6
    affected = [row for row in records if row.get('pid') == failure['pid']]
    assert [row['event'] for row in affected] == ['process_started', 'signal', 'process_exited', 'error']
    assert affected[1]['signal'] == 'SIGINT' and affected[1]['signal_sequence'] == 27
    assert affected[2]['returncode'] == -6 and affected[2]['controlled'] is True
    assert not any(row['event'] in ('ros_complete', 'gz_stop') for row in records)
    cli = re.findall(r'\[INFO\] \[mr3_gazebo_native_stop-(\d+)\]: '
                     r'process started with pid \[(\d+)\]', log)
    assert cli == []
    selected = [{'line': number, 'text': line} for number, line in enumerate(log.splitlines(), 1)
                if ('karto::Exception' in line or 'MR3_ROS_SHUTDOWN_ERROR' in line
                    or ('multirobot_slam_toolbox_node-7' in line and 'process has died' in line)
                    or ('gzserver-' in line and 'process has finished cleanly' in line))]
    assert any('karto::Exception' in row['text'] for row in selected)
    paths = [ROOT / 'ros2_ws/ros2-multi-robot-automap' / relative for relative in (
        'scripts/run_mr3_adapter_probe.py', 'scripts/mr3_env_worker.py',
        'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py')]
    source_proof = {}
    for path in paths:
        relative = str(path.relative_to(ROOT))
        frozen = subprocess.check_output(['git', 'show', FREEZE + ':' + relative], cwd=ROOT)
        assert path.read_bytes() == frozen
        source_proof[relative] = {'sha256': sha(path), 'git_source': FREEZE + ':' + relative}
    result = {'schema': 'mr3-independent-v6-native-stop-forensics-v1', 'freeze': FREEZE,
              'source_proof': source_proof, 'ordered_failure': failure,
              'failed_owned_process_lifecycle': affected, 'exact_log_lines': selected,
              'native_cli_start_identity_matches': cli, 'native_stop_receipt_present':
                  (NATIVE / 'native_stop.json').exists(),
              'worker_summary_present': (NATIVE / 'summary.json').exists(),
              'causal_diagnosis': [
                  'After actual Nav2 finalization, ordered shutdown signals tb1 SLAM with SIGINT '
                  'at sequence27; its controlled exit is -6 after a logged karto::Exception.',
                  'Frozen OrderedRosShutdown.exited treats any owned_ros nonzero exit as failure; '
                  'fail marks phase failed and emits launch Shutdown instead of next_process.',
                  'Native gz stop CLI is only created after serial ROS queue completion. No '
                  'ros_complete/gz_stop or native CLI start occurs. Later gzserver clean exit is '
                  'fallback launch shutdown, not the required native-stop lifecycle.',
                  'Worker native_stop_receipt raises on zero start identities before writing '
                  'native_stop.json or worker summary; the final native transition was written '
                  'before shutdown_episode, so raw300th record has no returned collector sample.'],
              'uncertainty': 'The log identifies uncaught karto::Exception/abort during SIGINT '
                             'shutdown. It does not establish the internal exception cause or '
                             'prove a FastDDS failure/fix.',
              'verdict': 'Genuine infrastructure failure; no gate repair, suppression or reuse '
                         'as valid terminal learning/95% evidence.',
              'launch_log_sha256': sha(NATIVE / 'launch.log'),
              'closure_review_sha256': sha(RUN / 'independent_pilot_closure_review_v6.json'),
              'repro_script_sha256': sha(Path(__file__).resolve())}
    target = RUN / 'independent_native_stop_forensics_v6.json'
    with target.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(target), 'sha256': sha(target), 'diagnosis': failure}))


if __name__ == '__main__':
    main()
