"""Seal the new V11 matrix after the V9 identity-entry failure; no trace retry."""
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
    target = HERE / 'predeclared_plan_v11.json'
    execution = Path('/tmp/mr3_p2a_v11_matrix_evidence')
    pf = Path('/tmp/mr3_p2a_v11_preflight.json')
    bp = Path('/tmp/mr3_p2a_v11_binaryproof.json')
    if any(path.exists() for path in (execution, pf, bp)):
        raise FileExistsError('cannot refresh an admitted/executed plan')
    binding_path = HERE / 'native_custody_binding.json'
    plan = build_plan(output_directory=execution, run_root=R / 'log/mr3_p2a_v11',
        custody_binding=binding_path, binary_proof=bp, preflight=pf,
        engineering_remaining_seconds='16047.2815487073982', run_prefix='mr3_p2a_v11')
    plan['budget'].update(matrix_wall_seconds='14900', borrow_unused_prior_stage_reservations=True)
    for stage, cap, work in zip(plan['stages'], ('1500','1200','4500','7700'), ('1250','850','3900','6600')):
        stage['wall_seconds'] = cap
        stage['native']['argv'][stage['native']['argv'].index('--work-wall-seconds') + 1] = work
    plan['readiness'] = {'ready': True, 'pending_bindings': []}
    plan['preflight']['schema'] = 'mr3-p2a-v11-preflight-v1'
    plan['final_external_coordinator_absence_required'] = True
    plan['budget'].update(engineering_entry_seconds='13952.7184512926018',
        engineering_ceiling_seconds='30000', minimal_ppo_reservation_seconds='900',
        engineering_remaining_basis='Exact prior cumulative account after conservative V10 upper-bound charge903.879658900',
        actual_costs_charged_separately=True)
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
                 helpers / 'final_closure.py', HERE / 'reviewed_execution_delta.json', W / 'MR3_ENV_CONTRACT.md']:
        plan['source_bindings'][str(path.relative_to(ROOT))] = sha(path)
    plan['matrix_command'] = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.preparation',
                              '--plan', str(target), '--freeze', '{freeze}']
    old = json.loads((helpers / 'predeclared_plan_v9.json').read_text())['ppo']

    def rename(value):
        if isinstance(value, str):
            return value.replace('mr3_p2a_v9', 'mr3_p2a_v11')
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
            total_phase_wall_scope='Outer elapsed from native admission through actual close/save/all required consumer waits',
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
