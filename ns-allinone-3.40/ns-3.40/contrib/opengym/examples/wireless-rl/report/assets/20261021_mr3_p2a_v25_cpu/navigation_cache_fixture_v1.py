"""Bounded artificial navigation timing; never constructs a world or episode."""
import argparse
import importlib.util
import json
from pathlib import Path
import time
from unittest.mock import patch

import numpy as np


ROOT = Path(__file__).resolve().parents[9]
TEST = ROOT / ("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/"
               "test/test_mr3_proxy2d_navigation_cache.py")
spec = importlib.util.spec_from_file_location("navigation_cache_cpu_fixture", TEST)
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
current, original = fixture.navigation, fixture.baseline_module()


def execute(implementation, requests):
    navigator = implementation.ProxyNavigator()
    state, goal = {"x": -.5, "y": -.5, "yaw": .2}, {"x": .8, "y": .7}
    observed, elapsed = [], 0
    with patch.object(implementation, "_path_distances", wraps=implementation._path_distances) as builds:
        for received in requests:
            started = time.perf_counter_ns()
            result = navigator.target_velocity("tb1", state, goal, received)
            elapsed += time.perf_counter_ns() - started
            # Equivalence capture/checking is outside the timed target call.
            observed.append((result, dict(navigator.blocked_quanta),
                             navigator.paths["tb1"][1].copy(), navigator.paths["tb1"][2].copy()))
        count = builds.call_count
    return {"target_velocity_ns": elapsed, "dijkstra_builds": count}, observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rounds = []
    for kind in ("timestamp_only", "real_cell_mutations"):
        requests = []
        for index in range(12):
            received = fixture.artificial_map(index, size=48)
            if kind == "real_cell_mutations":
                received["grid"][20, 20 + index] = 100
            requests.append(received)
        for round_index in range(3):
            implementations = ([("original", original), ("optimized", current)] if round_index % 2 == 0
                               else [("optimized", current), ("original", original)])
            results, outputs = {}, {}
            for name, implementation in implementations:
                results[name], outputs[name] = execute(implementation, requests)
            for left, right in zip(outputs["original"], outputs["optimized"]):
                assert left[:2] == right[:2]
                np.testing.assert_array_equal(left[2], right[2])
                np.testing.assert_array_equal(left[3], right[3])
            assert results["original"]["dijkstra_builds"] == 12
            assert results["optimized"]["dijkstra_builds"] == (1 if kind == "timestamp_only" else 12)
            rounds.append({"case": kind, "round": round_index + 1, "requests_per_implementation": 12,
                           "grid_shape": [48, 48], "grid_dtype": "int16",
                           "original": results["original"], "optimized": results["optimized"],
                           "full_velocity_blocked_and_field_outputs_equal": True})
    result = {"schema": "mr3-proxy2d-navigation-cache-artificial-timing-v1",
              "baseline_freeze": fixture.BASELINE_FREEZE, "baseline_sha256": fixture.BASELINE_SHA256,
              "rounds": rounds, "passed": True,
              "scope": "Fixed artificial received arrays and pose/goal only. Target-call timings include the "
              "new C-order byte packing; equivalence capture is outside those calls. These are not "
              "environment steps, long-rollout throughput or a measured real-environment speedup.",
              "worlds_created": 0, "nodes_created": 0, "episodes": 0,
              "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0,
              "qualification": False, "training_eligible": False, "native_credit": False}
    with args.output.open("x") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"passed": True, "rounds": rounds, "output": str(args.output)}))


if __name__ == "__main__":
    main()
