"""Artificial received-map records only; no scene, World, episode or native run."""

import copy
import gzip
import hashlib
import importlib
import json
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from mr3_learning import audit_seed_inputs as audit
from mr3_learning.reach_gates import (
    ENV_SHA256, extend_exact_snapshot_validator, load_exact_protocol, project_exact_environment,
)


FREEZE = "a" * 40


class ExactSeedInputAuditTests(unittest.TestCase):
    def test_exact_environment_restores_whole_old_document_and_rejects_other_bytes(self):
        raw=(audit.ROOT/"ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/MR3_ENV_CONTRACT.md").read_bytes()
        old,proof=project_exact_environment(raw)
        self.assertEqual(hashlib.sha256(old).hexdigest(),ENV_SHA256)
        self.assertEqual(proof["prior_document_bytes"],len(old))
        self.assertLess(len(old),len(raw))
        with self.assertRaises(ValueError):project_exact_environment(raw+b"\n")

    def test_protocol_reader_changes_only_its_private_adapter_identity(self):
        from mr3_learning import audit_protocol as original
        previous = dict(original.PINS)
        protocol, proof = load_exact_protocol("a" * 64)
        relative = proof["versioned_adapter_pin"]["path"]
        self.assertEqual(original.PINS, previous)
        self.assertEqual(protocol.PINS, {**previous, relative: "a" * 64})
        self.assertTrue(proof["whole_source_inverse_equal"])
        self.assertEqual(proof["literal_changes"], [])
        for name in ("verify_sources", "prove_unsent", "prove_command_envelope"):
            new, old = getattr(protocol, name), getattr(original, name)
            self.assertEqual(new.__code__.co_code, old.__code__.co_code)
            self.assertEqual(new.__code__.co_names, old.__code__.co_names)

    def fixture(self, directory, *, navigation_missing=False, robot_overrides=None):
        package = ModuleType("multi_robot_exploration")
        package.__path__ = [str(audit.ROOT / audit.COMPONENT)]
        previous = {name: value for name, value in sys.modules.items()
                    if name == "multi_robot_exploration" or name.startswith("multi_robot_exploration.")}
        try:
            for name in list(sys.modules):
                if name == "multi_robot_exploration" or name.startswith("multi_robot_exploration."):
                    del sys.modules[name]
            sys.modules["multi_robot_exploration"] = package
            observation = importlib.import_module("multi_robot_exploration.mr3_observation")
            grid = np.zeros((41, 41), dtype=np.int16)
            grid[[0, -1], :] = -1; grid[:, [0, -1]] = -1
            payload = {"header": {"frame_id": "map", "stamp": {"sec": 10, "nanosec": 0}},
                "info": {"resolution": .1, "width": 41, "height": 41,
                         "map_load_time": {"sec": 0, "nanosec": 0},
                         "origin": {"position": {"x": -2.05, "y": -2.05, "z": 0.},
                                    "orientation": {"x": 0., "y": 0., "z": 0., "w": 1.}}},
                "data": grid.ravel().tolist()}
            raw = audit.canonical(payload); digest = hashlib.sha256(raw).hexdigest()
            source = {"epoch": "artificial", "sequence": 1, "version": 1,
                      "source_stamp": 10., "received_stamp": 10., "payload_sha256": digest}
            navigation = {**source, "composition_version": observation.NAVIGATION_COMPOSITION_VERSION,
                "input_own_map_payload_sha256": digest, "input_shared_map_payload_sha256": digest,
                "input_own_source_stamp": 10., "shared_map_version": 1,
                "received_stamp_scope": "artificial"}
            robots = [{"name": name, "x": x, "y": 0., "yaw": 0., "v": 0., "w": 0., "valid": True,
                       "source_stamp": 10., "received_stamp": 10.,
                       "navigation": {"phase": "idle", "goal_id": None, "goal_x": None, "goal_y": None,
                                      "commitment_until": 0.}}
                      for name, x in zip(audit.ROBOTS, (-1., 0., 1.))]
            for robot in robots:
                if navigation_missing:
                    robot["navigation"] = {}
                robot.update(copy.deepcopy(robot_overrides or {}))
            record = {"grid": grid, "resolution": .1, "origin": (-2.05, -2.05)}
            snapshot = observation.build_snapshot(grid, .1, (-2.05, -2.05), robots, 10., "artificial", 1, 0,
                map_source_stamp=10., map_received_stamp=10., map_sources={n: source for n in audit.ROBOTS},
                task_start=10., robot_maps={n: {**record, **source} for n in audit.ROBOTS},
                navigation_maps={n: {**record, **navigation} for n in audit.ROBOTS}, seed_rule=audit.RULE)
        finally:
            for name in list(sys.modules):
                if name == "multi_robot_exploration" or name.startswith("multi_robot_exploration."):
                    del sys.modules[name]
            sys.modules.update(previous)
        metadata = {"epoch": "artificial", "map_version": 1, "map_payload_sha256": digest,
            "map_source_stamp": 10., "map_received_stamp": 10., "map_sources": {n: source for n in audit.ROBOTS},
            "navigation_sources": {n: navigation for n in audit.ROBOTS},
            "navigation_composition": {"version": "mr3-own-known-shared-unknown-v1"}}
        maps = directory / "observation_inputs/maps"; maps.mkdir(parents=True)
        (maps / (digest + ".json.gz")).write_bytes(gzip.compress(raw, mtime=0))
        manifests = directory / "observation_inputs/snapshots"; manifests.mkdir()
        manifest = {"schema": "mr3-observation-input-archive-v2", "scope": "encoder_result_before_publication",
            **{key: snapshot[key] for key in ("epoch", "sequence", "candidate_version", "source_stamp")},
            "snapshot_digest": snapshot["digest"], "metadata": metadata,
            "maps": {name: {"payload_sha256": digest, "artifact": f"maps/{digest}.json.gz"}
                     for name in ("fused", *audit.ROBOTS, *("navigation:" + n for n in audit.ROBOTS))}}
        def write(name, value):
            (directory / name).write_text(json.dumps(value) + "\n")
        write("metadata.json", {"freeze": FREEZE, "epoch": "artificial", "seed_rule": audit.RULE})
        write("supervisor_metadata.json", {"seed_rule": audit.RULE})
        write("summary.json", {"artificial_fixture": True})
        write("transitions.jsonl", {"kind": "reset", "snapshot": snapshot, "info": {"watermarks": metadata}})
        events = [{"kind": "task_start", "payload": {"start_sim_time_sec": 10.}},
                  {"kind": "observation", "payload": snapshot},
                  {"kind": "snapshot_completed", "payload": {"ok": True}}]
        (directory / "adapter.jsonl").write_text("".join(json.dumps(value) + "\n" for value in events))
        write(str(manifests.relative_to(directory) / f"{snapshot['sequence']:08d}_{snapshot['digest']}.json"), manifest)
        return snapshot

    @staticmethod
    def source(argv, **kwargs):
        # Only Git identity is artificial; replay compiles actual pure sources.
        return (audit.ROOT / argv[-1].split(":", 1)[1]).read_bytes()

    def test_complete_artificial_seven_map_and_snapshot_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); self.fixture(directory)
            with patch.object(audit.subprocess, "check_output", side_effect=self.source):
                result = audit.audit_episode(directory, FREEZE)
            self.assertTrue(result["passed"])
            self.assertEqual(result["exact_full_snapshot_replays"], 1)
            self.assertEqual(len(result["source_proof"]), 9)
            self.assertTrue(any(path.endswith("audit_seed_inputs.py") for path in result["source_proof"]))
            self.assertIn("normalized sufficient fields",result["robot_recovery_scope"])

    def test_standalone_replay_rejects_a_nonfrozen_helper_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);self.fixture(directory)
            def source(argv,**kwargs):
                raw=self.source(argv,**kwargs)
                return raw+b"\n" if argv[-1].endswith("navigation_archive.py") else raw
            with patch.object(audit.subprocess,"check_output",side_effect=source), \
                    self.assertRaisesRegex(ValueError,"source differs from native freeze"):
                audit.audit_episode(directory,FREEZE)

    def test_missing_navigation_recovers_empty_input_in_full_snapshot_replay(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            snapshot=self.fixture(directory,navigation_missing=True)
            self.assertTrue(all(robot["navigation"]["missing"] for robot in snapshot["robots"]))
            with patch.object(audit.subprocess,"check_output",side_effect=self.source):
                result=audit.audit_episode(directory,FREEZE)
            self.assertTrue(result["passed"])
            self.assertEqual(result["exact_full_snapshot_replays"],1)

    def test_other_normalized_missing_values_remain_sufficient_for_full_replay(self):
        variants=(
            {"x":None,"valid":False,"source_stamp":None,"received_stamp":None,"activity":None},
            {"history":[{"x":1.,"y":None,"source_stamp":9.},
                        {"x":.1,"y":.2,"source_stamp":9.9}]},
            {"navigation":{"phase":"invalid","source_stamp":None,"received_stamp":None,
                           "sequence":None,"owned":False,"commitment_until":None}},
        )
        for values in variants:
            with self.subTest(values=values),tempfile.TemporaryDirectory() as temporary:
                directory=Path(temporary);self.fixture(directory,robot_overrides=values)
                with patch.object(audit.subprocess,"check_output",side_effect=self.source):
                    result=audit.audit_episode(directory,FREEZE)
                self.assertTrue(result["passed"])

    def test_changed_actor_choice_cannot_pass_only_by_rehashing_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary); self.fixture(directory)
            path = directory / "transitions.jsonl"
            record = json.loads(path.read_text()); record["snapshot"]["candidates"][0]["x"] = 123.
            record["snapshot"]["candidate_version"] = hashlib.sha256(audit.canonical(
                {k: record["snapshot"][k] for k in
                 ("epoch", "map_version", "sequence", "candidate_rule", "candidates", "path_maps")})).hexdigest()
            record["snapshot"]["digest"] = hashlib.sha256(audit.canonical(
                {k: v for k, v in record["snapshot"].items() if k != "digest"})).hexdigest()
            path.write_text(json.dumps(record) + "\n")
            old = next((directory / "observation_inputs/snapshots").glob("*.json"))
            manifest = json.loads(old.read_text()); old.unlink()
            manifest.update(candidate_version=record["snapshot"]["candidate_version"],
                            snapshot_digest=record["snapshot"]["digest"])
            new = old.with_name(f"00000000_{record['snapshot']['digest']}.json")
            new.write_text(json.dumps(manifest) + "\n")
            events = [json.loads(line) for line in (directory / "adapter.jsonl").read_text().splitlines()]
            next(value for value in events if value["kind"] == "observation")["payload"] = record["snapshot"]
            (directory / "adapter.jsonl").write_text("".join(json.dumps(value) + "\n" for value in events))
            with patch.object(audit.subprocess, "check_output", side_effect=self.source), self.assertRaises(ValueError):
                audit.audit_episode(directory, FREEZE)

    def test_mixed_seed_or_unreferenced_map_is_rejected(self):
        for fault in ("worker", "supervisor", "extra_map"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary); self.fixture(directory)
                if fault == "extra_map":
                    (directory / "observation_inputs/maps/extra.json.gz").write_bytes(b"unreferenced")
                else:
                    path = directory / ("metadata.json" if fault == "worker" else "supervisor_metadata.json")
                    value = json.loads(path.read_text()); value["seed_rule"] = "legacy"
                    path.write_text(json.dumps(value))
                with patch.object(audit.subprocess, "check_output", side_effect=self.source), self.assertRaises(ValueError):
                    audit.audit_episode(directory, FREEZE)

    def test_exact_validator_retains_original_gate_and_rejects_legacy_or_rule_changes(self):
        candidate = SimpleNamespace(CANDIDATE_RULE_V5={"version": "old", "path_body_clearance_m": .29},
                                    CANDIDATE_RULES={"old": {"version": "old"}})
        calls = []
        owner = SimpleNamespace(validate_snapshot=lambda snapshot, epoch: calls.append((snapshot, epoch)))
        extend_exact_snapshot_validator(lambda *args: None, owner, candidate)
        rule = candidate.CANDIDATE_RULES[audit.VERSION]
        snapshot = {"schema": "mr3-observation-v3", "candidate_rule": copy.deepcopy(rule)}
        owner.validate_snapshot(snapshot, "artificial")
        self.assertEqual(len(calls), 1)
        for key, value in (("version", "old"), ("path_body_clearance_m", .28), ("seed_rule", "legacy")):
            changed = copy.deepcopy(snapshot); changed["candidate_rule"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): owner.validate_snapshot(changed, "artificial")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
