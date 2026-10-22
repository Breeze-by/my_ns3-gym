"""Seal one fresh V40 native qualification plan; never launch an experiment.

Run as a module from wireless-rl, with the canonical system Python. All outputs
are exclusive. Current ELF/source bytes may reuse a historical build only if
their exact original compiled-source and ELF hashes still match. Prior native
outcomes are references, never scientific credit for this new plan.
"""

import argparse
import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import subprocess

from mr3_learning import native_custody_reach as custody
from mr3_learning import reach_preparation as preparation
from mr3_learning.reach_policy_chain import stage_spec


ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = Path(__file__).resolve().parent
PRIOR = W / 'report/assets/20261019_mr3_p2a_v19'
BRIDGE = W / 'report/assets/20261019_mr3_p2a_v16/native_build_evidence_bridge_v3.json'
PLAN = A / 'plan_v1.json'
BINDING = A / 'native_custody_binding_v1.json'
QUALIFICATION = Path('/tmp/mr3_p2a_reach_v40_qualification.json')
RUN_ROOT = ROS / 'log/mr3_p2a_reach_v40'
POLICY_ROOT = ROS / 'log/mr3_ppo_reach_v40'
SEED_RULE = 'exact-point-bridge-v2'
START_RULE = 'point-attachment-3x3-v1'
CEILING = Decimal('75000')
OPENING_USED = Decimal('48259.9538193466018')
OPENING_REMAINING = Decimal('26740.0461806533982')
PINS = {
    PRIOR / 'predeclared_plan_v1.json': '331d83cb8fb7fb7498f9243eaccd49138f9117baae9ae69684d30b55ae8c2d3e',
    PRIOR / 'native_custody_binding_v1.json': '832c6fd25a44478cdbed6acf9ed2c35f8c8e501fe53674e6d432f7bd9e592470',
    BRIDGE: '3b8b9e03b786b8625a1a3747ee882c35d1dae106e969697ba6a829062ad37cbf',
}
CPU_INPUTS = {
    'v40_geometry': (A / 'checks/geometry_cpu_v1/actual_wait.json', A / 'checks/geometry_cpu_v1_source_recovery.json'),
    'v40_native_reader': (A / 'checks/reader_cpu_v1/actual_wait.json', A / 'checks/reader_cpu_v1_source_recovery.json'),
    'v40_learner': (A / 'checks/learner_cpu_v1/actual_wait.json', A / 'checks/learner_cpu_v1_source_recovery.json'),
    'v40_snapshot': (A / 'checks/snapshot_cpu_v1/actual_wait.json', A / 'checks/snapshot_cpu_v1_source_recovery.json'),
    'v40_readiness_cpu': (A / 'checks/readiness_cpu_v3/actual_wait.json', A / 'checks/readiness_cpu_v3_source_recovery.json'),
}
require, sha, dump = preparation.require, preparation.sha, preparation.dump


def decode(raw):
    def unique(pairs):
        value = {}
        for key, child in pairs:
            require(key not in value, 'duplicate JSON member: ' + key)
            value[key] = child
        return value
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: ' + value)))


class Inputs:
    def __init__(self):
        self.proofs = {}

    def read(self, path):
        path = Path(path).resolve(strict=True)
        require(path.is_relative_to(ROOT), 'preparation input is outside the canonical workspace')
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                'preparation input changed while read: ' + str(path))
        proof = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        require(self.proofs.setdefault(str(path.relative_to(ROOT)), proof) == proof,
                'preparation input changed between reads: ' + str(path))
        return raw

    def spec(self, path):
        self.read(path)
        relative = str(Path(path).resolve().relative_to(ROOT))
        return {'path': relative, **self.proofs[relative]}

    def bound(self, spec, expected_path=None):
        path = Path(spec['path'])
        path = path if path.is_absolute() else ROOT / path
        if expected_path is not None:
            require(path.resolve() == Path(expected_path).resolve(), 'unexpected declared preparation input')
        raw = self.read(path)
        require(hashlib.sha256(raw).hexdigest() == spec['sha256']
                and ('bytes' not in spec or spec['bytes'] == len(raw)), 'input binding differs: ' + str(path))
        return path, raw

    def finish(self):
        for relative, expected in tuple(self.proofs.items()):
            require(hashlib.sha256(self.read(ROOT / relative)).hexdigest() == expected['sha256'],
                    'preparation evidence changed before seal')


