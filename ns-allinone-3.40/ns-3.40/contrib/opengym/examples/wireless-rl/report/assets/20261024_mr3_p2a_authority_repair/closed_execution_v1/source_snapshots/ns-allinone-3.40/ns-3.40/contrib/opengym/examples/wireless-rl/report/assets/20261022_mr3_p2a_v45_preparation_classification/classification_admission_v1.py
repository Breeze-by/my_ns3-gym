"""Bind successful artificial classification checks to their exact current sources."""
import hashlib
from pathlib import Path

A = Path(__file__).resolve().parent
ROOT = Path("/home/zhuyulab/ns3-workspace")
PYTHON = "/home/zhuyulab/miniconda3/envs/ns3gym/bin/python"

def verify(inputs, verify_wait):
    wait_path = A / "checks/classification_cpu_v2/actual_wait.json"
    recovery_path = A / "checks/classification_cpu_v2_source_recovery.json"
    import json
    value = json.loads(inputs.read(wait_path))
    verify_wait(value)
    if value["actual_argv"] != [PYTHON,"-B","-m","pytest","-q",str(A/"test_preparation_classification_v1.py")]:
        raise ValueError("classification receipt has a different actual command")
    inputs.bound(value["console"])
    recovery = json.loads(inputs.read(recovery_path))
    original = {row["path"]:row for row in recovery["sources"]}
    before = {row["path"]:row for row in value["source_before"]}
    required = ("prepare_plan_v1.py", "preflight_v1.py", "cpu_driver_v1.py",
                "test_preparation_classification_v1.py", "classification_admission_v1.py")
    tested = []
    for name in required:
        path = A / name
        expected = before[str(path)]
        raw = inputs.read(path)
        if hashlib.sha256(raw).hexdigest() != expected["sha256"] or len(raw) != expected["bytes"]:
            raise ValueError("classification-tested admission source differs: " + name)
        if original[str(path.relative_to(ROOT))]["sha256"] != expected["sha256"]:
            raise ValueError("classification source recovery differs: " + name)
        tested.append(inputs.spec(path))
    return {"schema":"mr3-v45-classification-regression-admission-v1", "passed":True,
            "actual_wait":inputs.spec(wait_path), "source_recovery":inputs.spec(recovery_path),
            "tested_current_admission_sources":tested, "world_or_native_credit":False}

