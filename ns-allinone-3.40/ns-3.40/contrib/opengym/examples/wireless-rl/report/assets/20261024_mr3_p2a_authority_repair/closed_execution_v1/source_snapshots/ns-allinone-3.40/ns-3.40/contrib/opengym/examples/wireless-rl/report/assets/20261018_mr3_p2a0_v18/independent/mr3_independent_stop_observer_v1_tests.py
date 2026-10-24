#!/usr/bin/python3
"""Synthetic evidence mutations. No simulator, middleware or physical credit."""
import copy
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SOURCE = Path(__file__).with_name("mr3_independent_stop_observer_v1.py")
SPEC = importlib.util.spec_from_file_location("independent_observer", SOURCE)
review = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(review)
EPOCH = "synthetic_owned_epoch"
FREEZE = "a" * 40


def raw(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(
                ",",
                ":"),
            allow_nan=False) +
        "\n").encode()


def sha(value):
    return hashlib.sha256(value).hexdigest()


def native(iters=50):
    return {"iters": iters, "precon_iters": 0, "sor": 1.3, "cfm": 0.0, "erp": .2,
            "contact_max_correcting_vel": 100.0, "contact_surface_layer": .001,
            "sor_lcp_tolerance": 0.0, "use_dynamic_moi_rescaling": False,
            "gravity_xyz": [0.0, 0.0, -9.8]}


def native_row(iters=50):
    return {
        "available": True,
        "nonfinite": False,
        "values": native(iters),
        "readback_scope": "native_dWorld_getters_on_public_ODEPhysics_GetWorldId",
        "solver_dispatch": {
            "available": False,
            "reason": "active_private_step_function_has_no_public_getter; GetStepType_reads_SDF"}}


def snapshot(iters):
    cached = {k: {"cpp_type": "d", "value": v} for k, v in native(iters).items()}
    cached["iters"]["cpp_type"] = "i"
    cached["solver_type"] = {"cpp_type": "string", "value": "quick"}
    return {"engine_type": "ode", "cached": cached,
            "native_ode": {**native(iters), "friction_model_enum": 0},
            "max_step_size_sec": .001, "real_time_update_rate": 1000.0,
            "target_real_time_factor": 1.0, "world_gravity_xyz": [0.0, 0.0, -9.8],
            "engine_sdf": "<physics><iters>" + str(iters) + "</iters></physics>"}


def header(robot="tb1", iters=50):
    cached = {k: {"available": True, "readback_scope": "sdf_cached_public_GetParam", "value": v}
              for k,
              v in {"solver_type": "quick",
                    "iters": iters,
                    "sor": 1.3,
                    "cfm": 0.0,
                    "erp": .2}.items()}
    return {"schema": review.SCHEMA, "kind": "configuration", "epoch": EPOCH, "robot": robot,
            "record_sequence": 1, "sim_time_ns": 0, "world_iterations": 0,
            "wall_monotonic_ns": 1, "measurements_finite": True, "process_id": 42,
            "world_name": "p1c_open", "compiled_source_sha256": review.OBSERVER_SOURCE_SHA256,
            "loaded_library_path": "/tmp/library.so",
            "physics_type": "ode",
            "max_step_size_sec": .001,

            "native_ode": native_row(iters), "physics_parameters": cached,
            "physics_parameters_scope": (
                'public_GetParam; solver_type/iters/sor/cfm/erp_are_SDF_'
                'cached'
            ),
            "gravity_xyz": [0.0, 0.0, -9.8], "start_ns": 0, "end_ns": 300000000000,
            "canonical_name": robot + "::base_footprint", "base_name": robot + "::base_link",
            "read_only": True, "per_packet_or_driver_private_sequence": False,
            "flush_per_completed_pair": True,
            "observer_effect": (
                'synchronous getter/JSON/stdio wall-time overhead; no se'
                'tter or transport publisher'
            ),
            "axis_get_force_scope": (
                'Joint::GetForce readback, not a promised motor/solver r'
                'eaction wrench'
            )}


