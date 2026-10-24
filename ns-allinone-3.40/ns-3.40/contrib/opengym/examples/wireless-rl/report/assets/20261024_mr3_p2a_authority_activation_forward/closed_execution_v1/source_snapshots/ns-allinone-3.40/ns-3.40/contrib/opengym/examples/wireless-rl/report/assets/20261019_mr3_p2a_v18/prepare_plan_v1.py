"""Prepare new V18 source/ELF bindings and a fresh, unexecuted reach plan.

This script cannot launch native work. Root supplies the actual engineering
balance after V17's original wait and external closure tail are charged.
"""
import argparse
import copy
from decimal import Decimal
import json
from pathlib import Path
import runpy
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = Path(__file__).resolve().parent
PRIOR = W / 'report/assets/20261019_mr3_p2a_v17'
ORIGINAL = W / 'report/assets/20261019_mr3_p2a_v16'
V17_FREEZE = '023e488811743b3f325538d2854205466925c5c4'
MAX_AFTER_CLOSED_V17 = Decimal('19505.0955143393982')
V17_INPUTS = {
    'check_closed_preparation_v1.py': '940dd0b8ff5e68b53e35f6d9299e79d2798c8d42c8c66d52d1194a65be808d9e',
    'predeclared_plan_v1.json': '0b9951b44e842ef2677234659d813d74c97447068fe34688cc4f4b4b04ae3833',
    'native_custody_binding_v1.json': '2dd1d3f8367a83b40d9bd4cfc51ce3dc61941a7f9a17358ffa70dd73228a61ff',
    'closed_execution/matrix/summary.json': '83e6cf0755bdbeadae16152766fa3a39be0d30587041acf2a98a6f847fb98817',
    'closed_execution/matrix_outer/actual_wait.json': 'c5820f932311cd1cb18a0ab3415981d6e45f23fc1fdfa0286a7631c565fe76be',
    'closed_execution/engineering_accounting_v1.json': '6c4423974f1b729fc0fbc9d43a8a1989f40ae8c3401353cc2cc1b6d723ed1cac',
    'closed_execution/external_absence.json': 'c4a410dddbd38327e3b2fdce8419ad76fade7bded9609d5f904058f06407c110',
    'closed_execution/absence_outer/actual_wait.json': '65ac89f828614f44670905a84c28ac05d404122b8ea8a3b203cbea9bd7e60d80',
}
ORIGINAL_INPUTS = {
    'check_preparation_v1.py': '9390062d1dfe47e14fa71792048a486498d35fa3988e502ab259984ea695b75c',
    'native_build_evidence_bridge_v3.json': '3b8b9e03b786b8625a1a3747ee882c35d1dae106e969697ba6a829062ad37cbf',
    'budget_acceptance_v1.json': '37d0080ac70464576888d465ce25c5d3d68e562b69e27233b67c4a8c3b47bf0c',
}
sys.path.insert(0, str(W))
from mr3_learning import native_custody_reach as custody
from mr3_learning.reach_preparation import build_plan, dump, sha, validate_plan
from mr3_learning.reach_policy_chain import stage_spec


def require(value, message):
    if not value:
        raise ValueError(message)


def spec(path):
    path = Path(path)
    return {'path': str(path.relative_to(ROOT)), 'sha256': sha(path)}


def replace_argument(argv, flag, value):
    require(argv.count(flag) == 1, 'missing/repeated declaration: ' + flag)
    argv[argv.index(flag) + 1] = str(value)


