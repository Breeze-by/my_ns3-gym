"""Bind successful artificial classification checks to their exact current sources."""
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

A = Path(__file__).resolve().parent
ROOT = Path("/home/zhuyulab/ns3-workspace")
PYTHON = "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python"

def _historical(inputs, verify_wait):
    # Historical A50 classification credit remains exactly scoped to old files.
    A = Path(__file__).resolve().parent.parent / "20261023_mr3_p2a_v50_qualification"
    wait_path = A / "checks/classification_cpu_v1/actual_wait.json"
    recovery_path = A / "checks/classification_cpu_v1_source_recovery.json"
    import json
    value = json.loads(inputs.read(wait_path))
    verify_wait(value)
    if value["actual_argv"] != [PYTHON,"-B","-m","pytest","-q",str(A/"test_preparation_classification_v1.py")]:
        raise ValueError("classification receipt has a different actual command")
    inputs.bound(value["console"])
    recovery = json.loads(inputs.read(recovery_path))
    original = {row["path"]:row for row in recovery["sources"]}
    before = {row["path"]:row for row in value["source_before"]}
    required = ("prepare_plan_v1.py", "preflight_v1.py", "cpu_driver_v1.py",
                "test_preparation_classification_v1.py", "classification_admission_v1.py",
                "execute_chain_v1.py")
    tested = []
    for name in required:
        path = A / name
        expected = before[str(path)]
        raw = inputs.read(path)
        if hashlib.sha256(raw).hexdigest() != expected["sha256"] or len(raw) != expected["bytes"]:
            raise ValueError("classification-tested admission source differs: " + name)
        if original[str(path.relative_to(ROOT))]["sha256"] != expected["sha256"]:
            raise ValueError("classification source recovery differs: " + name)
        tested.append(inputs.spec(path))
    return {"schema":"mr3-v50-classification-regression-admission-v1", "passed":True,
            "actual_wait":inputs.spec(wait_path), "source_recovery":inputs.spec(recovery_path),
            "tested_current_admission_sources":tested, "world_or_native_credit":False}



REQUIRED_NAMES = ('prepare_plan_v1.py', 'preflight_v1.py', 'plan_check_v1.py',
                  'run_matrix_v1.py', 'bootstrap_v1.py', 'readiness_v1.py',
                  'run_admission_cpu_v1.py', 'classification_admission_v1.py')
OLD_EXTERNAL = A.parent / '20261023_mr3_p2a_v50_qualification/external_absence_v1.py'
OLD_EXTERNAL_SHA256 = '61dffad560007e88f2c8818bed9f1adf4630568bcb859732446d107b1a7e2e2f'
TEST = A / 'test_activity_resource_entry_v1.py'
MATRIX_TEST = A / 'test_matrix_parent_v1.py'
TEST_FILES = (TEST, MATRIX_TEST)
CONFIG_FILES = (A/'resource_v1.json', A/'scope_v1.json', A/'authorization_v1.json',
    A.parent/'20261024_mr3_p2a_v70_probe_v3_stimulus_description/closure_ledger_v1.json')
EXPECTED_CASE_COUNT = 33
SPEC = A / 'admission_cpu_spec_v1.json'
WAIT = A / 'checks/admission_cpu_v1/actual_wait.json'
RECOVERY = A / 'checks/admission_cpu_v1_source_recovery.json'
JUNIT = A / 'checks/admission_cpu_v1/pytest.xml'
REQUIRED_TESTS = ('test_new_block_keeps_all_actual_past_fees_and_original_policy_totals', 'test_forged_fee_reap_source_or_nonowned_claim_rejected_even_with_updated_toy_pin', 'test_old_unfunded_balance_cannot_be_presented_as_complete_new_reservation', 'test_missing_new_profile_weakened_workload_and_automatic_policy_entry_rejected', 'test_numeric_approval_cannot_be_invented_from_continuation', 'test_untracked_python_test_is_classified_before_git_add', 'test_actual_entry_module_help_does_not_start_native_or_create_parent_state', 'test_real_child_rc7_and_exact_env', 'test_identity_observation_failure_still_realwait', 'test_wait_interruption_does_not_abandon_child', 'test_phase_actual_source_wait_and_no_double_fee', 'test_phase_bad_receipt_preserves_true_child_rc', 'test_extra_current_assets_cannot_override_plan_source_pin', 'test_bad_bootstrap_identity_leaves_fee_unknown', 'test_dependency_failure_settles_known_parent_from_real_ledger', 'test_unadmitted_scope_earlyrefusal_and_postsource_attempt', 'test_only_matrix_stages_and_postsource_failure_fails', 'test_noncanonical_parent_refuses_before_import_or_phase', 'test_bootstrap_exec_failure_records_real_interval_and_ancestry')
HELP_MODULES = ('prepare_plan_v1', 'preflight_v1', 'plan_check_v1', 'readiness_v1', 'run_matrix_v1', 'bootstrap_v1')


