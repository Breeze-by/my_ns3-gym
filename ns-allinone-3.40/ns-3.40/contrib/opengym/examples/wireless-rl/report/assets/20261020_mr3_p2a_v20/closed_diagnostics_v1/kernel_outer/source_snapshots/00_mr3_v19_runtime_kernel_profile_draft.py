#!/usr/bin/python3
"""Future closed-artifact CPU kernel diagnosis; never scientific qualification.

This file has not been run as part of its preparation. It intentionally does
not call audit_episode, _audit_records, native_index, or ingress_index. A
selected recorded decision is input to small original pure functions only;
the complete episode's causal/physical validity is not re-established here.
"""
import argparse
import cProfile
from fractions import Fraction
import hashlib
import importlib.util
import io
import json
import marshal
import os
from pathlib import Path
import pstats
import re
import stat
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROBOTS = ('tb1', 'tb2', 'tb3')
CONTRACT = 'mr3-reach-v1'
BLOCK = 1024 * 1024


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def digest(value):
    return sha(canonical(value).encode('utf-8'))


def parse(raw):
    def unique(items):
        value = {}
        for key, item in items:
            require(key not in value, 'duplicate JSON member: ' + key)
            value[key] = item
        return value
    value = json.loads(raw, object_pairs_hook=unique,
                       parse_constant=lambda value: (_ for _ in ()).throw(
                           ValueError('nonfinite JSON: ' + value)))
    canonical(value)
    return value


def true_argv():
    raw = Path('/proc/self/cmdline').read_bytes()
    require(raw.endswith(b'\0') and raw[:-1], 'argv must be nonempty and NUL terminated')
    values = raw[:-1].split(b'\0')
    require(all(values), 'argv contains an empty argument')
    return [os.fsdecode(value) for value in values]


def identity(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns,
            value.st_ctime_ns, stat.S_IMODE(value.st_mode)]


def open_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        require(stat.S_ISREG(os.fstat(fd).st_mode), 'not a regular input: ' + str(path))
    except BaseException:
        os.close(fd)
        raise
    return os.fdopen(fd, 'rb')


def fingerprint(path, *, keep_bytes=False):
    with open_regular(path) as stream:
        before = identity(os.fstat(stream.fileno()))
        hasher, size, kept = hashlib.sha256(), 0, []
        for block in iter(lambda: stream.read(BLOCK), b''):
            hasher.update(block)
            size += len(block)
            if keep_bytes:
                kept.append(block)
        require(identity(os.fstat(stream.fileno())) == before == identity(path.lstat()),
                'input identity/stat changed while hashing: ' + str(path))
    require(size == before[2], 'input size changed: ' + str(path))
    proof = {'path': str(path), 'bytes': size, 'sha256': hasher.hexdigest(), 'stat': before}
    return (proof, b''.join(kept)) if keep_bytes else proof


def write_json(path, value):
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


def command(argv, cwd):
    started = time.monotonic_ns()
    completed = subprocess.run(argv, cwd=cwd, capture_output=True, check=False)
    proof = {'actual_argv': argv, 'cwd': str(cwd), 'actual_waited': True,
             'returncode': completed.returncode, 'started_monotonic_ns': started,
             'ended_monotonic_ns': time.monotonic_ns(),
             'stdout_sha256': sha(completed.stdout),
             'stderr': completed.stderr.decode('utf-8', errors='replace')}
    require(completed.returncode == 0, 'source Git command failed: ' + repr(proof))
    return completed.stdout, proof


