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
A = W / 'report/assets/20261018_mr3_p2a0_v18'


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


def main():
    freeze = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    require(subprocess.check_output(['git', 'rev-parse', '@{u}'], cwd=ROOT, text=True).strip() == freeze,
            'HEAD not pushed')
    require(not subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT), 'source not clean')
    plan_path = A / 'predeclared_plan_v18.json'
    plan_raw = plan_path.read_bytes()
    require(git_raw(freeze, plan_path.relative_to(ROOT)) == plan_raw, 'plan not frozen')
    plan = json.loads(plan_raw)
    require(plan['status'] == 'ready' and plan['pending'] == [], 'plan not ready')
    for binding in plan['independent_source_bindings']:
        frozen(freeze, binding)
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
        'binary_build_receipt': plan['drive_contract']['binary_build_receipt'],
        'original_driver_binary': original, 'new_diagnostic_libraries': libraries,
        'new_diagnostic_build_receipt': plan['new_diagnostic_build_receipt'],
        'shim_installed_and_tag_binding': shim,
        'scope': 'source/config/actual ELF admission only; no native or physical response acceptance'}
    destination = Path('/tmp/mr3_p2a0_v18_source_preflight.json')
    with destination.open('x') as stream:
        stream.write(json.dumps(output, indent=2) + '\n')
    print(json.dumps({'passed': True, 'freeze': freeze, 'runtime_bindings': len(runtime),
                      'independent_bindings': len(plan['independent_source_bindings']),
                      'original_driver': original['library_sha256'],
                      'new_libraries': {name: value['library_sha256'] for name, value in libraries.items()}}))


if __name__ == '__main__':
    main()
