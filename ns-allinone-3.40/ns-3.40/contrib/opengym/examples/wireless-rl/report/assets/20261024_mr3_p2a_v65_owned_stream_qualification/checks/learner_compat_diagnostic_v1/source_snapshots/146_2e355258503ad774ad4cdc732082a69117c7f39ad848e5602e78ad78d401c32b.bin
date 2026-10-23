"""Artificial workload/source dispatch counterexamples; never native evidence.

This draft must be applied and source-sealed by the root before any execution.
The V17 source definitions may be loaded, but all audit data below are newly
constructed toy JSON. An original mathematical FAIL is deliberately retained.
"""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning import audit_reach_reset_workload as reader
from mr3_learning import reach_audit_projection as projection
from mr3_learning import reach_preparation as preparation
from mr3_learning.tests import test_reach_qualification as qualification_fixtures

FREEZE = "a" * 40


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


class ProjectionTests(unittest.TestCase):
    def test_shared_file_core_preserves_old_adjacent_api_and_entire_inverse(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.py"
            raw = b'VERSION = "old"\nVALUE = [1, 2, 3]\n'
            path.write_bytes(raw)
            expected = hashlib.sha256(raw).hexdigest()
            changes = (('VERSION = "old"', 'VERSION = "new"', 1),)
            direct, proof = projection.project_file(path, expected, changes)
            with patch.object(projection, "__file__", str(path.with_name("anchor.py"))):
                adjacent, adjacent_proof = projection.project_module(path.name, expected, changes)
            self.assertEqual((direct.VERSION, adjacent.VERSION), ("new", "new"))
            self.assertEqual(proof, adjacent_proof)
            self.assertEqual(proof["source_sha256"], proof["inverse_sha256"])
            self.assertTrue(proof["whole_source_inverse_equal"])
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(direct.__file__, str(path))

    def test_source_mutation_and_ambiguous_inverse_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "fixture.py"
            raw = b'VERSION = "old"\n'
            expected = hashlib.sha256(raw).hexdigest()
            for data, changes in ((raw + b"# mutation\n", ()),
                                  (raw, (('missing', 'new', 1),)),
                                  (raw + raw, (('old', 'new', 1),)),
                                  (raw, (('old', 'old', 1),)),
                                  (raw, (('old', 'VERSION', 1),))):
                with self.subTest(data=data, changes=changes):
                    path.write_bytes(data)
                    digest = expected if data != raw + raw else hashlib.sha256(data).hexdigest()
                    with self.assertRaises(ValueError):
                        projection.project_file(path, digest, changes)

    def test_both_actual_immutable_sources_load_new_constant_and_exact_old_inverse(self):
        for kind, (relative, expected) in reader.SOURCES.items():
            with self.subTest(kind=kind):
                raw = (reader.WORKSPACE / relative).read_bytes()
                module, proof = reader.load_reader(kind)
                self.assertEqual(module.PROBE_VERSION, reader.PROBE_VERSION)
                self.assertEqual(proof["source_sha256"], expected)
                self.assertEqual(proof["inverse_sha256"], expected)
                self.assertEqual(proof["literal_changes"], [{
                    "before": reader.CHANGE[0], "after": reader.CHANGE[1], "count": 1}])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
                old = ModuleType("unchanged_original_reset_fixture")
                old.__file__ = str(reader.WORKSPACE / relative)
                exec(compile(raw, old.__file__, "exec"), old.__dict__)
                self.assertEqual(old.PROBE_VERSION, "mr3-p2a0-outward-cancel-v6")

    def test_unknown_kind_never_selects_an_arbitrary_source(self):
        for kind in (None, True, "input", "/tmp/other.py"):
            with self.subTest(kind=kind), patch.object(reader, "project_file") as load:
                with self.assertRaises(ValueError):
                    reader.load_reader(kind)
                load.assert_not_called()


class WrapperTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.metadata = {"safety_contract": reader.CONTRACT,
                         "preparation_probe_version": reader.PROBE_VERSION}
        for name in ("benchmark_metadata.json", "benchmark_summary.json"):
            put(self.directory / name, self.metadata)

    def invoke(self, kind="angular", **kwargs):
        return reader.audit(self.directory, FREEZE, kind=kind,
            workload_profile=reader.PROFILE,
            **({"per_episode_report": self.directory / "physical.json"} if kind == "physics" else {}),
            **kwargs)

    def original(self, kind, passed=True, errors=None):
        return {"schema": reader.EXPECTED_SCHEMAS[kind], "passed": passed,
                "errors": [] if errors is None else errors,
                "episodes": [{"artificial_original_fixture": True}],
                "criteria": {"all_original_math_retained": True}}

    def test_complete_original_result_is_retained_in_new_source_identified_envelope(self):
        for kind in reader.SOURCES:
            original = self.original(kind)
            method = Mock(return_value=original)
            with self.subTest(kind=kind), patch.object(reader, "load_reader", return_value=(
                    SimpleNamespace(audit=method), {"whole_source_inverse_equal": True})):
                result = self.invoke(kind)
            self.assertTrue(result["passed"])
            self.assertEqual(result["schema"], reader.SCHEMA)
            self.assertIs(result["original_reader_result"], original)
            self.assertEqual(result["workload_profile"], reader.PROFILE)
            self.assertEqual(result["entry"]["sha256"], hashlib.sha256(Path(reader.__file__).read_bytes()).hexdigest())
            expected = ((self.directory, FREEZE) if kind == "angular" else
                        (self.directory, self.directory / "physical.json", FREEZE))
            method.assert_called_once_with(*expected)

    def test_original_failures_and_invalid_result_identity_cannot_become_pass(self):
        for kind in reader.SOURCES:
            variants = (self.original(kind, False), self.original(kind, True, ["bound violated"]),
                        dict(self.original(kind), schema="wrong"), dict(self.original(kind), passed=1))
            for original in variants:
                with self.subTest(kind=kind, original=original), patch.object(reader, "load_reader", return_value=(
                        SimpleNamespace(audit=Mock(return_value=original)), {})):
                    result = self.invoke(kind)
                self.assertFalse(result["passed"])
                self.assertEqual(result["original_reader_result"], original)

    def test_original_exception_is_a_failed_receipt_not_a_retry(self):
        method = Mock(side_effect=ValueError("sampled stop bound exceeded"))
        with patch.object(reader, "load_reader", return_value=(SimpleNamespace(audit=method), {})):
            result = self.invoke("physics")
        self.assertFalse(result["passed"])
        self.assertIn("sampled stop bound exceeded", " ".join(result["errors"]))
        self.assertEqual(method.call_count, 1)

    def test_wrong_profile_and_report_shape_fail_before_any_input_read(self):
        variants = ({"workload_profile": None}, {"workload_profile": True},
                    {"workload_profile": "legacy"}, {"kind": "physics"},
                    {"per_episode_report": self.directory / "unexpected.json"}, {"freeze": "bad"})
        for changes in variants:
            kwargs = dict(kind="angular", workload_profile=reader.PROFILE)
            freeze = changes.get("freeze", FREEZE)
            kwargs.update({key: value for key, value in changes.items() if key != "freeze"})
            with self.subTest(changes=changes), patch.object(reader, "load_reader") as load:
                result = reader.audit(self.directory, freeze, **kwargs)
            self.assertFalse(result["passed"])
            load.assert_not_called()
            self.assertEqual(result["benchmark_inputs"], {})

    def test_legacy_missing_unknown_or_mixed_input_declarations_are_rejected(self):
        for key, value in (("safety_contract", "legacy"), ("safety_contract", None),
                           ("preparation_probe_version", "mr3-p2a0-outward-cancel-v6"),
                           ("preparation_probe_version", None), ("preparation_probe_version", "unknown")):
            for name in ("benchmark_metadata.json", "benchmark_summary.json"):
                put(self.directory / "benchmark_metadata.json", self.metadata)
                put(self.directory / "benchmark_summary.json", self.metadata)
                put(self.directory / name, dict(self.metadata, **{key: value}))
                method = Mock(return_value=self.original("angular"))
                with self.subTest(key=key, value=value, name=name), patch.object(reader, "load_reader", return_value=(
                        SimpleNamespace(audit=method), {})):
                    result = self.invoke()
                self.assertFalse(result["passed"])
                method.assert_not_called()

    def test_changed_benchmark_bytes_during_original_audit_fail(self):
        def change(*_):
            put(self.directory / "benchmark_summary.json", dict(self.metadata, changed=True))
            return self.original("angular")
        with patch.object(reader, "load_reader", return_value=(SimpleNamespace(audit=change), {})):
            result = self.invoke()
        self.assertFalse(result["passed"])
        self.assertIn("changed during reset audit", " ".join(result["errors"]))

    def test_cli_has_fixed_choices_rejects_overwrite_and_preserves_return_code(self):
        output = self.directory / "result.json"
        argv = [str(self.directory), "--kind", "angular", "--workload-profile", reader.PROFILE,
                "--freeze", FREEZE, "--output", str(output)]
        with patch.object(reader, "audit", return_value={"passed": False, "errors": ["toy math FAIL"]}), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(reader.main(argv), 1)
        old = output.read_bytes()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            reader.main(argv)
        self.assertEqual(output.read_bytes(), old)
        with patch.object(reader, "audit") as audit, contextlib.redirect_stderr(io.StringIO()), \
                self.assertRaises(SystemExit):
            reader.main([*argv[:-1], str(self.directory / "new.json"), "--angular-consumer", "/tmp/other.py"])
        audit.assert_not_called()


class OriginalDeclarationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        schedule = [["open", 101], ["open", 101], ["rooms", 101], ["corridors", 101]]
        self.metadata = {"freeze": FREEZE, "workers": 2, "robots_per_worker": 3,
            "schedule": schedule, "steps_per_episode": 32,
            "preparation_probe_version": reader.PROBE_VERSION,
            "preparation_motion_probe": True, "terminal_probe": False,
            "deadline_probe": False, "fault_probe": False,
            "safety_contract": reader.CONTRACT}
        self.summary = dict(self.metadata, passed=True, workers_results=[{
            "worker_id": worker, "episodes": [{"scene": scene, "seed": seed,
                "transitions": 32, "terminated": False, "truncated": True}
                for scene, seed in schedule]} for worker in range(2)])
        self.report = self.directory / "physical.json"
        put(self.report, {"schema": "deliberately-invalid-toy-physical-report"})
        self.save()

    def save(self):
        put(self.directory / "benchmark_metadata.json", self.metadata)
        put(self.directory / "benchmark_summary.json", self.summary)

    def declaration_rejected(self, kind, module):
        if kind == "angular":
            result = module.audit(self.directory, FREEZE)
            self.assertFalse(result["passed"])  # No scientific episode data were manufactured.
            self.assertEqual([error for error in result["errors"] if error.startswith("source:")], [],
                             "source-loading failure cannot masquerade as an expected toy math FAIL")
            self.assertEqual(result["angular_consumer"]["sha256"], module.CONSUMER_SHA256)
            return any(error.startswith("benchmark:") for error in result["errors"])
        with self.assertRaises(ValueError) as error:
            module.audit(self.directory, self.report, FREEZE)
        message = str(error.exception)
        self.assertTrue("aggregate requires only" in message or "per-episode consumer source/schema" in message)
        return "aggregate requires only" in message

    def test_actual_projected_entry_accepts_only_the_new_workload_before_real_math_failure(self):
        for kind in reader.SOURCES:
            module, _ = reader.load_reader(kind)
            with self.subTest(kind=kind):
                self.assertFalse(self.declaration_rejected(kind, module))
        # The deliberate missing-EP/invalid-report failure is not supplied as qualification.

    def test_missing_leaf_is_source_failure_not_successful_declaration_or_math_readiness(self):
        angular, _ = reader.load_reader("angular")
        result = angular.audit(self.directory, FREEZE, consumer_path=self.directory / "absent_leaf.py")
        self.assertFalse(result["passed"])
        self.assertTrue(any(error.startswith("source:") for error in result["errors"]))
        self.assertFalse(any(error.startswith("benchmark:") for error in result["errors"]))
        self.assertNotIn("sha256", result["angular_consumer"])
        physics, _ = reader.load_reader("physics")
        with patch.object(physics, "CONSUMER_PATH", self.directory / "absent_leaf.py"), self.assertRaises(OSError):
            physics.audit(self.directory, self.report, FREEZE)

    def test_actual_projected_entry_rejects_each_wrong_worker_schedule_step_flag_and_probe(self):
        mutations = (("workers", 1), ("schedule", [["open", 102]] * 4),
            ("steps_per_episode", 20), ("freeze", "b" * 40),
            ("preparation_probe_version", "mr3-p2a0-outward-cancel-v6"),
            ("preparation_probe_version", None), ("preparation_motion_probe", False),
            ("terminal_probe", True), ("deadline_probe", True), ("fault_probe", True))
        for kind in reader.SOURCES:
            module, _ = reader.load_reader(kind)
            for target in ("metadata", "summary"):
                for key, value in mutations:
                    data = getattr(self, target)
                    old = data[key]
                    data[key] = value
                    self.save()
                    with self.subTest(kind=kind, target=target, key=key):
                        self.assertTrue(self.declaration_rejected(kind, module))
                    data[key] = old
                    self.save()

    def test_unmodified_original_sources_still_reject_reach_and_accept_only_their_old_declaration(self):
        for kind, (relative, _) in reader.SOURCES.items():
            path = reader.WORKSPACE / relative
            module = ModuleType("actual_original_reset_workload")
            module.__file__ = str(path)
            exec(compile(path.read_bytes(), str(path), "exec"), module.__dict__)
            with self.subTest(kind=kind):
                self.assertTrue(self.declaration_rejected(kind, module))
                self.metadata["preparation_probe_version"] = "mr3-p2a0-outward-cancel-v6"
                self.summary["preparation_probe_version"] = "mr3-p2a0-outward-cancel-v6"
                self.save()
                self.assertFalse(self.declaration_rejected(kind, module))
                self.metadata["preparation_probe_version"] = reader.PROBE_VERSION
                self.summary["preparation_probe_version"] = reader.PROBE_VERSION
                self.save()


class PlanWiringTests(unittest.TestCase):
    def setUp(self):
        fixture = qualification_fixtures.ReachQualificationTests(
            methodName="test_new_plan_keeps_thirty_scientific_roles_and_twelve_episodes")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.plan = fixture.plan

    def reset_jobs(self, plan=None):
        stage = next(s for s in (plan or self.plan)["stages"] if s["stage"] == "reset")
        return stage, {job["id"]: job for job in stage["audits"]}

    def test_real_builder_registers_and_validator_accepts_both_exact_entry_argv(self):
        preparation.validate_plan(self.plan)
        self.assertEqual(self.plan["reset_workload_reader_profile"], reader.PROFILE)
        stage, jobs = self.reset_jobs()
        for kind in reader.SOURCES:
            report = jobs["physical_per_episode"]["output"] if kind == "physics" else None
            self.assertEqual(jobs[kind]["argv"], reader.command_argv(
                kind, stage["run_directory"], "{freeze}", jobs[kind]["output"], report))
        self.assertEqual(sum(len(preparation.primitives.roles(s)) for s in self.plan["stages"]), 30)
        self.assertEqual(sum(s["expected_episodes"] for s in self.plan["stages"]), 12)

    def test_missing_unknown_profile_or_source_pin_is_rejected(self):
        for value in (None, True, "legacy", "unknown"):
            changed = copy.deepcopy(self.plan)
            if value is None:
                changed.pop("reset_workload_reader_profile")
            else:
                changed["reset_workload_reader_profile"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                preparation.validate_plan(changed)
        for path, _ in reader.SOURCES.values():
            changed = copy.deepcopy(self.plan)
            changed["source_bindings"][str(path)] = "0" * 64
            with self.subTest(path=path), self.assertRaises(ValueError):
                preparation.validate_plan(changed)

    def test_source_inventory_omissions_reject_even_when_general_inventory_omits_new_files(self):
        for path in sorted(reader.SOURCE_PATHS):
            changed = copy.deepcopy(self.plan)
            changed["source_bindings"].pop(path)
            # A git-tracked-only inventory can miss a new file before commit;
            # the fixed reset-reader requirement must independently reject it.
            with self.subTest(path=path), patch.object(preparation, "source_inventory", return_value=set()), \
                    self.assertRaisesRegex(ValueError, "reset workload reader source inventory incomplete"):
                preparation.validate_plan(changed)

    def test_actual_role_module_kind_profile_run_freeze_output_and_dependency_mutations_reject(self):
        for kind in reader.SOURCES:
            for flag in ("--kind", "--workload-profile", "--freeze", "--output"):
                changed = copy.deepcopy(self.plan)
                _, jobs = self.reset_jobs(changed)
                jobs[kind]["argv"][jobs[kind]["argv"].index(flag) + 1] = "wrong"
                with self.subTest(kind=kind, flag=flag), self.assertRaises(ValueError):
                    preparation.validate_plan(changed)
            for index in (2, 3):
                changed = copy.deepcopy(self.plan)
                _, jobs = self.reset_jobs(changed)
                jobs[kind]["argv"][index] = "/other/entry-or-run"
                with self.subTest(kind=kind, index=index), self.assertRaises(ValueError):
                    preparation.validate_plan(changed)
        for field, value in (("depends_on", []), ("required", False), ("id", "wrong")):
            changed = copy.deepcopy(self.plan)
            _, jobs = self.reset_jobs(changed)
            jobs["physics"][field] = value
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                preparation.validate_plan(changed)

    def test_per_episode_report_cannot_read_another_run_or_feed_another_report(self):
        for job_id, flag in (("physics", "--per-episode-report"),
                             ("physical_per_episode", "--output")):
            changed = copy.deepcopy(self.plan)
            _, jobs = self.reset_jobs(changed)
            jobs[job_id]["argv"][jobs[job_id]["argv"].index(flag) + 1] = "/wrong/report.json"
            with self.subTest(job_id=job_id), self.assertRaises(ValueError):
                preparation.validate_plan(changed)

    def test_unchanged_legacy_preparation_still_declares_original_direct_v17_scripts(self):
        with tempfile.TemporaryDirectory(dir=preparation.WORKSPACE) as temporary:
            root = Path(temporary)
            binding = root / "binding.json"
            put(binding, {"source_bindings": [], "binaries": {}})
            old = preparation.primitives.build_plan(output_directory=root / "output", run_root=root / "native",
                custody_binding=binding, binary_proof=root / "binary.json", preflight=root / "preflight.json",
                engineering_remaining_seconds="20000")
        self.assertNotIn("reset_workload_reader_profile", old)
        reset = next(s for s in old["stages"] if s["stage"] == "reset")
        for job in reset["audits"]:
            if job.get("role") in ("angular", "physics"):
                self.assertIn("20261017_mr3_p2a0_v17/independent/", job["argv"][1])
        self.assertEqual(preparation.argument(reset["native"]["argv"], "--preparation-probe-version"),
                         "mr3-p2a0-outward-cancel-v6")


class PreflightReadinessTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"reset_workload_reader_profile": reader.PROFILE, "source_bindings": {
            relative: hashlib.sha256((reader.WORKSPACE / relative).read_bytes()).hexdigest()
            for relative in reader.SOURCE_PATHS}}

    def git_bytes(self, argv, **kwargs):
        self.assertEqual(argv[:2], ["git", "show"])
        self.assertEqual(kwargs["cwd"], reader.WORKSPACE)
        self.assertEqual(kwargs["timeout"], 10)
        revision, relative = argv[2].split(":", 1)
        self.assertEqual(revision, FREEZE)
        return (reader.WORKSPACE / relative).read_bytes()

    def test_actual_both_reader_kinds_and_leaf_definitions_are_loaded_without_audit(self):
        with patch.object(reader.subprocess, "check_output", side_effect=self.git_bytes) as git, \
                patch.object(reader, "load_reader", wraps=reader.load_reader) as load:
            result = reader.verify_reader_readiness(self.plan, FREEZE)
        self.assertTrue(result["passed"])
        self.assertEqual(result["schema"], "mr3-reach-reset-reader-entry-readiness-v1")
        self.assertEqual(result["audit_calls"], 0)
        self.assertFalse(result["native_inputs_read"])
        self.assertFalse(result["scientific_qualification_credit"])
        self.assertEqual([call.args for call in load.call_args_list], [("angular",), ("physics",)])
        self.assertEqual(git.call_count, len(reader.SOURCE_PATHS))
        self.assertEqual({row["path"] for row in result["sources"]}, reader.SOURCE_PATHS)
        for row in result["readers"]:
            self.assertEqual(row["probe_version"], reader.PROBE_VERSION)
            for key in ("immutable_reader_projection", "unchanged_leaf_source"):
                self.assertTrue(row[key]["whole_source_inverse_equal"])
                self.assertEqual(row[key]["source_sha256"], row[key]["inverse_sha256"])
            self.assertEqual(row["unchanged_leaf_source"]["literal_changes"], [])

    def test_missing_profile_inventory_or_bad_freeze_prevents_any_reader_load(self):
        variants = [(dict(self.plan, reset_workload_reader_profile=value), FREEZE)
                    for value in (None, True, "unknown")]
        variants += [(self.plan, value) for value in (None, True, "bad")]
        for relative in sorted(reader.SOURCE_PATHS):
            plan = copy.deepcopy(self.plan)
            plan["source_bindings"].pop(relative)
            variants.append((plan, FREEZE))
        for plan, freeze in variants:
            with self.subTest(plan=plan, freeze=freeze), patch.object(reader, "load_reader") as load, \
                    patch.object(reader.subprocess, "check_output") as git, self.assertRaises(ValueError):
                reader.verify_reader_readiness(plan, freeze)
            load.assert_not_called()
            git.assert_not_called()

    def test_wrong_entry_helper_or_immutable_current_and_git_bytes_prevents_loading(self):
        for relative in sorted(reader.SOURCE_PATHS):
            changed = copy.deepcopy(self.plan)
            changed["source_bindings"][relative] = "0" * 64
            with self.subTest(relative=relative), patch.object(reader, "load_reader") as load, \
                    patch.object(reader.subprocess, "check_output", side_effect=self.git_bytes), \
                    self.assertRaisesRegex(ValueError, "source pin differs"):
                reader.verify_reader_readiness(changed, FREEZE)
            load.assert_not_called()
        with patch.object(reader, "load_reader") as load, \
                patch.object(reader.subprocess, "check_output", return_value=b"wrong frozen bytes"), \
                self.assertRaisesRegex(ValueError, "current/Git differs"):
            reader.verify_reader_readiness(self.plan, FREEZE)
        load.assert_not_called()

    def test_actual_loaded_version_and_whole_inverse_are_required_not_only_plan_strings(self):
        module, proof = reader.load_reader("angular")
        variants = [(SimpleNamespace(**dict(vars(module), PROBE_VERSION="old")), proof),
                    (SimpleNamespace(**dict(vars(module), __file__="wrong")), proof)]
        for key, value in (("inverse_sha256", "0" * 64), ("source_sha256", "0" * 64),
                           ("whole_source_inverse_equal", False), ("literal_changes", [])):
            variants.append((module, dict(proof, **{key: value})))
        for loaded, changed_proof in variants:
            with self.subTest(proof=changed_proof), patch.object(reader, "load_reader", return_value=(loaded, changed_proof)), \
                    patch.object(reader.subprocess, "check_output", side_effect=self.git_bytes), \
                    self.assertRaisesRegex(ValueError, "actual load/inverse differs"):
                reader.verify_reader_readiness(self.plan, FREEZE)

    def test_leaf_source_loading_exception_is_entry_failure_not_a_fake_math_result(self):
        actual_project = reader.project_file
        calls = []
        def project(path, expected, changes):
            calls.append(Path(path))
            if Path(path) == reader.WORKSPACE / reader.LEAVES["angular"][0]:
                raise ImportError("artificial leaf definition loading failed")
            return actual_project(path, expected, changes)
        with patch.object(reader, "project_file", side_effect=project), \
                patch.object(reader.subprocess, "check_output", side_effect=self.git_bytes), \
                self.assertRaisesRegex(ImportError, "leaf definition loading failed"):
            reader.verify_reader_readiness(self.plan, FREEZE)
        self.assertEqual(calls, [reader.WORKSPACE / reader.SOURCES["angular"][0],
                                 reader.WORKSPACE / reader.LEAVES["angular"][0]])


if __name__ == "__main__":
    unittest.main()
