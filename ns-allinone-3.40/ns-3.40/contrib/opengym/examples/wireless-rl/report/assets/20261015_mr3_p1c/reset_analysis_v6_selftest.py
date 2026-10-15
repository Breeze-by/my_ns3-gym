"""Synthetic reset evidence only; never call analyse() on actual run directories."""

import gzip
import json
import math
from pathlib import Path
import tempfile
import unittest

import reset_analysis_v6 as R


ROOT = next(p for p in Path(__file__).resolve().parents if (p / ".git").exists())
_, AUDIT, _ = R.load_phase(ROOT)


def initial_fixture():
    epoch = "synthetic-current"
    sources = {name: {"payload_sha256": "1" * 64, "sequence": 3, "version": 2,
                      "source_stamp": .8, "received_stamp": .95} for name in R.ROBOTS}
    paths = {name: dict(source, epoch=epoch, missing=False, geometry_sha256="2" * 64)
             for name, source in sources.items()}
    robots = []
    for name in R.ROBOTS:
        robots.append({"name": name, "epoch": epoch, "valid": True, "x": 0., "y": 0.,
                       "yaw": 0., "source_stamp": .9, "received_stamp": .95,
                       "navigation": {"phase": "idle", "owned": False,
                                      "commitment_remaining_sec": 0.},
                       "history": [{"x": 0., "y": 0., "source_stamp": .8},
                                   {"x": 0., "y": 0., "source_stamp": .9}]})
    snapshot = {"schema": "mr3-observation-v2", "epoch": epoch, "sequence": 1,
                "source_stamp": 1., "task_elapsed_sec": 0., "task_remaining_sec": 300.,
                "robots": robots, "map": {"sources": sources}, "path_maps": paths,
                "map_version": 2, "candidates": [], "joint_action_mask": [True] * 1000}
    snapshot["candidate_version"] = R.canonical({key: snapshot[key] for key in
                                                ("epoch", "map_version", "sequence",
                                                 "candidates", "path_maps")})
    snapshot["digest"] = R.canonical(snapshot)
    reset = {"kind": "reset", "snapshot": snapshot, "reward": 0.,
             "terminated": False, "truncated": False, "info": {
                 "epoch": epoch, "dt": 0., "release_time_ns": 10**9,
                 "watermarks": {"map_sources": sources, "map_payload_sha256": "3" * 64},
                 "reward_diagnostics": {"sequence": 0, "reward": 0., "epoch": epoch,
                                        "kind": "reward_reset_binding", "reset_bound": True,
                                        "delta_sim_time": 0., "step_start": 1.,
                                        "effective_step_end": 1., "initial_correct_free_cells": 5,
                                        "map_watermark": {"payload_sha256": "3" * 64}}}}
    adapter = [{"kind": "state_update", "epoch": epoch, "payload": {"robots": [
        {"name": name, "valid": True, "source_stamp": stamp} for name in R.ROBOTS]}}
        for stamp in (.8, .9)]
    adapter += [{"kind": "observation", "epoch": epoch, "payload": snapshot},
                {"kind": "action", "epoch": epoch, "payload": {
                    "observation_sequence": 1, "observation_digest": snapshot["digest"]}}]
    return reset, adapter, epoch


def rehash(reset):
    snapshot = reset["snapshot"]
    snapshot["candidate_version"] = R.canonical({key: snapshot[key] for key in
                                                ("epoch", "map_version", "sequence",
                                                 "candidates", "path_maps")})
    snapshot["digest"] = R.canonical({k: v for k, v in snapshot.items() if k != "digest"})


def episode(identity, epoch, yaw=0.):
    return {"directory": epoch, "epoch": epoch,
            "processes": {"owned_pid_identities": [identity]},
            "configuration": {"semantic_input_sha256": "same"},
            "robots": {name: {"x": 0., "y": 0., "yaw": yaw} for name in R.ROBOTS},
            "map_payload_sha256": "same-map",
            "map_sources": {name: {"payload_sha256": "same"} for name in R.ROBOTS},
            "path_maps": {name: {"geometry_sha256": "same"} for name in R.ROBOTS}}


