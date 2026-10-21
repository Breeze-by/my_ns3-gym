"""Finite build and actual-library probe; no ROS or simulator backend."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

A = Path(__file__).resolve().parent
ROOT = next(p for p in A.parents if (p / '.git').exists())
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
SDK = ROS / 'src/slam_toolbox/lib/karto_sdk'
LIB = (ROS / 'build/slam_toolbox/lib/karto_sdk/libkartoSlamToolbox.so').resolve()


def sha(path):
    raw = path.read_bytes()
    return {'path': str(path.resolve()), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def identity(pid):
    raw = (Path('/proc') / str(pid) / 'stat').read_text()
    fields = raw.rsplit(')', 1)[1].split()
    return {'pid': pid, 'parent': int(fields[1]), 'group': int(fields[2]),
            'session': int(fields[3]), 'start_ticks': int(fields[19])}


def phase(name, command, output, errors, limit, env):
    start = time.monotonic_ns()
    saved, signals, identity_error, reap_overrun = None, [], None, False
    with output.open('xb') as stdout, errors.open('xb') as stderr:
        child = subprocess.Popen(command, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                                 start_new_session=True)
        try:
            saved = identity(child.pid)
        except Exception as error:
            identity_error = repr(error)  # Always actually wait, even if capture failed.
        try:
            code = child.wait(timeout=limit)
        except subprocess.TimeoutExpired:
            for sig, wait in ((signal.SIGTERM, 3), (signal.SIGKILL, 3)):
                try:
                    os.killpg(child.pid, sig)
                    signals.append(int(sig))
                except ProcessLookupError:
                    pass
                try:
                    code = child.wait(timeout=wait)
                    break
                except subprocess.TimeoutExpired:
                    continue
            else:
                reap_overrun = True
                code = child.wait()  # Never abandon the owned child to meet a deadline.
    end = time.monotonic_ns()
    return {'name': name, 'argv': command, 'cwd': str(ROOT), 'child_pid': child.pid,
            'saved_identity': saved, 'returncode': code, 'actual_waited': True,
            'identity_capture_error': identity_error,
            'reap_overrun': reap_overrun,
            'started_ns': start, 'ended_ns': end, 'signals': signals,
            'stdout': sha(output), 'stderr': sha(errors)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', required=True, type=Path)
    parser.add_argument('--evidence-dir', required=True, type=Path)
    args = parser.parse_args()
    args.build_dir.mkdir(parents=True, exist_ok=False)
    E = args.evidence_dir.resolve()
    assert E.is_relative_to(A)
    E.mkdir(parents=True, exist_ok=False)
    sources = [A / 'karto_kernel_probe_v1.cpp', A / 'predeclared_plan_v1.json', Path(__file__), LIB]
    sources += sorted((SDK / 'include/karto_sdk').glob('*.h'))
    sources += sorted((SDK / 'include/karto_sdk').glob('*.hpp'))
    compiler = Path('/usr/bin/g++').resolve()
    sources.append(compiler)
    before = [sha(path) for path in sources]
    env = dict(os.environ, PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
               PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1', CUDA_VISIBLE_DEVICES='')
    for key in ('LD_LIBRARY_PATH', 'LD_PRELOAD', 'PYTHONPATH', 'PYTHONHOME', 'LIBRARY_PATH',
                'CPATH', 'CPLUS_INCLUDE_PATH', 'C_INCLUDE_PATH'):
        env.pop(key, None)
    binary = args.build_dir.resolve() / 'karto_kernel_probe'
    command = [str(compiler), '-std=c++17', '-O1', '-I' + str(SDK / 'include'),
               '-I/usr/include/eigen3', str(A / 'karto_kernel_probe_v1.cpp'),
               str(LIB), '-lboost_serialization', '-ltbb', '-Wl,-rpath,' + str(LIB.parent),
               '-o', str(binary)]
    result = {'schema': 'mr3-p2a-v29-karto-cpu-build-v1', 'passed': False, 'phases': [],
              'source_before': before, 'compiler_version': subprocess.check_output(
                  [str(compiler), '--version'], env=env, text=True),
              'new_engineering_seconds': '0', 'production_enabled': False,
              'qualification': False, 'training_eligible': False, 'native_credit': False}
    try:
        build = phase('compile', command, E / 'compile_stdout.log', E / 'compile_stderr.log', 90, env)
        result['phases'].append(build)
        if build['returncode'] != 0 or build['signals'] or build['identity_capture_error']:
            raise RuntimeError('CPU probe compilation failed')
        result['binary'] = sha(binary)
        result['elf_dynamic'] = subprocess.check_output(['/usr/bin/readelf', '-d', str(binary)],
                                                        env=env, text=True)
        run = phase('probe', [str(binary)], E / 'kernel_result_v1.json', E / 'probe_stderr.log', 20, env)
        result['phases'].append(run)
        if run['returncode'] != 0 or run['signals'] or run['identity_capture_error']:
            raise RuntimeError('CPU library probe failed')
        probe = json.loads((E / 'kernel_result_v1.json').read_text())
        assert probe['passed'] is True
        loaded = {Path(path).resolve() for path in probe['loaded_karto_paths']}
        assert loaded == {LIB}, ('unexpected Karto ELF', loaded)
        assert probe['identity']['pid'] == run['child_pid']
        assert probe['identity'] == run['saved_identity']
        result['probe_identity'] = probe['identity']
        result['passed'] = True
    except Exception as error:
        result['error'] = repr(error)
    result['source_after'] = [sha(path) for path in sources]
    result['source_unchanged'] = result['source_before'] == result['source_after']
    result['passed'] &= result['source_unchanged']
    with (E / 'build_receipt_v1.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'phases': len(result['phases']),
                      'source_unchanged': result['source_unchanged'], 'error': result.get('error')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
