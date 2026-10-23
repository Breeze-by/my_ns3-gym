"""Exact gentle-turn deployment readback using the immutable nine-node reader.

This entry changes declared deployment facts only. It never writes parameters,
changes the physical/safety/task gates, or claims the old reader's full identity.
"""
import argparse
import copy
import hashlib
import importlib.util
import inspect
import json
import math
from pathlib import Path
import re
import subprocess
import time

WORKSPACE = Path(__file__).resolve().parents[7]
WIRELESS = Path('ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl')
LEGACY_RELATIVE = WIRELESS / 'report/assets/20261017_mr3_p2a0_v13/independent/mr3_actual_nav2_parameters_v13.py'
LEGACY_SHA = '9eb963457a8dc8297e4686004ea08c7a06e1e0e9ede7cd795ba9505da9d8f701'
SELECTION = 'gentle_turn_v1'
PROFILE = 'mr3-nav2-shim-dwb-030-a1-v1'
CHANGES = (
    ('controller_server', 'FollowPath.rotate_to_heading_angular_vel', .8, .3),
    ('controller_server', 'FollowPath.max_angular_accel', 3.2, 1.0),
    ('controller_server', 'FollowPath.max_vel_theta', .8, .3),
    ('controller_server', 'FollowPath.acc_lim_theta', 3.2, 1.0),
    ('velocity_smoother', 'max_velocity', [.2, 0., .8], [.2, 0., .3]),
    ('velocity_smoother', 'min_velocity', [-.2, 0., -.8], [-.2, 0., -.3]),
    ('velocity_smoother', 'max_accel', [.5, 0., 3.2], [.5, 0., 1.0]),
    ('behavior_server', 'max_rotational_vel', .8, .3),
    ('behavior_server', 'min_rotational_vel', .4, .15),
    ('behavior_server', 'rotational_acc_lim', 3.2, 1.0),
)
YAML_BASE_SHA = (
    '8854aac6fe3083aa1156072830358e9331f0e0a45144ab3df499f743a37c1b8a',
    '9c7a0f9c197c5b3eedc3567c0b70d4920a5ca8cc6057b5059f5c5844ab275386',
    '8794b037c1ef31f57c8d99ab05c57a646afe6653717c2f21100e00b6a5435fae',
)
# Exact source-byte inverse. The three recoveries_server values are retained
# static configuration only; the original reader has no fourth live node kind.
YAML_INVERSE = (
    ('rotate_to_heading_angular_vel: 0.3', 'rotate_to_heading_angular_vel: 0.8', 1),
    ('max_angular_accel: 1.0', 'max_angular_accel: 3.2', 1),
    ('max_vel_theta: 0.3', 'max_vel_theta: 0.8', 1),
    ('acc_lim_theta: 1.0', 'acc_lim_theta: 3.2', 1),
    ('max_rotational_vel: 0.3', 'max_rotational_vel: 0.8', 2),
    ('min_rotational_vel: 0.15', 'min_rotational_vel: 0.4', 2),
    ('rotational_acc_lim: 1.0', 'rotational_acc_lim: 3.2', 2),
    ('max_velocity: [0.20, 0.0, 0.3]', 'max_velocity: [0.20, 0.0, 0.8]', 1),
    ('min_velocity: [-0.20, 0.0, -0.3]', 'min_velocity: [-0.20, 0.0, -0.8]', 1),
    ('max_accel: [0.5, 0.0, 1.0]', 'max_accel: [0.5, 0.0, 3.2]', 1),
)


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def yaml_bindings(root=WORKSPACE):
    result = []
    for robot, expected in enumerate(YAML_BASE_SHA, 1):
        relative = Path('ros2_ws/ros2-multi-robot-automap/src/multi_robot/params') / f'nav2_params_tb{robot}_0.yaml'
        raw = (root / relative).read_bytes()
        inverse = raw
        for new, old, count in YAML_INVERSE:
            require(inverse.count(new.encode()) == count, 'exact gentle-turn YAML fact differs: ' + new)
            inverse = inverse.replace(new.encode(), old.encode())
        require(sha(inverse) == expected, 'gentle-turn YAML changes exceed the exact13 declared facts')
        result.append({'path': str(relative), 'sha256': sha(raw), 'bytes': len(raw),
                       'inverse_original_sha256': expected, 'exact_inverse': True,
                       'changed_lines': 13})
    return result


