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
import re
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
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSET = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install'
PLAN = ROOT / ASSET / 'predeclared_plan_v24.json'
BASE = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0'
TEMP = Path('/tmp')
STAGES = ('interface', 'terminal', 'reset', 'deadline')
GLOBAL_NAMES = (
    'mr3_p2a0_v24_remaining_matrix_v1.jsonl',
    'mr3_p2a0_v24_source_preflight.json',
    'mr3_p2a0_v24_binaryproof.json',
    'mr3_p2a0_v24_cross_stage_mapping_start_v1.json',
    'mr3_p2a0_v24_cross_stage_mapping_calls_v1.jsonl',
    'mr3_p2a0_v24_cross_stage_mapping_summary_v1.json',
    'mr3_p2a0_v24_cross_stage_mapping.lock',
)
SAFE_ENV = {'PATH', 'PYTHONNOUSERSITE', 'PYTHONDONTWRITEBYTECODE',
            'LANG', 'LC_ALL', 'LC_CTYPE', 'TZ'}
CODEC_becd6aeb9a0d58d34adbb446cade8eff3477d04c5b477d5ac9ff602275f2af6c256 = 'becd6aeb9a0d58d34adbb446cade8eff3477d04c5b477d5ac9ff602275f2af6c'
CODEC_FUNCTIONS = ('sha', 'identity', 'file_digest', 'verify_file', 'pack_file', 'inventory')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_bound(path, bindings):
    raw = path.read_bytes()
    record = {'sha256': sha(raw), 'bytes': len(raw), 'stat': identity(path.stat())}
    if str(path) in bindings:
        require(bindings[str(path)] == record, 'bound source changed between reads: ' + str(path))
    else:
        bindings[str(path)] = record
    return raw


def validate_plan(plan):
    require(plan.get('schema') == 'mr3-p2a0-predeclaration-v24', 'not declared V22 plan')
    specifications = plan['stages']
    require(tuple(x['stage'] for x in specifications) == STAGES, 'four declared stage order differs')
    for row in specifications:
        stage = row['stage']
        expected = BASE / ('mr3_p2a0_20261018_v24_' + stage)
        require(row['run_directory'] == str(expected), 'native root differs for ' + stage)
        command = row['command']
        require(command[command.index('--run-id') + 1] == expected.name
                and command[command.index('--output-root') + 1] == str(BASE),
                'actual declared native command targets another run')
        paths = row['required_audit_receipts']
        require(len(paths) == len(set(paths)) and all(
            Path(path).parent == TEMP and Path(path).name.startswith('mr3_p2a0_v24_' + stage + '_')
            for path in paths), 'declared formal outputs outside exact stage prefix')
    return specifications


def closed_metadata(plan, freeze, plan_sha, bindings):
    # These checks establish that the selected original ledger has its real final
    # event and submitted consumers are drained. They do not require scientific PASS.
    ledger_path = TEMP / GLOBAL_NAMES[0]
    raw = read_bound(ledger_path, bindings)
    require(raw and raw.endswith(b'\n'), 'orchestration ledger not complete newline')
    rows = [json.loads(line) for line in raw.splitlines()]
    require(all(row.get('schema') == 'mr3-declared-matrix-orchestration-v2'
                and row.get('freeze') == freeze and row.get('plan_sha256') == plan_sha for row in rows),
            'actual orchestration source/plan differs')
    final = rows[-1]
    require(final.get('event') in ('matrix_complete', 'version_failed_later_stages_skip'),
            'matrix has not recorded its actual final complete/failure event')
    watcher = json.loads(read_bound(TEMP / GLOBAL_NAMES[5], bindings))
    require(watcher.get('schema') == 'mr3-v24-cross-stage-mapping-complete-v1'
            and watcher.get('freeze') == freeze, 'actual mapping watcher has not closed')
    preflight = json.loads(read_bound(TEMP / GLOBAL_NAMES[1], bindings))
    require(preflight.get('freeze') == freeze and preflight.get('plan_sha256') == plan_sha,
            'original source preflight source/plan differs')
    states = {}
    for specification in validate_plan(plan):
        stage = specification['stage']
        prefix = 'mr3_p2a0_v24_' + stage
        launch_path, audit_path = TEMP / (prefix + '_launch.json'), TEMP / (prefix + '_audit_execution_v1.json')
        state = {'stage': stage, 'run_directory': specification['run_directory'],
                 'run_directory_exists': Path(specification['run_directory']).exists(),
                 'events': [x for x in rows if x.get('stage') == stage]}
        if launch_path.exists():
            launch = json.loads(read_bound(launch_path, bindings))
            require(launch.get('stage') == stage and launch.get('freeze') == freeze
                    and launch.get('plan_sha256') == plan_sha
                    and launch.get('status') in ('completed', 'failed'),
                    'actual native launcher has not closed or lost identity')
            state['original_launch'] = launch
        else:
            state['original_launch'] = None
        if audit_path.exists():
            audit = json.loads(read_bound(audit_path, bindings))
            require(audit.get('stage') == stage and audit.get('freeze') == freeze
                    and audit.get('plan_sha256') == plan_sha
                    and audit.get('all_submitted_jobs_finished') is True,
                    'submitted required/read-only audit jobs not all drained')
            state['original_audit_execution'] = audit
        else:
            state['original_audit_execution'] = None
        later = final.get('later_stages', []) if final['event'] == 'version_failed_later_stages_skip' else []
        state['declared_later_stage_skip'] = stage in later
        state['scientific_verdict_not_recomputed'] = True
        state['declared_receipts_availability'] = [
            {'path': path, 'exists': Path(path).exists()} for path in specification['required_audit_receipts']]
        states[stage] = state
    return {'orchestration_final_original': final, 'watcher_final_original': watcher, 'stages': states}


