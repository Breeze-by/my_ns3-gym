"""Four saved-input CPU comparisons; no original reader or native run is started."""
import hashlib
import json
from pathlib import Path
import subprocess
import time

OUT = Path('/tmp/mr3_information_three_key_candidate_closed_v1')
ROOT = Path('/home/zhuyulab/ns3-workspace')
ENTRY = Path('/tmp/mr3_information_three_key_candidate_v1.py')
FREEZE = '92f8bdf5bba1ba245dc53ca0964eef81a7fff938'


def identity(pid):
    try:
        fields = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': pid, 'start_ticks': int(fields[19]), 'parent': int(fields[1]), 'state': fields[0]}
    except (OSError, IndexError, ValueError):
        return None


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


OUT.mkdir(exist_ok=False)
rows = []
failed = False
for stage in ('interface', 'terminal', 'reset', 'deadline'):
    if failed:
        rows.append({'stage': stage, 'status': 'SKIPPED', 'reason': 'prior_equivalence_failure'})
        continue
    directory = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0' / ('mr3_p2a0_20261018_v26_' + stage)
    reference = Path('/tmp') / ('mr3_p2a0_v26_' + stage + '_information_review_v1.json')
    if stage == 'deadline':
        reference = Path('/tmp/mr3_p2a0_v26_deadline_information_supplemental_v1.json')
    report, receipt = OUT / (stage + '_report.json'), OUT / (stage + '_equivalence.json')
    argv = ['/usr/bin/python3', '-B', str(ENTRY), str(directory), '--freeze', FREEZE,
            '--reference', str(reference), '--output', str(report), '--receipt', str(receipt)]
    started = time.monotonic_ns()
    with (OUT / (stage + '_console.log')).open('x') as console:
        process = subprocess.Popen(argv, stdout=console, stderr=subprocess.STDOUT)
        saved = identity(process.pid)
        code = process.wait()
    ended = time.monotonic_ns()
    row = {'stage': stage, 'actual_argv': argv, 'entry_sha256': sha(ENTRY),
           'process_identity': saved, 'actual_wait_returncode': code,
           'started_wall_monotonic_ns': started, 'ended_wall_monotonic_ns': ended,
           'actual_wall_seconds': str((ended - started) / 10**9),
           'output': str(report), 'receipt': str(receipt),
           'output_present': report.exists(), 'receipt_present': receipt.exists()}
    if receipt.exists():
        value = json.loads(receipt.read_text())
        row.update(all_report_fields_deep_equal=value['all_report_fields_deep_equal'],
                   serialized_report_bytes_equal=value['serialized_report_bytes_equal'],
                   candidate_report_passed=value['candidate_report_passed'])
    failed = code != 0 or row.get('all_report_fields_deep_equal') is not True
    rows.append(row)
    with (OUT / (stage + '_actual_wait.json')).open('x') as stream:
        json.dump(row, stream, indent=2)
        stream.write('\n')
    print(json.dumps(row), flush=True)
result = {'schema': 'mr3-information-three-key-four-closed-equivalence-v1', 'stages': rows,
          'passed': not failed and len(rows) == 4,
          'scope': 'Offline CPU comparisons on original V26 frozen native inputs against saved original reports. Actual new entry provenance is in every equivalence receipt. Never credit current V11 or future native runs.'}
with (OUT / 'summary.json').open('x') as stream:
    json.dump(result, stream, indent=2)
    stream.write('\n')
raise SystemExit(1 if failed else 0)