def load_frozen_reader(path, freeze, source_before):
    root_raw, root_command = command(['git', '-C', str(path.parent),
                                      'rev-parse', '--show-toplevel'], path.parent)
    root = Path(os.fsdecode(root_raw).strip())
    require(root.is_absolute(), 'Git root is not absolute')
    relative = path.relative_to(root).as_posix()
    frozen, frozen_command = command(['git', 'show', freeze + ':' + relative], root)
    require(sha(frozen) == source_before['sha256'] and len(frozen) == source_before['bytes'],
            'reader source is not its exact episode-freeze Git bytes')
    spec = importlib.util.spec_from_file_location('mr3_closed_runtime_kernel_reader', path)
    require(spec is not None and spec.loader is not None, 'reader loader unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.CONTRACT == CONTRACT and tuple(module.ROBOTS) == ROBOTS,
            'specified reader contract/robot identities differ')
    for name in ('state_geometry', 'independent_pair', 'admitted_command',
                 'residual_squared_upper', 'trig_bounds'):
        require(callable(getattr(module, name, None)), 'original pure kernel missing: ' + name)
    return module, {'freeze': freeze, 'git_source': freeze + ':' + relative,
                    'reader_sha256': sha(frozen), 'git_commands': [root_command, frozen_command]}


def selected_context(path, epoch):
    """Hash all original bytes, but parse only the prefix through first match.

    received_states is one real central delivery of a three-robot bundle. It
    supplies each named logical guard's table, not three network ACKs.
    """
    selected, latest_ingress, delivered = None, None, {}
    parsed_sequence = 0
    with open_regular(path) as stream:
        before = identity(os.fstat(stream.fileno()))
        hasher, total = hashlib.sha256(), 0
        for line_number, raw in enumerate(stream, 1):
            hasher.update(raw)
            total += len(raw)
            if selected is not None or not raw.strip():
                continue
            row = parse(raw)
            parsed_sequence += 1
            require(row.get('schema') == 'mr3-motion-safety-v1' and row.get('epoch') == epoch
                    and row.get('record_sequence') == parsed_sequence,
                    'motion prefix schema/epoch/record sequence differs')
            kind, payload = row['kind'], row['payload']
            ref = {'path': str(path), 'line_number': line_number,
                   'record_sequence': row['record_sequence'], 'line_bytes': len(raw),
                   'line_sha256': sha(raw), 'wall_monotonic_ns': row['wall_monotonic_ns']}
            if kind == 'reach_state_ingress':
                require(canonical(parse(payload['raw_json'])) == canonical(payload['message']),
                        'actual received ingress lost its complete original wire payload')
                latest_ingress = {'reference': ref, 'row': row}
            elif kind == 'received_states':
                require(latest_ingress is not None and canonical(payload) == canonical(
                    latest_ingress['row']['payload']['message']),
                    'received bundle lacks its preceding identical actual ingress')
                require(payload.get('epoch') == epoch and payload.get('safety_contract') == CONTRACT,
                        'received bundle contract/epoch differs')
                states = payload['robots']
                require(type(states) is list and len(states) == 3
                        and {state['name'] for state in states} == set(ROBOTS),
                        'received bundle is not the complete three-robot table')
                actual = {'reference': ref, 'row': row, 'actual_ingress': latest_ingress}
                delivered = {state['name']: actual for state in states}
            elif kind == 'reach_decision':
                if payload.get('started') is not True or payload.get('decision', {}).get('allow') is not True:
                    continue
                own = payload.get('own_state')
                require(type(own) is dict and type(own.get('safety', {}).get('intent')) is dict,
                        'started allowed decision has no complete own intent')
                if own['safety']['intent'].get('role') not in ('X', 'N'):
                    continue
                # Do not skip an incomplete first match in favour of an easier one.
                name = payload['robot']
                require(name in ROBOTS and own['name'] == name and payload.get('ready') is True,
                        'first allowed X/N candidate lacks its own ready identity')
                require(payload.get('phase_kind', 'normal') == 'normal', 'candidate is not a normal phase')
                require(name in delivered, 'first candidate has no earlier real received bundle')
                prior = delivered[name]
                require(prior['reference']['record_sequence'] < row['record_sequence']
                        and prior['reference']['wall_monotonic_ns'] <= row['wall_monotonic_ns'],
                        'bundle was not actually received before candidate')
                bundle = prior['row']['payload']
                table = {state['name']: state for state in bundle['robots']}
                safety_sha = digest({name: table[name]['safety'] for name in ROBOTS})
                require(payload['safety_table_sha256'] == bundle['safety_table_sha256'] == safety_sha,
                        'first candidate did not consume that complete frozen safety table')
                peers = payload['received_peers']
                require(set(peers) == set(ROBOTS) - {name} and all(
                    canonical(peers[peer]) == canonical(table[peer]) for peer in peers),
                    'candidate peers differ from its actual received bundle')
                require(type(payload['clock_ns']) is int and own['epoch'] == epoch,
                        'candidate clock/own epoch differs')
                selected = {'selection': 'first started allowed normal decision whose consumed own intent is X or N',
                            'decision_reference': ref, 'decision_row': row,
                            'received_bundle': prior, 'robot': name, 'clock_ns': payload['clock_ns']}
        require(identity(os.fstat(stream.fileno())) == before == identity(path.lstat()),
                'motion source changed during selection/hash')
    require(total == before[2], 'motion source size changed during selection')
    return selected, {'path': str(path), 'bytes': total, 'sha256': hasher.hexdigest(), 'stat': before}


