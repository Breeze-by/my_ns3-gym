"""Bounded raw suffix description, without replay or qualification credit."""
from collections import defaultdict, deque
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def suffix(path, limit):
    """Return complete original lines with absolute byte offsets."""
    with path.open('rb') as stream:
        start = max(0, path.stat().st_size - limit)
        stream.seek(start)
        if start:
            stream.readline()
        while True:
            offset = stream.tell()
            raw = stream.readline()
            if not raw:
                break
            if not raw.endswith(b'\n'):
                raise ValueError('incomplete final original line')
            yield offset, raw, json.loads(raw)


def run(scope, output):
    started = time.monotonic()
    result = dict(schema=scope['schema'], prior_freeze=scope['prior_freeze'], inputs=[],
                  scope='fixed raw suffix description only', qualification=False)
    for item in scope['inputs']:
        path = Path(item['path']); before = path.stat()
        assert before.st_size == item['bytes'] and sha(path) == item['sha256']
        record = dict(input=item, selected=[], parsed_suffix_rows=0)
        if path.suffix == '.json':
            record['metadata'] = json.loads(path.read_bytes())
        else:
            selected = defaultdict(lambda: deque(maxlen=4))
            physical_end = None
            for offset, raw, row in suffix(path, item['tail_bytes']):
                record['parsed_suffix_rows'] += 1
                payload = row.get('payload', {})
                robot = row.get('robot', payload.get('robot'))
                key = row.get('kind'), robot
                selected[key].append(dict(offset=offset, sha256=hashlib.sha256(raw).hexdigest(),
                                          raw_line=raw.decode('utf-8')))
                if item['name'] == 'physics.jsonl':
                    physical_end = max(physical_end or 0, row['end_time_ns'])
                if time.monotonic() - started > scope['work_seconds']:
                    raise TimeoutError('declared description work exceeded')
            record['selected'] = sorted((x for rows in selected.values() for x in rows),
                                        key=lambda x: x['offset'])
            if physical_end is not None:
                record['complete_physics_end_ns'] = physical_end
        after = path.stat()
        assert (before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (
            after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
        result['inputs'].append(record)
    result['work_seconds'] = time.monotonic() - started
    result['description_complete'] = True
    raw = (json.dumps(result, indent=2, ensure_ascii=False) + '\n').encode()
    assert len(raw) <= scope['output_limit_bytes']
    with output.open('xb') as stream:
        stream.write(raw)
    print(json.dumps(dict(description_complete=True, bytes=len(raw), work_seconds=result['work_seconds'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--scope', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args()
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip() == args.freeze
    assert not subprocess.check_output(['git', 'status', '--porcelain'])
    run(json.loads(args.scope.read_bytes()), args.output)
