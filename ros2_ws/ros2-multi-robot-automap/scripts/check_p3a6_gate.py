#!/usr/bin/env python3
"""Verify saved P3A.6 evidence; run from the configured ROS workspace."""

import argparse
import hashlib
import json
from pathlib import Path

from multi_robot_exploration.bypass_audit import (
    runtime_violations, source_violations, split_node_name,
)


class Snapshot:
    """Expose a saved graph through the same API as the live audit."""

    def __init__(self, nodes):
        self.nodes = nodes

    def get_node_names_and_namespaces(self):
        return [split_node_name(name) for name in self.nodes]

    def get_subscriber_names_and_types_by_node(self, name, namespace):
        return self.nodes[f"{namespace.rstrip('/')}/{name}"]["subscribers"]

    def get_publisher_names_and_types_by_node(self, name, namespace):
        return self.nodes[f"{namespace.rstrip('/')}/{name}"]["publishers"]


def read_json(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def episode_ok(data):
    assert data["success"]
    assert data["task_phase"] == data["completion_status"] == "COMPLETE"
    assert len(data["robots"]) == data["required_robot_count"] == data["robot_count"]
    assert set(data["required_robot_names"]) == set(data["robots"])
    assert data["completion_time_sec"] <= 300 + 1e-6
    assert data["collision_monitoring_active"]
    assert data["collision_events"] == 0 and not data["failed_robots"]
    assert data["rally_position_tolerance_m"] == .35
    assert data["rally_linear_tolerance_mps"] == .05
    assert data["rally_angular_tolerance_radps"] == .1
    assert data["rally_hold_sec"] == 5
    for name, robot in data["robots"].items():
        assert robot["rally_final_error_m"] <= .35, (name, robot)
        assert robot["final_linear_speed_mps"] <= .05, (name, robot)
        assert robot["final_angular_speed_radps"] <= .1, (name, robot)
        assert robot["battery_minimum_energy"] > 0
        assert robot["battery_mode"] == "ACTIVE"


def same_candidate(candidate, reference):
    assert candidate.get("task_stack_clean", not candidate["worktree_dirty"])
    assert candidate["task_stack_candidate_commit"] == candidate["git_commit"]
    for field in ("git_commit", "source_digests", "environment"):
        assert candidate[field] == reference[field], field


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summaries", nargs="+", type=Path)
    parser.add_argument("--forced", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    package = Path.cwd() / "src/multi_robot_exploration"
    audit = read_json(package / "config/p3a_forbidden_bypasses.json")

    def graph_ok(path, count):
        violations = runtime_violations(
            Snapshot(read_json(path)["nodes"]), audit, count,
        )
        assert not violations, (path, violations)
        return digest(path)

    fixed_parameters = {
        "lab_far_northwest": ("my_world.world", -4., 4., 40.),
        "rooms_far_northeast": ("p1c_rooms.world", 5., 3., 40.),
        "corridors_far_west": ("p1c_corridors.world", -4.5, -.5, 45.),
    }
    manifest = None
    rows, evidence, batches = [], [], []
    for summary_path in args.summaries:
        summary = read_json(summary_path)
        candidate = summary["manifest"]
        if manifest is None:
            manifest = candidate
        same_candidate(candidate, manifest)
        assert summary["max_duration_sec"] == 300
        batches.append({
            "summary_path": str(summary_path),
            "summary_sha256": digest(summary_path),
            "git_commit": candidate["git_commit"], "worktree_dirty": False,
            "runner": candidate["runner"],
        })
        for entry in summary["episodes"]:
            assert entry["success"] and not entry["infrastructure_failure"]
            assert entry["prestart_failure_count"] == 0
            assert entry["runner_returncode"] == 0
            path = Path(entry["result_path"])
            data = read_json(path)
            episode_ok(data)
            assert data["robot_count"] == entry["robot_count"]
            assert data["gazebo_seed"] == entry["gazebo_seed"]
            world, tx, ty, energy = fixed_parameters[entry["scenario_id"]]
            assert Path(data["world_file"]).name == world
            assert data["target_x"] == tx and data["target_y"] == ty
            assert entry["battery_initial_energy"] == energy
            assert all(robot["battery_initial_energy"] == energy
                       for robot in data["robots"].values())
            rows.append((entry["scenario_id"], entry["robot_count"], entry["gazebo_seed"]))
            evidence.append({
                "episode_id": entry["episode_id"],
                "scenario_id": entry["scenario_id"],
                "robot_count": entry["robot_count"], "gazebo_seed": entry["gazebo_seed"],
                "world": world, "target": [tx, ty], "initial_energy": energy,
                "completion_time_sec": data["completion_time_sec"],
                "collision_events": 0,
                "battery_total_charges": data["battery_total_charges"],
                "minimum_energy": data["battery_minimum_energy"],
                "maximum_rally_error_m": max(
                    robot["rally_final_error_m"] for robot in data["robots"].values()
                ),
                "result_path": str(path), "result_sha256": digest(path),
                "world_sha256": digest(Path(data["world_file"])),
                "graph_path": entry["graph_path"],
                "graph_sha256": graph_ok(Path(entry["graph_path"]), entry["robot_count"]),
            })
    expected = {(scene, 3, seed) for scene in fixed_parameters
                for seed in (101, 202, 303)} | {("corridors_far_west", 2, 202)}
    assert len(rows) == 10 and set(rows) == expected

    forced_root = args.forced
    forced_manifest = read_json(forced_root / "manifest.json")
    same_candidate(forced_manifest, manifest)
    forced_results = list((forced_root / "episodes").glob("*.json"))
    assert len(forced_results) == 1
    assert read_json(forced_root / "exit_code.json")["exit_code"] == 0
    forced_path = forced_results[0]
    forced = read_json(forced_path)
    episode_ok(forced)
    assert forced["robot_count"] == 2 and forced["gazebo_seed"] == 303
    assert forced["battery_total_charges"] == 2
    assert forced["target_x"] == -4 and forced["target_y"] == 4
    assert Path(forced["world_file"]).name == "my_world.world"
    config = forced_manifest["forced_charge_episode"]
    for field, value in {
        "initial_energy": 18, "safety_margin": 5, "charge_duration_sec": 10,
        "return_timeout_sec": 120, "charge_timeout_sec": 60,
        "global_battery_rally_pause": False, "rally_max_concurrent": 2,
    }.items():
        assert config[field] == value, field
    assert all(robot["battery_initial_energy"] == 18
               and robot["battery_charge_count"] == 1
               for robot in forced["robots"].values())
    assert not source_violations(audit, package)
    result = {
        "task_stack_frozen_commit": manifest["git_commit"],
        "candidate_manifest": manifest,
        "fixed_matrix_complete_count": 10, "fixed_matrix_episode_count": 10,
        "fixed_matrix_collision_events": 0, "runtime_audit_count": 11,
        "source_audit_violations": [], "development_seeds": [101, 202, 303],
        "held_out_statistical_claim": False, "episodes": evidence,
        "batches": batches,
        "forced_charge": {
            "episode_id": forced["episode_id"],
            "completion_time_sec": forced["completion_time_sec"],
            "collision_events": 0,
            "charge_counts": {name: robot["battery_charge_count"]
                             for name, robot in forced["robots"].items()},
            "minimum_energy": forced["battery_minimum_energy"],
            "result_path": str(forced_path), "result_sha256": digest(forced_path),
            "graph_sha256": graph_ok(forced_root / "graph.json", 2),
            "manifest_sha256": digest(forced_root / "manifest.json"),
        },
        "validator": {"path": "scripts/check_p3a6_gate.py",
                      "sha256": digest(Path(__file__))},
    }
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print("P3A.6 PASS", result["task_stack_frozen_commit"],
          "10/10 COMPLETE, zero collisions, forced charge 1+1, 11 graph audits")


if __name__ == "__main__":
    main()
