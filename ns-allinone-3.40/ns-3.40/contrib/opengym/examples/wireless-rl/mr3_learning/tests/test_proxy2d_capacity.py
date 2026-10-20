"""Counter/codec/persistence fixtures, without a simulator or policy."""
from concurrent.futures import ThreadPoolExecutor
import base64
import copy
import json
import os
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import zlib

import numpy as np

from mr3_learning.proxy2d_capacity import StepBudget, Trace
from mr3_learning.proxy2d_codec import canonical_bytes, decode_arrays, encode_arrays, tensor_proofs
from mr3_learning.proxy2d_process import pidfd_open, pidfd_send_signal


class CapacityFixtures(unittest.TestCase):
    def test_host_pidfd_can_observe_this_process_without_sending_a_mutating_signal(self):
        descriptor = pidfd_open(os.getpid())
        try:
            pidfd_send_signal(descriptor, 0)
        finally:
            os.close(descriptor)

    def test_one_shared_counter_is_atomic_across_four_collectors_and_counts_errors(self):
        budget = StepBudget(10**30, maximum=17)
        with ThreadPoolExecutor(max_workers=4) as executor:
            tickets = list(executor.map(lambda _: budget.reserve(), range(100)))
        self.assertEqual(sorted(t for t in tickets if t), list(range(1, 18)))
        budget.failed()
        self.assertFalse(budget.reserve())
        self.assertEqual(budget.attempts, 17)
        self.assertEqual(budget.errors, 1)

    def test_admission_reserves_time_for_existing_rpc_and_close_without_resetting_count(self):
        budget = StepBudget(100_000_000_000)
        with patch("mr3_learning.proxy2d_capacity.time.monotonic_ns", return_value=55_000_000_000):
            self.assertFalse(budget.reserve())
        self.assertEqual(budget.attempts, 0)

    def test_full_array_roundtrip_keeps_dtype_shape_and_bits_across_processes(self):
        values = {"grid": np.array([[-1, 0, 100]], dtype=np.int16),
                  "features": np.array([.1, -.2], dtype=np.float32),
                  "valid": np.array([True, False], dtype=bool)}
        decoded = decode_arrays(json.loads(canonical_bytes(encode_arrays(values))))
        self.assertEqual(tensor_proofs(decoded), tensor_proofs(values))

    def test_byte_length_dtype_and_array_extent_are_validated_before_use(self):
        encoded = encode_arrays(np.array([1, 2], dtype=np.int16))
        for change in ({"shape": [3]}, {"dtype": "O"}, {"shape": [2_000_001]}, {"shape": [True]},
                       {"data": base64.b64encode(b"x").decode()}):
            bad = {**encoded, **change}
            with self.assertRaises(ValueError):
                decode_arrays(bad)

    def test_nonfinite_cannot_be_delivered_or_hashed_as_a_tensor_claim(self):
        encoded = encode_arrays(np.array([np.inf], dtype=np.float32))
        with self.assertRaises(ValueError):
            decode_arrays(encoded)
        with self.assertRaises(ValueError):
            canonical_bytes({"state": float("nan")})

    def test_attempt_record_is_recoverable_before_the_environment_call_or_stream_close(self):
        with tempfile.TemporaryDirectory() as tmp:
            trace = Trace(Path(tmp), 0, 1, "fixture")
            trace.record("step_attempt", action=888, global_attempt=1)
            raw = (Path(tmp) / "trace.jsonl.gz").read_bytes()
            prefix = zlib.decompressobj(16 + zlib.MAX_WBITS).decompress(raw)
            self.assertEqual(json.loads(prefix)["event"], "step_attempt")
            trace.close()


if __name__ == "__main__":
    unittest.main()
