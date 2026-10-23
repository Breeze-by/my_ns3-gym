import base64
import copy
import gzip
import hashlib
import json
from pathlib import Path
import unittest
import zlib

import numpy as np

from mr3_learning.observation import (
    CANDIDATE_FIELDS, HISTORY_FIELDS, ROBOT_FIELDS, TASK_FIELDS,
    SNAPSHOT_SCHEMA, encode_snapshot, observation_space,
)


def fixture(legacy=False):
    """Historical map/state inputs with explicit synthetic v3 activity metadata."""
    root = Path(__file__).resolve().parents[2]
    path = root / "report/assets/20261015_mr3_p1b/native_v4/open101/adapter.jsonl.gz"
    with gzip.open(path, "rt") as handle:
        for line in handle:
            row = json.loads(line)
            if row["kind"] == "observation":
                snapshot = row["payload"]
                if legacy:
                    return snapshot
                snapshot["schema"] = SNAPSHOT_SCHEMA
                for robot in snapshot["robots"]:
                    robot["navigation"]["accepted_goal_count"] = 0
                    robot["activity"] = {
                        "schema": "mr3-received-activity-v1", "epoch": snapshot["epoch"],
                        "started_at": snapshot["source_stamp"],
                        "last_odom_source_stamp": snapshot["source_stamp"],
                        "estimated_path_m": 0., "sample_count": 1, "state_sequence": 1,
                        "path_observation_complete": True,
                    }
                return seal(snapshot)
    raise AssertionError("accepted P1B fixture has no observation")


