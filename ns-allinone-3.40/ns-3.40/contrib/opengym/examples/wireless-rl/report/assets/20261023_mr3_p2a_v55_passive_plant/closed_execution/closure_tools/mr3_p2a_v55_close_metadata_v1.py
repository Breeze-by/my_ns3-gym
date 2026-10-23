"""Post-reap V55 source/process/accounting and opaque byte archive only."""
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261023_mr3_p2a_v55_passive_plant'
PREFIX = Path('/tmp/mr3_p2a_v55_driver_v1')
FREEZE = '63f5cc107161202a6d610f5fe39f3434b0d7eed9'
OLD = '1fa55bc56d5bb9e230d4b397f962d83b1604b278'
COPIER = W / 'report/assets/20261022_mr3_p2a_v45_preparation_classification/collect_closed_v1.py'
COPIER_SHA = '63d52ce389b7d61fa67f5080fa556b1f32e47b79e389800f9de55e97c40abf06'
ENTRY, CEILING = Decimal('90357.3610697996018'), Decimal('120000')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def proof(path):
    path = Path(path); before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'regular source required: ' + str(path))
    raw = path.read_bytes(); after = path.lstat()
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    require(all(getattr(before, k) == getattr(after, k) for k in keys), 'metadata/source changed')
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def bound(row):
    require(proof(row['path']) == row, 'critical reference SHA/bytes/path differs')


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def same(a, b):
    keys = ('pid', 'parent', 'group', 'session', 'start_ticks')
    require(type(a) is dict and type(b) is dict and all(
        type(a.get(k)) is int and a[k] > 0 and a[k] == b.get(k) for k in keys),
        'same-object identity differs')


def gone(saved):
    require(type(saved) is dict and type(saved.get('pid')) is int and saved['pid'] > 0 and
            type(saved.get('start_ticks')) is int and saved['start_ticks'] > 0, 'missing original saved identity')
    row = {'saved_identity': saved, 'observed_monotonic_ns': time.monotonic_ns()}
    try:
        raw = Path('/proc', str(saved['pid']), 'stat').read_text()
        end = raw.rfind(')')
        require(end >= 0 and int(raw[:raw.index('(')].strip()) == saved['pid'], 'malformed proc stat')
        fields = raw[end + 2:].split()
        row.update(same_identity_present=int(fields[19]) == saved['start_ticks'],
                   observed_state=fields[0], observed_start_ticks=int(fields[19]))
    except FileNotFoundError:
        row.update(same_identity_present=False, observed_state=None)
    except (OSError, ValueError, IndexError) as error:
        row.update(same_identity_present=None, error=repr(error))
    require(row['same_identity_present'] is False, 'saved identity present including Z, or unreadable')
    return row


