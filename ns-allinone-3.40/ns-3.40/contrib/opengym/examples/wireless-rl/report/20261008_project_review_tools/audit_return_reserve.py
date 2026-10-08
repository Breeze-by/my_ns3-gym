#!/usr/bin/env python3
"""Read-only counterexample: a fixed Euclidean factor cannot price a detour."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("never overwrite an audit")
    package = args.repo / "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration"
    sys.path.insert(0, str(package))
    from multi_robot_exploration.battery_manager import estimated_return_energy
    from multi_robot_exploration.control import (
        HeadquartersControl, path_distance_grid, traversable_grid,
    )

    resolution, origin = .2, (0., 0.)
    position, home, radius = (3.1, 1.1), (5.1, 1.1), .8
    raw = np.zeros((44, 44), dtype=np.int16)
    raw[:35, 20] = 100
    safe = traversable_grid(raw, resolution, clearance_m=.45)
    field = path_distance_grid(safe, (5, 15)) * resolution
    rows, columns = np.indices(raw.shape)
    contact = ((columns+.5)*resolution-home[0])**2 + ((rows+.5)*resolution-home[1])**2 <= radius**2
    known_path_m = float(field[safe & contact].min())
    euclidean_m = math.dist(position, home)
    reserve = estimated_return_energy(euclidean_m, 1., .02, 2., .18, 8.)
    route_nominal_cost = known_path_m * (1.+.02/.18)
    node = SimpleNamespace(battery_modes={"tb1": "ACTIVE"},
        battery_states={"tb1": {"energy": 40., "charge_x": home[0], "charge_y": home[1]}},
        robot_positions={"tb1": position})
    central_reserve = HeadquartersControl.exploration_required_energy(node, "tb1", 0., position)
    assert central_reserve == reserve and known_path_m > 2*euclidean_m
    assert route_nominal_cost > reserve, "fixture must expose a shortfall even without the route margin"
    raw[:, 20] = 100
    safe = traversable_grid(raw, resolution, clearance_m=.45)
    disconnected = not np.isfinite(path_distance_grid(safe, (5, 15))[safe & contact]).any()
    assert disconnected
    sources = {name: hashlib.sha256((package/"multi_robot_exploration"/name).read_bytes()).hexdigest()
               for name in ("battery_manager.py", "control.py")}
    result = {"status": "CONFIRMED_REQUIREMENT_GAP", "scope": "constructed known-free map, not a Gazebo task or physical safety certification",
        "source_sha256": sources, "fixture": {"resolution_m": resolution, "origin": origin,
            "shape": list(raw.shape), "wall_column": 20, "detour_wall_rows": [0, 35],
            "position": position, "home": home, "charge_radius_m": radius, "clearance_m": .45},
        "euclidean_distance_m": euclidean_m, "shortest_known_grid_path_to_any_contact_m": known_path_m,
        "current_local_reserve_units": reserve, "current_central_exploration_reserve_units": central_reserve,
        "nominal_route_cost_without_safety_margin_units": route_nominal_cost,
        "nominal_route_cost_with_original_margin_units": route_nominal_cost+8.,
        "disconnected_map_has_no_route": disconnected,
        "current_euclidean_reserve_is_finite_when_disconnected": math.isfinite(reserve),
        "required_closure": "full local known-map contact-route budget, bounded no-route safety behavior, prediction-error accounting and a new frozen integration cohort"}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False)+"\n")
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
