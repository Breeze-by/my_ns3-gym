"""Mutated receipts must not certify an unacknowledged physics advance."""

import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from mr3_learning.audit_evaluator_phase import PROTOCOL, audit_episode


def fixture(terminal=False):
    worker, evaluator, physics = [], [], []
    for index, target in enumerate((1_000_000_000, 1_020_000_000, 1_040_000_000)):
        wall = 100 + index * 10
        request = {"epoch": "episode", "request_id": "phase" + str(index + 1),
                   "target_time_ns": target}
        final = ({"epoch": "episode", "end_sim_time_sec": 1.02,
                  "termination_reason": "navigation_failure"}
                 if terminal and index == 2 else None)
        ack = {"schema": PROTOCOL, **request, "ok": True, "evaluator_clock_ns": target,
               "status": "TERMINAL" if final else "LIVE", "terminal": final}

        def w(kind, offset, **payload):
            return {"epoch": "episode", "kind": kind, "wall_monotonic_ns": wall + offset,
                    "worker_clock_ns": target, "worker_physical_ns": target, **payload}

        def e(kind, offset, **payload):
            return {"epoch": "episode", "kind": kind, "wall_monotonic_ns": wall + offset,
                    "evaluator_clock_ns": target, **payload}

        worker.extend([w("request", 0, request=request), w("ack_received", 3, ack=ack),
                       w("ack_consumed", 4, ack=ack)])
        evaluator.extend([e("request_received", 1, request=request),
                          e("ack_published", 2, ack=ack)])
        if index < 2:
            worker.append(w("advance_permitted", 5, next_target_time_ns=target + 20_000_000))
            physics.append({"epoch": "episode", "ok": True, "paused": True, "steps": 20,
                            "step_ns": 1_000_000, "start_iterations": 1000 + index * 20,
                            "end_iterations": 1020 + index * 20, "start_time_ns": target,
                            "end_time_ns": target + 20_000_000})
    return {"metadata.json": {"epoch": "episode", "evaluator_phase_protocol": PROTOCOL},
            "evaluator_phase_worker.jsonl": worker,
            "evaluator_phase_evaluator.jsonl": evaluator, "physics.jsonl": physics,
            "transitions.jsonl": [
                {"kind": "reset", "info": {"release_time_ns": 1_000_000_000},
                 "snapshot": {"source_stamp": 1.}},
                {"kind": "step", "snapshot": {"source_stamp": 1.04}}],
            "episode.json": {"end_sim_time_sec": 1.02 if terminal else 1.04,
                             "termination_reason": "navigation_failure" if terminal else
                             "external_sampler_limit"}}


class PhaseReceiptTests(unittest.TestCase):
    def audit(self, data, compressed=False):
        with tempfile.TemporaryDirectory() as name:
            directory = Path(name)
            for filename, value in data.items():
                payload = ("".join(json.dumps(row) + "\n" for row in value)
                           if filename.endswith(".jsonl") else json.dumps(value)).encode()
                if compressed:
                    (directory / (filename + ".gz")).write_bytes(gzip.compress(payload))
                else:
                    (directory / filename).write_bytes(payload)
            return audit_episode(directory)

    def test_live_truncation_and_true_terminal_replay_plain_and_compressed(self):
        for terminal in (False, True):
            for compressed in (False, True):
                result = self.audit(fixture(terminal), compressed)
                self.assertTrue(result["passed"])
                self.assertEqual(result["initial_and_policy_acks"], 3)
                self.assertEqual(result["policy_quanta"], 2)

    def test_missing_duplicate_wrong_clock_epoch_and_advance_order_rejected(self):
        def drop_ack(data):
            data["evaluator_phase_worker.jsonl"].pop(2)

        def duplicate_consume(data):
            data["evaluator_phase_worker.jsonl"].insert(
                3, copy.deepcopy(data["evaluator_phase_worker.jsonl"][2]))

        def early_advance(data):
            data["evaluator_phase_worker.jsonl"][3]["wall_monotonic_ns"] = 103

        def wrong_eval_clock(data):
            data["evaluator_phase_evaluator.jsonl"][3]["ack"]["evaluator_clock_ns"] -= 20_000_000

        def wrong_epoch(data):
            data["evaluator_phase_worker.jsonl"][1]["epoch"] = "old"

        def wrong_physics(data):
            data["physics.jsonl"][0]["steps"] = 40

        def missing_quantum(data):
            data["physics.jsonl"].pop()

        def unbound_received(data):
            data["evaluator_phase_worker.jsonl"][1]["ack"]["request_id"] = "phase99"

        for mutate in (drop_ack, duplicate_consume, early_advance, wrong_eval_clock,
                       wrong_epoch, wrong_physics, missing_quantum, unbound_received):
            with self.subTest(mutation=mutate.__name__):
                data = copy.deepcopy(fixture())
                mutate(data)
                with self.assertRaises(ValueError):
                    self.audit(data)

    def test_backdated_terminal_extra_metrics_and_postterminal_advance_rejected(self):
        for mutate in ("backdated", "extra_fields", "premature", "different_reason"):
            with self.subTest(mutation=mutate):
                data = fixture(True)
                final = data["evaluator_phase_evaluator.jsonl"][-1]["ack"]["terminal"]
                if mutate == "backdated":
                    final["end_sim_time_sec"] = 1.
                    data["episode.json"]["end_sim_time_sec"] = 1.
                elif mutate == "extra_fields":
                    final["coverage"] = .99
                elif mutate == "premature":
                    ack = data["evaluator_phase_evaluator.jsonl"][1]["ack"]
                    ack.update(status="TERMINAL", terminal={**final, "end_sim_time_sec": 1.})
                else:
                    final["termination_reason"] = "coverage_reached"
                with self.assertRaises(ValueError):
                    self.audit(data)

    def test_ahead_or_regressed_evaluator_request_clock_rejected(self):
        for clock in (9_999_999_999, -1, True, 1_000_000_000):
            with self.subTest(clock=clock):
                data = fixture()
                data["evaluator_phase_evaluator.jsonl"][4]["evaluator_clock_ns"] = clock
                with self.assertRaises(ValueError):
                    self.audit(data)

    def test_immutable_stale_duplicate_is_ignored_without_extra_consumption(self):
        data = fixture()
        worker = data["evaluator_phase_worker.jsonl"]
        duplicate = copy.deepcopy(worker[1])
        duplicate.update(wall_monotonic_ns=116, worker_clock_ns=1_020_000_000,
                         worker_physical_ns=1_020_000_000)
        worker.insert(8, duplicate)
        self.assertTrue(self.audit(data)["passed"])
        duplicate["ack"]["status"] = "TERMINAL"
        with self.assertRaises(ValueError):
            self.audit(data)


if __name__ == "__main__":
    unittest.main()
