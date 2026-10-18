"""Seal the V13 fixed tagged cadence and mathematically equivalent audit implementation."""
import copy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / '.git').exists())
W = HERE.parents[2]
R = ROOT / 'ros2_ws/ros2-multi-robot-automap'
sys.path.insert(0, str(W))
from mr3_learning.preparation import build_plan, sha, validate_plan


def main():
    target = HERE / 'predeclared_plan_v13.json'
    execution = Path('/tmp/mr3_p2a_v13_matrix_evidence')
    pf = Path('/tmp/mr3_p2a_v13_preflight.json')
    bp = Path('/tmp/mr3_p2a_v13_binaryproof.json')
    if any(path.exists() for path in (execution, pf, bp)):
        raise FileExistsError('cannot refresh an admitted/executed plan')
    qualification_path = W / 'report/assets/20261019_mr3_p2a_v12/checks/information_combined_cpu/summary.json'
    qualification = json.loads(qualification_path.read_text())
    required = ('passed', 'all_four_stages_complete', 'all_report_fields_deep_equal',
                'serialized_report_bytes_equal', 'source_and_reference_stable_end',
                'all_saved_cpu_identities_gone')
    if (qualification.get('schema') != 'mr3-information-combined-production-qualification-v1'
            or not all(qualification.get(key) is True for key in required)
            or qualification.get('outer_actual_wait_returncode') != 0
            or qualification.get('actual_wait_returncodes') !=
                {name: 0 for name in ('interface', 'terminal', 'reset', 'deadline')}
            or qualification.get('implementation') != 'admitted_index_three_keys_v1'):
        raise ValueError('complete independent information CPU qualification required')
    implementation = qualification['production_implementation']
    expected_entry = str((W / 'mr3_learning/audit_information.py').relative_to(ROOT))
    if implementation.get('path') != expected_entry or sha(ROOT / expected_entry) != implementation.get('sha256'):
        raise ValueError('qualified information implementation differs')
    qualification_index = W / 'report/assets/20261019_mr3_p2a_v12/checks/information_combined_cpu/index.json'
    if not qualification_index.is_file():
        raise ValueError('complete CPU evidence index is required')
    parameter_qualification_path = HERE / 'checks/nav2_profile_cpu/qualification.json'
    parameter_qualification = json.loads(parameter_qualification_path.read_text())
    flags = ('passed', 'exact10_typed_facts', 'three_yaml_exact13_inverse',
             'old_reader_unchanged', 'readback_functions_unchanged',
             'benchmark_and_builder_wiring_passed')
    if (parameter_qualification.get('schema') != 'mr3-nav2-gentle-profile-cpu-qualification-v1'
            or parameter_qualification.get('actual_wait_returncode') != 0
            or not all(parameter_qualification.get(key) is True for key in flags)
            or parameter_qualification.get('active_profile_selection') != 'gentle_turn_v1'
            or parameter_qualification.get('new_native_calls') != 0):
        raise ValueError('complete exact deployment CPU qualification required')
    for name, expected in parameter_qualification['source_sha256'].items():
        if sha(ROOT / name) != expected:
            raise ValueError('qualified deployment entry/wiring source differs: ' + name)
    from mr3_learning.audit_nav2_parameters import load_profile
    _, profile_proof = load_profile(ROOT)
    if (profile_proof['profile_sha256'] != parameter_qualification['profile_definition_sha256']
            or profile_proof['yaml_sources'] != parameter_qualification['deployment_yaml_sources']):
        raise ValueError('qualified exact deployment profile differs')
    parameter_index = HERE / 'checks/nav2_profile_cpu/index.json'
    if not parameter_index.is_file():
        raise ValueError('deployment CPU evidence index missing')
    binding_path = HERE / 'native_custody_binding.json'
    plan = build_plan(output_directory=execution, run_root=R / 'log/mr3_p2a_v13',
        custody_binding=binding_path, binary_proof=bp, preflight=pf,
        engineering_remaining_seconds='13076.4141104843982', run_prefix='mr3_p2a_v13',
        information_implementation='admitted_index_three_keys_v1', nav2_parameter_profile='gentle_turn_v1')
    plan['budget'].update(matrix_wall_seconds='12100', borrow_unused_prior_stage_reservations=True)
    for stage, cap, work in zip(plan['stages'], ('1400','900','4200','5600'), ('1150','600','3600','4500')):
        stage['wall_seconds'] = cap
        stage['native']['argv'][stage['native']['argv'].index('--work-wall-seconds') + 1] = work
    plan['read_only_audit_qualification'] = {
        'summary': {'path': str(qualification_path.relative_to(ROOT)), 'sha256': sha(qualification_path)},
        'index': {'path': str(qualification_index.relative_to(ROOT)), 'sha256': sha(qualification_index)},
        'production_implementation': implementation,
        'scope': 'Complete closed-data CPU equivalence only; no new-freeze native credit'}
    plan['nav2_deployment_qualification'] = {
        'qualification': {'path': str(parameter_qualification_path.relative_to(ROOT)),
                          'sha256': sha(parameter_qualification_path)},
        'index': {'path': str(parameter_index.relative_to(ROOT)), 'sha256': sha(parameter_index)},
        'effective_entry': parameter_qualification['entry'],
        'profile_definition_sha256': profile_proof['profile_sha256'],
        'scope': 'CPU/deployment source only; new live nine-node and native proof remain mandatory'}
    plan['readiness'] = {'ready': True, 'pending_bindings': []}
    plan['preflight']['schema'] = 'mr3-p2a-v13-preflight-v1'
    plan['final_external_coordinator_absence_required'] = True
    plan['budget'].update(engineering_entry_seconds='16923.5858895156018',
        engineering_ceiling_seconds='30000', minimal_ppo_reservation_seconds='900',
        engineering_remaining_basis='Exact cumulative after V12 conservative actual-wait upper-bound charge1851.306438272',
        engineering_unallocated_tail_seconds='76.4141104843982',
        actual_costs_charged_separately=True)
    plan['prior_engineering_attempt'] = {
        'freeze': 'ea759bea57d1e2ddd126d56c3a81801a072535a0',
        'native_decisions_returned': 48, 'completed_stage_roles': 19,
        'formal_stage_status': 'interface and terminal PASS; reset native FAIL after tb1 raw settled-turn speed .01636094718877706 > .01; reset scientific roles unsubmitted, deadline/PPO skipped',
        'all_saved_identities_gone': 253, 'old_failures_preserved': True,
        'engineering_charge_upper_bound_seconds': '1851.306438272', 'new_freeze_credit': False}
    plan['prior_trace'] = {'freeze': 'bbb2e6365fdbeae681bb3088faeedc6883db324b',
        'status': 'INCOMPLETE fixed_action_illegal and independent identity-entry FAIL; preserved',
        'native_decisions_returned': 0, 'trace_attempts_total': 1, 'additional_trace_attempts': 0,
        'physical_repair_credit': False, 'engineering_charge_upper_bound_seconds': '213.314474553'}
    binding = json.loads(binding_path.read_text())
    plan['library_bindings'] = {v['path']: v['sha256'] for v in binding['binaries'].values()}
    specs = [*binding['source_bindings'], *binding['build_receipts'], binding['process_tools'],
             binding['corrector_tools'], binding['corrector_binding']]
    specs += [value for fields in binding['compiled_sources'].values() for value in fields.values()]
    for spec in specs:
        plan['source_bindings'][spec['path']] = spec['sha256']
    helpers = W / 'report/assets/20261019_mr3_p2a_v9'
    for path in [binding_path, *HERE.glob('*.py'), helpers / 'execute.py',
                 helpers / 'final_closure.py', W / 'report/assets/20261019_mr3_p2a_v12/reviewed_execution_delta.json',
                 qualification_path, qualification_index, parameter_qualification_path,
                 parameter_index, W / 'MR3_ENV_CONTRACT.md']:
        plan['source_bindings'][str(path.relative_to(ROOT))] = sha(path)
    plan['matrix_command'] = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.preparation',
                              '--plan', str(target), '--freeze', '{freeze}']
    old = json.loads((helpers / 'predeclared_plan_v9.json').read_text())['ppo']

    def rename(value):
        if isinstance(value, str):
            return value.replace('mr3_p2a_v9', 'mr3_p2a_v13')
        if isinstance(value, list):
            return [rename(x) for x in value]
        if isinstance(value, dict):
            return {k: rename(v) for k, v in value.items()}
        return value

    plan['ppo'] = rename(copy.deepcopy(old))
    for name, soft, reserve, total, pool in (
            ('minimum', '700', '200', '900', 'engineering'),
            ('pilot', '2100', '805.9547395464029', '2905.9547395464029', 'original_pilot_balance'),
            ('validation', '8100', '900', '9000', 'original_final_only_validation')):
        phase = plan['ppo'][name]
        phase['command'][phase['command'].index('--wall-seconds') + 1] = soft
        phase.update(collector_soft_wall_seconds=soft, post_soft_reserve_seconds=reserve,
            total_phase_wall_allocation_seconds=total, budget_pool=pool,
            total_phase_wall_scope='Actual outer entry through final absence reader, write and tool wait completion; includes ready/source, native, close/save and all required consumer waits',
            reserve_is_proven_upper_bound=False,
            overrun_verdict='FAIL; actual cost still charged; no kill/refund/blind retry or cross-pool transfer')
    plan['ppo']['minimum']['required_native_decisions'] = 16
    plan['ppo']['minimum']['required_actual_optimizer_steps'] = 'positive; actual count retained'
    plan['ppo']['validation']['required_task_successes'] = 3
    plan['ppo']['validation']['required_task_failures'] = []
    plan['ppo']['wall_contract'] = '--wall-seconds is a soft collector deadline, never a proven hard total wall bound'
    validate_plan(plan)
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'plan': str(target), 'sha256': sha(target), 'mandatory_matrix_roles': 38,
                      'additional_trace_attempts': 0, 'native_started': False}))


if __name__ == '__main__':
    main()
