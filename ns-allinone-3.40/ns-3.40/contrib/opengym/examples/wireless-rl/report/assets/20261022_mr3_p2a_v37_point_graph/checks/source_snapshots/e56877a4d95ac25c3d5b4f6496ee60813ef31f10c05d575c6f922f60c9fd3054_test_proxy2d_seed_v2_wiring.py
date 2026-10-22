"""Mock process/collector wiring only; no World, episode or native library."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import proxy2d, proxy2d_capacity as capacity
from mr3_learning.tests import test_proxy2d as custody


class SeedV2WiringTests(unittest.TestCase):
    def test_supervisor_retains_legacy_and_binds_each_explicit_worker_rule(self):
        for rule in proxy2d.SEED_RULES:
            with self.subTest(rule=rule):
                fixture = custody.ProxySupervisorTests()
                fixture.setUp()
                try:
                    fixture.owner = proxy2d.ProxySupervisor(fixture.root / "selected", seed_rule=rule)
                    fixture.add_process(58001)
                    fixture.successful_reset()
                    command = proxy2d.subprocess.Popen.call_args.args[0]
                    metadata = json.loads((fixture.owner.directory / "episode.json").read_text())
                    if rule == "legacy":
                        self.assertNotIn("--seed-rule", command[4])
                        self.assertNotIn("seed_rule", metadata)
                        self.assertEqual(command[-2:], ["endpoint", ""])
                    else:
                        self.assertIn('--seed-rule "$8"', command[4])
                        self.assertEqual(command[-1], rule)
                        self.assertEqual(metadata["seed_rule"], rule)
                    fixture.owner.close()
                finally:
                    fixture.doCleanups()

    def test_unknown_supervisor_rule_rejects_before_directory_or_process(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(proxy2d.subprocess, "Popen") as spawn:
            for rule in (None, True, "exact-point-bridge-v3", "v2"):
                target = Path(temporary) / "not-created"
                with self.subTest(rule=rule), self.assertRaises(ValueError):
                    proxy2d.ProxySupervisor(target, seed_rule=rule)
                self.assertFalse(target.exists())
            spawn.assert_not_called()

    def test_each_fixed_probe_collects_three_assigned_mock_workers_with_192_tickets(self):
        for kind, rule in capacity.SEED_PROBE_RULES.items():
            calls, tickets = [], []
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
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary, \
                    patch.object(capacity.time, "monotonic_ns", return_value=10**12), \
                    patch.object(capacity, "collect_worker", side_effect=worker):
                summary = capacity.collect(Path(temporary), "a" * 40, {}, {}, 10**12,
                    10**12 + 1800 * 10**9, activity_spec=capacity.activity_spec(kind),
                    group_wall_seconds=[900], mapper="karto", mapper_library="mock-never-loaded.so",
                    native_manifest={"path": "mock-manifest.json", "sha256": "b" * 64}, seed_rule=rule)
            self.assertEqual((summary["step_attempts"], summary["step_returns"], summary["step_errors"]), (192, 192, 0))
            self.assertEqual(sorted(tickets), list(range(1, 193)))
            self.assertEqual(summary["seed_rule"], rule)
            self.assertEqual(summary["collection_deadline_ns"] - summary["collection_started_ns"], 900 * 10**9)
            self.assertEqual(summary["groups"][0]["wall_budget_seconds"], 900)
            self.assertEqual(summary["activity_spec"]["kind"], kind)
            for env_id, kwargs in sorted(calls):
                self.assertEqual(kwargs["cells"], [[("open", "rooms", "corridors")[env_id], 101]])
                self.assertEqual(kwargs["steps_per_episode"], 64)
                self.assertEqual(kwargs["seed_rule"], rule)
                self.assertEqual(kwargs["mapper"], "karto")
                self.assertFalse(kwargs["profile"])

    def test_probe_versions_cannot_mix_rule_mapper_clock_or_fixed_spec(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(capacity, "collect_worker") as worker:
            for kind, selected in capacity.SEED_PROBE_RULES.items():
                for rule in ("legacy", *capacity.SEED_PROBE_RULES.values()):
                    if rule == selected:
                        continue
                    with self.subTest(kind=kind, rule=rule), self.assertRaises(ValueError):
                        capacity.collect(Path(temporary), "a" * 40, {}, {}, 10**12, 10**12 + 1800 * 10**9,
                            activity_spec=capacity.activity_spec(kind), group_wall_seconds=[900],
                            mapper="karto", mapper_library="mock.so", native_manifest={"fixture": True}, seed_rule=rule)
                for changed in ("mapper", "wall", "spec"):
                    spec = copy.deepcopy(capacity.activity_spec(kind))
                    if changed == "spec":
                        spec["steps_per_episode"] = 65
                    with self.subTest(kind=kind, changed=changed), self.assertRaises(ValueError):
                        capacity.collect(Path(temporary), "a" * 40, {}, {}, 10**12, 10**12 + 1800 * 10**9,
                            activity_spec=spec, group_wall_seconds=[901] if changed == "wall" else [900],
                            mapper="endpoint" if changed == "mapper" else "karto", mapper_library="mock.so",
                            native_manifest={"fixture": True}, seed_rule=selected)
            worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
