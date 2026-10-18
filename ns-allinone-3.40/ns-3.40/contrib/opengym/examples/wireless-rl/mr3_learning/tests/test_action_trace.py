"""The fixed trace uses real MR3Env validation around a CPU supervisor fixture."""

import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import action_trace
from mr3_learning.tests.test_env import SupervisorFixture
from mr3_learning.tests.test_observation import seal


class FixedActionTraceTests(unittest.TestCase):
    def run_fixture(self, *, illegal=None, terminate=None, reset_wall=0., step_wall=0.,
                    close_wall=5., physics=None, error=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root, clock, instances = Path(temporary.name), [10 * 10**9], []
        args = SimpleNamespace(output_root=root, run_id="trace", domain=180, port=14001,
                               physics_config=physics)

        class FakeSupervisor(SupervisorFixture):
            def __init__(self, **kwargs):
                super().__init__()
                self.arguments = kwargs
                self.physics_environment = os.environ.get(action_trace.PHYSICS_CONFIG_ENV)
                self.directory = root / "trace/worker0"
                self.directory.mkdir(parents=True)
                self.episode = SimpleNamespace(directory=self.directory / "episode")
                self.receipts = []
                instances.append(self)

            def reset(self, scene, seed):
                result = super().reset(scene, seed)
                self.snapshot["joint_action_mask"] = [True] * 1000
                if illegal == 0:
                    self.snapshot["joint_action_mask"][action_trace.ACTIONS[0]] = False
                seal(self.snapshot)
                result["snapshot"] = self.snapshot.copy()
                clock[0] += round(reset_wall * 1e9)
                return result

            def step(self, action, external_truncation=None):
                decision = len([call for call in self.calls if call[0] == "step"])
                if error == decision:
                    raise RuntimeError("actual RPC exception")
                if terminate == decision:
                    self.terminal = True
                result = super().step(action, external_truncation)
                if illegal == decision + 1 and illegal < len(action_trace.ACTIONS):
                    self.snapshot["joint_action_mask"][action_trace.ACTIONS[illegal]] = False
                    seal(self.snapshot)
                    result["snapshot"] = self.snapshot.copy()
                result["info"]["reason"] = "actual_navigation_failure" if self.terminal else (
                    "external_sampler_limit" if result["truncated"] else None)
                clock[0] += round(step_wall * 1e9)
                return result

            def close(self):
                super().close()
                clock[0] += round(close_wall * 1e9)
                self.receipts.append({"epoch": self.snapshot["epoch"], "worker_returncode": 0,
                                      "forced_shutdown": False, "failed_sample": False,
                                      "remaining_owned_processes": [], "remaining_owned_zombies": []})

        with patch.object(action_trace, "Supervisor", FakeSupervisor), \
                patch.object(action_trace.subprocess, "check_output", return_value="freeze"), \
                patch.object(action_trace.time, "monotonic_ns", side_effect=lambda: clock[0]):
            result = action_trace.run_trace(args, started_ns=clock[0])
        self.assertEqual(json.loads((root / "trace/action_trace_summary.json").read_text()), result)
        return result, instances[0]

    def test_exact_actions_real_env_mask_and_last_external_truncation_with_clean_close(self):
        result, supervisor = self.run_fixture(reset_wall=100., step_wall=20.)
        self.assertEqual([call[1] for call in supervisor.calls if call[0] == "step"],
                         [231, 888, 888, 889, 880, 658, 888, 888])
        self.assertEqual(supervisor.calls[-1], ("step", 888, "external_sampler_limit"))
        self.assertEqual(supervisor.calls[0], ("reset", "open", 101))
        self.assertNotIn("plant_stimulus_arm", supervisor.arguments)
        self.assertEqual(supervisor.arguments["startup_timeout"], 420.)
        self.assertEqual(supervisor.arguments["request_timeout"], 90.)
        self.assertTrue(all(check["legal"] for check in result["mask_checks"]))
        self.assertEqual(result["native_decisions_returned"], 8)
        self.assertEqual(result["wall_sec_including_startup_and_close"], 265.)
        self.assertEqual(result["outcome"], "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT")
        self.assertTrue(result["shutdown_clean"])
        self.assertEqual(supervisor.closed, 1)
        self.assertEqual((result["policy_calls"], result["optimizer_steps"]), (0, 0))

    def test_illegal_fixed_action_keeps_prefix_without_replacement(self):
        for decision in (0, 3, 7):
            with self.subTest(decision=decision):
                result, supervisor = self.run_fixture(illegal=decision)
                self.assertEqual(result["native_decisions_returned"], decision)
                self.assertEqual([step["action"] for step in result["steps"]],
                                 list(action_trace.ACTIONS[:decision]))
                self.assertEqual(result["outcome"], "INCOMPLETE")
                self.assertEqual(result["first_failure"]["kind"], "fixed_action_illegal")
                self.assertEqual(supervisor.closed, 1)

    def test_real_termination_saved_closed_and_fail_even_on_eighth_step(self):
        for decision in (0, 7):
            with self.subTest(decision=decision):
                result, supervisor = self.run_fixture(terminate=decision)
                self.assertEqual(result["native_decisions_returned"], decision + 1)
                self.assertTrue(result["steps"][-1]["terminated"])
                self.assertFalse(result["steps"][-1]["truncated"])
                self.assertEqual(result["first_failure"]["reason"], "actual_navigation_failure")
                self.assertEqual(result["outcome"], "FAIL")
                self.assertEqual(supervisor.closed, 1)

    def test_rpc_exception_adds_no_transition_and_preserves_first_failure(self):
        result, supervisor = self.run_fixture(error=2)
        self.assertEqual(result["native_decisions_returned"], 2)
        self.assertEqual(result["first_failure"]["kind"], "rpc_or_runner_exception")
        self.assertEqual(supervisor.closed, 1)

    def test_step_admission_keeps_90_second_rpc_and_120_second_close_reserve(self):
        result, supervisor = self.run_fixture(reset_wall=491.)
        self.assertEqual(result["native_decisions_returned"], 0)
        self.assertEqual(result["first_failure"]["kind"], "work_wall_allocation_exhausted")
        self.assertEqual(supervisor.closed, 1)

    def test_total_wall_includes_close_and_excess_is_fail_without_kill(self):
        result, supervisor = self.run_fixture(close_wall=701.)
        self.assertEqual(result["native_decisions_returned"], 8)
        self.assertTrue(result["completed_requested_collection"])
        self.assertTrue(result["wall_limit_exceeded"])
        self.assertEqual(result["outcome"], "FAIL")
        self.assertEqual(supervisor.closed, 1)

    def test_optional_config_is_passive_and_ambient_config_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observer.json"
            path.write_text(json.dumps({"schema": "mr3-physics-diagnostic-config-v2",
                                        "mode": "observer_only"}))
            with patch.dict(os.environ, {action_trace.PHYSICS_CONFIG_ENV: "prior"}):
                result, supervisor = self.run_fixture(physics=path)
                self.assertEqual(os.environ[action_trace.PHYSICS_CONFIG_ENV], "prior")
                self.assertEqual(supervisor.physics_environment, str(path.resolve()))
            self.assertEqual(result["physics_config"]["configuration"]["mode"], "observer_only")

    def test_unspecified_observer_cannot_inherit_an_ambient_mutating_configuration(self):
        with patch.dict(os.environ, {action_trace.PHYSICS_CONFIG_ENV: "unreviewed_profile"}):
            result, supervisor = self.run_fixture()
            self.assertIsNone(supervisor.physics_environment)
            self.assertIsNone(result["physics_config"])
            self.assertEqual(os.environ[action_trace.PHYSICS_CONFIG_ENV], "unreviewed_profile")
