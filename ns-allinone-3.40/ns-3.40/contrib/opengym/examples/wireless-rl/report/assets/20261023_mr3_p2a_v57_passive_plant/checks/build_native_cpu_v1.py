"""Actual CPU-only generator/compiler receipts and opaque ELF custody. No ELF run."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261023_mr3_p2a_v57_passive_plant'
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
CPP = A / 'passive_plant_v1.cpp'
GENERATOR = A / 'prepare_passive_plant_v1.py'
HEADER = ROS / 'src/multi_robot/include/multi_robot/paired_wheel_slew.hpp'
BUILD = Path('/tmp/mr3_p2a_v57_build_v1')
ELF = BUILD / 'passive_plant_v1'


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def proof(path):
    path = Path(path)
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    if any(getattr(before, key) != getattr(after, key) for key in fields):
        raise ValueError('source changed while hashing: ' + str(path))
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def actual_cpu(name, command, sources):
    output = A / 'checks' / name
    argv = ['/usr/bin/python3', '-B', '-m', 'mr3_learning.reach_execution',
            '--output', str(output), '--scope', 'cpu']
    argv += [part for source in sources for part in ('--source', str(source))]
    argv += ['--', *command]
    started = time.monotonic_ns()
    with (A / 'checks' / (name + '_wrapper_stdout.log')).open('x') as console:
        child = subprocess.Popen(argv, cwd=W, env=os.environ.copy(), stdout=console,
                                 stderr=subprocess.STDOUT)
        while True:
            try:
                rc = child.wait()
                break
            except BaseException:
                continue
    ended = time.monotonic_ns()
    value = json.loads((output / 'actual_wait.json').read_text())
    write(A / 'checks' / (name + '_parent_wait.json'), {
        'argv': argv, 'started_monotonic_ns': started, 'ended_monotonic_ns': ended,
        'actual_returncode': rc, 'actual_waited': True,
        'scope': 'cpu', 'native_world_runs': 0})
    if (rc != 0 or value.get('passed') is not True or value.get('actual_waited') is not True
            or value.get('actual_returncode') != 0 or value.get('errors') != []
            or value.get('actual_argv') != command
            or value.get('source_before') != value.get('source_after')):
        raise ValueError(name + ' actual CPU failed; original receipts preserved')
    return output / 'actual_wait.json'


def main():
    BUILD.mkdir(exist_ok=False)
    compiler = Path('/usr/bin/g++')
    pkg_config = Path('/usr/bin/pkg-config')
    flags_raw = subprocess.check_output([str(pkg_config), '--cflags', '--libs', 'gazebo'], text=True)
    version = subprocess.check_output([str(pkg_config), '--modversion', 'gazebo'], text=True).strip()
    compiler_version = subprocess.check_output([str(compiler), '--version'], text=True)
    sources = [CPP, GENERATOR, HEADER, Path(__file__).resolve()]
    sources += [W / 'mr3_learning' / name for name in (
        'reach_execution.py', 'preparation.py', 'native_custody.py',
        'supervisor.py', 'ipc.py', '__init__.py')]
    sources += [compiler.resolve(), pkg_config.resolve(),
                Path('/usr/include/gazebo-11/gazebo/gazebo.hh'),
                Path('/usr/include/gazebo-11/gazebo/physics/PhysicsEngine.hh'),
                Path('/usr/include/gazebo-11/gazebo/physics/ode/ODEPhysics.hh')]
    sources = list(dict.fromkeys(sources))
    before = [proof(path) for path in sources]
    prepare_command = ['/usr/bin/python3', '-B', str(GENERATOR), '--output', str(A / 'prepared_worlds_v1')]
    actual_cpu('prepare_cpu_v1', prepare_command, sources)
    command = [str(compiler), '-std=c++17', '-O2', str(CPP),
               '-I' + str(ROS / 'src/multi_robot/include')]
    command += shlex.split(flags_raw) + ['-std=c++17', '-o', str(ELF)]
    write(A / 'checks/build_entry_v1.json', {
        'schema': 'mr3-v57-actual-compile-entry-v1', 'cwd': str(W),
        'compiler_argv': command, 'pkg_config_gazebo_flags': flags_raw,
        'pkg_config_gazebo_version': version, 'compiler_version': compiler_version,
        'elf': str(ELF), 'world_runs': 0, 'source_before': before})
    actual_wait = actual_cpu('compile_cpu_v1', command, sources)
    if ELF.read_bytes()[:4] != b'\x7fELF' or not os.access(ELF, os.X_OK):
        raise ValueError('compiler did not produce executable ELF')
    loader_env = {'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
                  'LD_LIBRARY_PATH': '/opt/ros/humble/lib:/opt/ros/humble/lib/x86_64-linux-gnu'}
    ldd_command = ['/usr/bin/ldd', str(ELF)]
    ldd = subprocess.run(ldd_command, env=loader_env, capture_output=True, text=True)
    write(A / 'checks/ldd_receipt_v1.json', {
        'argv': ldd_command, 'environment': loader_env, 'actual_returncode': ldd.returncode,
        'stdout': ldd.stdout, 'stderr': ldd.stderr, 'loader_only': True, 'world_runs': 0})
    if ldd.returncode != 0 or 'not found' in ldd.stdout:
        raise ValueError('ELF shared-library loader readiness failed')
    paths = []
    for line in ldd.stdout.splitlines():
        match = re.search(r'=>\s+(/\S+)\s+\(', line) or re.match(r'\s*(/\S+)\s+\(', line)
        if match:
            paths.append(Path(match.group(1)))
    if not paths:
        raise ValueError('no shared libraries recorded')
    libraries = [proof(path) for path in sorted(set(paths))]
    raw = ELF.read_bytes()
    packed = A / 'native/passive_plant_v1.elf.gz'
    with packed.open('xb') as target:
        with gzip.GzipFile(fileobj=target, mode='wb', filename='', mtime=0) as stream:
            stream.write(raw)
    if gzip.decompress(packed.read_bytes()) != raw:
        raise ValueError('opaque ELF gzip bytes differ')
    after = [proof(path) for path in sources]
    if before != after or libraries != [proof(Path(row['path'])) for row in libraries]:
        raise ValueError('source or linked library bytes changed')
    packed_ref = proof(packed)
    packed_ref.update(raw_bytes=len(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
    manifest = {'schema': 'mr3-v57-native-build-manifest-v1', 'passed': True,
        'build_entry': proof(A / 'checks/build_entry_v1.json'), 'actual_wait': proof(actual_wait),
        'elf': proof(ELF), 'archived_elf_gzip': packed_ref,
        'compiled_sources': [proof(CPP), proof(HEADER)], 'source_unchanged': True,
        'source_before': before, 'source_after': after,
        'gazebo_version': version, 'compiler_version': compiler_version,
        'shared_libraries': libraries, 'ldd_receipt': proof(A / 'checks/ldd_receipt_v1.json'),
        'world_runs': 0, 'native_qualification_credit': False}
    write(A / 'checks/build_manifest_v1.json', manifest)
    print(json.dumps({'passed': True, 'manifest': str(A / 'checks/build_manifest_v1.json'),
                      'shared_libraries': len(libraries), 'world_runs': 0}))


if __name__ == '__main__':
    main()
