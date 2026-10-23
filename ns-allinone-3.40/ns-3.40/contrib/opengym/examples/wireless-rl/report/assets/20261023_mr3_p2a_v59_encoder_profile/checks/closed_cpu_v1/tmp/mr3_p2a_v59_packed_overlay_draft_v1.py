"""DRAFT: separate post-collector packed-byte overlay; never run while live.

Selection occurs only from actual completed inventory sizes, after an actual
collector rc0/source-unchanged wait and fresh disappearance of its saved IDs.
No decompression/recompression, raw/scientific input reads or original removal.
The whole inventory and whole wrapper hashes remain immutable.
"""
import argparse
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSET = W / 'report/assets/20261023_mr3_p2a_v59_encoder_profile'
FREEZE = '783aec55353ecb93385ffe305300ab760f9c24fe'
MAX_PACKED = 64 * 1024 * 1024
SPLITTER = W / 'report/assets/20261019_mr3_p2a_v13/closed_continuation/checks/pack_cpu.py'
SPLITTER_SHA = '4cb98f6e0b4ab06bd5f0faa45bc343ccd644c5f2feeb109ded60595f383150a5'
COPIER = W / 'report/assets/20261022_mr3_p2a_v45_preparation_classification/collect_closed_v1.py'
COPIER_SHA = '63d52ce389b7d61fa67f5080fa556b1f32e47b79e389800f9de55e97c40abf06'
COLLECTOR = Path('/tmp/mr3_p2a_v59_collect_closed_draft_v1.py')
COLLECTOR_SHA = '89994b6e9eda98a6dacc96c7e9a566cfc0ecd4ed7bb96571d1ae6829ada3c155'


def require(value, message):
    if not value:
        raise ValueError(message)


