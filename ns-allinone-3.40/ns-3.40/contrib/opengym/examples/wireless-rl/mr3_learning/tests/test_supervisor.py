import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning.supervisor import (
    Episode, InfrastructureError, Supervisor, descendants, identity_alive, process_identity,
    remember_processes, ros_environment,
)


class SupervisorTests(unittest.TestCase):
    def test_existing_safety_contract_selects_fixed_actuator_profile(self):
        from mr3_learning.supervisor import actuation_profile_for_safety_contract
        for contract, expected in (("legacy", None),
                                   ("mr3-reach-v1", "initial-zero-encoder-hold-v1")):
            with tempfile.TemporaryDirectory() as directory:
                supervisor = Supervisor(safety_contract=contract, output_root=directory)
                self.assertEqual(supervisor.actuation_profile, expected)
        for unknown in (True, None, "reach", "mr3-reach-v1 "):
            with self.assertRaises(ValueError):
                actuation_profile_for_safety_contract(unknown)

    @staticmethod
    def episode_fixture():
        identity = {"pid": 100, "parent": 1, "group": 100, "session": 100,
                    "start_ticks": 1000, "state": "S"}
        return Episode("fixture", Path("/unused"), SimpleNamespace(pid=100), None, None,
                       identity, {(100, 1000): identity})

    def test_one_proc_snapshot_covers_escaped_descendants_and_same_session_orphans(self):
        episode = self.episode_fixture()
        rows = [episode.identity,
                {"pid": 101, "parent": 100, "session": 101, "start_ticks": 1001},
                {"pid": 102, "parent": 101, "session": 101, "start_ticks": 1002},
                {"pid": 103, "parent": 1, "session": 100, "start_ticks": 1003},
                {"pid": 104, "parent": 1, "session": 999, "start_ticks": 1004},
                {"pid": 105, "parent": 1, "session": 100, "start_ticks": 999}]
        identities = {str(row["pid"]): row for row in rows}
        entries = [Path("/proc") / key for key in identities] + [Path("/proc/sys")]
        with patch("mr3_learning.supervisor.Path.iterdir", return_value=iter(entries)) as listing:
            with patch("mr3_learning.supervisor.process_identity",
                       side_effect=identities.get) as identity_read:
                remember_processes(episode)
        listing.assert_called_once()
        self.assertEqual(identity_read.call_count, len(rows))
        self.assertEqual(set(episode.owned), {(100, 1000), (101, 1001), (102, 1002), (103, 1003)})
        # The public API still returns ancestry only, irrespective of sessions.
        with patch("mr3_learning.supervisor._process_snapshot", return_value=rows) as snapshot:
            self.assertEqual([row["pid"] for row in descendants(100)], [100, 101, 102])
        snapshot.assert_called_once()

    def test_exited_leader_keeps_session_members_and_previously_seen_escapees(self):
        episode = self.episode_fixture()
        escaped = {"pid": 101, "parent": 100, "session": 101, "start_ticks": 1001}
        orphan = {"pid": 103, "parent": 1, "session": 100, "start_ticks": 1003}
        older = {"pid": 105, "parent": 1, "session": 100, "start_ticks": 999}
        with patch("mr3_learning.supervisor._process_snapshot", side_effect=[
                [episode.identity, escaped], [orphan, older]]):
            remember_processes(episode)
            remember_processes(episode)
        self.assertIn((101, 1001), episode.owned)
        self.assertIn((103, 1003), episode.owned)
        self.assertNotIn((105, 999), episode.owned)

    def test_scan_statistics_use_real_start_intervals_not_the_nominal_50ms_wait(self):
        episode = self.episode_fixture()
        with patch("mr3_learning.supervisor._process_snapshot", return_value=[]):
            with patch("mr3_learning.supervisor.time.monotonic",
                       side_effect=[10., 10.3, 11.25, 11.4]):
                remember_processes(episode)
                remember_processes(episode)
        stats = episode.process_scan_statistics
        self.assertEqual(stats["count"], 2)
        self.assertAlmostEqual(stats["max_scan_wall_sec"], .3)
        self.assertAlmostEqual(stats["max_observed_interval_sec"], 1.25)
        self.assertGreater(stats["max_observed_interval_sec"], .05)

    def test_ros_environment_strips_conda_python_and_workspace_contamination(self):
        contaminated = {key: "contamination" for key in (
            "PYTHONPATH", "LD_LIBRARY_PATH", "AMENT_PREFIX_PATH", "CMAKE_PREFIX_PATH",
            "COLCON_PREFIX_PATH", "ROS_PACKAGE_PATH", "PYTHONHOME", "VIRTUAL_ENV",
            "GAZEBO_PLUGIN_PATH", "GAZEBO_MODEL_PATH", "GAZEBO_RESOURCE_PATH",
            "CONDA_PREFIX", "CONDA_DEFAULT_ENV", "CONDA_SHLVL", "CONDA_EXE",
        )}
        contaminated.update(PATH="/conda/bin:/old_ros/bin", ROS_DOMAIN_ID="9",
                            GAZEBO_MASTER_URI="http://foreign:9999", BENIGN_SETTING="preserved")
        with patch.dict(os.environ, contaminated, clear=True):
            environment = ros_environment(123, 12345)
        for key in contaminated:
            if key not in ("PATH", "ROS_DOMAIN_ID", "GAZEBO_MASTER_URI", "BENIGN_SETTING"):
                self.assertNotIn(key, environment)
        self.assertEqual(environment["ROS_DOMAIN_ID"], "123")
        self.assertEqual(environment["GAZEBO_MASTER_URI"], "http://127.0.0.1:12345")
        self.assertEqual(environment["PYTHONNOUSERSITE"], "1")
        self.assertNotIn("conda", environment["PATH"])
        self.assertNotIn("old_ros", environment["PATH"])
        self.assertEqual(environment["BENIGN_SETTING"], "preserved")

    def test_wrong_response_id_or_epoch_is_an_infrastructure_error(self):
        for response in ({"id": 100, "epoch": "episode-a", "ok": True},
                         {"id": 1, "epoch": "episode-b", "ok": True}):
            with tempfile.TemporaryDirectory() as directory:
                supervisor = Supervisor(run_id="identity_fixture", output_root=directory)
                requests = []
                peer = SimpleNamespace(send=requests.append, receive=lambda timeout: response)
                supervisor.episode = SimpleNamespace(epoch="episode-a", peer=peer)
                with patch("mr3_learning.supervisor.remember_processes"):
                    with self.assertRaisesRegex(InfrastructureError, "identity mismatch"):
                        supervisor._rpc("step", action=888)
                self.assertEqual(requests[0]["epoch"], "episode-a")
                self.assertEqual(requests[0]["id"], 1)

    def test_wall_guards_and_quantum_are_finite_and_explicit(self):
        for field in ("startup_timeout", "request_timeout"):
            for value in (0., -1., float("nan"), float("inf")):
                with tempfile.TemporaryDirectory() as directory:
                    with self.assertRaises(ValueError, msg=f"{field}={value}"):
                        Supervisor(output_root=directory, **{field: value})
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                Supervisor(output_root=directory, quantum_steps=20.)

    def test_terminal_probe_is_opt_in_bool_and_preserves_the_last_real_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            for invalid in (0, 1, "true", None):
                with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                    Supervisor(output_root=directory, terminal_probe=invalid)
            supervisor = Supervisor(output_root=directory, terminal_probe=True)
            sample = {"snapshot": {"epoch": "fixture"}, "terminated": False, "truncated": False}
            supervisor.last_result = sample
            supervisor.episode = self.episode_fixture()
            supervisor.episode.process.poll = lambda: None
            with patch("mr3_learning.supervisor.identity_alive", return_value=True):
                responses = [{"armed": True}, {"terminal": True}]
                with patch.object(supervisor, "_rpc", side_effect=responses) as rpc:
                    self.assertEqual(supervisor.arm_failure_probe(), {"armed": True})
                    self.assertIs(supervisor.last_result, sample)
                    self.assertEqual(supervisor.trigger_failure_probe(), {"terminal": True})
                    self.assertIs(supervisor.last_result, sample)
                    self.assertEqual([call.args for call in rpc.call_args_list],
                                     [("arm_failure_probe",), ("trigger_failure_probe",)])

    def test_probe_rejects_disabled_closed_or_dead_episode_before_rpc(self):
        for case in ("disabled", "missing_episode", "missing_sample", "terminated", "truncated",
                     "exited", "reused_pid"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                supervisor = Supervisor(output_root=directory, terminal_probe=case != "disabled")
                supervisor.episode = self.episode_fixture() if case != "missing_episode" else None
                if supervisor.episode:
                    supervisor.episode.process.poll = lambda: 1 if case == "exited" else None
                supervisor.last_result = None if case == "missing_sample" else {
                    "terminated": case == "terminated", "truncated": case == "truncated"}
                with patch("mr3_learning.supervisor.identity_alive",
                           return_value=case != "reused_pid"):
                    with patch.object(supervisor, "_rpc") as rpc:
                        with self.assertRaises((RuntimeError, InfrastructureError)):
                            supervisor.arm_failure_probe()
                        with self.assertRaises((RuntimeError, InfrastructureError)):
                            supervisor.trigger_failure_probe()
                        rpc.assert_not_called()

    @unittest.skipUnless(hasattr(os, "fork") and Path("/proc/self/stat").is_file(),
                         "owned-process fixture requires Linux /proc")
    def test_startup_worker_forks_child_and_exits_without_leaking_the_child(self):
        # The temporary subreaper applies only to this pure software test process,
        # so it can reap the deliberately orphaned fixture rather than leave PID1
        # to collect a zombie. There are no ROS/Gazebo processes in this fixture.
        libc = ctypes.CDLL(None, use_errno=True)
        previous = ctypes.c_int()
        self.assertEqual(libc.prctl(37, ctypes.byref(previous), 0, 0, 0), 0)
        self.assertEqual(libc.prctl(36, 1, 0, 0, 0), 0)
        real_popen = subprocess.Popen
        child_identity = None
        supervisor = None
        temporary = tempfile.TemporaryDirectory()
        try:
            directory = temporary.name
            supervisor = Supervisor(run_id="startup_crash_fixture", output_root=directory,
                                    startup_timeout=3., request_timeout=3., terminal_probe=True)
            script = (
                "import json,os,pathlib,sys,time\n"
                "request=json.loads(sys.stdin.readline())\n"
                "pid=os.fork()\n"
                "if pid==0:\n"
                " time.sleep(30)\n"
                " os._exit(0)\n"
                "stat=pathlib.Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()\n"
                "pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid':pid,"
                "'start_ticks':int(stat[19]),'terminal_probe':request['terminal_probe']}))\n"
                "print(json.dumps({'id':request['id'],'epoch':request['epoch'],"
                "'ok':False,'error':'intentional startup crash'}),flush=True)\n"
                "os._exit(1)\n"
            )

            def start_fixture(command, **kwargs):
                pid_path = Path(command[-1]) / "fixture_child.json"
                return real_popen([sys.executable, "-c", script, str(pid_path)], **kwargs)

            with patch("mr3_learning.supervisor.subprocess.Popen", side_effect=start_fixture):
                with self.assertRaises(InfrastructureError):
                    supervisor.reset(scene="open", seed=101)
            pid_path = next(Path(directory).rglob("fixture_child.json"))
            child_identity = json.loads(pid_path.read_text())
            self.assertIs(child_identity["terminal_probe"], True)
            metadata = json.loads((pid_path.parent / "supervisor_metadata.json").read_text())
            self.assertIs(metadata["terminal_probe"], True)
            receipt = supervisor.receipts[-1]
            self.assertTrue(receipt["failed_sample"])
            self.assertGreaterEqual(receipt["process_scan_statistics"]["count"], 2)
            self.assertGreaterEqual(receipt["process_scan_statistics"]["max_scan_wall_sec"], 0.)
            self.assertEqual(receipt["remaining_owned_processes"], [])
            self.assertIn(child_identity["pid"], [row["pid"]
                                                  for row in receipt["owned_processes_seen"]])
            self.assertFalse(identity_alive(child_identity))
            self.assertIsNone(supervisor.episode)
        finally:
            if supervisor is not None and supervisor.episode is not None:
                supervisor._cleanup(failed=True)
            if child_identity:
                current = process_identity(child_identity["pid"])
                if current and current["start_ticks"] == child_identity["start_ticks"]:
                    if current["state"] != "Z":
                        os.kill(current["pid"], signal.SIGKILL)
                    deadline = time.monotonic() + 2.
                    while time.monotonic() < deadline:
                        try:
                            pid, _ = os.waitpid(current["pid"], os.WNOHANG)
                        except ChildProcessError:
                            break
                        if pid:
                            break
                        time.sleep(.01)
            temporary.cleanup()
            libc.prctl(36, previous.value, 0, 0, 0)


if __name__ == "__main__":
    unittest.main()
