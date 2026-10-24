"""Prospective wall reservations with the full original qualification workload.

Only artificial plan JSON and the real arithmetic allocator are exercised;
these fixtures never execute the native dispatcher or scientific consumers.
"""
import copy
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import reach_preparation as prep


RESERVATION = {
    "matrix_wall_seconds": "16000",
    "stage_wall_seconds": dict(zip(prep.primitives.STAGES, ("2300", "1000", "5800", "6900"))),
    "native_wall_seconds": dict(zip(prep.primitives.STAGES, ("1800", "750", "4800", "5900"))),
}


class ReachReservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix=".mr3-reservation-cpu-", dir=prep.WORKSPACE)
        cls.root = Path(cls.temporary.name)
        binding = cls.root / "binding.json"
        binding.write_text('{"source_bindings": [], "binaries": {}}\n')
        cls.kwargs = dict(plan_path=cls.root / "plan.json", output_directory=cls.root / "execution",
            run_root=cls.root / "native", custody_binding=binding, binary_proof=cls.root / "binary.json",
            preflight=cls.root / "preflight.json")
        cls.original = prep.build_plan(**cls.kwargs, engineering_remaining_seconds="20000")
        with patch.object(prep.primitives, "build_plan", wraps=prep.primitives.build_plan) as builder:
            cls.bounded = prep.build_plan(**cls.kwargs, engineering_remaining_seconds="16500",
                                          reservation=copy.deepcopy(RESERVATION))
        cls.actual_builder_balance = builder.call_args.kwargs["engineering_remaining_seconds"]

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def test_builder_preserves_actual_balance_and_changes_only_explicit_reservations(self):
        self.assertEqual(self.actual_builder_balance, "16500")
        expected = copy.deepcopy(self.original)
        expected["budget"].update(matrix_wall_seconds="16000", engineering_remaining_seconds="16500",
                                  reservation_profile=prep.BOUNDED_RESERVATION_PROFILE)
        for stage in expected["stages"]:
            name = stage["stage"]
            stage["wall_seconds"] = RESERVATION["stage_wall_seconds"][name]
            argv = stage["native"]["argv"]
            argv[argv.index("--work-wall-seconds") + 1] = RESERVATION["native_wall_seconds"][name]
        self.assertEqual(self.bounded, expected)
        self.assertIs(prep.validate_plan(self.bounded), self.bounded)
        self.assertEqual(sum(stage["expected_episodes"] for stage in self.bounded["stages"]), 12)
        self.assertEqual(sum(len(prep.primitives.roles(stage)) for stage in self.bounded["stages"]), 30)

    def test_default_retains_exact_original_matrix_stage_and_native_allocations(self):
        self.assertNotIn("reservation_profile", self.original["budget"])
        self.assertEqual(self.original["budget"]["matrix_wall_seconds"], "18000")
        self.assertEqual(tuple(stage["wall_seconds"] for stage in self.original["stages"]), prep.CAPS)
        self.assertEqual(tuple(prep.argument(stage["native"]["argv"], "--work-wall-seconds")
                               for stage in self.original["stages"]), prep.NATIVE_CAPS)
        for fault in ("matrix", "stage", "native", "balance"):
            plan = copy.deepcopy(self.original)
            if fault == "matrix":
                plan["budget"]["matrix_wall_seconds"] = "17999"
            elif fault == "stage":
                plan["stages"][0]["wall_seconds"] = "2399"
            elif fault == "native":
                argv = plan["stages"][0]["native"]["argv"]
                argv[argv.index("--work-wall-seconds") + 1] = "1899"
            else:
                plan["budget"]["engineering_remaining_seconds"] = "17999"
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                prep.validate_plan(plan)

    def test_unknown_or_null_profile_cannot_opt_into_changed_allocations(self):
        for value in (None, True, "", "bounded-original-workload-v2"):
            plan = copy.deepcopy(self.bounded)
            plan["budget"]["reservation_profile"] = value
            with self.subTest(profile=value), self.assertRaisesRegex(ValueError, "unknown reservation profile"):
                prep.validate_plan(plan)
        plan = copy.deepcopy(self.bounded)
        del plan["budget"]["reservation_profile"]
        with self.assertRaises(ValueError):
            prep.validate_plan(plan)

    def test_all_reservations_and_actual_balance_must_be_finite_positive_nonboolean(self):
        invalid = ("NaN", "sNaN", "Infinity", "-Infinity", float("nan"), float("inf"),
                   "0", "-1", True, None, "not-seconds")
        for field in ("matrix", "stage", "native", "balance"):
            for value in invalid:
                plan = copy.deepcopy(self.bounded)
                if field == "matrix":
                    plan["budget"]["matrix_wall_seconds"] = value
                elif field == "stage":
                    plan["stages"][0]["wall_seconds"] = value
                elif field == "native":
                    argv = plan["stages"][0]["native"]["argv"]
                    argv[argv.index("--work-wall-seconds") + 1] = value
                else:
                    plan["budget"]["engineering_remaining_seconds"] = value
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    prep.validate_plan(plan)
        for value in ("NaN", "Infinity", float("inf")):
            plan = copy.deepcopy(self.original)
            plan["budget"]["engineering_remaining_seconds"] = value
            with self.subTest(default_balance=value), self.assertRaises(ValueError):
                prep.validate_plan(plan)

    def test_original_ceilings_and_closure_consumer_reserves_cannot_be_exceeded(self):
        for fault in ("matrix_cap", "matrix_balance", "stage_sum", "stage_cap", "native_cap",
                      "native_close_equal", "native_close_below", "native_stage_equal", "close_changed",
                      "carry_disabled"):
            plan = copy.deepcopy(self.bounded)
            argv = plan["stages"][0]["native"]["argv"]
            if fault == "matrix_cap":
                plan["budget"].update(matrix_wall_seconds="18001", engineering_remaining_seconds="20000")
            elif fault == "matrix_balance":
                plan["budget"]["engineering_remaining_seconds"] = "15999"
            elif fault == "stage_sum":
                plan["budget"]["matrix_wall_seconds"] = "15999"
            elif fault == "stage_cap":
                plan["stages"][0]["wall_seconds"] = "2401"
            elif fault == "native_cap":
                argv[argv.index("--work-wall-seconds") + 1] = "1901"
            elif fault.startswith("native_close"):
                argv[argv.index("--work-wall-seconds") + 1] = "120" if fault.endswith("equal") else "119"
            elif fault == "native_stage_equal":
                plan["stages"][0]["wall_seconds"] = "1800"
            elif fault == "close_changed":
                argv[argv.index("--close-reserve-seconds") + 1] = "119"
            else:
                plan["budget"]["borrow_unused_prior_stage_reservations"] = False
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                prep.validate_plan(plan)

    def test_builder_rejects_invalid_or_incomplete_reservations_before_primitive_io(self):
        invalid = []
        for key in RESERVATION:
            value = copy.deepcopy(RESERVATION)
            value.pop(key)
            invalid.append(value)
        value = copy.deepcopy(RESERVATION)
        value["extra"] = "ignored"
        invalid.append(value)
        for field in ("stage_wall_seconds", "native_wall_seconds"):
            for fault in ("missing", "extra", "sequence"):
                value = copy.deepcopy(RESERVATION)
                if fault == "missing":
                    value[field].pop("deadline")
                elif fault == "extra":
                    value[field]["optional"] = "1"
                else:
                    value[field] = list(value[field].values())
                invalid.append(value)
        value = copy.deepcopy(RESERVATION)
        value["matrix_wall_seconds"] = "Infinity"
        invalid.append(value)
        value = copy.deepcopy(RESERVATION)
        value["matrix_wall_seconds"] = "16501"
        invalid.append(value)
        for reservation in invalid:
            with self.subTest(reservation=reservation), patch.object(prep.primitives, "build_plan") as builder:
                with self.assertRaises(ValueError):
                    prep.build_plan(plan_path="unused.json", engineering_remaining_seconds="16500",
                                    reservation=reservation)
                builder.assert_not_called()

    def test_reduced_episodes_roles_steps_workers_or_schedule_still_reject(self):
        for fault in ("episodes", "role", "steps", "workers", "schedule", "safety", "physics_consumer"):
            plan = copy.deepcopy(self.bounded)
            stage = plan["stages"][2]
            argv = stage["native"]["argv"]
            if fault == "episodes":
                stage["expected_episodes"] = 7
            elif fault == "role":
                stage["audits"] = [job for job in stage["audits"] if job.get("role") != "runtime"]
            elif fault == "steps":
                argv[argv.index("--steps") + 1] = "31"
            elif fault == "workers":
                argv[argv.index("--workers") + 1] = "1"
            elif fault == "schedule":
                argv[argv.index("--schedule") + 1] = "open:101,open:101,rooms:101"
            elif fault == "safety":
                argv[argv.index("--safety-contract") + 1] = "legacy"
            else:
                job = next(job for job in stage["audits"] if job.get("role") == "physics")
                job["argv"][1] = "/artificial/always_pass.py"
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                prep.validate_plan(plan)

    def test_real_forward_allocator_carries_only_spent_prior_savings_and_preserves_future_and_close(self):
        allocation = prep.primitives.borrowed_stage_budget(self.bounded, 1, 1000 * 10**9)
        self.assertEqual(allocation["unused_prior_reservations_ns"], 1300 * 10**9)
        self.assertEqual(allocation["future_base_reservations_ns"], 12700 * 10**9)
        self.assertEqual(allocation["stage_remaining_ns"], 2300 * 10**9)
        self.assertEqual(allocation["stage_cumulative_deadline_from_matrix_entry_ns"], 3300 * 10**9)
        self.assertEqual(allocation["native_allocation_ns"], 2050 * 10**9)
        self.assertEqual(allocation["base_consumer_reserve_ns"], 250 * 10**9)
        self.assertEqual(allocation["close_reserve_ns"], 120 * 10**9)
        self.assertTrue(allocation["native_admission_possible"])
        job = prep.primitives.budgeted_native_job(self.bounded["stages"][1]["native"], allocation)
        self.assertEqual(Decimal(prep.argument(job["argv"], "--work-wall-seconds")), Decimal("2050"))
        self.assertEqual(prep.argument(job["argv"], "--close-reserve-seconds"), "120")
        self.assertEqual(prep.argument(self.bounded["stages"][1]["native"]["argv"], "--work-wall-seconds"), "750")

    def test_real_allocator_does_not_borrow_future_or_admit_native_without_its_reserves(self):
        allocation = prep.primitives.borrowed_stage_budget(self.bounded, 1, 3270 * 10**9)
        self.assertEqual(allocation["unused_prior_reservations_ns"], 0)
        self.assertEqual(allocation["future_base_reservations_ns"], 12700 * 10**9)
        self.assertEqual(allocation["stage_remaining_ns"], 30 * 10**9)
        self.assertEqual(allocation["native_allocation_ns"], 0)
        self.assertEqual(allocation["close_reserve_ns"], 120 * 10**9)
        self.assertFalse(allocation["native_admission_possible"])
        with self.assertRaisesRegex(ValueError, "above close reserve"):
            prep.primitives.budgeted_native_job(self.bounded["stages"][1]["native"], allocation)


if __name__ == "__main__":
    unittest.main()
