"""Check the one frozen V69 plan, actual ELF custody and reader dispatch only.

This loads definitions and verifies source/build bytes. It never invokes a
scientific trace consumer, World, ROS node, policy forward or optimizer.
Use canonical ns3gym Python because immutable PPO reader definitions import
their real learner dependencies; ROS process execution remains system Python.
"""

import argparse
from decimal import Decimal
import json
from pathlib import Path

from mr3_learning import native_custody_reach, reach_preparation, reach_gates
from mr3_learning import audit_reach_preparation, audit_reach_controlled_physics
from mr3_learning import audit_reach_peer_control, audit_reach_cadence, audit_reach_ppo, audit_reach_reset_workload, audit_reach_runtime
from mr3_learning.reach_policy_chain import stage_spec
from mr3_learning import initial_encoder_replay

ACTUATION_PROFILE = initial_encoder_replay.PROFILE

from . import prepare_plan_v1 as preparing


ROOT, A = preparing.ROOT, preparing.A
require = reach_preparation.require


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(args.plan.resolve() == preparing.PLAN, 'V69 preflight requires its one complete declared plan')
    require(not args.output.exists(), 'exclusive V69 preflight output exists')
    plan = reach_preparation.load_plan(args.plan)
    require(plan.get('seed_rule') == preparing.SEED_RULE and plan.get('start_graph_rule') == preparing.START_RULE
            and plan.get('map_output_packing_profile') == preparing.PACKING_PROFILE
            and plan.get('reach_geometry_rule') == preparing.REACH_GEOMETRY_RULE
            and plan.get('actuation_profile') == ACTUATION_PROFILE,
            'V69 native and policy must use the exact v3/point-graph pair')
    resource, inputs = preparing.verify_plan_resource(plan)
    remaining = Decimal(resource['budget']['engineering_remaining_seconds'])
    classification = preparing.verify_classification(inputs, preparing.verify_wait)
    require(plan.get('prospective_classification_regression') == classification,
            'classification regression evidence differs from frozen admission sources')
    preparation, _ = preparing.verify_preparation_evidence(inputs=inputs)
    require(plan.get('prospective_preparation_requirement') == preparation,
            'current original CPU evidence differs from the frozen plan')
    expected_policy = preparing.policy_registry(preparing.decode(inputs.read(
        preparing.PRIOR / 'predeclared_plan_v1.json')))
    require(plan.get('policy_stages') == expected_policy, 'V69 policy configuration changed from the complete declared registry')
    for name in ('minimum', 'pilot', 'validation'):
        require(plan['policy_stages'][name].get('external_finalize_reserve_seconds') ==
                ('0' if name == 'minimum' else '300'), 'V69 external finalizer reserve differs from the original phase cap')
        require(plan['policy_stages'][name].get('actuation_profile') == ACTUATION_PROFILE
                and plan['policy_stages'][name].get('motion_authority_profile') == preparing.MOTION_AUTHORITY_PROFILE,
                'V69 policy stage omitted the fixed actuator profile')
        stage_spec(plan, args.plan, preparing.QUALIFICATION, name)
    condition = plan['post_qualification']['fresh_minimum']['engineering_balance_condition']
    require(condition['admit_only_if'] == 'actual_engineering_remaining_seconds >= 1800 + unused_external_reserve_seconds'
            and condition['minimum_stage_reservation_seconds'] == '1800'
            and condition['external_reserve_initial_seconds'] == resource['budget']['external_final_and_accounting_reservation_seconds']
            and plan['post_qualification']['external_final_and_accounting_reservation_seconds'] == resource['budget']['external_final_and_accounting_reservation_seconds']
            and sum(stage['expected_episodes'] for stage in plan['stages']) == 12
            and sum(len(reach_preparation.primitives.roles(stage)) for stage in plan['stages']) == 30,
            'V69 complete workload or minimum admission was weakened')
    source_proof = reach_preparation.source_check(plan, args.plan, args.freeze)
    identity = native_custody_reach.verify_binding(ROOT, args.freeze, plan['custody_binding'])
    build = identity.get('reach_build_bridge_proof', {})
    require(identity.get('actuation_profile') == ACTUATION_PROFILE
            and build.get('actuation_profile') == ACTUATION_PROFILE
            and build.get('new_build_executed') is True,
            'V69 requires the actual A69 current21 incremental build/source evidence, no compiler jobs or native qualification inferred')
    require(audit_reach_reset_workload.profile_from_plan(plan)[:2] ==
            (preparing.WORKLOAD_PROFILE,preparing.PROBE_VERSION), "future v3 activity profile pair differs")
    reset_reader = audit_reach_reset_workload.verify_reader_readiness(plan, args.freeze)
    require(plan.get('motion_authority_profile') == preparing.MOTION_AUTHORITY_PROFILE
            and identity.get('motion_authority_profile') == preparing.MOTION_AUTHORITY_PROFILE
            and all(stage.get('motion_authority_profile') == preparing.MOTION_AUTHORITY_PROFILE for stage in plan['stages']),
            'new authority plan/stage/custody profile differs')
    runtime_sources = audit_reach_runtime.source_proof(ROOT, args.freeze,
        reach_geometry_rule=plan['reach_geometry_rule'], motion_authority_profile=preparing.MOTION_AUTHORITY_PROFILE)
    cadence_sources = audit_reach_cadence.source_proof(args.freeze, ROOT,
        reach_geometry_rule=plan['reach_geometry_rule'])
    require(build.get('initial_encoder_compiled_source', {}).get('sha256')
            == runtime_sources[audit_reach_runtime.ENCODER_HEADER_SOURCE]['sha256']
            and callable(initial_encoder_replay.replay_native_drive)
            and callable(initial_encoder_replay.check_applied_receipt),
            'loaded newbuild helper and independent compound replay source differ')
    _, executor = reach_preparation.load_executor()
    _, controlled = audit_reach_controlled_physics.load_impl()
    _, full = audit_reach_preparation.load_impl(args.plan)
    _, peer = audit_reach_peer_control.load_impl()
    _, cadence = audit_reach_cadence.load_implementation(ROOT, actuation_profile=ACTUATION_PROFILE)
    _, policy = audit_reach_ppo.load_impl(args.plan)
    *_, native_sources = reach_gates.load_native_gates(ROOT, args.freeze, args.plan)
    # Fresh actual device availability also prevents SB3's silent CPU fallback.
    import torch
    require(torch.cuda.is_available() and torch.cuda.device_count() >= 1, 'actual cuda:0 is unavailable')
    inputs.finish()
    reach_preparation.source_check(plan, args.plan, args.freeze)
    result = {'schema': 'mr3-reach-preflight-v1', 'passed': True, 'freeze': args.freeze,
        'safety_contract': 'mr3-reach-v1', 'motion_authority_profile': preparing.MOTION_AUTHORITY_PROFILE, 'actuation_profile': ACTUATION_PROFILE, 'seed_rule': preparing.SEED_RULE, 'start_graph_rule': preparing.START_RULE,
        'map_output_packing_profile': preparing.PACKING_PROFILE, 'reach_geometry_rule': preparing.REACH_GEOMETRY_RULE,
        'plan_sha256': reach_preparation.sha(args.plan), 'source_proof': source_proof,
        'native_gate_sources': native_sources, 'actual_binary_binding': identity,
        'dispatch_projections': {'executor': executor, 'controlled': controlled, 'full': full,
            'peer_control': peer, 'cadence': cadence, 'ppo': policy, 'reset_reader': reset_reader,
            'runtime_sources': runtime_sources, 'cadence_sources': cadence_sources},
        'engineering_resource': plan['engineering_resource'],
        'numeric_user_approval_claimed': False,
        'engineering_remaining_seconds_at_plan_entry': str(remaining), 'minimum_engineering_admission': condition,
        'minimum_admitted_by_this_preflight': False, 'prospective_source_preparation': preparation,
        'cuda_metadata': {'device': 'cuda:0', 'available': True, 'device_name': torch.cuda.get_device_name(0)},
        'scientific_native_credit': False, 'gpu_calls': 0, 'optimizer_steps': 0,
        'scope': 'Frozen source, actual new driver ELF/build evidence, unchanged other native bindings and reader dispatch only. Fresh same-freeze four-stage native scientific qualification and external actual wait/absence remain mandatory; no policy stage is admitted by this CPU preflight.'}
    reach_preparation.dump(args.output, result)
    print(json.dumps({'passed': True, 'sources': len(source_proof), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
