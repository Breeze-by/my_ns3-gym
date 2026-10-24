#!/usr/bin/python3
"""Fixed overlay file/build and per-episode actual smoother mapping custody only."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
ROS = ROOT / 'ros2_ws/ros2-multi-robot-automap'
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ASSET = W / 'report/assets/20261018_mr3_p2a0_v25_smoother'
MONITOR = W / 'report/assets/20261017_mr3_p2a0_v13/independent/mr3_readonly_v13_drive_shim_process_monitor_v2.py'
MONITOR_SHA = '45d33e163848da42a73c41f67a8f4c0cd27d36d19ffe645b62072e42994aaae8'
UPSTREAM_COMMIT = 'a097086719c88f781aa59788eca29ac6ca5e56db'
UPSTREAM_CPP_SHA = '788822f4ac41a03a46e73b6a7a73f876a75792e093d6c3f7b3dceecb69bcc50d'
SOURCE_SHA = {
    'CMakeLists.txt': '234d4190fbd7a624fad57aa96f12dc0f0c641ffd372b95209f1b388fe3dee875',
    'LICENSE': 'e71fcb65bd31cdbdcf50cf43ab87a0c600ea3ec407495c2e15d1e68bc9c3bfc1',
    'README.md': 'f5c941119a0781806fb8e2db079f5de9b60af720a622cc6e1b06b2f835e94393',
    'include/nav2_velocity_smoother/velocity_smoother.hpp': '0c1c4f3b1609e9eddb4a2f3c6029ceff6b1247cffaf7fb0725e010fb75aaaedd',
    'package.xml': '91c33d28154f13ae22e0e7c4e4f4eaf44a01402377922903daed9afbdbc13439',
    'src/main.cpp': '1e6ac714f19ca1bdf157eda45209cfa2fe0dad1e429df50b033c671cfbe79240',
    'src/velocity_smoother.cpp': 'b49f5d345391ccf62dcd4111cfa82c49065efad997d4723f60c7dab3edc15cec',
    'test/CMakeLists.txt': '883e05c9e6984a95d446943fd735a75c7de75864fc508a589c6eb4ebea0bcf6f',
    'test/test_velocity_smoother.cpp': '6da51c5b6b7ffcd60d1a6510d1283cd60bb11849558dff0932fbcd3a5c94df61',
    'MR3_PROVENANCE.md': '81298764a6924f1084216b13a7a9430eaad1e5b10e3ab3667b1b28fe0db52dfb',
}
ROBOTS = ('tb1', 'tb2', 'tb3')
OLD_LIBRARY_SHA = {
    'libmr3_gazebo_diff_drive.so': 'a014f2c618e38fc8a306d76c100083d952606333045a2e35bffce6f8b25b10c8',
    'libmr3_gazebo_step.so': '8ae4067bcb8177ed7a28eeba3b2632a0de1df0c7250e5d1f019247323d9efee9',
    'libmr3_physics_diagnostic_profile.so': '09321ea65a2c893d2e65316f43d5ee54d5dda7014a5d40e2186b6b720055fcc1',
    'libmr3_ray_box_corrector.so': '782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8',
    'libmr3_ray_provenance_observer.so': 'b76138132ae7dbb35936c2e0971e909f688189d240de3910516157b3553d57b8',
    'libmr3_stop_response_observer.so': '9a1d76b0d9a6585bb2d40fb348bc5636bdd256838291e8ea605d1d05b18806bf',
}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def parse(raw):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def pair(value):
    require(type(value) is dict and type(value.get('pid')) is int
            and type(value.get('start_ticks')) is int and value['pid'] > 0
            and value['start_ticks'] > 0, 'typed PID/start required')
    return value['pid'], value['start_ticks']


def stat_key(value):
    return [value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


class Reader:
    def __init__(self):
        self.bindings = {}

    def __call__(self, path):
        path = Path(path)
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read()
            after = os.fstat(stream.fileno())
        require(stat_key(before) == stat_key(after) == stat_key(path.stat()), 'input changed during read')
        entry = {'sha256': sha(raw), 'bytes': len(raw)}
        previous = self.bindings.setdefault(str(path), entry)
        require(previous == entry, 'input changed across reads')
        return raw

    def finish(self):
        for path, expected in list(self.bindings.items()):
            require({'sha256': sha(Path(path).read_bytes()), 'bytes': Path(path).stat().st_size}
                    == expected, 'bound input changed before verdict')


def tools(read):
    raw = read(MONITOR)
    require(sha(raw) == MONITOR_SHA, 'original A13 monitor source differs')
    spec = importlib.util.spec_from_file_location('v25_original_process_tools', MONITOR)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(MONITOR), 'exec'), module.__dict__)
    return module


def inverse_cpp(raw):
    include = b'#include "rclcpp/create_timer.hpp"\n'
    require(raw.count(include) == 1, 'fixed new timer include differs')
    result = raw.replace(include, b'', 1)
    for indent in ('  ', '        '):
        new = (indent + 'timer_ = rclcpp::create_timer(\n' + indent +
               '  get_node_base_interface(), get_node_timers_interface(), get_clock(),\n' + indent +
               '  rclcpp::Duration(std::chrono::milliseconds(static_cast<int>(timer_duration_ms))),\n').encode()
        old = (indent + 'timer_ = this->create_wall_timer(\n' + indent +
               '  std::chrono::milliseconds(static_cast<int>(timer_duration_ms)),\n').encode()
        require(result.count(new) == 1, 'one of two fixed timer sites differs')
        result = result.replace(new, old, 1)
    require(sha(result) == UPSTREAM_CPP_SHA, 'timer inverse does not restore exact upstream source')
    return result


def expected_installed():
    return {
        'executable': {'path': str(ROS / 'install/nav2_velocity_smoother/lib/nav2_velocity_smoother/velocity_smoother'),
                       'resolved': str(ROS / 'build/nav2_velocity_smoother/velocity_smoother')},
        'core': {'path': str(ROS / 'install/nav2_velocity_smoother/lib/libvelocity_smoother_core.so'),
                 'resolved': str(ROS / 'build/nav2_velocity_smoother/libvelocity_smoother_core.so')},
    }


def file_proof(value, read):
    path = Path(value['path'])
    try:
        with path.open('rb') as stream:
            before = os.fstat(stream.fileno())
            raw = stream.read()
            after = os.fstat(stream.fileno())
        require(stat_key(before) == stat_key(after) == stat_key(path.stat()), 'ELF changed during read')
        require(path.resolve(strict=True) == Path(value['resolved']) and raw.startswith(b'\x7fELF')
                and type(value['bytes']) is int and len(raw) == value['bytes'] > 0
                and type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256'])
                and sha(raw) == value['sha256'], 'fixed installed ELF/path/size/SHA differs')
        require(read(path) == raw, 'bound ELF bytes differ')
    except OSError as error:
        raise ValueError('fixed ELF unavailable: ' + str(path)) from error
    return {**value, 'stat': stat_key(before), 'inode': before.st_ino,
            'device': '%02x:%02x' % (os.major(before.st_dev), os.minor(before.st_dev))}


def load_binding(path, read):
    require(Path(path) == ASSET / 'independent/mr3_v25_smoother_binding_v1.json', 'fixed binding path required')
    binding = parse(read(Path(path)))
    require(binding.get('schema') == 'mr3-v25-smoother-binding-v1'
            and binding.get('status') == 'ready', 'smoother binding pending/unknown')
    require(binding['monitor'] == {'path': str(MONITOR), 'sha256': MONITOR_SHA}, 'old monitor identity differs')
    tools(read)
    require(set(binding['installed']) == {'executable', 'core'}, 'both actual overlay ELFs required')
    for name, expected in expected_installed().items():
        require(all(binding['installed'][name][key] == value for key, value in expected.items()),
                'only canonical smoother overlay install/build paths accepted')
        file_proof(binding['installed'][name], read)
    for name, filename in (('source_manifest', 'source_manifest_v1.json'),
                           ('binary_receipt', 'build_evidence/selected_elf_manifest_v1.json')):
        item = binding[name]
        require(item['path'] == str(ASSET / filename)
                and sha(read(Path(item['path']))) == item['sha256'], 'fixed custody document differs')
    manifest = parse(read(Path(binding['source_manifest']['path'])))
    require(manifest.get('schema') == 'mr3-v25-smoother-source-manifest-v1'
            and manifest['upstream_commit'] == UPSTREAM_COMMIT
            and manifest['upstream_tag'] == '1.1.20'
            and manifest['source_root'] == str(ROS / 'src/nav2_velocity_smoother')
            and set(manifest['files']) == set(SOURCE_SHA), 'fixed source manifest differs')
    for relative, entry in manifest['files'].items():
        raw = read(Path(manifest['source_root']) / relative)
        require(type(entry['bytes']) is int and len(raw) == entry['bytes']
                and sha(raw) == entry['sha256'], 'source bytes differ: ' + relative)
        if relative in SOURCE_SHA:
            require(entry['sha256'] == SOURCE_SHA[relative], 'unreviewed official/timer source: ' + relative)
    inverse_cpp(read(Path(manifest['source_root']) / 'src/velocity_smoother.cpp'))
    receipt = parse(read(Path(binding['binary_receipt']['path'])))
    require(receipt.get('schema') == 'mr3-v25-smoother-selected-elf-v1'
            and receipt.get('roundtrip') is True and len(receipt['outputs']) == 2,
            'actual selected ELF custody differs')
    outputs = {row['path']: row for row in receipt['outputs']}
    require(set(outputs) == {item['path'] for item in binding['installed'].values()}, 'actual ELF set differs')
    for name, value in binding['installed'].items():
        item = outputs[value['path']]
        require(all(item[key] == value[key] for key in ('path', 'resolved', 'sha256', 'bytes')),
                'selected ELF differs from fixed binding')
        filename = 'velocity_smoother.gz.part000' if name == 'executable' else 'libvelocity_smoother_core.so.gz.part000'
        require(len(item['parts']) == 1, 'only reviewed single-part gzip archive accepted')
        part = item['parts'][0]
        require(part['path'] == str((ASSET / 'build_evidence' / filename).relative_to(ROOT)),
                'fixed ELF archive path differs')
        raw = read(ROOT / part['path'])
        require(type(part['bytes']) is int and len(raw) == part['bytes'] == item['gzip_bytes']
                and len(raw) < 100000000 and sha(raw) == part['sha256'] == item['gzip_sha256']
                and gzip.decompress(raw) == read(Path(value['path'])), 'ELF archive differs')
    require(receipt['build_receipt'] == str((ASSET / 'build_evidence/build_receipt_v1.json').relative_to(ROOT)),
            'fixed build receipt path differs')
    build_path = ROOT / receipt['build_receipt']
    require(sha(read(build_path)) == receipt['build_receipt_sha256'], 'actual build receipt differs')
    build_row = parse(read(build_path))
    require(build_row.get('schema') == 'mr3-v25-canonical-smoother-build-v1'
            and build_row.get('passed') is True
            and build_row.get('unchanged_mr3') is True and build_row.get('unchanged_sources') is True
            and canonical(build_row['sources']) == canonical(build_row['sources_after'])
            and canonical(build_row['previous_mr3_libraries']) == canonical(build_row['mr3_libraries_after']),
            'canonical build did not bind this overlay and unchanged native libraries')
    built = {row['path']: row for row in build_row['outputs']}
    require(set(built) == set(outputs), 'build output set differs')
    for path, item in outputs.items():
        require(all(built[path][key] == item[key] for key in ('path', 'resolved', 'sha256', 'bytes')),
                'selected output differs from actual canonical build')
    source_rows = {row['path']: row for row in build_row['sources']}
    require(len(source_rows) == len(SOURCE_SHA), 'build source set differs')
    for relative, item in manifest['files'].items():
        built_source = source_rows[str(ROS / 'src/nav2_velocity_smoother' / relative)]
        require(built_source['sha256'] == item['sha256'] and built_source['bytes'] == item['bytes'],
                'actual built source differs from fixed manifest')
    previous = {Path(row['path']).name: row for row in build_row['previous_mr3_libraries']}
    require(set(previous) == set(OLD_LIBRARY_SHA), 'six native library set differs')
    for name, digest in OLD_LIBRARY_SHA.items():
        value = previous[name]
        require(value['path'] == str(ROS / 'install/multi_robot/lib' / name)
                and value['resolved'] == str(ROS / 'build/multi_robot' / name)
                and value['sha256'] == digest, 'old native library binding differs')
        file_proof({key: value[key] for key in ('path', 'resolved', 'sha256', 'bytes')}, read)
    return binding


def runtime_resolution(binding):
    """Resolve the actual launch package and dependency without creating a ROS node."""
    code = '''from ament_index_python.packages import get_package_prefix
from launch_ros.substitutions import ExecutableInPackage
from launch import LaunchContext
import json, os, subprocess, sys
prefix = get_package_prefix('nav2_velocity_smoother')
executable = ExecutableInPackage(package='nav2_velocity_smoother', executable='velocity_smoother').perform(LaunchContext())
result = subprocess.run(['/usr/bin/ldd', executable], capture_output=True, text=True, timeout=5)
print(json.dumps(dict(package_prefix=prefix, executable=executable, interpreter=sys.executable,
    ld_library_path=os.environ.get('LD_LIBRARY_PATH'), ament_prefix_path=os.environ.get('AMENT_PREFIX_PATH'),
    ldd_returncode=result.returncode, ldd_stdout=result.stdout, ldd_stderr=result.stderr)))
'''
    command = ['/usr/bin/bash', '--noprofile', '--norc', '-e', '-c',
               'source /opt/ros/humble/setup.bash && source "$1/install/setup.bash" '
               '&& exec /usr/bin/python3 -B -c "$2"', 'mr3-v25-resolution', str(ROS), code]
    removed = {'PYTHONPATH', 'LD_LIBRARY_PATH', 'AMENT_PREFIX_PATH', 'CMAKE_PREFIX_PATH',
               'COLCON_PREFIX_PATH', 'ROS_PACKAGE_PATH', 'PYTHONHOME', 'VIRTUAL_ENV',
               'GAZEBO_PLUGIN_PATH', 'GAZEBO_MODEL_PATH', 'GAZEBO_RESOURCE_PATH'}
    env = {key: value for key, value in os.environ.items()
           if key not in removed and not key.startswith('CONDA')}
    env.update(PATH='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
               PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run(command, cwd=ROS, env=env, capture_output=True, timeout=15)
    require(result.returncode == 0, 'actual ROS overlay resolution subprocess failed: ' + repr(result.stderr))
    data = parse(result.stdout)
    require(data['package_prefix'] == str(ROS / 'install/nav2_velocity_smoother')
            and data['executable'] == binding['installed']['executable']['path']
            and data['interpreter'] == '/usr/bin/python3'
            and type(data['ldd_returncode']) is int and data['ldd_returncode'] == 0
            and 'not found' not in data['ldd_stdout'] + data['ldd_stderr'],
            'actual package/executable/ldd resolution differs')
    lines = [line for line in data['ldd_stdout'].splitlines()
             if line.strip().startswith('libvelocity_smoother_core.so => ')]
    require(len(lines) == 1 and lines[0].split()[2] == binding['installed']['core']['path']
            and Path(lines[0].split()[2]).resolve(strict=True) == Path(binding['installed']['core']['resolved']),
            'actual launch executable resolves another smoother core')
    return {'passed': True, 'argv': command, 'returncode': result.returncode,
            'stdout_sha256': sha(result.stdout), 'stderr_sha256': sha(result.stderr),
            'resolution': data, 'scope': 'Read-only ament/Launch/ldd; no ROS node or DDS participant'}


def verify_frozen_build(root, freeze, binding_path, read):
    require(Path(root) == ROOT and re.fullmatch('[0-9a-f]{40}', freeze), 'fixed root/exact freeze required')
    binding = load_binding(binding_path, read)
    documents = [Path(binding_path), Path(binding['source_manifest']['path']),
                 Path(binding['binary_receipt']['path'])]
    receipt = parse(read(documents[-1]))
    documents += [ROOT / receipt['build_receipt']]
    documents += [ROOT / part['path'] for item in receipt['outputs'] for part in item['parts']]
    manifest = parse(read(Path(binding['source_manifest']['path'])))
    documents += [Path(manifest['source_root']) / relative for relative in manifest['files']]
    proof = {}
    for path in documents:
        relative = str(path.relative_to(ROOT))
        raw = read(path)
        require(subprocess.check_output(['git', 'show', freeze + ':' + relative], cwd=ROOT) == raw,
                'smoother worktree differs from exact freeze: ' + relative)
        proof[relative] = {'sha256': sha(raw), 'bytes': len(raw), 'git_source': freeze + ':' + relative}
    proof[str(Path(binding_path).relative_to(ROOT))].update(
        actual_installed=binding['installed'], actual_ros_resolution=runtime_resolution(binding),
        scope='Fixed source/build/file identity; live per-episode mappings required separately')
    return proof


def map_lines(raw, elf):
    selected = []
    for line in raw.decode().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or 'libvelocity_smoother_core.so' not in fields[5]:
            continue
        require(fields[5] == elf['resolved'] and int(fields[4]) == elf['inode']
                and fields[3] == elf['device'], 'core mapped from another/deleted inode/path/device')
        selected.append(line)
    require(selected and any('x' in row.split()[1] for row in selected), 'declared core lacks executable map')
    return selected


def observe(monitor_path, binding_path, freeze, read, proc_root=Path('/proc')):
    binding, util = load_binding(binding_path, read), tools(read)
    base_raw = read(Path(monitor_path))
    base = parse(base_raw)
    require(base['freeze'] == freeze and base['errors'] == [], 'original monitor error/freeze differs')
    supplement = base['shim_mapping']
    require(supplement['producer_source'] == str(MONITOR)
            and supplement['producer_source_sha256'] == MONITOR_SHA, 'original monitor source differs')
    inventory = {row['identity']['pid']: row['identity'] for row in base['owned_current_processes']}
    executable = file_proof(binding['installed']['executable'], read)
    core = file_proof(binding['installed']['core'], read)
    episodes, errors = [], []
    for old in supplement['episodes']:
        result = {'directory': old['directory'], 'epoch': old.get('epoch'),
                  'worker_identity': old.get('worker_identity'), 'complete': False,
                  'processes': {}, 'errors': []}
        episodes.append(result)
        if old.get('active_worker') is not True or old.get('complete') is not True:
            result['pending_reason'] = 'original per-episode active worker proof pending'
            continue
        try:
            directory, worker = Path(old['directory']), old['worker_identity']
            meta_raw, supervisor_raw = read(directory / 'metadata.json'), read(directory / 'supervisor_metadata.json')
            meta, supervisor = parse(meta_raw), parse(supervisor_raw)
            require(meta['epoch'] == supervisor['epoch'] == old['epoch']
                    and meta['freeze'] == freeze and pair(supervisor['worker_identity']) == pair(worker),
                    'episode identity differs')
            worker_argv = ['/usr/bin/python3', str(ROS / 'scripts/mr3_env_worker.py'), '--run-dir', str(directory)]
            actual_worker = (proc_root / str(worker['pid']) / 'cmdline').read_bytes()
            require(old['worker_actual_argv'] == worker_argv, 'original worker argv borrows another episode')
            require(not actual_worker or actual_worker.decode().rstrip('\0').split('\0') == worker_argv,
                    'nonempty worker argv borrows another episode')
            fresh_worker = util.proc_identity(worker['pid'], proc_root)
            if fresh_worker is None:
                result['pending_reason'] = 'owned worker naturally disappeared; no credit'
                continue
            require(pair(fresh_worker) == pair(worker), 'worker PID reused')
            if fresh_worker['state'] == 'Z' and not actual_worker:
                result['pending_reason'] = 'same owned worker naturally closed; no credit'
                continue
            require(actual_worker.decode().rstrip('\0').split('\0') == worker_argv
                    and old['worker_actual_argv'] == worker_argv, 'worker argv borrows another episode')
            result.update(metadata_sha256=sha(meta_raw), supervisor_metadata_sha256=sha(supervisor_raw),
                          worker_actual_argv=worker_argv)
            for captured in base['owned_current_processes']:
                argv, identity = captured['argv'], captured['identity']
                if not argv or Path(argv[0]).name != 'velocity_smoother':
                    continue
                current = util.proc_identity(identity['pid'], proc_root)
                if current is None:
                    continue
                require(pair(current) == pair(identity), 'smoother PID reused')
                if current['state'] == 'Z':
                    continue
                chain = util.ancestor_chain(current, worker, inventory, proc_root)
                if chain is None:
                    continue
                raw_argv = (proc_root / str(identity['pid']) / 'cmdline').read_bytes()
                actual_argv = raw_argv.decode().rstrip('\0').split('\0')
                require(actual_argv == argv and argv[0] == executable['path']
                        and (proc_root / str(identity['pid']) / 'exe').resolve(strict=True)
                        == Path(executable['resolved']), 'actual smoother executable/argv differs')
                executable_stat = (proc_root / str(identity['pid']) / 'exe').stat()
                require(executable_stat.st_ino == executable['inode']
                        and executable_stat.st_dev == executable['stat'][0]
                        and executable_stat.st_mode & 0o111, 'actual executable inode/device/permission differs')
                robot = util.namespace(argv)
                require(robot not in result['processes'], 'duplicate actual smoother namespace')
                maps_path = proc_root / str(identity['pid']) / 'maps'
                maps_raw = maps_path.read_bytes()
                lines = map_lines(maps_raw, core)
                require(file_proof(binding['installed']['executable'], read) == executable
                        and file_proof(binding['installed']['core'], read) == core, 'ELF identity changed during capture')
                after = util.proc_identity(identity['pid'], proc_root)
                if after is None or (pair(after) == pair(identity) and after['state'] == 'Z'):
                    result['pending_reason'] = 'same process naturally closed during capture; no credit'
                    continue
                after_chain = util.ancestor_chain(after, worker, inventory, proc_root) or []
                same_chain = len(after_chain) == len(chain) and all(
                    util.identity_equal(before, final) for before, final in zip(chain, after_chain))
                require(pair(after) == pair(identity)
                        and maps_path.read_bytes() == maps_raw
                        and (proc_root / str(identity['pid']) / 'cmdline').read_bytes() == raw_argv
                        and (proc_root / str(identity['pid']) / 'exe').resolve(strict=True) == Path(executable['resolved'])
                        and (proc_root / str(identity['pid']) / 'exe').stat().st_ino == executable['inode']
                        and same_chain,
                        'process/ancestry/maps changed during capture')
                result['processes'][robot] = {'identity': identity, 'identity_after': after,
                    'argv': argv, 'actual_ancestry': chain, 'cmdline_sha256': sha(raw_argv),
                    'maps_raw': maps_raw.decode(), 'maps_sha256': sha(maps_raw),
                    'core_maps_lines': lines, 'executable': executable, 'core': core}
            result['complete'] = (set(result['processes']) == set(ROBOTS)
                                  and util.same(worker, proc_root) is not None
                                  and (proc_root / str(worker['pid']) / 'cmdline').read_bytes() == actual_worker)
            if not result['complete']:
                result.setdefault('pending_reason', 'awaiting three own active smoother processes')
        except FileNotFoundError:
            result['pending_reason'] = 'owned process naturally disappeared; no credit'
        except (OSError, ValueError, KeyError, TypeError) as error:
            result['errors'].append(str(error))
            errors.append(str(error))
    return {'schema': 'mr3-v25-smoother-live-mapping-v1', 'freeze': freeze,
            'producer_source_sha256': sha(read(Path(__file__))),
            'binding': {'path': str(binding_path), 'sha256': sha(read(Path(binding_path)))},
            'monitor': {'path': str(monitor_path), 'sha256': sha(base_raw)},
            'wall_monotonic_ns': time.monotonic_ns(), 'episodes': episodes, 'errors': errors,
            'passed': not errors and any(row['complete'] for row in episodes),
            'scope': 'Actual mapped overlay custody only, not body dynamics or task success'}


def review(run, prefix, freeze, binding_path, read):
    binding = load_binding(binding_path, read)
    paths = sorted(Path(prefix).parent.glob(Path(prefix).name + '_smoother_mapping_*.json'))
    require(paths, 'no actual smoother mapping snapshots')
    rows = []
    for path in paths:
        proof = parse(read(path))
        require(proof.get('schema') == 'mr3-v25-smoother-live-mapping-v1'
                and proof['freeze'] == freeze and proof['errors'] == []
                and proof['producer_source_sha256'] == sha(read(Path(__file__)))
                and proof['binding'] == {'path': str(binding_path), 'sha256': sha(read(Path(binding_path)))},
                'mapping source/binding/freeze/error differs')
        monitor = parse(read(Path(proof['monitor']['path'])))
        require(sha(read(Path(proof['monitor']['path']))) == proof['monitor']['sha256']
                and monitor['freeze'] == freeze and monitor['errors'] == [], 'original monitor changed')
        rows.extend((row, monitor) for row in proof['episodes'] if row.get('complete') is True)
    episodes = []
    for directory in sorted(Path(run).glob('worker*/episode*')):
        meta_raw, supervisor_raw = read(directory / 'metadata.json'), read(directory / 'supervisor_metadata.json')
        meta, supervisor = parse(meta_raw), parse(supervisor_raw)
        require(meta['freeze'] == freeze and meta['epoch'] == supervisor['epoch'], 'closed episode identity differs')
        found = []
        for row, monitor in rows:
            if row['directory'] != str(directory) or row['epoch'] != meta['epoch'] \
                    or pair(row['worker_identity']) != pair(supervisor['worker_identity']):
                continue
            support = monitor['shim_mapping']
            require(support['producer_source'] == str(MONITOR)
                    and support['producer_source_sha256'] == MONITOR_SHA, 'wrong original monitor producer')
            original = [x for x in support['episodes'] if x['directory'] == str(directory)
                        and x.get('complete') is True and x.get('active_worker') is True
                        and x.get('epoch') == meta['epoch']
                        and pair(x['worker_identity']) == pair(supervisor['worker_identity'])]
            require(len(original) == 1 and original[0]['worker_actual_argv'] == row['worker_actual_argv']
                    and row['worker_actual_argv'] == ['/usr/bin/python3', str(ROS / 'scripts/mr3_env_worker.py'), '--run-dir', str(directory)]
                    and row['metadata_sha256'] == sha(meta_raw)
                    and row['supervisor_metadata_sha256'] == sha(supervisor_raw)
                    and set(row['processes']) == set(ROBOTS), 'mapped episode borrowed another worker')
            inventory = {x['identity']['pid']: x for x in monitor['owned_current_processes']}
            for robot, process in row['processes'].items():
                require(pair(process['identity']) == pair(process['identity_after'])
                        and process['identity']['state'] != 'Z'
                        and process['identity_after']['state'] != 'Z', 'mapped PID reused or no longer active')
                captured = inventory.get(process['identity']['pid'])
                require(captured and captured['argv'] == process['argv']
                        and pair(captured['identity']) == pair(process['identity'])
                        and tools(read).namespace(process['argv']) == robot
                        and process['argv'][0] == binding['installed']['executable']['path'], 'mapped process differs from original inventory')
                chain = process['actual_ancestry']
                require(chain and pair(chain[0]) == pair(process['identity'])
                        and pair(chain[-1]) == pair(supervisor['worker_identity']), 'ancestry endpoints differ')
                for index, ancestor in enumerate(chain):
                    require(ancestor['pid'] in inventory
                            and pair(inventory[ancestor['pid']]['identity']) == pair(ancestor)
                            and inventory[ancestor['pid']]['identity']['parent'] == ancestor['parent']
                            and (index + 1 == len(chain) or ancestor['parent'] == chain[index + 1]['pid']),
                            'original ancestry chain differs')
                maps_raw = process['maps_raw'].encode()
                require(sha(maps_raw) == process['maps_sha256'], 'saved maps bytes differ')
                core = file_proof(binding['installed']['core'], read)
                executable = file_proof(binding['installed']['executable'], read)
                require(canonical(core) == canonical(process['core'])
                        and canonical(executable) == canonical(process['executable'])
                        and map_lines(maps_raw, core) == process['core_maps_lines'], 'saved ELF/maps identity differs')
            found.append(row)
        require(found, 'this exact episode lacks a complete active three-smoother mapping')
        episodes.append({'directory': str(directory), 'epoch': meta['epoch'],
                         'worker_identity': supervisor['worker_identity'], 'active_captures': len(found), 'passed': True})
    require(episodes, 'no actual episodes')
    return {'schema': 'mr3-v25-smoother-custody-review-v1', 'passed': True, 'freeze': freeze,
            'episodes': episodes, 'errors': [], 'scope': 'Overlay file/build and per-episode mapped identity only; all old mathematical and closure gates remain necessary'}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='operation', required=True)
    observe_parser = sub.add_parser('observe')
    observe_parser.add_argument('--monitor', required=True, type=Path)
    review_parser = sub.add_parser('review')
    review_parser.add_argument('run', type=Path)
    review_parser.add_argument('--prefix', required=True, type=Path)
    for child in (observe_parser, review_parser):
        child.add_argument('--binding', required=True, type=Path)
        child.add_argument('--freeze', required=True)
        child.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    reader = Reader()
    require(re.fullmatch('[0-9a-f]{40}', args.freeze), 'exact freeze required')
    result = (observe(args.monitor, args.binding, args.freeze, reader) if args.operation == 'observe'
              else review(args.run, args.prefix, args.freeze, args.binding, reader))
    reader.finish()
    result['bindings'] = reader.bindings
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    return 0 if result['passed'] is True else 1


if __name__ == '__main__':
    raise SystemExit(main())
