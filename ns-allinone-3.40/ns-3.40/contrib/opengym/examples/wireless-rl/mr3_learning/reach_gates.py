"""Source-bound reach-profile dispatch to the immutable native scientific gates.

The new plan explicitly versions changed execution sources. Unchanged W7 truth,
reward, task, SLAM and independent mathematics keep their original exact pins.
"""

from pathlib import Path
import hashlib
import re
import subprocess

from .reach_audit_projection import project_module
from . import audit_reach_sensor_model
from .supervisor import (EXACT_SEED_VERSIONS, POINT_START_GRAPH_RULE, POINT_GRAPH_PROFILE,
                         POINT_GRAPH_COST, candidate_version_for_rules,
                         validate_seed_rule, validate_start_graph_rule,
                         validate_reach_geometry_rule, BINARY_REACH_GEOMETRY_RULE,
                         SUPPORT_REACH_GEOMETRY_RULE)

PPO_READER_SHA256 = "b2e0737d79826b7ecb319cc91b58ff45475ea831a9cb2b4cab2298aaf6474567"
PROTOCOL_READER_SHA256 = "8bc1ee209761be2108a3d1d0248f2d0ab40b9fc68539ecedffec11cb81fd1647"
ENV_SHA256 = "e21cade7fecc17461007903e74ccd870c26e1d1e4a766731c2850dd567a73869"
EXACT_ENV_SHA256 = "1cebd1d5c6abf2750991a40ab50065c4f9b655f11f30e3f1734ea2130612d143"
EXACT_V2_ENV_SHA256 = "11a70fb42a58c104a55a68186795226dbf2c1f4bd4170066dfaad209e63ba8d5"
POINT_GRAPH_ENV_SHA256 = "baffbf1bffc7fadff80105ec5c5dce3a04c694ce7e7a8f72ca6620d8a7c13a1a"
POINT_GRAPH_HELPER_SHA256 = "e55b776c3ec088fe51dfa76ff204b4b135138038502fabc6af01717ed75efc83"
SUPPORT_REFERENCE_GEOMETRY_SHA256 = "cf46b49f0740f84511f3d34f9a8eb3e56720744515d9eea1dc81bd8bacb85f0a"
ENV_STATUS = ("2026-10-19：用户已接受[V14科学候选](report/assets/20261019_mr3_p2a_v14/scientific_contract_candidate_v1.md)。显式新profile的执行规则以[MR3_REACH_CONTRACT.md](MR3_REACH_CONTRACT.md)为准；本文件下述原速度/累计路径与v1相位规则继续描述默认`legacy`。V15已接线并完成CPU/编译准备，尚无新冻结原生资格、训练或95%信用；旧FAIL不改判。\n\n").encode()
ROS = "ros2_ws/ros2-multi-robot-automap/"
MAP_OUTPUT_PACKING_PROFILE = "mr3-occupancy-int8-array-v1"
MERGE_MAP_SOURCE = ROS + "src/merge_map/merge_map/merge_map.py"
MERGE_MAP_LEGACY_SHA256 = "76c3d2c604f38f61116be1f39263472f9074b4f69fe7a0428b532da977530078"
MERGE_MAP_PACKED_SHA256 = "e4cf897d2c22e70f89d9293efc00f44dd4bf1eb01624713735e08afdee0cbfcc"
MAP_OUTPUT_PACKING_INVERSE = (
    (b"from array import array\n", b""),
    (b"    merged_map.data = array('b', merged.astype(np.int8).tobytes())\n",
     b"    merged_map.data = merged.ravel().tolist()\n"),
    (b"    composed = np.where(observed_own >= 0, observed_own, conservative)\n"
     b"    navigation.data = array('b', composed.astype(np.int8).tobytes())\n",
     b"    navigation.data = np.where(observed_own >= 0, observed_own, conservative).ravel().tolist()\n"),
)
REVISED_RUNTIME = {
    ROS + "scripts/mr3_env_worker.py",
    *(ROS + "src/multi_robot_exploration/multi_robot_exploration/" + name + ".py"
      for name in ("mr3_information", "peer_obstacles", "motion_safety",
                   "mr3_control_phase", "mr3_motion_control")),
}
REVISED_CONFIG = {ROS + "src/multi_robot/CMakeLists.txt",
                  ROS + "src/multi_robot/src/mr3_gazebo_diff_drive.cpp",
                  ROS + "src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py"}


