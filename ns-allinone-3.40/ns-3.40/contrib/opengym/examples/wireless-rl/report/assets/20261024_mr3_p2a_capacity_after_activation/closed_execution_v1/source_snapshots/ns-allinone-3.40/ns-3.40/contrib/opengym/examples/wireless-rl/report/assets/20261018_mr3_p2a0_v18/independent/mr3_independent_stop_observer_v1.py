#!/usr/bin/python3
"""Independent bounded observer evidence review; no production or ROS imports.

This reviews capture completeness, finite numeric data and declared provenance.
It does not replace the immutable 30 Hz stopping/physical reader or award task
success.  Header/profile field adapters are explicit and versioned below.
"""
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape


SCHEMA = "mr3-stop-response-observer-v1"
ROOT = Path("/home/zhuyulab/ns3-workspace")
ROBOTS = ("tb1", "tb2", "tb3")
TICK_NS = 1000000
CAPTURE_START_NS = 0
CAPTURE_END_NS = 300000000000
PRE = "before_physics_after_collision"
POST = "world_update_end_after_physics_and_pose_propagation"
OBSERVER_SOURCE_SHA256 = "4e721e15ee7c67938c1f2c1dbd3005e0832adb0182c66d6dce6ddcafaf7c0396"
PROFILE_SOURCE_SHA256 = "26952e1cb8b17239a61b75ee98466daad65bafe116864557bbe92cc0b7fed7c0"
NATIVE_KEYS = (
    "iters",
    "precon_iters",
    "sor",
    "cfm",
    "erp",
    "contact_max_correcting_vel",
    "contact_surface_layer",
    "sor_lcp_tolerance",
    "use_dynamic_moi_rescaling",
    "gravity_xyz")


class AuditError(ValueError):
    def __init__(self, code, **context):
        self.code = code
        self.context = context
        super().__init__(code)


def need(condition, code, **context):
    if not condition:
        raise AuditError(code, **context)


def integer(value, name, minimum=0):
    need(type(value) is int and value >= minimum, "invalid_integer", field=name)
    return value


def number(value, name):
    need(type(value) in (int, float), "invalid_number_type", field=name)
    try:
        valid = math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        valid = False
    need(valid, "nonfinite_number", field=name)
    return value


def text(value, name):
    need(type(value) is str and bool(value), "invalid_text", field=name)
    return value


def digest_text(value, name):
    need(type(value) is str and re.fullmatch("[0-9a-f]{64}", value) is not None,
         "invalid_sha256", field=name)
    return value


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def same(left, right):
    return canonical(left) == canonical(right)


def finite_tree(value, field="root"):
    if type(value) is float:
        number(value, field)
    elif isinstance(value, dict):
        for key, child in value.items():
            finite_tree(child, field + "." + key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            finite_tree(child, field + "[" + str(index) + "]")


def pairs(values):
    result = {}
    for key, value in values:
        need(key not in result, "duplicate_json_key", key=key)
        result[key] = value
    return result


def decode(raw):
    def bad_constant(value):
        raise AuditError("nonfinite_json_token", token=value)
    result = json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)
    finite_tree(result)
    return result


def sha_file(path):
    digest = hashlib.sha256()
    count = 0
    with Path(path).open("rb") as stream:
        for raw in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(raw)
            count += len(raw)
    return digest.hexdigest(), count


def read_json(path, bindings, expected_sha=None):
    path = Path(path)
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    need(expected_sha is None or actual == expected_sha, "input_sha256_mismatch", path=str(path))
    bindings[str(path)] = {"bytes": len(raw), "sha256": actual}
    return decode(raw)


def bind_file(path, bindings, expected_sha=None):
    path = Path(path)
    before = path.stat()
    actual, size = sha_file(path)
    after = path.stat()
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
         == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
         "input_changed_while_read", path=str(path))
    need(expected_sha is None or actual == expected_sha, "input_sha256_mismatch", path=str(path))
    bindings[str(path)] = {"bytes": size, "sha256": actual}
    return after


def line_rows(path, bindings, first_line=None):
    """Stream plain/gzip JSONL, preserving exact encoded and decoded hashes."""
    path = Path(path)
    variants = [p for p in (path, Path(str(path) + ".gz")) if p.is_file()]
    need(len(variants) == 1, "missing_or_ambiguous_jsonl", path=str(path))
    selected = variants[0]
    digest = hashlib.sha256()
    decoded_size = 0
    count = 0
    before = selected.stat()
    opener = gzip.open if selected.suffix == ".gz" else open
    complete = False
    try:
        with opener(selected, "rb") as stream:
            for raw in stream:
                digest.update(raw)
                decoded_size += len(raw)
                count += 1
                need(raw.endswith(b"\n"), "truncated_jsonl_line", path=str(selected), line=count)
                need(bool(raw.strip()), "empty_jsonl_line", path=str(selected), line=count)
                if count == 1 and first_line is not None:
                    need(type(first_line.get("first_line_bytes")) is int
                         and first_line["first_line_bytes"] == len(raw)
                         and first_line.get("first_line_sha256")
                         == hashlib.sha256(raw).hexdigest(),





                         "admitted_configuration_bytes_changed", path=str(selected))
                yield decode(raw)
        complete = True
    finally:
        after = selected.stat()
        need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
             == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
             "jsonl_changed_while_read", path=str(selected))
        encoded_sha, encoded_size = sha_file(selected)
        bindings[str(selected)] = {"bytes": encoded_size,
                                   "sha256": encoded_sha,
                                   "decoded_bytes": decoded_size,
                                   "decoded_sha256": digest.hexdigest(),
                                   "records": count,
                                   "decoded_stream_complete": complete}


def vector(value, field, length=3):
    need(type(value) is list and len(value) == length, "invalid_vector", field=field)
    return [number(item, field + "[" + str(i) + "]") for i, item in enumerate(value)]


def pose(value, field):
    need(type(value) is dict, "invalid_pose", field=field)
    position = vector(value["position_xyz"], field + ".position_xyz")
    orientation = vector(value["quaternion_wxyz"], field + ".quaternion_wxyz", 4)
    need(any(item != 0 for item in orientation), "zero_quaternion", field=field)
    return position


def cross(left, right):
    return [left[1] * right[2] - left[2] * right[1],
            left[2] * right[0] - left[0] * right[2],
            left[0] * right[1] - left[1] * right[0]]


def sub(left, right):
    return [number(a - b, "derived_difference") for a, b in zip(left, right)]


