"""Synthetic offline-analysis admission checks; no actual v7 run inputs."""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("v7_analysis_test", HERE / "v7_analysis_driver.py")
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


def matrix_fixture():
    return {"passed": True, "errors": [], "benchmarks": [{} for _ in range(6)],
            "offline_contact_phase_audit": {"freeze": D.FREEZE}}


def journal_fixture(matrix_sha):
    rows = [{"kind": "command_complete", "freeze": D.FREEZE, "stage": name,
             "role": "native", "returncode": 0} for name in D.STAGES]
    rows += [{"kind": "stage_all_declared_gates_passed", "freeze": D.FREEZE,
              "stage": name} for name in D.GROUPS]
    return rows + [{"kind": "all_eight_stages_and_declared_audits_complete", "freeze": D.FREEZE,
                    "matrix_sha256": matrix_sha}]


class AnalysisDriverTests(unittest.TestCase):
    def test_default_only_builds_commands_without_opening_run_results(self):
        with patch.object(D, "read", side_effect=AssertionError("result read")), patch.object(
                D, "closed_execution", side_effect=AssertionError("journal read")), patch.object(
                D, "execute", side_effect=AssertionError("execution")), contextlib.redirect_stdout(
                io.StringIO()) as output:
            self.assertEqual(D.main([]), 0)
        self.assertFalse(json.loads(output.getvalue())["reads_run_results"])

    def test_resource_has_no_invented_freeze_flag_and_reset_has_exact_binding(self):
        directories, jobs = D.commands(Path("/synthetic"))
        self.assertEqual(len(directories), 7)
        self.assertEqual([name for name, _ in jobs], ["resource", "reset"])
        self.assertNotIn("--freeze", jobs[0][1])
        self.assertEqual(jobs[1][1][jobs[1][1].index("--freeze") + 1], D.FREEZE)
        self.assertEqual(jobs[1][1][jobs[1][1].index("--implementation-checks-sha256") + 1],
                         D.CHECKS_SHA)

    def test_execution_requires_an_explicit_binding_identity(self):
        with self.assertRaises(SystemExit):
            D.main(["--execute"])

    def check_closed(self, mutate=None):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            matrix = directory / "matrix.json"
            matrix.write_text(json.dumps(matrix_fixture()))
            rows = journal_fixture(D.sha(matrix))
            if mutate:
                mutate(rows, matrix)
            journal = directory / "execution.jsonl"
            journal.write_text("".join(json.dumps(row) + "\n" for row in rows))
            return D.closed_execution(journal, matrix)

    def test_all_eight_closed_with_matching_final_matrix_is_admitted(self):
        self.assertIn("journal_sha256", self.check_closed())

    def test_live_partial_or_failed_execution_is_rejected(self):
        def missing(rows, matrix):
            rows.pop()

        def failure(rows, matrix):
            rows[0]["returncode"] = 1

        def absent_stage(rows, matrix):
            rows.pop(3)

        def interrupted(rows, matrix):
            rows.insert(0, {"kind": "command_interrupted_or_failed", "freeze": D.FREEZE})

        def wrong_freeze(rows, matrix):
            rows[0]["freeze"] = "old-freeze"

        def missing_gate(rows, matrix):
            rows.pop(8)

        for mutate in (missing, failure, absent_stage, interrupted, wrong_freeze, missing_gate):
            with self.subTest(mutate=mutate.__name__), self.assertRaises(ValueError):
                self.check_closed(mutate)

    def test_changed_or_failed_matrix_does_not_inherit_the_completion_marker(self):
        def changed(rows, matrix):
            matrix.write_text(matrix.read_text() + " ")

        def failed(rows, matrix):
            value = matrix_fixture()
            value["passed"] = False
            matrix.write_text(json.dumps(value))
            rows[-1]["matrix_sha256"] = D.sha(matrix)

        for mutate in (changed, failed):
            with self.subTest(mutate=mutate.__name__), self.assertRaises(ValueError):
                self.check_closed(mutate)

    def resource_fixture(self):
        directories, _ = D.commands(Path("/synthetic"))
        rows = []
        expected = {"workers1": 32, "workers2": 64, "workers4": 128}
        for name, directory in zip(D.GROUPS, directories):
            comparison = ({"eligible": True, "transitions": expected[name],
                           "denominator_wall_sec": 500.} if name in expected else
                          {"eligible": False})
            rows.append({"directory": str(directory), "summary_passed": True,
                         "fair_comparison": comparison})
        value = {"freezes": [D.FREEZE], "mixed_freeze_warning": False, "benchmarks": rows}
        return value, directories

    def test_resource_scope_keeps_only_normal_first_two_cells_comparable(self):
        value, directories = self.resource_fixture()
        D.resource_gate(value, directories)

    def test_other_freeze_failed_stage_or_diagnostic_rate_is_rejected(self):
        for case in ("freeze", "mixed", "missing", "failed", "terminal", "count"):
            with self.subTest(case=case):
                original, directories = self.resource_fixture()
                value = copy.deepcopy(original)
                if case == "freeze":
                    value["freezes"] = ["old"]
                elif case == "mixed":
                    value["mixed_freeze_warning"] = True
                elif case == "missing":
                    value["benchmarks"].pop()
                elif case == "failed":
                    value["benchmarks"][0]["summary_passed"] = False
                elif case == "terminal":
                    value["benchmarks"][1]["fair_comparison"]["eligible"] = True
                else:
                    value["benchmarks"][4]["fair_comparison"]["transitions"] = 127
                with self.assertRaises(ValueError):
                    D.resource_gate(value, directories)

    def test_existing_output_is_preserved_before_reading_any_run_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / D.ASSETS / "resource_analysis_v7.json"
            output.parent.mkdir(parents=True)
            output.write_text("immutable previous result")
            with patch.object(D, "closed_execution", side_effect=AssertionError("run read")):
                with self.assertRaisesRegex(ValueError, "output already exists"):
                    D.execute(root, "a" * 64)
            self.assertEqual(output.read_text(), "immutable previous result")


if __name__ == "__main__":
    unittest.main()
