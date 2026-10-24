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
A = W / 'report/assets/20261018_mr3_p2a0_v21_ray'
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
    witness_path = A / 'independent/mr3_p2a0_v21_ray_live_admission_v1.py'
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
            and stage['steps'] == 4 and stage['domain'] == 174
            and stage['port'] == 13471, 'fixed sensor workload differs')
    require(stage['returned_resets_max'] == 1 and stage['returned_steps_max'] == 4
            and stage['saved_api_records_max'] == 5, 'sensor API ceiling differs')
    budget = plan['budget']
    require(budget['max_native_runs'] == 1 and budget['max_native_launcher_wall_seconds'] == 350.
            and budget['max_saved_api_records'] == 5, 'sensor native budget differs')
    require(budget['previous_v18_v19_v20_charged_wall_seconds'] == 2718.6609461181798
            and budget['cumulative_diagnostic_ceiling_seconds'] == 3600., 'carried budget changed')
    require(plan['e61c_consumer']['status'] == 'SKIP'
            and plan['research_credit']['matrix'] is False
            and plan['research_credit']['physical_repair'] is False, 'capture credit scope changed')
    command = stage['command']
    expected = ['env', 'MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE=' + stage['configuration'],
        '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python', '-m', 'mr3_learning.benchmark',
        '--workers', '1', '--schedule', 'open:101', '--steps', '4',
        '--base-domain', '174', '--base-port', '13471', '--output-root',
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
            and template['expected_domain_id'] == 174
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
    # RTPS domain174 well-known block:7400+250*174 .. +249.
    for table in ('tcp', 'tcp6', 'udp', 'udp6'):
        path = proc / 'net' / table
        if not path.exists():
            continue
        for line in path.read_text().splitlines()[1:]:
            fields = line.split()
            port = int(fields[1].rsplit(':', 1)[1], 16)
            if port == 13471 or (table.startswith('udp') and 50900 <= port <= 51149):
                conflicts.append({'table': table, 'local_address': fields[1], 'state': fields[3]})
    domain_owners = []
    for path in proc.glob('[0-9]*/environ'):
        try:
            values = path.read_bytes().split(b'\0')
        except (OSError, ProcessLookupError):
            continue
        if b'ROS_DOMAIN_ID=174' in values:
            domain_owners.append(int(path.parent.name))
    require(not conflicts and not domain_owners, 'domain174 or port13471 already occupied')
    return {'domain_id': 174, 'gazebo_port': 13471, 'socket_conflicts': conflicts,
            'process_environment_domain_owners': domain_owners,
            'scope': 'Read-only point-in-time admission; no socket reservation or DDS participant created.'}



def check_ray(freeze, plan, configuration):
    expected = plan['ray_library']
    fixed = ROOT/'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_ray_provenance_observer.so'
    require(expected['installed_path'] == str(fixed) and expected['plugin_type'] == 'SensorPlugin',
            'only fixed SensorPlugin target permitted')
    source = frozen(freeze, {'path': expected['source_path'], 'sha256': expected['source_sha256']})
    actual = fixed.read_bytes()
    require(actual.startswith(b'\x7fELF') and sha(actual) == expected['library_sha256']
            and len(actual) == expected['library_bytes']
            and str(fixed.resolve(strict=True)) == expected['installed_resolved_path'],
            'actual ray SensorPlugin ELF/path differs')
    encoded = frozen(freeze, expected['archived_library_binding'])
    require(gzip.decompress(encoded) == actual and sha(source).encode() in actual,
            'ray archive/compiled source differs')
    receipt = json.loads(frozen(freeze, plan['ray_build_receipt']))
    require(receipt['passed'] is True
            and receipt['source_after']['sha256'] == expected['source_sha256']
            and receipt['installed_new_library'] == {
                'path': str(fixed), 'resolved': expected['installed_resolved_path'],
                'bytes': expected['library_bytes'], 'sha256': expected['library_sha256']},
            'ray canonical build receipt source/actual ELF differs')
    custody = json.loads(frozen(freeze, plan['ray_binary_receipt_binding']))
    require(custody['decoded_sha256'] == sha(actual) and custody['decoded_bytes'] == len(actual)
            and custody['encoded_sha256'] == sha(encoded)
            and custody['source_cpp_sha256'] == expected['source_sha256'],
            'ray binary custody receipt differs')
    require(configuration['capture_start_ns'] == 0 and configuration['capture_end_ns'] == 1000000,
            'old observer measurement window must be explicitly one millisecond')
    require(configuration['ray_provenance'] == {
        'enabled': True, 'library': str(fixed), 'source_sha256': expected['source_sha256'],
        'library_sha256': expected['library_sha256'], 'start_ns': 0, 'end_ns': 300000000000,
        'sensor_link': 'base_scan', 'sensor_name': 'hls_lfcd_lds'}, 'fixed ray config differs')
    return {'source_sha256': sha(source), 'actual_elf_sha256': sha(actual),
            'actual_elf_bytes': len(actual), 'plugin_type': 'SensorPlugin',
            'scope': 'Source/archive/actual ELF identity only; live mapped Load evidence still required.'}


# Fixed V21 diagnostic-only runtime delta. No caller-supplied override map.
RAY_NORMATIVE_FREEZE = '4f8bd0e509e6f958c5993a50008955afac72c345'
RAY_EXECUTION_DELTAS = {
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt': (
        '7ebe737cdec686b08b02702846ca27998d1f67e9f1070979fa9123bfd6ea08b7',
        '170eb49947c4daa61d30f45ab8fde637aa12766182dddfda15c9ca6453d0cc0d'),
    'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py': (
        'bcb177d669890ecd6f552379afad771656b6b748c314ea158e5599d37a0c3d2b',
        '6c76a4f0afbeb4c26f8c28b8e1139bbd12e5162a54ca3a193b99a156ef47a2d2')}
