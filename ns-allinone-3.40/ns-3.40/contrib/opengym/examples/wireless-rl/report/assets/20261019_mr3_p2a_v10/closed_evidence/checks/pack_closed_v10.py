"""Archive closed V10 originals without repairing any historical result."""

from collections import Counter
from decimal import Decimal
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess

import tarfile


ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSETS = W / 'report/assets/20261019_mr3_p2a_v10'
OUT = ASSETS / 'closed_evidence'
FREEZE = 'ab03d9ea867a05712d4d5e200761d33523fc9d20'
EVIDENCE = Path('/tmp/mr3_p2a_v10_matrix_evidence')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def signature(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns]


def exclusive(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def frozen(relative):
    return subprocess.check_output(['git', 'show', FREEZE + ':' + relative], cwd=ROOT)


def relative_bindings(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            if not Path(value['path']).is_absolute():
                yield value['path'], value['sha256']
        for child in value.values():
            yield from relative_bindings(child)
    elif isinstance(value, list):
        for child in value:
            yield from relative_bindings(child)


def add_directory(sources, directory, prefix):
    assert directory.is_dir(), str(directory)
    for path in sorted(directory.rglob('*')):
        assert not path.is_symlink(), str(path)
        assert path.is_dir() or path.is_file(), str(path)
        if path.is_file():
            sources.append((path, prefix + '/' + path.relative_to(directory).as_posix(), None))


def main():
    plan_relative = str((ASSETS / 'predeclared_plan_v10.json').relative_to(ROOT))
    plan_raw = frozen(plan_relative)
    plan = json.loads(plan_raw)
    binding_relative = str((ASSETS / 'native_custody_binding.json').relative_to(ROOT))
    binding_raw = frozen(binding_relative)
    binding = json.loads(binding_raw)
    launch = json.loads(Path('/tmp/mr3_p2a_v10_matrix_execution_receipt.json').read_text())
    final = json.loads(Path('/tmp/mr3_p2a_v10_matrix_final_closure.json').read_text())
    summary = json.loads((EVIDENCE / 'summary.json').read_text())
    preflight = json.loads(Path('/tmp/mr3_p2a_v10_preflight.json').read_text())
    assert all(value['freeze'] == FREEZE for value in (launch, final, summary, preflight))
    assert all(value['plan_sha256'] == digest(plan_raw) for value in (launch, summary, preflight))
    assert preflight['passed'] is True and launch['returncode'] == 1
    assert launch['wall_seconds'] == '829.007653796'
    assert final['closure_passed'] is True and final['all_saved_identities_gone'] is True
    assert final['saved_identity_count'] == len(final['identities']) == 49
    assert all(row['current'] is None and row['same_identity_present'] is False for row in final['identities'])
    assert final['execution_passed'] is False and final['passed'] is False and summary['passed'] is False
    assert 'ended_wall_monotonic_ns' not in final
    assert summary['all_submitted_children_waited'] is True
    for name, expected in final['inputs'].items():
        path = Path(name)
        assert path.stat().st_size == expected['bytes'] and file_sha(path) == expected['sha256'], name

    sources = []
    add_directory(sources, EVIDENCE, 'matrix_evidence')
    stage_presence = []
    stage_summaries = {stage['stage']: stage for stage in summary['stages']}
    for stage in plan['stages']:
        directory = Path(stage['run_directory'])
        present = directory.exists()
        stage_presence.append({'stage': stage['stage'], 'original_path': str(directory),
                               'actual_directory_exists': present,
                               'original_execution_status': stage_summaries[stage['stage']]['status']})
        if present:
            add_directory(sources, directory, 'native_runs/' + stage['stage'])
        else:
            assert stage_summaries[stage['stage']]['status'] == 'SKIPPED'
    assert [row['stage'] for row in stage_presence if row['actual_directory_exists']] == ['interface']
    native_path = Path(plan['stages'][0]['native']['output'])
    native = json.loads(native_path.read_text())
    live = json.loads((EVIDENCE / 'interface/live_custody.json').read_text())
    assert native['freeze'] == live['freeze'] == FREEZE
    assert live['binding_sha256'] == digest(binding_raw)
    assert native['passed'] is True and native['valid_transitions'] == 32
    assert live['passed'] is False and len(live['errors']) > 0
    assert summary['stages'][0]['native']['returncode'] == 0
    assert summary['stages'][0]['watcher']['returncode'] == 1

    # Preserve every currently existing, exactly named V10 temporary original.
    extras = sorted(path for path in Path('/tmp').iterdir() if 'p2a_v10' in path.name and path != EVIDENCE)
    assert len(extras) == 16, [str(path) for path in extras]
    for path in extras:
        assert path.is_file() and not path.is_symlink(), str(path)
        sources.append((path, 'external_checks/' + path.name, None))
    observer_receipts = []
    for version, expected_pid, expected_start, expected_rc in ((1, 909112, 409344729, 143),
                                                           (2, 910648, 409360386, 0)):
        path = Path('/tmp/mr3_p2a_v10_readonly_observer_v%d_actual_wait.json' % version)
        value = json.loads(path.read_text())
        assert value['observer_identity']['pid'] == expected_pid
        assert value['observer_identity']['start_ticks'] == expected_start
        assert value['actual_tool_wait_returncode'] == expected_rc
        assert value['saved_identity_absent'] is True and value['current_identity'] is None
        observer_receipts.append({'version': version, 'path': str(path),
                                 'identity': value['observer_identity'],
                                 'actual_tool_wait_returncode': value['actual_tool_wait_returncode'],
                                 'natural_exit': value['natural_exit'],
                                 'saved_identity_absent': value['saved_identity_absent'],
                                 'script_original': 'not_saved_inline' if version == 1 else
                                 '/tmp/mr3_p2a_v10_readonly_matrix_watch_v2.py'})

    binary_inventory = {}
    assert len(binding['binaries']) == 10
    for role, expected in sorted(binding['binaries'].items()):
        alias = Path(expected['path'])
        path = alias.resolve(strict=True)
        assert str(path) == expected['resolved_path']
        assert file_sha(path) == expected['sha256'] and path.stat().st_size == expected['bytes']
        with path.open('rb') as stream:
            assert stream.read(4) == b'\x7fELF'
        if 'stat' in expected:
            assert path.stat().st_dev == expected['stat']['dev']
            assert path.stat().st_ino == expected['stat']['ino']
        sources.append((path, 'binaries/' + role + '/' + path.name, None))
        binary_inventory[role] = dict(expected, archive_path=sources[-1][1],
                                      actual_snapshot_stat=signature(path))

    asset_relative = str(ASSETS.relative_to(ROOT))
    asset_names = set(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', FREEZE,
        asset_relative], cwd=ROOT, text=True).splitlines())
    assert len(asset_names) == 7
    expected_sources = dict(plan['source_bindings'])
    assert len(expected_sources) == 273
    custody_source_bindings = dict(relative_bindings(binding))
    for name, value in custody_source_bindings.items():
        assert name not in expected_sources or expected_sources[name] == value, name
    names = asset_names | set(expected_sources) | set(custody_source_bindings)
    names.add(str((W / 'report/20261019_mr3_p2a_v10.md').relative_to(ROOT)))
    for name in sorted(names):
        raw = frozen(name)
        if name in expected_sources:
            assert digest(raw) == expected_sources[name], name
        if name in custody_source_bindings:
            assert digest(raw) == custody_source_bindings[name], name
        sources.append((None, 'frozen_sources/' + name, raw))
    assert len({name for _, name, _ in sources}) == len(sources)

    rows = []
    for path, name, raw in sources:
        if path is not None:
            assert path.is_file() and not path.is_symlink(), str(path)
            stat = signature(path)
            value = file_sha(path)
            assert signature(path) == stat
            row = {'path': name, 'original_path': str(path), 'bytes': stat[2],
                   'sha256': value, 'source_stat': stat, 'source_origin': 'actual_closed_file'}
        else:
            row = {'path': name, 'original_path': name.removeprefix('frozen_sources/'),
                   'bytes': len(raw), 'sha256': digest(raw), 'source_origin': 'git_blob', 'freeze': FREEZE}
        rows.append(row)

    archive_path = OUT / 'closed.tar.gz'
    with archive_path.open('xb') as destination:
        with gzip.GzipFile(filename='', fileobj=destination, mode='wb', mtime=0, compresslevel=6) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|') as archive:
                for (path, name, raw), row in zip(sources, rows):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = row['bytes'], 0o644, 0
                    if path is None:
                        archive.addfile(info, io.BytesIO(raw))
                    else:
                        with path.open('rb') as stream:
                            archive.addfile(info, stream)
                        assert signature(path) == row['source_stat'] and file_sha(path) == row['sha256']
    expected = {row['path']: row for row in rows}
    seen = set()
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            assert member.isfile() and member.name in expected and member.name not in seen
            seen.add(member.name)
            total, value = 0, hashlib.sha256()
            with archive.extractfile(member) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    total += len(block)
                    value.update(block)
            assert total == expected[member.name]['bytes']
            assert value.hexdigest() == expected[member.name]['sha256']
    assert seen == set(expected)
    with gzip.open(archive_path, 'rb') as stream:
        while stream.read(1024 * 1024):
            pass  # Reading gzip through EOF verifies its trailer and CRC.
    parts = []
    with archive_path.open('rb') as stream:
        for index in range(10000):
            block = stream.read(49_000_000)
            if not block:
                break
            part = OUT / ('closed.tar.gz.part%04d' % index)
            with part.open('xb') as destination:
                destination.write(block)
            assert part.stat().st_size < 50_000_000
            parts.append({'path': part.name, 'bytes': len(block), 'sha256': file_sha(part)})
    combined = hashlib.sha256()
    for part in parts:
        with (OUT / part['path']).open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                combined.update(block)
    assert combined.hexdigest() == file_sha(archive_path)
    for (path, _, _), row in zip(sources, rows):
        if path is not None:
            assert signature(path) == row['source_stat'] and file_sha(path) == row['sha256']
    for role, expected in binding['binaries'].items():
        assert Path(expected['path']).resolve(strict=True) == Path(expected['resolved_path'])

    accounting = {
        'schema': 'mr3-p2a-v10-parent-declared-conservative-charge-v1', 'freeze': FREEZE,
        'outer_start_wall_monotonic_ns': launch['started_wall_monotonic_ns'],
        'outer_actual_wait_end_wall_monotonic_ns': launch['ended_wall_monotonic_ns'],
        'outer_actual_wait_returncode': launch['returncode'],
        'outer_actual_wait_wall_seconds': launch['wall_seconds'],
        'coordinator_internal_charge_wall_seconds': summary['charged_wall_seconds'],
        'final_closure_internal_observation_wall_monotonic_ns': final['wall_monotonic_ns'],
        'final_closure_actual_script_end_timestamp': None,
        'whole_final_closure_tool_wall_seconds_as_explicitly_reported_by_root': '0.266266357',
        'final_closure_tool_returncode_as_explicitly_reported_by_root': 1,
        'gross_to_final_internal_observation_seconds': '903.613392543',
        'formula': '(4094280735939646 - 4093377122547103) / 1e9 + 0.266266357',
        'charge_seconds_conservative_upper_bound': '903.879658900',
        'engineering_used_before_seconds': '13048.8387923926018',
        'engineering_used_after_seconds': '13952.7184512926018',
        'engineering_remaining_after_seconds': '16047.2815487073982',
        'engineering_authorized_total_seconds': '30000',
        'pilot_decisions_remaining_unchanged': 1870,
        'pilot_wall_seconds_remaining_unchanged': '2905.9547395464029',
        'scope': 'Root explicitly supplied the measured whole final tool wall. Adding that entire wall '
                 'to the internal observation is a conservative upper bound, not an invented exact '
                 'end timestamp or a fabricated old-script receipt. Archive CPU is excluded from '
                 'native engineering charge.'}
    assert Decimal(final['wall_monotonic_ns'] - launch['started_wall_monotonic_ns']) / Decimal(10**9) == Decimal(accounting['gross_to_final_internal_observation_seconds'])
    assert Decimal(accounting['gross_to_final_internal_observation_seconds']) + Decimal(accounting['whole_final_closure_tool_wall_seconds_as_explicitly_reported_by_root']) == Decimal(accounting['charge_seconds_conservative_upper_bound'])
    assert Decimal(accounting['engineering_used_before_seconds']) + Decimal(accounting['charge_seconds_conservative_upper_bound']) == Decimal(accounting['engineering_used_after_seconds'])
    assert Decimal(accounting['engineering_used_after_seconds']) + Decimal(accounting['engineering_remaining_after_seconds']) == Decimal('30000')
    exclusive(OUT / 'accounting.json', accounting)

    science_unsubmitted, auxiliary_unsubmitted = [], []
    for stage in plan['stages']:
        observed = stage_summaries[stage['stage']].get('audits', {})
        assert observed == {}, observed
        for job in stage['audits']:
            row = {'stage': stage['stage'], 'id': job['id'], 'role': job['role'],
                   'required': job['required'], 'status': 'NOT_SUBMITTED',
                   'output_original_path': job['output']}
            assert not Path(job['output']).exists(), job['output']
            if job.get('receipt'):
                assert not Path(job['receipt']).exists(), job['receipt']
                row['receipt_original_path'] = job['receipt']
            (science_unsubmitted if job['role'] else auxiliary_unsubmitted).append(row)
    assert len(science_unsubmitted) == 38
    direct = [{'path': str(path.relative_to(OUT)), 'bytes': path.stat().st_size, 'sha256': file_sha(path)}
              for path in (Path(__file__), OUT / 'accounting.json')]
    result = {
        'schema': 'mr3-p2a-v10-closed-packet-v1', 'freeze': FREEZE,
        'files': rows, 'parts': parts, 'direct_files': direct,
        'file_count': len(rows), 'source_binding_files_verified': len(expected_sources),
        'custody_source_bindings_verified': len(custody_source_bindings),
        'frozen_v10_assets_files': len(asset_names),
        'file_counts_by_top_directory': dict(Counter(row['path'].split('/')[0] for row in rows)),
        'raw_bytes': sum(row['bytes'] for row in rows), 'archive_bytes': archive_path.stat().st_size,
        'archive_sha256': file_sha(archive_path), 'binary_inventory': binary_inventory,
        'all_tar_members_byte_roundtrip_verified': True, 'gzip_to_eof_crc_verified': True,
        'parts_concatenation_sha_verified': True, 'actual_source_files_stable_end_verified': True,
        'git_source_bytes_bound_to_original_freeze': True,
        'gross_wall_accounting': accounting,
        'preserved_outcome': {
            'native_scripted_collection_passed': native['passed'],
            'native_valid_transitions': native['valid_transitions'],
            'native_actual_wait_returncode': summary['stages'][0]['native']['returncode'],
            'watcher_live_custody_passed': live['passed'],
            'watcher_actual_wait_returncode': summary['stages'][0]['watcher']['returncode'],
            'watcher_original_error_count': len(live['errors']),
            'watcher_unique_original_errors': sorted({row['error'] for row in live['errors']}),
            'outer_actual_wait_returncode': launch['returncode'],
            'matrix_coordinator_passed': summary['passed'],
            'final_absence_closure_passed': final['closure_passed'],
            'all_actual_saved_matrix_identities_gone': final['all_saved_identities_gone'],
            'actual_saved_matrix_identity_count': final['saved_identity_count'],
            'overall_execution_passed': final['passed'],
            'stage_directory_presence': stage_presence,
            'scientific_roles_without_submitted_receipts': science_unsubmitted,
            'auxiliary_jobs_without_submitted_receipts': auxiliary_unsubmitted,
            'observer_actual_waits_and_absence': observer_receipts,
            'gpu_calls': summary['gpu_calls'], 'optimizer_steps': summary['optimizer_steps'],
            'scope': 'Every original FAIL/nonzero and skipped/unsubmitted job remains distinct from '
                     'the successful absence closure. No missing returncode, native identity, '
                     'consumer result or first-generation inline script is invented.'},
        'restore': 'Concatenate listed parts in order, verify archive_sha256, read gzip to EOF, '
                   'then verify every regular tar member SHA/size against files[]. native_runs/* '
                   'and matrix_evidence/* contain all actual originals; external_checks/* preserve '
                   'the V10 receipts, diagnosis and saved observer artifacts; binaries/* contain '
                   'ten exact bound ELF snapshots; frozen_sources/* are original ab03 Git bytes. '
                   'Direct files are named in direct_files[]. The later actual pack-wait receipt '
                   'checks/pack_actual_wait.json binds this manifest after the real CPU child exit.',
        'scope': 'Canonical closed V10 evidence only. No runtime/source original was edited. '
                 'Snapshot identity does not relabel failed live custody as passed. No full '
                 '38-role matrix, PPO minimum, pilot, 95% reliability or P2A PASS credit.'}
    exclusive(OUT / 'manifest.json', result)
    archive_path.unlink()
    print(json.dumps({key: result[key] for key in (
        'file_count', 'file_counts_by_top_directory', 'raw_bytes', 'archive_bytes', 'archive_sha256',
        'all_tar_members_byte_roundtrip_verified', 'actual_source_files_stable_end_verified')}))


if __name__ == '__main__':
    main()
