"""Read-only V9 original-byte archive; no run, gate or missing wait result is repaired."""
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
ASSETS = W / 'report/assets/20261019_mr3_p2a_v9'
OUT = ASSETS / 'closed_evidence'
FREEZE = 'bbb2e6365fdbeae681bb3088faeedc6883db324b'
RUN = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_action_trace/mr3_p2a_v9_trace'
TRACE = Path('/tmp/mr3_p2a_v9_trace_evidence')
EXTRAS = ['mr3_p2a_v9_preflight.json', 'mr3_p2a_v9_binaryproof.json',
          'mr3_p2a_v9_trace_physics.json', 'mr3_p2a_v9_trace_execution_receipt.json',
          'mr3_p2a_v9_trace_final_closure.json', 'mr3_p2a_v9_custody_trace_failure_review_v1.json',
          'mr3_p2a_v9_trace_descriptive_odometry_observation_v1.json']


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def file_sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def signature(path):
    s = path.stat()
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def exclusive(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def frozen(relative):
    return subprocess.check_output(['git', 'show', FREEZE + ':' + relative], cwd=ROOT)


def main():
    plan_relative = str((ASSETS / 'predeclared_plan_v9.json').relative_to(ROOT))
    plan = json.loads(frozen(plan_relative))
    binding = json.loads(frozen(str((ASSETS / 'native_custody_binding.json').relative_to(ROOT))))
    launch = json.loads(Path('/tmp/mr3_p2a_v9_trace_execution_receipt.json').read_text())
    final = json.loads(Path('/tmp/mr3_p2a_v9_trace_final_closure.json').read_text())
    native = json.loads((RUN / 'action_trace_summary.json').read_text())
    summary = json.loads((TRACE / 'summary.json').read_text())
    assert all(v['freeze'] == FREEZE for v in (launch, final, native, summary))
    assert final['closure_passed'] is True and final['all_saved_identities_gone'] is True
    assert final['saved_identity_count'] == 51 and launch['returncode'] == 1
    assert native['completed_requested_collection'] is False and summary['passed'] is False
    sources = []
    for directory, prefix in ((RUN, 'native_run'), (TRACE, 'trace_evidence')):
        for path in sorted(directory.rglob('*')):
            assert not path.is_symlink(), str(path)
            if path.is_file():
                sources.append((path, prefix + '/' + path.relative_to(directory).as_posix(), None))
    sources += [(Path('/tmp') / name, 'external_checks/' + name, None) for name in EXTRAS]
    binary_inventory = {}
    assert len(binding['binaries']) == 9
    for role, expected in sorted(binding['binaries'].items()):
        path = Path(expected['path']).resolve(strict=True)
        assert str(path) == expected['resolved_path'] and file_sha(path) == expected['sha256']
        assert path.stat().st_size == expected['bytes'] and path.read_bytes()[:4] == b'\x7fELF'
        sources.append((path, 'binaries/' + role + '/' + path.name, None))
        binary_inventory[role] = dict(expected, archive_path=sources[-1][1])
    relative_assets = str(ASSETS.relative_to(ROOT))
    names = set(subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', FREEZE,
        relative_assets], cwd=ROOT, text=True).splitlines())
    names.update(plan['source_bindings'])
    names.add(str((W / 'report/20261019_mr3_p2a_v9.md').relative_to(ROOT)))
    for name in sorted(names):
        raw = frozen(name)
        if name in plan['source_bindings']:
            assert digest(raw) == plan['source_bindings'][name], name
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
                   'bytes': len(raw), 'sha256': digest(raw), 'source_origin': 'git_blob',
                   'freeze': FREEZE}
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
            assert total == expected[member.name]['bytes'] and value.hexdigest() == expected[member.name]['sha256']
    assert seen == set(expected)
    with gzip.open(archive_path, 'rb') as stream:
        while stream.read(1024 * 1024):
            pass  # Read to gzip EOF so its trailer/CRC is also checked.
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
    accounting = {'schema': 'mr3-p2a-v9-parent-declared-conservative-charge-v1',
        'freeze': FREEZE, 'outer_start_wall_monotonic_ns': launch['started_wall_monotonic_ns'],
        'outer_actual_wait_end_wall_monotonic_ns': launch['ended_wall_monotonic_ns'],
        'outer_actual_wait_returncode': launch['returncode'],
        'outer_actual_wait_wall_seconds': launch['wall_seconds'],
        'final_closure_internal_observation_wall_monotonic_ns': final['wall_monotonic_ns'],
        'final_closure_actual_script_end_timestamp': None,
        'whole_final_closure_tool_wall_seconds_as_explicitly_reported_by_parent': '0.838237729',
        'final_closure_tool_returncode_as_explicitly_reported_by_parent': 1,
        'all_saved_identities_gone': final['all_saved_identities_gone'],
        'saved_identity_count': final['saved_identity_count'], 'execution_passed': final['execution_passed'],
        'formula': '(4092847873757710 - 4092635397520886) / 1e9 + 0.838237729',
        'charge_seconds_conservative_upper_bound': '213.314474553',
        'engineering_used_before_seconds': '12835.5243178396018',
        'engineering_used_after_seconds': '13048.8387923926018',
        'engineering_remaining_after_seconds': '16951.1612076073982',
        'engineering_authorized_total_seconds': '30000',
        'pilot_decisions_remaining_unchanged': 1870,
        'pilot_wall_seconds_remaining_unchanged': '2905.9547395464029',
        'scope': 'Parent explicitly supplied measured whole tool wall. Adding that entire wall to its internal observation is a conservative upper bound, not an invented exact end timestamp or a fabricated old-script receipt. Packing CPU is excluded from native engineering charge.'}
    assert Decimal(accounting['engineering_used_before_seconds']) + Decimal(accounting['charge_seconds_conservative_upper_bound']) == Decimal(accounting['engineering_used_after_seconds'])
    assert Decimal(accounting['engineering_used_after_seconds']) + Decimal(accounting['engineering_remaining_after_seconds']) == Decimal('30000')
    exclusive(OUT / 'accounting.json', accounting)
    direct = [{'path': str(path.relative_to(OUT)), 'bytes': path.stat().st_size, 'sha256': file_sha(path)}
              for path in (Path(__file__), OUT / 'accounting.json')]
    result = {'schema': 'mr3-p2a-v9-closed-packet-v1', 'freeze': FREEZE,
        'files': rows, 'parts': parts, 'direct_files': direct,
        'file_count': len(rows), 'source_binding_files_verified': len(plan['source_bindings']),
        'raw_bytes': sum(row['bytes'] for row in rows), 'archive_bytes': archive_path.stat().st_size,
        'archive_sha256': file_sha(archive_path), 'binary_inventory': binary_inventory,
        'all_tar_members_byte_roundtrip_verified': True, 'gzip_to_eof_crc_verified': True,
        'parts_concatenation_sha_verified': True, 'actual_source_files_stable_end_verified': True,
        'git_source_bytes_bound_to_original_freeze': True,
        'gross_wall_accounting': accounting,
        'preserved_outcome': {'native_completed_requested_collection': native['completed_requested_collection'],
            'native_decisions_returned': native['native_decisions_returned'], 'first_failure': native['first_failure'],
            'trace_wrapper_passed': summary['passed'], 'outer_actual_wait_returncode': launch['returncode'],
            'final_absence_closure_passed': final['closure_passed'], 'overall_execution_passed': final['passed'],
            'scientific_jobs_without_submitted_receipts': [j['id'] for j in plan['trace']['scientific_audits']
                if j['id'] not in summary['audits']],
            'matrix_stage_jobs_not_submitted': [j['stage'] for j in plan['stages']],
            'scope': 'No missing or unsubmitted job is assigned an invented returncode. Original FAIL/nonzero, incomplete collection, skipped science/matrix and successful absence closure are retained separately.'},
        'restore': 'Concatenate listed parts in order, verify archive_sha256, read gzip to EOF, then verify each regular tar member SHA/size against files[]. native_run/* and trace_evidence/* contain all originals; external_checks/* preserve actual receipts/diagnosis; binaries/* contain nine actual bound ELF snapshots; frozen_sources/* are original bbb2 Git bytes. Direct files are named in direct_files[].',
        'scope': 'Canonical closed V9 evidence only. No source/runtime original was edited. No policy action returned, no training/optimizer or V7 reproduction/repair, 38-role matrix or P2A PASS credit. Snapshot identity does not relabel failed live custody as passed.'}
    exclusive(OUT / 'manifest.json', result)
    archive_path.unlink()
    print(json.dumps({k: result[k] for k in ('file_count', 'raw_bytes', 'archive_bytes', 'archive_sha256',
        'all_tar_members_byte_roundtrip_verified', 'actual_source_files_stable_end_verified')}))


if __name__ == '__main__':
    main()
