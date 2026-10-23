"""Prepare fixed A62 source/12-ELF scope; never launch native work.

Default writes a pending scope. --admit needs the completed canonical 23-case
CPU proof and its real wait/JUnit/source recovery. It still needs a subsequent
clean pushed execution freeze enforced by the existing parent/bootstrap.
"""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261024_mr3_p2a_v62_process_profile'
SELF = A / 'prepare_scope_v1.py'
OLD = W / 'report/assets/20261023_mr3_p2a_v60_reader_registration'
LEDGER = W / 'report/assets/20261024_mr3_p2a_v61_cancel_forensics/closure_ledger_v1.json'
METADATA_HELPER = LEDGER.parent / 'run_cancel_forensics_v1.py'
CPU = A / 'checks/canonical_cpu_v1'
PROFILE = 'mr3-p2a-v62-open101-8step-cprofile-v1'
RUN = Path('/tmp/mr3_p2a_v62_open101_8step_profile_v1')
LEARNER = Path('/home/zhuyulab/miniconda3/envs/ns3gym/bin/python')
STABLE = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stamp(value):
    return tuple(getattr(value, key) for key in STABLE)


def proof(path):
    path = Path(path)
    require(path.is_absolute() and path == path.resolve(strict=True), 'noncanonical source/ELF path: ' + str(path))
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= 64 * 1024**2, 'nonregular/oversize bound file')
    digest, size = hashlib.sha256(), 0
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        require(stamp(os.fstat(stream.fileno())) == stamp(before), 'source identity differs before read')
        for chunk in iter(lambda: stream.read(1024**2), b''):
            digest.update(chunk); size += len(chunk)
        require(stamp(os.fstat(stream.fileno())) == stamp(before), 'source changed during read')
    require(stamp(path.lstat()) == stamp(before) and size == before.st_size, 'source stat/size drift')
    return {'path': str(path), 'bytes': size, 'sha256': digest.hexdigest()}


def read(path):
    before = proof(path)
    raw = path.read_bytes()
    require(len(raw) == before['bytes'] and hashlib.sha256(raw).hexdigest() == before['sha256'], 'metadata changed after pin')
    return json.loads(raw), before


def same_bytes(left, right):
    return (left['bytes'], left['sha256']) == (right['bytes'], right['sha256'])


def repo_path(value):
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    require(path.is_relative_to(ROOT) and '..' not in path.parts, 'source escapes workspace')
    return path


def junit_counts(path):
    tree = ET.fromstring(path.read_bytes())
    rows = tree.findall('.//testcase')
    return {'tests': len(rows), 'failures': sum(bool(r.findall('failure')) for r in rows),
            'errors': sum(bool(r.findall('error')) for r in rows),
            'skipped': sum(bool(r.findall('skipped')) for r in rows)}


