"""Offline P2A provenance, native-gate and collecting-policy audit.

No ROS or simulator is imported. Original P1C helpers remain immutable; this
wrapper pins their bytes and the accepted environment document separately.
Task failure remains a failure even when its measurement/provenance audit passes.
"""

import argparse
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
from functools import partial
from types import ModuleType, SimpleNamespace

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from . import audit_evaluator_phase, audit_odometry_cadence, audit_protocol, audit_scalar
from .audit_controlled_physics import dispatch_controlled_physics, dispatch_controlled_readiness
from .observation import encode_snapshot, observation_space


WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ROS = "ros2_ws/ros2-multi-robot-automap/"
OBSERVATION_SOURCE = ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py"
OBSERVATION_SHA256 = "b81da18c256ff307a4afc09c5115d0057e5a142a246555f39c1f7a5cee88c6e8"
REWARD_SOURCE = ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_reward.py"
W7_REWARD_SHA256 = "77485e7988489a146e4c44207343a0a4be7c12b5ffe36906dde59257cac16f88"
EVALUATOR_PHASE_PINS = {
    ROS + 'scripts/mr3_env_worker.py':
        'f957d3fcfe480145b805ef3e0d82ec0bd2c882c6fd1ac8ed0bc7c6458e6d9bed',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py':
        '3aa0655113c0c2402c6e587730fa1f457d1f837ff0ce00928e6c8ca433f3c8d6',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_evaluator_phase.py':
        '9c43ace376354edbdf496fe920d04a539ed47912fd0840f6d290c459450d69fa',
}
CURRENT_AUDITOR_PINS = {
    ROS + 'scripts/audit_mr3_env.py':
        '5ba60bc89f3c87059cd5d4342fa433de25548c7d95c66ea0ce7708eb4ae8dad2',
    ROS + 'scripts/audit_mr3_adapter_probe.py':
        '5b0ecf24617e317415b66876add73f5834187d022647d251edde8d1082370195',
}
PREPARATION_RUNTIME_PINS = {
    ROS + 'src/multi_robot/config/mr3_fastdds_loopback_udp.xml':
        '0b909216206301a5bee45cb1fd755f67a92481d98cec39d818b2dc8764844e37',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py':
        'd9121970b18e86a524ad4aad591a64661555bc15c0a59bf425896324473eecfc',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_observation_archive.py':
        '03da72d5e989e6c7af99b90aaddf357120c2239fc08e99febb858554b1fefea8',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py':
        'ad8f1676a4743f6cb01ff5d4b3b4a56555ec752e0fb92538597b54fffdf59b56',
    ROS + 'src/merge_map/merge_map/merge_map.py':
        '76c3d2c604f38f61116be1f39263472f9074b4f69fe7a0428b532da977530078',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_information.py':
        'b46d098cb9a762a7558ea84adf85d943f1e631b248b478a9ce1a2d6b0b07e644',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_activity.py':
        '7af918d75c05b6f8fb1a65899e43aad11a315640e8b00fdb589c31f693ad696e',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_protocol.py':
        '5a2b90efd162b19a35964750002fe549413fec6e07f9679ea611d3fe6b1e4ada',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py':
        '06ca6ece92ca49072df9eedbdd5396148ca2e09d4f2560204448e460e3e73ae7',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/motion_safety.py':
        '8ad1647dd76227ca763a72e3c635374c55185bd4891c11b6a6db7a1b5b6c05c1',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/control.py':
        '3b6fb71f2c90a055ef3bb922bd3f08332eb366d8becde577106d1ed5bd56cedd',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_drive_phase.py':
        '0525230f4719e7279826810f0c177f6a6317a961d50711ac76d8a0338f93d987',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_control_phase.py':
        '9d7b0cc64d2eb9cd4aee49de50feb63ebf117a31b41cc000119c2f4ea2741e15',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py':
        '03de01b95a442b81e0f25fe6618c72ceb5d3ab3628914c51c7cce8b29bac50a8',
}
SLAM = ROS + "src/slam_toolbox/"
SLAM_RUNTIME_PINS = {
    SLAM + "CMakeLists.txt":
        "1125c85d10877b32711495ac9cdfa9a6f78066be18f141705f43adf4a44ee12b",
    SLAM + "include/slam_toolbox/experimental/slam_toolbox_lifelong.hpp":
        "9ecb0d48e43165a4189dd66bc8153e4227ccbcec44bedc0118b5ef8a8597b13c",
    SLAM + "include/slam_toolbox/experimental/slam_toolbox_map_and_localization.hpp":
        "80a61fc113fd2b60ae39846431215e16f8ffccb707358bec1fd5f428e7d532de",
    SLAM + "include/slam_toolbox/laser_utils.hpp":
        "e0150bb5e2a0c4437885e597ab2d42b767326e0079b612bd88fd4eda13e6684d",
    SLAM + "include/slam_toolbox/loop_closure_assistant.hpp":
        "9d1e81296b47aa6270b7927f124e5ee8b173e7d651ed17eff01830ff9889e912",
    SLAM + "include/slam_toolbox/map_saver.hpp":
        "b6f5cfb830b3c11d330cf98c75e4ba5ed340f25428c3f3ed58df0b74dcf680e5",
    SLAM + "include/slam_toolbox/slam_toolbox_async.hpp":
        "db0662e8cd6cf7dbacca0e8e8554260f9c673c659fd8c58f18cf1681bfe68b2f",
    SLAM + "include/slam_toolbox/slam_toolbox_common.hpp":
        "a2da12ccf1459e4a1ad6a727f1d08ee68b54eb47a3bea2cb32558cf75731d63e",
    SLAM + "include/slam_toolbox/slam_toolbox_localization.hpp":
        "cedbe39bcc9f1c38b43c20301dfa6606b8b6fb7908bf1f8f99d7a39498a1b7e4",
    SLAM + "include/slam_toolbox/slam_toolbox_multirobot.hpp":
        "860b3c54a209e53c5073ce9242a199e37722cc0e6c74c55d6dd288b55b3ddcfa",
    SLAM + "include/slam_toolbox/slam_toolbox_sync.hpp":
        "47d1e34a12e187b6d62788e78ef59b689612ca211e1563a38a3904ac7d1fd8e7",
    SLAM + "include/slam_toolbox/visualization_utils.hpp":
        "2ebcfee911c632c0f0d9ed519aec9c52d160bff40186833843a1bbfe874510d5",
    SLAM + "solvers/ceres_solver.cpp":
        "e2b6c8e4c89a57a4939e7514c8f5e4cd43ec04eadc354f7fbf9feb34ecfd3e0f",
    SLAM + "solvers/ceres_solver.hpp":
        "06b0fcaef5705f01ed3851ce52b2126d54c8076fcc9ec22d135bfb977e32bbe3",
    SLAM + "src/laser_utils.cpp":
        "695277ffd043293849772d1b8688bbab95dcf95204f9ce1399656ce97d093fba",
    SLAM + "src/loop_closure_assistant.cpp":
        "324fb71c693002419fbf47cd76ed3917f8a716ddf698a3428703693d122c044e",
    SLAM + "src/map_saver.cpp":
        "85d12d04783e0ad49ce8561eb7c0b77973f38aa2153dcfcb72c3300b7ce1e6d4",
    SLAM + "src/merge_maps_kinematic.cpp":
        "3252af48fffdeaddb084bd376c45423c6ca6e49d0da057a60a5d8ad724d1af8c",
    SLAM + "src/slam_toolbox_common.cpp":
        "3b1323d284cb1e05c171199f3c9b8eca3cefbb775c6350bb0e84d695c9d62309",
    SLAM + "src/slam_toolbox_multirobot_node.cpp":
        "1472cfff3644523c60a7fc454c4cc875faa5d481455c85d7e7747042b6944573",
}
EXECUTION_CONFIG_PINS = {
    ROS + 'src/slam_toolbox/config/mapper_params_online_multi_async.yaml':
        '3ca81b5afb628d5787e60a266c6dc375a26f6b6a5c4fef70bd8a5261dc8dbb17',
    ROS + 'src/multi_robot/params/nav2_params_tb1_0.yaml':
        '8854aac6fe3083aa1156072830358e9331f0e0a45144ab3df499f743a37c1b8a',
    ROS + 'src/multi_robot/params/nav2_params_tb2_0.yaml':
        '9c7a0f9c197c5b3eedc3567c0b70d4920a5ca8cc6057b5059f5c5844ab275386',
    ROS + 'src/multi_robot/params/nav2_params_tb3_0.yaml':
        '8794b037c1ef31f57c8d99ab05c57a646afe6653717c2f21100e00b6a5435fae',
    ROS + 'src/multi_robot/config/nav2_params.yaml':
        '143b93aed93c0b71986844b7e3c00e1046e0b4fa9be8c94bcbc37b95e36b1e5b',
    ROS + 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py':
        'bcb177d669890ecd6f552379afad771656b6b748c314ea158e5599d37a0c3d2b',
    ROS + 'src/multi_robot/launch/nav2_bringup/bringup_launch.py':
        '41b7e5e65c2c61ce6f1efb5a9288c3875e60f6c9054d77f96f7fc6f0a6f2aa53',
    ROS + 'src/multi_robot/launch/nav2_bringup/navigation_launch.py':
        'ee4a7b7d590eb9f1a8129d025e99ceaf5908537d0063144da159d5a7ae8fd209',
    ROS + 'src/multi_robot_exploration/setup.py':
        'a23cd0dc598ebb59d9eae325bd1a6ee0ae700751986cac6858fe2c2949b68a15',
    ROS + 'src/multi_robot/models/turtlebot3_waffle/model.sdf':
        'c8131da065085475bdb0ce1e4c3abfc8c009811af6851fadf1fc33bd38b1d8a1',
    ROS + 'src/multi_robot/CMakeLists.txt':
        '7ebe737cdec686b08b02702846ca27998d1f67e9f1070979fa9123bfd6ea08b7',
    ROS + 'src/multi_robot/src/mr3_stop_response_observer.cpp':
        'b6619d3d246385f34b720c365a584d157ef75fc6a6cff64d58ff0ddedb0354c7',
    ROS + 'src/multi_robot/src/mr3_physics_diagnostic_profile.cpp':
        '26952e1cb8b17239a61b75ee98466daad65bafe116864557bbe92cc0b7fed7c0',
    ROS + 'src/multi_robot/package.xml':
        '170fb26fb5557b94107afc991ac9625359834415172119ebce43b822d94387cf',
    ROS + 'src/multi_robot/src/mr3_gazebo_diff_drive.cpp':
        '15f54f0786330ac78d5d75853295050a69c0b6d431d19a82f3ae005d288ad8f1',
    ROS + 'src/multi_robot/include/multi_robot/mr3_gazebo_diff_drive.hpp':
        'c86c9b3469e0d81c6a037840cb3c091411c023115c563f454d1ce4399ec08e64',
    ROS + 'src/multi_robot/include/multi_robot/paired_wheel_slew.hpp':
        'dca3dbaf01251cf7ffe167f1dabb23a45b4fc95d6ad317dcc3290ff50ecf9a1b',
    ROS + 'src/multi_robot/vendor/gazebo_ros_diff_drive.PROVENANCE.md':
        '6aa47fdbc6fb0bcf419fff199bd2aecbb0b3791e33f481473f7e37e597701235',
    ROS + 'src/multi_robot/vendor/gazebo_ros_diff_drive.BSD-3-Clause.txt':
        '771978f82c58310201ccdfdfd66e8ca798d26c2202d77f32a131d60bd297a545',
    WIRELESS + 'MR3_ADAPTER_CONTRACT.md':
        'b8a61963772dd8a6410d11647435e386c056e5c64e56325b650c447bbe21df04',
    ROS + 'src/multi_robot/include/multi_robot/mr3_drive_target.hpp':
        '4be4d77de247a5bcd427eb6948165e85098eb361030cf89d278d6df92e959d41',
}
EXECUTION_CONFIG_PINS.update({'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_odometry_json.hpp': '4b251bff9336a6005a4fff9b6a981286687e99cbff86bf8b3410163e32392c74', 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_odometry_recorder.cpp': 'd70502556ca840d8e01ce0183db7befbeecefc3bf267ba239867937013cb6168'})
ENV_DOCUMENT_SHA256 = 'a30419335428f53fdfbe88f9805eab2d742d177428b6b45db0c3c77be752b15c'
TASK_DOCUMENT_SHA256 = "f96f5ba785a39daa882b3c2ea217c58dd968550b65bf0ee15faf07ca079f8991"
PRIOR_TASK_DOCUMENT_SHA256 = "5e4400396e4aaf5a5094fb4c0c04c85810c327cc85be88b7d03fa3faeade07d2"
TASK_BASE_FREEZE = "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a"
SOLVER150_WORLD_PINS = {
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/worlds/p1c_open.world':
        'ed3fcd526d7367e8e0eb5245c365ba60631a6f4a6d725c64134221217ddc4846',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/worlds/p1c_rooms.world':
        '92ac7dff82bdf03b9f1ce3e9f075a3f59ca07df23c2f89fca654b3f423742768',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/worlds/p1c_corridors.world':
        '7e15f3ba716fd2f6cdc55310ab3064e61c8d0d34c4f8cba79a964260a8dac051',
}
SOLVER150_TASK_PINS = {
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_p1a/open.json':
        'e4a3c25374bb482a0104530f1765f17b807377e0a5c85bc42d6645a63bfc5487',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_p1a/rooms.json':
        'c4ddca59d8b955f5410a0e639736263c750d6e819a864020c3e4e6da783a811e',
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_p1a/corridors.json':
        '44cc8593cf69206a36b3a7bf82b2008957d5454caaa040dc4b3ac815e1b778a6',
}

PHASE_SHA256 = "4e2a24e3465fa45c06c05c37b57b8b77b6e462845b3227be10c1fecb85c2c7d7"
SCALAR_SHA256 = "895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665"
POLICY_ATOL = 1e-4  # CPU replay of CUDA collecting inference; never a task tolerance.
POLICY_RTOL = 1e-5


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_machine_task_file(root, freeze, relative):
    """Bind current bytes and narrowly project only the reviewed six-file revision."""
    normative = subprocess.check_output(
        ["git", "show", TASK_BASE_FREEZE + ":" + relative], cwd=root)
    actual = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
    normative_digest = hashlib.sha256(normative).hexdigest()
    actual_digest = hashlib.sha256(actual).hexdigest()
    if relative not in SOLVER150_WORLD_PINS and relative not in SOLVER150_TASK_PINS:
        require(actual == normative and sha(root / relative) == normative_digest,
                "machine task/geometry changed from accepted W7 contract: " + relative)
        return {"sha256": normative_digest, "git_source": freeze + ":" + relative,
                "normative_source": TASK_BASE_FREEZE + ":" + relative}
    expected_digest = (SOLVER150_WORLD_PINS if relative in SOLVER150_WORLD_PINS
                       else SOLVER150_TASK_PINS)[relative]
    require(actual_digest == expected_digest and sha(root / relative) == expected_digest,
            "explicit solver150 machine source freeze/worktree SHA mismatch: " + relative)
    if relative in SOLVER150_WORLD_PINS:
        anchor = b"      <real_time_update_rate>1000</real_time_update_rate>\n"
        block = (b"      <ode>\n"
                 b"        <solver>\n"
                 b"          <type>quick</type>\n"
                 b"          <iters>150</iters>\n"
                 b"        </solver>\n"
                 b"      </ode>\n")
        require(normative.count(anchor) == 1 and b"<ode>" not in normative
                and actual.count(block) == 1
                and actual == normative.replace(anchor, anchor + block, 1)
                and actual.replace(block, b"", 1) == normative,
                "solver150 world does not project exactly to W7: " + relative)
        revision = "explicit_quickstep150_physics_only_v1"
        world_reference = None
    else:
        scene = Path(relative).stem
        world_relative = ROS + "src/multi_robot/worlds/p1c_" + scene + ".world"
        require(world_relative in SOLVER150_WORLD_PINS,
                "solver150 task metadata has no reviewed matching scene")
        world_proof = verify_machine_task_file(root, freeze, world_relative)
        old_field = ('  "world_sha256": "' + world_proof["normative_sha256"] + '",\n').encode()
        new_field = ('  "world_sha256": "' + world_proof["sha256"] + '",\n').encode()
        require(normative.count(old_field) == 1 and actual.count(new_field) == 1
                and actual == normative.replace(old_field, new_field, 1)
                and actual.replace(new_field, old_field, 1) == normative,
                "solver150 task metadata does not project exactly to W7: " + relative)
        revision = "actual_world_sha256_metadata_only_v1"
        world_reference = {"path": world_relative, "sha256": world_proof["sha256"]}
    proof = {"sha256": actual_digest, "git_source": freeze + ":" + relative,
             "normative_source": TASK_BASE_FREEZE + ":" + relative,
             "normative_sha256": normative_digest, "machine_revision": revision,
             "projected_normative_sha256": normative_digest,
             "scope": "actual revised execution/config bytes; exact W7 geometry/task projection"}
    if world_reference is not None:
        proof["actual_world"] = world_reference
    return proof



ENV_NORMATIVE_FREEZE = "4f8bd0e509e6f958c5993a50008955afac72c345"
ENV_NORMATIVE_SHA256 = "96d9bd3e3d597899b3d44a69ef9138e77b62b3641bd7261eb38846d5b003f155"
ENV_EXECUTION_APPENDIX_SHA256 = 'f150768f6e3a4eedb4a2b5ff2336935249368436c1a82567a4604ac54acf4966'
ENV_EXECUTION_APPENDIX_BYTES = 14761

def verify_environment_appendix(root, freeze):
    relative = WIRELESS + "MR3_ENV_CONTRACT.md"
    normative = subprocess.check_output(["git", "show", ENV_NORMATIVE_FREEZE + ":" + relative], cwd=root)
    actual = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
    require(hashlib.sha256(normative).hexdigest() == ENV_NORMATIVE_SHA256
            and hashlib.sha256(actual).hexdigest() == ENV_DOCUMENT_SHA256
            and sha(root / relative) == ENV_DOCUMENT_SHA256, "execution ENV Git/worktree identity differs")
    require(len(actual) == len(normative) + ENV_EXECUTION_APPENDIX_BYTES
            and actual[:len(normative)] == normative
            and hashlib.sha256(actual[len(normative):]).hexdigest() == ENV_EXECUTION_APPENDIX_SHA256,
            "execution ENV must preserve normative whole prefix plus unique fixed appendix")
    return {"environment_revision": "native_ray_box_and_explicit_solver150_v1",
            "normative_sha256": ENV_NORMATIVE_SHA256,
            "normative_source": ENV_NORMATIVE_FREEZE + ":" + relative,
            "appendix_sha256": ENV_EXECUTION_APPENDIX_SHA256,
            "append_only_normative_prefix_exact": True,
            "scope": "actual revised environment document; original numeric/task/eligibility gates retained"}

def parameter_changes(before, after):
    left, right = before.policy.state_dict(), after.policy.state_dict()
    require(left.keys() == right.keys(), "checkpoint policy parameter names differ")
    return sum(not torch.equal(left[key], right[key]) for key in left)


def load_json(path):
    return json.loads(Path(path).read_text())


def load_rows(path):
    path = Path(path)
    if not path.exists():
        path = path.with_name(path.name + ".gz")
    with (gzip.open(path, "rt") if path.suffix == ".gz" else path.open()) as source:
        return [json.loads(line) for line in source if line.strip()]


def load_pinned(name, path, digest):
    require(sha(path) == digest, "immutable offline helper changed: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_frozen_pins(root, freeze, pins, label):
    """Bind explicitly reviewed bytes to both the claimed commit and worktree."""
    proof = {}
    for relative, expected in pins.items():
        payload = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        digest = hashlib.sha256(payload).hexdigest()
        require(digest == expected and sha(root / relative) == expected,
                label + " source freeze/worktree SHA mismatch: " + relative)
        proof[relative] = {"sha256": digest, "git_source": freeze + ":" + relative,
                           "worktree_sha256": expected}
    return proof



# Only these reviewed execution-source additions have a whole-byte inverse.
EXECUTION_NORMATIVE_FREEZE = '4f8bd0e509e6f958c5993a50008955afac72c345'
EXECUTION_NORMATIVE_PINS = {'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py': 'bcb177d669890ecd6f552379afad771656b6b748c314ea158e5599d37a0c3d2b',
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt': '7ebe737cdec686b08b02702846ca27998d1f67e9f1070979fa9123bfd6ea08b7'}
SENSOR_DIAGNOSTIC_CONFIG_PINS = {'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py': '6c76a4f0afbeb4c26f8c28b8e1139bbd12e5162a54ca3a193b99a156ef47a2d2',
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt': '170eb49947c4daa61d30f45ab8fde637aa12766182dddfda15c9ca6453d0cc0d'}
RAY_BOX_EXECUTION_PINS = {'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py': '814f5b6256ac8badfb7f74dae21f0c66423c6e8ca7181266639d8865dc09cfd1',
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt': '12b994e0fc0c01ec8761aaf23a7ae4722fe3026391b0622d13b842d0b425ebdc'}
RAY_BOX_SOURCE_PINS = {'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_ray_box_corrector.cpp': 'f82646c8434b77c42f585ac1828eda84640bac873f70cc7de6848cfbd6493473',
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_ray_box_collision.cpp': 'd556dda57250da3680a7d5a9862416f6196cab9763e495ee75269307b87715cb',
 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include/multi_robot/mr3_ray_box_collision.hpp': 'c619442d038e4bc6ea0695ada34d7074ee83d775b2137222ab9fb6bf8193879b'}
RAY_BOX_LICENSE_PINS = {'ros2_ws/ros2-multi-robot-automap/src/multi_robot/vendor/mr3_ray_box_corrector/LICENSE-BSD.TXT': 'fe012d262cf04a701cc856e2d12780261a60d7b17f4f7cb9cd589ff65b3f4f32'}
RAY_BOX_LAUNCH_CHANGES = [{'before': '    server_state = {\n',
  'after': '    ray_box_plugin = None\n'
           '    ray_box_audit_path = None\n'
           '    if stepped_mode:\n'
           '        ray_box_plugin = os.path.join(get_package_prefix("multi_robot"),\n'
           '                                     "lib", "libmr3_ray_box_corrector.so")\n'
           '        if not os.path.isfile(ray_box_plugin):\n'
           '            raise ValueError(f"installed MR3 ray-box corrector does not exist: '
           '{ray_box_plugin}")\n'
           '        ray_box_directory = (Path(adapter_audit_path).parent.resolve(strict=True)\n'
           '                             if adapter_audit_path else\n'
           '                             Path(tempfile.mkdtemp(prefix="mr3_ray_box_corrector_")))\n'
           '        ray_box_audit_path = str(ray_box_directory / "ray_box_corrector.jsonl")\n'
           '    server_state = {\n'},
 {'before': '                "stepped_mode": stepped_mode, "selected_step_plugin": step_plugin,\n',
  'after': '                "stepped_mode": stepped_mode, "selected_step_plugin": step_plugin,\n'
           '                "selected_ray_box_plugin": ray_box_plugin,\n'
           '                "ray_box_audit_path": ray_box_audit_path,\n'},
 {'before': '        diagnostic_system_args = []\n',
  'after': '        gazebo_environment["MR3_RAY_BOX_CORRECTOR_AUDIT_PATH"] = ray_box_audit_path\n'
           '        gazebo_environment["MR3_RAY_BOX_CORRECTOR_EPOCH"] = '
           'episode_epoch.perform(context)\n'
           '        diagnostic_system_args = []\n'},
 {'before': '                 "-s", "libgazebo_ros_force_system.so", "-s", step_plugin,\n',
  'after': '                 "-s", "libgazebo_ros_force_system.so",\n'
           '                 "-s", ray_box_plugin, "-s", step_plugin,\n'}]
RAY_BOX_CMAKE_ADDITION = ('\n'
 '# MR3 ray/box finite-segment correction (the other collider pairs are unchanged).\n'
 'set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS\n'
 '  "${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_box_corrector.cpp"\n'
 '  "${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_box_collision.cpp"\n'
 '  "${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/mr3_ray_box_collision.hpp")\n'
 'file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_box_corrector.cpp"\n'
 '  MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256)\n'
 'file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_box_collision.cpp"\n'
 '  MR3_RAY_BOX_COLLISION_SOURCE_SHA256)\n'
 'file(SHA256 "${CMAKE_CURRENT_SOURCE_DIR}/include/multi_robot/mr3_ray_box_collision.hpp"\n'
 '  MR3_RAY_BOX_COLLISION_HEADER_SHA256)\n'
 'add_library(mr3_ray_box_corrector SHARED\n'
 '  src/mr3_ray_box_corrector.cpp src/mr3_ray_box_collision.cpp)\n'
 'set_target_properties(mr3_ray_box_corrector PROPERTIES CXX_STANDARD 17 CXX_STANDARD_REQUIRED '
 'ON)\n'
 'target_include_directories(mr3_ray_box_corrector PRIVATE\n'
 '  "${CMAKE_CURRENT_SOURCE_DIR}/include" ${GAZEBO_INCLUDE_DIRS})\n'
 'target_link_libraries(mr3_ray_box_corrector ${GAZEBO_LIBRARIES} gazebo_ode ${CMAKE_DL_LIBS})\n'
 'target_compile_definitions(mr3_ray_box_corrector PRIVATE\n'
 '  MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256="${MR3_RAY_BOX_CORRECTOR_SOURCE_SHA256}"\n'
 '  MR3_RAY_BOX_COLLISION_SOURCE_SHA256="${MR3_RAY_BOX_COLLISION_SOURCE_SHA256}"\n'
 '  MR3_RAY_BOX_COLLISION_HEADER_SHA256="${MR3_RAY_BOX_COLLISION_HEADER_SHA256}")\n'
 'install(TARGETS mr3_ray_box_corrector LIBRARY DESTINATION lib)\n'
 'install(FILES vendor/mr3_ray_box_corrector/LICENSE-BSD.TXT\n'
 '  DESTINATION share/${PROJECT_NAME}/vendor/mr3_ray_box_corrector)\n')
RAY_CMAKE_ADDITION = ('# Opt-in ray provenance SensorPlugin; original targets/sources/flags unchanged.\n'
 'set(mr3_ray_provenance_source ${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_provenance_observer.cpp)\n'
 'set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${mr3_ray_provenance_source})\n'
 'file(SHA256 ${mr3_ray_provenance_source} mr3_ray_provenance_source_sha)\n'
 'add_library(mr3_ray_provenance_observer SHARED src/mr3_ray_provenance_observer.cpp)\n'
 'target_compile_features(mr3_ray_provenance_observer PRIVATE cxx_std_17)\n'
 'target_include_directories(mr3_ray_provenance_observer PRIVATE ${GAZEBO_INCLUDE_DIRS})\n'
 'target_link_libraries(mr3_ray_provenance_observer ${GAZEBO_LIBRARIES}\n'
 '  nlohmann_json::nlohmann_json ${CMAKE_DL_LIBS})\n'
 'target_compile_definitions(mr3_ray_provenance_observer PRIVATE\n'
 '  MR3_RAY_PROVENANCE_SOURCE_SHA256="${mr3_ray_provenance_source_sha}")\n'
 'install(TARGETS mr3_ray_provenance_observer DESTINATION lib)\n'
 '\n')

def project_sensor_diagnostic_runtime(relative, current):
    """Remove only the fixed opt-in SensorPlugin target/config/injection additions."""
    text = current.decode()
    if relative.endswith('/CMakeLists.txt'):
        require(text.count(RAY_CMAKE_ADDITION) == 1, 'ray target addition differs')
        return text.replace(RAY_CMAKE_ADDITION, '', 1).encode()
    def replace_once(text, added, original=''):
        require(text.count(added) == 1, 'ray launch inverse marker differs')
        return text.replace(added, original, 1)
    text = replace_once(text, 'import xml.etree.ElementTree as ET\n')
    text = replace_once(text,
        '    if (type(config) is not dict or set(config) not in (expected, expected | {"ray_provenance"}) or\n',
        '    if (type(config) is not dict or set(config) != expected or\n')
    start = text.index('    ray = None\n')
    end = text.index('    world_path = Path(world).resolve(strict=True)\n', start)
    text = text[:start] + text[end:]
    text = replace_once(text, '    if ray is not None:\n        binding["ray_provenance"] = ray\n')
    start = text.index('def append_ray_provenance(')
    end = text.index('def drive_spawn_model(', start)
    text = text[:start] + text[end:]
    text = replace_once(text, '        model = append_ray_provenance(model, robot_name, physics_diagnostic)\n')
    return text.encode()

def project_ray_box_runtime(relative, current):
    text = current.decode()
    if relative.endswith('/CMakeLists.txt'):
        require(text.count(RAY_BOX_CMAKE_ADDITION) == 1,
                'ray-box target addition differs')
        return text.replace(RAY_BOX_CMAKE_ADDITION, '', 1).encode()
    for change in reversed(RAY_BOX_LAUNCH_CHANGES):
        require(text.count(change['after']) == 1, 'ray-box launch inverse marker differs')
        text = text.replace(change['after'], change['before'], 1)
    return text.encode()


REVIEWED_EXECUTION_DELTA = WIRELESS + "report/assets/20261019_mr3_p2a_v12/reviewed_execution_delta.json"
REVIEWED_EXECUTION_DELTA_SHA256 = "3ff0e754cb733b9c2557410978e59bfe567c99092639dca26316158df6196082"


def project_reviewed_execution(root, freeze, relative, actual):
    """Reverse only fixed reviewed V8/V9 edits before both older inverses."""
    verify_frozen_pins(root, freeze, {REVIEWED_EXECUTION_DELTA: REVIEWED_EXECUTION_DELTA_SHA256},
                       "reviewed execution delta")
    delta = load_json(root / REVIEWED_EXECUTION_DELTA)
    require(delta["schema"] == "mr3-reviewed-execution-delta-v1"
            and delta["base_freeze"] == "92f8bdf5bba1ba245dc53ca0964eef81a7fff938",
            "execution delta base identity differs")
    item = delta["files"][relative]
    require(hashlib.sha256(actual).hexdigest() == item["after_sha256"],
            "reviewed execution source identity differs: " + relative)
    lines = actual.decode().splitlines(keepends=True)
    for change in reversed(item["changes"]):
        at = change["new_line_start"]
        added = change["after"].splitlines(keepends=True)
        require(lines[at:at + len(added)] == added, "reviewed execution inverse differs")
        lines[at:at + len(added)] = change["before"].splitlines(keepends=True)
    projected = "".join(lines).encode()
    require(hashlib.sha256(projected).hexdigest() == item["before_sha256"]
            == RAY_BOX_EXECUTION_PINS[relative], "reviewed execution whole-source projection differs")
    return projected, item["after_sha256"]


def verify_execution_configs(root, freeze):
    require(all(EXECUTION_CONFIG_PINS.get(path) == digest
                for path, digest in EXECUTION_NORMATIVE_PINS.items()),
            'original execution config pins differ')
    retained = {path: digest for path, digest in EXECUTION_CONFIG_PINS.items()
                if path not in EXECUTION_NORMATIVE_PINS}
    proof = verify_frozen_pins(root, freeze, retained, 'execution config')
    for relative, expected in RAY_BOX_EXECUTION_PINS.items():
        actual = subprocess.check_output(['git', 'show', freeze + ':' + relative], cwd=root)
        require(sha(root / relative) == hashlib.sha256(actual).hexdigest(),
                'ray-box execution source Git/worktree SHA mismatch: ' + relative)
        prior, current_digest = project_reviewed_execution(root, freeze, relative, actual)
        intermediate = project_ray_box_runtime(relative, prior)
        require(hashlib.sha256(intermediate).hexdigest() == SENSOR_DIAGNOSTIC_CONFIG_PINS[relative],
                'ray-box source does not project exactly to sensor diagnostic revision: ' + relative)
        normative = subprocess.check_output(
            ['git', 'show', EXECUTION_NORMATIVE_FREEZE + ':' + relative], cwd=root)
        projected = project_sensor_diagnostic_runtime(relative, intermediate)
        require(hashlib.sha256(normative).hexdigest() == EXECUTION_NORMATIVE_PINS[relative]
                and projected == normative, 'execution source does not restore normative whole bytes: ' + relative)
        proof[relative] = {'sha256': current_digest, 'git_source': freeze + ':' + relative,
                           'worktree_sha256': current_digest,
                           'execution_revision': 'v8_disabled_stimulus_v9_world_odometry_recorder',
                           'reviewed_delta_sha256': REVIEWED_EXECUTION_DELTA_SHA256,
                           'prior_ray_box_source_sha256': expected,
                           'intermediate_sha256': SENSOR_DIAGNOSTIC_CONFIG_PINS[relative],
                           'normative_source': EXECUTION_NORMATIVE_FREEZE + ':' + relative,
                           'normative_sha256': EXECUTION_NORMATIVE_PINS[relative],
                           'projected_normative_sha256': hashlib.sha256(projected).hexdigest()}
    proof.update(verify_frozen_pins(root, freeze, {**RAY_BOX_SOURCE_PINS, **RAY_BOX_LICENSE_PINS},
                                    'ray-box implementation'))
    return proof



RAY_BOX_LIBRARY_SPEC = {'receipt': {'path': 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install/binary/receipt_v1.json',
             'sha256': '84bbd6bd4b5a8802222dfff9ef8f5a741b89a5d670b71170f46e9a8ae67b4ac8',
             'bytes': 7954},
 'build': {'path': 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install/binary/canonical_build_receipt_v1.json',
           'sha256': '6ee8d2739a62d4432122b47aface5abbbc56242737528e2284c03696fd6b7ef6',
           'bytes': 17467},
 'archive': {'path': 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install/binary/libmr3_ray_box_corrector.so.gz',
             'sha256': '41c1ae6ad5fd1c80a220ecde90328271e2f4e0668d4d240beb44bc0dce67abed',
             'bytes': 129776},
 'library': {'path': 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_ray_box_corrector.so',
             'resolved': 'ros2_ws/ros2-multi-robot-automap/build/multi_robot/libmr3_ray_box_corrector.so',
             'bytes': 398080,
             'sha256': '782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8'},
 'ode_library': {'path': '/lib/x86_64-linux-gnu/libgazebo_ode.so.11',
                 'resolved': '/usr/lib/x86_64-linux-gnu/libgazebo_ode.so.11.10.2',
                 'bytes': 719240,
                 'sha256': 'a94a424df0b3af9d8a04c58ef1562734cc81728253bcedd25c7705330289c258'},
 'unchanged_libraries': {'libmr3_gazebo_diff_drive.so': {'path': 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_gazebo_diff_drive.so',
                                                         'resolved': 'ros2_ws/ros2-multi-robot-automap/build/multi_robot/libmr3_gazebo_diff_drive.so',
                                                         'bytes': 1999200,
                                                         'sha256': 'a014f2c618e38fc8a306d76c100083d952606333045a2e35bffce6f8b25b10c8'},
                         'libmr3_stop_response_observer.so': {'path': 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_stop_response_observer.so',
                                                              'resolved': 'ros2_ws/ros2-multi-robot-automap/build/multi_robot/libmr3_stop_response_observer.so',
                                                              'bytes': 497648,
                                                              'sha256': '9a1d76b0d9a6585bb2d40fb348bc5636bdd256838291e8ea605d1d05b18806bf'},
                         'libmr3_physics_diagnostic_profile.so': {'path': 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_physics_diagnostic_profile.so',
                                                                  'resolved': 'ros2_ws/ros2-multi-robot-automap/build/multi_robot/libmr3_physics_diagnostic_profile.so',
                                                                  'bytes': 496360,
                                                                  'sha256': '09321ea65a2c893d2e65316f43d5ee54d5dda7014a5d40e2186b6b720055fcc1'},
                         'libmr3_ray_provenance_observer.so': {'path': 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_ray_provenance_observer.so',
                                                               'resolved': 'ros2_ws/ros2-multi-robot-automap/build/multi_robot/libmr3_ray_provenance_observer.so',
                                                               'bytes': 463272,
                                                               'sha256': 'b76138132ae7dbb35936c2e0971e909f688189d240de3910516157b3553d57b8'}}}

def verify_ray_box_library(root, freeze):
    """Bind the actual installed ELF to fixed compiled sources and saved build bytes.

    This proves file/build identity only. Per-episode loaded mappings, installed
    callback/real ODE readback and closed ledger are separately required.
    """
    spec = RAY_BOX_LIBRARY_SPEC
    tracked = {spec[key]['path']: spec[key]['sha256'] for key in ('receipt', 'build', 'archive')}
    proof = verify_frozen_pins(root, freeze, tracked, 'ray-box binary custody')
    for key in ('receipt', 'build', 'archive'):
        require((root / spec[key]['path']).stat().st_size == spec[key]['bytes'],
                'ray-box binary custody byte count differs: ' + key)
    receipt = json.loads((root / spec['receipt']['path']).read_bytes())
    require(receipt.get('schema') == 'mr3-v22-ray-box-actual-binary-custody-v1'
            and receipt.get('passed') is True and receipt.get('old_four_libraries_byte_unchanged') is True,
            'ray-box canonical build custody is not passed')
    actual_library = root / spec['library']['path']
    require(actual_library.resolve(strict=True) == (root / spec['library']['resolved']).resolve(strict=True),
            'ray-box installed library resolves outside reviewed build artifact')
    raw = actual_library.read_bytes()
    require(raw[:4] == b'\x7fELF' and len(raw) == spec['library']['bytes']
            and hashlib.sha256(raw).hexdigest() == spec['library']['sha256'],
            'ray-box actual installed ELF differs')
    require(gzip.decompress((root / spec['archive']['path']).read_bytes()) == raw,
            'ray-box actual ELF/archive bytes differ')
    for relative, expected in RAY_BOX_SOURCE_PINS.items():
        require(expected.encode() in raw, 'ray-box compiled source macro missing: ' + relative)
        short = str(Path(relative).relative_to(ROS + 'src/multi_robot'))
        require(receipt['sources'][short]['sha256'] == expected,
                'ray-box build receipt source identity differs: ' + relative)
    # Driver/observer have an explicit new compiled-source/build identity below;
    # the original corrector/ODE/archive and other unchanged ELFs stay exact.
    revised = {'libmr3_gazebo_diff_drive.so', 'libmr3_stop_response_observer.so'}
    for library in [spec['ode_library'], *(value for name, value in
                   spec['unchanged_libraries'].items() if name not in revised)]:
        path = root / library['path']
        require(path.resolve(strict=True) == (root / library['resolved']).resolve(strict=True),
                'reviewed ODE/unchanged library resolved path differs: ' + str(path))
        payload = path.read_bytes()
        require(payload[:4] == b'\x7fELF' and len(payload) == library['bytes']
                and hashlib.sha256(payload).hexdigest() == library['sha256'],
                'reviewed ODE/unchanged library bytes differ: ' + str(path))
    proof[spec['receipt']['path']].update(
        installed_library_sha256=spec['library']['sha256'],
        installed_library_bytes=spec['library']['bytes'],
        installed_library_path=str(actual_library),
        installed_library_resolved=str(actual_library.resolve(strict=True)),
        compiled_source_sha256=dict(RAY_BOX_SOURCE_PINS),
        actual_ode_library=spec['ode_library'],
        scope='actual file/build/archive identity; loaded process and callback/iterations are separate custody gates')
    proof.update(verify_current_native_binding(root, freeze))
    return proof



SMOOTHER_OVERLAY_PINS = {
    'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v26_capture/independent/mr3_v26_smoother_custody_v2.py': 'ac90b7f896592a5a08430ee859ad73332a4e0cd3292e53e20ada310179841c30',
    'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v25_smoother/independent/mr3_v25_smoother_binding_v1.json': '61276e5b98a8fb641ecae464386a7f1403acc73789df5251cd82bb35ab83b5e0',
}


CURRENT_NATIVE_BINDING = WIRELESS + 'report/assets/20261019_mr3_p2a_v12/native_custody_binding.json'
CURRENT_NATIVE_BINDING_SHA256 = '65a20bf73c2eda4350cdfdc587f7f9688ea57b2a998d467f0f7a1f2e8e5e3934'
CURRENT_NATIVE_CUSTODY_SOURCE_SHA256 = '4edcdb6b33105e274c1c908c9d78e8c5d24461ff6733ed0f976e41bad3f2d928'


def verify_current_native_binding(root, freeze):
    """Explicit V9 sources/build/ELFs; loaded custody is a separate real CLI."""
    from . import native_custody
    source = WIRELESS + 'mr3_learning/native_custody.py'
    proof = verify_frozen_pins(root, freeze, {
        CURRENT_NATIVE_BINDING: CURRENT_NATIVE_BINDING_SHA256,
        source: CURRENT_NATIVE_CUSTODY_SOURCE_SHA256}, 'V9 native custody entry')
    identity = native_custody.verify_binding(root, freeze, root / CURRENT_NATIVE_BINDING)
    proof[CURRENT_NATIVE_BINDING]['identity_proof'] = identity
    proof[CURRENT_NATIVE_BINDING]['scope'] = (
        'actual files/build/compiled source only; per-episode loaded maps, received messages, '
        'native close and all mathematical/body gates remain independently required')
    return proof


def verify_velocity_smoother_overlay(root, freeze):
    """Node-clock smoother with explicit default-off diagnostic build identity."""
    return verify_current_native_binding(root, freeze)


def extend_snapshot_validator(auditor, candidate_module):
    """Extend the original validator for exact reviewed candidate/schema rules.

    Original records take the unmodified legacy path. New records first prove
    their actual whole-snapshot and versioned candidate digests; a detached
    legacy-format view then passes every original non-version validation.
    Native snapshots and immutable helper files are never changed.
    """
    original = auditor.validate_snapshot

    def validate(snapshot, epoch):
        if "candidate_rule" not in snapshot:
            return original(snapshot, epoch)
        versioned_digest = candidate_module.candidate_digest(snapshot)
        require(snapshot.get("candidate_version") == versioned_digest,
                "versioned candidate digest mismatch")
        require(snapshot.get("digest") == auditor.canonical_digest(
            {key: value for key, value in snapshot.items() if key != "digest"}),
            "saved snapshot digest mismatch")
        if snapshot.get("schema") == "mr3-observation-v3":
            # The current encoder validates every activity field and valid bit.
            # Native masks, candidate coordinates and execution gates are not
            # changed in the detached original-validator view below.
            encode_snapshot(snapshot)
        legacy = copy.deepcopy(snapshot)
        if legacy.get("schema") == "mr3-observation-v3":
            legacy["schema"] = "mr3-observation-v2"
        legacy.pop("candidate_rule")
        legacy["candidate_version"] = auditor.canonical_digest({
            key: legacy[key] for key in
            ("epoch", "map_version", "sequence", "candidates", "path_maps")})
        legacy["digest"] = auditor.canonical_digest({
            key: value for key, value in legacy.items() if key != "digest"})
        return original(legacy, epoch)

    auditor.validate_snapshot = validate


def load_compatible_components(phase, root, freeze):
    """Keep W7 native auditors and phase/command gates as verified Git bytes.

    The current CLI validators understand both candidate formats. The native
    gate uses the exact original auditor modules in memory, adding only the
    reviewed candidate-version dispatch, while unchanged runtime sources remain
    pinned to W7 and the new candidate source/configs have explicit new pins.
    """
    base = phase.load_pinned_module("mr3_p2a_legacy_phase_v2", Path(phase.__file__).parent /
                                    phase.BASE_NAME, phase.BASE_SHA256)
    command = phase.load_pinned_module("mr3_p2a_legacy_command_v7", Path(phase.__file__).parent /
                                       phase.COMMAND_NAME, phase.COMMAND_SHA256)
    require(all(phase.PINNED_RUNTIME.get(path) == digest
                for path, digest in command.PINNED_AUDITORS.items()),
            "original command-time auditor pins differ from W7 phase pins")
    normative_reward = subprocess.check_output(
        ["git", "show", TASK_BASE_FREEZE + ":" + REWARD_SOURCE], cwd=root)
    require(hashlib.sha256(normative_reward).hexdigest() == W7_REWARD_SHA256,
            "original W7 reward ledger Git SHA mismatch")
    runtime = {**phase.PINNED_RUNTIME, OBSERVATION_SOURCE: OBSERVATION_SHA256,
               REWARD_SOURCE: W7_REWARD_SHA256, **EVALUATOR_PHASE_PINS,
               **PREPARATION_RUNTIME_PINS, **SLAM_RUNTIME_PINS}
    original_scripts = set(command.PINNED_AUDITORS)
    native_pins = {path: digest for path, digest in runtime.items()
                   if path not in original_scripts}
    proof = verify_frozen_pins(root, freeze, native_pins, "native runtime")
    proof[REWARD_SOURCE]["normative_source"] = TASK_BASE_FREEZE + ":" + REWARD_SOURCE
    proof.update(verify_frozen_pins(root, freeze, CURRENT_AUDITOR_PINS, "current auditor"))
    proof.update(verify_execution_configs(root, freeze))
    proof.update(verify_ray_box_library(root, freeze))
    proof.update(verify_velocity_smoother_overlay(root, freeze))
    for relative, expected in phase.PINNED_DOCUMENTS.items():
        payload = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        require(hashlib.sha256(payload).hexdigest() == expected,
                "frozen document SHA mismatch: " + relative)
        proof[relative] = {"sha256": expected, "source": freeze + ":" + relative}
    names = ("ros_smoke_test", "audit_mr3_adapter_probe", "mr3_p2a_legacy_env_audit")
    previous = {name: sys.modules.get(name) for name in names}
    loaded = {}
    try:
        filenames = ("ros_smoke_test.py", "audit_mr3_adapter_probe.py", "audit_mr3_env.py")
        for name, filename in zip(names, filenames):
            relative = ROS + "scripts/" + filename
            payload = subprocess.check_output(
                ["git", "show", TASK_BASE_FREEZE + ":" + relative], cwd=root)
            digest = hashlib.sha256(payload).hexdigest()
            require(digest == runtime[relative],
                    "original W7 auditor Git SHA mismatch: " + relative)
            # ros_smoke_test also executes natively, so retain its source pin.
            if relative not in CURRENT_AUDITOR_PINS:
                proof.update(verify_frozen_pins(
                    root, freeze, {relative: digest}, "native runtime"))
            proof[relative].update(legacy_auditor_sha256=digest,
                                   legacy_auditor_git_source=TASK_BASE_FREEZE + ":" + relative)
            module = ModuleType(name)
            module.__file__ = str(root / relative)
            sys.modules[name] = module
            exec(compile(payload, TASK_BASE_FREEZE + ":" + relative, "exec"), module.__dict__)
            loaded[name] = module
        current_path = ROS + "scripts/audit_mr3_adapter_probe.py"
        current_probe = load_pinned("mr3_p2a_current_candidate_rules", root / current_path,
                                    CURRENT_AUDITOR_PINS[current_path])
    finally:
        for name, prior in previous.items():
            if prior is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = prior
    auditor = loaded[names[-1]]
    extend_snapshot_validator(auditor, current_probe)
    auditor.audit_protocol = audit_protocol.ProtocolAuditor(auditor.audit_protocol, root, freeze)
    base.FREEZE, base.METHOD = freeze, phase.METHOD
    base.PINNED_RUNTIME, base.PINNED_DOCUMENTS = runtime, dict(phase.PINNED_DOCUMENTS)
    proof[OBSERVATION_SOURCE]["snapshot_validator_override"] = {
        "rules": list(current_probe.CANDIDATE_RULES.values()),
        "scope": ("exact reviewed candidate digest/schema dispatch; "
                  "v3 activity encoder validation; "
                  "legacy/contact/clock/command/scalar rules retained"),
        "original_auditor_files_modified": False}
    return base, auditor, command, proof


def load_native_gates(root, freeze):
    directory = root / WIRELESS / "report/assets/20261015_mr3_p1c"
    phase = load_pinned("mr3_p2a_phase_v3", directory /
                        "audit_mr3_env_contact_phase_v3.py", PHASE_SHA256)
    task_relative = WIRELESS + "MR3_TASK_CONTRACT.md"
    source_task = subprocess.check_output(["git", "show", freeze + ":" + task_relative], cwd=root)
    source_task_digest = hashlib.sha256(source_task).hexdigest()
    require(source_task_digest in (TASK_DOCUMENT_SHA256, PRIOR_TASK_DOCUMENT_SHA256),
            "source task document is not an explicitly pinned status revision")
    # These exact task documents differ in delivery status. Relative to W7
    # they also clarify the still-unapproved budget per run. Original runtime
    # pins and the contact/command-time implementations remain unchanged.
    phase.PINNED_DOCUMENTS = {
        **phase.PINNED_DOCUMENTS,
        WIRELESS + "MR3_ENV_CONTRACT.md": ENV_DOCUMENT_SHA256,
        task_relative: source_task_digest}
    base, auditor, command, proof = load_compatible_components(phase, root, freeze)
    original_scalar = load_pinned("mr3_p2a_scalar_v3", directory / "reward_gate_audit_v3.py",
                                  SCALAR_SHA256)
    require(audit_scalar.ORIGINAL_SCALAR_SHA256 == SCALAR_SHA256,
            "causal scalar wrapper does not preserve the original helper pin")
    scalar = SimpleNamespace(
        audit_episode=partial(audit_scalar.audit_episode, original=original_scalar))
    require(sha(root / WIRELESS / "MR3_ENV_CONTRACT.md") == ENV_DOCUMENT_SHA256,
            "current accepted environment document differs from explicit P2A pin")
    require(sha(root / task_relative) == TASK_DOCUMENT_SHA256,
            "current accepted task document differs from explicit P2A status pin")
    proof[WIRELESS + "MR3_ENV_CONTRACT.md"].update(verify_environment_appendix(root, freeze))
    proof[task_relative].update(
        current_status_sha256=TASK_DOCUMENT_SHA256,
        native_document_sha256=source_task_digest, status_only_revision=True)
    config = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/config/mr3_p1a/"
    machine_paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", TASK_BASE_FREEZE, "--", config],
        cwd=root, text=True).splitlines()
    machine_paths += ["ros2_ws/ros2-multi-robot-automap/src/multi_robot/worlds/p1c_" +
                      scene + ".world" for scene in ("open", "rooms", "corridors")]
    require(len(machine_paths) > 3, "original machine task contract is unavailable")
    for relative in machine_paths:
        proof[relative] = verify_machine_task_file(root, freeze, relative)
    for filename in ("audit_ppo.py", "audit_scalar.py", "audit_protocol.py",
                     "audit_evaluator_phase.py", "audit_preparation.py", "audit_activity.py",
                     "audit_motion.py", "audit_controlled_physics.py",
                     "navigation_archive.py", "ppo.py",
                     "rollout.py", "policy.py",
                     "model.py", "env.py", "ipc.py", "benchmark.py",
                     "observation.py", "supervisor.py", "requirements-env.txt",
                     "requirements-ppo.txt"):
        relative = WIRELESS + "mr3_learning/" + filename
        blob = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        digest = hashlib.sha256(blob).hexdigest()
        require(digest == sha(root / relative),
                "learner worktree differs from freeze: " + filename)
        proof[relative] = {"sha256": digest, "git_source": freeze + ":" + relative}
    return phase, base, auditor, command, scalar, proof


def native_decisions(directory):
    """Reconstruct inputs and settlements from actual system-ROS receipts."""
    transitions = load_rows(directory / "transitions.jsonl")
    require(transitions and transitions[0]["kind"] == "reset", "native reset missing")
    previous = transitions[0]["snapshot"]
    decisions = []
    for row in transitions[1:]:
        require(row["kind"] == "step", "unexpected native transition kind")
        info = row["info"]
        if info.get("action_submitted", True) is False:
            require(decisions and row["terminated"] and not row["truncated"]
                    and info["dt"] == 0 and row["snapshot"] == previous,
                    "unproven no-action terminal settlement")
            decisions[-1].update(reward=decisions[-1]["reward"] + row["reward"],
                                 terminated=True, truncated=False)
        else:
            command = info["command"]
            require(command["observation_digest"] == previous["digest"]
                    and command["observation_sequence"] == previous["sequence"],
                    "submitted action not bound to preceding native snapshot")
            decisions.append({"observation": encode_snapshot(previous),
                              "following": encode_snapshot(row["snapshot"]),
                              "action": command["action"], "reward": row["reward"],
                              "dt": info["dt"], "terminated": row["terminated"],
                              "truncated": row["truncated"],
                              "snapshot_digest": previous["digest"]})
        previous = row["snapshot"]
    require(decisions and (decisions[-1]["terminated"] or decisions[-1]["truncated"]),
            "native decision episode is incomplete")
    return decisions, len(transitions) - 1


def policy_replay(model, decisions, *, deterministic):
    """Evaluate saved actions using the policy that actually collected them."""
    model.policy.set_training_mode(False)
    for start in range(0, len(decisions), 16):
        rows = decisions[start:start + 16]
        batch = {key: np.stack([row["observation"][key] for row in rows])
                 for key in observation_space().spaces}
        masks = batch["action_mask"].astype(bool)
        actions = np.asarray([row["action"] for row in rows], dtype=np.int64)
        require(np.all((actions >= 0) & (actions < 1000))
                and masks[np.arange(len(rows)), actions].all(),
                "native selected action violates its actual saved mask")
        with torch.no_grad():
            tensors, _ = model.policy.obs_to_tensor(batch)
            values, log_probs, _ = model.policy.evaluate_actions(
                tensors, torch.as_tensor(actions), action_masks=masks)
            if deterministic:
                predicted, _ = model.predict(batch, deterministic=True, action_masks=masks)
                require(np.array_equal(predicted, actions),
                        "evaluation action differs from frozen deterministic policy")
        for index, row in enumerate(rows):
            row["value"] = float(values[index].cpu().item())
            row["log_prob"] = float(log_probs[index].cpu().item())
            require(np.isfinite(row["value"]) and np.isfinite(row["log_prob"]),
                    "policy replay produced nonfinite outputs")
            if row["terminated"]:
                row["next_value"] = 0.
            else:
                with torch.no_grad():
                    following, _ = model.policy.obs_to_tensor(row["following"])
                    row["next_value"] = float(model.policy.predict_values(following).cpu().item())
    goal_components = sum(sum(choice < 8 for choice in (
        row["action"] // 100, row["action"] // 10 % 10, row["action"] % 10)) for row in decisions)
    return {"decisions": len(decisions), "legal_actions": len(decisions),
            "candidate_choice_components": goal_components,
            "deterministic_actions_verified": deterministic,
            "input_scope": "encode_snapshot of original preceding native snapshot only"}


def audit_rollout(path, decisions, *, gamma=.99, gae_lambda=.95):
    """Bind stored actor samples, masks, rewards and duration-aware GAE to native data."""
    with np.load(path, allow_pickle=False) as archive:
        data = {key: archive[key] for key in archive.files}
    count = len(decisions)
    require(count >= 1, "rollout needs a submitted decision")
    for key, array in data.items():
        require(np.isfinite(array).all(), "nonfinite rollout field: " + key)
    expected_keys = {"obs_" + key for key in observation_space().spaces} | {
        "actions", "masks", "rewards", "values", "log_probs", "advantages", "returns",
        "dt", "terminated", "truncated", "next_values"}
    require(set(data) == expected_keys,
            "rollout fields differ from declared actor/target contract")
    for key in observation_space().spaces:
        expected = np.stack([row["observation"][key] for row in decisions])[:, None]
        require(np.array_equal(data["obs_" + key], expected),
                "rollout tensor differs from native received snapshot: " + key)
    masks = data["masks"]
    require(np.array_equal(masks, data["obs_action_mask"])
            and np.isin(masks, (0, 1)).all(), "saved mask differs from actor observation mask")
    exact = {"actions": np.asarray([row["action"] for row in decisions])[:, None, None],
             "dt": np.asarray([row["dt"] for row in decisions]),
             "terminated": np.asarray([row["terminated"] for row in decisions]),
             "truncated": np.asarray([row["truncated"] for row in decisions])}
    for key, expected in exact.items():
        require(np.array_equal(data[key], expected), "native rollout mismatch: " + key)
    discrepancies = {}
    for key, field in (("rewards", "reward"), ("values", "value"),
                       ("log_probs", "log_prob"), ("next_values", "next_value")):
        expected = np.asarray([row[field] for row in decisions]).reshape(data[key].shape)
        require(np.allclose(data[key], expected, atol=POLICY_ATOL, rtol=POLICY_RTOL),
                "native/pre-update collecting-policy mismatch: " + key)
        discrepancies[key] = float(np.max(np.abs(data[key] - expected)))
    advantages = np.zeros(count)
    carry = 0.
    for index in reversed(range(count)):
        row = decisions[index]
        value = float(data["values"][index, 0])
        next_value = 0. if row["terminated"] else float(data["next_values"][index])
        discount = gamma ** row["dt"]
        delta = float(data["rewards"][index, 0]) + discount * next_value - value
        closed = row["terminated"] or row["truncated"]
        carry = delta + (0. if closed else discount * gae_lambda ** row["dt"] * carry)
        advantages[index] = carry
    require(np.allclose(data["advantages"].reshape(-1), advantages, atol=1e-4, rtol=1e-5),
            "duration-aware GAE/closed-episode recursion differs")
    require(np.allclose(data["returns"], data["advantages"] + data["values"],
                        atol=1e-5, rtol=1e-5), "returns do not equal saved advantages plus values")
    return {"path": str(path), "sha256": sha(path), "decisions": count,
            "all_fields_finite": True, "native_tensors_exact": True,
            "sampling_masks_exact": True, "duration_gae_verified": True,
            "pre_update_replay_max_abs_error": discrepancies,
            "policy_cpu_atol": POLICY_ATOL, "policy_cpu_rtol": POLICY_RTOL}


def collecting_checkpoint(directory, mode, round_index, updated_rounds):
    """Use actual update chronology even if prior native evidence failed."""
    previous = ([row["round"] for row in updated_rounds if row["round"] < round_index]
                if mode == "train" else [])
    return (directory / f"checkpoint_{max(previous):04d}.zip" if previous
            else directory / "initial.zip")


def audit_run(directory, freeze):
    directory = Path(directory).resolve()
    root = next(parent for parent in Path(__file__).resolve().parents
                if (parent / ".git").exists())
    require(re.fullmatch(r"[0-9a-f]{40}", freeze) is not None, "exact source freeze required")
    metadata = load_json(directory / "metadata.json")
    summary = load_json(directory / "summary.json")
    require(metadata["freeze"] == summary["freeze"] == freeze, "run source freeze mismatch")
    phase, base, native_auditor, command, scalar, proof = load_native_gates(root, freeze)
    result = {"schema": "mr3-p2a-ppo-offline-audit-v1", "directory": str(directory),
              "freeze": freeze, "mode": metadata["mode"], "errors": [], "episodes": [],
              "rounds": [], "source_proof": proof, "original_helpers_modified": False,
              "native_gates": ("phase-v2 contact + phase-v3 command + scalar-v3; "
                               "causal scalar: " + audit_scalar.METHOD + "; proven unsent: "
                               + audit_protocol.METHOD + "; evaluator ACK: "
                               + audit_evaluator_phase.METHOD),
              "helper_sha256": {"phase_v3": PHASE_SHA256, "scalar_v3": SCALAR_SHA256},
              "task_success_credit": "only original evaluator success with passed native gates"}

    def check(label, operation):
        try:
            return operation()
        except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError) as error:
            result["errors"].append(label + ": " + str(error))
            return None

    listed = {Path(row["directory"]).resolve(): row for row in summary["episodes"]}
    discovered = sorted(path.parent.resolve() for path in (directory / "native").glob(
        "round*/worker*/episode*/metadata.json"))
    check("native attempts", lambda: require(discovered and set(discovered) == set(listed),
          "every attempted native episode, including failures, must appear in summary"))
    rounds = {}
    for native in discovered:
        row = {"directory": str(native), "errors": []}
        try:
            native_meta = load_json(native / "metadata.json")
            epoch = native_meta["epoch"]
            row.update(epoch=epoch, scene=native_meta["scene"], seed=native_meta["seed"])
            motion_cache = {}
            original_readiness = native_auditor.audit_initial_inputs_ready
            original_physics = dispatch_controlled_physics(native_auditor, [native], motion_cache)
            try:
                dispatch_controlled_readiness(native_auditor, [native], motion_cache)
                row["native"] = phase.corrected_audit(base, native_auditor, command, [native])
            finally:
                native_auditor.audit_physics = original_physics
                native_auditor.audit_initial_inputs_ready = original_readiness
            row["scalar"] = scalar.audit_episode(native, freeze)
            row["evaluator_phase"] = audit_evaluator_phase.audit_episode(native)
            row["odometry_cadence"] = audit_odometry_cadence.audit(native, freeze)
            evaluation = load_json(native / (epoch + ".json"))
            row["task"] = {key: evaluation[key] for key in (
                "success", "termination_reason", "correct_free_coverage_ratio", "map_quality_pass",
                "robot_participation_pass", "collision_events", "collision_monitoring_fresh",
                "navigation_protocol_closed", "elapsed_sim_time_sec", "time_to_95_coverage_sec")}
            require(row["native"]["passed"], "original native gates: " +
                    "; ".join(row["native"]["errors"]))
            require(not row["scalar"]["errors"], "original scalar gates: " +
                    "; ".join(row["scalar"]["errors"]))
            require(row["odometry_cadence"]["passed"] is True,
                    "independent real odometry cadence/received-source gate failed")
            require(evaluation["schema_version"] == 4 and evaluation["robot_count"] == 3
                    and evaluation["coverage_threshold"] == .95
                    and evaluation["max_duration_sec"] == 300., "task contract gate changed")
            if evaluation["success"]:
                require(evaluation["correct_free_coverage_ratio"] >= .95
                        and evaluation["map_quality_pass"]
                        and evaluation["robot_participation_pass"]
                        and evaluation["collision_events"] == 0
                        and evaluation["collision_monitoring_fresh"]
                        and evaluation["navigation_protocol_closed"]
                        and evaluation["elapsed_sim_time_sec"] < 300.,
                        "claimed task success violates original task gates")
            decisions, api_count = native_decisions(native)
            recorded = listed[native]
            require(recorded["decisions"] == len(decisions)
                    and recorded["api_records"] == api_count,
                    "run/native decision and API counts differ")
            require(np.isclose(recorded["reward_sum"], sum(x["reward"] for x in decisions))
                    and np.isclose(recorded["simulation_seconds"],
                                   sum(x["dt"] for x in decisions)),
                    "run/native reward or simulation-duration totals differ")
            round_id = int(native.parent.parent.name.removeprefix("round"))
            rounds.setdefault(round_id, []).append((recorded["episode_index"], decisions, row))
        except (OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError) as error:
            row["errors"].append(str(error))
            result["errors"].append(str(native) + ": " + str(error))
        result["episodes"].append(row)
    initial = directory / "initial.zip"
    check("initial checkpoint hash", lambda: require(
        sha(initial) == summary["initial_checkpoint_sha256"], "initial checkpoint hash differs"))
    for index, entries in sorted(rounds.items()):
        checkpoint = collecting_checkpoint(directory, metadata["mode"], index, summary["rounds"])
        round_result = {"round": index, "collecting_checkpoint": str(checkpoint)}

        def replay_round():
            model = MaskablePPO.load(checkpoint, device="cpu")
            decisions = []
            for _, episode, episode_result in sorted(entries, key=lambda entry: entry[0]):
                episode_result["policy"] = policy_replay(
                    model, episode, deterministic=metadata["mode"] == "evaluate")
                decisions.extend(episode)
            round_result["collecting_checkpoint_sha256"] = sha(checkpoint)
            round_result["rollout"] = audit_rollout(
                directory / f"rollout_{index:04d}.npz", decisions,
                gamma=metadata["gamma_per_second"], gae_lambda=metadata["lambda_per_second"])
            if metadata["mode"] == "train" and len(decisions) >= 2:
                updated_path = directory / f"checkpoint_{index:04d}.zip"
                updated = MaskablePPO.load(updated_path, device="cpu")
                changed = parameter_changes(model, updated)
                declared = [row for row in summary["rounds"] if row["round"] == index]
                require(len(declared) == 1 and changed > 0
                        and declared[0]["changed_parameter_tensors"] == changed
                        and updated._n_updates > model._n_updates,
                        "post-update checkpoint lacks real parameter/optimizer change")
                round_result.update(updated_checkpoint_sha256=sha(updated_path),
                                    changed_parameter_tensors=changed)
            return decisions
        check("round " + str(index), replay_round)
        result["rounds"].append(round_result)
    check("completed run", lambda: require(summary["completed"] and summary["error"] is None
          and not summary["cleanup_errors"], "run has an error/incomplete native closure"))
    check("decision totals", lambda: require(
        summary["decisions"] == sum(row["decisions"] for row in summary["episodes"])
        and summary["api_records"] == sum(row["api_records"] for row in summary["episodes"]),
        "summary count totals differ"))
    if metadata["mode"] == "train":
        check("optimizer evidence", lambda: require(summary["optimizer_updates"] > 0
              and summary["rounds"] and all(row["changed_parameter_tensors"] > 0
              and all((value is None and key == "train/explained_variance")
                      or (value is not None and np.isfinite(value))
                      for key, value in row["metrics"].items())
              for row in summary["rounds"]), "no finite real PPO optimizer update evidence"))
    else:
        check("evaluation schedule", lambda: require(
            len(summary["episodes"]) == len(metadata["schedule"])
            and all((row["scene"], row["seed"]) == tuple(task)
                    for row, task in zip(summary["episodes"], metadata["schedule"])),
            "evaluation did not retain the complete declared schedule"))
        check("evaluation optimizer", lambda: require(summary["optimizer_updates"] == 0,
                                                      "evaluation performed optimizer updates"))
        check("input checkpoint hash", lambda: require(sha(metadata["checkpoint"]) ==
              summary["input_checkpoint_sha256"], "frozen evaluation checkpoint changed"))
        check("evaluation frozen weights", lambda: require(
            parameter_changes(MaskablePPO.load(directory / "initial.zip", device="cpu"),
                              MaskablePPO.load(directory / "final.zip", device="cpu")) == 0
            and parameter_changes(MaskablePPO.load(directory / "initial.zip", device="cpu"),
                                  MaskablePPO.load(metadata["checkpoint"], device="cpu")) == 0,
            "evaluation weights differ from original frozen input checkpoint"))
    check("final checkpoint hash", lambda: require(sha(directory / "final.zip") ==
          summary["final_checkpoint_sha256"], "final checkpoint hash differs"))
    result["native_attempts"] = len(discovered)
    result["task_successes"] = sum(
        row.get("task", {}).get("success", False) and not row["errors"]
        for row in result["episodes"])
    result["task_failures"] = [{"epoch": row.get("epoch"), "task": row.get("task"),
                                "audit_errors": row["errors"]} for row in result["episodes"]
                               if row["errors"] or not row.get("task", {}).get("success", False)]
    result["passed"] = not result["errors"]
    result["scope"] = "pilot audit only; no statistical baseline superiority or network credit"
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("audit output exists; choose a new path")
    torch.set_num_threads(1)
    result = audit_run(args.directory, args.freeze)
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": result["passed"], "native_attempts": result["native_attempts"],
                      "task_successes": result["task_successes"], "errors": result["errors"]}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
