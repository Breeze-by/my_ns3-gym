#!/usr/bin/env python3
"""Run the frozen held-out P3A.5 algorithm variants with identical gates."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = Path(__file__).with_name("p3a5_heldout_scenarios.json")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--variant", action="append")
    parser.add_argument("--seeds", nargs="+", type=int)
    parser.add_argument("--robot-count", type=int, choices=(2, 3), default=3)
    parser.add_argument("--ros-domain-base", type=int, default=140)
    parser.add_argument("--run-id", default="p3a5_heldout_ablation")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=PROJECT_ROOT / "log" / "p3a5_ablation",
    )
    return parser.parse_args()


def variant_args(name, variant):
    args = [
        "--rally-assignment-objective",
        variant["rally_assignment_objective"],
        "--rally-max-concurrent",
        str(variant["rally_max_concurrent"]),
    ]
    if not variant["map_safe_rally_order"]:
        args.append("--disable-map-safe-rally-order")
    if not variant["global_battery_rally_pause"]:
        args.append("--disable-global-battery-rally-pause")
    return args


def main():
    args = parse_args()
    config = json.loads(args.config.read_text())
    scenarios = config["scenarios"]
    variants = config["variants"]
    selected = args.variant or list(variants)
    unknown = sorted(set(selected) - set(variants))
    if unknown:
        raise SystemExit("unknown variants: " + ", ".join(unknown))
    seeds = args.seeds or config["heldout_seeds"]
    if any(seed in config["development_seeds"] for seed in seeds):
        raise SystemExit("development seed supplied to held-out run")
    if not 0 <= args.ros_domain_base <= 231:
        raise SystemExit("--ros-domain-base must be between 0 and 231")

    args.output_root.mkdir(parents=True, exist_ok=True)
    runner = PROJECT_ROOT / "scripts" / "run_p2d_baseline.py"
    records = []
    scenario_ids = [scenario["id"] for scenario in scenarios]
    for index, name in enumerate(selected):
        variant = variants[name]
        run_id = f"{args.run_id}_{name}"
        command = [
            sys.executable,
            str(runner),
            "--config",
            str(args.config),
            "--scenarios",
            *scenario_ids,
            "--seeds",
            *(str(seed) for seed in seeds),
            "--robot-count",
            str(args.robot_count),
            "--skip-cross-check",
            "--run-id",
            run_id,
            "--ros-domain-base",
            str(args.ros_domain_base + index * 30),
            "--output-root",
            str(args.output_root),
            *variant_args(name, variant),
        ]
        completed = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
        summary_path = args.output_root / run_id / "summary.json"
        records.append(
            {
                "variant": name,
                "command": command,
                "returncode": completed.returncode,
                "summary": str(summary_path),
                "summary_exists": summary_path.is_file(),
            }
        )

    aggregate = args.output_root / f"{args.run_id}_aggregate.json"
    aggregate.write_text(
        json.dumps(
            {
                "config": str(args.config),
                "seeds": seeds,
                "scenarios": scenario_ids,
                "variants": records,
            },
            indent=2,
        )
    )
    return 0 if all(record["returncode"] == 0 for record in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