def project_map_output_packing(raw):
    """Invert only the reviewed V23 output packing; preserve the whole old file."""
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest() != MERGE_MAP_PACKED_SHA256:
        raise ValueError("declared map output packing source SHA differs")
    restored = raw
    for current, original in MAP_OUTPUT_PACKING_INVERSE:
        if restored.count(current) != 1:
            raise ValueError("map output packing inverse occurrence differs")
        restored = restored.replace(current, original, 1)
    inverse_sha = hashlib.sha256(restored).hexdigest()
    if inverse_sha != MERGE_MAP_LEGACY_SHA256:
        raise ValueError("map output packing inverse does not restore the complete old source")
    return restored, {"profile": MAP_OUTPUT_PACKING_PROFILE,
        "sha256": MERGE_MAP_PACKED_SHA256, "whole_source_inverse_sha256": inverse_sha,
        "new_source_bytes": len(raw), "old_source_bytes": len(restored),
        "literal_inverse_replacements": len(MAP_OUTPUT_PACKING_INVERSE),
        "scope": "Three exact output-packing substitutions only; entire legacy fusion/navigation source restored."}


def version_map_output_packing(legacy, root, freeze, source_bindings, profile=None):
    """Change one private reader pin only after explicit three-way source proof.

    Omission retains the immutable old pin and its original refusal of new
    bytes. This is orthogonal to seed/graph selection and grants no qualification.
    """
    if profile is None:
        return None
    if type(profile) is not str or profile != MAP_OUTPUT_PACKING_PROFILE:
        raise ValueError("unknown map output packing profile")
    if type(freeze) is not str or re.fullmatch(r"[0-9a-f]{40}", freeze) is None:
        raise ValueError("map output packing requires an exact source freeze")
    if source_bindings.get(MERGE_MAP_SOURCE) != MERGE_MAP_PACKED_SHA256:
        raise ValueError("map output packing is not bound to the exact declared source")
    pins = dict(legacy.PREPARATION_RUNTIME_PINS)
    if pins.get(MERGE_MAP_SOURCE) != MERGE_MAP_LEGACY_SHA256:
        raise ValueError("immutable legacy map output source pin differs")
    root = Path(root)
    frozen = subprocess.check_output(["git", "show", freeze + ":" + MERGE_MAP_SOURCE], cwd=root)
    current = (root / MERGE_MAP_SOURCE).read_bytes()
    if (hashlib.sha256(frozen).hexdigest() != MERGE_MAP_PACKED_SHA256
            or hashlib.sha256(current).hexdigest() != MERGE_MAP_PACKED_SHA256 or frozen != current):
        raise ValueError("map output packing plan/frozen/worktree source differs")
    _, proof = project_map_output_packing(current)
    # Copy rather than mutate: even a caller sharing the old table keeps it.
    pins[MERGE_MAP_SOURCE] = MERGE_MAP_PACKED_SHA256
    legacy.PREPARATION_RUNTIME_PINS = pins
    proof.update(path=MERGE_MAP_SOURCE, source=freeze + ":" + MERGE_MAP_SOURCE,
        previous_scope_sha256=MERGE_MAP_LEGACY_SHA256, new_source_sha256=MERGE_MAP_PACKED_SHA256,
        plan_frozen_worktree_source_equal=True, original_mathematical_predicates_changed=False,
        scientific_native_credit=False)
    return proof


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


