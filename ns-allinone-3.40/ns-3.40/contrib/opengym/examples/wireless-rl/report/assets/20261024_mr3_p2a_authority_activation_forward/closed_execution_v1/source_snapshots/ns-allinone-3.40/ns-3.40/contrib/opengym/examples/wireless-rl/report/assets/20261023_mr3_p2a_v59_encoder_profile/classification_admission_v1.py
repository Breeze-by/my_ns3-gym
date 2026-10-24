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
                  'execute_chain_v1.py', 'readiness_v1.py', 'classification_admission_v1.py')
OLD_EXTERNAL = A.parent / '20261023_mr3_p2a_v50_qualification/external_absence_v1.py'
OLD_EXTERNAL_SHA256 = '61dffad560007e88f2c8818bed9f1adf4630568bcb859732446d107b1a7e2e2f'
TEST = A / 'test_activity_resource_entry_v1.py'
SPEC = A / 'admission_cpu_spec_v1.json'
WAIT = A / 'checks/admission_cpu_v1/actual_wait.json'
RECOVERY = A / 'checks/admission_cpu_v1_source_recovery.json'
JUNIT = A / 'checks/admission_cpu_v1/pytest.xml'
REQUIRED_TESTS = (
    'test_prior_carry_and_one_resource_are_accepted',
    'test_forged_prior_or_parent_fee_is_rejected',
    'test_all_four_real_entries_accept_only_to_pre_model_boundary',
    'test_all_four_real_entries_reject_overbudget_before_effects',
    'test_conflicting_plan_budget_is_rejected',
    'test_preflight_really_calls_both_reset_reader_readiness_and_keeps_receipt',
    'test_current_python_classification_includes_untracked',
    'test_all_four_real_module_help')
HELP_MODULES = ('prepare_plan_v1', 'preflight_v1', 'plan_check_v1', 'execute_chain_v1')


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
    """Bind the genuinely new small CPU group; never borrow the earlier23 suite."""
    historical = _historical(inputs, verify_wait)
    spec = decode(inputs.read(SPEC))
    required = {str(path.relative_to(ROOT)) for path in
        [*(A/name for name in REQUIRED_NAMES), OLD_EXTERNAL, TEST]}
    require(set(spec) == {'schema', 'actual_argv', 'required_test_names',
                         'expected_source_hashes', 'pytest_junit'}
        and spec['schema'] == 'mr3-v59-admission-cpu-spec-v1'
        and spec['actual_argv'] == [PYTHON, '-B', '-m', 'pytest', '-q', str(TEST),
                                    '--junitxml', str(JUNIT)]
        and spec['required_test_names'] == list(REQUIRED_TESTS)
        and spec['pytest_junit'] == str(JUNIT), 'admission CPU exact specification differs')
    hashes = spec['expected_source_hashes']
    require(type(hashes) is dict and set(hashes) == required and all(
        type(value) is str and re.fullmatch('[0-9a-f]{64}', value) for value in hashes.values()),
        'admission source SHA template is incomplete or contains unknown paths')
    require(hashes[str(OLD_EXTERNAL.relative_to(ROOT))] == OLD_EXTERNAL_SHA256,
            'reused original absence source is not the unchanged A50 bytes')
    value = decode(inputs.read(WAIT))
    verify_wait(value)
    require(value['actual_argv'] == spec['actual_argv']
        and value['source_before'] == value['source_after'], 'admission CPU argv/source differs')
    inputs.bound(value['console'])
    recovery = decode(inputs.read(RECOVERY))
    before = {row['path']:row for row in value['source_before']}
    recovered = {row['path']:row for row in recovery['sources']}
    require(len(before) == len(value['source_before']) and len(recovered) == len(recovery['sources']),
            'duplicate actual CPU/recovery source registration')
    tested = []
    # The spec cannot self-hash; require its exact bytes in the actual CPU
    # source_before+recovery in addition to all explicitly expected SHA paths.
    for relative in sorted(required | {str(SPEC.relative_to(ROOT))}):
        path = ROOT / relative
        raw = inputs.read(path)
        digest, expected = hashlib.sha256(raw).hexdigest(), before[str(path)]
        require(digest == expected['sha256'] and len(raw) == expected['bytes']
            and recovered[relative]['sha256'] == digest and recovered[relative]['bytes'] == len(raw)
            and (relative not in hashes or hashes[relative] == digest),
            'new admission CPU current/spec/wait/recovery source differs: '+relative)
        tested.append(inputs.spec(path))
    xml_raw = inputs.read(JUNIT)
    document = ET.fromstring(xml_raw)
    cases = list(document.iter('testcase'))
    names = [case.get('name', '') for case in cases]
    identities = [(case.get('classname'), case.get('name')) for case in cases]
    require(len(cases) == 11 and len(set(identities)) == len(cases)
        and all(case.get('classname') and not any(case.find(tag) is not None
            for tag in ('failure', 'error', 'skipped')) for case in cases),
        'admission fixtures did not all execute with zero failures/errors/skips')
    require({name.split('[',1)[0] for name in names} == set(REQUIRED_TESTS)
        and all(names.count(name) == 1 for name in REQUIRED_TESTS[:-1])
        and {name for name in names if name.startswith(REQUIRED_TESTS[-1]+'[')} == {
            REQUIRED_TESTS[-1]+'['+module+']' for module in HELP_MODULES},
        'admission JUnit fixture or four actual module-help identities differ')
    for suite in document.iter('testsuite'):
        require(all(suite.get(key) == '0' for key in ('failures','errors','skipped')),
                'admission JUnit suite contains failure/error/skip')
    return {'schema':'mr3-v59-classification-regression-admission-v1', 'passed':True,
        'historical_v50_classification':historical,
        'actual_wait':inputs.spec(WAIT), 'source_recovery':inputs.spec(RECOVERY),
        'actual_spec':inputs.spec(SPEC), 'fixture_results':inputs.spec(JUNIT),
        'fixture_case_count':11, 'fixture_names':names,
        'tested_current_admission_sources':tested,
        'original_absence_source':inputs.spec(OLD_EXTERNAL),
        'original_absence_wrapper_schema':'mr3-v45-external-absence-wrapper-v1',
        'original_absence_source_unchanged':True,
        'four_new_entries_imported_with_real_module_help':True,
        'native_main_paths_executed':False, 'model_or_world_started':False,
        'fresh23_receipt_claimed_to_cover_new_activity_scripts':False,
        'world_or_native_credit':False}