def replace_argument(argv, flag, value):
    require(argv.count(flag) == 1 and argv.index(flag) + 1 < len(argv), 'missing/repeated declaration: ' + flag)
    argv[argv.index(flag) + 1] = str(value)


def verify_authorization(inputs, remaining):
    authorization = decode(inputs.read(A / 'authorization_v1.json'))
    budget = decode(inputs.read(A / 'budget_acceptance_v1.json'))
    inputs.bound(budget['authorization'], A / 'authorization_v1.json')
    require(authorization.get('schema') == 'mr3-p2a-autonomous-continuation-authorization-v1'
            and authorization.get('status') == 'AUTHORIZED_BY_USER_CONTINUATION'
            and authorization.get('user_exact_text') == '你一直继续执行就好了，直到把P2A完成，不需要问我是否批准'
            and authorization.get('engineering_current_block_ceiling_seconds') == str(CEILING)
            and authorization.get('engineering_used_at_entry_seconds') == str(OPENING_USED)
            and authorization.get('engineering_remaining_at_entry_seconds') == str(OPENING_REMAINING)
            and authorization.get('acceptance_gates_unchanged') is True
            and authorization.get('old_failures_preserved') is True
            and authorization.get('p2b_gateway_authorized') is False,
            'V40 does not have its explicit current continuation/budget authority')
    require(budget.get('schema') == 'mr3-p2a-reach-engineering-budget-acceptance-v1'
            and budget.get('engineering_ceiling_wall_seconds') == str(CEILING)
            and budget.get('opening_used_wall_seconds') == str(OPENING_USED)
            and budget.get('opening_remaining_wall_seconds') == str(OPENING_REMAINING)
            and budget.get('reservations', {}).get('total') == '20100'
            and budget.get('pilot_remaining_decisions') == 1870
            and budget.get('pilot_remaining_wall_seconds') == '2905.9547395464029'
            and budget.get('final_only_schedule') == ['open:401', 'open:402', 'open:403']
            and remaining.is_finite() and Decimal('20100') <= remaining <= OPENING_REMAINING
            and OPENING_USED + OPENING_REMAINING == CEILING,
            'engineering entry must fund the complete unchanged qualification/minimum/external reservation')
    return authorization, budget


def verify_wait(value):
    require(value.get('schema') == 'mr3-reach-outer-actual-wait-v1'
            and value.get('scope') == 'cpu' and value.get('safety_contract') == custody.CONTRACT
            and value.get('actual_waited') is True and type(value.get('actual_returncode')) is int
            and value['actual_returncode'] == 0 and value.get('errors') == []
            and value.get('source_unchanged') is True and value.get('passed') is True,
            'CPU evidence is not a successful actual finite wait')
    start, end = value['started_monotonic_ns'], value['ended_monotonic_ns']
    require(type(start) is int and type(end) is int and 0 < start < end
            and Decimal(value['actual_child_wait_seconds']) == Decimal(end - start) / 10**9,
            'CPU wait duration differs from the original nanosecond interval')
    parent, child = value['coordinator_identity'], value['child_identity']
    require(all(type(row.get(key)) is int and row[key] > 0
                for row in (parent, child) for key in ('pid', 'start_ticks'))
            and child.get('parent') == parent['pid'], 'CPU wait process identities differ')
    require(type(value.get('actual_argv')) is list and value['actual_argv']
            and all(type(arg) is str for arg in value['actual_argv'])
            and type(value.get('source_before')) is list and value['source_before']
            and value['source_before'] == value.get('source_after'), 'CPU command/source evidence is incomplete')


