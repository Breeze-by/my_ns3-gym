"""Artificial archive dispatch and real system-Python dependency regression.

No World/Node/native collection: the positive CLI input is one artificial reset
with seven references to a small hand-written map, built by the existing fixture.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mr3_learning import audit_reach_preparation as audit
from mr3_learning import audit_reach_ppo, reach_policy_chain


FREEZE = "a" * 40
SEED = "exact-point-bridge-v2"
START = "point-attachment-3x3-v1"


class SystemExactReplayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "artificial"
        self.directory.mkdir()
        self.metadata = {"freeze": FREEZE, "epoch": "artificial", "seed_rule": SEED,
                         "start_graph_rule": START}
        self.write_metadata()

    def write_metadata(self):
        (self.directory / "metadata.json").write_text(json.dumps(self.metadata))

    def valid_result(self):
        raw = (self.directory / "metadata.json").read_bytes()
        return {"schema": audit.EXACT_REPLAY_SCHEMA, "passed": True, "errors": [],
            "freeze": FREEZE, "episode": str(self.directory.resolve()), "seed_rule": SEED,
            "start_graph_rule": START, "whole_observation_and_seven_map_replay_passed": True,
            "exact_full_snapshot_replays": 1,
            "source_proof": {"artificial_source.py": {"sha256": "b" * 64,
                "git_source": FREEZE + ":artificial_source.py"}},
            "input_bindings": {str(self.directory / "metadata.json"): {
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}}}

    @staticmethod
    def identity(pid):
        return {"pid": pid, "start_ticks": 111 if pid == os.getpid() else 222,
                "parent": os.getppid() if pid == os.getpid() else os.getpid(),
                "group": 1, "session": 1, "state": "R"}

    def replay(self, result=None, *, rc=0, raw=None, mutate_metadata=False, wait=None):
        child = SimpleNamespace(pid=43210, wait=wait or Mock(return_value=rc))

        def launch(argv, **kwargs):
            self.assertEqual(argv[:5], ["/usr/bin/python3", "-B", "-m",
                                       "mr3_learning.audit_seed_inputs", "--episode"])
            self.assertEqual(kwargs["cwd"], audit.WIRELESS)
            self.assertNotIn("PYTHONPATH", kwargs["env"])
            self.assertNotIn("PYTHONHOME", kwargs["env"])
            self.assertEqual(kwargs["env"]["PYTHONNOUSERSITE"], "1")
            output = Path(argv[argv.index("--output") + 1])
            self.assertFalse(output.exists())
            if raw is not None:
                output.write_bytes(raw)
            elif result is not None:
                output.write_text(json.dumps(result))
            kwargs["stdout"].write(b"artificial child console\n")
            if mutate_metadata:
                (self.directory / "metadata.json").write_text('{"changed":true}')
            return child

        with patch.object(audit.subprocess, "Popen", side_effect=launch) as popen, \
                patch.object(audit, "identity", side_effect=self.identity):
            value = audit.audit_exact_seed_inputs_system(self.directory,
                seed_rule=SEED, start_graph_rule=START)
        return value, popen, child

    def test_positive_contract_preserves_full_proofs_actual_wait_and_removes_only_temporary_files(self):
        expected = self.valid_result()
        with patch.dict(os.environ, {"PYTHONPATH": "/poison", "PYTHONHOME": "/poison"}):
            result, popen, child = self.replay(expected)
        self.assertTrue(result["passed"])
        self.assertEqual({key: result[key] for key in expected}, expected)
        receipt = result["system_python_execution"]
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(receipt["returncode"], 0)
        self.assertEqual(receipt["child_identity"]["pid"], child.pid)
        self.assertEqual(receipt["child_identity"]["parent"], os.getpid())
        self.assertEqual(json.loads(receipt["result_json"]), expected)
        self.assertEqual(hashlib.sha256(receipt["result_json"].encode()).hexdigest(), receipt["result_sha256"])
        self.assertFalse(Path(receipt["temporary_output"]).exists())
        self.assertTrue(receipt["temporary_files_removed"])
        self.assertEqual(receipt["errors"], [])
        self.assertGreater(receipt["ended_monotonic_ns"], receipt["started_monotonic_ns"])
        child.wait.assert_called_once()
        popen.assert_called_once()
        # Policy binding traversal must not treat a removed temp output as a
        # retained evidence file; the original input bindings remain real.
        bindings = {}
        reach_policy_chain._report_bindings(result, bindings, audit.WIRELESS)
        self.assertIn(str(self.directory / "metadata.json"), bindings)

    def test_false_pass_wrong_identity_or_missing_full_evidence_is_never_accepted(self):
        variants = [("schema", "other"), ("passed", 1), ("errors", ["failed"]),
            ("freeze", "b" * 40), ("episode", str(self.directory / "other")),
            ("seed_rule", "exact-point-bridge-v1"), ("start_graph_rule", "original-seed-cell"),
            ("whole_observation_and_seven_map_replay_passed", False),
            ("exact_full_snapshot_replays", 0), ("exact_full_snapshot_replays", True),
            ("source_proof", {}), ("input_bindings", {})]
        for key, value in variants:
            with self.subTest(key=key, value=value):
                report = self.valid_result(); report[key] = value
                result, _, _ = self.replay(report)
                self.assertFalse(result["passed"])
                self.assertTrue(result["errors"])
                self.assertTrue(result["system_python_execution"]["actual_waited"])

    def test_nonzero_child_missing_output_or_invalid_json_preserves_failure_receipt(self):
        for rc, raw, report in [(1, None, self.valid_result()), (0, None, None),
                (0, b'{"passed":true,"passed":false}', None),
                (0, b'{"value":NaN}', None), (0, b'not json', None)]:
            with self.subTest(rc=rc, raw=raw):
                result, _, _ = self.replay(report, rc=rc, raw=raw)
                self.assertFalse(result["passed"])
                receipt = result["system_python_execution"]
                self.assertTrue(receipt["actual_waited"])
                self.assertEqual(receipt["returncode"], rc)
                self.assertEqual(receipt["stdout_stderr"], "artificial child console\n")
                if raw is not None:
                    self.assertEqual(receipt["result_bytes"], len(raw))

    def test_launch_failure_is_a_failed_archive_gate_with_no_invented_wait(self):
        with patch.object(audit.subprocess, "Popen", side_effect=OSError("cannot exec")), \
                patch.object(audit, "identity", side_effect=self.identity):
            result = audit.audit_exact_seed_inputs_system(self.directory,
                seed_rule=SEED, start_graph_rule=START)
        self.assertFalse(result["passed"])
        self.assertFalse(result["system_python_execution"]["actual_waited"])
        self.assertIsNone(result["system_python_execution"]["child_identity"])
        self.assertIn("cannot exec", " ".join(result["errors"]))

    def test_interrupted_wait_is_drained_but_cannot_claim_a_clean_pass(self):
        wait = Mock(side_effect=[KeyboardInterrupt(), 0])
        result, _, _ = self.replay(self.valid_result(), wait=wait)
        self.assertFalse(result["passed"])
        self.assertTrue(result["system_python_execution"]["actual_waited"])
        self.assertEqual(wait.call_count, 2)

    def test_metadata_change_during_child_is_rejected(self):
        result, _, _ = self.replay(self.valid_result(), mutate_metadata=True)
        self.assertFalse(result["passed"])
        self.assertIn("metadata changed", " ".join(result["errors"]))

    def test_wrong_declared_rules_refuse_before_submitting_any_child(self):
        self.metadata["seed_rule"] = "exact-point-bridge-v1"; self.write_metadata()
        with patch.object(audit.subprocess, "Popen") as popen:
            result = audit.audit_exact_seed_inputs_system(self.directory,
                seed_rule=SEED, start_graph_rule=START)
        self.assertFalse(result["passed"])
        popen.assert_not_called()

    def test_legacy_load_keeps_original_archives_and_exact_hook_is_shared_by_ppo(self):
        plan = Path(self.temporary.name) / "plan.json"
        original = Mock(return_value={"passed": True, "unique_maps": 1})
        module = SimpleNamespace(audit_archives=original,
            audit_activity=Mock(return_value={"passed": True}),
            audit_execution_inputs=Mock(return_value={"passed": True}))
        plan.write_text('{}')
        with patch.object(audit, "project_module", return_value=(module, {})), \
                patch.object(audit, "audit_exact_seed_inputs_system") as replay:
            loaded, _ = audit.load_impl(plan)
            self.assertIs(loaded.audit_archives, original)
            replay.assert_not_called()
        plan.write_text(json.dumps({"seed_rule": SEED, "start_graph_rule": START}))
        failed = {"schema": audit.EXACT_REPLAY_SCHEMA, "passed": False,
                  "errors": ["artificial system child failure"], "system_python_execution": {"actual_waited": True}}
        with patch.object(audit, "project_module", return_value=(module, {})), \
                patch.object(audit, "audit_exact_seed_inputs_system", return_value=failed) as replay:
            loaded, _ = audit.load_impl(plan)
            archives = loaded.audit_archives(self.directory)
            self.assertFalse(archives["passed"])
            self.assertEqual(archives["exact_seed_full_replay"], failed)
            shared = {"passed": True, "errors": [], "safety_contract": "mr3-reach-v1", "freeze": FREEZE}
            runtime = {"passed": True, "errors": [], "contract": "mr3-reach-v1", "freeze": FREEZE,
                       "independent_necessary_replay": True, "continuous_physical_model_proved": False}
            with patch.object(audit_reach_ppo.audit_reach_information, "audit_episode", return_value=shared), \
                    patch.object(audit_reach_ppo.audit_reach_peer_control, "audit_episode", return_value=shared), \
                    patch.object(audit_reach_ppo.audit_reach_runtime, "audit_episode", return_value=runtime):
                conjunction = audit_reach_ppo.audit_episode_conjunction(self.directory, FREEZE, loaded)
            self.assertFalse(conjunction["passed"])
            self.assertFalse(conjunction["observation_archives"]["passed"])
            self.assertIn("observation_archives: observation_archives independent gate failed", conjunction["errors"])
            self.assertEqual(replay.call_count, 2)

    def test_actual_system_child_replays_artificial_frozen_observation_and_scipy_without_poison(self):
        # Construction and replay are both system Python, not the conda parent.
        # Freeze exact current source bytes in an isolated real Git repository.
        # The main checkout may contain pending edits; no Git/source gate is
        # mocked and no historical native freeze is reused for this fixture.
        root = Path(audit.__file__).resolve().parents[7]
        wireless_relative = audit.WIRELESS.relative_to(root)
        learner = wireless_relative / "mr3_learning"
        component = Path("ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration")
        relatives = [learner / name for name in (
            "__init__.py", "audit_seed_inputs.py", "navigation_archive.py", "reach_gates.py",
            "reach_audit_projection.py", "audit_reach_sensor_model.py", "native_custody.py",
            "supervisor.py", "ipc.py", "tests/__init__.py", "tests/test_audit_seed_inputs.py")]
        relatives += [component / name for name in (
            "__init__.py", "mr3_observation.py", "mr3_episode.py", "mr3_seed_certificate.py",
            "mr3_reach_geometry.py", "mr3_point_graph.py")]
        relatives.append(Path("ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py"))
        isolated_root = Path(self.temporary.name) / "source_freeze"
        source_bytes = {}
        for relative in relatives:
            raw = (root / relative).read_bytes()
            destination = isolated_root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            source_bytes[str(relative)] = raw
        isolated_wireless = isolated_root / wireless_relative
        env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1",
                   GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1")
        env.pop("PYTHONPATH", None); env.pop("PYTHONHOME", None)

        def git(*args):
            completed = subprocess.run(["git", "-c", "core.hooksPath=/dev/null",
                "-c", "commit.gpgSign=false", "-c", "user.name=MR3 artificial fixture",
                "-c", "user.email=mr3-artificial@example.invalid", *args],
                cwd=isolated_root, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            return completed.stdout

        git("init", "--quiet")
        git("add", "--", *(str(relative) for relative in relatives))
        git("commit", "--quiet", "-m", "Freeze artificial replay source fixture")
        freeze = git("rev-parse", "HEAD").decode().strip()
        self.assertRegex(freeze, r"^[0-9a-f]{40}$")
        for relative, raw in source_bytes.items():
            self.assertEqual((root / relative).read_bytes(), raw, "source changed during fixture copy")
            self.assertEqual(git("show", freeze + ":" + relative), raw)

        script = '''import json,sys
from pathlib import Path
import numpy,scipy
from mr3_learning.tests.test_audit_seed_inputs import ExactSeedInputAuditTests
p=Path(sys.argv[1])
snapshot=ExactSeedInputAuditTests().fixture(p,seed_rule="exact-point-bridge-v2",start_graph_rule="point-attachment-3x3-v1")
metadata=json.loads((p/"metadata.json").read_text())
metadata["freeze"]=sys.argv[2]
(p/"metadata.json").write_text(json.dumps(metadata))
print(json.dumps({"python":sys.executable,"numpy_version":numpy.__version__,"numpy_path":numpy.__file__,"scipy_version":scipy.__version__,"scipy_path":scipy.__file__,"snapshot_digest":snapshot["digest"]}))
'''
        created = subprocess.run(["/usr/bin/python3", "-B", "-c", script,
            str(self.directory), freeze], cwd=isolated_wireless, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        self.assertEqual(created.returncode, 0, created.stderr)
        dependencies = json.loads(created.stdout)
        self.assertEqual(Path(dependencies["python"]).resolve(), Path("/usr/bin/python3").resolve())
        self.assertNotIn("miniconda", dependencies["numpy_path"])
        self.assertNotIn("miniconda", dependencies["scipy_path"])
        poison = Path(self.temporary.name) / "poison"; poison.mkdir()
        marker = poison / "poison_imported"
        (poison / "scipy").mkdir()
        (poison / "scipy/__init__.py").write_text(
            "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('bad')\nraise RuntimeError('poison scipy')\n")
        poisoned_env = dict(env, PYTHONPATH=str(poison), PYTHONHOME="/invalid-python-home")
        with patch.object(audit, "WIRELESS", isolated_wireless), \
                patch.dict(os.environ, poisoned_env, clear=True):
            result = audit.audit_exact_seed_inputs_system(self.directory,
                seed_rule=SEED, start_graph_rule=START)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["exact_full_snapshot_replays"], 1)
        self.assertEqual(result["freeze"], freeze)
        self.assertEqual(len(result["source_proof"]), 10)
        for relative, proof in result["source_proof"].items():
            self.assertEqual(proof["sha256"], hashlib.sha256(source_bytes[relative]).hexdigest())
            self.assertEqual(proof["git_source"], freeze + ":" + relative)
        receipt = result["system_python_execution"]
        self.assertTrue(receipt["actual_waited"])
        self.assertEqual(receipt["returncode"], 0)
        self.assertEqual(receipt["child_identity"]["parent"], os.getpid())
        self.assertFalse(marker.exists())
        # A real worktree/freeze mismatch must still fail the unchanged reader.
        supervisor_relative = str(learner / "supervisor.py")
        supervisor = isolated_root / supervisor_relative
        try:
            supervisor.write_bytes(source_bytes[supervisor_relative] + b"\n# artificial source mismatch\n")
            with patch.object(audit, "WIRELESS", isolated_wireless), \
                    patch.dict(os.environ, poisoned_env, clear=True):
                mismatched = audit.audit_exact_seed_inputs_system(self.directory,
                    seed_rule=SEED, start_graph_rule=START)
            self.assertFalse(mismatched["passed"], mismatched)
            mismatch_result = json.loads(mismatched["system_python_execution"]["result_json"])
            self.assertFalse(mismatch_result["passed"])
            self.assertIn("reader/source differs from native freeze: " + supervisor_relative,
                          " ".join(mismatch_result["errors"]))
            self.assertTrue(mismatched["system_python_execution"]["actual_waited"])
            self.assertEqual(mismatched["system_python_execution"]["returncode"], 1)
        finally:
            supervisor.write_bytes(source_bytes[supervisor_relative])
        self.assertFalse(marker.exists())
        print(json.dumps({"artificial_system_replay_regression": "PASS", "dependencies": dependencies,
            "artificial_source_freeze": freeze, "source_mismatch_rejected": True,
            "replayer_child_identity": receipt["child_identity"], "argv": receipt["argv"],
            "started_monotonic_ns": receipt["started_monotonic_ns"],
            "ended_monotonic_ns": receipt["ended_monotonic_ns"],
            "actual_wait_seconds": receipt["actual_wait_seconds"], "returncode": receipt["returncode"],
            "full_snapshot_replays": 1, "world_or_native_collection": False}))


if __name__ == "__main__":
    unittest.main()
