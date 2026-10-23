"""Fixed artificial mapper-v1/v2 comparison, never a World or task run.

The declared inputs/parameters below are fixed before execution. Truth is used
only to generate artificial range fixtures and evaluate detached output grids;
neither mapper receives geometry, truth, physical state or a hidden hit flag.
No result is a task PASS, real-scene performance or learning qualification.
"""

import argparse
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import time

import numpy as np


SHAPE = (48, 48)
RESOLUTION = .05
ORIGIN = (-1.2, -1.2)
BOUNDS = (-1.2, -1.2, 1.2, 1.2)
RANGE_MIN, RANGE_MAX = .12, 10.
FIXED_V2 = {
    "model": "range_ray_bounded_evidence_v2", "hit_increment": 2, "free_decrement": 1,
    "evidence_clip": [-4, 4], "occupied_threshold": 2, "free_threshold": -2,
    "endpoint_tie_lattice_ulps": 4, "max_ray_workspace_samples": 8_000_000,
    "within_scan_rule": "at most one vote per cell, hit wins free conflict",
    "gridline_rule": "four lattice ULP tie only; negative direction nextafter(-inf), positive floor, zero direction floor",
    "spatial_guard_or_dilation": False,
}


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _sha(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _helpers():
    path = Path(__file__).with_name("test_mr3_proxy2d_mapping_quality.py")
    spec = importlib.util.spec_from_file_location("_mapping_quality_comparison_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def _scan(scan_id, pose, angles, ranges, **annotation):
    value = {"scan_id": scan_id, "sensor_pose": list(map(float, pose)),
             "angles": list(map(float, angles)), "ranges": list(map(float, ranges)),
             "range_min": RANGE_MIN, "range_max": RANGE_MAX, **annotation}
    value["input_sha256"] = hashlib.sha256(_canonical(value)).hexdigest()
    return value


def _analytic_scan(helper, scan_id, pose, angles, rectangles, **annotation):
    angles = np.asarray(angles, dtype=float)
    heading = angles + pose[2]
    directions = np.column_stack((np.cos(heading), np.sin(heading)))
    ranges = helper.ray_box_ranges(pose[:2], directions, rectangles, RANGE_MAX)
    return _scan(scan_id, pose, angles, ranges, input_kind="analytic artificial box returns", **annotation)


def _cases(helper):
    cases = []
    for name, rectangle in (("four_faces_gridline", (0., 0., 0., .5, .5)),
                            ("four_faces_off_grid", (.011, .013, 0., .5, .5)),
                            ("rotated_bar", (.03, -.02, .45, .3, .9))):
        scans = []
        for index, (x, y) in enumerate(((-.85, 0.), (.85, .1), (0., -.85), (0., .85)), 1):
            yaw = math.atan2(rectangle[1] - y, rectangle[0] - x)
            scans.append(_analytic_scan(helper, index, (x, y, yaw), [-.12, -.06, 0., .06, .12], [rectangle]))
        cases.append({"id": name, "rectangles": [rectangle], "scans": scans})

    rectangle = (0., 0., 0., .5, .5)
    angles = [0., 1e-12, -1e-12, math.atan2(.5, .55)]
    cases.append({"id": "corner_and_grazing", "rectangles": [rectangle], "scans": [
        _analytic_scan(helper, index, (-.8, -.25, 0.), angles, [rectangle]) for index in (1, 2)]})

    rectangle = (.399, .5, 0., .2, .5)
    perturbations = [0., .002, -.002, .01, -.01, .002, -.002, 0.]
    cases.append({"id": "prescribed_signed_range_errors", "rectangles": [rectangle], "scans": [
        _scan(index, (0., .325, 0.), [0.], [.299 + error],
              input_kind="prescribed range error; not a random frequency estimate", range_error_m=error,
              analytic_reference_range_m=.299)
        for index, error in enumerate(perturbations, 1)]})
    cases.append({"id": "persistent_positive_two_mm_bias", "rectangles": [rectangle], "scans": [
        _scan(index, (0., .325 if index % 2 else .525, 0.), [0.], [.301],
              input_kind="prescribed persistent positive range bias", range_error_m=.002,
              analytic_reference_range_m=.299)
        for index in range(1, 9)]})

    cases.append({"id": "max_range_nohit_only", "rectangles": [], "scans": [
        _scan(index, (-.8, .025, 0.), [-.2, 0., .2], [10., 10., 10.], input_kind="prescribed max-range nohit")
        for index in range(1, 5)]})
    cases.append({"id": "near_max_hit_then_nohit", "rectangles": [], "scans": [
        _scan(index, (-9.875, .025, 0.), [0.], [9.999 if index == 1 else 10.],
              input_kind="prescribed range-limit/ghost fixture; sensor origin outside evaluation ROI")
        for index in range(1, 8)]})

    rectangle = (0., 0., 0., .8, .6)
    for order, ranges in (("hit_first", [.4, 10.]), ("free_first", [10., .4])):
        cases.append({"id": "same_scan_conflict_" + order, "rectangles": [rectangle],
                      "permutation_pair": "same_scan_conflict", "scans": [
                          _scan(index, (-.8, .025, 0.), [0., 0.], ranges,
                                input_kind="prescribed contradictory same-scan rays; ray-order permutation")
                          for index in (1, 2)]})

    rectangle = (0., 0., 0., .5, .5)
    cases.append({"id": "duplicate_and_new_scan_ids", "rectangles": [rectangle], "scans": [
        _scan(index, (-.8, .025, 0.), [0.], [.55], input_kind="same payload, repeated and independent scan IDs")
        for index in (1, 1, 2, 2, 3)]})
    cases.append({"id": "ghost_recovery_by_independent_free_scans", "rectangles": [], "scans": [
        _scan(index, (-.8, .025, 0.), [0.], [.55 if index <= 2 else 10.],
              input_kind="prescribed transient exterior object return followed by nohit; static truth is free")
        for index in range(1, 11)]})
    cases.append({"id": "saturated_free_then_three_new_hit_scans", "rectangles": [rectangle],
                  "truth_scope": "fixed artificial box; early nohits are prescribed missed-obstacle measurements, not physical replay",
                  "scans": [_scan(index, (-.8, .025, 0.), [0.], [10. if index <= 4 else .55],
                                  input_kind="four independent free scans, then three independent new hit scans")
                            for index in range(1, 8)]})

    base, offset = (.7, .7, math.pi / 2), (-.064, 0.)
    sx = base[0] + math.cos(base[2]) * offset[0] - math.sin(base[2]) * offset[1]
    sy = base[1] + math.sin(base[2]) * offset[0] + math.cos(base[2]) * offset[1]
    sensor = (sx, sy, base[2])
    center_angle = (math.atan2(-sy, -sx) - sensor[2]) % (2 * math.pi)
    cases.append({"id": "known_estimated_sensor_offset", "rectangles": [rectangle],
                  "estimated_base_pose": list(base), "sensor_frame_offset_m": list(offset),
                  "sensor_pose_derivation": "estimated base rigid transform only; no physical pose correction",
                  "scans": [_analytic_scan(helper, index, sensor,
                                            [center_angle - .04, center_angle, center_angle + .04], [rectangle])
                            for index in range(1, 5)]})
    return cases


def _quality(helper, truth, grid):
    # Identical original full-ROI evaluator metrics for both detached maps.
    original = helper.metrics(truth, grid)
    occupied, free = truth.occupied & truth.roi_mask, ~truth.occupied & truth.roi_mask
    known, predicted = (grid >= 0) & truth.roi_mask, grid >= 50
    counts = {
        "TP": int((known & predicted & occupied).sum()),
        "FP": int((known & predicted & free).sum()),
        "false_free": int((known & ~predicted & occupied).sum()),
        "TN": int((known & ~predicted & free).sum()),
        "unknown_occupied": int((~known & occupied).sum()),
        "unknown_free": int((~known & free).sum()),
    }
    return {"counts": counts, "original_metrics": original,
            "original_artificial_map_quality_pass": helper.mr3_quality_pass(original, helper.QUALITY),
            "quality_gate_pass_is_not_task_success": True,
            "FP_over_truth_free_auxiliary_not_a_new_gate": counts["FP"] / max(1, int(free.sum())),
            "grid_sha256": _sha(grid), "grid_dtype": str(grid.dtype), "grid_shape": list(grid.shape),
            "grid_values": [int(value) for value in np.unique(grid)]}


def _arguments(scan):
    return (np.array(scan["sensor_pose"], dtype=np.float64),
            np.array(scan["angles"], dtype=np.float64),
            np.array(scan["ranges"], dtype=np.float64))


def _argument_digest(pose, angles, ranges):
    return hashlib.sha256(pose.tobytes() + angles.tobytes() + ranges.tobytes()).hexdigest()


def _v1_integrate(helper, state, scan, pose, angles, ranges):
    state._angles = angles
    state._laser["range_max"] = scan["range_max"]
    # Inputs are already sensor poses. The synthetic container's offset is zero.
    helper.ProxyWorld._integrate_scan(state, "sensor", pose, ranges)


def _v1_memory(state):
    return state._maps["sensor"].nbytes + sum(value.nbytes for value in state._last_ray_cells.values())


def _compare_case(helper, mapping, case):
    truth = helper.artificial_truth(case["rectangles"], BOUNDS)
    truth.roi_mask = np.ones_like(truth.occupied)
    v1 = helper.measurement_container(truth, case["scans"][0]["angles"])
    v2 = mapping.SensorMapperV2(SHAPE, RESOLUTION, ORIGIN)
    result = {key: value for key, value in case.items() if key != "scans"}
    result["truth_occupied_cells"] = int(truth.occupied.sum())
    result["truth_free_cells"] = int((~truth.occupied).sum())
    result["truth_occupied_sha256"] = _sha(truth.occupied)
    result["checkpoints"] = []
    for index, scan in enumerate(case["scans"], 1):
        pose1, angles1, ranges1 = _arguments(scan)
        pose2, angles2, ranges2 = _arguments(scan)
        before1, before2 = _argument_digest(pose1, angles1, ranges1), _argument_digest(pose2, angles2, ranges2)
        assert before1 == before2
        _v1_integrate(helper, v1, scan, pose1, angles1, ranges1)
        accepted = v2.integrate(scan["scan_id"], pose2, angles2, ranges2,
                                range_min=scan["range_min"], range_max=scan["range_max"])
        assert before1 == _argument_digest(pose1, angles1, ranges1)
        assert before2 == _argument_digest(pose2, angles2, ranges2)
        evidence = v2.evidence()
        result["checkpoints"].append({
            "index": index, "input": scan, "identical_detached_inputs_sha256": before1,
            "input_arrays_unchanged": True,
            "v1": {**_quality(helper, truth, v1._maps["sensor"]), "persistent_buffer_bytes": _v1_memory(v1)},
            "v2": {**_quality(helper, truth, v2.grid()), "new_scan_accepted": bool(accepted),
                   "persistent_buffer_bytes": v2.memory_bytes, "evidence_sha256": _sha(evidence),
                   "evidence_min": int(evidence.min()), "evidence_max": int(evidence.max())},
        })
    return result


def _timing(helper, mapping):
    angles = np.linspace(0., 6.28, 360)
    ranges = np.full(360, .7)
    scans_by_kind = {kind: [_scan(1 if kind == "duplicate_same_scan" else i, (0., 0., .13), angles, ranges)
                           for i in range(1, 13)]
                     for kind in ("duplicate_same_scan", "new_scan_same_geometry")}
    results = []
    for kind, scans in scans_by_kind.items():
        for round_index in range(3):
            order = ("v1", "v2") if round_index % 2 == 0 else ("v2", "v1")
            implementations = {}
            for implementation in order:
                truth = helper.artificial_truth([], BOUNDS)
                mapper = (helper.measurement_container(truth, angles) if implementation == "v1"
                          else mapping.SensorMapperV2(SHAPE, RESOLUTION, ORIGIN))
                durations, accepted = [], []
                for scan in scans:
                    pose, actual_angles, actual_ranges = _arguments(scan)
                    digest = _argument_digest(pose, actual_angles, actual_ranges)
                    if implementation == "v1":
                        mapper._angles = actual_angles
                        mapper._laser["range_max"] = scan["range_max"]
                        started = time.perf_counter_ns()
                        helper.ProxyWorld._integrate_scan(mapper, "sensor", pose, actual_ranges)
                        durations.append(time.perf_counter_ns() - started)
                    else:
                        started = time.perf_counter_ns()
                        new_scan = mapper.integrate(scan["scan_id"], pose, actual_angles, actual_ranges,
                                                    range_min=RANGE_MIN, range_max=RANGE_MAX)
                        durations.append(time.perf_counter_ns() - started)
                        accepted.append(bool(new_scan))
                    assert digest == _argument_digest(pose, actual_angles, actual_ranges)
                grid = mapper._maps["sensor"] if implementation == "v1" else mapper.grid()
                implementations[implementation] = {
                    "integrate_calls": len(scans), "integrate_nanoseconds_each": durations,
                    "total_integrate_nanoseconds": sum(durations),
                    "persistent_buffer_bytes": _v1_memory(mapper) if implementation == "v1" else mapper.memory_bytes,
                    "final_grid_sha256": _sha(grid), "new_scan_accepted": accepted if implementation == "v2" else None,
                }
            results.append({"kind": kind, "round": round_index + 1,
                            "implementation_order": list(order), **implementations})
    return {
        "shape": list(SHAPE), "resolution": RESOLUTION, "origin": list(ORIGIN),
        "rays_per_scan": 360, "calls_per_implementation_round": 12, "rounds_per_kind": 3,
        "pose": [0., 0., .13], "angles_definition": "np.linspace(0.,6.28,360)", "ranges_m": .7,
        "input_sha256_by_kind": {kind: [scan["input_sha256"] for scan in scans] for kind, scans in scans_by_kind.items()},
        "scan_ids_by_kind": {kind: [scan["scan_id"] for scan in scans] for kind, scans in scans_by_kind.items()},
        "rounds": results,
        "scope": "fixed artificial integrate calls only; excludes input construction, output copies, quality evaluation and JSON; no ENV throughput claim",
        "memory_scope": "persistent score/map+cache/payload buffers only; excludes Python objects, input angle references and temporary workspace; not RSS",
        "models_intentionally_differ_no_bitwise_equivalence_claim": True,
    }


def run_comparison():
    from multi_robot_exploration import mr3_proxy2d_mapping as mapping
    helper, helper_path = _helpers()
    actual = (mapping.MODEL, mapping.HIT_INCREMENT, mapping.FREE_DECREMENT,
              mapping.EVIDENCE_LIMIT, mapping.OCCUPIED_THRESHOLD, mapping.FREE_THRESHOLD,
              mapping.TIE_ULPS, mapping.MAX_RAY_SAMPLES)
    assert actual == ("range_ray_bounded_evidence_v2", 2, 1, 4, 2, -2, 4, 8_000_000), "candidate differs from predeclared parameters"
    sources = [Path(__file__).resolve(), helper_path.resolve(), Path(mapping.__file__).resolve(),
               Path(helper.mr3_proxy2d_world.__file__).resolve(), Path(helper.mr3_task_contract.__file__).resolve(),
               Path(helper.task_evaluator.__file__).resolve()]
    before = {str(path): path.read_bytes() for path in sources}
    proc_tail = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    report = {
        "schema": "mr3-proxy2d-mapping-v1-v2-artificial-comparison-v1",
        "scope": "fixed artificial sensor-only CPU candidate comparison; no task PASS or real-scene applicability proof",
        "consumer_identity": {"pid": os.getpid(), "parent": os.getppid(), "group": os.getpgrp(),
                              "session": os.getsid(0), "start_ticks": int(proc_tail[19])},
        "fixed_v2_parameters": FIXED_V2, "original_quality_gates": dict(helper.QUALITY),
        "lattice": {"shape": list(SHAPE), "resolution": RESOLUTION, "origin": list(ORIGIN)},
        "cases": [], "errors": [], "completed": False,
        "worlds_created": 0, "nodes_created": 0, "episodes": 0, "actor_calls": 0,
        "reward_replays": 0, "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0,
        "qualification": False, "training_eligible": False, "native_credit": False,
    }
    for case in _cases(helper):
        try:
            report["cases"].append(_compare_case(helper, mapping, case))
        except Exception as error:
            report["errors"].append({"case": case["id"], "error": f"{type(error).__name__}: {error}"})
    try:
        report["artificial_timing"] = _timing(helper, mapping)
    except Exception as error:
        report["errors"].append({"phase": "timing", "error": f"{type(error).__name__}: {error}"})
    report["bound_source_bytes_unchanged"] = all(Path(path).read_bytes() == payload for path, payload in before.items())
    report["source_bindings"] = {path: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
                                 for path, payload in before.items()}
    if not report["bound_source_bytes_unchanged"]:
        report["errors"].append({"phase": "source", "error": "source bytes changed"})
    report["completed"] = not report["errors"] and len(report["cases"]) == 14
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    report = run_comparison()
    with args.output.open("x") as handle:
        json.dump(report, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return 0 if report["completed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
