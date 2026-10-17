"""Only v4/32 eligibility changes; fixed-source gates retain byte/AST evidence."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile
from types import ModuleType
import unittest

ASSETS = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
OLD = ASSETS / "20261017_mr3_p2a0_v4" / "independent"
PATCH_SPEC = {'angular': {'new': 'mr3_independent_angular_reset_matrix_v15.py',
             'new_sha256': '73128aed50763f6a50426bc2b7e0ce98bce6bfa6d8db3a560d265be5a6df8ae2',
             'old': 'mr3_independent_angular_reset_matrix_v1.py',
             'old_sha256': '6f4b0c3ce7b3cd2eba18c9e264c6d0cdc980ab486b5d235f1f2b06f7a8a774c1',
             'patches': [['"""Reset-only sampled angular bounds; stdlib, frozen diagnostic '
                          'consumer only."""',
                          '"""v15 workload adapter: v4/32 reset bounds, unchanged fixed '
                          'angular criteria."""'],
                         ['PROBE_VERSION = "mr3-p2a0-outward-cancel-v2"',
                          'PROBE_VERSION = "mr3-p2a0-outward-cancel-v4"'],
                         ['Path(__file__).with_name("mr3_independent_angular_interface_v1.py")',
                          'Path(__file__).resolve().parents[2] / "20261017_mr3_p2a0_v4" / '
                          '"independent" / "mr3_independent_angular_interface_v1.py"'],
                         ['"steps_per_episode": 20', '"steps_per_episode": 32'],
                         ['canonical([scene, seed, 20])', 'canonical([scene, seed, 32])'],
                         ['len(transitions) == 21', 'len(transitions) == 33'],
                         ['twenty actual nonterminal reset-step records',
                          'thirty-two actual nonterminal reset-step records']]},
 'physical': {'additions': [['import argparse\n', 'import argparse\nimport gzip\n'],
                            ['CONSUMER_SHA256 = '
                             '"2516e394f60eac5dd24fd66b51c4c48fc37245090eb1626ebe1c7a3a23f8bafb"\n',
                             'CONSUMER_SHA256 = '
                             '"2516e394f60eac5dd24fd66b51c4c48fc37245090eb1626ebe1c7a3a23f8bafb"\n'
                             'CONSUMER_PATH = (Path(__file__).resolve().parents[2] / '
                             '"20261017_mr3_p2a0_v3"\n'
                             '                 / "independent" / '
                             '"mr3_independent_physics_review.py")\n'],
                            ['    require(re.fullmatch(r"[0-9a-f]{40}", freeze), "exact '
                             'freeze required")\n',
                             '    require(re.fullmatch(r"[0-9a-f]{40}", freeze), "exact '
                             'freeze required")\n'
                             '    require(sha(CONSUMER_PATH) == CONSUMER_SHA256, "immutable '
                             'physical consumer SHA mismatch")\n']],
              'eligibility_block': '        # New workload eligibility only; the physical '
                                   'response/closure pool below is unchanged.\n'
                                   '        variants = [path for path in (directory / '
                                   '"transitions.jsonl",\n'
                                   '                    directory / "transitions.jsonl.gz") '
                                   'if path.is_file()]\n'
                                   '        require(len(variants) == 1, "missing/ambiguous v4 '
                                   'reset transitions")\n'
                                   '        transition_path = variants[0]\n'
                                   '        transition_raw = transition_path.read_bytes()\n'
                                   '        transition_data = '
                                   '(gzip.decompress(transition_raw) if '
                                   'transition_path.suffix == ".gz"\n'
                                   '                           else transition_raw)\n'
                                   '        require(transition_data.endswith(b"\\n"), '
                                   '"incomplete v4 reset transitions")\n'
                                   '        transitions = [json.loads(line) for line in '
                                   'transition_data.splitlines()]\n'
                                   '        require(len(transitions) == 33 and '
                                   'transitions[0]["kind"] == "reset"\n'
                                   '                and all(item["kind"] == "step" for item '
                                   'in transitions[1:])\n'
                                   '                and all(item["terminated"] is False and '
                                   'item["truncated"] is False\n'
                                   '                        for item in transitions[1:-1])\n'
                                   '                and transitions[-1]["terminated"] is '
                                   'False\n'
                                   '                and transitions[-1]["truncated"] is True\n'
                                   '                and transitions[-1]["info"]["reason"] == '
                                   '"external_sampler_limit",\n'
                                   '                "v4 reset requires one actual reset and32 '
                                   'nonterminal steps ending external truncation")\n'
                                   '        proof["/".join(identity) + "/transitions"] = {\n'
                                   '            "path": str(transition_path), "bytes": '
                                   'len(transition_raw),\n'
                                   '            "sha256": '
                                   'hashlib.sha256(transition_raw).hexdigest()}\n',
              'new': 'mr3_independent_physics_matrix_v15.py',
              'new_sha256': 'fa988a29465f928eb425f626f246b85f36ddee5bc168c24ffce9d125e7a51754',
              'old': 'mr3_independent_physics_matrix_v4.py',
              'old_sha256': 'c6dcad54743a2d04ce64dd3f4feb329b1a4e3116b384f9269db342df4f6fa655',
              'patches': [['"""Version 2: predeclared 20-step outward/cancel reset aggregate; '
                           'same frozen physical criteria."""',
                           '"""v15 workload adapter: v4/32 reset aggregate, unchanged fixed '
                           'physical criteria."""'],
                          ['PROBE_VERSION = "mr3-p2a0-outward-cancel-v2"',
                           'PROBE_VERSION = "mr3-p2a0-outward-cancel-v4"'],
                          ['source["steps_per_episode"] == 20',
                           'source["steps_per_episode"] == 32'],
                          ['"steps_per_episode": 20', '"steps_per_episode": 32'],
                          ['predeclared v2 probe reset-only eight-episode/20-step aggregate',
                           'predeclared v4 probe reset-only eight-episode/32-step '
                           'aggregate']]}}


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ANGULAR = load_module("mr3_independent_angular_reset_matrix_v15",
                      HERE / "mr3_independent_angular_reset_matrix_v15.py")
