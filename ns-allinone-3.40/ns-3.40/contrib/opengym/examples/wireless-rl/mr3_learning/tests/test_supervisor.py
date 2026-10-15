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
    InfrastructureError, Supervisor, identity_alive, process_identity, ros_environment,
)


class SupervisorTests(unittest.TestCase):
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
                                    startup_timeout=3., request_timeout=3.)
            script = (
                "import json,os,pathlib,sys,time\n"
                "request=json.loads(sys.stdin.readline())\n"
                "pid=os.fork()\n"
                "if pid==0:\n"
                " time.sleep(30)\n"
                " os._exit(0)\n"
                "stat=pathlib.Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()\n"
                "pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid':pid,"
                "'start_ticks':int(stat[19])}))\n"
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
            receipt = supervisor.receipts[-1]
            self.assertTrue(receipt["failed_sample"])
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
