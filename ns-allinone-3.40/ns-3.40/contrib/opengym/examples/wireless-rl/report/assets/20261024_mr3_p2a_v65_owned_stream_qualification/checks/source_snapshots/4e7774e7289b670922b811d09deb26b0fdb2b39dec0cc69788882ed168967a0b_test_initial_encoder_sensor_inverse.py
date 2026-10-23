"""Artificial CPU evidence only; never opens any V59 native artifact."""

import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning.tests import test_audit_action_trace as old


from mr3_learning import audit_reach_sensor_model as sensor
PROFILE = "initial-zero-encoder-hold-v1"
INSERTED = ("<mr3_actuation_profile>" + PROFILE + "</mr3_actuation_profile>\n      ").encode()
MARKER = b"<mr3_tagged_commands>true</mr3_tagged_commands>"


class InitialEncoderSensorInverseTests(unittest.TestCase):
    fixture = old.ReachSensorModelTests.fixture

    def profiled_fixture(self):
        episode, epoch, source, generated, starts = self.fixture()
        for robot, raw in list(generated.items()):
            generated[robot] = raw.replace(MARKER, INSERTED + MARKER, 1)
            (episode / f"drive_model_{robot}.sdf").write_bytes(generated[robot])
        return episode, epoch, source, generated, starts

    def inverse(self, raw, source, epoch, episode, profile=PROFILE):
        return sensor.inverse_reach_lidar(raw, source, "tb1", epoch, episode,
                                          actuation_profile=profile)

    def test_explicit_profile_exact_inverse_restores_detached_legacy_bytes(self):
        episode, epoch, source, generated, _ = self.profiled_fixture()
        original = generated["tb1"]
        restored, proof = self.inverse(original, source, epoch, episode)
        self.assertNotIn(b"mr3_actuation_profile", restored)
        self.assertIn(b"<update_rate>5</update_rate>", restored)
        self.assertEqual(proof["whole_byte_inverse_sha256"], proof["source_sha256"])
        self.assertEqual(proof["actuation_profile_inverse"]["actuation_profile"], PROFILE)
        self.assertFalse(proof["actuation_profile_inverse"]["actual_driver_build_proved_here"])
        self.assertEqual((episode / "drive_model_tb1.sdf").read_bytes(), original)

    def test_legacy_and_new_profile_require_separate_exact_inputs(self):
        episode, epoch, source, generated, _ = self.fixture()
        with self.assertRaises(ValueError):
            self.inverse(generated["tb1"], source, epoch, episode)
        changed = generated["tb1"].replace(MARKER, INSERTED + MARKER, 1)
        with self.assertRaises(ValueError):
            sensor.inverse_reach_lidar(changed, source, "tb1", epoch, episode)

    def test_unknown_profile_cannot_select_a_new_inverse(self):
        episode, epoch, source, generated, _ = self.profiled_fixture()
        for profile in ("", "other", True, {"actuation_profile": PROFILE}):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                self.inverse(generated["tb1"], source, epoch, episode, profile)

    def test_duplicate_missing_wrong_value_nested_and_misplaced_tags_rejected(self):
        episode, epoch, source, generated, _ = self.profiled_fixture()
        raw = generated["tb1"]
        bare = raw.replace(INSERTED, b"", 1)
        moved = bare.replace(b"</model>", INSERTED + b"</model>", 1)
        comment = bare.replace(b"</model>", b"<!--" + INSERTED + b"--></model>", 1)
        mutations = [
            bare,
            raw.replace(INSERTED, INSERTED + INSERTED, 1),
            raw.replace(PROFILE.encode(), b"other-profile", 1),
            raw.replace(INSERTED, b"<nested>" + INSERTED + b"</nested>", 1),
            moved,
            comment,
            raw.replace(b"<mr3_actuation_profile>", b'<mr3_actuation_profile x="1">', 1),
            raw.replace(b"</mr3_actuation_profile>\n      ", b"</mr3_actuation_profile> ", 1),
            raw.replace(b"</mr3_actuation_profile>", b"<extra/></mr3_actuation_profile>", 1),
        ]
        for index, changed in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.inverse(changed, source, epoch, episode)

    def test_driver_sensor_pose_and_arbitrary_bytes_remain_whole_byte_bound(self):
        episode, epoch, source, generated, _ = self.profiled_fixture()
        raw = generated["tb1"]
        mutations = [
            raw.replace(b'filename="libmr3_gazebo_diff_drive.so"', b'filename="other.so"', 1),
            raw.replace(b'name="turtlebot3_diff_drive"', b'name="other_driver"', 1),
            raw.replace(b"<wheel_diameter>0.066</wheel_diameter>", b"<wheel_diameter>0.067</wheel_diameter>", 1),
            raw.replace(b"<samples>360</samples>", b"<samples>361</samples>", 1),
            raw.replace(b"<update_rate>20</update_rate>", b"<update_rate>5</update_rate>", 1),
            raw.replace(b"<model name=", b" <model name=", 1),
        ]
        for index, changed in enumerate(mutations):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.inverse(changed, source, epoch, episode)

    def test_immutable_spawn_checks_all_three_artificial_new_profile_models(self):
        episode, epoch, _, generated, _ = self.profiled_fixture()
        module, projection = sensor.load_spawn_impl(actuation_profile=PROFILE)
        self.assertEqual(projection["inverse_sha256"], sensor.ORIGINAL_READER_SHA256)
        self.assertEqual(len(projection["literal_changes"]), 2)
        self.assertEqual(projection["actuation_profile"], PROFILE)
        result = module._spawn(episode, epoch, Path.read_bytes, False)
        self.assertEqual(set(result["robots"]), {"tb1", "tb2", "tb3"})
        for robot, report in result["robots"].items():
            self.assertIn("actuation_profile_inverse", report["reach_sensor_profile"])
            self.assertEqual((episode / f"drive_model_{robot}.sdf").read_bytes(), generated[robot])

    def test_new_profile_still_rejects_changed_spawn_pose(self):
        episode, epoch, _, _, starts = self.profiled_fixture()
        module, _ = sensor.load_spawn_impl(actuation_profile=PROFILE)
        changed = copy.deepcopy(starts)
        argv = changed[0]["argv"]
        argv[argv.index("-x") + 1] = "3.0"
        (episode / "launch.log").write_text("".join(
            "MR3_ORDERED_SHUTDOWN " + json.dumps(row) + "\n" for row in changed))
        with self.assertRaises(ValueError):
            module._spawn(episode, epoch, Path.read_bytes, False)

    def test_metadata_profile_must_match_explicit_dispatch_before_reading_source(self):
        for expected, actual in ((PROFILE, None), (None, PROFILE), (PROFILE, "other")):
            metadata = {"freeze":"a" * 40,"safety_contract":"mr3-reach-v1"}
            if actual is not None:
                metadata["actuation_profile"] = actual
            with self.subTest(expected=expected, actual=actual), patch.object(sensor, "Reader") as reader:
                reader.return_value.side_effect = lambda path: json.dumps(metadata).encode()
                with patch.object(sensor, "load_spawn_impl") as load, self.assertRaises(ValueError):
                    sensor.audit_episode(Path("/synthetic/episode"), Path("/synthetic/root"),
                                         "a" * 40, actuation_profile=expected)
                load.assert_not_called()

    def test_dispatch_conjoins_existing_gate_and_propagates_explicit_profile(self):
        episode, _, _, _, _ = self.profiled_fixture()
        (episode / "metadata.json").write_text("{}")
        for old_pass in (False, True):
            phase = SimpleNamespace(corrected_audit=lambda *args, **kwargs: {
                "passed":old_pass,"errors":[] if old_pass else ["original failure"]})
            sensor.attach_native_gate(phase, Path("/source"), "a" * 40, actuation_profile=PROFILE)
            with patch.object(sensor, "audit_episode", return_value={"passed":True}) as audit:
                result = phase.corrected_audit(None, None, None, [episode])
            audit.assert_called_once_with(episode, Path("/source"), "a" * 40,
                                          actuation_profile=PROFILE)
            self.assertEqual(result["passed"], old_pass)
