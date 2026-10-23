"""Compile and execute only the isolated encoder helper CPU fixtures; no Gazebo."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from mr3_learning.preparation import identity

ROOT = Path('/home/zhuyulab/ns3-workspace')
A = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261023_mr3_p2a_v58_encoder_hold'
OUT = Path('/tmp/mr3_p2a_v58_helper_cpu_v1')
OUT.mkdir(exist_ok=False)
compiler = Path('/usr/bin/g++').resolve(strict=True)
binary = OUT / 'test_initial_zero_encoder_servo_v1'

def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write('\n')

def run(label, argv):
    started = time.monotonic_ns()
    child = subprocess.Popen(argv)
    observed = identity(child.pid)
    errors = []
    while True:
        try:
            rc = child.wait()
            break
        except BaseException as error:
            errors.append(repr(error))
    ended = time.monotonic_ns()
    row = {'argv': argv, 'identity': observed, 'actual_waited': True,
           'actual_returncode': rc, 'errors': errors,
           'started_monotonic_ns': started, 'ended_monotonic_ns': ended}
    write(OUT / (label + '.json'), row)
    if rc != 0 or errors:
        raise SystemExit(rc if rc else 1)
    return row

compile_argv = [str(compiler), '-std=c++17', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic',
    '-I' + str(ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/include'),
    str(A / 'test_initial_zero_encoder_servo_v1.cpp'), '-o', str(binary)]
compile_receipt = run('compile', compile_argv)
fixture_receipt = run('fixtures', [str(binary)])
raw = binary.read_bytes()
write(OUT / 'summary.json', {'passed': True, 'World_runs': 0, 'physical_credit': False,
      'fixture_groups': 12, 'compile': compile_receipt, 'fixtures': fixture_receipt,
      'binary': {'path': str(binary), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()},
      'driver_identity': identity(os.getpid())})
print(json.dumps({'helper_cpu_passed': True, 'fixture_groups': 12, 'World_runs': 0}))
