"""Preserve closed V7 file bytes and verify a bounded, split gzip/tar packet."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil
import tarfile

RUN = Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_ppo/mr3_p2a_v7_minimal')
OUT = Path('/tmp/mr3_p2a_v7_closed_packet_v2')
EXTRAS = [
    '/tmp/mr3_p2a_v7_preflight_v1.json',
    '/tmp/mr3_p2a_v7_minimal_full_audit_v1.json',
    '/tmp/mr3_p2a_v7_minimal_input_audit_v1.json',
    '/tmp/mr3_p2a_v7_minimal_live_source_observation_v1.json',
    '/tmp/mr3_p2a_v7_minimal_live_source_closure_observation_v1.json',
    '/tmp/mr3_p2a_v7_minimal_all_saved_identity_closure_v1.json',
    '/tmp/mr3_p2a_v7_minimal_settled_turn_diagnosis_v1.json',
    '/tmp/mr3_p2a_v7_minimal_settled_turn_diagnosis_v1.md',
    '/tmp/mr3_p2a_v7_minimal_value_mismatch_diagnosis_v1.json',
    '/tmp/mr3_p2a_v7_minimal_value_mismatch_diagnosis_field_note_v1.json',
    '/tmp/mr3_p2a_v7_minimal_checkpoint_selection_regression_v1.json',
    '/tmp/mr3_p2a_v7_execution_receipts_v1.json',
    '/tmp/mr3_p2a_v7_pack_closed_v2.py',
]

def sha(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()

def signature(path):
    stat = path.stat()
    return [stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns]

def main():
    summary = json.loads((RUN / 'summary.json').read_text())
    assert summary['completed'] and not summary['cleanup_errors']
    assert json.loads(Path(EXTRAS[5]).read_text())['passed']
    sources = [(p, 'minimal/' + p.relative_to(RUN).as_posix())
               for p in sorted(RUN.rglob('*')) if p.is_file()]
    native_count = len(sources)
    sources += [(Path(p), 'checks/' + Path(p).name) for p in EXTRAS]
    assert len({name for _, name in sources}) == len(sources)
    rows = []
    for path, name in sources:
        assert path.is_file() and not path.is_symlink(), str(path)
        before = signature(path)
        digest = sha(path)
        assert signature(path) == before
        rows.append({'path': name, 'original_path': str(path), 'bytes': before[2],
                     'sha256': digest, 'source_stat': before})
    OUT.mkdir(exist_ok=False)
    temporary = OUT / 'closed.tar.gz'
    with temporary.open('xb') as destination:
        with gzip.GzipFile(filename='', fileobj=destination, mode='wb', mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|') as archive:
                for (path, name), row in zip(sources[:native_count], rows[:native_count]):
                    info = tarfile.TarInfo(name)
                    info.size, info.mode, info.mtime = row['bytes'], 0o644, 0
                    with path.open('rb') as stream:
                        archive.addfile(info, stream)
                    assert signature(path) == row['source_stat'] and sha(path) == row['sha256']
    verified = []
    expected = {row['path']: row for row in rows[:native_count]}
    with tarfile.open(temporary, 'r:gz') as archive:
        for member in archive:
            assert member.isfile() and member.name in expected and member.name not in verified
            raw = archive.extractfile(member)
            digest = hashlib.sha256()
            count = 0
            for chunk in iter(lambda: raw.read(1024 * 1024), b''):
                digest.update(chunk)
                count += len(chunk)
            assert count == expected[member.name]['bytes']
            assert digest.hexdigest() == expected[member.name]['sha256']
            verified.append(member.name)
    assert set(verified) == set(expected)
    parts = []
    with temporary.open('rb') as stream:
        for index in range(10000):
            block = stream.read(64 * 1024 * 1024)
            if not block:
                break
            target = OUT / ('closed.tar.gz.part%04d' % index)
            target.write_bytes(block)
            assert target.stat().st_size < 100000000
            parts.append({'path': target.name, 'bytes': len(block), 'sha256': sha(target)})
    combined = hashlib.sha256()
    for part in parts:
        combined.update((OUT / part['path']).read_bytes())
    assert combined.hexdigest() == sha(temporary)
    for (path, _), row in zip(sources, rows):
        assert signature(path) == row['source_stat'] and sha(path) == row['sha256']
    (OUT / 'checks').mkdir()
    for (path, name), row in zip(sources[native_count:], rows[native_count:]):
        destination = OUT / name
        shutil.copyfile(path, destination)
        assert destination.stat().st_size == row['bytes'] and sha(destination) == row['sha256']
    result = {'schema': 'mr3-p2a-v7-closed-packet-v1', 'files': rows, 'parts': parts,
              'file_count': len(rows), 'archived_file_count': native_count,
              'direct_check_file_count': len(rows) - native_count,
              'raw_bytes': sum(row['bytes'] for row in rows),
              'archive_bytes': temporary.stat().st_size, 'archive_sha256': sha(temporary),
              'roundtrip_verified': True, 'source_end_verified': True,
              'restore': 'Concatenate parts in listed order, verify archive SHA256, then read gzip/tar for minimal/* files. checks/* are direct files. Paths are relative; all file byte SHA256/size are in files[]. No original runtime file was rewritten.',
              'scope': 'V7 engineering minimum and actual failed scientific audits only; weights are diagnostic and never substitute for a pilot final.'}
    (OUT / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
    temporary.unlink()
    print(json.dumps({key: result[key] for key in ('file_count', 'raw_bytes', 'archive_bytes', 'archive_sha256', 'roundtrip_verified')}))

if __name__ == '__main__':
    main()
