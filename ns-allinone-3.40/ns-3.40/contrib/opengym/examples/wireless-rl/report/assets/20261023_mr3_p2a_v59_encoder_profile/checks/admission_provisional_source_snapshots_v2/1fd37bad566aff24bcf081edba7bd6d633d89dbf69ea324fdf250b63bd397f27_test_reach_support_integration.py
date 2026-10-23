"""Artificial rule/CLI/metadata/source binding checks; no native credit."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning import supervisor as owner, benchmark, ppo
from mr3_learning import reach_preparation as preparation, reach_policy_chain as chain
from mr3_learning import audit_reach_preparation as full, audit_reach_ppo as policy_audit
from mr3_learning.tests import test_reach_policy_chain as policy_fixtures
from mr3_learning.tests import test_audit_reach_ppo as audit_fixtures
from mr3_learning.tests import test_audit_reach_system_replay as replay_fixtures

BINARY, SUPPORT = owner.BINARY_REACH_GEOMETRY_RULE, owner.SUPPORT_REACH_GEOMETRY_RULE
CONTRACT = "mr3-reach-v1"


class ReachSupportIntegrationTests(unittest.TestCase):
    def test_strict_rule_and_canonical_argv_reject_before_native_side_effects(self):
        self.assertEqual(owner.reach_geometry_rule_from_argv([]), BINARY)
        argv = ["--safety-contract", CONTRACT, "--reach-geometry-rule", SUPPORT]
        self.assertEqual(owner.reach_geometry_rule_from_argv(argv), SUPPORT)
        for value in (None, True, False, 1, {}, [], "unknown"):
            with self.subTest(value=value), patch.object(owner.Path, "mkdir") as mkdir:
                with self.assertRaises(ValueError): owner.Supervisor(reach_geometry_rule=value)
                mkdir.assert_not_called()
        with patch.object(owner.Path, "mkdir") as mkdir:
            with self.assertRaisesRegex(ValueError, "requires mr3-reach-v1"):
                owner.Supervisor(reach_geometry_rule=SUPPORT)
            mkdir.assert_not_called()
        for flags in (["--reach-geometry-rule"], ["--reach-geometry-rule=" + SUPPORT],
                      ["--reach-geometry-rule", BINARY, "--reach-geometry-rule", SUPPORT],
                      ["--reach-geometry-rule", SUPPORT]):
            with self.subTest(flags=flags), self.assertRaises(ValueError):
                owner.reach_geometry_rule_from_argv(flags)

    def test_actual_benchmark_cli_rejects_duplicate_and_equals_before_any_work(self):
        prefix = ["--workers", "1", "--run-id", "support-cli-only", "--safety-contract", CONTRACT]
        for suffix in (["--reach-geometry-rule", BINARY, "--reach-geometry-rule", SUPPORT],
                       ["--reach-geometry-rule=" + SUPPORT]):
            with self.subTest(suffix=suffix), patch.object(benchmark.Path, "mkdir") as mkdir, \
                    patch.object(benchmark, "Supervisor") as native, \
                    patch.object(benchmark.subprocess, "check_output") as git, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                benchmark.main(prefix + suffix)
            self.assertEqual(error.exception.code, 2)
            for operation in (mkdir, native, git): operation.assert_not_called()

    def test_actual_ppo_cli_rejects_duplicate_and_equals_before_model_or_admission(self):
        prefix = ["--run-id", "support-cli-only", "--decisions", "2", "--wall-seconds", "10",
                  "--safety-contract", CONTRACT, "--reach-plan", "/artificial/plan",
                  "--reach-qualification", "/artificial/qualification"]
        for suffix in (["--reach-geometry-rule", BINARY, "--reach-geometry-rule", SUPPORT],
                       ["--reach-geometry-rule=" + SUPPORT]):
            with self.subTest(suffix=suffix), patch.object(ppo.Path, "mkdir") as mkdir, \
                    patch.object(ppo, "MaskablePPO") as model, \
                    patch.object(preparation, "validate_qualification") as admission, \
                    contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                ppo.main(prefix + suffix)
            self.assertEqual(error.exception.code, 2)
            for operation in (mkdir, model, admission): operation.assert_not_called()

    def test_real_supervisor_reset_rpc_and_metadata_forward_only_explicit_support(self):
        for rule in (BINARY, SUPPORT):
            with self.subTest(rule=rule), tempfile.TemporaryDirectory() as temporary:
                supervisor = owner.Supervisor(output_root=temporary, safety_contract=CONTRACT,
                    seed_rule="exact-point-bridge-v2", start_graph_rule="point-attachment-3x3-v1",
                    reach_geometry_rule=rule)
                identity = {"pid": 43121, "parent": 1, "group": 43121, "session": 43121,
                            "start_ticks": 123, "state": "S"}
                process = Mock(pid=identity["pid"])
                process.stdout.fileno.return_value = 9; process.stdin.fileno.return_value = 10
                def reset(operation, **payload):
                    return {"snapshot": {"epoch": supervisor.episode.epoch}}
                with patch.object(owner.subprocess, "Popen", return_value=process), \
                        patch.object(owner, "process_identity", return_value=identity), \
                        patch.object(owner, "JsonLinePeer", return_value=SimpleNamespace()), \
                        patch.object(owner.threading, "Thread"), patch.object(supervisor, "close"), \
                        patch.object(supervisor, "_rpc", side_effect=reset) as rpc:
                    try:
                        supervisor.reset()
                        metadata = json.loads((supervisor.episode.directory / "supervisor_metadata.json").read_text())
                        if rule == BINARY:
                            self.assertNotIn("reach_geometry_rule", metadata)
                            self.assertNotIn("reach_geometry_rule", rpc.call_args.kwargs)
                        else:
                            self.assertEqual(metadata["reach_geometry_rule"], SUPPORT)
                            self.assertEqual(rpc.call_args.kwargs["reach_geometry_rule"], SUPPORT)
                    finally:
                        if supervisor.episode is not None: supervisor.episode.output.close()

    def plan(self, rule=BINARY, *, binding_rule=None):
        temporary = tempfile.TemporaryDirectory(prefix=".mr3-support-plan-unit-", dir=preparation.WORKSPACE)
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name); binding = root / "binding.json"
        rows = [{"path": path, "sha256": preparation.sha(preparation.WORKSPACE / path)}
                for path in sorted(preparation.SUPPORT_REACH_SOURCES)] if rule == SUPPORT else []
        document = {"source_bindings": rows, "binaries": {}}
        if binding_rule is not None: document["reach_geometry_rule"] = binding_rule
        elif rule == SUPPORT: document["reach_geometry_rule"] = SUPPORT
        binding.write_text(json.dumps(document))
        kwargs = dict(plan_path=root / "plan.json", output_directory=root / "execution", run_root=root / "native",
            custody_binding=binding, binary_proof=root / "binary.json", preflight=root / "preflight.json",
            engineering_remaining_seconds="25000")
        return preparation.build_plan(reach_geometry_rule=rule, **kwargs), kwargs

    def test_real_plan_builder_binds_four_stages_and_both_support_sources(self):
        plan, _ = self.plan(SUPPORT)
        self.assertEqual(plan["reach_geometry_rule"], SUPPORT)
        self.assertEqual(sum(stage["expected_episodes"] for stage in plan["stages"]), 12)
        self.assertEqual(sum(len(preparation.primitives.roles(stage)) for stage in plan["stages"]), 30)
        self.assertTrue(preparation.SUPPORT_REACH_SOURCES <= plan["source_bindings"].keys())
        for i, stage in enumerate(plan["stages"]):
            self.assertEqual(owner.reach_geometry_rule_from_argv(stage["native"]["argv"]), SUPPORT)
            changed = copy.deepcopy(plan); argv = changed["stages"][i]["native"]["argv"]
            del argv[argv.index("--reach-geometry-rule"):argv.index("--reach-geometry-rule") + 2]
            with self.subTest(stage=stage["stage"]), self.assertRaisesRegex(ValueError, "reach geometry rule differs"):
                preparation.validate_plan(changed)
        for source in preparation.SUPPORT_REACH_SOURCES:
            changed = copy.deepcopy(plan); changed["source_bindings"].pop(source)
            with self.subTest(source=source), self.assertRaises(ValueError): preparation.validate_plan(changed)

    def test_default_plan_is_identical_to_explicit_binary_and_cannot_take_support_binding(self):
        plan, kwargs = self.plan()
        self.assertEqual(plan, preparation.build_plan(**kwargs))
        self.assertNotIn("reach_geometry_rule", plan)
        self.assertTrue(all("--reach-geometry-rule" not in stage["native"]["argv"] for stage in plan["stages"]))
        with self.assertRaisesRegex(ValueError, "custody binding reach geometry rule differs"):
            self.plan(SUPPORT, binding_rule=BINARY)

    def test_minimum_pilot_final_all_require_exact_rule_and_positive_updates_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            plan, path, qualification = policy_fixtures.plan_fixture(Path(temporary))
            plan["reach_geometry_rule"] = SUPPORT
            for stage in chain.STAGES:
                plan["policy_stages"][stage]["argv"] += ["--reach-geometry-rule", SUPPORT]
                chain.stage_spec(plan, path, qualification, stage)
                changed = copy.deepcopy(plan); argv = changed["policy_stages"][stage]["argv"]
                argv[argv.index("--reach-geometry-rule") + 1] = BINARY
                with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "reach geometry rule differs"):
                    chain.stage_spec(changed, path, qualification, stage)
        for stage in chain.STAGES:
            metadata, native, audit, episodes, spec = policy_fixtures.native_fixture(stage)
            self.assertNotIn("reach_geometry_rule", chain.check_native_result(stage, metadata, native, audit, episodes, spec))
            spec["argv"] += ["--safety-contract", CONTRACT, "--reach-geometry-rule", SUPPORT]
            metadata["reach_geometry_rule"] = native["reach_geometry_rule"] = SUPPORT
            self.assertEqual(chain.check_native_result(stage, metadata, native, audit, episodes, spec)["reach_geometry_rule"], SUPPORT)
            for row in (metadata, native):
                saved = row.pop("reach_geometry_rule")
                with self.subTest(stage=stage), self.assertRaisesRegex(ValueError, "reach geometry rule differs"):
                    chain.check_native_result(stage, metadata, native, audit, episodes, spec)
                row["reach_geometry_rule"] = saved
            if stage != "validation":
                native["optimizer_updates"] = 0
                with self.assertRaises(ValueError): chain.check_native_result(stage, metadata, native, audit, episodes, spec)
            else:
                audit["task_successes"] = 2
                with self.assertRaises(ValueError): chain.check_native_result(stage, metadata, native, audit, episodes, spec)

    def audit_fixture(self):
        fixture = audit_fixtures.ReachPPOAuditTests(); self.addCleanup(fixture.doCleanups)
        root, native, metadata, result = fixture.fixture()
        plan_path = Path(metadata["reach_plan"]); plan = json.loads(plan_path.read_text())
        plan["reach_geometry_rule"] = SUPPORT; plan_path.write_text(json.dumps(plan))
        metadata.update(reach_geometry_rule=SUPPORT, reach_plan_sha256=hashlib.sha256(plan_path.read_bytes()).hexdigest())
        (root / "metadata.json").write_text(json.dumps(metadata))
        for path in (root / "summary.json", native / "metadata.json", native / "supervisor_metadata.json"):
            value = json.loads(path.read_text()); value["reach_geometry_rule"] = SUPPORT
            path.write_text(json.dumps(value))
        return fixture, root, native, result

    def test_ppo_audit_refuses_old_runtime_pass_for_new_rule(self):
        fixture, root, native, result = self.audit_fixture()
        a, b, c, d, e, f = fixture.harness(result)
        with a, b, c, d, e, f:
            report = policy_audit.audit_run(root, audit_fixtures.FREEZE)
        self.assertFalse(report["passed"])
        self.assertTrue(any("runtime role" in x for x in report["reach_episodes"][0]["errors"]))
        a, b, c, d, e, f = fixture.harness(result)
        with a, b, c, d, e, f as runtime:
            runtime.return_value["reach_geometry_rule"] = SUPPORT
            report = policy_audit.audit_run(root, audit_fixtures.FREEZE)
        self.assertTrue(report["passed"], report)

    def test_ppo_audit_rejects_episode_or_supervisor_mode_fallthrough(self):
        for kind in ("episode", "supervisor", "summary"):
            fixture, root, native, result = self.audit_fixture()
            path = {"episode": native / "metadata.json", "supervisor": native / "supervisor_metadata.json",
                    "summary": root / "summary.json"}[kind]
            value = json.loads(path.read_text()); value.pop("reach_geometry_rule"); path.write_text(json.dumps(value))
            a, b, c, d, e, f = fixture.harness(result)
            with self.subTest(kind=kind), a, b, c, d, e, f, self.assertRaisesRegex(ValueError, "reach geometry rule differs"):
                policy_audit.audit_run(root, audit_fixtures.FREEZE)

    def test_system_input_bridge_keeps_leaf_snapshot_math_and_binds_native_mode(self):
        fixture = replay_fixtures.SystemExactReplayTests(); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        with patch.object(full.subprocess, "Popen") as launch:
            result = full.audit_exact_seed_inputs_system(fixture.directory, seed_rule=replay_fixtures.SEED,
                start_graph_rule=replay_fixtures.START, reach_geometry_rule=SUPPORT)
        self.assertFalse(result["passed"]); launch.assert_not_called()
        fixture.metadata.update(reach_geometry_rule=SUPPORT, safety_contract=CONTRACT); fixture.write_metadata()
        expected = fixture.valid_result(); original = full.audit_exact_seed_inputs_system
        def selected(*args, **kwargs):
            return original(*args, **kwargs, reach_geometry_rule=SUPPORT)
        with patch.object(full, "audit_exact_seed_inputs_system", side_effect=selected):
            result, launch, child = fixture.replay(expected)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["reach_geometry_rule"], SUPPORT)
        self.assertEqual(result["system_python_execution"]["reach_geometry_rule"], SUPPORT)
        self.assertNotIn("--reach-geometry-rule", result["system_python_execution"]["argv"])
        child.wait.assert_called_once()


if __name__ == "__main__":
    unittest.main()