def metadata_selection(extras):
    # Copy every original matching each exact stage prefix, including partial
    # output, console, monitor, corrector mapping, FIFO/phase and failing leaves.
    selected = set()
    directories = []
    for stage in STAGES:
        for path in sorted(TEMP.glob('mr3_p2a0_v24_' + stage + '_*')):
            mode = path.lstat().st_mode
            require(not stat.S_ISLNK(mode), 'metadata symlink not followed: ' + str(path))
            if stat.S_ISDIR(mode):
                files, subdirectories = inventory(path)
                selected.update(x for x, unused in files)
                directories.append(str(path))
                directories.extend(str(path / x['relative_path']) for x in subdirectories)
            else:
                require(stat.S_ISREG(mode), 'nonregular metadata: ' + str(path))
                selected.add(path)
    for name in GLOBAL_NAMES:
        path = TEMP / name
        if path.exists():
            selected.add(path)
    # Root may explicitly add closed controller/watcher stdout, original source
    # packs and small final diagnostics whose names are not per-stage prefixes.
    for path in extras:
        require(path.is_absolute() and path.is_relative_to(TEMP) and path.resolve(strict=True).is_relative_to(TEMP),
                'extra must name one exact original file within /tmp')
        require(path.exists(), 'declared extra is missing: ' + str(path))
        selected.add(path)
    files = []
    for path in sorted(selected):
        value = path.lstat()
        require(stat.S_ISREG(value.st_mode) and not stat.S_ISLNK(value.st_mode),
                'extra/global original is not regular: ' + str(path))
        files.append((path, identity(value)))
    return files, sorted(set(directories))


