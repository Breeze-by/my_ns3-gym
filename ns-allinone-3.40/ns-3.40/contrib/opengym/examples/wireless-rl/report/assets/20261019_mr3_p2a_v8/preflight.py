#!/usr/bin/env python3
"""Bind the prospective V8 fixture to one clean pushed source and actual ELF bytes."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time


HERE = Path(__file__).resolve().parent
ROOT = Path(subprocess.check_output(
    ["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], text=True).strip())
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("native admission requires a clean working tree")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    pushed = subprocess.check_output(
        ["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip()
    if head != pushed:
        raise ValueError("native admission requires the pushed main freeze")
    plan = json.loads((HERE / "predeclared_plan_v8.json").read_text())
    for name, digest in plan["source_bindings"].items():
        if sha(ROOT / name) != digest:
            raise ValueError("source binding changed: " + name)
    libraries = {}
    for name, spec in plan["library_bindings"].items():
        path = ROOT / spec["relative_path"]
        if sha(path) != spec["sha256"]:
            raise ValueError("installed ELF changed: " + name)
        libraries[name] = {**spec, "path": str(path), "resolved_path": str(path.resolve(strict=True))}
    observer = libraries["observer"]
    if observer["source_sha256"].encode() not in Path(observer["path"]).read_bytes():
        raise ValueError("observer ELF lacks the current compiled-source SHA")
    configs = {}
    for arm in ("continuous", "pulse"):
        run_id = "mr3_p2a_v8_" + arm
        run = ROS / "log/mr3_plant" / run_id
        if run.exists():
            raise FileExistsError("single-opportunity native run already exists: " + str(run))
        config = {
            "schema": "mr3-physics-diagnostic-config-v2", "mode": "observer_only",
            "run_directory": str(run),
            "episode_relative_directory": "worker0/episode001_open_101",
            "scene": "open", "seed": 101, "capture_start_ns": 0,
            "capture_end_ns": 300_000_000_000,
            "observer_library": {key: observer[key] for key in ("path", "sha256", "source_sha256")},
        }
        target = Path("/tmp") / (run_id + "_physics.json")
        with target.open("x") as stream:
            json.dump(config, stream, indent=2)
            stream.write("\n")
        configs[arm] = {"path": str(target), "sha256": sha(target)}
    result = {"schema": "mr3-p2a-v8-preflight-v1", "passed": True,
              "freeze": head, "wall_monotonic_ns": time.monotonic_ns(),
              "plan_sha256": sha(HERE / "predeclared_plan_v8.json"),
              "source_count": len(plan["source_bindings"]),
              "libraries": libraries, "configs": configs,
              "scope": "source/installed admission only; actual mappings and stimulus require native evidence"}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"passed": True, "freeze": head, "output": str(args.output)}))


if __name__ == "__main__":
    main()
