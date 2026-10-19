#!/usr/bin/python3
"""Small real-CLI packaging checks, never a native/scientific consumer."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import time

DRAFT = Path('/tmp/mr3_v19_archive_draft.py')
RECEIPT = Path('/tmp/mr3_v19_archive_draft_tiny_cpu_v1.json')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def snapshot(path):
    value = path.stat()
    return {'path': str(path), 'bytes': value.st_size, 'sha256': sha(path.read_bytes()),
            'stat': [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
                     value.st_ctime_ns]}


def main():
    assert not RECEIPT.exists(), 'exclusive receipt already exists'
    started = time.monotonic_ns()
    before = snapshot(DRAFT)
    fixture = Path(tempfile.mkdtemp(prefix='mr3_v19_archive_tiny_'))
    source = fixture / 'source'
    source.mkdir()
    (source / 'nested').mkdir()
    expected = {'plain.txt': b'closed tiny fixture\n', 'nested/empty': b'',
                'nested/binary.bin': os.urandom(4096),
                'nested/unicode-\u8bc1\u636e.txt': '\u5b8c\u6574\u539f\u4ef6\n'.encode()}
    for name, data in expected.items():
        (source / name).write_bytes(data)
    cases = []

    def run(name, root, output, *extra):
        argv = [sys.executable, '-B', str(DRAFT), '--source-root', str(root),
                '--output-dir', str(output), '--label', name, *extra]
        t0 = time.monotonic_ns()
        result = subprocess.run(argv, capture_output=True,
                                env=dict(os.environ, PYTHONNOUSERSITE='1',
                                         PYTHONDONTWRITEBYTECODE='1'))
        t1 = time.monotonic_ns()
        console = fixture / (name + '.console.log')
        with console.open('xb') as stream:
            stream.write(result.stdout)
            stream.write(result.stderr)
        row = {'id': name, 'actual_argv': argv, 'actual_waited': True,
               'returncode': result.returncode, 'started_monotonic_ns': t0,
               'ended_monotonic_ns': t1, 'wall_seconds': (t1 - t0) / 1e9,
               'console': snapshot(console)}
        cases.append(row)
        return result, row

    passed = False
    errors = []
    try:
        output = fixture / 'good'
        result, case = run('tiny', source, output, '--part-bytes', '256')
        assert result.returncode == 0, result.stderr.decode(errors='replace')
        manifest = json.loads((output / 'manifest.json').read_text())
        assert manifest['passed'] and manifest['scope'] == 'packaging_only'
        assert not manifest['native_credit'] and not manifest['scientific_pass_claimed']
        assert manifest['source_inventory_before'] == manifest['source_inventory_after']
        assert manifest['source_inventory_before']['regular_file_count'] == len(expected)
        assert manifest['source_inventory_before']['regular_file_bytes'] == sum(map(len, expected.values()))
        parts = manifest['ordered_parts']
        assert len(parts) > 1 and all(0 < x['bytes'] <= 256 for x in parts)
        assert [x['ordinal'] for x in parts] == list(range(1, len(parts) + 1))
        logical = b''.join((output / x['relative_path']).read_bytes() for x in parts)
        assert {'bytes': len(logical), 'sha256': sha(logical)} == manifest['logical_tar_xz']
        with tarfile.open(fileobj=io.BytesIO(logical), mode='r:xz') as archive:
            members = archive.getmembers()
            assert [x.name for x in members] == sorted(expected)
            for member in members:
                assert member.isfile()
                assert archive.extractfile(member).read() == expected[member.name]
        assert all((source / name).read_bytes() == data for name, data in expected.items())
        assert not list(output.glob('*.partial'))
        case['assertions_passed'] = True
        case['part_count'] = len(parts)
        case['manifest'] = snapshot(output / 'manifest.json')

        # Existing output must fail before any byte can be overwritten.
        output_before = {p.relative_to(output).as_posix(): snapshot(p) for p in output.rglob('*') if p.is_file()}
        result, case = run('existing', source, output)
        assert result.returncode != 0
        assert output_before == {p.relative_to(output).as_posix(): snapshot(p) for p in output.rglob('*') if p.is_file()}
        case['assertions_passed'] = True

        linked = fixture / 'linked-source'
        linked.mkdir()
        (linked / 'bad-link').symlink_to(source / 'plain.txt')
        linked_output = fixture / 'linked-output'
        result, case = run('symlink', linked, linked_output)
        assert result.returncode != 0
        failed = json.loads((linked_output / 'manifest.json').read_text())
        assert failed['passed'] is False and failed['partial_outputs_preserved']
        assert 'symlink/special' in failed['errors'][0]['message']
        assert (linked / 'bad-link').is_symlink()
        case['assertions_passed'] = True
        case['failed_manifest'] = snapshot(linked_output / 'manifest.json')

        special = fixture / 'special-source'
        special.mkdir()
        os.mkfifo(special / 'fifo')
        special_output = fixture / 'special-output'
        result, case = run('special', special, special_output)
        assert result.returncode != 0
        failed = json.loads((special_output / 'manifest.json').read_text())
        assert failed['passed'] is False and 'symlink/special' in failed['errors'][0]['message']
        case['assertions_passed'] = True
        case['failed_manifest'] = snapshot(special_output / 'manifest.json')

        # Path normalization must reject output containment even through '..'.
        nested_output = source / 'nested' / '..' / 'bad-output'
        result, case = run('overlap', source, nested_output)
        assert result.returncode != 0 and not (source / 'bad-output').exists()
        case['assertions_passed'] = True

        result, case = run('oversized', source, fixture / 'oversized-output', '--part-bytes', '80000001')
        assert result.returncode != 0 and not (fixture / 'oversized-output').exists()
        case['assertions_passed'] = True

        empty = fixture / 'empty-source'
        empty.mkdir()
        empty_output = fixture / 'empty-output'
        result, case = run('empty', empty, empty_output, '--part-bytes', '64')
        assert result.returncode == 0
        manifest = json.loads((empty_output / 'manifest.json').read_text())
        assert manifest['passed'] and manifest['readback']['members'] == []
        assert manifest['source_inventory_before']['regular_file_count'] == 0
        case['assertions_passed'] = True
        case['manifest'] = snapshot(empty_output / 'manifest.json')
        passed = True
    except BaseException as error:
        errors.append({'type': type(error).__name__, 'message': str(error)})
    after = snapshot(DRAFT)
    if before != after:
        passed = False
        errors.append({'type': 'SourceChanged', 'message': 'draft source before/after differs'})
    ended = time.monotonic_ns()
    receipt = {'schema': 'mr3-archive-draft-tiny-cpu-validation-v1',
               'scope': 'packaging_only', 'native_credit': False,
               'scientific_pass_claimed': False, 'passed': passed, 'errors': errors,
               'actual_argv': [sys.executable, *sys.argv], 'fixture_directory': str(fixture),
               'started_monotonic_ns': started, 'ended_monotonic_ns': ended,
               'wall_seconds': (ended - started) / 1e9, 'cases': cases,
               'source_before': before, 'source_after': after, 'source_unchanged': before == after}
    with RECEIPT.open('x') as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': passed, 'case_count': len(cases), 'receipt': str(RECEIPT),
                      'wall_seconds': receipt['wall_seconds'], 'errors': errors}))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
