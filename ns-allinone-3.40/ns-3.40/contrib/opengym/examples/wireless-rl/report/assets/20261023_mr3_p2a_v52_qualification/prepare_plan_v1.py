"""Seal one fresh V52 native qualification plan; never launch an experiment.

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

from .classification_admission_v1 import verify as verify_classification

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
QUALIFICATION = Path('/tmp/mr3_p2a_reach_v52_qualification.json')
RUN_ROOT = ROS / 'log/mr3_p2a_reach_v52'
POLICY_ROOT = ROS / 'log/mr3_ppo_reach_v52'
SEED_RULE = 'exact-point-bridge-v2'
START_RULE = 'point-attachment-3x3-v1'
PACKING_PROFILE = 'mr3-occupancy-int8-array-v1'
REACH_GEOMETRY_RULE = 'cone-support-v2'
RESOURCE = A / 'resource_v1.json'
NORMALIZED_PRIOR = A.parent / '20261023_mr3_p2a_v51_runtime_profile/closure_ledger_v1.json'
PRIOR_ORIGINAL_SHA256 = {
    'driver_summary': '974a22e9401ce45a0057d7150035dc295d4a6c24fc214d057bc3c0d35cde4294',
    'closed_metadata_review': 'b844223b1724c4bdc614a4d2a2bc2b9fa6a9d6567104fdd208e6471ed20ee714',
}


def entry_budget(inputs):
    spec = inputs.spec(RESOURCE)
    resource = preparation.engineering_resource_budget(spec, ROOT)
    value = decode(inputs.read(RESOURCE))
    _, raw = inputs.bound(value['previous_accounting'], NORMALIZED_PRIOR)
    closed = decode(raw)
    used = Decimal(value['engineering_used_seconds'])
    remaining = Decimal(value['engineering_remaining_seconds'])
    require(closed.get('schema') == 'mr3-engineering-closure-ledger-v1'
            and closed.get('passed') is True
            and Decimal(closed['engineering_cumulative_seconds']) == used
            and Decimal(closed['engineering_previous_cumulative_seconds'])
                + Decimal(closed['engineering_added_seconds']) == used
            and Decimal(closed['engineering_remaining_seconds'])
                + used == Decimal(closed['engineering_ceiling_seconds'])
            and closed.get('old_failures_and_cumulative_ledger_preserved') is True
            and closed.get('scientific_qualification_credit') is False,
            'entry cumulative use differs from the real normalized V51 closure')
    # V51 references are W-relative in the normalized ledger. Preserve and bind
    # their original bytes as well as the normalized cumulative figure.
    originals = {}
    for key in ('driver_summary', 'closed_metadata_review'):
        prior_spec = dict(closed[key])
        prior_spec['path'] = str((W / prior_spec['path']).relative_to(ROOT))
        require(prior_spec.get('sha256') == PRIOR_ORIGINAL_SHA256[key],
                'normalized ledger does not reference the actual closed V51 original')
        _, raw = inputs.bound(prior_spec)
        originals[key] = decode(raw)
    driver, review = originals['driver_summary'], originals['closed_metadata_review']
    lo, hi = driver['started_monotonic_ns'], driver['ended_monotonic_ns']
    require(type(lo) is int and type(hi) is int and 0 < lo < hi,
            'prior real parent interval is invalid')
    added = Decimal(hi - lo) / 10**9
    require(closed['actual_parent_intervals'] == [{'started_monotonic_ns': lo,
                'ended_monotonic_ns': hi, 'actual_seconds': str(added)}]
            and driver.get('schema') == 'mr3-single-ep-runtime-profile-driver-v1'
            and driver.get('passed') is True and driver.get('actual_returncode') == 0
            and driver.get('actual_wrapper_waited') is True and driver.get('errors') == []
            and Decimal(driver['actual_parent_wait_seconds']) == added
            and Decimal(driver['engineering_added_seconds']) == added
            and Decimal(closed['engineering_added_seconds']) == added
            and Decimal(driver['engineering_used_at_entry_seconds'])
                == Decimal(closed['engineering_previous_cumulative_seconds'])
            and Decimal(driver['engineering_cumulative_used_seconds']) == used
            and Decimal(driver['engineering_remaining_seconds'])
                == Decimal(closed['engineering_remaining_seconds'])
                == Decimal(review['engineering_remaining_seconds'])
            and Decimal(driver['engineering_ceiling_seconds'])
                == Decimal(closed['engineering_ceiling_seconds'])
            and closed['execution_freeze'] == driver['profiling_execution_freeze']
                == review['execution_freeze']
            and closed['native_evidence_freeze'] == driver['native_evidence_freeze']
                == review['native_evidence_freeze']
            and review.get('schema') == 'mr3-v51-independent-closed-metadata-review-v1'
            and review.get('passed') is True and review.get('actual_wrapper_waited') is True
            and review.get('scope_and_sources_unchanged') is True
            and review.get('all_saved_identities_fresh_gone') is True
            and review.get('closed_guard_and_child_passed') is True
            and Decimal(review['engineering_cumulative_used_seconds']) == used
            and Decimal(review['engineering_added_parent_wait_seconds']) == added
            and all(Decimal(row[key]) == 0 for row in (closed, review)
                    for key in ('external_scientific_tail_actual_seconds',
                                'pilot_added_seconds', 'validation_added_seconds')),
            'V51 normalized carry, exact parent fee, source or closure differs from actual originals')
    return resource, value, used, remaining
PINS = {
    PRIOR / 'predeclared_plan_v1.json': '331d83cb8fb7fb7498f9243eaccd49138f9117baae9ae69684d30b55ae8c2d3e',
    PRIOR / 'native_custody_binding_v1.json': '832c6fd25a44478cdbed6acf9ed2c35f8c8e501fe53674e6d432f7bd9e592470',
    BRIDGE: '3b8b9e03b786b8625a1a3747ee882c35d1dae106e969697ba6a829062ad37cbf',
}
CPU_ASSETS = A.parent / '20261023_mr3_p2a_v49_startup_protocol'
FRESH_CPU_GROUP = 'fresh_preparation_cpu_v1'
FRESH_CPU_SPEC = A / 'fresh_cpu_spec_v1.json'
PRESERVED_PPO_ASSETS = A.parent / '20261023_mr3_p2a_v50_qualification'
PRESERVED_PPO_TESTS = ('test_reach_runtime_fault_admission', 'test_reach_training_admission',
                       'test_reach_policy_chain', 'test_audit_reach_ppo')
PILOT_REQUESTED_DECISIONS = 64  # Prospective candidate; must agree with the new sealed scope.
CPU_INPUTS = {name: (CPU_ASSETS / 'checks' / name / 'actual_wait.json',
                    CPU_ASSETS / 'checks' / (name + '_source_recovery.json'))
    for name in ('geometry_cpu_v2', 'learner_cpu_v2', 'reader_cpu_v2',
                 'snapshot_cpu_v2', 'readiness_cpu_v2', 'startup_review_cpu_v1')}
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


def verify_authorization(inputs, remaining=None):
    resource, decision, opening_used, opening_remaining = entry_budget(inputs)
    scope = decode(inputs.read(A / 'scope_v1.json'))
    authorization = decode(inputs.read(A / 'authorization_v1.json'))
    require(scope.get('schema') == 'mr3-p2a-v52-native-qualification-scope-v1'
            and scope.get('pilot_requested_decisions') == PILOT_REQUESTED_DECISIONS
            and scope.get('engineering_resource') == inputs.spec(RESOURCE),
            'prospective scope differs from the one sealed resource or pilot prefix')
    require(authorization.get('schema') == 'mr3-p2a-autonomous-continuation-authorization-v1'
            and authorization.get('status') == 'AUTHORIZED_BY_USER_CONTINUATION'
            and authorization.get('user_exact_text') == '你一直继续执行就好了，直到把P2A完成，不需要问我是否批准'
            and authorization.get('numeric_user_approval_claimed') is False
            and authorization.get('engineering_resource') == inputs.spec(RESOURCE)
            and authorization.get('acceptance_gates_unchanged') is True
            and authorization.get('old_failures_preserved') is True
            and authorization.get('p2b_gateway_authorized') is False,
            'V52 continuation authority/resource attribution is missing or false')
    require(scope.get('pilot_remaining_decisions') == 1870
            and scope.get('pilot_remaining_wall_seconds') == '2905.9547395464029'
            and scope.get('final_only_schedule') == ['open:401', 'open:402', 'open:403']
            and (remaining is None or remaining == opening_remaining),
            'resource plan cannot alter the independent pilot/final quotas or entry balance')
    require(scope.get('robots_per_environment') == 3 and scope.get('mandatory_roles') == 30
            and scope.get('matrix_episodes') == 12 and scope.get('minimum_decisions') == 16
            and scope.get('mapping_target') == 0.95 and scope.get('acceptance_gates_unchanged') is True
            and scope.get('old_failures_preserved') is True
            and scope.get('no_retry_on_required_failure') is True
            and scope.get('p2b_gateway_authorized') is False
            and scope.get('prior_native_credit_reused') is False
            and scope.get('seed_rule') == SEED_RULE and scope.get('start_graph_rule') == START_RULE
            and scope.get('reach_geometry_rule') == REACH_GEOMETRY_RULE
            and scope.get('reset_workload_reader_profile') == preparation.reset_workload.PROFILE,
            'resource profile cannot weaken the declared scientific workload or gates')
    return authorization, resource


def verify_plan_resource(plan, inputs=None):
    """One admission boundary shared by preflight, plan-check and driver."""
    inputs = Inputs() if inputs is None else inputs
    remaining = Decimal(plan['budget']['engineering_remaining_seconds'])
    _, resource = verify_authorization(inputs, remaining)
    require(plan.get('engineering_resource') == inputs.spec(RESOURCE)
            and plan.get('agent_resource_decision_evidence') == inputs.spec(RESOURCE)
            and plan.get('authorization_evidence') == inputs.spec(A / 'authorization_v1.json')
            and plan.get('activity_scope') == inputs.spec(A / 'scope_v1.json')
            and all(plan['budget'].get(key) == value for key, value in resource['budget'].items())
            and plan['budget'].get('full_minimum_reservation_available_at_plan_entry') is True
            and 'approved_cumulative_engineering_seconds' not in plan['budget']
            and 'approved_budget_evidence' not in plan,
            'sealed plan does not repeat the exact agent-selected resource')
    for stage in plan['stages']:
        name = stage['stage']
        require(stage['wall_seconds'] == resource['stage_wall_seconds'][name]
                and preparation.argument(stage['native']['argv'], '--work-wall-seconds')
                    == resource['native_wall_seconds'][name],
                'stage/native allocation differs from the one resource')
    return resource, inputs


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


def verify_preserved_ppo_cpu(inputs):
    """Retain V50's five explicitly replaced files only at exact tested bytes."""
    wait_path = PRESERVED_PPO_ASSETS / 'checks/ppo_fault_cpu_v1/actual_wait.json'
    recovery_path = PRESERVED_PPO_ASSETS / 'checks/ppo_fault_cpu_v1_source_recovery.json'
    value = decode(inputs.read(wait_path))
    verify_wait(value)
    require(value['actual_argv'] == ['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python',
        '-B', '-m', 'pytest', '-q',
        *(str(W / 'mr3_learning/tests' / (name + '.py')) for name in PRESERVED_PPO_TESTS)],
        'preserved V50 PPO CPU command differs')
    inputs.bound(value['console'])
    sources = {str(Path(row['path']).resolve().relative_to(ROOT)): row
               for row in value['source_before']}
    recovery_rows = decode(inputs.read(recovery_path))['sources']
    recovery = {row['path']: row for row in recovery_rows}
    require(len(sources) == len(value['source_before']) and len(recovery) == len(recovery_rows),
            'duplicate preserved V50 PPO CPU source')
    paths = {str((W / 'mr3_learning/ppo.py').relative_to(ROOT)),
        *(str((W / 'mr3_learning/tests' / (name + '.py')).relative_to(ROOT))
          for name in PRESERVED_PPO_TESTS)}
    for relative in sorted(paths):
        row, saved = sources[relative], recovery[relative]
        raw = inputs.read(ROOT / relative)
        require(type(row['bytes']) is int and row['bytes'] >= 0
                and row['sha256'] == saved.get('sha256') == hashlib.sha256(raw).hexdigest()
                and row['bytes'] == saved.get('bytes') == len(raw),
                'preserved V50 PPO replacement differs from exact current bytes: ' + relative)
    return paths


