"""Artificial closed-summary/collector checks; no Node, model or optimizer run.

The closed receipts and callbacks are synthetic. Historical V49 evidence is
not consumed or reclassified by these checks.
"""
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning import ppo
from mr3_learning.supervisor import InfrastructureError
from mr3_learning.tests import test_ppo as collection


SCHEMA = "mr3-reach-runtime-fault-v1"
EPOCH = "closed-artificial-epoch"


def fault(reason="calibration sequence gap/regression", **changes):
    value = {"component": "motion_safety", "schema": SCHEMA, "epoch": EPOCH,
             "robot": "tb3", "reason": reason, "clock_ns": 1_000_000_000}
    value.update(changes)
    return value


class ReachRuntimeFaultAdmissionTests(unittest.TestCase):
    def eligibility(self, messages, *, summary_epoch=EPOCH):
        with tempfile.TemporaryDirectory(prefix="mr3_artificial_admission_") as directory:
            path = Path(directory) / "summary.json"
            raw = (json.dumps({"epoch": summary_epoch, "failures": messages}) + "\n").encode()
            path.write_bytes(raw)
            try:
                return ppo.closed_episode_training_eligibility(directory, EPOCH)
            finally:
                self.assertEqual(path.read_bytes(), raw)

    def test_current_epoch_versioned_fault_rejects_precise_native_reasons(self):
        for reason in ("calibration sequence gap/regression", "storage target changed",
                       "a precise cause not in the historical reason registry"):
            with self.subTest(reason=reason), self.assertRaisesRegex(
                    InfrastructureError, "native training ineligible: motion_safety reach runtime fault"):
                self.eligibility([json.dumps(fault(reason))])

    def test_new_fault_missing_or_foreign_epoch_is_bad_receipt_not_eligible(self):
        for epoch in (None, "other-episode", True, 7, ""):
            for omit in ((True, False) if epoch is None else (False,)):
                value = fault(epoch=epoch)
                if omit:
                    value.pop("epoch")
                with self.subTest(epoch=epoch, omitted=omit), self.assertRaisesRegex(
                        InfrastructureError, "eligibility receipt: reach fault epoch differs") as error:
                    self.eligibility([json.dumps(value)])
                self.assertNotIn("native training ineligible:", str(error.exception))

    def test_three_old_reason_literals_still_reject_without_an_epoch(self):
        for reason in ("settled_turn_model_failure", "normal_control_model_invalid", "reach_model_failure"):
            with self.subTest(reason=reason), self.assertRaisesRegex(InfrastructureError, reason):
                self.eligibility([json.dumps({"component": "motion_safety", "reason": reason})])

    def test_ordinary_task_failure_and_empty_failure_list_remain_eligible(self):
        for messages in ([], ["ordinary navigation failure"],
                         [json.dumps({"component": "motion_safety", "epoch": EPOCH, "reason": "contact"})],
                         [json.dumps({"component": "other", "reason": "normal_control_model_invalid"})]):
            with self.subTest(messages=messages):
                self.assertTrue(self.eligibility(messages)["training_eligible"])

    def test_foreign_closed_summary_cannot_supply_the_current_epoch(self):
        with self.assertRaisesRegex(InfrastructureError, "eligibility receipt"):
            self.eligibility([], summary_epoch="other-closed-episode")

    def test_entire_round_is_reaped_and_rejected_before_targets_or_optimizer(self):
        environments = [collection.ReceiptEnv([
            {"reward": .2}, {"reward": -20., "terminated": True,
                             "reason": "navigation_failure", "dt": .22, "physical_dt": .24}],
            epoch=EPOCH, native_failures=[json.dumps(fault())]),
            collection.ReceiptEnv([{"terminated": True}], epoch="healthy-artificial-peer")]
        journal = {}
        model = SimpleNamespace(train=Mock())
        actual_check = ppo.closed_episode_training_eligibility

        def check_after_close(directory, epoch):
            self.assertEqual([env.closed for env in environments], [1, 1])
            return actual_check(directory, epoch)

        with patch.object(ppo, "infer", side_effect=collection.fixture_infer), \
                patch.object(ppo, "next_value", return_value=.25), \
                patch.object(ppo, "closed_episode_training_eligibility", side_effect=check_after_close), \
                patch.object(ppo, "build_rollout_buffer") as targets, \
                self.assertRaisesRegex(InfrastructureError, "reach runtime fault"):
            episodes, _ = ppo.collect_episodes(model, environments, collection.tasks_for(environments),
                deadline=time.monotonic() + 60., journal=journal)
            # The real PPO caller likewise builds targets/trains only after
            # collect_episodes returns. These unreachable calls guard that edge.
            ppo.build_rollout_buffer(episodes)
            model.train()
        targets.assert_not_called()
        model.train.assert_not_called()
        self.assertEqual([env.closed for env in environments], [1, 1])
        self.assertEqual([len(rows) for rows in journal["episodes"]], [2, 1])
        terminal = journal["episodes"][0][-1]
        self.assertEqual((terminal.reward, terminal.dt, terminal.next_value), (-20., .22, 0.))
        self.assertTrue(terminal.terminated)
        self.assertFalse(terminal.truncated)
        self.assertIn("infrastructure_error", journal["summaries"][0])


if __name__ == "__main__":
    unittest.main()