def current_python_sources(root=ROOT):
    """Stable classification includes current untracked Python source/tests."""
    root = Path(root)
    ros = root / 'ros2_ws/ros2-multi-robot-automap'
    learner = root / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning'
    pure = ros / 'src/multi_robot_exploration/multi_robot_exploration'
    runtime = {str(p.relative_to(root)) for directory in (pure, learner) for p in directory.glob('*.py')}
    tests = {str(p.relative_to(root)) for directory in (
        ros / 'src/multi_robot_exploration/test', learner / 'tests') for p in directory.glob('test_*.py')}
    return runtime, tests


def require(value, message):
    if not value:
        raise ValueError(message)


def decode(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'duplicate admission JSON member')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=pairs,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite admission JSON')))


def verify(inputs, verify_wait):
    """Require all predeclared new-entry cases and the exact actual CPU wait."""
    historical = _historical(inputs, verify_wait)
    spec = decode(inputs.read(SPEC))
    required = {str(path.relative_to(ROOT)) for path in
        [*(A/name for name in REQUIRED_NAMES), OLD_EXTERNAL, *TEST_FILES, *CONFIG_FILES]}
    expected_argv = [PYTHON, '-B', '-m', 'pytest', '-q', *map(str,TEST_FILES), '--junitxml', str(JUNIT)]
    require(set(spec) == {'schema','actual_argv','required_test_names','expected_testcase_names',
                         'expected_source_hashes','pytest_junit'}
            and spec['schema'] == 'mr3-v71-admission-cpu-spec-v1'
            and spec['actual_argv'] == expected_argv and spec['pytest_junit'] == str(JUNIT)
            and spec['required_test_names'] == list(REQUIRED_TESTS),
            'new admission CPU exact specification differs')
    declared_names = spec['expected_testcase_names']
    require(type(declared_names) is list and len(declared_names) == EXPECTED_CASE_COUNT
            and all(type(name) is str and name for name in declared_names)
            and len(set(declared_names)) == EXPECTED_CASE_COUNT
            and {name.split('[',1)[0] for name in declared_names} == set(REQUIRED_TESTS),
            'pre-execution collected new CPU identities differ')
    hashes=spec['expected_source_hashes']
    require(type(hashes) is dict and set(hashes) == required and all(
        type(value) is str and re.fullmatch('[0-9a-f]{64}',value) for value in hashes.values()),
        'new admission source SHA scope is incomplete')
    require(hashes[str(OLD_EXTERNAL.relative_to(ROOT))] == OLD_EXTERNAL_SHA256,
            'reused external absence source differs')
    value=decode(inputs.read(WAIT));verify_wait(value)
    require(value['actual_argv'] == expected_argv and value['source_before'] == value['source_after'],
            'new admission CPU actual command/source differs')
    inputs.bound(value['console'])
    recovery=decode(inputs.read(RECOVERY))
    before={row['path']:row for row in value['source_before']}
    recovered={row['path']:row for row in recovery['sources']}
    require(len(before) == len(value['source_before']) and len(recovered) == len(recovery['sources']),
            'duplicate CPU/recovery source identity')
    tested=[]
    for relative in sorted(required | {str(SPEC.relative_to(ROOT))}):
        path=ROOT/relative;raw=inputs.read(path)
        require(str(path) in before and relative in recovered,'admission source not actually observed')
        digest=hashlib.sha256(raw).hexdigest();observed=before[str(path)]
        require(digest == observed['sha256'] and len(raw) == observed['bytes']
                and recovered[relative]['sha256'] == digest and recovered[relative]['bytes'] == len(raw)
                and (relative not in hashes or hashes[relative] == digest),
                'admission actual/current/recovery source differs: '+relative)
        tested.append(inputs.spec(path))
    document=ET.fromstring(inputs.read(JUNIT));cases=list(document.iter('testcase'))
    names=[case.get('name','') for case in cases]
    identities=[(case.get('classname'),case.get('name')) for case in cases]
    require(len(cases) == EXPECTED_CASE_COUNT and len(set(identities)) == len(cases)
            and sorted(names) == sorted(declared_names)
            and all(case.get('classname') and not any(case.find(tag) is not None
                    for tag in ('failure','error','skipped')) for case in cases),
            'new entry cases did not all actually execute without failure/error/skip')
    for suite in document.iter('testsuite'):
        require(all(suite.get(key) == '0' for key in ('failures','errors','skipped')),
                'new admission JUnit suite failed')
    return {'schema':'mr3-v71-classification-regression-admission-v1','passed':True,
        'historical_v50_classification':historical,'actual_wait':inputs.spec(WAIT),
        'source_recovery':inputs.spec(RECOVERY),'actual_spec':inputs.spec(SPEC),
        'fixture_results':inputs.spec(JUNIT),'fixture_case_count':len(cases),'fixture_names':names,
        'tested_current_admission_sources':tested,'original_absence_source':inputs.spec(OLD_EXTERNAL),
        'original_absence_source_unchanged':True,'actual_module_help_count':len(HELP_MODULES),
        'native_main_paths_executed':False,'model_or_world_started':False,
        'world_or_native_credit':False}
