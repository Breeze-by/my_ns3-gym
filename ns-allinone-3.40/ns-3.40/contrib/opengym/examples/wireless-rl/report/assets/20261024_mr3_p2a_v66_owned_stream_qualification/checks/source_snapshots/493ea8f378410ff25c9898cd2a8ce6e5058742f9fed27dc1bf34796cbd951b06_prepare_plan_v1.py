"""Seal one fresh V66 native qualification plan; never launch an experiment.

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
BRIDGE = Path(__file__).resolve().parent / 'native_build_bridge_v1.json'
PLAN = A / 'plan_v1.json'
BINDING = A / 'native_custody_binding_v1.json'
QUALIFICATION = Path('/tmp/mr3_p2a_reach_v66_qualification.json')
RUN_ROOT = ROS / 'log/mr3_p2a_reach_v66'
POLICY_ROOT = ROS / 'log/mr3_ppo_reach_v66'
SEED_RULE = 'exact-point-bridge-v2'
START_RULE = 'point-attachment-3x3-v1'
PACKING_PROFILE = 'mr3-occupancy-int8-array-v1'
REACH_GEOMETRY_RULE = 'cone-support-v2'
RESOURCE = A / 'resource_v1.json'
PRIOR_ACTIVITY = A.parent / '20261023_mr3_p2a_v59_encoder_profile'
NORMALIZED_PRIOR = W / 'report/assets/20261024_mr3_p2a_v65_owned_stream_qualification/closure_ledger_v1.json'
PREVIOUS_LEDGER_SHA256 = '773c0d31b705a45dff2116472ae851cce368f14a4b774a335c11e40c89b1ef2b'
ACTUATION_PROFILE = 'initial-zero-encoder-hold-v1'
MOTION_AUTHORITY_PROFILE = 'mr3-owned-stream-authority-v1'
WORKLOAD_PROFILE = preparation.reset_workload.PROFILE_V2
PROBE_VERSION = preparation.reset_workload.PROBE_VERSION_V2


def entry_budget(inputs):
    """Carry the actual closed V65 failure fee; no account reset or native credit."""
    resource = preparation.engineering_resource_budget(inputs.spec(RESOURCE), ROOT)
    value = decode(inputs.read(RESOURCE))
    _, raw = inputs.bound(value['previous_accounting'], NORMALIZED_PRIOR)
    require(hashlib.sha256(raw).hexdigest() == PREVIOUS_LEDGER_SHA256,
            'actual previous V65 closed failure ledger bytes differ')
    closed = decode(raw)
    used, remaining = map(Decimal, (value['engineering_used_seconds'], value['engineering_remaining_seconds']))
    added = Decimal(closed['engineering_added_parent_union_seconds'])
    require(closed.get('schema') == 'mr3-engineering-closure-ledger-v1'
            and closed.get('passed') is True and closed.get('activity_passed') is False
            and closed.get('activity_passed_scope') == 'preflight FAIL before any matrix or World'
            and closed.get('execution_freeze') == '6acdb141c47ec87d39cb8e32633b79605db68206'
            and type(closed.get('actual_root_tool_session_id')) is int and closed['actual_root_tool_session_id'] == 25222
            and type(closed.get('actual_root_tool_returncode')) is int and closed['actual_root_tool_returncode'] == 1
            and added == Decimal('57.081760798')
            and Decimal(closed['engineering_entry_seconds']) + added == used
            and Decimal(closed['engineering_cumulative_seconds']) == used == Decimal('109131.3266391666018')
            and Decimal(closed['engineering_ceiling_seconds']) == Decimal('180000')
            and Decimal(closed['engineering_remaining_seconds']) == remaining == Decimal('70868.6733608333982')
            and closed.get('actual_recorded_before_after_count') == 1096 and closed.get('actual_before_after_equal') is True
            and closed.get('current_Git_nonlibrary_source_count') == 1086 and closed.get('current_selected_ELF_count') == 10
            and closed.get('saved_main_identity_count') == 3 and closed.get('all_saved_main_identities_fresh_gone') is True
            and closed.get('nonowned_ancestor_absence_claimed') is False
            and closed.get('matrix_submitted') is False and closed.get('World_started') is False
            and closed.get('scientific_qualification_credit') is False and closed.get('old_FAIL_rejudged') is False
            and closed.get('capacity_qualified') is False and closed.get('automatic_pilot_final_entry_allowed') is False
            and closed.get('P2A_complete') is False
            and all(Decimal(closed[k]) == 0 for k in ('pilot_added_parent_union_seconds','validation_added_parent_union_seconds')),
            'actual V65 FAIL/reap/fullfee/source/owned closure differs')
    require(Decimal(value['engineering_ceiling_seconds']) == Decimal('180000')
            and used + remaining == Decimal('180000') and value['decision_maker'] == 'agent'
            and value['numeric_user_approval_claimed'] is False,
            'finite continuation account is not the declared agent decision')
    return resource, value, used, remaining

PINS = {
    PRIOR / 'predeclared_plan_v1.json': '331d83cb8fb7fb7498f9243eaccd49138f9117baae9ae69684d30b55ae8c2d3e',
    PRIOR / 'native_custody_binding_v1.json': '832c6fd25a44478cdbed6acf9ed2c35f8c8e501fe53674e6d432f7bd9e592470',
}
CPU_ASSETS = A.parent / '20261023_mr3_p2a_v49_startup_protocol'
FRESH_CPU_GROUP = 'fresh_preparation_cpu_v1'
PRESERVED_EVIDENCE = A.parent / '20261024_mr3_p2a_v65_owned_stream_qualification'
PRESERVED_PREPARER_SHA256 = 'a017df9b1b6210d0b8c1ec6f29f0d6bac5072b366929599f9ab84e13a672e5e0'
FRESH_CPU_SPEC = PRESERVED_EVIDENCE / 'fresh_cpu_spec_v3.json'
CURRENT_BUILD = A
PRESERVED_PPO_ASSETS = A.parent / '20261023_mr3_p2a_v50_qualification'
PRIOR_FRESH_CPU_SPEC_SHA256 = '43f7b4bba131ef272619e8902b08e80ac1b043cb57e958fe83e1fdc8fe8a9653'
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
    require(scope.get('schema') == 'mr3-p2a-v66-native-qualification-scope-v1'
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
            'V66 continuation authority/resource attribution is missing or false')
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
            and scope.get('reset_workload_reader_profile') == WORKLOAD_PROFILE
            and scope.get('preparation_probe_version') == PROBE_VERSION
            and scope.get('actuation_profile') == ACTUATION_PROFILE
            and scope.get('motion_authority_profile') == MOTION_AUTHORITY_PROFILE
            and scope.get('capacity_qualified') is False
            and scope.get('automatic_policy_entry_allowed') is False,
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


def verify_preserved_ppo_cpu(inputs, *, freshly_verified_paths=()):
    """V50 supplies only exact-byte credit; changed paths need a later real CPU proof."""
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
    preserved = set()
    for relative in sorted(paths):
        row, saved = sources[relative], recovery[relative]
        require(type(row['bytes']) is int and row['bytes'] >= 0
                and row['sha256'] == saved.get('sha256') and row['bytes'] == saved.get('bytes'),
                'original V50 PPO replacement/recovery differs: ' + relative)
        raw = inputs.read(ROOT / relative)
        if row['sha256'] == hashlib.sha256(raw).hexdigest() and row['bytes'] == len(raw):
            preserved.add(relative)
        else:
            require(relative in freshly_verified_paths,
                    'changed V50 PPO source lacks later successful exact CPU coverage: ' + relative)
    return preserved




def verify_preparation_evidence(*, inputs=None):
    """Reuse actual A65 CPU evidence at identical current bytes; no new 688 run.

    The unchanged A65 verifier keeps its genuine A-relative waits, recovery,
    covered-path declarations and JUnit identities. New A66 entry/config code
    is separately checked by this activity's actual 33-case admission.
    """
    import importlib
    inputs = Inputs() if inputs is None else inputs
    source = PRESERVED_EVIDENCE / 'prepare_plan_v1.py'
    require(hashlib.sha256(inputs.read(source)).hexdigest() == PRESERVED_PREPARER_SHA256,
            'preserved A65 whole verifier source changed')
    preserved = importlib.import_module('report.assets.20261024_mr3_p2a_v65_owned_stream_qualification.prepare_plan_v1')
    require(Path(preserved.__file__).resolve() == source, 'noncanonical preserved A65 verifier import')
    actual, _ = preserved.verify_preparation_evidence(inputs=inputs)
    require(actual.get('passed') is True and actual.get('scientific_pass_claimed') is False,
            'actual A65 same-byte CPU preparation proof failed')
    wait_path = PRESERVED_EVIDENCE / 'checks/dual_readiness_cpu_v1/actual_wait.json'
    wait = decode(inputs.read(wait_path)); verify_wait(wait)
    expected_argv = ['/usr/bin/python3','-B','-m',
        'report.assets.20261024_mr3_p2a_v65_owned_stream_qualification.readiness_v1',
        '--mode','both','--output',str(PRESERVED_EVIDENCE/'checks/dual_env_readiness_v1.json')]
    require(wait['actual_argv'] == expected_argv and wait['source_before'] == wait['source_after'],
            'preserved A65 actual dual-readiness command/source differs')
    inputs.bound(wait['console'])
    for row in wait['source_before']:
        raw = inputs.read(Path(row['path']))
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                'preserved actual readiness bound source changed: '+row['path'])
    ready = []
    for name in ('dual_env_readiness_v1.json','dual_env_readiness_v1_ros.json','dual_env_readiness_v1_learner.json'):
        path = PRESERVED_EVIDENCE / 'checks' / name
        document = decode(inputs.read(path))
        require(document.get('passed') is True and document.get('world_started') is False,
                'preserved A65 readiness was not a real software-only PASS')
        modules = list(document.get('modules', []))
        modules.extend(document.get('reader_definitions', {}).get('modules', []))
        for row in modules:
            current = inputs.read(Path(row['path']))
            require(len(current) == row['bytes'] and hashlib.sha256(current).hexdigest() == row['sha256'],
                    'preserved readiness module changed: '+row['path'])
        ready.append(inputs.spec(path))
    return {'schema':'mr3-p2a-v66-preserved-software-preparation-proof-v1','passed':True,
        'preserved_evidence_asset':str(PRESERVED_EVIDENCE),'preserved_whole_verifier':inputs.spec(source),
        'actual_A65_source_preparation':actual,'A65_original_readiness':ready,
        'A65_original_readiness_actual_wait':inputs.spec(wait_path),
        'credit_requires_exact_current_source_bytes':True,'new_A66_688_tests_executed':False,
        'new_entry_admission_is_separate':True,'readiness_device_observation_is_historical':True,
        'formal_preflight_checks_current_cuda_and_source_build_again':True,
        'scientific_pass_claimed':False,'native_admission':False,'native_or_qualification_credit':False}, inputs




def policy_registry(old_plan, plan_path=PLAN, qualification=QUALIFICATION):
    registry = copy.deepcopy(old_plan['policy_stages'])
    require(set(registry) == {'minimum', 'pilot', 'validation'}, 'old policy registry is incomplete')
    for name, domain, port in (('minimum', 212, 15801), ('pilot', 214, 15811), ('validation', 218, 15821)):
        row, run_id = registry[name], 'mr3_p2a_reach_v66_' + name
        row['actuation_profile'] = ACTUATION_PROFILE
        row['motion_authority_profile'] = MOTION_AUTHORITY_PROFILE
        command = row['argv']
        for flag, value in (('--reach-plan', plan_path), ('--reach-qualification', qualification),
                ('--base-domain', domain), ('--base-port', port), ('--output-root', POLICY_ROOT), ('--run-id', run_id)):
            replace_argument(command, flag, value)
        require('--seed-rule' not in command and '--start-graph-rule' not in command,
                'historical policy input already has an unexpected rule override')
        command.extend(['--seed-rule', SEED_RULE, '--start-graph-rule', START_RULE, '--reach-geometry-rule', REACH_GEOMETRY_RULE])
        row.update(run_directory=str(POLICY_ROOT / run_id), output_directory='/tmp/mr3_p2a_reach_v66_' + name)
        if name == 'pilot':
            replace_argument(command, '--decisions', PILOT_REQUESTED_DECISIONS)
        row['external_finalize_reserve_seconds'] = '0' if name == 'minimum' else '300'
        if name != 'minimum':
            previous = 'minimum' if name == 'pilot' else 'pilot'
            row['condition'].update(previous_stage_summary=f'/tmp/mr3_p2a_reach_v66_{previous}/summary.json',
                previous_stage_outer_wait=f'/tmp/mr3_p2a_reach_v66_{previous}_wait/actual_wait.json',
                previous_stage_final_absence=f'/tmp/mr3_p2a_reach_v66_{previous}_final.json')
        if name == 'validation':
            replace_argument(command, '--checkpoint', POLICY_ROOT / 'mr3_p2a_reach_v66_pilot/final.zip')
    return registry


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engineering-resource-sha256', required=True)
    args = parser.parse_args(argv)
    require(not PLAN.exists() and not BINDING.exists(), 'V66 outputs already exist; preserve the original preparation attempt')
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
    for name, row in binding['binaries'].items():
        if name == 'driver':
            continue  # The new actual-build branch below proves this one changed DSO.
        actual = native.file_proof(row['path'])
        require(actual['sha256'] == row['sha256'] and actual['bytes'] == row['bytes'],
                'native ELF changed without a new original build proof: ' + row['path'])
        row.update(actual)
    for name, fields in binding['compiled_sources'].items():
        if name == 'driver':
            continue
        for row in fields.values():
            inputs.bound(row)
    from .make_native_binding_v1 import update_driver_binding
    binding = update_driver_binding(binding, CURRENT_BUILD / 'checks/native_build_v1/build_manifest_v1.json', BRIDGE)
    source_paths = {ROOT / row['path'] if not Path(row['path']).is_absolute() else Path(row['path'])
                    for row in binding['source_bindings']}
    extra = binding['initial_encoder_compiled_source']
    source_paths.add(Path(extra['path']) if Path(extra['path']).is_absolute() else ROOT / extra['path'])
    source_paths.update((BRIDGE, ROOT / custody.INITIAL_ENCODER_SOURCE_PROFILE))
    source_paths.update(path for directory in (CURRENT_BUILD / 'checks/native_build_v1', CURRENT_BUILD / 'native')
                        for path in directory.rglob('*') if path.is_file() and not path.is_symlink())
    source_paths.update(ROOT / path for path in preparation.source_inventory(ROOT))
    # Include newly added Python before Git-add as well; the fresh proof has
    # already checked this complete filesystem source/test union bytewise.
    fresh_sources = decode(inputs.read(FRESH_CPU_SPEC))['source_bindings']
    source_paths.update(ROOT / relative for relative in fresh_sources)
    source_paths.update((ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration').glob('mr3_reach_*.py'))
    source_paths.update(A.glob('*.py'))
    source_paths.add(A.parent / '20261023_mr3_p2a_v50_qualification/external_absence_v1.py')
    source_paths.update((A / name) for name in ('authorization_v1.json', 'resource_v1.json', 'scope_v1.json'))
    source_paths.add(FRESH_CPU_SPEC)
    sources = {row['path']: row for row in (inputs.spec(path) for path in sorted(source_paths))}
    binding['source_bindings'] = [sources[path] for path in sorted(sources)]
    binding['reach_geometry_rule'] = REACH_GEOMETRY_RULE
    binding['actuation_profile'] = ACTUATION_PROFILE
    binding['motion_authority_profile'] = MOTION_AUTHORITY_PROFILE
    wrappers = sorted(path for path in (W / 'mr3_learning').glob('*.py')
        if path.name.startswith(('reach_', 'audit_reach_')) or path.name == 'native_custody_reach.py')
    binding['qualification_wrappers'] = [inputs.spec(path) for path in [*wrappers, *sorted(A.glob('*.py'))]]
    binding['build_receipts'][0] = inputs.spec(BRIDGE)
    dump(BINDING, binding)
    plan = preparation.build_plan(plan_path=PLAN, seed_rule=SEED_RULE, start_graph_rule=START_RULE, reach_geometry_rule=REACH_GEOMETRY_RULE,
        actuation_profile=ACTUATION_PROFILE, motion_authority_profile=MOTION_AUTHORITY_PROFILE, reset_workload_reader_profile=WORKLOAD_PROFILE,
        output_directory='/tmp/mr3_p2a_reach_v66_matrix', run_root=RUN_ROOT, custody_binding=BINDING,
        binary_proof=BRIDGE, preflight='/tmp/mr3_p2a_reach_v66_preflight.json',
        engineering_remaining_seconds=str(remaining), run_prefix='mr3_p2a_reach_v66',
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
    plan['actuation_profile'] = ACTUATION_PROFILE
    plan['motion_authority_profile'] = MOTION_AUTHORITY_PROFILE
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
        'map_output_packing_profile': PACKING_PROFILE, 'reach_geometry_rule': REACH_GEOMETRY_RULE, 'actuation_profile': ACTUATION_PROFILE,
        'motion_authority_profile': MOTION_AUTHORITY_PROFILE,
        'old_failures': 'All prior native and proxy failures retain their original verdicts; this plan grants no retrospective credit.'}
    for name in plan['policy_stages']:
        stage_spec(plan, PLAN, QUALIFICATION, name)
    require(sum(stage['expected_episodes'] for stage in plan['stages']) == 12
            and sum(len(preparation.primitives.roles(stage)) for stage in plan['stages']) == 30,
            'V66 omitted a mandatory native episode or scientific role')
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
