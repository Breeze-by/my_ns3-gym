"""Finite parallel CPU-only closed comparisons, actual wait of every child."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
OUT = Path('/tmp/mr3_information_combined_candidate_closed_v2')
ENTRY = Path('/tmp/mr3_information_combined_candidate_v2.py')
FREEZE = '92f8bdf5bba1ba245dc53ca0964eef81a7fff938'
STAGES = ('interface', 'terminal', 'reset', 'deadline')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(pid):
    try:
        path = Path('/proc') / str(pid)
        fields = (path / 'stat').read_text().rsplit(')', 1)[1].split()
        return {'pid': pid, 'start_ticks': int(fields[19]), 'parent_pid': int(fields[1]),
                'state': fields[0], 'actual_argv': (path / 'cmdline').read_bytes().decode().rstrip('\0').split('\0')}
    except (OSError, IndexError, ValueError):
        return None


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def run_stage(stage):
    directory = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0' / ('mr3_p2a0_20261018_v26_' + stage)
    reference = Path('/tmp') / ('mr3_p2a0_v26_' + stage + '_information_review_v1.json')
    if stage == 'deadline':
        reference = Path('/tmp/mr3_p2a0_v26_deadline_information_supplemental_v1.json')
    output, receipt = OUT / (stage + '_report.json'), OUT / (stage + '_equivalence.json')
    argv = ['/usr/bin/python3', '-B', str(ENTRY), str(directory), '--freeze', FREEZE,
            '--reference', str(reference), '--output', str(output), '--receipt', str(receipt)]
    started = time.monotonic_ns()
    submission_receipt_error = None
    with (OUT / (stage + '_console.log')).open('x') as console:
        process = subprocess.Popen(argv, stdout=console, stderr=subprocess.STDOUT)
        try:
            saved = identity(process.pid)
            write(OUT / (stage + '_submitted.json'), {'actual_argv': argv, 'process_identity': saved,
                  'started_wall_monotonic_ns': started, 'entry_sha256': ENTRY_SHA})
        except Exception as exc:
            submission_receipt_error = repr(exc)
        finally:
            code = process.wait()
    ended = time.monotonic_ns()
    row = {'stage': stage, 'actual_argv': argv, 'process_identity': saved,
           'actual_wait_returncode': code, 'started_wall_monotonic_ns': started,
           'ended_wall_monotonic_ns': ended, 'actual_wall_seconds': str((ended - started) / 10**9),
           'output': str(output), 'receipt': str(receipt), 'output_present': output.exists(),
           'receipt_present': receipt.exists(), 'entry_source_stable_end': sha(ENTRY) == ENTRY_SHA}
    row['submission_receipt_error'] = submission_receipt_error
    if receipt.exists():
        value = json.loads(receipt.read_text())
        row.update(all_report_fields_deep_equal=value['all_report_fields_deep_equal'],
                   serialized_report_bytes_equal=value['serialized_report_bytes_equal'],
                   candidate_report_passed=value['candidate_report_passed'],
                   equivalence_passed=value['passed'])
    write(OUT / (stage + '_actual_wait.json'), row)
    print(json.dumps(row), flush=True)
    return row


OUT.mkdir(exist_ok=False)
STARTED = time.monotonic_ns()
ENTRY_SHA = sha(ENTRY)
RUNNER_SHA = sha(__file__)
write(OUT / 'owner_observation.json', {'schema': 'mr3-information-combined-owner-v2',
      'identity': identity(os.getpid()), 'observed_wall_monotonic_ns': STARTED,
      'runner_sha256': RUNNER_SHA, 'entry_sha256': ENTRY_SHA,
      'scope': 'Actual current CPU owner identity, not a completion receipt.'})
rows = {}
with ThreadPoolExecutor(max_workers=4) as executor:
    submitted = {executor.submit(run_stage, stage): stage for stage in STAGES}
    for future in as_completed(submitted):
        stage = submitted[future]
        try:
            rows[stage] = future.result()
        except Exception as exc:
            rows[stage] = {'stage': stage, 'passed': False, 'error': repr(exc),
                           'actual_wait_returncode': None,
                           'scope': 'No returncode invented for a wrapper exception; inspect submitted receipt and original files.'}
ENDED = time.monotonic_ns()
passed = all(rows[stage].get('actual_wait_returncode') == 0
             and rows[stage].get('equivalence_passed') is True
             and rows[stage].get('submission_receipt_error') is None
             and rows[stage].get('entry_source_stable_end') is True for stage in STAGES)
result = {'schema': 'mr3-information-combined-four-closed-equivalence-v2',
          'passed': passed and sha(__file__) == RUNNER_SHA,
          'stages': [rows[stage] for stage in STAGES], 'parallel_children': 4,
          'started_wall_monotonic_ns': STARTED, 'ended_wall_monotonic_ns': ENDED,
          'actual_wall_seconds': str((ENDED - STARTED) / 10**9),
          'runner_source_stable_end': sha(__file__) == RUNNER_SHA,
          'scope': 'Four new CPU-only implementations compare complete original mathematical reports including all input SHA bindings. No original reader rerun, native call, V11 repair credit, or future admission inferred.'}
write(OUT / 'summary.json', result)
raise SystemExit(0 if result['passed'] else 1)