def verify_preparation_evidence(index_path=A / 'cpu_validation_index_v1.json', *, inputs=None):
    inputs = Inputs() if inputs is None else inputs
    index = decode(inputs.read(index_path))
    require(index.get('schema') == 'mr3-p2a-v40-cpu-validation-index-v1'
            and type(index.get('entries')) is list, 'V40 CPU validation index schema differs')
    entries = {row['id']: row for row in index['entries']}
    require(len(entries) == len(index['entries']) and set(entries) == set(CPU_INPUTS),
            'V40 requires exactly its five explicitly selected preparation checks')
    runtime = preparation.source_inventory(ROOT)
    runtime.update(str(path.relative_to(ROOT)) for path in (W / 'mr3_learning/tests').glob('*.py'))
    covered, rows = set(), []
    for name, (wait_path, recovery_path) in CPU_INPUTS.items():
        row = entries[name]
        _, raw = inputs.bound(row['actual_wait'], wait_path)
        wait = decode(raw)
        verify_wait(wait)
        inputs.bound(wait['console'])
        if name == 'v40_readiness_cpu':
            readiness = decode(inputs.read(A / 'checks/readiness_cpu_v3_result.json'))
            require(readiness.get('schema') == 'mr3-v40-cpu-import-device-readiness-v1'
                    and readiness.get('passed') is True and readiness.get('world_started') is False
                    and readiness.get('model_constructed') is False
                    and all(readiness.get(key) == 0 for key in ('forward_calls', 'backward_calls', 'optimizer_steps'))
                    and len(readiness.get('results', [])) == 2, 'fresh V40 import/device readiness result differs')
            ros, learner = readiness['results']
            require(ros.get('schema') == 'mr3-v40-ros-import-readiness-v1' and ros.get('passed') is True
                    and learner.get('schema') == 'mr3-v40-learner-device-readiness-v1'
                    and learner.get('passed') is True and learner.get('cuda_available') is True
                    and learner.get('device') == 'cuda:0' and learner.get('visible_cuda_devices', 0) >= 1,
                    'canonical system ROS or actual CUDA learner readiness is absent')
        recovery = {}
        if recovery_path is not None:
            _, raw = inputs.bound(row['source_recovery'], recovery_path)
            records = decode(raw)['sources']
            recovery = {record['path']: record for record in records}
            require(len(recovery) == len(records), 'duplicate CPU source-recovery path')
        seen = set()
        for source in wait['source_before']:
            path = Path(source['path']).resolve()
            relative = str(path.relative_to(ROOT))
            require(relative not in seen and type(source['bytes']) is int and source['bytes'] >= 0,
                    'duplicate or malformed original CPU source')
            seen.add(relative)
            expected = {'sha256': source['sha256'], 'bytes': source['bytes']}
            if recovery_path is not None:
                saved = recovery[relative]
                require(all(saved.get(key) == item for key, item in expected.items()),
                        'CPU source-recovery hash/size differs')
            current = inputs.read(path)
            matches = hashlib.sha256(current).hexdigest() == expected['sha256'] and len(current) == expected['bytes']
            if relative in runtime:
                require(matches, 'tested runtime/test source differs from current preparation: ' + relative)
                covered.add(relative)
            if not matches:
                require(recovery_path is not None, 'changed CPU-only source lacks original bytes')
                if saved.get('kind') == 'snapshot':
                    original = inputs.read(recovery_path.parent.parent / saved['snapshot'])
                else:
                    require(saved.get('kind') == 'git_blob', 'unknown original CPU source recovery kind')
                    original = subprocess.check_output(['git', 'show', saved['freeze'] + ':' + relative], cwd=ROOT)
                require(hashlib.sha256(original).hexdigest() == expected['sha256'] and len(original) == expected['bytes'],
                        'original CPU-only source bytes are not recoverable')
        rows.append({'id': name, 'actual_wait': inputs.spec(wait_path),
            'actual_returncode': 0, 'actual_child_wait_seconds': wait['actual_child_wait_seconds'],
            'source_count': len(seen)})
    required_current = {str((W / 'mr3_learning' / name).relative_to(ROOT)) for name in
        ('reach_preparation.py', 'reach_policy_chain.py', 'reach_gates.py', 'ppo.py', 'supervisor.py')}
    required_current.update('ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/' + name
        for name in ('mr3_observation.py', 'mr3_seed_certificate.py', 'mr3_point_graph.py', 'mr3_adapter.py'))
    require(required_current <= covered, 'current P2A/native admission source coverage is incomplete')
    return {'schema': 'mr3-p2a-v40-source-preparation-proof-v1', 'passed': True,
        'entries': rows, 'current_runtime_and_test_sources_checked': len(covered),
        'scientific_pass_claimed': False, 'native_admission': False,
        'native_or_qualification_credit': False, 'fresh_full_native_qualification_required': True}, inputs


