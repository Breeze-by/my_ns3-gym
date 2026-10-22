"""Fresh imports and device metadata only; no World, policy or GPU workload."""

import argparse
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def imports(names, base):
    result = []
    for name in names:
        module = importlib.import_module(name)
        path = Path(module.__file__).resolve()
        expected = base / (name.replace('.', '/') + '.py')
        if path != expected:
            raise ValueError('noncanonical module import: ' + name + ': ' + str(path))
        raw = path.read_bytes()
        result.append({'module': name, 'path': str(path), 'bytes': len(raw),
                       'sha256': hashlib.sha256(raw).hexdigest()})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=('ros', 'learner', 'both'), default='both')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.mode == 'ros':
        if sys.executable != '/usr/bin/python3':
            raise ValueError('ROS must use system Python')
        modules = imports(['multi_robot_exploration.' + name for name in (
            'mr3_observation', 'mr3_seed_certificate', 'mr3_point_graph',
            'mr3_adapter', 'mr3_reach_runtime')], ROS / 'src/multi_robot_exploration')
        import rclpy
        value = {'schema': 'mr3-v40-ros-import-readiness-v1', 'passed': True,
                 'python': sys.executable, 'modules': modules,
                 'rclpy_path': rclpy.__file__, 'world_started': False,
                 'ros_nodes_created': False}
    elif args.mode == 'learner':
        if Path(sys.executable).resolve() != Path(PYTHON).resolve():
            raise ValueError('learner must use ns3gym Python')
        import torch
        import stable_baselines3
        import sb3_contrib
        if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise ValueError('cuda:0 unavailable; do not silently fall back to CPU')
        modules = imports(['mr3_learning.' + name for name in (
            'ppo', 'reach_preparation', 'reach_policy_chain', 'supervisor')], WIRELESS)
        value = {'schema': 'mr3-v40-learner-device-readiness-v1', 'passed': True,
                 'python': sys.executable, 'torch_version': torch.__version__,
                 'torch_cuda_version': torch.version.cuda,
                 'sb3_version': stable_baselines3.__version__,
                 'sb3_contrib_version': sb3_contrib.__version__,
                 'cuda_available': True, 'visible_cuda_devices': torch.cuda.device_count(),
                 'device': 'cuda:0', 'device_name': torch.cuda.get_device_name(0),
                 'modules': modules, 'world_started': False,
                 'model_constructed': False, 'forward_calls': 0,
                 'backward_calls': 0, 'optimizer_steps': 0}
    else:
        output = args.output
        ros_output = output.with_name('readiness_ros_v1.json')
        learner_output = output.with_name('readiness_learner_v1.json')
        for path in (output, ros_output, learner_output):
            if path.exists():
                raise ValueError('exclusive readiness output exists: ' + str(path))
        script = str(Path(__file__).resolve())
        setup = ('source /opt/ros/humble/setup.bash && source '
                 + str(ROS / 'install/setup.bash') + ' && exec /usr/bin/python3 -B '
                 + script + ' --mode ros --output ' + str(ros_output))
        commands = [
            ['/usr/bin/bash', '--noprofile', '--norc', '-e', '-c', setup],
            [PYTHON, '-B', script, '--mode', 'learner', '--output', str(learner_output)],
        ]
        for command in commands:
            subprocess.run(command, cwd=WIRELESS, check=True)
        value = {'schema': 'mr3-v40-cpu-import-device-readiness-v1', 'passed': True,
                 'scope': 'artificial CPU/import/device metadata only; no native qualification credit',
                 'commands': commands, 'results': [json.loads(path.read_text())
                                                   for path in (ros_output, learner_output)],
                 'engineering_increment_seconds': '0', 'world_started': False,
                 'model_constructed': False, 'forward_calls': 0,
                 'backward_calls': 0, 'optimizer_steps': 0}
    write(args.output, value)
    print(json.dumps({'mode': args.mode, 'passed': True}))


if __name__ == '__main__':
    main()
