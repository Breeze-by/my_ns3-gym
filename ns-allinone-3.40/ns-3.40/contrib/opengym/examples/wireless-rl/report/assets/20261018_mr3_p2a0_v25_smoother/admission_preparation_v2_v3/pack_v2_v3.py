"""Losslessly seal already stopped v2/v3 TMP originals; never touch canonical files."""
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import time

OUT = Path(__file__).parent
started = time.monotonic()
rows = []
stats = {}
for version in ('v2', 'v3'):
    root = Path('/tmp/mr3_p2a0_v25_smoother_custody_proposal_' + version)
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts or path.suffix == '.pyc':
            continue
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read()
            after = os.fstat(stream.fileno())
        identity = lambda s: [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]
        assert identity(before) == identity(after) == identity(path.stat())
        row = {'source': str(path), 'archive_member': version + '/' + str(path.relative_to(root)),
               'raw_sha256': hashlib.sha256(raw).hexdigest(), 'raw_bytes': len(raw),
               'source_stat': identity(after)}
        rows.append(row)
        stats[str(path)] = row
archive = OUT / 'originals.tar.gz'
with archive.open('xb') as target, gzip.GzipFile(fileobj=target, mode='wb', filename='', mtime=0) as gz, \
        tarfile.open(fileobj=gz, mode='w|') as tar:
    for row in rows:
        raw = Path(row['source']).read_bytes()
        item = tarfile.TarInfo(row['archive_member'])
        item.size = len(raw)
        item.mode = 0o644
        item.mtime = 0
        tar.addfile(item, io.BytesIO(raw))
with tarfile.open(archive, 'r:gz') as tar:
    assert len(tar.getmembers()) == len(rows)
    for row in rows:
        raw = tar.extractfile(row['archive_member']).read()
        assert len(raw) == row['raw_bytes'] and hashlib.sha256(raw).hexdigest() == row['raw_sha256']
for row in rows:
    path = Path(row['source'])
    assert identity(path.stat()) == row['source_stat']
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row['raw_sha256']
encoded = archive.read_bytes()
manifest = {'schema': 'mr3-v25-smoother-v2-v3-author-originals-v1', 'self_excluded': True,
    'files': rows, 'count': len(rows), 'raw_bytes': sum(row['raw_bytes'] for row in rows),
    'archive': {'path': str(archive), 'encoded_bytes': len(encoded),
        'encoded_sha256': hashlib.sha256(encoded).hexdigest(),
        'decoded_tar_sha256': hashlib.sha256(gzip.decompress(encoded)).hexdigest()},
    'source_final_stat_sha_verified': True, 'tar_roundtrip_verified': True, 'cache_excluded': True,
    'argv': sys.argv, 'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'v1_already_archived_not_reincluded': '/tmp/mr3_p2a0_v25_smoother_custody_offline_v1/originals.tar.gz',
    'scope': 'Only stopped author source/fixtures/CPU originals; v2=19 and v3=21 methods, no new tests or native credit.',
    'wall_seconds': time.monotonic() - started, 'writer_status': 'STOP'}
path = OUT / 'manifest.json'
with path.open('x') as stream:
    json.dump(manifest, stream, indent=2)
    stream.write('\n')
print(json.dumps({'manifest': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'files': len(rows), 'raw_bytes': manifest['raw_bytes'], 'archive': manifest['archive']}))
