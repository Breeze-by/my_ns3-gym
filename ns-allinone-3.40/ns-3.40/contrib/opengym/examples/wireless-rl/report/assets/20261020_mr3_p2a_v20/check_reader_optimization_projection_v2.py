"""Check a three-reader optimization inverse in a temporary tree only.

This imports no project reader and executes only Git byte commands. A successful
result is a CPU source-projection proof, never scientific qualification.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time


ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = Path('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl')
FREEZE = '3631c788ca46e03a52f34ad48c41611761c17f1e'
MANIFEST_SCHEMA = 'mr3-reach-reader-optimization-projection-manifest-v2'
MODULES = tuple((WIRELESS / 'mr3_learning' / name).as_posix() for name in (
    'audit_reach_information.py', 'audit_reach_peer_control.py', 'audit_reach_runtime.py'))
RUNTIME = MODULES[-1]
IMMUTABLE_RUNTIME = (
    'require', 'canonical', 'decode_text', 'same', 'digest', 'integer', 'fields',
    'sec_ns', 'state_ns', 'source', 'vector', 'raw_check', 'xy', 'axis',
    'target_check', 'calibration_check', 'intent_check', 'residual_squared_upper',
    'trig_bounds', 'nonclosing', 'intent_role', 'state_geometry', 'independent_pair',
    'admitted_command', 'Inputs', 'source_proof', 'graph_identity', 'copy_value',
    'replay_robot', 'audit_episode', 'run_workers', 'discover_attempts',
    'audit_episode_set', 'audit', 'main',
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_keys(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), label + ' keys differ')


def sha_value(value, label):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{64}', value) is not None,
            label + ' must be a lowercase SHA256')
    return value


def json_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate JSON member: ' + key)
        value[key] = item
    return value


def invalid_constant(value):
    raise ValueError('nonfinite JSON constant: ' + value)


def capture(path):
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'regular nonsymlink input required: ' + str(path))
    raw = path.read_bytes()
    after = path.lstat()
    keys = ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    identity = [getattr(before, key) for key in keys]
    require(identity == [getattr(after, key) for key in keys],
            'input changed while hashing: ' + str(path))
    require(len(raw) == before.st_size, 'input byte count differs: ' + str(path))
    return {'path': str(path), 'bytes': len(raw), 'sha256': sha(raw), 'stat': identity}, raw


def actual_argv():
    raw = Path('/proc/self/cmdline').read_bytes()
    require(raw.endswith(b'\0') and raw[:-1], 'nonempty NUL-terminated actual argv required')
    parts = raw[:-1].split(b'\0')
    require(all(parts), 'actual argv has an empty argument')
    return [os.fsdecode(part) for part in parts]


def definitions(raw):
    text = raw.decode('utf-8')
    tree = ast.parse(text)
    found = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            require(node.name not in found, 'duplicate top-level definition: ' + node.name)
            found[node.name] = node
    return text, tree, found


def segment(text, node, *, decorators=False):
    first = node.lineno
    if decorators:
        first = min([first] + [value.lineno for value in node.decorator_list])
    return ''.join(text.splitlines(keepends=True)[first-1:node.end_lineno]).encode('utf-8')


def ast_same(left, right):
    return ast.dump(left, include_attributes=False) == ast.dump(right, include_attributes=False)


def runtime_proof(current_raw, frozen_raw):
    current_text, current_tree, current = definitions(current_raw)
    frozen_text, frozen_tree, frozen = definitions(frozen_raw)
    rows = []
    for name in IMMUTABLE_RUNTIME:
        require(name in current and name in frozen, 'immutable definition missing: ' + name)
        now, old = current[name], frozen[name]
        now_segment = segment(current_text, now, decorators=True)
        old_segment = segment(frozen_text, old, decorators=True)
        require(now_segment == old_segment and ast_same(now, old),
                'immutable runtime source text/AST differs: ' + name)
        rows.append({'name': name, 'current_sha256': sha(now_segment),
                     'frozen_sha256': sha(old_segment), 'bytes': len(old_segment),
                     'complete_source_text_equal': True, 'ast_equal': True})

    # The sole numeric change is a bounded typed cache around the same pure
    # conversion. Its original validation must still execute on every call.
    require('number' in current and 'number' in frozen and '_number_fraction' in current,
            'number/cache definitions missing')
    now, old, helper = current['number'], frozen['number'], current['_number_fraction']
    require(isinstance(now, ast.FunctionDef) and isinstance(old, ast.FunctionDef)
            and isinstance(helper, ast.FunctionDef)
            and ast_same(now.args, old.args) and ast_same(helper.args, old.args)
            and now.returns is old.returns is helper.returns is None
            and not now.decorator_list and not old.decorator_list
            and len(now.body) == len(old.body) == 2 and len(helper.body) == 1,
            'number/cache function structure changed')
    require(ast_same(now.body[0], old.body[0])
            and segment(current_text, now.body[0]) == segment(frozen_text, old.body[0]),
            'original number validation must remain the first unchanged statement')
    expected_return = ast.parse('def number(value):\n    return _number_fraction(value)\n').body[0].body[0]
    expected_decorator = ast.parse('@lru_cache(maxsize=4096, typed=True)\ndef f(value):\n    return value\n').body[0].decorator_list[0]
    require(ast_same(now.body[1], expected_return) and ast_same(helper.body[0], old.body[1])
            and len(helper.decorator_list) == 1
            and ast_same(helper.decorator_list[0], expected_decorator),
            'number cache must preserve the original conversion with typed4096 bound')
    number = {'original_validation_first_text_equal': True,
              'original_validation_sha256': sha(segment(frozen_text, old.body[0])),
              'original_conversion_ast_equal': True,
              'original_conversion_sha256': sha(segment(frozen_text, old.body[1])),
              'cached_conversion_sha256': sha(segment(current_text, helper.body[0])),
              'cache_maxsize': 4096, 'cache_typed': True,
              'validation_outside_cache': True}
    return {'immutable_definitions': rows, 'number_conversion': number,
            'current_top_level_definition_count': len(current),
            'frozen_top_level_definition_count': len(frozen),
            'current_ast_statement_count': len(current_tree.body),
            'frozen_ast_statement_count': len(frozen_tree.body),
            'project_reader_imported': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--patch', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.patch.is_absolute() and args.manifest.is_absolute(),
            'absolute patch and manifest paths required')
    require(args.output.is_absolute() and not args.output.exists() and not args.output.is_symlink(),
            'exclusive absolute output required')
    require(args.output.parent.is_dir(), 'output parent directory must already exist')
    source = Path(__file__).resolve()
    tracked = [source, args.manifest, args.patch]
    require(len(set(map(str, tracked))) == len(tracked), 'input paths must be distinct')
    before, raw_inputs = [], {}
    result = {'schema': 'mr3-reach-reader-optimization-whole-file-inverse-v2',
              'scope': 'CPU source projection only; no scientific replay or qualification',
              'passed': False, 'scientific_pass_claimed': False, 'native_admission': False,
              'native_runs': 0, 'gpu_calls': 0, 'project_reader_imported': False,
              'freeze_reference': FREEZE, 'started_monotonic_ns': time.monotonic_ns(),
              'commands': [], 'modules': [], 'errors': [], 'source_before': before}

    def command(argv, cwd):
        receipt = {'requested_argv': argv, 'cwd': str(cwd), 'spawned': False,
                   'actual_waited': False, 'started_monotonic_ns': time.monotonic_ns()}
        result['commands'].append(receipt)
        try:
            completed = subprocess.run(argv, cwd=cwd, capture_output=True, check=False)
        except BaseException as error:
            receipt.update(ended_monotonic_ns=time.monotonic_ns(),
                           error={'type': type(error).__name__, 'message': str(error)})
            raise
        receipt.update(actual_argv=argv, spawned=True, actual_waited=True,
                       returncode=completed.returncode, ended_monotonic_ns=time.monotonic_ns(),
                       stdout_bytes=len(completed.stdout), stdout_sha256=sha(completed.stdout),
                       stderr=completed.stderr.decode('utf-8', errors='replace'))
        require(completed.returncode == 0, 'Git byte command failed: ' + repr(argv))
        return completed.stdout

    try:
        result['actual_argv'] = actual_argv()
        for path in tracked:
            proof, raw = capture(path)
            before.append(proof)
            raw_inputs[str(path)] = raw
        manifest = json.loads(raw_inputs[str(args.manifest)].decode('utf-8'),
                              object_pairs_hook=json_object, parse_constant=invalid_constant)
        exact_keys(manifest, ('schema', 'freeze', 'patch_sha256', 'modules'), 'manifest')
        require(manifest['schema'] == MANIFEST_SCHEMA and manifest['freeze'] == FREEZE,
                'manifest schema/frozen reference differs')
        require(sha_value(manifest['patch_sha256'], 'patch_sha256') == sha(raw_inputs[str(args.patch)]),
                'patch bytes differ from explicit manifest SHA')
        require(type(manifest['modules']) is list and len(manifest['modules']) == len(MODULES),
                'exactly three reader module bindings required')
        names = []
        for module in manifest['modules']:
            exact_keys(module, ('relative_path', 'current_sha256', 'frozen_sha256'), 'module')
            relative = module['relative_path']
            require(type(relative) is str and relative in MODULES and relative not in names,
                    'unexpected/duplicate reader relative path')
            names.append(relative)
            sha_value(module['current_sha256'], 'current_sha256')
            sha_value(module['frozen_sha256'], 'frozen_sha256')
            origin = ROOT / relative
            require(str(origin) not in raw_inputs, 'duplicate input file path')
            tracked.append(origin)
            proof, raw = capture(origin)
            before.append(proof)
            raw_inputs[str(origin)] = raw
            require(proof['sha256'] == module['current_sha256'],
                    'current reader identity differs: ' + relative)
        require(set(names) == set(MODULES), 'three-reader path set differs')
        result['manifest'] = {'path': str(args.manifest),
                              'sha256': sha(raw_inputs[str(args.manifest)]), 'value': manifest}
        result['patch'] = {'path': str(args.patch), 'sha256': sha(raw_inputs[str(args.patch)]),
                           'bytes': len(raw_inputs[str(args.patch)])}
        frozen_sources = {}
        with tempfile.TemporaryDirectory(prefix='mr3_reader_optimization_inverse_') as temporary:
            mirror = Path(temporary)
            result['temporary_mirror'] = str(mirror)
            # Copy no source, repository, or immutable oracle beyond these three
            # declared current modules; reverse Git commands have no --index.
            for module in manifest['modules']:
                relative = module['relative_path']
                raw = raw_inputs[str(ROOT / relative)]
                target = mirror / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open('xb') as stream:
                    stream.write(raw)
                require(target.read_bytes() == raw, 'temporary reader copy differs')
            # Bind the patch used by Git to the captured bytes as well as its
            # outer before/after proof, avoiding a path reread during application.
            temporary_patch = mirror / 'combined_optimization.patch'
            with temporary_patch.open('xb') as stream:
                stream.write(raw_inputs[str(args.patch)])
            command(['git', 'apply', '--reverse', '--check', '--', str(temporary_patch)], mirror)
            command(['git', 'apply', '--reverse', '--', str(temporary_patch)], mirror)
            temporary_patch.unlink()
            actual_files = set()
            for path in mirror.rglob('*'):
                mode = path.lstat().st_mode
                require(stat.S_ISREG(mode) or stat.S_ISDIR(mode),
                        'unexpected temporary mirror symlink/special file')
                if stat.S_ISREG(mode):
                    actual_files.add(path.relative_to(mirror).as_posix())
            require(actual_files == set(MODULES), 'reverse patch changed the three-file mirror scope')
            for module in manifest['modules']:
                relative = module['relative_path']
                git_source = FREEZE + ':' + relative
                frozen = command(['git', 'show', git_source], ROOT)
                restored = (mirror / relative).read_bytes()
                require(sha(frozen) == module['frozen_sha256'], 'frozen Git blob SHA differs: ' + relative)
                require(restored == frozen, 'whole-file inverse differs from frozen Git bytes: ' + relative)
                frozen_sources[relative] = frozen
                result['modules'].append({'relative_path': relative,
                    'current_sha256': module['current_sha256'], 'restored_sha256': sha(restored),
                    'restored_bytes': len(restored), 'git_source': git_source,
                    'git_blob_sha256': sha(frozen), 'git_blob_bytes': len(frozen),
                    'whole_file_inverse_equal': True})
        result['temporary_mirror_removed'] = not mirror.exists()
        require(result['temporary_mirror_removed'], 'temporary mirror was not removed')
        result['runtime_unchanged_mathematical_sources'] = runtime_proof(
            raw_inputs[str(ROOT / RUNTIME)], frozen_sources[RUNTIME])
        after = [capture(path)[0] for path in tracked]
        result['source_after'] = after
        require(before == after, 'source/patch/manifest bytes or stat changed')
        result.update(passed=True, source_unchanged=True, whole_file_inverse_equal=True,
                      original_modules_unmodified=True)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'message': str(error)})
        try:
            result['source_after'] = [capture(path)[0] for path in tracked]
            result['source_unchanged'] = before == result['source_after']
        except BaseException as source_error:
            result['errors'].append({'type': type(source_error).__name__, 'message': str(source_error)})
    result['ended_monotonic_ns'] = time.monotonic_ns()
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'source_unchanged': result.get('source_unchanged'),
                      'modules': len(result['modules']), 'output': str(args.output),
                      'scientific_pass_claimed': False, 'errors': result['errors']}, sort_keys=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