RAY_CMAKE_ADDITION = '# Opt-in ray provenance SensorPlugin; original targets/sources/flags unchanged.\nset(mr3_ray_provenance_source ${CMAKE_CURRENT_SOURCE_DIR}/src/mr3_ray_provenance_observer.cpp)\nset_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS ${mr3_ray_provenance_source})\nfile(SHA256 ${mr3_ray_provenance_source} mr3_ray_provenance_source_sha)\nadd_library(mr3_ray_provenance_observer SHARED src/mr3_ray_provenance_observer.cpp)\ntarget_compile_features(mr3_ray_provenance_observer PRIVATE cxx_std_17)\ntarget_include_directories(mr3_ray_provenance_observer PRIVATE ${GAZEBO_INCLUDE_DIRS})\ntarget_link_libraries(mr3_ray_provenance_observer ${GAZEBO_LIBRARIES}\n  nlohmann_json::nlohmann_json ${CMAKE_DL_LIBS})\ntarget_compile_definitions(mr3_ray_provenance_observer PRIVATE\n  MR3_RAY_PROVENANCE_SOURCE_SHA256="${mr3_ray_provenance_source_sha}")\ninstall(TARGETS mr3_ray_provenance_observer DESTINATION lib)\n\n'


def project_ray_runtime(relative, current):
    """Remove only the fixed opt-in SensorPlugin target/config/injection additions."""
    text = current.decode()
    if relative.endswith('/CMakeLists.txt'):
        require(text.count(RAY_CMAKE_ADDITION) == 1, 'ray target addition differs')
        return text.replace(RAY_CMAKE_ADDITION, '', 1).encode()
    def replace_once(text, added, original=''):
        require(text.count(added) == 1, 'ray launch inverse marker differs')
        return text.replace(added, original, 1)
    text = replace_once(text, 'import xml.etree.ElementTree as ET\n')
    text = replace_once(text,
        '    if (type(config) is not dict or set(config) not in (expected, expected | {"ray_provenance"}) or\n',
        '    if (type(config) is not dict or set(config) != expected or\n')
    start = text.index('    ray = None\n')
    end = text.index('    world_path = Path(world).resolve(strict=True)\n', start)
    text = text[:start] + text[end:]
    text = replace_once(text, '    if ray is not None:\n        binding["ray_provenance"] = ray\n')
    start = text.index('def append_ray_provenance(')
    end = text.index('def drive_spawn_model(', start)
    text = text[:start] + text[end:]
    text = replace_once(text, '        model = append_ray_provenance(model, robot_name, physics_diagnostic)\n')
    return text.encode()