def verify_preparation_evidence(*, inputs=None):
    """Reuse real V49 CPU evidence only where exact tested current bytes agree.

    All tests are classified explicitly before Git-add; old orchestration files
    are recoverable artifacts, never new V52 entry-execution evidence.
    """
    inputs = Inputs() if inputs is None else inputs
    runtime = preparation.source_inventory(ROOT)
    runtime.update(str(path.relative_to(ROOT)) for path in
        (ROS / 'src/multi_robot_exploration/multi_robot_exploration').glob('*.py'))
    tests = {str(path.relative_to(ROOT)) for directory in
        (ROS / 'src/multi_robot_exploration/test', W / 'mr3_learning/tests')
        for path in directory.glob('test_*.py')}
    runtime.difference_update(tests)
    current_required = runtime | tests
    # New PPO fault semantics may never be relabelled a CPU-only artifact.
    # Its new targeted group must execute before classification/plan preparation.
    fresh_spec = decode(inputs.read(FRESH_CPU_SPEC))
    require(set(fresh_spec) == {'schema', 'actual_argv', 'replacement_paths', 'test_files',
                              'scientific_qualification_credit'}
            and fresh_spec['schema'] == 'mr3-v52-fresh-cpu-spec-v1'
            and fresh_spec['scientific_qualification_credit'] is False
            and type(fresh_spec['actual_argv']) is list and fresh_spec['actual_argv']
            and all(type(arg) is str for arg in fresh_spec['actual_argv'])
            and type(fresh_spec['replacement_paths']) is list
            and all(type(path) is str for path in fresh_spec['replacement_paths'])
            and len(fresh_spec['replacement_paths']) == len(set(fresh_spec['replacement_paths'])),
            'fresh preparation CPU specification is missing or malformed')
    names = fresh_spec['test_files']
    require(type(names) is list and names and len(names) == len(set(names))
            and all(type(name) is str and name.isidentifier() for name in names)
            and fresh_spec['actual_argv'] == ['/home/zhuyulab/miniconda3/envs/ns3gym/bin/python',
                '-B', '-m', 'pytest', '-q',
                *(str(W / 'mr3_learning/tests' / (name + '.py')) for name in names)],
            'fresh CPU command does not execute its exact declared tests')
    fresh_path = A / 'checks' / FRESH_CPU_GROUP / 'actual_wait.json'
    fresh_recovery_path = A / 'checks' / (FRESH_CPU_GROUP + '_source_recovery.json')
    fresh = decode(inputs.read(fresh_path))
    verify_wait(fresh)
    require(fresh['actual_argv'] == fresh_spec['actual_argv'], 'new PPO fault CPU command differs')
    inputs.bound(fresh['console'])
    fresh_records = decode(inputs.read(fresh_recovery_path))['sources']
    recovered = {row['path']: row for row in fresh_records}
    require(len(recovered) == len(fresh_records), 'duplicate new PPO CPU recovery')
    fresh_current = {}
    for source in fresh['source_before']:
        path = Path(source['path']).resolve()
        relative = str(path.relative_to(ROOT))
        raw = inputs.read(path)
        expected = {'sha256': source['sha256'], 'bytes': source['bytes']}
        require(relative not in fresh_current
                and all(recovered[relative].get(key) == item for key, item in expected.items())
                and hashlib.sha256(raw).hexdigest() == expected['sha256'] and len(raw) == expected['bytes'],
                'new PPO CPU source is not exact current bytes: ' + relative)
        fresh_current[relative] = expected
    replacement_paths = set(fresh_spec['replacement_paths'])
    fixed_replacements = {str((W / 'mr3_learning' / name).relative_to(ROOT)) for name in
        ('reach_preparation.py', 'reach_audit_projection.py', 'audit_reach_runtime.py',
         'audit_reach_reset_workload.py', 'tests/test_reach_reset_workload.py',
         'tests/test_reach_engineering_block.py', 'tests/test_reach_runtime_index_regression.py',
         'tests/test_reach_preparation_entry.py')}
    require(replacement_paths == fixed_replacements,
            'fresh replacement whitelist differs from the explicit V52 changed/new modules/tests')
    require(replacement_paths <= fresh_current.keys(),
            'new preparation production/tests lack fresh exact CPU binding')
    # These five V50 changes already replaced older V49 bytes. They are not
    # automatically inherited: verify the exact original command/current SHA.
    preserved_ppo_paths = verify_preserved_ppo_cpu(inputs)
    covered = replacement_paths | preserved_ppo_paths
    rows = [{'id': FRESH_CPU_GROUP, 'actual_wait': inputs.spec(fresh_path),
             'source_recovery': inputs.spec(fresh_recovery_path),
             'actual_child_wait_seconds': fresh['actual_child_wait_seconds'],
             'new_current_runtime_and_test_credit': sorted(replacement_paths),
             'source_count': len(fresh_current)}]
    historical_inputs = dict(CPU_INPUTS)
    old_ppo = PRESERVED_PPO_ASSETS
    historical_inputs['v50_ppo_fault_cpu_v1'] = (old_ppo / 'checks/ppo_fault_cpu_v1/actual_wait.json',
        old_ppo / 'checks/ppo_fault_cpu_v1_source_recovery.json')
    for name, (wait_path, recovery_path) in historical_inputs.items():
        wait = decode(inputs.read(wait_path))
        verify_wait(wait)
        inputs.bound(wait['console'])
        records = decode(inputs.read(recovery_path))['sources']
        recovery = {row['path']: row for row in records}
        require(len(recovery) == len(records), 'duplicate original CPU source recovery')
        seen, counts = set(), dict(runtime=0, test=0, artifact=0)
        for source in wait['source_before']:
            path = Path(source['path']).resolve()
            relative = str(path.relative_to(ROOT))
            require(relative not in seen and type(source['bytes']) is int and source['bytes'] >= 0,
                    'duplicate/malformed original CPU source')
            seen.add(relative)
            expected = {'sha256': source['sha256'], 'bytes': source['bytes']}
            saved = recovery[relative]
            require(all(saved.get(key) == item for key, item in expected.items()),
                    'original CPU recovery hash/size differs')
            current = inputs.read(path)
            matches = hashlib.sha256(current).hexdigest() == expected['sha256'] and len(current) == expected['bytes']
            category = 'test' if relative in tests else 'runtime' if relative in runtime else 'artifact'
            counts[category] += 1
            if relative in current_required:
                require(matches or relative in replacement_paths or relative in preserved_ppo_paths,
                        'tested runtime/test source differs from current preparation: ' + relative)
                covered.add(relative)
            if not matches:
                if saved.get('kind') == 'snapshot':
                    original = inputs.read(recovery_path.parent.parent / saved['snapshot'])
                else:
                    require(saved.get('kind') == 'git_blob', 'unknown original artifact recovery kind')
                    original = subprocess.check_output(['git', 'show', saved['freeze'] + ':' + relative], cwd=ROOT)
                require(hashlib.sha256(original).hexdigest() == expected['sha256'] and len(original) == expected['bytes'],
                        'changed CPU-only artifact original bytes are not recoverable')
        rows.append({'id': name, 'actual_wait': inputs.spec(wait_path),
            'source_recovery': inputs.spec(recovery_path), 'actual_returncode': 0,
            'actual_child_wait_seconds': wait['actual_child_wait_seconds'],
            'source_count': len(seen), 'classification_counts': counts})
    required_current = {str((W / 'mr3_learning' / name).relative_to(ROOT)) for name in
        ('reach_preparation.py', 'reach_policy_chain.py', 'reach_gates.py', 'ppo.py', 'supervisor.py',
         'audit_reach_runtime.py', 'audit_reach_preparation.py', 'audit_reach_ppo.py', 'reach_support_replay.py')}
    required_current.update('ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/' + name
        for name in ('mr3_observation.py', 'mr3_seed_certificate.py', 'mr3_point_graph.py', 'mr3_adapter.py',
                     'mr3_reach_support.py', 'mr3_reach_runtime.py', 'motion_safety.py'))
    required_current.add('ros2_ws/ros2-multi-robot-automap/src/merge_map/merge_map/merge_map.py')
    require(required_current <= covered, 'current native source CPU coverage is incomplete')
    return {'schema': 'mr3-p2a-v52-source-preparation-proof-v1', 'passed': True,
        'entries': rows, 'current_runtime_and_test_sources_checked': len(covered),
        'scientific_pass_claimed': False, 'native_admission': False,
        'native_or_qualification_credit': False, 'fresh_full_native_qualification_required': True,
        'new_v52_orchestration_executed_by_these_receipts': False,
        'preserved_v50_ppo_replacement_sources': sorted(preserved_ppo_paths),
        'fresh_cpu_spec': inputs.spec(FRESH_CPU_SPEC), 'scientific_consumer_or_native_credit': False}, inputs


