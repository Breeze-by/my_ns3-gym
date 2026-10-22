"""Artificial schema/files only; no original evidence, World or ROS object."""
from fractions import Fraction as Q
import gzip
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch

import numpy as np
import pytest


spec = importlib.util.spec_from_file_location("v34_rooms_forensic_fixture", Path(__file__).with_name("rooms_forensic_v1.py"))
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def event(sequence, kind="step_attempt", reason=None):
    return {"schema": "mr3-proxy2d-trace-v1", "event_sequence": sequence, "event": kind,
            "epoch": "artificial", "snapshot": {"path_maps": {"tb3": {"seed_rejection_reason": reason}}}}


def write_episode(tmp_path, reasons=(None, "seed_cell_body_clearance", None)):
    episode = tmp_path / "artificial_episode"
    (episode / "inputs").mkdir(parents=True)
    metadata = {"epoch": "artificial", "scene": "rooms", "seed": 101, "freeze": f.EVIDENCE_FREEZE,
                "seed_rule": f.RULE, "mapper": "karto", "env_id": 1, "episode_index": 1}
    (episode / "episode.json").write_text(json.dumps(metadata))
    rows = []
    for index, reason in enumerate(reasons, 1):
        if index > 1:
            rows.append(event(len(rows) + 1))
        params = {"epoch": "artificial", "sequence": index, "map_version": 1,
                  "now": float(index), "seed_rule": f.RULE, "raw_grid": [[0]],
                  "resolution": .05, "origin": [0, 0], "robots": [], "navigation_maps": {}}
        raw = f.canonical(params)
        sha = f.digest(raw)
        (episode / "inputs" / (sha + ".json.gz")).write_bytes(gzip.compress(raw))
        row = event(len(rows) + 1, "reset" if index == 1 else "step_return", reason)
        row["actor_input_ref"] = {"path": "inputs/" + sha + ".json.gz", "sha256": sha}
        row["snapshot"].update(epoch="artificial", sequence=index, map_version=1,
                               source_stamp=float(index), candidate_rule={"seed_rule": f.RULE})
        rows.append(row)
    rows.append(event(len(rows) + 1, "close"))
    (episode / "trace.jsonl.gz").write_bytes(gzip.compress(b"".join(f.canonical(row) + b"\n" for row in rows)))
    return episode, rows


def test_fixed_three_selections_and_input_sha_are_retained(tmp_path, monkeypatch):
    episode, _ = write_episode(tmp_path)
    decoded = []
    def decode(value):
        decoded.append(value["sequence"])
        return value
    monkeypatch.setattr(f, "analyse_params", lambda params, snapshot, helpers: {"sequence": params["sequence"]})
    result = f.inspect_episode(episode, "a" * 40, (None, None, None, NS(decode_arrays=decode)))
    assert decoded == [1, 2, 3]
    assert result["actual"] == {"trace_events": 6, "selected_actors": 3, "decoded_actor_inputs": 3}
    assert [row["trace_line_1based"] for row in result["records"]] == [1, 3, 5]
    assert [row["roles"] for row in result["records"]] == [
        ["reset"], ["first_tb3_seed_cell_body_clearance"], ["last_actor"]]
    for row in result["records"]:
        reference = row["actor_input_ref"]
        raw = gzip.decompress(Path(reference["path"]).read_bytes())
        assert f.digest(raw) == reference["canonical_sha256"]
    assert result["trace_metadata"]["last_event_sequence"] == 6


def test_overlapping_selection_is_deduplicated_without_replacement():
    rows = [event(1, "reset", "seed_cell_body_clearance"), event(2, "close")]
    selected = f.select_actors(rows)
    assert len(selected) == 1
    assert selected[0]["roles"] == ["reset", "first_tb3_seed_cell_body_clearance", "last_actor"]


def test_missing_first_declared_rejection_does_not_substitute_other_actor():
    with pytest.raises(ValueError, match="declared tb3"):
        f.select_actors([event(1, "reset"), event(2, "step_return"), event(3, "close")])


def test_130th_close_is_valid_but_131st_event_is_never_decoded():
    rows = [event(index, "reset" if index == 1 else "close" if index == 130 else "step_attempt")
            for index in range(1, 131)]
    raw = b"".join(f.canonical(row) + b"\n" for row in rows)
    assert f.trace_rows(gzip.compress(raw))[-1]["event"] == "close"
    with patch.object(f.json, "loads", wraps=json.loads) as loads:
        with pytest.raises(ValueError, match="130 events"):
            f.trace_rows(gzip.compress(raw + f.canonical(event(131)) + b"\n"))
    assert loads.call_count == 130


