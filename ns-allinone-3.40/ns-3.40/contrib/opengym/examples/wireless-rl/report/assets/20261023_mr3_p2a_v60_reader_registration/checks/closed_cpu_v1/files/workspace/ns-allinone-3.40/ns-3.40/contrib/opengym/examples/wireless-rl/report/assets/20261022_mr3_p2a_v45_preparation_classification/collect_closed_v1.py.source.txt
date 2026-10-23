"""Exclusive post-wait V45 byte archive; no scientific replay or model load.

Run only after the driver has returned and its owned children have been reaped.
The closure guard reads named process metadata only. Telemetry/model contents
are opaque streams. Existing originals and any partial archive remain intact.
"""

import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat


ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
A = ROOT / ('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/'
            'report/assets/20261022_mr3_p2a_v45_preparation_classification')
PREFIX = 'mr3_p2a_reach_v45'
FREEZE = 'cace46e08e53b7e89a434e23721db85ac993f6f5'
DRIVER = Path('/tmp') / (PREFIX + '_driver_v1/summary.json')
ABSENCE = Path('/tmp') / (PREFIX + '_chain_final_absence.json')
DEST = A / 'closed_execution'
INVENTORY = A / 'closed_inventory_v1.json'
FAILED = A / 'closed_inventory_v1.failed.json'
TEXT_SUFFIXES = frozenset(('.jsonl', '.csv', '.log', '.txt', '.out', '.err'))
TEXT_NAMES = frozenset(('console', 'stdout', 'stderr'))
BLOCK = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stamp(value):
    return dict(zip(('dev', 'ino', 'mode', 'size', 'mtime_ns', 'ctime_ns'),
        (value.st_dev, value.st_ino, value.st_mode, value.st_size,
         value.st_mtime_ns, value.st_ctime_ns)))


def regular_stamp(path):
    value = path.lstat()
    require(stat.S_ISREG(value.st_mode), 'not a regular non-symlink file: ' + str(path))
    return stamp(value)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate metadata member: ' + key)
        result[key] = value
    return result


def metadata(path):
    before = regular_stamp(path)
    require(before['size'] <= 16 * BLOCK, 'process metadata exceeds the finite bound: ' + str(path))
    with path.open('rb') as stream:
        raw = stream.read(16 * BLOCK + 1)
    require(regular_stamp(path) == before and len(raw) == before['size'],
            'metadata changed during read: ' + str(path))
    value = json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda item: (_ for _ in ()).throw(ValueError('nonfinite metadata: ' + item)))
    return value, {'path': str(path), 'bytes': len(raw),
                   'sha256': hashlib.sha256(raw).hexdigest(), 'stat': before}


def require_absent(identity):
    require(type(identity) is dict and all(type(identity.get(key)) is int and identity[key] > 0
            for key in ('pid', 'start_ticks')), 'missing saved PID/start identity')
    path = Path('/proc') / str(identity['pid']) / 'stat'
    try:
        raw = path.read_text()
    except FileNotFoundError:
        return
    fields = raw[raw.rfind(')') + 2:].split()
    require(len(fields) >= 20, 'malformed current process identity: ' + str(path))
    # A zombie with the same start tick still exists and has not been reaped.
    require(int(fields[19]) != identity['start_ticks'],
            'saved process still exists, including zombie: ' + str(identity['pid']))


def scoped_tmp(path):
    path = Path(path)
    require(path.is_absolute() and path.parent == Path('/tmp')
            and path.name.startswith(PREFIX), 'outer path is outside V45: ' + str(path))
    return path


def closure_guard(freeze):
    summary, source = metadata(DRIVER)
    require(summary.get('schema') == 'mr3-v45-actual-chain-driver-result-v1'
            and summary.get('freeze') == freeze
            and type(summary.get('ended_monotonic_ns')) is int
            and summary['ended_monotonic_ns'] > 0,
            'V45 driver has no completed matching summary')
    require_absent(summary.get('driver_identity'))
    rows = summary.get('actual_waits')
    require(type(rows) is list and rows, 'completed driver has no actual waits')
    receipts = []
    for row in rows:
        require(type(row) is dict and type(row.get('returncode')) is int
                and type(row.get('started_monotonic_ns')) is int
                and type(row.get('ended_monotonic_ns')) is int
                and 0 < row['started_monotonic_ns'] < row['ended_monotonic_ns']
                <= summary['ended_monotonic_ns'], 'driver phase is not fully waited')
        require_absent(row.get('wrapper_identity'))
        wait, proof = metadata(scoped_tmp(row['outer']) / 'actual_wait.json')
        require(wait.get('schema') == 'mr3-reach-outer-actual-wait-v1'
                and wait.get('actual_waited') is True
                and type(wait.get('actual_returncode')) is int
                and wait['actual_returncode'] == row.get('actual_returncode'),
                'driver outer does not have a completed matching wait')
        require_absent(wait.get('coordinator_identity'))
        require_absent(wait.get('child_identity'))
        receipts.append(proof)
    absence = None
    if any(row.get('name') == 'matrix' for row in rows):
        value, absence = metadata(ABSENCE)
        require(value.get('wrapper_schema') == 'mr3-v45-external-absence-wrapper-v1'
                and value.get('passed') is True
                and value.get('all_saved_identities_absent') is True
                and value.get('source_stable') is True
                and value.get('inventory_membership_stable') is True
                and value.get('plan') == str(A / 'plan_v1.json')
                and any(row.get('name') == 'chain_final_absence'
                        and row.get('passed') is True for row in rows),
                'submitted matrix lacks its completed final saved-identity absence receipt')
    return {'driver_summary': source, 'outer_waits': receipts,
            'chain_final_absence': absence,
            'scope': 'Named completed driver/outer metadata; existing final absence receipt retained. '
                     'No new all-native identity or scientific verdict is inferred.'}


