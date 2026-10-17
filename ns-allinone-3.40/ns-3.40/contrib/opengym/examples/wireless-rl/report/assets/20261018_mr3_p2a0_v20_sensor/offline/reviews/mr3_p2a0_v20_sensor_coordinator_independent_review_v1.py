#!/usr/bin/env python3
"""Static read-only final coordinator review; no imported entrypoints or subprocesses."""
import ast
import gzip
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
BASE = Path('/tmp/mr3_p2a0_v20_sensor_coordinator_proposal_v1')
CANON = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v20_sensor'
OUT = Path('/tmp/mr3_p2a0_v20_sensor_coordinator_independent_review_v1.json')
INPUTS = {}

def read(path):
    raw = path.read_bytes()
    item = path.stat()
    value = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw), 'mtime_ns': item.st_mtime_ns}
    if str(path) in INPUTS:
        assert INPUTS[str(path)] == value
    INPUTS[str(path)] = value
    return raw

def doc(path):
    return json.loads(read(path))

def changes(old, new, path=''):
    if type(old) is not type(new):
        return [path]
    if isinstance(old, dict):
        result = []
        for key in sorted(set(old) | set(new)):
            label = path + '/' + key
            result.extend(changes(old[key], new[key], label) if key in old and key in new else [label])
        return result
    if old != new:
        return [path]
    return []