def load_native_gates_with_ray(freeze):
    """Fixed two-file source projection; all other original pins/math remain active."""
    from mr3_learning import audit_ppo
    auditor_path = 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/audit_ppo.py'
    frozen(freeze, {'path': auditor_path,
        'sha256': 'f42e727156369ddb3447f385451dfcdfd777ae2fb8e03c78397a4c356258a7da'})
    previous = audit_ppo.EXECUTION_CONFIG_PINS
    original = dict(previous)
    adjusted = dict(previous)
    proof = {'schema': 'mr3-v21-ray-runtime-config-projection-v1',
             'normative_freeze': RAY_NORMATIVE_FREEZE, 'files': {},
             'old_auditor_source_unchanged': True,
             'scope': 'Actual two-file ray diagnostic increment explicitly versioned; not original raw execution-config pin identity. All other original runtime/task/actor/math gates retained.'}
    for relative, (old_sha, new_sha) in RAY_EXECUTION_DELTAS.items():
        require(previous.get(relative) == old_sha, 'original execution pin differs')
        current = frozen(freeze, {'path': relative, 'sha256': new_sha})
        normative = git_raw(RAY_NORMATIVE_FREEZE, relative)
        require(sha(normative) == old_sha, 'normative source bytes differ')
        projected = project_ray_runtime(relative, current)
        require(projected == normative, 'ray inverse did not restore normative whole bytes')
        adjusted[relative] = new_sha
        proof['files'][relative] = {'actual_sha256': new_sha, 'normative_sha256': old_sha,
            'actual_git_source': freeze + ':' + relative,
            'normative_git_source': RAY_NORMATIVE_FREEZE + ':' + relative,
            'strict_inverse_whole_bytes_equal': True}
    try:
        audit_ppo.EXECUTION_CONFIG_PINS = adjusted
        result = audit_ppo.load_native_gates(ROOT, freeze)
    finally:
        audit_ppo.EXECUTION_CONFIG_PINS = previous
    require(previous == original, 'original execution pins unexpectedly mutated')
    proof['original_pin_dict_restored'] = True
    return result, proof

def main():
    freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(subprocess.check_output(['git', 'rev-parse', '@{u}'], cwd=ROOT, text=True).strip() == freeze,
            'HEAD not pushed')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'source not clean')
    plan_path = A / 'predeclared_plan_v21_ray.json'
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
    native_gates, ray_runtime_projection = load_native_gates_with_ray(freeze)
    *_, runtime = native_gates
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
    ray_libraries = {}
    for stage in plan['stages']:
        raw = frozen(freeze, stage['configuration_binding'])
        config = json.loads(raw)
        require(config['mode'] == stage['stage'] and config['run_directory'] == stage['run_directory'],
                'config run/profile differs')
        ray_libraries[stage['stage']] = check_ray(freeze, plan, config)
        for name in ('observer', 'profile'):
            expected = libraries[name]
            actual = config[name + '_library']
            require(actual == {'path': expected['installed_path'], 'sha256': expected['library_sha256'],
                               'source_sha256': expected['source_sha256']}, 'config library/source differs')
    output = {'passed': True, 'freeze': freeze, 'plan_sha256': sha(plan_raw),
        'source_bindings': runtime, 'ray_runtime_config_projection': ray_runtime_projection,
        'independent_source_bindings': plan['independent_source_bindings'],
        'gazebo_executable': gazebo_executable, 'recorder': recorder,
        'unused_resources': unused_resources,
        'binary_build_receipt': plan['drive_contract']['binary_build_receipt'],
        'original_driver_binary': original, 'new_diagnostic_libraries': libraries,
        'new_diagnostic_build_receipt': plan['new_diagnostic_build_receipt'],
        'ray_library': ray_libraries,
        'shim_installed_and_tag_binding': shim,
        'scope': 'source/config/actual ELF admission only; no native or physical response acceptance'}
    destination = Path('/tmp/mr3_p2a0_v21_ray_source_preflight_v1.json')
    with destination.open('x') as stream:
        stream.write(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'passed': True, 'freeze': freeze, 'runtime_bindings': len(runtime),
                      'independent_bindings': len(plan['independent_source_bindings']),
                      'original_driver': original['library_sha256'],
                      'new_libraries': {name: value['library_sha256'] for name, value in libraries.items()}}))


if __name__ == '__main__':
    main()
