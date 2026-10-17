#!/usr/bin/env python3
"""Lossless closed-run byte custody only. No canonical write, audit or native run."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import sys
import time
import zlib

RAW_CHUNK_BYTES = 32 * 1024 * 1024
COPY_BYTES = 1024 * 1024
MAX_ENCODED_BYTES = 100000000
COMPRESSION_LEVEL = 6
WORKERS = 2


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def identity(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def file_digest(path, decoded=False):
    checksum, size = hashlib.sha256(), 0
    with (gzip.open if decoded else open)(path, 'rb') as stream:
        for block in iter(lambda: stream.read(COPY_BYTES), b''):
            checksum.update(block)
            size += len(block)
    return size, checksum.hexdigest()


def verify_file(row, target):
    checksum, size = hashlib.sha256(), 0
    offset = 0
    for index, piece in enumerate(row['parts']):
        assert piece['index'] == index and piece['raw_offset'] == offset
        selected = target / piece['selected']
        assert selected.stat().st_size < MAX_ENCODED_BYTES
        assert file_digest(selected) == (piece['selected_bytes'], piece['selected_sha256'])
        part_sha, part_size = hashlib.sha256(), 0
        with gzip.open(selected, 'rb') as stream:
            for block in iter(lambda: stream.read(COPY_BYTES), b''):
                checksum.update(block)
                part_sha.update(block)
                size += len(block)
                part_size += len(block)
        assert (part_size, part_sha.hexdigest()) == (piece['raw_bytes'], piece['raw_sha256'])
        assert part_size <= RAW_CHUNK_BYTES
        if index < len(row['parts']) - 1:
            assert part_size == RAW_CHUNK_BYTES
        offset += part_size
    assert (size, checksum.hexdigest()) == (row['raw_bytes'], row['raw_sha256'])
    return {'decoded_bytes': size, 'reassembled_decoded_sha256': checksum.hexdigest(),
            'all_part_encoded_and_decoded_sha_verified': True}


def pack_file(index, path, source, target, initial, prospective):
    before = path.lstat()
    assert stat.S_ISREG(before.st_mode) and identity(before) == initial
    relative = path.relative_to(source).as_posix()
    whole = hashlib.sha256()
    parts = []
    total = 0
    with path.open('rb') as original:
        assert identity(os.fstat(original.fileno())) == initial
        # One empty gzip is retained for an empty original. Otherwise boundaries
        # depend only on the predeclared raw32MiB limit, never compression ratio.
        for part_index in range(max(1, (before.st_size + RAW_CHUNK_BYTES - 1) // RAW_CHUNK_BYTES)):
            selected_relative = f'blobs/{index:06d}/part{part_index:06d}.gz'
            selected = target / selected_relative
            selected.parent.mkdir(parents=True, exist_ok=True)
            piece_sha, piece_bytes = hashlib.sha256(), 0
            with selected.open('xb') as output:
                with gzip.GzipFile(filename='', mode='wb', fileobj=output,
                                   compresslevel=COMPRESSION_LEVEL, mtime=0) as encoded:
                    remaining = min(RAW_CHUNK_BYTES, before.st_size - total)
                    while remaining:
                        block = original.read(min(COPY_BYTES, remaining))
                        assert block, 'source ended before declared original size'
                        whole.update(block)
                        piece_sha.update(block)
                        encoded.write(block)
                        piece_bytes += len(block)
                        remaining -= len(block)
            size, encoded_sha = file_digest(selected)
            assert size < MAX_ENCODED_BYTES, 'encoded part exceeds strict100MB limit'
            parts.append({'index': part_index, 'raw_offset': total, 'raw_bytes': piece_bytes,
                          'raw_sha256': piece_sha.hexdigest(), 'encoding': 'gzip',
                          'selected': selected_relative, 'selected_bytes': size,
                          'selected_sha256': encoded_sha,
                          'prospective_canonical': prospective + '/' + selected_relative})
            total += piece_bytes
        assert original.read(1) == b'', 'source grew beyond original size'
        after_fd = identity(os.fstat(original.fileno()))
    after_path = identity(path.lstat())
    assert initial == after_fd == after_path
    assert total == before.st_size
    row = {'source': str(path), 'relative_path': relative, 'source_stat_initial': initial,
           'source_stat_final': after_path, 'source_mode': stat.S_IMODE(before.st_mode),
           'source_uid': before.st_uid, 'source_gid': before.st_gid,
           'raw_bytes': total, 'raw_sha256': whole.hexdigest(), 'empty_original': total == 0,
           'encoding': 'gzip' if len(parts) == 1 else 'ordered_gzip_raw_byte_chunks',
           'parts': parts}
    row['verification'] = verify_file(row, target)
    return row


def inventory(source):
    files, directories = [], []
    assert source.is_dir() and not source.is_symlink()
    for path in sorted(source.rglob('*')):
        value = path.lstat()
        assert not stat.S_ISLNK(value.st_mode), 'source symlink not followed: ' + str(path)
        if stat.S_ISDIR(value.st_mode):
            directories.append({'relative_path': path.relative_to(source).as_posix(),
                                'mode': stat.S_IMODE(value.st_mode)})
        else:
            assert stat.S_ISREG(value.st_mode), 'unsupported nonregular original: ' + str(path)
            files.append((path, identity(value)))
    return files, directories


ROOT = Path('/home/zhuyulab/ns3-workspace')
FIXED_FREEZE = '099a8eeaa00676f7e6e00d7f5ef51294aac5edcb'
FIXED_RUN = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261018_v21_ray'
FIXED_CAPTURE = Path('/tmp/mr3_p2a0_v21_ray_capture_v1')
FIXED_EXECUTION = Path('/tmp/mr3_p2a0_v21_ray_execution_v1.json')
A21 = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v21_ray'


def validate_selection(source, target, prospective, execution_path, source_kind):
    expected = {'native': (FIXED_RUN, A21 + '/native/iters150'),
                'sensor_capture': (FIXED_CAPTURE, A21 + '/sensor_capture')}
    assert type(source_kind) is str and source_kind in expected
    fixed_source, fixed_prospective = expected[source_kind]
    assert source == fixed_source and prospective == fixed_prospective
    assert execution_path == FIXED_EXECUTION
    assert target.is_absolute() and target.is_relative_to(Path('/tmp'))
    assert target != source and not target.is_relative_to(source)


def validate_execution_identity(execution):
    assert execution['schema'] == 'mr3-startup-sensor-execution-v1'
    assert execution['status'] == 'completed' and execution['stage'] == 'iters150'
    assert execution['freeze'] == FIXED_FREEZE
    assert type(execution['passed']) is bool
    assert type(execution['capture_process_completed']) is bool
    assert type(execution['strict_native_closure_passed']) is bool
    assert execution['benchmark_summary']['path'] == str(FIXED_RUN / 'benchmark_summary.json')
    expected_episode = FIXED_RUN / 'worker0/episode001_open_101'
    assert execution['actual_workload']['protocol']['path'] == str(expected_episode / 'transitions.jsonl')
    assert execution['recorder_final']['path'] == str(FIXED_CAPTURE / 'final.json')
    ray = execution['ray_measurement_availability']
    assert type(ray['passed']) is bool and type(ray['robots']) is dict
    assert set(ray['robots']) == {'tb1', 'tb2', 'tb3'}
    for robot, row in ray['robots'].items():
        assert type(row['passed']) is bool
        assert row['path'] == str(expected_episode / ('ray_' + robot + '.jsonl'))
        assert type(row['process_id']) is int and row['process_id'] > 0
        assert row['sensor_identity'] == {
            'parent': robot + '::base_scan',
            'scoped_name': 'p1c_open::' + robot + '::base_scan::hls_lfcd_lds'}
        assert type(row['scans']) is int and row['scans'] >= 0
        assert type(row['configuration']) is int and type(row['sensor_connected']) is int
    return ray


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--prospective-prefix', required=True)
    parser.add_argument('--execution', type=Path, required=True)
    parser.add_argument('--source-kind', choices=('native', 'sensor_capture'), required=True)
    args = parser.parse_args()
    started = time.monotonic()
    start_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    source = args.source.resolve(strict=True)
    target = args.target
    assert target.is_absolute() and target.resolve().is_relative_to(Path('/tmp'))
    validate_selection(source, target, args.prospective_prefix, args.execution, args.source_kind)
    assert not target.exists(), 'refuse overwrite of any custody attempt'
    execution_raw = args.execution.read_bytes()
    execution = json.loads(execution_raw)
    basic_ray = validate_execution_identity(execution)
    assert execution['status'] == 'completed' and execution['stage'] == 'iters150'
    assert type(execution['passed']) is bool, 'closed execution verdict must be an actual boolean'
    assert type(execution['freeze']) is str and len(execution['freeze']) == 40
    artifacts = []
    assert execution['schema'] == 'mr3-startup-sensor-execution-v1'
    consumers = [execution['original_physical_4step']]
    assert type(consumers[0]) is dict
    for row in consumers:
        output = row.get('output')
        if not isinstance(output, dict) or not output.get('path'):
            artifacts.append({'label': row.get('label'), 'available': False,
                              'original_passed': row.get('passed'),
                              'scope': 'original closed execution declares no output artifact'})
            continue
        artifact_path = Path(output['path'])
        artifact_raw = artifact_path.read_bytes()
        assert sha(artifact_raw) == output['sha256']
        artifacts.append({'label': row.get('label'), 'available': True,
                          'source': str(artifact_path), 'sha256': sha(artifact_raw),
                          'bytes': len(artifact_raw), 'original_passed': row.get('passed'),
                          'scope': 'verdict copied from closed execution, not re-audited by custody'})
    summary_path = Path(execution['benchmark_summary']['path'])
    summary_raw = summary_path.read_bytes()
    assert sha(summary_raw) == execution['benchmark_summary']['sha256']
    summary = json.loads(summary_raw)
    assert summary['freeze'] == execution['freeze'] and type(summary['passed']) is bool
    recorder_path = Path(execution['recorder_final']['path'])
    recorder_raw = recorder_path.read_bytes()
    assert sha(recorder_raw) == execution['recorder_final']['sha256']
    recorder = json.loads(recorder_raw)
    metadata_path = Path(execution['actual_workload']['protocol']['path']).parent / 'metadata.json'
    metadata_raw = metadata_path.read_bytes()
    metadata = json.loads(metadata_raw)
    assert metadata['freeze'] == execution['freeze'] and recorder['epoch'] == metadata['epoch']
    files, directories = inventory(source)
    if args.source_kind == 'sensor_capture':
        assert not directories and {path.name for path, _ in files} == {'messages.cdr', 'records.jsonl', 'final.json'}
    target.mkdir(parents=True)
    source_code = Path(__file__).read_bytes()
    configuration = {'schema': 'mr3-v21-ray-custody-helper-configuration-v1',
        'argv': sys.argv, 'python_executable': sys.executable, 'python_version': platform.python_version(),
        'cwd': os.getcwd(), 'environment_exact': dict(os.environ), 'source_sha256': sha(source_code),
        'source': str(source), 'target': str(target), 'prospective_prefix': args.prospective_prefix,
        'raw_chunk_bytes': RAW_CHUNK_BYTES, 'copy_buffer_bytes': COPY_BYTES,
        'compression_level': COMPRESSION_LEVEL, 'gzip_mtime': 0, 'gzip_filename_header': '',
        'max_encoded_bytes_strict': MAX_ENCODED_BYTES, 'workers': WORKERS,
        'zlib_compile_version': zlib.ZLIB_VERSION, 'zlib_runtime_version': zlib.ZLIB_RUNTIME_VERSION,
        'start_utc': start_utc, 'source_files': len(files), 'source_bytes': sum(x[1][2] for x in files)}
    # Wrapper starts this helper with a small fully declared environment. Do not
    # accidentally dump a caller's unrestricted credentials into evidence.
    assert set(os.environ) <= {'PATH', 'PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE',
                               'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ'}
    with (target / 'helper_configuration.json').open('x') as stream:
        json.dump(configuration, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'event': 'custody_started', 'files': len(files),
                      'raw_bytes': configuration['source_bytes'], 'raw_chunk_bytes': RAW_CHUNK_BYTES}), flush=True)
    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(pack_file, index, path, source, target, initial,
                               args.prospective_prefix): path
                   for index, (path, initial) in enumerate(files)}
        for future in as_completed(futures):
            row = future.result()
            rows.append(row)
            if row['raw_bytes'] > RAW_CHUNK_BYTES:
                print(json.dumps({'event': 'large_original_verified', 'relative_path': row['relative_path'],
                                  'raw_bytes': row['raw_bytes'], 'parts': len(row['parts']),
                                  'selected_bytes': sum(x['selected_bytes'] for x in row['parts'])}), flush=True)
    final_files, final_directories = inventory(source)
    assert [(str(path), value) for path, value in files] == [(str(path), value) for path, value in final_files]
    assert directories == final_directories
    assert Path(__file__).read_bytes() == source_code, 'helper source changed during custody'
    assert args.execution.read_bytes() == execution_raw, 'closed execution receipt changed'
    assert summary_path.read_bytes() == summary_raw, 'closed benchmark summary changed'
    assert recorder_path.read_bytes() == recorder_raw, 'closed recorder final changed'
    assert metadata_path.read_bytes() == metadata_raw, 'closed worker metadata changed'
    for artifact in artifacts:
        if artifact['available']:
            assert sha(Path(artifact['source']).read_bytes()) == artifact['sha256'], 'closed consumer artifact changed'
    rows.sort(key=lambda row: row['relative_path'])
    by_relative = {row['relative_path']: row for row in rows}
    if args.source_kind == 'native':
        for robot, original in basic_ray['robots'].items():
            packed = by_relative['worker0/episode001_open_101/ray_' + robot + '.jsonl']
            assert (packed['raw_sha256'], packed['raw_bytes']) == (original['sha256'], original['bytes'])
    else:
        assert by_relative['final.json']['raw_sha256'] == sha(recorder_raw)
    manifest = {'schema': 'mr3-v21-ray-byte-custody-v1', 'passed': True,
        'pass_scope': 'Lossless byte custody and codec/stat verification only; stage results copied from completed original.',
        'stage': 'iters150', 'source_kind': args.source_kind, 'source': str(source), 'freeze': execution['freeze'],
        'plan_sha256': execution['plan_sha256'], 'prospective_prefix': args.prospective_prefix,
        'original_stage_passed': execution['passed'], 'original_benchmark_passed': summary['passed'],
        'original_execution': {'source': str(args.execution), 'sha256': sha(execution_raw)},
        'original_benchmark_summary': {'source': str(summary_path), 'sha256': sha(summary_raw)},
        'original_execution_errors': execution.get('errors'),
        'original_physical_4step': execution['original_physical_4step'],
        'original_physical_passed': execution['original_physical_passed'],
        'original_ray_measurement_availability': basic_ray,
        'strict_native_closure_passed': execution['strict_native_closure_passed'],
        'actual_workload_original': execution['actual_workload'],
        'e61c_original': execution['e61c'],
        'closed_recorder_final': {'source': str(recorder_path), 'sha256': sha(recorder_raw),
                                  'bytes': len(recorder_raw), 'original_value': recorder},
        'closed_worker_metadata': {'source': str(metadata_path), 'sha256': sha(metadata_raw),
                                  'bytes': len(metadata_raw)},
        'native_wall_seconds_original': execution.get('native_wall_seconds'),
        'no_new_formal_or_native': True, 'no_missing_credit_filled': True,
        'closed_consumer_artifacts': artifacts,
        'source_files': len(rows), 'raw_bytes': sum(row['raw_bytes'] for row in rows),
        'selected_bytes': sum(piece['selected_bytes'] for row in rows for piece in row['parts']),
        'selected_parts': sum(len(row['parts']) for row in rows),
        'largest_encoded_part_bytes': max(piece['selected_bytes'] for row in rows for piece in row['parts']),
        'raw_chunk_bytes': RAW_CHUNK_BYTES, 'directories': directories, 'files': rows,
        'selection': 'Every regular original file including original gzip bytes and empty files. No exclusions/deduplication; no source file changed or deleted.',
        'reassembly': 'For each original relative_path, gzip-decode each listed part exactly once and concatenate in index/raw_offset order. This yields the exact original bytes; an original.gz remains original gzip bytes at that point. Verify raw_bytes/raw_sha256. This custody tree is not a directly runnable old EP tree.',
        'source_statfinal_inventory_exact': True, 'helper_configuration': configuration,
        'end_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'custody_wall_seconds': time.monotonic() - started}
    with (target / 'manifest.json').open('x') as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'event': 'custody_complete', 'passed': True,
        'scope': manifest['pass_scope'], 'source_files': manifest['source_files'],
        'raw_bytes': manifest['raw_bytes'], 'selected_bytes': manifest['selected_bytes'],
        'selected_parts': manifest['selected_parts'],
        'largest_encoded_part_bytes': manifest['largest_encoded_part_bytes'],
        'wall_seconds': manifest['custody_wall_seconds'], 'manifest': str(target / 'manifest.json'),
        'manifest_sha256': sha((target / 'manifest.json').read_bytes())}), flush=True)


if __name__ == '__main__':
    main()
