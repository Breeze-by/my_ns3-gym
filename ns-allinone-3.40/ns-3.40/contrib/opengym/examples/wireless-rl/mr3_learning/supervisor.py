"""Complete ROS/Gazebo process rebuilds behind a private, ROS-free IPC client."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import threading
import time
import uuid

from .ipc import JsonLinePeer


WORKSPACE = Path(__file__).resolve().parents[7]
ROS_ROOT = WORKSPACE / "ros2_ws/ros2-multi-robot-automap"
SCENES = ("open", "rooms", "corridors")


class InfrastructureError(RuntimeError):
    """An invalid sample, distinct from a task's terminated/truncated outcome."""


def process_identity(pid):
    """Linux PID/start-tick identity protects cleanup from PID reuse."""
    try:
        suffix = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": int(pid), "parent": int(suffix[1]), "group": int(suffix[2]),
                "session": int(suffix[3]),
                "start_ticks": int(suffix[19]), "state": suffix[0]}
    except (OSError, ValueError, IndexError):
        return None


def identity_alive(identity):
    current = process_identity(identity["pid"])
    return bool(current and current["start_ticks"] == identity["start_ticks"]
                and current["state"] != "Z")


def descendants(pid):
    """Return only identities descended from this owned worker, not command lines."""
    rows = [process_identity(p.name) for p in Path("/proc").iterdir() if p.name.isdigit()]
    rows = [row for row in rows if row]
    owned = {pid}
    while True:
        added = {row["pid"] for row in rows if row["parent"] in owned} - owned
        if not added:
            break
        owned.update(added)
    return [row for row in rows if row["pid"] in owned]


def ros_environment(domain_id, gazebo_port):
    """Re-source the canonical ROS environment without inheriting conda paths."""
    removed = {"PYTHONPATH", "LD_LIBRARY_PATH", "AMENT_PREFIX_PATH", "CMAKE_PREFIX_PATH",
               "COLCON_PREFIX_PATH", "ROS_PACKAGE_PATH", "PYTHONHOME", "VIRTUAL_ENV",
               "GAZEBO_PLUGIN_PATH", "GAZEBO_MODEL_PATH", "GAZEBO_RESOURCE_PATH"}
    env = {key: value for key, value in os.environ.items()
           if key not in removed and not key.startswith("CONDA")}
    env.update(PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
               PYTHONNOUSERSITE="1", ROS_DOMAIN_ID=str(domain_id),
               GAZEBO_MASTER_URI=f"http://127.0.0.1:{gazebo_port}",
               TURTLEBOT3_MODEL="waffle")
    return env


@dataclass
class Episode:
    epoch: str
    directory: Path
    process: subprocess.Popen
    peer: JsonLinePeer
    output: object
    identity: dict
    owned: dict
    lock: object = field(default_factory=threading.Lock)
    stop_monitor: object = field(default_factory=threading.Event)
    monitor: object = None


def remember_processes(episode):
    rows = descendants(episode.process.pid)
    # Session membership survives the group leader exiting during startup.
    # The group/session IDs remain allocated while their members exist.
    for p in Path("/proc").iterdir():
        if p.name.isdigit():
            row = process_identity(p.name)
            if (row and row["session"] == episode.identity["pid"]
                    and row["start_ticks"] >= episode.identity["start_ticks"]):
                rows.append(row)
    with episode.lock:
        for row in rows:
            episode.owned[(row["pid"], row["start_ticks"])] = row


