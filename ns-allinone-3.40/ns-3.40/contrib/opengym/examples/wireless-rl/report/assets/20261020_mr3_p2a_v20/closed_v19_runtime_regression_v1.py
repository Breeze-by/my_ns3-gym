#!/usr/bin/python3
"""Compare a declared candidate reader with the original closed V19 result.

This is an engineering diagnostic, not native qualification. Only source_proof
is projected in memory: the candidate reader is explicitly different from the
artifact freeze. Every other original source check, native configuration check,
input loader, core check, and Inputs.close call remains the candidate's own.
"""
import argparse
import ast
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import time
import traceback
import types


ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
EPISODE = ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v19/mr3_p2a_reach_v19_interface/worker0/episode001_open_101'
READER = W/'mr3_learning/audit_reach_runtime.py'
FREEZE = '3631c788ca46e03a52f34ad48c41611761c17f1e'
FROZEN_READER_SHA = '62f4a7e010e1b339eb7bbe7754c56e71baea46dc084b3792d44ec3f1e7ae89d8'
ORIGINAL_RESULT = Path('/tmp/mr3_p2a_reach_v19_matrix/interface/runtime_result.json')
ORIGINAL_RESULT_SHA = '090da423a650cf6511ea52707b42eddc45fadd6be197bf411d2993e624bde784'
DEFAULT_CANDIDATE_SHA = '4f6505f686945927641431a7cc64ee42e1fa5219b9d5f5144c82118fb96d88fa'
DEFAULT_PATCH_SHA = 'cfef27a0c669d09324d522005754c1575e68361c22263c140fb610ee0776731c'
DEFAULT_PATCH = W/'report/assets/20261020_mr3_p2a_v20/runtime_index_optimization_v2.patch'
SCHEMA = 'mr3-v20-closed-v19-runtime-regression-v1'
ROBOTS = ('tb1', 'tb2', 'tb3')
ARTIFACTS = ('metadata.json', 'transitions.jsonl',
    *('drive_'+name+'.jsonl' for name in ROBOTS),
    *('odometry_'+name+'.jsonl' for name in ROBOTS),
    'motion_safety.jsonl', 'physics.jsonl', 'drive_phase_worker.jsonl',
    'control_phase_worker.jsonl', 'information_states.jsonl')
GUARD = '        require(payload == (root/name).read_bytes(), "current source differs from declared freeze: "+name)'
PROJECTED_GUARD = '''        require((payload == (root/name).read_bytes()) if name != reader else
                (root == _DIAGNOSTIC_ROOT and freeze == _DIAGNOSTIC_FREEZE
                 and payload == _DIAGNOSTIC_FROZEN_READER
                 and hashlib.sha256((root/name).read_bytes()).hexdigest() == _DIAGNOSTIC_CANDIDATE_SHA),
                "current source differs from declared freeze: "+name)'''
RETURN = '    return proof'
MARKED_RETURN = '''    proof[reader].update(_DIAGNOSTIC_READER_MARKER)
    return proof'''
sys.dont_write_bytecode = True


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def parse(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON member: '+key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: '+value)))


def stat_identity(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, stat.S_IMODE(value.st_mode)]


def fingerprint(path):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode), 'input is not a regular file: '+str(path))
        digest, size = hashlib.sha256(), 0
        for block in iter(lambda:stream.read(1024*1024), b''):
            digest.update(block)
            size += len(block)
        require(stat_identity(before) == stat_identity(os.fstat(stream.fileno()))
                == stat_identity(path.lstat()) and size == before.st_size,
                'input changed while hashing: '+str(path))
    return {'path':str(path), 'sha256':digest.hexdigest(), 'bytes':size,
            'stat':stat_identity(before)}


def bound_bytes(path):
    proof = fingerprint(path)
    raw = Path(path).read_bytes()
    require(sha(raw) == proof['sha256'] and len(raw) == proof['bytes']
            and stat_identity(Path(path).lstat()) == proof['stat'],
            'bound small input changed: '+str(path))
    return raw, proof


def command(argv, cwd, receipts):
    environment = dict(os.environ)
    for name in ('GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
                 'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES'):
        environment.pop(name, None)
    environment.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')
    started = time.monotonic_ns()
    child = subprocess.run(argv, cwd=cwd, env=environment, capture_output=True, check=False)
    ended = time.monotonic_ns()
    receipts.append({'argv':list(argv), 'cwd':str(cwd), 'returncode':child.returncode,
        'actual_waited':True, 'start_monotonic_ns':started, 'end_monotonic_ns':ended,
        'stdout_sha256':sha(child.stdout), 'stdout_bytes':len(child.stdout),
        'stderr_sha256':sha(child.stderr), 'stderr_bytes':len(child.stderr),
        'stderr':child.stderr.decode('utf-8', 'replace')[:4096]})
    require(child.returncode == 0, 'diagnostic command failed: '+repr(argv))
    return child.stdout


