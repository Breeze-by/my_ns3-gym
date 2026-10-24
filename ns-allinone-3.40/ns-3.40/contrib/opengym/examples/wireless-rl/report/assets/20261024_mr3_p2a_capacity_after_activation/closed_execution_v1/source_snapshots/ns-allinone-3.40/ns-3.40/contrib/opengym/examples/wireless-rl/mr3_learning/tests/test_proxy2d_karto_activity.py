"""Artificial metadata/admission fixtures; no native load, World or episode."""
from contextlib import ExitStack
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import proxy2d_karto_activity as activity


def identity(pid):
    return dict(pid=pid, parent=10, group=pid, session=pid, start_ticks=pid * 100)


def write(path, value):
    path.write_text(json.dumps(value))


class ProfileAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "profile"
        self.run.mkdir()
        self.plan = self.root / "profile_plan.json"
        self.plan.write_text("profile plan fixture")
        self.freeze = "a" * 40
        self.native = {"path": str(self.root / "native.json"), "sha256": "b" * 64}
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(activity, "output_path", return_value=self.run))
        self.stack.enter_context(patch.object(activity, "plan_path", return_value=self.plan))
        self.stack.enter_context(patch.object(activity, "manifest_reference", return_value=self.native))
        self.absence = self.stack.enter_context(patch.object(activity, "_absence"))
        self.outer = self.root / "outer.json"
        self.final = self.root / "final.json"
        self.final_outer = self.root / "final_outer.json"
        start = dict(kind="karto_profile", freeze=self.freeze,
            plan_sha256=activity.sha(self.plan), started_ns=2_000_000_000,
            deadline_ns=602_000_000_000, coordinator_identity=identity(100))
        phases = {}
        for i, name in enumerate(activity.PHASES["karto_profile"]):
            row = dict(passed=True, actual_waited=True, actual_returncode=0,
                timed_out=False, signals_sent=[], errors=[],
                started_monotonic_ns=(3 + i * 2) * 10**9,
                ended_monotonic_ns=(4 + i * 2) * 10**9)
            phases[name] = row
            write(self.run / (name + "_actual_wait.json"), row)
        result = dict(start, passed=True, source_unchanged=True, errors=[], phases=phases,
                      ended_ns=15_000_000_000)
        write(self.run / "activity_start.json", start)
        write(self.run / "activity_result.json", result)
        write(self.run / "capacity_summary.json", dict(activity_spec=activity.activity_spec("karto_profile"),
            mapper="karto", native_manifest=self.native, step_attempts=8, step_returns=8, step_errors=0))
        write(self.run / "independent_audit.json", dict(passed=True, verified_action_count=8,
            verified_uniform_action_count=8, verified_step_return_count=8, verified_actor_record_count=9))
        write(self.run / "profile_summary.json", dict(passed=True))
        self.source = self.root / "source.txt"
        self.source.write_text("bound artificial source")
        self.console = self.root / "console.log"
        self.console.write_text("fixture")
        self._write_outer(self.outer, activity._execute_argv("karto_profile", self.freeze),
                          identity(100), 1_000_000_000, 20_000_000_000)
        write(self.final, dict(passed=True, absence_passed=True, activity_passed=True,
            kind="karto_profile", freeze=self.freeze, outer_reference=activity.record(self.outer),
            saved_identities=[identity(100), identity(101)]))
        self._write_outer(self.final_outer,
            activity._final_argv("karto_profile", self.run, self.outer, self.final),
            identity(200), 21_000_000_000, 22_000_000_000)

    def _write_outer(self, path, argv, child, start, end):
        source = activity.record(self.source)
        write(path, dict(scope="engineering", actual_waited=True, passed=True,
            actual_returncode=0, source_unchanged=True, source_before=[source], source_after=[source],
            errors=[], cwd=str(activity.W), actual_argv=argv, child_identity=child,
            coordinator_identity=identity(child["pid"] + 1), started_monotonic_ns=start,
            ended_monotonic_ns=end, actual_child_wait_seconds=str((end - start) // 10**9),
            console={"path": str(self.console), "sha256": activity.sha(self.console)}))

    def admit(self):
        return activity.profile_admission(self.freeze, self.outer, self.final, self.final_outer)

    def change(self, path, **fields):
        row = activity.read(path)
        row.update(fields)
        write(path, row)

    def test_complete_actual_wait_and_verified_prefix_admits_exact_block(self):
        result = self.admit()
        self.assertTrue(result["passed"])
        self.assertEqual(result["profile_actual_union_seconds"], "20")
        self.assertEqual(result["profile_observed_wall_seconds"], "21")
        self.assertEqual(len(result["profile_evidence_bindings"]), 10)
        self.assertEqual(result["minimum_remaining_seconds_after_reserved_block"], "2054.5762973333982")
        self.assertEqual(self.absence.call_count, 6)

    def test_profile_failure_prevents_behavior_before_output_or_phase(self):
        self.change(self.run / "activity_result.json", passed=False)
        with patch.object(activity, "check", return_value={}), patch.object(activity, "phase") as phase:
            with self.assertRaisesRegex(ValueError, "completely pass"):
                activity.execute("karto_behavior", self.freeze, (self.outer, self.final, self.final_outer))
            phase.assert_not_called()

    def test_success_label_cannot_hide_failed_actual_phase(self):
        path = self.run / "audit_actual_wait.json"
        self.change(path, actual_returncode=1)
        with self.assertRaisesRegex(ValueError, "actual wait"):
            self.admit()

    def test_raw_count_cannot_replace_verified_action_coverage(self):
        self.change(self.run / "independent_audit.json", verified_uniform_action_count=7)
        with self.assertRaisesRegex(ValueError, "raw/verified"):
            self.admit()

    def test_missing_external_wait_or_wrong_owner_rejected(self):
        with self.assertRaisesRegex(ValueError, "requires profile"):
            activity.profile_admission(self.freeze, self.outer, self.final, None)
        self.change(self.outer, child_identity=identity(999))
        with self.assertRaisesRegex(ValueError, "owner/timeline"):
            self.admit()

    def test_old_freeze_or_overbudget_profile_rejected(self):
        with self.assertRaisesRegex(ValueError, "completely pass"):
            activity.profile_admission("c" * 40, self.outer, self.final, self.final_outer)
        value = activity.read(self.final_outer)
        value.update(ended_monotonic_ns=703_000_000_000, actual_child_wait_seconds="682")
        write(self.final_outer, value)
        with self.assertRaisesRegex(ValueError, "cost"):
            self.admit()

    def test_tampered_bound_outer_source_rejected(self):
        self.source.write_text("changed")
        with self.assertRaisesRegex(ValueError, "bound current file"):
            self.admit()


class NativeManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sdk = self.root / "sdk"
        (self.sdk / "include/karto_sdk").mkdir(parents=True)
        self.header = self.sdk / "include/karto_sdk/Karto.h"
        self.cpp, self.adapter, self.karto = [self.root / name for name in ("native.cpp", "adapter.so", "sdk.so")]
        for path in (self.header, self.cpp, self.adapter, self.karto):
            path.write_bytes(path.name.encode())  # Artificial bytes, never loaded.
        self.receipt = self.root / "build.json"
        self.manifest = self.root / "manifest.json"
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        for name, path in (("ROOT", self.root), ("SDK", self.sdk), ("CPP", self.cpp),
                           ("ADAPTER", self.adapter), ("KARTO", self.karto),
                           ("BUILD_RECEIPT", self.receipt), ("MANIFEST", self.manifest)):
            self.stack.enter_context(patch.object(activity, name, path))
        sources = [activity.record(path) for path in
                   (self.cpp, self.header, self.karto, Path("/usr/bin/g++").resolve())]
        phases = []
        for i, name in enumerate(("compile", "adapter_cpu", "extra_cpu")):
            phases.append(dict(name=name, returncode=0, actual_waited=True, signals=[],
                identity_capture_error=None, reap_overrun=False, saved_identity=identity(300 + i)))
        for filename, count, phase in (("adapter_result_v1.json", 14, phases[1]),
                                       ("extra_result_v1.json", 10, phases[2])):
            write(self.root / filename, dict(passed=True, tests=count, failures=0, errors=0,
                                            identity=phase["saved_identity"]))
        write(self.receipt, dict(passed=True, source_unchanged=True, source_before=sources,
            source_after=deepcopy(sources), binary=activity.record(self.adapter), phases=phases))

    def test_three_waited_native_phases_and_both_raw_cpu_results_bind(self):
        result = activity.native_manifest(create=True)
        self.assertEqual(result["scan_budget"], 6300)
        self.assertEqual(result["artifacts"], [activity.record(self.adapter), activity.record(self.karto)])
        self.assertEqual(len(result["cpu_results"]), 2)
        self.assertFalse(result["qualification"])

    def test_adapter_or_sdk_current_bytes_cannot_be_substituted(self):
        activity.native_manifest(create=True)
        for path in (self.adapter, self.karto):
            raw = path.read_bytes()
            path.write_bytes(b"substituted")
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "bound current file"):
                activity.native_manifest()
            path.write_bytes(raw)

    def test_extra_cpu_failure_or_failed_wait_never_creates_manifest(self):
        self.extra = self.root / "extra_result_v1.json"
        value = activity.read(self.extra)
        value["passed"] = False
        write(self.extra, value)
        with self.assertRaisesRegex(ValueError, "raw CPU result"):
            activity.native_manifest(create=True)
        self.assertFalse(self.manifest.exists())


if __name__ == "__main__":
    unittest.main()
