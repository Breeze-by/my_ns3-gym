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
PACKAGE = 'report.assets.20261024_mr3_p2a_v65_owned_stream_qualification'


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
        'reach_audit_projection', 'reach_support_replay', 'initial_encoder_replay', 'native_custody_reach',
        'motion_authority_profile', 'motion_authority_audit')], WIRELESS)
    from mr3_learning import initial_encoder_replay as motor
    from mr3_learning import native_custody_reach as custody
    from mr3_learning import audit_reach_runtime as runtime
    from mr3_learning import audit_reach_cadence as cadence
    from mr3_learning import audit_reach_reset_workload as reset
    from mr3_learning import motion_authority_profile as authority_profile
    from mr3_learning import motion_authority_audit as authority_audit
    if (authority_profile.motion_authority_profile_for_safety_contract('mr3-reach-v1') != 'mr3-owned-stream-authority-v1'
            or authority_profile.motion_authority_profile_for_safety_contract('legacy') is not None
            or not callable(authority_audit.replay_motion) or not callable(authority_audit.replay_adapter)
            or not callable(authority_audit.original_protocol_class)):
        raise ValueError('actual independent authority source/profile/replay definitions absent')
    if not callable(runtime.source_proof) or not callable(runtime.audit_episode):
        raise ValueError('runtime source/audit definitions absent')
    if runtime.geometry_rule({'safety_contract':'mr3-reach-v1',
                              'reach_geometry_rule':'cone-support-v2'}) != 'cone-support-v2':
        raise ValueError('actual runtime support dispatch differs')
    if (not callable(motor.replay_native_drive) or not callable(motor.check_applied_receipt)
            or motor.PROFILE != 'initial-zero-encoder-hold-v1'
            or not callable(custody.verify_binding)):
        raise ValueError('actual new actuator source/build/replay definitions absent')
    cadence_module, cadence_proof = cadence.load_implementation(ROOT, actuation_profile=motor.PROFILE)
    if (cadence_module.PERIOD != 20_000_000 or cadence_module.ACTUATION != 34_000_000
            or not cadence_proof['projection']['exact_whole_source_inverse']):
        raise ValueError('actual cadence loader/constants/inverse differ')
    workload_profile,probe_version,change = reset.profile_spec(reset.PROFILE_V2)
    readers = []
    for kind in ('angular', 'physics'):
        module, proof = reset.load_reader(kind, workload_profile=workload_profile)
        relative, expected = reset.SOURCES[kind]
        if (module.PROBE_VERSION != probe_version or module.__file__ != str(ROOT/relative)
                or proof['source_sha256'] != expected or proof['inverse_sha256'] != expected
                or proof['whole_source_inverse_equal'] is not True
                or proof['literal_changes'] != [{'before':change[0], 'after':change[1], 'count':1}]):
            raise ValueError('actual reset loader/constant/full inverse differs: '+kind)
        leaf_relative, leaf_sha = reset.LEAVES[kind]
        if module.CONSUMER_SHA256 != leaf_sha:
            raise ValueError('actual reset leaf pin differs')
        leaf, leaf_proof = reset.project_file(ROOT/leaf_relative, leaf_sha, ())
        if not callable(module.audit) or not callable(leaf.audit_episode):
            raise ValueError('actual reset/leaf definitions absent')
        readers.append({'kind':kind, 'probe_version':module.PROBE_VERSION,
            'immutable_reader_projection':proof, 'unchanged_leaf_source':leaf_proof})
    return {'schema':'mr3-v65-system-reader-definitions-readiness-v1', 'passed':True,
        'modules':records, 'cadence':cadence_proof, 'reset_readers':readers,
        'reset_workload_reader_profile':workload_profile, 'preparation_probe_version':probe_version,
        'motion_authority_profile':authority_profile.MOTION_AUTHORITY_PROFILE,
        'independent_authority_replay_definitions_present':True,
        'runtime_source_proof_definition_present':True, 'actuation_profile':motor.PROFILE,
        'compound_motor_replay_definitions_present':True, 'newbuild_binding_verifier_present':True,
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
            'mr3_adapter', 'mr3_motion_authority', 'mr3_reach_runtime', 'mr3_reach_support', 'mr3_safety_intent')], ROS / 'src/multi_robot_exploration')
        modules.extend(imports(['merge_map.merge_map'], ROS / 'src/merge_map'))
        from multi_robot_exploration.mr3_safety_intent import actuation_profile_for_safety_contract
        if (actuation_profile_for_safety_contract('mr3-reach-v1') != 'initial-zero-encoder-hold-v1'
                or actuation_profile_for_safety_contract('legacy') is not None):
            raise ValueError('actual ROS automatic actuation selection differs')
        import rclpy
        reader_definitions = system_reader_definitions()
        value = {'schema': 'mr3-v65-ros-import-readiness-v1', 'passed': True,
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
            'audit_reach_preparation', 'audit_reach_ppo', 'initial_encoder_replay', 'native_custody_reach',
            'motion_authority_profile', 'motion_authority_audit')], WIRELESS)
        from mr3_learning.supervisor import actuation_profile_for_safety_contract
        if (actuation_profile_for_safety_contract('mr3-reach-v1') != 'initial-zero-encoder-hold-v1'
                or actuation_profile_for_safety_contract('legacy') is not None):
            raise ValueError('actual learner automatic actuation selection differs')
        value = {'schema': 'mr3-v65-learner-device-readiness-v1', 'passed': True,
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
        value = {'schema': 'mr3-v65-cpu-import-device-readiness-v1', 'passed': True,
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
