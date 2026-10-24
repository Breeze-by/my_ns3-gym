"""CPU-only admission, native-hook restoration and immutable diagnostic inputs."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning import audit_reach_diagnostic as diagnostic
from mr3_learning import reach_gates, reach_preparation


FREEZE = "a" * 40


class DiagnosticTests(unittest.TestCase):
    def fixture(self, root):
        root = Path(root)
        run = root / "run"
        episode = run / "worker0/episode001_open_101"
        episode.mkdir(parents=True)
        (episode / "metadata.json").write_text('{"freeze":"' + FREEZE + '"}')
        source = root / "execution.py"
        source.write_text("actual source\n")
        binding = root / "binding.json"
        binding.write_text("{}\n")
        plan = {"schema": diagnostic.SCHEMA, "safety_contract": diagnostic.CONTRACT,
                "robots_per_environment": 3, "optimizer_steps": 0, "gpu_calls": 0,
                "qualification": False, "training_eligible": False,
                "run_directory": str(run), "expected_episodes": 1,
                "custody_binding": str(binding),
                "source_bindings": {"execution.py": diagnostic.digest(source.read_bytes())}}
        plan_path = root / "plan.json"
        plan_path.write_text(json.dumps(plan))
        return root, run, episode, plan, plan_path

    @staticmethod
    def git(root):
        return lambda argv, **kwargs: (root / argv[-1].split(":", 1)[1]).read_bytes()

    def test_source_binding_requires_complete_inventory_exact_git_and_explicit_nontraining(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, run, _, plan, plan_path = self.fixture(temporary)
            with patch.object(reach_preparation, "source_inventory", return_value={"execution.py"}), \
                    patch.object(diagnostic.subprocess, "check_output", side_effect=self.git(root)):
                loaded, proof, stable = diagnostic.bound_sources(plan_path, run, FREEZE, root)
                self.assertEqual(loaded, plan)
                self.assertEqual(set(proof), {"execution.py", "binding.json", "plan.json"})
                self.assertEqual(len(stable), 3)
                with patch.object(reach_preparation, "source_inventory", return_value={"missing.py"}):
                    with self.assertRaisesRegex(ValueError, "inventory is incomplete"):
                        diagnostic.bound_sources(plan_path, run, FREEZE, root)
                with patch.object(diagnostic.subprocess, "check_output", return_value=b"different frozen source"):
                    with self.assertRaisesRegex(ValueError, "plan/Git freeze"):
                        diagnostic.bound_sources(plan_path, run, FREEZE, root)
                plan["qualification"] = True
                plan_path.write_text(json.dumps(plan))
                with self.assertRaisesRegex(ValueError, "non-training"):
                    diagnostic.bound_sources(plan_path, run, FREEZE, root)

    def test_original_qualification_plan_and_source_rejections_precede_shared_body(self):
        with patch.object(reach_preparation, "load_plan", side_effect=ValueError("original rejection")), \
                patch.object(reach_gates, "_load_versioned_native_gates") as body:
            with self.assertRaisesRegex(ValueError, "original rejection"):
                reach_gates.load_native_gates(Path("/root"), FREEZE, Path("/root/plan"))
            body.assert_not_called()
        plan = {"source_bindings": {"actual": "hash"}, "custody_binding": "binding"}
        with patch.object(reach_preparation, "load_plan", return_value=plan), \
                patch.object(reach_preparation, "source_check", side_effect=ValueError("source rejection")), \
                patch.object(reach_gates, "_load_versioned_native_gates") as body:
            with self.assertRaisesRegex(ValueError, "source rejection"):
                reach_gates.load_native_gates(Path("/root"), FREEZE, Path("/root/plan"))
            body.assert_not_called()
        with patch.object(reach_preparation, "load_plan", return_value=plan), \
                patch.object(reach_preparation, "source_check", return_value={"proof": 1}) as check, \
                patch.object(reach_gates, "_load_versioned_native_gates", return_value="same gates") as body:
            self.assertEqual(reach_gates.load_native_gates(Path("/root"), FREEZE, Path("/root/plan")), "same gates")
            check.assert_called_once_with(plan, Path("/root/plan"), FREEZE, Path("/root"), require_clean=False)
            body.assert_called_once_with(Path("/root"), FREEZE, {"proof": 1}, {"actual": "hash"}, "binding")

    def test_fifo_result_rejects_missing_or_mutated_raw_bindings_and_mixed_freeze(self):
        with tempfile.TemporaryDirectory() as temporary:
            _, _, episode, _, _ = self.fixture(temporary)
            payload = episode / "motion.jsonl"
            payload.write_text("original\n")
            leaf = {"schema": "mr3-reach-peer-control-fifo-review-v1", "episode": str(episode),
                    "safety_contract": diagnostic.CONTRACT, "freeze": FREEZE,
                    "passed": True, "errors": [], "bindings": {str(payload): {
                        "sha256": diagnostic.digest(payload.read_bytes()), "bytes": payload.stat().st_size}}}
            selected = Path(temporary) / "fifo.json"
            selected.write_text(json.dumps(leaf))
            result, stable = diagnostic.fifo_results([selected], [episode], FREEZE)
            self.assertEqual(result[episode], leaf)
            self.assertEqual(stable[selected], selected.read_bytes())
            with self.assertRaisesRegex(ValueError, "duplicated"):
                diagnostic.fifo_results([selected, selected], [episode], FREEZE)
            payload.write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "raw binding differs"):
                diagnostic.fifo_results([selected], [episode], FREEZE)
            leaf["freeze"] = "b" * 40
            selected.write_text(json.dumps(leaf))
            with self.assertRaisesRegex(ValueError, "failed/mixed"):
                diagnostic.fifo_results([selected], [episode], FREEZE)

    def test_native_failures_restore_hooks_and_do_not_invoke_scripted_coverage(self):
        from mr3_learning import audit_reach_controlled_physics, audit_evaluator_phase
        directory = Path("/actual/episode")
        native = SimpleNamespace(audit_physics=object(), audit_initial_inputs_ready=object())
        old_physics, old_readiness = native.audit_physics, native.audit_initial_inputs_ready
        fifo = {"passed": True, "real": "independent FIFO"}
        def physics(auditor, directories, cache):
            self.assertEqual(cache, {directory: fifo})
            auditor.audit_physics = "temporary physics"
        def readiness(auditor, directories, cache):
            auditor.audit_initial_inputs_ready = "temporary readiness"
        scalar = SimpleNamespace(audit_episode=Mock(return_value={"passed": True, "errors": []}))
        phase = SimpleNamespace(corrected_audit=Mock(side_effect=ValueError("real native failure")))
        preparation = SimpleNamespace(audit_archives=Mock(return_value={"passed": True}),
            audit_activity=Mock(return_value={"passed": True}),
            audit_execution_inputs=Mock(return_value={"passed": True}))
        with patch.object(audit_reach_controlled_physics, "dispatch_controlled_physics", side_effect=physics), \
                patch.object(audit_reach_controlled_physics, "dispatch_controlled_readiness", side_effect=readiness), \
                patch.object(audit_evaluator_phase, "audit_episode", return_value={"passed": True}):
            result = diagnostic.audit_episode(directory, FREEZE,
                (phase, object(), native, object(), scalar, {}), preparation, fifo)
        self.assertFalse(result["passed"])
        self.assertEqual(result["errors"], ["native: real native failure"])
        self.assertIs(native.audit_physics, old_physics)
        self.assertIs(native.audit_initial_inputs_ready, old_readiness)
        self.assertIs(result["peer_control_fifo"], fifo)
        self.assertEqual(result["fifo_source"], "independent_result")
        preparation.audit_execution_inputs.assert_called_once_with(directory, fifo)
        scalar.audit_episode.assert_called_once_with(directory, FREEZE)

    def test_incomplete_and_modified_evidence_are_reported_without_training_credit(self):
        from mr3_learning import audit_reach_preparation
        for mutate, expected in ((False, "incomplete"), (True, "input inventory/bytes changed")):
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as temporary:
                root, run, episode, plan, plan_path = self.fixture(temporary)
                plan["expected_episodes"] = 2 if not mutate else 1
                plan_path.write_text(json.dumps(plan))
                stable = {plan_path: plan_path.read_bytes()}
                def episode_audit(*args):
                    if mutate:
                        (episode / "metadata.json").write_text("changed evidence")
                    return {"directory": str(episode), "passed": True, "errors": []}
                with patch.object(diagnostic, "bound_sources", return_value=(plan, {}, stable)), \
                        patch.object(reach_gates, "_load_versioned_native_gates", return_value=(None,) * 5 + ({},)), \
                        patch.object(audit_reach_preparation, "load_impl", return_value=(object(), {})), \
                        patch.object(diagnostic, "audit_episode", side_effect=episode_audit):
                    result = diagnostic.audit(run, FREEZE, plan_path, root=root)
                self.assertFalse(result["passed"])
                self.assertFalse(result["qualification"])
                self.assertFalse(result["training_eligible"])
                self.assertTrue(any(expected in error for error in result["errors"]), result["errors"])
                self.assertEqual(len(result["episodes"]), 1)

    def test_cli_preserves_existing_outputs_and_writes_fail_closed_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, run, _, _, plan_path = self.fixture(temporary)
            output = root / "result.json"
            args = [str(run), "--freeze", FREEZE, "--plan", str(plan_path), "--output", str(output)]
            report = {"passed": False, "qualification": False, "training_eligible": False,
                      "errors": ["genuine incomplete native evidence"]}
            with patch.object(diagnostic, "audit", return_value=report), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(diagnostic.main(args), 1)
            self.assertEqual(json.loads(output.read_text()), report)
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                diagnostic.main(args)
            self.assertEqual(json.loads(output.read_text()), report)


if __name__ == "__main__":
    unittest.main()
