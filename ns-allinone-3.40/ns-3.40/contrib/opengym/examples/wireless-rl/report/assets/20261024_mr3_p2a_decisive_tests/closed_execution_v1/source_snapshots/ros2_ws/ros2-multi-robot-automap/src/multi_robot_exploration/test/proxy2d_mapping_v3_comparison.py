"""Fixed sensor-only v1/v2/v3 CPU comparison; no World or task replay.

The original fourteen fixtures and their scan input digests are immutable.
New fixtures separate observation consistency from endpoint ambiguity. Truth
is evaluation-only; it is never passed to any mapper. Technical decision flags
are not task success, actual-scene safety, model selection or RL qualification.
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


LEGACY_SOURCE_SHA256 = "bac3d39e8cf84d3fbebaeaa0d0aa40ef76be2c650bfe3ec5889571c187b98efb"
LEGACY_INPUT_MANIFEST_SHA256 = "e6884eea2900ae1165fb0197d75ca3875b2ddc5bf38250f43fcfd1e89117d763"
V3_MODEL = "range_ray_closed_cell_veto_v3"


def _legacy():
    path = Path(__file__).with_name("proxy2d_mapping_comparison.py")
    assert hashlib.sha256(path.read_bytes()).hexdigest() == LEGACY_SOURCE_SHA256
    spec = importlib.util.spec_from_file_location("_mapping_v27_fixed_fixture_reference", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, path


def _new_cases(old):
    scan, cases = old._scan, []
    box = (.001, 0., 0., .5, .5)  # Near face -.249 is strictly inside a cell.
    scans = [scan(i, (-.8, .025, 0.), [0.], [10.], input_kind="prescribed missed-obstacle free") for i in range(1, 5)]
    scans += [scan(5, (-.8, .025, 0.), [0.], [.551], input_kind="off-grid current hit after saturated free"),
              scan(6, (-.8, .025, math.pi), [0.], [10.], input_kind="look away; watched cell is unobserved"),
              scan(6, (-.8, .025, math.pi), [0.], [10.], input_kind="look away; watched cell is unobserved"),
              scan(7, (-.8, .025, 0.), [0.], [.551], input_kind="second off-grid hit")]
    cases.append({"id": "off_grid_hit_persistent_veto_while_unseen", "rectangles": [box],
                  "watch_cells_row_column": [[24, 19]], "scans": scans})
    scans = [scan(i, (-.8, .025, 0.), [0.], [10.], input_kind="prescribed free before ambiguous endpoint") for i in range(1, 5)]
    scans += [scan(i, (-.8, .025, 0.), [0.], [.8], input_kind="one-axis closed-cell ambiguous hit") for i in (5, 6)]
    scans += [scan(7, (-.8, .025, math.pi), [0.], [10.], input_kind="unseen alternatives must stay unknown")]
    cases.append({"id": "ambiguous_hit_persistent_veto_while_unseen", "rectangles": [( .1, .025, 0., .2, .2)],
                  "watch_cells_row_column": [[24, 23], [24, 24]], "scans": scans})

    # Each pair has byte-identical mapper inputs and different evaluator truth.
    for name, pose, rectangles in (
        ("horizontal_tangent", (-.8, -.25, 0.), [(0., 0., 0., .5, .5), (0., -.5, 0., .5, .5)]),
        ("vertical_tangent", (-.25, -.8, math.pi / 2), [(0., 0., 0., .5, .5), (-.5, 0., 0., .5, .5)]),
    ):
        shared = [scan(i, pose, [0.], [.55], input_kind="same measured tangent endpoint, two different truth sides") for i in (1, 2, 3)]
        for side, rectangle in enumerate(rectangles):
            cases.append({"id": name + "_truth_" + str(side), "rectangles": [rectangle],
                          "identical_input_pair": name, "scans": shared})

    # Diamond rightmost vertex lies on an x gridline, with y strictly in a cell.
    # A nonzero positive dx ray touches the vertex from outside, then exits.
    sensor, endpoint = (-.35, 1.027), (0., .327)
    yaw = math.atan2(endpoint[1] - sensor[1], endpoint[0] - sensor[0])
    distance = math.hypot(endpoint[0] - sensor[0], endpoint[1] - sensor[1])
    cases.append({"id": "rotated_vertex_single_axis_tie_nonzero_direction", "rectangles": [(-.2 * math.sqrt(2), .327, math.pi / 4, .4, .4)],
                  "input_scope": "prescribed exact artificial vertex grazing, no actual scene or ray simulation",
                  "scans": [scan(i, (*sensor, yaw), [0.], [distance], input_kind="single-axis tie at rotated convex vertex") for i in (1, 2, 3)]})
    for name, pose, distance, rectangle in (
        ("raw_ambiguity_before_side_clipping", (-2., .025, 0.), .8, (-1.1, .025, 0., .2, .2)),
        ("raw_ambiguity_before_corner_clipping", (-2., -1.2, 0.), .8, (-1.1, -1.1, 0., .2, .2)),
    ):
        cases.append({"id": name, "rectangles": [rectangle],
                      "scans": [scan(i, pose, [0.], [distance], input_kind="raw alternatives include out-of-map cells") for i in (1, 2, 3)]})

    for family, pose, distance in (
        ("closed_two_cell_conflict", (-.8, .025, 0.), .8),
        ("closed_four_cell_conflict", (-.8, -.8, math.pi / 4), .8 * math.sqrt(2)),
    ):
        for order, ranges in (("hit_first", [distance, 10.]), ("free_first", [10., distance])):
            cases.append({"id": family + "_" + order, "rectangles": [( .1, .1, 0., .2, .2)],
                          "permutation_pair": family,
                          "scans": [scan(i, pose, [0., 0.], ranges, input_kind="closed alternatives versus same-scan free") for i in (1, 2)]})
    for order, ranges in (("unique_first", [.801, .8]), ("ambiguous_first", [.8, .801])):
        cases.append({"id": "unique_and_ambiguous_overlap_" + order, "rectangles": [( .1, .025, 0., .2, .2)],
                      "permutation_pair": "unique_and_ambiguous_overlap",
                      "scans": [scan(i, (-.8, .025, 0.), [0., 0.], ranges,
                                     input_kind="a separate unique hit may retain positive evidence within ambiguous alternatives") for i in (1, 2)]})
    cases.append({"id": "off_grid_ghost_recovery", "rectangles": [], "watch_cells_row_column": [[24, 19]],
                  "scans": [scan(i, (-.8, .025, 0.), [0.], [.551 if i <= 2 else 10.],
                                 input_kind="non-tie transient object followed by independent free") for i in range(1, 11)]})
    cases.append({"id": "prior_positive_retained_by_ambiguous_hit", "rectangles": [( .1, .025, 0., .2, .2)],
                  "watch_cells_row_column": [[24, 23], [24, 24]],
                  "scans": [scan(i, (-.8, .025, 0.), [0.], [.801 if i <= 2 else .8],
                                 input_kind="two unique hits, then ambiguous hits; retain old positive without adding neighbors") for i in (1, 2, 3, 4)]})
    return cases


def _closed_support(old, scan):
    """Independent scalar closed-cell oracle; no mapper private method calls."""
    support, unique, ambiguous, raw_sizes, clipped_sizes = set(), set(), set(), [], []
    sx, sy, yaw = scan["sensor_pose"]
    for angle, distance in zip(scan["angles"], scan["ranges"]):
        if distance >= scan["range_max"]:
            continue
        coordinates = ((sx - old.ORIGIN[0]) / old.RESOLUTION + math.cos(angle + yaw) * distance / old.RESOLUTION,
                       (sy - old.ORIGIN[1]) / old.RESOLUTION + math.sin(angle + yaw) * distance / old.RESOLUTION)
        axes = []
        for value in coordinates:
            nearest = round(value)
            axes.append([nearest - 1, nearest] if abs(value - nearest) <= 4 * math.ulp(max(1., abs(value)))
                        else [math.floor(value)])
        raw = {(row, column) for column in axes[0] for row in axes[1]}
        clipped = {(row, column) for row, column in raw if 0 <= row < old.SHAPE[0] and 0 <= column < old.SHAPE[1]}
        support |= clipped
        (unique if len(raw) == 1 else ambiguous).update(clipped)
        raw_sizes.append(len(raw)); clipped_sizes.append(len(clipped))
    return support, unique, ambiguous, raw_sizes, clipped_sizes


def _cells_json(cells):
    return [list(cell) for cell in sorted(cells)]


def _compare_case(old, helper, mapping2, mapping3, case):
    truth = helper.artificial_truth(case["rectangles"], old.BOUNDS)
    truth.roi_mask = np.ones_like(truth.occupied)
    models = {"v1": helper.measurement_container(truth, case["scans"][0]["angles"]),
              "v2": mapping2.SensorMapperV2(old.SHAPE, old.RESOLUTION, old.ORIGIN),
              "v3": mapping3.SensorMapperV3(old.SHAPE, old.RESOLUTION, old.ORIGIN)}
    result = {key: value for key, value in case.items() if key != "scans"}
    result.update(truth_occupied_cells=int(truth.occupied.sum()), truth_free_cells=int((~truth.occupied).sum()),
                  truth_occupied_sha256=old._sha(truth.occupied), checkpoints=[])
    previous_id, previous_v3 = None, None
    for index, scan in enumerate(case["scans"], 1):
        support, unique, ambiguous, raw_sizes, clipped_sizes = _closed_support(old, scan)
        before3 = models["v3"].evidence()
        checkpoint = {"index": index, "input": scan, "input_arrays_unchanged": True,
                      "closed_support_oracle": {"in_map_row_column": _cells_json(support),
                          "unique_row_column": _cells_json(unique), "ambiguous_row_column": _cells_json(ambiguous),
                          "raw_alternative_counts": raw_sizes, "clipped_alternative_counts": clipped_sizes}}
        digests = []
        for name, model in models.items():
            pose, angles, ranges = old._arguments(scan)
            digest = old._argument_digest(pose, angles, ranges)
            digests.append(digest)
            if name == "v1":
                old._v1_integrate(helper, model, scan, pose, angles, ranges)
                grid = model._maps["sensor"]
                data = {"persistent_buffer_bytes": old._v1_memory(model)}
            else:
                accepted = model.integrate(scan["scan_id"], pose, angles, ranges,
                                           range_min=scan["range_min"], range_max=scan["range_max"])
                grid, evidence = model.grid(), model.evidence()
                data = {"new_scan_accepted": bool(accepted), "evidence_sha256": old._sha(evidence),
                        "evidence_min": int(evidence.min()), "evidence_max": int(evidence.max()),
                        "persistent_buffer_bytes": model.memory_bytes}
            assert digest == old._argument_digest(pose, angles, ranges)
            checkpoint[name] = {**old._quality(helper, truth, grid), **data}
        assert len(set(digests)) == 1
        checkpoint["identical_detached_inputs_sha256"] = digests[0]
        grid3, after3 = models["v3"].grid(), models["v3"].evidence()
        ambiguous_only = ambiguous - unique
        flags = {
            "current_hit_support_is_not_free": all(grid3[cell] != 0 for cell in support),
            "ambiguous_only_cells_add_no_positive_evidence": all(after3[cell] <= max(int(before3[cell]), 0) for cell in ambiguous_only),
            "ambiguous_only_nonpositive_history_does_not_become_occupied": all(grid3[cell] != 100 for cell in ambiguous_only if before3[cell] <= 0),
            "latest_exact_duplicate_is_idempotent": (scan["scan_id"] != previous_id
                or (not checkpoint["v3"]["new_scan_accepted"] and old._sha(after3) == previous_v3)),
        }
        checkpoint["v3_technical_flags"] = flags
        checkpoint["watched_v3_cells"] = [{"row_column": cell, "grid_value": int(grid3[tuple(cell)]),
                                             "evidence": int(after3[tuple(cell)])}
                                            for cell in case.get("watch_cells_row_column", [])]
        result["checkpoints"].append(checkpoint)
        previous_id, previous_v3 = scan["scan_id"], old._sha(after3)
    return result


def _decision_flags(cases):
    by_id = {case["id"]: case for case in cases}
    flags = {"all_checkpoint_structural_invariants": all(all(cp["v3_technical_flags"].values())
                                                         for case in cases for cp in case["checkpoints"])}
    for field in ("identical_input_pair", "permutation_pair"):
        groups = {}
        for case in cases:
            if field in case:
                groups.setdefault(case[field], []).append(case)
        for name, group in groups.items():
            first, second = group
            if field == "identical_input_pair":
                flags[name + "_same_inputs"] = ([cp["input"]["input_sha256"] for cp in first["checkpoints"]]
                                                == [cp["input"]["input_sha256"] for cp in second["checkpoints"]])
            for version in ("v1", "v2", "v3"):
                flags[name + "_" + version + "_same_output"] = all(
                    left[version]["grid_sha256"] == right[version]["grid_sha256"]
                    and (version == "v1" or left[version]["evidence_sha256"] == right[version]["evidence_sha256"])
                    for left, right in zip(first["checkpoints"], second["checkpoints"]))
    watched = by_id["off_grid_hit_persistent_veto_while_unseen"]["checkpoints"]
    flags["first_off_grid_hit_rebases_free_to_unknown"] = watched[4]["watched_v3_cells"][0]["grid_value"] == -1
    flags["unseen_and_duplicate_keep_persistent_veto"] = all(cp["watched_v3_cells"] == watched[4]["watched_v3_cells"] for cp in watched[5:7])
    flags["next_off_grid_hit_can_become_occupied"] = watched[7]["watched_v3_cells"][0]["grid_value"] == 100
    watched = by_id["ambiguous_hit_persistent_veto_while_unseen"]["checkpoints"]
    flags["ambiguous_free_history_stays_unknown_through_repeats_and_unseen"] = all(
        all(cell["grid_value"] == -1 for cell in cp["watched_v3_cells"]) for cp in watched[4:])
    for name in ("raw_ambiguity_before_side_clipping", "raw_ambiguity_before_corner_clipping"):
        checkpoint = by_id[name]["checkpoints"][0]
        oracle = checkpoint["closed_support_oracle"]
        flags[name + "_really_has_raw_ambiguity_and_one_clipped_cell"] = oracle["raw_alternative_counts"][0] > 1 and oracle["clipped_alternative_counts"][0] == 1
        flags[name + "_adds_no_occupied"] = all(cp["v3"]["counts"]["TP"] + cp["v3"]["counts"]["FP"] == 0 for cp in by_id[name]["checkpoints"])
    ghost = by_id["off_grid_ghost_recovery"]["checkpoints"]
    flags["ordinary_non_tie_hit_is_usable"] = ghost[0]["watched_v3_cells"][0]["grid_value"] == 100
    flags["ordinary_ghost_can_become_free"] = ghost[-1]["watched_v3_cells"][0]["grid_value"] == 0
    flags["ordinary_nohit_can_make_free"] = by_id["max_range_nohit_only"]["checkpoints"][-1]["v3"]["counts"]["TN"] > 0
    flags["off_grid_faces_can_still_make_occupied"] = by_id["four_faces_off_grid"]["checkpoints"][-1]["v3"]["counts"]["TP"] > 0
    return flags


def _timing(old, helper, mapping2, mapping3):
    angles, ranges = np.linspace(0., 6.28, 360), np.full(360, .7)
    rounds = []
    for kind in ("duplicate_same_scan", "new_scan_same_geometry"):
        scans = [old._scan(1 if kind == "duplicate_same_scan" else i, (0., 0., .13), angles, ranges) for i in range(1, 13)]
        for number in range(3):
            order = ("v1", "v2", "v3")[number:] + ("v1", "v2", "v3")[:number]
            entry = {"kind": kind, "round": number + 1, "implementation_order": list(order)}
            for name in order:
                if name == "v1":
                    mapper = helper.measurement_container(helper.artificial_truth([], old.BOUNDS), angles)
                else:
                    cls = mapping2.SensorMapperV2 if name == "v2" else mapping3.SensorMapperV3
                    mapper = cls(old.SHAPE, old.RESOLUTION, old.ORIGIN)
                durations, accepted = [], []
                for scan in scans:
                    pose, a, r = old._arguments(scan)
                    digest = old._argument_digest(pose, a, r)
                    if name == "v1":
                        mapper._angles, mapper._laser["range_max"] = a, scan["range_max"]
                        started = time.perf_counter_ns()
                        helper.ProxyWorld._integrate_scan(mapper, "sensor", pose, r)
                        durations.append(time.perf_counter_ns() - started)
                    else:
                        started = time.perf_counter_ns()
                        value = mapper.integrate(scan["scan_id"], pose, a, r, range_min=old.RANGE_MIN, range_max=old.RANGE_MAX)
                        durations.append(time.perf_counter_ns() - started)
                        accepted.append(bool(value))
                    assert digest == old._argument_digest(pose, a, r)
                grid = mapper._maps["sensor"] if name == "v1" else mapper.grid()
                entry[name] = {"integrate_calls": 12, "integrate_nanoseconds_each": durations,
                               "total_integrate_nanoseconds": sum(durations), "final_grid_sha256": old._sha(grid),
                               "persistent_buffer_bytes": old._v1_memory(mapper) if name == "v1" else mapper.memory_bytes,
                               "new_scan_accepted": accepted if name != "v1" else None}
            rounds.append(entry)
    return {"shape": list(old.SHAPE), "resolution": old.RESOLUTION, "origin": list(old.ORIGIN),
            "rays_per_scan": 360, "calls_per_model_round": 12, "rounds_per_kind": 3,
            "angles_definition": "np.linspace(0.,6.28,360)", "ranges_m": .7, "sensor_pose": [0., 0., .13],
            "scope": "artificial integrate calls only; no ENV throughput or equal-semantics speedup claim",
            "memory_scope": "persistent score/map/cache/payload buffers; excludes Python objects and transient workspace; not RSS",
            "rounds": rounds}


def run_comparison():
    from multi_robot_exploration import mr3_proxy2d_mapping as mapping2
    from multi_robot_exploration import mr3_proxy2d_mapping_v3 as mapping3
    old, old_path = _legacy()
    helper, helper_path = old._helpers()
    assert (mapping2.MODEL, mapping2.HIT_INCREMENT, mapping2.FREE_DECREMENT, mapping2.EVIDENCE_LIMIT,
            mapping2.OCCUPIED_THRESHOLD, mapping2.FREE_THRESHOLD, mapping2.TIE_ULPS, mapping2.MAX_RAY_SAMPLES) == (
                "range_ray_bounded_evidence_v2", 2, 1, 4, 2, -2, 4, 8_000_000)
    assert mapping3.MODEL == V3_MODEL
    legacy = old._cases(helper)
    manifest = [{"id": case["id"], "input_sha256": [scan["input_sha256"] for scan in case["scans"]]} for case in legacy]
    assert hashlib.sha256(old._canonical(manifest)).hexdigest() == LEGACY_INPUT_MANIFEST_SHA256
    cases = legacy + _new_cases(old)
    assert len(legacy) == 14 and len(cases) == 31
    source_paths = [Path(__file__).resolve(), old_path.resolve(), helper_path.resolve(),
                    Path(mapping2.__file__).resolve(), Path(mapping3.__file__).resolve(),
                    Path(helper.mr3_proxy2d_world.__file__).resolve(), Path(helper.mr3_task_contract.__file__).resolve(),
                    Path(helper.task_evaluator.__file__).resolve()]
    before = {str(path): path.read_bytes() for path in source_paths}
    tail = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    report = {"schema": "mr3-proxy2d-mapping-v1-v2-v3-artificial-comparison-v1",
              "scope": "fixed source-bound synthetic comparison; technical flags and completed are not task PASS",
              "legacy_fixture_source_sha256": LEGACY_SOURCE_SHA256,
              "legacy_input_manifest_sha256": LEGACY_INPUT_MANIFEST_SHA256,
              "legacy_cases": 14, "new_cases": 17,
              "consumer_identity": {"pid": os.getpid(), "parent": os.getppid(), "group": os.getpgrp(),
                                    "session": os.getsid(0), "start_ticks": int(tail[19])},
              "fixed_v2_parameters": old.FIXED_V2,
              "fixed_v3_rule": {"model": V3_MODEL, "same_score_parameters_as_v2": True,
                                "ties": "closed alternatives on every 4ULP axis, including zero direction; uniqueness before clipping",
                                "votes": "unique hit +2; ambiguous hit adds no occupied evidence; all support excluded from free",
                                "persistent_veto": "after votes, score[C]=max(score[C],0); old positive evidence retained"},
              "original_quality_gates": dict(helper.QUALITY), "cases": [], "errors": [], "completed": False,
              "qualification": False, "training_eligible": False, "native_credit": False,
              "worlds_created": 0, "nodes_created": 0, "episodes": 0, "actor_calls": 0,
              "reward_replays": 0, "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}
    for case in cases:
        try:
            report["cases"].append(_compare_case(old, helper, mapping2, mapping3, case))
        except Exception as error:
            report["errors"].append({"case": case["id"], "error": f"{type(error).__name__}: {error}"})
    try:
        report["artificial_timing"] = _timing(old, helper, mapping2, mapping3)
        if len(report["cases"]) == len(cases):
            report["decision_flags"] = _decision_flags(report["cases"])
    except Exception as error:
        report["errors"].append({"phase": "timing_or_flags", "error": f"{type(error).__name__}: {error}"})
    report["technical_invariants_all_true"] = bool(report.get("decision_flags")) and all(report.get("decision_flags", {}).values())
    report["source_bindings"] = {path: {"sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)} for path, payload in before.items()}
    report["bound_source_bytes_unchanged"] = all(Path(path).read_bytes() == payload for path, payload in before.items())
    if not report["bound_source_bytes_unchanged"]:
        report["errors"].append({"phase": "source", "error": "bound source bytes changed"})
    report["completed"] = not report["errors"] and len(report["cases"]) == 31
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output.exists():
        raise FileExistsError(args.output)
    result = run_comparison()
    with args.output.open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return 0 if result["completed"] and result["technical_invariants_all_true"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
