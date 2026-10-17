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

from . import audit_evaluator_phase, audit_protocol, audit_scalar
from .audit_controlled_physics import dispatch_controlled_physics
from .observation import encode_snapshot, observation_space


WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ROS = "ros2_ws/ros2-multi-robot-automap/"
OBSERVATION_SOURCE = ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py"
OBSERVATION_SHA256 = "b81da18c256ff307a4afc09c5115d0057e5a142a246555f39c1f7a5cee88c6e8"
REWARD_SOURCE = ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_reward.py"
W7_REWARD_SHA256 = "77485e7988489a146e4c44207343a0a4be7c12b5ffe36906dde59257cac16f88"
EVALUATOR_PHASE_PINS = {
    ROS + 'scripts/mr3_env_worker.py':
        '2da3ba79c20c1d2516c74eb6201384847fe08e1f6a41b0a64d7ec6013d4fd712',
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
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py':
        '90444564b04b86982553a7fe6e0b98beb290ba92c3ab1e32e503998e6411fc1c',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_observation_archive.py':
        '03da72d5e989e6c7af99b90aaddf357120c2239fc08e99febb858554b1fefea8',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/peer_obstacles.py':
        'ac0834ab362a771efddbbb656d27edee176b9089be81a83f55ad3a2440065898',
    ROS + 'src/merge_map/merge_map/merge_map.py':
        '76c3d2c604f38f61116be1f39263472f9074b4f69fe7a0428b532da977530078',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_information.py':
        'b46d098cb9a762a7558ea84adf85d943f1e631b248b478a9ce1a2d6b0b07e644',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_activity.py':
        '7af918d75c05b6f8fb1a65899e43aad11a315640e8b00fdb589c31f693ad696e',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_protocol.py':
        '5a2b90efd162b19a35964750002fe549413fec6e07f9679ea611d3fe6b1e4ada',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_motion_safety.py':
        'fc1adb189922e5b7f7d62ece2a3bdf9720fb3766916bc98b3f74d71930906ef8',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/motion_safety.py':
        'd6f3d950736d927efc3bafba31bc55d3fed73b480d941de22dbab13e77bbb6a3',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/control.py':
        'f595fd1e999a5cbe9d0f33db549d7aba0af615703b589ef14ff2538a871e380c',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_drive_phase.py':
        '0525230f4719e7279826810f0c177f6a6317a961d50711ac76d8a0338f93d987',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_control_phase.py':
        '9d7b0cc64d2eb9cd4aee49de50feb63ebf117a31b41cc000119c2f4ea2741e15',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_motion_control.py':
        '6f13f59d0959c92ef5bf4e3492285e7e5b086958daa4fd33a0362db484e8627e',
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
        '342679598ebfa27b503cf5be16cf921c35c32a4dcd8cd0f861df9f70ed2cde07',
    ROS + 'src/multi_robot/params/nav2_params_tb2_0.yaml':
        '022e3ff990ace0a30fee4e0bd2917ee02a3ee1cd96e8ff566e54d25b2048906e',
    ROS + 'src/multi_robot/params/nav2_params_tb3_0.yaml':
        'ddc3c75ae0a3add7e2055458bab1cbe138c24c32a0897b2669560dfd52791281',
    ROS + 'src/multi_robot/config/nav2_params.yaml':
        '53b1fd403a55b6567a238efe954fadd40f572347f18bd0d258993b0e8d10d723',
    ROS + 'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py':
        '9a281992530cd0b4f36f72e1ae5a9ccfed441599b511e5599ee738a0e889a4a7',
    ROS + 'src/multi_robot/launch/nav2_bringup/bringup_launch.py':
        '41b7e5e65c2c61ce6f1efb5a9288c3875e60f6c9054d77f96f7fc6f0a6f2aa53',
    ROS + 'src/multi_robot/launch/nav2_bringup/navigation_launch.py':
        'ee4a7b7d590eb9f1a8129d025e99ceaf5908537d0063144da159d5a7ae8fd209',
    ROS + 'src/multi_robot_exploration/setup.py':
        'a23cd0dc598ebb59d9eae325bd1a6ee0ae700751986cac6858fe2c2949b68a15',
    ROS + 'src/multi_robot/models/turtlebot3_waffle/model.sdf':
        'c8131da065085475bdb0ce1e4c3abfc8c009811af6851fadf1fc33bd38b1d8a1',
    ROS + 'src/multi_robot/CMakeLists.txt':
        '84c4ecd5d04d20567406b8cc6079e20bc1366012b762e2d01aa600d15899a38d',
    ROS + 'src/multi_robot/package.xml':
        'befde661174ae259974b6dcfe1ff98f8ce44568fd2ec94663303de413b7d1601',
    ROS + 'src/multi_robot/src/mr3_gazebo_diff_drive.cpp':
        '09f741ee154d620fb3d62f8473853929231093fd8cc0b9a4be62b535b514dc05',
    ROS + 'src/multi_robot/include/multi_robot/mr3_gazebo_diff_drive.hpp':
        'a7c237943e8728f72cd39e815b8aa47c0bff45374941293aacf77384e3c4b63e',
    ROS + 'src/multi_robot/include/multi_robot/paired_wheel_slew.hpp':
        '80cf2e51f1b39f7bb89ef8b61b4b6eaf7c9be68c418bf0bb7ef57640d82c99d9',
    ROS + 'src/multi_robot/vendor/gazebo_ros_diff_drive.PROVENANCE.md':
        '30f8bcd5a84fed138c076d9ee4ae96e1899d09c1aa932b784db03a5ff735465d',
    ROS + 'src/multi_robot/vendor/gazebo_ros_diff_drive.BSD-3-Clause.txt':
        '771978f82c58310201ccdfdfd66e8ca798d26c2202d77f32a131d60bd297a545',
    WIRELESS + 'MR3_ADAPTER_CONTRACT.md':
        '4cc62c7ac015b7489bd14d4e346723ef7a15fef7212f21ff67aa9e5d0a6aa3bb',
    ROS + 'src/multi_robot/include/multi_robot/mr3_drive_target.hpp':
        'a1a11a73ac5c416d6d548249829717ccb262005498566c0bcc8dc1997999b9ba',
}
ENV_DOCUMENT_SHA256 = "bff928d151130e22def798c359f2eb56fa1b937213c324ee1c389857ef890f33"
TASK_DOCUMENT_SHA256 = "f96f5ba785a39daa882b3c2ea217c58dd968550b65bf0ee15faf07ca079f8991"
PRIOR_TASK_DOCUMENT_SHA256 = "5e4400396e4aaf5a5094fb4c0c04c85810c327cc85be88b7d03fa3faeade07d2"
TASK_BASE_FREEZE = "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a"
PHASE_SHA256 = "4e2a24e3465fa45c06c05c37b57b8b77b6e462845b3227be10c1fecb85c2c7d7"
SCALAR_SHA256 = "895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665"
POLICY_ATOL = 1e-4  # CPU replay of CUDA collecting inference; never a task tolerance.
POLICY_RTOL = 1e-5


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
    proof.update(verify_frozen_pins(root, freeze, EXECUTION_CONFIG_PINS, "execution config"))
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
        normative = subprocess.check_output(
            ["git", "show", TASK_BASE_FREEZE + ":" + relative], cwd=root)
        actual = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        digest = hashlib.sha256(normative).hexdigest()
        require(actual == normative and sha(root / relative) == digest,
                "machine task/geometry changed from accepted W7 contract: " + relative)
        proof[relative] = {"sha256": digest, "git_source": freeze + ":" + relative,
                           "normative_source": TASK_BASE_FREEZE + ":" + relative}
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
            original_physics = dispatch_controlled_physics(native_auditor, [native], {})
            try:
                row["native"] = phase.corrected_audit(base, native_auditor, command, [native])
            finally:
                native_auditor.audit_physics = original_physics
            row["scalar"] = scalar.audit_episode(native, freeze)
            row["evaluator_phase"] = audit_evaluator_phase.audit_episode(native)
            evaluation = load_json(native / (epoch + ".json"))
            row["task"] = {key: evaluation[key] for key in (
                "success", "termination_reason", "correct_free_coverage_ratio", "map_quality_pass",
                "robot_participation_pass", "collision_events", "collision_monitoring_fresh",
                "navigation_protocol_closed", "elapsed_sim_time_sec", "time_to_95_coverage_sec")}
            require(row["native"]["passed"], "original native gates: " +
                    "; ".join(row["native"]["errors"]))
            require(not row["scalar"]["errors"], "original scalar gates: " +
                    "; ".join(row["scalar"]["errors"]))
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
    previous = directory / "initial.zip"
    check("initial checkpoint hash", lambda: require(
        sha(previous) == summary["initial_checkpoint_sha256"], "initial checkpoint hash differs"))
    for index, entries in sorted(rounds.items()):
        checkpoint = previous if metadata["mode"] == "train" else directory / "initial.zip"
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
        if metadata["mode"] == "train" and (directory / f"checkpoint_{index:04d}.zip").exists():
            previous = directory / f"checkpoint_{index:04d}.zip"
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
