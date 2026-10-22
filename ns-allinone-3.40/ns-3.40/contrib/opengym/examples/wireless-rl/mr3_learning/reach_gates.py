"""Source-bound reach-profile dispatch to the immutable native scientific gates.

The new plan explicitly versions changed execution sources. Unchanged W7 truth,
reward, task, SLAM and independent mathematics keep their original exact pins.
"""

from pathlib import Path
import hashlib
import subprocess

from .reach_audit_projection import project_module
from . import audit_reach_sensor_model
from .supervisor import (EXACT_SEED_VERSIONS, POINT_START_GRAPH_RULE, POINT_GRAPH_PROFILE,
                         POINT_GRAPH_COST, candidate_version_for_rules,
                         validate_seed_rule, validate_start_graph_rule)

PPO_READER_SHA256 = "b2e0737d79826b7ecb319cc91b58ff45475ea831a9cb2b4cab2298aaf6474567"
PROTOCOL_READER_SHA256 = "8bc1ee209761be2108a3d1d0248f2d0ab40b9fc68539ecedffec11cb81fd1647"
ENV_SHA256 = "e21cade7fecc17461007903e74ccd870c26e1d1e4a766731c2850dd567a73869"
EXACT_ENV_SHA256 = "1cebd1d5c6abf2750991a40ab50065c4f9b655f11f30e3f1734ea2130612d143"
EXACT_V2_ENV_SHA256 = "11a70fb42a58c104a55a68186795226dbf2c1f4bd4170066dfaad209e63ba8d5"
POINT_GRAPH_ENV_SHA256 = "baffbf1bffc7fadff80105ec5c5dce3a04c694ce7e7a8f72ca6620d8a7c13a1a"
POINT_GRAPH_HELPER_SHA256 = "e55b776c3ec088fe51dfa76ff204b4b135138038502fabc6af01717ed75efc83"
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


def project_exact_v2_environment(raw):
    """Restore the complete V33 document by removing only its unique V34 block."""
    if hashlib.sha256(raw).hexdigest() != EXACT_V2_ENV_SHA256:
        raise ValueError("exact seed v2 environment document SHA differs")
    start = "2026-10-21 V34：新增显式 `seed_rule=exact-point-bridge-v2`，legacy与v1实现语义保留。\n".encode()
    end = "2026-10-21：新增显式 `seed_rule=exact-point-bridge-v1` 观测规则，默认仍为 `legacy`。\n".encode()
    if raw.count(start) != 1 or raw.count(end) != 1 or raw.index(start) >= raw.index(end):
        raise ValueError("exact seed v2 environment insertion boundaries differ")
    restored = raw[:raw.index(start)] + raw[raw.index(end):]
    if hashlib.sha256(restored).hexdigest() != EXACT_ENV_SHA256:
        raise ValueError("exact seed v2 inverse does not restore the whole V33 document")
    return restored, {"sha256": EXACT_V2_ENV_SHA256,
                      "whole_prior_document_inverse_sha256": EXACT_ENV_SHA256,
                      "prior_document_bytes": len(restored), "new_document_bytes": len(raw),
                      "scope": "unique V34 insertion only; complete V33 document restored"}


def load_exact_protocol(adapter_sha256):
    """Version the adapter source identity without changing protocol predicates."""
    protocol, proof = project_module("audit_protocol.py", PROTOCOL_READER_SHA256, ())
    relative = ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py"
    previous = protocol.PINS[relative]
    protocol.PINS = {**protocol.PINS, relative: adapter_sha256}
    proof["versioned_adapter_pin"] = {"path": relative, "previous_sha256": previous,
                                      "new_source_sha256": adapter_sha256}
    return protocol, proof


def project_point_graph_environment(raw):
    """Remove only V37's unique insertion, restoring the whole V34 document."""
    if hashlib.sha256(raw).hexdigest() != POINT_GRAPH_ENV_SHA256:
        raise ValueError("point graph environment document SHA differs")
    start = "2026-10-22 V37：新增正交显式".encode()
    end = "本节独立删除后必须逐字恢复V34完整环境合同；只允许显式新模式，不切换默认。\n\n".encode()
    if raw.count(start) != 1 or raw.count(end) != 1 or raw.index(start) >= raw.index(end):
        raise ValueError("point graph environment insertion boundaries differ")
    restored = raw[:raw.index(start)] + raw[raw.index(end) + len(end):]
    if hashlib.sha256(restored).hexdigest() != EXACT_V2_ENV_SHA256:
        raise ValueError("point graph inverse does not restore the whole V34 document")
    return restored, {"sha256": POINT_GRAPH_ENV_SHA256,
                      "whole_prior_document_inverse_sha256": EXACT_V2_ENV_SHA256,
                      "prior_document_bytes": len(restored), "new_document_bytes": len(raw),
                      "scope": "unique V37 insertion only; complete V34 document restored"}