def serializable(value):
    """Preserve exact Q numerator/denominator and Python repr; never cast Q to float."""
    if isinstance(value, Fraction):
        return {'python_type': 'fractions.Fraction', 'repr': repr(value),
                'numerator': str(value.numerator), 'denominator': str(value.denominator)}
    if type(value) is tuple:
        return {'python_type': 'tuple', 'items': [serializable(v) for v in value]}
    if type(value) is list:
        return [serializable(v) for v in value]
    if type(value) is dict:
        require(all(type(key) is str for key in value), 'kernel output has a non-string mapping key')
        return {key: serializable(item) for key, item in value.items()}
    require(value is None or type(value) in (bool, int, float, str),
            'unsupported original kernel output: ' + type(value).__name__)
    return value


def profile_segment(output, module, name, function, count):
    before_cache = module.trig_bounds.cache_info()._asdict()
    profiler = cProfile.Profile()
    expected, first_repr = None, None
    started = time.monotonic_ns()
    for index in range(count):
        actual = profiler.runcall(function)
        encoded = serializable(actual)
        if index == 0:
            expected, first_repr = encoded, repr(actual)
        else:
            require(canonical(encoded) == canonical(expected), 'same original kernel changed output across repeats')
    ended = time.monotonic_ns()
    # Same standard cProfile marshal representation, but exclusive creation.
    profiler.create_stats()
    profile_path = output / (name + '.prof')
    with profile_path.open('xb') as stream:
        marshal.dump(profiler.stats, stream)
    texts = {}
    for order in ('cumulative', 'tottime'):
        text = io.StringIO()
        pstats.Stats(profiler, stream=text).strip_dirs().sort_stats(order).print_stats(30)
        path = output / (name + '.' + order + '.txt')
        with path.open('x', encoding='utf-8') as stream:
            stream.write(text.getvalue())
        texts[order] = fingerprint(path)
    return {'id': name, 'call_count': count, 'started_monotonic_ns': started,
            'ended_monotonic_ns': ended, 'wall_seconds': (ended-started)/1e9,
            'output': expected, 'original_output_repr': first_repr,
            'all_repeated_outputs_equal': True, 'trig_cache_before': before_cache,
            'trig_cache_after': module.trig_bounds.cache_info()._asdict(),
            'profile': fingerprint(profile_path), 'top30': texts}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode', required=True, type=Path)
    parser.add_argument('--reader-source', required=True, type=Path)
    parser.add_argument('--output-dir', required=True, type=Path)
    args = parser.parse_args(argv)
    require(all(path.is_absolute() for path in (args.episode, args.reader_source, args.output_dir)),
            'all CLI paths must be absolute')
    episode, reader, output = (Path(os.path.abspath(path)) for path in
                               (args.episode, args.reader_source, args.output_dir))
    require(not output.exists() and not output.is_symlink(), 'exclusive output directory already exists')
    require(output != episode and not output.is_relative_to(episode)
            and not episode.is_relative_to(output), 'output and original episode must not overlap')
    started = time.monotonic_ns()
    output.mkdir(mode=0o755)
    result = {'schema': 'mr3-closed-runtime-pure-kernel-profile-v1', 'scope': 'cpu_performance_diagnostic_only',
              'diagnostic_completed': False, 'scientific_pass_claimed': False, 'native_admission': False,
              'complete_episode_replayed': False, 'actual_argv': true_argv(),
              'started_monotonic_ns': started, 'errors': [], 'profiles': [],
              'warning': 'Recorded inputs are profiled; full causal/source/plant qualification is not reproduced.'}
    sources = {}
    result['sources_before'] = sources
    try:
        reader_before = fingerprint(reader)
        metadata_path, motion_path = episode / 'metadata.json', episode / 'motion_safety.jsonl'
        metadata_before, metadata_raw = fingerprint(metadata_path, keep_bytes=True)
        sources.update({str(reader): reader_before, str(metadata_path): metadata_before})
        metadata = parse(metadata_raw)
        freeze, epoch = metadata['freeze'], metadata['epoch']
        require(type(freeze) is str and re.fullmatch('[0-9a-f]{40}', freeze) is not None
                and type(epoch) is str and epoch and metadata.get('safety_contract') == CONTRACT,
                'episode lacks exact freeze/epoch/reach identity')
        module, frozen_proof = load_frozen_reader(reader, freeze, reader_before)
        context, motion_before = selected_context(motion_path, epoch)
        sources[str(motion_path)] = motion_before
        result.update(freeze=freeze, epoch=epoch, reader_source_proof=frozen_proof)
        require(context is not None, 'no complete actual allowed X/N decision was found')
        context_sha = digest(context)
        context_path = output / 'selected_original_context.json'
        write_json(context_path, context)
        result.update(context_sha256=context_sha, context_artifact=fingerprint(context_path),
                      selected_decision=context['decision_reference'],
                      selected_bundle=context['received_bundle']['reference'])
        decision = context['decision_row']['payload']
        own, peers, clock = decision['own_state'], decision['received_peers'], decision['clock_ns']
        table = {state['name']: state for state in context['received_bundle']['row']['payload']['robots']}
        raw, calibration = own['odometry'], own['safety']['calibration']
        signs = tuple(own['safety']['intent']['admitted_signs'])
        kernels = (
            ('state_geometry', lambda: module.state_geometry(own, clock, epoch)),
            ('pair_geometry_original_all', lambda: all(module.independent_pair(own, peer, clock, epoch)
                                                      for peer in peers.values())),
            ('admitted_command', lambda: module.admitted_command(decision, own, table[context['robot']],
                                                                 peers, clock, epoch)),
            ('residual_full_rest', lambda: module.residual_squared_upper(raw, calibration, ())),
            ('residual_actual_signed_family', lambda: module.residual_squared_upper(raw, calibration, signs)),
        )
        for name, function in kernels:
            module.trig_bounds.cache_clear()
            cold_output = None
            for suffix, count in (('cold1', 1), ('warm25', 25)):
                segment = profile_segment(output, module, name + '.' + suffix, function, count)
                result['profiles'].append(segment)
                if suffix == 'cold1':
                    cold_output = segment['output']
                else:
                    require(canonical(segment['output']) == canonical(cold_output),
                            'cold and warm original kernel outputs differ')
                require(digest(context) == context_sha, 'original pure kernel mutated recorded input context')
        after = {path: fingerprint(Path(path)) for path in sources}
        result['sources_after'] = after
        require(after == sources, 'reader/metadata/motion original input bytes/stat changed')
        result.update(diagnostic_completed=True, source_unchanged=True, original_context_unchanged=True)
    except BaseException as error:
        result['errors'].append({'type': type(error).__name__, 'message': str(error)})
        result['partial_outputs_preserved'] = True
    result['ended_monotonic_ns'] = time.monotonic_ns()
    result['wall_seconds'] = (result['ended_monotonic_ns']-started)/1e9
    write_json(output / 'result.json', result)
    print(canonical({'diagnostic_completed': result['diagnostic_completed'],
                     'scientific_pass_claimed': False, 'result': str(output / 'result.json'),
                     'errors': result['errors']}))
    return 0 if result['diagnostic_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
