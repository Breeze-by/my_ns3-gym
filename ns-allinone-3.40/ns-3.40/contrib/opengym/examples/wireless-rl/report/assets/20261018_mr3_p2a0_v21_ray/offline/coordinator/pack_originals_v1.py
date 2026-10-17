"""Lossless sealed coordinator originals only; exact TMP manifest selection."""
import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import tarfile
import time


MANIFEST = Path('/tmp/mr3_p2a0_v21_ray_proposal_v4/sealed_manifest_v2.json')
HANDOFF = MANIFEST.parent / 'handoff_v2.json'
ARCHIVE = Path('/tmp/mr3_p2a0_v21_coordinator_originals_sealed_v1.tar.gz')
RECEIPT = Path('/tmp/mr3_p2a0_v21_coordinator_originals_custody_v1.json')


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def read_stable(path):
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode)
    with path.open('rb') as stream:
        assert identity(os.fstat(stream.fileno())) == identity(before)
        raw = stream.read()
        assert identity(os.fstat(stream.fileno())) == identity(before)
    assert identity(path.lstat()) == identity(before)
    return raw, before


def main():
    began = time.monotonic()
    self_raw, self_stat = read_stable(Path(__file__))
    raw, manifest_stat = read_stable(MANIFEST)
    assert digest(raw) == 'b545df2fd622419649f5549f211784e056fbc2a5ad50193c58d1894e904152ef'
    manifest = json.loads(raw)
    assert manifest['writers_stopped'] is True and len(manifest['files']) == 136
    selection = {row['source']: row for row in manifest['files']}
    assert len(selection) == 136
    selection[str(MANIFEST)] = {'source': str(MANIFEST), 'bytes': len(raw), 'sha256': digest(raw)}
    handoff_raw, _ = read_stable(HANDOFF)
    assert digest(handoff_raw) == '20a473e11dd866a4e6b7010c537fda386919f1e49483d00b57ee9c5608c8a12b'
    selection.setdefault(str(HANDOFF), {'source': str(HANDOFF), 'bytes': len(handoff_raw), 'sha256': digest(handoff_raw)})
    rows = []
    with ARCHIVE.open('xb') as output:
        with gzip.GzipFile(filename='', fileobj=output, mode='wb', compresslevel=6, mtime=0) as encoded:
            with tarfile.open(fileobj=encoded, mode='w') as archive:
                for source, expected in sorted(selection.items()):
                    path = Path(source)
                    assert path.is_absolute() and path.resolve().is_relative_to(Path('/tmp'))
                    member = path.relative_to('/tmp').as_posix()
                    raw, before = read_stable(path)
                    assert (len(raw), digest(raw)) == (expected['bytes'], expected['sha256'])
                    info = tarfile.TarInfo(member)
                    info.size = len(raw)
                    info.mode = stat.S_IMODE(before.st_mode)
                    info.mtime = 0
                    archive.addfile(info, io.BytesIO(raw))
                    rows.append({'source': source, 'member': member, 'bytes': len(raw),
                                 'sha256': digest(raw), 'source_stat_initial': identity(before)})
    expected_members = {row['member']: row for row in rows}
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        members = archive.getmembers()
        assert len(members) == len(rows) and len({row.name for row in members}) == len(rows)
        for member in members:
            assert member.isfile() and member.name in expected_members
            raw = archive.extractfile(member).read()
            expected = expected_members[member.name]
            assert (len(raw), digest(raw)) == (expected['bytes'], expected['sha256'])
    for row in rows:
        raw, after = read_stable(Path(row['source']))
        assert identity(after) == row['source_stat_initial']
        assert (len(raw), digest(raw)) == (row['bytes'], row['sha256'])
        row['source_stat_final'] = identity(after)
    assert read_stable(Path(__file__))[0] == self_raw
    encoded_raw, _ = read_stable(ARCHIVE)
    result = {'schema': 'mr3-v21-sealed-coordinator-originals-byte-custody-v1',
              'passed': True, 'scope': 'Lossless manifest-selected original bytes only; no test/SDK/native/canonical/Git action.',
              'argv': sys.argv, 'cwd': os.getcwd(),
              'environment_exact': dict(os.environ),
              'manifest': {'path': str(MANIFEST), 'sha256': selection[str(MANIFEST)]['sha256']},
              'handoff': {'path': str(HANDOFF), 'sha256': digest(handoff_raw), 'already_in_manifest_deduplicated': True},
              'manifest_selected_files': manifest['file_count'], 'actual_members': len(rows),
              'raw_bytes': sum(row['bytes'] for row in rows), 'files': rows,
              'archive': {'path': str(ARCHIVE), 'bytes': len(encoded_raw), 'sha256': digest(encoded_raw),
                          'encoding': 'gzip(mtime0,empty filename) of tar; member names retain full path relative to /tmp'},
              'all_members_roundtrip_sha_verified': True, 'all_sources_final_hash_stat_stable': True,
              'helper_sha256': digest(self_raw),
              'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'wall_seconds': time.monotonic() - began, 'writers': 'STOP'}
    with RECEIPT.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': True, 'archive': result['archive'], 'members': len(rows),
                      'raw_bytes': result['raw_bytes'], 'receipt': str(RECEIPT),
                      'receipt_sha256': digest(RECEIPT.read_bytes()), 'wall_seconds': result['wall_seconds']}))


if __name__ == '__main__':
    main()
