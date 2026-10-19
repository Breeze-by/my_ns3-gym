import json
import os
from pathlib import Path
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import plant_probe
from mr3_learning.supervisor import Supervisor


class PlantProbeTests(unittest.TestCase):
    def test_stimulus_cannot_enter_normal_or_other_scene_interfaces(self):
        with tempfile.TemporaryDirectory() as directory:
            for arm in (False, True, "", "other"):
                with self.assertRaises(ValueError):
                    Supervisor(output_root=directory, plant_stimulus_arm=arm)
            with self.assertRaises(ValueError):
                Supervisor(output_root=directory, plant_stimulus_arm="pulse", terminal_probe=True)
            supervisor = Supervisor(output_root=directory, plant_stimulus_arm="pulse")
            with patch.object(supervisor, "close") as close:
                for scene, seed in (("rooms", 101), ("open", 102)):
                    with self.assertRaises(ValueError):
                        supervisor.reset(scene, seed)
                close.assert_not_called()

    def test_observer_only_configuration_rejects_mutating_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "physics.json"
            for value in (
                    {"schema": "mr3-physics-diagnostic-config-v1", "mode": "observer_only"},
                    {"schema": "mr3-physics-diagnostic-config-v2", "mode": "profile"},
                    {"schema": "mr3-physics-diagnostic-config-v2", "mode": "observer_only",
                     "profile_library": "/fake.so"}):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    plant_probe.physics_config(path)

    def test_four_keep_collection_preserves_incomplete_scope_and_charges_final_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "physics.json"
            path.write_text(json.dumps({"schema": "mr3-physics-diagnostic-config-v2",
                                        "mode": "observer_only"}))
            args = SimpleNamespace(physics_config=path, arm="pulse", run_id="fixture",
                                   domain=180, port=14001, output_root=Path(directory))
            clock = [10_000_000_000]
            calls = []

            class FakeSupervisor:
                def __init__(self, **kwargs):
                    self.directory = Path(directory) / "fixture/worker0"
                    self.directory.mkdir(parents=True)
                    self.episode = SimpleNamespace(directory=self.directory, epoch="native")
                    self.receipts = []
                    calls.append(kwargs)

                def reset(self, **kwargs):
                    return {"snapshot": {"epoch": "native"},
                            "info": {"release_time_ns": 20_000_000}}

                def step(self, action, *, external_truncation):
                    calls.append((action, external_truncation))
                    return {"terminated": False, "truncated": external_truncation is not None,
                            "info": {"dt": 1.}}

                def close(self):
                    clock[0] += 25_000_000_000
                    self.receipts.append({"closed": True})

            with patch.dict(os.environ, {plant_probe.PHYSICS_CONFIG_ENV: "prior"}):
                with patch.object(plant_probe, "Supervisor", FakeSupervisor), patch.object(
                        plant_probe.subprocess, "check_output", return_value="freeze\n"), patch.object(
                        plant_probe.time, "monotonic_ns", side_effect=lambda: clock[0]), patch.object(
                        plant_probe, "native_custody", return_value={"passed": True}):
                    result = plant_probe.run_arm(args)
                self.assertEqual(os.environ[plant_probe.PHYSICS_CONFIG_ENV], "prior")
            self.assertEqual(calls[1:], [(888, None)] * 3 + [(888, "plant_probe_fixed_end")])
            self.assertEqual(result["wall_sec"], 25.)
            self.assertFalse(result["training_eligible"])
            self.assertTrue(result["validity_audit_required"])
            self.assertEqual(result["optimizer_steps"], 0)
            self.assertEqual(result["outcome"], "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT")
            self.assertEqual(result["shutdown_receipts"], [{"closed": True}])

    def test_native_custody_hashes_actual_owned_maps_and_rejects_replaced_inode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proc = root / "proc"
            libraries = []
            for name in ("libmr3_gazebo_diff_drive.so", "libmr3_stop_response_observer.so",
                         "libmr3_ray_box_corrector.so", "libgazebo_ode.so.11",
                         "libvelocity_smoother_core.so"):
                path = root / name
                path.write_bytes(name.encode())
                libraries.append(path)
            identities = {pid: {"pid": pid, "parent": 100, "start_ticks": pid * 10, "state": "S"}
                          for pid in (101, 102, 103, 104)}
            for index, pid in enumerate(identities):
                process = proc / str(pid)
                process.mkdir(parents=True)
                args = ["/usr/bin/gzserver"] if index == 0 else [
                    "/canonical/velocity_smoother", "--ros-args", "__ns:=/tb" + str(index)]
                (process / "cmdline").write_bytes(b"\0".join(value.encode() for value in args))
                mapped = libraries[:4] if index == 0 else libraries[4:]
                lines = []
                for path in mapped:
                    stat = path.stat()
                    device = f"{os.major(stat.st_dev):x}:{os.minor(stat.st_dev):x}"
                    lines.append(f"1000-2000 r-xp 00000000 {device} {stat.st_ino} {path}")
                (process / "maps").write_text("\n".join(lines) + "\n")
            episode_dir = root / "episode"
            episode_dir.mkdir()
            episode = SimpleNamespace(epoch="owned", directory=episode_dir,
                                      lock=threading.Lock(), owned=identities)
            with patch.object(plant_probe, "process_identity", side_effect=identities.get):
                proof = plant_probe.native_custody(
                    episode, proc_root=proc, expected_smoother_core=libraries[-1])
                self.assertTrue(proof["passed"], proof["errors"])
                self.assertEqual(len(proof["processes"]), 4)
                actual_tb3 = next(value for value in proof["processes"] if value.get("robot") == "tb3")
                self.assertTrue(actual_tb3["maps"][0]["sha256"])
                maps = proc / "104/maps"
                maps.write_text(maps.read_text().replace(str(libraries[-1].stat().st_ino), "0"))
                failed = plant_probe.native_custody(
                    episode, proc_root=proc, expected_smoother_core=libraries[-1])
                self.assertFalse(failed["passed"])
                self.assertTrue(any("device/inode" in str(value) for value in failed["errors"]))


if __name__ == "__main__":
    unittest.main()
