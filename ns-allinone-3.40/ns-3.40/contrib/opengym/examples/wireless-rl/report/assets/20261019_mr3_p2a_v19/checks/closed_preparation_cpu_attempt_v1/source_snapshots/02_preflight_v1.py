"""Frozen V19 source/build/reader dispatch preflight; no simulator or GPU."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import runpy
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
sys.path.insert(0, str(W))
from mr3_learning import native_custody_reach, reach_preparation, reach_gates
from mr3_learning import audit_reach_preparation, audit_reach_controlled_physics
from mr3_learning import audit_reach_peer_control, audit_reach_cadence, audit_reach_ppo
from mr3_learning.reach_policy_chain import stage_spec


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    require = reach_preparation.require
    require(args.plan.resolve() == A / 'predeclared_plan_v1.json', 'V19 preflight requires its one declared fresh plan')
    require(not args.output.exists(), 'exclusive V19 preflight output exists')
    plan = reach_preparation.load_plan(args.plan)
    preparation = plan['prospective_preparation_requirement']
    require(preparation.get('passed') is True
            and preparation.get('scientific_pass_claimed') is False
            and preparation.get('native_admission') is False
            and preparation.get('native_or_qualification_credit') is False
            and preparation.get('fresh_full_native_qualification_required') is True,
            'V19 needs source-bound finite CPU preparation without native credit')
    require(plan['sensor_source_profile'] == {
        'name': 'mr3-reach-lidar-20hz-v1', 'sensor': 'hls_lfcd_lds',
        'scope': 'Generated SDF for explicitly selected reach profile only',
        'native_scan_update_rate_hz': 20, 'base_and_legacy_scan_update_rate_hz': 5,
        'original_source_timestamps_retained': True,
        'observation_distribution_changed': True,
        'geometry_and_physical_safety_thresholds_changed': False,
        'full_new_same_freeze_qualification_required': True,
    }, 'V19 requires the exact explicit genuine sensor-source profile')
    qualification = Path('/tmp/mr3_p2a_reach_v19_qualification.json')
    for name in plan['policy_stages']:
        stage_spec(plan, args.plan, qualification, name)
    minimum_condition = plan['post_qualification']['fresh_minimum']['engineering_balance_condition']
    require(minimum_condition['admit_only_if'] ==
            'actual_engineering_remaining_seconds >= 1800 + unused_external_reserve_seconds'
            and minimum_condition['minimum_stage_reservation_seconds'] == '1800'
            and minimum_condition['external_reserve_initial_seconds'] == '300'
            and plan['post_qualification']['external_final_and_accounting_reservation_seconds'] == '300'
            and Decimal(plan['budget']['engineering_remaining_seconds']) >= Decimal('18300'),
            'V19 must retain matrix/external reservations and conditional unmodified minimum')
    source_proof = reach_preparation.source_check(plan, args.plan, args.freeze)
    checker = runpy.run_path(str(A/'check_preparation_v1.py'))
    actual_preparation, _ = checker['verify_preparation_evidence']()
    require(actual_preparation == preparation, 'current actual CPU evidence differs from the frozen plan')
    identity = native_custody_reach.verify_binding(ROOT, args.freeze, plan['custody_binding'])
    _, executor = reach_preparation.load_executor()
    _, control = audit_reach_controlled_physics.load_impl()
    _, full = audit_reach_preparation.load_impl(args.plan)
    _, peer = audit_reach_peer_control.load_impl()
    _, cadence = audit_reach_cadence.load_implementation()
    _, policy = audit_reach_ppo.load_impl(args.plan)
    *_, native_sources = reach_gates.load_native_gates(ROOT, args.freeze, args.plan)
    reach_preparation.source_check(plan, args.plan, args.freeze)
    result = {'schema': 'mr3-reach-preflight-v1', 'passed': True,
        'freeze': args.freeze, 'safety_contract': 'mr3-reach-v1',
        'plan_sha256': reach_preparation.sha(args.plan),
        'source_proof': source_proof, 'native_gate_sources': native_sources,
        'actual_binary_binding': identity,
        'dispatch_projections': {'executor': executor, 'controlled': control, 'full': full,
                                'peer_control': peer, 'cadence': cadence, 'ppo': policy},
        'engineering_remaining_seconds_at_plan_entry': plan['budget']['engineering_remaining_seconds'],
        'minimum_engineering_admission': minimum_condition,
        'minimum_admitted_by_this_preflight': False,
        'prospective_source_preparation': preparation,
        'failed_predecessor': plan['failed_predecessor'],
        'scientific_native_credit': False, 'gpu_calls': 0, 'optimizer_steps': 0,
        'scope': 'Frozen source, actual unchanged ELF/original build evidence and reader dispatch only. Fresh same-freeze four-stage scientific artifacts remain mandatory; minimum additionally requires root actual engineering balance admission.'}
    reach_preparation.dump(args.output, result)
    print(json.dumps({'passed': True, 'sources': len(source_proof), 'output': str(args.output)}))


if __name__ == '__main__':
    main()
