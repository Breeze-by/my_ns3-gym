"""Whole-file inverse of the sealed owner-index/SHA patch in a temporary tree.

Only Git byte tools execute. No project reader is imported or replayed, and no
native/GPU work runs. This CPU source-projection proof is not qualification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = Path('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl')
FREEZE = '3631c788ca46e03a52f34ad48c41611761c17f1e'
PATCH_SHA = 'f68a92f92b691f4ffe7d7fe818c54820a1df7c72e37404503b18607f7f9d7e06'
MODULES = (
    (WIRELESS / 'mr3_learning/audit_reach_information.py',
     'ffcb403badc8c05c863d9dec9aa7ede27e403567294bb3acc32b60c0e844a27f',
     'ab1bfe144e9ab85276718a6131fe87fd3c90a09a1bd71056acc203c0e0765e30'),
    (WIRELESS / 'mr3_learning/audit_reach_peer_control.py',
     '29f074ecf0d704b4f484ccc1c0c990b0bdf7223e04ffbd44e4af887b038c989f',
     'b4fad008410e4e83de55c02718e28cdd12e9555ef551ca3149061634fcbb7917'),
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def binding(path):
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    keys = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    stat_before = [getattr(before, key) for key in keys]
    require(stat_before == [getattr(after, key) for key in keys], 'input changed while hashing: ' + str(path))
    require(len(raw) == before.st_size, 'input byte count differs: ' + str(path))
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw), 'stat': stat_before}


def actual_argv():
    raw = Path('/proc/self/cmdline').read_bytes()
    require(raw.endswith(b'\0') and raw[:-1], 'nonempty NUL-terminated actual argv required')
    parts = raw[:-1].split(b'\0')
    require(all(parts), 'actual argv has an empty argument')
    return [os.fsdecode(part) for part in parts]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--result', required=True, type=Path)
    args = parser.parse_args()
    require(args.result.is_absolute() and not args.result.exists(), 'exclusive absolute result required')
    source = Path(__file__).resolve()
    patch = source.with_name('mr3_reach_information_owner_index_optimization.patch')
    test = ROOT / WIRELESS / 'mr3_learning/tests/test_reach_information_index_regression.py'
    inputs = [source, patch, *(ROOT / relative for relative, _, _ in MODULES), test]
    started = time.monotonic_ns()
    result = {'schema': 'mr3-reach-information-index-whole-file-inverse-v1',
              'scope': 'CPU source projection only; no scientific replay or qualification',
              'passed': False, 'scientific_pass_claimed': False, 'native_admission': False,
              'native_runs': 0, 'gpu_calls': 0, 'freeze_reference': FREEZE,
              'actual_argv': actual_argv(), 'started_monotonic_ns': started,
              'commands': [], 'modules': [], 'errors': []}

    def command(argv, cwd):
        t0 = time.monotonic_ns()
        completed = subprocess.run(argv, cwd=cwd, capture_output=True, check=False)
        t1 = time.monotonic_ns()
        result['commands'].append({'actual_argv': argv, 'cwd': str(cwd),
            'actual_waited': True, 'returncode': completed.returncode,
            'started_monotonic_ns': t0, 'ended_monotonic_ns': t1,
            'stdout_bytes': len(completed.stdout), 'stdout_sha256': sha(completed.stdout),
            'stderr': completed.stderr.decode('utf-8', errors='replace')})
        require(completed.returncode == 0, 'Git byte command failed: ' + repr(argv))
        return completed.stdout

    try:
        before = [binding(path) for path in inputs]
        result['source_before'] = before
        require(binding(patch)['sha256'] == PATCH_SHA, 'canonical patch SHA differs')
        with tempfile.TemporaryDirectory(prefix='mr3_information_index_inverse_') as temporary:
            mirror = Path(temporary)
            result['temporary_mirror'] = str(mirror)
            for relative, expected_current, _ in MODULES:
                origin, target = ROOT / relative, mirror / relative
                raw = origin.read_bytes()
                require(sha(raw) == expected_current, 'current module identity differs: ' + str(relative))
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(raw)
                require(target.read_bytes() == raw, 'temporary source copy differs')
            # Both applications are confined to the temporary mirror. No --index.
            command(['git', 'apply', '--reverse', '--check', '--', str(patch)], mirror)
            command(['git', 'apply', '--reverse', '--', str(patch)], mirror)
            for relative, expected_current, expected_original in MODULES:
                frozen = command(['git', 'show', FREEZE + ':' + relative.as_posix()], ROOT)
                restored = (mirror / relative).read_bytes()
                require(sha(frozen) == expected_original, 'original Git blob pin differs: ' + str(relative))
                require(restored == frozen, 'whole-file inverse differs from original Git bytes: ' + str(relative))
                result['modules'].append({'relative_path': relative.as_posix(),
                    'current_sha256': expected_current, 'restored_sha256': sha(restored),
                    'restored_bytes': len(restored), 'git_source': FREEZE + ':' + relative.as_posix(),
                    'git_blob_sha256': sha(frozen), 'git_blob_bytes': len(frozen),
                    'whole_file_inverse_equal': True})
        result['temporary_mirror_removed'] = not mirror.exists()
        require(result['temporary_mirror_removed'], 'temporary mirror was not removed')
        after = [binding(path) for path in inputs]
        result['source_after'] = after
        require(before == after, 'current source/patch/test bytes or stat changed')
        result.update(passed=True, source_unchanged=True,
                      whole_file_inverse_equal=True, original_modules_unmodified=True)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'message': str(error)})
        try:
            result['source_after'] = [binding(path) for path in inputs]
            result['source_unchanged'] = result.get('source_before') == result['source_after']
        except BaseException as source_error:
            result['errors'].append({'type': type(source_error).__name__, 'message': str(source_error)})
    result['ended_monotonic_ns'] = time.monotonic_ns()
    with args.result.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'source_unchanged': result.get('source_unchanged'),
                      'module_count': len(result['modules']), 'result': str(args.result),
                      'scientific_pass_claimed': False, 'errors': result['errors']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
