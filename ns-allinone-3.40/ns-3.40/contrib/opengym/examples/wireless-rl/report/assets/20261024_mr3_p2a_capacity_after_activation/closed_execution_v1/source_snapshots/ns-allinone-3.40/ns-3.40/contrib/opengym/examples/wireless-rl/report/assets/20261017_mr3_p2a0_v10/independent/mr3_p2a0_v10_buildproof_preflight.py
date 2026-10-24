"""Read-only source/build preflight; creates new /tmp v10 receipts, never builds."""
from pathlib import Path
import gzip
import hashlib
import json
import subprocess
import sys

ROOT = Path("/home/zhuyulab/ns3-workspace")
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
ASSET = WIRELESS / "report/assets/20261017_mr3_p2a0_v10"
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


def main():
    freeze = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert subprocess.check_output(
        ["git", "rev-parse", "@{u}"], cwd=ROOT, text=True).strip() == freeze, "not pushed"
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True), "source not clean"
    plan_path = ASSET / "predeclared_plan_v10.json"
    plan_raw = plan_path.read_bytes()
    assert git_bytes(freeze, str(plan_path.relative_to(ROOT))) == plan_raw
    plan = json.loads(plan_raw)
    assert plan["schema"] == "mr3-p2a0-predeclaration-v10"
    assert plan["information_selection_audit"]["status"] == "ready", \
        "information consumer/schema/bindings not frozen"
    assert plan["controlled_execution_audit"]["status"] == "ready", \
        "controlled execution consumer/schema/bindings not frozen"
    sys.path.insert(0, str(WIRELESS))
    from mr3_learning.audit_ppo import load_native_gates
    *_, source_proof = load_native_gates(ROOT, freeze)
    for binding in plan["independent_source_bindings"]:
        raw = git_bytes(freeze, binding["path"])
        assert raw == (ROOT / binding["path"]).read_bytes()
        assert sha(raw) == binding["sha256"], binding["path"]
    binary = check_binary(plan, freeze)
    binary_path = Path("/tmp/mr3_p2a0_v10_binaryproof.json")
    output_path = Path("/tmp/mr3_p2a0_v10_source_preflight.json")
    assert not binary_path.exists() and not output_path.exists(), "do not overwrite evidence"
    with binary_path.open("x") as output:
        output.write(json.dumps(binary, indent=2) + "\n")
    result = dict(
        passed=True, freeze=freeze, plan_sha256=sha(plan_raw), source_bindings=source_proof,
        independent_source_bindings=plan["independent_source_bindings"],
        binary_build_receipt=plan["drive_contract"]["binary_build_receipt"],
        binary_proof=str(binary_path), binary_proof_sha256=sha(binary_path.read_bytes()))
    with output_path.open("x") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(dict(passed=True, freeze=freeze, source_bindings=len(source_proof),
                          independent_bindings=len(plan["independent_source_bindings"]),
                          binary_sha256=binary["library_sha256"])))


if __name__ == "__main__":
    main()