def decode(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON member')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def signature(path):
    s = Path(path).lstat()
    require(stat.S_ISREG(s.st_mode), 'regular non-symlink file required: ' + str(path))
    return [s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def digest(path):
    sha, count = hashlib.sha256(), 0
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(block)
            count += len(block)
    return sha.hexdigest(), count


def bound_json(path, expected_sha=None):
    before = signature(path)
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    require(signature(path) == before and len(raw) == before[2], 'JSON changed while reading')
    require(expected_sha is None or sha == expected_sha, 'bound inventory SHA differs')
    return decode(raw), {'path': str(path), 'sha256': sha, 'bytes': len(raw)}, before


def load_pinned(path, expected, name):
    require(digest(path)[0] == expected, 'immutable packed/copy helper SHA differs')
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def collector_complete(path, copier):
    value, proof, _ = bound_json(path)
    lo, hi = value['started_monotonic_ns'], value['ended_monotonic_ns']
    require(value.get('schema') == 'mr3-reach-outer-actual-wait-v1'
        and value.get('scope') == 'cpu' and value.get('actual_waited') is True
        and type(value.get('actual_returncode')) is int and value['actual_returncode'] == 0
        and value.get('passed') is True and value.get('errors') == []
        and value.get('source_unchanged') is True
        and value.get('source_before') == value.get('source_after')
        and type(lo) is int and type(hi) is int and 0 < lo < hi
        and Decimal(value['actual_child_wait_seconds']) == Decimal(hi - lo) / 10**9,
        'collector has not actually completed its unchanged successful wait')
    argv = value['actual_argv']
    require(type(argv) is list and str(COLLECTOR) in argv
        and argv.count('--mode') == argv.count('--freeze') == 1
        and argv[argv.index('--mode') + 1] in ('closed', 'preserve-evidence')
        and argv[argv.index('--freeze') + 1] == FREEZE
        and any(row.get('path') == str(COLLECTOR) and row.get('sha256') == COLLECTOR_SHA
                for row in value['source_before']), 'another collector/mode/source was waited')
    for key in ('coordinator_identity', 'child_identity'):
        copier.require_absent(value[key])
    return dict(proof, archive_mode=argv[argv.index('--mode') + 1])


def relative(value):
    require(type(value) is str and value and not any(c in value for c in '\x00\n\r'),
            'invalid relative path text')
    path = PurePosixPath(value)
    require(not path.is_absolute() and '..' not in path.parts and value == path.as_posix(),
            'noncanonical/escaping inventory path')
    return Path(value)


def snapshot(directory):
    rows = {}
    for parent, names, files in os.walk(directory, followlinks=False):
        for name in names:
            require(not (Path(parent) / name).is_symlink(), 'unexpected canonical directory symlink')
        for name in files:
            path = Path(parent) / name
            rows[str(path.relative_to(directory))] = signature(path)
    return rows


def write(path, raw):
    with Path(path).open('xb') as stream:
        require(stream.write(raw) == len(raw), 'short output write')
        stream.flush()
        os.fsync(stream.fileno())


def ignore_pattern(path):
    # Slash-anchored and escaped: no wildcard, basename or directory aliases.
    return '/' + ''.join('\\' + c if c in '\\!#*?[] \t' else c for c in path.as_posix())


def git(repo, *argv, input=None, check=True):
    return subprocess.run(['git', *([] if argv[:1] == ('check-ignore',) else ['--literal-pathspecs']), *argv], cwd=repo,
        input=input, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=check, timeout=30)


def ignored(repo, paths):
    raw = b''.join(str(path.relative_to(repo)).encode() + b'\0' for path in paths)
    result = git(repo, 'check-ignore', '--no-index', '-z', '--stdin', input=raw, check=False)
    require(result.returncode in (0, 1), 'git check-ignore failed')
    return set(result.stdout.split(b'\0')) - {b''}


def build_overlay(asset, repo, inventory_sha, collector_wait):
    asset, repo = Path(asset).resolve(strict=True), Path(repo).resolve(strict=True)
    archive, output = asset / 'closed_execution', asset / 'packed_overlay_v1'
    inventory_path, ignore = asset / 'closed_inventory_v1.json', archive / '.gitignore'
    require(not output.exists() and not output.is_symlink() and not ignore.exists()
            and not ignore.is_symlink(), 'exclusive overlay or local ignore already exists')
    splitter = load_pinned(SPLITTER, SPLITTER_SHA, '_v59_original_packed_splitter')
    copier = load_pinned(COPIER, COPIER_SHA, '_v59_original_process_absence')
    waited = collector_complete(collector_wait, copier)
    inventory, inventory_proof, inventory_stat = bound_json(inventory_path, inventory_sha)
    require(inventory.get('schema') == 'mr3-v59-closed-byte-archive-draft-v2'
        and inventory.get('freeze') == FREEZE and inventory.get('byte_archive_complete') is True
        and inventory.get('archive_mode') == waited['archive_mode']
        and inventory.get('closed_saved_identity_inventory_claimed') is (waited['archive_mode'] == 'closed'),
        'successful actual collector inventory with matching explicit mode required; never split a live/incomplete archive')
    before = snapshot(archive)
    entries, selected = {}, []
    for row in inventory['entries']:
        name = relative(row['canonical'])
        require(name.parts[0] == 'closed_execution' and str(name) not in entries,
                'duplicate/out-of-archive canonical inventory path')
        path = asset / name
        require(path.resolve(strict=True) == path and signature(path)[2] == row['canonical_bytes']
            and type(row['canonical_bytes']) is int and row['canonical_bytes'] >= 0
            and row.get('source_stat_stable') is True and row.get('decoded_bytes_verified') is True
            and re.fullmatch('[0-9a-f]{64}', row['canonical_sha256'])
            and re.fullmatch('[0-9a-f]{64}', row['original_sha256']), 'canonical size/proof differs')
        entries[str(name)] = row
        if row['canonical_bytes'] > MAX_PACKED:
            selected.append((path, row))
    require(inventory['files'] == len(entries) and set(before) == {
        str(Path(name).relative_to('closed_execution')) for name in entries},
        'canonical full file membership differs from immutable V1 inventory')
    originals = [asset / name for name in sorted(entries)]
    original_ignored = ignored(repo, originals)
    selected_paths = [path for path, _ in selected]
    if selected_paths:
        tracked = git(repo, 'ls-files', '-z', '--', *(str(p.relative_to(repo)) for p in selected_paths))
        require(not tracked.stdout, 'overlarge packed originals already tracked; do not hide tracked blobs')
    splitter.PART_BYTES = MAX_PACKED
    representations = []
    output.mkdir(exist_ok=False)
    try:
        for index, (source, row) in enumerate(selected):
            require(digest(source) == (row['canonical_sha256'], row['canonical_bytes']),
                    'packed original differs from V1 archive bytes')
            parts_dir = output / 'parts' / ('%04d' % index)
            parts_dir.mkdir(parents=True, exist_ok=False)
            parts, offset = splitter.split_archive(source, parts_dir), 0
            saved = []
            for ordinal, part in enumerate(parts):
                path = parts_dir / part['path']
                require(0 < part['bytes'] <= MAX_PACKED and digest(path) == (part['sha256'], part['bytes']),
                        'part is corrupt or exceeds the packed blob limit')
                with path.open('rb') as stream:
                    os.fsync(stream.fileno())
                saved.append(dict(index=ordinal, offset=offset, path=str(path.relative_to(asset)),
                                  bytes=part['bytes'], sha256=part['sha256']))
                offset += part['bytes']
            require(offset == row['canonical_bytes'], 'parts do not cover complete packed original')
            representations.append(dict(canonical=row['canonical'], original=row['original'],
                original_bytes=row['original_bytes'], original_sha256=row['original_sha256'],
                codec=row['codec'], packed_bytes=row['canonical_bytes'],
                packed_sha256=row['canonical_sha256'], parts=saved,
                ordered_concatenation_verified_by_original_splitter=True,
                raw_decoded_byte_proof_from_immutable_v1_only=True))
        require(snapshot(archive) == before and signature(inventory_path) == inventory_stat
                and digest(inventory_path) == (inventory_proof['sha256'], inventory_proof['bytes']),
                'original archive/inventory changed during binary chunk copy')
        attributes = b'* -text -whitespace\n'
        write(output / '.gitattributes', attributes)
        ignore_raw = ''.join(ignore_pattern(p.relative_to(archive)) + '\n'
                             for p in selected_paths).encode()
        manifest = dict(schema='mr3-v59-packed-byte-overlay-v1', passed=False,
            status='PARTS_VERIFIED_PENDING_FINAL_IGNORE_CHECKS', freeze=FREEZE,
            archive_mode=inventory['archive_mode'],
            closed_identity_inventory_claimed=inventory['closed_saved_identity_inventory_claimed'],
            preservation_mode_does_not_grant_identity_or_scientific_closure=True,
            base_inventory=inventory_proof, collector_actual_wait=waited,
            max_packed_blob_bytes=MAX_PACKED, original_file_count=len(entries),
            replacement_file_count=len(representations), representations=representations,
            unchanged_entries_remain_in_v1_inventory=True,
            local_packed_originals_retained=True, raw_originals_not_read_or_modified=True,
            decoded_original_proof_not_reexecuted=True, no_decompression_or_recompression=True,
            scientific_results_recomputed=False, engineering_added_seconds='0',
            splitter=dict(path=str(SPLITTER), sha256=SPLITTER_SHA,
                          called_function='split_archive only', configured_part_bytes=MAX_PACKED),
            gitignore=dict(path=str(ignore.relative_to(asset)), sha256=hashlib.sha256(ignore_raw).hexdigest(),
                           bytes=len(ignore_raw), exact_original_paths_only=[str(p.relative_to(asset))
                               for p in selected_paths]),
            restore='Concatenate listed parts in index/offset order without decoding; check every part SHA/size, then full packed SHA/size. Original raw SHA and decoded proof remain in the immutable V1 inventory.',
            admission='Require this actual overlay process rc0/source-unchanged receipt before staging. Partial output/manifest after failure is not an admitted representation.')
        write(output / 'manifest.pending.json', (json.dumps(manifest, indent=2) + '\n').encode())
        # Exclude only after the complete verified part mapping exists on disk.
        if selected_paths:
            write(ignore, ignore_raw)
        after_ignored = ignored(repo, originals)
        expected_new = {str(p.relative_to(repo)).encode() for p in selected_paths}
        require(after_ignored == original_ignored | expected_new, 'ignore excludes other original paths')
        after = snapshot(archive)
        if selected_paths:
            after.pop('.gitignore')
        require(after == before and digest(inventory_path) ==
            (inventory_proof['sha256'], inventory_proof['bytes']), 'source set changed at overlay seal')
        manifest.update(passed=True, status='COMPLETE')
        write(output / 'manifest.json', (json.dumps(manifest, indent=2) + '\n').encode())
        return manifest
    except BaseException as error:
        write(output / 'failure.json', (json.dumps({'passed': False, 'error': repr(error),
            'originals_retained': True, 'partial_outputs_preserved': True}) + '\n').encode())
        raise


def restore(manifest_path, canonical, output):
    manifest_path, output = Path(manifest_path), Path(output)
    manifest, _, _ = bound_json(manifest_path)
    require(manifest.get('schema') == 'mr3-v59-packed-byte-overlay-v1' and manifest.get('passed') is True,
            'verified overlay manifest required')
    matches = [r for r in manifest['representations'] if r['canonical'] == canonical]
    require(len(matches) == 1, 'exact canonical replacement required')
    row, sha, count = matches[0], hashlib.sha256(), 0
    asset = manifest_path.parent.parent
    with output.open('xb') as writer:
        for index, part in enumerate(row['parts']):
            require(part['index'] == index and part['offset'] == count and 0 < part['bytes'] <= MAX_PACKED,
                    'part index/offset/size differs')
            source = asset / relative(part['path'])
            require(source.resolve(strict=True) == source and source.is_relative_to(manifest_path.parent / 'parts'),
                    'part symlink/alias or outside-overlay path is not allowed')
            before = signature(source)
            local, size = hashlib.sha256(), 0
            with source.open('rb') as reader:
                for block in iter(lambda: reader.read(1024 * 1024), b''):
                    writer.write(block); local.update(block); sha.update(block); size += len(block)
            require(signature(source) == before and size == part['bytes'] and local.hexdigest() == part['sha256'],
                    'part bytes/hash changed')
            count += size
        writer.flush(); os.fsync(writer.fileno())
    require(count == row['packed_bytes'] and sha.hexdigest() == row['packed_sha256'],
            'restored full packed size/hash differs')
    return {'path': str(output), 'bytes': count, 'sha256': sha.hexdigest(), 'decoded': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='operation', required=True)
    build = sub.add_parser('build')
    build.add_argument('--inventory-sha256', required=True)
    build.add_argument('--collector-actual-wait', type=Path, required=True)
    rebuilding = sub.add_parser('restore')
    rebuilding.add_argument('--manifest', type=Path, required=True)
    rebuilding.add_argument('--canonical', required=True)
    rebuilding.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.operation == 'build':
        require(re.fullmatch('[0-9a-f]{64}', args.inventory_sha256), 'exact inventory SHA required')
        result = build_overlay(ASSET, ROOT, args.inventory_sha256, args.collector_actual_wait)
        print(json.dumps({'passed': True, 'replacement_file_count': result['replacement_file_count']}))
    else:
        print(json.dumps(restore(args.manifest, args.canonical, args.output)))


if __name__ == '__main__':
    main()
