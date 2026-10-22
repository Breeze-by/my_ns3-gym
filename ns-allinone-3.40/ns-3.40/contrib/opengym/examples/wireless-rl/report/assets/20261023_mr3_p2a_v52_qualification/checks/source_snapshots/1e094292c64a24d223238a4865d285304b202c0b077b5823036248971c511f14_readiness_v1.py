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
PACKAGE = 'report.assets.20261023_mr3_p2a_v52_qualification'


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



def system_reader_definitions():
    """Actually load canonical fixed definitions/pins; no telemetry or audit call.

    CPU preparation may precede the future commit. Only formal preflight can
    call source_proof/verify_reader_readiness against that new execution Git.
    """
    records = imports(['mr3_learning.' + name for name in (
        'audit_reach_runtime', 'audit_reach_cadence', 'audit_reach_reset_workload',
        'reach_audit_projection', 'reach_support_replay')], WIRELESS)
    from mr3_learning import audit_reach_runtime as runtime
    from mr3_learning import audit_reach_cadence as cadence
    from mr3_learning import audit_reach_reset_workload as reset
    if not callable(runtime.source_proof) or not callable(runtime.audit_episode):
        raise ValueError('runtime source/audit definitions absent')
    if runtime.geometry_rule({'safety_contract':'mr3-reach-v1',
                              'reach_geometry_rule':'cone-support-v2'}) != 'cone-support-v2':
        raise ValueError('actual runtime support dispatch differs')
    cadence_module, cadence_proof = cadence.load_implementation(ROOT)
    if (cadence_module.PERIOD != 20_000_000 or cadence_module.ACTUATION != 34_000_000
            or not cadence_proof['projection']['exact_whole_source_inverse']):
        raise ValueError('actual cadence loader/constants/inverse differ')
    readers = []
    for kind in ('angular', 'physics'):
        module, proof = reset.load_reader(kind)
        relative, expected = reset.SOURCES[kind]
        if (module.PROBE_VERSION != reset.PROBE_VERSION or module.__file__ != str(ROOT/relative)
                or proof['source_sha256'] != expected or proof['inverse_sha256'] != expected
                or proof['whole_source_inverse_equal'] is not True
                or proof['literal_changes'] != [{'before':reset.CHANGE[0], 'after':reset.CHANGE[1], 'count':1}]):
            raise ValueError('actual reset loader/constant/full inverse differs: '+kind)
        leaf_relative, leaf_sha = reset.LEAVES[kind]
        if module.CONSUMER_SHA256 != leaf_sha:
            raise ValueError('actual reset leaf pin differs')
        leaf, leaf_proof = reset.project_file(ROOT/leaf_relative, leaf_sha, ())
        if not callable(module.audit) or not callable(leaf.audit_episode):
            raise ValueError('actual reset/leaf definitions absent')
        readers.append({'kind':kind, 'probe_version':module.PROBE_VERSION,
            'immutable_reader_projection':proof, 'unchanged_leaf_source':leaf_proof})
    return {'schema':'mr3-v52-system-reader-definitions-readiness-v1', 'passed':True,
        'modules':records, 'cadence':cadence_proof, 'reset_readers':readers,
        'runtime_source_proof_definition_present':True,
        'formal_git_source_proof_executed':False,
        'formal_git_source_proof_required_in_preflight':True,
        'native_inputs_read':False, 'audit_calls':0, 'world_or_qualification_credit':False}


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
            'mr3_adapter', 'mr3_reach_runtime', 'mr3_reach_support')], ROS / 'src/multi_robot_exploration')
        modules.extend(imports(['merge_map.merge_map'], ROS / 'src/merge_map'))
        import rclpy
        reader_definitions = system_reader_definitions()
        value = {'schema': 'mr3-v52-ros-import-readiness-v1', 'passed': True,
                 'python': sys.executable, 'modules': modules,
                 'rclpy_path': rclpy.__file__, 'reader_definitions': reader_definitions, 'world_started': False,
                 'ros_nodes_created': False}
    elif args.mode == 'learner':
        if Path(sys.executable).resolve() != Path(PYTHON).resolve():
            raise ValueError('learner must use ns3gym Python')
        # A directly executed asset script starts with its own directory on
        # sys.path. Add only the canonical learner root, never ROS Python paths.
        sys.path.insert(0, str(WIRELESS))
        import torch
        import stable_baselines3
        import sb3_contrib
        if not torch.cuda.is_available() or torch.cuda.device_count() < 1:
            raise ValueError('cuda:0 unavailable; do not silently fall back to CPU')
        modules = imports(['mr3_learning.' + name for name in (
            'ppo', 'reach_preparation', 'reach_policy_chain', 'supervisor',
            'audit_reach_runtime', 'reach_support_replay', 'audit_reach_reset_workload',
            'audit_reach_preparation', 'audit_reach_ppo')], WIRELESS)
        value = {'schema': 'mr3-v52-learner-device-readiness-v1', 'passed': True,
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
        ros_output = output.with_name(output.stem + '_ros.json')
        learner_output = output.with_name(output.stem + '_learner.json')
        for path in (output, ros_output, learner_output):
            if path.exists():
                raise ValueError('exclusive readiness output exists: ' + str(path))
        script = str(Path(__file__).resolve())
        setup = ('source /opt/ros/humble/setup.bash && source '
                 + str(ROS / 'install/setup.bash') + ' && exec /usr/bin/python3 -B -m '
                 + PACKAGE + '.readiness_v1 --mode ros --output ' + str(ros_output))
        commands = [
            ['/usr/bin/bash', '--noprofile', '--norc', '-e', '-c', setup],
            [PYTHON, '-B', '-m', PACKAGE+'.readiness_v1', '--mode', 'learner', '--output', str(learner_output)],
        ]
        for command in commands:
            subprocess.run(command, cwd=WIRELESS, check=True)
        value = {'schema': 'mr3-v52-cpu-import-device-readiness-v1', 'passed': True,
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
