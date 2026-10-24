"""Independent final absence check after the finite coordinator really exits."""
import argparse
import hashlib
import json
from pathlib import Path
import time


def identity(pid):
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': int(pid), 'start_ticks': int(fields[19]), 'state': fields[0]}
    except (OSError, ValueError, IndexError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--receipt', type=Path, required=True)
    parser.add_argument('--root', type=Path, action='append', required=True)
    parser.add_argument('--summary', type=Path, required=True)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('previous evidence cannot be overwritten')
    inputs, saved = {}, {}

    def read(path):
        before = path.stat()
        raw = path.read_bytes()
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('input changed during read: ' + str(path))
        inputs[str(path)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        return json.loads(raw)

    def collect(value, origin):
        if isinstance(value, dict):
            if type(value.get('pid')) is int and type(value.get('start_ticks')) is int:
                key = (value['pid'], value['start_ticks'])
                saved.setdefault(key, {'saved': value, 'origins': []})['origins'].append(origin)
            for key, child in value.items():
                collect(child, origin + '/' + str(key))
        elif isinstance(value, list):
            for i, child in enumerate(value):
                collect(child, origin + '/' + str(i))

    receipt = read(args.receipt)
    if (receipt.get('schema') != 'mr3-p2a-v9-outer-actual-wait-v1'
            or receipt['freeze'] != args.freeze or receipt['returncode'] is None
            or not isinstance(receipt.get('errors'), list)):
        raise ValueError('missing real frozen coordinator wait receipt')
    collect(receipt, str(args.receipt))
    summary = read(args.summary)
    if summary['freeze'] != args.freeze:
        raise ValueError('summary freeze differs')
    schemas = {'trace': 'mr3-p2a-v9-fixed-trace-execution-v1',
               'matrix': 'mr3-preparation-execution-v1'}
    if (receipt.get('scope') not in schemas or summary.get('schema') != schemas[receipt['scope']]
            or summary.get('plan_sha256') != receipt.get('plan_sha256')
            or not isinstance(receipt.get('plan_sha256'), str)
            or len(receipt['plan_sha256']) != 64):
        raise ValueError('outer receipt/summary plan or scope identity differs')
    collect(summary, str(args.summary))
    names = {'supervisor_shutdown.json', 'supervisor_metadata.json', 'native.json', 'watcher.json',
             'live_custody.json', 'native_command.json', 'watcher_command.json'}
    for root in args.root:
        if not root.exists():
            raise ValueError('declared evidence root is missing: ' + str(root))
        for path in sorted(root.rglob('*.json')):
            if path.name in names or path.name.endswith('_command.json'):
                collect(read(path), str(path))
        ledger = root / 'ledger.jsonl'
        if ledger.exists():
            raw = ledger.read_bytes()
            inputs[str(ledger)] = {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            for i, line in enumerate(raw.splitlines(), 1):
                collect(json.loads(line), str(ledger) + ':' + str(i))
    rows = []
    for (pid, start), value in sorted(saved.items()):
        current = identity(pid)
        rows.append({**value, 'current': current,
                     'same_identity_present': bool(current and current['start_ticks'] == start)})
    for name, expected in inputs.items():
        raw = Path(name).read_bytes()
        if len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError('closed input changed before verdict: ' + name)
    clean = bool(rows) and all(not row['same_identity_present'] for row in rows)
    result = {'schema': 'mr3-p2a-v9-final-coordinator-closure-v1', 'freeze': args.freeze,
              'closure_passed': clean, 'all_saved_identities_gone': clean,
              'saved_identity_count': len(rows), 'identities': rows, 'inputs': inputs,
              'execution_passed': receipt['returncode'] == 0 and receipt['errors'] == [] and summary.get('passed') is True,
              'passed': clean and receipt['returncode'] == 0 and receipt['errors'] == [] and summary.get('passed') is True,
              'wall_monotonic_ns': time.monotonic_ns(),
              'scope': 'All actual saved PID/start identities including the persistent coordinator after its real exit; '
                       'a still-present zombie fails. No unsaved identity is invented; no process signalling.'}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('passed', 'closure_passed', 'saved_identity_count')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