def _support_geometry_pins(source_bindings):
    prefix = ROS+"src/multi_robot_exploration/multi_robot_exploration/"
    relative = prefix+"mr3_reach_geometry.py"
    if source_bindings.get(relative) != SUPPORT_REFERENCE_GEOMETRY_SHA256:
        raise ValueError("support geometry cannot replace the original declared reach sets")
    extras = {relative: SUPPORT_REFERENCE_GEOMETRY_SHA256}
    for name in (prefix+"mr3_reach_support.py",
                 "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/reach_support_replay.py"):
        expected = source_bindings[name]
        if type(expected) is not str or re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise ValueError("invalid support geometry source SHA: "+name)
        extras[name] = expected
    return extras


def load_native_gates(root, freeze, plan_path):
    from .reach_preparation import load_plan, source_check
    root, plan_path = Path(root), Path(plan_path)
    plan = load_plan(plan_path, root)
    source_proof = source_check(plan, plan_path, freeze, root, require_clean=False)
    geometry = validate_reach_geometry_rule(plan.get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE),
                                             safety_contract="mr3-reach-v1")
    packing = plan.get("map_output_packing_profile")
    if "map_output_packing_profile" in plan and (
            type(packing) is not str or packing != MAP_OUTPUT_PACKING_PROFILE):
        raise ValueError("unknown declared map output packing profile")
    from .native_custody_reach import initial_encoder_profile
    actuation = initial_encoder_profile(plan)
    from .motion_authority_profile import selected_motion_authority_profile
    authority = selected_motion_authority_profile(plan)
    if authority is not None:
        policies = plan.get("policy_stages")
        if type(policies) is not dict or set(policies) != {"minimum","pilot","validation"} or not all(
                row.get("motion_authority_profile") == authority for row in policies.values()):
            raise ValueError("authority qualification requires three same-profile policy stages")
    if actuation is not None:
        policies = plan.get("policy_stages")
        if type(policies) is not dict or set(policies) != {"minimum", "pilot", "validation"} or not all(
                initial_encoder_profile(row) == actuation for row in policies.values()):
            raise ValueError("new encoder qualification needs the three mandatory same-profile policy stages")
    return _load_versioned_native_gates(root, freeze, source_proof,
        plan["source_bindings"], plan["custody_binding"],
        **({"seed_rule": plan["seed_rule"]} if plan.get("seed_rule", "legacy") != "legacy" else {}),
        **({"start_graph_rule": plan["start_graph_rule"]}
           if plan.get("start_graph_rule", "original-seed-cell") != "original-seed-cell" else {}),
        **({"map_output_packing_profile": packing} if packing is not None else {}),
        **({"reach_geometry_rule": geometry} if geometry != BINARY_REACH_GEOMETRY_RULE else {}),
        **({"actuation_profile": actuation} if actuation is not None else {}),
        **({"motion_authority_profile": authority} if authority is not None else {}))