class VectorStats:
    def __init__(self):
        self.count = 0
        self.minimum = None
        self.maximum = None
        self.maximum_norm = 0.0
        self.maximum_planar_norm = 0.0

    def add(self, values):
        values = vector(values, "derived_vector")
        self.count += 1
        self.minimum = values[:] if self.minimum is None else [
            min(a, b) for a, b in zip(self.minimum, values)]
        self.maximum = values[:] if self.maximum is None else [
            max(a, b) for a, b in zip(self.maximum, values)]
        self.maximum_norm = max(self.maximum_norm, number(math.hypot(*values), "derived_norm"))
        self.maximum_planar_norm = max(self.maximum_planar_norm, number(
            math.hypot(*values[:2]), "derived_planar_norm"))

    def result(self):
        return {"count": self.count, "minimum_xyz": self.minimum, "maximum_xyz": self.maximum,
                "maximum_norm": self.maximum_norm, "maximum_planar_norm": self.maximum_planar_norm}


def entities(row, robot, expected):
    native_values(row["native_ode"], expected["native_values"])
    contact_data(row["contacts"], robot, row["sim_time_ns"], row["phase"], row["physics_enabled"])
    model = row["model"]
    need(model["name"] == robot, "wrong_sample_model", robot=robot)
    result = {
        "model": (
            pose(
                model["world_pose"],
                "model.world_pose"),
            vector(
                model["world_linear_velocity_xyz"],
                "model.world_linear_velocity_xyz"))}
    vector(model["world_angular_velocity_xyz"], "model.world_angular_velocity_xyz")
    for name in ("canonical", "base"):
        link = row[name]
        need(link["name"] == expected[name], "wrong_scoped_link", field=name, robot=robot)
        origin = pose(link["world_pose"], name + ".world_pose")
        cog = pose(link["world_cog_pose"], name + ".world_cog_pose")
        origin_velocity = vector(
            link["world_origin_linear_velocity_xyz"],
            name + ".world_origin_linear_velocity_xyz")
        cog_velocity = vector(
            link["world_cog_linear_velocity_xyz"],
            name + ".world_cog_linear_velocity_xyz")
        angular = vector(link["world_angular_velocity_xyz"], name + ".world_angular_velocity_xyz")
        result[name + "_origin"] = (origin, origin_velocity)
        result[name + "_cog"] = (cog, cog_velocity)
        result[name + "_point_velocity_residual"] = sub(
            origin_velocity, sub(cog_velocity, cross(angular, sub(cog, origin))))
    wheels = row["joints_right_left"]
    need(type(wheels) is list and len(wheels) == 2, "invalid_joint_pair", robot=robot)
    for joint, name in zip(wheels, expected["joints"]):
        need(joint["name"] == name, "wrong_scoped_joint", robot=robot)
        for field in (
            "position_rad",
            "velocity_radps",
            "motor_velocity_target_radps",
            "motor_fmax_nm",
                "axis_get_force_nm"):
            number(joint[field], "joint." + field)
    diagnostics = row["solver_diagnostics_world_scope"]
    for key in ("rms_error", "constraint_residual", "num_contacts"):
        datum = diagnostics[key]
        need(type(datum.get("available")) is bool, "untyped_parameter_availability", parameter=key)
        if datum["available"]:
            number(datum["value"], "world_parameter." + key)
    return result


def native_values(value, expected=None):
    need(type(value) is dict and value.get("available") is True,
         "native_ode_unavailable")
    need(value.get("readback_scope") == "native_dWorld_getters_on_public_ODEPhysics_GetWorldId",
         "native_ode_scope_mismatch")
    need(value.get("nonfinite") is False, "native_ode_nonfinite")
    dispatch = value["solver_dispatch"]
    need(dispatch.get("available") is False and type(dispatch.get("reason")) is str,
         "invented_native_solver_dispatch")
    values = value["values"]
    integer(values["iters"], "native_ode.iters", 1)
    integer(values["precon_iters"], "native_ode.precon_iters")
    for key in (
        "sor",
        "cfm",
        "erp",
        "contact_max_correcting_vel",
        "contact_surface_layer",
            "sor_lcp_tolerance"):
        number(values[key], "native_ode." + key)
    need(type(values["use_dynamic_moi_rescaling"]) in (int, bool),
         "native_ode_rescaling_type")
    vector(values["gravity_xyz"], "native_ode.gravity_xyz")
    if expected is not None:
        need(type(expected) is dict and set(NATIVE_KEYS).issubset(expected),
             "profile_native_value_fields_missing")
        need(all(same(values[key], expected[key]) for key in NATIVE_KEYS),
             "profile_native_values_mismatch")
    return values


def contact_data(value, robot, clock, phase, physics_enabled=True):
    need(type(value) is dict and type(value.get("available")) is bool,
         "invalid_contact_availability")
    if value.get("manager_available") is not True:
        need(value["available"] is False and type(value.get("reason")) is str,
             "contact_manager_unavailable_without_reason")
        return
    prefix = integer(value["valid_prefix_count"], "contact.valid_prefix_count")
    need(type(value["never_drop_contacts"]) is bool and type(value["records"]) is list,
         "invalid_contact_metadata")
    observed = set()
    usable = False
    for record in value["records"]:
        index = integer(record["valid_prefix_index"], "contact.valid_prefix_index")
        need(index < prefix and index not in observed, "invalid_contact_prefix_reference")
        observed.add(index)
        own = integer(record["own_collision_index"], "contact.own_collision_index", 1)
        need(own in (1, 2) and record["other_model_static"] is True,
             "invalid_contact_own_static_scope")
        for key in ("collision1", "collision2", "link1", "link2"):
            text(record[key], "contact." + key)
        need(record["collision" + str(own)].startswith(robot + "::")
             and record["link" + str(own)].startswith(robot + "::"),
             "contact_wrong_own_model")
        need(type(record["available"]) is bool, "untyped_contact_record_availability")
        count = integer(record["point_count"], "contact.point_count")
        integer(record["contact_time_ns"], "contact.contact_time_ns")
        if record["available"]:
            need(record["contact_time_ns"] == clock and count > 0,
                 "available_stale_contact")
            need(type(record["points"]) is list and len(record["points"]) == count,
                 "contact_point_count_mismatch")
            usable = True
        for point in record.get("points", []):
            vector(point["position_world_xyz"], "contact.position_world_xyz")
            vector(point["normal_world_xyz"], "contact.normal_world_xyz")
            number(point["depth_m"], "contact.depth_m")
            force = point["forces"]
            need(type(force.get("available")) is bool, "untyped_force_availability")
            if force["available"]:
                need(phase == POST and record["available"] is True and physics_enabled is True,
                     "force_before_current_solve_or_stale_contact")
                for key in ("body1_force_link_xyz", "body2_force_link_xyz",
                            "body1_torque_link_xyz", "body2_torque_link_xyz"):
                    vector(force[key], "contact." + key)
                need(
                    force["scope"] == (
                        'ODEPhysics_UpdatePhysics_rotates_feedback_into_each_lin'
                        'k_frame; torque_about_CoG'
                    ),
                    "force_frame_scope_mismatch")
            else:
                text(force.get("reason"), "force.unavailable_reason")
    need(value["available"] is usable, "contact_availability_mismatch")
    if not usable:
        text(value.get("reason"), "contact.unavailable_reason")


