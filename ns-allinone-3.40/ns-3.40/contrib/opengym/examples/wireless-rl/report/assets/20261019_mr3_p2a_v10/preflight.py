"""Admit one clean pushed V10 freeze; never starts native processes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = next(p for p in HERE.parents if (p / ".git").exists())
W = HERE.parents[2]
sys.path.insert(0, str(W))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trace-physics-output", type=Path)
    parser.add_argument("--binary-proof-output", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("native admission requires clean source")
    freeze = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    pushed = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip()
    if freeze != pushed:
        raise ValueError("native admission requires pushed main")
    plan_path = args.plan.resolve(strict=True)
    raw = plan_path.read_bytes()
    if subprocess.check_output(["git", "show", freeze + ":" + str(plan_path.relative_to(ROOT))], cwd=ROOT) != raw:
        raise ValueError("plan differs from source freeze")
    plan = json.loads(raw)
    if plan["readiness"]["ready"] is not True:
        raise ValueError("plan is not ready")
    for name, expected in plan["source_bindings"].items():
        path = ROOT / name
        if sha(path) != expected or subprocess.check_output(["git", "show", freeze + ":" + name], cwd=ROOT) != path.read_bytes():
            raise ValueError("source binding differs: " + name)
    for name, expected in plan["library_bindings"].items():
        if sha(name) != expected:
            raise ValueError("library binding differs: " + name)
    from mr3_learning import audit_ppo, native_custody
    identity = native_custody.verify_binding(ROOT, freeze, HERE / "native_custody_binding.json")
    _, _, _, _, _, proof = audit_ppo.load_native_gates(ROOT, freeze)
    driver = identity['binaries']['driver']
    binary_proof = {'schema': 'mr3-drive-binary-binding-v1', 'freeze': freeze,
                    'library_path': driver['resolved_path'], 'installed_path': driver['path'],
                    'library_sha256': driver['sha256'], 'library_bytes': driver['bytes'],
                    **{key: value['sha256'] for key, value in identity['compiled_sources']['driver'].items()},
                    'build_receipt': str(HERE / 'checks/v9_build.json'),
                    'scope': 'Actual current compiled source/ELF; loaded custody and physical gates separate'}
    with args.binary_proof_output.open('x') as stream:
        json.dump(binary_proof, stream, indent=2)
        stream.write('\n')
    config = None
    if args.trace_physics_output:
        observer = identity["binaries"]["observer"]
        trace = plan["trace"]
        run = Path(trace["run_directory"])
        if run.exists():
            raise FileExistsError("single-opportunity trace already exists")
        config = {"schema": "mr3-physics-diagnostic-config-v2", "mode": "observer_only",
                  "run_directory": str(run), "episode_relative_directory": "worker0/episode001_open_101",
                  "scene": "open", "seed": 101, "capture_start_ns": 0,
                  "capture_end_ns": 300000000000,
                  "observer_library": {"path": observer["path"], "sha256": observer["sha256"],
                      "source_sha256": identity["compiled_sources"]["observer"]["compiled_source_sha256"]["sha256"]}}
        with args.trace_physics_output.open("x") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
        config = {"path": str(args.trace_physics_output), "sha256": sha(args.trace_physics_output)}
    result = {"schema": "mr3-p2a-v10-preflight-v1", "passed": True, "freeze": freeze,
              "plan_sha256": hashlib.sha256(raw).hexdigest(), "plan_path": str(plan_path),
              "wall_monotonic_ns": time.monotonic_ns(), "native_identity": identity,
              "native_source_proof": proof, "trace_physics_config": config,
              "drive_binary_proof": {"path": str(args.binary_proof_output), "sha256": sha(args.binary_proof_output)},
              "scope": "source/build/file admission only; native science and loaded custody are separate"}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": True, "freeze": freeze, "output": str(args.output)}))


if __name__ == "__main__":
    main()
