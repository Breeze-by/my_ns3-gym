"""Unexecuted artificial resource/qualification fixtures; never native credit.

Apply reset-v2 plus this incremental candidate before root's source-sealed CPU
run. All amounts below are deliberately synthetic, not a proposed real block.
Qualification source/Git and liveness are stubbed exactly as the existing
bookkeeping fixture. PPO stops before directory/model/GPU/native side effects.
"""
import contextlib
import copy
import hashlib
import json
import io
from pathlib import Path
import unittest
from unittest.mock import patch

from mr3_learning import ppo, reach_gates, reach_preparation as prep
from mr3_learning.initial_encoder_replay import PROFILE as ACTUATION_PROFILE
from mr3_learning.tests import test_reach_qualification as bookkeeping
from mr3_learning.tests import test_reach_training_admission as training

FREEZE = "a" * 40


class AdmissionBoundaryReached(Exception):
    pass


class EngineeringBlockTests(unittest.TestCase):
    def setUp(self):
        self.fixture = bookkeeping.ReachQualificationTests(
            methodName="test_new_plan_keeps_thirty_scientific_roles_and_twelve_episodes")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root, self.plan_path = self.fixture.root, self.fixture.plan_path
        self.ledger = self.root / "toy_previous_accounting.json"
        self.ledger.write_text(json.dumps({"passed": True, "engineering_cumulative_seconds": "100",
                                           "fixture_only": True}) + "\n")
        self.resource_path = self.root / "toy_resource.json"
        self.value = {"schema": prep.AUTONOMOUS_RESOURCE_SCHEMA, "decision_maker": "agent",
            "authority_basis": "user-autonomous-continuation", "numeric_user_approval_claimed": False,
            "previous_accounting": self.spec(self.ledger), "engineering_used_seconds": "100",
            "engineering_ceiling_seconds": "40100", "engineering_remaining_seconds": "40000",
            "matrix_wall_seconds": "30000", "stage_wall_seconds": dict(zip(prep.primitives.STAGES,
                ("3000", "1500", "10000", "15500"))),
            "native_wall_seconds": dict(zip(prep.primitives.STAGES, ("2500", "1000", "8500", "14000"))),
            "close_reserve_seconds": "120", "preflight_wall_seconds": "120",
            "minimum_wall_seconds": "1800", "external_wall_seconds": "300",
            "total_reservation_seconds": "32220"}
        self.seal(self.value)

    def spec(self, path):
        raw = path.read_bytes()
        return {"path": str(path.relative_to(prep.WORKSPACE)),
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}

    def seal(self, value):
        self.resource_path.write_text(json.dumps(value) + "\n")
        return self.spec(self.resource_path)

    def kwargs(self):
        return dict(plan_path=self.plan_path, output_directory=self.root / "execution",
            run_root=self.root / "native", custody_binding=self.root / "binding.json",
            binary_proof=self.root / "binary.json", preflight=self.root / "preflight.json")

    def build(self, *, actuation_profile=None):
        return prep.build_plan(**self.kwargs(), engineering_remaining_seconds="40000",
            reservation_profile=prep.AUTONOMOUS_RESOURCE_PROFILE,
            engineering_resource=self.spec(self.resource_path), actuation_profile=actuation_profile)

    def test_default_and_old_bounded_plan_fields_remain_unchanged(self):
        original = prep.build_plan(**self.kwargs(), engineering_remaining_seconds="20000")
        self.assertEqual(original, self.fixture.plan)
        reservation = {"matrix_wall_seconds": "16000",
            "stage_wall_seconds": dict(zip(prep.primitives.STAGES, ("2300", "1000", "5800", "6900"))),
            "native_wall_seconds": dict(zip(prep.primitives.STAGES, ("1800", "750", "4800", "5900")))}
        bounded = prep.build_plan(**self.kwargs(), engineering_remaining_seconds="16500", reservation=reservation)
        expected = copy.deepcopy(original)
        expected["budget"].update(matrix_wall_seconds="16000", engineering_remaining_seconds="16500",
                                  reservation_profile=prep.BOUNDED_RESERVATION_PROFILE)
        for stage in expected["stages"]:
            stage["wall_seconds"] = reservation["stage_wall_seconds"][stage["stage"]]
            argv = stage["native"]["argv"]
            argv[argv.index("--work-wall-seconds") + 1] = reservation["native_wall_seconds"][stage["stage"]]
        self.assertEqual(bounded, expected)
        self.assertEqual(prep.PREPARATION_SHA256,
                         "850ab8947f711033f3f2fd17ef57d32098c02d569c1bea0f5cf58aaff8acd767")
        for old in (original, bounded):
            changed = copy.deepcopy(old)
            changed["engineering_resource"] = self.spec(self.resource_path)
            with self.assertRaisesRegex(ValueError, "explicit autonomous profile"):
                prep.validate_plan(changed)
        with self.assertRaises(ValueError):
            prep.build_plan(**self.kwargs(), engineering_remaining_seconds="40000", reservation={
                key: self.value[key] for key in reservation})

    def test_explicit_new_profile_changes_only_resource_fields_and_binds_both_inputs(self):
        plan = self.build()
        self.assertIs(prep.validate_plan(plan), plan)
        result = prep.engineering_resource_budget(self.spec(self.resource_path))
        self.assertEqual(sum(s["expected_episodes"] for s in plan["stages"]), 12)
        self.assertEqual(sum(len(prep.primitives.roles(s)) for s in plan["stages"]), 30)
        self.assertEqual(plan["engineering_resource"], self.spec(self.resource_path))
        for key, value in result["budget"].items():
            self.assertEqual(plan["budget"][key], value)
        for path, expected in result["source_bindings"].items():
            self.assertEqual(plan["source_bindings"][path], expected)
        for stage in plan["stages"]:
            self.assertEqual(prep.argument(stage["native"]["argv"], "--close-reserve-seconds"), "120")

    def test_builder_does_not_infer_profile_or_accept_unknown_profile_or_wrong_balance(self):
        for profile in (True, "", "unknown"):
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                prep.build_plan(**self.kwargs(), engineering_remaining_seconds="40000",
                    reservation_profile=profile, engineering_resource=self.spec(self.resource_path))
        with self.assertRaises(ValueError):
            prep.build_plan(**self.kwargs(), engineering_remaining_seconds="40000",
                            engineering_resource=self.spec(self.resource_path))
        with self.assertRaises(ValueError):
            prep.build_plan(**self.kwargs(), engineering_remaining_seconds="40001",
                reservation_profile=prep.AUTONOMOUS_RESOURCE_PROFILE,
                engineering_resource=self.spec(self.resource_path))
        for profile in (None, True, "", "unknown", prep.BOUNDED_RESERVATION_PROFILE):
            plan = self.build()
            plan["budget"]["reservation_profile"] = profile
            with self.subTest(plan_profile=profile), self.assertRaises(ValueError):
                prep.validate_plan(plan)

    def test_all_resource_amounts_reject_boolean_nonfinite_or_invalid_values(self):
        keys = ("engineering_used_seconds", "engineering_ceiling_seconds", "engineering_remaining_seconds",
                "matrix_wall_seconds", "preflight_wall_seconds", "minimum_wall_seconds",
                "external_wall_seconds", "total_reservation_seconds", "close_reserve_seconds")
        for key in keys:
            for bad in (True, None, "NaN", "Infinity", "-1", "not-seconds"):
                value = copy.deepcopy(self.value)
                value[key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    prep.engineering_resource_budget(self.seal(value))
        for key in ("stage_wall_seconds", "native_wall_seconds"):
            for bad in (True, None, "NaN", "Infinity", "0"):
                value = copy.deepcopy(self.value)
                value[key]["reset"] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    prep.engineering_resource_budget(self.seal(value))

    def test_decision_previous_accounting_and_reservation_constraints_fail_closed(self):
        variants = []
        for key, bad in (("numeric_user_approval_claimed", True), ("decision_maker", "user"),
                         ("authority_basis", "undeclared"), ("schema", "unknown"),
                         ("engineering_used_seconds", "101"), ("engineering_remaining_seconds", "39999"),
                         ("total_reservation_seconds", "32219"), ("minimum_wall_seconds", "1801"),
                         ("close_reserve_seconds", "119"), ("matrix_wall_seconds", "29999")):
            value = copy.deepcopy(self.value)
            value[key] = bad
            variants.append(value)
        for key in ("stage_wall_seconds", "native_wall_seconds"):
            value = copy.deepcopy(self.value)
            value[key].pop("deadline")
            variants.append(value)
        for native in ("120", "10000"):
            value = copy.deepcopy(self.value)
            value["native_wall_seconds"]["reset"] = native
            variants.append(value)
        value = copy.deepcopy(self.value)
        value.update(engineering_ceiling_seconds="30100", engineering_remaining_seconds="30000")
        variants.append(value)
        for index, value in enumerate(variants):
            with self.subTest(variant=index), self.assertRaises(ValueError):
                prep.engineering_resource_budget(self.seal(value))

    def test_sha_size_path_duplicate_json_and_changed_previous_total_are_rejected(self):
        valid = self.spec(self.resource_path)
        for key, bad in (("sha256", "0" * 64), ("bytes", valid["bytes"] + 1),
                         ("path", "../outside.json"), ("bytes", True)):
            with self.subTest(key=key), self.assertRaises(ValueError):
                prep.engineering_resource_budget(dict(valid, **{key: bad}))
        self.resource_path.write_text('{"schema":"first","schema":"second"}\n')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            prep.engineering_resource_budget(self.spec(self.resource_path))
        self.ledger.write_text('{"passed":true,"engineering_cumulative_seconds":"101"}\n')
        value = copy.deepcopy(self.value)
        value["previous_accounting"] = self.spec(self.ledger)
        with self.assertRaisesRegex(ValueError, "previous closed accounting"):
            prep.engineering_resource_budget(self.seal(value))

    def test_plan_budget_stage_and_both_source_bindings_must_match_sealed_resource(self):
        plan = self.build()
        for key, value in (("approved_cumulative_engineering_seconds", "75000"),
                           ("approved_engineering_seconds", "40100"),
                           ("unknown", "40000"),
                           ("full_minimum_reservation_available_at_plan_entry", False)):
            changed = copy.deepcopy(plan)
            changed["budget"][key] = value
            with self.subTest(extra=key), self.assertRaisesRegex(ValueError, "approval fields"):
                prep.validate_plan(changed)
        for key in prep.engineering_resource_budget(plan["engineering_resource"])["budget"]:
            changed = copy.deepcopy(plan)
            changed["budget"][key] = "wrong"
            with self.subTest(key=key), self.assertRaises(ValueError):
                prep.validate_plan(changed)
        for path in (self.resource_path, self.ledger):
            changed = copy.deepcopy(plan)
            changed["source_bindings"].pop(str(path.relative_to(prep.WORKSPACE)))
            with self.subTest(source=path), self.assertRaises(ValueError):
                prep.validate_plan(changed)
        for target in ("stage", "native"):
            changed = copy.deepcopy(plan)
            stage = changed["stages"][2]
            if target == "stage":
                stage["wall_seconds"] = "10001"
            else:
                argv = stage["native"]["argv"]
                argv[argv.index("--work-wall-seconds") + 1] = "8501"
            with self.subTest(target=target), self.assertRaises(ValueError):
                prep.validate_plan(changed)

    def test_new_resource_profile_cannot_reduce_roles_episodes_steps_or_change_close(self):
        for fault in ("role", "episodes", "steps", "close", "schedule"):
            plan = self.build()
            stage = plan["stages"][2]
            if fault == "role":
                stage["audits"] = [j for j in stage["audits"] if j.get("role") != "runtime"]
            elif fault == "episodes":
                stage["expected_episodes"] -= 1
            else:
                flag, bad = {"steps": ("--steps", "31"), "close": ("--close-reserve-seconds", "121"),
                             "schedule": ("--schedule", "open:101")}[fault]
                stage["native"]["argv"][stage["native"]["argv"].index(flag) + 1] = bad
            with self.subTest(fault=fault), self.assertRaises(ValueError):
                prep.validate_plan(plan)

    def qualification_fixture(self, *, actuation_profile=None):
        if actuation_profile is not None:
            binding_path = self.kwargs()["custody_binding"]
            binding = json.loads(binding_path.read_text())
            binding["actuation_profile"] = actuation_profile
            bookkeeping.write(binding_path, binding)
        self.fixture.plan = self.build(actuation_profile=actuation_profile)
        if actuation_profile is not None:
            self.fixture.plan["policy_stages"] = {
                name: {"actuation_profile": actuation_profile, "fixture_only": True}
                for name in ("minimum", "pilot", "validation")}
        bookkeeping.write(self.plan_path, self.fixture.plan)
        self.fixture.evidence()
        if actuation_profile is not None:
            # Synthetic producer/supervisor metadata must declare the same
            # profile as the binding, native stages and policy registry.
            for stage in self.fixture.plan["stages"]:
                for path in Path(stage["run_directory"]).glob("worker*/episode*/metadata.json"):
                    for filename in ("metadata.json", "supervisor_metadata.json"):
                        current = path.parent / filename
                        metadata = json.loads(current.read_text())
                        metadata["actuation_profile"] = actuation_profile
                        bookkeeping.write(current, metadata)
        output = self.root / "toy_qualification.json"
        with patch.object(prep, "source_check", return_value={}), \
                patch.object(prep.primitives, "identity", return_value=None):
            result = prep.qualify(self.plan_path, FREEZE, self.fixture.outer, output)
            self.assertEqual(prep.validate_qualification(output, self.plan_path, FREEZE), result)
        self.assertEqual(result["mandatory_roles"], 30)
        self.assertEqual(len(result["episodes"]), 12)
        self.assertFalse(result["policy_reliability_credit"])
        return output

    def ppo_arguments(self, qualification):
        return ["--run-id", "toy-admission", "--safety-contract", "mr3-reach-v1",
                "--decisions", "2", "--episode-steps", "2", "--wall-seconds", "60",
                "--reach-plan", str(self.plan_path), "--reach-qualification", str(qualification),
                "--output-root", str(self.root / "not-created")]

    def ppo_guards(self, stack):
        owner = training.ReachTrainingAdmissionTests(
            methodName="test_missing_either_or_both_new_qualification_parameters_rejects_train_and_eval")
        guards = [stack.enter_context(item) for item in owner.guards()]
        stack.enter_context(patch.object(ppo.subprocess, "check_output", return_value=FREEZE))
        stack.enter_context(patch.object(prep, "source_check", return_value={}))
        stack.enter_context(patch.object(prep.primitives, "identity", return_value=None))
        return guards

    def test_stubbed_new_profile_roundtrip_reaches_only_the_first_ppo_side_effect_boundary(self):
        qualification = self.qualification_fixture(actuation_profile=ACTUATION_PROFILE)
        self.assertEqual(self.fixture.plan["actuation_profile"], ACTUATION_PROFILE)
        self.assertTrue(all(row["actuation_profile"] == ACTUATION_PROFILE
                            for row in self.fixture.plan["stages"]))
        self.assertTrue(all(row["actuation_profile"] == ACTUATION_PROFILE
                            for row in self.fixture.plan["policy_stages"].values()))
        marker = object()
        with patch.object(prep, "source_check", return_value={}), \
                patch.object(reach_gates, "_load_versioned_native_gates", return_value=marker) as leaf:
            self.assertIs(reach_gates.load_native_gates(prep.WORKSPACE, FREEZE, self.plan_path), marker)
            leaf.assert_called_once()
        with contextlib.ExitStack() as stack:
            guards = self.ppo_guards(stack)
            guards[0].side_effect = AdmissionBoundaryReached
            with self.assertRaises(AdmissionBoundaryReached):
                ppo.main(self.ppo_arguments(qualification))
            guards[0].assert_called_once()
            for guard in guards[1:]:
                guard.assert_not_called()

    def test_missing_or_wrong_actuation_profile_rejects_before_ppo_side_effects(self):
        for profile in (None, "unknown", "measured_joint_rim_paired_common_fraction_v1"):
            plan = {"seed_rule": "legacy", "start_graph_rule": "original-seed-cell"}
            if profile is not None:
                plan["actuation_profile"] = profile
            with self.subTest(profile=profile), contextlib.ExitStack() as stack:
                guards = self.ppo_guards(stack)
                guards[0].side_effect = AdmissionBoundaryReached
                stack.enter_context(patch.object(prep, "validate_qualification", return_value={"passed": True}))
                stack.enter_context(patch.object(prep, "load_plan", return_value=plan))
                stack.enter_context(contextlib.redirect_stderr(io.StringIO()))
                with self.assertRaises(SystemExit) as error:
                    ppo.main(self.ppo_arguments(self.root / "unread-profile-qualification.json"))
                self.assertEqual(error.exception.code, 2)
                for guard in guards:
                    guard.assert_not_called()

    def test_changed_resource_is_rejected_before_mkdir_model_native_or_gpu(self):
        qualification = self.qualification_fixture()
        changed = copy.deepcopy(self.fixture.plan)
        changed["budget"]["engineering_remaining_seconds"] = "40001"
        bookkeeping.write(self.plan_path, changed)
        with patch.object(prep, "source_check") as proof, \
                patch.object(reach_gates, "_load_versioned_native_gates") as leaf:
            with self.assertRaisesRegex(ValueError, "plan budget differs"):
                reach_gates.load_native_gates(prep.WORKSPACE, FREEZE, self.plan_path)
            proof.assert_not_called()
            leaf.assert_not_called()
        with contextlib.ExitStack() as stack:
            guards = self.ppo_guards(stack)
            with self.assertRaisesRegex(ValueError, "plan budget differs"):
                ppo.main(self.ppo_arguments(qualification))
            for guard in guards:
                guard.assert_not_called()


if __name__ == "__main__":
    unittest.main()