def verify_preparation_evidence():
    """Load only the guarded standard-library packaging gate; never its main."""
    checker = runpy.run_path(str(A / "check_continuation_preparation_v1.py"))
    return checker["verify_preparation_evidence"]()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engineering-remaining-seconds', required=True)
    args = parser.parse_args(argv)
    remaining = Decimal(args.engineering_remaining_seconds)
    require(remaining.is_finite() and Decimal('18300') <= remaining <= MAX_AFTER_CLOSED_V17,
            'actual engineering balance must fund matrix18000 + external300, without restoring any fee')
    binding_path, plan_path = A / 'native_custody_binding_v1.json', A / 'predeclared_plan_v1.json'
    require(not binding_path.exists() and not plan_path.exists(), 'V18 outputs exist; preserve the original attempt')
    require((A / 'closed_prewarm_replay_v1.py').is_file(), 'V18 requires the complete closed-prewarm replay helper source')
    preparation_proof, preparation_artifacts = verify_preparation_evidence()
    for relative, expected in V17_INPUTS.items():
        require(sha(PRIOR / relative) == expected, 'original V17 evidence changed: ' + relative)
    for relative, expected in ORIGINAL_INPUTS.items():
        require(sha(ORIGINAL / relative) == expected, 'original V16 approval/build evidence changed: ' + relative)
    accounting = json.loads((PRIOR / 'closed_execution/engineering_accounting_v1.json').read_text())
    absence = json.loads((PRIOR / 'closed_execution/external_absence.json').read_text())
    require(accounting.get('schema') == 'mr3-v17-closed-actual-engineering-accounting-v1'
            and accounting.get('source_freeze') == V17_FREEZE
            and accounting.get('engineering_ceiling_wall_seconds') == '52000'
            and accounting.get('qualification_passed') is False and accounting.get('policy_stage_started') is False
            and remaining == Decimal(accounting['remaining_seconds'])
            and remaining + Decimal(accounting['cumulative_used_seconds']) == Decimal('52000')
            and accounting.get('charged_this_version_seconds') == '449.410014623'
            and absence.get('passed') is True and absence.get('all_saved_identities_absent') is True
            and absence.get('identity_count') == 48 and absence.get('present') == [] and absence.get('errors') == [],
            'engineering argument must equal the complete original V17 actual accounting and absence proof')
    old_plan = json.loads((PRIOR / 'predeclared_plan_v1.json').read_text())
    failed = json.loads((PRIOR / 'closed_execution/matrix/summary.json').read_text())
    outer = json.loads((PRIOR / 'closed_execution/matrix_outer/actual_wait.json').read_text())
    require(failed.get('freeze') == V17_FREEZE and failed.get('passed') is False
            and failed.get('all_submitted_children_waited') is True
            and [row.get('status') for row in failed['stages']] == ['FAIL', 'SKIPPED', 'SKIPPED', 'SKIPPED']
            and outer.get('actual_waited') is True and outer.get('actual_returncode') == 1
            and outer.get('passed') is False and outer.get('source_unchanged') is True
            and outer.get('actual_child_wait_seconds') == '449.21890062',
            'V17 failed original wait/stop facts differ')
    bridge_path = ORIGINAL / 'native_build_evidence_bridge_v3.json'
    binding = json.loads((PRIOR / 'native_custody_binding_v1.json').read_text())
    require(binding.get('schema') == custody.SCHEMA_BINDING
            and binding.get('safety_contract') == custody.CONTRACT
            and binding.get('execution_phase_protocol') == custody.PROTOCOL,
            'base binding is not the original reach profile')
    native, _ = custody.load_implementation()
    for row in binding['binaries'].values():
        actual = native.file_proof(row['path'])
        require(actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes'],
                'V18 does not authorize a changed native ELF: ' + row['path'])
        row.update(actual)
    for fields in binding['compiled_sources'].values():
        for row in fields.values():
            path = Path(row['path']); path = path if path.is_absolute() else ROOT / path
            require(sha(path) == row['sha256'], 'compiled native source changed without a new build: ' + str(path))
    sources = {}
    for row in binding['source_bindings']:
        path = Path(row['path']); path = path if path.is_absolute() else ROOT / path
        sources[str(path)] = spec(path)
    for path in [*(W / 'mr3_learning').glob('*.py'), *A.glob('*.py')]:
        sources[str(path)] = spec(path)
    binding['source_bindings'] = sorted(sources.values(), key=lambda row: row['path'])
    wrappers = [p for p in sorted((W / 'mr3_learning').glob('*.py'))
                if p.name.startswith(('audit_reach_', 'reach_')) or p.name == 'native_custody_reach.py']
    binding['qualification_wrappers'] = [spec(p) for p in [*wrappers, *sorted(A.glob('*.py'))]]
    binding['build_receipts'][0] = spec(bridge_path)
    dump(binding_path, binding)

    plan = build_plan(plan_path=plan_path,
        output_directory=Path('/tmp/mr3_p2a_reach_v18_matrix'),
        run_root=ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v18',
        custody_binding=binding_path, binary_proof=bridge_path,
        preflight=Path('/tmp/mr3_p2a_reach_v18_preflight.json'),
        engineering_remaining_seconds=str(remaining), run_prefix='mr3_p2a_reach_v18')
    for stage, domain, port in zip(plan['stages'], (200, 202, 204, 208), (14501, 14511, 14521, 14531)):
        replace_argument(stage['native']['argv'], '--base-domain', domain)
        replace_argument(stage['native']['argv'], '--base-port', port)
    plan['budget'].update(engineering_remaining_basis=
        'Actual cumulative52000 engineering balance supplied after original V17 wait and external tail fees; no fee refunded.',
        approved_cumulative_engineering_seconds='52000',
        engineering_used_at_plan_entry_seconds=str(Decimal('52000') - remaining),
        external_final_and_accounting_reservation_seconds='300',
        full_minimum_reservation_available_at_plan_entry=remaining >= Decimal('20100'))
    condition = {
        'accounting_source': 'external actual engineering ledger after every submitted child and closure tail is waited',
        'admit_only_if': 'actual_engineering_remaining_seconds >= 1800 + unused_external_reserve_seconds',
        'minimum_stage_reservation_seconds': '1800',
        'external_reserve_initial_seconds': '300',
        'unused_external_reserve_rule': 'max(0, 300 - actual_external_tail_seconds_already_charged)',
        'enforcement_owner': 'root external actual-fee admission before invoking reach_policy_chain minimum',
        'otherwise': 'SKIPPED for insufficient actual engineering balance; no cap reduction, retry, pilot borrowing or extension',
    }
    plan['post_qualification'] = {
        'fresh_minimum': {'seed': 41, 'decisions': 16, 'wall_reservation_seconds': '1800',
            'native_wall_seconds': '1150', 'epochs': 4, 'batch_size': 16,
            'required': 'actual eligible samples, positive optimizer changes and complete new independent audit',
            'engineering_balance_condition': condition},
        'external_final_and_accounting_reservation_seconds': '300',
        'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
        'final_only_development_validations': 3, 'p2b_or_gateway_authorized': False,
        'no_retry_on_required_failure': True,
    }
    qualification = Path('/tmp/mr3_p2a_reach_v18_qualification.json')
    policy_root = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_ppo_reach_v18'
    plan['policy_stages'] = copy.deepcopy(old_plan['policy_stages'])
    for name, domain, port in (('minimum', 210, 14601), ('pilot', 212, 14611), ('validation', 216, 14621)):
        row = plan['policy_stages'][name]
        run_id = 'mr3_p2a_reach_v18_' + name
        command = row['argv']
        for flag, value in (('--reach-plan', plan_path), ('--reach-qualification', qualification),
                ('--base-domain', domain), ('--base-port', port), ('--output-root', policy_root), ('--run-id', run_id)):
            replace_argument(command, flag, value)
        row.update(run_directory=str(policy_root / run_id), output_directory='/tmp/mr3_p2a_reach_v18_' + name)
        if name == 'minimum':
            row['engineering_admission_ref'] = 'post_qualification.fresh_minimum.engineering_balance_condition'
        else:
            previous = 'minimum' if name == 'pilot' else 'pilot'
            row['condition'].update(previous_stage_summary=f'/tmp/mr3_p2a_reach_v18_{previous}/summary.json',
                previous_stage_outer_wait=f'/tmp/mr3_p2a_reach_v18_{previous}_wait/actual_wait.json',
                previous_stage_final_absence=f'/tmp/mr3_p2a_reach_v18_{previous}_final.json')
        if name == 'validation':
            replace_argument(command, '--checkpoint', policy_root / 'mr3_p2a_reach_v18_pilot/final.zip')
    plan['failed_predecessor'] = {
        'freeze': V17_FREEZE, 'plan': spec(PRIOR / 'predeclared_plan_v1.json'),
        'summary': spec(PRIOR / 'closed_execution/matrix/summary.json'),
        'outer_actual_wait': spec(PRIOR / 'closed_execution/matrix_outer/actual_wait.json'),
        'engineering_accounting': spec(PRIOR / 'closed_execution/engineering_accounting_v1.json'),
        'external_absence': spec(PRIOR / 'closed_execution/external_absence.json'),
        'original_returncode': 1, 'actual_outer_wall_seconds': '449.21890062',
        'status': 'FAIL retained; original no-retry stopped V17',
        'failure_scope': 'Delayed startup ACK fix worked; same-tick order inference latched a runtime fault. Complete later CPU replay also retained missing Motion storage receipts and three unresolved causal suffixes. Both failures remain unchanged and ineligible; no scientific qualification.',
        'new_execution': 'Fresh V18 same-freeze four stages, twelve episodes and thirty mandatory roles; no V17 credit reused',
    }
    plan['prospective_preparation_requirement'] = preparation_proof
    plan['approved_budget_evidence'] = spec(ORIGINAL / 'budget_acceptance_v1.json')
    for path in [*(PRIOR / relative for relative in V17_INPUTS),
            *(ORIGINAL / relative for relative in ORIGINAL_INPUTS), *A.glob('*.py'), *preparation_artifacts,
            PRIOR / 'check_closed_preparation_v1.py', ORIGINAL / 'check_preparation_v1.py',
            W / 'MR3_ENV_CONTRACT.md', W / 'MR3_REACH_CONTRACT.md',
            W / 'report/assets/20261019_mr3_p2a_v14/scientific_contract_candidate_v1.md',
            W / 'report/assets/20261019_mr3_p2a_v15/contract_acceptance_v1.json']:
        plan['source_bindings'][str(path.relative_to(ROOT))] = sha(path)
    for relative in plan['source_bindings']:
        plan['source_bindings'][relative] = sha(ROOT / relative)
    for name in plan['policy_stages']:
        stage_spec(plan, plan_path, qualification, name)
    validate_plan(plan)
    dump(plan_path, plan)
    print(json.dumps({'plan': str(plan_path), 'plan_sha256': sha(plan_path),
        'binding': str(binding_path), 'binding_sha256': sha(binding_path),
        'engineering_remaining_seconds': str(remaining), 'minimum_is_budget_conditional': True,
        'source_bindings': len(plan['source_bindings']), 'binaries': len(plan['library_bindings'])}))


if __name__ == '__main__':
    main()
