"""Explicit reach external-fixture admission/forwarding; no native processes."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning import benchmark, supervisor as owner
from mr3_learning.tests import test_benchmark as fixtures


VERSION = benchmark.PREPARATION_PROBE_REACH_V1


class ReachPreparationEntryTests(unittest.TestCase):
    def test_seed_rule_rejects_unknown_values_before_any_native_side_effect(self):
        for value in (None,True,0,"unknown"):
            with self.subTest(value=value),patch.object(owner.Path,"mkdir") as mkdir:
                with self.assertRaises(ValueError):owner.Supervisor(seed_rule=value)
                mkdir.assert_not_called()
        for argv in (["--seed-rule"],["--seed-rule=legacy"],
                     ["--seed-rule","legacy","--seed-rule","exact-point-bridge-v1"]):
            with self.subTest(argv=argv),self.assertRaises(ValueError):owner.seed_rule_from_argv(argv)

    def test_exact_seed_rule_reaches_real_reset_rpc_and_supervisor_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            supervisor=owner.Supervisor(output_root=temporary,seed_rule="exact-point-bridge-v1")
            identity={"pid":43121,"parent":1,"group":43121,"session":43121,"start_ticks":123,"state":"S"}
            process=Mock(pid=identity["pid"])
            process.stdout.fileno.return_value=9;process.stdin.fileno.return_value=10
            def reset(operation,**payload):return {"snapshot":{"epoch":supervisor.episode.epoch}}
            with patch.object(owner.subprocess,"Popen",return_value=process), \
                    patch.object(owner,"process_identity",return_value=identity), \
                    patch.object(owner,"JsonLinePeer",return_value=SimpleNamespace()), \
                    patch.object(owner.threading,"Thread"),patch.object(supervisor,"close"), \
                    patch.object(supervisor,"_rpc",side_effect=reset) as rpc:
                try:
                    supervisor.reset()
                    self.assertEqual(rpc.call_args.kwargs["seed_rule"],"exact-point-bridge-v1")
                    metadata=json.loads((supervisor.episode.directory/"supervisor_metadata.json").read_text())
                    self.assertEqual(metadata["seed_rule"],"exact-point-bridge-v1")
                finally:
                    if supervisor.episode is not None:supervisor.episode.output.close()

    def test_cross_profile_implicit_version_and_wrong_budget_reject_before_any_work(self):
        for profile, flags in (
                ("legacy", ["--preparation-motion-probe", "--preparation-probe-version", VERSION]),
                ("mr3-reach-v1", ["--preparation-motion-probe"]),
                ("mr3-reach-v1", ["--preparation-motion-probe", "--preparation-probe-version", benchmark.PREPARATION_PROBE_V6]),
                ("mr3-reach-v1", ["--preparation-probe-version", VERSION]),
                ("mr3-reach-v1", ["--preparation-motion-probe", "--preparation-probe-version", VERSION, "--steps", "20"]),
                ("mr3-reach-v1", ["--preparation-motion-probe", "--preparation-probe-version", VERSION, "--preparation-parameter-review"]),
                ("mr3-reach-v1", ["--preparation-parameter-profile", "gentle_turn_v1"])):
            args = ["--workers", "1", "--schedule", "open:101", "--steps", "32", "--run-id", "no-work",
                    "--safety-contract", profile, *flags]
            with self.subTest(profile=profile, flags=flags), \
                    patch.object(benchmark.Path, "mkdir") as mkdir, \
                    patch.object(benchmark, "Supervisor") as native, \
                    patch.object(benchmark, "_parameter_review_binding") as review, \
                    patch.object(benchmark.subprocess, "check_output") as git, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                benchmark.main(args)
            self.assertEqual(error.exception.code, 2)
            for operation in (mkdir, native, review, git): operation.assert_not_called()

    def test_interface_and_multiworker_reset_record_new_version_without_training_credit(self):
        for workers, schedule, review in ((1, "open:101", True), (4, "open:101,rooms:101", False)):
            with self.subTest(workers=workers), tempfile.TemporaryDirectory() as root:
                def complete(args, worker, abort):
                    self.assertEqual(args.preparation_probe_version, VERSION)
                    self.assertEqual(args.safety_contract, "mr3-reach-v1")
                    return {"worker_id": worker, "error": None,
                            "episodes": [{"transitions": 32, "terminated": False, "truncated": True}
                                         for _ in args.schedule],
                            "shutdown_receipts": [{"remaining_owned_processes": [], "remaining_owned_zombies": [],
                                                   "forced_shutdown": False, "worker_returncode": 0}
                                                  for _ in args.schedule]}
                args = ["--workers", str(workers), "--schedule", schedule, "--steps", "32", "--run-id", "new-fixture",
                        "--output-root", root, "--safety-contract", "mr3-reach-v1",
                        "--preparation-motion-probe", "--preparation-probe-version", VERSION]
                if review: args += ["--preparation-parameter-review", "--preparation-parameter-profile", "gentle_turn_v1"]
                with patch.object(benchmark, "run_worker", side_effect=complete), \
                        patch.object(benchmark, "resource_sample", return_value={}), \
                        patch.object(benchmark.subprocess, "check_output", return_value="a"*40), \
                        patch.object(benchmark, "_parameter_review_binding", return_value={"new_entry": True}) as binding, \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(benchmark.main(args), 0)
                if review: binding.assert_called_once_with("a"*40, "gentle_turn_v1", "mr3-reach-v1")
                else: binding.assert_not_called()
                summary = json.loads((Path(root)/"new-fixture/benchmark_summary.json").read_text())
                self.assertTrue(summary["passed"])
                self.assertEqual(summary["valid_transitions"], workers*len(schedule.split(","))*32)
                self.assertEqual(summary["preparation_probe_version"], VERSION)
                self.assertEqual(summary["preparation_fixture_implementation"], "unchanged_v6_external_actions")
                self.assertFalse(summary["training_eligible"])
                self.assertFalse(summary["scientific_readers_applied"])

    def test_new_binding_covers_actual_entry_immutable_math_deployment_and_shared_wire(self):
        def git(argv, **kwargs):
            return (benchmark.WORKSPACE/argv[-1].split(":", 1)[1]).read_bytes()
        with patch.object(benchmark.subprocess, "check_output", side_effect=git):
            binding = benchmark._parameter_review_binding("a"*40, "gentle_turn_v1", "mr3-reach-v1")
        self.assertEqual(binding["relative_path"], benchmark.REACH_PARAMETER_REVIEW_SCRIPT.as_posix())
        self.assertEqual(binding["immutable_reader"]["relative_path"], benchmark.PARAMETER_REVIEW_SCRIPT.as_posix())
        self.assertEqual(binding["deployment_entry"]["relative_path"], benchmark.GENTLE_PARAMETER_REVIEW_SCRIPT.as_posix())
        self.assertEqual(binding["safety_contract"], "mr3-reach-v1")
        self.assertEqual(len(binding["deployment_yaml_sources"]), 3)
        self.assertTrue(binding["shared_wire_source"]["relative_path"].endswith("mr3_safety_intent.py"))
        with patch.object(benchmark.subprocess, "check_output", return_value=b"different freeze"):
            with self.assertRaises(RuntimeError):
                benchmark._parameter_review_binding("a"*40, "gentle_turn_v1", "mr3-reach-v1")

    def test_readback_argv_selects_new_readonly_system_ros_entry(self):
        args = SimpleNamespace(freeze="a"*40, preparation_parameter_profile="gentle_turn_v1",
                               safety_contract="mr3-reach-v1", preparation_parameter_review_source={"new": True})
        episode = {"output_directory": "/unused/episode"}
        with patch.object(benchmark, "_parameter_review_binding", return_value={"new": True}) as binding, \
                patch.object(benchmark, "_parameter_review_environment", return_value=({"native_transport": "exact"}, {})), \
                patch.object(benchmark.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="ok", stderr="")) as child:
            benchmark._run_parameter_review(args, 0, episode)
        binding.assert_called_once_with("a"*40, "gentle_turn_v1", "mr3-reach-v1")
        argv = child.call_args.args[0]
        self.assertIn(str(benchmark.WORKSPACE/benchmark.REACH_PARAMETER_REVIEW_SCRIPT), argv)
        self.assertNotIn(str(benchmark.WORKSPACE/benchmark.GENTLE_PARAMETER_REVIEW_SCRIPT), argv)
        self.assertEqual(argv[-6:], ["--freeze", "a"*40, "--output", "/unused/episode/actual_nav2_parameters.json", "--wall-timeout-sec", "30"])
        self.assertEqual(child.call_args.kwargs["env"], {"native_transport": "exact"})

    def test_worker_reuses_v6_fixture_through_all_32_steps_and_complete_resets(self):
        fixture = fixtures.CooperativeAbortTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        args = fixture.args(); args.steps = 32
        args.safety_contract, args.preparation_probe_version = "mr3-reach-v1", VERSION
        fake_owner, fake_environment = fixture.fakes()
        with fake_owner, fake_environment, patch.object(benchmark, "probe_action_v6", return_value=888) as choose, \
                patch.object(benchmark, "record_probe_v4_submission") as submission:
            constructor = benchmark.Supervisor
            with patch.object(benchmark, "Supervisor", side_effect=constructor) as selected:
                result = benchmark.run_worker(args, 0)
        self.assertIsNone(result["error"])
        self.assertEqual([row["transitions"] for row in result["episodes"]], [32, 32])
        self.assertEqual(choose.call_count, 64)
        self.assertEqual(submission.call_count, 64)
        self.assertEqual(selected.call_args.kwargs["preparation_probe_version"], VERSION)
        self.assertEqual(selected.call_args.kwargs["safety_contract"], "mr3-reach-v1")
        self.assertEqual(fixture.environments[0].reset_calls, 2)
        self.assertEqual(fixture.environments[0].close_calls, 1)

    def test_supervisor_rejects_cross_profile_before_mkdir(self):
        for profile, version in (("legacy", VERSION), ("mr3-reach-v1", benchmark.PREPARATION_PROBE_V2),
                                 ("mr3-reach-v1", benchmark.PREPARATION_PROBE_V6), ("legacy", True)):
            with self.subTest(profile=profile, version=version), patch.object(owner.Path, "mkdir") as mkdir:
                with self.assertRaises(ValueError): owner.Supervisor(safety_contract=profile, preparation_probe_version=version)
                mkdir.assert_not_called()

    def test_supervisor_metadata_keeps_fixture_version_out_of_native_rpc(self):
        with tempfile.TemporaryDirectory() as temporary:
            supervisor = owner.Supervisor(output_root=temporary, run_id="reach-external",
                                          safety_contract="mr3-reach-v1", preparation_probe_version=VERSION)
            identity = {"pid": 43121, "parent": 1, "group": 43121, "session": 43121,
                        "start_ticks": 123, "state": "S"}
            process = Mock(pid=identity["pid"])
            process.stdout.fileno.return_value = 9; process.stdin.fileno.return_value = 10
            def reset(operation, **payload): return {"snapshot": {"epoch": supervisor.episode.epoch}}
            with patch.object(owner.subprocess, "Popen", return_value=process), \
                    patch.object(owner, "process_identity", return_value=identity), \
                    patch.object(owner, "JsonLinePeer", return_value=SimpleNamespace()), \
                    patch.object(owner.threading, "Thread"), patch.object(supervisor, "close"), \
                    patch.object(supervisor, "_rpc", side_effect=reset) as rpc:
                try:
                    supervisor.reset()
                    metadata = json.loads((supervisor.episode.directory/"supervisor_metadata.json").read_text())
                    self.assertEqual(metadata["preparation_probe_version"], VERSION)
                    self.assertFalse(metadata["training_eligible"])
                    self.assertEqual(rpc.call_args.kwargs["safety_contract"], "mr3-reach-v1")
                    self.assertNotIn("preparation_probe_version", rpc.call_args.kwargs)
                finally:
                    if supervisor.episode is not None: supervisor.episode.output.close()


if __name__ == "__main__":
    unittest.main()
