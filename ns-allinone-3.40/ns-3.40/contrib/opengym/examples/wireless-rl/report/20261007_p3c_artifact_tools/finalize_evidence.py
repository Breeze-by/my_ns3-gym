"""Read-only final evidence checks and explicit copies of derived P3C artifacts.

Run from any cwd with ns3gym Python and PYTHONNOUSERSITE=1. Raw task files
and user materials are only read. This script updates the named derived report.
"""

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[8]
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
REPORT = Path(__file__).resolve().parents[1]
LOG = ROS / "log/p3c"
TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(ROS / "src/multi_robot_exploration"))
from multi_robot_exploration.metrics_io import flatten
from multi_robot_exploration.gateway_metrics import validate_pair_configuration


def load(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_record(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": sha(path)}


gate = load(LOG / "v11_gate.json")
assert gate["status"] == "PASS"
protected = load(LOG / "pre_freeze/user_materials_sha256.json")
assert all(sha(ROOT / path) == value for path, value in protected.items())
replay = load(LOG / "v7_accepted_replay/summary.json")
originals = replay["audits"]
assert len(originals) == 63
for audit in originals:
    for kind in ("result", "ledger"):
        assert sha(audit[f"{kind}_path"]) == audit[f"{kind}_sha256"]
for pair in replay["pairs"]:
    if "comparison" in pair:
        validate_pair_configuration(load(LOG / "v7_accepted_replay" / pair["fault"] / "curves/summary.json"),
                                    load(LOG / "v7_accepted_replay" / pair["ideal"] / "curves/summary.json"))

csv_checks, manifests = {}, []
for episode in gate["episodes"]:
    directory = Path(episode["manifest"]).parent
    manifests.append(load(episode["manifest"]))
    assert sha(directory / "ledger.jsonl") == episode["ledger_sha256"]
    result = Path(load(directory / "summary.json")["result_path"])
    assert sha(result) == episode["result_sha256"]
    metrics = directory / "ledger_metrics"
    with (metrics / "windows.csv").open() as stream:
        actual = list(csv.DictReader(stream))
    expected = [flatten(json.loads(line)) for line in (metrics / "windows.jsonl").read_text().splitlines()]
    assert len(actual) == len(expected)
    for index, (left, right) in enumerate(zip(actual, expected)):
        for key, value in right.items():
            serialized = "" if value is None else str(value)
            assert left[key] == serialized, (episode["case"], index, key)
    csv_checks[episode["case"]] = {"status": "PASS", "rows": len(actual),
                                   "csv": file_record(metrics / "windows.csv"),
                                   "jsonl": file_record(metrics / "windows.jsonl")}
assert sum(item["rows"] for item in csv_checks.values()) == 26852

owned = []
for path in Path("/proc").iterdir():
    if not path.name.isdigit():
        continue
    try:
        environment = path.joinpath("environ").read_bytes().split(b"\0")
        commands = path.joinpath("cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except (FileNotFoundError, PermissionError, ProcessLookupError):
        continue
    if any(f"ROS_DOMAIN_ID={domain}".encode() in environment for domain in (190, 195, 196, 197)) or any(
            f"GAZEBO_MASTER_URI=http://127.0.0.1:{port}".encode() in environment for port in (19820, 19821, 19822)):
        owned.append({"pid": int(path.name), "command": commands})
assert not owned, owned

source, runtime = load(LOG / "v13_source.json"), load(LOG / "v13_runtime/checks.json")
assert source["status"] == runtime["status"] == "PASS"
checks = TOOLS / "checks"
checks.mkdir(exist_ok=True)
for name in ("p3c_v1_build.txt", "p3c_v1_components.txt", "p3c_v3_build.txt", "p3c_v3_targeted.txt",
             "p3c_v4_replay.txt", "p3c_v5_replay.txt", "p3c_v5_source.txt", "p3c_v6_replay.txt",
             "p3c_v6_build.txt", "p3c_v6_components.txt", "p3c_v7_replay.txt",
             "p3c_v7_ideal_owner.txt", "p3c_v7_forced_owner.txt", "p3c_v7_dynamic_owner.txt",
             "p3c_v8_gate_initial.txt", "p3c_v8_gate_final.txt", "p3c_v8_figures.txt",
             "p3c_v10_build.txt", "p3c_v10_figures.txt", "p3c_v11_components.txt", "p3c_v11_gate.txt",
             "p3c_v11_full_dynamic.txt", "p3c_v12_full_dynamic.txt", "p3c_v10_full_ideal.txt",
             "p3c_v12_source.txt", "p3c_v13_runtime.txt", "p3c_v13_source.txt",
             "p3c_v13_targeted.txt", "p3c_v13_build.txt", "p3c_v12_targeted.txt"):
    shutil.copyfile(Path("/tmp") / name, checks / name)
for name in ("monitor", "details", "console"):
    shutil.copyfile(LOG / "v13_runtime" / f"{name}.png", REPORT / f"20261007_p3c_{name}.png")
shutil.copyfile("/tmp/plot_p3c_results.py", TOOLS / "plot_p3c_results.py")

old_gate = REPORT / "20261007_p3c_gate.json"
if not (LOG / "v8_gate.json").exists():
    shutil.copyfile(old_gate, LOG / "v8_gate.json")
gate["final_verification"] = {"source_audit": source, "runtime_probe": runtime, "csv_json": csv_checks,
                              "component_checks": 676, "component_wall_sec": 17.05,
                              "four_package_build_wall_sec": 5.62, "final_related_checks": 26, "final_related_wall_sec": .51,
                              "user_files_unchanged": len(protected), "owned_processes_remaining": owned,
                              "full_reconstruction_pair": load(LOG / "v12_full_replay/dynamic/comparison.json"),
                              "qualification": "post-task display/export/pair-validation refinements; no task rerun"}
old_gate.write_text(json.dumps(gate, indent=2, sort_keys=True, allow_nan=False)+"\n")

sources = [path for path in (ROS / "src/multi_robot_exploration/multi_robot_exploration").glob("*.py")
           if path.name in ("gateway_metrics.py", "gateway_panel.py", "metrics_node.py", "metrics_io.py", "gateway_config.py",
                            "fault_model.py", "ideal_gateway.py", "navigation_gateway.py")]
sources += [ROS / "scripts" / name for name in ("export_gateway_metrics.py", "check_p3c_gate.py", "check_p3c_source.py",
            "check_p3c_runtime.py", "audit_p3c_evidence.py", "run_p3c_integration.py", "gateway_configure.py",
            "p3c_integration_manifest.json")]
artifacts = [path for path in REPORT.glob("20261007_p3c_*") if path.is_file() and path.suffix in (".png", ".md")]
artifacts += list(checks.iterdir()) + list(TOOLS.glob("*.py")) + [old_gate]
provenance = {"status": "PASS", "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "task_frozen_commit": gate["frozen_commit"], "original_manifests": manifests,
              "original_63_unchanged": originals, "protected_user_files_unchanged": protected,
              "csv_json_checks": csv_checks, "owned_domains": [190, 195, 196, 197],
              "owned_processes_remaining": owned, "current_sources": [file_record(p) for p in sources],
              "artifacts": [file_record(p) for p in sorted(artifacts)],
              "gate_checks": [file_record(LOG / name) for name in ("v8_gate.json", "v11_gate.json", "v13_source.json", "v13_runtime/checks.json")],
              "limits": gate["limits"]}
(REPORT / "20261007_p3c_provenance.json").write_text(json.dumps(provenance, indent=2, sort_keys=True, allow_nan=False)+"\n")
print(json.dumps({"status": "PASS", "protected": len(protected), "originals": len(originals),
                  "csv_rows": sum(c["rows"] for c in csv_checks.values()), "owned_processes": len(owned)}))