class CaptureReplay:
    """One file, bounded memory. All conclusions here concern evidence only."""

    def __init__(self, robot, epoch, start, end, validate_header):
        self.robot = robot
        self.epoch = epoch
        self.start = start
        self.end = end
        self.validate_header = validate_header
        self.header = None
        self.expected = None
        self.last_record = 0
        self.last_pair = 0
        self.last_clock = None
        self.last_iteration = None
        self.last_wall = None
        self.pending = None
        self.complete = False
        self.task_clocks = 0
        self.next_task_clock = start
        self.first_pair_clock = None
        self.last_sample_phase = None
        self.previous_post = None
        self.velocity = {}
        self.pre_post_speed = {}
        self.pre_post_residual = {}
        self.adjacent_post_speed = {}
        self.point_velocity_residual = {}
        self.integral = {}
        self.pose_displacement = {}
        self.contact_availability = {
            key: {
                "available": 0,
                "unavailable": 0,
                "minimum": None,
                "maximum": None} for key in (
                "rms_error",
                "constraint_residual",
                "num_contacts")}
        self.wheel_zero = {
            "motor_both_exact_zero_task_samples": 0,
            "motor_and_joint_both_exact_zero_task_samples": 0,
            "maximum_body_planar_speed_when_motor_both_zero": 0.0,
            "motor_both_zero_body_planar_above_original_rest_threshold_samples": 0,
            "scope": (
                'Exact motor GetParam(vel) readbacks only; no private de'
                'sired/applied/target ACK inferred. Counts above .01 are'
                ' explanatory, never a replacement stop verdict.'
            )}
        self.contacts = {
            "samples_with_retained_own_static_evidence": 0,
            "samples_without_retained_evidence": 0,
            "fresh_contact_records": 0,
            "post_solve_wrench_points": 0,
            "collision_pairs": set(),
            "scope": (
                'Retained own-vs-static records only; absence is not pro'
                'of of no physical contact, and world residuals do not i'
                'dentify a per-robot cause.'
            )}

    def record(self, row):
        need(type(row) is dict and row.get("schema") == SCHEMA, "unknown_observer_schema")
        need(row.get("epoch") == self.epoch and row.get("robot") == self.robot,
             "wrong_observer_identity", robot=self.robot)
        sequence = integer(row.get("record_sequence"), "record_sequence", 1)
        need(sequence == self.last_record + 1,
             "record_sequence_gap_or_duplicate",
             robot=self.robot)
        self.last_record = sequence
        clock = integer(row.get("sim_time_ns"), "sim_time_ns")
        iteration = integer(row.get("world_iterations"), "world_iterations")
        wall = integer(row.get("wall_monotonic_ns"), "wall_monotonic_ns")
        need(self.last_wall is None or wall >= self.last_wall, "observer_wall_clock_rewind")
        self.last_wall = wall
        need(row.get("measurements_finite") is True, "producer_measurements_nonfinite")
        finite_tree(row)
        kind = row.get("kind")
        if kind == "configuration":
            need(sequence == 1 and self.header is None, "duplicate_or_late_configuration")
            self.header = row
            self.expected = self.validate_header(row)
            return
        need(self.header is not None, "missing_configuration")
        need(not self.complete, "record_after_capture_complete")
        if kind == "capture_complete":
            need(
                self.pending is None and clock > self.header["end_ns"],
                "invalid_capture_complete")
            need(row["last_pair_sequence"] == self.last_pair, "capture_complete_pair_mismatch")
            self.complete = True
            return
        need(kind == "sample", "unknown_observer_record_kind", kind=kind)
        need(type(row.get("physics_enabled")) is bool, "untyped_physics_enabled")
        if self.start <= clock <= self.end:
            need(row["physics_enabled"] is True, "task_physics_disabled")
        phase = row.get("phase")
        need(phase in (PRE, POST), "unknown_observer_phase", phase=phase)
        pair = integer(row.get("pair_sequence"), "pair_sequence", 1)
        before_sequence = integer(row.get("before_record_sequence"), "before_record_sequence", 1)
        need(type(row.get("pair_iterations")) is int and row["pair_iterations"] == iteration,
             "pair_iteration_field_mismatch")
        need(row.get("before_clock_ns") == clock and type(row.get("before_clock_ns")) is int,
             "before_clock_mismatch")
        need(self.header["start_ns"] <= clock <=
             self.header["end_ns"], "sample_outside_capture_window")
        values = entities(row, self.robot, self.expected)
        if phase == PRE:
            need(self.pending is None, "missing_post_before_next_pre")
            need(pair == self.last_pair + 1 and before_sequence ==
                 sequence, "pair_sequence_or_reference_mismatch")
            if self.last_clock is not None:
                need(clock == self.last_clock + TICK_NS and iteration == self.last_iteration + 1,
                     "physics_pair_gap_or_duplicate")
            self.pending = (row, values)
            if self.first_pair_clock is None:
                self.first_pair_clock = clock
        else:
            need(self.pending is not None, "post_without_pre")
            pre, pre_values = self.pending
            need(pair == pre["pair_sequence"] and before_sequence ==
                 pre["record_sequence"], "wrong_pre_reference")
            need(clock == pre["sim_time_ns"] and iteration == pre["world_iterations"],
                 "pre_post_clock_or_iteration_mismatch")
            if "pair_iterations" in row:
                need(type(row["pair_iterations"]) is int and row["pair_iterations"] == iteration,
                     "pair_iteration_field_mismatch")
            if self.start <= clock <= self.end:
                need(clock == self.next_task_clock, "task_capture_missing_or_duplicate_tick")
                self.next_task_clock += TICK_NS
                self.task_clocks += 1
                self.observe(pre, row, pre_values, values)
            self.previous_post = values
            self.last_pair = pair
            self.last_clock = clock
            self.last_iteration = iteration
            self.pending = None
        self.last_sample_phase = phase

    def stat(self, collection, key, values):
        collection.setdefault(key, VectorStats()).add(values)

    def observe(self, pre, post, pre_values, post_values):
        dt = TICK_NS / 1e9
        for phase, row, values in (("pre", pre, pre_values), ("post", post, post_values)):
            for name, value in values.items():
                if name.endswith("residual"):
                    self.stat(self.point_velocity_residual, phase + "." + name, value)
                else:
                    self.stat(self.velocity, phase + "." + name, value[1])
            for key, counter in self.contact_availability.items():
                datum = row["solver_diagnostics_world_scope"][key]
                if datum["available"]:
                    counter["available"] += 1
                    counter["minimum"] = datum["value"] if counter["minimum"] is None else min(
                        counter["minimum"], datum["value"])
                    counter["maximum"] = datum["value"] if counter["maximum"] is None else max(
                        counter["maximum"], datum["value"])
                else:
                    counter["unavailable"] += 1
            joints = row["joints_right_left"]
            contacts = row["contacts"]
            self.contacts["samples_with_retained_own_static_evidence" if contacts["available"]
                          else "samples_without_retained_evidence"] += 1
            for record in contacts.get("records", []):
                if record["available"]:
                    self.contacts["fresh_contact_records"] += 1
                    self.contacts["collision_pairs"].add(
                        (record["collision1"], record["collision2"]))
                self.contacts["post_solve_wrench_points"] += sum(
                    point["forces"]["available"] is True for point in record.get("points", []))
            if all(item["motor_velocity_target_radps"] == 0 for item in joints):
                self.wheel_zero["motor_both_exact_zero_task_samples"] += 1
                if all(item["velocity_radps"] == 0 for item in joints):
                    self.wheel_zero["motor_and_joint_both_exact_zero_task_samples"] += 1
                speed = number(math.hypot(*values["model"][1][:2]), "derived_zero_motor_speed")
                self.wheel_zero["maximum_body_planar_speed_when_motor_both_zero"] = max(
                    self.wheel_zero["maximum_body_planar_speed_when_motor_both_zero"], speed)
                self.wheel_zero[(
                    'motor_both_zero_body_planar_above_original_rest_thresho'
                    'ld_samples'
                )] += int(
                    speed > .01)
        # At start the same-clock pair is a boundary anchor; its preceding
        # [T-h,T] integration interval is not charged as task motion.
        if post["sim_time_ns"] == self.start:
            return
        for name, value in post_values.items():
            if name.endswith("residual"):
                continue
            displacement = sub(value[0], pre_values[name][0])
            expected = [number((a + b) * .5 * dt, "trapezoid_displacement")
                        for a, b in zip(pre_values[name][1], value[1])]
            self.stat(
                self.pre_post_speed, name, [
                    number(
                        x / dt, "pre_post_speed") for x in displacement])
            self.stat(self.pre_post_residual, name, sub(displacement, expected))
            self.integral[name] = [number(a + b, "integral_sum")
                                   for a,
                                   b in zip(self.integral.get(name,
                                                              [0.,
                                                               0.,
                                                               0.]),
                                            expected)]
            self.pose_displacement[name] = [
                number(
                    a + b, "displacement_sum") for a, b in zip(
                    self.pose_displacement.get(
                        name, [
                            0., 0., 0.]), displacement)]
            if self.previous_post is not None:
                adjacent = sub(value[0], self.previous_post[name][0])
                self.stat(
                    self.adjacent_post_speed, name, [
                        number(
                            x / dt, "adjacent_post_speed") for x in adjacent])

    def finish(self):
        need(self.header is not None, "missing_configuration")
        need(self.pending is None and self.last_sample_phase == POST, "incomplete_final_pair")
        need(self.next_task_clock == self.end + TICK_NS,
             "task_interval_not_fully_captured", robot=self.robot, next_clock=self.next_task_clock)
        return {"robot": self.robot, "configuration": self.header,
                "record_count": self.last_record, "pair_count": self.last_pair,
                "first_pair_clock_ns": self.first_pair_clock,
                "last_pair_clock_ns": self.last_clock,

                "task_pairs_including_start_anchor": self.task_clocks,
                "task_integration_intervals": self.task_clocks - 1,
                "capture_complete_record_present": self.complete,
                "velocity": {k: v.result() for k, v in self.velocity.items()},
                "pre_post_pose_finite_difference_speed": {k: v.result() for k,
                                                          v in self.pre_post_speed.items()},

                "adjacent_post_pose_finite_difference_speed": {
                    k: v.result() for k, v in self.adjacent_post_speed.items()},





                "pre_post_trapezoid_displacement_residual": {k: v.result() for k,
                                                             v in self.pre_post_residual.items()},

                "point_velocity_residual": {k: v.result() for k,
                                            v in self.point_velocity_residual.items()},

                "integrated_velocity_xyz": self.integral,
                "summed_pre_post_displacement_xyz": self.pose_displacement,
                "integral_residual_xyz": {k: sub(self.pose_displacement[k],
                                                 v) for k,
                                          v in self.integral.items()},

                "world_solver_diagnostic_availability": self.contact_availability,
                "contacts": {**self.contacts,
                             "collision_pairs": sorted(self.contacts["collision_pairs"])},

                "wheel_zero_diagnostics": self.wheel_zero,
                "scope": (
                    'Finite sampled model/link/CoG explanatory statistics on'
                    'ly. No physical-stop, contact-cause, continuous-path or'
                    ' task-success verdict.'
                )}