def policy_registry(old_plan, plan_path=PLAN, qualification=QUALIFICATION):
    registry = copy.deepcopy(old_plan['policy_stages'])
    require(set(registry) == {'minimum', 'pilot', 'validation'}, 'old policy registry is incomplete')
    for name, domain, port in (('minimum', 212, 15801), ('pilot', 214, 15811), ('validation', 218, 15821)):
        row, run_id = registry[name], 'mr3_p2a_reach_v52_' + name
        command = row['argv']
        for flag, value in (('--reach-plan', plan_path), ('--reach-qualification', qualification),
                ('--base-domain', domain), ('--base-port', port), ('--output-root', POLICY_ROOT), ('--run-id', run_id)):
            replace_argument(command, flag, value)
        require('--seed-rule' not in command and '--start-graph-rule' not in command,
                'historical policy input already has an unexpected rule override')
        command.extend(['--seed-rule', SEED_RULE, '--start-graph-rule', START_RULE, '--reach-geometry-rule', REACH_GEOMETRY_RULE])
        row.update(run_directory=str(POLICY_ROOT / run_id), output_directory='/tmp/mr3_p2a_reach_v52_' + name)
        if name == 'pilot':
            replace_argument(command, '--decisions', PILOT_REQUESTED_DECISIONS)
        row['external_finalize_reserve_seconds'] = '0' if name == 'minimum' else '300'
        if name != 'minimum':
            previous = 'minimum' if name == 'pilot' else 'pilot'
            row['condition'].update(previous_stage_summary=f'/tmp/mr3_p2a_reach_v52_{previous}/summary.json',
                previous_stage_outer_wait=f'/tmp/mr3_p2a_reach_v52_{previous}_wait/actual_wait.json',
                previous_stage_final_absence=f'/tmp/mr3_p2a_reach_v52_{previous}_final.json')
        if name == 'validation':
            replace_argument(command, '--checkpoint', POLICY_ROOT / 'mr3_p2a_reach_v52_pilot/final.zip')
    return registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engineering-resource-sha256', required=True)
    args = parser.parse_args(argv)
    require(not PLAN.exists() and not BINDING.exists(), 'V52 outputs already exist; preserve the original preparation attempt')
    inputs = Inputs()
    require(inputs.spec(RESOURCE)['sha256'] == args.engineering_resource_sha256,
            'caller resource SHA differs from the sealed file')
    _, resource = verify_authorization(inputs)
    remaining = Decimal(resource['budget']['engineering_remaining_seconds'])
    inputs.read(A / 'scope_v1.json')
    classification = verify_classification(inputs, verify_wait)
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
    source_paths.update((ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration').glob('mr3_reach_*.py'))
    source_paths.update(A.glob('*.py'))
    source_paths.add(A.parent / '20261023_mr3_p2a_v50_qualification/external_absence_v1.py')
    source_paths.update((A / name) for name in ('authorization_v1.json', 'resource_v1.json', 'scope_v1.json', 'fresh_cpu_spec_v1.json'))
    sources = {row['path']: row for row in (inputs.spec(path) for path in sorted(source_paths))}
    binding['source_bindings'] = [sources[path] for path in sorted(sources)]
    binding['reach_geometry_rule'] = REACH_GEOMETRY_RULE
    wrappers = sorted(path for path in (W / 'mr3_learning').glob('*.py')
        if path.name.startswith(('reach_', 'audit_reach_')) or path.name == 'native_custody_reach.py')
    binding['qualification_wrappers'] = [inputs.spec(path) for path in [*wrappers, *sorted(A.glob('*.py'))]]
    binding['build_receipts'][0] = inputs.spec(BRIDGE)
    dump(BINDING, binding)
    plan = preparation.build_plan(plan_path=PLAN, seed_rule=SEED_RULE, start_graph_rule=START_RULE, reach_geometry_rule=REACH_GEOMETRY_RULE,
        output_directory='/tmp/mr3_p2a_reach_v52_matrix', run_root=RUN_ROOT, custody_binding=BINDING,
        binary_proof=BRIDGE, preflight='/tmp/mr3_p2a_reach_v52_preflight.json',
        engineering_remaining_seconds=str(remaining), run_prefix='mr3_p2a_reach_v52',
        reservation_profile=preparation.AUTONOMOUS_RESOURCE_PROFILE,
        engineering_resource=inputs.spec(RESOURCE))
    for stage, domain, port in zip(plan['stages'], (202, 204, 206, 210), (15701, 15711, 15721, 15731)):
        replace_argument(stage['native']['argv'], '--base-domain', domain)
        replace_argument(stage['native']['argv'], '--base-port', port)
    plan['budget']['full_minimum_reservation_available_at_plan_entry'] = True
    external = resource['budget']['external_final_and_accounting_reservation_seconds']
    condition = {'accounting_source': 'external actual engineering ledger after every submitted child and closure tail is waited',
        'admit_only_if': 'actual_engineering_remaining_seconds >= 1800 + unused_external_reserve_seconds',
        'minimum_stage_reservation_seconds': '1800', 'external_reserve_initial_seconds': external,
        'unused_external_reserve_rule': 'max(0, sealed_external_reserve_seconds - actual_external_tail_seconds_already_charged)',
        'enforcement_owner': 'root external actual-fee admission before invoking reach_policy_chain minimum',
        'otherwise': 'SKIPPED for insufficient actual engineering balance; no cap reduction, retry, pilot borrowing or extension'}
    plan['post_qualification'] = {'fresh_minimum': {'seed': 41, 'decisions': 16, 'wall_reservation_seconds': '1800',
        'native_wall_seconds': '1150', 'epochs': 4, 'batch_size': 16,
        'required': 'actual eligible samples, positive optimizer changes and complete new independent audit',
        'engineering_balance_condition': condition}, 'external_final_and_accounting_reservation_seconds': external,
        'pilot_requested_decisions': PILOT_REQUESTED_DECISIONS,
        'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
        'final_only_development_validations': 3, 'p2b_or_gateway_authorized': False, 'no_retry_on_required_failure': True}
    plan['map_output_packing_profile'] = PACKING_PROFILE
    plan['policy_stages'] = policy_registry(old_plan)
    plan['sensor_source_profile'] = copy.deepcopy(old_plan['sensor_source_profile'])
    plan['prospective_preparation_requirement'] = proof
    plan['prospective_classification_regression'] = classification
    plan['agent_resource_decision_evidence'] = inputs.spec(RESOURCE)
    plan['authorization_evidence'] = inputs.spec(A / 'authorization_v1.json')
    plan['activity_scope'] = inputs.spec(A / 'scope_v1.json')
    plan['fresh_qualification_scope'] = {'mandatory_roles': 30, 'episodes': 12,
        'previous_native_results_reused': False, 'two_dimensional_success_is_prerequisite': False,
        'seed_rule': SEED_RULE, 'start_graph_rule': START_RULE,
        'map_output_packing_profile': PACKING_PROFILE, 'reach_geometry_rule': REACH_GEOMETRY_RULE,
        'old_failures': 'All prior native and proxy failures retain their original verdicts; this plan grants no retrospective credit.'}
    for name in plan['policy_stages']:
        stage_spec(plan, PLAN, QUALIFICATION, name)
    require(sum(stage['expected_episodes'] for stage in plan['stages']) == 12
            and sum(len(preparation.primitives.roles(stage)) for stage in plan['stages']) == 30,
            'V52 omitted a mandatory native episode or scientific role')
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

