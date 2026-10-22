"""Admission/failed-closure fixtures; no World, scene or original consumer."""
from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from mr3_learning import proxy2d_seed_activity as activity


class SeedActivityTests(unittest.TestCase):
    def test_v2_has_separate_artifacts_and_keeps_the_same_bounded_workload(self):
        old = activity.settings()
        new = activity.settings("seed_probe_v2")
        self.assertEqual(old[3], "exact-point-bridge-v1")
        self.assertEqual(new[3], "exact-point-bridge-v2")
        self.assertTrue(all(old[index] != new[index] for index in (0, 1, 2)))
        first, second = activity.activity_spec("seed_probe"), activity.activity_spec("seed_probe_v2")
        self.assertEqual({key: value for key, value in first.items() if key != "kind"},
                         {key: value for key, value in second.items() if key != "kind"})
        self.assertLessEqual(Decimal(new[4]) + second["activity_seconds"], Decimal(52000))
        self.assertEqual(activity.kind_arguments("seed_probe"), [])
        self.assertEqual(activity.kind_arguments("seed_probe_v2"), ["--kind", "seed_probe_v2"])
        with self.assertRaises(ValueError):
            activity.settings("invented")

    def test_v2_nested_collection_and_description_keep_the_selected_kind(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); output = root / "run"
            plan_path = root / "plan.json"; plan_path.write_text("{}\n")
            commands = {}
            def phase(directory, name, command, maximum):
                commands[name] = command
                if name == "conformity":
                    (directory / "conformity.json").write_text("{}\n")
                return {"passed": True}
            config = (root, plan_path, output, "exact-point-bridge-v2", "47269.8043977356018")
            with patch.object(activity, "settings", return_value=config), \
                    patch.object(activity, "check", return_value={"source_bindings": {},
                        "activity_spec": activity.activity_spec("seed_probe_v2"), "native_manifest": {}}), \
                    patch.object(activity, "phase", side_effect=phase), \
                    patch.object(activity, "bindings", return_value={}):
                result = activity.execute("a" * 40, "seed_probe_v2")
            self.assertTrue(result["passed"])
            for name in ("collection", "description"):
                self.assertEqual(commands[name][-2:], ["--kind", "seed_probe_v2"])
            self.assertIn("exact-point-bridge-v2", commands["conformity"])
            context = json.loads((output / "collection_context.json").read_text())
            self.assertEqual(context["seed_rule"], "exact-point-bridge-v2")
            self.assertEqual(context["activity_spec"]["kind"], "seed_probe_v2")

    def test_description_cannot_apply_verified_prefix_to_changed_trace(self):
        for changed in (False, True):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as temporary:
                run = Path(temporary); episode = run / "episode"; episode.mkdir()
                snapshot = {"path_maps": {name: {"seed_rejection_reason": None,
                    "seed_point_bridge_certificate": None} for name in ("tb1", "tb2", "tb3")},
                    "per_robot_action_mask": [[False] * 8 + [True, True]] * 3, "robots": []}
                raw = gzip.compress((json.dumps({"event": "reset", "event_sequence": 1,
                    "snapshot": snapshot, "reward_diagnostics": {}}) + "\n").encode())
                (episode / "trace.jsonl.gz").write_bytes(raw)
                report = {"directory": str(episode), "bound_bytes_unchanged": True,
                    "validated_prefix_records": 1, "passed": True,
                    "trace_sha256": "0" * 64 if changed else hashlib.sha256(raw).hexdigest()}
                (run / "independent_audit.json").write_text(json.dumps({"passed": True, "episodes": [report]}))
                (run / "capacity_summary.json").write_text(json.dumps({"freeze": "a" * 40,
                    "groups": [{"episodes": [{"directory": str(episode), "scene": "artificial", "seed": 1}]}]}))
                with patch.object(activity, "OUTPUT", run):
                    result = activity.describe()
                self.assertEqual(result["passed"], not changed)
                self.assertEqual(result["episodes"][0]["raw_actor_records"], 1)
                self.assertEqual(result["episodes"][0]["verified_prefix_actor_records"], 0 if changed else 1)

    def test_total_reservation_fits_original_cap_and_explicit_activity(self):
        spec = activity.activity_spec("seed_probe")
        self.assertEqual(spec["steps_per_episode"], 64)
        self.assertEqual(spec["max_attempts"], 192)
        self.assertLessEqual(sum(activity.PHASES.values()) + 120 + 180, spec["activity_seconds"])
        self.assertLessEqual(Decimal(activity.ENTRY) + spec["activity_seconds"], Decimal(52000))

    def test_changed_native_source_preserves_failed_activity_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            plan = {"source_bindings": {}}
            def phase(directory, name, *unused, **kwargs):
                if name == "conformity":
                    (directory / "conformity.json").write_text("{}\n")
                return {"passed": True}
            with patch.object(activity, "OUTPUT", run), patch.object(activity, "PLAN", Path(__file__)), \
                    patch.object(activity, "check", return_value=plan), \
                    patch.object(activity, "phase", side_effect=phase), \
                    patch.object(activity, "bindings", side_effect=ValueError("native source changed")):
                result = activity.execute("a" * 40)
            self.assertFalse(result["passed"])
            self.assertFalse(result["source_unchanged"])
            self.assertIn("native source changed", str(result["errors"]))
            self.assertEqual(json.loads((run / "activity_result.json").read_text()), result)

    def test_missing_activity_result_retains_external_failure_and_saved_identity_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"; run.mkdir()
            plan = root / "plan.json"; plan.write_text('{"source_bindings": {}}\n')
            identity = {"pid": 999999, "parent": 1, "group": 999999, "session": 999999, "start_ticks": 10}
            outer = root / "outer.json"
            outer.write_text(json.dumps({"child_identity": identity, "started_monotonic_ns": time.monotonic_ns(),
                                         "passed": True}) + "\n")
            start = {"freeze": "a" * 40, "coordinator_identity": identity, "plan_sha256": activity.sha(plan)}
            (run / "activity_start.json").write_text(json.dumps(start) + "\n")
            output = root / "external_final.json"
            with patch.object(activity, "OUTPUT", run), patch.object(activity, "PLAN", plan), \
                    patch.object(activity, "_outer"), patch.object(activity, "_absence") as absence:
                result = activity.final(outer, output)
            self.assertFalse(result["passed"])
            self.assertFalse(result["activity_passed"])
            self.assertTrue(result["errors"])
            absence.assert_called_once_with(identity)
            self.assertEqual(json.loads(output.read_text()), result)


if __name__ == "__main__":
    unittest.main()
