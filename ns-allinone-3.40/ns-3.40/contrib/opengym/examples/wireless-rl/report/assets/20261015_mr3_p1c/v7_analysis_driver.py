#!/usr/bin/env python3
"""Prepare, or explicitly execute after closure, the two v7 offline analyses.

The default prints commands only and reads no run results. --execute is for
root-authorized final analysis after all eight native stages have closed. This
does not launch ROS, a simulator, GPU work or training, and never edits bindings.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import time


FREEZE = "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ASSETS = WIRELESS + "report/assets/20261015_mr3_p1c/"
ROS = "ros2_ws/ros2-multi-robot-automap/"
CHECKS_SHA = "5aa211fb00ffbd2170510f2f8f9c169cbb53bf52315fc4e70602b2857bee90a8"
FIXED = {
    "resource_analysis_v2.py":
        "f92b7a9c4f3ec1e06c423d846d810b6f0799bdf08e7c44ba27b507d155b24fdf",
    "reset_analysis_v7.py":
        "7975b917c99d2656962c0620fba273750b55ac905e96583ba2326e479b7f03d3",
    "v7_execution_driver.py":
        "25c1e2a5bf83f5e3aa2fe34c1fc1781e460f44f27bb9917462b213ceb1a04e27",
    "implementation_checks_v7.json": CHECKS_SHA,
}
STAGES = ("clock", "pilot", "terminal", "workers1", "workers2", "workers4", "fault", "deadline")
GROUPS = STAGES[1:]


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def commands(root):
    assets = root / ASSETS
    prefix = ["rtk", "proxy", "env", "PYTHONNOUSERSITE=1", "/usr/bin/python3", "-B"]
    directories = [root / ROS / "log/mr3_learning" / ("mr3_p1c_v7_" + name)
                   for name in GROUPS]
    resource = [*prefix, str(assets / "resource_analysis_v2.py"),
                *(str(path) for path in directories), "--output",
                str(assets / "resource_analysis_v7.json")]
    reset = [*prefix, str(assets / "reset_analysis_v7.py"), "--freeze", FREEZE,
             "--implementation-checks", str(assets / "implementation_checks_v7.json"),
             "--implementation-checks-sha256", CHECKS_SHA, "--native-root",
             str(assets / "native_v7"), "--output", str(assets / "reset_summary_v7.json")]
    return directories, [("resource", resource), ("reset", reset)]


def closed_execution(journal, matrix):
    """Read only after authorization; a partial live journal never admits analysis."""
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    require(rows and all(row.get("freeze") == FREEZE for row in rows),
            "execution journal missing or cross-freeze")
    require(not any(row.get("kind") in ("stopped_after_failure", "command_interrupted_or_failed")
                    for row in rows), "execution did not complete cleanly")
    native = [row for row in rows if row.get("kind") == "command_complete"
              and row.get("role") == "native"]
    require([row.get("stage") for row in native] == list(STAGES)
            and all(row.get("returncode") == 0 for row in native),
            "eight successful native exits are not recorded")
    gates = [row.get("stage") for row in rows
             if row.get("kind") == "stage_all_declared_gates_passed"]
    require(gates == list(GROUPS), "phase3/scalar stage gates incomplete")
    final = rows[-1]
    require(final.get("kind") == "all_eight_stages_and_declared_audits_complete"
            and final.get("matrix_sha256") == sha(matrix), "final matrix closure marker missing")
    result = read(matrix)
    require(result.get("passed") is True and result.get("errors") == []
            and result.get("offline_contact_phase_audit", {}).get("freeze") == FREEZE
            and len(result.get("benchmarks", [])) == 6, "final same-freeze matrix audit failed")
    return {"journal_sha256": sha(journal), "matrix_sha256": sha(matrix),
            "scope": "recorded driver closure; separate final PID/evidence audit still required"}


def resource_gate(value, directories):
    require(value.get("freezes") == [FREEZE] and value.get("mixed_freeze_warning") is False,
            "resource analysis contains another runtime freeze")
    rows = value.get("benchmarks", [])
    require(len(rows) == 7 and all(row.get("summary_passed") is True for row in rows)
            and {Path(row["directory"]).resolve() for row in rows} ==
            {path.resolve() for path in directories}, "resource benchmark scope differs")
    for row in rows:
        name = Path(row["directory"]).name.removeprefix("mr3_p1c_v7_")
        comparison = row["fair_comparison"]
        expected = {"workers1": 32, "workers2": 64, "workers4": 128}
        if name in expected:
            require(comparison.get("eligible") is True
                    and comparison.get("transitions") == expected[name]
                    and comparison.get("denominator_wall_sec", 0) > 0,
                    "fair normal first-two-cell comparison differs")
        else:
            require(comparison.get("eligible") is False, "diagnostic entered fair throughput")


def execute(root, binding_sha):
    assets = root / ASSETS
    directories, jobs = commands(root)
    outputs = [assets / "resource_analysis_v7.json", assets / "reset_summary_v7.json"]
    journal, logs = assets / "v7_analysis_execution.jsonl", assets / "v7_analysis_logs"
    require(not any(path.exists() for path in [*outputs, journal, logs]),
            "analysis output already exists; preserve original evidence")
    for name, expected in FIXED.items():
        require(sha(assets / name) == expected, "fixed analysis dependency changed: " + name)
    driver_path = assets / "v7_execution_driver.py"
    spec = importlib.util.spec_from_file_location("mr3_v7_completed_execution", driver_path)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    driver.verify_binding(root, FREEZE, assets / "predeclared_execution_binding_v7.json",
                          binding_sha)
    closure = closed_execution(assets / "v7_execution.jsonl",
                               assets / "matrix_v7_contact_phase_v3_audit.json")
    for directory in directories:
        require(read(directory / "benchmark_metadata.json").get("freeze") == FREEZE,
                "raw resource input has another source freeze")
    require(all((assets / "native_v7" / ("workers" + str(workers))).is_dir()
                for workers in (1, 2, 4)), "canonical normal reset inputs are not ready")
    logs.mkdir()
    with journal.open("x") as stream:
        def emit(kind, **fields):
            row = {"kind": kind, "freeze": FREEZE,
                   "utc": datetime.now(timezone.utc).isoformat(), **fields}
            stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
            stream.flush()
        emit("analysis_preflight_passed", closure=closure, binding_sha256=binding_sha,
             analyzer_driver_sha256=sha(Path(__file__)))
        for (name, argv), output in zip(jobs, outputs):
            out, err = logs / (name + ".stdout.txt"), logs / (name + ".stderr.txt")
            emit("command_started", name=name, argv=argv, cwd=str(root))
            started = time.monotonic()
            with out.open("x") as stdout, err.open("x") as stderr:
                result = subprocess.run(argv, cwd=root, stdout=stdout, stderr=stderr)
            emit("command_complete", name=name, returncode=result.returncode,
                 wall_sec=time.monotonic() - started,
                 stdout_sha256=sha(out), stderr_sha256=sha(err),
                 output_sha256=sha(output) if output.exists() else None)
            require(result.returncode == 0, name + " analysis failed; originals retained")
            value = read(output)
            if name == "resource":
                resource_gate(value, directories)
            else:
                require(value.get("passed") is True and value.get("freeze") == FREEZE
                        and value.get("observed_cells") == 16
                        and len(value.get("same_seed_pairs", [])) == 7
                        and len(value.get("cross_scene_isolation", [])) == 2,
                        "reset summary failed its declared structural scope")
        emit("both_v7_offline_analyses_complete", policy_training_performed=False,
             scope="resource diagnostics and structural reset; no automatic user acceptance")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--binding-sha256")
    args = parser.parse_args(argv)
    root = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
    if not args.execute:
        print(json.dumps({"dry_run": True, "reads_run_results": False,
                          "freeze": FREEZE, "commands": commands(root)[1]}, indent=2))
        return 0
    if not args.binding_sha256:
        parser.error("--execute requires the prospectively bound execution-binding SHA256")
    return execute(root, args.binding_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
