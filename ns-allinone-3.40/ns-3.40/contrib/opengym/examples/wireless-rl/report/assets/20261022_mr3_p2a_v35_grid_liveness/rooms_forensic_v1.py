"""Bounded V34 rooms101 received-input geometry inspection; never an episode.

Decode at most three archived actor calls: reset, first tb3 cell-gate rejection,
last actor (overlaps share one selection, without replacement). No private
journal, truth, World, Node, scan reconstruction or historical audit is read.
The source freeze is supplied by the owning external runner; this program
records helper bytes but does not manufacture native/task qualification.
"""
import argparse
import gzip
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
from unittest.mock import patch


ROOT = Path("/home/zhuyulab/ns3-workspace")
PACKAGE = ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration"
CODEC = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/proxy2d_codec.py"
EVIDENCE_FREEZE = "7816cced7067c4505bd2874f0ad323cbb4fad85e"
RULE = "exact-point-bridge-v2"
MAX_EVENTS = 130
MAX_DECODED_INPUTS = 3
MAX_FILE_BYTES = 16_000_000
MAX_LINE_BYTES = 4_000_000
MAX_INPUT_BYTES = 8_000_000
SOURCE_NAMES = ("mr3_observation.py", "mr3_seed_certificate.py",
                "mr3_proxy2d_navigation.py", "mr3_reach_geometry.py", "mr3_episode.py")
PARAMETERS = {"raw_grid", "resolution", "origin", "robots", "now", "epoch", "map_version",
              "sequence", "map_source_stamp", "map_received_stamp", "map_sources", "task_start",
              "robot_maps", "navigation_maps", "seed_rule"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def identity():
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": os.getpid(), "parent": int(fields[1]), "group": int(fields[2]),
            "session": int(fields[3]), "start_ticks": int(fields[19])}


def read_limited(path, limit=MAX_FILE_BYTES):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "file byte limit exceeded")
    return raw


def decompress_limited(raw, limit):
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        result = stream.read(limit + 1)
    require(len(result) <= limit, "decompressed byte limit exceeded")
    return result


def trace_rows(raw):
    rows, consumed = [], 0
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        for index in range(MAX_EVENTS):
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                return rows
            consumed += len(line)
            require(len(line) <= MAX_LINE_BYTES and consumed <= 32_000_000, "trace byte limit exceeded")
            row = json.loads(line)
            require(row.get("schema") == "mr3-proxy2d-trace-v1", "unexpected trace schema")
            require(type(row.get("event_sequence")) is int and row["event_sequence"] == index + 1,
                    "noncontiguous trace event sequence")
            require(row.get("event") in ("reset", "step_attempt", "step_return", "step_error", "close"),
                    "unexpected trace event")
            rows.append(row)
        # At most one extra byte is inspected, never a 131st event decoded.
        require(not stream.read(1), "trace exceeds 130 events")
    return rows


def select_actors(rows):
    actors = [(index + 1, row) for index, row in enumerate(rows)
              if row["event"] in ("reset", "step_return")]
    resets = [(index, row) for index, row in actors if row["event"] == "reset"]
    require(len(resets) == 1 and actors, "exactly one reset actor required")
    rejected = [(index, row) for index, row in actors if row.get("snapshot", {}).get(
        "path_maps", {}).get("tb3", {}).get("seed_rejection_reason") == "seed_cell_body_clearance"]
    require(rejected, "declared tb3 cell rejection absent; do not substitute another selection")
    selected = {}
    for role, (index, row) in (("reset", resets[0]), ("first_tb3_seed_cell_body_clearance", rejected[0]),
                              ("last_actor", actors[-1])):
        entry = selected.setdefault(index, {"trace_line_1based": index, "row": row, "roles": []})
        entry["roles"].append(role)
    require(len(selected) <= MAX_DECODED_INPUTS, "actor selection budget exceeded")
    return list(selected.values())


def load_helpers():
    # Only pure received-geometry modules, never world, worker or evaluator.
    from multi_robot_exploration import mr3_observation as obs
    from multi_robot_exploration import mr3_proxy2d_navigation as nav
    from multi_robot_exploration import mr3_seed_certificate as cert
    spec = importlib.util.spec_from_file_location("mr3_v34_forensic_codec", CODEC)
    codec = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(codec)
    require(Path(obs.__file__).resolve() == PACKAGE / "mr3_observation.py"
            and Path(nav.__file__).resolve() == PACKAGE / "mr3_proxy2d_navigation.py"
            and Path(cert.__file__).resolve() == PACKAGE / "mr3_seed_certificate.py",
            "pure helper resolved outside canonical source")
    return obs, nav, cert, codec


