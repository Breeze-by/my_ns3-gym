"""Wall admission preserves real RPC returns and closes every shared worker."""

from concurrent.futures import ThreadPoolExecutor
import contextlib
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from mr3_learning import benchmark
from mr3_learning.tests import test_benchmark as benchmark_fixture


class WorkWallTests(unittest.TestCase):
    def setUp(self):
        self.fixture = benchmark_fixture.CooperativeAbortTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.clock = [0]

    def args(self, preparation=False):
        args = self.fixture.args(preparation)
        args.close_reserve_seconds = 120.
        args.allocation_deadline_monotonic_ns = 1_000_000_000_000
        return args

    def test_admission_requires_whole_existing_rpc_upper_bound_plus_close(self):
        args, abort = self.args(), benchmark._new_preparation_abort()
        for operation, clock, allowed in (("reset", 460, True), ("reset", 461, False),
                                          ("step", 790, True), ("step", 791, False),
                                          ("after_rpc", 880, True), ("after_rpc", 881, False)):
            with self.subTest(operation=operation, clock=clock):
                abort = benchmark._new_preparation_abort()
                with patch.object(benchmark.time, "monotonic_ns", return_value=clock * 10**9):
                    self.assertEqual(benchmark._wall_admission(args, abort, 0, operation), allowed)

    def test_nonmotion_preserves_completed_step_then_skips_next_step_and_reset(self):
        def step(environment):
            self.clock[0] = 850 * 10**9
            return False, False
        supervisor, environment = self.fixture.fakes(on_step=step)
        with supervisor, environment, patch.object(
                benchmark.time, "monotonic_ns", side_effect=lambda: self.clock[0]):
            result = benchmark.run_worker(self.args(), 0)
        instance = self.fixture.environments[0]
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (1, 1, 1))
        self.assertEqual(result["episodes"][0]["transitions"], 1)
        self.assertNotIn("truncated", result["episodes"][0])
        self.assertIsNone(result["error"])
        self.assertEqual(result["work_wall_abort"]["first_failure"]["kind"],
                         "work_wall_allocation_exhausted")

    def test_terminal_probe_is_also_stopped_before_first_step(self):
        def reset(environment):
            self.clock[0] = 850 * 10**9
        args = self.args()
        args.terminal_probe = True
        supervisor, environment = self.fixture.fakes(on_reset=reset)
        with supervisor, environment, patch.object(
                benchmark.time, "monotonic_ns", side_effect=lambda: self.clock[0]):
            result = benchmark.run_worker(args, 0)
        instance = self.fixture.environments[0]
        self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (1, 0, 1))
        self.assertEqual(result["episodes"][0]["transitions"], 0)
        self.assertTrue(result["work_wall_abort"]["requested"])

    def test_two_workers_share_absolute_deadline_and_keep_both_inflight_returns(self):
        barrier, abort = threading.Barrier(2), benchmark._new_preparation_abort()

        def step(environment):
            barrier.wait(timeout=5.)
            if environment.supervisor.worker_id == 0:
                self.clock[0] = 900 * 10**9
            else:
                self.assertTrue(abort["event"].wait(timeout=5.))
            return False, False

        supervisor, environment = self.fixture.fakes(on_step=step)
        with supervisor, environment, patch.object(
                benchmark.time, "monotonic_ns", side_effect=lambda: self.clock[0]), \
                ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(benchmark.run_worker, self.args(), worker, abort)
                       for worker in range(2)]
            results = [future.result(timeout=10.) for future in futures]
        for result in results:
            instance = self.fixture.environments[result["worker_id"]]
            self.assertEqual((instance.reset_calls, instance.step_calls, instance.close_calls), (1, 1, 1))
            self.assertEqual(result["episodes"][0]["reward_sum"], 1.)
            self.assertEqual(result["work_wall_abort"]["first_failure"], abort["first_failure"])
        original = dict(abort["first_failure"])
        benchmark._preparation_failure(abort, 1, "later_failure", "must not replace")
        self.assertEqual(abort["first_failure"], original)

    def test_real_preparation_failure_precedes_wall_failure(self):
        def step(environment):
            self.clock[0] = 900 * 10**9
            return True, False
        supervisor, environment = self.fixture.fakes(on_step=step)
        with supervisor, environment, patch.object(
                benchmark.time, "monotonic_ns", side_effect=lambda: self.clock[0]):
            result = benchmark.run_worker(self.args(preparation=True), 0)
        self.assertTrue(result["episodes"][0]["terminated"])
        self.assertEqual(result["preparation_abort"]["first_failure"]["kind"], "unexpected_termination")

    def test_main_entry_clock_shared_with_workers_and_summary_counts_close(self):
        def complete(args, worker_id, abort):
            self.assertEqual(args.allocation_deadline_monotonic_ns, 710 * 10**9)
            self.clock[0] = 720 * 10**9  # Includes a close that exceeded allocation.
            return {"worker_id": worker_id, "episodes": [], "error": None,
                    "shutdown_receipts": []}
        with tempfile.TemporaryDirectory() as root:
            self.clock[0] = 10 * 10**9
            argv = ["benchmark", "--workers", "1", "--steps", "1", "--run-id", "wall",
                    "--output-root", root, "--work-wall-seconds", "700", "--close-reserve-seconds", "120"]
            with patch("sys.argv", argv), patch.object(benchmark, "run_worker", side_effect=complete), \
                    patch.object(benchmark, "resource_sample", return_value={}), \
                    patch.object(benchmark.subprocess, "check_output", return_value="freeze"), \
                    patch.object(benchmark.time, "monotonic_ns", side_effect=lambda: self.clock[0]), \
                    patch.object(benchmark.time, "monotonic", side_effect=lambda: self.clock[0] / 1e9), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(benchmark.main(), 1)
            summary = json.loads((Path(root) / "wall/benchmark_summary.json").read_text())
            self.assertEqual(summary["wall_sec_including_all_attempts"], 710.)
            self.assertTrue(summary["wall_limit_exceeded"])
            self.assertFalse(summary["passed"])
            self.assertEqual(summary["outcome"], "FAIL")
            self.assertEqual(summary["work_wall_abort"]["first_failure"]["kind"],
                             "wall_allocation_exceeded")

    def test_invalid_wall_budgets_rejected_before_directory_creation(self):
        for total, reserve in (("nan", "120"), ("inf", "120"), ("120", "120"), ("700", "0")):
            with self.subTest(total=total, reserve=reserve), tempfile.TemporaryDirectory() as root:
                with patch("sys.argv", ["benchmark", "--workers", "1", "--run-id", "bad",
                                         "--output-root", root, "--work-wall-seconds", total,
                                         "--close-reserve-seconds", reserve]), \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    benchmark.main()
                self.assertEqual(list(Path(root).iterdir()), [])