def pack_selection(source, files, directories, target, prospective):
    require(not target.exists(), 'refuse overwrite: ' + str(target))
    target.mkdir(parents=True)
    rows = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = [pool.submit(pack_file, index, path, source, target, initial, prospective)
                   for index, (path, initial) in enumerate(files)]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda row: row['relative_path'])
    # In addition to each fd/path stability check, rehash every complete original
    # after all parts are decoded. This is byte custody, not a formal re-audit.
    for row in rows:
        path = Path(row['source'])
        require(identity(path.lstat()) == row['source_stat_initial'], 'source final stat changed: ' + str(path))
        require(file_digest(path) == (row['raw_bytes'], row['raw_sha256']), 'source final whole SHA changed: ' + str(path))
    manifest = {'schema': 'mr3-v24-matrix-selection-byte-custody-v1', 'passed': True,
                'scope': 'Lossless encoded/decoded and full original byte custody only; original failures/skips retained.',
                'source': str(source), 'prospective_prefix': prospective, 'directories': directories,
                'source_files': len(rows), 'raw_bytes': sum(row['raw_bytes'] for row in rows),
                'selected_parts': sum(len(row['parts']) for row in rows),
                'selected_bytes': sum(part['selected_bytes'] for row in rows for part in row['parts']),
                'raw_chunk_bytes': RAW_CHUNK_BYTES, 'strict_max_encoded_part_bytes': MAX_ENCODED_BYTES,
                'files': rows, 'source_end_sha_and_stat_verified': True}
    with (target / 'manifest.json').open('x') as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--plan', type=Path, default=PLAN)
    parser.add_argument('--target', type=Path, required=True)
    parser.add_argument('--extra', type=Path, action='append', default=[])
    parser.add_argument('--all-writers-closed', action='store_true', required=True,
                        help='Required explicit root GO; not itself scientific closure evidence.')
    args = parser.parse_args()
    require(re.fullmatch('[0-9a-f]{40}', args.freeze) is not None, 'exact freeze required')
    require(args.plan == PLAN, 'only fixed canonical V22 plan selected')
    require(args.target.is_absolute() and args.target.parent == TEMP and not args.target.exists(),
            'new direct /tmp output only; refuse any prior custody attempt')
    require(set(os.environ) <= SAFE_ENV, 'use declared minimal environment only')
    require(not any(path == args.target or path.is_relative_to(args.target) for path in args.extra),
            'never select output as an original')
    started = time.monotonic()
    bindings = {}
    plan_raw = read_bound(args.plan, bindings)
    plan_sha = sha(plan_raw)
    plan = json.loads(plan_raw)
    states = closed_metadata(plan, args.freeze, plan_sha, bindings)
    native_selections = {}
    for specification in validate_plan(plan):
        source = Path(specification['run_directory'])
        native_selections[specification['stage']] = inventory(source) if source.exists() else None
    metadata_files, metadata_directories = metadata_selection(args.extra)
    source_code = Path(__file__).read_bytes()
    args.target.mkdir()
    configuration = {'schema': 'mr3-v24-matrix-custody-helper-configuration-v1',
                     'source': str(Path(__file__)), 'source_sha256': sha(source_code),
                     'codec_base_sha256': CODEC_becd6aeb9a0d58d34adbb446cade8eff3477d04c5b477d5ac9ff602275f2af6c256, 'codec_functions': list(CODEC_FUNCTIONS),
                     'argv': sys.argv, 'cwd': os.getcwd(), 'environment_exact': dict(os.environ),
                     'freeze': args.freeze, 'plan': str(args.plan), 'plan_sha256': plan_sha,
                     'root_closed_go_flag': args.all_writers_closed,
                     'python_executable': sys.executable, 'python_version': platform.python_version(),
                     'zlib_compile_version': zlib.ZLIB_VERSION, 'zlib_runtime_version': zlib.ZLIB_RUNTIME_VERSION,
                     'raw_chunk_bytes': RAW_CHUNK_BYTES, 'strict_max_encoded_part_bytes': MAX_ENCODED_BYTES,
                     'workers': WORKERS, 'compression_level': COMPRESSION_LEVEL,
                     'gzip_mtime': 0, 'gzip_filename_header': ''}
    with (args.target / 'helper_configuration.json').open('x') as stream:
        json.dump(configuration, stream, indent=2, allow_nan=False)
        stream.write('\n')
    groups = {}
    for specification in validate_plan(plan):
        stage = specification['stage']
        selection = native_selections[stage]
        if selection is None:
            groups[stage] = {'source_exists': False, 'original_stage_state': states['stages'][stage]}
            continue
        source = Path(specification['run_directory'])
        manifest = pack_selection(source, *selection, args.target / 'native' / stage, ASSET + '/native/' + stage)
        require(inventory(source) == selection, 'whole native tree changed while packed: ' + stage)
        groups[stage] = {'source_exists': True, 'manifest': str(args.target / 'native' / stage / 'manifest.json'),
                         'manifest_sha256': sha((args.target / 'native' / stage / 'manifest.json').read_bytes()),
                         'source_files': manifest['source_files'], 'raw_bytes': manifest['raw_bytes'],
                         'selected_bytes': manifest['selected_bytes'], 'selected_parts': manifest['selected_parts'],
                         'original_stage_state': states['stages'][stage]}
    metadata = pack_selection(TEMP, metadata_files, metadata_directories, args.target / 'metadata', ASSET + '/native/metadata')
    require(metadata_selection(args.extra) == (metadata_files, metadata_directories), 'metadata selection changed while packed')
    require(Path(__file__).read_bytes() == source_code, 'helper source changed during custody')
    for path, original in bindings.items():
        require(identity(Path(path).stat()) == original['stat'] and file_digest(Path(path)) == (original['bytes'], original['sha256']),
                'bound completion/plan original changed: ' + path)
    result = {'schema': 'mr3-v24-closed-matrix-byte-custody-v1', 'passed': True,
              'scope': 'Lossless byte custody only; no new native/formal, no missing credit filled or scientific verdict changed.',
              'freeze': args.freeze, 'plan_sha256': plan_sha, 'native': groups,
              'metadata': {'manifest': str(args.target / 'metadata/manifest.json'),
                           'manifest_sha256': sha((args.target / 'metadata/manifest.json').read_bytes()),
                           'source_files': metadata['source_files'], 'raw_bytes': metadata['raw_bytes'],
                           'selected_bytes': metadata['selected_bytes'], 'selected_parts': metadata['selected_parts']},
              'original_closed_state': states, 'initial_final_bound_inputs': bindings,
              'all_original_stat_and_whole_sha_rechecked': True,
              'source_selections': 'All regular originals under each existing fixed four-stage native tree and all exact stage-prefixed TMP files/trees, known global matrix/watcher/preflight/binary metadata, plus named root extras; empty and original gzip bytes retained.',
              'reassembly': 'Per original manifest: decode listed gzip parts and concatenate in index/raw_offset order to recover exact original bytes. Original .gz remains original .gz bytes after this layer. Verify all encoded, part-decoded and whole-decoded SHAs.',
              'custody_wall_seconds': time.monotonic() - started}
    with (args.target / 'manifest.json').open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'event': 'custody_complete', 'scope': result['scope'],
                      'manifest': str(args.target / 'manifest.json'),
                      'manifest_sha256': sha((args.target / 'manifest.json').read_bytes()),
                      'custody_wall_seconds': result['custody_wall_seconds']}), flush=True)


if __name__ == '__main__':
    main()
