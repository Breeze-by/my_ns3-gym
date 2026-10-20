"""Closed metadata/accounting only; no simulation or original trace re-audit."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path

A = Path(__file__).resolve().parent
RUN = Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v22/run_v1')
paths = [Path('/tmp/mr3_proxy2d_v22_' + name + '/actual_wait.json')
         for name in ('outer', 'forensics_outer', 'final_outer')]
receipts = [json.loads(path.read_text()) for path in paths]
intervals = []
for path, record in zip(paths, receipts):
    start, end = record['started_monotonic_ns'], record['ended_monotonic_ns']
    assert record['scope'] == 'engineering' and record['actual_waited'] and record['source_unchanged']
    assert 0 < start < end
    assert Decimal(record['actual_child_wait_seconds']) == Decimal(end - start) / Decimal(10**9)
    intervals.append((start, end))
merged = []
for start, end in sorted(intervals):
    if merged and start <= merged[-1][1]:
        merged[-1][1] = max(merged[-1][1], end)
    else:
        merged.append([start, end])
charge = Decimal(sum(end - start for start, end in merged)) / Decimal(10**9)
entry = Decimal('41480.3336378496018')
ledger = {'schema': 'mr3-proxy2d-closed-accounting-v1', 'method': 'union of actual engineering outer intervals; nested phases not added',
          'receipts': [{'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                        'actual_returncode': record['actual_returncode'], 'actual_seconds': record['actual_child_wait_seconds']}
                       for path, record in zip(paths, receipts)], 'union_intervals_ns': merged,
          'charge_seconds': str(charge), 'entry_used_seconds': str(entry), 'ceiling_seconds': '52000',
          'cumulative_used_seconds': str(entry + charge), 'remaining_seconds': str(Decimal(52000) - entry - charge),
          'pilot_remaining_decisions': 1870, 'pilot_remaining_wall_seconds': '2905.9547395464029',
          'final_only_unused_seeds': [401, 402, 403], 'budget_extension': False, 'qualification': False}
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
metadata = list(RUN.rglob('*.json')) + paths + [Path('/tmp/mr3_proxy2d_v22_absence.json'),
    Path('/tmp/mr3_proxy2d_v22_forensics_v1.json'), Path('/tmp/mr3_proxy2d_v22_preflight_outer/actual_wait.json')]
for path in metadata:
    visit(json.loads(path.read_text()))
present, unreadable = [], []
for (pid, ticks), value in identities.items():
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
    except FileNotFoundError:
        continue
    except OSError as error:
        unreadable.append({'identity': value, 'error': repr(error)})
        continue
    fields = raw[raw.rfind(')') + 2:].split()
    if int(fields[19]) == ticks:
        present.append({'identity': value, 'actual_state': fields[0]})
absence = {'schema': 'mr3-proxy2d-later-saved-absence-v1', 'scope': 'Saved main/forensic/final/preflight identities after their actual parent waits; same-start zombies are present',
           'saved_identities': list(identities.values()), 'saved_identity_count': len(identities),
           'present': present, 'unreadable': unreadable, 'passed': not present and not unreadable,
           'activity_passed': False, 'qualification': False}
assert absence['passed']
assert charge <= 3600 and ledger['remaining_seconds'][0] != '-'
for name, value in [('engineering_accounting_v1.json', ledger), ('saved_process_absence_v1.json', absence)]:
    with (A / name).open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
print(json.dumps({'passed': True, 'charge_seconds': str(charge), 'remaining': ledger['remaining_seconds'], 'saved_absent': len(identities)}))
