"""Read-only source/build preflight; creates new /tmp v22 receipts, never builds."""
from pathlib import Path
import gzip
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time

ROOT = Path("/home/zhuyulab/ns3-workspace")
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
ASSET = WIRELESS / "report/assets/20261018_mr3_p2a0_v24_install"
LEARNER_PYTHON = Path('/home/zhuyulab/miniconda3/envs/ns3gym/bin/python')
PROBE_PREFIX = Path('/tmp/mr3_p2a0_v24_preflight_learner_entry')
COMPILED = (
    ("compiled_source_sha256", "src/mr3_gazebo_diff_drive.cpp"),
    ("compiled_header_sha256", "include/multi_robot/mr3_gazebo_diff_drive.hpp"),
    ("compiled_helper_sha256", "include/multi_robot/paired_wheel_slew.hpp"),
    ("compiled_target_contract_sha256", "include/multi_robot/mr3_drive_target.hpp"),
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git_bytes(freeze, relative):
    return subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=ROOT)


def check_binary(plan, freeze):
    binding = plan["drive_contract"]["binary_build_receipt"]
    raw = (ROOT / binding["path"]).read_bytes()
    assert sha(raw) == binding["sha256"], "build receipt SHA mismatch"
    assert git_bytes(freeze, binding["path"]) == raw, "build receipt differs from freeze"
    build = json.loads(raw)
    assert build["schema"] == "mr3-drive-binary-build-v1"
    libraries = {}
    for key in ("library_path", "installed_path"):
        path = Path(build[key])
        assert path.is_absolute()
        libraries[key] = path.read_bytes()
        assert sha(libraries[key]) == build["library_sha256"], key + " SHA mismatch"
        assert len(libraries[key]) == build["library_bytes"]
    blob = (ROOT / build["archived_library_gzip"]).read_bytes()
    assert sha(blob) == build["archived_library_encoded_sha256"], "encoded library SHA mismatch"
    assert git_bytes(freeze, build["archived_library_gzip"]) == blob
    assert gzip.decompress(blob) == libraries["library_path"], "archived library differs"
    for field, relative in COMPILED:
        relative = "ros2_ws/ros2-multi-robot-automap/src/multi_robot/" + relative
        raw = git_bytes(freeze, relative)
        assert raw == (ROOT / relative).read_bytes(), "compiled source differs from freeze"
        assert sha(raw) == build[field], field + " differs from unchanged built source"
        assert build[field].encode() in libraries["library_path"], field + " macro missing"
    return {**build, "schema": "mr3-drive-binary-binding-v1", "freeze": freeze}


def check_shim(plan, freeze):
    binding = plan["shim_runtime_custody"]["binding"]
    path = ROOT / binding["path"]
    raw = path.read_bytes()
    assert sha(raw) == binding["sha256"] and git_bytes(freeze, binding["path"]) == raw
    monitor_path = WIRELESS / "report/assets/20261017_mr3_p2a0_v13/independent/mr3_readonly_v13_drive_shim_process_monitor_v2.py"
    spec = importlib.util.spec_from_file_location("shim_monitor", monitor_path)
    monitor = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(monitor)
    return monitor.check_binding(path)