def transition_interval(rows, epoch):
    need(bool(rows) and rows[0].get("kind") == "reset", "missing_actual_reset")
    reset = rows[0]
    need(reset["snapshot"]["epoch"] == epoch and reset["info"]["epoch"] == epoch,
         "transition_epoch_mismatch")

    def ns(value):
        return round(number(value, "transition_time") * 1e9)
    start = ns(reset["snapshot"]["source_stamp"])
    need(type(reset["info"]["release_time_ns"]) is int
         and reset["info"]["release_time_ns"] == start, "task_start_release_mismatch")
    need(ns(reset["info"]["reward_diagnostics"]["effective_step_end"]) == start,
         "initial_reward_boundary_mismatch")
    need(start % TICK_NS == 0, "unaligned_task_start")
    previous = start
    for row in rows[1:]:
        need(row.get("kind") == "step" and row["info"]["epoch"] == epoch
             and row["snapshot"]["epoch"] == epoch, "transition_epoch_or_kind_mismatch")
        info = row["info"]
        diagnostics = info["reward_diagnostics"]
        current = ns(diagnostics["effective_step_end"])
        need(ns(diagnostics["step_start"]) == previous
             and ns(row["snapshot"]["source_stamp"]) == current
             and current >= previous, "step_time_boundary_mismatch")
        need(ns(info["dt"]) == current - previous, "actual_dt_boundary_mismatch")
        previous = current
    need(len(rows) > 1 and previous > start and previous % TICK_NS == 0,
         "no_actual_task_interval")
    return {
        "start_ns": start,
        "end_ns": previous,
        "returned_step_calls": len(rows) -
        1,
        "source": (
            'actual reset snapshot.source_stamp/release and step rew'
            'ard effective_step_end; no projected32s or wall time'
        )}


