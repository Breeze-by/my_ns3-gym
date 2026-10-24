"""Invoke immutable drive-v5 in full, then enforce the new .20 final-command cap."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

LEGACY = Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/'
              'examples/wireless-rl/report/assets/20261017_mr3_p2a0_v10/independent/'
              'mr3_independent_drive_trace_v5.py')
LEGACY_SHA = '1010c0192233c2c649924bda2709479c991b18b34a753bda265779cf5bbf57a5'
if hashlib.sha256(LEGACY.read_bytes()).hexdigest() != LEGACY_SHA:
    raise ValueError('immutable drive-v5 SHA mismatch')
SPEC = importlib.util.spec_from_file_location('immutable_drive_v5_for_v6', LEGACY)
OLD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(OLD)
BASE = OLD.BASE
require, number = BASE.require, BASE.number
ROBOTS = BASE.ROBOTS
LINEAR_CAP = .20
ANGULAR_CAP = .8


def final_command(v, w, where):
    require(number(v) and number(w), 'nonfinite or nonnumeric final command: ' + where)
    require(abs(v) <= LINEAR_CAP and abs(w) <= ANGULAR_CAP,
            'final command exceeds .20/.8: ' + where)


def audit_cap_episode(directory, freeze, inputs):
    metadata = inputs.json(directory / 'metadata.json')
    require(metadata['freeze'] == freeze, 'cap review episode freeze mismatch')
    epoch = metadata['epoch']
    counts = {kind: dict.fromkeys(ROBOTS, 0) for kind in
              ('guard_outputs', 'target_publications', 'native_received', 'native_actuations')}
    maxima = dict.fromkeys(ROBOTS, 0.)

    def check(kind, name, v, w, where):
        require(name in ROBOTS, 'cap review unknown robot')
        final_command(v, w, where)
        counts[kind][name] += 1
        maxima[name] = max(maxima[name], abs(v))

    for line, row in enumerate(inputs.lines(directory / 'motion_safety.jsonl'), 1):
        if row['kind'] != 'decision':
            continue
        value = row['payload']
        require(row['epoch'] == epoch, 'cap guard epoch mismatch')
        v, w = BASE.pair(value['decision']['output'], 'cap guard output pair')
        check('guard_outputs', value['robot'], v, w, 'guard line ' + str(line))
    for line, row in enumerate(inputs.lines(directory / 'drive_targets.jsonl'), 1):
        require(row['epoch'] == epoch, 'cap target ledger epoch mismatch')
        target = json.loads(row['target_json'])
        require(target['schema'] == 'mr3-drive-target-v1' and target['epoch'] == epoch,
                'cap target payload identity')
        check('target_publications', target['robot'], target['linear_x'], target['angular_z'],
              'target publication line ' + str(line))
    for name in ROBOTS:
        for line, row in enumerate(inputs.lines(directory / ('drive_' + name + '.jsonl')), 1):
            if row['kind'] not in ('command_received', 'actuation'):
                continue
            require(row['epoch'] == epoch, 'cap native command epoch mismatch')
            kind = 'native_received' if row['kind'] == 'command_received' else 'native_actuations'
            check(kind, name, row['desired_v'], row['desired_w'],
                  name + ' ' + row['kind'] + ' line ' + str(line))
    require(all(count > 0 for roles in counts.values() for count in roles.values()),
            'cap review missing actual guard/publication/native command or actuation role')
    return {'directory': str(directory), 'epoch': epoch, 'passed': True,
            'record_counts': counts, 'max_abs_final_linear_by_robot': maxima}


def review(directory, freeze, proof_path, archived=False):
    # This calls the actual complete immutable reader, including its v4 math/phase/source
    # chain. Nothing is patched, replaced, skipped or converted from FAIL to PASS.
    try:
        original = OLD.review(directory, freeze, proof_path, archived)
    except Exception as error:
        original = {'schema': 'mr3-independent-drive-trace-review-v5', 'passed': False,
                    'freeze': freeze, 'error': repr(error), 'world_body_response_credit': False}
    inputs = BASE.Inputs()
    directory = Path(directory)
    episodes = ([directory] if (directory / 'metadata.json').exists() or
                (directory / 'metadata.json.gz').exists() else sorted(directory.glob('worker*/episode*')))
    additions = []
    for episode in episodes:
        try:
            additions.append(audit_cap_episode(episode, freeze, inputs))
        except Exception as error:
            additions.append({'directory': str(episode), 'passed': False, 'error': repr(error)})
    cap_error = None
    try:
        require(bool(episodes), 'cap review has no episode directories')
        for path, binding in inputs.bindings.items():
            if path in original.get('inputs', {}):
                require(binding == original['inputs'][path], 'cap/base input bytes differ: ' + path)
        inputs.verify_unchanged()
        require(hashlib.sha256(LEGACY.read_bytes()).hexdigest() == LEGACY_SHA,
                'immutable drive-v5 changed during review')
    except Exception as error:
        cap_error = repr(error)
    additional_passed = bool(additions) and all(row['passed'] for row in additions) and cap_error is None
    return {'schema': 'mr3-independent-drive-trace-review-v6', 'freeze': freeze,
            'passed': original.get('passed') is True and additional_passed,
            'immutable_v5_result': original,
            'immutable_v5_binding': {'path': str(LEGACY), 'sha256': LEGACY_SHA,
                'scope': 'Actual complete original review call; all raw/math/source/stop gates remain necessary'},
            'final_command_cap': {'passed': additional_passed, 'linear_mps': LINEAR_CAP,
                'angular_radps': ANGULAR_CAP, 'episodes': additions, 'inputs': inputs.bindings,
                'error': cap_error,
                'scope': 'All original final guard output, target publication, native received target and actuation desired target records, including prewarm/cleanup; no raw request normalization or epsilon. Original raw bytes unchanged.'},
            'world_body_response_credit': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--binary-proof', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--archived', action='store_true')
    args = parser.parse_args()
    require(not args.output.exists(), 'previous result cannot be overwritten')
    try:
        result = review(args.directory, args.freeze, args.binary_proof, args.archived)
    except Exception as error:
        result = {'schema': 'mr3-independent-drive-trace-review-v6', 'freeze': args.freeze,
                  'passed': False, 'error': repr(error), 'world_body_response_credit': False}
    result['script_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    with args.output.open('x') as stream:
        stream.write(json.dumps(result, indent=2, allow_nan=False) + '\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