def target_for(label, relative, source):
    target = DEST / label / relative
    compressed = source.suffix in TEXT_SUFFIXES or source.name in TEXT_NAMES
    # Already compressed streams/checkpoints are always copied byte for byte.
    compressed = compressed and source.suffix not in ('.gz', '.zip')
    return Path(str(target) + '.rawbytes.gz') if compressed else target, compressed


def link_record(source, label, relative):
    before = stamp(source.lstat())
    require(stat.S_ISLNK(before['mode']), 'link type changed: ' + str(source))
    target = os.readlink(source)
    require(stamp(source.lstat()) == before, 'link changed during read: ' + str(source))
    lexical = Path(os.path.abspath(os.path.join(source.parent, target)))
    native = ROS / 'log/mr3_p2a_reach_v45'
    policy = ROS / 'log/mr3_ppo_reach_v45'
    inside = (lexical.is_relative_to(native) or lexical.is_relative_to(policy)
              or (len(lexical.parts) >= 3 and lexical.parts[1] == 'tmp'
                  and lexical.parts[2].startswith(PREFIX)))
    return {'original': str(source),
            'canonical_link_name': str((DEST / label / relative).relative_to(A)),
            'target_text': target, 'lexical_target_without_dereference': str(lexical),
            'target_scope': 'known-source-roots' if inside else 'outside-known-source-roots',
            'target_followed': False, 'link_stat': before}


def discover():
    roots = [(path, 'tmp', Path(path.name))
             for path in sorted(Path('/tmp').glob(PREFIX + '*'))]
    roots += [(ROS / 'log/mr3_p2a_reach_v45', 'native', Path()),
              (ROS / 'log/mr3_ppo_reach_v45', 'policy', Path())]
    result, links, directories, missing = {}, {}, {}, []
    for root, label, relative in roots:
        if not root.exists() and not root.is_symlink():
            missing.append(str(root))
            continue
        mode = root.lstat().st_mode
        if stat.S_ISLNK(mode):
            links[str(root)] = link_record(root, label, relative)
            continue
        require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'unsupported source root: ' + str(root))
        if stat.S_ISREG(mode):
            paths = [(root, relative)]
        else:
            paths = []
            for parent, names, files in os.walk(root, followlinks=False):
                parent = Path(parent)
                directories[str(parent)] = stamp(parent.lstat())
                names.sort(); files.sort()
                for name in list(names):
                    child = parent / name
                    child_relative = relative / child.relative_to(root)
                    if stat.S_ISLNK(child.lstat().st_mode):
                        links[str(child)] = link_record(child, label, child_relative)
                        names.remove(name)
                    else:
                        require(stat.S_ISDIR(child.lstat().st_mode),
                                'special source directory entry: ' + str(child))
                for name in files:
                    child = parent / name
                    child_relative = relative / child.relative_to(root)
                    if stat.S_ISLNK(child.lstat().st_mode):
                        links[str(child)] = link_record(child, label, child_relative)
                    else:
                        paths.append((child, child_relative))
        for source, suffix in paths:
            state = regular_stamp(source)
            target, compressed = target_for(label, suffix, source)
            require(source not in result, 'duplicate original source: ' + str(source))
            result[source] = {'target': target, 'compressed': compressed, 'stat': state}
    targets = [str(row['target']) for row in result.values()]
    targets += [str(A / row['canonical_link_name']) for row in links.values()]
    require(len(set(targets)) == len(targets), 'canonical names collide after rawbytes gzip suffix')
    target_set = set(targets)
    require(not any(str(parent) in target_set for target in targets
                    for parent in Path(target).parents if parent != DEST),
            'canonical file/link name collides with another target parent')
    require(result, 'no V45 originals found')
    return result, links, directories, missing


