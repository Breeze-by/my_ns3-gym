"""Read-only exact pushed source and actual build admission; never builds/runs Gazebo."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v20_sensor'
OLD_A = W / 'report/assets/20261018_mr3_p2a0_v19'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git_raw(freeze, path):
    return subprocess.check_output(['git', 'show', freeze + ':' + str(path)], cwd=ROOT)


def frozen(freeze, binding):
    raw = (ROOT / binding['path']).read_bytes()
    require(sha(raw) == binding['sha256'] and git_raw(freeze, binding['path']) == raw,
            'frozen binding differs: ' + binding['path'])
    return raw


def check_gazebo_executable(freeze, plan):
    witness_path = OLD_A / 'independent/mr3_p2a0_v19_live_admission_v1.py'
    relative = str(witness_path.relative_to(ROOT))
    bindings = [row for row in plan['independent_source_bindings']
                if row['path'] == relative]
    require(len(bindings) == 1, 'corrected live witness must have one frozen source binding')
    frozen(freeze, bindings[0])
    spec = importlib.util.spec_from_file_location('declared_live_witness', witness_path)
    witness = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(witness)
    return witness.declared_gazebo_executable(plan['gazebo_executable'])


def validate_sensor_plan(plan):
    require(plan.get('status') == 'ready' and plan.get('pending') == []
            and plan.get('new_source_bindings_pending') == [], 'sensor plan is not ready')
    require(len(plan['stages']) == 1, 'only one isolated sensor attempt')
    stage = plan['stages'][0]
    require(stage['stage'] == 'iters150' and stage['scene'] == 'open'
            and stage['seed'] == 101 and stage['workers'] == 1
            and stage['steps'] == 4 and stage['domain'] == 170
            and stage['port'] == 13451, 'fixed sensor workload differs')
    require(stage['returned_resets_max'] == 1 and stage['returned_steps_max'] == 4
            and stage['saved_api_records_max'] == 5, 'sensor API ceiling differs')
    budget = plan['budget']
    require(budget['max_native_runs'] == 1 and budget['max_native_launcher_wall_seconds'] == 900.
            and budget['max_saved_api_records'] == 5, 'sensor native budget differs')
    require(budget['previous_v18_v19_charged_wall_seconds'] == 2489.3860735194758
            and budget['cumulative_diagnostic_ceiling_seconds'] == 3600., 'carried budget changed')
    require(plan['e61c_consumer']['status'] == 'SKIP'
            and plan['research_credit']['matrix'] is False
            and plan['research_credit']['physical_repair'] is False, 'capture credit scope changed')
    command = stage['command']
    expected = ['env', 'MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE=' + stage['configuration'],
        '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python', '-m', 'mr3_learning.benchmark',
        '--workers', '1', '--schedule', 'open:101', '--steps', '4',
        '--base-domain', '170', '--base-port', '13451', '--output-root',
        str(ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0'), '--run-id', stage['run_id']]
    require(command == expected, 'must use exact existing ordinary four-step benchmark')
    require(plan['benchmark_interface']['default_action_selector'] == 'probe_action(snapshot,outward_goals=False)',
            'default action selector scope differs')
    require(stage['diagnostic_consumers'][0]['required_original_closure'] is True
            and stage['diagnostic_consumers'][0]['required_capture_success'] is False,
            'physical scientific outcome must remain distinct from required closure')


def check_recorder(freeze, plan):
    value = plan['recorder_contract']
    source = frozen(freeze, {'path': value['source_path'], 'sha256': value['source_sha256']})
    binary = Path(value['executable_path']).read_bytes()
    require(binary.startswith(b'\x7fELF') and len(binary) == value['executable_bytes']
            and sha(binary) == value['executable_sha256'], 'recorder actual ELF identity differs')
    encoded = frozen(freeze, value['archived_binary_binding'])
    require(binary == gzip.decompress(encoded), 'recorder archived ELF differs')
    require(sha(source).encode() in binary, 'recorder compiled source macro absent')
    raw = frozen(freeze, value['config_template_binding'])
    template = json.loads(raw)
    require(template['expected_freeze'] == '{freeze}'
            and template['expected_domain_id'] == 170
            and template['wall_guard_sec'] == 1000, 'recorder config identity/guard differs')
    require(template['run_directory'] == plan['stages'][0]['run_directory'], 'recorder future run differs')
    profile = Path(plan['transport']['FASTRTPS_DEFAULT_PROFILES_FILE']).read_bytes()
    require(sha(profile) == plan['transport']['profile_sha256'], 'DDS loopback profile differs')
    require(value['manifest_schema'] and value['manifest_path'] and value['command'],
            'recorder final output interface unresolved')
    return {'source_path': value['source_path'], 'source_sha256': sha(source),
            'executable_path': value['executable_path'], 'executable_sha256': sha(binary),
            'executable_bytes': len(binary), 'config_template_sha256': sha(raw)}


def check_unused_resources(proc=Path('/proc')):
    """Observe actual sockets/environments; do not bind ports or create DDS."""
    conflicts = []
    # RTPS domain170 well-known block:7400+250*170 .. +249.
    for table in ('tcp', 'tcp6', 'udp', 'udp6'):
        path = proc / 'net' / table
        if not path.exists():
            continue
        for line in path.read_text().splitlines()[1:]:
            fields = line.split()
            port = int(fields[1].rsplit(':', 1)[1], 16)
            if port == 13451 or (table.startswith('udp') and 49900 <= port <= 50149):
                conflicts.append({'table': table, 'local_address': fields[1], 'state': fields[3]})
    domain_owners = []
    for path in proc.glob('[0-9]*/environ'):
        try:
            values = path.read_bytes().split(b'\0')
        except (OSError, ProcessLookupError):
            continue
        if b'ROS_DOMAIN_ID=170' in values:
            domain_owners.append(int(path.parent.name))
    require(not conflicts and not domain_owners, 'domain170 or port13451 already occupied')
    return {'domain_id': 170, 'gazebo_port': 13451, 'socket_conflicts': conflicts,
            'process_environment_domain_owners': domain_owners,
            'scope': 'Read-only point-in-time admission; no socket reservation or DDS participant created.'}


def main():
    freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(subprocess.check_output(['git', 'rev-parse', '@{u}'], cwd=ROOT, text=True).strip() == freeze,
            'HEAD not pushed')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'source not clean')
    plan_path = A / 'predeclared_plan_v20_sensor.json'
    plan_raw = plan_path.read_bytes()
    require(git_raw(freeze, plan_path.relative_to(ROOT)) == plan_raw, 'plan not frozen')
    plan = json.loads(plan_raw)
    validate_sensor_plan(plan)
    for binding in plan['independent_source_bindings']:
        frozen(freeze, binding)
    recorder = check_recorder(freeze, plan)
    unused_resources = check_unused_resources()
    gazebo_executable = check_gazebo_executable(freeze, plan)
    sys.path.insert(0, str(W))
    from mr3_learning.audit_ppo import load_native_gates
    *_, runtime = load_native_gates(ROOT, freeze)
    helper_path = W / 'report/assets/20261017_mr3_p2a0_v17/independent/mr3_p2a0_v17_buildproof_preflight.py'
    spec = importlib.util.spec_from_file_location('old_buildproof', helper_path)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    original = helper.check_binary(plan, freeze)
    shim = helper.check_shim(plan, freeze)
    require(original['library_sha256'] == plan['original_driver']['library_sha256'], 'old driver changed')
    build = json.loads(frozen(freeze, plan['new_diagnostic_build_receipt']))
    require(build['passed'] is True, 'new plugin build/link checks failed')
    libraries = {}
    for name in ('observer', 'profile'):
        value = build['libraries'][name]
        source = frozen(freeze, {'path': value['source_path'], 'sha256': value['source_sha256']})
        library = Path(value['library_path']).read_bytes()
        installed = Path(value['installed_path']).read_bytes()
        encoded = frozen(freeze, {'path': value['archived_library_gzip'],
                                  'sha256': value['archived_library_encoded_sha256']})
        require(library == installed == gzip.decompress(encoded), 'actual/installed/archived new ELF differs')
        require(sha(library) == value['library_sha256'] and len(library) == value['library_bytes'], 'ELF SHA/size differs')
        require(sha(source).encode() in library, 'compiled new source macro absent from actual ELF')
        libraries[name] = value
    for stage in plan['stages']:
        raw = frozen(freeze, stage['configuration_binding'])
        config = json.loads(raw)
        require(config['mode'] == stage['stage'] and config['run_directory'] == stage['run_directory'],
                'config run/profile differs')
        for name in ('observer', 'profile'):
            expected = libraries[name]
            actual = config[name + '_library']
            require(actual == {'path': expected['installed_path'], 'sha256': expected['library_sha256'],
                               'source_sha256': expected['source_sha256']}, 'config library/source differs')
    output = {'passed': True, 'freeze': freeze, 'plan_sha256': sha(plan_raw),
        'source_bindings': runtime, 'independent_source_bindings': plan['independent_source_bindings'],
        'gazebo_executable': gazebo_executable, 'recorder': recorder,
        'unused_resources': unused_resources,
        'binary_build_receipt': plan['drive_contract']['binary_build_receipt'],
        'original_driver_binary': original, 'new_diagnostic_libraries': libraries,
        'new_diagnostic_build_receipt': plan['new_diagnostic_build_receipt'],
        'shim_installed_and_tag_binding': shim,
        'scope': 'source/config/actual ELF admission only; no native or physical response acceptance'}
    destination = Path('/tmp/mr3_p2a0_v20_sensor_source_preflight_v1.json')
    with destination.open('x') as stream:
        stream.write(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'passed': True, 'freeze': freeze, 'runtime_bindings': len(runtime),
                      'independent_bindings': len(plan['independent_source_bindings']),
                      'original_driver': original['library_sha256'],
                      'new_libraries': {name: value['library_sha256'] for name, value in libraries.items()}}))


if __name__ == '__main__':
    main()
