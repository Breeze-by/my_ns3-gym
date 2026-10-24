"""Owned-process and mapped actuator binary snapshot; read-only, no ROS imports."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET


def proc_identity(pid):
    try:
        raw = Path(f'/proc/{pid}/stat').read_text()
    except FileNotFoundError:
        return None
    values = raw[raw.rfind(')') + 2:].split()
    return {'pid': pid, 'parent': int(values[1]), 'group': int(values[2]),
            'session': int(values[3]), 'start_ticks': int(values[19]), 'state': values[0]}


def same(saved):
    current = proc_identity(saved['pid'])
    return current if current and current['start_ticks'] == saved['start_ticks'] else None


def complete_rows(path):
    if not path.exists():
        return
    with path.open() as stream:
        for line in stream:
            if not line.endswith('\n'):
                break
            if line.strip():
                yield json.loads(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--launch', type=Path, required=True)
    parser.add_argument('--binary-proof', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    launch = json.loads(args.launch.read_bytes())
    binary = json.loads(args.binary_proof.read_bytes())
    assert launch['freeze'] == binary['freeze']
    parent = same(launch['benchmark_parent'])
    processes = {}
    for path in Path('/proc').iterdir():
        if path.name.isdigit():
            value = proc_identity(int(path.name))
            if value:
                processes[value['pid']] = value
    owned = set()
    if parent:
        owned.add(parent['pid'])
        changed = True
        while changed:
            added = {pid for pid, value in processes.items() if value['parent'] in owned} - owned
            changed = bool(added)
            owned.update(added)
    snapshots, mapped, errors = [], [], []
    for pid in sorted(owned):
        identity = processes[pid]
        try:
            argv = Path(f'/proc/{pid}/cmdline').read_bytes().decode().rstrip('\0').split('\0')
            if same(identity) is None:
                continue
            snapshot = {'identity': identity, 'argv': argv}
            snapshots.append(snapshot)
            if not argv or Path(argv[0]).name != 'gzserver':
                continue
            raw_maps = Path(f'/proc/{pid}/maps').read_bytes()
            if same(identity) is None:
                continue
            selected = [line for line in raw_maps.decode().splitlines()
                        if 'libmr3_gazebo_diff_drive.so' in line or 'libgazebo_ros_diff_drive.so' in line]
            mappings = []
            for line in selected:
                values = line.split(maxsplit=5)
                path = Path(values[5])
                current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
                stat = path.stat()
                device = f'{os.major(stat.st_dev):02x}:{os.minor(stat.st_dev):02x}'
                proof = {'raw_maps_line': line, 'path': str(path), 'resolved': str(path.resolve()),
                         'current_file_sha256': current_sha, 'file_inode': stat.st_ino,
                         'mapping_inode': int(values[4]), 'file_device': device,
                         'mapping_device': values[3],
                         'matches_declared_binary': str(path.resolve()) == binary['library_path']
                         and current_sha == binary['library_sha256']
                         and stat.st_ino == int(values[4]) and device == values[3]}
                mappings.append(proof)
                if not proof['matches_declared_binary']:
                    errors.append('mapped drive library differs from frozen binary proof')
            mapped.append({'identity': identity, 'matching_drive_map_lines': selected,
                           'mappings': mappings,
                           'new_drive_mapped': any('libmr3_gazebo_diff_drive.so' in s for s in selected),
                           'old_system_drive_mapped': any('libgazebo_ros_diff_drive.so' in s for s in selected),
                           'identity_still_same_after_maps': same(identity) is not None})
        except FileNotFoundError:
            continue
    episodes = []
    for directory in sorted(args.run.glob('worker*/episode*')):
        drivers = {}
        metadata_path = directory / 'metadata.json'
        metadata = json.loads(metadata_path.read_bytes()) if metadata_path.exists() else None
        for name in ('tb1', 'tb2', 'tb3'):
            path = directory / f'drive_{name}.jsonl'
            rows = list(complete_rows(path))
            if not rows:
                drivers[name] = {'available': False}
                continue
            config = rows[0]
            valid = (config.get('kind') == 'configuration'
                     and config.get('schema') == 'mr3-drive-actuation-v2'
                     and config.get('robot') == name and config.get('record_sequence') == 1
                     and (metadata is None or config.get('epoch') == metadata['epoch']))
            expected = {'compiled_source_sha256', 'compiled_header_sha256', 'compiled_helper_sha256', 'compiled_target_contract_sha256'}
            compiled_match = all(config.get(key) == binary[key] for key in expected)
            tagged_match = (config.get('command_mode') == 'tagged'
                            and config.get('command_topic') == f'/{name}/mr3_drive/target'
                            and config.get('status_topic') == f'/{name}/mr3_drive/status')
            library_match = config.get('loaded_library_path') == binary['library_path']
            if not valid or not compiled_match or not library_match or not tagged_match:
                errors.append('driver configuration source/library mismatch ' + name)
            drivers[name] = {'available': True, 'configuration': config,
                             'compiled_match': compiled_match, 'library_match': library_match,
                             'tagged_match': tagged_match,
                             'complete_rows': len(rows), 'last_record': rows[-1],
                             'command_received_count': sum(row['kind'] == 'command_received' for row in rows),
                             'actuation_count': sum(row['kind'] == 'actuation' for row in rows)}
        evidence = {}
        topology_path = directory / 'drive_topology.json'
        if topology_path.exists():
            raw = topology_path.read_bytes()
            topology = json.loads(raw)
            valid = topology.get('schema') == 'mr3-drive-topology-v1'
            for name in ('tb1', 'tb2', 'tb3'):
                driver = ('/' + name, 'turtlebot3_diff_drive')
                target, status = f'/{name}/mr3_drive/target', f'/{name}/mr3_drive/status'
                for entries, owner in ((topology['publishers'][target], ('/', 'motion_safety')),
                                       (topology['publishers'][status], driver),
                                       (topology['target_subscribers'][target], driver)):
                    valid = valid and len(entries) == 1 and all(
                        (row['namespace'], row['node']) == owner and
                        row['topic_type'] == 'std_msgs/msg/String' for row in entries)
                valid = valid and not any((row['namespace'], row['node']) == driver
                                          for row in topology['legacy_subscribers'][f'/{name}/cmd_vel'])
            if not valid:
                errors.append('native target/status topology differs from tagged pipeline')
            evidence['drive_topology'] = {'path': str(topology_path), 'sha256': hashlib.sha256(raw).hexdigest(),
                                          'valid': valid, 'actual': topology}
        for name in ('tb1', 'tb2', 'tb3'):
            path = directory / f'drive_model_{name}.sdf'
            if path.exists():
                raw = path.read_bytes()
                plugins = ET.fromstring(raw).findall(".//plugin[@name='turtlebot3_diff_drive']")
                valid = len(plugins) == 1
                if valid:
                    plugin = plugins[0]
                    valid = (plugin.get('filename') == 'libmr3_gazebo_diff_drive.so'
                             and plugin.findtext('mr3_tagged_commands') == 'true'
                             and (metadata is None or plugin.findtext('mr3_epoch') == metadata['epoch'])
                             and plugin.findtext('mr3_audit_path') == str(directory / f'drive_{name}.jsonl'))
                if not valid:
                    errors.append('actual effective tagged drive model differs ' + name)
                evidence[f'model_{name}'] = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                                             'valid': valid}
        episodes.append({'directory': str(directory), 'drivers': drivers, 'evidence': evidence})
    result = {'schema': 'mr3-v9-readonly-drive-mapping-monitor-v1', 'freeze': launch['freeze'],
              'run': str(args.run), 'wall_monotonic_ns': time.monotonic_ns(),
              'benchmark_parent_saved': launch['benchmark_parent'], 'benchmark_parent_current': parent,
              'launcher_saved': launch['launcher_identity'],
              'launcher_current': same(launch['launcher_identity']),
              'owned_current_processes': snapshots, 'gazebo_mapped_libraries': mapped,
              'episodes': episodes, 'errors': sorted(set(errors)),
              'scope': 'Owned identity, actual proc maps/inode and current disk bytes at capture; no process-memory byte read or body-response credit. Incomplete warmup is pending, not failure.'}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'output': str(args.output), 'parent': parent,
                      'owned_current': len(snapshots), 'gazebo': mapped, 'errors': result['errors']}))


if __name__ == '__main__':
    main()
