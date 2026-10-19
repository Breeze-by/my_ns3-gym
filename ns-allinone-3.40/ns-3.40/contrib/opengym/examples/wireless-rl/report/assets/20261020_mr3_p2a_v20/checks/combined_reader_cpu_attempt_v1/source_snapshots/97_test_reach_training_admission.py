"""Reject reach training before side effects; all native receipts are fixtures.

The qualifier bookkeeping fixture stubs source admission and PID liveness. It
does not create a scientific qualification. Every CLI case below is refused.
"""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import numpy as np

from mr3_learning import ppo, reach_preparation as qualification
from mr3_learning.supervisor import InfrastructureError
from mr3_learning.tests import test_ppo as collection
from mr3_learning.tests import test_reach_qualification as bookkeeping


FREEZE = "a"*40


class ReachTrainingAdmissionTests(unittest.TestCase):
    def guards(self):
        return (patch.object(ppo.Path, "mkdir"), patch.object(ppo, "Supervisor"),
                patch.object(ppo, "MaskablePPO"), patch.object(ppo, "resource_sample"),
                patch.object(ppo.torch, "set_num_threads"),
                patch.object(ppo.torch, "use_deterministic_algorithms"),
                patch.object(ppo.torch.cuda, "is_available"))

    def arguments(self, root, mode="train"):
        result = ["--run-id", "must-not-start", "--safety-contract", "mr3-reach-v1",
                  "--mode", mode, "--decisions", "2", "--episode-steps", "2",
                  "--wall-seconds", "60", "--output-root", str(root)]
        if mode == "evaluate": result += ["--checkpoint", str(Path(root)/"old-final.zip")]
        return result

    def test_missing_either_or_both_new_qualification_parameters_rejects_train_and_eval(self):
        for mode in ("train", "evaluate"):
            for flags in ([], ["--reach-plan", "/unused/plan"],
                          ["--reach-qualification", "/unused/old-passed.json"]):
                with self.subTest(mode=mode, flags=flags), tempfile.TemporaryDirectory() as root:
                    a,b,c,d,e,f,g = self.guards()
                    with a as mkdir,b as native,c as model,d as resources,e as threads,f as deterministic,g as gpu, \
                            patch.object(ppo.subprocess, "check_output") as git, \
                            patch.object(qualification, "validate_qualification") as validate, \
                            contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                        ppo.main([*self.arguments(root, mode), *flags])
                    self.assertEqual(error.exception.code, 2)
                    for operation in (mkdir,native,model,resources,threads,deterministic,gpu,git,validate):
                        operation.assert_not_called()

    def test_old_passed_qualification_schema_is_refused_before_mkdir_model_or_gpu(self):
        with tempfile.TemporaryDirectory() as root:
            old = Path(root)/"old.json"
            old.write_text(json.dumps({"schema": "mr3-preparation-qualification-v1", "passed": True,
                                       "freeze": FREEZE, "mandatory_roles": 38}))
            a,b,c,d,e,f,g = self.guards()
            with a as mkdir,b as native,c as model,d as resources,e as threads,f as deterministic,g as gpu, \
                    patch.object(ppo.subprocess, "check_output", return_value=FREEZE), \
                    patch.object(qualification, "_qualification_evidence") as evidence:
                with self.assertRaisesRegex(ValueError, "old/missing qualification schema"):
                    ppo.main([*self.arguments(root), "--reach-plan", str(Path(root)/"absent-plan.json"),
                              "--reach-qualification", str(old)])
            for operation in (mkdir,native,model,resources,threads,deterministic,gpu,evidence): operation.assert_not_called()
            self.assertFalse((Path(root)/"must-not-start").exists())

    def test_wrong_plan_sha_in_a_new_schema_receipt_is_recomputed_and_refused_before_side_effects(self):
        fixture = bookkeeping.ReachQualificationTests(); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        fixture.evidence()
        receipt = fixture.replay()
        receipt.update(schema=qualification.QUALIFICATION_SCHEMA, plan_sha256="0"*64)
        path = fixture.root/"wrong-plan-qualification.json"; path.write_text(json.dumps(receipt))
        original_git = ppo.subprocess.check_output
        def git(argv, **kwargs):
            if argv == ["git", "rev-parse", "HEAD"]: return FREEZE
            return original_git(argv, **kwargs)
        a,b,c,d,e,f,g = self.guards()
        with a as mkdir,b as native,c as model,d as resources,e as threads,f as deterministic,g as gpu, \
                patch.object(ppo.subprocess, "check_output", side_effect=git), \
                patch.object(qualification, "source_check", return_value={}), \
                patch.object(qualification.primitives, "identity", return_value=None):
            with self.assertRaisesRegex(ValueError, "receipt differs from actual evidence"):
                ppo.main([*self.arguments(fixture.root), "--reach-plan", str(fixture.plan_path),
                          "--reach-qualification", str(path)])
        for operation in (mkdir,native,model,resources,threads,deterministic,gpu): operation.assert_not_called()
        self.assertFalse((fixture.root/"must-not-start").exists())

    def test_legacy_profile_cannot_borrow_reach_receipt_before_any_side_effect(self):
        a,b,c,d,e,f,g = self.guards()
        with a as mkdir,b as native,c as model,d as resources,e as threads,f as deterministic,g as gpu, \
                patch.object(qualification, "validate_qualification") as validate, \
                contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
            ppo.main(["--run-id", "refused", "--decisions", "2", "--wall-seconds", "60",
                      "--reach-plan", "/unused/plan", "--reach-qualification", "/unused/receipt"])
        self.assertEqual(error.exception.code, 2)
        for operation in (mkdir,native,model,resources,threads,deterministic,gpu,validate): operation.assert_not_called()

    def test_normal_control_model_scalar_failure_rejects_entire_closed_round_without_targets(self):
        environments = [collection.ReceiptEnv([
            {"reward": .2}, {"reward": -20., "terminated": True, "reason": "navigation_failure",
                             "dt": .22, "physical_dt": .24}], epoch="normal-model-failure", native_failures=[
                json.dumps({"component": "motion_safety", "reason": "normal_control_model_invalid"})]),
            collection.ReceiptEnv([{"terminated": True}], epoch="healthy-peer")]
        journal = {}
        original_check = ppo.closed_episode_training_eligibility
        def closed_check(directory, epoch):
            self.assertEqual([env.closed for env in environments], [1, 1])
            return original_check(directory, epoch)
        with patch.object(ppo, "infer", side_effect=collection.fixture_infer), \
                patch.object(ppo, "next_value", return_value=.25), \
                patch.object(ppo, "closed_episode_training_eligibility", side_effect=closed_check), \
                patch.object(ppo, "build_rollout_buffer") as targets, \
                self.assertRaisesRegex(InfrastructureError, "normal_control_model_invalid") as rejected:
            ppo.collect_episodes(None, environments, collection.tasks_for(environments),
                                 deadline=time.monotonic()+60, journal=journal)
        targets.assert_not_called()
        self.assertEqual([len(rows) for rows in journal["episodes"]], [2, 1])
        self.assertTrue(all(row["shutdown"]["clean"] for row in journal["summaries"]))
        self.assertIn("normal_control_model_invalid", journal["summaries"][0]["infrastructure_error"])
        terminal = journal["episodes"][0][-1]
        self.assertEqual((terminal.reward,terminal.dt,terminal.next_value), (-20.,.22,0.))
        self.assertTrue(terminal.terminated); self.assertFalse(terminal.truncated)
        with tempfile.TemporaryDirectory() as root:
            path = Path(root)/"whole-round-ineligible.npz"
            ppo.save_failed_collection(path, journal, rejected.exception)
            diagnostic = json.loads(path.with_suffix(".json").read_text())
            self.assertFalse(diagnostic["training_eligible"])
            self.assertEqual(diagnostic["collector_returned_decisions"], 3)
            with np.load(path, allow_pickle=False) as arrays:
                self.assertNotIn("advantages", arrays.files); self.assertNotIn("returns", arrays.files)
                np.testing.assert_array_equal(arrays["terminated"], [False, True, True])
                np.testing.assert_array_equal(arrays["dt"], [1., .22, 1.])


if __name__ == "__main__":
    unittest.main()
