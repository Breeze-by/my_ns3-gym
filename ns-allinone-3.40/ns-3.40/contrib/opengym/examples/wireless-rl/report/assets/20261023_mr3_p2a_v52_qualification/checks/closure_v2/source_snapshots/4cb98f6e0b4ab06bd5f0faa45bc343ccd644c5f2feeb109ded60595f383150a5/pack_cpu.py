"""CPU archive mechanism. Run only after root declares every selected scope closed.

This tool copies bytes and records file integrity. It does not interpret scientific
PASS/FAIL, invent missing fields, authorize execution, or impose research gates.
"""
import argparse
from collections import Counter
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import stat
import tarfile

CHUNK = 1024 * 1024
PART_BYTES = 49_000_000


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def signature(path):
    value = Path(path).stat()
    return [value.st_dev, value.st_ino, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns]


def stable_file(path, expected_sha=None):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'regular file required: ' + str(path))
    before = signature(path)
    digest = sha(path)
    require(signature(path) == before, 'file changed while hashing: ' + str(path))
    require(expected_sha is None or digest == expected_sha, 'bound SHA differs: ' + str(path))
    return {'path': str(path), 'bytes': before[2], 'sha256': digest, 'stat': before}


def save(path, value):
    with Path(path).open('x') as target:
        json.dump(value, target, indent=2, allow_nan=False)
        target.write('\n')


def member_name(value):
    require(isinstance(value, str), 'archive member name must be a string')
    path = PurePosixPath(value)
    require(value and path.parts and '\x00' not in value and not path.is_absolute()
            and value == path.as_posix() and all(p not in ('', '.', '..') for p in path.parts),
            'unsafe/noncanonical archive member: ' + str(value))
    return value


def tree_snapshot(root):
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'regular directory required: ' + str(root))
    rows = []
    for path in sorted(root.rglob('*')):
        mode = path.lstat().st_mode
        require(not stat.S_ISLNK(mode), 'symlink not archived: ' + str(path))
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), 'special file not archived: ' + str(path))
        rows.append([path.relative_to(root).as_posix(), 'directory' if stat.S_ISDIR(mode) else 'file'])
    return rows


def selection_entries(selection, output):
    """Enumerate explicit selected trees/files; never discover runtime/PPO scopes."""
    require(isinstance(selection.get('closed_scope_declaration'), str)
            and selection['closed_scope_declaration'].strip(), 'root closed-scope declaration missing')
    require(selection.get('roots') or selection.get('files'), 'no explicit closed inputs selected')
    output = Path(output).resolve()
    entries, trees = [], []
    names, sources = set(), set()

    def add(path, name, group):
        path = Path(path).absolute()
        require(not path.is_relative_to(output), 'input inside output attempt: ' + str(path))
        member_name(name)
        require(name not in names, 'duplicate archive member: ' + name)
        resolved = str(path.resolve(strict=True))
        require(resolved not in sources, 'duplicate original input: ' + resolved)
        names.add(name)
        sources.add(resolved)
        entries.append({'original_path': str(path), 'path': name, 'group': group})

    for root in selection.get('roots', []):
        path = Path(root['path']).absolute()
        require(not output.is_relative_to(path) and not path.is_relative_to(output),
                'selected tree and output overlap: ' + str(path))
        prefix = member_name(root['member_prefix'])
        snapshot = tree_snapshot(path)
        trees.append({'path': str(path), 'entries': snapshot})
        for relative, kind in snapshot:
            if kind == 'file':
                add(path / relative, prefix + '/' + relative, root['group'])
    for item in selection.get('files', []):
        add(item['path'], item['member'], item['group'])
    return entries, trees


def check_tree_end(trees):
    for tree in trees:
        require(tree_snapshot(tree['path']) == tree['entries'],
                'selected directory membership changed: ' + tree['path'])