def main():
    require(proof(COPIER)['sha256'] == COPIER_SHA, 'original opaque copier changed')
    pack = load_module(COPIER, 'v55_immutable_v45_opaque_copier')
    pack.A = A; pack.DEST = A / 'closed_execution'
    def read(path):
        return pack.metadata(Path(path))[0]
    def write(path, value):
        pack.write_json(Path(path), value)
    summary = read(PREFIX / 'summary.json')
    entry = read(PREFIX / 'entry.json')
    rootwait_path = Path('/tmp/mr3_p2a_v55_actual_tool_wait_v1.json')
    rootwait = read(rootwait_path)
    require(rootwait['schema'] == 'mr3-v55-root-tool-actual-wait-v1' and
            rootwait['tool_session_id'] == 23231 and rootwait['actual_waited'] is True and
            type(rootwait['actual_returncode_observed']) is int and
            rootwait['actual_returncode_observed'] == (0 if summary['passed'] is True else 1),
            'real root tool wait does not match actual completed driver')
    bound(rootwait['launch']); bound(rootwait['live_ancestor'])
    launch, live = read(rootwait['launch']['path']), read(rootwait['live_ancestor']['path'])
    require(summary['execution_freeze'] == launch['freeze'] == FREEZE and summary['evidence_freeze'] == OLD,
            'actual source/evidence freeze differs')
    require(summary['actual_driver_argv'] == entry['actual_driver_argv'] ==
            [launch['argv'][0], *launch['argv'][2:]] and
            summary['actual_driver_program_argument'] == live['actual_tool_program_argument'] == launch['argv'][2] and
            live['launch_program_argument_identical'] is True and launch['cwd'] == entry['cwd'] == str(W),
            'complete actual driver program/argv differs')
    for row in launch['binding_refs']:
        bound(row)
    same(summary['driver_identity'], entry['driver_identity'])
    same(summary['driver_identity'], live['saved_driver_identity'])
    same(summary['driver_identity'], live['live_driver_identity'])
    ancestor = live['actually_observed_tool_ancestor']
    require(live['tool_session_id'] == 23231 and live['relationship_confirmed_while_alive'] is True and
            live['no_missing_start_reconstruction'] is True and
            ancestor['pid'] == summary['driver_identity']['parent'] and
            ancestor['group'] == summary['driver_identity']['group'] and
            ancestor['session'] == summary['driver_identity']['session'], 'real live ancestry is not bound')
    observations = [gone(summary['driver_identity']), gone(ancestor)]

    driver_path = A / 'run_passive_pair_v1.py'
    require(driver_path.read_bytes() == subprocess.check_output(
        ['rtk', 'proxy', 'git', 'show', FREEZE + ':' + str(driver_path.relative_to(ROOT))], cwd=ROOT),
        'frozen metadata/source verifier differs')
    driver = load_module(driver_path, 'v55_exact_frozen_source_verifier')
    scope = read(A / 'scope_v1.json')
    spec, current_sources = driver.verify_inputs(scope, FREEZE)  # Pure metadata/Git/source bytes, not World.
    require(len(current_sources) == 371 and len(scope['source_bindings']) == 19 and
            len(scope['old_source_bindings']) == 10 and
            summary['source_before'] == summary['source_after'] == current_sources,
            '371 complete source bindings/current-Git proof differs')
    manifest = read(scope['build_manifest']['path'])
    require(len(manifest['shared_libraries']) == 342, 'fixed linked-library membership differs')
    aliases = {row['path']: str(Path(row['path']).resolve(strict=True)) for row in manifest['shared_libraries']}
    require([row['arm'] for row in summary['arms']] == ['quick50', 'direct-world'], 'actual two-case membership differs')
    actual_rows = []
    for arm in summary['arms']:
        label = arm['arm']; arm_dir = PREFIX / 'arms' / label
        wait = read(PREFIX / 'waits' / label / 'actual_wait.json')
        early = read(arm_dir / 'identity.json')
        require(wait['schema'] == 'mr3-reach-outer-actual-wait-v1' and wait['scope'] == 'engineering' and
                wait['actual_waited'] is True and type(wait['actual_returncode']) is int and
                arm['actual_wrapper_waited'] is True and type(arm['actual_wrapper_returncode']) is int and
                arm['actual_CPP_returncode'] == wait['actual_returncode'] and
                wait['actual_argv'] == early['actual_argv'] == arm['actual_CPP_argv'],
                'actual CPP/wrapper wait/argv not retained')
        same(arm['wrapper_identity'], wait['coordinator_identity'])
        same(early['identity'], wait['child_identity'])
        same(early['identity'], arm['CPP_identity_from_actual_wait'])
        same(early['identity'], read(PREFIX / (label + '_CPP_identity.json')))
        same(arm['wrapper_identity'], read(PREFIX / (label + '_wrapper_identity.json')))
        for observed in arm['CPP_identities_observed']:
            same(observed, early['identity'])
        require(arm['wrapper_identity']['parent'] == summary['driver_identity']['pid'] and
                arm['wrapper_identity']['group'] == arm['wrapper_identity']['session'] == arm['wrapper_identity']['pid'] and
                early['identity']['parent'] == arm['wrapper_identity']['pid'] and
                early['identity']['group'] == early['identity']['session'] == arm['wrapper_identity']['pid'],
                'fresh private wrapper/CPP ownership differs')
        observations.extend([gone(arm['wrapper_identity']), gone(early['identity'])])
        require(wait['source_before'] == wait['source_after'] and wait['source_unchanged'] is True and
                len(wait['source_before']) == len(current_sources) and
                [{k: row[k] for k in ('path', 'bytes', 'sha256')} for row in wait['source_before']] == current_sources,
                'complete case source before/after differs')
        require(proof(PREFIX / 'waits' / label / 'console.log')['sha256'] == wait['console']['sha256'],
                'actual CPP console SHA differs')
        started, ended = arm['started_monotonic_ns'], arm['ended_monotonic_ns']
        require(type(started) is int and type(ended) is int and
                0 < started <= wait['started_monotonic_ns'] < wait['ended_monotonic_ns'] <= ended and
                Decimal(arm['actual_case_parent_wall_seconds']) == Decimal(ended - started) / 10**9 and
                Decimal(wait['actual_child_wait_seconds']) == Decimal(wait['ended_monotonic_ns'] - wait['started_monotonic_ns']) / 10**9,
                'actual contained case wall intervals differ')
        native_summary_present = (arm_dir / 'summary.json').exists()
        if not native_summary_present:
            require(arm['actual_CPP_summary'] is None and arm['execution_passed'] is False,
                    'missing CPP summary has been promoted to execution success')
        actual_rows.append({'arm': label, 'actual_wrapper_returncode': arm['actual_wrapper_returncode'],
            'actual_CPP_returncode': wait['actual_returncode'], 'execution_passed': arm['execution_passed'],
            'CPP_summary_present': native_summary_present, 'driver_arm_errors': arm['errors'],
            'started_monotonic_ns': started, 'ended_monotonic_ns': ended,
            'actual_case_parent_wall_seconds': arm['actual_case_parent_wall_seconds'],
            'nested_CPP_wall_seconds_not_added': wait['actual_child_wait_seconds']})

    start, end = summary['pair_started_monotonic_ns'], summary['pair_ended_monotonic_ns']
    require(start == actual_rows[0]['started_monotonic_ns'] and end == actual_rows[-1]['ended_monotonic_ns'] and
            actual_rows[0]['ended_monotonic_ns'] <= actual_rows[1]['started_monotonic_ns'] and end <= time.monotonic_ns(),
            'one continuous first-Popen/last-real-wait span differs')
    fee = Decimal(end - start) / 10**9
    require(fee == Decimal(summary['engineering_added_parent_wall_seconds']) and
            Decimal(summary['engineering_entry_seconds']) == ENTRY and
            Decimal(summary['engineering_ceiling_seconds']) == CEILING and
            Decimal(summary['engineering_cumulative_seconds']) == ENTRY + fee and
            Decimal(summary['engineering_remaining_seconds']) == CEILING - ENTRY - fee,
            'actual continuous parent accounting/carry differs')
    originals = {}
    directories = {}
    for parent, names, files in os.walk(PREFIX, followlinks=False):
        parent = Path(parent); directories[str(parent)] = pack.stamp(parent.lstat())
        for name in names:
            require(not (parent / name).is_symlink(), 'unexpected source directory symlink')
        for name in files:
            source = parent / name
            originals[source] = {'target': A / 'closed_execution/tmp' / PREFIX.name / source.relative_to(PREFIX),
                'compressed': source.suffix in pack.TEXT_SUFFIXES or source.name in pack.TEXT_NAMES,
                'stat': pack.regular_stamp(source)}
    tools = [rootwait_path, Path(rootwait['launch']['path']), Path(rootwait['live_ancestor']['path']), Path(__file__)]
    for source in tools:
        originals[source] = {'target': A / 'closed_execution/closure_tools' / source.name,
                            'compressed': False, 'stat': pack.regular_stamp(source)}
    for source, row in originals.items():
        if row['compressed']:
            row['target'] = Path(str(row['target']) + '.rawbytes.gz')
        require(not row['target'].exists() and not row['target'].is_symlink(), 'archive already exists')
    (A / 'closed_execution').mkdir(exist_ok=False)
    entries = [pack.archive(source, row) for source, row in sorted(originals.items())]
    require({p for p in PREFIX.rglob('*') if p.is_file()} == {p for p in originals if p.is_relative_to(PREFIX)},
            'closed prefix membership changed')
    require(all(pack.regular_stamp(p) == row['stat'] for p, row in originals.items()) and
            all(pack.stamp(Path(path).lstat()) == stamp for path, stamp in directories.items()),
            'closed original bytes/membership changed during opaque archive')
    after = [driver.proof(row['path']) for row in current_sources]
    require(after == current_sources and
            aliases == {row['path']: str(Path(row['path']).resolve(strict=True)) for row in manifest['shared_libraries']},
            'source or library alias targets changed across opaque archive')
    post_observations = [gone(row['saved_identity']) for row in observations]
    inventory = {'schema': 'mr3-v55-closed-opaque-byte-inventory-v1', 'passed': True,
        'activity_passed': summary['passed'], 'execution_freeze': FREEZE, 'evidence_freeze': OLD,
        'files': len(entries), 'original_bytes': sum(r['original_bytes'] for r in entries),
        'canonical_bytes': sum(r['canonical_bytes'] for r in entries), 'links': [], 'link_count': 0,
        'entries': entries, 'opaque_copier': proof(COPIER), 'CSV_semantics_read_or_recomputed': False,
        'V52_raw_read_or_copied': False, 'system_shared_libraries_copied': False,
        'original_driver_pending_and_FAIL_preserved': True}
    write(A / 'closed_inventory_v1.json', inventory)
    review = {'schema': 'mr3-v55-closed-metadata-review-v1', 'passed': True,
        'activity_passed': summary['passed'], 'actual_root_tool_session_id': 23231,
        'actual_root_returncode_observed': rootwait['actual_returncode_observed'],
        'execution_freeze': FREEZE, 'evidence_freeze': OLD,
        'root_actual_wait': proof(rootwait_path), 'driver_summary': proof(PREFIX / 'summary.json'),
        'source_count': len(current_sources), 'new_execution_Git_code_source_count': 19,
        'old_evidence_Git_source_subset_count': 10, 'linked_library_objects': 342,
        'source_before': current_sources, 'source_after': after,
        'old_source_subset_not_added_again_to_total': True,
        'saved_identity_count': len(observations), 'identity_observations_before_archive': observations,
        'identity_observations_after_archive': post_observations, 'all_saved_identities_fresh_gone': True,
        'arms': actual_rows, 'engineering_added_parent_wall_seconds': str(fee),
        'engineering_cumulative_seconds': str(ENTRY + fee), 'engineering_remaining_seconds': str(CEILING - ENTRY - fee),
        'accounting': 'Continuous first wrapper Popen through last real wait including inter-arm gaps; no nested sum.',
        'closed_inventory': proof(A / 'closed_inventory_v1.json'),
        'small_metadata_and_opaque_copy_only': True, 'CPP_or_World_rerun': False,
        'CSV_semantics_replayed': False, 'V52_raw_read': False,
        'physical_result_inferred_from_missing_summary_or_console': False,
        'root_cause_proved': False, 'learner_models_loaded': False, 'optimizer_updates': 0,
        'native_qualification_credit': False}
    write(A / 'checks/closed_metadata_review_v1.json', review)
    print(json.dumps({'passed': True, 'activity_passed': summary['passed'],
          'saved_identity_count': len(observations), 'files': len(entries),
          'engineering_added_parent_wall_seconds': str(fee)}))


if __name__ == '__main__':
    main()