def xml_without_observer(raw, name):
    root = ET.fromstring(raw)
    model = root.find("model")
    need(model is not None, "generated_model_missing")
    matches = [node for node in model.findall("plugin") if node.get("name") == name]
    need(len(matches) == 1, "observer_plugin_not_unique")
    plugin = matches[0]
    model.remove(plugin)
    return root, plugin


def original_render(template_raw, episode, robot, epoch):
    """Independently derive the pre-observer bytes from the immutable template."""
    value = template_raw.decode()
    for tag, replacement in {"mr3_audit_path": str(episode / ("drive_" + robot + ".jsonl")),
                             "mr3_epoch": epoch, "mr3_tagged_commands": "true"}.items():
        placeholder = "<" + tag + "/>"
        need(value.count(placeholder) == 1, "original_placeholder_not_unique", tag=tag)
        value = value.replace(
            placeholder,
            "<" +
            tag +
            ">" +
            escape(replacement) +
            "</" +
            tag +
            ">")
    return value.encode()


def profile_record(path, bindings, expected_sha):
    raw = Path(path).read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    need(actual == expected_sha, "profile_ledger_sha256_mismatch")
    bindings[str(path)] = {"bytes": len(raw), "sha256": actual}
    need(raw.endswith(b"\n"), "truncated_profile_ledger")
    rows = [decode(line) for line in raw.splitlines()]
    need(len(rows) == 1, "profile_ledger_not_single_first_boundary")
    return rows[0]


def stat_identity(raw):
    prefix, rest = text(raw, "proc.stat_raw").rsplit(")", 1)
    pid = int(prefix.split("(", 1)[0].strip())
    fields = rest.split()
    return {
        "pid": pid, "parent": int(
            fields[1]), "start_ticks": int(
            fields[19]), "state": fields[0]}


def ancestry_proof(value, owned):
    need(value.get("schema") == "mr3-live-owned-ancestry-v1", "unknown_ancestry_schema")
    rows = value["before"]
    need(type(rows) is list and bool(rows), "empty_owned_ancestry")
    seen = set()
    for index, row in enumerate(rows):
        actual = stat_identity(row["stat_raw"])
        for key in ("pid", "parent", "start_ticks"):
            integer(row[key], "ancestry." + key, 0 if key == "parent" else 1)
            need(same(row[key], actual[key]), "ancestry_raw_stat_mismatch", field=key)
        need(row["state"] == actual["state"] and row["state"] not in ("Z", "X"),
             "owned_identity_not_live_at_witness")
        identity = (row["pid"], row["start_ticks"])
        need(identity not in seen, "owned_ancestry_cycle")
        seen.add(identity)
        if index:
            need(rows[index - 1]["parent"] == row["pid"], "owned_ancestry_parent_mismatch")
    need(rows[0]["pid"] == owned["pid"] and rows[0]["start_ticks"] == owned["start_ticks"],
         "owned_server_ancestry_mismatch")
    benchmark = value["benchmark_identity"]
    need(same(rows[-1]["pid"], benchmark["pid"])
         and same(rows[-1]["start_ticks"], benchmark["start_ticks"]), "wrong_benchmark_ancestor")
    after = value["after"]
    actual = stat_identity(after["stat_raw"])
    need(
        same(
            after["pid"],
            owned["pid"]) and same(
            after["start_ticks"],
            owned["start_ticks"]) and all(
                same(
                    after[key],
                    actual[key]) for key in (
                        "pid",
                        "parent",
                        "start_ticks",
                        "state")) and actual["state"] not in (
                            "Z",
                            "X"),
        "owned_server_changed_at_witness")


def library_proof(spec, maps_raw, source_sha, bindings):
    need(spec["source_sha256"] == source_sha, "unknown_compiled_source")
    digest_text(spec["library_sha256"], "library_sha256")
    integer(spec["library_bytes"], "library_bytes", 1)
    selected = Path(text(spec["installed_path"], "installed_path")).resolve(strict=True)
    need(str(selected) == spec["loaded_library_realpath"], "loaded_library_realpath_mismatch")
    info = bind_file(selected, bindings, spec["library_sha256"])
    need(info.st_size == spec["library_bytes"], "library_size_mismatch")
    with selected.open("rb") as stream:
        need(stream.read(4) == b"\x7fELF", "loaded_object_is_not_elf")
    matched = []
    for line in maps_raw.decode().splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or fields[5] != str(selected):
            continue
        major, minor = [int(x, 16) for x in fields[3].split(":")]
        need(int(fields[4]) == info.st_ino
             and (major, minor) == (os.major(info.st_dev), os.minor(info.st_dev)),
             "library_maps_inode_device_mismatch")
        matched.append(fields)
    need(bool(matched) and any("x" in row[1] for row in matched), "library_not_executable_mapped")
    return {"installed_path": str(selected), "library_sha256": spec["library_sha256"],
            "map_rows": len(matched), "source_sha256": source_sha}


