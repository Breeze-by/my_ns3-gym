"""External preparation inputs remain legal and separate from policy control."""

from concurrent.futures import ThreadPoolExecutor
import contextlib
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import benchmark
from mr3_learning.benchmark import probe_action


class PreparationProbeTests(unittest.TestCase):
    def test_outward_goals_do_not_reuse_crossing_stress_order(self):
        mask = [False] * 1000
        for action in (12, 345, 889):
            mask[action] = True
        candidates = [{"path_distances_m": [1., 1., 1.]} for _ in range(8)]
        for candidate, point in zip(candidates, (
                (-1., -1.4), (-1., 1.4), (1.45, 0.), (1., 0.),
                (1., .5), (-1., 0.), (0., 0.), (0., 0.))):
            candidate.update(x=point[0], y=point[1])
        for index in (3, 4, 5):
            candidates[index]["path_distances_m"] = [4., 4., 4.]
        snapshot = {"task_elapsed_sec": 0., "joint_action_mask": mask,
                    "candidates": candidates,
                    "robots": [{"x": 0., "y": -.45}, {"x": 0., "y": .45},
                               {"x": .45, "y": 0.}]}
        self.assertEqual(probe_action(snapshot), 345)
        self.assertEqual(probe_action(snapshot, outward_goals=True), 12)
        for index in (0, 1, 2):
            candidates[index]["path_distances_m"] = [100., 100., 100.]
        self.assertEqual(probe_action(snapshot, outward_goals=True), 12)
        # Only the declared engineering flag uses the longer motion/stop fixture.
        for elapsed, default, outward in (
                (1.49, 12, 12), (1.5, 888, 888), (6.99, 888, 888),
                (7., 889, 888), (9.99, 889, 888), (10., 12, 889),
                (11.99, 12, 889), (12., 889, 889), (12.99, 889, 889),
                (13., 889, 12), (14.99, 889, 12), (15., 889, 888),
                (19.99, 889, 888)):
            with self.subTest(elapsed=elapsed):
                snapshot["task_elapsed_sec"] = elapsed
                self.assertEqual(probe_action(snapshot), default)
                self.assertEqual(probe_action(snapshot, outward_goals=True), outward)

    def test_flag_rejects_old_sixteen_step_fixture_before_creating_run(self):
        with tempfile.TemporaryDirectory() as root:
            argv = ["benchmark", "--workers", "1", "--steps", "16",
                    "--run-id", "reject_old_fixture", "--output-root", root,
                    "--preparation-motion-probe"]
            with patch("sys.argv", argv), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    benchmark.main()
            self.assertEqual(error.exception.code, 2)
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_parameter_review_rejects_other_worker_schedule_or_probe_before_run(self):
        for options in ([], ["--preparation-motion-probe", "--workers", "2"],
                        ["--preparation-motion-probe", "--schedule", "rooms:101"],
                        ["--preparation-motion-probe", "--schedule", "open:101,open:101"]):
            with self.subTest(options=options), tempfile.TemporaryDirectory() as root:
                argv = ["benchmark", "--workers", "1", "--steps", "20", "--run-id", "rejected",
                        "--output-root", root, "--schedule", "open:101",
                        "--preparation-parameter-review", *options]
                with patch("sys.argv", argv), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as error:
                        benchmark.main()
                self.assertEqual(error.exception.code, 2)
                self.assertEqual(list(Path(root).iterdir()), [])

    def test_parameter_review_requires_exact_tracked_freeze_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            Path(root, "fixed.py").write_bytes(b"frozen-script")
            with patch.object(benchmark, "WORKSPACE", Path(root)), \
                    patch.object(benchmark, "PARAMETER_REVIEW_SCRIPT", Path("fixed.py")), \
                    patch.object(benchmark.subprocess, "check_output",
                                 return_value=b"frozen-script") \
                    as git:
                binding = benchmark._parameter_review_binding("freeze")
                self.assertEqual(binding["relative_path"], "fixed.py")
                git.assert_called_once_with(["git", "show", "freeze:fixed.py"], cwd=Path(root))
                Path(root, "fixed.py").write_bytes(b"changed-script")
                with self.assertRaisesRegex(RuntimeError, "differs from the declared source"):
                    benchmark._parameter_review_binding("freeze")


class CooperativeAbortTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.environments = {}

    def args(self, preparation=True):
        return SimpleNamespace(
            run_id="fake_native_inputs", base_domain=206, base_port=12541,
            output_root=self.root, terminal_probe=False, fault_probe=False,
            deadline_probe=False, preparation_motion_probe=preparation,
            steps=20, schedule=[("open", 101), ("open", 101)])

    def fakes(self, *, on_reset=None, on_step=None, on_close=None):
        owner = self

        class FakeSupervisor:
            def __init__(self, **kwargs):
                self.worker_id = kwargs["worker_id"]
                self.directory = owner.root / str(self.worker_id)
                self.directory.mkdir()
                self.receipts = []

        class FakeEnvironment:
            def __init__(self, *, supervisor, max_steps):
                self.supervisor, self.max_steps = supervisor, max_steps
                self.reset_calls, self.step_calls, self.close_calls = 0, 0, 0
                self.returned_steps = []
                owner.environments[supervisor.worker_id] = self

            def snapshot(self, elapsed):
                mask = [False] * 1000
                mask[888] = True
                self.supervisor.last_result = {"snapshot": {
                    "task_elapsed_sec": elapsed, "joint_action_mask": mask,
                    "candidates": [], "robots": [
                        {"name": name, "x": 0., "y": 0., "yaw": 0.}
                        for name in ("tb1", "tb2", "tb3")]}}

            def reset(self, **kwargs):
                self.reset_calls += 1
                self.episode_steps, self._episode_done = 0, False
                if on_reset:
                    on_reset(self)
                self.supervisor.episode = SimpleNamespace(
                    directory=self.supervisor.directory / str(self.reset_calls))
                self.snapshot(0.)
                return None, {"epoch": f"epoch-{self.reset_calls}",
                              "observation_digest": "fake", "startup_wall_sec": 0.}

            def step(self, action):
                self.step_calls += 1
                self.episode_steps += 1
                terminated, truncated = (on_step(self) if on_step else
                                         (False, self.episode_steps == self.max_steps))
                self._episode_done = terminated or truncated
                self.snapshot(float(self.episode_steps))
                info = {"dt": 1., "reason": "actual_failure" if terminated else
                        ("actual_external_truncation" if truncated else None)}
                self.returned_steps.append((action, terminated, truncated, info))
                return None, 1., terminated, truncated, info

            def close(self):
                self.close_calls += 1
                if on_close:
                    on_close(self)

        return (patch.object(benchmark, "Supervisor", FakeSupervisor),
                patch.object(benchmark, "MR3Env", FakeEnvironment))

    def pair(self, abort, **callbacks):
        supervisor, environment = self.fakes(**callbacks)
        with supervisor, environment, ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(benchmark.run_worker, self.args(), worker, abort)
                       for worker in range(2)]
            return [future.result(timeout=10.) for future in futures]

    def assert_real_prefix(self, result, expected_steps):
        environment = self.environments[result["worker_id"]]
        self.assertEqual(environment.reset_calls, 1)
        self.assertEqual(environment.close_calls, 1)
        self.assertEqual(len(environment.returned_steps), expected_steps)
        self.assertEqual(sum(episode["transitions"] for episode in result["episodes"]),
                         expected_steps)
        self.assertEqual(len(result["reset_attempts"]), 1)
        self.assertTrue(result["preparation_abort"]["requested"])
        disk = json.loads((environment.supervisor.directory / "worker_summary.json").read_text())
        self.assertEqual(disk, result)

    def test_real_termination_saved_before_peer_abort_and_all_workers_close(self):
        abort, both_in_rpc = benchmark._new_preparation_abort(), threading.Barrier(2)

        def step(environment):
            both_in_rpc.wait(timeout=5.)
            if environment.supervisor.worker_id == 0:
                return True, False
            self.assertTrue(abort["event"].wait(timeout=5.))
            return False, False

        results = self.pair(abort, on_step=step)
        for result in results:
            self.assert_real_prefix(result, 1)
            self.assertIsNone(result["error"])
            self.assertEqual(result["episodes"][0]["reward_sum"], 1.)
            self.assertEqual(result["episodes"][0]["dt_values"], [1.])
        failure, peer = [result["episodes"][0] for result in results]
        self.assertTrue(failure["terminated"])
        self.assertFalse(failure["truncated"])
        self.assertEqual(failure["reason"], "actual_failure")
        self.assertNotIn("intentional_abort_prefix", failure)
        self.assertNotIn("terminated", peer)
        self.assertNotIn("truncated", peer)
        self.assertEqual(peer["intentional_abort_prefix"]["after_rpc"], "step")
        self.assertEqual(abort["first_failure"]["kind"], "unexpected_termination")
        self.assertEqual(abort["first_failure"]["worker_id"], 0)
        original = dict(abort["first_failure"])
        benchmark._preparation_failure(abort, 1, "later_error", "cannot replace first failure")
        self.assertEqual(abort["first_failure"], original)

    def test_early_truncation_is_real_failure_not_completed_fixture(self):
        abort, both_in_rpc = benchmark._new_preparation_abort(), threading.Barrier(2)

        def step(environment):
            both_in_rpc.wait(timeout=5.)
            if environment.supervisor.worker_id == 0:
                return False, True
            self.assertTrue(abort["event"].wait(timeout=5.))
            return False, False

        results = self.pair(abort, on_step=step)
        for result in results:
            self.assert_real_prefix(result, 1)
        self.assertEqual(abort["first_failure"]["kind"], "early_truncation")
        self.assertTrue(results[0]["episodes"][0]["truncated"])
        self.assertFalse(results[0]["episodes"][0]["terminated"])

    def test_step_exception_adds_no_transition_but_retains_peer_return(self):
        abort, both_in_rpc = benchmark._new_preparation_abort(), threading.Barrier(2)

        def step(environment):
            both_in_rpc.wait(timeout=5.)
            if environment.supervisor.worker_id == 0:
                raise RuntimeError("step RPC failed")
            self.assertTrue(abort["event"].wait(timeout=5.))
            return False, False

        results = self.pair(abort, on_step=step)
        self.assert_real_prefix(results[0], 0)
        self.assert_real_prefix(results[1], 1)
        self.assertEqual(results[0]["error"], "RuntimeError('step RPC failed')")
        self.assertEqual(abort["first_failure"]["kind"], "rpc_or_worker_exception")

    def test_reset_exception_closes_both_without_resetting_again(self):
        abort, both_in_rpc = benchmark._new_preparation_abort(), threading.Barrier(2)

        def reset(environment):
            both_in_rpc.wait(timeout=5.)
            if environment.supervisor.worker_id == 0:
                raise RuntimeError("reset RPC failed")
            self.assertTrue(abort["event"].wait(timeout=5.))

        results = self.pair(abort, on_reset=reset)
        for result in results:
            self.assert_real_prefix(result, 0)
        self.assertEqual(results[0]["episodes"], [])
        self.assertFalse(results[0]["reset_attempts"][0]["reset_returned"])
        self.assertTrue(results[1]["reset_attempts"][0]["reset_returned"])
        self.assertEqual(results[1]["episodes"][0]["intentional_abort_prefix"]["after_rpc"],
                         "reset")
        self.assertIsNone(abort["first_failure"]["epoch"])

    def test_close_exception_does_not_skip_other_worker_close(self):
        abort, both_in_rpc = benchmark._new_preparation_abort(), threading.Barrier(2)

        def step(environment):
            if environment.episode_steps == 1:
                both_in_rpc.wait(timeout=5.)
            if environment.supervisor.worker_id == 1:
                self.assertTrue(abort["event"].wait(timeout=5.))
                return False, False
            return False, environment.episode_steps == environment.max_steps

        def close(environment):
            if environment.supervisor.worker_id == 0:
                raise RuntimeError("close RPC failed")

        supervisor, environment = self.fakes(on_step=step, on_close=close)
        args = self.args()
        args.schedule = args.schedule[:1]
        with supervisor, environment, ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(benchmark.run_worker, args, worker, abort)
                       for worker in range(2)]
            results = [future.result(timeout=10.) for future in futures]
        self.assert_real_prefix(results[0], 20)
        self.assert_real_prefix(results[1], 1)
        self.assertEqual(results[0]["cleanup_error"], "RuntimeError('close RPC failed')")
        self.assertNotIn("cleanup_error", results[1])
        self.assertEqual(abort["first_failure"]["kind"], "cleanup_exception")
        self.assertTrue(results[0]["episodes"][0]["truncated"])

    def test_complete_flag_fixture_keeps_both_twenty_step_episodes(self):
        abort = benchmark._new_preparation_abort()
        supervisor, environment = self.fakes()
        with supervisor, environment:
            result = benchmark.run_worker(self.args(), 0, abort)
        instance = self.environments[0]
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls),
                         (2, 40, 1))
        self.assertFalse(abort["event"].is_set())
        self.assertFalse(result["preparation_abort"]["requested"])
        self.assertIsNone(result["error"])
        for episode in result["episodes"]:
            self.assertEqual(episode["transitions"], 20)
            self.assertTrue(episode["truncated"])
            self.assertFalse(episode["terminated"])
            self.assertNotIn("intentional_abort_prefix", episode)

    def test_later_reset_exception_does_not_claim_previous_epoch(self):
        abort = benchmark._new_preparation_abort()

        def reset(environment):
            if environment.reset_calls == 2:
                raise RuntimeError("second reset failed")

        supervisor, environment = self.fakes(on_reset=reset)
        with supervisor, environment:
            result = benchmark.run_worker(self.args(), 0, abort)
        self.assertEqual(self.environments[0].reset_calls, 2)
        self.assertEqual(self.environments[0].close_calls, 1)
        self.assertEqual(len(result["episodes"]), 1)
        self.assertEqual(result["episodes"][0]["transitions"], 20)
        self.assertEqual(abort["first_failure"]["episode_index"], 1)
        self.assertIsNone(abort["first_failure"]["epoch"])

    def test_already_aborted_worker_closes_without_any_reset(self):
        abort = benchmark._new_preparation_abort()
        benchmark._preparation_failure(abort, 1, "existing_failure", "actual failure")
        supervisor, environment = self.fakes()
        with supervisor, environment:
            result = benchmark.run_worker(self.args(), 0, abort)
        instance = self.environments[0]
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls),
                         (0, 0, 1))
        self.assertEqual(result["episodes"], [])
        self.assertEqual(result["reset_attempts"], [])

    def check_main_summary(self, *, preparation, on_step=None, parameter_review=False):
        supervisor, environment = self.fakes(on_step=on_step)
        argv = ["benchmark", "--workers", "1", "--steps", "20", "--schedule", "open:101",
                "--run-id", "main_summary", "--output-root", str(self.root)]
        if preparation:
            argv.append("--preparation-motion-probe")
        if parameter_review:
            argv.append("--preparation-parameter-review")
        binding = {"relative_path": benchmark.PARAMETER_REVIEW_SCRIPT.as_posix(),
                   "freeze": "fake-freeze", "sha256": "fixed-source-sha"}
        with supervisor, environment, patch("sys.argv", argv), \
                patch.object(benchmark, "resource_sample", return_value={}), \
                patch.object(benchmark.subprocess, "check_output", return_value="fake-freeze"), \
                patch.object(benchmark, "_parameter_review_binding", return_value=binding), \
                patch.object(benchmark, "_parameter_review_environment", return_value=({}, {})), \
                patch.object(benchmark.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout="readonly-review", stderr="")), \
                contextlib.redirect_stdout(io.StringIO()):
            returncode = benchmark.main()
        directory = self.root / "main_summary"
        return (returncode, json.loads((directory / "benchmark_metadata.json").read_text()),
                json.loads((directory / "benchmark_summary.json").read_text()))

    def test_main_records_version_and_real_first_failure(self):
        returncode, metadata, summary = self.check_main_summary(
            preparation=True, on_step=lambda environment: (True, False))
        self.assertEqual(returncode, 1)
        self.assertEqual(metadata["preparation_probe_version"], "mr3-p2a0-outward-cancel-v2")
        self.assertFalse(summary["passed"])
        self.assertEqual(summary["valid_transitions"], 1)
        self.assertEqual(summary["preparation_abort"]["first_failure"]["worker_id"], 0)
        self.assertEqual(summary["preparation_abort"]["first_failure"]["reason"], "actual_failure")

    def test_main_complete_flag_fixture_passes_without_abort(self):
        returncode, metadata, summary = self.check_main_summary(preparation=True)
        self.assertEqual(returncode, 0)
        self.assertTrue(summary["passed"])
        self.assertFalse(summary["preparation_abort"]["requested"])
        self.assertEqual(summary["valid_transitions"], 20)

    def test_main_legacy_metadata_has_no_preparation_version_or_abort(self):
        returncode, metadata, summary = self.check_main_summary(preparation=False)
        self.assertEqual(returncode, 0)
        self.assertIsNone(metadata["preparation_probe_version"])
        self.assertFalse(metadata["preparation_parameter_review"])
        self.assertIsNone(metadata["preparation_parameter_review_source"])
        self.assertNotIn("preparation_abort", summary)

    def test_main_parameter_review_source_binding_is_in_metadata_and_summary(self):
        returncode, metadata, summary = self.check_main_summary(
            preparation=True, parameter_review=True)
        self.assertEqual(returncode, 0)
        self.assertTrue(metadata["preparation_parameter_review"])
        self.assertEqual(metadata["preparation_parameter_review_source"], {
            "relative_path": benchmark.PARAMETER_REVIEW_SCRIPT.as_posix(),
            "freeze": metadata["freeze"], "sha256": "fixed-source-sha"})
        self.assertEqual(summary["preparation_parameter_review_source"],
                         metadata["preparation_parameter_review_source"])

    def test_parameter_review_runs_after_reset_before_any_step_in_system_ros_environment(self):
        self.check_parameter_review(returncode=0)

    def test_parameter_review_failure_aborts_closes_and_saves_no_fake_step(self):
        self.check_parameter_review(returncode=1)

    def test_parameter_review_timeout_retains_partial_output_and_closes_without_step(self):
        self.check_parameter_review(returncode="timeout")

    def test_parameter_review_bad_transport_stops_before_spawn_or_step_and_closes(self):
        args = self.args()
        args.preparation_parameter_review, args.freeze = True, "fake-freeze"
        binding = {"sha256": "fixed-source-sha"}
        args.preparation_parameter_review_source = binding
        abort = benchmark._new_preparation_abort()
        supervisor, environment = self.fakes()
        with supervisor, environment, \
                patch.object(benchmark, "_parameter_review_binding", return_value=binding), \
                patch.object(benchmark, "_parameter_review_environment",
                             side_effect=RuntimeError("native transport mismatch")), \
                patch.object(benchmark.subprocess, "run") as command:
            result = benchmark.run_worker(args, 0, abort)
        command.assert_not_called()
        instance = self.environments[0]
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls),
                         (1, 0, 1))
        self.assertTrue(abort["event"].is_set())
        self.assertEqual(result["episodes"][0]["transitions"], 0)
        self.assertIn("native transport mismatch", result["error"])

    def check_parameter_review(self, returncode):
        args = self.args()
        args.schedule = args.schedule[:1]
        args.preparation_parameter_review, args.freeze = True, "fake-freeze"
        binding = {"relative_path": benchmark.PARAMETER_REVIEW_SCRIPT.as_posix(),
                   "freeze": args.freeze, "sha256": "fixed-source-sha"}
        args.preparation_parameter_review_source = binding
        abort = benchmark._new_preparation_abort()
        supervisor, environment = self.fakes()

        def review(command, **kwargs):
            instance = self.environments[0]
            self.assertEqual((instance.reset_calls, instance.step_calls), (1, 0))
            self.assertFalse(instance._episode_done)
            self.assertEqual(command[:2], ["bash", "-c"])
            self.assertIn('exec /usr/bin/python3 "$@"', command[2])
            self.assertEqual(command[4], str(
                benchmark.WORKSPACE / "ros2_ws/ros2-multi-robot-automap/install/setup.bash"))
            self.assertEqual(command[5], str(
                benchmark.WORKSPACE / benchmark.PARAMETER_REVIEW_SCRIPT))
            expected_tail = ["--freeze", "fake-freeze", "--output",
                             str(instance.supervisor.episode.directory /
                                 "actual_nav2_parameters.json"), "--wall-timeout-sec", "30"]
            self.assertEqual(command[-6:], expected_tail)
            self.assertEqual(kwargs, {"env": {"ROS_DOMAIN_ID": "206"},
                                      "text": True, "capture_output": True, "timeout": 45})
            if returncode == "timeout":
                raise subprocess.TimeoutExpired(command, 45, output=b"original-output",
                                                stderr=b"original-error")
            return SimpleNamespace(returncode=returncode, stdout="original-output",
                                   stderr="original-error")

        with supervisor, environment, \
                patch.object(benchmark, "_parameter_review_binding", return_value=binding), \
                patch.object(benchmark, "_parameter_review_environment", return_value=(
                    {"ROS_DOMAIN_ID": "206"}, {"native_profile_verified": True})) as ros_env, \
                patch.object(benchmark.subprocess, "run", side_effect=review) as command:
            result = benchmark.run_worker(args, 0, abort)
        ros_env.assert_called_once()
        self.assertEqual(ros_env.call_args.args[:2], (args, 0))
        command.assert_called_once()
        self.assertEqual(self.environments[0].close_calls, 1)
        trace = result["episodes"][0]["preparation_parameter_review"]
        self.assertEqual(trace["transport"], {"native_profile_verified": True})
        if returncode == "timeout":
            self.assertTrue(trace["timed_out"])
            self.assertEqual(trace["wall_timeout_sec"], 45)
        else:
            self.assertEqual(trace["returncode"], returncode)
        self.assertEqual(trace["stdout"], "original-output")
        self.assertEqual(trace["stderr"], "original-error")
        if returncode:
            self.assertTrue(abort["event"].is_set())
            self.assertEqual(result["episodes"][0]["transitions"], 0)
            self.assertEqual(self.environments[0].returned_steps, [])
            self.assertIn("TimeoutExpired" if returncode == "timeout" else
                          "parameter review failed", result["error"])
        else:
            self.assertFalse(abort["event"].is_set())
            self.assertEqual(result["episodes"][0]["transitions"], 20)
            self.assertIsNone(result["error"])

    def test_legacy_keeps_existing_reset_after_real_termination(self):
        supervisor, environment = self.fakes(on_step=lambda environment: (True, False))
        with supervisor, environment:
            result = benchmark.run_worker(self.args(preparation=False), 0)
        instance = self.environments[0]
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls),
                         (2, 2, 1))
        self.assertNotIn("preparation_abort", result)
        self.assertNotIn("reset_attempts", result)
        self.assertTrue(all(episode["terminated"] for episode in result["episodes"]))


class ParameterReviewTransportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.args = SimpleNamespace(freeze="a" * 40, base_domain=212, base_port=12561)
        self.profile = self.root / benchmark.PARAMETER_REVIEW_PROFILE
        self.profile.parent.mkdir(parents=True)
        self.profile.write_bytes(b"reviewed-loopback-udp-profile")
        self.episode = {"output_directory": str(self.root / "episode"), "epoch": "actual-epoch"}
        Path(self.episode["output_directory"]).mkdir()
        self.native = {
            "RMW_IMPLEMENTATION": "rmw_fastrtps_cpp", "ROS_LOCALHOST_ONLY": "0",
            "FASTRTPS_DEFAULT_PROFILES_FILE": str(self.profile), "SKIP_DEFAULT_XML": "1",
            "FASTDDS_DEFAULT_PROFILES_FILE": None, "RMW_FASTRTPS_USE_QOS_FROM_XML": None,
            "RMW_FASTRTPS_PUBLICATION_MODE": None,
            "profile_sha256": hashlib.sha256(self.profile.read_bytes()).hexdigest(),
        }
        self.metadata = {"freeze": self.args.freeze, "epoch": self.episode["epoch"],
                         "transport_environment": self.native}

    def environment(self, *, frozen=None):
        path = Path(self.episode["output_directory"]) / "metadata.json"
        path.write_text(json.dumps(self.metadata))
        baseline = {"ROS_DOMAIN_ID": "212", "PATH": "/usr/bin",
                    **{key: "unrelated-parent-value" for key in benchmark.TRANSPORT_ENV_KEYS}}
        frozen = self.profile.read_bytes() if frozen is None else frozen
        with patch.object(benchmark, "WORKSPACE", self.root), \
                patch.object(benchmark, "ros_environment", return_value=baseline) as ros_env, \
                patch.object(benchmark.subprocess, "check_output", return_value=frozen) as git:
            result = benchmark._parameter_review_environment(self.args, 0, self.episode)
        ros_env.assert_called_once_with(212, 12561)
        git.assert_called_once_with([
            "git", "show", f"{self.args.freeze}:{benchmark.PARAMETER_REVIEW_PROFILE.as_posix()}"],
            cwd=self.root)
        self.assertTrue(all(baseline[key] == "unrelated-parent-value"
                            for key in benchmark.TRANSPORT_ENV_KEYS))
        return result

    def test_native_discovery_keys_are_exact_none_values_remove_parent_defaults(self):
        self.native["BASH_ENV"] = "/untrusted/metadata/must/not/execute"
        environment, trace = self.environment()
        self.assertEqual(environment["ROS_DOMAIN_ID"], "212")
        self.assertEqual(environment["PATH"], "/usr/bin")
        for key in benchmark.TRANSPORT_ENV_KEYS:
            if self.native[key] is None:
                self.assertNotIn(key, environment)
            else:
                self.assertEqual(environment[key], self.native[key])
        self.assertNotIn("BASH_ENV", environment)
        self.assertNotIn("BASH_ENV", trace["native_transport_environment"])
        self.assertEqual(trace["profile_source"]["sha256"], self.native["profile_sha256"])
        self.assertEqual(trace["profile_source"]["freeze"], self.args.freeze)
        self.assertEqual(trace["selected_transport_environment"],
                         {key: self.native[key] for key in benchmark.TRANSPORT_ENV_KEYS})

    def test_wrong_rmw_profile_hash_or_transport_key_rejected(self):
        for key, value in (
                ("RMW_IMPLEMENTATION", "rmw_other"), ("ROS_LOCALHOST_ONLY", "1"),
                ("FASTRTPS_DEFAULT_PROFILES_FILE", "/unreviewed/profile.xml"),
                ("SKIP_DEFAULT_XML", "0"), ("FASTDDS_DEFAULT_PROFILES_FILE", "/alternate.xml"),
                ("RMW_FASTRTPS_USE_QOS_FROM_XML", "1"),
                ("RMW_FASTRTPS_PUBLICATION_MODE", "ASYNCHRONOUS"),
                ("profile_sha256", "0" * 64)):
            with self.subTest(key=key):
                original = self.native[key]
                self.native[key] = value
                with self.assertRaisesRegex(RuntimeError, "transport/profile declaration"):
                    self.environment()
                self.native[key] = original

    def test_missing_none_key_is_not_silently_inherited(self):
        del self.native["FASTDDS_DEFAULT_PROFILES_FILE"]
        with self.assertRaisesRegex(RuntimeError, "transport/profile declaration"):
            self.environment()

    def test_native_metadata_epoch_and_freeze_bindings_required(self):
        for key in ("epoch", "freeze"):
            with self.subTest(key=key):
                original = self.metadata[key]
                self.metadata[key] = "different"
                with self.assertRaisesRegex(RuntimeError, "metadata freeze/epoch mismatch"):
                    self.environment()
                self.metadata[key] = original

    def test_native_declared_profile_must_equal_frozen_git_bytes(self):
        with self.assertRaisesRegex(RuntimeError, "profile differs from the declared source"):
            self.environment(frozen=b"different-frozen-profile")

    def test_changed_disk_profile_rejected_even_if_native_sha_updated(self):
        frozen = self.profile.read_bytes()
        self.profile.write_bytes(b"changed-profile")
        self.native["profile_sha256"] = hashlib.sha256(self.profile.read_bytes()).hexdigest()
        with self.assertRaisesRegex(RuntimeError, "profile differs from the declared source"):
            self.environment(frozen=frozen)

    def test_symlinked_profile_is_not_an_alternate_execution_path(self):
        target = self.root / "elsewhere.xml"
        target.write_bytes(self.profile.read_bytes())
        self.profile.unlink()
        self.profile.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError, "canonical unsymlinked path"):
            self.environment()


if __name__ == "__main__":
    unittest.main()