def digest_stream(stream):
    digest, count = hashlib.sha256(), 0
    for chunk in iter(lambda: stream.read(BLOCK), b''):
        digest.update(chunk)
        count += len(chunk)
    return digest.hexdigest(), count


def archive(source, row):
    target, compressed, before = row['target'], row['compressed'], row['stat']
    require(regular_stamp(source) == before, 'source changed before copy: ' + str(source))
    target.parent.mkdir(parents=True, exist_ok=True)
    digest, count = hashlib.sha256(), 0
    descriptor = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as reader, target.open('xb') as raw_writer:
        require(stamp(os.fstat(reader.fileno())) == before, 'source changed before open')
        writer = (gzip.GzipFile(filename='', mode='wb', fileobj=raw_writer,
                               compresslevel=6, mtime=0) if compressed else raw_writer)
        try:
            for chunk in iter(lambda: reader.read(BLOCK), b''):
                writer.write(chunk)
                digest.update(chunk)
                count += len(chunk)
        finally:
            if compressed:
                writer.close()
        raw_writer.flush()
        os.fsync(raw_writer.fileno())
        require(stamp(os.fstat(reader.fileno())) == before, 'source changed while open')
    after = regular_stamp(source)
    require(after == before and count == before['size'], 'source changed during copy: ' + str(source))
    with target.open('rb') as stream:
        packed_hash, packed_size = digest_stream(stream)
    with (gzip.open(target, 'rb') if compressed else target.open('rb')) as stream:
        decoded_hash, decoded_size = digest_stream(stream)
    require(decoded_hash == digest.hexdigest() and decoded_size == count,
            'archive decoded bytes differ: ' + str(target))
    return {'original': str(source), 'canonical': str(target.relative_to(A)),
            'original_bytes': count, 'original_sha256': digest.hexdigest(),
            'canonical_bytes': packed_size, 'canonical_sha256': packed_hash,
            'decoded_bytes': decoded_size, 'decoded_sha256': decoded_hash,
            'codec': 'gzip-mtime0-lossless' if compressed else 'original-bytes',
            'verification_domain': 'original file bytes; existing gz/zip originals are not decoded',
            'source_stat_before': before, 'source_stat_after': after,
            'source_stat_stable': True, 'decoded_bytes_verified': True}


def write_json(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze', required=True)
    args = parser.parse_args(argv)
    require(args.freeze == FREEZE, 'this packager is fixed to the sole V45 freeze')
    require(not any(path.exists() or path.is_symlink() for path in (DEST, INVENTORY, FAILED)),
            'exclusive archive or previous failure already exists; preserve it')
    entries, current_target = [], None
    try:
        closed = closure_guard(args.freeze)
        selected, links, directories, missing = discover()
        for row in selected.values():
            require(not row['target'].exists() and not row['target'].is_symlink(),
                    'canonical output already exists: ' + str(row['target']))
        DEST.mkdir(exist_ok=False)
        for source, row in sorted(selected.items()):
            current_target = str(row['target'])
            entries.append(archive(source, row))
        require(discover() == (selected, links, directories, missing),
                'source membership or stat changed during the complete archive')
        require(closure_guard(args.freeze) == closed, 'closure metadata changed during archive')
        value = {'schema': 'mr3-v45-closed-byte-archive-v1', 'freeze': args.freeze,
                 'purpose': 'Post-wait lossless byte archival only; original activity results preserved.',
                 'byte_archive_complete': True, 'scientific_results_recomputed': False,
                 'fees_recomputed': False, 'models_loaded': False,
                 'closure_metadata': closed, 'missing_optional_roots': missing,
                 'coverage': 'All regular files and symlink metadata in the fixed roots; no link targets followed.',
                 'links': [links[path] for path in sorted(links)], 'link_count': len(links),
                 'external_link_targets_not_followed': [row for row in links.values()
                    if row['target_scope'] == 'outside-known-source-roots'],
                 'entries': entries, 'files': len(entries),
                 'original_bytes': sum(row['original_bytes'] for row in entries),
                 'canonical_bytes': sum(row['canonical_bytes'] for row in entries)}
        write_json(INVENTORY, value)
        print(json.dumps({'byte_archive_complete': True, 'files': len(entries),
                          'inventory': str(INVENTORY)}), flush=True)
        return 0
    except BaseException as error:
        write_json(FAILED, {'schema': 'mr3-v45-closed-byte-archive-failure-v1',
            'freeze': args.freeze, 'byte_archive_complete': False,
            'error': repr(error), 'last_attempted_target': current_target,
            'completed_entries': entries, 'originals_deleted': False,
            'partial_outputs_preserved': True, 'scientific_results_recomputed': False,
            'fees_recomputed': False})
        raise


if __name__ == '__main__':
    raise SystemExit(main())