def _load_versioned_native_gates(root, freeze, source_proof, source_bindings, custody_binding,
                                 *, seed_rule="legacy", start_graph_rule="original-seed-cell",
                                 map_output_packing_profile=None,
                                 reach_geometry_rule=BINARY_REACH_GEOMETRY_RULE,
                                 actuation_profile=None, motion_authority_profile=None):
    """Reuse unchanged native predicates after an explicit caller source check.

    The public qualification entry above still requires its complete sealed
    four-stage plan. A separately labelled diagnostic can bind its own finite
    source inventory without manufacturing a qualification plan or receipt.
    """
    from . import native_custody_reach
    root = Path(root)
    if motion_authority_profile is not None:
        from .motion_authority_profile import selected_motion_authority_profile
        selected_motion_authority_profile(dict(safety_contract="mr3-reach-v1",
            motion_authority_profile=motion_authority_profile), required=True)
    if actuation_profile is not None:
        native_custody_reach.initial_encoder_profile({"actuation_profile":actuation_profile})
    validate_seed_rule(seed_rule)
    validate_start_graph_rule(start_graph_rule, seed_rule=seed_rule)
    validate_reach_geometry_rule(reach_geometry_rule, safety_contract="mr3-reach-v1")
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
    packing_projection = version_map_output_packing(legacy, root, freeze, source_bindings,
                                                   map_output_packing_profile)
    if packing_projection is not None:
        revised_proof[MERGE_MAP_SOURCE] = packing_projection

    def execution_configs(root, freeze):
        retained = {p: d for p, d in legacy.EXECUTION_CONFIG_PINS.items()
                    if p not in REVISED_CONFIG}
        proof = legacy.verify_frozen_pins(root, freeze, retained, "unchanged execution config")
        proof.update({p: source_proof[p] for p in REVISED_CONFIG})
        return proof

    def native_binding(root, freeze):
        result = native_custody_reach.verify_binding(root, freeze, custody_binding)
        legacy.require(result.get("reach_source_proof", {}).get("reach_geometry_rule", BINARY_REACH_GEOMETRY_RULE)
                       == reach_geometry_rule, "custody binding geometry rule differs from qualification dispatch")
        legacy.require(result.get("actuation_profile") == actuation_profile,
                       "actual native build/custody profile differs from the qualification plan")
        legacy.require(result.get("motion_authority_profile") == motion_authority_profile,
                       "actual Python authority custody/profile differs from qualification dispatch")
        if actuation_profile is not None:
            legacy.require(result.get("reach_build_bridge_proof", {}).get("new_build_executed") is True,
                           "new encoder plan has no actual new driver build")
        return {custody_binding: {"identity_proof": result,
                "scope": "actual source-bound ELF identity and explicit actuator build; live maps/close are separate roles"}}

    legacy.verify_execution_configs = execution_configs
    legacy.verify_current_native_binding = native_binding
    legacy.verify_velocity_smoother_overlay = native_binding
    phase, base, auditor, command, scalar, proof = legacy.load_native_gates(root, freeze)
    if reach_geometry_rule == SUPPORT_REACH_GEOMETRY_RULE:
        extras = _support_geometry_pins(source_bindings)
        proof.update(legacy.verify_frozen_pins(root, freeze, extras, "explicit support geometry dependencies"))
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
    _,sensor_projection = audit_reach_sensor_model.load_spawn_impl(
        **({"actuation_profile":actuation_profile} if actuation_profile is not None else {}))
    audit_reach_sensor_model.attach_native_gate(phase,root,freeze,
        **({"actuation_profile":actuation_profile} if actuation_profile is not None else {}))
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
    if actuation_profile is not None:
        proof["reach_dispatch"]["actuation_profile"] = actuation_profile
        proof["reach_dispatch"]["new_actual_driver_build_required"] = True
        proof["reach_dispatch"]["independent_compound_law_replay_required"] = True
    if motion_authority_profile is not None:
        proof["reach_dispatch"].update(motion_authority_profile=motion_authority_profile,
            independent_receiving_authority_and_deferred_protocol_replay_required=True,
            authority_cpp_build_credit=False)
    if packing_projection is not None:
        proof["reach_dispatch"]["map_output_packing"] = packing_projection
    if reach_geometry_rule != BINARY_REACH_GEOMETRY_RULE:
        proof["reach_dispatch"].update(reach_geometry_rule=reach_geometry_rule,
            geometry_certificate_semantics="conditional sufficient separation of unchanged declared Reach sets",
            independent_geometry_replay="mr3_learning.reach_support_replay",
            original_mathematical_predicates_changed=False,
            geometry_admission_predicate_changed=True,
            original_binary_geometry_source_sha256=SUPPORT_REFERENCE_GEOMETRY_SHA256,
            new_geometry_admission_version=True)
    if seed_rule != "legacy":
        proof["reach_dispatch"]["seed_rule"] = seed_rule
        proof["reach_dispatch"]["candidate_rule_version"] = candidate_version_for_rules(seed_rule, start_graph_rule)
        proof["reach_dispatch"]["protocol_reader_projection"] = protocol_projection
    if start_graph_rule != "original-seed-cell":
        proof["reach_dispatch"]["start_graph_rule"] = start_graph_rule
        proof["reach_dispatch"]["original_seed_cell_admission_replaced"] = True
    return phase, base, auditor, command, scalar, proof
