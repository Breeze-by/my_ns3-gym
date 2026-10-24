"""CPU synthetic archives and boxes only; never read the six V21 originals."""

import copy
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from mr3_learning import proxy2d_conformity as conformity


class ConformityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = conformity.PureBuilder()

    @classmethod
    def tearDownClass(cls):
        receipt = cls.builder.close()
        assert receipt["actual_waited"] and receipt["returncode"] == 0

    def archive_fixture(self, directory):
        """Use actual pure builder and map archive format on invented inputs."""
        records, files = [], {}
        def store(relative, raw):
            path = directory / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            files[str(relative)] = {"bytes": len(raw), "sha256": conformity.sha(raw)}
        for number in (1, 2):
            episode = f"worker0/episode{number:03d}_open_101"
            store(Path(episode) / "metadata.json", conformity.canonical({
                "freeze": conformity.NATIVE_FREEZE, "safety_contract": "mr3-reach-v1"}))
            selected = []
            for sequence, now in ((1, 1.), (2, 2.), (33, 33.)):
                grid = np.full((32, 32), -1, dtype=np.int16); grid[8:24, 8:24] = 0
                payload = {"header": {"frame_id": "map", "stamp": {"sec": int(now), "nanosec": 0}},
                    "info": {"map_load_time": {"sec": 0, "nanosec": 0}, "resolution": .25,
                        "height": 32, "width": 32, "origin": {"position": {"x": -4., "y": -4., "z": 0.},
                            "orientation": {"x": 0., "y": 0., "z": 0., "w": 1.}}}, "data": grid.ravel().tolist()}
                raw = conformity.canonical(payload); digest = conformity.sha(raw)
                sources = {name: {"version": sequence, "sequence": sequence, "source_stamp": now,
                                  "received_stamp": now, "payload_sha256": digest} for name in conformity.ROBOTS}
                navigation_sources = {name: {**sources[name], "epoch": "synthetic-archive",
                    "composition_version": conformity.COMPOSITION, "input_own_map_payload_sha256": digest,
                    "input_shared_map_payload_sha256": digest, "input_own_source_stamp": now,
                    "received_stamp_scope": "synthetic_fixture", "shared_map_version": sequence}
                    for name in conformity.ROBOTS}
                robots = [{"name": name, "epoch": "synthetic-archive", "x": float(i - 1), "y": 0.,
                    "yaw": 0., "v": 0., "w": 0., "valid": True, "source_stamp": now, "received_stamp": now,
                    "navigation": {"phase": "idle", "source_stamp": now, "received_stamp": now,
                                   "sequence": sequence, "accepted_goal_count": 0}, "history": []}
                    for i, name in enumerate(conformity.ROBOTS)]
                robots[2]["navigation"] = {}
                if sequence > 1:
                    robots[0]["navigation"].update(phase="active", goal_id="synthetic-goal", goal_x=.5, goal_y=1.,
                        owned=True, requested_at=1., accepted_at=1.25, commitment_until=now + 3.,
                        progress_m=.3, accepted_goal_count=2, lease_until=now + 2.,
                        command_id="synthetic-command", observation_version="synthetic-version")
                    robots[1]["history"] = [{"x": 0., "y": 0., "source_stamp": 1.}]
                    robots[1]["activity"] = {"schema": "mr3-received-activity-v1", "epoch": "synthetic-archive",
                        "state_sequence": sequence, "sample_count": sequence, "started_at": 1.,
                        "last_odom_source_stamp": now, "estimated_path_m": .25, "path_observation_complete": True}
                own = {name: {"grid": grid.copy(), "resolution": .25, "origin": [-4., -4.],
                               "epoch": "synthetic-archive", **sources[name]} for name in conformity.ROBOTS}
                nav = {name: {**own[name], **navigation_sources[name]} for name in conformity.ROBOTS}
                params = {"raw_grid": grid, "resolution": .25, "origin": [-4., -4.], "robots": robots,
                    "now": now, "epoch": "synthetic-archive", "map_version": sequence, "sequence": sequence,
                    "map_source_stamp": now, "map_received_stamp": now, "map_sources": sources,
                    "task_start": 1., "robot_maps": own, "navigation_maps": nav}
                snapshot = self.builder(**params)
                archive = Path(episode) / "observation_inputs"
                roles = ["fused", *conformity.ROBOTS, *("navigation:" + n for n in conformity.ROBOTS)]
                maps = {role: {"artifact": f"maps/{digest}.json.gz", "payload_sha256": digest} for role in roles}
                manifest = {"schema": "mr3-observation-input-archive-v2", "scope": "encoder_result_before_publication",
                    **{key: snapshot[key] for key in ("epoch", "sequence", "candidate_version", "source_stamp")},
                    "snapshot_digest": snapshot["digest"], "metadata": {"navigation_composition": {"version": conformity.COMPOSITION},
                        "navigation_sources": snapshot["navigation_sources"], "map_sources": snapshot["map"]["sources"],
                        "map_version": sequence, "map_payload_sha256": digest, "map_source_stamp": now, "map_received_stamp": now},
                    "maps": maps}
                store(archive / f"snapshots/{sequence:08d}_{snapshot['digest']}.json", conformity.canonical(manifest))
                store(archive / f"maps/{digest}.json.gz", gzip.compress(raw, mtime=0))
                selected.append({"kind": "reset" if sequence == 1 else "step", "snapshot": snapshot,
                    "terminated": False, "truncated": sequence == 33,
                    "info": {"reason": "external_sampler_limit" if sequence == 33 else None}})
            rows = [selected[0], selected[1]] + [selected[1]] * 30 + [selected[2]]
            store(Path(episode) / "transitions.jsonl", b"\n".join(conformity.canonical(row) for row in rows) + b"\n")
            records.extend(selected)
        inventory = directory / "inventory.json"
        inventory.write_bytes(conformity.canonical({"schema": "mr3-closed-byte-inventory-v1",
            "original_root": str(directory.resolve()), "files": files}))
        return conformity.NativeInputs(directory, inventory), records

    def test_synthetic_six_archive_inputs_rebuild_full_candidates_masks_and_tensors(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs, original = self.archive_fixture(Path(temporary))
            records = conformity.replay_native(inputs, self.builder)
            self.assertEqual([row["selection"] for row in records], ["reset", "first_step", "last_step"] * 2)
            self.assertEqual([row["native_snapshot_ref"]["line_1based"] for row in records], [1, 2, 33] * 2)
            self.assertTrue(all(row["expected"] == row["actual"] and row["candidate_mask_full_snapshot_equal"] for row in records))
            self.assertTrue(any(candidate["valid"] for candidate in original[0]["snapshot"]["candidates"]))
            self.assertEqual(set(records[0]["expected"]["tensor_proofs"]),
                {"global_map", "local_maps", "robots", "candidates", "history", "task", "action_mask"})
            params, _ = conformity.recover_parameters(inputs, records[0]["episode"], original[0])
            self.assertEqual(params["robots"][0]["navigation"]["sequence"], 1)
            self.assertEqual(params["robots"][2]["navigation"], {})
            self.assertEqual(params["raw_grid"].dtype, np.int16)
            self.assertEqual(params["task_start"], 1.)
            inputs.verify()

    def test_changed_rebuilt_mask_even_with_valid_digest_is_detected(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs, _ = self.archive_fixture(Path(temporary))
            def corrupt(**params):
                snapshot = self.builder(**params)
                index = next(i for i, valid in enumerate(snapshot["joint_action_mask"]) if not valid)
                snapshot["joint_action_mask"][index] = True
                snapshot["digest"] = conformity.sha(conformity.canonical({k: v for k, v in snapshot.items() if k != "digest"}))
                return snapshot
            records = conformity.replay_native(inputs, corrupt)
            self.assertTrue(all(row["expected"] != row["actual"] and not row["candidate_mask_full_snapshot_equal"] for row in records))

    def test_original_inventory_detects_changed_missing_and_escaped_files(self):
        for case in ("changed", "missing", "escape", "changed_before_verdict"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary); inputs, _ = self.archive_fixture(directory)
                relative = "worker0/episode001_open_101/metadata.json"
                if case == "changed":
                    (directory / relative).write_bytes(b"{}")
                    with self.assertRaisesRegex(ValueError, "closed native bytes differ"): inputs.read(relative)
                elif case == "missing":
                    (directory / relative).unlink()
                    with self.assertRaises(OSError): inputs.read(relative)
                elif case == "escape":
                    with self.assertRaisesRegex(ValueError, "escaped"): inputs.read("../outside")
                else:
                    inputs.read(relative); (directory / relative).write_bytes(b"{}")
                    with self.assertRaisesRegex(ValueError, "changed before verdict"): inputs.verify()

    def test_selection_does_not_silently_use_missing_step_or_nonexternal_terminal(self):
        row = {"kind": "step", "truncated": True, "terminated": False, "info": {"reason": "external_sampler_limit"}}
        rows = [{"kind": "reset"}, *([row] * 32)]
        self.assertEqual([line for line, _ in conformity.selected_rows(b"\n".join(conformity.canonical(r) for r in rows))], [1, 2, 33])
        for corrupted in (rows[:-1], rows + [row], [*rows[:-1], {**row, "terminated": True}],
                          [*rows[:-1], {**row, "info": {"reason": "collision"}}]):
            with self.assertRaises(ValueError): conformity.selected_rows(b"\n".join(conformity.canonical(r) for r in corrupted))

    def test_map_loader_rejects_rotated_corrupt_and_nonintegral_cells(self):
        payload = {"info": {"width": 2, "height": 1, "resolution": .05000000074505806,
            "origin": {"position": {"x": 0., "y": 1.}, "orientation": {"x": 0., "y": 0., "z": 0., "w": 1.}}}, "data": [-1, 100]}
        self.assertEqual(conformity.grid_from_payload(payload)["resolution"], .05000000074505806)
        for case in ("rotation", "length", "range", "float"):
            bad = copy.deepcopy(payload)
            if case == "rotation": bad["info"]["origin"]["orientation"]["z"] = .1
            elif case == "length": bad["data"] = [0]
            elif case == "range": bad["data"] = [-1, 101]
            else: bad["data"] = [-1., 100.]
            with self.assertRaises(ValueError): conformity.grid_from_payload(bad)

    def test_missing_navigation_role_fails_without_truth_or_ledger_substitute(self):
        with tempfile.TemporaryDirectory() as temporary:
            inputs, rows = self.archive_fixture(Path(temporary))
            original_read = inputs.read
            def read(relative):
                raw = original_read(relative)
                if "/snapshots/" in str(relative):
                    manifest = conformity.parse(raw); del manifest["maps"]["navigation:tb3"]
                    return conformity.canonical(manifest)
                return raw
            with patch.object(inputs, "read", side_effect=read):
                with self.assertRaisesRegex(ValueError, "omitted a received map role"):
                    conformity.recover_parameters(inputs, "worker0/episode001_open_101", rows[0])

    def test_synthetic_box_halved_dt_and_information_separation_use_real_pure_modules(self):
        # System interpreter owns scipy/ROS-pure world modules; conda owns encoder.
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "synthetic-unit.json"
            script = ("import json,sys; from pathlib import Path; "
                "from mr3_learning.proxy2d_conformity import synthetic_cases; "
                "r=synthetic_cases(Path(sys.argv[1]).with_suffix('.inputs')); "
                "Path(sys.argv[1]).write_text(json.dumps(r,allow_nan=False)); "
                "sys.exit(0 if r['passed'] else 1)")
            env = os.environ.copy(); env.pop("PYTHONPATH", None)
            env.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
            process = subprocess.run(["/usr/bin/python3", "-B", "-c", script, str(output)],
                cwd=conformity.WIRELESS, env=env, capture_output=True, text=True, timeout=30.)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            result = json.loads(output.read_bytes())
            self.assertEqual(len(result["cases"]), 3)
            self.assertEqual(result["native_runs"], 0)
            for case in result["cases"]:
                self.assertTrue(case["passed"], case)
                for ref in case["input_refs"]:
                    raw = Path(ref["path"]).read_bytes()
                    self.assertEqual((len(raw), conformity.sha(raw)), (ref["bytes"], ref["sha256"]))
            reward = result["cases"][-1]
            self.assertNotEqual(*reward["actual"]["rewards"])

    def test_timeout_closes_helper_and_retains_actual_wait_receipt(self):
        class Hanging:
            pid, returncode = 123, None
            def wait(self, timeout=None):
                if self.returncode is None: raise subprocess.TimeoutExpired("synthetic", timeout)
                return self.returncode
            def poll(self): return self.returncode
            def terminate(self): self.returncode = -15
        with tempfile.TemporaryDirectory() as temporary:
            receipt = {}
            with patch.object(conformity.subprocess, "Popen", return_value=Hanging()), \
                 patch.object(conformity, "process_identity", return_value={"pid": 123, "parent": 1, "start_ticks": 5}):
                with self.assertRaises(subprocess.TimeoutExpired):
                    conformity.run_synthetic_helper("a" * 40, Path(temporary) / "out.json", receipt)
            waited = receipt["synthetic_actual_wait"]
            self.assertTrue(waited["actual_waited"] and waited["termination_requested"])
            self.assertEqual(waited["returncode"], -15)


if __name__ == "__main__":
    unittest.main()
