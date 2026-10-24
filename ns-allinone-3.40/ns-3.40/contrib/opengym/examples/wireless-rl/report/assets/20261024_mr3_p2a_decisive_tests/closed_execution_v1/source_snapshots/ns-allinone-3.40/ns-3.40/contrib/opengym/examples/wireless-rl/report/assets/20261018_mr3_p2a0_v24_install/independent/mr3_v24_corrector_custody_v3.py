#!/usr/bin/python3
"""Additional actual ray-box corrector custody only; old native/math gates stay separate."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
MONITOR = W / 'report/assets/20261017_mr3_p2a0_v13/independent/mr3_readonly_v13_drive_shim_process_monitor_v2.py'
MONITOR_SHA = '45d33e163848da42a73c41f67a8f4c0cd27d36d19ffe645b62072e42994aaae8'
WORKER = ROS / 'scripts/mr3_env_worker.py'
SOURCE_FIELDS = ('compiled_source_sha256', 'compiled_collision_source_sha256',
                 'compiled_collision_header_sha256')
COUNTERS = ('callback_calls', 'hits', 'misses', 'nonzero_nearparallel_calls', 'callback_errors')


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def parse(raw):
    return json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON constant')))


def id_pair(value):
    require(type(value) is dict and type(value.get('pid')) is int
            and type(value.get('start_ticks')) is int
            and value['pid'] > 0 and value['start_ticks'] > 0, 'PID/start identity must be typed positive integers')
    return value['pid'], value['start_ticks']


def stat_identity(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


class Reader:
    """Frozen file reader; /proc observations deliberately use separate fresh reads."""
    def __init__(self):
        self.bindings = {}

    def __call__(self, path):
        path = Path(path)
        before = path.stat()
        raw = path.read_bytes()
        require(stat_identity(before) == stat_identity(path.stat()), 'input changed during read: ' + str(path))
        entry = {'sha256': sha(raw), 'bytes': len(raw)}
        require(str(path) not in self.bindings or self.bindings[str(path)] == entry,
                'input changed across reads: ' + str(path))
        self.bindings.setdefault(str(path), entry)
        return raw

    def finish(self):
        for path, value in list(self.bindings.items()):
            require(sha(Path(path).read_bytes()) == value['sha256'], 'bound file changed before verdict: ' + path)


def load_binding(path, read):
    binding = parse(read(Path(path)))
    require(binding.get('schema') == 'mr3-ray-box-corrector-binding-v1'
            and binding.get('status') == 'ready', 'corrector binding pending or unknown')
    require(binding['monitor'] == {'path': str(MONITOR), 'sha256': MONITOR_SHA}, 'immutable monitor binding differs')
    require(sha(read(MONITOR)) == MONITOR_SHA, 'immutable monitor bytes differ')
    require(binding['ledger_filename'] == 'ray_box_corrector.jsonl', 'only actual fixed per-episode ledger accepted')
    require(set(binding['sources']) == set(SOURCE_FIELDS), 'three compiled source bindings required')
    for key, value in binding['sources'].items():
        require(type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256'])
                and sha(read(Path(value['path']))) == value['sha256'], 'source identity differs: ' + key)
    for name in ('library', 'ode_library'):
        value = binding[name]
        require(type(value['bytes']) is int and value['bytes'] > 0
                and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']), 'invalid library binding')
    require(binding['world_names'] == {'open': 'p1c_open', 'rooms': 'p1c_rooms', 'corridors': 'p1c_corridors'},
            'actual world-name mapping differs')
    receipt_binding = binding['binary_receipt']
    receipt_raw = read(Path(receipt_binding['path']))
    require(sha(receipt_raw) == receipt_binding['sha256'], 'actual binary custody receipt changed')
    receipt = parse(receipt_raw)
    require(receipt.get('schema') == 'mr3-v22-ray-box-actual-binary-custody-v1'
            and receipt.get('passed') is True
            and canonical(receipt['installed_library']) == canonical(binding['library'])
            and canonical(receipt['actual_ode_library']) == canonical(binding['ode_library']),
            'binding differs from actual canonical binary/ODE custody')
    names = dict(zip(SOURCE_FIELDS, ('src/mr3_ray_box_corrector.cpp',
                     'src/mr3_ray_box_collision.cpp', 'include/multi_robot/mr3_ray_box_collision.hpp')))
    for key, name in names.items():
        original = receipt['sources'][name]
        require(binding['sources'][key] == {'path': original['path'], 'sha256': original['sha256']},
                'binding differs from canonical compiled-source receipt')
    return binding


def file_proof(value, read):
    path = Path(value['path'])
    with path.open('rb') as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read()
        after = os.fstat(stream.fileno())
    require(stat_identity(before) == stat_identity(after) == stat_identity(path.stat()), 'library changed during read')
    require(str(path.resolve(strict=True)) == value['resolved'] and raw.startswith(b'\x7fELF')
            and sha(raw) == value['sha256'] and len(raw) == value['bytes'], 'actual ELF/path/SHA/size differs')
    require(read(path) == raw, 'bound library bytes differ')
    return {'path': str(path), 'resolved': value['resolved'], 'sha256': sha(raw), 'bytes': len(raw),
            'stat': stat_identity(before), 'device': '%02x:%02x' % (os.major(before.st_dev), os.minor(before.st_dev)),
            'inode': before.st_ino}


def maps_for(raw, library):
    rows = []
    for line in raw.decode().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or fields[5] != library['resolved']:
            continue
        require(int(fields[4]) == library['inode']
                and [int(x, 16) for x in fields[3].split(':')] ==
                [int(x, 16) for x in library['device'].split(':')], 'mapped library inode/device differs')
        rows.append(line)
    require(rows and any('x' in line.split()[1] for line in rows),
            'actual owned process lacks executable declared mapped library')
    return rows


def proc_identity(pid, proc_root):
    raw = (proc_root / str(pid) / 'stat').read_text()
    fields = raw[raw.rfind(')') + 2:].split()
    return {'pid': pid, 'start_ticks': int(fields[19]), 'parent': int(fields[1]),
            'state': fields[0], 'stat_raw': raw}


def actual_ancestry(gz, worker, inventory, proc_root):
    target = id_pair(worker)
    chain, visited = [], set()
    pid = id_pair(gz)[0]
    while pid not in visited:
        visited.add(pid)
        require(pid in inventory, 'gzserver worker ancestry absent from immutable snapshot')
        captured = inventory[pid]
        current = proc_identity(pid, proc_root)
        require(id_pair(captured) == id_pair(current) and current['state'] != 'Z'
                and current['parent'] == captured['parent'], 'live ancestor identity changed')
        chain.append(current)
        if id_pair(current) == target:
            return chain
        pid = current['parent']
    raise ValueError('owned gzserver does not descend from this exact worker')


def config_check(row, binding, epoch, pid):
    require(row.get('schema') == 'mr3-ray-box-corrector-audit-v1'
            and row.get('kind') == 'configuration' and row.get('plugin_type') == 'SystemPlugin'
            and row.get('epoch') == epoch and type(row.get('process_id')) is int
            and row['process_id'] == pid, 'corrector actual configuration identity differs')
    for key in SOURCE_FIELDS:
        require(row.get(key) == binding['sources'][key]['sha256'], 'compiled source macro differs: ' + key)
    require(row.get('loaded_library_path') == binding['library']['resolved']
            and row.get('actual_ode_library_path') == binding['ode_library']['resolved'], 'actual callback/library path differs')


def observe(monitor_path, binding_path, freeze, read, *, proc_root=Path('/proc')):
    require(type(freeze) is str and re.fullmatch('[0-9a-f]{40}', freeze), 'exact freeze required')
    binding = load_binding(binding_path, read)
    monitor_raw = read(Path(monitor_path))
    monitor = parse(monitor_raw)
    require(monitor['freeze'] == freeze and monitor['errors'] == [], 'original monitor freeze/error differs')
    shim = monitor['shim_mapping']
    require(shim['producer_source'] == str(MONITOR) and shim['producer_source_sha256'] == MONITOR_SHA,
            'actual immutable monitor producer differs')
    inventory = {row['identity']['pid']: row['identity'] for row in monitor['owned_current_processes']}
    libraries = {name: file_proof(binding[name], read) for name in ('library', 'ode_library')}
    require(all(value['sha256'].encode() in read(Path(binding['library']['path']))
                for value in binding['sources'].values()), 'actual corrector ELF lacks compiled source3 macros')
    episodes, errors, pending = [], [], []
    for original in monitor['episodes']:
        directory = Path(original['directory'])
        try:
            meta_raw = read(directory / 'metadata.json')
            supervisor_raw = read(directory / 'supervisor_metadata.json')
            meta, supervisor = parse(meta_raw), parse(supervisor_raw)
            require(meta['freeze'] == freeze and meta['epoch'] == supervisor['epoch'], 'actual episode identity differs')
            worker = supervisor['worker_identity']
            worker_id = id_pair(worker)
            supporting = [row for row in shim['episodes'] if row.get('directory') == str(directory)
                          and row.get('epoch') == meta['epoch'] and row.get('active_worker') is True
                          and row.get('complete') is True and id_pair(row['worker_identity']) == worker_id]
            if not supporting:
                pending.append({'directory': str(directory), 'reason': 'original active complete worker proof not yet available'})
                continue
            cmdline = (proc_root / str(worker['pid']) / 'cmdline').read_bytes()
            argv = cmdline.decode().rstrip('\0').split('\0')
            require(len(argv) == 4 and Path(argv[0]).resolve() == Path('/usr/bin/python3').resolve()
                    and Path(argv[1]).resolve() == WORKER.resolve()
                    and argv[2:] == ['--run-dir', str(directory)]
                    and supporting[0]['worker_actual_argv'] == argv, 'worker argv does not identify this episode')
            matches = []
            for gz in monitor['gazebo_mapped_libraries']:
                if not (gz.get('new_drive_mapped') is True and gz.get('old_system_drive_mapped') is False
                        and gz.get('identity_still_same_after_maps') is True and gz.get('mappings')
                        and all(x.get('matches_declared_binary') is True for x in gz['mappings'])):
                    continue
                try:
                    chain = actual_ancestry(gz['identity'], worker, inventory, proc_root)
                except ValueError:
                    continue
                matches.append((gz['identity'], chain))
            require(len(matches) == 1, 'unique actual owned gzserver ancestry not established')
            gz, chain = matches[0]
            pid = gz['pid']
            before = proc_identity(pid, proc_root)
            maps_raw = (proc_root / str(pid) / 'maps').read_bytes()
            mapped = {name: maps_for(maps_raw, value) for name, value in libraries.items()}
            ledger_path = directory / binding['ledger_filename']
            with ledger_path.open('rb') as stream:
                header_raw = stream.readline(100000)
            require(header_raw.endswith(b'\n'), 'corrector configuration not complete')
            config = parse(header_raw)
            config_check(config, binding, meta['epoch'], pid)
            # Do not discard a real file/ELF error just because shutdown also occurs.
            for name, value in libraries.items():
                require(file_proof(binding[name], read) == value, 'mapped ELF changed during observation')
            require(id_pair(before) == id_pair(gz), 'owned gzserver changed before maps read')
            try:
                after = proc_identity(pid, proc_root)
            except FileNotFoundError:
                pending.append({'directory': str(directory),
                                'reason': 'owned gzserver disappeared after maps read; no mapping credit'})
                continue
            require(id_pair(before) == id_pair(after), 'owned gzserver changed during maps read')
            if after['state'] == 'Z':
                pending.append({'directory': str(directory),
                                'reason': 'same owned gzserver became zombie after maps read; no mapping credit'})
                continue
            episodes.append({'directory': str(directory), 'epoch': meta['epoch'], 'scene': meta['scene'],
                'worker_identity': worker, 'worker_actual_argv': argv, 'worker_cmdline_sha256': sha(cmdline),
                'metadata_sha256': sha(meta_raw), 'supervisor_metadata_sha256': sha(supervisor_raw),
                'gzserver_identity': before, 'gzserver_identity_after': after, 'actual_ancestry': chain,
                'maps_raw': maps_raw.decode(), 'maps_sha256': sha(maps_raw), 'maps_bytes': len(maps_raw),
                'mapped_libraries': libraries, 'matching_map_lines': mapped,
                'configuration_raw': header_raw.decode(), 'configuration_sha256': sha(header_raw),
                'configuration': config, 'actual_mapping_observed': True})
        except FileNotFoundError as error:
            pending.append({'directory': str(directory), 'reason': str(error)})
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append({'directory': str(directory), 'error': str(error)})
    return {'schema': 'mr3-v22-corrector-live-mapping-proof-v1', 'passed': bool(episodes) and not errors,
            'freeze': freeze, 'binding': {'path': str(binding_path), 'sha256': sha(read(Path(binding_path)))},
            'monitor': {'path': str(monitor_path), 'sha256': sha(monitor_raw), 'bytes': len(monitor_raw)},
            'episodes': episodes, 'errors': errors, 'pending': pending,
            'producer_source_sha256': sha(Path(__file__).read_bytes()),
            'wall_monotonic_ns': time.monotonic_ns(),
            'scope': 'One new /proc maps read per active exact worker/gzserver; source/ELF/inode custody only, not callback/physics/task proof.'}


def primitive_check(row):
    for key, count in [('start_box_local', 3), ('direction_box_local', 3), ('box_lengths', 3),
                       ('ray_start_world', 3), ('ray_direction_world', 3), ('box_rotation', 12)]:
        value = row[key]
        require(type(value) is list and len(value) == count
                and all(type(x) in (int, float) and math.isfinite(x) for x in value), 'primitive vector must be finite typed numeric')
    require(type(row['finite_ray_length']) in (int, float) and math.isfinite(row['finite_ray_length'])
            and row['finite_ray_length'] >= 0 and type(row['corrected_hit']) is bool
            and type(row['ray_body_is_null']) is bool, 'primitive scalar/flag differs')
    if row['corrected_hit']:
        require(type(row['corrected_axis']) is int and 0 <= row['corrected_axis'] < 3
                and type(row['corrected_depth']) in (int, float)
                and math.isfinite(row['corrected_depth']) and 0 <= row['corrected_depth'] <= row['finite_ray_length'], 'primitive contact depth/axis invalid')
    else:
        require(row['corrected_axis'] is None and row['corrected_depth'] is None, 'miss must not contain hit depth')
    require(type(row['published_world_clock_ns']) is int and row['published_world_clock_ns'] >= -1,
            'primitive publication clock invalid')


def ledger_review(raw, binding, epoch, pid, world, configuration_sha):
    require(raw.endswith(b'\n'), 'closed corrector ledger has partial tail')
    rows = [parse(line) for line in raw.splitlines()]
    require(len(rows) >= 4, 'closed ledger lacks lifecycle rows')
    kinds = [row.get('kind') for row in rows]
    require(kinds[0] == 'configuration' and kinds.count('configuration') == 1
            and kinds[1] == 'installed' and kinds.count('installed') == 1
            and kinds[-1] == 'process_lifetime_summary' and kinds.count('process_lifetime_summary') == 1
            and kinds.count('plugin_destructor_snapshot') == 1, 'corrector lifecycle row ordering/count differs')
    require(sha(raw.splitlines(keepends=True)[0]) == configuration_sha, 'closed configuration differs from actual mapped header')
    config_check(rows[0], binding, epoch, pid)
    allowed = {'configuration', 'installed', 'first_actual_callback',
               'first_outside_nearparallel_toward_slab', 'plugin_destructor_snapshot', 'process_lifetime_summary'}
    for row in rows:
        require(row.get('schema') == 'mr3-ray-box-corrector-audit-v1' and row.get('epoch') == epoch
                and type(row.get('process_id')) is int and row['process_id'] == pid
                and row['kind'] in allowed, 'ledger source/PID/epoch/kind differs or fatal error recorded')
    install = rows[1]
    require(type(install['native_ode_quickstep_iterations']) is int
            and install['native_ode_quickstep_iterations'] == 150
            and type(install['physics_max_step_size_sec']) in (int, float)
            and math.isfinite(install['physics_max_step_size_sec'])
            and install['physics_max_step_size_sec'] == .001, 'native ODE150/actual maxstep readback differs')
    require(type(install['world_clock_ns']) is int and install['world_clock_ns'] == 0
            and install['installation_phase'] == 'world_created_during_load_before_world_init'
            and install['world_iterations'] is None
            and install['world_iterations_available'] is False
            and install['world_iterations_unavailable_reason'] == 'counter_initialized_only_in_World_Init'
            and install['world_lookup_succeeded'] is True
            and install['physics_available'] is True
            and install['physics_type'] == 'ode'
            and install['native_ode_world_available'] is True
            and type(install['failed_preconditions']) is list and not install['failed_preconditions']
            and install['world_load_completed'] is False
            and install['world_sensors_initialized'] is False
            and type(install['model_sensor_count']) is int and install['model_sensor_count'] == 0
            and type(install['world_running_getter']) is bool
            and install['world'] == world and install['registered_pair'] == ['dRayClass', 'dBoxClass'], 'actual preInit lifecycle/pair differs')
    snapshots = [row for row in rows if row['kind'] in ('plugin_destructor_snapshot', 'process_lifetime_summary')]
    require(snapshots[-1] is rows[-1] and kinds[-2] == 'plugin_destructor_snapshot',
            'final process summary or normal plugin snapshot tail missing')
    previous = None
    for row in snapshots:
        require(all(type(row[key]) is int and row[key] >= 0 for key in COUNTERS), 'typed nonnegative counters required')
        require(row['callback_errors'] == 0, 'actual callback errors occurred')
        if previous is not None:
            require(all(row[key] >= previous[key] for key in COUNTERS), 'callback counters moved backwards')
        previous = row
    final = snapshots[-1]
    require(final['callback_calls'] > 0 and final['hits'] + final['misses'] == final['callback_calls']
            and final['nonzero_nearparallel_calls'] <= final['callback_calls'], 'actual completed callback count inconsistent or zero')
    for kind in ('first_actual_callback', 'first_outside_nearparallel_toward_slab'):
        selected = [row for row in rows if row['kind'] == kind]
        require(len(selected) <= 1, 'one-shot primitive duplicated')
        for row in selected:
            primitive_check(row)
    return {'passed': True, 'configuration': rows[0], 'installed': install,
            'plugin_snapshot': snapshots[0], 'process_summary': final,
            'first_actual_callback': next((row for row in rows if row['kind'] == 'first_actual_callback'), None),
            'first_outside_nearparallel_toward_slab': next((row for row in rows if row['kind'] == 'first_outside_nearparallel_toward_slab'), None),
            'scope': 'Actual registered-pair/source/callback lifecycle custody only. Optional nearparallel branch is descriptive, never required legacy-defect proof or new math credit.'}


def review(run, prefix, freeze, binding_path, read):
    require(type(freeze) is str and re.fullmatch('[0-9a-f]{40}', freeze), 'exact freeze required')
    binding = load_binding(binding_path, read)
    run, prefix = Path(run), Path(prefix)
    require(prefix.is_absolute() and prefix.is_relative_to(Path('/tmp')), 'only explicit TMP proof prefix accepted')
    mapping_paths = sorted(prefix.parent.glob(prefix.name + '_corrector_mapping_*.json'))
    require(mapping_paths, 'no actual corrector mapping snapshots')
    mappings = []
    for path in mapping_paths:
        proof = parse(read(path))
        require(proof.get('schema') == 'mr3-v22-corrector-live-mapping-proof-v1'
                and proof['freeze'] == freeze and proof['errors'] == []
                and proof.get('producer_source_sha256') == sha(Path(__file__).read_bytes()),
                'mapping proof has real error, wrong source or wrong freeze')
        require(proof['binding'] == {'path': str(binding_path), 'sha256': sha(read(Path(binding_path)))}, 'mapping used another binding')
        monitor = parse(read(Path(proof['monitor']['path'])))
        require(sha(read(Path(proof['monitor']['path']))) == proof['monitor']['sha256']
                and monitor['freeze'] == freeze and monitor['errors'] == [], 'original immutable monitor bytes changed')
        for row in proof['episodes']:
            attached = dict(row)
            attached['_monitor'] = monitor
            mappings.append(attached)
    episodes = []
    for directory in sorted(run.glob('worker*/episode*')):
        meta_raw, supervisor_raw = read(directory / 'metadata.json'), read(directory / 'supervisor_metadata.json')
        meta, supervisor = parse(meta_raw), parse(supervisor_raw)
        epoch, worker = meta['epoch'], supervisor['worker_identity']
        require(meta['freeze'] == freeze and supervisor['epoch'] == epoch, 'closed episode identity differs')
        found = [row for row in mappings if row['directory'] == str(directory) and row['epoch'] == epoch
                 and id_pair(row['worker_identity']) == id_pair(worker) and row.get('actual_mapping_observed') is True]
        require(found, 'this exact actual episode/worker lacks corrector mapping proof')
        for row in found:
            monitor = row['_monitor']
            supplement = monitor['shim_mapping']
            require(supplement['producer_source'] == str(MONITOR)
                    and supplement['producer_source_sha256'] == MONITOR_SHA, 'monitor producer identity differs')
            support = [x for x in supplement['episodes'] if x.get('directory') == str(directory)
                       and x.get('epoch') == epoch and x.get('complete') is True
                       and x.get('active_worker') is True and id_pair(x['worker_identity']) == id_pair(worker)]
            require(len(support) == 1 and support[0]['worker_actual_argv'] == row['worker_actual_argv'],
                    'mapped corrector proof borrowed a different actual worker/episode')
            argv = row['worker_actual_argv']
            require(len(argv) == 4 and Path(argv[0]).resolve() == Path('/usr/bin/python3').resolve()
                    and Path(argv[1]).resolve() == WORKER.resolve()
                    and argv[2:] == ['--run-dir', str(directory)], 'stored worker argv borrowed another episode')
            require(any(x['directory'] == str(directory) for x in monitor['episodes']),
                    'original monitor lacks this actual episode')
            inventory = {x['identity']['pid']: x['identity'] for x in monitor['owned_current_processes']}
            chain = row['actual_ancestry']
            require(chain and id_pair(chain[0]) == id_pair(row['gzserver_identity'])
                    and id_pair(chain[-1]) == id_pair(worker), 'captured ancestry endpoints differ')
            for index, ancestor in enumerate(chain):
                captured = inventory.get(ancestor['pid'])
                require(captured is not None and id_pair(ancestor) == id_pair(captured)
                        and ancestor['parent'] == captured['parent'], 'captured actual ancestry differs from immutable monitor')
                if index + 1 < len(chain):
                    require(ancestor['parent'] == chain[index + 1]['pid'], 'captured ancestry has a gap')
            require(any(id_pair(g['identity']) == id_pair(row['gzserver_identity'])
                        and g.get('new_drive_mapped') is True and g.get('old_system_drive_mapped') is False
                        and g.get('identity_still_same_after_maps') is True
                        for g in monitor['gazebo_mapped_libraries']), 'original owned gzserver mapping missing')
            require(row['metadata_sha256'] == sha(meta_raw) and row['supervisor_metadata_sha256'] == sha(supervisor_raw), 'mapped episode metadata changed')
            require(id_pair(row['gzserver_identity']) == id_pair(row['gzserver_identity_after']), 'mapped gzserver PID reused')
            maps_raw = row['maps_raw'].encode()
            require(sha(maps_raw) == row['maps_sha256'] and len(maps_raw) == row['maps_bytes'], 'actual maps original bytes differ')
            for name in ('library', 'ode_library'):
                actual = file_proof(binding[name], read)
                require(actual == row['mapped_libraries'][name], 'mapped library file identity changed')
                require(maps_for(maps_raw, actual) == row['matching_map_lines'][name], 'stored selected maps differ')
            require(sha(row['configuration_raw'].encode()) == row['configuration_sha256'], 'original mapped header bytes differ')
            config_check(parse(row['configuration_raw']), binding, epoch, row['gzserver_identity']['pid'])
        row = found[0]
        pid = row['gzserver_identity']['pid']
        require(all(id_pair(item['gzserver_identity']) == id_pair(row['gzserver_identity'])
                    and item['configuration_sha256'] == row['configuration_sha256'] for item in found), 'one episode has conflicting gzserver/configuration identities')
        ledger_path = directory / binding['ledger_filename']
        raw = read(ledger_path)
        checked = ledger_review(raw, binding, epoch, pid, binding['world_names'][meta['scene']], row['configuration_sha256'])
        shutdown = parse(read(directory / 'supervisor_shutdown.json'))
        require(shutdown['epoch'] == epoch and type(shutdown['worker_returncode']) is int and shutdown['worker_returncode'] == 0
                and shutdown['forced_shutdown'] is False and shutdown['failed_sample'] is False
                and shutdown['remaining_owned_processes'] == [] and shutdown['remaining_owned_zombies'] == [], 'corrector evidence lacks normal strict supervisor closure')
        require(any(id_pair(identity) == id_pair(row['gzserver_identity']) for identity in shutdown['owned_processes_seen']), 'actual corrected gzserver missing from owned shutdown identities')
        episodes.append({'directory': str(directory), 'epoch': epoch, 'worker_identity': worker,
                         'gzserver_identity': row['gzserver_identity'], 'mapping_count': len(found),
                         'ledger': {'path': str(ledger_path), 'sha256': sha(raw), 'bytes': len(raw)},
                         'review': checked, 'passed': True})
    require(episodes, 'no actual episodes to review')
    return {'schema': 'mr3-v22-corrector-closed-custody-review-v1', 'passed': True,
            'freeze': freeze, 'run': str(run), 'episodes': episodes, 'errors': [],
            'scope': 'Nested corrector mapping/ledger custody supplement only. Original full closure/34math jobs remain independently mandatory; this is not task or physics repair PASS.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    active = sub.add_parser('observe')
    active.add_argument('--monitor', type=Path, required=True)
    closed = sub.add_parser('review')
    closed.add_argument('run', type=Path)
    closed.add_argument('--prefix', type=Path, required=True)
    for child in (active, closed):
        child.add_argument('--binding', type=Path, required=True)
        child.add_argument('--freeze', required=True)
        child.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    require(args.output.is_absolute() and args.output.is_relative_to(Path('/tmp')), 'only new TMP output permitted')
    reader = Reader()
    try:
        result = (observe(args.monitor, args.binding, args.freeze, reader) if args.mode == 'observe'
                  else review(args.run, args.prefix, args.freeze, args.binding, reader))
        reader.finish()
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {'schema': 'mr3-v22-corrector-' + args.mode + '-failure-v1',
                  'passed': False, 'freeze': args.freeze, 'errors': [str(error)]}
    result.update(input_bindings=reader.bindings, source_sha256=sha(Path(__file__).read_bytes()))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'passed': result['passed'], 'output': str(args.output), 'errors': result.get('errors', [])}))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