def definition(raw, name):
    text = raw.decode('utf-8')
    nodes = [node for node in ast.parse(text).body
             if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
    require(len(nodes) == 1, 'source definition is not unique: '+name)
    node = nodes[0]
    lines = text.splitlines(keepends=True)
    return ''.join(lines[node.lineno-1:node.end_lineno])


def inverse_proof(candidate_raw, frozen, patch_raw, receipts):
    relative = READER.relative_to(ROOT).as_posix()
    text = patch_raw.decode('utf-8')
    require([line for line in text.splitlines() if line.startswith('--- ')] == ['--- a/'+relative]
            and [line for line in text.splitlines() if line.startswith('+++ ')] == ['+++ b/'+relative],
            'patch must name only the declared runtime reader')
    with tempfile.TemporaryDirectory(prefix='mr3-v20-runtime-inverse-') as temporary:
        work = Path(temporary)
        command(['git', '-c', 'init.defaultBranch=diagnostic', 'init', '--quiet'], work, receipts)
        path = work/relative
        path.parent.mkdir(parents=True)
        path.write_bytes(candidate_raw)
        patch = work/'candidate.patch'
        patch.write_bytes(patch_raw)
        for mode in ('--check', None):
            argv = ['git', 'apply', '--reverse', '--whitespace=nowarn']
            if mode:
                argv.append(mode)
            command(argv+['--', str(patch)], work, receipts)
        restored = path.read_bytes()
        require(restored == frozen, 'whole-source reverse patch is not the frozen Git blob')
        command(['git', 'apply', '--whitespace=nowarn', '--', str(patch)], work, receipts)
        require(path.read_bytes() == candidate_raw, 'whole-source forward patch differs from candidate')
        return {'temporary_git_only':True, 'workspace_git_mutated':False,
            'reverse_whole_source_equals_git':True, 'forward_roundtrip_equals_candidate':True,
            'frozen_sha256':sha(frozen), 'restored_sha256':sha(restored),
            'candidate_sha256':sha(candidate_raw), 'patch_sha256':sha(patch_raw)}


def project_source_proof(module, candidate_raw, frozen, candidate_sha):
    original = definition(candidate_raw, 'source_proof')
    require(original == definition(frozen, 'source_proof'), 'production source_proof was changed')
    require(original.count(GUARD) == 1 and original.count(RETURN) == 1,
            'source_proof projection literals are not unique')
    projected = original.replace(GUARD, PROJECTED_GUARD).replace(RETURN, MARKED_RETURN)
    require(projected.replace(PROJECTED_GUARD, GUARD).replace(MARKED_RETURN, RETURN) == original,
            'source_proof literal projection does not invert exactly')
    marker = {'current_equals_freeze':False, 'diagnostic_candidate_sha256':candidate_sha,
              'diagnostic_only':True, 'scientific_qualification':False, 'native_admission':False}
    module.__dict__.update(_DIAGNOSTIC_ROOT=ROOT, _DIAGNOSTIC_FREEZE=FREEZE,
        _DIAGNOSTIC_FROZEN_READER=frozen, _DIAGNOSTIC_CANDIDATE_SHA=candidate_sha,
        _DIAGNOSTIC_READER_MARKER=marker)
    before = {name:id(value) for name, value in vars(module).items() if callable(value)}
    exec(compile(projected, 'diagnostic-only/source_proof_projection', 'exec'), vars(module))
    after = {name:id(value) for name, value in vars(module).items() if callable(value)}
    require({k:v for k,v in before.items() if k != 'source_proof'}
            == {k:v for k,v in after.items() if k != 'source_proof'},
            'projection changed another candidate callable')
    return marker, {'only_projected_symbol':'source_proof', 'in_memory_only':True,
        'single_guard_replacement_count':1, 'marked_return_replacement_count':1,
        'whole_function_projection_inverse_equal':True,
        'original_function_source_sha256':sha(original.encode()),
        'projected_function_source_sha256':sha(projected.encode()),
        'other_candidate_callable_identities_unchanged':True,
        'core_math_or_inputs_patched':False}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate-sha', default=DEFAULT_CANDIDATE_SHA,
                        help='exact declared candidate SHA; default is the sealed v2 candidate')
    parser.add_argument('--patch', type=Path, default=DEFAULT_PATCH)
    parser.add_argument('--patch-sha', default=DEFAULT_PATCH_SHA,
                        help='exact whole-source patch SHA; default is the sealed v2 patch')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(all(re.fullmatch('[0-9a-f]{64}', value)
                for value in (args.candidate_sha, args.patch_sha)), 'exact candidate and patch SHA required')
    require(args.output.is_absolute() and args.output.is_relative_to(Path('/tmp'))
            and not args.output.is_symlink(), 'output must be an exclusive absolute /tmp file')
    require(args.patch.is_absolute(), 'patch path must be absolute')
    output = args.output.open('x', encoding='utf-8')
    started = time.monotonic_ns()
    result = {'schema':SCHEMA, 'passed':False, 'scope':'engineering_closed_data_candidate_regression_only',
        'scientific_pass_claimed':False, 'qualification_passed':False, 'native_admission':False,
        'native_runs':0, 'gpu_calls':0, 'original_v19_matrix_failure_retained':True,
        'artifact_freeze':FREEZE, 'artifact_freeze_is_candidate_freeze':False,
        'candidate_sha256':args.candidate_sha, 'patch_sha256':args.patch_sha,
        'started_monotonic_ns':started, 'commands':[], 'errors':[],
        'original_candidate_audit_invoked':False, 'original_candidate_audit_completed':False,
        'source_before':{}, 'inputs_before':{}}
    try:
        require(os.environ.get('PYTHONPATH') is None and os.environ.get('PYTHONNOUSERSITE') == '1'
                and os.environ.get('PYTHONDONTWRITEBYTECODE') == '1'
                and os.environ.get('CUDA_VISIBLE_DEVICES') == '', 'explicit CPU environment differs')
        raw_argv = Path('/proc/self/cmdline').read_bytes()
        require(raw_argv.endswith(b'\0'), 'actual argv is missing')
        result['actual_argv'] = [os.fsdecode(value) for value in raw_argv[:-1].split(b'\0')]
        proc = Path('/proc/self/stat').read_text().rsplit(')', 1)[1].split()
        result['identity'] = {'pid':os.getpid(), 'parent':int(proc[1]), 'start_ticks':int(proc[19])}
        candidate_raw, reader_before = bound_bytes(READER)
        patch_raw, patch_before = bound_bytes(args.patch)
        original_raw, original_before = bound_bytes(ORIGINAL_RESULT)
        require(reader_before['sha256'] == args.candidate_sha != FROZEN_READER_SHA,
                'current reader is not the explicitly declared different candidate')
        require(patch_before['sha256'] == args.patch_sha, 'declared whole-source patch differs')
        require(original_before['sha256'] == ORIGINAL_RESULT_SHA, 'original V19 runtime result differs')
        relative = READER.relative_to(ROOT).as_posix()
        frozen = command(['git', 'show', FREEZE+':'+relative], ROOT, result['commands'])
        require(sha(frozen) == FROZEN_READER_SHA, 'original frozen reader Git blob differs')
        result['whole_source_inverse'] = inverse_proof(candidate_raw, frozen, patch_raw, result['commands'])
        original_run = parse(original_raw)
        episodes = original_run['episodes']
        require(original_run['passed'] is True and original_run['errors'] == []
                and original_run['freeze'] == FREEZE and len(episodes) == 1
                and episodes[0]['directory'] == str(EPISODE) and episodes[0]['passed'] is True
                and episodes[0]['errors'] == [], 'original runtime leaf scope differs')
        expected = episodes[0]['result']
        require(expected['passed'] is True and expected['freeze'] == FREEZE
                and set(expected['artifact_proof']) == set(ARTIFACTS), 'original episode result differs')
        result['original_runtime_leaf_pass_retained'] = True
        source_paths = {str(Path(__file__).resolve()):fingerprint(Path(__file__).resolve()),
                        str(READER):reader_before, str(args.patch):patch_before,
                        str(ORIGINAL_RESULT):original_before}
        result['source_before'] = source_paths
        for name, proof in expected['source_proof'].items():
            path = ROOT/name
            require(path.is_relative_to(ROOT) and not path.is_symlink(), 'source path escapes workspace')
            source_paths[str(path)] = fingerprint(path)
            payload = command(['git', 'show', FREEZE+':'+name], ROOT, result['commands'])
            require(proof == {'git_source':FREEZE+':'+name, 'sha256':sha(payload)},
                    'original source proof differs from frozen Git: '+name)
            if name == relative:
                require(payload == frozen and source_paths[str(path)] == reader_before,
                        'candidate reader binding changed')
            else:
                require(payload == path.read_bytes(), 'other original source differs from freeze: '+name)
        require(relative in expected['source_proof'], 'original result has no runtime reader source')
        for name, proof in expected['artifact_proof'].items():
            path = Path(proof['path'])
            require(path in (EPISODE/name, Path(str(EPISODE/name)+'.gz')),
                    'original artifact path differs: '+name)
            result['inputs_before'][name] = fingerprint(path)
            require(result['inputs_before'][name]['sha256'] == proof['sha256'],
                    'closed artifact differs from original result: '+name)
        for name in ('audit_episode', 'Inputs'):
            require(definition(candidate_raw, name) == definition(frozen, name),
                    'original complete loader/configuration/close contract changed: '+name)
        audit_tree = ast.parse(definition(candidate_raw, 'audit_episode')).body[0]
        closes = [node for node in ast.walk(audit_tree) if isinstance(node, ast.Call)
                  and isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name)
                  and node.func.value.id == 'inputs' and node.func.attr == 'close']
        require(len(closes) == 1, 'original audit has no unique Inputs.close call')
        module = types.ModuleType('mr3_v20_diagnostic_candidate_runtime')
        module.__file__ = str(READER)
        exec(compile(candidate_raw, str(READER), 'exec'), vars(module))
        require(module.CONTRACT == 'mr3-reach-v1' and tuple(module.ROBOTS) == ROBOTS,
                'candidate contract differs')
        marker, result['source_projection'] = project_source_proof(
            module, candidate_raw, frozen, args.candidate_sha)
        identities = {name:id(value) for name,value in vars(module).items() if callable(value)}
        original_read, original_close = module.Inputs.read, module.Inputs.close
        result['original_candidate_audit_invoked'] = True
        returned = module.audit_episode(EPISODE, FREEZE)
        result['original_candidate_audit_completed'] = True
        result['candidate_episode_result'] = returned
        require(identities == {name:id(value) for name,value in vars(module).items() if callable(value)}
                and module.Inputs.read is original_read and module.Inputs.close is original_close,
                'candidate callable or Inputs methods were replaced during execution')
        expected_sources = dict(expected['source_proof'])
        expected_sources[relative] = dict(expected_sources[relative], **marker)
        require(canonical(returned['source_proof']) == canonical(expected_sources),
                'candidate marked/other-original source proofs differ')
        without_source = lambda value:{k:v for k,v in value.items() if k != 'source_proof'}
        require(canonical(without_source(returned)) == canonical(without_source(expected)),
                'complete core/artifact result differs from original V19 runtime leaf')
        require(canonical(returned['artifact_proof']) == canonical(expected['artifact_proof']),
                'original complete artifact proof differs')
        result.update(source_projection_result_exact=True, complete_core_and_artifact_result_exact=True,
                      original_inputs_close_mandatory_and_returned=True,
                      candidate_callable_identities_unchanged=True)
    except BaseException as error:
        result['errors'].append({'type':type(error).__name__, 'message':str(error),
                                 'traceback':traceback.format_exc()})
    finally:
        try:
            result['source_after'] = {name:fingerprint(Path(name))
                                      for name in result['source_before']}
            result['inputs_after'] = {name:fingerprint(Path(proof['path']))
                                      for name,proof in result['inputs_before'].items()}
            require(result['source_after'] == result['source_before'], 'diagnostic source/result/patch changed')
            require(result['inputs_after'] == result['inputs_before'], 'closed artifact changed during diagnostic')
            result.update(source_unchanged=True, inputs_unchanged=True)
        except BaseException as error:
            result['errors'].append({'type':type(error).__name__, 'message':str(error),
                                     'traceback':traceback.format_exc()})
        result['ended_monotonic_ns'] = time.monotonic_ns()
        result['actual_child_wall_seconds'] = str(Decimal(result['ended_monotonic_ns']-started)/10**9)
        result['passed'] = (not result['errors'] and result['original_candidate_audit_completed']
                            and result.get('complete_core_and_artifact_result_exact') is True
                            and result.get('source_projection_result_exact') is True
                            and result.get('source_unchanged') is True
                            and result.get('inputs_unchanged') is True)
        with output:
            json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)
            output.write('\n')
    print(json.dumps({key:result[key] for key in ('schema', 'passed', 'scientific_pass_claimed',
        'qualification_passed', 'native_admission', 'actual_child_wall_seconds', 'errors')}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