PHYSICAL = load_module("mr3_independent_physics_matrix_v15",
                       HERE / "mr3_independent_physics_matrix_v15.py")
ANGULAR_CONSUMER = OLD / "mr3_independent_angular_interface_v1.py"


class WorkloadConstants(ast.NodeTransformer):
    def visit_Constant(self, node):
        mapping = {20: 32, 21: 33, 19: 31, 400: 640, 401: 641,
                   30_000_000_000: 42_000_000_000}
        if type(node.value) in (int, float) and node.value in mapping:
            # Float-workload mutations stay float and must still be rejected.
            value = mapping[node.value]
            if type(node.value) is float:
                value = float(value)
            return ast.copy_location(ast.Constant(value=value), node)
        if node.value == "mr3_independent_angular_reset_matrix_v1.py":
            return ast.copy_location(ast.Constant(value="mr3_independent_angular_reset_matrix_v15.py"), node)
        return node

    def visit_ImportFrom(self, node):
        if node.module == "mr3_independent_physics_matrix_v4":
            node.module = "mr3_independent_physics_matrix_v15"
        return node


def adapted_original_tests(filename, expected_sha):
    path = OLD / filename
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha:
        raise ValueError("exact original test source changed")
    tree = ast.fix_missing_locations(WorkloadConstants().visit(ast.parse(raw)))
    module = ModuleType("adapted_" + path.stem)
    module.__file__ = str(Path(__file__))
    exec(compile(tree, str(path), "exec"), module.__dict__)
    return module


