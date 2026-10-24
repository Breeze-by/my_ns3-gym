"""Counter/codec/persistence fixtures, without a simulator or policy."""
from concurrent.futures import ThreadPoolExecutor
import base64
import copy
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import zlib

import numpy as np

from mr3_learning import proxy2d_capacity as capacity
from mr3_learning.proxy2d_capacity import StepBudget, Trace
from mr3_learning.proxy2d_codec import canonical_bytes, decode_arrays, encode_arrays, tensor_proofs
from mr3_learning.proxy2d_process import pidfd_open, pidfd_send_signal


class CapacityFixtures(unittest.TestCase):
    def test_only_two_exact_bounded_specs_are_accepted(self):
        for kind, attempts, seconds in (("profile", 8, 600), ("short_capacity", 240, 1800)):
            spec = capacity.activity_spec(kind)
            self.assertEqual(capacity.validate_activity_spec(spec), spec)
            self.assertEqual(spec["max_attempts"], attempts)
            self.assertEqual(spec["activity_seconds"], seconds)
            for key, value in (("steps_per_episode", 8.), ("max_attempts", attempts + 1),
                               ("extra", False), ("cells", [["open", 103]])):
                with self.subTest(kind=kind, key=key), self.assertRaises(ValueError):
                    capacity.validate_activity_spec({**spec, key: value})
        with self.assertRaises(ValueError):
            capacity.activity_spec("arbitrary")

    def test_expired_group_does_not_consume_next_groups_shared_counter_or_deadline(self):
        budget = StepBudget(1000 * 10**9, maximum=240)
        with patch.object(capacity.time, "monotonic_ns", return_value=100 * 10**9):
            self.assertFalse(budget.reserve(deadline_ns=145 * 10**9))
            self.assertEqual(budget.reserve(deadline_ns=900 * 10**9), 1)
        self.assertEqual(budget.deadline_ns, 1000 * 10**9)
        self.assertFalse(budget.stop.is_set())

    def test_full_behavior_exact_three_worker_cells_and_budgets(self):
        spec = capacity.activity_spec("full_behavior")
        expected = {"schema": "mr3-proxy2d-activity-spec-v1", "kind": "full_behavior",
            "groups": [3], "cells": [["open", 101], ["rooms", 101], ["corridors", 101]],
            "worker_cells": [[[["open", 101]], [["rooms", 101]], [["corridors", 101]]]],
            "steps_per_episode": 300, "max_attempts": 900, "activity_seconds": 3600}
        self.assertEqual(spec, expected)
        for key, value in (("steps_per_episode", 300.), ("max_attempts", 901), ("groups", [1, 3]),
                ("worker_cells", [[[spec["cells"]] for _ in range(3)]]),
                ("cells", [["open", 103], ["rooms", 101], ["corridors", 101]]), ("extra", False)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                capacity.validate_activity_spec({**spec, key: value})

    def test_full_behavior_collect_assigns_one_scene_per_worker_and_only900_tickets(self):
        calls = []
        tickets = []
        def worker(group, env_id, budget, freeze, **kwargs):
            calls.append((env_id, kwargs))
            episodes = []
            for index, (scene, seed) in enumerate(kwargs["cells"], 1):
                for _ in range(kwargs["steps_per_episode"]):
                    ticket = budget.reserve(deadline_ns=kwargs["group_deadline_ns"])
                    self.assertTrue(ticket)
                    tickets.append(ticket)
                    budget.returned()
                episodes.append({"env_id": env_id, "episode_index": index, "scene": scene, "seed": seed})
            return {"episodes": episodes, "error": None, "saved_identities": []}
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(capacity.time, "monotonic_ns", return_value=10**12), \
                patch.object(capacity, "collect_worker", side_effect=worker):
            summary = capacity.collect(Path(tmp), "a" * 40, {}, {}, 10**12, 10**12 + 3600 * 10**9,
                activity_spec=capacity.activity_spec("full_behavior"), group_wall_seconds=[2100], profile=False)
        self.assertEqual(summary["step_attempts"], 900)
        self.assertEqual(summary["step_returns"], 900)
        self.assertEqual(sorted(tickets), list(range(1, 901)))
        self.assertEqual(len(summary["groups"]), 1)
        self.assertEqual(len(summary["groups"][0]["episodes"]), 3)
        self.assertEqual(summary["groups"][0]["workers"], 3)
        self.assertEqual(summary["collection_deadline_ns"], 10**12 + 2100 * 10**9)
        for env_id, kwargs in sorted(calls):
            self.assertEqual(kwargs["cells"], [[("open", "rooms", "corridors")[env_id], 101]])
            self.assertEqual(kwargs["steps_per_episode"], 300)
            self.assertFalse(kwargs["profile"])

    def test_full_behavior_changed_wall_or_profile_is_rejected_before_collecting(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(capacity, "collect_worker") as worker:
            for walls, profile in (([2400], False), ([2100], True), ([2100.], False), ([700, 700, 700], False)):
                with self.subTest(walls=walls, profile=profile), self.assertRaises(ValueError):
                    capacity.collect(Path(tmp), "a" * 40, {}, {}, 10**12, 10**12 + 3600 * 10**9,
                        activity_spec=capacity.activity_spec("full_behavior"), group_wall_seconds=walls, profile=profile)
            worker.assert_not_called()

    def test_collect_fixed_reservations_and_shared_global_budget_without_an_environment(self):
        for kind, walls, maximum, seconds in (("profile", [240], 8, 600),
                                               ("short_capacity", [400, 800], 240, 1800)):
            calls = []
            def worker(group, env_id, budget, freeze, **kwargs):
                calls.append((env_id, kwargs))
                episodes = []
                for index, (scene, seed) in enumerate(kwargs["cells"], 1):
                    for _ in range(kwargs["steps_per_episode"]):
                        self.assertTrue(budget.reserve(deadline_ns=kwargs["group_deadline_ns"]))
                        budget.returned()
                    episodes.append({"env_id": env_id, "episode_index": index, "scene": scene, "seed": seed})
                return {"episodes": episodes, "error": None, "saved_identities": []}
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp, \
                    patch.object(capacity.time, "monotonic_ns", return_value=10**12), \
                    patch.object(capacity, "collect_worker", side_effect=worker):
                summary = capacity.collect(Path(tmp), "a" * 40, {}, {}, 10**12, 10**12 + seconds * 10**9,
                    activity_spec=capacity.activity_spec(kind), group_wall_seconds=walls, profile=kind == "profile")
                self.assertEqual(summary["step_attempts"], maximum)
                self.assertEqual(summary["step_returns"], maximum)
                self.assertEqual(summary["collection_started_ns"], 10**12)
                self.assertEqual(summary["collection_deadline_ns"], 10**12 + sum(walls) * 10**9)
                self.assertEqual(len(calls), 1 if kind == "profile" else 5)
                self.assertTrue(all(kwargs["steps_per_episode"] == 8 for _, kwargs in calls))
                self.assertEqual([g["wall_budget_seconds"] for g in summary["groups"]], walls)
                self.assertEqual([g["deadline_ns"] for g in summary["groups"]],
                    [10**12 + wall * 10**9 for wall in walls])

    def test_legacy_collect_still_calls_four_argument_worker_stub(self):
        calls = []
        def worker(group, env_id, budget, freeze):
            calls.append(env_id)
            return {"episodes": [], "error": None, "saved_identities": []}
        with tempfile.TemporaryDirectory() as tmp, patch.object(capacity, "collect_worker", side_effect=worker):
            summary = capacity.collect(Path(tmp), "a" * 40, {}, {}, 1, 10**30)
        self.assertEqual(len(calls), 5)
        self.assertNotIn("activity_spec", summary)

    def test_bounded_collection_rejects_changed_reservations_or_insufficient_tail(self):
        spec = capacity.activity_spec("profile")
        with tempfile.TemporaryDirectory() as tmp, patch.object(capacity.time, "monotonic_ns", return_value=10**12):
            for kwargs in ({"group_wall_seconds": [241], "profile": True},
                           {"group_wall_seconds": [240], "profile": False}):
                with self.assertRaises(ValueError):
                    capacity.collect(Path(tmp), "a" * 40, {}, {}, 10**12, 10**12 + 600 * 10**9,
                                     activity_spec=spec, **kwargs)
            with self.assertRaisesRegex(ValueError, "remaining activity tail"):
                capacity.collect(Path(tmp), "a" * 40, {}, {}, 10**12 - 500 * 10**9, 10**12 + 100 * 10**9,
                                 activity_spec=spec, group_wall_seconds=[240], profile=True)

    def test_worker_profile_and_both_gym_creation_points_use_eight_steps(self):
        created, supervisors = [], []
        class Supervisor:
            process = None
            identities = []
            def __init__(self, directory, env_id, profile=False):
                supervisors.append(profile)
                self.root, self.number = directory, 0
                self.last_result = {"info": {"reason": "external_sampler_limit"}}
        class Environment:
            def __init__(self, supervisor, max_steps):
                self.supervisor, self.maximum, self.count = supervisor, max_steps, 0
                created.append(max_steps)
                self._snapshot = {"epoch": "fixture", "digest": "a" * 64, "candidate_version": "fixture"}
            def reset(self, **unused):
                self.supervisor.number += 1
                self.supervisor.directory = self.supervisor.root / str(self.supervisor.number)
                self.supervisor.directory.mkdir(parents=True)
                (self.supervisor.directory / "episode.json").write_text("{}")
                return {}, {}
            def action_masks(self):
                return np.ones(1000, dtype=bool)
            def step(self, action):
                self.count += 1
                return {}, 0., False, self.count == self.maximum, {}
            def close(self):
                pass
        with tempfile.TemporaryDirectory() as tmp, patch.object(capacity, "ProxySupervisor", Supervisor), \
                patch.object(capacity, "MR3Env", Environment), patch.object(capacity, "Trace"):
            budget = StepBudget(10**30, maximum=16)
            result = capacity.collect_worker(Path(tmp), 0, budget, "a" * 40,
                cells=[["open", 101], ["rooms", 101]], steps_per_episode=8, profile=True)
        self.assertIsNone(result["error"])
        self.assertEqual(created, [8, 8, 8])
        self.assertEqual(supervisors, [True])
        self.assertEqual(budget.attempts, 16)
        class UnsafeSupervisor(Supervisor):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.last_result = {"info": {"reason": "peer_contact"}}
        class UnsafeEnvironment(Environment):
            def step(self, action):
                return {}, 0., True, False, {}
        for explicit in (True, False):
            with tempfile.TemporaryDirectory() as tmp, patch.object(capacity, "ProxySupervisor", UnsafeSupervisor), \
                    patch.object(capacity, "MR3Env", UnsafeEnvironment), patch.object(capacity, "Trace"):
                budget = StepBudget(10**30, maximum=8)
                result = capacity.collect_worker(Path(tmp), 0, budget, "a" * 40,
                    cells=[["open", 101]] if explicit else None, steps_per_episode=8)
            self.assertTrue(budget.stop.is_set())
            self.assertEqual(budget.attempts, 1)
            if explicit:
                self.assertIn("unsafe_terminal", result["error"])
            else:
                self.assertIsNone(result["error"])

    def test_host_pidfd_can_observe_this_process_without_sending_a_mutating_signal(self):
        descriptor = pidfd_open(os.getpid())
        try:
            pidfd_send_signal(descriptor, 0)
        finally:
            os.close(descriptor)

    def test_one_shared_counter_is_atomic_across_four_collectors_and_counts_errors(self):
        budget = StepBudget(10**30, maximum=17)
        with ThreadPoolExecutor(max_workers=4) as executor:
            tickets = list(executor.map(lambda _: budget.reserve(), range(100)))
        self.assertEqual(sorted(t for t in tickets if t), list(range(1, 18)))
        budget.failed()
        self.assertFalse(budget.reserve())
        self.assertEqual(budget.attempts, 17)
        self.assertEqual(budget.errors, 1)

    def test_admission_reserves_time_for_existing_rpc_and_close_without_resetting_count(self):
        budget = StepBudget(100_000_000_000)
        with patch("mr3_learning.proxy2d_capacity.time.monotonic_ns", return_value=55_000_000_000):
            self.assertFalse(budget.reserve())
        self.assertEqual(budget.attempts, 0)

    def test_full_array_roundtrip_keeps_dtype_shape_and_bits_across_processes(self):
        values = {"grid": np.array([[-1, 0, 100]], dtype=np.int16),
                  "features": np.array([.1, -.2], dtype=np.float32),
                  "valid": np.array([True, False], dtype=bool)}
        decoded = decode_arrays(json.loads(canonical_bytes(encode_arrays(values))))
        self.assertEqual(tensor_proofs(decoded), tensor_proofs(values))

    def test_byte_length_dtype_and_array_extent_are_validated_before_use(self):
        encoded = encode_arrays(np.array([1, 2], dtype=np.int16))
        for change in ({"shape": [3]}, {"dtype": "O"}, {"shape": [2_000_001]}, {"shape": [True]},
                       {"data": base64.b64encode(b"x").decode()}):
            bad = {**encoded, **change}
            with self.assertRaises(ValueError):
                decode_arrays(bad)

    def test_nonfinite_cannot_be_delivered_or_hashed_as_a_tensor_claim(self):
        encoded = encode_arrays(np.array([np.inf], dtype=np.float32))
        with self.assertRaises(ValueError):
            decode_arrays(encoded)
        with self.assertRaises(ValueError):
            canonical_bytes({"state": float("nan")})

    def test_attempt_record_is_recoverable_before_the_environment_call_or_stream_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Trace(Path(tmp), 0, 1, "fixture")
            trace.record("step_attempt", action=888, global_attempt=1)
            raw = (Path(tmp) / "trace.jsonl.gz").read_bytes()
            prefix = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
            self.assertEqual(json.loads(prefix)["event"], "step_attempt")
            trace.close()


if __name__ == "__main__":
    unittest.main()
