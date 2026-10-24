"""Read-only drive plus per-worker loaded RotationShim custody; no ROS imports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

REPO = Path('/home/zhuyulab/ns3-workspace')
ASSETS = REPO / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets'
BASE = ASSETS / '20261017_mr3_p2a0_v10/independent/mr3_readonly_v10_drive_process_monitor.py'
BASE_SHA = '7126969f615d768c5b8fe18039ffd5e0f9d090941e7a857e75b2c44436fb3d13'
ROBOTS = ('tb1', 'tb2', 'tb3')
ROS = REPO / 'ros2_ws/ros2-multi-robot-automap'
WORKER = ROS / 'scripts/mr3_env_worker.py'
EXPECTED = {
    'library': ('/opt/ros/humble/lib/libnav2_rotation_shim_controller.so',
                'ec301e3ef10e7e71dfdfc77d0164dfecfba2408ea0523bb05ebf1983da13fc15'),
    'header': ('/opt/ros/humble/include/nav2_rotation_shim_controller/nav2_rotation_shim_controller.hpp',
               '6bbd9ebf8eda7bbb9d32be60d7640d2e22e06801d30d87364dd3242b7a44ad01'),
    'plugin_xml': ('/opt/ros/humble/share/nav2_rotation_shim_controller/nav2_rotation_shim_controller.xml',
                   'efd520f83ddcbe8848ac4fe0d38571ce29e09a9d83cd265e609091aa36d31d2b'),
    'package_xml': ('/opt/ros/humble/share/nav2_rotation_shim_controller/package.xml',
                    'f4c57958fec392f9395082d291d2c5431c39d158ddf4618ef490530eef9ae510'),
    'tag_source': (None, 'e06b6c6a64853334b20398f750c517018c17a2017bec864c626726fcea261288'),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_identity(stat):
    return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def stable_file(path):
    """The returned bytes and stat belong to the same open file description."""
    path = Path(path)
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read()
        after = os.fstat(stream.fileno())
        linked = path.stat()
        if file_identity(before) != file_identity(after) or file_identity(after) != file_identity(linked):
            raise ValueError('file changed during read: ' + str(path))
    return raw, after


def stable_bytes(path):
    return stable_file(path)[0]


def proc_identity(pid, proc_root=Path('/proc')):
    try:
        raw = (proc_root / str(pid) / 'stat').read_text()
        fields = raw[raw.rfind(')') + 2:].split()
        return {'pid': pid, 'parent': int(fields[1]), 'group': int(fields[2]),
                'session': int(fields[3]), 'start_ticks': int(fields[19]), 'state': fields[0]}
    except (FileNotFoundError, ProcessLookupError):
        return None


def same(saved, proc_root=Path('/proc')):
    current = proc_identity(saved['pid'], proc_root)
    return (current if current and current['state'] != 'Z'
            and current['start_ticks'] == saved['start_ticks'] else None)


def identity_equal(left, right):
    keys = ('pid', 'parent', 'group', 'session', 'start_ticks')
    return left is not None and right is not None and all(left[k] == right[k] for k in keys)


def ancestor_chain(identity, worker, inventory, proc_root):
    """Each ancestor is tied to a captured start time, including the worker itself."""
    chain, seen = [], set()
    current = identity
    while current and current['pid'] not in seen:
        pid = current['pid']
        seen.add(pid)
        captured = inventory.get(pid)
        if (not captured or not identity_equal(captured, current)
                or same(captured, proc_root) is None):
            return None
        chain.append(current)
        if pid == worker['pid']:
            return chain if current['start_ticks'] == worker['start_ticks'] else None
        current = proc_identity(current['parent'], proc_root)
    return None


def namespace(argv):
    values = []
    for i, value in enumerate(argv):
        if value.startswith('__ns:='):
            if i == 0 or argv[i - 1] not in ('-r', '--remap'):
                raise ValueError('namespace is not an actual ROS remap')
            values.append(value.partition(':=')[2])
    if len(values) != 1 or values[0] not in tuple('/' + name for name in ROBOTS):
        raise ValueError('controller namespace missing, repeated or unexpected')
    return values[0][1:]


def check_binding(path):
    raw = stable_bytes(path)
    document = json.loads(raw)
    url = ('https://raw.githubusercontent.com/ros-navigation/navigation2/1.1.20/'
           'nav2_rotation_shim_controller/src/nav2_rotation_shim_controller.cpp')
    if (document.get('schema') != 'mr3-shim-installed-and-tag-binding-v1'
            or document.get('upstream_tag') != '1.1.20'
            or document.get('upstream_url') != url
            or set(document.get('files', {})) != set(EXPECTED)):
        raise ValueError('unexpected Shim installed/tag binding')
    files = {}
    for role, (canonical, expected_sha) in EXPECTED.items():
        declared = document['files'][role]
        target = Path(declared['path'])
        if not target.is_absolute():
            if role != 'tag_source':
                raise ValueError('installed Shim path must be absolute: ' + role)
            target = Path(path).parent / target
        if (declared['sha256'] != expected_sha
                or canonical is not None and target.resolve() != Path(canonical).resolve()):
            raise ValueError('unexpected Shim path/hash: ' + role)
        payload = stable_bytes(target)
        if sha(payload) != expected_sha:
            raise ValueError('Shim installed/tag bytes differ: ' + role)
        files[role] = {'path': str(target), 'resolved': str(target.resolve()),
                       'sha256': expected_sha, 'bytes': len(payload)}
    return {'path': str(path), 'sha256': sha(raw), 'files': files,
            'scope': 'Installed ELF/header/plugin XML/package plus independent official tag source '
                     'identity; this does not prove compiler reproducibility or source-to-ELF build.'}


def mapped_controller(captured, inventory, worker, library, proc_root=Path('/proc')):
    identity = captured['identity']
    result = {'identity': identity, 'valid': False, 'errors': []}
    try:
        current = same(identity, proc_root)
        if current is None:
            raise ValueError('controller PID/start no longer current')
        chain = ancestor_chain(current, worker, inventory, proc_root)
        if chain is None:
            raise ValueError('controller is not in this actual worker ancestry')
        result['ancestor_chain'] = chain
        cmdline = (proc_root / str(identity['pid']) / 'cmdline').read_bytes()
        argv = cmdline.decode().rstrip('\0').split('\0')
        result.update(argv=argv, cmdline_sha256=sha(cmdline))
        if not argv or Path(argv[0]).name != 'controller_server' or argv != captured['argv']:
            raise ValueError('controller actual argv changed or executable differs')
        result['robot'] = namespace(argv)
        maps_path = proc_root / str(identity['pid']) / 'maps'
        raw_maps = maps_path.read_bytes()
        lines = [line for line in raw_maps.decode().splitlines()
                 if 'libnav2_rotation_shim_controller.so' in line]
        result.update(maps_sha256=sha(raw_maps), shim_maps_lines=lines)
        if not lines:
            raise ValueError('Shim has not been mapped by this controller')
        mappings = []
        for line in lines:
            fields = line.split(maxsplit=5)
            if len(fields) != 6 or fields[5].endswith(' (deleted)'):
                raise ValueError('invalid/deleted Shim mapping')
            path = Path(fields[5])
            if not path.is_absolute() or str(path.resolve()) != library['resolved']:
                raise ValueError('Shim mapping has unexpected actual path')
            payload, stat = stable_file(path)
            device = f'{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}'
            if (sha(payload) != library['sha256'] or int(fields[4]) != stat.st_ino
                    or fields[3] != device):
                raise ValueError('Shim mapping inode/device/disk SHA differs')
            mappings.append({'raw_maps_line': line, 'resolved': str(path.resolve()),
                             'sha256': sha(payload), 'inode': stat.st_ino, 'device': device})
        result['mappings'] = mappings
        for mapping in mappings:
            payload, stat = stable_file(Path(mapping['resolved']))
            if (sha(payload) != mapping['sha256'] or stat.st_ino != mapping['inode']
                    or f'{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}' != mapping['device']):
                raise ValueError('Shim file identity/hash changed after mapping read')
        # Exec does not change start_ticks: compare the actual argv again as well.
        second_lines = [line for line in maps_path.read_text().splitlines()
                        if 'libnav2_rotation_shim_controller.so' in line]
        second_chain = ancestor_chain(current, worker, inventory, proc_root) or []
        chain_matches = (len(second_chain) == len(chain) and all(
            identity_equal(before, after) for before, after in zip(chain, second_chain)))
        if (not identity_equal(same(identity, proc_root), current) or lines != second_lines
                or (proc_root / str(identity['pid']) / 'cmdline').read_bytes() != cmdline
                or not chain_matches):
            raise ValueError('controller/ancestry/maps changed during capture')
        result['valid'] = True
    except (OSError, ValueError, KeyError, IndexError) as error:
        result['errors'].append(str(error))
    return result


def inspect_episodes(base, binding, proc_root=Path('/proc')):
    snapshots = base['owned_current_processes']
    inventory = {row['identity']['pid']: row['identity'] for row in snapshots}
    captured_by_pid = {row['identity']['pid']: row for row in snapshots}
    episodes = []
    for old in base['episodes']:
        directory = Path(old['directory'])
        result = {'directory': str(directory), 'complete': False, 'active_worker': False,
                  'controllers': {}, 'errors': []}
        try:
            metadata_raw = stable_bytes(directory / 'metadata.json')
            supervisor_raw = stable_bytes(directory / 'supervisor_metadata.json')
            metadata, supervisor = json.loads(metadata_raw), json.loads(supervisor_raw)
            result.update(epoch=metadata['epoch'], metadata_sha256=sha(metadata_raw),
                          supervisor_metadata_sha256=sha(supervisor_raw))
            if (metadata['freeze'] != base['freeze'] or metadata['epoch'] != supervisor['epoch']):
                raise ValueError('episode source freeze/epoch mismatch')
            worker = supervisor['worker_identity']
            result['worker_identity'] = worker
            current = same(worker, proc_root)
            if current is None:
                result['pending_reason'] = 'saved worker is no longer active; other snapshots required'
                episodes.append(result)
                continue
            if (not identity_equal(inventory.get(worker['pid']), current)
                    or not identity_equal(worker, current)):
                raise ValueError('episode worker not in actual benchmark-owned inventory')
            worker_cmdline = (proc_root / str(worker['pid']) / 'cmdline').read_bytes()
            worker_argv = worker_cmdline.decode().rstrip('\0').split('\0')
            command = supervisor['command']
            if (len(worker_argv) != 4
                    or Path(worker_argv[0]).resolve() != Path('/usr/bin/python3').resolve()
                    or Path(worker_argv[1]).resolve() != WORKER.resolve()
                    or worker_argv[2:] != ['--run-dir', str(directory)]
                    or worker_argv != captured_by_pid[worker['pid']]['argv']
                    or len(command) != 8 or command[:4] != [
                        '/usr/bin/bash', '--noprofile', '--norc', '-c']
                    or command[5:] != ['mr3-worker', str(ROS), str(directory)]):
                raise ValueError('actual worker argv/spawn command is not this episode')
            result.update(active_worker=True, worker_actual_argv=worker_argv,
                          worker_cmdline_sha256=sha(worker_cmdline))
            for captured in snapshots:
                argv = captured['argv']
                if not argv or Path(argv[0]).name != 'controller_server':
                    continue
                current_controller = same(captured['identity'], proc_root)
                if current_controller is None or ancestor_chain(
                        current_controller, worker, inventory, proc_root) is None:
                    continue
                controller = mapped_controller(captured, inventory, worker,
                                               binding['files']['library'], proc_root)
                robot = controller.get('robot', 'unresolved_' + str(captured['identity']['pid']))
                if robot in result['controllers']:
                    raise ValueError('duplicate actual controller for robot ' + robot)
                result['controllers'][robot] = controller
            result['complete'] = (set(result['controllers']) == set(ROBOTS)
                                  and all(row['valid'] for row in result['controllers'].values())
                                  and identity_equal(same(worker, proc_root), current)
                                  and (proc_root / str(worker['pid']) / 'cmdline').read_bytes()
                                  == worker_cmdline)
            if not result['complete']:
                result['pending_reason'] = 'awaiting all three actual configured and mapped controllers'
        except (OSError, ValueError, KeyError) as error:
            result['errors'].append(str(error))
        episodes.append(result)
    return episodes


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--launch', type=Path, required=True)
    parser.add_argument('--binary-proof', type=Path, required=True)
    parser.add_argument('--shim-binding', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    if sha(stable_bytes(BASE)) != BASE_SHA:
        raise ValueError('immutable original drive monitor source changed')
    binding = check_binding(args.shim_binding)
    support = args.output.parent / (args.output.stem + '_support')
    support.mkdir(exist_ok=False)
    argv = [sys.executable, str(BASE), str(args.run), '--launch', str(args.launch),
            '--binary-proof', str(args.binary_proof), '--output', str(support / 'drive_base.json')]
    completed = subprocess.run(argv, capture_output=True, timeout=45, check=False)
    (support / 'base.stdout').write_bytes(completed.stdout)
    (support / 'base.stderr').write_bytes(completed.stderr)
    if completed.returncode:
        raise RuntimeError('original drive mapping monitor failed; original output retained')
    raw = stable_bytes(support / 'drive_base.json')
    base = json.loads(raw)
    base['shim_mapping'] = {
        'schema': 'mr3-v13-shim-mapping-supplement-v2', 'captured_wall_monotonic_ns': time.monotonic_ns(),
        'producer_source': str(Path(__file__).resolve()),
        'producer_source_sha256': sha(stable_bytes(Path(__file__))),
        'binding': binding, 'base_monitor': {
            'source': str(BASE), 'sha256': BASE_SHA, 'actual_argv': argv,
            'returncode': completed.returncode, 'output_sha256': sha(raw),
            'stdout_sha256': sha(completed.stdout), 'stderr_sha256': sha(completed.stderr)},
        'episodes': inspect_episodes(base, binding),
        'scope': 'Actual worker/controller PID start, ancestry, namespace and mapped path/inode/disk '
                 'ELF bytes at capture only. No ROS calls, process memory read, body response, '
                 'whole-task or per-packet credit. Unconfigured startup is pending. Each real '
                 'episode needs its own active complete snapshot; old worker snapshots cannot substitute.'}
    with args.output.open('x') as stream:
        json.dump(base, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'shim_episodes': [
        {'directory': row['directory'], 'active': row['active_worker'], 'complete': row['complete'],
         'errors': row['errors']} for row in base['shim_mapping']['episodes']]}))


if __name__ == '__main__':
    main()
