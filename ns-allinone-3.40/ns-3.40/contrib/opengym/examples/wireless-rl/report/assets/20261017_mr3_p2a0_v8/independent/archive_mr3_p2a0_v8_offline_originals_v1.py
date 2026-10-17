"""Append original v8 CPU/review evidence without overwriting any canonical bytes."""
from pathlib import Path
import gzip
import hashlib
import json
import shutil

ROOT = Path("/home/zhuyulab/ns3-workspace")
W = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
A = W / "report/assets/20261017_mr3_p2a0_v8"
I = A / "independent"
sha = lambda raw: hashlib.sha256(raw).hexdigest()


def original(path, selected=None, compress=False):
    raw = path.read_bytes()
    destination = selected or I / (path.name + (".gz" if compress else ""))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        encoded = destination.read_bytes()
        decoded = gzip.decompress(encoded) if compress else encoded
        assert decoded == raw, destination
    else:
        encoded = gzip.compress(raw, mtime=0) if compress else raw
        with destination.open("xb") as stream:
            stream.write(encoded)
    assert (gzip.decompress(encoded) if compress else encoded) == raw
    return {"source": str(path), "selected": str(destination.relative_to(A)),
            "encoding": "gzip" if compress else "identity", "raw_bytes": len(raw),
            "raw_sha256": sha(raw), "selected_bytes": len(encoded), "selected_sha256": sha(encoded)}


rows, known = [], set()
settled_path = I / "settled_turn_originals_manifest_v1.json"
settled = json.loads(settled_path.read_text())
for row in settled["files"]:
    encoded = (A / row["selected"]).read_bytes()
    decoded = gzip.decompress(encoded) if row["encoding"] == "gzip" else encoded
    assert sha(encoded) == row["selected_sha256"] and len(encoded) == row["selected_bytes"]
    assert sha(decoded) == row["raw_sha256"] and len(decoded) == row["raw_bytes"]
    assert decoded == Path(row["source"]).read_bytes()
    rows.append(row)
    known.add(row["source"])
sources = list(Path("/tmp").glob("mr3_p2a0_v8*"))
sources += [Path("/tmp") / name for name in (
    "mr3_independent_angular_reset_matrix_v8.py", "mr3_independent_physics_matrix_v8.py",
    "mr3_independent_reset_wrappers_v8_tests.py")]
for path in sorted(set(sources)):
    if not path.is_file() or path.suffix not in (".json", ".py", ".log", ".txt") or str(path) in known:
        continue
    if path.suffix == ".json":
        json.loads(path.read_text())
    selected = None
    if path.name == "mr3_p2a0_v8_plan_launch_tests_v1.py":
        selected = I / "mr3_p2a0_v8_plan_launch_tests_v1_before_final_binding.py"
    row = original(path, selected, path.suffix in (".log", ".txt"))
    rows.append(row)
    known.add(str(path))
rows.append(original(Path(__file__)))
root_checks = []
for receipt in sorted(A.glob("*.json")):
    value = json.loads(receipt.read_text())
    if value.get("schema") != "mr3-p2a0-check-v1":
        continue
    path = A / value["stdout_stderr_gzip"]
    encoded = path.read_bytes()
    raw = gzip.decompress(encoded)
    assert sha(raw) == value["decoded_sha256"], path
    root_checks.append({"receipt": str(receipt.relative_to(A)),
                        "receipt_sha256": sha(receipt.read_bytes()),
                        "stdout": str(path.relative_to(A)), "raw_bytes": len(raw),
                        "raw_sha256": sha(raw), "encoded_bytes": len(encoded),
                        "encoded_sha256": sha(encoded), "exit_code": value["exit_code"],
                        "command": value["command"], "cwd": value["cwd"], "python": value["python"]})
local = []
for path in sorted(I.rglob("*")):
    if not path.is_file() or path.name == "offline_originals_manifest_v1.json":
        continue
    raw = path.read_bytes()
    local.append({"path": str(path.relative_to(A)), "bytes": len(raw), "sha256": sha(raw)})
for row in rows:
    raw = Path(row["source"]).read_bytes()
    encoded = (A / row["selected"]).read_bytes()
    assert sha(raw) == row["raw_sha256"] and len(raw) == row["raw_bytes"]
    assert sha(encoded) == row["selected_sha256"] and len(encoded) == row["selected_bytes"]
    assert (gzip.decompress(encoded) if row["encoding"] == "gzip" else encoded) == raw
payload = {"schema": "mr3-p2a0-v8-offline-originals-v1", "passed": True,
           "files": rows, "root_check_receipts": root_checks,
           "local_original_bindings": local,
           "reused_settled_manifest": {"path": str(settled_path.relative_to(A)),
                                       "sha256": sha(settled_path.read_bytes()), "files": len(settled["files"])},
           "scope": "Original CPU PASS/FAIL, source/counterexample/review scripts and stdout append-only; existing canonical bytes verified and reused, no rewrite. This is an offline-original mapping, not the final prefreeze inventory or native evidence. Historic plan checks remain historic; final v3 plan receipt is separately bound."}
target = I / "offline_originals_manifest_v1.json"
with target.open("x") as stream:
    json.dump(payload, stream, indent=2, allow_nan=False)
    stream.write("\n")
print(json.dumps({"passed": True, "original_mappings": len(rows), "root_checks": len(root_checks),
                  "local_original_files": len(local), "manifest_sha256": sha(target.read_bytes())}))