def extend_exact_snapshot_validator(original_validator, auditor, candidate_module,
                                    *, seed_rule="exact-point-bridge-v1", start_graph_rule="original-seed-cell"):
    """Register both exact full rules, while accepting only the declared one."""
    if type(seed_rule) is not str or seed_rule not in EXACT_SEED_VERSIONS:
        raise ValueError("an explicit exact seed rule is required")
    validate_start_graph_rule(start_graph_rule, seed_rule=seed_rule)
    rules = {version: {**candidate_module.CANDIDATE_RULE_V5,
                       "version": version, "seed_rule": name}
             for name, version in EXACT_SEED_VERSIONS.items()}
    point_version = candidate_version_for_rules("exact-point-bridge-v2", POINT_START_GRAPH_RULE)
    rules[point_version] = {**candidate_module.CANDIDATE_RULE_V5,
        "version": point_version, "seed_rule": "exact-point-bridge-v2",
        "start_graph_rule": POINT_START_GRAPH_RULE, "start_graph_profile": POINT_GRAPH_PROFILE,
        "start_graph_cost": POINT_GRAPH_COST}
    candidate_module.CANDIDATE_RULES = {**candidate_module.CANDIDATE_RULES, **rules}
    rule = rules[candidate_version_for_rules(seed_rule, start_graph_rule)]
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
        **({"seed_rule": plan["seed_rule"]} if plan.get("seed_rule", "legacy") != "legacy" else {}),
        **({"start_graph_rule": plan["start_graph_rule"]}
           if plan.get("start_graph_rule", "original-seed-cell") != "original-seed-cell" else {}))


def _load_versioned_native_gates(root, freeze, source_proof, source_bindings, custody_binding,
                                 *, seed_rule="legacy", start_graph_rule="original-seed-cell"):
    """Reuse unchanged native predicates after an explicit caller source check.

    The public qualification entry above still requires its complete sealed
    four-stage plan. A separately labelled diagnostic can bind its own finite
    source inventory without manufacturing a qualification plan or receipt.
    """
    from . import native_custody_reach
    root = Path(root)
    validate_seed_rule(seed_rule)
    validate_start_graph_rule(start_graph_rule, seed_rule=seed_rule)
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
            extend_exact_snapshot_validator(original_validator, auditor, candidate_module,
                                            seed_rule=seed_rule, start_graph_rule=start_graph_rule)

        legacy.extend_snapshot_validator = extend_exact_validator
    old_env_sha = legacy.ENV_DOCUMENT_SHA256
    environment_sha = legacy.sha(root / legacy.WIRELESS / "MR3_ENV_CONTRACT.md")
    allowed_environments = ({POINT_GRAPH_ENV_SHA256} if start_graph_rule == POINT_START_GRAPH_RULE else
                            {ENV_SHA256} if seed_rule == "legacy" else
                            {EXACT_V2_ENV_SHA256, POINT_GRAPH_ENV_SHA256} if seed_rule == "exact-point-bridge-v2" else
                            {EXACT_ENV_SHA256, EXACT_V2_ENV_SHA256, POINT_GRAPH_ENV_SHA256})
    legacy.require(environment_sha in allowed_environments, "environment document is not declared for this seed rule")

    def environment_document(root, freeze):
        relative = legacy.WIRELESS + "MR3_ENV_CONTRACT.md"
        raw = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        require = legacy.require
        require(hashlib.sha256(raw).hexdigest() == legacy.sha(root / relative) == environment_sha
                and raw.count(ENV_STATUS) == 1, "reach environment status revision differs")
        exact_projection = None
        exact_v2_projection = None
        point_projection = None
        if seed_rule != "legacy":
            if environment_sha == POINT_GRAPH_ENV_SHA256:
                raw, point_projection = project_point_graph_environment(raw)
            if hashlib.sha256(raw).hexdigest() == EXACT_V2_ENV_SHA256:
                raw, exact_v2_projection = project_exact_v2_environment(raw)
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
                **({"exact_seed_environment_projection": exact_projection} if exact_projection else {}),
                **({"exact_seed_v2_environment_projection": exact_v2_projection} if exact_v2_projection else {}),
                **({"point_graph_environment_projection": point_projection} if point_projection else {})}

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
    if start_graph_rule == POINT_START_GRAPH_RULE:
        relative = ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_point_graph.py"
        legacy.require(source_bindings[relative] == POINT_GRAPH_HELPER_SHA256,
                       "point graph helper differs from the declared V37 implementation")
        proof.update(legacy.verify_frozen_pins(root, freeze, {relative: POINT_GRAPH_HELPER_SHA256},
                                             "point graph attachment dependency"))
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
        proof["reach_dispatch"]["candidate_rule_version"] = candidate_version_for_rules(seed_rule, start_graph_rule)
        proof["reach_dispatch"]["protocol_reader_projection"] = protocol_projection
    if start_graph_rule != "original-seed-cell":
        proof["reach_dispatch"]["start_graph_rule"] = start_graph_rule
        proof["reach_dispatch"]["original_seed_cell_admission_replaced"] = True
    return phase, base, auditor, command, scalar, proof