def position(clock, speed=.011):
    return {
        "position_xyz": [
            0.0,
            clock /
            1e9 *
            speed,
            0.1],
        "quaternion_wxyz": [
            1.0,
            0.0,
            0.0,
            0.0]}


def sample(sequence, clock, pair, phase, robot="tb1", iters=50):
    before = sequence if phase == review.PRE else sequence - 1
    pose_clock = clock - review.TICK_NS if phase == review.PRE else clock
    links = {}
    for key, name in (("canonical", "base_footprint"), ("base", "base_link")):
        links[key] = {
            "name": robot + "::" + name,
            "world_pose": position(pose_clock),
            "world_cog_pose": position(pose_clock),
            "world_angular_velocity_xyz": [
                0.0,
                0.0,
                0.0],
            "world_origin_linear_velocity_xyz": [
                0.0,
                .011,
                0.0],
            "world_cog_linear_velocity_xyz": [
                0.0,
                .011,
                0.0]}
    return {"schema": review.SCHEMA, "kind": "sample", "epoch": EPOCH, "robot": robot,
            "record_sequence": sequence,
            "sim_time_ns": clock,
            "world_iterations": clock // review.TICK_NS,

            "wall_monotonic_ns": sequence, "measurements_finite": True,
            "phase": phase, "physics_enabled": True, "pair_sequence": pair,
            "pair_iterations": clock // review.TICK_NS,
            "before_record_sequence": before,
            "before_clock_ns": clock,

            "model": {"name": robot, "world_pose": position(pose_clock),
                      "world_linear_velocity_xyz": [0.0,
                                                    .011,
                                                    0.0],
                      "world_angular_velocity_xyz": [0.0,
                                                     0.0,
                                                     0.0]},

            **links, "joints_right_left": [{"name": robot + "::" + name, "position_rad": 0.0,
                                            "velocity_radps": 0.0,
                                            "motor_velocity_target_radps": 0.0,
                                            "motor_fmax_nm": 10.0,

                                            "axis_get_force_nm": 0.0} for name in (
                                             "wheel_right_joint",




                                             "wheel_left_joint")],





            "solver_diagnostics_world_scope": {key: {"available": False, "reason": "unsupported"}
                                               for key in ("rms_error",
                                                           "constraint_residual",
                                                           "num_contacts")},

            "native_ode": native_row(iters),
            "contacts": {"manager_available": True, "valid_prefix_count": 0,
                         "never_drop_contacts": False, "records": [], "available": False,
                         "reason": (
                             'no_retained_fresh_own_static_contact_evidence_not_proof'
                             '_of_no_physical_contact'
                         )}}


def rows(robot="tb1", end=3000000, iters=50):
    result = [header(robot, iters)]
    for pair, clock in enumerate(range(review.TICK_NS, end + review.TICK_NS, review.TICK_NS), 1):
        result.append(sample(len(result) + 1, clock, pair, review.PRE, robot, iters))
        result.append(sample(len(result) + 1, clock, pair, review.POST, robot, iters))
    return result


def expected(row):
    return {"canonical": row["canonical_name"], "base": row["base_name"],
            "joints": [row["robot"] + "::wheel_right_joint", row["robot"] + "::wheel_left_joint"],
            "native_values": native(row["native_ode"]["values"]["iters"])}


def replay(values):
    instance = review.CaptureReplay("tb1", EPOCH, 1000000, 3000000, expected)
    for row in values:
        instance.record(row)
    return instance.finish()


