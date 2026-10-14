#!/usr/bin/env python3
"""Emit an offline MR3 SDF/ROI diagnostic; this never runs a simulator."""

import argparse
import json
from pathlib import Path
import sys


ROS_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROS_ROOT / "src" / "multi_robot_exploration"))

from multi_robot_exploration.mr3_task_contract import (  # noqa: E402
    diagnose_contract_geometry,
    inspect_world_geometry,
    load_contract_truth,
    load_task_contract,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, help="One SDF world; default audits all four")
    parser.add_argument("--contract", type=Path, help="Contract for --world")
    parser.add_argument("--contract-dir", type=Path,
                        default=ROS_ROOT / "src/multi_robot/config/mr3_p1a")
    parser.add_argument("--output", type=Path, help="New receipt path; existing files are refused")
    args = parser.parse_args()
    if args.contract and not args.world:
        parser.error("--contract requires --world")
    worlds_dir = ROS_ROOT / "src/multi_robot/worlds"
    names = ["p1c_open.world", "p1c_rooms.world", "p1c_corridors.world", "my_world.world"]
    worlds = [args.world] if args.world else [worlds_dir/name for name in names]
    entries = []
    invalid_contract = False
    for world in worlds:
        _, audit = inspect_world_geometry(world)
        entry = {"geometry_audit": audit}
        contract_path = args.contract
        if contract_path is None:
            stem = world.stem.removeprefix("p1c_")
            candidate = args.contract_dir / f"{stem}.json"
            if candidate.exists():
                contract_path = candidate
        if contract_path is not None:
            try:
                contract = load_task_contract(contract_path, world)
                truth = load_contract_truth(world, contract)
                entry["contract_file"] = str(contract_path)
                entry["contract_sha256"] = contract.sha256
                entry["diagnostic"] = diagnose_contract_geometry(truth, contract)
            except (ValueError, OSError) as exc:
                entry["contract_error"] = str(exc)
                invalid_contract = True
        else:
            entry["contract_status"] = "not_declared; no MR3 task acceptance credit"
        entries.append(entry)
    receipt = {"type": "offline_geometry_audit_not_simulation",
               "simulator_runs": 0, "worlds": entries}
    payload = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x") as stream:
            stream.write(payload)
    print(payload, end="")
    return 1 if invalid_contract else 0


if __name__ == "__main__":
    raise SystemExit(main())
