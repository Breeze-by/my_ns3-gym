"""Source-bound reach-profile dispatch to the immutable native scientific gates.

The new plan explicitly versions changed execution sources. Unchanged W7 truth,
reward, task, SLAM and independent mathematics keep their original exact pins.
"""

from pathlib import Path
import hashlib
import subprocess

from .reach_audit_projection import project_module
from . import audit_reach_sensor_model
from .supervisor import validate_seed_rule

PPO_READER_SHA256 = "b2e0737d79826b7ecb319cc91b58ff45475ea831a9cb2b4cab2298aaf6474567"
PROTOCOL_READER_SHA256 = "08bc1ee209761be2108a3d1d0248f2d0ab40b9fc68539ecedffec11cb81fd1647"
ENV_SHA256 = "e21cade7fecc17461007903e74ccd870c26e1d1e4a766731c2850dd567a73869"
EXACT_ENV_SHA256 = "1cebd1d5c6abf2750991a40ab50065c4f9b655f11f30e3f1734ea2130612d143"
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


def project_exact_environment(raw):
    """Remove only the two declared insertions, restoring the entire prior file."""
    if hashlib.sha256(raw).hexdigest() != EXACT_ENV_SHA256:
        raise ValueError("exact seed environment document SHA differs")
    status = "2026-10-21：新增显式 `seed_rule=exact-point-bridge-v1` 观测规则，默认仍为 `legacy`。\n".encode()
    start = "显式 `exact-point-bridge-v1` 保留上述地图合成、原seed cell、原图及 `.29m` 路径门。\n".encode()
    end = "adapter模式的controller和behavior速度统一经过Nav2 smoother及`/motion_safety`最终门，\n".encode()
    if raw.count(status) != 1 or raw.count(ENV_STATUS) != 1 or raw.count(start) != 1 or raw.count(end) != 1:
        raise ValueError("exact seed environment insertion boundaries differ")
    first, last = raw.index(status), raw.index(ENV_STATUS)
    if first >= last:
        raise ValueError("exact seed environment status order differs")
    restored = raw[:first] + raw[last:]
    first, last = restored.index(start), restored.index(end)
    if first >= last:
        raise ValueError("exact seed environment section order differs")
    restored = restored[:first] + restored[last:]
    if hashlib.sha256(restored).hexdigest() != ENV_SHA256:
        raise ValueError("exact seed environment inverse does not restore the whole prior document")
    return restored, {"sha256": EXACT_ENV_SHA256, "whole_prior_document_inverse_sha256": ENV_SHA256,
                      "prior_document_bytes": len(restored), "new_document_bytes": len(raw),
                      "scope": "two declared exact-seed insertions only; complete prior file restored"}


def load_exact_protocol(adapter_sha256):
    """Version the adapter source identity without changing protocol predicates."""
    protocol, proof = project_module("audit_protocol.py", PROTOCOL_READER_SHA256, ())
    relative = ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py"
    previous = protocol.PINS[relative]
    protocol.PINS = {**protocol.PINS, relative: adapter_sha256}
    proof["versioned_adapter_pin"] = {"path": relative, "previous_sha256": previous,
                                      "new_source_sha256": adapter_sha256}
    return protocol, proof


def extend_exact_snapshot_validator(original_validator, auditor, candidate_module):
    """Add one exact native rule and retain the complete original validator."""
    rule = {**candidate_module.CANDIDATE_RULE_V5,
            "version": "mr3-navigation-geometric-staging-v6-exact-seed-v1",
            "seed_rule": "exact-point-bridge-v1"}
    candidate_module.CANDIDATE_RULES = {**candidate_module.CANDIDATE_RULES, rule["version"]: rule}
    original_validator(auditor, candidate_module)
    validate = auditor.validate_snapshot

    def exact_snapshot(snapshot, epoch):
        if snapshot.get("schema") != "mr3-observation-v3" or snapshot.get("candidate_rule") != rule:
            raise ValueError("native actor did not use the declared exact seed candidate rule")
        return validate(snapshot, epoch)

    auditor.validate_snapshot = exact_snapshot


def load_native_gates(root, freeze, plan_path):
    from .reach_preparation import load_plan, source_check
    root, plan_path = Path(root), Path(plan_path)
    plan = load_plan(plan_path, root)
    source_proof = source_check(plan, plan_path, freeze, root, require_clean=False)
    return _load_versioned_native_gates(root, freeze, source_proof,
        plan["source_bindings"], plan["custody_binding"],
        **({"seed_rule": plan["seed_rule"]} if plan.get("seed_rule", "legacy") != "legacy" else {}))