def reference_records(selection):
    rows = []
    for reference in selection['references']:
        bound = stable_file(reference['manifest_path'], reference['manifest_sha256'])
        value = json.loads(Path(reference['manifest_path']).read_bytes())
        require(value['archive_sha256'] == reference['archive_sha256'],
                'referenced archive identity differs')
        rows.append({'label': reference['label'], 'manifest': bound,
                     'archive_sha256': value['archive_sha256'],
                     'archive_bytes': value['archive_bytes'], 'parts': value['parts'],
                     'reference_only': True,
                     'original_parts_rehashed_by_this_pack': False})
    require(len(rows) == 2, 'select the original matrix and reset completion references')
    require({row['manifest']['sha256'] for row in rows} == {
        '914f9428cc0c0b2970e87571d77f977e144cd4f897c6d12f9747f67e0bb6d65d',
        '399caea5c6893689d8808c8c6fbc39486ac9d869df9f15a8da4503437d02bd86'},
        'unexpected predecessor packet manifest identities')
    return rows


def verification_records(selection):
    rows, seen = [], set()
    for binding in selection.get('verification_only_bindings', []):
        path = Path(binding['path']).resolve(strict=True)
        require(str(path) not in seen, 'duplicate verification-only binding: ' + str(path))
        seen.add(str(path))
        row = stable_file(path, binding['sha256'])
        require(binding.get('bytes', row['bytes']) == row['bytes'], 'bound verification size differs')
        rows.append({**row, 'original_binding_path': binding['path'],
                     'group': binding['group'], 'copied_into_archive': False})
    return rows


def verify_end(rows):
    for row in rows:
        path = Path(row.get('original_path', row['path']))
        if row.get('original_binding_path'):
            require(Path(row['original_binding_path']).resolve(strict=True) == path,
                    'verification binding resolved target changed: ' + row['original_binding_path'])
        require(signature(path) == row['stat'] and sha(path) == row['sha256']
                and signature(path) == row['stat'], 'input changed before seal: ' + str(path))


def roundtrip(archive_path, rows):
    expected, seen = {row['path']: row for row in rows}, set()
    with tarfile.open(archive_path, 'r:gz') as archive:
        for member in archive:
            require(member.isfile() and member.name in expected and member.name not in seen,
                    'unexpected/duplicate/non-file tar member: ' + member.name)
            seen.add(member.name)
            digest, size = hashlib.sha256(), 0
            with archive.extractfile(member) as source:
                for block in iter(lambda: source.read(CHUNK), b''):
                    digest.update(block)
                    size += len(block)
            require(size == expected[member.name]['bytes']
                    and digest.hexdigest() == expected[member.name]['sha256'],
                    'tar member SHA/size mismatch: ' + member.name)
    require(seen == set(expected), 'missing tar members')
    # tar EOF can precede gzip EOF; separately drain gzip to validate its trailer.
    with gzip.open(archive_path, 'rb') as source:
        while source.read(CHUNK):
            pass


