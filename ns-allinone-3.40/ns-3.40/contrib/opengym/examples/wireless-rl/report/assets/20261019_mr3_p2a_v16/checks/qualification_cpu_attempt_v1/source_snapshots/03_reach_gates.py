"""Source-bound reach-profile dispatch to the immutable native scientific gates.

The new plan explicitly versions changed execution sources. Unchanged W7 truth,
reward, task, SLAM and independent mathematics keep their original exact pins.
"""

from pathlib import Path
import hashlib
import subprocess

from .reach_audit_projection import project_module

PPO_READER_SHA256 = "b2e0737d79826b7ecb319cc91b58ff45475ea831a9cb2b4cab2298aaf6474567"
ENV_SHA256 = "e21cade7fecc17461007903e74ccd870c26e1d1e4a766731c2850dd567a73869"
ENV_STATUS = ("2026-10-19：用户已接受[V14科学候选](report/assets/20261019_mr3_p2a_v14/scientific_contract_candidate_v1.md)。显式新profile的执行规则以[MR3_REACH_CONTRACT.md](MR3_REACH_CONTRACT.md)为准；本文件下述原速度/累计路径与v1相位规则继续描述默认`legacy`。V15已接线并完成CPU/编译准备，尚无新冻结原生资格、训练或95%信用；旧FAIL不改判。\n\n").encode()
ROS = "ros2_ws/ros2-multi-robot-automap/"
REVISED_RUNTIME = {
    ROS + "scripts/mr3_env_worker.py",
    *(ROS + "src/multi_robot_exploration/multi_robot_exploration/" + name + ".py"
      for name in ("mr3_information", "peer_obstacles", "motion_safety",
                   "mr3_control_phase", "mr3_motion_control")),
}
REVISED_CONFIG = {ROS + "src/multi_robot/CMakeLists.txt",
                  ROS + "src/multi_robot/src/mr3_gazebo_diff_drive.cpp",
                  ROS + "src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py"}


def load_native_gates(root, freeze, plan_path):
    from .reach_preparation import load_plan, source_check
    from . import native_custody_reach
    root, plan_path = Path(root), Path(plan_path)
    plan = load_plan(plan_path, root)
    source_proof = source_check(plan, plan_path, freeze, root, require_clean=False)
    legacy, projection = project_module("audit_ppo.py", PPO_READER_SHA256, ())
    old_env_sha = legacy.ENV_DOCUMENT_SHA256

    def environment_document(root, freeze):
        relative = legacy.WIRELESS + "MR3_ENV_CONTRACT.md"
        raw = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        require = legacy.require
        require(hashlib.sha256(raw).hexdigest() == legacy.sha(root / relative) == ENV_SHA256
                and raw.count(ENV_STATUS) == 1, "reach environment status revision differs")
        projected = raw.replace(ENV_STATUS, b"", 1)
        normative = subprocess.check_output(["git", "show", legacy.ENV_NORMATIVE_FREEZE + ":" + relative], cwd=root)
        require(hashlib.sha256(projected).hexdigest() == old_env_sha
                and hashlib.sha256(normative).hexdigest() == legacy.ENV_NORMATIVE_SHA256
                and projected.startswith(normative)
                and len(projected) == len(normative) + legacy.ENV_EXECUTION_APPENDIX_BYTES
                and hashlib.sha256(projected[len(normative):]).hexdigest() == legacy.ENV_EXECUTION_APPENDIX_SHA256,
                "environment status inverse does not restore complete old document/normative prefix")
        return {"environment_revision": "explicit_reach_status_dispatch_v1",
                "sha256": ENV_SHA256, "whole_document_inverse_sha256": old_env_sha,
                "normative_prefix_sha256": legacy.ENV_NORMATIVE_SHA256,
                "legacy_numeric_and_task_rules_preserved": True,
                "reach_execution_rules": "MR3_REACH_CONTRACT.md and independent new runtime gates"}

    legacy.ENV_DOCUMENT_SHA256 = ENV_SHA256
    legacy.verify_environment_appendix = environment_document
    # Each replacement is a declared runtime version, never a change to the
    # independent gate implementation. All other pins below remain untouched.
    revised_proof = {}
    for name in ("EVALUATOR_PHASE_PINS", "PREPARATION_RUNTIME_PINS"):
        pins = dict(getattr(legacy, name))
        for path in REVISED_RUNTIME & pins.keys():
            revised_proof[path] = {"previous_scope_sha256": pins[path],
                                  "new_source_sha256": plan["source_bindings"][path]}
            pins[path] = plan["source_bindings"][path]
        setattr(legacy, name, pins)

    def execution_configs(root, freeze):
        retained = {p: d for p, d in legacy.EXECUTION_CONFIG_PINS.items()
                    if p not in REVISED_CONFIG}
        proof = legacy.verify_frozen_pins(root, freeze, retained, "unchanged execution config")
        proof.update({p: source_proof[p] for p in REVISED_CONFIG})
        return proof

    def native_binding(root, freeze):
        result = native_custody_reach.verify_binding(root, freeze, plan["custody_binding"])
        return {plan["custody_binding"]: {"identity_proof": result,
                "scope": "new six-source actual ELF identity; live maps/close are separate required roles"}}

    legacy.verify_execution_configs = execution_configs
    legacy.verify_current_native_binding = native_binding
    legacy.verify_velocity_smoother_overlay = native_binding
    phase, base, auditor, command, scalar, proof = legacy.load_native_gates(root, freeze)
    proof.update(source_proof)
    proof["reach_dispatch"] = {"schema": "mr3-reach-native-gate-dispatch-v1",
        "safety_contract": "mr3-reach-v1", "immutable_reader": projection,
        "versioned_runtime": revised_proof,
        "versioned_execution_config": sorted(REVISED_CONFIG),
        "original_mathematical_predicates_changed": False,
        "old_profile_qualification_credit_reused": False}
    return phase, base, auditor, command, scalar, proof
