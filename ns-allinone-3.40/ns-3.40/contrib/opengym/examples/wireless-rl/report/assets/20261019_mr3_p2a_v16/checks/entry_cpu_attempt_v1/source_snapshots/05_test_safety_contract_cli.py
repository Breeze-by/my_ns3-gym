"""CPU entry guards: a new engineering profile cannot inherit old PPO credit."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import benchmark, ppo


class SafetyContractCLITests(unittest.TestCase):
    def test_reach_train_and_evaluate_reject_before_files_gpu_or_native_even_with_old_receipts(self):
        for mode in ("train", "evaluate"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                root = Path(root)
                (root/"legacy_qualification.json").write_text(json.dumps({"passed": True, "roles": "38/38"}))
                (root/"final.zip").write_bytes(b"old checkpoint cannot authorize a new contract")
                args = ["--run-id", "refused", "--safety-contract", "mr3-reach-v1", "--mode", mode,
                        "--decisions", "2", "--wall-seconds", "60", "--output-root", str(root)]
                if mode == "evaluate":
                    args += ["--checkpoint", str(root/"final.zip")]
                stderr = io.StringIO()
                with patch.object(ppo.Path, "mkdir") as mkdir, \
                        patch.object(ppo, "Supervisor") as supervisor, \
                        patch.object(ppo, "MaskablePPO") as model, \
                        patch.object(ppo, "resource_sample") as resources, \
                        patch.object(ppo.subprocess, "check_output") as git, \
                        patch.object(ppo.torch, "set_num_threads") as threads, \
                        patch.object(ppo.torch, "use_deterministic_algorithms") as deterministic, \
                        contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit) as failure:
                    ppo.main(args)
                self.assertEqual(failure.exception.code, 2)
                self.assertIn("new-freeze scientific qualification", stderr.getvalue())
                for operation in (mkdir, supervisor, model, resources, git, threads, deterministic):
                    operation.assert_not_called()
                self.assertFalse((root/"refused").exists())

    def test_reach_legacy_preparation_options_reject_before_source_review_or_launch(self):
        for flags in (["--preparation-motion-probe"], ["--preparation-parameter-review"],
                      ["--preparation-probe-version", benchmark.PREPARATION_PROBE_V3],
                      ["--preparation-parameter-profile", "gentle_turn_v1"]):
            with self.subTest(flags=flags), tempfile.TemporaryDirectory() as root:
                args = ["--workers", "1", "--schedule", "open:101", "--steps", "32", "--run-id", "refused",
                        "--safety-contract", "mr3-reach-v1", "--output-root", root, *flags]
                with patch.object(benchmark.Path, "mkdir") as mkdir, \
                        patch.object(benchmark, "Supervisor") as supervisor, \
                        patch.object(benchmark, "_parameter_review_binding") as reader, \
                        patch.object(benchmark.subprocess, "check_output") as git, \
                        contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as failure:
                    benchmark.main(args)
                self.assertEqual(failure.exception.code, 2)
                for operation in (mkdir, supervisor, reader, git):
                    operation.assert_not_called()
                self.assertFalse((Path(root)/"refused").exists())

    def test_benchmark_records_profile_and_keeps_engineering_success_unqualified(self):
        for profile in ("legacy", "mr3-reach-v1"):
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as root:
                def completed(args, worker_id, abort):
                    self.assertEqual(args.safety_contract, profile)
                    return {"worker_id": worker_id, "error": None, "episodes": [
                        {"transitions": 2, "terminated": False, "truncated": True, "dt_values": [1., 1.]}],
                        "shutdown_receipts": [{"remaining_owned_processes": [], "remaining_owned_zombies": [],
                                               "forced_shutdown": False, "worker_returncode": 0}]}
                args = ["--workers", "1", "--schedule", "open:101", "--steps", "2", "--run-id", "fixture", "--output-root", root]
                if profile != "legacy":
                    args += ["--safety-contract", profile]
                with patch.object(benchmark, "run_worker", side_effect=completed), \
                        patch.object(benchmark, "resource_sample", return_value={}), \
                        patch.object(benchmark.subprocess, "check_output", return_value="a"*40), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(benchmark.main(args), 0)
                metadata = json.loads((Path(root)/"fixture/benchmark_metadata.json").read_text())
                summary = json.loads((Path(root)/"fixture/benchmark_summary.json").read_text())
                self.assertEqual(metadata["safety_contract"], profile)
                self.assertTrue(summary["passed"])  # Scripted collection completeness only.
                if profile != "legacy":
                    self.assertFalse(metadata["training_eligible"])
                    self.assertFalse(metadata["scientific_readers_applied"])
                    self.assertEqual(metadata["scientific_qualification"], "PENDING_NEW_FREEZE_INDEPENDENT_AUDITS")

    def test_worker_passes_explicit_reach_to_supervisor_before_any_reset(self):
        args = SimpleNamespace(safety_contract="mr3-reach-v1", preparation_motion_probe=False,
                               run_id="fixture", base_domain=120, base_port=12001,
                               output_root=Path("unused"), terminal_probe=False)
        with patch.object(benchmark, "Supervisor", side_effect=RuntimeError("CPU construction sentinel")) as owner:
            with self.assertRaisesRegex(RuntimeError, "CPU construction sentinel"):
                benchmark.run_worker(args, 0)
        self.assertEqual(owner.call_args.kwargs["safety_contract"], "mr3-reach-v1")

    def test_unknown_direct_collection_profile_rejects_before_supervisor(self):
        with patch.object(benchmark, "Supervisor") as owner:
            with self.assertRaisesRegex(ValueError, "unknown safety contract"):
                benchmark.run_worker(SimpleNamespace(safety_contract=True), 0)
        owner.assert_not_called()


if __name__ == "__main__":
    unittest.main()
