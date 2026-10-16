from pathlib import Path
import gzip
import hashlib
import json
import sys

source = Path(sys.argv[1]).resolve()
target = Path(sys.argv[2]).resolve()
if target == source or source in target.parents:
    raise ValueError('archive target must be outside the original source')
target.mkdir(parents=True, exist_ok=False)
manifest = []
for path in sorted(source.rglob('*')):
    if not path.is_file() or path.suffix == '.pyc':
        continue
    if path.suffix == '.gz':
        sibling = path.with_suffix('')
        if sibling.is_file() and gzip.decompress(path.read_bytes()) == sibling.read_bytes():
            continue
    relative = path.relative_to(source)
    selected = target / relative
    compress = path.suffix in ('.log', '.jsonl', '.csv', '.zip') or path.name == 'resources.json'
    if compress:
        selected = selected.with_name(selected.name + '.gz')
    selected.parent.mkdir(parents=True, exist_ok=True)
    payload = path.read_bytes()
    if compress:
        with selected.open('xb') as sink:
            with gzip.GzipFile(filename='', mode='wb', fileobj=sink, mtime=0) as encoded:
                encoded.write(payload)
    else:
        with selected.open('xb') as sink:
            sink.write(payload)
    manifest.append({'source': str(path), 'selected': str(selected.relative_to(target)),
                     'encoding': 'gzip' if compress else 'identity',
                     'raw_bytes': len(payload), 'raw_sha256': hashlib.sha256(payload).hexdigest(),
                     'selected_bytes': selected.stat().st_size,
                     'selected_sha256': hashlib.sha256(selected.read_bytes()).hexdigest()})
result = {'schema': 'mr3-p2a-selected-originals-v1', 'source': str(source),
          'selection': 'All run files, excluding byte-duplicate prior .gz copies and Python cache.',
          'source_files': len(manifest), 'raw_bytes': sum(x['raw_bytes'] for x in manifest),
          'selected_bytes': sum(x['selected_bytes'] for x in manifest), 'files': manifest}
(target / 'manifest.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'files'}))