ANGULAR_TESTS = adapted_original_tests(
    "mr3_independent_angular_reset_matrix_v1_tests.py",
    "051a7c46ff62ab6a55746bd0affea65accdf1eda1a77398e6f93ec3cda26f691")
ANGULAR_TESTS.CONSUMER = ANGULAR_CONSUMER
PHYSICAL_TESTS = adapted_original_tests(
    "mr3_independent_physics_matrix_v4_tests.py",
    "4082ca7e8149881ee94ccc99cce2d2262563232efd801bb9f4243b35dcfa6988")
ORIGINAL_PHYSICAL_FIXTURE = PHYSICAL_TESTS.fixture


def physical_fixture(directory):
    path, report = ORIGINAL_PHYSICAL_FIXTURE(directory)
    for episode in report["episodes"]:
        target = Path(episode["directory"])
        rows = [{"kind": "reset", "info": {"epoch": episode["epoch"]}}]
        rows += [{"kind": "step", "terminated": False, "truncated": index == 31,
                  "info": {"reason": "external_sampler_limit" if index == 31 else ""}}
                 for index in range(32)]
        (target / "transitions.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return path, report


PHYSICAL_TESTS.fixture = physical_fixture
# These are the complete original suites, with only workload constants/import
# paths adapted and mandatory33-record raw fixtures added for the new gate.
AngularOriginalGateTests = ANGULAR_TESTS.AngularResetMatrixMutationTests
PhysicalOriginalGateTests = PHYSICAL_TESTS.MatrixTests


def mutate(path, update):
    value = json.loads(path.read_text())
    update(value)
    path.write_text(json.dumps(value))


class V8EligibilityAndEquivalenceTests(unittest.TestCase):
    def test_reversible_text_and_ast_prove_nonworkload_gates_unchanged(self):
        for kind, item in PATCH_SPEC.items():
            with self.subTest(kind=kind):
                original = (OLD / item["old"]).read_text()
                current = (HERE / item["new"]).read_text()
                self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), item["old_sha256"])
                self.assertEqual(hashlib.sha256(current.encode()).hexdigest(), item["new_sha256"])
                normalized = current
                if kind == "physical":
                    self.assertEqual(normalized.count(item["eligibility_block"]), 1)
                    normalized = normalized.replace(item["eligibility_block"], "")
                    for before, after in reversed(item["additions"]):
                        self.assertEqual(normalized.count(after), 1)
                        normalized = normalized.replace(after, before)
                for before, after in reversed(item["patches"]):
                    self.assertIn(after, normalized)
                    normalized = normalized.replace(after, before)
                self.assertEqual(normalized, original)
                self.assertEqual(ast.dump(ast.parse(normalized), include_attributes=False),
                                 ast.dump(ast.parse(original), include_attributes=False))

    def test_explicit_fixed_immutable_sources(self):
        self.assertEqual(ANGULAR.CONSUMER_SHA256,
                         "7a472ba7efdd55addc710b98c66c89feff7f5092f214f76fd76cd4ca526343d0")
        self.assertEqual(PHYSICAL.CONSUMER_SHA256,
                         "2516e394f60eac5dd24fd66b51c4c48fc37245090eb1626ebe1c7a3a23f8bafb")
        self.assertEqual(hashlib.sha256(PHYSICAL.CONSUMER_PATH.read_bytes()).hexdigest(),
                         PHYSICAL.CONSUMER_SHA256)
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            ANGULAR_TESTS.fixture(root)
            # Default resolution is the old immutable consumer, not a missing
            # v15 sibling with a similar name.
            result = ANGULAR.audit(root, "a" * 40)
            self.assertTrue(result["passed"], result["errors"])
            self.assertEqual(Path(result["angular_consumer"]["path"]), ANGULAR_CONSUMER)

    def test_old_v2_twenty_step_workload_is_ineligible_for_both(self):
        for field, value in (("steps_per_episode", 20),
                             ("preparation_probe_version", "mr3-p2a0-outward-cancel-v2")):
            for kind in ("angular", "physical"):
                with self.subTest(field=field, kind=kind), tempfile.TemporaryDirectory() as name:
                    root = Path(name)
                    if kind == "angular":
                        ANGULAR_TESTS.fixture(root)
                    else:
                        report_path, _ = physical_fixture(root)
                    for filename in ("benchmark_metadata.json", "benchmark_summary.json"):
                        mutate(root / filename, lambda data: data.update({field: value}))
                    if kind == "angular":
                        self.assertFalse(ANGULAR.audit(root, "a" * 40)["passed"])
                    else:
                        with self.assertRaises(ValueError):
                            PHYSICAL.audit(root, report_path, "a" * 40)

    def test_old_v3_32_workload_is_rejected_by_new_v4_dispatch(self):
        for kind in ("angular", "physical"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                if kind == "angular":
                    ANGULAR_TESTS.fixture(root)
                else:
                    report_path, _ = physical_fixture(root)
                for filename in ("benchmark_metadata.json", "benchmark_summary.json"):
                    mutate(root / filename, lambda value: value.update({
                        "preparation_probe_version": "mr3-p2a0-outward-cancel-v3"}))
                if kind == "angular":
                    self.assertFalse(ANGULAR.audit(root, "a" * 40)["passed"])
                else:
                    with self.assertRaises(ValueError):
                        PHYSICAL.audit(root, report_path, "a" * 40)

    def test_physical_requires_exact33_raw_records_and_external_truncation(self):
        for fault in ("short", "mixed20", "terminal", "early", "reason"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                report_path, _ = physical_fixture(root)
                target = root / "worker1/episode004_corridors_101/transitions.jsonl"
                rows = [json.loads(line) for line in target.read_text().splitlines()]
                if fault == "short":
                    rows.pop()
                elif fault == "mixed20":
                    rows = rows[:21]
                elif fault == "terminal":
                    rows[-1].update(terminated=True)
                elif fault == "early":
                    rows[12].update(truncated=True)
                else:
                    rows[-1]["info"]["reason"] = "unplanned"
                target.write_text("".join(json.dumps(row) + "\n" for row in rows))
                with self.assertRaises(ValueError):
                    PHYSICAL.audit(root, report_path, "a" * 40)

    def test_physical_raw_transition_hash_and_gzip_are_preserved(self):
        import gzip
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            report_path, _ = physical_fixture(root)
            target = root / "worker0/episode001_open_101/transitions.jsonl"
            encoded = gzip.compress(target.read_bytes(), mtime=0)
            Path(str(target) + ".gz").write_bytes(encoded)
            target.unlink()
            result = PHYSICAL.audit(root, report_path, "a" * 40)
            self.assertTrue(result["passed"])
            proof = result["artifact_proof"]["worker0/episode001_open_101/transitions"]
            self.assertEqual(proof["sha256"], hashlib.sha256(encoded).hexdigest())
            self.assertEqual(proof["bytes"], len(encoded))

    def test_missing_eighth_or_one_bad_original_gate_still_fails(self):
        for fault in ("missing_directory", "closure", "no_robot_stop"):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as name:
                root = Path(name)
                report_path, report = physical_fixture(root)
                if fault == "missing_directory":
                    shutil.rmtree(root / "worker1/episode004_corridors_101")
                    with self.assertRaises(ValueError):
                        PHYSICAL.audit(root, report_path, "a" * 40)
                    continue
                if fault == "closure":
                    report["episodes"][7]["closure"]["checks"]["all_native"] = False
                else:
                    for episode in report["episodes"]:
                        robot = episode["robots"]["tb1"]
                        robot.update(stop_responses=[], eligible_stop_events=0,
                                     credited_sampled_stop_events=0)
                report_path.write_text(json.dumps(report))
                result = PHYSICAL.audit(root, report_path, "a" * 40)
                self.assertFalse(result["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