class PairEvidenceTests(unittest.TestCase):
    def rejects(self, values):
        with self.assertRaises((review.AuditError, KeyError, TypeError, ValueError)):
            replay(values)

    def test_complete_without_capture_complete_is_valid_evidence_only(self):
        result = replay(rows())
        self.assertEqual(result["task_pairs_including_start_anchor"], 3)
        self.assertEqual(result["task_integration_intervals"], 2)
        self.assertFalse(result["capture_complete_record_present"])

    def test_zero_motor_with_lateral_motion_reported_not_reclassified_rest(self):
        result = replay(rows())
        datum = result["wheel_zero_diagnostics"]
        self.assertEqual(datum["motor_and_joint_both_exact_zero_task_samples"], 6)
        self.assertEqual(
            datum["motor_both_zero_body_planar_above_original_rest_threshold_samples"], 6)
        self.assertEqual(datum["maximum_body_planar_speed_when_motor_both_zero"], .011)
        self.assertEqual(result["contacts"]["samples_without_retained_evidence"], 6)

    def test_missing_pre_post_or_tick_rejected(self):
        for index in (1, 2, 3, 4, 5, 6):
            with self.subTest(index=index):
                value = rows()
                del value[index]
                self.rejects(value)

    def test_duplicate_row_and_swapped_phase_rejected(self):
        value = rows()
        value.insert(3, copy.deepcopy(value[2]))
        self.rejects(value)
        value = rows()
        value[1]["phase"] = review.POST
        self.rejects(value)

    def test_clock_iteration_reference_and_type_mutations(self):
        for key, replacement in (("sim_time_ns", 1000001), ("world_iterations", 2),
                                 ("pair_iterations", True), ("before_clock_ns", True),
                                 ("before_record_sequence",
                                  1),
                                 ("pair_sequence",
                                  2),
                                 ("record_sequence",
                                  99)):
            with self.subTest(field=key):
                value = rows()
                value[2][key] = replacement
                self.rejects(value)

    def test_gap_even_when_record_sequences_renumbered(self):
        value = rows(end=4000000)
        del value[3:5]
        for i, row in enumerate(value, 1):
            row["record_sequence"] = i
        self.rejects(value)

    def test_epoch_robot_model_and_joint_identity(self):
        for key in ("epoch", "robot"):
            value = rows()
            value[3][key] = "other"
            self.rejects(value)
        value = rows()
        value[3]["model"]["name"] = "tb2"
        self.rejects(value)
        value = rows()
        value[3]["joints_right_left"].reverse()
        self.rejects(value)

    def test_null_nan_and_bool_cannot_replace_measurement(self):
        for replacement in (None, float("nan"), True, float("inf")):
            value = rows()
            value[3]["model"]["world_linear_velocity_xyz"][1] = replacement
            self.rejects(value)
        value = rows()
        value[3]["measurements_finite"] = False
        self.rejects(value)

    def test_unknown_configuration_kind_and_physics_disabled(self):
        value = rows()
        value[3]["kind"] = "unrecognized"
        self.rejects(value)
        value = rows()
        value[3]["physics_enabled"] = False
        self.rejects(value)

    def test_native_profile_change_and_invented_dispatch_rejected(self):
        value = rows()
        value[3]["native_ode"]["values"]["iters"] = 150
        self.rejects(value)
        value = rows()
        value[3]["native_ode"]["solver_dispatch"]["available"] = True
        self.rejects(value)

    def test_record_after_capture_complete_rejected(self):
        value = rows()
        value.append({**value[0], "kind": "capture_complete", "record_sequence": 8,
                      "sim_time_ns": review.CAPTURE_END_NS + 1000000, "wall_monotonic_ns": 8,
                      "last_pair_sequence": 3})
        self.assertTrue(replay(value)["capture_complete_record_present"])
        value.append({**value[-1], "record_sequence": 9, "wall_monotonic_ns": 9})
        self.rejects(value)

    def test_derived_velocity_and_integral_residual(self):
        result = replay(rows())
        self.assertAlmostEqual(
            result["pre_post_pose_finite_difference_speed"]["model"]["maximum_xyz"][1], .011)
        self.assertAlmostEqual(result["integral_residual_xyz"]["model"][1], 0.0)

    def test_contact_force_requires_post_fresh_enabled_and_link_frame(self):
        force = {"available": True,
                 "body1_force_link_xyz": [0.0, 0.0, 1.0], "body2_force_link_xyz": [0.0, 0.0, -1.0],
                 "body1_torque_link_xyz": [0.0,
                                           0.0,
                                           0.0],
                 "body2_torque_link_xyz": [0.0,
                                           0.0,
                                           0.0],

                 "scope": (
                     'ODEPhysics_UpdatePhysics_rotates_feedback_into_each_lin'
                     'k_frame; torque_about_CoG'
                 )}
        contacts = {"manager_available": True,
                    "valid_prefix_count": 1,
                    "never_drop_contacts": False,
                    "available": True,
                    "records": [{"valid_prefix_index": 0,
                                 "own_collision_index": 1,
                                 "other_model_static": True,
                                 "collision1": "tb1::wheel::collision",
                                 "link1": "tb1::wheel",
                                 "collision2": "ground::link::collision",
                                 "link2": "ground::link",
                                 "available": True,
                                 "point_count": 1,
                                 "contact_time_ns": 1000000,
                                 "points": [{"position_world_xyz": [0.0,
                                                                    0.0,
                                                                    0.0],
                                             "normal_world_xyz": [0.0,
                                                                  0.0,
                                                                  1.0],
                                             "depth_m": .0001,
                                             "forces": force}]}]}
        review.contact_data(contacts, "tb1", 1000000, review.POST, True)
        for phase, enabled in ((review.PRE, True), (review.POST, False)):
            with self.assertRaises(review.AuditError):
                review.contact_data(contacts, "tb1", 1000000, phase, enabled)
        with self.assertRaises(review.AuditError):
            review.contact_data(contacts, "tb1", 2000000, review.POST, True)
        force["scope"] = "world"
        with self.assertRaises(review.AuditError):
            review.contact_data(contacts, "tb1", 1000000, review.POST, True)