def seal(snapshot):
    encoded = json.dumps({key: value for key, value in snapshot.items() if key != "digest"},
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    snapshot["digest"] = hashlib.sha256(encoded).hexdigest()
    return snapshot


class ObservationTests(unittest.TestCase):
    def test_explicit_v3_fixture_matches_fixed_spaces_and_all_indices(self):
        encoded = encode_snapshot(fixture())
        self.assertTrue(observation_space().contains(encoded))
        fields = (ROBOT_FIELDS, CANDIDATE_FIELDS, HISTORY_FIELDS, TASK_FIELDS)
        self.assertEqual(tuple(map(len, fields)), (71, 16, 4, 12))
        for fields in (ROBOT_FIELDS, CANDIDATE_FIELDS, HISTORY_FIELDS, TASK_FIELDS):
            self.assertEqual(len(fields), len(set(fields)))
        self.assertEqual(encoded["global_map"].dtype, np.uint8)
        self.assertEqual(encoded["robots"].dtype, np.float32)
        self.assertLessEqual(int(encoded["global_map"].max()), 1)

    def test_old_snapshot_is_explicitly_incompatible_with_new_actor_inputs(self):
        with self.assertRaisesRegex(ValueError, "unsupported snapshot"):
            encode_snapshot(fixture(legacy=True))

    def test_received_activity_is_scaled_and_complete_status_is_explicit(self):
        snapshot = fixture()
        snapshot["robots"][0]["activity"]["estimated_path_m"] = 1.5
        snapshot["robots"][0]["navigation"]["accepted_goal_count"] = 2
        encoded = encode_snapshot(seal(snapshot))["robots"][0]
        self.assertEqual(encoded[ROBOT_FIELDS.index("received_estimated_path_m")], 1.5 / 32)
        self.assertEqual(encoded[ROBOT_FIELDS.index("received_accepted_goal_count")], 2 / 64)
        self.assertEqual(encoded[ROBOT_FIELDS.index("received_path_complete")], 1)
        self.assertEqual(encoded[ROBOT_FIELDS.index("estimated_activity_ready")], 1)
        snapshot["robots"][0]["activity"]["path_observation_complete"] = False
        encoded = encode_snapshot(seal(snapshot))["robots"][0]
        self.assertEqual(encoded[ROBOT_FIELDS.index("received_path_complete")], 0)
        self.assertEqual(encoded[ROBOT_FIELDS.index("estimated_activity_ready")], 0)

    def test_cross_epoch_future_and_invalid_activity_counters_are_rejected(self):
        for field, value in (("epoch", "old"), ("estimated_path_m", -1.),
                             ("last_odom_source_stamp", fixture()["source_stamp"] + 1)):
            snapshot = fixture()
            snapshot["robots"][0]["activity"][field] = value
            with self.assertRaises(ValueError):
                encode_snapshot(seal(snapshot))
        for count in (-1, .5, True):
            snapshot = fixture()
            snapshot["robots"][0]["navigation"]["accepted_goal_count"] = count
            with self.assertRaises(ValueError):
                encode_snapshot(seal(snapshot))

    def test_missing_values_have_zero_and_explicit_valid_bits(self):
        snapshot = fixture()
        robot = snapshot["robots"][0]
        robot.update(x=None, yaw=None, valid=False, fresh=False, missing=True)
        encoded = encode_snapshot(seal(snapshot))["robots"][0]
        self.assertEqual(encoded[ROBOT_FIELDS.index("x")], 0)
        self.assertEqual(encoded[ROBOT_FIELDS.index("x_valid")], 0)
        self.assertEqual(encoded[ROBOT_FIELDS.index("cos_yaw_valid")], 0)
        self.assertEqual(encoded[ROBOT_FIELDS.index("state_missing")], 1)

    def test_out_of_reference_range_is_retained_and_flagged(self):
        snapshot = fixture()
        snapshot["robots"][0]["x"] = 64.0
        candidate = snapshot["candidates"][0]
        candidate["path_distances_m"] = [96.0, None, None]
        candidate["reachable"] = [True, False, False]
        encoded = encode_snapshot(seal(snapshot))
        self.assertEqual(encoded["robots"][0, ROBOT_FIELDS.index("x")], 4.0)
        self.assertEqual(encoded["robots"][0, ROBOT_FIELDS.index("position_out_of_bounds")], 1)
        self.assertEqual(encoded["candidates"][0, CANDIDATE_FIELDS.index("path_tb1_m")], 3.0)
        self.assertEqual(encoded["candidates"][0, CANDIDATE_FIELDS.index("out_of_bounds")], 1)

    def test_corrupt_digest_and_nonfinite_values_are_errors(self):
        snapshot = fixture()
        snapshot["robots"][0]["x"] += 1
        with self.assertRaisesRegex(ValueError, "digest"):
            encode_snapshot(snapshot)
        snapshot = fixture()
        snapshot["robots"][0]["x"] = float("nan")
        with self.assertRaises(ValueError):
            encode_snapshot(snapshot)

    def test_future_measurement_is_rejected_but_forward_tf_validity_is_metadata(self):
        snapshot = fixture()
        snapshot["robots"][0]["tf_source_stamp"] = snapshot["source_stamp"] + 0.1
        with self.assertRaisesRegex(ValueError, "future"):
            encode_snapshot(seal(snapshot))
        snapshot = fixture()
        snapshot["robots"][0]["tf_validity_stamp"] = snapshot["source_stamp"] + 0.2
        self.assertTrue(observation_space().contains(encode_snapshot(seal(snapshot))))

    def test_mask_requires_a_legal_action_and_preserves_coupled_joint_mask(self):
        snapshot = fixture()
        expected = np.asarray(snapshot["joint_action_mask"], dtype=np.int8)
        np.testing.assert_array_equal(encode_snapshot(snapshot)["action_mask"], expected)
        snapshot["joint_action_mask"] = [False] * 1000
        with self.assertRaisesRegex(ValueError, "mask"):
            encode_snapshot(seal(snapshot))

    def test_compressed_shape_boundary_and_binary_semantics_are_checked(self):
        for raw in (bytes([2]) * (3 * 128 * 128), bytes(3 * 128 * 128 + 1)):
            snapshot = fixture()
            snapshot["maps"]["global"]["data"] = base64.b64encode(zlib.compress(raw)).decode()
            with self.assertRaises(ValueError):
                encode_snapshot(seal(snapshot))

    def test_encoding_returns_detached_arrays(self):
        snapshot = fixture()
        first = encode_snapshot(snapshot)
        original = copy.deepcopy(snapshot)
        first["robots"][0, 0] = 900
        first["action_mask"][:] = 0
        second = encode_snapshot(snapshot)
        self.assertEqual(snapshot, original)
        self.assertNotEqual(second["robots"][0, 0], 900)
        self.assertTrue(second["action_mask"].any())

    def test_cross_epoch_robot_or_path_map_cannot_enter_actor_features(self):
        for field in ("robots", "path_maps"):
            snapshot = fixture()
            if field == "robots":
                snapshot["robots"][0]["epoch"] = "old-episode"
            else:
                snapshot["path_maps"]["tb1"]["epoch"] = "old-episode"
            with self.assertRaisesRegex(ValueError, "cross-epoch"):
                encode_snapshot(seal(snapshot))

    def test_declared_age_cannot_freshen_an_old_received_sample(self):
        snapshot = fixture()
        snapshot["robots"][0]["source_age_sec"] = 0.0
        with self.assertRaisesRegex(ValueError, "age and timestamp"):
            encode_snapshot(seal(snapshot))

    def test_received_own_map_ages_and_recent_failure_are_actor_features(self):
        snapshot = fixture()
        snapshot["robots"][0]["navigation"]["last_failure"] = "nav2_aborted"
        encoded = encode_snapshot(seal(snapshot))["robots"][0]
        self.assertAlmostEqual(
            encoded[ROBOT_FIELDS.index("path_map_source_age_sec")],
            snapshot["path_maps"]["tb1"]["source_age_sec"] / 300, places=6)
        self.assertEqual(encoded[ROBOT_FIELDS.index("last_failure_present")], 1)


if __name__ == "__main__":
    unittest.main()
