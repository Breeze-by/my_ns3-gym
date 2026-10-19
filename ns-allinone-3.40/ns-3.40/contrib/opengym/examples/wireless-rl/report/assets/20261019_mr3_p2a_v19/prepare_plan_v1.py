"""Prepare new V19 source/ELF bindings and a fresh, unexecuted reach plan.

This script cannot launch native work. Root supplies the actual engineering
balance after V18's original wait and external closure tail are charged.
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
PRIOR = W / 'report/assets/20261019_mr3_p2a_v18'
ORIGINAL = W / 'report/assets/20261019_mr3_p2a_v16'
V18_FREEZE = 'ed2306e9fa100f6ada4ab6496a53a3bd08e58017'
MAX_AFTER_CLOSED_V18 = Decimal('19326.4535690163982')
V18_INPUTS = {
    'prepare_plan_v1.py': '956de18026b6119aee4f9f703516ec4d7525301b6aa1981811d0abc125660546',
    'preflight_v1.py': '1e3b87570a743f0bf6dd68d37e4f70b1ed717da4a0f6eab521682eb67b61ccf5',
    'predeclared_plan_v1.json': '29294bba562f6e249166d6ffc4b4c20cc602f005d10d3c7f11ee598c9f1adb49',
    'native_custody_binding_v1.json': '0ebd64cc9db18df5fe6a86ea8b337b0532561c2b5302c9aecdc89c96516fffba',
    'closed_execution/matrix/summary.json': '0b4046a1166418dab5145e9d79d20d380841a83d631b760954b4dd802d5f3dfe',
    'closed_execution/matrix_outer/actual_wait.json': '597191891a9ff152e18ed84f1dde9dca15dba52e25b86129a46e6ded4877b49b',
    'closed_execution/engineering_accounting_v1.json': 'aa9cb9a27ae101cf3002d6f47115609263e01e0d95494f97ff36292452de48cb',
    'closed_execution/external_absence.json': 'fca94226c7b099e75dfe3bab40c06041ed9f31ad85a0485f439fa179d47cd633',
    'closed_execution/absence_outer/actual_wait.json': '05ddc77d4cd78b74ee5a939d70d64297dab3e9e60016614d975c672e9bcf293c',
    'closed_execution/native_closed_manifest_v1.json': '8361f6206e721bd415557193e7613c10adb5141e2249d2d39bebfe162b23abb6',
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
    checker = runpy.run_path(str(A / "check_preparation_v1.py"))
    return checker["verify_preparation_evidence"]()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engineering-remaining-seconds', required=True)
    args = parser.parse_args(argv)
    remaining = Decimal(args.engineering_remaining_seconds)
    require(remaining.is_finite() and Decimal('18300') <= remaining <= MAX_AFTER_CLOSED_V18,
            'actual engineering balance must fund matrix18000 + external300, without restoring any fee')
    binding_path, plan_path = A / 'native_custody_binding_v1.json', A / 'predeclared_plan_v1.json'
    require(not binding_path.exists() and not plan_path.exists(), 'V19 outputs exist; preserve the original attempt')
    preparation_proof, preparation_artifacts = verify_preparation_evidence()
    for relative, expected in V18_INPUTS.items():
        require(sha(PRIOR / relative) == expected, 'original V18 evidence changed: ' + relative)
    for relative, expected in ORIGINAL_INPUTS.items():
        require(sha(ORIGINAL / relative) == expected, 'original V16 approval/build evidence changed: ' + relative)
    accounting = json.loads((PRIOR / 'closed_execution/engineering_accounting_v1.json').read_text())
    absence = json.loads((PRIOR / 'closed_execution/external_absence.json').read_text())
    require(accounting.get('schema') == 'mr3-v18-closed-actual-engineering-accounting-v1'
            and accounting.get('source_freeze') == V18_FREEZE
            and accounting.get('engineering_ceiling_wall_seconds') == '52000'
            and accounting.get('qualification_passed') is False and accounting.get('policy_stage_started') is False
            and remaining == Decimal(accounting['remaining_seconds'])
            and remaining + Decimal(accounting['cumulative_used_seconds']) == Decimal('52000')
            and accounting.get('charged_this_version_seconds') == '178.641945323'
            and absence.get('passed') is True and absence.get('all_saved_identities_absent') is True
            and absence.get('identity_count') == 49 and absence.get('present') == [] and absence.get('errors') == [],
            'engineering argument must equal the complete original V18 actual accounting and absence proof')
    old_plan = json.loads((PRIOR / 'predeclared_plan_v1.json').read_text())
    failed = json.loads((PRIOR / 'closed_execution/matrix/summary.json').read_text())
    outer = json.loads((PRIOR / 'closed_execution/matrix_outer/actual_wait.json').read_text())
    require(failed.get('freeze') == V18_FREEZE and failed.get('passed') is False
            and failed.get('all_submitted_children_waited') is True
            and [row.get('status') for row in failed['stages']] == ['FAIL', 'SKIPPED', 'SKIPPED', 'SKIPPED']
            and outer.get('actual_waited') is True and outer.get('actual_returncode') == 1
            and outer.get('passed') is False and outer.get('source_unchanged') is True
            and outer.get('actual_child_wait_seconds') == '178.458480158',
            'V18 failed original wait/stop facts differ')
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
                'V19 does not authorize a changed native ELF: ' + row['path'])
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
        output_directory=Path('/tmp/mr3_p2a_reach_v19_matrix'),
        run_root=ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v19',
        custody_binding=binding_path, binary_proof=bridge_path,
        preflight=Path('/tmp/mr3_p2a_reach_v19_preflight.json'),
        engineering_remaining_seconds=str(remaining), run_prefix='mr3_p2a_reach_v19')
    for stage, domain, port in zip(plan['stages'], (180, 182, 184, 188), (14701, 14711, 14721, 14731)):
        replace_argument(stage['native']['argv'], '--base-domain', domain)
        replace_argument(stage['native']['argv'], '--base-port', port)
    plan['budget'].update(engineering_remaining_basis=
        'Actual cumulative52000 engineering balance supplied after original V18 wait and external tail fees; no fee refunded.',
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
    qualification = Path('/tmp/mr3_p2a_reach_v19_qualification.json')
    policy_root = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_ppo_reach_v19'
    plan['policy_stages'] = copy.deepcopy(old_plan['policy_stages'])
    for name, domain, port in (('minimum', 190, 14801), ('pilot', 192, 14811), ('validation', 196, 14821)):
        row = plan['policy_stages'][name]
        run_id = 'mr3_p2a_reach_v19_' + name
        command = row['argv']
        for flag, value in (('--reach-plan', plan_path), ('--reach-qualification', qualification),
                ('--base-domain', domain), ('--base-port', port), ('--output-root', policy_root), ('--run-id', run_id)):
            replace_argument(command, flag, value)
        row.update(run_directory=str(policy_root / run_id), output_directory='/tmp/mr3_p2a_reach_v19_' + name)
        if name == 'minimum':
            row['engineering_admission_ref'] = 'post_qualification.fresh_minimum.engineering_balance_condition'
        else:
            previous = 'minimum' if name == 'pilot' else 'pilot'
            row['condition'].update(previous_stage_summary=f'/tmp/mr3_p2a_reach_v19_{previous}/summary.json',
                previous_stage_outer_wait=f'/tmp/mr3_p2a_reach_v19_{previous}_wait/actual_wait.json',
                previous_stage_final_absence=f'/tmp/mr3_p2a_reach_v19_{previous}_final.json')
        if name == 'validation':
            replace_argument(command, '--checkpoint', policy_root / 'mr3_p2a_reach_v19_pilot/final.zip')
    plan['failed_predecessor'] = {
        'freeze': V18_FREEZE, 'plan': spec(PRIOR / 'predeclared_plan_v1.json'),
        'summary': spec(PRIOR / 'closed_execution/matrix/summary.json'),
        'outer_actual_wait': spec(PRIOR / 'closed_execution/matrix_outer/actual_wait.json'),
        'engineering_accounting': spec(PRIOR / 'closed_execution/engineering_accounting_v1.json'),
        'external_absence': spec(PRIOR / 'closed_execution/external_absence.json'),
        'original_returncode': 1, 'actual_outer_wall_seconds': '178.458480158',
        'status': 'FAIL retained; original no-retry stopped V18',
        'failure_scope': 'Reset released at39.20s; first post-release control at39.22s failed complete HOLD pair geometry in both map and raw frames because conservative geometry ages were dominated by genuine5Hz scan-derived TF sources. Old failure retained; no physical-dynamics or qualification PASS.',
        'new_execution': 'Fresh V19 same-freeze four stages, twelve episodes and thirty mandatory roles; no V18 credit reused',
    }
    plan['sensor_source_profile'] = {
        'name': 'mr3-reach-lidar-20hz-v1', 'sensor': 'hls_lfcd_lds',
        'scope': 'Generated SDF for explicitly selected reach profile only',
        'native_scan_update_rate_hz': 20, 'base_and_legacy_scan_update_rate_hz': 5,
        'original_source_timestamps_retained': True,
        'observation_distribution_changed': True,
        'geometry_and_physical_safety_thresholds_changed': False,
        'full_new_same_freeze_qualification_required': True,
    }
    plan['prospective_preparation_requirement'] = preparation_proof
    plan['approved_budget_evidence'] = spec(ORIGINAL / 'budget_acceptance_v1.json')
    for path in [*(PRIOR / relative for relative in V18_INPUTS),
            *(ORIGINAL / relative for relative in ORIGINAL_INPUTS), *A.glob('*.py'), *preparation_artifacts,
            PRIOR / 'check_continuation_preparation_v1.py', ORIGINAL / 'check_preparation_v1.py',
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