class IOTests(unittest.TestCase):
    def test_plain_gzip_hashes_match_decoded_and_ambiguous_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rows.jsonl"
            content = b"".join(raw(row) for row in rows())
            path.write_bytes(content)
            plain = {}
            self.assertEqual(len(list(review.line_rows(path, plain))), 7)
            path.unlink()
            zipped = Path(str(path) + ".gz")
            zipped.write_bytes(gzip.compress(content, mtime=0))
            encoded = {}
            self.assertEqual(len(list(review.line_rows(path, encoded))), 7)
            self.assertEqual(encoded[str(zipped)]["decoded_sha256"], sha(content))
            self.assertEqual(plain[str(path)]["sha256"], encoded[str(zipped)]["decoded_sha256"])
            path.write_bytes(content)
            with self.assertRaises(review.AuditError):
                list(review.line_rows(path, {}))

    def test_admitted_first_line_changed_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "rows.jsonl"
            value = rows()
            proof = {"first_line_bytes": len(
                raw(value[0])), "first_line_sha256": sha(raw(value[0]))}
            value[0]["process_id"] = 43
            path.write_bytes(b"".join(raw(row) for row in value))
            with self.assertRaisesRegex(review.AuditError, "admitted_configuration_bytes_changed"):
                list(review.line_rows(path, {}, proof))

    def test_truncation_duplicate_keys_and_nan_tokens(self):
        for content in (b'{"a":1}', b'{"a":1,"a":2}\n', b'{"a":NaN}\n'):
            with self.subTest(raw=content), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "rows.jsonl"
                path.write_bytes(content)
                with self.assertRaises((review.AuditError, ValueError)):
                    list(review.line_rows(path, {}))


def proc_row(pid, parent, start, state="S"):
    fields = [state, str(parent)] + ["0"] * 17 + [str(start)] + ["0"] * 4
    value = str(pid) + " (gzserver test) " + " ".join(fields) + "\n"
    return {"pid": pid, "parent": parent, "start_ticks": start, "state": state, "stat_raw": value}


