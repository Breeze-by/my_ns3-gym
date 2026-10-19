#!/usr/bin/python3
"""Exclusive, lossless regular-file archive packaging; no scientific credit."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tarfile
import time

MAX_PART = 80_000_000
BLOCK = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def metadata(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, stat.S_IMODE(value.st_mode)]


def dump_new(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def no_symlink_ancestors(path):
    require(path.is_absolute(), 'absolute path required: ' + str(path))
    for item in (path, *path.parents):
        if item.exists() or item.is_symlink():
            require(not item.is_symlink(), 'symlink path component: ' + str(item))


def file_digest(stream):
    digest, size = hashlib.sha256(), 0
    for block in iter(lambda: stream.read(BLOCK), b''):
        digest.update(block)
        size += len(block)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def open_regular(root_fd, relative):
    parts = Path(relative).parts
    require(parts and all(part not in ('', '.', '..') for part in parts)
            and not Path(relative).is_absolute(), 'unsafe relative file path')
    parent = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent)
            parent = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            require(stat.S_ISREG(os.fstat(fd).st_mode), 'nonregular file: ' + relative)
        except BaseException:
            os.close(fd)
            raise
        return os.fdopen(fd, 'rb')
    finally:
        os.close(parent)


def inventory(root, root_fd):
    require(metadata(root.lstat()) == metadata(os.fstat(root_fd)), 'source root identity changed')
    files, directories = [], []
    for current, dirs, names, current_fd in os.fwalk('.', topdown=True, follow_symlinks=False, dir_fd=root_fd):
        dirs.sort()
        names.sort()
        relative_dir = Path(current)
        directories.append(relative_dir.as_posix())
        for name in dirs:
            value = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
            require(stat.S_ISDIR(value.st_mode), 'symlink/special directory entry: ' + str(relative_dir / name))
        for name in names:
            value = os.stat(name, dir_fd=current_fd, follow_symlinks=False)
            relative = (relative_dir / name).as_posix()
            require(stat.S_ISREG(value.st_mode), 'symlink/special file entry: ' + relative)
            with open_regular(root_fd, relative) as stream:
                before = metadata(os.fstat(stream.fileno()))
                require(before == metadata(value), 'source entry changed before open: ' + relative)
                content = file_digest(stream)
                require(before == metadata(os.fstat(stream.fileno())), 'source changed while hashing: ' + relative)
            require(content['bytes'] == value.st_size, 'source size changed while hashing: ' + relative)
            files.append({'relative_path': relative, **content, 'stat': before})
    files.sort(key=lambda item: item['relative_path'])
    require(len(files) == len({item['relative_path'] for item in files}), 'duplicate source relative path')
    require(metadata(root.lstat()) == metadata(os.fstat(root_fd)), 'source root identity changed')
    return {'directories': sorted(directories), 'files': files,
            'regular_file_count': len(files), 'regular_file_bytes': sum(item['bytes'] for item in files)}


def pack(root_fd, before, temporary):
    with temporary.open('xb') as compressed:
        with tarfile.open(fileobj=compressed, mode='w|xz', format=tarfile.PAX_FORMAT) as archive:
            for item in before['files']:
                relative = item['relative_path']
                with open_regular(root_fd, relative) as stream:
                    require(metadata(os.fstat(stream.fileno())) == item['stat'], 'source changed before packing: ' + relative)
                    header = tarfile.TarInfo(relative)
                    header.size = item['bytes']
                    header.mode = item['stat'][-1]
                    header.mtime = item['stat'][3] // 1_000_000_000
                    archive.addfile(header, stream)
                    require(metadata(os.fstat(stream.fileno())) == item['stat'], 'source changed while packing: ' + relative)
        compressed.flush()
        os.fsync(compressed.fileno())
    with temporary.open('rb') as stream:
        return file_digest(stream)


def split(temporary, output, label, part_bytes):
    parts = []
    with temporary.open('rb') as stream:
        ordinal = 0
        while True:
            chunk = stream.read(part_bytes)
            if not chunk:
                break
            ordinal += 1
            name = f'{label}.tar.xz.part{ordinal:04d}'
            path = output / name
            with path.open('xb') as target:
                target.write(chunk)
                target.flush()
                os.fsync(target.fileno())
            parts.append({'ordinal': ordinal, 'relative_path': name, 'bytes': len(chunk),
                          'sha256': hashlib.sha256(chunk).hexdigest()})
    require(parts and all(0 < row['bytes'] <= part_bytes for row in parts), 'invalid compressed part inventory')
    return parts


class ConcatenatedParts(io.RawIOBase):
    def __init__(self, output, parts):
        super().__init__()
        self.output, self.parts = output, parts
        self.index, self.current, self.current_digest, self.current_size = 0, None, None, 0
        self.digest, self.size, self.verified_parts = hashlib.sha256(), 0, []

    def readable(self):
        return True

    def readinto(self, buffer):
        destination = memoryview(buffer).cast('B')
        written = 0
        while written < len(destination):
            if self.current is None:
                if self.index == len(self.parts):
                    break
                spec = self.parts[self.index]
                fd = os.open(self.output / spec['relative_path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                value = os.fstat(fd)
                if not stat.S_ISREG(value.st_mode) or value.st_size != spec['bytes']:
                    os.close(fd)
                    raise ValueError('compressed part type/size changed')
                self.current = os.fdopen(fd, 'rb')
                self.current_digest, self.current_size = hashlib.sha256(), 0
            block = self.current.read(len(destination) - written)
            if block:
                destination[written:written + len(block)] = block
                self.digest.update(block)
                self.current_digest.update(block)
                self.size += len(block)
                self.current_size += len(block)
                written += len(block)
            else:
                actual = {'ordinal': self.index + 1, 'relative_path': self.parts[self.index]['relative_path'],
                          'bytes': self.current_size, 'sha256': self.current_digest.hexdigest()}
                require(actual == self.parts[self.index], 'compressed part SHA changed during readback')
                self.verified_parts.append(actual)
                self.current.close()
                self.current = None
                self.index += 1
        return written

    def close(self):
        if self.current is not None:
            self.current.close()
            self.current = None
        super().close()


def readback(output, parts, expected, logical):
    expected_by_name = {row['relative_path']: row for row in expected['files']}
    actual = []
    with ConcatenatedParts(output, parts) as joined:
        with io.BufferedReader(joined, buffer_size=BLOCK) as buffered:
            with tarfile.open(fileobj=buffered, mode='r|xz') as archive:
                seen = set()
                for member in archive:
                    require(member.isfile() and not member.issparse(), 'archive contains a nonregular/sparse member')
                    require(member.name in expected_by_name and member.name not in seen, 'unexpected/duplicate archive member')
                    seen.add(member.name)
                    spec = expected_by_name[member.name]
                    require(member.size == spec['bytes'], 'archive header size differs: ' + member.name)
                    extracted = archive.extractfile(member)
                    require(extracted is not None, 'archive member data unavailable')
                    with extracted:
                        content = file_digest(extracted)
                    require(content == {key: spec[key] for key in ('bytes', 'sha256')}, 'archive member SHA/bytes differ: ' + member.name)
                    actual.append({'relative_path': member.name, **content})
            # tar readers may stop at the tar end marker before compressed EOF.
            while buffered.read(BLOCK):
                pass
            require(joined.size == logical['bytes'] and joined.digest.hexdigest() == logical['sha256'],
                    'ordered compressed concatenation differs from logical tar.xz')
            require(joined.verified_parts == parts, 'not all compressed parts reached verified EOF')
    require([row['relative_path'] for row in actual] == [row['relative_path'] for row in expected['files']],
            'archive member order or complete file inventory differs')
    return {'members': actual, 'member_count': len(actual), 'all_member_bytes_and_sha_equal': True,
            'ordered_part_concatenation_equal': True, 'verified_parts': parts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--label', required=True)
    parser.add_argument('--part-bytes', type=int, default=MAX_PART)
    args = parser.parse_args(argv)
    source, output = args.source_root, args.output_dir
    require(source.is_absolute() and output.is_absolute(), 'source/output must be absolute paths')
    source, output = Path(os.path.abspath(source)), Path(os.path.abspath(output))
    require(1 <= args.part_bytes <= MAX_PART, 'part-bytes must be between1 and80000000')
    require(re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', args.label) is not None, 'unsafe archive label')
    no_symlink_ancestors(output)
    require(not output.exists(), 'output already exists; original evidence must not be overwritten')
    require(output != source and not output.is_relative_to(source) and not source.is_relative_to(output),
            'source/output roots must not contain each other')
    output.mkdir(mode=0o755)
    started = time.monotonic_ns()
    attempt = {'schema': 'mr3-regular-file-archive-attempt-v1', 'scope': 'packaging_only',
        'source_root': str(source), 'output_directory': str(output), 'label': args.label,
        'part_bytes': args.part_bytes, 'actual_argv': [sys.executable, *sys.argv],
        'started_monotonic_ns': started, 'scientific_pass_claimed': False, 'native_credit': False}
    dump_new(output / 'attempt.json', attempt)
    manifest = dict(attempt, schema='mr3-regular-file-archive-manifest-v1', passed=False, errors=[])
    root_fd = None
    phase = 'source_admission'
    rc = 1
    temporary = output / ('.' + args.label + '.logical.tar.xz.partial')
    try:
        no_symlink_ancestors(source)
        require(source.is_dir(), 'source root is not a directory')
        root_fd = os.open(source, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        manifest['source_root_stat_before'] = metadata(os.fstat(root_fd))
        phase = 'source_inventory_before'
        before = inventory(source, root_fd)
        manifest['source_inventory_before'] = before
        dump_new(output / 'source_inventory_before.json', before)
        phase = 'tar_xz_pack'
        logical = pack(root_fd, before, temporary)
        manifest['logical_tar_xz'] = logical
        phase = 'split'
        parts = split(temporary, output, args.label, args.part_bytes)
        manifest['ordered_parts'] = parts
        phase = 'ordered_concat_tar_readback'
        manifest['readback'] = readback(output, parts, before, logical)
        phase = 'source_inventory_after'
        after = inventory(source, root_fd)
        manifest['source_inventory_after'] = after
        dump_new(output / 'source_inventory_after.json', after)
        require(before == after, 'source inventory/fileset/stat/bytes/SHA changed during packaging')
        require(metadata(source.lstat()) == manifest['source_root_stat_before'], 'source root changed during packaging')
        output_fd = os.open(output, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for row in parts:
                with open_regular(output_fd, row['relative_path']) as stream:
                    require(file_digest(stream) == {key: row[key] for key in ('bytes', 'sha256')}, 'part changed after readback')
        finally:
            os.close(output_fd)
        temporary.unlink()
        manifest.update(passed=True, source_unchanged=True, source_originals_preserved=True,
                        temporary_logical_file_removed_after_success=True)
        phase = 'complete'
        rc = 0
    except BaseException as error:
        manifest['errors'].append({'phase': phase, 'type': type(error).__name__, 'message': str(error)})
        manifest.update(partial_outputs_preserved=True, source_originals_preserved=True)
    finally:
        if root_fd is not None:
            os.close(root_fd)
    manifest.update(ended_monotonic_ns=time.monotonic_ns(), final_phase=phase,
                    output_inventory=sorted(path.name for path in output.iterdir()))
    dump_new(output / 'manifest.json', manifest)
    print(json.dumps({'passed': manifest['passed'], 'manifest': str(output / 'manifest.json'),
                      'scope': 'packaging_only', 'native_credit': False, 'errors': manifest['errors']}))
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