def decode_reference(episode, row, codec):
    reference = row["actor_input_ref"]
    relative = reference.get("path")
    require(isinstance(relative, str) and re.fullmatch(r"inputs/[0-9a-f]{64}\.json\.gz", relative),
            "actor input is not content addressed")
    path = (episode / relative).resolve()
    require(path.is_relative_to(episode), "actor input escaped episode")
    raw = read_limited(path)
    unpacked = decompress_limited(raw, MAX_INPUT_BYTES)
    encoded = json.loads(unpacked)
    require(canonical(encoded) == unpacked and digest(unpacked) == reference.get("sha256")
            == Path(relative).name.removesuffix(".json.gz"), "actor bytes/digest differ")
    require(isinstance(encoded, dict) and set(encoded) <= PARAMETERS, "unknown actor parameter")
    params = codec.decode_arrays(encoded)
    snapshot = row["snapshot"]
    require(params.get("seed_rule") == RULE and snapshot["candidate_rule"].get("seed_rule") == RULE,
            "wrong seed rule")
    require(params["epoch"] == row["epoch"] == snapshot["epoch"]
            and params["sequence"] == snapshot["sequence"]
            and params["map_version"] == snapshot["map_version"]
            and params["now"] == snapshot["source_stamp"], "actor identity differs")
    return params, {"path": str(path), "compressed_sha256": digest(raw),
                    "canonical_sha256": digest(unpacked), "canonical_bytes": len(unpacked)}