class Supervisor:
    """One isolated three-robot environment; reset always replaces all processes."""

    def __init__(self, *, run_id=None, worker_id=0, domain_id=120, gazebo_port=12001,
                 output_root=None, startup_timeout=420., request_timeout=90.,
                 quantum_steps=20):
        self.run_id = run_id or (datetime.now(timezone.utc).strftime("mr3_%Y%m%d_%H%M%S_")
                                 + uuid.uuid4().hex[:8])
        allowed = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
        if not self.run_id or any(c not in allowed for c in self.run_id):
            raise ValueError("run_id must be a safe unique path component")
        if type(worker_id) is not int or worker_id < 0:
            raise ValueError("worker_id must be nonnegative")
        if type(domain_id) is not int or not 0 <= domain_id <= 232:
            raise ValueError("ROS_DOMAIN_ID is outside the supported range")
        if type(gazebo_port) is not int or not 1024 <= gazebo_port <= 65535:
            raise ValueError("Gazebo port is outside the supported range")
        if type(quantum_steps) is not int or quantum_steps != 20:
            raise ValueError("P1C scheduler v1 requires 20 physical 1ms ticks per quantum")
        if (not math.isfinite(startup_timeout) or not math.isfinite(request_timeout)
                or startup_timeout <= 0 or request_timeout <= 0):
            raise ValueError("wall guards must be positive")
        self.worker_id = worker_id
        self.domain_id = domain_id
        self.gazebo_port = gazebo_port
        self.output_root = Path(output_root or ROS_ROOT / "log/mr3_learning")
        self.directory = self.output_root / self.run_id / f"worker{worker_id}"
        self.directory.mkdir(parents=True, exist_ok=False)
        self.startup_timeout = float(startup_timeout)
        self.request_timeout = float(request_timeout)
        self.quantum_steps = quantum_steps
        self.episode_number = 0
        self.request_number = 0
        self.episode = None
        self.last_result = None
        self.receipts = []

    def _rpc(self, op, timeout=None, **payload):
        if self.episode is None:
            raise InfrastructureError("environment has no running episode")
        self.request_number += 1
        remember_processes(self.episode)
        request = {"id": self.request_number, "op": op, "epoch": self.episode.epoch, **payload}
        try:
            self.episode.peer.send(request)
            response = self.episode.peer.receive(timeout or self.request_timeout)
            if response.get("id") != request["id"] or response.get("epoch") != request["epoch"]:
                raise ValueError("IPC response identity mismatch")
            remember_processes(self.episode)
            if response.get("ok") is not True:
                raise InfrastructureError(str(response.get("error", "worker failed")))
            return response.get("result")
        except (OSError, EOFError, TimeoutError, ValueError) as error:
            raise InfrastructureError(f"{op}: {error}") from error

    def reset(self, scene="open", seed=101):
        if scene not in SCENES or type(seed) is not int or seed < 0:
            raise ValueError("reset requires a declared development scene and nonnegative seed")
        self.close()
        self.episode_number += 1
        epoch = f"{self.run_id}_w{self.worker_id}_e{self.episode_number}_{uuid.uuid4().hex[:8]}"
        directory = self.directory / f"episode{self.episode_number:03d}_{scene}_{seed}"
        directory.mkdir(exist_ok=False)
        output = (directory / "worker.log").open("wb")
        command = ["/usr/bin/bash", "--noprofile", "--norc", "-c",
                   'source /opt/ros/humble/setup.bash && source "$1/install/setup.bash" '
                   '&& source /usr/share/gazebo/setup.sh '
                   '&& exec /usr/bin/python3 "$1/scripts/mr3_env_worker.py" '
                   '--run-dir "$2"', "mr3-worker", str(ROS_ROOT), str(directory)]
        process = subprocess.Popen(command, cwd=ROS_ROOT,
                                   env=ros_environment(self.domain_id, self.gazebo_port),
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=output,
                                   start_new_session=True)
        identity = process_identity(process.pid)
        if identity is None:
            process.wait()
            output.close()
            raise InfrastructureError("worker exited before ownership could be recorded")
        peer = JsonLinePeer(process.stdout.fileno(), process.stdin.fileno())
        self.episode = Episode(epoch, directory, process, peer, output, identity,
                               {(identity["pid"], identity["start_ticks"]): identity})
        episode = self.episode

        def monitor():
            while not episode.stop_monitor.is_set():
                remember_processes(episode)
                episode.stop_monitor.wait(.05)

        episode.monitor = threading.Thread(target=monitor, name="mr3_process_owner", daemon=True)
        episode.monitor.start()
        metadata = {"epoch": epoch, "scene": scene, "seed": seed,
                    "worker_id": self.worker_id, "worker_identity": identity,
                    "domain_id": self.domain_id, "gazebo_port": self.gazebo_port,
                    "command": command, "reset_kind": "complete_process_rebuild",
                    "startup_wall_guard_sec": self.startup_timeout,
                    "request_wall_guard_sec": self.request_timeout}
        (directory / "supervisor_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
        try:
            result = self._rpc("reset", timeout=self.startup_timeout, scene=scene, seed=seed,
                               quantum_steps=self.quantum_steps)
            if result["snapshot"]["epoch"] != epoch:
                raise InfrastructureError("reset returned a previous episode snapshot")
            self.last_result = result
            return result
        except Exception:
            self._cleanup(failed=True)
            raise

    def step(self, action, *, external_truncation=None):
        if type(action) is not int or not 0 <= action < 1000:
            raise ValueError("action must be an integer in [0,1000)")
        if self.last_result is None or self.last_result.get("terminated") or self.last_result.get(
                "truncated"):
            raise RuntimeError("reset is required before another step")
        try:
            result = self._rpc("step", action=action, external_truncation=external_truncation)
            if result["snapshot"]["epoch"] != self.episode.epoch:
                raise InfrastructureError("step returned a previous epoch")
            self.last_result = result
            return result
        except Exception:
            self._cleanup(failed=True)
            raise

    def truncate(self, reason="external_sampler_limit"):
        if not isinstance(reason, str) or not reason:
            raise ValueError("truncation requires a reason")
        if self.last_result is None or self.last_result.get("terminated") or self.last_result.get(
                "truncated"):
            raise RuntimeError("episode is already closed")
        try:
            self.last_result = self._rpc("truncate", reason=reason)
            return self.last_result
        except Exception:
            self._cleanup(failed=True)
            raise

    def _cleanup(self, failed=False):
        episode = self.episode
        if episode is None:
            return
        remember_processes(episode)
        with episode.lock:
            known = list(episode.owned.values())
        forced = False
        if episode.process.poll() is None:
            forced = True
            # The worker is the new session/group leader. Its start identity
            # must still match before signalling that owned group.
            if identity_alive(episode.identity):
                os.killpg(episode.process.pid, signal.SIGTERM)
            try:
                episode.process.wait(timeout=10.)
            except subprocess.TimeoutExpired:
                if identity_alive(episode.identity):
                    os.killpg(episode.process.pid, signal.SIGKILL)
                episode.process.wait(timeout=10.)
        remember_processes(episode)
        with episode.lock:
            known = list(episode.owned.values())
        remaining = [row for row in known if row["pid"] != episode.process.pid
                     and identity_alive(row)]
        forced = forced or bool(remaining)
        # A child that created its own session is still an owned descendant,
        # with its saved PID/start-time identity verified individually.
        for row in remaining:
            if identity_alive(row):
                os.kill(row["pid"], signal.SIGTERM)
        deadline = time.monotonic() + 5.
        while any(identity_alive(row) for row in remaining) and time.monotonic() < deadline:
            time.sleep(.05)
        for row in remaining:
            if identity_alive(row):
                os.kill(row["pid"], signal.SIGKILL)
        episode.stop_monitor.set()
        if episode.monitor:
            episode.monitor.join(timeout=2.)
        leftovers = [row for row in known if identity_alive(row)]
        zombies = []
        deadline = time.monotonic() + 2.
        while True:
            zombies = [current for row in known
                       if (current := process_identity(row["pid"])) is not None
                       and current["start_ticks"] == row["start_ticks"] and current["state"] == "Z"]
            if not zombies or time.monotonic() >= deadline:
                break
            time.sleep(.05)
        receipt = {"epoch": episode.epoch, "worker_returncode": episode.process.returncode,
                   "forced_shutdown": forced, "failed_sample": failed,
                   "owned_processes_seen": known, "remaining_owned_processes": leftovers,
                   "remaining_owned_zombies": zombies}
        (episode.directory / "supervisor_shutdown.json").write_text(
            json.dumps(receipt, indent=2) + "\n")
        self.receipts.append(receipt)
        episode.process.stdin.close()
        episode.process.stdout.close()
        episode.output.close()
        self.episode = None
        self.last_result = None
        if not failed and (forced or leftovers or zombies or receipt["worker_returncode"] != 0):
            raise InfrastructureError("episode cleanup was not a clean owned-process shutdown")

    def close(self):
        if self.episode is None:
            return
        try:
            self._rpc("close", timeout=90.)
            self.episode.process.wait(timeout=20.)
        except Exception:
            self._cleanup(failed=True)
            raise
        self._cleanup()
