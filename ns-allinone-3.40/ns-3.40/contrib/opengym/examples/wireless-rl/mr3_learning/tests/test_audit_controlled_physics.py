"""Shared engineering/PPO dispatch consumes unchanged native physics math."""

import ast
import copy
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import audit_controlled_physics as shared, audit_motion, audit_ppo
from mr3_learning import audit_preparation
from mr3_learning.audit_motion import _audit_records
from mr3_learning.tests.test_audit_motion import write_files
from mr3_learning.tests import test_audit_preparation as preparation_tests


class SharedControlledPhysicsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        preparation_tests.ControlledPreparationTests.setUpClass()
        cls.fixture = preparation_tests.ControlledPreparationTests()
        cls.original = staticmethod(preparation_tests.ControlledPreparationTests.original_physics)

    def test_shared_module_imports_with_stdlib_only_and_prep_reexports_same_rules(self):
        subprocess.run([
            sys.executable, "-S", "-c",
            "import sys; from mr3_learning import audit_controlled_physics; "
            "assert 'torch' not in sys.modules and 'numpy' not in sys.modules; "
            "assert 'mr3_learning.audit_ppo' not in sys.modules",
        ], check=True, cwd=Path(audit_ppo.__file__).parent.parent)
        for name in ("controlled_bootstrap", "dispatch_controlled_physics",
                     "verify_motion_artifacts"):
            self.assertIs(getattr(audit_preparation, name), getattr(shared, name))

    def test_episode_entry_keeps_full_math_rows_release_and_capacity_unchanged(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory, files, motion = self.fixture.setup_episode(Path(temporary))
            rows, epoch, release = files["physics.jsonl"], files["metadata.json"]["epoch"], \
                1_020_000_000
            saved = copy.deepcopy(rows)
            capacity = object()
            auditor = SimpleNamespace(audit_physics=self.original,
                                      comparison_statistics=capacity)
            original = shared.dispatch_controlled_physics(
                auditor, [directory], {directory: motion})
            result = auditor.audit_physics(rows, epoch, release)
            self.assertIs(original, self.original)
            self.assertIs(auditor.comparison_statistics, capacity)
            self.assertEqual(rows, saved)
            self.assertEqual(result["total_physical_ticks"], 60)
            self.assertEqual(result["controlled_bootstrap"]["actual_task_release_time_ns"],
                             release)
            for protocol in (None, "unreviewed-phase"):
                if protocol is None:
                    files["metadata.json"].pop("execution_phase_protocol")
                else:
                    files["metadata.json"]["execution_phase_protocol"] = protocol
                write_files(directory, files)
                auditor.audit_physics = self.original
                shared.dispatch_controlled_physics(auditor, [directory], {})
                with self.assertRaises(ValueError):
                    auditor.audit_physics(rows, epoch, release)

    def ppo_call_block(self):
        """Execute the actual call-scoped PPO wiring without a learner/model.

        Only the phase traverser is a fixture: it invokes the original native
        math. The real shared dispatch, motion consumer, and finally run.
        """
        tree = ast.parse(Path(audit_ppo.__file__).read_text())
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == "audit_run")
        for container in ast.walk(function):
            if not isinstance(container, ast.Try) or not container.finalbody:
                continue
            if any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                   and node.func.attr == "corrected_audit" for node in ast.walk(container)):
                self.assertEqual(len(container.body), 2)
                self.assertEqual(len(container.finalbody), 2)
                # Dispatch assignment is immediately before this exact try.
                parent = next(node for node in ast.walk(function)
                              if isinstance(getattr(node, "body", None), list)
                              and container in node.body)
                index = parent.body.index(container)
                return compile(ast.Module(body=parent.body[index - 3:index] + [container],
                                          type_ignores=[]), audit_ppo.__file__, "exec")
        self.fail("PPO native call has no call-scoped restoration")

    def test_real_ppo_call_layer_dispatches_episode_and_restores_on_success_and_error(self):
        block = self.ppo_call_block()
        with tempfile.TemporaryDirectory() as temporary:
            directory, files, _ = self.fixture.setup_episode(Path(temporary))
            capacity = object()

            def original_readiness(*args):
                return {"required": False, "proven": False}
            auditor = SimpleNamespace(audit_physics=self.original,
                                      audit_initial_inputs_ready=original_readiness,
                                      comparison_statistics=capacity)
            for fail_after_math in (False, True):
                def traverse(base, actual_auditor, command, directories):
                    self.assertIs(actual_auditor, auditor)
                    self.assertEqual(directories, [directory])
                    result = actual_auditor.audit_physics(
                        files["physics.jsonl"], files["metadata.json"]["epoch"], 1_020_000_000)
                    self.assertEqual(result["total_physical_ticks"], 60)
                    if fail_after_math:
                        raise RuntimeError("fixture phase failure after real native math")
                    return result

                namespace = {"dispatch_controlled_physics": shared.dispatch_controlled_physics,
                             "dispatch_controlled_readiness": shared.dispatch_controlled_readiness,
                             "native_auditor": auditor, "native": directory,
                             "phase": SimpleNamespace(corrected_audit=traverse),
                             "base": object(), "command": object(), "row": {}}
                # Synthetic metadata has no claimed committed freeze. Inject
                # only its real pure helper at the frozen-loader seam; replay
                # every actual raw/provenance check rather than mocking PASS.
                with patch.object(audit_motion, "load_frozen_helper",
                                  return_value=(self.fixture.helper, {})):
                    if fail_after_math:
                        with self.assertRaisesRegex(RuntimeError, "after real native math"):
                            exec(block, namespace)
                    else:
                        exec(block, namespace)
                        self.assertIn("controlled_bootstrap", namespace["row"]["native"])
                self.assertIs(auditor.audit_physics, self.original)
                self.assertIs(auditor.audit_initial_inputs_ready, original_readiness)
                self.assertIs(auditor.comparison_statistics, capacity)

    def test_second_installer_error_still_restores_both_original_callables(self):
        block = self.ppo_call_block()
        with tempfile.TemporaryDirectory() as temporary:
            directory, _, _ = self.fixture.setup_episode(Path(temporary))
            original_readiness = object()
            auditor = SimpleNamespace(audit_physics=self.original,
                                      audit_initial_inputs_ready=original_readiness)

            def broken(*args):
                raise ValueError("fixture readiness installer error")
            namespace = {"dispatch_controlled_physics": shared.dispatch_controlled_physics,
                         "dispatch_controlled_readiness": broken,
                         "native_auditor": auditor, "native": directory}
            with self.assertRaisesRegex(ValueError, "installer error"):
                exec(block, namespace)
            self.assertIs(auditor.audit_physics, self.original)
            self.assertIs(auditor.audit_initial_inputs_ready, original_readiness)

    def test_controlled_dispatch_cannot_bypass_original_integer_quantum_math(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory, files, _ = self.fixture.setup_episode(Path(temporary))
            # The bootstrap remains valid. A later actual helper iteration
            # count no longer agrees with its unchanged duration/tick count.
            files["physics.jsonl"][-1]["end_iterations"] += 1
            write_files(directory, files)
            motion = _audit_records(directory, self.fixture.helper, {})
            auditor = SimpleNamespace(audit_physics=self.original)
            shared.dispatch_controlled_physics(auditor, [directory], {directory: motion})
            with self.assertRaisesRegex(ValueError, "tick|iteration"):
                auditor.audit_physics(files["physics.jsonl"],
                                      files["metadata.json"]["epoch"], 1_020_000_000)


if __name__ == "__main__":
    unittest.main()