def analyse_params(params, snapshot, helpers):
    obs, nav, cert, _ = helpers
    robots = {robot["name"]: robot for robot in params["robots"]}
    require(set(robots) == {"tb1", "tb2", "tb3"}, "three received robots required")
    state = robots["tb3"]
    received = params["navigation_maps"]["tb3"]
    require(received.get("composition_version") == obs.NAVIGATION_COMPOSITION_VERSION,
            "wrong delivered navigation composition")
    grid = obs._received_grid(received["grid"])
    require(bool(grid.size), "empty received navigation map")
    res, origin, pose = received["resolution"], received["origin"], (state["x"], state["y"])
    cell = cert.canonical_seed_cell(pose, res, origin, grid.shape)
    traversable, clearance = obs.native_traversable(grid, res)
    point = cert.certify_estimated_segment(grid, res, origin, pose, pose)
    current = {"canonical_cell": None if cell is None else list(cell), "value": None,
               "traversable": False, "cell_lower_bound_m": None, "pose_offset_m": None,
               "legacy_pose_lower_bound_m": None}
    bridge, geometry_bridge, centre = None, None, None
    if cell is not None:
        centre = cert.canonical_cell_centre(cell, res, origin)
        offset = obs._point_offset(pose, cell, res, origin)
        current.update(value=int(grid[cell]), traversable=bool(traversable[cell]),
                       cell_lower_bound_m=float(clearance[cell]), pose_offset_m=offset,
                       legacy_pose_lower_bound_m=float(clearance[cell]) - offset)
        bridge = cert.certify_seed_pose_bridge(grid, res, origin, pose, cell,
            seed_cell_traversable=bool(traversable[cell]))
        # Explicitly a counterfactual geometry measurement, never an override
        # of the actual seed-cell/graph gate preserved in `bridge` above.
        geometry_bridge = cert.certify_estimated_segment(grid, res, origin, pose, centre)
    ownership = state.get("navigation", {})
    goal = (None if ownership.get("goal_x") is None or ownership.get("goal_y") is None else
            {"x": ownership["goal_x"], "y": ownership["goal_y"]})
    active = (ownership.get("phase") == "active" and bool(ownership.get("goal_id"))
              and not ownership.get("cancel_requested", False))
    arrived = goal is not None and math.hypot(goal["x"] - pose[0], goal["y"] - pose[1]) <= obs.GOAL_XY_TOLERANCE_M
    path = {"status": None, "target_cell": None, "target_traversable": None,
            "seed_field_m": None, "seed_field_finite": False, "finite_graph_cells": None,
            "seed_field_condition": "no_goal", "nodes_1_to_5": [], "whole_segments_longest_first": [],
            "selected_waypoint": None, "proposal": None, "nominal_output_before_scan_pair": None}
    # Inspect the unchanged goal field even if the cell gate rejects execution.
    # A rejected cell is not a graph node; call this undefined, not disconnected.
    field = None
    if goal is not None:
        target = obs._cell(goal["x"], goal["y"], res, origin, grid.shape)
        path["target_cell"] = None if target is None else list(target)
        path["target_traversable"] = target is not None and bool(traversable[target])
        distances, ids = obs._path_distances(traversable, [target], res)
        field = nav.np.full(grid.shape, nav.np.inf)
        field[ids >= 0] = distances[0, ids[ids >= 0]]
        path["finite_graph_cells"] = int(nav.np.count_nonzero(nav.np.isfinite(field)))
        if cell is None:
            path["seed_field_condition"] = "outside_map"
        elif not traversable[cell]:
            path["seed_field_condition"] = "seed_is_not_original_graph_node"
        elif math.isfinite(field[cell]):
            path.update(seed_field_condition="finite", seed_field_finite=True, seed_field_m=float(field[cell]))
        else:
            path["seed_field_condition"] = "disconnected" if path["target_traversable"] else "goal_cell_unavailable"
    if not active or goal is None:
        path["status"] = "no_snapshot_active_goal"
    elif arrived:
        path["status"] = "within_original_goal_tolerance"
    elif cell is None or not traversable[cell]:
        path["status"] = "original_seed_cell_gate_rejected_not_graph_disconnection"
        path["nominal_output_before_scan_pair"] = [0., 0.]
    else:
        if not math.isfinite(field[cell]):
            path["status"] = "graph_disconnected" if path["target_traversable"] else "goal_cell_unavailable"
            path["nominal_output_before_scan_pair"] = [0., 0.]
        else:
            nodes = nav._lookahead_cells(traversable, field, cell)
            path["nodes_1_to_5"] = [list(node) for node in nodes]
            waypoint = None
            for node in reversed(nodes):
                endpoint = cert.canonical_cell_centre(node, res, origin)
                proof = cert.certify_estimated_segment(grid, res, origin, pose, endpoint)
                path["whole_segments_longest_first"].append({"cell": list(node), "certificate": proof})
                if proof["accepted"]:
                    waypoint = endpoint
                    path["selected_waypoint"] = {"source": "original_supplied_goal_path", "cell": list(node)}
                    break
            if waypoint is None and bridge["accepted"]:
                waypoint = centre
                path["selected_waypoint"] = {"source": "same_canonical_seed_centre", "cell": list(cell)}
            if waypoint is None:
                path["status"] = "all_route_and_same_seed_bridge_rejected"
                path["nominal_output_before_scan_pair"] = [0., 0.]
            else:
                # Observe the frozen local controller's own proposed segment;
                # no command is applied and no world object is constructed.
                proposals = []
                def record_proposal(*args, **kwargs):
                    proof = cert.certify_estimated_segment(*args, **kwargs)
                    proposals.append({"start_exact": [str(cert._number(v)) for v in args[3]],
                                      "end_exact": [str(cert._number(v)) for v in args[4]], "certificate": proof})
                    return proof
                controller = nav.ProxyNavigator(seed_rule=RULE)
                with patch.object(nav, "certify_estimated_segment", side_effect=record_proposal):
                    output = controller._exact_waypoint_velocity("tb3", state, received, waypoint)
                require(len(proposals) <= 1, "unexpected multiple motion proposals")
                path["proposal"] = proposals[0] if proposals else None
                path["nominal_output_before_scan_pair"] = list(output)
                path["status"] = ("nominal_straight_proposal_passed" if output[0] > 0 else
                                  "nominal_rotate_only" if output[1] else "nominal_geometry_or_length_stop")
    if not point["accepted"]:
        finding = "estimated_point_fails_exact_received_square_threshold"
    elif not current["traversable"] and geometry_bridge and geometry_bridge["accepted"]:
        finding = "original_cell_bound_rejects_but_exact_point_and_same_centre_segment_pass"
    elif geometry_bridge and not geometry_bridge["accepted"]:
        finding = "estimated_point_passes_but_same_centre_segment_fails"
    else:
        finding = path["status"]
    return {"robot": "tb3", "now": params["now"], "received_pose_exact": [str(cert._number(v)) for v in pose],
            "received_yaw": state["yaw"], "state_source_stamp": state.get("source_stamp"),
            "state_received_stamp": state.get("received_stamp"), "snapshot_seed_diagnostic": snapshot["path_maps"]["tb3"],
            "navigation_map": {"shape": list(grid.shape), "dtype": grid.dtype.str,
                "grid_bytes_sha256": digest(grid.tobytes(order="C")), "resolution_exact": str(cert._number(res)),
                "origin_exact": [str(cert._number(v)) for v in origin], **{k: received.get(k) for k in (
                    "epoch", "sequence", "version", "source_stamp", "received_stamp", "payload_sha256")}},
            "original_cell": current, "exact_point": point, "original_gate_bridge": bridge,
            "geometry_only_same_centre_segment_no_cell_admission": geometry_bridge,
            "snapshot_goal_context": {"active_owner": active, "arrived": arrived, "navigation": ownership},
            "local_path_execution": path, "finding": finding,
            "unavailable_actual_gates": ["20ms received states and applied commands not archived",
                "local forward scan not archived", "actual per-quantum peer command directions not archived"],
            "qualification": "received-grid nominal geometry only; no graph override, command replay, task/native credit"}