def validate_profile(ledger, proof, binding_raw, binding):
    need(ledger.get("schema") == "mr3-physics-diagnostic-profile-v1"
         and ledger.get("kind") == "first_boundary_profile", "unknown_profile_ledger")
    need(ledger["epoch"] == proof["epoch"] and ledger["process_id"] ==
         proof["owned_gzserver"]["pid"], "profile_ledger_identity_mismatch")
    integer(ledger["process_id"], "profile.process_id", 1)
    need(type(ledger["record_sequence"]) is int and ledger["record_sequence"] == 1,
         "profile_ledger_sequence_mismatch")
    need(type(ledger["sim_time_ns"]) is int and ledger["sim_time_ns"] == TICK_NS
         and type(ledger["world_iterations"]) is int and ledger["world_iterations"] == 1,
         "profile_not_exact_first_boundary")
    need(ledger["compiled_source_sha256"] == PROFILE_SOURCE_SHA256
         and ledger["loaded_library_path"] == proof["profile"]["loaded_library_realpath"],
         "profile_source_or_library_mismatch")
    need(
        ledger["binding_json"].encode() == binding_raw and Path(
            ledger["binding_path"]).resolve() == Path(
            proof["runtime_binding"]["path"]).resolve(),
        "profile_consumed_binding_bytes_mismatch")
    need(ledger["mode"] == proof["profile"]["mode"] == binding["mode"], "profile_mode_mismatch")
    need(proof["profile"]["mode"] in ("baseline", "iters150"), "unknown_profile_mode")
    expected = 50 if ledger["mode"] == "baseline" else 150
    need(type(proof["profile"]["expected_iters"]) is int and proof["profile"]
         ["expected_iters"] == expected, "profile_expected_iters_mismatch")
    need(type(ledger["setter_call_count"]) is int and ledger["setter_call_count"]
         == (0 if expected == 50 else 1), "profile_setter_count_mismatch")
    before, after = ledger["before"], ledger["after"]
    for snapshot, count in ((before, 50), (after, expected)):
        need(snapshot["engine_type"] == "ode" and same(snapshot["max_step_size_sec"], .001),
             "profile_engine_or_step_mismatch")
        need(type(snapshot["native_ode"]["iters"]) is int
             and snapshot["native_ode"]["iters"] == count
             and type(snapshot["cached"]["iters"]["value"]) is int
             and snapshot["cached"]["iters"]["value"] == count, "profile_native_iters_mismatch")
        need(snapshot["cached"]["solver_type"]["value"] == "quick"
             and same(snapshot["cached"]["sor"]["value"], 1.3)
             and same(snapshot["native_ode"]["sor"], 1.3), "profile_solver_baseline_mismatch")
        for key in NATIVE_KEYS:
            need(key in snapshot["native_ode"], "profile_native_key_missing", key=key)
        for key in ("iters", "precon_iters", "friction_model_enum"):
            integer(snapshot["native_ode"][key], "profile.native_ode." + key)
        for key in (
            "sor",
            "cfm",
            "erp",
            "contact_max_correcting_vel",
            "contact_surface_layer",
                "sor_lcp_tolerance"):
            number(snapshot["native_ode"][key], "profile.native_ode." + key)
        vector(snapshot["native_ode"]["gravity_xyz"], "profile.native_ode.gravity_xyz")
        need(bool(snapshot["engine_sdf"]), "profile_engine_sdf_missing")

    def invariants(value):
        value = json.loads(canonical(value))
        value["cached"].pop("iters")
        value["native_ode"].pop("iters")
        value.pop("engine_sdf")
        return value
    need(same(invariants(before), invariants(after)), "profile_changed_more_than_iters")
    return before, after


