"""Seal prospective V9 source bindings before any declared native run exists."""
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
    target = HERE / 'predeclared_plan_v9.json'
    binding_path = HERE / 'native_custody_binding.json'
    execution = Path('/tmp/mr3_p2a_v9_matrix_evidence')
    trace_output = Path('/tmp/mr3_p2a_v9_trace_evidence')
    run_root = R / 'log/mr3_p2a_v9'
    trace_root = R / 'log/mr3_action_trace'
    trace_run = trace_root / 'mr3_p2a_v9_trace'
    pf = Path('/tmp/mr3_p2a_v9_preflight.json')
    bp = Path('/tmp/mr3_p2a_v9_binaryproof.json')
    if any(p.exists() for p in (execution, trace_output, trace_run, pf, bp)):
        raise FileExistsError('cannot prepare/refresh a plan after execution admission or native evidence exists')
    plan = build_plan(output_directory=execution, run_root=run_root,
        custody_binding=binding_path, binary_proof=bp, preflight=pf,
        engineering_remaining_seconds='16464.4756821603982', run_prefix='mr3_p2a_v9')
    plan['readiness'] = {'ready': True, 'pending_bindings': []}
    plan['final_external_coordinator_absence_required'] = True
    plan['budget'].update(engineering_entry_seconds='12835.5243178396018',
        engineering_ceiling_seconds='30000', trace_reservation_seconds='700',
        engineering_remaining_before_trace_seconds='17164.4756821603982',
        minimal_ppo_reservation_seconds='900', actual_costs_charged_separately=True)
    binding = json.loads(binding_path.read_text())
    plan['library_bindings'] = {v['path']: v['sha256'] for v in binding['binaries'].values()}
    source_specs = [*binding['source_bindings'], *binding['build_receipts'],
                    binding['process_tools'], binding['corrector_tools'], binding['corrector_binding']]
    source_specs += [s for fields in binding['compiled_sources'].values() for s in fields.values()]
    for spec in source_specs:
        plan['source_bindings'][spec['path']] = spec['sha256']
    for path in [binding_path, *HERE.glob('*.py'), W / 'MR3_ENV_CONTRACT.md']:
        plan['source_bindings'][str(path.relative_to(ROOT))] = sha(path)
    interface = plan['stages'][0]
    old_run, old_local = interface['run_directory'], str(execution / 'interface')

    def adapt(value):
        if isinstance(value, str):
            return value.replace(old_run, str(trace_run)).replace(old_local, str(trace_output))
        if isinstance(value, list):
            return [adapt(x) for x in value]
        if isinstance(value, dict):
            return {k: adapt(v) for k, v in value.items()}
        return value

    trace_jobs = adapt(copy.deepcopy(interface['audits']))
    scientific = [job for job in trace_jobs if job.get('role') in
                  {'full', 'drive', 'information', 'peer', 'control', 'settled', 'cadence', 'input'}]
    episode = trace_run / 'worker0/episode001_open_101'
    for job in scientific:
        if job.get('role') == 'full':
            job['argv'] = [plan['learner_python'], '-B', '-m', 'mr3_learning.audit_action_trace',
                           str(episode), '--freeze', '{freeze}', '--output', job['output']]
        if job.get('role') == 'settled':
            job['argv'] = [arg for arg in job['argv'] if arg != '--require-use']
    closure = [job for job in trace_jobs if job['id'].startswith('fifo_') or job.get('role') == 'closure']
    for job in closure:
        if job.get('role') == 'closure':
            argv = job['argv']
            argv[argv.index('--expected-episodes') + 1] = '1'
            job['argv'] = [arg for arg in argv if arg != '--require-parameters']
    plan['trace'] = {'run_directory': str(trace_run), 'output_directory': str(trace_output),
        'actions': [231, 888, 888, 889, 880, 658, 888, 888], 'wall_seconds': '700',
        'physics_config': '/tmp/mr3_p2a_v9_trace_physics.json',
        'watcher': adapt(copy.deepcopy(interface['watcher'])),
        'native': {'argv': [plan['learner_python'], '-B', '-m', 'mr3_learning.action_trace',
            '--run-id', 'mr3_p2a_v9_trace', '--domain', '180', '--port', '14001',
            '--output-root', str(trace_root), '--physics-config', '/tmp/mr3_p2a_v9_trace_physics.json'],
            'output': str(trace_run / 'action_trace_summary.json'),
            'receipt': str(trace_output / 'native.json'), 'console': str(trace_output / 'native.log'),
            'result_pass_key': 'completed_requested_collection'},
        'closure_audits': closure, 'scientific_audits': scientific,
        'physical_claim': 'No guarantee of matching V7 trajectory or reproducing/repairing its counterexample',
        'incomplete_mask_rule': 'No replacement/retry; preserve INCOMPLETE. No physical PASS. '
            'Only a demonstrated native/model/infrastructure counterexample blocks subsequent independent matrix; '
            'lack of a legal fixed stimulus alone does not prove a physical counterexample.'}
    plan['trace_command'] = ['/usr/bin/python3', '-B', str(HERE / 'run_trace.py'),
        '--plan', str(target), '--freeze', '{freeze}', '--preflight', str(pf)]
    plan['matrix_command'] = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.preparation',
        '--plan', str(target), '--freeze', '{freeze}']
    python = plan['learner_python']
    common = [python, '-B', '-m', 'mr3_learning.ppo']
    plan['ppo'] = {
        'minimum': {'condition': 'All four stages and38 roles plus final coordinator closure PASS',
            'command': common + ['--mode', 'train', '--workers', '1', '--schedule', 'open:101',
                '--decisions', '16', '--episode-steps', '16', '--wall-seconds', '900', '--seed', '41',
                '--base-domain', '180', '--base-port', '14001', '--run-id', 'mr3_p2a_v9_minimal'],
            'engineering_wall_reservation_seconds': '900'},
        'pilot': {'condition': 'New minimum/full/input audits PASS; fresh seed41 weights, no engineering checkpoint',
            'command': common + ['--mode', 'train', '--workers', '2', '--schedule', 'open:101',
                '--decisions', '1870', '--episode-steps', '64', '--wall-seconds', '2100', '--seed', '41',
                '--base-domain', '182', '--base-port', '14011', '--run-id', 'mr3_p2a_v9_pilot'],
            'remaining_decisions': 1870, 'remaining_wall_seconds': '2905.9547395464029',
            'soft_wall_seconds': '2100', 'closure_save_inflight_reserve_seconds': '805.9547395464029'},
        'validation': {'condition': 'Only the successful new pilot final.zip; all prior gates PASS; otherwise SKIPPED',
            'command': common + ['--mode', 'evaluate', '--workers', '4', '--checkpoint',
                str(R / 'log/mr3_ppo/mr3_p2a_v9_pilot/final.zip'),
                '--schedule', 'open:401,open:402,open:403', '--decisions', '900', '--episode-steps', '300',
                '--wall-seconds', '9000', '--seed', '41', '--base-domain', '186', '--base-port', '14021',
                '--run-id', 'mr3_p2a_v9_validation'], 'total_wall_seconds': '9000', 'optimizer_steps': 0},
        'required_consumers': ['mr3_learning.audit_ppo (includes native/scalar/policy/GAE/real odometry cadence)',
                               'mr3_learning.audit_policy_inputs'],
        'failure_rule': 'Stop the failed run and all later phases; no blind same-freeze retry, no fabricated final',
        'completion_rule': 'Original95%/quality/participation/safety/native closure and actual PPO validation exit; '
                           'no P2B or gateway until separate user acceptance'}
    validate_plan(plan)
    target.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + '\n')
    print(json.dumps({'prepared': str(target), 'mandatory_matrix_roles': 38,
                      'sha256': sha(target), 'native_started': False}))


if __name__ == '__main__':
    main()
