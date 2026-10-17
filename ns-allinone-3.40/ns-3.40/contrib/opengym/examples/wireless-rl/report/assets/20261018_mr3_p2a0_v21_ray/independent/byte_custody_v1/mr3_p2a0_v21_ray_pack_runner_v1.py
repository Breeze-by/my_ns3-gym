#!/usr/bin/python3
"""Execute fixed closed V21 custody twice, sequentially; no retry/timeout/signal."""
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
HELPER = Path('/tmp/mr3_p2a0_v21_ray_pack_closed_v1.py')
EXECUTION = Path('/tmp/mr3_p2a0_v21_ray_execution_v1.json')
TARGET = Path('/tmp/mr3_p2a0_v21_ray_selected_v1')
A21 = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v21_ray'
OUT = Path('/tmp/mr3_p2a0_v21_ray_pack_execution_v1.json')
ENV = {'PATH': '/usr/bin:/bin', 'PYTHONNOUSERSITE': '1',
       'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'C.UTF-8',
       'LC_ALL': 'C.UTF-8', 'TZ': 'UTC'}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    helper_before = HELPER.read_bytes()
    assert sha(helper_before) == 'becd6aeb9a0d58d34adbb446cade8eff3477d04c5b477d5ac9ff602275f2af6c'
    execution_before = EXECUTION.read_bytes()
    assert sha(execution_before) == 'a490a7157268537eafc232d8e73149d17873e515b1e14d7f01db4db1bb666c2a'
    assert not TARGET.exists() and not OUT.exists()
    jobs = [
        ('native', ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v21_ray',
         TARGET / 'native/iters150', A21 + '/native/iters150'),
        ('sensor_capture', Path('/tmp/mr3_p2a0_v21_ray_capture_v1'),
         TARGET / 'sensor_capture', A21 + '/sensor_capture')]
    records = []
    started = time.monotonic()
    for kind, source, target, prospective in jobs:
        argv = ['/usr/bin/python3', '-B', str(HELPER), '--source', str(source),
                '--target', str(target), '--prospective-prefix', prospective,
                '--execution', str(EXECUTION), '--source-kind', kind]
        stdout = Path('/tmp/mr3_p2a0_v21_ray_pack_' + kind + '_v1.stdout.log')
        stderr = Path('/tmp/mr3_p2a0_v21_ray_pack_' + kind + '_v1.stderr.log')
        prior = resource.getrusage(resource.RUSAGE_CHILDREN)
        begin = time.monotonic()
        with stdout.open('xb') as output, stderr.open('xb') as error:
            child = subprocess.Popen(argv, cwd=ROOT, env=ENV, stdout=output, stderr=error)
            pid = child.pid
            stat = Path('/proc') / str(pid) / 'stat'
            try:
                start_stat_raw = stat.read_text()
            except FileNotFoundError:
                start_stat_raw = None
            code = child.wait()
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        row = {'source_kind': kind, 'argv': argv, 'cwd': str(ROOT), 'environment_exact': ENV,
               'pid': pid, 'initial_stat_raw': start_stat_raw,
               'exit_code': code, 'wall_seconds': time.monotonic() - begin,
               'cpu_seconds': {'user': after.ru_utime - prior.ru_utime,
                               'system': after.ru_stime - prior.ru_stime},
               'stdout': {'path': str(stdout), 'sha256': sha(stdout.read_bytes())},
               'stderr': {'path': str(stderr), 'sha256': sha(stderr.read_bytes())},
               'target': str(target), 'prospective_prefix': prospective}
        manifest = target / 'manifest.json'
        if manifest.exists():
            raw = manifest.read_bytes()
            value = json.loads(raw)
            row['manifest'] = {'path': str(manifest), 'sha256': sha(raw),
                               'passed': value['passed'], 'source_files': value['source_files'],
                               'raw_bytes': value['raw_bytes'], 'selected_bytes': value['selected_bytes'],
                               'selected_parts': value['selected_parts'],
                               'largest_encoded_part_bytes': value['largest_encoded_part_bytes']}
        records.append(row)
        print(json.dumps(row), flush=True)
        if code != 0:
            break
    result = {'schema': 'mr3-v21-lossless-custody-execution-v1',
              'passed': len(records) == 2 and all(row['exit_code'] == 0 for row in records),
              'scope': 'Lossless closed-run byte custody only; no new native/formal or changed original verdict.',
              'helper': {'path': str(HELPER), 'sha256': sha(helper_before),
                         'before_after_equal': HELPER.read_bytes() == helper_before},
              'original_execution': {'path': str(EXECUTION), 'sha256': sha(execution_before),
                                      'before_after_equal': EXECUTION.read_bytes() == execution_before},
              'runner_source_sha256': sha(Path(__file__).read_bytes()),
              'jobs': records, 'wall_seconds': time.monotonic() - started,
              'no_signals_timeout_or_retry': True, 'no_canonical_mutation': True,
              'native_or_formal_rerun': False}
    with OUT.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'output': str(OUT),
                      'sha256': sha(OUT.read_bytes()), 'wall_seconds': result['wall_seconds']}), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