def prepare_admission(proof_path, plan_path, run, freeze, bindings):
    proof = read_json(proof_path, bindings)
    need(proof.get("schema") == "mr3-stop-observer-admission-proof-v1"
         and proof.get("passed") is True, "unknown_or_failed_admission_proof")
    need(type(freeze) is str and re.fullmatch("[0-9a-f]{40}", freeze) is not None
         and proof["freeze"] == freeze, "admission_freeze_mismatch")
    plan = read_json(plan_path, bindings, digest_text(proof["plan_sha256"], "plan_sha256"))
    text(proof["stage"], "stage")
    need(
        type(
            plan.get("stages")) is list and sum(
            row.get("stage") == proof["stage"] for row in plan["stages"]) == 1,
        "admission_stage_not_unique_in_plan")
    stage = next(row for row in plan["stages"] if row.get("stage") == proof["stage"])
    need(Path(proof["run_directory"]).resolve() == run.resolve()
         and Path(stage["run_directory"]).resolve() == run.resolve(), "admission_run_mismatch")
    need(same(proof["robot_order"], list(ROBOTS)), "wrong_robot_order")
    episode = Path(proof["episode_directory"])
    need(episode.is_dir() and episode.resolve().is_relative_to(run.resolve()),
         "episode_outside_run")
    required_episode = run / ("worker0/episode001_" +
                              str(stage["scene"]) + "_" + str(stage["seed"]))
    need(episode.resolve() == required_episode.resolve(), "wrong_declared_first_episode")
    epoch = text(proof["epoch"], "epoch")
    metadata = read_json(episode / "metadata.json", bindings)
    need(metadata.get("epoch") == epoch and metadata.get("freeze") == freeze
         and same(metadata.get("scene"), stage["scene"])
         and same(metadata.get("seed"), stage["seed"]), "episode_metadata_binding_mismatch")
    for name in ("observer", "profile"):
        declared, admitted = plan["diagnostic_libraries"][name], proof[name]
        need(declared["source_sha256"] == admitted["source_sha256"]
             and declared["installed_path"] == admitted["installed_path"]
             and declared["library_sha256"] == admitted["library_sha256"]
             and same(declared["library_bytes"], admitted["library_bytes"]),
             "admission_library_differs_from_plan", library=name)
        source_path = Path(declared["source_path"])
        source_path = source_path if source_path.is_absolute() else ROOT / source_path
        bind_file(source_path, bindings, declared["source_sha256"])
        build_library = Path(declared["library_path"])
        bind_file(build_library, bindings, declared["library_sha256"])
        need(build_library.resolve(strict=True) == Path(admitted["loaded_library_realpath"]),
             "declared_build_library_differs_from_loaded_library", library=name)
    owned = proof["owned_gzserver"]
    integer(owned["pid"], "owned_gzserver.pid", 1)
    integer(owned["start_ticks"], "owned_gzserver.start_ticks", 1)
    need(owned["observer_mapped"] is True and owned["profile_mapped"]
         is True, "admission_library_not_mapped")
    maps_path = Path(owned["maps_path"])
    maps_raw = maps_path.read_bytes()
    need(hashlib.sha256(maps_raw).hexdigest() == owned["maps_sha256"], "maps_sha256_mismatch")
    bindings[str(maps_path)] = {"bytes": len(maps_raw), "sha256": owned["maps_sha256"]}
    ancestry = read_json(owned["ancestry_path"], bindings, owned["ancestry_sha256"])
    ancestry_proof(ancestry, owned)
    libraries = {
        "observer": library_proof(
            proof["observer"],
            maps_raw,
            OBSERVER_SOURCE_SHA256,
            bindings),
        "profile": library_proof(
            proof["profile"],
            maps_raw,
            PROFILE_SOURCE_SHA256,
            bindings)}
    binding_path = Path(proof["runtime_binding"]["path"])
    binding_raw = binding_path.read_bytes()
    need(hashlib.sha256(binding_raw).hexdigest() ==
         proof["runtime_binding"]["sha256"], "runtime_binding_sha256_mismatch")
    bindings[str(binding_path)] = {"bytes": len(binding_raw),
                                   "sha256": proof["runtime_binding"]["sha256"]}
    binding = decode(binding_raw)
    need(binding.get("schema") == "mr3-physics-diagnostic-binding-v1"
         and binding["epoch"] == epoch
         and Path(binding["episode_directory"]).resolve() == episode.resolve(),





         "runtime_binding_identity_mismatch")
    config_proof = stage["configuration_binding"]
    config_path = Path(config_proof["path"])
    config_path = config_path if config_path.is_absolute() else ROOT / config_path
    config = read_json(config_path, bindings, config_proof["sha256"])
    need(binding.get("config_sha256") == config_proof["sha256"]
         and Path(binding["config_source"]).resolve() == config_path.resolve(),
         "runtime_binding_config_mismatch")
    need(config.get("schema") == "mr3-physics-diagnostic-config-v1"
         and config.get("mode") == binding["mode"] == proof["stage"]
         and config.get("run_directory") == str(run)
         and same(config.get("scene"), stage["scene"])
         and same(config.get("seed"), stage["seed"])
         and config.get("episode_relative_directory") == str(episode.relative_to(run)),
         "configuration_stage_identity_mismatch")
    need(
        same(
            config.get("capture_start_ns"),
            CAPTURE_START_NS) and same(
            config.get("capture_end_ns"),
            CAPTURE_END_NS) and same(
                binding.get("capture_start_ns"),
                CAPTURE_START_NS) and same(
                    binding.get("capture_end_ns"),
                    CAPTURE_END_NS),
        "binding_capture_window_mismatch")
    bind_file(binding["world_path"], bindings, binding["world_sha256"])
    need(
        type(
            binding.get("observer_outputs")) is dict and set(
            binding["observer_outputs"]) == set(ROBOTS),
        "runtime_binding_observer_outputs_missing")
    need(binding.get("profile_output_path") == proof["profile"]["ledger_path"],
         "runtime_binding_profile_output_mismatch")
    for name in ("observer", "profile"):
        spec, admitted = binding[name + "_library"], proof[name]
        need(spec.get("path") == admitted["installed_path"]
             and spec.get("resolved_path") == admitted["loaded_library_realpath"]
             and spec.get("source_sha256") == admitted["source_sha256"]
             and spec.get("sha256") == admitted["library_sha256"],
             "runtime_binding_library_mismatch", library=name)
        need(same(config[name + "_library"],
                  {key: spec[key] for key in ("path",
                                              "sha256",
                                              "source_sha256")}),
             "configuration_library_mismatch",
             library=name)
    ledger = profile_record(
        proof["profile"]["ledger_path"],
        bindings,
        proof["profile"]["ledger_sha256"])
    before, after = validate_profile(ledger, proof, binding_raw, binding)
    need(set(proof["generated_models"]) == set(ROBOTS)
         and set(proof["observer_files"]) == set(ROBOTS), "missing_robot_evidence")
    expected = {}
    for robot in ROBOTS:
        entry = proof["generated_models"][robot]
        model_raw = Path(entry["path"]).read_bytes()
        need(
            hashlib.sha256(model_raw).hexdigest() == entry["sha256"],
            "generated_model_sha256_mismatch",
            robot=robot)
        bindings[str(entry["path"])] = {"bytes": len(model_raw), "sha256": entry["sha256"]}
        base_raw = Path(entry["before_observer_path"]).read_bytes()
        need(hashlib.sha256(base_raw).hexdigest() ==
             entry["before_observer_sha256"], "before_observer_sha256_mismatch")
        bindings[str(entry["before_observer_path"])] = {"bytes": len(
            base_raw), "sha256": entry["before_observer_sha256"]}
        template = entry["original_template"]
        bind_file(template["path"], bindings, template["sha256"])
        template_raw = Path(template["path"]).read_bytes()
        need(type(template.get("bytes")) is int and len(template_raw) == template["bytes"],
             "template_size_mismatch")
        need(base_raw == original_render(template_raw, episode, robot, epoch),
             "before_observer_not_original_render", robot=robot)
        need(entry.get("original_render_rule") == "exact three original driver placeholders only",
             "unknown_original_render_rule")
        need(entry["original_body_bytes_preserved"] is True, "original_model_not_preserved")
        need(binding["observer_outputs"][robot] == proof["observer_files"][robot]["path"],
             "runtime_binding_observer_output_mismatch", robot=robot)
        _, plugin = xml_without_observer(model_raw, entry["observer_plugin_name"])
        actual_text = model_raw.decode()
        literal = '  <plugin name="' + entry["observer_plugin_name"] + '"'
        need(actual_text.count(literal) == 1, "observer_literal_plugin_not_unique")
        begin = actual_text.index(literal)
        end = actual_text.index("  </plugin>\n", begin) + len("  </plugin>\n")
        need((actual_text[:begin] + actual_text[end:]).encode() == base_raw,
             "observer_injection_changed_original_bytes")
        need(
            plugin.get(
                "filename") == entry["observer_library"] == proof["observer"]["installed_path"],
            "observer_plugin_library_mismatch")
        for key, value in {"epoch": epoch,
                           "robot": robot,
                           "output_path": proof["observer_files"][robot]["path"],

                           "base_link": "base_link",
                           "right_joint": "wheel_right_joint",
                           "left_joint": "wheel_left_joint"}.items():
            need(
                plugin.findtext(key) == value,
                "observer_plugin_field_mismatch",
                robot=robot,
                field=key)
        need(plugin.findtext("start_ns") == str(CAPTURE_START_NS) and plugin.findtext(
            "end_ns") == str(CAPTURE_END_NS), "observer_capture_window_mismatch")
        expected[robot] = {
            "base": robot + "::base_link",
            "joints": [
                robot + "::wheel_right_joint",
                robot + "::wheel_left_joint"],
            "source_model_path": entry["path"],
            "before_observer_path": entry["before_observer_path"]}
    return {"proof": proof, "episode": episode, "epoch": epoch, "stage": stage,
            "binding": binding, "ledger": ledger, "profile_before": before, "profile_after": after,
            "libraries": libraries, "expected": expected}


