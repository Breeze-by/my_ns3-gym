"""Disabled world/spec generator. No Gazebo load, compiler, ROS or model runs.

Only the two declared worlds are generated. Source physical subtrees are checked
identically after removing only plugins, sensors and visuals. The explicit
installed ground is this diagnostic's choice, not a claim about V52 resolution.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
MODEL = ROS / 'src/multi_robot/models/turtlebot3_waffle/model.sdf'
GROUND = Path('/usr/share/gazebo-11/models/ground_plane/model.sdf')
HEADER = ROS / 'src/multi_robot/include/multi_robot/paired_wheel_slew.hpp'
DRIVE = ROS / 'src/multi_robot/src/mr3_gazebo_diff_drive.cpp'
SPAWNS = (('tb1', (0, -.45, .01, 0, 0, 0)),
          ('tb2', (0, .45, .01, 0, 0, 0)),
          ('tb3', (.45, 0, .01, 0, 0, 0)))
ARMS = (('quick150', 'quick150.world', 'quick'),
        ('direct-world', 'direct_world.world', 'world'))
REMOVED = frozenset(('plugin', 'sensor', 'visual'))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def source(path):
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, key) != getattr(after, key) for key in fields):
        raise ValueError('source changed during read: ' + str(path))
    return raw, {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw)}


def stripped(element):
    result = copy.deepcopy(element)
    for parent in result.iter():
        for child in list(parent):
            if child.tag in REMOVED:
                parent.remove(child)
    return result


def physical_tree(element):
    """Preserve all attributes/text/order except model name/initial model pose."""
    item = stripped(element)
    item.attrib.pop('name', None)
    pose = item.find('pose')
    if pose is not None:
        item.remove(pose)

    def tree(node):
        return (node.tag, tuple(sorted(node.attrib.items())),
                (node.text or '').strip(), tuple(tree(child) for child in node))
    return tree(item)


def make_world(model, ground, solver):
    root = ET.Element('sdf', version='1.6')
    world = ET.SubElement(root, 'world', name='mr3_passive_zero')
    ET.SubElement(world, 'gravity').text = '0 0 -9.8'
    physics = ET.SubElement(world, 'physics', name='ode', type='ode')
    ET.SubElement(physics, 'max_step_size').text = '0.001'
    ET.SubElement(physics, 'real_time_update_rate').text = '0'
    ode = ET.SubElement(physics, 'ode')
    spec = ET.SubElement(ode, 'solver')
    ET.SubElement(spec, 'type').text = solver
    ET.SubElement(spec, 'iters').text = '150'  # ignored by direct world, explicitly identical
    world.append(stripped(ground))
    for name, pose in SPAWNS:
        item = stripped(model)
        item.set('name', name)
        old = item.find('pose')
        if old is not None:
            item.remove(old)
        ET.SubElement(item, 'pose').text = ' '.join(str(value) for value in pose)
        if physical_tree(item) != physical_tree(model):
            raise ValueError('canonical body physical tree changed')
        world.append(item)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.output.is_absolute():
        raise ValueError('absolute exclusive output directory required')
    raw_model, model_ref = source(MODEL)
    raw_ground, ground_ref = source(GROUND)
    _, header_ref = source(HEADER)
    _, drive_ref = source(DRIVE)
    _, generator_ref = source(Path(__file__).resolve())
    _, cpp_ref = source(Path(__file__).with_name('passive_plant_v1.cpp').resolve())
    model = ET.fromstring(raw_model).find('model')
    ground = ET.fromstring(raw_ground).find('model')
    if model is None or ground is None:
        raise ValueError('canonical model/ground source shape differs')
    drive = model.find("plugin[@name='turtlebot3_diff_drive']")
    expected = {'update_rate': '30', 'left_joint': 'wheel_left_joint',
                'right_joint': 'wheel_right_joint', 'wheel_separation': '0.287',
                'wheel_diameter': '0.066', 'max_wheel_torque': '20',
                'max_wheel_acceleration': '1.0'}
    if drive is None or any(drive.findtext(key) != value for key, value in expected.items()):
        raise ValueError('canonical drive parameters differ')
    if any(item.find('static') is not None and item.findtext('static') == 'true'
           for item in [model]):
        raise ValueError('canonical body unexpectedly static')
    worlds = [(arm, filename, make_world(model, ground, solver))
              for arm, filename, solver in ARMS]
    # Arm worlds must differ ONLY by their ode solver child subtree.
    roots = [ET.fromstring(raw) for _, _, raw in worlds]
    for item in roots:
        solver = item.find('world/physics/ode/solver')
        item.find('world/physics/ode').remove(solver)
    if ET.tostring(roots[0]) != ET.tostring(roots[1]):
        raise ValueError('arm worlds differ outside solver subtree')
    args.output.mkdir(exist_ok=False)
    references = []
    for arm, filename, raw in worlds:
        path = args.output / filename
        with path.open('xb') as stream:
            stream.write(raw)
        references.append({'arm': arm, 'path': str(path), 'sha256': sha(raw), 'bytes': len(raw)})
    result = {
        'schema': 'mr3-v57-passive-plant-spec-v1', 'status': 'PREPARED_NOT_EXECUTED',
        'diagnostic_only': True, 'native_qualification': False, 'world_runs': 0,
        'input_sources': [model_ref, ground_ref, header_ref, drive_ref],
        'execution_sources': [generator_ref, cpp_ref], 'worlds': references,
        'robots': [{'name': name, 'spawn_xyz_rpy': list(pose)} for name, pose in SPAWNS],
        'native_seed': 101, 'native_seed_api': 'ignition::math::Rand::Seed',
        'physics_seed_api': 'gazebo::physics::PhysicsEngine::SetSeed',
        'physics_seed_readback_claimed': False,
        'settle_seconds': 45, 'hold_seconds': 310, 'native_steps_per_arm': 355000,
        'step_ns': 1000000, 'observations_every_physics_step': True,
        'csv_sample_period_ns': 20000000, 'motor_update_period_ns': 34000000,
        'radius_m': .0078, 'work_wall_seconds_per_arm': 600,
        'complete_pair_parent_reservation_seconds': 1800,
        'gazebo_master_uri': 'http://127.0.0.1:11555',
        'zero_control': expected, 'desired_body_target': [0, 0],
        'physical_model_tree_preserved': True,
        'arm_difference': 'quick150 versus direct-world solver subtree only',
        'quick150_scope': 'production configuration baseline; this standalone diagnostic is not a production episode',
        'omitted_nonphysical_elements': sorted(REMOVED),
        'ground_scope': 'explicit installed source, not proof of historical V52 resolution',
        'identity': {'pid': os.getpid(), 'parent': os.getppid()},
        'external_build_required': True,
        'build_command_template': [
            'c++', '-std=c++17', '-O2', 'CPP', '-I' + str(ROS / 'src/multi_robot/include'),
            'PKG_CONFIG_GAZEBO_CFLAGS_AND_LIBS', '-o', 'NEW_ELF'],
        'forbidden': ['SetWorldPose', 'SetLinearVel', 'SetAngularVel', 'SetPosition',
                      'fixed/weld joints', 'anchor refresh', 'extra controller', 'automatic retry'],
        'qualification_warning': 'passive plant observations do not replace twelveEP/thirtyroles or continuous proof',
    }
    with (args.output / 'spec_v1.json').open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'prepared': True, 'output': str(args.output), 'world_runs': 0}))


if __name__ == '__main__':
    main()
