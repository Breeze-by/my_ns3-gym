"""Explicit proxy supervisor for zero-update engineering, separate from PPO."""
import json
import os
from pathlib import Path
import signal
import select
import subprocess
import time
import uuid

from .ipc import JsonLinePeer
from .proxy2d_process import pidfd_open, pidfd_send_signal
from .supervisor import ROS_ROOT, InfrastructureError, process_identity, ros_environment


class ProxySupervisor:
    training_eligible = False
    native_qualification = False

    def __init__(self, directory, env_id=0, *, profile=False,mapper="endpoint",mapper_library=None,
                 seed_rule="legacy"):
        if type(profile) is not bool:
            raise ValueError("proxy profile switch must be boolean")
        self.profile = profile
        if seed_rule not in ("legacy", "exact-point-bridge-v1"):
            raise ValueError("unsupported seed rule")
        self.seed_rule = seed_rule
        if mapper not in ("endpoint","karto") or (mapper=="karto") != (mapper_library is not None):
            raise ValueError("explicit supported mapper/library pair required")
        self.mapper = mapper
        self.mapper_library = None if mapper_library is None else str(Path(mapper_library).resolve(strict=True))
        self.root = Path(directory).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.env_id, self.episode_number = env_id, 0
        self.process = self.peer = self.console = None
        self.last_result = None
        self.identities = []
        self.directory = None

    def _rpc(self, operation, **fields):
        self.peer.send({"operation": operation, **fields})
        response = self.peer.receive(40.)
        if not response.get("ok"):
            raise InfrastructureError("2D proxy IPC failed: " + str(response.get("error")))
        return response["result"]

    def reset(self, scene="open", seed=101):
        if scene not in ("open", "rooms", "corridors") or type(seed) is not int or seed < 0:
            raise ValueError("proxy reset requires a declared scene and nonnegative seed")
        self.close()
        self.episode_number += 1
        epoch = f"proxy2d_w{self.env_id}_e{self.episode_number}_{uuid.uuid4().hex[:8]}"
        self.directory = self.root / f"episode{self.episode_number:03d}_{scene}_{seed}"
        self.directory.mkdir()
        self.console = (self.directory / "worker.stderr.log").open("wb")
        script = ROS_ROOT / "scripts/mr3_proxy2d_worker.py"
        command = ["/usr/bin/bash", "--noprofile", "--norc", "-c",
                   'source /opt/ros/humble/setup.bash && source "$1/install/setup.bash" '
                   '&& exec /usr/bin/python3 -B "$1/scripts/mr3_proxy2d_worker.py" '
                   '--role worker --directory "$2" --epoch "$3" --scene "$4" --seed "$5" '
                   '--mapper "$6" ${7:+--mapper-library "$7"}'
                   + (' --seed-rule "$8"' if self.seed_rule != "legacy" else ''),
                   "mr3-proxy", str(ROS_ROOT), str(self.directory), epoch, scene, str(seed),
                   self.mapper,self.mapper_library or ""]
        if self.seed_rule != "legacy":
            command.append(self.seed_rule)
        env = ros_environment(230 + self.env_id, 15901 + self.env_id)
        env.update(PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="",
                   OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1", MKL_NUM_THREADS="1")
        env.pop("MR3_PROXY2D_PROFILE_OUTPUT", None)
        if self.profile:
            env["MR3_PROXY2D_PROFILE_OUTPUT"] = str(self.directory / "worker.pstats")
        self.worker_identity = None
        try:
            self.process = subprocess.Popen(command, cwd=ROS_ROOT, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.console, start_new_session=True)
            identity = process_identity(self.process.pid)
            if identity is None:
                raise InfrastructureError("proxy process disappeared before identity capture")
            self.identities.append(identity)
            self.worker_identity = identity
            self.peer = JsonLinePeer(self.process.stdout.fileno(), self.process.stdin.fileno())
            metadata = {"epoch": epoch, "scene": scene, "seed": seed, "env_id": self.env_id,
                        "episode_index": self.episode_number, "worker_identity": identity,
                        "actual_argv": command, "cwd": str(ROS_ROOT), "proxy_only": True,
                        "training_eligible": False, "profile_enabled": self.profile,
                        "reset_kind": "complete_proxy_process_rebuild"}
            if self.mapper == "karto":
                metadata.update(mapper=self.mapper,mapper_library=self.mapper_library)
            if self.seed_rule != "legacy":
                metadata["seed_rule"] = self.seed_rule
            (self.directory / "episode.json").write_text(json.dumps(metadata, indent=2) + "\n")
            self.last_result = self._rpc("reset")
            child = json.loads((self.directory / "evaluator_identity.json").read_text())
            observed = process_identity(child["pid"])
            if (observed is None or observed["start_ticks"] != child["start_ticks"]
                    or observed["parent"] != identity["pid"]
                    or observed["group"] != identity["group"]
                    or observed["session"] != identity["session"]):
                raise InfrastructureError("proxy evaluator ownership could not be independently observed")
            self.identities.append(observed)
            return self.last_result
        except Exception:
            self.last_result = None
            self.close(failed=True)
            raise

    def step(self, action, *, external_truncation=None):
        if self.last_result is None or self.last_result["terminated"] or self.last_result["truncated"]:
            raise RuntimeError("proxy reset required before step")
        try:
            self.last_result = self._rpc("step", action=action, external_truncation=external_truncation)
            return self.last_result
        except Exception:
            self.last_result = None
            self.close(failed=True)
            raise

    def close(self, failed=False):
        if self.process is None:
            if self.console is not None:
                self.console.close()
                self.console = None
            self.last_result = None
            return
        started = time.monotonic_ns()
        errors, forced = [], False
        try:
            if not failed and self.process.poll() is None:
                try:
                    self._rpc("close")
                except Exception as error:
                    errors.append(repr(error))
            try:
                self.process.wait(timeout=12.)
            except subprocess.TimeoutExpired:
                forced = True
                # Only our saved, unreaped child group; no name-based cleanup.
                current = process_identity(self.process.pid)
                if current is not None and self.worker_identity is not None and current["start_ticks"] == self.worker_identity["start_ticks"]:
                    os.killpg(self.process.pid, signal.SIGTERM)
                elif self.worker_identity is None and self.process.poll() is None:
                    self.process.terminate()
                try:
                    self.process.wait(timeout=10.)
                except subprocess.TimeoutExpired:
                    current = process_identity(self.process.pid)
                    if current is not None and self.worker_identity is not None and current["start_ticks"] == self.worker_identity["start_ticks"]:
                        os.killpg(self.process.pid, signal.SIGKILL)
                    elif self.worker_identity is None and self.process.poll() is None:
                        self.process.kill()
                    self.process.wait()  # Preserve the owned handle until actual reap.
            # A failed constructor/worker may have exited before its evaluator.
            # Verify the current episode's real child identity and owned session;
            # never signal a name or an identity from an older episode.
            identity_path = self.directory / "evaluator_identity.json"
            if identity_path.exists() and self.worker_identity is not None:
                saved = json.loads(identity_path.read_text())
                child = process_identity(saved["pid"])
                if (child is not None and child["start_ticks"] == saved["start_ticks"]
                        and child["group"] == self.worker_identity["group"]
                        and child["session"] == self.worker_identity["session"]):
                    forced = True
                    descriptor = pidfd_open(child["pid"])
                    try:
                        pidfd_send_signal(descriptor, signal.SIGTERM)
                        poll = select.poll()
                        poll.register(descriptor, select.POLLIN)
                        if not poll.poll(1000):
                            pidfd_send_signal(descriptor, signal.SIGKILL)
                            if not poll.poll(10000):
                                errors.append("owned evaluator did not exit after SIGKILL")
                    finally:
                        os.close(descriptor)
            result = {"actual_waited": True, "returncode": self.process.returncode,
                      "forced": forced, "errors": errors, "identities": self.identities,
                      "started_ns": started, "ended_ns": time.monotonic_ns(),
                      "proxy_only": True, "passed": not forced and not errors and self.process.returncode == 0}
            (self.directory / "supervisor_close.json").write_text(json.dumps(result, indent=2) + "\n")
            if not result["passed"] and not failed:
                raise InfrastructureError("proxy did not close cleanly: " + str(result))
        finally:
            for stream in (self.process.stdin, self.process.stdout, self.console):
                if stream is not None:
                    stream.close()
            self.process = self.peer = self.console = None
            self.last_result = None
