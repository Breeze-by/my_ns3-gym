"""Closed metadata/actual-interval accounting only; no original trace audit."""
import argparse
from decimal import Decimal
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
for name in ('run', 'outer', 'final-outer', 'absence', 'output'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--extra-outer', action='append', type=Path, default=[])
parser.add_argument('--extra-json', action='append', type=Path, default=[])
parser.add_argument('--entry', required=True)
parser.add_argument('--kind', choices=('full_behavior',), required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=False)
receipt_paths = [args.outer, *args.extra_outer, args.final_outer]
receipts = [json.loads(path.read_text()) for path in receipt_paths]
intervals = []
for record in receipts:
    start, end = record['started_monotonic_ns'], record['ended_monotonic_ns']
    assert record['scope'] == 'engineering' and record['actual_waited'] and record['source_unchanged']
    assert type(start) is int and type(end) is int and 0 < start < end
    assert Decimal(record['actual_child_wait_seconds']) == Decimal(end - start) / Decimal(10**9)
    intervals.append((start, end))
merged = []
for start, end in sorted(intervals):
    if merged and start <= merged[-1][1]:
        merged[-1][1] = max(merged[-1][1], end)
    else:
        merged.append([start, end])
charge = Decimal(sum(end - start for start, end in merged)) / Decimal(10**9)
entry = Decimal(args.entry)
ledger = {'schema': 'mr3-proxy2d-performance-accounting-v1', 'kind': args.kind,
          'method': 'union of actual engineering outer intervals; nested phases not added',
          'outer_receipts': [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                             for path in receipt_paths], 'union_intervals_ns': merged,
          'charge_seconds': str(charge), 'entry_used_seconds': str(entry), 'ceiling_seconds': '52000',
          'cumulative_used_seconds': str(entry + charge), 'remaining_seconds': str(Decimal(52000) - entry - charge),
          'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
          'final_only_unused_seeds': [401, 402, 403], 'qualification': False}
identities = {}
def visit(value):
    if isinstance(value, dict):
        if type(value.get('pid')) is int and type(value.get('start_ticks')) is int:
            identities[value['pid'], value['start_ticks']] = value
        for item in value.values():
            visit(item)
    elif isinstance(value, list):
        for item in value:
            visit(item)
for path in [*args.run.rglob('*.json'), *receipt_paths, args.absence, *args.extra_json]:
    visit(json.loads(path.read_text()))
present, unreadable = [], []
for (pid, ticks), value in identities.items():
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        if int(fields[19]) == ticks:
            present.append({'identity': value, 'state': fields[0]})
    except FileNotFoundError:
        continue
    except (OSError, ValueError, IndexError) as error:
        unreadable.append({'identity': value, 'error': repr(error)})
absence = {'schema': 'mr3-proxy2d-performance-later-absence-v1', 'kind': args.kind,
           'saved_identities': list(identities.values()), 'saved_identity_count': len(identities),
           'present': present, 'unreadable': unreadable, 'passed': not present and not unreadable,
           'activity_passed': json.loads((args.run / 'activity_result.json').read_text())['passed'],
           'qualification': False}
assert absence['passed'] and charge <= 3600
assert entry + charge <= 52000
for name, value in [('engineering_accounting_v1.json', ledger), ('saved_process_absence_v1.json', absence)]:
    with (args.output / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
print(json.dumps({'passed': True, 'charge_seconds': str(charge), 'remaining': ledger['remaining_seconds'],
                  'saved_absent': len(identities)}))
