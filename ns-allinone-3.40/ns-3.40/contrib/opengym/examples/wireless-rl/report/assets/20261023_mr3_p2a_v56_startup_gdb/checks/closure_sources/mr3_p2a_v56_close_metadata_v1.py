"""V56 post-reap metadata and opaque-byte closure; no native or library reread."""
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
A = W / 'report/assets/20261023_mr3_p2a_v56_startup_gdb'
A55 = W / 'report/assets/20261023_mr3_p2a_v55_passive_plant'
PREFIX = Path('/tmp/mr3_p2a_v56_startup_gdb_v1')
FREEZE = '9d22290108d3edc8861216eb0505220356de6d32'
OLD = '1fa55bc56d5bb9e230d4b397f962d83b1604b278'
ENTRY, CEILING = Decimal('90370.2852481186018'), Decimal('120000')
COPIER = W / 'report/assets/20261022_mr3_p2a_v45_preparation_classification/collect_closed_v1.py'


def require(ok, message):
    if not ok:
        raise ValueError(message)


def proof(path):
    path = Path(path); before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'regular source required: ' + str(path))
    raw = path.read_bytes(); after = path.lstat()
    require(all(getattr(before, k) == getattr(after, k) for k in
                ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')), 'source changed')
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def same(a, b, fields=('pid', 'parent', 'group', 'session', 'start_ticks')):
    require(type(a) is dict and type(b) is dict and all(type(a.get(k)) is int and
            a[k] > 0 and a[k] == b.get(k) for k in fields), 'same-object identity differs')


def gone(saved):
    require(type(saved.get('pid')) is int and saved['pid'] > 0 and
            type(saved.get('start_ticks')) is int and saved['start_ticks'] > 0, 'saved identity missing')
    row = {'saved_identity': saved, 'observed_monotonic_ns': time.monotonic_ns()}
    try:
        raw = Path('/proc', str(saved['pid']), 'stat').read_text()
        end = raw.rfind(')'); fields = raw[end + 2:].split()
        require(end >= 0 and int(raw[:raw.index('(')].strip()) == saved['pid'], 'bad proc stat')
        row.update(same_identity_present=int(fields[19]) == saved['start_ticks'],
                   observed_state=fields[0], observed_start_ticks=int(fields[19]))
    except FileNotFoundError:
        row.update(same_identity_present=False, observed_state=None)
    except (OSError, ValueError, IndexError) as error:
        row.update(same_identity_present=None, error=repr(error))
    require(row['same_identity_present'] is False, 'saved identity present (including Z) or unreadable')
    return row


def main():
    require(proof(COPIER)['sha256'] == '63d52ce389b7d61fa67f5080fa556b1f32e47b79e389800f9de55e97c40abf06', 'copier differs')
    spec = importlib.util.spec_from_file_location('v56_original_opaque_copier', COPIER)
    pack = importlib.util.module_from_spec(spec); spec.loader.exec_module(pack)
    pack.A = A; pack.DEST = A / 'closed_execution'
    def read(path):
        return pack.metadata(Path(path))[0]
    def write(path, value):
        pack.write_json(Path(path), value)

    summary = read(PREFIX / 'summary.json'); entry = read(PREFIX / 'entry.json')
    wait = read(PREFIX / 'actual_wait/actual_wait.json')
    rootwait_path = Path('/tmp/mr3_p2a_v56_actual_tool_wait_v1.json')
    launch_path = Path('/tmp/mr3_p2a_v56_root_launch_v1.json')
    live_path = Path('/tmp/mr3_p2a_v56_live_ancestor_observation_v1.json')
    rootwait, launch, live = read(rootwait_path), read(launch_path), read(live_path)
    require(rootwait['schema'] == 'mr3-root-tool-actual-wait-v1' and rootwait['actual_tool_session'] == 8209 and
            rootwait['actual_waited'] is True and type(rootwait['actual_returncode']) is int and
            rootwait['actual_returncode'] == 0 and summary['passed'] is True and summary['errors'] == [], 'actual root wait differs')
    require(launch['freeze'] == entry['freeze'] == FREEZE and launch['cwd'] == str(W), 'actual freeze/cwd differs')
    argv = launch['actual_tool_cmd_argv']
    require(argv[:8] == ['rtk', 'proxy', 'env', 'PYTHONNOUSERSITE=1', 'PYTHONDONTWRITEBYTECODE=1',
            'CUDA_VISIBLE_DEVICES=', '/usr/bin/python3', '-B'] and
            entry['actual_argv'] == [argv[6], *argv[8:]] == live['entry_actual_argv'] and
            live['entry_program'] == str(A / 'run_startup_gdb_v1.py'), 'actual argv differs')
    same(summary['driver_identity'], entry['identity']); same(entry['identity'], live['driver'])
    ancestor = live['live_parent']
    require(entry['identity']['parent'] == ancestor['pid'] and
            entry['identity']['group'] == ancestor['group'] and
            entry['identity']['session'] == ancestor['session'], 'observed live ancestor differs')
    same(summary['wrapper_identity'], read(PREFIX / 'wrapper_identity.json'))
    same(summary['wrapper_identity'], wait['coordinator_identity'])
    observed = summary['observed_owned_identities']
    require(len(observed) == 4, 'owned identity membership differs')
    same(observed[0], summary['wrapper_identity'])
    # timeout changes its process group after the immediate Popen identity snapshot.
    same(observed[1], wait['child_identity'], ('pid', 'parent', 'session', 'start_ticks'))
    require(wait['child_identity']['group'] == summary['wrapper_identity']['pid'] and
            observed[1]['group'] == observed[1]['pid'], 'saved timeout group transition differs')
    for parent, child in zip(observed, observed[1:]):
        require(child['parent'] == parent['pid'] and child['session'] == observed[0]['session'], 'owned ancestry differs')
    early = read(PREFIX / 'native/identity.json')
    same(observed[-1], early['identity'])
    activity_spec = read(A / 'spec_v1.json')
    require(wait['actual_argv'] == activity_spec['command'] and
            early['actual_argv'] == wait['actual_argv'][wait['actual_argv'].index('--args') + 1:] and
            wait['actual_waited'] is True and type(wait['actual_returncode']) is int and
            wait['actual_returncode'] == summary['actual_debugger_command_returncode'] == 0 and
            summary['actual_wrapper_waited'] is True and summary['actual_wrapper_returncode'] == 0,
            'actual debugger/native argv or wait differs')
    require(summary['inferior_SIGSEGV_observed'] is True and summary['backtrace_observed'] is True and
            summary['inferior_natural_exit_claimed'] is False and summary['native_qualification_credit'] is False,
            'debugger result promoted to inferior natural exit or qualification')
    sources = summary['source_before']
    require(len(sources) == 376 and sources == summary['source_after'] and
            wait['source_before'] == wait['source_after'] and wait['source_unchanged'] is True and
            [{k: row[k] for k in ('path', 'bytes', 'sha256')} for row in wait['source_before']] == sources,
            'actual complete source before/after differs')
    manifest = read(A55 / 'checks/build_manifest_v2.json')
    libraries = manifest['shared_libraries']; library_paths = {r['path'] for r in libraries}
    require(len(libraries) == len(library_paths) == 342 and
            {r['path']: r for r in sources if r['path'] in library_paths} == {r['path']: r for r in libraries},
            '342 actual library source metadata differs from sealed build manifest')
    # Only source/config/tool files are read here. The 342 library objects are NOT reopened.
    fresh_sources = [r for r in sources if r['path'] not in library_paths]
    require(len(fresh_sources) == 34 and [proof(r['path']) for r in fresh_sources] == fresh_sources,
            'fresh non-library source bindings differ')
    repo_sources = [r for r in fresh_sources if Path(r['path']).is_relative_to(ROOT)]
    require(len(repo_sources) == 30, 'repository source membership differs')
    for row in repo_sources:
        raw = subprocess.check_output(['rtk', 'proxy', 'git', 'show',
              FREEZE + ':' + str(Path(row['path']).relative_to(ROOT))], cwd=ROOT)
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Git source differs')
    old_bindings = read(A55 / 'scope_v1.json')['old_source_bindings']
    require(len(old_bindings) == 10, 'old subset membership differs')
    current = {r['path']: r for r in sources}
    for path, binding in old_bindings.items():
        raw = subprocess.check_output(['rtk', 'proxy', 'git', 'show', OLD + ':' + path], cwd=ROOT)
        require(len(raw) == binding['bytes'] and hashlib.sha256(raw).hexdigest() == binding['sha256'] and
                current[str(ROOT / path)] == dict(path=str(ROOT / path), **binding), 'old evidence source differs')
    require(proof(PREFIX / 'actual_wait/console.log')['sha256'] == wait['console']['sha256'], 'console differs')
    saved = [summary['driver_identity'], ancestor, *observed]
    require(len({(r['pid'], r['start_ticks']) for r in saved}) == 6, 'saved identity count differs')
    observations = [gone(r) for r in saved]
    start, end = summary['started_monotonic_ns'], summary['ended_monotonic_ns']
    require(type(start) is int and type(end) is int and 0 < start <= wait['started_monotonic_ns'] <
            wait['ended_monotonic_ns'] <= summary['actual_popen_wait_returned_monotonic_ns'] <= end <= time.monotonic_ns(),
            'actual contained intervals differ')
    fee = Decimal(end - start) / 10**9
    require(fee == Decimal('12.268341836') == Decimal(summary['engineering_added_seconds']) and
            Decimal(summary['engineering_cumulative_seconds']) == ENTRY + fee and
            Decimal(summary['engineering_remaining_seconds']) == CEILING - ENTRY - fee and fee <= 300,
            'actual parent accounting differs')

    originals, directories = {}, {}
    for parent, names, files in os.walk(PREFIX, followlinks=False):
        parent = Path(parent); directories[str(parent)] = pack.stamp(parent.lstat())
        for name in names:
            require(not (parent / name).is_symlink(), 'unexpected directory symlink')
        for name in files:
            source = parent / name
            originals[source] = {'target': A / 'closed_execution/tmp' / PREFIX.name / source.relative_to(PREFIX),
                'compressed': source.suffix in pack.TEXT_SUFFIXES or source.name in pack.TEXT_NAMES,
                'stat': pack.regular_stamp(source)}
    for source in (rootwait_path, launch_path, live_path, Path(__file__)):
        originals[source] = {'target': A / 'closed_execution/closure_tools' / source.name,
                            'compressed': False, 'stat': pack.regular_stamp(source)}
    for source, row in originals.items():
        if row['compressed']:
            row['target'] = Path(str(row['target']) + '.rawbytes.gz')
        require(not row['target'].exists() and not row['target'].is_symlink(), 'archive already exists')
    (A / 'closed_execution').mkdir(exist_ok=False)
    entries = [pack.archive(source, row) for source, row in sorted(originals.items())]
    require({p for p in PREFIX.rglob('*') if p.is_file()} == {p for p in originals if p.is_relative_to(PREFIX)} and
            all(pack.regular_stamp(p) == row['stat'] for p, row in originals.items()) and
            all(pack.stamp(Path(path).lstat()) == stamp for path, stamp in directories.items()), 'original bytes/membership changed')
    require([proof(r['path']) for r in fresh_sources] == fresh_sources, 'non-library source changed during closure')
    inventory = {'schema': 'mr3-v56-closed-opaque-byte-inventory-v1', 'passed': True,
        'activity_passed': True, 'execution_freeze': FREEZE, 'files': len(entries),
        'original_bytes': sum(r['original_bytes'] for r in entries),
        'canonical_bytes': sum(r['canonical_bytes'] for r in entries), 'links': [], 'link_count': 0,
        'entries': entries, 'opaque_copier': proof(COPIER), 'native_rerun': False,
        'system_shared_libraries_read_or_copied': False, 'old_raw_reread': False,
        'original_pending_fields_preserved': True}
    write(A / 'closed_inventory_v1.json', inventory)
    refs = {k: proof(p) for k, p in [('root_actual_wait', rootwait_path), ('root_launch', launch_path),
            ('live_ancestor', live_path), ('driver_summary', PREFIX / 'summary.json'),
            ('original_debugger_wait', PREFIX / 'actual_wait/actual_wait.json'),
            ('closed_inventory', A / 'closed_inventory_v1.json')]}
    review = {'schema': 'mr3-v56-closed-metadata-review-v1', 'passed': True, 'activity_passed': True,
        'execution_freeze': FREEZE, **refs, 'actual_root_tool_session_id': 8209,
        'actual_root_returncode_observed': 0, 'complete_original_source_count': 376,
        'complete_original_source_before_after_equal': True, 'fresh_non_library_source_count': 34,
        'fresh_repository_current_Git_source_count': 30, 'old_evidence_Git_source_subset_count': 10,
        'library_metadata_count': 342, 'library_objects_reread': False,
        'library_credit': 'Original actual engineering wait before/after metadata plus sealed build manifest; no fresh library hashing.',
        'saved_identity_count': 6, 'identity_observations_before_archive': observations,
        'identity_observations_after_archive': [gone(r) for r in saved], 'all_saved_identities_fresh_gone': True,
        'inferior_SIGSEGV_observed': True, 'backtrace_observed': True, 'inferior_natural_exit_claimed': False,
        'native_qualification_credit': False, 'engineering_added_seconds': str(fee),
        'engineering_cumulative_seconds': str(ENTRY + fee), 'engineering_remaining_seconds': str(CEILING - ENTRY - fee),
        'native_or_debugger_rerun': False, 'models_loaded': False, 'optimizer_updates': 0}
    write(A / 'checks/closed_metadata_review_v1.json', review)
    ledger = {'schema': 'mr3-engineering-closure-ledger-v1', 'passed': True,
        'activity': 'V56 bounded startup GDB diagnostic', 'activity_passed': True,
        'execution_freeze': FREEZE, 'previous_ledger': proof(A55 / 'closure_ledger_v1.json'),
        'engineering_entry_seconds': str(ENTRY), 'engineering_added_seconds': str(fee),
        'engineering_cumulative_seconds': str(ENTRY + fee), 'engineering_ceiling_seconds': str(CEILING),
        'engineering_remaining_seconds': str(CEILING - ENTRY - fee),
        'numeric_user_approval_claimed': False, 'ceiling_decision': 'Previously selected autonomous bounded engineering block; unchanged.',
        'fee_interval': {'started_monotonic_ns': start, 'ended_monotonic_ns': end,
            'accounting': 'Actual wrapper Popen through real wait plus post-source verification and owned cleanup; nested waits not added.'},
        **refs, 'closed_metadata_review': proof(A / 'checks/closed_metadata_review_v1.json'),
        'saved_main_identity_count': 6, 'all_saved_main_identities_fresh_gone': True,
        'inferior_natural_exit_claimed': False, 'diagnostic_PASS_is_only_crash_stack_acquisition': True,
        'native_qualification_credit': False, 'policies_executed': 0, 'model_updates': 0,
        'pilot_added_decisions': 0, 'pilot_added_seconds': '0', 'validation_added_decisions': 0,
        'validation_added_seconds': '0', 'pilot_remaining_decisions': 1870,
        'pilot_remaining_seconds': '2905.9547395464029', 'final_only_open_seeds': [401, 402, 403],
        'final_remaining_decisions': 900, 'final_remaining_seconds': '9000',
        'closure_metadata_scope': 'cpu', 'closure_metadata_engineering_added_seconds': '0',
        'old_FAIL_and_pending_fields_preserved': True, 'P2A_complete': False}
    write(A / 'closure_ledger_v1.json', ledger)
    print(json.dumps({'passed': True, 'files': len(entries), 'saved_main_identity_count': 6,
                     'engineering_cumulative_seconds': str(ENTRY + fee)}))


if __name__ == '__main__':
    main()