@pytest.mark.parametrize("change", ["digest", "canonical", "path"])
def test_actor_reference_rejects_digest_canonical_and_path_mismatch(tmp_path, change):
    episode, rows = write_episode(tmp_path)
    row = rows[0]
    path = episode / row["actor_input_ref"]["path"]
    if change == "digest":
        encoded = json.loads(gzip.decompress(path.read_bytes()))
        encoded["now"] = 999.
        path.write_bytes(gzip.compress(f.canonical(encoded)))
    elif change == "canonical":
        path.write_bytes(gzip.compress(gzip.decompress(path.read_bytes()) + b" "))
    else:
        row["actor_input_ref"]["path"] = "../private_evaluator.jsonl.gz"
    with pytest.raises(ValueError):
        f.decode_reference(episode.resolve(), row, NS(decode_arrays=lambda value: value))


def test_wrong_episode_scope_fails_before_input_decoding(tmp_path):
    episode, _ = write_episode(tmp_path)
    metadata = json.loads((episode / "episode.json").read_text())
    metadata["scene"] = "open"
    (episode / "episode.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="declared V34 rooms101"):
        f.inspect_episode(episode, "a" * 40, (None, None, None, NS(decode_arrays=lambda value: pytest.fail("decoded"))))


def test_existing_output_is_not_overwritten_or_evidence_read(tmp_path, monkeypatch):
    output = tmp_path / "result.json"
    output.write_text("original")
    monkeypatch.setattr(f, "inspect_episode", lambda *args, **kwargs: pytest.fail("consumed evidence"))
    with pytest.raises(FileExistsError):
        f.main(["--episode", str(tmp_path), "--source-freeze", "a" * 40, "--output", str(output)])
    assert output.read_text() == "original"


def artificial_helpers(traversable, point_pass=True, bridge_pass=True, connected=True):
    shape = traversable.shape
    obs = NS(NAVIGATION_COMPOSITION_VERSION="artificial", GOAL_XY_TOLERANCE_M=.1,
        _received_grid=lambda value: np.asarray(value, dtype=np.int8).copy(),
        native_traversable=lambda grid, res: (traversable, np.full(shape, .28)),
        _point_offset=lambda *args: 0., _cell=lambda *args: (3, 5))
    def paths(*args):
        distances = np.zeros((1, np.prod(shape))) if connected else np.full((1, np.prod(shape)), np.inf)
        return distances, np.arange(np.prod(shape)).reshape(shape)
    obs._path_distances = paths
    def segment(grid, res, origin, start, end):
        return {"accepted": point_pass if start == end else bridge_pass,
                "segment_distance_squared_capped_exact": "841/10000" if point_pass else "0"}
    cert = NS(canonical_seed_cell=lambda *args: (3, 3), canonical_cell_centre=lambda *args: (Q(0), Q(0)),
        certify_estimated_segment=segment, _number=lambda value: Q(value),
        certify_seed_pose_bridge=lambda *args, **kwargs: {"accepted": bool(kwargs["seed_cell_traversable"]) and bridge_pass,
            "reason": None if kwargs["seed_cell_traversable"] and bridge_pass else "seed_cell_body_clearance"})
    return obs, NS(np=np), cert, None


def artificial_params(active=False):
    navigation = {"phase": "active" if active else "idle", "goal_id": "goal" if active else None,
                  "goal_x": .5 if active else None, "goal_y": 0. if active else None}
    robots = [{"name": name, "x": 0., "y": 0., "yaw": 0., "source_stamp": 1., "received_stamp": 1.,
               "navigation": navigation if name == "tb3" else {}} for name in ("tb1", "tb2", "tb3")]
    entry = {"grid": np.zeros((7, 7), np.int8), "resolution": .05, "origin": (-.175, -.175),
             "composition_version": "artificial"}
    return {"robots": robots, "navigation_maps": {"tb3": entry}, "now": 1.}


def test_geometry_only_bridge_does_not_override_rejected_original_cell():
    traversable = np.ones((7, 7), bool)
    traversable[3, 3] = False
    result = f.analyse_params(artificial_params(), {"path_maps": {"tb3": {}}}, artificial_helpers(traversable))
    assert not result["original_cell"]["traversable"]
    assert result["exact_point"]["accepted"]
    assert not result["original_gate_bridge"]["accepted"]
    assert result["geometry_only_same_centre_segment_no_cell_admission"]["accepted"]
    assert result["finding"] == "original_cell_bound_rejects_but_exact_point_and_same_centre_segment_pass"
    assert result["local_path_execution"]["nominal_output_before_scan_pair"] is None


def test_actual_point_threshold_failure_is_distinct_from_bound_conservativeness():
    result = f.analyse_params(artificial_params(), {"path_maps": {"tb3": {}}},
        artificial_helpers(np.ones((7, 7), bool), point_pass=False))
    assert result["finding"] == "estimated_point_fails_exact_received_square_threshold"


def test_graph_disconnected_is_reported_only_for_admitted_seed_and_goal_nodes():
    result = f.analyse_params(artificial_params(active=True), {"path_maps": {"tb3": {}}},
        artificial_helpers(np.ones((7, 7), bool), connected=False))
    path = result["local_path_execution"]
    assert path["target_traversable"] and not path["seed_field_finite"]
    assert path["seed_field_condition"] == "disconnected" and path["status"] == "graph_disconnected"