def policy_registry(old_plan, plan_path=PLAN, qualification=QUALIFICATION):
    registry = copy.deepcopy(old_plan['policy_stages'])
    require(set(registry) == {'minimum', 'pilot', 'validation'}, 'old policy registry is incomplete')
    for name, domain, port in (('minimum', 212, 15801), ('pilot', 214, 15811), ('validation', 218, 15821)):
        row, run_id = registry[name], 'mr3_p2a_reach_v40_' + name
        command = row['argv']
        for flag, value in (('--reach-plan', plan_path), ('--reach-qualification', qualification),
                ('--base-domain', domain), ('--base-port', port), ('--output-root', POLICY_ROOT), ('--run-id', run_id)):
            replace_argument(command, flag, value)
        require('--seed-rule' not in command and '--start-graph-rule' not in command,
                'historical policy input already has an unexpected rule override')
        command.extend(['--seed-rule', SEED_RULE, '--start-graph-rule', START_RULE])
        row.update(run_directory=str(POLICY_ROOT / run_id), output_directory='/tmp/mr3_p2a_reach_v40_' + name)
        row['external_finalize_reserve_seconds'] = '0' if name == 'minimum' else '300'
        if name != 'minimum':
            previous = 'minimum' if name == 'pilot' else 'pilot'
            row['condition'].update(previous_stage_summary=f'/tmp/mr3_p2a_reach_v40_{previous}/summary.json',
                previous_stage_outer_wait=f'/tmp/mr3_p2a_reach_v40_{previous}_wait/actual_wait.json',
                previous_stage_final_absence=f'/tmp/mr3_p2a_reach_v40_{previous}_final.json')
        if name == 'validation':
            replace_argument(command, '--checkpoint', POLICY_ROOT / 'mr3_p2a_reach_v40_pilot/final.zip')
    return registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engineering-remaining-seconds', required=True)
    args = parser.parse_args(argv)
    remaining = Decimal(args.engineering_remaining_seconds)
    require(not PLAN.exists() and not BINDING.exists(), 'V40 outputs already exist; preserve the original preparation attempt')
    inputs = Inputs()
    verify_authorization(inputs, remaining)
    inputs.read(A / 'scope_v1.json')
    proof, _ = verify_preparation_evidence(inputs=inputs)
    for path, expected in PINS.items():
        require(hashlib.sha256(inputs.read(path)).hexdigest() == expected, 'immutable V19/build reference differs')
    old_plan = decode(inputs.read(PRIOR / 'predeclared_plan_v1.json'))
    binding = decode(inputs.read(PRIOR / 'native_custody_binding_v1.json'))
    require(binding.get('schema') == custody.SCHEMA_BINDING and binding.get('safety_contract') == custody.CONTRACT
            and binding.get('execution_phase_protocol') == custody.PROTOCOL, 'binding is not the real reach/v2 native contract')
    native, _ = custody.load_implementation()
    for row in binding['binaries'].values():
        actual = native.file_proof(row['path'])
        require(actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes'],
                'native ELF changed without a new original build proof: ' + row['path'])
        row.update(actual)
    for fields in binding['compiled_sources'].values():
        for row in fields.values():
            inputs.bound(row)
    source_paths = {ROOT / row['path'] if not Path(row['path']).is_absolute() else Path(row['path'])
                    for row in binding['source_bindings']}
    source_paths.update(ROOT / path for path in preparation.source_inventory(ROOT))
    source_paths.update(A.glob('*.py'))
    source_paths.update((A / name) for name in ('authorization_v1.json', 'budget_acceptance_v1.json', 'scope_v1.json'))
    sources = {row['path']: row for row in (inputs.spec(path) for path in sorted(source_paths))}
    binding['source_bindings'] = [sources[path] for path in sorted(sources)]
    wrappers = sorted(path for path in (W / 'mr3_learning').glob('*.py')
        if path.name.startswith(('reach_', 'audit_reach_')) or path.name == 'native_custody_reach.py')
    binding['qualification_wrappers'] = [inputs.spec(path) for path in [*wrappers, *sorted(A.glob('*.py'))]]
    binding['build_receipts'][0] = inputs.spec(BRIDGE)
    dump(BINDING, binding)
    plan = preparation.build_plan(plan_path=PLAN, seed_rule=SEED_RULE, start_graph_rule=START_RULE,
        output_directory='/tmp/mr3_p2a_reach_v40_matrix', run_root=RUN_ROOT, custody_binding=BINDING,
        binary_proof=BRIDGE, preflight='/tmp/mr3_p2a_reach_v40_preflight.json',
        engineering_remaining_seconds=str(remaining), run_prefix='mr3_p2a_reach_v40')
    for stage, domain, port in zip(plan['stages'], (202, 204, 206, 210), (15701, 15711, 15721, 15731)):
        replace_argument(stage['native']['argv'], '--base-domain', domain)
        replace_argument(stage['native']['argv'], '--base-port', port)
    plan['budget'].update(engineering_remaining_basis=
        'Authorized cumulative75000 current engineering block; actual native/read-only/closure union fees remain charged; no old fee refunded.',
        approved_cumulative_engineering_seconds=str(CEILING), engineering_used_at_plan_entry_seconds=str(CEILING - remaining),
        external_final_and_accounting_reservation_seconds='300', full_minimum_reservation_available_at_plan_entry=True)
    condition = {'accounting_source': 'external actual engineering ledger after every submitted child and closure tail is waited',
        'admit_only_if': 'actual_engineering_remaining_seconds >= 1800 + unused_external_reserve_seconds',
        'minimum_stage_reservation_seconds': '1800', 'external_reserve_initial_seconds': '300',
        'unused_external_reserve_rule': 'max(0, 300 - actual_external_tail_seconds_already_charged)',
        'enforcement_owner': 'root external actual-fee admission before invoking reach_policy_chain minimum',
        'otherwise': 'SKIPPED for insufficient actual engineering balance; no cap reduction, retry, pilot borrowing or extension'}
    plan['post_qualification'] = {'fresh_minimum': {'seed': 41, 'decisions': 16, 'wall_reservation_seconds': '1800',
        'native_wall_seconds': '1150', 'epochs': 4, 'batch_size': 16,
        'required': 'actual eligible samples, positive optimizer changes and complete new independent audit',
        'engineering_balance_condition': condition}, 'external_final_and_accounting_reservation_seconds': '300',
        'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
        'final_only_development_validations': 3, 'p2b_or_gateway_authorized': False, 'no_retry_on_required_failure': True}
    plan['policy_stages'] = policy_registry(old_plan)
    plan['sensor_source_profile'] = copy.deepcopy(old_plan['sensor_source_profile'])
    plan['prospective_preparation_requirement'] = proof
    plan['approved_budget_evidence'] = inputs.spec(A / 'budget_acceptance_v1.json')
    plan['authorization_evidence'] = inputs.spec(A / 'authorization_v1.json')
    plan['activity_scope'] = inputs.spec(A / 'scope_v1.json')
    plan['fresh_qualification_scope'] = {'mandatory_roles': 30, 'episodes': 12,
        'previous_native_results_reused': False, 'two_dimensional_success_is_prerequisite': False,
        'seed_rule': SEED_RULE, 'start_graph_rule': START_RULE,
        'old_failures': 'All prior native and proxy failures retain their original verdicts; this plan grants no retrospective credit.'}
    for name in plan['policy_stages']:
        stage_spec(plan, PLAN, QUALIFICATION, name)
    require(sum(stage['expected_episodes'] for stage in plan['stages']) == 12
            and sum(len(preparation.primitives.roles(stage)) for stage in plan['stages']) == 30,
            'V40 omitted a mandatory native episode or scientific role')
    inputs.finish()
    plan['source_bindings'].update({path: row['sha256'] for path, row in inputs.proofs.items()})
    preparation.validate_plan(plan)
    dump(PLAN, plan)
    print(json.dumps({'plan': str(PLAN), 'plan_sha256': sha(PLAN), 'binding': str(BINDING),
        'binding_sha256': sha(BINDING), 'source_bindings': len(plan['source_bindings']),
        'binaries': len(plan['library_bindings']), 'engineering_remaining_seconds': str(remaining),
        'policy_stages': list(plan['policy_stages']), 'native_started': False}))


if __name__ == '__main__':
    main()
