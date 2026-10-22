"""Artificial fixtures only; no archived input, scene, World or actor execution."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import numpy as np


SCRIPT = Path(__file__).with_name("attachment_replay_v1.py")
spec = importlib.util.spec_from_file_location("mr3_v36_attachment_replay_fixture", SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)
codec = replay.load_file("mr3_v36_artificial_fixture_codec", replay.CODEC)
FREEZE = "1" * 40


class ActualHelperLoadingTests(unittest.TestCase):
    def test_canonical_pure_helpers_load_without_reading_evidence(self):
        with patch.object(replay, "read_limited", side_effect=AssertionError("evidence read during helper loading")):
            primitive, loaded_codec = replay.load_helpers()
        self.assertEqual(primitive.PROFILE, replay.PROFILE)
        self.assertTrue(callable(loaded_codec.decode_arrays))


class FakePrimitive:
    PROFILE = replay.PROFILE

    def __init__(self, accept=False):
        self.calls = []
        self.accept = accept

    def point_graph_attachments(self, grid, resolution, origin, estimated_xy):
        self.calls.append({"marker": int(grid[0, 0]), "resolution": resolution,
                           "origin": list(origin), "estimated_xy": list(estimated_xy)})
        anchors = [{"cell": [2, 2], "bridge_length_squared_exact": "1/4"}] if self.accept else []
        return {"schema": "mr3-point-graph-attachment-candidate-v1", "profile": replay.PROFILE,
                "production_enabled": False, "graph_mutated": False, "accepted": self.accept,
                "reason": None if self.accept else "no_certified_anchor_in_fixed_3x3",
                "anchors": anchors, "candidate_nodes": []}


class FixedInputFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.episode = self.directory / "episode"
        (self.episode / "inputs").mkdir(parents=True)
        self.report_path = self.directory / "report.json"
        self.expected = []
        self.params = []
        records = []
        for index, selection in enumerate(replay.EXPECTED_INPUTS):
            now = float(index * 64)
            maps, robots = {}, []
            for robot_index, name in enumerate(replay.ROBOTS, 1):
                grid = np.zeros((7, 7), dtype=np.int16)
                grid[0, 0] = index * 10 + robot_index
                maps[name] = {"grid": grid, "resolution": .5 * robot_index,
                    "origin": [-robot_index, index], "epoch": "artificial_epoch", "sequence": index + 1,
                    "source_stamp": now - .1, "received_stamp": now,
                    "composition_version": replay.COMPOSITION}
                robots.append({"name": name, "x": index * 10 + robot_index + .125,
                    "y": robot_index + .25, "yaw": .0, "epoch": "artificial_epoch",
                    "source_stamp": now - .05, "received_stamp": now})
            # List and mapping order must not substitute a different robot's map.
            params = {"robots": list(reversed(robots)), "navigation_maps": dict(reversed(list(maps.items()))),
                      "seed_rule": replay.RULE, "epoch": "artificial_epoch", "now": now,
                      "sequence": index + 1, "map_version": "fixture"}
            self.params.append(params)
            unpacked = replay.canonical(codec.encode_arrays(params))
            compressed = gzip.compress(unpacked, mtime=0)
            expected = {**copy.deepcopy(selection), "canonical_sha256": replay.digest(unpacked),
                        "compressed_sha256": replay.digest(compressed), "canonical_bytes": len(unpacked)}
            self.expected.append(expected)
            path = self.episode / "inputs" / (expected["canonical_sha256"] + ".json.gz")
            path.write_bytes(compressed)
            reference = {"path": str(path), **{key: expected[key] for key in (
                "compressed_sha256", "canonical_sha256", "canonical_bytes")}}
            records.append({"roles": expected["roles"], "event_sequence": expected["event_sequence"],
                "trace_line_1based": expected["event_sequence"], "event": expected["event"],
                "actor_input_ref": reference, "snapshot_canonical_sha256": str(index + 2) * 64,
                "geometry": {"now": now}})
        self.report = {"schema": "mr3-v34-rooms-received-geometry-forensic-v1",
            "source_freeze": replay.REPORT_FREEZE, "evidence_freeze": replay.EVIDENCE_FREEZE,
            "source_stable": True, "scene": "rooms", "seed": 101, "epoch": "artificial_epoch",
            "actual": {"trace_events": 130, "selected_actors": 2, "decoded_actor_inputs": 2},
            "trace_metadata": {"epoch": "artificial_epoch", "env_id": 1, "episode_index": 1,
                "scene": "rooms", "seed": 101, "evidence_freeze": replay.EVIDENCE_FREEZE,
                "first_event_sequence": 1, "last_event_sequence": 130},
            "records": records, "input_index": [record["actor_input_ref"] for record in records]}
        self.save_report()

    def save_report(self):
        self.report_path.write_bytes(replay.canonical(self.report))

    def compute(self, primitive=None, custom_codec=codec):
        return replay.inspect_fixed_inputs(FREEZE, report_path=self.report_path, episode=self.episode,
            expected_inputs=self.expected, helpers=(primitive or FakePrimitive(), custom_codec))

    def test_exactly_two_decodes_and_six_correct_own_map_pose_pairs(self):
        primitive = FakePrimitive(accept=True)
        counted_codec = types.SimpleNamespace(encode_arrays=codec.encode_arrays,
            decode_arrays=Mock(wraps=codec.decode_arrays))
        result = self.compute(primitive, counted_codec)
        self.assertEqual(counted_codec.decode_arrays.call_count, 2)
        self.assertEqual(len(primitive.calls), 6)
        for frame in range(2):
            for robot in range(1, 4):
                self.assertEqual(primitive.calls[frame * 3 + robot - 1], {
                    "marker": frame * 10 + robot, "resolution": .5 * robot,
                    "origin": [-robot, frame], "estimated_xy": [frame * 10 + robot + .125, robot + .25]})
        self.assertEqual([row["event_sequence"] for row in result["records"]], [1, 129])
        self.assertEqual(result["counts"], {"selected_frames": 2, "decoded_inputs": 2,
            "robot_computations": 6, "robots_with_attachments": 6, "robots_without_attachments": 0,
            "total_anchors": 6})
        self.assertEqual(result["input_bindings_before"], result["input_bindings_after"])
        self.assertFalse(result["qualification"])
        self.assertFalse(result["freshness_recertified"])

    def test_zero_anchors_is_closed_negative_not_computation_failure(self):
        result = self.compute()
        self.assertTrue(result["passed"])
        self.assertTrue(result["computation_passed"])
        self.assertEqual(result["counts"]["robots_with_attachments"], 0)
        self.assertEqual(result["counts"]["robots_without_attachments"], 6)
        self.assertEqual(sum(len(row["robots"]) for row in result["records"]), 6)
        self.assertTrue(all(not robot["attachment"]["accepted"]
                            for row in result["records"] for robot in row["robots"]))

    def test_bad_reference_rejects_before_any_input_decode_or_primitive(self):
        self.report["records"][1]["actor_input_ref"]["path"] = "/tmp/undeclared.json.gz"
        self.save_report()
        primitive = FakePrimitive()
        with patch.object(replay, "read_limited", wraps=replay.read_limited) as reads:
            with self.assertRaisesRegex(ValueError, "reference differs"):
                self.compute(primitive)
        self.assertEqual([call.args[0] for call in reads.call_args_list], [self.report_path])
        self.assertEqual(primitive.calls, [])

    def test_selection_cannot_replace_or_split_overlapping_roles(self):
        self.report["records"][0]["roles"] = ["reset"]
        self.save_report()
        with self.assertRaisesRegex(ValueError, "selection identity"):
            self.compute()

    def test_compressed_sha_corruption_stops_before_any_geometry(self):
        path = Path(self.report["records"][1]["actor_input_ref"]["path"])
        path.write_bytes(path.read_bytes() + b"corruption")
        primitive = FakePrimitive()
        with self.assertRaisesRegex(ValueError, "compressed input SHA"):
            self.compute(primitive)
        self.assertEqual(primitive.calls, [])

    def rewrite_second(self, change):
        params = copy.deepcopy(self.params[1])
        change(params)
        unpacked = replay.canonical(codec.encode_arrays(params))
        compressed = gzip.compress(unpacked, mtime=0)
        expected = self.expected[1]
        expected.update(canonical_sha256=replay.digest(unpacked), compressed_sha256=replay.digest(compressed),
                        canonical_bytes=len(unpacked))
        path = self.episode / "inputs" / (expected["canonical_sha256"] + ".json.gz")
        path.write_bytes(compressed)
        self.report["records"][1]["actor_input_ref"] = {"path": str(path), **{
            key: expected[key] for key in ("compressed_sha256", "canonical_sha256", "canonical_bytes")}}
        self.report["input_index"][1] = self.report["records"][1]["actor_input_ref"]
        self.save_report()

    def test_epoch_now_and_rule_bind_before_any_geometry(self):
        for field, bad in (("epoch", "other"), ("seed_rule", "legacy"), ("now", 99.0)):
            with self.subTest(field=field):
                self.rewrite_second(lambda params: params.__setitem__(field, bad))
                primitive = FakePrimitive()
                with self.assertRaises(ValueError):
                    self.compute(primitive)
                self.assertEqual(primitive.calls, [])

    def test_primitive_cannot_mutate_the_input(self):
        primitive = FakePrimitive()
        original = primitive.point_graph_attachments
        def mutate(grid, *args):
            result = original(grid, *args)
            grid[0, 0] = 100
            return result
        primitive.point_graph_attachments = mutate
        with self.assertRaisesRegex(ValueError, "changed received map"):
            self.compute(primitive)

    def test_changed_compressed_bytes_after_computation_fail(self):
        primitive = FakePrimitive()
        original = primitive.point_graph_attachments
        def change_file(*args):
            result = original(*args)
            if len(primitive.calls) == 6:
                path = Path(self.report["records"][0]["actor_input_ref"]["path"])
                path.write_bytes(path.read_bytes() + b"changed")
            return result
        primitive.point_graph_attachments = change_file
        with self.assertRaisesRegex(ValueError, "inputs changed"):
            self.compute(primitive)

    def test_original_report_source_freeze_is_not_inherited_as_new_freeze(self):
        self.report["source_freeze"] = FREEZE
        self.save_report()
        with self.assertRaisesRegex(ValueError, "closed source-stable V35"):
            self.compute()

    def test_main_preserves_existing_output_before_source_or_evidence_reads(self):
        output = self.directory / "already.json"
        output.write_bytes(b"original failure stays\n")
        with patch.object(replay, "source_bindings") as sources, patch.object(replay, "inspect_fixed_inputs") as inspect:
            with self.assertRaises(FileExistsError):
                replay.main(["--source-freeze", FREEZE, "--output", str(output)])
        sources.assert_not_called()
        inspect.assert_not_called()
        self.assertEqual(output.read_bytes(), b"original failure stays\n")

    def test_main_actual_self_identity_and_fail_metadata_without_real_inputs(self):
        output = self.directory / "failed.json"
        with patch.object(replay, "source_bindings", return_value={"fixture": "a" * 64}), \
                patch.object(replay, "inspect_fixed_inputs", side_effect=ValueError("artificial refusal")):
            with self.assertRaisesRegex(ValueError, "artificial refusal"):
                replay.main(["--source-freeze", FREEZE, "--output", str(output)])
        result = json.loads(output.read_bytes())
        self.assertFalse(result["computation_passed"])
        self.assertFalse(result["source_stable"])
        self.assertEqual(result["source_freeze"], FREEZE)
        self.assertEqual(result["identity"], replay.identity())
        self.assertIn("artificial refusal", result["error"])

    def test_main_zero_anchor_success_is_compatible_with_final_observer(self):
        output = self.directory / "closed.json"
        computed = self.compute()
        with patch.object(replay, "source_bindings", return_value={"fixture": "b" * 64}), \
                patch.object(replay, "inspect_fixed_inputs", return_value=computed):
            self.assertEqual(replay.main(["--source-freeze", FREEZE, "--output", str(output)]), 0)
        result = json.loads(output.read_bytes())
        self.assertNotIn("error", result)
        self.assertTrue(result["source_stable"])
        self.assertEqual(result["source_freeze"], FREEZE)
        self.assertEqual(result["identity"], replay.identity())
        self.assertEqual(result["counts"]["robots_without_attachments"], 6)


if __name__ == "__main__":
    unittest.main()