def header_validator(context, robot, row):
    proof = context["proof"]
    need(row.get("process_id") == proof["owned_gzserver"]["pid"] and type(
        row.get("process_id")) is int, "observer_process_id_mismatch")
    need(row["compiled_source_sha256"] == OBSERVER_SOURCE_SHA256,
         "unknown_observer_compiled_source")
    need(row["loaded_library_path"] == proof["observer"]["loaded_library_realpath"],
         "observer_loaded_library_mismatch")
    need(row["world_name"] == context["binding"]["world_name"] == context["ledger"]["world_name"],
         "observer_world_mismatch")
    need(row["physics_type"] == "ode" and same(
        row["max_step_size_sec"], .001), "observer_engine_or_step_mismatch")
    vector(row["gravity_xyz"], "configuration.gravity_xyz")
    need(row.get("physics_parameters_scope") == (
        'public_GetParam; solver_type/iters/sor/cfm/erp_are_SDF_'
        'cached'
    )
        and row.get("observer_effect") == (
        'synchronous getter/JSON/stdio wall-time overhead; no se'
        'tter or transport publisher'
    )
        and row.get("axis_get_force_scope") == (
        'Joint::GetForce readback, not a promised motor/solver r'
        'eaction wrench'
    ),
        "configuration_readback_scope_mismatch")
    need(type(row["start_ns"]) is int and row["start_ns"] == CAPTURE_START_NS and type(
        row["end_ns"]) is int and row["end_ns"] == CAPTURE_END_NS, "unknown_capture_configuration")
    need(row["read_only"] is True and row["per_packet_or_driver_private_sequence"] is False
         and row["flush_per_completed_pair"] is True, "unknown_observer_configuration")
    need(row["base_name"] == context["expected"][robot]["base"]
         and type(row["canonical_name"]) is str and row["canonical_name"].startswith(robot + "::"),
         "observer_header_scoped_links_mismatch")
    values = native_values(row["native_ode"])
    matches = []
    for label in ("before", "after"):
        original = context["profile_" + label]["native_ode"]
        if all(same(values[key], original[key]) for key in NATIVE_KEYS):
            matches.append(label)
    need(bool(matches), "configuration_native_values_match_neither_profile_state")
    row["_reader_configuration_profile_matches"] = matches
    for key in ("solver_type", "iters", "sor", "cfm", "erp"):
        datum = row["physics_parameters"][key]
        need(
            datum.get("available") is True and datum.get(
                "readback_scope") == "sdf_cached_public_GetParam",
            "cached_parameter_claim_or_availability_mismatch",
            parameter=key)
        need(any(same(datum.get("value"),
                      context["profile_" + label]["cached"][key]["value"]) for label in ("before",
                                                                                         "after")),
             "configuration_cached_value_mismatch",
             parameter=key)
    # Load may precede the actual first-boundary setter. Do not invent an
    # atomic loader/profile order. Only the samples prove applied task values.
    return {**context["expected"][robot], "canonical": row["canonical_name"],
            "native_values": context["profile_after"]["native_ode"]}


def audit(run, freeze, plan_path, proof_path, bindings=None):
    bindings = {} if bindings is None else bindings
    context = prepare_admission(proof_path, plan_path, Path(run), freeze, bindings)
    rows = list(line_rows(context["episode"] / "transitions.jsonl", bindings))
    interval = transition_interval(rows, context["epoch"])
    need(len(rows) == 33 and all(row.get("terminated") is False for row in rows)
         and rows[-1].get("truncated") is True
         and rows[-1]["info"].get("reason") == "external_sampler_limit",
         "diagnostic_not_complete_32_step_workload")
    need(all(row.get("truncated") is False for row in rows[:-1]), "early_truncated_diagnostic")
    need(interval["start_ns"] >= CAPTURE_START_NS and interval["end_ns"] <= CAPTURE_END_NS,
         "task_outside_predeclared_capture_window")
    results = []
    for robot in ROBOTS:
        replay = CaptureReplay(robot, context["epoch"], interval["start_ns"], interval["end_ns"],
                               lambda row, robot=robot: header_validator(context, robot, row))
        file_proof = context["proof"]["observer_files"][robot]
        for row in line_rows(file_proof["path"], bindings, first_line=file_proof):
            replay.record(row)
        results.append(replay.finish())
    for path, proof in bindings.items():
        actual, size = sha_file(path)
        need(actual == proof["sha256"] and size == proof["bytes"],
             "input_changed_before_verdict", path=path)
    return {
        "schema": "mr3-independent-stop-observer-review-v1",
        "passed": True,
        "errors": [],
        "freeze": freeze,
        "stage": context["proof"]["stage"],
        "epoch": context["epoch"],
        "run_directory": str(
            Path(run)),
        "episode_directory": str(
            context["episode"]),
        "actual_interval": interval,
        "robots": results,
        "profile_ledger": context["ledger"],
        "loaded_libraries": context["libraries"],
        "owned_gzserver": context["proof"]["owned_gzserver"],
        "inputs": bindings,
        "consumer_sha256": hashlib.sha256(
            Path(__file__).read_bytes()).hexdigest(),
        "limitations": [
            (
                'Capture/provenance/finite-data review and explanatory s'
                'tatistics only; no task, policy or preparation-matrix a'
                'cceptance.'
            ),
            (
                'Original30Hz .01/three-source/.78/.144 stopping, full b'
                'ody/angular/contact and native close audits remain sepa'
                'rate and unchanged.'
            ),
            (
                'Retained contact availability is not proof of absence; '
                'GetForce/motor references do not establish a reaction w'
                'rench or physical rest.'
            ),
            (
                'Finite differences and integrals are sampled evidence. '
                'Load-time configuration is allowed before the one first'
                '-boundary profile application; every sample must match '
                'actual post-profile native values.'
            ),
            (
                'No ROS/production imports, new native launch, setters, '
                'process control or truth feedback into actor/candidates'
                '/reward.'
            )]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--admission-proof", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    bindings = {}
    try:
        result = audit(args.directory, args.freeze, args.plan, args.admission_proof, bindings)
    except AuditError as error:
        result = {"schema": "mr3-independent-stop-observer-review-v1", "passed": False,
                  "errors": [{"code": error.code,
                              "context": error.context}],
                  "freeze": args.freeze}
    except (OSError, ValueError, TypeError, KeyError, IndexError,
            OverflowError, ET.ParseError) as error:
        result = {"schema": "mr3-independent-stop-observer-review-v1",
                  "passed": False,
                  "errors": [{"code": "malformed_or_unavailable_input",
                              "exception_type": type(error).__name__,
                              "message": str(error)}],
                  "freeze": args.freeze}
    result.setdefault("inputs", bindings)
    result.setdefault("consumer_sha256", hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    result.setdefault("run_directory", str(args.directory))
    result.setdefault("plan_path", str(args.plan))
    result.setdefault("admission_proof_path", str(args.admission_proof))
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"],
                      "errors": result["errors"],
                      "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
