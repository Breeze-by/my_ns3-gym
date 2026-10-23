"""CPU-only dispatch/admission/conjunction attacks; synthetic PASS is not credit."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import audit_ppo as original
from mr3_learning import audit_reach_ppo as entry


FREEZE = "a"*40


def digest(raw): return hashlib.sha256(raw).hexdigest()


class ReachPPOAuditTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        qualification, plan = root/"qualification.json", root/"plan.json"
        qualification.write_text('{"fixture":"validator is independently mocked"}')
        relative = Path(entry.__file__).resolve().relative_to(entry.WORKSPACE)
        plan.write_text(json.dumps({"source_bindings": {str(relative): digest(Path(entry.__file__).read_bytes())}}))
        metadata = {"freeze": FREEZE, "safety_contract": entry.CONTRACT,
                    "reach_plan": str(plan), "reach_qualification": str(qualification),
                    "reach_plan_sha256": digest(plan.read_bytes()),
                    "reach_qualification_sha256": digest(qualification.read_bytes())}
        (root/"metadata.json").write_text(json.dumps(metadata))
        (root/"summary.json").write_text(json.dumps({"freeze": FREEZE, "safety_contract": entry.CONTRACT}))
        native = root/"native/round0001/worker0/episode001_open_101"; native.mkdir(parents=True)
        (native/"metadata.json").write_text(json.dumps({"freeze": FREEZE, "safety_contract": entry.CONTRACT,
            "execution_phase_protocol": "mr3-controlled-execution-phase-v2",
            "reset_handshake": "paused-controlled-state-peer-guard-storage-v2"}))
        (native/"supervisor_metadata.json").write_text('{}\n')
        result = {"passed": True, "errors": [], "native_attempts": 1, "task_successes": 1,
                  "episodes": [{"directory": str(native), "epoch": "fixture", "errors": [], "task": {"success": True}}]}
        return root, native, metadata, result

    def harness(self, result, *, information=None):
        passed = lambda *args: {"passed": True}
        preparation = SimpleNamespace(audit_archives=passed, audit_activity=passed, audit_execution_inputs=passed)
        info = information or (lambda *args: {"passed": True, "safety_contract": entry.CONTRACT, "freeze": FREEZE})
        return (
            patch("mr3_learning.reach_preparation.validate_qualification", return_value={"fixture_only": True}),
            patch.object(entry, "load_impl", return_value=(SimpleNamespace(audit_run=lambda *args: copy.deepcopy(result)), {})),
            patch.object(entry.audit_reach_preparation, "load_impl", return_value=(preparation, {})),
            patch.object(entry.audit_reach_information, "audit_episode", side_effect=info),
            patch.object(entry.audit_reach_peer_control, "audit_episode", return_value={"passed": True, "safety_contract": entry.CONTRACT, "freeze": FREEZE}),
            patch.object(entry.audit_reach_runtime, "audit_episode", return_value={"passed": True, "contract": entry.CONTRACT, "freeze": FREEZE,
                "independent_necessary_replay": True, "continuous_physical_model_proved": False}),
        )

    def test_private_reader_preserves_whole_source_math_and_original_global_dispatch(self):
        old_gate, old_cadence = original.load_native_gates, original.audit_odometry_cadence
        plan_path = Path("/unused/plan")
        module, proof = entry.load_impl(plan_path)
        self.assertTrue(proof["whole_source_inverse_equal"])
        self.assertEqual(proof["source_sha256"], entry.PPO_READER_SHA256)
        self.assertEqual(proof["projected_sha256"], proof["source_sha256"])
        self.assertEqual(proof["literal_changes"], [])
        for name in entry.UNCHANGED_FUNCTIONS:
            current, old = getattr(module, name), getattr(original, name)
            self.assertEqual(current.__code__.co_code, old.__code__.co_code)
            self.assertEqual(current.__code__.co_names, old.__code__.co_names)
            self.assertIsNot(current.__globals__, old.__globals__)
        self.assertIs(original.load_native_gates, old_gate)
        self.assertIs(original.audit_odometry_cadence, old_cadence)
        for name in ("dispatch_controlled_physics", "dispatch_controlled_readiness"):
            args = object(), [Path("/synthetic/native")], {}
            returned = object()
            with self.subTest(dispatch=name), patch.object(
                    entry.audit_reach_controlled_physics, name, return_value=returned) as called:
                self.assertIs(getattr(module, name)(*args), returned)
                called.assert_called_once_with(*args, plan_path=plan_path)
        self.assertIs(module.audit_odometry_cadence.audit, entry.audit_reach_cadence.audit)

    def test_qualification_uses_shared_validator_and_exact_original_metadata_bytes(self):
        root, _, metadata, _ = self.fixture()
        with patch("mr3_learning.reach_preparation.validate_qualification", return_value={"verified": "fixture"}) as validate:
            plan, qualification, saved, proof = entry.admission(metadata, FREEZE)
            validate.assert_called_once_with(qualification, plan, FREEZE, root=entry.WORKSPACE)
            self.assertEqual(proof, {"verified": "fixture"})
            self.assertEqual(set(saved), {plan, qualification})
            for field in ("reach_plan_sha256", "reach_qualification_sha256"):
                bad = dict(metadata); bad[field] = "0"*64
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "original PPO admission"):
                    entry.admission(bad, FREEZE)
            with self.assertRaisesRegex(ValueError, "differs from original PPO metadata"):
                entry.admission(metadata, FREEZE, root/"different-plan")
        self.assertEqual(validate.call_count, 1)

    def test_old_reader_pass_is_insufficient_when_independent_information_fails(self):
        root, _, _, result = self.fixture()
        a,b,c,d,e,f = self.harness(result, information=lambda *args: {"passed": False, "errors": ["missing actual delivery"]})
        with a,b,c,d,e as peer,f as runtime:
            report = entry.audit_run(root, FREEZE)
        self.assertFalse(report["passed"])
        self.assertEqual(report["task_successes"], 0)
        self.assertEqual(len(report["task_failures"]), 1)
        self.assertIn("information", report["errors"][-1])
        self.assertEqual(peer.call_count, 1); self.assertEqual(runtime.call_count, 1)

    def test_all_new_roles_and_original_policy_failure_are_conjunctive(self):
        root, _, _, result = self.fixture()
        result["passed"] = False; result["errors"] = ["original rollout GAE mismatch"]
        a,b,c,d,e,f = self.harness(result)
        with a,b,c,d,e,f: report = entry.audit_run(root, FREEZE)
        self.assertFalse(report["passed"])
        self.assertIn("original rollout GAE mismatch", report["errors"])
        self.assertTrue(report["reach_episodes"][0]["passed"])
        self.assertEqual(set(report["reach_episodes"][0])-{ "directory", "passed", "errors"},
                         {"information", "runtime_drive", "peer_control_fifo", "observation_archives", "activity", "execution_inputs"})

    def test_old_profile_and_mixed_native_attempt_reject_before_policy_replay(self):
        root, native, metadata, result = self.fixture()
        with patch.object(entry, "load_impl") as policy, \
                patch("mr3_learning.reach_preparation.validate_qualification", return_value={}):
            mixed = json.loads((native/"metadata.json").read_text()); mixed["safety_contract"] = "legacy"
            (native/"metadata.json").write_text(json.dumps(mixed))
            with self.assertRaisesRegex(ValueError, "mixed/legacy"):
                entry.audit_run(root, FREEZE)
            metadata["safety_contract"] = "legacy"
            with self.assertRaisesRegex(ValueError, "exact reach profile"):
                entry.admission(metadata, FREEZE)
            policy.assert_not_called()

    def test_qualification_bytes_changed_mid_audit_cannot_get_pass(self):
        root, _, metadata, result = self.fixture()
        def mutate(*args):
            path = Path(metadata["reach_qualification"])
            path.write_bytes(path.read_bytes()+b"\n")
            return {"passed": True, "safety_contract": entry.CONTRACT, "freeze": FREEZE}
        a,b,c,d,e,f = self.harness(result, information=mutate)
        with a,b,c,d,e,f: report = entry.audit_run(root, FREEZE)
        self.assertFalse(report["passed"])
        self.assertTrue(any("input changed" in error for error in report["errors"]))

    def test_missing_archive_or_topology_role_cannot_hide_behind_independent_replays(self):
        for failed in ("audit_archives", "audit_activity", "audit_execution_inputs"):
            root, _, _, result = self.fixture()
            a,b,c,d,e,f = self.harness(result)
            with a,b,c as preparation,d,e,f:
                helper = preparation.return_value[0]
                setattr(helper, failed, lambda *args: {"passed": False, "errors": ["missing raw fixture"]})
                report = entry.audit_run(root, FREEZE)
            with self.subTest(failed=failed): self.assertFalse(report["passed"])


if __name__ == "__main__":
    unittest.main()