class ResetAnalysisTests(unittest.TestCase):
    def test_gzip_and_plain_have_same_decoded_identity_without_writing_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            content = b'{"a": 1}\n'
            packed = gzip.compress(content, mtime=0)
            (path / "rows.jsonl.gz").write_bytes(packed)
            reader = R.Reader(path)
            self.assertEqual(reader.rows("rows.jsonl"), [{"a": 1}])
            self.assertEqual(reader.files["rows.jsonl"]["decoded_sha256"], R.sha(content))
            self.assertEqual((path / "rows.jsonl.gz").read_bytes(), packed)

    def test_first_observation_keeps_legitimate_warmup_and_unpaid_initial_map(self):
        reset, adapter, epoch = initial_fixture()
        result = R.initial_state(reset, adapter, epoch, AUDIT)
        self.assertEqual(result["snapshot_sequence"], 1)
        self.assertEqual(result["reward_sequence"], 0)
        self.assertEqual(result["history"]["tb1"]["count"], 2)
        self.assertEqual(result["initial_correct_free_cells"], 5)

    def test_bad_initial_state_cannot_be_hidden_by_recomputed_snapshot_digest(self):
        cases = ("old_epoch", "reward_sequence", "actor_sequence", "task_time", "goal",
                 "old_history", "future_map", "map_epoch", "reward_map", "old_action")
        for case in cases:
            with self.subTest(case=case):
                reset, adapter, epoch = initial_fixture()
                robot = reset["snapshot"]["robots"][0]
                if case == "old_epoch":
                    robot["epoch"] = "previous"
                elif case == "reward_sequence":
                    reset["info"]["reward_diagnostics"]["sequence"] = 8
                elif case == "actor_sequence":
                    reset["snapshot"]["sequence"] = 9
                elif case == "task_time":
                    reset["snapshot"]["task_elapsed_sec"] = 3.
                elif case == "goal":
                    robot["navigation"]["last_goal_id"] = "previous-goal"
                elif case == "old_history":
                    robot["history"][0]["source_stamp"] = .7
                elif case == "future_map":
                    reset["snapshot"]["path_maps"]["tb1"]["received_stamp"] = 1.1
                elif case == "map_epoch":
                    reset["snapshot"]["path_maps"]["tb1"]["epoch"] = "previous"
                elif case == "reward_map":
                    reset["info"]["reward_diagnostics"]["map_watermark"]["payload_sha256"] = "wrong"
                else:
                    adapter[-1]["payload"]["observation_sequence"] = 7
                rehash(reset)
                with self.assertRaises((ValueError, KeyError)):
                    R.initial_state(reset, adapter, epoch, AUDIT)

    def test_bare_pid_reuse_is_legal_but_same_pid_start_identity_is_rejected(self):
        a, b = episode([123, 100], "old"), episode([123, 200], "new")
        self.assertTrue(R.pair(a, b)["new_epoch_and_disjoint_saved_process_identities"])
        b["processes"]["owned_pid_identities"] = [[123, 100]]
        with self.assertRaisesRegex(ValueError, "identity reused"):
            R.pair(a, b)

    def test_yaw_wrap_and_equal_map_digest_do_not_fake_reset_failure_or_proof(self):
        a = episode([1, 1], "old", math.pi - .01)
        b = episode([2, 2], "new", -math.pi + .01)
        result = R.pair(a, b)
        self.assertAlmostEqual(result["max_yaw_rad"], .02)
        self.assertTrue(result["map_payload_equal"])

    def test_same_seed_config_difference_fails_cross_scene_difference_is_descriptive(self):
        a, b = episode([1, 1], "old"), episode([2, 2], "new")
        b["configuration"]["semantic_input_sha256"] = "new-world"
        with self.assertRaisesRegex(ValueError, "configuration differs"):
            R.pair(a, b)
        self.assertFalse(R.pair(a, b, False)["same_seed_comparison"])

    def test_duplicate_launch_parameter_and_invalid_times_rejected(self):
        with self.assertRaisesRegex(ValueError, "duplicate"):
            R.arguments(["world:=a", "world:=b"])
        for value in (True, float("nan"), -1.):
            with self.assertRaises(ValueError):
                R.ns(value)

    def test_actual_world_spawn_model_chain_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            model = root / "model.sdf"
            model.write_bytes(b"frozen model")
            world_key = R.PACKAGE + "worlds/p1c_open.world"
            contract_key = R.PACKAGE + "config/mr3_p1a/open.json"
            model_key = R.PACKAGE + "models/turtlebot3_waffle/model.sdf"
            contract = json.dumps({"world_sha256": "a" * 64}).encode()
            proof = {world_key: {"sha256": "a" * 64},
                     contract_key: {"sha256": R.sha(contract)},
                     model_key: {"sha256": R.sha(model.read_bytes())}}
            metadata = {"scene": "open", "seed": 101, "command": [
                "world:=p1c_open.world", "gazebo_seed:=101",
                "evaluation_contract_path:=/task/open.json"],
                "physical_step_ns": 10**6, "policy_step_ns": 10**9,
                "quantum_steps": 20, "transport_environment": {"profile_sha256": "p"}}
            evaluator = {"world_sha256": "a" * 64, "task_contract_sha256": R.sha(contract),
                         "gazebo_seed": 101, "robot_count": 3, "world_file": "/world/open"}
            starts = [{"role": "gazebo_server", "process_name": "gzserver-1",
                       "argv": ["gzserver", "/world/open", "--seed=101"]}]
            for index, name in enumerate(R.ROBOTS):
                argv = ["spawn_entity.py", "-entity", name, "-robot_namespace", "/" + name,
                        "-file", str(model)]
                for key, value in zip(("-x", "-y", "-z", "-R", "-P", "-Y"), R.SPAWNS[name]):
                    argv.extend([key, str(value)])
                starts.append({"role": "owned_ros", "process_name": f"spawn_entity.py-{index + 2}",
                               "argv": argv})
            first = R.configuration(root, metadata, evaluator, starts,
                                    {contract_key: contract}, proof)
            self.assertEqual(set(first["semantic_input"]["spawns"]), set(R.ROBOTS))
            starts[1]["argv"][starts[1]["argv"].index("-x") + 1] = "2.0"
            with self.assertRaisesRegex(ValueError, "spawn pose differs"):
                R.configuration(root, metadata, evaluator, starts, {contract_key: contract}, proof)
            starts[1]["argv"][starts[1]["argv"].index("-x") + 1] = "0.0"
            model.write_bytes(b"changed model")
            with self.assertRaisesRegex(ValueError, "model path/current deployment differs"):
                R.configuration(root, metadata, evaluator, starts, {contract_key: contract}, proof)

    def test_frozen_source_and_world_catalogue_without_reading_any_runtime_results(self):
        blobs, proof = R.frozen_catalogue(ROOT)
        self.assertEqual(proof[R.PACKAGE + "worlds/p1c_open.world"]["sha256"],
                         json.loads(blobs[R.PACKAGE + "config/mr3_p1a/open.json"])["world_sha256"])

    def test_output_refuses_overwrite_before_analysis(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / "existing.json"
            output.write_text("preserved")
            with self.assertRaises(SystemExit):
                R.main(["--output", str(output)])
            self.assertEqual(output.read_text(), "preserved")


if __name__ == "__main__":
    unittest.main()
