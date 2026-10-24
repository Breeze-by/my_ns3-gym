"""Independent saved-wrapper/base equality and per-episode loaded Shim custody."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

REPO = Path('/home/zhuyulab/ns3-workspace')
ROS = REPO / 'ros2_ws/ros2-multi-robot-automap'
BASE = (REPO / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/'
        '20261017_mr3_p2a0_v10/independent/mr3_readonly_v10_drive_process_monitor.py')
BASE_SHA = '7126969f615d768c5b8fe18039ffd5e0f9d090941e7a857e75b2c44436fb3d13'
MONITOR = Path(__file__).with_name('mr3_readonly_v13_drive_shim_process_monitor_v2.py')
BINDING = Path(__file__).with_name('mr3_v13_shim_binding_v1.json')
BINARY = Path('/tmp/mr3_p2a0_v13_binaryproof.json')
LIBRARY = Path('/opt/ros/humble/lib/libnav2_rotation_shim_controller.so')
ROLES = ('tb1', 'tb2', 'tb3')
EXPECTED = {
    'library': 'ec301e3ef10e7e71dfdfc77d0164dfecfba2408ea0523bb05ebf1983da13fc15',
    'header': '6bbd9ebf8eda7bbb9d32be60d7640d2e22e06801d30d87364dd3242b7a44ad01',
    'plugin_xml': 'efd520f83ddcbe8848ac4fe0d38571ce29e09a9d83cd265e609091aa36d31d2b',
    'package_xml': 'f4c57958fec392f9395082d291d2c5431c39d158ddf4618ef490530eef9ae510',
    'tag_source': 'e06b6c6a64853334b20398f750c517018c17a2017bec864c626726fcea261288',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def identity(value):
    fields = ('pid', 'parent', 'group', 'session', 'start_ticks')
    require(isinstance(value, dict) and all(type(value.get(k)) is int for k in fields)
            and value['pid'] > 0 and value['start_ticks'] > 0, 'invalid captured PID/start identity')
    return tuple(value[k] for k in fields)


def binding_inputs(read):
    raw = read(BINDING)
    document = json.loads(raw)
    require(document.get('schema') == 'mr3-shim-installed-and-tag-binding-v1'
            and document.get('upstream_tag') == '1.1.20'
            and set(document.get('files', {})) == set(EXPECTED), 'Shim binding roles/schema/tag differ')
    expected = {}
    for role, expected_sha in EXPECTED.items():
        item = document['files'][role]
        path = Path(item['path'])
        if not path.is_absolute():
            path = BINDING.parent / path
        payload = read(path)
        require(item['sha256'] == digest(payload) == expected_sha, 'Shim source/artifact SHA differs')
        expected[role] = {'path': str(path), 'resolved': str(path.resolve()),
                          'sha256': expected_sha, 'bytes': len(payload)}
    require(expected['library']['resolved'] == str(LIBRARY.resolve()), 'unexpected actual Shim path')
    return {'path': str(BINDING), 'sha256': digest(raw), 'files': expected}


def review_wrapper(path, run, prefix, freeze, read, expected_binding):
    document = json.loads(read(path))
    supplement = document.get('shim_mapping')
    require(isinstance(supplement, dict)
            and supplement.get('schema') == 'mr3-v13-shim-mapping-supplement-v2',
            'monitor lacks the frozen Shim supplement')
    support = path.parent / (path.stem + '_support')
    raw_base = read(support / 'drive_base.json')
    base = json.loads(raw_base)
    original_fields = {key: value for key, value in document.items() if key != 'shim_mapping'}
    require(canonical(original_fields) == canonical(base),
            'wrapper changed original drive monitor JSON fields')
    origin = supplement['base_monitor']
    argv = origin['actual_argv']
    require(type(origin['returncode']) is int and origin['returncode'] == 0
            and origin['output_sha256'] == digest(raw_base)
            and origin['source'] == str(BASE) and origin['sha256'] == digest(read(BASE)) == BASE_SHA,
            'original drive monitor source/result binding differs')
    require(isinstance(argv, list) and len(argv) == 9
            and Path(argv[0]).resolve() == Path('/usr/bin/python3').resolve()
            and argv[1:] == [str(BASE), str(run), '--launch', str(prefix) + '_launch.json',
                             '--binary-proof', str(BINARY), '--output', str(support / 'drive_base.json')],
            'original drive monitor actual CLI differs')
    require(origin['stdout_sha256'] == digest(read(support / 'base.stdout'))
            and origin['stderr_sha256'] == digest(read(support / 'base.stderr')),
            'original drive monitor console binding differs')
    require(supplement['producer_source'] == str(MONITOR.resolve())
            and supplement['producer_source_sha256'] == digest(read(MONITOR)),
            'wrapper producer source differs')
    require(base.get('freeze') == freeze and base.get('run') == str(run),
            'monitor run/freeze differs')
    actual_binding = supplement['binding']
    require(all(canonical(actual_binding[key]) == canonical(expected_binding[key])
                for key in ('path', 'sha256', 'files')), 'captured Shim binding differs')
    return document


def episode_proof(row, base, directory, metadata, supervisor):
    require(row.get('complete') is True and row.get('active_worker') is True
            and row.get('errors') == [], 'capture is incomplete or rejected')
    require(row['directory'] == str(directory) and row['epoch'] == metadata['epoch'],
            'capture episode/epoch differs')
    worker = supervisor['worker_identity']
    require(canonical(row['worker_identity']) == canonical(worker), 'capture saved worker differs')
    worker_key = identity(worker)
    inventory = {entry['identity']['pid']: entry for entry in base['owned_current_processes']}
    require(worker['pid'] in inventory
            and identity(inventory[worker['pid']]['identity']) == worker_key,
            'worker lacks original benchmark-owned process capture')
    argv = row['worker_actual_argv']
    require(argv == ['/usr/bin/python3', str(ROS / 'scripts/mr3_env_worker.py'),
                     '--run-dir', str(directory)]
            and argv == inventory[worker['pid']]['argv']
            and row['worker_cmdline_sha256'] == digest(('\0'.join(argv) + '\0').encode()),
            'actual worker argv is not this episode')
    command = supervisor['command']
    require(len(command) == 8 and command[:4] == [
        '/usr/bin/bash', '--noprofile', '--norc', '-c']
        and command[5:] == ['mr3-worker', str(ROS), str(directory)],
        'saved supervisor command is not this episode')
    require(set(row['controllers']) == set(ROLES), 'three controller roles are incomplete')
    controller_pids = set()
    for robot in ROLES:
        controller = row['controllers'][robot]
        require(controller.get('valid') is True and controller.get('errors') == []
                and controller.get('robot') == robot, 'invalid actual controller proof')
        captured = controller['identity']
        key = identity(captured)
        require(captured['pid'] not in controller_pids and captured['pid'] in inventory
                and identity(inventory[captured['pid']]['identity']) == key,
                'controller identity missing, duplicated or changed')
        controller_pids.add(captured['pid'])
        argv = controller['argv']
        require(argv and Path(argv[0]).name == 'controller_server'
                and argv == inventory[captured['pid']]['argv']
                and controller['cmdline_sha256'] == digest(('\0'.join(argv) + '\0').encode()),
                'actual controller argv differs')
        remaps = [(i, value) for i, value in enumerate(argv) if value.startswith('__ns:=')]
        require(len(remaps) == 1 and remaps[0][0] > 0
                and argv[remaps[0][0] - 1] in ('-r', '--remap')
                and remaps[0][1] == '__ns:=/' + robot, 'actual controller namespace differs')
        chain = controller['ancestor_chain']
        require(chain and identity(chain[0]) == key and identity(chain[-1]) == worker_key,
                'controller ancestry endpoints differ')
        require(len({item['pid'] for item in chain}) == len(chain), 'ancestry cycle')
        for i, item in enumerate(chain):
            require(item['pid'] in inventory
                    and identity(item) == identity(inventory[item['pid']]['identity']),
                    'ancestry identity differs from original process capture')
            if i + 1 < len(chain):
                require(item['parent'] == chain[i + 1]['pid'], 'ancestry parent link differs')
        lines, mappings = controller['shim_maps_lines'], controller['mappings']
        require(isinstance(lines, list) and lines and isinstance(mappings, list)
                and len(lines) == len(mappings)
                and re.fullmatch('[0-9a-f]{64}', controller['maps_sha256']) is not None,
                'missing actual Shim mapping records')
        for line, mapping in zip(lines, mappings):
            fields = line.split(maxsplit=5)
            require(len(fields) == 6 and fields[5] == str(LIBRARY)
                    and mapping['raw_maps_line'] == line
                    and mapping['resolved'] == str(LIBRARY.resolve())
                    and type(mapping['inode']) is int and mapping['inode'] == int(fields[4])
                    and mapping['device'] == fields[3] and mapping['sha256'] == EXPECTED['library'],
                    'actual Shim path/inode/device/SHA mapping differs')
    return {'controller_identities': {robot: row['controllers'][robot]['identity'] for robot in ROLES},
            'worker_identity': worker, 'epoch': metadata['epoch']}


def review(run, prefix, freeze, read):
    errors, episodes, wrappers = [], [], []
    expected_binding = binding_inputs(read)
    for path in sorted(prefix.parent.glob(prefix.name + '_process_monitor_*.json')):
        try:
            wrappers.append((path, review_wrapper(path, run, prefix, freeze, read, expected_binding)))
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(str(path) + ': ' + str(error))
    for directory in sorted(run.glob('worker*/episode*')):
        metadata_raw, supervisor_raw = read(directory / 'metadata.json'), read(
            directory / 'supervisor_metadata.json')
        metadata, supervisor = json.loads(metadata_raw), json.loads(supervisor_raw)
        matches, rejected = [], []
        require(metadata['freeze'] == freeze and metadata['epoch'] == supervisor['epoch'],
                'native episode metadata freeze/epoch differs')
        for path, wrapper in wrappers:
            for row in wrapper['shim_mapping']['episodes']:
                if row.get('directory') != str(directory):
                    continue
                try:
                    require(row.get('metadata_sha256') == digest(metadata_raw)
                            and row.get('supervisor_metadata_sha256') == digest(supervisor_raw),
                            'native metadata byte binding differs')
                    proof = episode_proof(row, wrapper, directory, metadata, supervisor)
                    matches.append({'monitor': str(path), **proof})
                except (ValueError, KeyError, TypeError) as error:
                    rejected.append({'monitor': str(path), 'reason': str(error)})
        if not matches:
            errors.append(str(directory) + ': no active exact-episode three-controller Shim proof')
        episodes.append({'directory': str(directory), 'epoch': metadata['epoch'],
                         'passed': bool(matches), 'complete_captures': matches, 'rejected_captures': rejected})
    require(episodes, 'no native episode to verify')
    return {'schema': 'mr3-v13-shim-mapping-review-v1', 'passed': not errors, 'freeze': freeze,
            'run': str(run), 'episodes': episodes, 'errors': errors,
            'scope': 'Independent saved-wrapper original-field equality, exact original monitor CLI '
                     'and raw/source SHA, then per-episode worker/controller namespace and loaded '
                     'Shim custody. Original closure gates still required; no body, 95% or PPO credit.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--freeze', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    bindings = {}

    def read(path):
        raw = path.read_bytes()
        entry = {'bytes': len(raw), 'sha256': digest(raw)}
        require(str(path) not in bindings or bindings[str(path)] == entry, 'input changed while reading')
        bindings[str(path)] = entry
        return raw

    result = review(args.run, args.prefix, args.freeze, read)
    for path, entry in bindings.items():
        require(digest(Path(path).read_bytes()) == entry['sha256'], 'input changed before verdict')
    result['bindings'] = bindings
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'errors': result['errors']}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
