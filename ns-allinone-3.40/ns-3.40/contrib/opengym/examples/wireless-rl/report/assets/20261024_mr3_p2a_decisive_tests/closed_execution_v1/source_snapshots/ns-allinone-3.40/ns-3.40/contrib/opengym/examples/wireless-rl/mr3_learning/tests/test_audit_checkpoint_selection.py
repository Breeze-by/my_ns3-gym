"""Collecting-policy provenance when earlier native evidence is rejected.

The integration fixture retains a genuine audit failure and checks that it
cannot make a later round replay the wrong policy. No simulator or GPU runs.
"""

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import audit_ppo as audit


class CollectingCheckpointTests(unittest.TestCase):
    def test_latest_declared_update_survives_missing_native_round_and_update_gap(self):
        directory = Path("/fixture")
        updates = [{"round": 4}, {"round": 0}, {"round": 2}]
        self.assertEqual(audit.collecting_checkpoint(directory, "train", 4, updates),
                         directory / "checkpoint_0002.zip")

    def test_no_prior_update_and_evaluation_use_initial_policy(self):
        directory = Path("/fixture")
        for mode, index, updates in (("train", 0, [{"round": 0}]),
                                      ("train", 3, []),
                                      ("evaluate", 3, [{"round": 0}, {"round": 2}])):
            with self.subTest(mode=mode, index=index, updates=updates):
                self.assertEqual(audit.collecting_checkpoint(directory, mode, index, updates),
                                 directory / "initial.zip")

    def test_missing_declared_checkpoint_does_not_fall_back_to_another_policy(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            (directory / "initial.zip").write_bytes(b"initial")
            (directory / "checkpoint_0001.zip").write_bytes(b"stray unlisted update")
            selected = audit.collecting_checkpoint(directory, "train", 2, [{"round": 0}])
            self.assertEqual(selected, directory / "checkpoint_0000.zip")
            with self.assertRaises(FileNotFoundError):
                audit.sha(selected)

    def test_rejected_first_native_round_retains_failure_without_wrong_later_replay(self):
        freeze = "a" * 40
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            directory = Path(temporary)

            def write(path, value):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))

            episodes = []
            for index in (0, 1):
                episode = directory / "native" / f"round{index:04d}" / "worker0" / "episode001"
                epoch = f"epoch-{index}"
                write(episode / "metadata.json", {"epoch": epoch, "scene": "open", "seed": 101})
                write(episode / (epoch + ".json"), {
                    "schema_version": 4, "robot_count": 3, "coverage_threshold": .95,
                    "max_duration_sec": 300., "success": False,
                    "termination_reason": "navigation_failure",
                    "correct_free_coverage_ratio": .8, "map_quality_pass": True,
                    "robot_participation_pass": False, "collision_events": 0,
                    "collision_monitoring_fresh": True, "navigation_protocol_closed": False,
                    "elapsed_sim_time_sec": 2., "time_to_95_coverage_sec": None})
                episodes.append({"directory": str(episode), "episode_index": index,
                                 "decisions": 2, "api_records": 2,
                                 "reward_sum": 2., "simulation_seconds": 2.})
            for filename in ("initial.zip", "checkpoint_0000.zip", "checkpoint_0001.zip", "final.zip"):
                (directory / filename).write_bytes(filename.encode())
            digest = lambda filename: hashlib.sha256((directory / filename).read_bytes()).hexdigest()
            write(directory / "metadata.json", {"freeze": freeze, "mode": "train",
                                                "gamma_per_second": 1., "lambda_per_second": 1.})
            write(directory / "summary.json", {
                "freeze": freeze, "episodes": episodes, "completed": True, "error": None,
                "cleanup_errors": [], "decisions": 4, "api_records": 4, "optimizer_updates": 8,
                "initial_checkpoint_sha256": digest("initial.zip"),
                "final_checkpoint_sha256": digest("final.zip"),
                "rounds": [{"round": index, "changed_parameter_tensors": 1, "metrics": {}}
                           for index in (0, 1)]})

            native = SimpleNamespace(audit_initial_inputs_ready=lambda *args: None,
                                     audit_physics=lambda *args: None)

            def native_gate(*args):
                failed = "round0000" in str(args[-1][0])
                return {"passed": not failed,
                        "errors": ["retained physical failure"] if failed else []}

            phase = SimpleNamespace(corrected_audit=native_gate)
            scalar = SimpleNamespace(audit_episode=lambda *args: {"errors": []})
            stack.enter_context(patch.object(audit, "load_native_gates", return_value=(
                phase, None, native, None, scalar, {})))
            stack.enter_context(patch.object(audit, "dispatch_controlled_physics", return_value=
                                             native.audit_physics))
            stack.enter_context(patch.object(audit, "dispatch_controlled_readiness"))
            stack.enter_context(patch.object(audit.audit_evaluator_phase, "audit_episode",
                                             return_value={"passed": True}))
            stack.enter_context(patch.object(audit, "native_decisions", return_value=(
                [{"reward": 1., "dt": 1.}, {"reward": 1., "dt": 1.}], 2)))
            loaded = []

            def load(path, **kwargs):
                loaded.append(path.name)
                return SimpleNamespace(checkpoint=path.name,
                                       _n_updates={"initial.zip": 0,
                                                   "checkpoint_0000.zip": 4,
                                                   "checkpoint_0001.zip": 8}[path.name])

            def replay(model, decisions, **kwargs):
                for row in decisions:
                    row["value"] = 1. if model.checkpoint == "checkpoint_0000.zip" else 0.
                return {"passed": True}

            def rollout(path, decisions, **kwargs):
                audit.require(all(row["value"] == 1. for row in decisions),
                              "native/pre-update collecting-policy mismatch: values")
                return {"passed": True}

            stack.enter_context(patch.object(audit.MaskablePPO, "load", side_effect=load))
            stack.enter_context(patch.object(audit, "policy_replay", side_effect=replay))
            stack.enter_context(patch.object(audit, "audit_rollout", side_effect=rollout))
            stack.enter_context(patch.object(audit, "parameter_changes", return_value=1))
            result = audit.audit_run(directory, freeze)
            self.assertFalse(result["passed"])
            self.assertEqual(len(result["errors"]), 1)
            self.assertIn("retained physical failure", result["errors"][0])
            self.assertEqual(loaded, ["checkpoint_0000.zip", "checkpoint_0001.zip"])
            self.assertEqual(result["rounds"][0]["collecting_checkpoint"],
                             str(directory / "checkpoint_0000.zip"))
            self.assertTrue(result["rounds"][0]["rollout"]["passed"])


if __name__ == "__main__":
    unittest.main()
