"""Copy closed original metadata and compute exact engineering interval union."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import shutil

A = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def identities(value, saved):
    if isinstance(value, dict):
        if isinstance(value.get('pid'), int) and isinstance(value.get('start_ticks'), int):
            saved[(value['pid'], value['start_ticks'])] = value
        for child in value.values():
            identities(child, saved)
    elif isinstance(value, list):
        for child in value:
            identities(child, saved)


scope = read(A / 'scope_acceptance_v1.json')
main = read(Path('/tmp/mr3_proxy2d_v26_outer/actual_wait.json'))
final = read(Path('/tmp/mr3_proxy2d_v26_final_outer/actual_wait.json'))
for outer in (main, final):
    assert outer['scope'] == 'engineering' and outer['passed']
    assert outer['actual_waited'] and outer['actual_returncode'] == 0
    assert outer['source_unchanged'] and not outer['errors']
intervals = sorted((outer['started_monotonic_ns'], outer['ended_monotonic_ns']) for outer in (main, final))
merged = []
for start, end in intervals:
    assert end >= start
    if merged and start <= merged[-1][1]:
        merged[-1][1] = max(end, merged[-1][1])
    else:
        merged.append([start, end])
charge = Decimal(sum(end - start for start, end in merged)) / 10**9
span = Decimal(max(end for start, end in intervals) - min(start for start, end in intervals)) / 10**9
assert span <= Decimal(scope['activity_engineering_ceiling_seconds'])
entry = Decimal(scope['engineering_entry_seconds'])
ceiling = Decimal(scope['engineering_ceiling_seconds'])
accounting = {'schema': 'mr3-p2a-v26-engineering-accounting-v1',
              'source_freeze': '89a1b0543c5445bb5815162ae4ef07f1f7c728c0',
              'entry_seconds': str(entry), 'ceiling_seconds': str(ceiling),
              'charged_outer_paths': ['/tmp/mr3_proxy2d_v26_outer/actual_wait.json',
                                      '/tmp/mr3_proxy2d_v26_final_outer/actual_wait.json'],
              'merged_monotonic_ns': merged, 'charged_seconds': str(charge),
              'full_start_to_final_end_seconds': str(span),
              'cumulative_seconds': str(entry + charge),
              'remaining_seconds': str(ceiling - entry - charge),
              'cpu_preflight_seconds_excluded': '0.878233462',
              'nested_guard_and_consumer_not_added': True,
              'pilot_remaining_decisions': 1870, 'pilot_remaining_seconds': '2905.9547395464029',
              'final_only_unused_seeds': [401, 402, 403],
              'new_episodes': 0, 'new_policy_calls': 0, 'new_optimizer_steps': 0,
              'new_native_runs': 0, 'qualification': False,
              'training_eligible': False, 'native_credit': False}
assert accounting['charged_seconds'] == '4.886817531'
assert accounting['remaining_seconds'] == '6554.5762973333982'

evidence = A / 'closed_execution'
evidence.mkdir(exist_ok=False)
copies = []
for source, relative in (
    (Path('/tmp/mr3_proxy2d_v26_guard_v1'), 'guard'),
    (Path('/tmp/mr3_proxy2d_v26_outer'), 'main_outer'),
    (Path('/tmp/mr3_proxy2d_v26_final_outer'), 'final_outer'),
    (Path('/tmp/mr3_proxy2d_v26_preflight_outer'), 'preflight_outer'),
    (Path('/tmp/mr3_proxy2d_v26_preflight.json'), 'preflight.json'),
    (Path('/tmp/mr3_proxy2d_v26_final.json'), 'final.json'),
):
    files = sorted(source.rglob('*')) if source.is_dir() else [source]
    for original in files:
        if not original.is_file():
            continue
        destination = evidence / relative
        if source.is_dir():
            destination /= original.relative_to(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = original.read_bytes()
        with destination.open('xb') as stream:
            stream.write(raw)
        assert destination.read_bytes() == original.read_bytes() == raw
        copies.append({'original': str(original), 'copy': str(destination.relative_to(A)),
                       'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
assert len(copies) == 13
saved = {}
for record in copies:
    path = A / record['copy']
    if path.suffix == '.json':
        identities(read(path), saved)
absence = []
for (pid, start), record in sorted(saved.items()):
    row = {'saved_identity': record}
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
    except FileNotFoundError:
        row['status'] = 'gone'
    else:
        assert int(fields[19]) != start, f'saved process still present (including zombie): {pid}'
        row['status'] = 'reused'
    absence.append(row)
assert len(absence) == 7
metadata = A / 'closed_metadata'
metadata.mkdir(exist_ok=False)
write(metadata / 'engineering_accounting_v1.json', accounting)
write(metadata / 'saved_process_absence_v1.json',
      {'passed': True, 'engineering_identities': 5, 'cpu_preflight_identities': 2,
       'total_saved_identities': len(absence), 'records': absence})
write(A / 'evidence_copy_index_v1.json', {'original_files': len(copies),
      'total_bytes': sum(row['bytes'] for row in copies), 'files': copies,
      'originals_and_copies_byte_identical': True})
print(json.dumps({'passed': True, 'original_files': len(copies), 'saved_identities_absent': len(absence),
                  'charge_seconds': str(charge), 'remaining_seconds': accounting['remaining_seconds']}))
