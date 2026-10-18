"""Future finite stock/fixed component probe. Preparation alone executes no child."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

STOCK_SHA = '3581b317ef094f77b6bdab8df122c438ff7a8f8d09154eed7cc5f736e10576cf'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stat(path):
    value = path.stat()
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def exclusive(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def identity(pid):
    try:
        raw = (Path('/proc') / str(pid) / 'stat').read_text()
    except FileNotFoundError:
        return None
    fields = raw.rsplit(') ', 1)[1].split()
    return dict(pid=pid, start_ticks=int(fields[19]), state=fields[0], stat_raw=raw)


def binding_status(row):
    try:
        stable = stat(Path(row['path'])) == row['stat'] and digest(Path(row['path'])) == row['sha256']
        return dict(row, stable=stable)
    except Exception as error:
        return dict(row, stable=False, error=repr(error))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--probe-sha256', required=True)
    parser.add_argument('--stock-library', type=Path, required=True)
    parser.add_argument('--fixed-library', type=Path, required=True)
    parser.add_argument('--fixed-library-sha256', required=True)
    parser.add_argument('--fixed-build-receipt', type=Path, required=True)
    parser.add_argument('--output-directory', type=Path, required=True)
    parser.add_argument('--domain-id', type=int, default=175)
    args = parser.parse_args()
    assert 0 <= args.domain_id <= 232
    assert args.stock_library.name == args.fixed_library.name == 'libvelocity_smoother_core.so'
    assert not os.path.samefile(args.stock_library, args.fixed_library)
    assert digest(args.stock_library) == STOCK_SHA
    assert digest(args.fixed_library) == args.fixed_library_sha256
    assert digest(args.probe) == args.probe_sha256
    assert all(path.is_absolute() for path in (args.probe, args.stock_library, args.fixed_library,
                                               args.fixed_build_receipt, args.output_directory))
    assert all(len(value) == 64 and set(value) <= set('0123456789abcdef') for value in
               (args.probe_sha256, args.fixed_library_sha256))
    sources = [Path(__file__), Path(__file__).with_name('smoother_clock_probe.cpp'),
               Path(__file__).with_name('CMakeLists.txt'), args.probe,
               args.stock_library, args.fixed_library, args.fixed_build_receipt]
    bindings = [dict(path=str(path), sha256=digest(path), stat=stat(path)) for path in sources]
    args.output_directory.mkdir(parents=True, exist_ok=False)
    report = dict(schema='mr3-v25-stock-fixed-smoother-probe-pair-v1', passed=False,
                  utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                  argv=os.sys.argv, cwd=str(Path.cwd()), bindings=bindings, children=[], errors=[],
                  native_or_gazebo_started=0, retry_count=0, signal_count=0,
                  scope='Two finite real ROS component probes; no Gazebo, actor, policy or physics/task/matrix PASS. Stock expected to demonstrate wall-time behavior; fixed expected to demonstrate ROS-clock behavior.')
    started = time.monotonic()
    exclusive(args.output_directory / 'started_v1.json', report)
    try:
        for mode, library in [('stock', args.stock_library), ('fixed', args.fixed_library)]:
            environment = dict(os.environ)
            for name in ('CONDA_PREFIX', 'CONDA_DEFAULT_ENV', 'CONDA_PROMPT_MODIFIER',
                         'CONDA_SHLVL', '_CE_CONDA', '_CE_M'):
                environment.pop(name, None)
            directories = [str(library.parent)] + [item for item in
                           environment.get('LD_LIBRARY_PATH', '').split(':') if item]
            environment.update(LD_LIBRARY_PATH=':'.join(dict.fromkeys(directories)),
                               ROS_DOMAIN_ID=str(args.domain_id), ROS_LOCALHOST_ONLY='1',
                               RMW_IMPLEMENTATION='rmw_fastrtps_cpp',
                               PYTHONNOUSERSITE='1', CUDA_VISIBLE_DEVICES='')
            output = args.output_directory / (mode + '_probe.json')
            command = [str(args.probe), '--mode', mode, '--output', str(output)]
            record = dict(mode=mode, argv=command, expected_library=str(library),
                          expected_library_sha256=digest(library),
                          environment={key: environment.get(key) for key in
                                       ('LD_LIBRARY_PATH', 'ROS_DOMAIN_ID', 'ROS_LOCALHOST_ONLY',
                                        'RMW_IMPLEMENTATION', 'PYTHONNOUSERSITE', 'CUDA_VISIBLE_DEVICES',
                                        'FASTRTPS_DEFAULT_PROFILES_FILE', 'RMW_FASTRTPS_USE_QOS_FROM_XML')},
                          passed=False, stdout=str(args.output_directory / (mode + '.stdout')),
                          stderr=str(args.output_directory / (mode + '.stderr')))
            report['children'].append(record)
            before = time.monotonic()
            with Path(record['stdout']).open('xb') as stdout, Path(record['stderr']).open('xb') as stderr:
                process = subprocess.Popen(command, env=environment, stdout=stdout, stderr=stderr)
                record['identity_at_spawn'] = identity(process.pid)
                # No parent timeout/signal. The child has a cooperative steady work guard
                # and records any >15s natural-close outcome as failure.
                record['returncode'] = process.wait()
            record['wall_seconds'] = time.monotonic() - before
            record['identity_after_wait'] = identity(process.pid)
            for channel in ('stdout', 'stderr'):
                record[channel + '_sha256'] = digest(Path(record[channel]))
            value = json.loads(output.read_bytes())
            record['result'] = dict(path=str(output), sha256=digest(output),
                                    passed=value['passed'], normal_cleanup=value['normal_cleanup'])
            assert value['process_id'] == process.pid and value['mode'] == mode
            assert os.path.samefile(value['loaded_library_path'], library)
            mapped = []
            for line in value['process_maps_at_start'].splitlines():
                fields = line.split(None, 5)
                if len(fields) == 6 and fields[5].startswith('/'):
                    candidate = Path(fields[5])
                    if candidate.exists() and os.path.samefile(candidate, library):
                        mapped.append(line)
            assert mapped, 'actual selected ELF absent from process maps'
            record['actual_library_maps'] = mapped
            assert value['timer_is_steady_after_activate'] is (mode == 'stock')
            assert value['timer_is_steady_after_frequency_change'] is (mode == 'stock')
            assert record['returncode'] == 0 and value['passed'] is True
            assert value['normal_cleanup'] is True and value['wall_seconds'] <= 15.
            assert record['wall_seconds'] <= 15.
            saved = record['identity_at_spawn']
            assert saved is not None
            after = record['identity_after_wait']
            assert after is None or after['start_ticks'] != saved['start_ticks']
            record['passed'] = True
        assert sum(row['wall_seconds'] for row in report['children']) <= 30.
        for row in bindings:
            path = Path(row['path'])
            assert stat(path) == row['stat'] and digest(path) == row['sha256']
        report['passed'] = True
    except Exception as error:
        report['errors'].append(repr(error))
        if len(report['children']) < 2:
            report['fixed_skipped_after_failed_stock'] = True
    finally:
        report['wall_seconds'] = time.monotonic() - started
        report['actual_probe_child_wall_seconds'] = sum(row.get('wall_seconds', 0.) for row in report['children'])
        report['compile_wall_seconds_included'] = False
        report['source_and_library_checks_final'] = [binding_status(row) for row in bindings]
        if not all(row['stable'] for row in report['source_and_library_checks_final']):
            report['passed'] = False
            report['errors'].append('source/library binding changed during probe pair')
        exclusive(args.output_directory / 'execution_v1.json', report)
    print(json.dumps(dict(passed=report['passed'], execution=str(args.output_directory / 'execution_v1.json'))))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