def load_profile(root=WORKSPACE):
    path = root / LEGACY_RELATIVE
    raw = path.read_bytes()
    require(sha(raw) == LEGACY_SHA, 'immutable nine-node parameter reader differs')
    spec = importlib.util.spec_from_file_location('mr3_gentle_private_parameter_reader', path)
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    require(legacy.PROFILE == 'mr3-nav2-shim-dwb-020-v1', 'original deployment profile differs')
    expected = copy.deepcopy(legacy.EXPECTED)
    facts = []
    for node, name, before, after in CHANGES:
        kind, value = expected[node][name]
        require(value == before, 'original exact deployment fact differs: ' + name)
        expected[node][name] = (kind, copy.deepcopy(after))
        facts.append({'node_kind': node, 'name': name, 'type': kind,
                      'old': before, 'new': after})
    definition = {'schema': 'mr3-nav2-exact-deployment-profile-v1', 'selection': SELECTION,
                  'profile': PROFILE, 'immutable_reader_sha256': LEGACY_SHA,
                  'changed_typed_facts': facts, 'expected_typed_parameters': expected}
    # Fresh private module data only; decode/status/service/collect functions are
    # the unchanged original functions with the same exact typed predicates.
    legacy.EXPECTED = expected
    legacy.PROFILE = PROFILE
    provenance = {'schema': 'mr3-nav2-parameter-implementation-v1',
        'effective_entry': {'path': str(Path(__file__).resolve()),
                            'sha256': sha(Path(__file__).read_bytes())},
        'immutable_reader': {'path': str(LEGACY_RELATIVE), 'sha256': LEGACY_SHA},
        'profile_definition': definition, 'profile_sha256': sha(canonical(definition)),
        'yaml_sources': yaml_bindings(root),
        'unchanged_function_sha256': {name: sha(inspect.getsource(getattr(legacy, name)).encode())
            for name in ('decode_parameters', 'validate_parameters', 'validate_status', 'collect')},
        'scope': 'Exact deployment profile only; original nine services, typed equality, release-status source, finite readback and cleanup logic unchanged. recoveries_server three source facts are static configuration, not a new live readback. Old reader bytes remain unchanged and do not identify this effective entry. No physical/safety/task bound changed or plant repair guaranteed.'}
    return legacy, provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('episode_directory', type=Path)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--wall-timeout-sec', type=float, default=30.)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('output exists')
    if not (math.isfinite(args.wall_timeout_sec) and 0 < args.wall_timeout_sec <= 60):
        parser.error('wall timeout must be finite and at most 60 seconds')
    result = {'schema': 'mr3-actual-nav2-parameter-readback-v3', 'profile': PROFILE,
              'passed': False, 'freeze': args.freeze, 'episode_directory': str(args.episode_directory),
              'script_sha256': sha(Path(__file__).read_bytes()), 'nodes': [], 'errors': [],
              'scope': 'Read-only actual GetParameters from the original nine namespaced nodes at the exact paused reset release; no parameter writes, control publications, stepping, physical/safety/task bound change or repair credit.'}
    started = time.monotonic()
    try:
        require(re.fullmatch(r'[0-9a-f]{40}', args.freeze), 'exact source freeze required')
        legacy, proof = load_profile()
        result.update(implementation_provenance=proof, expected_typed_parameters=legacy.EXPECTED)
        sources = [Path(__file__).resolve().relative_to(WORKSPACE), LEGACY_RELATIVE,
                   *(Path(row['path']) for row in proof['yaml_sources'])]
        for relative in sources:
            frozen = subprocess.check_output(['git', 'show', args.freeze + ':' + str(relative)], cwd=WORKSPACE)
            require(frozen == (WORKSPACE / relative).read_bytes(), 'parameter entry/profile source differs from freeze: ' + str(relative))
        metadata = json.loads((args.episode_directory / 'metadata.json').read_bytes())
        require(metadata['freeze'] == args.freeze, 'episode metadata freeze mismatch')
        transition_path = args.episode_directory / 'transitions.jsonl'
        reset = json.loads(transition_path.read_text().splitlines()[0])
        require(reset['kind'] == 'reset' and reset['snapshot']['epoch'] == metadata['epoch'],
                'original returned reset binding missing')
        release = reset['info']['release_time_ns']
        require(type(release) is int and release > 0, 'invalid reset release source clock')
        result.update(epoch=metadata['epoch'], source_clock_ns=release,
            metadata_sha256=sha((args.episode_directory / 'metadata.json').read_bytes()),
            reset_transition_sha256=sha(transition_path.read_bytes()))
        legacy.collect(metadata['epoch'], release, args.wall_timeout_sec, result)
        require(sha(Path(__file__).read_bytes()) == result['script_sha256']
                and sha((WORKSPACE / LEGACY_RELATIVE).read_bytes()) == LEGACY_SHA
                and yaml_bindings() == proof['yaml_sources'], 'parameter implementation/profile source changed during readback')
        result['passed'] = True
    except Exception as error:
        result['errors'].append(repr(error))
    result['wall_duration_sec'] = time.monotonic() - started
    with args.output.open('x') as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write('\n')
    print(json.dumps({'passed': result['passed'], 'nodes': len(result['nodes']),
                      'errors': result['errors'], 'output': str(args.output)}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