def learner_entry_probe(freeze):
    """Read-only actual conda imports/argparse help; never create an environment."""
    output = Path(str(PROBE_PREFIX) + '_probe_v1.json')
    if output.exists():
        raise ValueError('do not overwrite learner entry probe')
    environment = dict(os.environ, PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
                       CUDA_VISIBLE_DEVICES='')
    environment.pop('PYTHONPATH', None)
    import_code = (
        'import json,sys,gymnasium,torch; print(json.dumps({'
        '"interpreter":sys.executable,"gymnasium":gymnasium.__version__,'
        '"torch":torch.__version__,"gymnasium_file":gymnasium.__file__,'
        '"torch_file":torch.__file__}))')
    commands = [
        ('imports', [str(LEARNER_PYTHON), '-B', '-c', import_code]),
        ('benchmark_help', [str(LEARNER_PYTHON), '-B', '-m', 'mr3_learning.benchmark', '--help']),
        ('full_audit_help', [str(LEARNER_PYTHON), '-B', '-m', 'mr3_learning.audit_preparation', '--help']),
    ]
    records = []
    for label, command in commands:
        stdout = Path(str(PROBE_PREFIX) + '_' + label + '.stdout.log')
        stderr = Path(str(PROBE_PREFIX) + '_' + label + '.stderr.log')
        if stdout.exists() or stderr.exists():
            raise ValueError('do not overwrite learner probe console')
        started = time.monotonic()
        row = {'label': label, 'argv': command, 'cwd': str(WIRELESS), 'returncode': None,
               'stdout': str(stdout), 'stderr': str(stderr), 'passed': False}
        out, err = b'', b''
        try:
            completed = subprocess.run(command, cwd=WIRELESS, env=environment,
                                       capture_output=True, timeout=45)
            row['returncode'] = completed.returncode
            out, err = completed.stdout, completed.stderr
            if label == 'imports':
                details = json.loads(out)
                row['import_details'] = details
                row['passed'] = (completed.returncode == 0 and type(details) is dict
                    and Path(details['interpreter']).resolve(strict=True)
                    == LEARNER_PYTHON.resolve(strict=True)
                    and all(type(details[key]) is str and details[key]
                            for key in ('gymnasium', 'torch', 'gymnasium_file', 'torch_file')))
            else:
                row['passed'] = completed.returncode == 0 and b'usage:' in out
        except subprocess.TimeoutExpired as error:
            out, err = error.stdout or b'', error.stderr or b''
            row['error'] = repr(error)
        except (OSError, ValueError, KeyError, TypeError) as error:
            row['error'] = repr(error)
        with stdout.open('xb') as stream:
            stream.write(out)
        with stderr.open('xb') as stream:
            stream.write(err)
        row.update(wall_seconds=time.monotonic() - started, stdout_sha256=sha(out),
                   stderr_sha256=sha(err))
        records.append(row)
        if row['passed'] is not True:
            break
    result = {'schema': 'mr3-v24-learner-entry-reachability-v1', 'freeze': freeze,
              'passed': len(records) == 3 and all(row['passed'] is True for row in records),
              'outer_interpreter': sys.executable,
              'learner_interpreter': str(LEARNER_PYTHON),
              'learner_resolved': str(LEARNER_PYTHON.resolve()),
              'environment_delta': {'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                                    'CUDA_VISIBLE_DEVICES': '', 'PYTHONPATH': None},
              'commands': records,
              'scope': 'CPU imports and argparse help only; no environment construction, '
                       'GPU API, ROS/DDS, native, policy forward/backward or gate override.'}
    with output.open('x') as stream:
        stream.write(json.dumps(result, indent=2) + '\n')
    if result['passed'] is not True:
        raise ValueError('bound learner entry reachability failed: ' + str(output))
    return {'path': str(output), 'sha256': sha(output.read_bytes()), 'result': result}


def main():
    if "MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE" in os.environ:
        raise ValueError("production matrix forbids diagnostic physics/ray-observer configuration")
    freeze = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert subprocess.check_output(
        ["git", "rev-parse", "@{u}"], cwd=ROOT, text=True).strip() == freeze, "not pushed"
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True), "source not clean"
    plan_path = ASSET / "predeclared_plan_v24.json"
    plan_raw = plan_path.read_bytes()
    assert git_bytes(freeze, str(plan_path.relative_to(ROOT))) == plan_raw
    plan = json.loads(plan_raw)
    assert plan['readiness']['status'] == 'ready' and not plan['readiness']['pending_bindings'], 'V23 template not finalized'
    assert plan["schema"] == "mr3-p2a0-predeclaration-v24"
    assert plan["information_selection_audit"]["status"] == "ready", \
        "information consumer/schema/bindings not frozen"
    assert plan["controlled_execution_audit"]["status"] == "ready", \
        "controlled execution consumer/schema/bindings not frozen"
    assert Path(sys.executable).resolve(strict=True) == LEARNER_PYTHON.resolve(strict=True), \
        "preflight must run with the bound learner Python (audit_ppo imports torch)"
    entry_probe = learner_entry_probe(freeze)
    sys.path.insert(0, str(WIRELESS))
    from mr3_learning.audit_ppo import load_native_gates
    *_, source_proof = load_native_gates(ROOT, freeze)
    for binding in plan["independent_source_bindings"]:
        raw = git_bytes(freeze, binding["path"])
        assert raw == (ROOT / binding["path"]).read_bytes()
        assert sha(raw) == binding["sha256"], binding["path"]
    # The shared production loader has already checked final corrector source,
    # actual ELF/archive/build identity. Also bind the independent runtime witness.
    custody_binding = plan["native_ray_box_correction"]["binding"]
    custody_path = ROOT / custody_binding["path"]
    custody_raw = custody_path.read_bytes()
    assert sha(custody_raw) == custody_binding["sha256"]
    assert git_bytes(freeze, custody_binding["path"]) == custody_raw
    custody_module = WIRELESS / "report/assets/20261018_mr3_p2a0_v24_install/independent/mr3_v24_corrector_custody_v3.py"
    custody_relative = str(custody_module.relative_to(ROOT))
    custody_expected = next(row["sha256"] for row in plan["independent_source_bindings"]
                            if row["path"] == custody_relative)
    custody_source = custody_module.read_bytes()
    assert sha(custody_source) == custody_expected
    spec = importlib.util.spec_from_file_location("v22_corrector_binding_preflight", custody_module)
    custody = importlib.util.module_from_spec(spec)
    exec(compile(custody_source, str(custody_module), "exec"), custody.__dict__)
    custody_reader = custody.Reader()
    corrector = custody.load_binding(custody_path, custody_reader)
    custody_reader.finish()
    binary = check_binary(plan, freeze)
    shim = check_shim(plan, freeze)
    binary_path = Path("/tmp/mr3_p2a0_v24_binaryproof.json")
    output_path = Path("/tmp/mr3_p2a0_v24_source_preflight.json")
    assert not binary_path.exists() and not output_path.exists(), "do not overwrite evidence"
    with binary_path.open("x") as output:
        output.write(json.dumps(binary, indent=2) + "\n")
    result = dict(
        passed=True, freeze=freeze, plan_sha256=sha(plan_raw), source_bindings=source_proof,
        independent_source_bindings=plan["independent_source_bindings"],
        binary_build_receipt=plan["drive_contract"]["binary_build_receipt"],
        binary_proof=str(binary_path), binary_proof_sha256=sha(binary_path.read_bytes()),
        learner_entry_reachability=entry_probe,
        actual_preflight_interpreter=sys.executable,
        shim_installed_and_tag_binding=shim,
        native_corrector_installed_and_source_binding=corrector)
    with output_path.open("x") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(passed=True, freeze=freeze, source_bindings=len(source_proof),
                          independent_bindings=len(plan["independent_source_bindings"]),
                          binary_sha256=binary["library_sha256"])))


if __name__ == "__main__":
    main()
