"""Artificial activity admission; no World, external evidence, native or policy."""
from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import proxy2d_seed_activity as a


class PointGraphActivityTests(unittest.TestCase):
    def test_profile_and_probe_reservations_are_distinct_and_fit_approved_cap(self):
        configs = [a.settings(kind) for kind in a.POINT_KINDS]
        self.assertNotEqual(configs[0][1], configs[1][1])
        self.assertNotEqual(configs[0][2], configs[1][2])
        self.assertEqual([a.activity_spec(kind)["max_attempts"] for kind in a.POINT_KINDS], [8, 192])
        self.assertEqual([a.activity_spec(kind)["activity_seconds"] for kind in a.POINT_KINDS], [600, 1800])
        self.assertLessEqual(Decimal(configs[0][4]) + 2400, Decimal(52000))
        self.assertLessEqual(sum(a.phase_limits(a.POINT_KINDS[0]).values()) + 120 + 180, 600)
        self.assertLessEqual(sum(a.phase_limits(a.POINT_KINDS[1]).values()) + 120 + 180, 1800)

    def test_new_phase_wiring_has_exact_pair_and_profile_enabled_branch(self):
        for kind in a.POINT_KINDS:
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); output = root / "run"; plan_path = root / "plan.json"
                plan_path.write_text("{}")
                commands = {}
                def phase(directory, name, command, maximum):
                    commands[name] = command
                    if name == "conformity":
                        (directory / "conformity.json").write_text("{}")
                    return {"passed": True}
                config = (root, plan_path, output, "exact-point-bridge-v2", "47739.5359129776018")
                plan = {"source_bindings": {}, "activity_spec": a.activity_spec(kind), "native_manifest": {}}
                with patch.object(a, "settings", return_value=config), patch.object(a, "check", return_value=plan), \
                        patch.object(a, "bindings", return_value={}), patch.object(a, "phase", side_effect=phase), \
                        patch.object(a, "point_profile_admission", return_value={"passed": True}) as admission:
                    result = a.execute("a" * 40, kind)
                self.assertTrue(result["passed"])
                self.assertEqual(commands["conformity"][-2:], ["--start-graph-rule", a.POINT_START])
                self.assertEqual(set(result["phases"]), set(a.phase_limits(kind)))
                context = json.loads((output / "collection_context.json").read_text())
                self.assertEqual(context["start_graph_rule"], a.POINT_START)
                self.assertEqual(context["group_wall_seconds"], a.group_limits(kind))
                self.assertEqual(admission.call_count, kind == "point_graph_probe_v1")

    def test_failed_profile_admission_never_creates_probe_or_launches_child(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); output = root / "run"
            config = (root, root / "plan.json", output, "exact-point-bridge-v2", "47739.5359129776018")
            with patch.object(a, "settings", return_value=config), patch.object(a, "check", return_value={}), \
                    patch.object(a, "point_profile_admission", side_effect=ValueError("profile not closed")), \
                    patch.object(a, "phase") as phase:
                with self.assertRaisesRegex(ValueError, "profile not closed"):
                    a.execute("a" * 40, "point_graph_probe_v1")
            self.assertFalse(output.exists())
            phase.assert_not_called()

    def test_scope_requires_combined_reservation_even_for_profile_only(self):
        for kind in a.POINT_KINDS:
            with self.subTest(kind=kind), patch.object(a, "specification", return_value={
                    "activity_spec": a.activity_spec(kind), "combined_reservation_seconds": 2400}), \
                    patch.object(a, "settings", return_value=(Path("."), Path("plan"), Path("out"), "exact-point-bridge-v2", "50000")), \
                    patch.object(a, "exclusive") as write:
                with self.assertRaises(ValueError): a.build(kind)
                write.assert_not_called()


if __name__ == "__main__":
    unittest.main()
