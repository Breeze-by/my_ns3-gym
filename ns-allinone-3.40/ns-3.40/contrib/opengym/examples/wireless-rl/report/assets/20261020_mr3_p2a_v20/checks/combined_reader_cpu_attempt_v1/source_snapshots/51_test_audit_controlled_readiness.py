"""Real controlled-release provenance composes with immutable W7 ACK/contact hooks."""

import ast
import copy
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

from mr3_learning import audit_controlled_physics as shared
from mr3_learning.audit_motion import _audit_records, require, same_json
from mr3_learning.audit_ppo import TASK_BASE_FREEZE
from unittest.mock import patch
from mr3_learning import audit_motion
from mr3_learning.tests import test_audit_controlled_physics as physics_tests
from mr3_learning.tests.test_audit_motion import (
    ROBOTS, helper_module, write_controlled_fixture, write_files,
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def replace_value(value, before, after):
    if same_json(value, before):
        return copy.deepcopy(after)
    if isinstance(value, dict):
        return {key: replace_value(item, before, after) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_value(item, before, after) for item in value]
    return value


def readiness_fixture(directory, helper):
    files = write_controlled_fixture(directory, helper)
    epoch, release = files["metadata.json"]["epoch"], 1_020_000_000
    files["metadata.json"]["reset_handshake"] = shared.CONTROLLED_HANDSHAKE
    files["metadata.json"]["command"] = [f"{key}:={value}" for key, value in {
        "execution_mode": "adapter", "mr3_stepped": "true", "training_reward_enabled": "true",
        "enable_task_evaluator": "true", "robot_count": "3", "evaluation_episode_id": epoch,
        "mr3_episode_epoch": epoch}.items()]
    control = files["control_phase_worker.jsonl"]

    def phase(component, operation, kind="ack_consumed"):
        return next(row for row in control if row["kind"] == kind
                    and row.get("component") == component
                    and row.get("ack", row.get("request", {})).get("operation") == operation
                    and row.get("ack", row.get("request", {})).get("target_time_ns")
                    == (1_000_000_000 if operation == "takeover" else release))

    for component, scope in (("state", "periodic_state_publication_disabled"),
                             ("peer", "automatic_obstacle_timer_disabled")):
        before = phase(component, "takeover")["ack"]
        files = replace_value(files, before, {**before, "scope": scope})
        control = files["control_phase_worker.jsonl"]
    bundle = copy.deepcopy(next(row["payload"] for row in files["motion_safety.jsonl"]
                                if row["kind"] == "received_states"))
    bundle.update(sequence=2, map_payload_sha256="b" * 64, map_version=2)
    for row in files["motion_safety.jsonl"]:
        if row["kind"] == "received_states":
            row["payload"] = copy.deepcopy(bundle)
    state_before = phase("state", "commit")["ack"]
    sent = phase("state", "commit", "request")["wall_monotonic_ns"]
    refs, sides, inputs, callbacks = {}, [], {}, []
    for index, name in enumerate(ROBOTS):
        refs[name] = {"sequence": 1, "version": 1, "source_ns": 1_000_000_000,
                      "odom_source_ns": 1_000_000_000, "tf_source_ns": 1_000_000_000,
                      "source_stamp": 1.}
        for kind in ("odom", "tf"):
            raw = {"fixture_local_input": kind, "robot": name}
            raw_sha = digest(raw)
            refs[name].update({kind + "_sha256": raw_sha,
                               kind + "_topic": f"/mr3/received/{name}/{kind}"})
            inputs[f"{kind}:{name}"] = {"input_sequence": index + 1, "raw_sha256": raw_sha,
                                        "received_wall_monotonic_ns": sent + 3}
            callbacks.append({"kind": "received_" + kind, "epoch": epoch,
                              "clock_ns": release, "wall_monotonic_ns": sent + 3,
                              "payload": {"robot": name, "input_sequence": index + 1,
                                          "raw": raw, "raw_sha256": raw_sha,
                                          "received_wall_monotonic_ns": sent + 3}})
        sides.append({"robot": name, "envelope_sequence": 1,
                      **{key: value for key, value in refs[name].items()
                         if key.endswith("_topic") or key.endswith("_sha256")}})
    state = {**state_before, "bundle_sha256": digest(bundle), "robots": refs,
             "side_publish_started_wall_monotonic_ns": sent + 2,
             "bundle_publish_started_wall_monotonic_ns": sent + 3,
             "bundle_publish_completed_wall_monotonic_ns": sent + 4}
    files = replace_value(files, state_before, state)
    control = files["control_phase_worker.jsonl"]
    inputs["bundle"] = {"message_sha256": digest(bundle), "state_sequence": 2,
                        "received_wall_monotonic_ns": sent + 4}
    callbacks.append({"kind": "received_state_bundle", "epoch": epoch,
                      "clock_ns": release, "wall_monotonic_ns": sent + 4,
                      "payload": {"message": bundle,
                                 "received_wall_monotonic_ns": sent + 4}})
    peer_before = phase("peer", "commit")["ack"]
    peer_sent = phase("peer", "commit", "request")["wall_monotonic_ns"]
    publications = [{"robot": name, "kind": kind, "message_sha256": "c" * 64}
                    for name in ROBOTS for kind in ("scan", "cloud")]
    peer = {**peer_before, "bundle_sha256": state["bundle_sha256"],
            "inputs": inputs, "publications": publications,
            "state_sequence": 2, "obstacle_publication_sha256": digest(publications)}
    files = replace_value(files, peer_before, peer)
    control = files["control_phase_worker.jsonl"]
    information, peers = [], callbacks
    for operation in ("takeover", "commit"):
        for component, rows in (("state", information), ("peer", peers)):
            req = phase(component, operation, "request")
            ack = phase(component, operation)["ack"]
            wall = req["wall_monotonic_ns"]
            rows.append({"kind": "state_phase_request" if component == "state"
                         else "request_received", "epoch": epoch,
                         "clock_ns": ack["clock_ns"], "wall_monotonic_ns": wall + 1,
                         "payload": {"request": req["request"], "duplicate": False}
                         if component == "state" else req["request"]})
            rows.append({"kind": "state_phase_ack" if component == "state" else "ack_published",
                         "epoch": epoch, "clock_ns": ack["clock_ns"],
                         "wall_monotonic_ns": wall + 7,
                         "payload": {"ack": ack, "cached": False,
                                     "publish_started_wall_monotonic_ns": wall + 5,
                                     "publish_completed_wall_monotonic_ns": wall + 6}})
    information.append({"kind": "state_publish", "epoch": epoch, "clock_ns": release,
                        "wall_monotonic_ns": sent + 4,
                        "payload": {"message": bundle, "message_sha256": digest(bundle),
                                    "side_publications": sides,
                                    "side_publish_started_wall_monotonic_ns": sent + 2,
                                    "publish_started_wall_monotonic_ns": sent + 3,
                                    "publish_completed_wall_monotonic_ns": sent + 4,
                                    "scope": "actual_publish_calls_returned"}})
    peers.extend([
        {"kind": "inputs_matched", "epoch": epoch, "clock_ns": release,
         "wall_monotonic_ns": peer_sent + 2,
         "payload": {"request": phase("peer", "commit", "request")["request"],
                     "inputs": inputs}},
        {"kind": "obstacles_published", "epoch": epoch, "clock_ns": release,
         "wall_monotonic_ns": peer_sent + 3,
         "payload": {"request_id": peer["request_id"], "publications": publications}},
    ])
    files["information_states.jsonl"] = sorted(
        information, key=lambda row: row["wall_monotonic_ns"])
    files["peer_phase.jsonl"] = sorted(peers, key=lambda row: row["wall_monotonic_ns"])
    reset = files["transitions.jsonl"][0]
    snapshot = reset["snapshot"]
    snapshot.update(sequence=1, map_version=2, map={"version": 2})
    water = {"state_sequence": 2, "map_payload_sha256": "b" * 64, "map_version": 2}
    prewarm = {"schema": "mr3-initial-inputs-ready-v1", "epoch": epoch, "stamp": .9,
               "state_sequence": 1, "map_version": 1, "map_payload_sha256": "d" * 64,
               "map_source_stamp": .8, "map_received_stamp": .9,
               "robots": [{"name": name, "source_stamp": .8, "received_stamp": .9}
                          for name in ROBOTS],
               "map_sources": {name: {"source_stamp": .8, "received_stamp": .9,
                                      "payload_sha256": "e" * 64} for name in ROBOTS}}
    storage = next(row for row in files["drive_phase_worker.jsonl"]
                   if row["kind"] == "ack_consumed"
                   and row["expected_motion"]["clock_ns"] == release)
    reset["info"].update(epoch=epoch, scheduler="mr3-physical-20ms-v1",
                         initial_pause_time_ns=1_000_000_000, initial_inputs_ready=prewarm,
                         initial_drive_receipts=storage["receipts"], watermarks=water,
                         reward_diagnostics={"kind": "reward_reset_binding", "epoch": epoch,
                                             "sequence": 0, "reward": 0., "reset_bound": True,
                                             "delta_sim_time": 0, "terminated": False,
                                             "truncated": False, "step_start": 1.02,
                                             "effective_step_end": 1.02,
                                             "map_watermark": {"payload_sha256": "b" * 64}})
    projection = {"sequence": 2, "information_diagnostics": None,
                  "robots": [{key: robot.get(key) for key in (
                      "name", "source_stamp", "received_stamp", "odom_source_stamp",
                      "tf_source_stamp", "tf_validity_stamp", "valid", "epoch", "odometry")}
                      for robot in bundle["robots"]]}

    def adapter(kind, payload):
        return {"epoch": epoch, "kind": kind, "stamp": 1.02, "payload": payload}
    files["adapter.jsonl"] = [
        adapter("initial_inputs_ready", prewarm), adapter("state_update", projection),
        adapter("snapshot_requested", {"request_id": "s1", "target_time_ns": release,
                                       "expected_map_sha256": "b" * 64}),
        adapter("task_start", {"start_sim_time_sec": 1.02}), adapter("observation", snapshot),
        adapter("snapshot_completed", {"request_id": "s1", "ok": True, "watermarks": water}),
    ]
    ack = {"schema": "mr3-evaluator-clock-terminal-ack-v1", "epoch": epoch,
           "request_id": "phase1", "target_time_ns": release, "evaluator_clock_ns": release,
           "ok": True, "status": "LIVE", "terminal": None}
    wall = storage["wall_monotonic_ns"]
    files["evaluator_phase_worker.jsonl"] = [
        {"kind": "request", "wall_monotonic_ns": wall + 1,
         "request": {"epoch": epoch, "request_id": "phase1", "target_time_ns": release}},
        {"kind": "ack_received", "wall_monotonic_ns": wall + 2, "ack": ack},
        {"kind": "ack_consumed", "wall_monotonic_ns": wall + 3, "ack": ack},
    ]
    write_files(directory, files)
    return files


class ControlledReadinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helper = helper_module()
        root = Path(__file__).resolve().parents[8]
        relative = "ros2_ws/ros2-multi-robot-automap/scripts/audit_mr3_env.py"
        raw = subprocess.check_output(["git", "show", TASK_BASE_FREEZE + ":" + relative], cwd=root)
        function = next(node for node in ast.parse(raw).body if isinstance(node, ast.FunctionDef)
                        and node.name == "audit_initial_inputs_ready")
        namespace = {"require": require, "number": lambda value: type(value) in (int, float)
                     and math.isfinite(value), "NS": 10**9, "ROBOTS": ROBOTS, "re": re}
        exec(compile(ast.Module(body=[function], type_ignores=[]),
                     TASK_BASE_FREEZE + ":" + relative, "exec"), namespace)
        cls.original = staticmethod(namespace["audit_initial_inputs_ready"])
        for name in ("Evidence", "nanoseconds", "audit_physics"):
            item = next(node for node in ast.parse(raw).body
                        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name)
            namespace.update(json=json, hashlib=hashlib, gzip=gzip, Path=Path)
            exec(compile(ast.Module(body=[item], type_ignores=[]),
                         TASK_BASE_FREEZE + ":" + relative, "exec"), namespace)
        cls.evidence = namespace["Evidence"]
        cls.nanoseconds = staticmethod(namespace["nanoseconds"])
        cls.physics = staticmethod(namespace["audit_physics"])
        contact_path = root / ("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
                               "report/assets/20261015_mr3_p1c/audit_mr3_env_contact_phase_v2.py")
        contact = next(node for node in ast.parse(contact_path.read_bytes()).body
                       if isinstance(node, ast.FunctionDef) and node.name == "release_context")
        context = {"require": require, "FREEZE": "0" * 40}
        exec(compile(ast.Module(body=[contact], type_ignores=[]),
                     str(contact_path), "exec"), context)
        cls.contact_context = staticmethod(context["release_context"])

    def run_fixture(self, directory, files):
        motion = _audit_records(directory, self.helper, {})
        auditor = SimpleNamespace(audit_initial_inputs_ready=self.original)
        shared.dispatch_controlled_readiness(auditor, [directory], {directory: motion})
        return auditor, auditor.audit_initial_inputs_ready(
            files["metadata.json"], files["transitions.jsonl"], files["adapter.jsonl"],
            files["metadata.json"]["epoch"])

    def test_actual_controlled_chain_composes_original_prewarm_without_changing_raw(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = readiness_fixture(directory, self.helper)
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            with self.assertRaisesRegex(ValueError, "unknown reset handshake"):
                self.original(files["metadata.json"], files["transitions.jsonl"],
                              files["adapter.jsonl"], files["metadata.json"]["epoch"])
            auditor, result = self.run_fixture(directory, files)
            self.assertTrue(result["required"] and result["proven"])
            self.assertEqual(result["protocol"], shared.CONTROLLED_HANDSHAKE)
            self.assertEqual(result["controlled_release"]["state_sequence"], 2)
            self.assertIn("metadata view only", result["prewarm_ack_subpredicate"]["scope"])
            # Same hook serves the original contact release_context call too.
            self.assertEqual(result, auditor.audit_initial_inputs_ready(
                files["metadata.json"], files["transitions.jsonl"], files["adapter.jsonl"],
                files["metadata.json"]["epoch"]))
            self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})

    def test_modern_native_metadata_cannot_be_disguised_by_legacy_call_arguments(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = readiness_fixture(directory, self.helper)
            supplied = copy.deepcopy(files["metadata.json"])
            supplied.pop("execution_phase_protocol")
            supplied["reset_handshake"] = "delivered_inputs_before_pause-v1"
            auditor = SimpleNamespace(audit_initial_inputs_ready=self.original)
            shared.dispatch_controlled_readiness(auditor, [directory], {})
            with self.assertRaisesRegex(ValueError, "call metadata differs"):
                auditor.audit_initial_inputs_ready(supplied, files["transitions.jsonl"],
                                                   files["adapter.jsonl"], supplied["epoch"])

    def test_missing_or_mixed_protocol_cannot_fall_back_to_legacy(self):
        for mutation in ("missing_handshake", "old_handshake", "missing_control",
                         "unknown_control"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = readiness_fixture(directory, self.helper)
                meta = files["metadata.json"]
                if mutation == "missing_handshake":
                    meta.pop("reset_handshake")
                elif mutation == "old_handshake":
                    meta["reset_handshake"] = "delivered_inputs_before_pause-v1"
                elif mutation == "missing_control":
                    meta.pop("execution_phase_protocol")
                else:
                    meta["execution_phase_protocol"] = "unknown"
                write_files(directory, files)
                auditor = SimpleNamespace(audit_initial_inputs_ready=self.original)
                shared.dispatch_controlled_readiness(auditor, [directory], {})
                with self.assertRaisesRegex(ValueError, "declarations"):
                    auditor.audit_initial_inputs_ready(meta, files["transitions.jsonl"],
                                                       files["adapter.jsonl"], meta["epoch"])

    def test_missing_real_chain_or_storage_or_adapter_binding_is_rejected(self):
        for mutation in ("state_publish", "peer_publish", "side_callback", "native_storage",
                         "evaluator", "snapshot_watermark", "seq0", "prewarm"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = readiness_fixture(directory, self.helper)
                if mutation == "state_publish":
                    files["information_states.jsonl"] = [
                        r for r in files["information_states.jsonl"]
                        if r["kind"] != "state_publish"]
                elif mutation == "peer_publish":
                    files["peer_phase.jsonl"] = [r for r in files["peer_phase.jsonl"]
                                                 if r["kind"] != "obstacles_published"]
                elif mutation == "side_callback":
                    files["peer_phase.jsonl"] = [r for r in files["peer_phase.jsonl"]
                                                 if r["kind"] != "received_tf"]
                elif mutation == "native_storage":
                    files["drive_tb2.jsonl"] = [r for r in files["drive_tb2.jsonl"]
                                                if not (r["kind"] == "command_received"
                                                        and r["target_clock_ns"] == 1_020_000_000)]
                elif mutation == "evaluator":
                    files["evaluator_phase_worker.jsonl"][1]["ack"]["status"] = "TERMINAL"
                elif mutation == "snapshot_watermark":
                    files["transitions.jsonl"][0]["info"]["watermarks"]["state_sequence"] = True
                elif mutation == "seq0":
                    files["transitions.jsonl"][0]["info"]["reward_diagnostics"]["sequence"] = True
                else:
                    files["adapter.jsonl"][0]["payload"]["stamp"] = 2.
                write_files(directory, files)
                with self.assertRaises((ValueError, KeyError)):
                    self.run_fixture(directory, files)

    def test_publish_receipt_may_precede_producer_return_but_not_publish_start(self):
        for legitimate in (True, False):
            with self.subTest(legitimate=legitimate), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = readiness_fixture(directory, self.helper)
                row = next(r for r in files["information_states.jsonl"]
                           if r["kind"] == "state_phase_ack"
                           and r["payload"]["ack"]["operation"] == "commit")
                received = next(r for r in files["control_phase_worker.jsonl"]
                                if r["kind"] == "ack_received" and r["component"] == "state"
                                and r["ack"]["operation"] == "commit")["wall_monotonic_ns"]
                if legitimate:
                    row["payload"]["publish_completed_wall_monotonic_ns"] = received + 1
                else:
                    row["payload"]["publish_started_wall_monotonic_ns"] = received + 1
                    row["payload"]["publish_completed_wall_monotonic_ns"] = received + 2
                write_files(directory, files)
                if legitimate:
                    self.run_fixture(directory, files)
                else:
                    with self.assertRaisesRegex(ValueError, "publication window"):
                        self.run_fixture(directory, files)

    def test_cached_proof_rejects_changes_to_each_additional_raw_producer(self):
        for filename in ("information_states.jsonl", "peer_phase.jsonl",
                         "evaluator_phase_worker.jsonl", "drive_tb1.jsonl"):
            with self.subTest(filename=filename), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = readiness_fixture(directory, self.helper)
                auditor, _ = self.run_fixture(directory, files)
                with (directory / filename).open("a") as stream:
                    stream.write("\n")
                with self.assertRaisesRegex(ValueError, "raw input changed"):
                    auditor.audit_initial_inputs_ready(
                        files["metadata.json"], files["transitions.jsonl"],
                        files["adapter.jsonl"], files["metadata.json"]["epoch"])

    def test_original_contact_entry_and_actual_ppo_call_share_the_new_proof(self):
        block = physics_tests.SharedControlledPhysicsTests().ppo_call_block()
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            readiness_fixture(directory, self.helper)
            auditor = SimpleNamespace(audit_physics=self.physics,
                                      audit_initial_inputs_ready=self.original,
                                      Evidence=self.evidence, nanoseconds=self.nanoseconds)

            def traverse(base, actual, command, directories):
                self.assertEqual(directories, [directory])
                # Execute the entire unchanged contact release_context, including
                # its original physics, seq0, actual task_start, and readiness calls.
                return self.contact_context(actual, directory)
            namespace = {"dispatch_controlled_physics": shared.dispatch_controlled_physics,
                         "dispatch_controlled_readiness": shared.dispatch_controlled_readiness,
                         "native_auditor": auditor, "native": directory,
                         "phase": SimpleNamespace(corrected_audit=traverse),
                         "base": object(), "command": object(), "row": {}}
            with patch.object(audit_motion, "load_frozen_helper", return_value=(self.helper, {})):
                exec(block, namespace)
            self.assertTrue(namespace["row"]["native"]["actual_seq0_binding"])
            self.assertEqual(namespace["row"]["native"]["release_time_ns"], 1_020_000_000)
            self.assertIs(auditor.audit_physics, self.physics)
            self.assertIs(auditor.audit_initial_inputs_ready, self.original)

    def test_later_same_clock_map_is_legal_but_snapshot_and_seq0_must_match(self):
        for mutation in (None, "snapshot", "seq0"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                files = readiness_fixture(directory, self.helper)
                # State was actually committed with map b/version2. A later
                # same-clock map delivery legitimately supplies c/version3.
                reset = files["transitions.jsonl"][0]
                info, snapshot = reset["info"], reset["snapshot"]
                info["watermarks"].update(map_payload_sha256="c" * 64, map_version=3)
                info["reward_diagnostics"]["map_watermark"]["payload_sha256"] = "c" * 64
                snapshot.update(map_version=3, map={"version": 3})
                for row in files["adapter.jsonl"]:
                    if row["kind"] == "snapshot_requested":
                        row["payload"]["expected_map_sha256"] = "c" * 64
                if mutation == "snapshot":
                    snapshot["map"]["version"] = 4
                elif mutation == "seq0":
                    info["reward_diagnostics"]["map_watermark"]["payload_sha256"] = "d" * 64
                write_files(directory, files)
                if mutation is None:
                    self.run_fixture(directory, files)
                else:
                    with self.assertRaises(ValueError):
                        self.run_fixture(directory, files)

    def test_evaluator_initial_live_must_precede_first_actual_task_advance(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = readiness_fixture(directory, self.helper)
            permit = next(row for row in files["drive_phase_worker.jsonl"]
                          if row.get("start_time_ns") == 1_020_000_000
                          and row["kind"] == "advance_permitted")
            files["evaluator_phase_worker.jsonl"][-1]["wall_monotonic_ns"] = \
                permit["wall_monotonic_ns"] + 1
            write_files(directory, files)
            with self.assertRaisesRegex(ValueError, "first task physics"):
                self.run_fixture(directory, files)

    def test_legacy_metadata_and_function_result_are_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            files = readiness_fixture(directory, self.helper)
            meta = files["metadata.json"]
            meta.pop("execution_phase_protocol")
            meta["reset_handshake"] = "delivered_inputs_before_pause-v1"
            write_files(directory, files)
            auditor = SimpleNamespace(audit_initial_inputs_ready=self.original)
            shared.dispatch_controlled_readiness(auditor, [directory], {})
            args = (meta, files["transitions.jsonl"], files["adapter.jsonl"], meta["epoch"])
            self.assertEqual(auditor.audit_initial_inputs_ready(*args), self.original(*args))


if __name__ == "__main__":
    unittest.main()