def canonical_cpu(runtime_sources):
    value, value_ref = read(CPU / 'proof_v1.json')
    require(value.get('schema') == 'mr3-v62-fixed-profile-canonical-cpu-proof-v1'
            and value.get('passed') is True and type(value.get('actual_returncode')) is int
            and value['actual_returncode'] == 0
            and value.get('source_before_after_current_and_snapshots_stable') is True
            and value.get('native_executed') is False
            and value.get('scientific_qualification') is False
            and value.get('capacity_qualified') is False, 'canonical CPU proof is not actually passed in its CPU-only scope')
    tool = value['actual_tool_wait']
    require(tool.get('actual_waited') is True and tool.get('actual_reap_observed') is True
            and type(tool.get('actual_returncode_observed')) is int and tool['actual_returncode_observed'] == 0,
            'canonical CPU root tool was not really reaped0')
    actual_path = Path(tool['actual_wait_path'])
    require(actual_path == CPU / 'actual/actual_wait.json', 'unexpected canonical CPU actual-wait path')
    actual, actual_ref = read(actual_path)
    require(actual.get('schema') == 'mr3-reach-outer-actual-wait-v1'
            and actual.get('scope') == 'cpu' and actual.get('passed') is True
            and actual.get('actual_waited') is True and type(actual.get('actual_returncode')) is int
            and actual['actual_returncode'] == 0 and actual.get('errors') == []
            and actual.get('source_unchanged') is True and actual['source_before'] == actual['source_after'],
            'canonical actual CPU source/wait receipt differs')
    expected_counts = {'tests': 23, 'failures': 0, 'errors': 0, 'skipped': 0}
    require(value['JUnit_counts'] == expected_counts
            and junit_counts(CPU / 'actual/pytest.xml') == expected_counts,
            'canonical 23-case JUnit result differs')
    require(value['pytest_argv'] == actual['actual_argv'], 'canonical test command is not the actually waited command')
    tests = {str(p) for p in A.glob('test_*.py')}
    require(len(tests) == 6 and tests <= set(value['pytest_argv']), 'actual CPU argv does not select all six canonical test files')
    recover_path = Path(value['source_recovery'])
    require(recover_path == CPU / 'source_recovery_v1.json', 'unexpected canonical source recovery path')
    recovered, recovery_ref = read(recover_path)
    recovery_rows = {str(Path(r['path']).resolve(strict=True)): r for r in recovered['sources']}
    waited = {r['path']: r for r in actual['source_before']}
    declared = {r['path']: r for r in value['source_bindings']}
    require(set(waited) == set(declared)
            and all(same_bytes(waited[p], declared[p]) for p in waited), 'proof source table differs from actual wait')
    checked = []
    # Only matching runtime/canonical sources are current CPU credit here.
    # Third-party framework inputs remain in the original CPU proof/recovery;
    # they are not promoted to an all-mapped-library runtime requirement.
    for row in runtime_sources:
        path = Path(row['path'])
        if str(path) not in waited:
            continue
        require(same_bytes(row, waited[str(path)]), 'canonical CPU-covered source differs from installed bytes')
        recovery = recovery_rows.get(str(path))
        require(recovery is not None and same_bytes(row, recovery), 'CPU source recovery binding missing')
        if path.parent == A:
            require(recovery.get('kind') == 'uncommitted_canonical_snapshot' and 'snapshot' in recovery,
                    'new canonical source is not explicitly recovered from its CPU snapshot')
            snapshot = Path(recovery['snapshot'])
            require(snapshot.is_relative_to(CPU / 'source_snapshots') and same_bytes(row, proof(snapshot)),
                    'new canonical CPU snapshot bytes differ')
        checked.append(str(path))
    required = {str(p) for p in A.glob('*.py') if p != SELF}
    required.add(str(A / 'base_source_pins_v1.json'))
    require(required <= set(checked), 'canonical execution/test files lack actual canonical CPU byte credit')
    return {'proof': value_ref, 'actual_wait': actual_ref,
            'junit': proof(CPU / 'actual/pytest.xml'), 'source_recovery': recovery_ref,
            'JUnit_counts': expected_counts, 'current_runtime_sources_with_CPU_credit': checked,
            'actual_CPU_source_binding_count': len(waited),
            'source_preparation_kind': 'canonical uncommitted byte snapshots; not a new Git execution freeze',
            'scope_producer_has_no_inherited_CPU_test_credit': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--admit', action='store_true', help='require the completed canonical CPU before writing final scope')
    args = parser.parse_args(argv)
    require(Path(__file__).resolve() == SELF, 'install the exact canonical scope producer before use')
    require(Path.cwd() == W, 'run from wireless-rl')
    output = A / ('scope_v1.json' if args.admit else 'scope_prepared_v1.json')
    require(not output.exists(), 'exclusive output exists; preserve the previous preparation')
    previous, previous_ref = read(LEDGER)
    require((previous_ref['bytes'], previous_ref['sha256']) == (6554, '6e9e808a36533cd08ce1986a98c9a3065bbf769fe78ddf340f08539c898f8d53')
            and previous['passed'] is True and previous['P2A_complete'] is False,
            'actual previous V61 ledger differs')
    used, ceiling = Decimal(previous['engineering_cumulative_seconds']), Decimal(previous['engineering_ceiling_seconds'])
    require(used == Decimal('108886.5066566616018') and ceiling == 150000
            and ceiling-used == Decimal('41113.4933433383982') and ceiling-used >= 1800, 'continuous reservation is not funded')
    old_plan, old_plan_ref = read(OLD / 'plan_v1.json')
    binding, binding_ref = read(OLD / 'native_custody_binding_v1.json')
    bridge, bridge_ref = read(OLD / 'native_build_bridge_v1.json')
    require(binding['actuation_profile'] == bridge['actuation_profile'] == 'initial-zero-encoder-hold-v1'
            and bridge['passed'] is True, 'original actual-build identity profile differs')
    manifest_path = repo_path(bridge['manifest']['path'])
    manifest, manifest_ref = read(manifest_path)
    require(same_bytes(manifest_ref, bridge['manifest']) and manifest['passed'] is True
            and manifest['new_actual_build_executed'] is True
            and manifest['existing_v15_no_new_build_credit_reused'] is False
            and manifest['source_before'] == manifest['source_after'] == manifest['sources']
            and len(manifest['sources']) == 20, 'historical actual build provenance differs')
    build_sources, historical_tools = [], []
    for row in manifest['sources']:
        path = Path(row['path'])
        if path.is_relative_to(ROOT):
            require(proof(path) == row, 'reused ROOT compiled/build source changed')
            build_sources.append(path)
        else:
            historical_tools.append(row)  # History only: deliberately never open these four tools.
    require(len(build_sources) == 16 and len(historical_tools) == 4, 'fixed old build16+4 scope differs')
    sys.path.insert(0, str(W))
    from mr3_learning import reach_preparation
    paths = {repo_path(p) for p in reach_preparation.source_inventory(ROOT)}
    paths.update(repo_path(p) for p in old_plan['source_bindings'])  # Names only; never borrow old hashes as new source credit.
    paths.update(A.glob('*.py'))
    paths.update(build_sources)
    paths.update((A/'base_source_pins_v1.json', LEDGER, METADATA_HELPER,
                  OLD/'plan_v1.json', OLD/'native_custody_binding_v1.json',
                  OLD/'native_build_bridge_v1.json', manifest_path))
    build_refs = {}
    for key in ('actual_wait', 'compiler_flags_archive', 'source_derivation'):
        p = repo_path(bridge[key]['path'])
        actual = proof(p)
        require(same_bytes(actual, bridge[key]), 'historical build receipt bytes differ: ' + key)
        paths.add(p); build_refs[key] = actual
    libraries, aliases = {}, []
    require(len(binding['binaries']) == len(old_plan['library_bindings']) == 10, 'original native ELF registry differs')
    for name, old in sorted(binding['binaries'].items()):
        literal = Path(old['path'])
        resolved = literal.resolve(strict=True)
        require(str(resolved) == old['resolved_path'], 'native alias resolved target differs from original actual identity')
        actual = proof(resolved)
        require(same_bytes(actual, old) and old_plan['library_bindings'][str(literal)] == actual['sha256'], 'native ELF changed since actual old build')
        libraries[str(resolved)] = actual
        aliases.append({'role': name, 'literal_path': str(literal), 'resolved_path_at_preparation': str(resolved),
                        'literal_lstat': list(stamp(literal.lstat())), 'literal_readlink': os.readlink(literal) if literal.is_symlink() else None})
    for name, literal in (('system_python', Path('/usr/bin/python3')), ('learner_python', LEARNER)):
        resolved = literal.resolve(strict=True)
        libraries[str(resolved)] = proof(resolved)
        aliases.append({'role': name, 'literal_path': str(literal), 'resolved_path_at_preparation': str(resolved),
                        'literal_lstat': list(stamp(literal.lstat())), 'literal_readlink': os.readlink(literal) if literal.is_symlink() else None})
    require(len(libraries) == 12, 'expected exactly ten native plus two distinct resolved interpreter ELFs')
    source_rows = [proof(p) for p in sorted(paths)]
    cpu = {'status': 'PENDING_CANONICAL_ACTUAL_CPU', 'canonical_execution_credit': False}
    if args.admit:
        cpu = canonical_cpu(source_rows)
        cpu['canonical_execution_credit'] = True
        paths.update(Path(cpu[key]['path']) for key in ('proof', 'actual_wait', 'junit', 'source_recovery'))
        source_rows = [proof(p) for p in sorted(paths)]
    scope = {'schema': 'mr3-v62-fixed-process-profile-scope-v1', 'admitted': bool(args.admit),
        'diagnostic_profile': PROFILE, 'run_root': str(RUN),
        'robots_per_environment': 3, 'fixed_scene': 'open', 'fixed_seed': 101,
        'ordinary_legal_probe_decisions': 8, 'training_eligible': False,
        'resource': {'parent_cap_seconds': 1800, 'native_allocation_seconds': 1500,
                     'close_reserve_seconds': 120, 'review_max_seconds': 300},
        'resource_semantics': 'cooperative native1500 includes close120; reader admitted at most min(240, remaining-60); full actual parent1800 is a post-hoc cost/FAIL gate, never hard realtime',
        'previous_accounting': previous_ref, 'engineering_entry_seconds': str(used),
        'engineering_ceiling_seconds': str(ceiling), 'engineering_remaining_seconds_at_entry': str(ceiling-used),
        'engineering_reservation_seconds': '1800', 'numeric_user_approval_claimed': False,
        'continuous_user_delegation_preserved': True,
        'expected_launcher_argv_template': [str(LEARNER), '-B', '-m',
            'report.assets.20261024_mr3_p2a_v62_process_profile.fixed_profile_launcher_v1', '--freeze', '__EXECUTION_FREEZE__'],
        'source_bindings': source_rows, 'library_bindings': [libraries[k] for k in sorted(libraries)],
        'library_alias_observations_at_preparation': aliases,
        'library_scope': 'ten unchanged actual native ELFs and two resolved Python ELFs; no342 all-mapped-library expansion',
        'old_plan_names_current_bytes_only': old_plan_ref,
        'old_native_binding': binding_ref,
        'old_build_reuse': {'bridge': bridge_ref, 'manifest': manifest_ref, 'receipt_references': build_refs,
            'current_ROOT_build_source_count': 16, 'current_ROOT_build_sources': [proof(p) for p in build_sources],
            'historical_all20_input_bindings': manifest['sources'],
            'four_external_tool_bindings_historical_only': historical_tools,
            'four_external_tools_opened_for_current_admission': False,
            'parent_before_after_claims_only16_ROOT_inputs_plus12_resolved_ELFs': True,
            'new_build_executed_for_A62': False, 'new_native_scientific_build_credit': False},
        'canonical_cpu_evidence': cpu,
        'prepared_at_git_HEAD_not_execution_freeze': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        'requires_new_clean_pushed_execution_freeze': True,
        'scientific_qualification': False, 'capacity_qualified': False,
        'optimizer_updates': 0, 'pilot_added_seconds': '0', 'validation_added_seconds': '0',
        'original_pilot_final_totals_preserved': True, 'automatic_pilot_final_entry_allowed': False,
        'P2A_complete': False, 'native_or_old_activity_executed_by_preparation': False}
    require([proof(Path(row['path'])) for row in source_rows] == source_rows
            and [proof(Path(row['path'])) for row in scope['library_bindings']] == scope['library_bindings'], 'sources/ELFs changed during preparation')
    with output.open('x') as stream:
        json.dump(scope, stream, indent=2, allow_nan=False)
        stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    print(json.dumps({'output': str(output), 'admitted': scope['admitted'],
        'source_bindings': len(source_rows), 'library_bindings': len(libraries),
        'native_executed': False, 'capacity_qualified': False}))


if __name__ == '__main__':
    main()