def _load_versioned_native_gates(root, freeze, source_proof, source_bindings, custody_binding,
                                 *, seed_rule="legacy"):
    """Reuse unchanged native predicates after an explicit caller source check.

    The public qualification entry above still requires its complete sealed
    four-stage plan. A separately labelled diagnostic can bind its own finite
    source inventory without manufacturing a qualification plan or receipt.
    """
    from . import native_custody_reach
    root = Path(root)
    validate_seed_rule(seed_rule)
    legacy, projection = project_module("audit_ppo.py", PPO_READER_SHA256, ())
    revised_runtime = set(REVISED_RUNTIME)
    protocol_projection = None
    if seed_rule != "legacy":
        adapter_source = ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py"
        revised_runtime.add(adapter_source)
        legacy.audit_protocol, protocol_projection = load_exact_protocol(source_bindings[adapter_source])
        legacy.OBSERVATION_SHA256 = source_bindings[legacy.OBSERVATION_SOURCE]
        original_validator = legacy.extend_snapshot_validator

        def extend_exact_validator(auditor, candidate_module):
            extend_exact_snapshot_validator(original_validator, auditor, candidate_module)

        legacy.extend_snapshot_validator = extend_exact_validator
    old_env_sha = legacy.ENV_DOCUMENT_SHA256
    environment_sha = EXACT_ENV_SHA256 if seed_rule != "legacy" else ENV_SHA256

    def environment_document(root, freeze):
        relative = legacy.WIRELESS + "MR3_ENV_CONTRACT.md"
        raw = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        require = legacy.require
        require(hashlib.sha256(raw).hexdigest() == legacy.sha(root / relative) == environment_sha
                and raw.count(ENV_STATUS) == 1, "reach environment status revision differs")
        exact_projection = None
        if seed_rule != "legacy":
            raw, exact_projection = project_exact_environment(raw)
        projected = raw.replace(ENV_STATUS, b"", 1)
        normative = subprocess.check_output(["git", "show", legacy.ENV_NORMATIVE_FREEZE + ":" + relative], cwd=root)
        require(hashlib.sha256(projected).hexdigest() == old_env_sha
                and hashlib.sha256(normative).hexdigest() == legacy.ENV_NORMATIVE_SHA256
                and projected.startswith(normative)
                and len(projected) == len(normative) + legacy.ENV_EXECUTION_APPENDIX_BYTES
                and hashlib.sha256(projected[len(normative):]).hexdigest() == legacy.ENV_EXECUTION_APPENDIX_SHA256,
                "environment status inverse does not restore complete old document/normative prefix")
        return {"environment_revision": "explicit_reach_status_dispatch_v1",
                "sha256": environment_sha, "whole_document_inverse_sha256": old_env_sha,
                "normative_prefix_sha256": legacy.ENV_NORMATIVE_SHA256,
                "legacy_numeric_and_task_rules_preserved": True,
                "reach_execution_rules": "MR3_REACH_CONTRACT.md and independent new runtime gates",
                **({"exact_seed_environment_projection": exact_projection} if exact_projection else {})}

    legacy.ENV_DOCUMENT_SHA256 = environment_sha
    legacy.verify_environment_appendix = environment_document
    # Each replacement is a declared runtime version, never a change to the
    # independent gate implementation. All other pins below remain untouched.
    revised_proof = {}
    for name in ("EVALUATOR_PHASE_PINS", "PREPARATION_RUNTIME_PINS"):
        pins = dict(getattr(legacy, name))
        for path in revised_runtime & pins.keys():
            revised_proof[path] = {"previous_scope_sha256": pins[path],
                                  "new_source_sha256": source_bindings[path]}
            pins[path] = source_bindings[path]
        setattr(legacy, name, pins)

    def execution_configs(root, freeze):
        retained = {p: d for p, d in legacy.EXECUTION_CONFIG_PINS.items()
                    if p not in REVISED_CONFIG}
        proof = legacy.verify_frozen_pins(root, freeze, retained, "unchanged execution config")
        proof.update({p: source_proof[p] for p in REVISED_CONFIG})
        return proof

    def native_binding(root, freeze):
        result = native_custody_reach.verify_binding(root, freeze, custody_binding)
        return {custody_binding: {"identity_proof": result,
                "scope": "new six-source actual ELF identity; live maps/close are separate required roles"}}

    legacy.verify_execution_configs = execution_configs
    legacy.verify_current_native_binding = native_binding
    legacy.verify_velocity_smoother_overlay = native_binding
    phase, base, auditor, command, scalar, proof = legacy.load_native_gates(root, freeze)
    if seed_rule != "legacy":
        extra = {ROS + "src/multi_robot_exploration/multi_robot_exploration/" + filename:
                 source_bindings[ROS + "src/multi_robot_exploration/multi_robot_exploration/" + filename]
                 for filename in ("mr3_seed_certificate.py", "mr3_reach_geometry.py")}
        proof.update(legacy.verify_frozen_pins(root, freeze, extra, "exact seed certificate dependencies"))
    _,sensor_projection = audit_reach_sensor_model.load_spawn_impl()
    audit_reach_sensor_model.attach_native_gate(phase,root,freeze)
    proof.update(source_proof)
    proof["reach_dispatch"] = {"schema": "mr3-reach-native-gate-dispatch-v1",
        "safety_contract": "mr3-reach-v1", "immutable_reader": projection,
        "versioned_runtime": revised_proof,
        "versioned_execution_config": sorted(REVISED_CONFIG),
        "sensor_profile":audit_reach_sensor_model.PROFILE,
        "sensor_reader_projection":sensor_projection,
        "sensor_model_gate":"actual spawn and unique20Hz ray; whole-byte inverse restores original5Hz model",
        "original_mathematical_predicates_changed": False,
        "old_profile_qualification_credit_reused": False}
    if seed_rule != "legacy":
        proof["reach_dispatch"]["seed_rule"] = seed_rule
        proof["reach_dispatch"]["candidate_rule_version"] = "mr3-navigation-geometric-staging-v6-exact-seed-v1"
        proof["reach_dispatch"]["protocol_reader_projection"] = protocol_projection
    return phase, base, auditor, command, scalar, proof
