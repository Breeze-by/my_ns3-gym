"""Seal original successful artificial checks; never execute a simulator."""
import hashlib
import json
from pathlib import Path
from . import prepare_plan_v1 as preparing

A = Path(__file__).resolve().parent

def proof(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

def main():
    entries = []
    for name, (wait_path, recovery_path) in preparing.CPU_INPUTS.items():
        value = preparing.decode(wait_path.read_bytes())
        preparing.verify_wait(value)
        entries.append({"id": name, "actual_wait": proof(wait_path),
                        "source_recovery": proof(recovery_path)})
    target = A / "cpu_validation_index_v1.json"
    with target.open("x") as stream:
        json.dump({"schema": "mr3-p2a-v44-cpu-validation-index-v1",
                   "purpose": "Artificial CPU/import/source checks only; no native/plant/PPO credit.",
                   "engineering_seconds": "0", "entries": entries}, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"index": str(target), "entries": len(entries)}))

if __name__ == "__main__":
    main()
