"""Synthetic CPU collection/dispatch evidence; these mocks earn no native credit."""

import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import action_trace, audit_action_trace as audit
from mr3_learning import audit_reach_sensor_model as sensor_audit
from mr3_learning.tests.test_env import SupervisorFixture
from mr3_learning.tests.test_observation import seal


class ReachSensorModelTests(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        episode = Path(temporary.name)
        epoch = "reach<&epoch>"
        source = (audit.WORKSPACE/audit.MODEL).read_bytes()
        generated = {}
        starts = []
        for robot,position in audit.SPAWN.items():
            start = source.index(b'<sensor name="hls_lfcd_lds" type="ray">')
            end = source.index(b"</sensor>",start)
            raw = source[:start]+source[start:end].replace(b"<update_rate>5</update_rate>",b"<update_rate>20</update_rate>",1)+source[end:]
            from xml.sax.saxutils import escape
            for tag,value in (("mr3_audit_path",str(episode/f"drive_{robot}.jsonl")),
                              ("mr3_epoch",epoch),("mr3_tagged_commands","true")):
                raw = raw.replace(f"<{tag}/>".encode(),f"<{tag}>{escape(value)}</{tag}>".encode(),1)
            path = episode/f"drive_model_{robot}.sdf"; path.write_bytes(raw)
            generated[robot] = raw
            argv = ["/usr/bin/python3","/opt/ros/humble/lib/gazebo_ros/spawn_entity.py",
                "-file",str(path),"-entity",robot,"-robot_namespace","/"+robot,
                "-x",str(position[0]),"-y",str(position[1]),"-z",str(position[2]),
                "-R","0","-P","0","-Y","0"]
            starts.append({"event":"process_started","epoch":epoch,"argv":argv})
        (episode/"launch.log").write_text("".join("MR3_ORDERED_SHUTDOWN "+json.dumps(row)+"\n" for row in starts))
        return episode,epoch,source,generated,starts

    def test_independent_whole_source_and_model_inverse_preserves_original_reader(self):
        episode,epoch,source,generated,_ = self.fixture()
        module,projection = sensor_audit.load_spawn_impl()
        self.assertTrue(projection['whole_source_inverse_equal'])
        self.assertEqual(projection['inverse_sha256'],sensor_audit.ORIGINAL_READER_SHA256)
        self.assertEqual(len(projection['literal_changes']),2)
        original_code = audit._spawn.__code__
        report = module._spawn(episode,epoch,Path.read_bytes,False)
        self.assertEqual(set(report['robots']),set(audit.SPAWN))
        for robot,row in report['robots'].items():
            proof = row['reach_sensor_profile']
            self.assertEqual(proof['effective_update_rate_hz'],20)
            self.assertEqual(proof['whole_byte_inverse_sha256'],proof['source_sha256'])
            restored,_ = sensor_audit.inverse_reach_lidar(generated[robot],source,robot,epoch,episode)
            self.assertIn(b"<update_rate>5</update_rate>",restored)
            self.assertEqual((episode/f"drive_model_{robot}.sdf").read_bytes(),generated[robot])
        self.assertIs(audit._spawn.__code__,original_code)

    def test_rejects_old_rate_and_any_unrelated_sensor_body_or_driver_byte_change(self):
        episode,epoch,source,generated,_ = self.fixture()
        raw = generated['tb1']
        mutations = [
            raw.replace(b'<sensor name="hls_lfcd_lds"',b'<sensor name="other_lidar"',1),
            raw.replace(b"<update_rate>20</update_rate>",b"<update_rate>5</update_rate>"),
            raw.replace(b"<samples>360</samples>",b"<samples>361</samples>",1),
            raw.replace(b"<wheel_diameter>0.066</wheel_diameter>",b"<wheel_diameter>0.067</wheel_diameter>",1),
            raw.replace(b"<model name=",b" <model name=",1),
        ]
        for changed in mutations:
            self.assertNotEqual(changed,raw)
            with self.subTest(change=changed[:40]),self.assertRaises(ValueError):
                sensor_audit.inverse_reach_lidar(changed,source,'tb1',epoch,episode)
        with self.assertRaises(ValueError):
            sensor_audit.inverse_reach_lidar(raw,source,'tb2',epoch,episode)

    def test_original_spawn_gate_still_rejects_changed_actual_pose_or_file(self):
        episode,epoch,_,_,starts = self.fixture()
        module,_ = sensor_audit.load_spawn_impl()
        for argument,value in (("-x","3.0"),("-file",str(episode/"drive_model_tb2.sdf"))):
            altered = copy.deepcopy(starts)
            argv = altered[0]['argv']; argv[argv.index(argument)+1] = value
            (episode/"launch.log").write_text("".join("MR3_ORDERED_SHUTDOWN "+json.dumps(row)+"\n" for row in altered))
            with self.subTest(argument=argument),self.assertRaises(ValueError):
                module._spawn(episode,epoch,Path.read_bytes,False)

    def test_native_dispatch_conjoins_sensor_and_original_failures(self):
        episode,_,_,_,_ = self.fixture()
        (episode/"metadata.json").write_text("{}")
        for old_pass,sensor_pass in ((True,True),(False,True),(True,False)):
            calls = []
            def original(*args,**kwargs):
                calls.append(kwargs)
                return {'passed':old_pass,'errors':[] if old_pass else ['original failure']}
            phase = SimpleNamespace(corrected_audit=original)
            sensor_audit.attach_native_gate(phase,Path('/source'),'a'*40)
            with patch.object(sensor_audit,'audit_episode',side_effect=
                    (None if sensor_pass else ValueError('wrong real sensor rate')),
                    return_value={'passed':True}):
                result = phase.corrected_audit(None,None,None,[episode],matrix=True,expected_fault=True)
            self.assertEqual(result['passed'],old_pass and sensor_pass)
            self.assertEqual(calls,[{'matrix':True,'expected_fault':True}])

    def test_missing_native_episode_cannot_acquire_sensor_credit(self):
        with tempfile.TemporaryDirectory() as directory:
            phase = SimpleNamespace(corrected_audit=lambda *args,**kwargs:{'passed':True,'errors':[]})
            sensor_audit.attach_native_gate(phase,Path('/source'),'a'*40)
            self.assertFalse(phase.corrected_audit(None,None,None,[Path(directory)])['passed'])

    def test_missing_metadata_attempt_is_reported_beside_a_complete_sibling(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory)
            complete = run/'worker0/episode001_open_101'; complete.mkdir(parents=True)
            missing = run/'worker0/episode002_open_102'; missing.mkdir()
            (complete/'metadata.json').write_text('{}')
            phase = SimpleNamespace(corrected_audit=lambda *args,**kwargs:{'passed':True,'errors':[]})
            sensor_audit.attach_native_gate(phase,Path('/source'),'a'*40)
            def audit_attempt(path,*args):
                if path == missing:
                    raise FileNotFoundError('metadata.json')
                return {'passed':True}
            with patch.object(sensor_audit,'audit_episode',side_effect=audit_attempt) as checked:
                result = phase.corrected_audit(None,None,None,[run])
            self.assertFalse(result['passed'])
            self.assertEqual(checked.call_count,2)
            self.assertEqual({row['directory'] for row in result['reach_sensor_models']},{str(complete),str(missing)})


class TraceCollectionTests(unittest.TestCase):
    def fixture(self, observer=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root, clock = Path(temporary.name), [10 * 10**9]
        epoch, freeze = "synthetic-episode", "a" * 40
        run = root / "trace"
        episode = run / "worker0/episode001_open_101"
        config = root / "observer.json" if observer else None
        observer_library = str(audit.WORKSPACE / audit.ROS /
                               "install/multi_robot/lib/libmr3_stop_response_observer.so")
        if config:
            config.write_text(json.dumps({"schema": "mr3-physics-diagnostic-config-v2",
                                          "mode": "observer_only",
                                          "observer_library": {"path": observer_library}}))

        class FakeSupervisor(SupervisorFixture):
            def __init__(self, **kwargs):
                super().__init__()
                episode.mkdir(parents=True)
                self.directory = episode.parent
                self.episode = SimpleNamespace(directory=episode)
                self.receipts = []

            def append(self, kind, payload):
                with (episode / "transitions.jsonl").open("a") as stream:
                    stream.write(json.dumps(dict(payload, kind=kind)) + "\n")

            def reset(self, scene, seed):
                result = super().reset(scene, seed)
                # The original fixture creates its own consistent epoch.
                nonlocal epoch
                epoch = self.snapshot["epoch"]
                self.snapshot["joint_action_mask"] = [True] * 1000
                seal(self.snapshot)
                result["snapshot"] = copy.deepcopy(self.snapshot)
                common = {"epoch": epoch, "scene": "open", "seed": 101,
                          "plant_stimulus_arm": None, "plant_stimulus_work_deadline_ns": None,
                          "terminal_probe": False}
                (episode / "metadata.json").write_text(json.dumps(dict(
                    common, freeze=freeze, command=["ros2", "launch", "multi_robot", "normal.py"])))
                (episode / "supervisor_metadata.json").write_text(json.dumps(dict(
                    common, startup_wall_guard_sec=420., request_wall_guard_sec=90.,
                    command=["/usr/bin/python3", "mr3_env_worker.py"])))
                for robot, xyz in audit.SPAWN.items():
                    sdf = (audit.WORKSPACE / audit.MODEL).read_text()
                    for tag, value in {
                            "mr3_audit_path": str(episode / f"drive_{robot}.jsonl"),
                            "mr3_epoch": epoch, "mr3_tagged_commands": "true"}.items():
                        sdf = sdf.replace(f"<{tag}/>", f"<{tag}>{value}</{tag}>")
                    if observer:
                        sdf = sdf.replace("</model>", f'<plugin name="mr3_stop_response_observer_{robot}" '
                                          f'filename="{observer_library}"/></model>')
                        rows = [
                            {"kind": "configuration", "epoch": epoch, "robot": robot,
                             "read_only": True, "paused_only": True},
                            {"kind": "sample", "epoch": epoch, "robot": robot,
                             "record_sequence": 2, "sim_time_ns": 1, "measurements_finite": True,
                             "model": {"name": robot, "world_pose": {"position_xyz": list(xyz),
                                                                       "quaternion_wxyz": [1., 0., 0., 0.]}}}]
                        (episode / f"physics_{robot}.jsonl").write_text(
                            "".join(json.dumps(row) + "\n" for row in rows))
                    model = episode / f"drive_model_{robot}.sdf"
                    model.write_text(sdf)
                    argv = ["/usr/bin/python3", "/opt/ros/humble/lib/gazebo_ros/spawn_entity.py",
                            "-file", str(model), "-entity", robot, "-robot_namespace", "/" + robot,
                            "-x", str(xyz[0]), "-y", str(xyz[1]), "-z", str(xyz[2]),
                            "-R", "0", "-P", "0", "-Y", "0"]
                    with (episode / "launch.log").open("a") as stream:
                        stream.write("[launch] MR3_ORDERED_SHUTDOWN " + json.dumps({
                            "event": "process_started", "epoch": epoch, "argv": argv}) + "\n")
                self.append("reset", result)
                return result

            def step(self, action, external_truncation=None):
                previous = copy.deepcopy(self.snapshot)
                result = super().step(action, external_truncation)
                result["info"].update({
                    "command": {"action": action, "epoch": epoch,
                                "observation_sequence": previous["sequence"],
                                "observation_digest": previous["digest"]},
                    "reason": "external_sampler_limit" if result["truncated"] else None})
                clock[0] += 100_000_000
                self.append("step", result)
                return result

            def close(self):
                super().close()
                clock[0] += 100_000_000
                receipt = {"epoch": epoch, "worker_returncode": 0, "forced_shutdown": False,
                           "failed_sample": False, "remaining_owned_processes": [],
                           "remaining_owned_zombies": []}
                self.receipts.append(receipt)
                (episode / "supervisor_shutdown.json").write_text(json.dumps(receipt))

        args = SimpleNamespace(run_id="trace", output_root=root, domain=180, port=14001,
                               physics_config=config)
        with patch.object(action_trace, "Supervisor", FakeSupervisor), \
                patch.object(action_trace.subprocess, "check_output", return_value=freeze), \
                patch.object(action_trace.time, "monotonic_ns", side_effect=lambda: clock[0]):
            result = action_trace.run_trace(args)
        if config:
            (episode / "physics_diagnostic_binding.json").write_text(json.dumps({
                "schema": "mr3-physics-diagnostic-binding-v2", "epoch": epoch,
                "mode": "observer_only", "config_sha256": result["physics_config"]["sha256"],
                "config_source": str(config), "observer_library": {"path": observer_library},
                "physics_intervention": "none_observer_only"}))
        self.assertEqual(result["outcome"], "CAPTURED_PENDING_INDEPENDENT_VALIDITY_AUDIT")
        return episode, freeze

    def review(self, episode, freeze):
        def frozen(command, **kwargs):
            self.assertEqual(command[:2], ["git", "show"])
            revision, relative = command[2].split(":", 1)
            self.assertEqual(revision, freeze)
            return (audit.WORKSPACE / relative).read_bytes()
        with patch.object(audit.subprocess, "check_output", side_effect=frozen):
            return audit.audit_collection(episode, freeze)

    @staticmethod
    def update(path, operation):
        value = json.loads(path.read_text())
        operation(value)
        path.write_text(json.dumps(value))

    def test_real_wrapper_synthetic_eight_steps_bind_without_native_credit(self):
        episode, freeze = self.fixture()
        result = self.review(episode, freeze)
        self.assertTrue(result["passed"], result)
        self.assertEqual(result["steps"], 8)
        self.assertFalse(result["spawn"]["physical_pose_admission"])
        self.assertIn(str(episode / "transitions.jsonl"), result["artifact_proof"])

    def test_optional_real_getter_shape_is_required_for_physical_spawn_admission(self):
        episode, freeze = self.fixture(observer=True)
        result = self.review(episode, freeze)
        self.assertTrue(result["passed"], result)
        self.assertTrue(result["spawn"]["physical_pose_admission"])
        path = episode / "physics_tb3.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        rows[1]["model"]["world_pose"]["position_xyz"][0] += .01001
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        failed = self.review(episode, freeze)
        self.assertFalse(failed["passed"])
        self.assertIn("1cm", failed["errors"][0])

    def test_collection_rejects_changed_summary_source_action_reward_dt_and_budget(self):
        changes = [
            lambda value: value["actions"].__setitem__(0, 888),
            lambda value: value["steps"][0].__setitem__("action", 888),
            lambda value: value["steps"][0].__setitem__("reward", 999.),
            lambda value: value["steps"][0]["info"].__setitem__("dt", .9),
            lambda value: value["mask_checks"][0]["joint_action_mask"].__setitem__(231, False),
            lambda value: value["mask_checks"][0].__setitem__("observation_digest", "f" * 64),
            lambda value: value.__setitem__("native_decisions_returned", 7),
            lambda value: value.__setitem__("ended_wall_monotonic_ns", value["started_wall_monotonic_ns"] + 701 * 10**9),
            lambda value: value["source_bindings"].__setitem__("env.py", "0" * 64),
            lambda value: value.__setitem__("first_failure", {"kind": "actual_failure"}),
        ]
        for index, change in enumerate(changes):
            with self.subTest(change=index):
                episode, freeze = self.fixture()
                self.update(episode.parent.parent / "action_trace_summary.json", change)
                result = self.review(episode, freeze)
                self.assertFalse(result["passed"], index)
                self.assertEqual(result["outcome"], "INCOMPLETE")

    def test_native_transition_tampering_or_prefix_never_passes(self):
        for field in ("action", "mask", "digest", "prefix", "terminated"):
            with self.subTest(field=field):
                episode, freeze = self.fixture()
                path = episode / "transitions.jsonl"
                rows = [json.loads(line) for line in path.read_text().splitlines()]
                if field == "action":
                    rows[1]["info"]["command"]["action"] = 888
                elif field == "mask":
                    rows[0]["snapshot"]["joint_action_mask"][231] = False
                elif field == "digest":
                    rows[-1]["snapshot"]["digest"] = "0" * 64
                elif field == "terminated":
                    rows[-1]["terminated"] = True
                else:
                    rows.pop()
                path.write_text("".join(json.dumps(row) + "\n" for row in rows))
                self.assertFalse(self.review(episode, freeze)["passed"])

    def test_removed_odometry_sdf_option_is_rejected(self):
        episode, freeze = self.fixture()
        path = episode / "drive_model_tb1.sdf"
        path.write_text(path.read_text().replace("</plugin>",
            "<mr3_odometry_period_ns>20000000</mr3_odometry_period_ns></plugin>", 1))
        self.assertFalse(self.review(episode, freeze)["passed"])

    def test_real_launch_spawn_and_physical_sdf_are_bound_not_estimated_slam_pose(self):
        for field in ("spawn", "model", "arm", "shutdown"):
            with self.subTest(field=field):
                episode, freeze = self.fixture()
                if field == "spawn":
                    path = episode / "launch.log"
                    path.write_text(path.read_text().replace('"-0.45"', '"-1.6"'))
                elif field == "model":
                    path = episode / "drive_model_tb1.sdf"
                    path.write_text(path.read_text().replace("<pose>0.0 0.0 0.0 0.0 0.0 0.0</pose>",
                                                             "<pose>1 0 0 0 0 0</pose>", 1))
                elif field == "arm":
                    self.update(episode / "metadata.json", lambda value: value.__setitem__("plant_stimulus_arm", "pulse"))
                else:
                    self.update(episode / "supervisor_shutdown.json", lambda value: value.__setitem__("forced_shutdown", True))
                self.assertFalse(self.review(episode, freeze)["passed"])


class OriginalGateDispatchTests(unittest.TestCase):
    def fixture(self, failure=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        episode = Path(temporary.name).resolve()
        original_physics, original_readiness = object(), object()
        native = SimpleNamespace(audit_physics=original_physics,
                                 audit_initial_inputs_ready=original_readiness)
        phase = SimpleNamespace(corrected_audit=lambda *args: {"passed": failure != "native"})
        scalar = SimpleNamespace(audit_episode=lambda *args: {"errors": ["actual scalar failure"]
                                                            if failure == "scalar" else []})
        calls = []

        def operation(name):
            def invoke(*args):
                calls.append(name)
                return {"passed": failure != name}
            return invoke

        def physics(auditor, directories, cache):
            cache[episode] = {"passed": failure != "motion"}
            auditor.audit_physics = object()
            return original_physics

        def readiness(*args):
            native.audit_initial_inputs_ready = object()

        with patch.object(audit, "load_native_gates", return_value=(phase, object(), native, object(), scalar, {})), \
                patch.object(audit, "dispatch_controlled_physics", side_effect=physics), \
                patch.object(audit, "dispatch_controlled_readiness", side_effect=readiness), \
                patch.object(audit, "audit_collection", side_effect=operation("collection")), \
                patch.object(audit.audit_evaluator_phase, "audit_episode", side_effect=operation("evaluator_phase")), \
                patch.object(audit.audit_preparation, "audit_archives", side_effect=operation("archives")), \
                patch.object(audit.audit_preparation, "audit_execution_inputs", side_effect=operation("execution_inputs")), \
                patch.object(audit.audit_activity, "audit_episode", side_effect=operation("activity")):
            result = audit.audit(episode, "a" * 40)
        self.assertIs(native.audit_physics, original_physics)
        self.assertIs(native.audit_initial_inputs_ready, original_readiness)
        self.assertEqual(set(calls), {"collection", "evaluator_phase", "archives", "execution_inputs", "activity"})
        self.assertEqual(set(result["components"]), {"native", "collection", "scalar", "motion", *calls})
        return result

    def test_all_original_scientific_gates_still_run(self):
        self.assertTrue(self.fixture()["passed"])

    def test_any_original_gate_or_collection_failure_is_not_hidden(self):
        for failure in ("native", "collection", "scalar", "evaluator_phase", "archives",
                        "execution_inputs", "activity", "motion"):
            with self.subTest(failure=failure):
                result = self.fixture(failure)
                self.assertFalse(result["passed"])
                self.assertTrue(any(error.startswith(failure + ":") for error in result["errors"]))

    def test_cli_retains_fail_result_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "failed.json"
            argv = ["audit", directory, "--freeze", "a" * 40, "--output", str(path)]
            with patch("sys.argv", argv), patch.object(audit, "audit", side_effect=ValueError("real missing evidence")), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(audit.main(), 1)
            self.assertFalse(json.loads(path.read_text())["passed"])
            before = path.read_bytes()
            with patch("sys.argv", argv), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                audit.main()
            self.assertEqual(path.read_bytes(), before)