def inspect_episode(episode, source_freeze, helpers=None):
    episode = Path(episode).resolve()
    require(re.fullmatch(r"[0-9a-f]{40}", source_freeze) is not None, "exact source freeze required")
    metadata_raw = read_limited(episode / "episode.json", 1_000_000)
    metadata = json.loads(metadata_raw)
    require(metadata.get("scene") == "rooms" and type(metadata.get("seed")) is int
            and metadata["seed"] == 101 and metadata.get("freeze") == EVIDENCE_FREEZE
            and metadata.get("seed_rule") == RULE and metadata.get("mapper") == "karto",
            "not the declared V34 rooms101 evidence")
    trace_path = episode / "trace.jsonl.gz"
    trace_raw = read_limited(trace_path)
    rows = trace_rows(trace_raw)
    require(all(row.get("epoch") == metadata["epoch"] for row in rows), "trace mixes epochs")
    selected = select_actors(rows)
    helpers = load_helpers() if helpers is None else helpers
    results, references, cache = [], [], {}
    for entry in selected:
        row = entry["row"]
        require(row.get("epoch") == metadata["epoch"], "actor belongs to another epoch")
        key = row["actor_input_ref"]["sha256"]
        if key not in cache:
            require(len(cache) < MAX_DECODED_INPUTS, "actor decoding budget exceeded")
            cache[key] = decode_reference(episode, row, helpers[3])
        params, reference = cache[key]
        references.append(reference)
        results.append({"roles": entry["roles"], "trace_line_1based": entry["trace_line_1based"],
            "event_sequence": row["event_sequence"], "event": row["event"], "actor_input_ref": reference,
            "snapshot_canonical_sha256": digest(canonical(row["snapshot"])),
            "geometry": analyse_params(params, row["snapshot"], helpers)})
    return {"schema": "mr3-v34-rooms-received-geometry-forensic-v1", "source_freeze": source_freeze,
            "evidence_freeze": EVIDENCE_FREEZE, "scene": "rooms", "seed": 101, "epoch": metadata["epoch"],
            "limits": {"trace_events": MAX_EVENTS, "decoded_actor_inputs": MAX_DECODED_INPUTS},
            "actual": {"trace_events": len(rows), "selected_actors": len(results), "decoded_actor_inputs": len(cache)},
            "trace_metadata": {"epoch": metadata["epoch"], "env_id": metadata.get("env_id"),
                "episode_index": metadata.get("episode_index"), "scene": metadata["scene"], "seed": metadata["seed"],
                "evidence_freeze": metadata["freeze"], "first_event_sequence": rows[0]["event_sequence"],
                "last_event_sequence": rows[-1]["event_sequence"]},
            "selection": "reset / first tb3 seed_cell_body_clearance / last actor; deduplicate, never replace",
            "input_index": [{"path": str(episode / "episode.json"), "sha256": digest(metadata_raw)},
                            {"path": str(trace_path), "sha256": digest(trace_raw)}, *references],
            "records": results, "scope": "no private truth, World, scans, episode replay, training or qualification"}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode", type=Path, required=True)
    parser.add_argument("--source-freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Exclusive output claim precedes all evidence reads; failures stay visible.
    with args.output.open("x") as stream:
        own_identity = identity()
        sources = [Path(__file__).resolve(), CODEC, *(PACKAGE / name for name in SOURCE_NAMES)]
        before = {str(path): digest(read_limited(path)) for path in sources}
        try:
            result = inspect_episode(args.episode, args.source_freeze)
            after = {str(path): digest(read_limited(path)) for path in sources}
            require(before == after, "forensic helper source changed during inspection")
            result.update(source_bindings=before, source_stable=True, identity=own_identity)
        except Exception as error:
            stream.write(json.dumps({"schema": "mr3-v34-rooms-received-geometry-forensic-v1", "error": repr(error),
                                     "source_bindings": before, "identity": own_identity,
                                     "qualification": False}, indent=2) + "\n")
            raise
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
