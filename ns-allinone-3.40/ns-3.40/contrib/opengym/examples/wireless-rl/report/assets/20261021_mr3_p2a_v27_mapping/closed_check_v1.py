"""V27 CPU metadata/source closure only; never compute mapping or create a backend."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

A = Path(__file__).resolve().parent
ROOT = next(path for path in A.parents if (path / '.git').exists())
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
BASE = '53d3c90090e491bf64e79f82318247a78caec907'
BACKUP = '8fe1495b6624cd9136f3ce160acaa274428e54ae'
NEW_ARCHIVE_KEY = 'mr3_p2a_v27_mapping_20261021'


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def read(path):
    return json.loads(path.read_text())


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def local(path):
    result = (A / path).resolve()
    assert result.is_relative_to(A), ('index path outside V27', path)
    return result


def absent(saved):
    pid, start = saved['pid'], saved['start_ticks']
    assert type(pid) is int and pid > 0 and type(start) is int and start > 0
    try:
        raw = (Path('/proc') / str(pid) / 'stat').read_text()
    except FileNotFoundError:
        return {'saved_identity': saved, 'status': 'gone'}
    # No broad exception handler: unreadable or malformed /proc fails closure.
    end = raw.rfind(')')
    assert end > 0
    fields = raw[end + 2:].split()
    current_start = int(fields[19])
    assert current_start != start, ('saved process still present, including Z', saved, fields[0])
    return {'saved_identity': saved, 'status': 'reused_original_absent',
            'current_start_ticks': current_start, 'current_state': fields[0]}


def check():
    index = read(A / 'cpu_validation_index_v1.json')
    assert isinstance(index['checks'], list) and index['checks']
    identities, receipts, source_paths = {}, set(), set()
    cpu_seconds = Decimal(0)
    for item in index['checks']:
        path = local(item['receipt'])
        assert path not in receipts, ('duplicate receipt', path)
        receipts.add(path)
        row = read(path)
        assert row['scope'] == 'cpu' and row['passed'] is True
        assert row['actual_waited'] is True and type(row['actual_returncode']) is int
        assert row['actual_returncode'] == 0 and row['errors'] == []
        assert row['source_unchanged'] is True and row['source_before'] == row['source_after']
        assert isinstance(row['source_after'], list) and row['source_after']
        start, end = row['started_monotonic_ns'], row['ended_monotonic_ns']
        assert type(start) is int and type(end) is int and 0 < start < end
        seconds = Decimal(row['actual_child_wait_seconds'])
        assert seconds == Decimal(end - start) / Decimal(10**9)
        cpu_seconds += seconds
        for source in row['source_after']:
            source_path = Path(source['path']).resolve()
            assert source_path.is_relative_to(ROOT), source_path
            raw = source_path.read_bytes()
            assert digest(raw) == source['sha256'] and len(raw) == source['bytes'], source_path
            source_paths.add(str(source_path))
        console = path.with_name('console.log')
        assert Path(row['console']['path']).resolve() == console.resolve()
        assert digest(console.read_bytes()) == row['console']['sha256'], console
        if 'pytest_passed' in item:
            count = item['pytest_passed']
            assert type(count) is int and count > 0
            assert re.search(r'\b' + str(count) + r' passed\b', console.read_text()), console
        for label in ('coordinator_identity', 'child_identity'):
            saved = row[label]
            assert isinstance(saved, dict), (path, label)
            key = (saved['pid'], saved['start_ticks'])
            if key not in identities:
                identities[key] = absent(saved)

    generated = index['generated']
    assert isinstance(generated, list) and generated
    generated_paths = set()
    for item in generated:
        path = local(item['path'])
        assert path not in generated_paths, ('duplicate generated artifact', path)
        generated_paths.add(path)
        raw = path.read_bytes()
        assert digest(raw) == item['sha256'] and len(raw) == item['bytes'], path
    assert A / 'mapping_comparison_v1.json' in generated_paths

    # Only new candidate/tests/artifacts may be added; all existing runtime and
    # old evidence bytes must remain as at the V26 closure baseline.
    baseline_files = set(git('ls-tree', '-r', '--name-only', '-z', BASE).decode().split('\0'))
    changed = set(filter(None, git('diff', '--no-renames', '--name-only', '-z', BASE).decode().split('\0')))
    archive = str((W / 'report/ARCHIVE_INDEX.json').relative_to(ROOT))
    old_assets = str((W / 'report/assets').relative_to(ROOT)) + '/'
    existing_changes = changed & baseline_files
    for relative in sorted(existing_changes):
        assert not relative.startswith(old_assets), ('old evidence changed', relative)
        assert relative in (archive, '.gitattributes') or Path(relative).suffix == '.md', (
            'existing program/configuration changed', relative)
        assert (ROOT / relative).is_file(), ('existing file deleted', relative)

    log = str((W / 'log.md').relative_to(ROOT))
    assert (ROOT / log).read_bytes().startswith(git('show', BASE + ':' + log)), 'log is not append-only'
    before = json.loads(git('show', BASE + ':' + archive))
    after = read(ROOT / archive)
    assert all(key in after and after[key] == value for key, value in before.items()), 'old archive entry changed'
    assert set(after) - set(before) <= {NEW_ARCHIVE_KEY}, 'unexpected archive entry added'
    attributes_before = git('show', BASE + ':.gitattributes')
    attributes_after = (ROOT / '.gitattributes').read_bytes()
    assert attributes_after.startswith(attributes_before), 'old attributes changed'
    added_lines = [line for line in attributes_after[len(attributes_before):].decode().splitlines() if line.strip()]
    allowed = str(A.relative_to(ROOT)) + '/**/*.log -text -whitespace'
    assert added_lines in ([], [allowed]), ('unexpected attributes addition', added_lines)
    assert git('rev-parse', 'p2c1/global-mission-20261012').decode().strip() == BACKUP

    untracked = set(filter(None, git('ls-files', '--others', '--exclude-standard', '-z').decode().split('\0')))
    documents = {relative for relative in changed | untracked if Path(relative).suffix == '.md'}
    links = 0
    for relative in sorted(documents):
        path = ROOT / relative
        for target in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text()):
            if target.startswith('<'):
                target = target[1:].split('>', 1)[0]
            else:
                target = target.split()[0]
            if target.startswith('#') or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:', target):
                continue
            target = unquote(target.split('#', 1)[0])
            if target:
                assert (path.parent / target).exists(), ('missing relative link', relative, target)
                links += 1

    plan = read(A / 'predeclared_plan_v1.json')
    assert plan['baseline'] == BASE
    assert plan['new_engineering_seconds'] == '0'
    assert plan['engineering_used'] == '45445.4237026666018'
    assert plan['engineering_remaining'] == '6554.5762973333982'
    assert plan['engineering_limit'] == '52000'
    assert plan['pilot_decisions_remaining'] == 1870
    assert plan['pilot_seconds_remaining'] == '2905.9547395464029'
    assert plan['final_only'] == '401/402/403 unused'
    assert plan['production_enabled'] is False and plan['qualification'] is False
    return {'schema': 'mr3-p2a-v27-cpu-closed-static-v1', 'passed': True, 'scope': __doc__,
            'baseline': BASE, 'cpu_checks': len(receipts), 'cpu_actual_wait_seconds': str(cpu_seconds),
            'current_bound_sources': len(source_paths), 'generated_artifacts': len(generated_paths),
            'saved_cpu_identities_absent': len(identities), 'saved_processes': list(identities.values()),
            'existing_tracked_changes': sorted(existing_changes), 'relative_links': links,
            'existing_program_configuration_and_prior_evidence_unchanged': True,
            'log_append_only': True, 'old_archive_entries_unchanged': True,
            'new_engineering_seconds': '0', 'cumulative_engineering_seconds': '45445.4237026666018',
            'remaining_engineering_seconds': '6554.5762973333982', 'qualification': False,
            'training_eligible': False, 'native_credit': False}


def main():
    # Reserve the exclusive output first; the report may already link to it.
    with (A / 'static_result_v1.json').open('x') as stream:
        try:
            result = check()
        except Exception as error:
            result = {'schema': 'mr3-p2a-v27-cpu-closed-static-v1', 'passed': False,
                      'scope': __doc__, 'error': repr(error), 'qualification': False,
                      'training_eligible': False, 'native_credit': False}
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
