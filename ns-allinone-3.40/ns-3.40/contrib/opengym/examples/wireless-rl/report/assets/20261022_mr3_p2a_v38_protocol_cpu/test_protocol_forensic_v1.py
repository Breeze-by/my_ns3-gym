"""Stdlib artificial rows only; never read the fixed original protocol input."""
import copy
import gzip
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("mr3_v38_protocol_fixture", Path(__file__).with_name("protocol_forensic_v1.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def delivery(clock, generated, *, received=None, stream="heartbeat", source="tb3", goal="tb3:53", sequence=1):
    goal = module.EPOCH + ":" + goal if goal in module.GOAL_SUFFIXES else goal
    return {"kind": "proxy_delivery", "epoch": module.EPOCH, "clock_ns": clock,
        "envelope": {"epoch": module.EPOCH, "stream": stream, "source": source,
            "sequence": sequence, "version": sequence, "source_stamp": generated,
            "generated_stamp": generated, "received_stamp": clock / 10**9 if received is None else received,
            "payload": {"goal_id": goal}}}


def event(clock, kind="send_goal", goal="tb3:53"):
    goal = module.EPOCH + ":" + goal if goal in module.GOAL_SUFFIXES else goal
    return {"kind": "dispatcher_event", "epoch": module.EPOCH, "clock_ns": clock,
        "event": {"epoch": module.EPOCH, "type": kind, "robot": "tb3", "goal_id": goal,
                  "stamp": clock / 10**9, "reason": "artificial"}}


def encode(rows):
    body = b"".join(json.dumps(row, sort_keys=True).encode() + b"\n" for row in rows)
    return gzip.compress(body, mtime=0), body


def extract(rows):
    raw, body = encode(rows)
    return module.extract_protocol(raw, expected_sha256=module.sha(raw), expected_bytes=len(raw)), raw, body


class ProtocolForensicFixtures(unittest.TestCase):
    def test_fixed_goal_full_prefix_and_closed_integer_clock_window(self):
        rows = [event(1_000_000_000, goal="tb3:46"),
                delivery(52_099_999_999, 51.9, goal="unselected"),
                delivery(52_100_000_000, 52.1, source="tb1", goal="tb1:53"),
                delivery(54_300_000_000, 54.1, source="tb2", goal="tb2:51"),
                delivery(54_300_000_001, 54.3, source="tb1", goal="unselected")]
        result, _, body = extract(rows)
        index = result["selection_index"]
        self.assertEqual(index["reliable_deliveries_in_window"], [3, 4])
        self.assertEqual(index["fixed_goal_history"][module.EPOCH + ":tb3:46"], [1])
        self.assertEqual(index["fixed_goal_history"][module.EPOCH + ":tb1:53"], [3])
        self.assertEqual(index["fixed_goal_history"][module.EPOCH + ":tb2:51"], [4])
        self.assertEqual(result["decoded_bytes"], len(body))
        self.assertEqual(result["parsed_rows"], 5)

    def test_raw_line_exact_sha_and_original_json_preserved(self):
        rows = [event(52_100_000_000, "protocol_failure")]
        result, _, body = extract(rows)
        entry = result["selected_rows"][0]
        self.assertEqual(entry["raw_line"].encode(), body)
        self.assertEqual(entry["raw_line_sha256"], module.sha(body))
        self.assertEqual(entry["record"], rows[0])
        self.assertEqual(entry["line_1based"], 1)

    def test_late_queued_heartbeat_does_not_turn_receipt_gap_into_generation_gap(self):
        rows = [delivery(52_000_000_000, 51.9), delivery(54_100_000_000, 52.1, sequence=2)]
        result, _, _ = extract(rows)
        late = next(row for row in result["selected_rows"] if row["line_1based"] == 2)["delivery_timing"]
        self.assertEqual(late["received_minus_generated_seconds"], "2.0")
        self.assertEqual(late["generated_gap_from_previous_actual_delivery_seconds"], "0.2")
        self.assertEqual(late["received_gap_from_previous_actual_delivery_seconds"], "2.1")
        self.assertIn("heartbeat_generated_before_its_recorded_receipt", late["labels"])
        self.assertEqual(result["selection_index"]["last_delivery_strictly_before"][0]["line_1based"], 1)

    def test_last_before_is_per_stream_source_and_strict_at_cut(self):
        rows = [delivery(53_900_000_000, 53.9, stream="command", source="tb1", goal="unselected"),
                delivery(54_000_000_000, 54., stream="heartbeat", source="tb2", goal="unselected"),
                delivery(54_100_000_000, 54.1, stream="command", source="tb1", goal="unselected")]
        result, _, _ = extract(rows)
        last = {(row["stream"], row["source"]): row["line_1based"]
                for row in result["selection_index"]["last_delivery_strictly_before"]}
        self.assertEqual(last, {("command", "tb1"): 1, ("heartbeat", "tb2"): 2})

    def test_first_failure_is_full_prefix_not_replaced_by_window_failure(self):
        rows = [event(2_000_000_000, "protocol_failure", goal="unselected"),
                event(54_100_000_000, "protocol_failure")]
        result, _, _ = extract(rows)
        self.assertEqual(result["selection_index"]["first_protocol_failure"], 1)
        self.assertIn("first_recorded_protocol_failure_in_full_epoch_prefix", result["selected_rows"][0]["selection_labels"])

    def test_wrong_compressed_hash_refuses_before_decompression(self):
        raw, _ = encode([event(1)])
        with patch.object(module.gzip, "GzipFile", side_effect=AssertionError("decode forbidden")):
            with self.assertRaisesRegex(ValueError, "SHA/bytes"):
                module.extract_protocol(raw, expected_sha256="0" * 64, expected_bytes=len(raw))

    def test_epoch_rejection_covers_unselected_prefix_and_nested_envelope(self):
        for nested in (False, True):
            rows = [delivery(1_000_000_000, 1., goal="unselected")]
            rows[0]["envelope" if nested else "epoch"] = ({**rows[0]["envelope"], "epoch": "wrong"}
                                                           if nested else "wrong")
            with self.subTest(nested=nested), self.assertRaises(ValueError):
                extract(rows)

    def test_one_decompression_and_no_fixture_mutation(self):
        rows = [delivery(52_100_000_000, 52.1), event(54_100_000_000, "protocol_failure")]
        before = copy.deepcopy(rows)
        raw, _ = encode(rows)
        original = module.gzip.GzipFile
        with patch.object(module.gzip, "GzipFile", wraps=original) as decompressor:
            result = module.extract_protocol(raw, expected_sha256=module.sha(raw), expected_bytes=len(raw))
        self.assertEqual(decompressor.call_count, 1)
        self.assertEqual(result["decompression_passes"], 1)
        self.assertEqual(rows, before)

    def test_row_and_decoded_byte_limits_do_not_decode_replacement(self):
        raw, _ = encode([event(1), event(2)])
        for field, value in (("MAX_ROWS", 1), ("MAX_DECODED_BYTES", 10)):
            with self.subTest(field=field), patch.object(module, field, value):
                with self.assertRaisesRegex(ValueError, "limit exceeded"):
                    module.extract_protocol(raw, expected_sha256=module.sha(raw), expected_bytes=len(raw))

    def test_inventory_requires_exact_single_canonical_binding(self):
        entry = {"canonical": "fixed/protocol.jsonl.gz", "sha256": "a" * 64, "bytes": 23}
        inventory = {"schema": "mr3-closed-byte-inventory-v1", "files": [entry]}
        self.assertEqual(module.check_inventory(inventory, entry["canonical"], entry["sha256"], 23), entry)
        for files in ([], [entry, entry], [{**entry, "bytes": 24}]):
            with self.subTest(files=files), self.assertRaises(ValueError):
                module.check_inventory({**inventory, "files": files}, entry["canonical"], entry["sha256"], 23)

    def test_exclusive_output_precedes_any_evidence_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.json"
            output.write_bytes(b"retain old failure\n")
            with patch.object(module, "inspect_fixed_protocol") as inspect:
                with self.assertRaises(FileExistsError):
                    module.main(["--source-freeze", "a" * 40, "--output", str(output)])
            inspect.assert_not_called()
            self.assertEqual(output.read_bytes(), b"retain old failure\n")

    def test_main_failure_keeps_self_identity_and_no_qualification(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "result.json"
            with patch.object(module, "inspect_fixed_protocol", side_effect=ValueError("artificial refusal")):
                with self.assertRaisesRegex(ValueError, "artificial refusal"):
                    module.main(["--source-freeze", "a" * 40, "--output", str(output)])
            result = json.loads(output.read_bytes())
            self.assertEqual(result["identity"], module.identity())
            self.assertFalse(result["source_stable"])
            self.assertFalse(result["qualification"])
            self.assertIn("artificial refusal", result["error"])


if __name__ == "__main__":
    unittest.main()