def split_archive(archive_path, output):
    parts = []
    with archive_path.open('rb') as source:
        part_index = 0
        while True:
            block = source.read(PART_BYTES)
            if not block:
                break
            path = output / ('closed.tar.gz.part%04d' % part_index)
            with path.open('xb') as target:
                target.write(block)
            require(0 < path.stat().st_size <= PART_BYTES, 'part size bound failed')
            require(path.stat().st_size == len(block), 'short part write')
            parts.append({'path': path.name, 'bytes': len(block), 'sha256': sha(path)})
            part_index += 1
    concatenated, size = hashlib.sha256(), 0
    for part in parts:
        with (output / part['path']).open('rb') as source:
            for block in iter(lambda: source.read(CHUNK), b''):
                concatenated.update(block)
                size += len(block)
    require(size == archive_path.stat().st_size and concatenated.hexdigest() == sha(archive_path),
            'part concatenation differs from original archive')
    return parts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    require(output.is_relative_to('/tmp') and output != Path('/tmp'), 'output must be an exclusive /tmp attempt')
    require(output.is_dir() and {p.name for p in output.iterdir()} == {'checks'},
            'launcher must create a fresh attempt containing only checks/')
    selected = stable_file(args.selection.resolve())
    selection = json.loads(args.selection.read_bytes())
    references = reference_records(selection)
    verification = verification_records(selection)
    entries, trees = selection_entries(selection, output)
    rows = []
    for entry in entries:
        bound = stable_file(entry['original_path'])
        rows.append({**entry, 'bytes': bound['bytes'], 'sha256': bound['sha256'], 'stat': bound['stat']})
    require(rows, 'selected closed inventory contains no files')
    inventory = {'closed_scope_declaration': selection['closed_scope_declaration'],
                 'root_scope_notes': selection.get('scope_notes'),
                 'files': rows, 'file_count': len(rows), 'raw_bytes': sum(row['bytes'] for row in rows),
                 'file_counts_by_group': dict(Counter(row['group'] for row in rows)),
                 'directory_membership': trees}
    save(output / 'inventory_draft.json', inventory)
    save(output / 'prior_packet_references.json', references)
    save(output / 'verification_only_bindings.json', verification)
    print(json.dumps({key: inventory[key] for key in ('file_count', 'raw_bytes', 'file_counts_by_group')}), flush=True)
    archive_path = output / 'closed.tar.gz'
    with archive_path.open('xb') as destination:
        with gzip.GzipFile(filename='', fileobj=destination, mode='wb', mtime=0, compresslevel=6) as zipped:
            with tarfile.open(fileobj=zipped, mode='w|') as archive:
                for row in rows:
                    info = tarfile.TarInfo(row['path'])
                    info.size, info.mode, info.mtime = row['bytes'], 0o644, 0
                    with Path(row['original_path']).open('rb') as source:
                        archive.addfile(info, source)
                    verify_end([row])
    roundtrip(archive_path, rows)
    parts = split_archive(archive_path, output)
    verify_end(rows + verification + [selected] + [row['manifest'] for row in references])
    check_tree_end(trees)
    direct_paths = [Path(__file__), output / 'checks/pack_launcher.py', args.selection.resolve(), output / 'inventory_draft.json',
                    output / 'prior_packet_references.json', output / 'verification_only_bindings.json']
    direct = []
    for path in direct_paths:
        require(path.is_relative_to(output), 'direct file must be saved inside output by launcher')
        row = stable_file(path)
        direct.append({'path': path.relative_to(output).as_posix(), 'bytes': row['bytes'], 'sha256': row['sha256']})
    result = {'archive_kind': 'closed-scope incremental CPU byte archive',
              'runtime_freeze_reference': '0063aa233ba3008ddcc1eb09ea8068112eea3965',
              'closed_scope_declaration': selection['closed_scope_declaration'],
              'root_scope_notes': selection.get('scope_notes'),
              'file_count': len(rows), 'raw_bytes': inventory['raw_bytes'],
              'file_counts_by_group': inventory['file_counts_by_group'], 'files': rows,
              'parts': parts, 'direct_files': direct,
              'archive_bytes': archive_path.stat().st_size, 'archive_sha256': sha(archive_path),
              'all_tar_members_sha_size_roundtrip_verified': True, 'gzip_eof_crc_verified': True,
              'parts_concatenation_sha_verified': True,
              'all_selected_input_stat_sha_stable_end_verified': True,
              'selected_directory_membership_stable_end_verified': True,
              'verification_only_bindings_provided': bool(verification),
              'verification_only_bindings_stat_sha_stable_end_verified': True if verification else None,
              'verification_only_counts_by_group': dict(Counter(row['group'] for row in verification)),
              'prior_packet_references': references, 'prior_packet_raw_repacked': False,
              'scope': 'Only explicitly selected closed bytes. Original failures and all unknown fields remain in unchanged original files. No scientific result reinterpretation, historical role credit, new execution authorization, Git HEAD equality assertion, or inferred unexecuted PPO evidence. CPU pack wait and actual creator tool metadata are appended outside this sealed manifest.'}
    save(output / 'manifest.json', result)
    archive_path.unlink()
    print(json.dumps({key: result[key] for key in ('file_count', 'raw_bytes', 'archive_bytes', 'archive_sha256', 'parts')}), flush=True)


if __name__ == '__main__':
    main()