class AdmissionFixture:
    """Complete tiny synthetic evidence tree; no real PID or library load claimed."""

    def __init__(self, path):
        self.path = path
        self.run = path / "run"
        self.episode = self.run / "worker0/episode001_open_101"
        self.episode.mkdir(parents=True)
        self.proof_path = path / "proof.json"
        self.plan_path = path / "plan.json"
        self.config_path = path / "config.json"
        self.world = path / "world.sdf"
        self.world.write_text("<sdf><world name=\"p1c_open\"/></sdf>\n")
        self.template = path / "model.sdf"
        self.template.write_text(
            '<sdf version="1.7"><model name="waffle">\n'
            '  <link name="base_link"><mass>1.372</mass></link>\n'
            '  <plugin name="drive" filename="original.so">\n'
            '    <mr3_audit_path/>\n    <mr3_epoch/>\n    <mr3_tagged_commands/>\n'
            '  </plugin>\n</model></sdf>\n')
        self.libraries = {}
        self.sources = {}
        for name in ("observer", "profile"):
            source = path / (name + ".cpp")
            source.write_text("// synthetic " + name + "\n")
            library = path / (name + ".so")
            library.write_bytes(b"\x7fELF synthetic test object " + name.encode())
            self.sources[name] = sha(source.read_bytes())
            self.libraries[name] = {
                "source_sha256": self.sources[name],
                "source_path": str(source),
                "installed_path": str(library),
                "library_path": str(library),
                "library_sha256": sha(
                    library.read_bytes()),
                "library_bytes": library.stat().st_size}
        self.config = {
            "schema": "mr3-physics-diagnostic-config-v1",
            "run_directory": str(
                self.run),
            "episode_relative_directory": "worker0/episode001_open_101",
            "scene": "open",
            "seed": 101,
            "mode": "baseline",
            "capture_start_ns": 0,
            "capture_end_ns": 300000000000}
        for name, spec in self.libraries.items():
            self.config[name + "_library"] = {"path": spec["installed_path"],
                                              "sha256": spec["library_sha256"],
                                              "source_sha256": spec["source_sha256"]}
        self.config_path.write_bytes(raw(self.config))
        self.plan = {"stages": [{"stage": "baseline",
                                 "run_directory": str(self.run),
                                 "scene": "open",
                                 "seed": 101,
                                 "configuration_binding": {"path": str(self.config_path),
                                                           "sha256": sha(raw(self.config))}}],
                     "diagnostic_libraries": self.libraries}
        self.plan_path.write_bytes(raw(self.plan))
        self.binding_path = self.episode / "physics_diagnostic_binding.json"
        self.binding = {"schema": "mr3-physics-diagnostic-binding-v1", "epoch": EPOCH,
                        "episode_directory": str(self.episode),
                        "config_source": str(self.config_path),

                        "config_sha256": sha(raw(self.config)),
                        "mode": "baseline",
                        "world_name": "p1c_open",

                        "world_path": str(self.world),
                        "world_sha256": sha(self.world.read_bytes()),
                        "seed": 101,

                        "capture_start_ns": 0, "capture_end_ns": 300000000000,
                        "profile_output_path": str(self.episode / "physics_profile.jsonl"),
                        "observer_outputs": {
                            robot: str(self.episode / ("physics_" + robot + ".jsonl"))
                            for robot in review.ROBOTS}}
        for name, spec in self.libraries.items():
            self.binding[name + "_library"] = {**self.config[name +
                                                             "_library"],
                                               "resolved_path": spec["installed_path"]}
        self.binding_path.write_bytes(raw(self.binding))
        self.ledger_path = self.episode / "physics_profile.jsonl"
        self.ledger = {
            "schema": "mr3-physics-diagnostic-profile-v1",
            "kind": "first_boundary_profile",
            "epoch": EPOCH,
            "process_id": 42,
            "record_sequence": 1,
            "sim_time_ns": 1000000,
            "world_iterations": 1,
            "world_name": "p1c_open",
            "wall_monotonic_ns": 1,
            "compiled_source_sha256": self.sources["profile"],
            "loaded_library_path": self.libraries["profile"]["installed_path"],
            "binding_json": raw(
                self.binding).decode(),
            "binding_path": str(
                self.binding_path),
            "mode": "baseline",
            "setter_call_count": 0,
            "before": snapshot(50),
            "after": snapshot(50)}
        self.ledger_path.write_bytes(raw(self.ledger))
        (self.episode / "metadata.json").write_bytes(
            raw({"epoch": EPOCH, "freeze": FREEZE, "scene": "open", "seed": 101}))
        ancestry = {
            "schema": "mr3-live-owned-ancestry-v1",
            "benchmark_identity": {
                "pid": 40,
                "start_ticks": 400},
            "before": [
                proc_row(
                    42,
                    41,
                    420),
                proc_row(
                    41,
                    40,
                    410),
                proc_row(
                    40,
                    1,
                    400)],
            "after": proc_row(
                42,
                41,
                420,
                "R")}
        ancestry_path = path / "ancestry.json"
        ancestry_path.write_bytes(raw(ancestry))
        maps = []
        for spec in self.libraries.values():
            stat = Path(spec["installed_path"]).stat()
            maps.append("1234-5678 r-xp 00000000 " +
                        format(os.major(stat.st_dev), "x") +
                        ":" +
                        format(os.minor(stat.st_dev), "x") +
                        " " +
                        str(stat.st_ino) +
                        " " +
                        spec["installed_path"] +
                        "\n")
        self.maps_path = path / "maps"
        self.maps_path.write_text("".join(maps))
        self.proof = {"schema": "mr3-stop-observer-admission-proof-v1",
                      "passed": True,
                      "freeze": FREEZE,
                      "plan_sha256": sha(raw(self.plan)),
                      "stage": "baseline",
                      "run_directory": str(self.run),
                      "episode_directory": str(self.episode),
                      "epoch": EPOCH,
                      "robot_order": list(review.ROBOTS),
                      "owned_gzserver": {"pid": 42,
                                         "start_ticks": 420,
                                         "maps_path": str(self.maps_path),
                                         "maps_sha256": sha(self.maps_path.read_bytes()),
                                         "observer_mapped": True,
                                         "profile_mapped": True,
                                         "ancestry_path": str(ancestry_path),
                                         "ancestry_sha256": sha(raw(ancestry))},
                      "runtime_binding": {"path": str(self.binding_path),
                                          "sha256": sha(raw(self.binding))},
                      "generated_models": {},
                      "observer_files": {}}
        for name, spec in self.libraries.items():
            self.proof[name] = {
                key: value for key,
                value in spec.items() if key not in (
                    "source_path",
                    "library_path")}
            self.proof[name]["loaded_library_realpath"] = spec["installed_path"]
        self.proof["profile"].update({"mode": "baseline",
                                      "expected_iters": 50,
                                      "ledger_path": str(self.ledger_path),
                                      "ledger_sha256": sha(raw(self.ledger))})
        for robot in review.ROBOTS:
            name = "mr3_stop_response_observer_" + robot
            base = review.original_render(self.template.read_bytes(), self.episode, robot, EPOCH)
            base_path = path / ("before_" + robot + ".sdf")
            base_path.write_bytes(base)
            fields = {
                "epoch": EPOCH,
                "robot": robot,
                "output_path": self.binding["observer_outputs"][robot],
                "base_link": "base_link",
                "right_joint": "wheel_right_joint",
                "left_joint": "wheel_left_joint",
                "start_ns": "0",
                "end_ns": "300000000000"}
            block = '  <plugin name="' + name + '" filename="' + \
                self.libraries["observer"]["installed_path"] + '">\n'
            block += "".join("    <" + k + ">" + v + "</" + k + ">\n" for k,
                             v in fields.items()) + "  </plugin>\n"
            model = base.decode().replace("</model>", block + "</model>", 1).encode()
            model_path = self.episode / ("drive_model_" + robot + ".sdf")
            model_path.write_bytes(model)
            self.proof["generated_models"][robot] = {
                "path": str(model_path),
                "sha256": sha(model),
                "observer_plugin_name": name,
                "observer_library": self.libraries["observer"]["installed_path"],
                "before_observer_path": str(base_path),
                "before_observer_sha256": sha(base),
                "original_template": {
                    "path": str(
                        self.template),
                    "sha256": sha(
                        self.template.read_bytes()),
                    "bytes": self.template.stat().st_size},
                "original_body_bytes_preserved": True,
                "original_render_rule": "exact three original driver placeholders only"}
            values = rows(robot, end=33000000)
            values[0]["compiled_source_sha256"] = self.sources["observer"]
            values[0]["loaded_library_path"] = self.libraries["observer"]["installed_path"]
            observer_path = Path(self.binding["observer_outputs"][robot])
            observer_path.write_bytes(b"".join(raw(v) for v in values))
            self.proof["observer_files"][robot] = {"path": str(observer_path),
                                                   "first_line_bytes": len(
                raw(values[0])), "first_line_sha256": sha(raw(values[0]))}
        transitions = [{"kind": "reset", "terminated": False, "truncated": False,
                        "snapshot": {"epoch": EPOCH, "source_stamp": .001},
                        "info": {"epoch": EPOCH, "release_time_ns": 1000000,
                                 "reward_diagnostics": {"effective_step_end": .001}}}]
        for index in range(1, 33):
            start, end = index / 1000, (index + 1) / 1000
            transitions.append({"kind": "step",
                                "terminated": False,
                                "truncated": index == 32,
                                "snapshot": {"epoch": EPOCH,
                                             "source_stamp": end},
                                "info": {"epoch": EPOCH,
                                         "dt": .001,
                                         "reason": ("external_sampler_limit"
                                                    if index == 32 else "running"),





                                         "reward_diagnostics": {"effective_step_end": end,
                                                                "step_start": start}}})
        (self.episode / "transitions.jsonl").write_bytes(b"".join(raw(v) for v in transitions))
        self.save_proof()

    def save_proof(self):
        self.proof_path.write_bytes(raw(self.proof))

    def patches(self):
        return mock.patch.multiple(review,
                                   OBSERVER_SOURCE_SHA256=self.sources["observer"],
                                   PROFILE_SOURCE_SHA256=self.sources["profile"])

    def admit(self):
        self.save_proof()
        with self.patches():
            return review.prepare_admission(self.proof_path, self.plan_path, self.run, FREEZE, {})


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.fixture = AdmissionFixture(Path(self.temp.name))

    def test_complete_synthetic_capture_returns_only_evidence_credit(self):
        fixture = self.fixture
        with fixture.patches():
            result = review.audit(fixture.run, FREEZE, fixture.plan_path, fixture.proof_path)
        self.assertTrue(result["passed"])
        self.assertEqual(result["actual_interval"]["returned_step_calls"], 32)
        self.assertEqual(result["actual_interval"]["end_ns"], 33000000)
        self.assertEqual(len(result["robots"]), 3)
        self.assertIn("no task", result["limitations"][0])

    def test_pid_start_ancestry_cannot_be_borrowed(self):
        self.fixture.proof["owned_gzserver"]["start_ticks"] += 1
        with self.assertRaisesRegex(review.AuditError, "owned_server_ancestry_mismatch"):
            self.fixture.admit()

    def test_wrong_maps_inode_or_library_hash(self):
        fixture = self.fixture
        fixture.maps_path.write_text(fixture.maps_path.read_text().replace(" r-xp ", " rw-p "))
        fixture.proof["owned_gzserver"]["maps_sha256"] = sha(fixture.maps_path.read_bytes())
        with self.assertRaisesRegex(review.AuditError, "library_not_executable_mapped"):
            fixture.admit()

    def test_actual_model_body_changed_despite_true_flag(self):
        fixture = self.fixture
        entry = fixture.proof["generated_models"]["tb1"]
        path = Path(entry["path"])
        path.write_text(path.read_text().replace("1.372", "1.373"))
        entry["sha256"] = sha(path.read_bytes())
        with self.assertRaisesRegex(review.AuditError,
                                    "observer_injection_changed_original_bytes"):
            fixture.admit()

    def test_sidecar_cannot_be_reverse_derived_from_mutated_model(self):
        fixture = self.fixture
        entry = fixture.proof["generated_models"]["tb1"]
        for field in ("path", "before_observer_path"):
            path = Path(entry[field])
            path.write_text(path.read_text().replace("1.372", "1.373"))
        entry["sha256"] = sha(Path(entry["path"]).read_bytes())
        entry["before_observer_sha256"] = sha(Path(entry["before_observer_path"]).read_bytes())
        with self.assertRaisesRegex(review.AuditError, "before_observer_not_original_render"):
            fixture.admit()

    def test_profile_typed_boundary_and_setter_counter(self):
        fixture = self.fixture
        for key, value in (("world_iterations", True), ("setter_call_count", False)):
            with self.subTest(field=key):
                ledger = copy.deepcopy(fixture.ledger)
                ledger[key] = value
                with fixture.patches(), self.assertRaises(review.AuditError):
                    review.validate_profile(
                        ledger, fixture.proof, raw(
                            fixture.binding), fixture.binding)

    def test_profile_cannot_change_sor_with_iters(self):
        fixture = self.fixture
        ledger = copy.deepcopy(fixture.ledger)
        ledger["after"]["native_ode"]["sor"] = 1.31
        with fixture.patches(), self.assertRaises(review.AuditError):
            review.validate_profile(ledger, fixture.proof, raw(fixture.binding), fixture.binding)

    def test_runtime_library_field_not_just_proof_flag(self):
        fixture = self.fixture
        fixture.binding["observer_library"]["source_sha256"] = "b" * 64
        fixture.binding_path.write_bytes(raw(fixture.binding))
        fixture.proof["runtime_binding"]["sha256"] = sha(raw(fixture.binding))
        with self.assertRaisesRegex(review.AuditError, "runtime_binding_library_mismatch"):
            fixture.admit()

    def test_plan_library_binding_not_just_loaded_path(self):
        self.fixture.proof["observer"]["source_sha256"] = "b" * 64
        with self.assertRaisesRegex(review.AuditError, "admission_library_differs_from_plan"):
            self.fixture.admit()

    def test_header_load_50_allowed_with_contrast_samples_150(self):
        context = self.fixture.admit()
        context["profile_after"] = snapshot(150)
        value = header()
        value["compiled_source_sha256"] = self.fixture.sources["observer"]
        value["loaded_library_path"] = self.fixture.libraries["observer"]["installed_path"]
        with self.fixture.patches():
            result = review.header_validator(context, "tb1", value)
        self.assertEqual(result["native_values"]["iters"], 150)
        self.assertEqual(value["_reader_configuration_profile_matches"], ["before"])

    def test_missing_robot_or_unknown_capture_configuration(self):
        del self.fixture.proof["observer_files"]["tb2"]
        with self.assertRaises(review.AuditError):
            self.fixture.admit()

    def test_configuration_scope_and_window_mutations(self):
        fixture = self.fixture
        context = fixture.admit()
        value = header()
        value["compiled_source_sha256"] = fixture.sources["observer"]
        value["loaded_library_path"] = fixture.libraries["observer"]["installed_path"]
        for key, replacement in (("start_ns", False), ("end_ns", 299999999999),
                                 ("read_only", False), ("flush_per_completed_pair", False),
                                 ("per_packet_or_driver_private_sequence",
                                  True),
                                 ("process_id",
                                  43)):
            changed = copy.deepcopy(value)
            changed[key] = replacement
            with self.subTest(field=key), fixture.patches(), self.assertRaises(review.AuditError):
                review.header_validator(context, "tb1", changed)

    def test_complete_32_calls_does_not_hide_early_external_truncation(self):
        fixture = self.fixture
        path = fixture.episode / "transitions.jsonl"
        values = [json.loads(line) for line in path.read_bytes().splitlines()]
        values[2]["truncated"] = True
        path.write_bytes(b"".join(raw(v) for v in values))
        with fixture.patches(), self.assertRaisesRegex(review.AuditError,
                                                       "early_truncated_diagnostic"):
            review.audit(fixture.run, FREEZE, fixture.plan_path, fixture.proof_path)


if __name__ == "__main__":
    unittest.main()