def main():
    parent_path = BASE / 'mr3_p2a0_v20_sensor_run_v1.py'
    pre_path = BASE / 'mr3_p2a0_v20_sensor_preflight_v1.py'
    test_path = BASE / 'mr3_p2a0_v20_sensor_coordinator_tests_v1.py'
    parent = read(parent_path).decode()
    pre = read(pre_path).decode()
    read(test_path)
    manifest = doc(BASE / 'manifest_final_v1.json')
    checks = doc(BASE / 'checks_v3.json')
    draft = doc(BASE / 'predeclared_plan_v20_sensor.json')
    final = doc(CANON / 'predeclared_plan_v20_sensor.json')
    promotion = doc(CANON / 'promotion_v2.json')
    assert INPUTS[str(parent_path)]['sha256'] == '8259eefcdd4906084ca204fa09b6bae897c1d8219796bf594ca86834bb2121d5'
    assert INPUTS[str(pre_path)]['sha256'] == '28da0a640a423ffc16ab122795728ee6454214899883aa04186b6207d99f86eb'
    assert INPUTS[str(test_path)]['sha256'] == 'fd0139288826d6d72d3d529eeb45e4227767d507def5c2b31a87ca8ce8a3695a'
    assert INPUTS[str(BASE / 'manifest_final_v1.json')]['sha256'] == 'e0d07e2204234406c14e139bb2851b7e25fdc7a819bc44043926343d370c944d'
    assert checks['passed'] is True and checks['sources_before'] == checks['sources_after']
    tree = ast.parse(parent)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
    assert not [n for n in calls if isinstance(n.func, ast.Attribute)
                and n.func.attr in {'kill', 'terminate', 'send_signal', 'killpg'}]
    subset = [n.func.attr for n in ast.walk(funcs['verify_profile_subset'])
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
              and isinstance(n.func.value, ast.Name) and n.func.value.id == 'helper']
    assert subset == ['profile_record', 'validate_profile']
    expected_changes = {'/status', '/pending', '/new_source_bindings_pending',
                        '/independent_source_bindings', '/recorder_contract/archived_binary_binding',
                        '/readiness_scope'}
    actual_changes = changes(draft, final)
    assert set(actual_changes) == expected_changes, actual_changes
    assert draft['status'] == 'draft' and draft['pending'] and draft['new_source_bindings_pending']
    assert final['status'] == 'ready' and final['pending'] == [] and final['new_source_bindings_pending'] == []
    assert len(draft['independent_source_bindings']) == 155
    assert final['independent_source_bindings'][:155] == draft['independent_source_bindings']
    assert len(final['independent_source_bindings']) == 160
    appended = final['independent_source_bindings'][155:]
    assert len({r['path'] for r in final['independent_source_bindings']}) == 160
    for item in appended:
        actual = read(ROOT / item['path'])
        assert hashlib.sha256(actual).hexdigest() == item['sha256']
        name = Path(item['path']).name
        source = (BASE / name if name.endswith('.py') else
                  Path('/tmp/mr3_p2a0_v20_sensor_recorder_proposal_v1') / name)
        assert actual == read(source)
    archived = final['recorder_contract']['archived_binary_binding']
    encoded = read(ROOT / archived['path'])
    assert hashlib.sha256(encoded).hexdigest() == archived['sha256']
    binary = read(Path(final['recorder_contract']['executable_path']))
    assert gzip.decompress(encoded) == binary
    assert hashlib.sha256(binary).hexdigest() == final['recorder_contract']['executable_sha256']
    assert len(binary) == final['recorder_contract']['executable_bytes']
    stage = final['stages'][0]
    assert len(final['stages']) == 1 and stage['steps'] == 4 and stage['workers'] == 1
    assert stage['saved_api_records_max'] == 5 and stage['domain'] == 170 and stage['port'] == 13451
    assert all(flag not in stage['command'] for flag in
               ('--preparation-motion-probe', '--preparation-probe-version', '--preparation-parameter-review'))
    assert final['e61c_consumer']['status'] == 'SKIP'
    assert final['budget']['max_native_runs'] == 1 and final['budget']['max_native_launcher_wall_seconds'] == 900.
    # Accounting display arithmetic has a binary64 ULP; compare its declared nanosecond values.
    assert round(final['budget']['previous_v18_v19_charged_wall_seconds'] * 1e9) + 900_000_000_000 == round(
        final['budget']['max_cumulative_after_this_ceiling_seconds'] * 1e9)
    result = {
      'schema': 'mr3-v20-sensor-coordinator-independent-review-v1', 'review_complete': True,
      'blocking_issues': [], 'native_admission_by_this_review': False,
      'scope': 'Static source/actual promoted bytes and existing CPU receipts only. No SDK/DDS/native/formal, entrypoint or fake subprocess rerun.',
      'functions_reviewed': {name: {'line': funcs[name].lineno, 'end': funcs[name].end_lineno}
        for name in ('wait_ready', 'verify_profile_subset', 'verify_actual_workload', 'execute_capture', 'main')},
      'findings': [
        'Preflight requires ready and cleared pending lists, exact Git-frozen plan/bindings and clean pushed HEAD. Runner requires matching actual source-preflight receipt and rechecks source/binary before and after execution.',
        'One exclusive attempt lock plus absent run/config/output/ready/stop/execution paths prevents retry/overwrite; only one recorder and one ordinary benchmark child are launched.',
        'Original ordinary benchmark requests4steps, no V6/preparation/parameter-review flags. Actual reset and zero-to-four returned steps/at most5API are bound to typed termination/epoch/summary counts.',
        'A real early protocol end preserves original benchmark passedFalse/CLI1/reason. Collection process completion is not benchmark task success or a replacement matrix slot.',
        'Exact recorder PID/config/source ready precedes benchmark. Parent naturally waits/reaps benchmark, then exclusively writes marker, then naturally waits/reaps recorder. Pre-benchmark failure does not invent a closed marker. No signal/kill/replacement native call is present.',
        'Native wall starts immediately before benchmark launch and includes startup/close.900seconds is checked/charged after natural closure, not signal-enforced. Recorder own1000wallguard is separate and declared.',
        'Event Lock serializes parent/witness ledger writes; owned witness thread is joined before final ledger close. Read-only witness readiness polling is not another native attempt.',
        'Original2516 is genuinely called on4step output; its scientific overallFalse remains permitted and recorded, while exactly one episode without consumer/episode error and original strict closureTrue are required.',
        'Exact e61c sourceSHA is checked, then only profile_record and validate_profile verify actual first-boundary ledger/runtime binding. Full32step e61c CLI remains SKIP, not a narrowed PASS.',
        'Measurement counts, parameter states and absent aliases/sources remain descriptive and cannot be converted from process completion into occupancy causality or physical-repair credit.'
      ],
      'canonical_promotion': {'draft_plan_sha256': INPUTS[str(BASE / 'predeclared_plan_v20_sensor.json')]['sha256'],
        'final_plan_sha256': INPUTS[str(CANON / 'predeclared_plan_v20_sensor.json')]['sha256'],
        'changed_paths_exact': actual_changes, 'old155_bindings_unchanged': True,
        'new5_bindings_match_sealed_sources': True, 'encoded_binary_sha256': archived['sha256'],
        'actual_binary_sha256': hashlib.sha256(binary).hexdigest(),
        'readiness_scope': final['readiness_scope'],
        'promotion_record': promotion},
      'author_existing_checks': {'path': str(BASE / 'checks_v3.json'),
        'sha256': INPUTS[str(BASE / 'checks_v3.json')]['sha256'], 'reported_related_CPU': 14,
        'reviewer_reran': False, 'scope': checks['scope']},
      'initial_review_diagnostics': [
        'First file read tried predeclared_plan_v20.json; corrected to actual predeclared_plan_v20_sensor.json. No file changed.',
        'First reviewer assertion compared binary64 printed cumulative budgets for exact equality:3389.3860735194758 versus3389.386073519476. Corrected reviewer accounting check uses their declared integer nanoseconds. No production budget or math gate changed.'
      ],
      'limitations': [
        'Actual new clean pushed exact40 preflight has not been run by reviewer; final ready-source scope does not grant native admission itself.',
        'If the benchmark does not exit, parent waits/reaps without signals; original finite worker guards remain responsible. Actual excess wall is FAIL and not a retry.',
        'Source identities and interfaces were checked, not actual future native response, sensor availability or root cause.'
      ],
      'inputs': INPUTS, 'execution': {'argv': sys.argv}, 'canonical_edits': False, 'writers': 'STOP'}
    for name, expected in INPUTS.items():
        path = Path(name)
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected['sha256']
        assert path.stat().st_mtime_ns == expected['mtime_ns']
    result['inputs_unchanged_during_review'] = True
    with OUT.open('x') as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'path': str(OUT), 'sha256': hashlib.sha256(OUT.read_bytes()).hexdigest(),
                      'bytes': OUT.stat().st_size, 'final_plan_sha256': result['canonical_promotion']['final_plan_sha256']}))

if __name__ == '__main__':
    main()
