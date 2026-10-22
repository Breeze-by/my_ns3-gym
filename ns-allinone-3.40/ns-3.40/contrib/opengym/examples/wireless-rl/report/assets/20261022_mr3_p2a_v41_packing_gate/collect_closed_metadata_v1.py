"""Lossless byte archive after the actual V41 driver wait; no trace interpretation."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
ASSETS = Path(__file__).resolve().parent
NATIVE = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v41'
DEST = ASSETS / 'closed_execution'


def main():
    DEST.mkdir(exist_ok=False)
    entries = []
    inputs = []
    for source in sorted(Path('/tmp').glob('mr3_p2a_reach_v41*')):
        for path in ([source] if source.is_file() else sorted(source.rglob('*'))):
            if path.is_file():
                inputs.append((path, DEST / 'tmp' / path.relative_to('/tmp')))
    for path in sorted(NATIVE.rglob('*')):
        if path.is_file():
            inputs.append((path, DEST / 'native' / path.relative_to(NATIVE)))
    for source, target in inputs:
        before = source.stat()
        compressed = source.suffix in ('.jsonl', '.csv')
        if compressed:
            target = Path(str(target) + '.rawbytes.gz')
        target.parent.mkdir(parents=True, exist_ok=True)
        original_hash = hashlib.sha256()
        count = 0
        with source.open('rb') as reader, target.open('xb') as raw_writer:
            writer = gzip.GzipFile(filename='', mode='wb', fileobj=raw_writer, compresslevel=6, mtime=0) if compressed else raw_writer
            try:
                for block in iter(lambda: reader.read(1024 * 1024), b''):
                    original_hash.update(block)
                    count += len(block)
                    writer.write(block)
            finally:
                if compressed:
                    writer.close()
        after = source.stat()
        assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns), source
        assert count == before.st_size, source
        archived_hash = hashlib.sha256()
        verify_hash = hashlib.sha256()
        with target.open('rb') as reader:
            for block in iter(lambda: reader.read(1024 * 1024), b''):
                archived_hash.update(block)
        opener = gzip.open if compressed else open
        with opener(target, 'rb') as reader:
            for block in iter(lambda: reader.read(1024 * 1024), b''):
                verify_hash.update(block)
        assert verify_hash.digest() == original_hash.digest(), target
        entries.append({'original': str(source), 'canonical': str(target.relative_to(ASSETS)),
                        'original_bytes': count, 'original_sha256': original_hash.hexdigest(),
                        'canonical_bytes': target.stat().st_size, 'canonical_sha256': archived_hash.hexdigest(),
                        'codec': 'gzip-mtime0-lossless' if compressed else 'original-bytes',
                        'source_stat_stable': True, 'decoded_bytes_verified': True})
    value = {'schema': 'mr3-v41-closed-byte-archive-v1', 'freeze': '47224c51c1c525c55093dce26b374d1ccb07eb06',
             'purpose': 'Post-wait lossless byte archival only; no scientific replay, verdict or new experiment.',
             'engineering_added_seconds': '0', 'entries': entries, 'files': len(entries),
             'original_bytes': sum(e['original_bytes'] for e in entries),
             'canonical_bytes': sum(e['canonical_bytes'] for e in entries)}
    with (ASSETS / 'closed_inventory_v1.json').open('x') as stream:
        json.dump(value, stream, indent=2); stream.write('\n')
    print(json.dumps({k:v for k,v in value.items() if k != 'entries'}), flush=True)


if __name__ == '__main__':
    main()
