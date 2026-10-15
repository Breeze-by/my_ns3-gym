#!/usr/bin/env python3
"""Describe completed v7 normal resets using pinned v6 structural checks.

No ROS initialization, simulation, or training. Run only after final analysis
authorization. Initial pose/map differences remain descriptive, and legitimate
current-epoch warmup history/maps are never claimed blank or bitwise repeatable.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import itertools
import json
from pathlib import Path
import re
import subprocess
import sys


WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
ASSETS = WIRELESS + "report/assets/20261015_mr3_p1c/"
CORE_NAME = "reset_analysis_v6.py"
CORE_SHA = "019e7a97e8d2d3370a633bd03e5e0dd13bb81b27bd7fa5c0729499c31e166995"
PHASE_NAME = "audit_mr3_env_contact_phase_v3.py"
PHASE_SHA = "4e2a24e3465fa45c06c05c37b57b8b77b6e462845b3227be10c1fecb85c2c7d7"
COMMAND_SHA = "4787ca8d2e6b4d7ba06b3d5a3c1ead82fe6f079485a790c5b940f2ba7636c3b9"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def exact_hex(value, length, label):
    require(isinstance(value, str) and re.fullmatch("[0-9a-f]{" + str(length) + "}", value),
            "explicit exact " + label + " is required")


def load_pinned(name, path, digest):
    require(sha(path.read_bytes()) == digest, "reset dependency SHA changed: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def load_core(root, freeze):
    exact_hex(freeze, 40, "source freeze")
    core = load_pinned("mr3_reset_v7_core_v6", root / ASSETS / CORE_NAME, CORE_SHA)
    core.FREEZE = freeze
    return core


def extra_inputs(core):
    files = [core.PACKAGE + "models/turtlebot3_waffle/model.sdf",
             core.PACKAGE + "urdf/turtlebot3_waffle.urdf",
             core.MODULE + "mr3_protocol.py", core.MODULE + "mr3_transport.py",
             core.ROS + "src/slam_toolbox/launch/online_async_multirobot_launch.py",
             core.ROS + "src/slam_toolbox/config/mapper_params_online_multi_async.yaml"]
    files += [core.PACKAGE + "params/nav2_params_" + name + "_0.yaml" for name in core.ROBOTS]
    files += [core.PACKAGE + "worlds/p1c_" + scene + ".world"
              for scene in ("open", "rooms", "corridors")]
    files += [core.PACKAGE + "config/mr3_p1a/" + scene + ".json"
              for scene in ("open", "rooms", "corridors")]
    return files


def frozen_catalogue(core, root, freeze, checks_path, checks_sha):
    """Bind the supplied implementation lock, its Git blob and every source byte."""
    exact_hex(freeze, 40, "source freeze")
    exact_hex(checks_sha, 64, "implementation-check SHA256")
    checks_path = Path(checks_path).resolve()
    relative = checks_path.relative_to(root.resolve()).as_posix()
    payload = checks_path.read_bytes()
    require(sha(payload) == checks_sha, "implementation lock changed")
    saved = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
    require(sha(saved) == checks_sha, "implementation lock/Git freeze mismatch")
    checks = json.loads(payload)
    require(checks.get("schema") == "mr3-p1c-implementation-checks-v7"
            and isinstance(checks.get("source_sha256"), dict) and checks["source_sha256"],
            "invalid v7 implementation source lock")
    sources = checks["source_sha256"]
    blobs, proof = {}, {}
    for name in sorted(set(sources) | set(extra_inputs(core))):
        path = Path(name)
        require(not path.is_absolute() and ".." not in path.parts, "unsafe source lock path")
        if name in sources:
            exact_hex(sources[name], 64, "source SHA256")
        blob = subprocess.check_output(["git", "show", freeze + ":" + name], cwd=root)
        digest = sha(blob)
        require(name not in sources or sources[name] == digest,
                "frozen lock/blob mismatch: " + name)
        require(sha((root / name).read_bytes()) == digest, "current input/source changed: " + name)
        blobs[name] = blob
        proof[name] = {"sha256": digest, "git_object": freeze + ":" + name,
                       "current_bytes_match": True}
    lock = {"path": str(checks_path), "sha256": checks_sha,
            "git_object": freeze + ":" + relative, "current_bytes_match": True,
            "source_count": len(sources)}
    return blobs, proof, lock


def load_phase(root, freeze):
    phase = load_pinned("mr3_reset_v7_phase_v3", root / ASSETS / PHASE_NAME, PHASE_SHA)
    base, audit, command, proof = phase.load_components(freeze, root)
    require(phase.COMMAND_SHA256 == COMMAND_SHA, "unexpected command-time dependency")
    return base, audit, proof


def primary_audit_link(core, root, workers, freeze):
    path = root / ASSETS / f"workers{workers}_v7_contact_phase_v3_benchmark_audit.json"
    payload = path.read_bytes()
    verdict = json.loads(payload)
    phase = verdict.get("offline_contact_phase_audit", {})
    require(verdict.get("schema") == "mr3-p1c-contact-phase-audit-v3"
            and verdict.get("passed") is True and verdict.get("freeze") == freeze
            and phase.get("freeze") == freeze and phase.get("wrapper_sha256") == PHASE_SHA
            and phase.get("command_time_gate", {}).get("sha256") == COMMAND_SHA
            and phase.get("only_overridden_functions") == ["audit_contacts", "audit_protocol"]
            and phase.get("original_results_modified") is False,
            "normal benchmark lacks the fixed-source phase3/command-time audit")
    return {"path": str(path), "sha256": core.sha(payload)}


def analyse(root, native, freeze, checks_path, checks_sha):
    core = load_core(root, freeze)
    blobs, source, lock = frozen_catalogue(core, root, freeze, checks_path, checks_sha)
    phase, audit, phase_proof = load_phase(root, freeze)
    episodes, pairs, cross, errors, links = [], [], [], [], []
    all_identities, all_epochs = set(), set()
    for workers in (1, 2, 4):
        directory = native / ("workers" + str(workers))
        benchmark = core.Reader(directory)
        declaration = benchmark.json("benchmark_metadata.json")
        require(declaration["workers"] == workers and declaration["freeze"] == freeze,
                "benchmark reset configuration differs")
        schedule = [["open", 101], ["open", 101]]
        if workers == 1:
            schedule += [["rooms", 202], ["corridors", 303]]
        require(declaration["schedule"] == schedule, "normal reset schedule changed")
        link = primary_audit_link(core, root, workers, freeze)
        link["benchmark_inputs"] = benchmark.files
        links.append(link)
        for worker in range(workers):
            group = []
            for index, (scene, seed) in enumerate(schedule, 1):
                path = directory / f"worker{worker}" / f"episode{index:03d}_{scene}_{seed}"
                try:
                    row = core.summarize_episode(root, path, phase, audit, blobs, source)
                    require([row["scene"], row["seed"]] == [scene, seed]
                            and row["worker_id"] == worker, "episode declaration differs")
                    identities = {tuple(p) for p in row["processes"]["owned_pid_identities"]}
                    require(row["epoch"] not in all_epochs
                            and not identities.intersection(all_identities),
                            "epoch/owned full process identity reused across normal matrix")
                    all_epochs.add(row["epoch"])
                    all_identities.update(identities)
                    group.append(row)
                    episodes.append(row)
                except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
                    errors.append({"directory": str(path), "error": str(error)})
            if len(group) == len(schedule):
                try:
                    pairs.append(core.pair(group[0], group[1]))
                    cross.extend(core.pair(a, b, False) for a, b in zip(group[1:], group[2:]))
                except (ValueError, TypeError, KeyError) as error:
                    errors.append({"worker": worker, "workers": workers, "error": str(error)})
    opens = [row for row in episodes if row["scene"] == "open"]
    require(len(episodes) == 16 and len(pairs) == 7 and len(cross) == 2 or errors,
            "reset cell coverage differs")
    equivalence = {row["configuration"]["semantic_input_sha256"] for row in opens}
    if len(equivalence) != 1:
        errors.append({"error": "open101 semantic input configuration differs across workers"})
    all_pairs = [core.pair(a, b) for a, b in itertools.combinations(opens, 2)] if not errors else []
    return {"schema": "mr3-p1c-reset-summary-v2", "freeze": freeze, "passed": not errors,
            "errors": errors, "required_cells": 16, "observed_cells": len(episodes),
            "episodes": episodes, "same_seed_pairs": pairs, "cross_scene_isolation": cross,
            "same_seed_max_xy_m": max((p["max_xy_m"] for p in pairs), default=None),
            "same_seed_max_yaw_rad": max((p["max_yaw_rad"] for p in pairs), default=None),
            "all_open101_pairwise_maxima": {
                "pair_count": len(all_pairs),
                "xy_pair": max(all_pairs, key=lambda p: p["max_xy_m"], default=None),
                "yaw_pair": max(all_pairs, key=lambda p: p["max_yaw_rad"], default=None)},
            "open101_semantic_input_hash_count": len(equivalence), "source_proof": source,
            "implementation_lock": lock, "phase_source_proof": phase_proof,
            "initialization_source_scope": core.INITIALIZATION_SCOPE,
            "initialization_proof_kind": (
                "reviewed pinned construction code; no dynamic cache probe"),
            "primary_audit_links": links, "current_proc_snapshot_performed": False,
            "dependencies": {CORE_NAME: CORE_SHA, PHASE_NAME: PHASE_SHA,
                             "audit_command_time_v7.py": COMMAND_SHA},
            "scope": ("Saved reset identities/source chain and estimated initial differences; "
                      "no bitwise DDS/SLAM claim; reused immutable v6 structural checks"),
            "limitations": [
                "No saved temp RewrittenYaml bytes; frozen sources and actual launch paths only",
                "Deployed model digest checked now; no independent run-time file attestation",
                "History lacks per-point epoch/raw XY logs; process/filter/source-stamp proof only",
                "Payload SHA includes headers; hash inequality is not occupancy/no-residual proof",
                "Snapshot SHA includes epoch/time; its inequality is not a reproducibility failure",
                "No per-message contact timing replay or initial raw reward_ready payload",
                "No invented numerical tolerance; pose differences are descriptive",
                "Saved cleanup receipts do not supply an exact cross-episode process span"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--implementation-checks", required=True, type=Path)
    parser.add_argument("--implementation-checks-sha256", required=True)
    parser.add_argument("--native-root", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; choose a new filename")
    exact_hex(args.freeze, 40, "source freeze")
    exact_hex(args.implementation_checks_sha256, 64, "implementation-check SHA256")
    root = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
    report = analyse(root, args.native_root or root / ASSETS / "native_v7", args.freeze,
                     args.implementation_checks, args.implementation_checks_sha256)
    report.update(created_at_utc=datetime.now(timezone.utc).isoformat(),
                  analyzer_sha256=sha(Path(__file__).read_bytes()),
                  command=[sys.executable, str(Path(__file__)),
                           *(sys.argv[1:] if argv is None else argv)])
    with args.output.open("x") as output:
        json.dump(report, output, sort_keys=True, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": report["passed"], "errors": report["errors"],
                      "output": str(args.output)}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
