"""Independent read-only WORLD odometry cadence and received-source audit.

The original drive, information, control, settled-turn and body-response gates
remain necessary. This audit adds the independent20ms publisher contract; it
does not claim a body repair or replace source/loaded-ELF custody.
"""

import argparse
import bisect
from decimal import Decimal
import hashlib
import json
import math
from pathlib import Path
import re
import xml.etree.ElementTree as ET


ROBOTS = ("tb1", "tb2", "tb3")
PERIOD = 20_000_000
ACTUATION = 34_000_000
COMPILED = ("compiled_source_sha256", "compiled_header_sha256", "compiled_helper_sha256",
            "compiled_target_contract_sha256", "compiled_odometry_json_sha256")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def stamp(message):
    value = message["header"]["stamp"]
    require(type(value["sec"]) is int and type(value["nanosec"]) is int
            and 0 <= value["nanosec"] < 1_000_000_000, "invalid native header timestamp")
    return value["sec"] * 1_000_000_000 + value["nanosec"]


def seconds_ns(value):
    result = Decimal(str(value)) * 1_000_000_000
    require(result.is_finite() and result == result.to_integral_value(), "nonexact second timestamp")
    return int(result)


def finite(value):
    if isinstance(value, dict):
        return all(finite(child) for child in value.values())
    if isinstance(value, list):
        return all(finite(child) for child in value)
    return not isinstance(value, float) or math.isfinite(value)


def packet_publisher(row, robot, kind):
    topic = f"/{robot}/" + ("odom" if kind == "odom" else "tf")
    gid = row["publisher_gid"]
    require(isinstance(gid, str) and re.fullmatch(r"(?:[0-9a-f]{2})+", gid)
            and any(bytes.fromhex(gid)), "actual packet publisher GID unavailable/zero")
    graph = row["publisher_graph"]
    endpoints = graph["endpoints"]
    matching = [value for value in endpoints if value["endpoint_gid"] == gid]
    require(row["topic"] == graph["topic"] == topic and len(matching) == 1
            and matching[0]["namespace"] == "/" + robot
            and matching[0]["node"] == "turtlebot3_diff_drive"
            and matching[0]["topic_type"] == ("nav_msgs/msg/Odometry" if kind == "odom"
                                                else "tf2_msgs/msg/TFMessage")
            and (kind == "tf" or len(endpoints) == 1),
            "actual packet publisher is not the matching native driver endpoint")
    require(row.get("driver_identity_match") is True and row.get("driver_gid_stable") is True
            and row.get("from_intra_process") is False, "actual recorder identity/transport status differs")
    return gid


class Inputs:
    def __init__(self):
        self.bindings = {}
        self.stats = {}

    @staticmethod
    def stat(path):
        value = path.stat()
        return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns

    def raw(self, path):
        before = self.stat(path)
        raw = path.read_bytes()
        require(before == self.stat(path), "source changed while read: " + str(path))
        self.bindings[str(path)] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        self.stats[path] = before
        return raw

    def document(self, path):
        value = json.loads(self.raw(path))
        require(finite(value), "nonfinite JSON in " + str(path))
        return value

    def rows(self, path):
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for line, raw in enumerate(stream, 1):
                require(raw.endswith(b"\n"), "incomplete JSONL record: " + str(path))
                digest.update(raw)
                value = json.loads(raw)
                require(isinstance(value, dict) and finite(value), "invalid/nonfinite JSONL object")
                yield value, {"file": str(path), "line": line,
                              "raw_line_sha256": hashlib.sha256(raw).hexdigest()}
        after = path.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
                "source changed while read: " + str(path))
        self.bindings[str(path)] = {"bytes": after.st_size, "sha256": digest.hexdigest()}
        self.stats[path] = self.stat(path)

    def verify_unchanged(self):
        require(all(self.stat(path) == value for path, value in self.stats.items()),
                "bound original artifact changed before final verdict")


def audit_episode(directory, freeze, inputs):
    meta = inputs.document(directory / "metadata.json")
    require(meta["freeze"] == freeze, "worker freeze differs (identity failure, not a mathematical counterexample)")
    epoch = meta["epoch"]
    transitions = [row for row, _ in inputs.rows(directory / "transitions.jsonl")]
    require(transitions and transitions[0]["kind"] == "reset", "actual reset missing")
    begin = transitions[0]["info"]["release_time_ns"]
    end = seconds_ns(transitions[-1]["snapshot"]["source_stamp"])
    require(type(begin) is int and end > begin, "no completed positive physical observation window")
    result = {"directory": str(directory), "epoch": epoch, "window_ns": [begin, end],
              "robots": {}, "selected_received": {"guard": dict.fromkeys(ROBOTS, 0),
                                                   "information": dict.fromkeys(ROBOTS, 0)}}
    publications = {robot: {} for robot in ROBOTS}
    configs = {}
    receipts = {}

    physical = begin
    for row, _ in inputs.rows(directory / "physics.jsonl"):
        if row.get("steps", 0) > 0 and begin <= row["start_time_ns"] < end:
            require(row.get("epoch") == epoch and row.get("ok") is True
                    and row.get("paused") is True and row["start_time_ns"] == physical
                    and row["steps"] == 20 and row["step_ns"] == 1_000_000
                    and row["end_time_ns"] == physical + PERIOD,
                    "cadence window lacks contiguous actual paused20x1ms physical receipts")
            physical = row["end_time_ns"]
    require(physical == end, "actual physics does not cover the complete cadence window")

    def identity(row, schema=None):
        require(row.get("epoch") == epoch and (schema is None or row.get("schema") == schema),
                "artifact schema/epoch differs")

    for robot in ROBOTS:
        rows = inputs.rows(directory / ("odometry_" + robot + ".jsonl"))
        config, _ = next(rows)
        configs[robot] = config
        identity(config, "mr3-world-odometry-publication-v1")
        require(config["kind"] == "configuration" and config["robot"] == robot
                and config["period_ns"] == PERIOD and config["provider"] == "WORLD"
                and config["phase"] == "world_update_begin_before_actuation"
                and config["actuation_update_rate_hz"] == 30., "native independent odometry configuration differs")
        previous_seq = config["record_sequence"]
        previous_source = -1
        require(previous_seq == 1, "producer configuration sequence differs")
        for row, ref in rows:
            identity(row, "mr3-world-odometry-publication-v1")
            require(row["record_sequence"] == previous_seq + 1 and row["kind"] == "publication"
                    and row["publication_sequence"] == previous_seq
                    and row["publication_scope"] == "actual_publisher_calls_returned_not_delivery"
                    and row["robot"] == robot, "producer sequence/robot/kind/scope differs")
            previous_seq = row["record_sequence"]
            clock = row["source_clock_ns"]
            odom, transform = row["odometry"], row["transform"]
            require(type(clock) is int and clock == row["sim_time_ns"] == stamp(odom) == stamp(transform)
                    and row["odom_published"] is True and row["odom_tf_published"] is True,
                    "published odometry/TF clocks or actual publication scope differ")
            require(clock > previous_source and clock % 1_000_000 == 0,
                    "native source publication is regressed or not on the actual1ms grid")
            previous_source = clock
            require(odom["header"]["frame_id"].lstrip("/") == "odom"
                    and odom["child_frame_id"].lstrip("/") in ("base_footprint", "base_link")
                    and transform["header"] == odom["header"]
                    and odom["header"]["frame_id"] == config["odometry_frame"]
                    and odom["child_frame_id"] == config["robot_base_frame"]
                    and transform["child_frame_id"] == odom["child_frame_id"]
                    and transform["transform"]["translation"] == odom["pose"]["pose"]["position"]
                    and transform["transform"]["rotation"] == odom["pose"]["pose"]["orientation"],
                    "native odometry/TF frame, pose or quaternion differs")
            require(clock not in publications[robot], "duplicate native publication source clock")
            publications[robot][clock] = (row, ref)
        before = [clock for clock in publications[robot] if clock <= begin]
        require(before, "no actual native source at/before release to anchor20ms phase")
        anchor = max(before)
        expected = list(range(anchor if anchor == begin else anchor + PERIOD, end + 1, PERIOD))
        actual = sorted(clock for clock in publications[robot] if begin <= clock <= end)
        require(anchor > begin - PERIOD and actual == expected and bool(actual),
                "native source publication is not complete exact20ms cadence")
        driver_config = None
        actuation = []
        for row, _ in inputs.rows(directory / ("drive_" + robot + ".jsonl")):
            identity(row, "mr3-drive-actuation-v2")
            if row["kind"] == "configuration":
                require(driver_config is None, "duplicate native drive configuration")
                driver_config = row
            elif row["kind"] == "actuation":
                if begin <= row["sim_time_ns"] <= end:
                    require(row["dt_ns"] == ACTUATION, "native wheel update period changed from34ms")
                    actuation.append(row["sim_time_ns"])
        require(driver_config and driver_config["update_rate_hz"] == 30.
                and driver_config["mr3_odometry_period_ns"] == PERIOD
                and driver_config["actuation_algorithm"] == "measured_joint_rim_paired_common_fraction_v1"
                and all(config[key] == driver_config[key] for key in (*COMPILED, "loaded_library_path")),
                "producer/actuator compiled identity or original paired actuation contract differs")
        require(actuation and all(right - left == ACTUATION for left, right in zip(actuation, actuation[1:]))
                and actuation[0] < begin + ACTUATION and actuation[-1] > end - ACTUATION,
                "raw actuator trace is not complete original34ms cadence")
        model = ET.fromstring(inputs.raw(directory / ("drive_model_" + robot + ".sdf")))
        plugins = model.findall(".//plugin[@name='turtlebot3_diff_drive']")
        require(len(plugins) == 1 and not plugins[0].findall("mr3_odometry_period_ns")
                and len(plugins[0].findall("mr3_tagged_commands")) == 1
                and plugins[0].findtext("mr3_tagged_commands") == "true"
                and float(plugins[0].findtext("update_rate")) == 30.,
                "effective SDF tagged fixed cadence or original actuator rate differs")
        result["robots"][robot] = {"publications": len(actual), "period_ns": PERIOD,
                                     "actuations": len(actuation), "actuation_period_ns": ACTUATION}

    gids = {}
    previous_sequence = 0
    previous_wall = -1
    recorder_config = None
    ready = None
    unqualified_startup = 0
    for row, ref in inputs.rows(directory / "driver_odometry_receipts.jsonl"):
        identity(row, "mr3-driver-odometry-receipt-v1")
        require(row["record_sequence"] == previous_sequence + 1, "passive receipt sequence differs")
        previous_sequence = row["record_sequence"]
        require(type(row["clock_ns"]) is int and row["clock_ns"] >= 0
                and type(row["wall_monotonic_ns"]) is int
                and row["wall_monotonic_ns"] >= previous_wall, "passive recorder clock/wall identity differs")
        previous_wall = row["wall_monotonic_ns"]
        kind, robot = row["kind"], row["robot"]
        if kind == "configuration":
            require(recorder_config is None and row["record_sequence"] == 1
                    and row.get("use_sim_time") is True and set(row["robots"]) == set(ROBOTS)
                    and all(row["compiled_odometry_json_sha256"] == value["compiled_odometry_json_sha256"]
                            for value in configs.values())
                    and re.fullmatch(r"[0-9a-f]{64}", row["compiled_source_sha256"]),
                    "actual passive recorder configuration differs")
            recorder_config = row
            continue
        if kind == "ready":
            require(ready is None and recorder_config is not None and row["clock_ns"] <= begin
                    and row["publisher_gids"] == [gids.get((name, stream)) for name in ROBOTS
                                                   for stream in ("odom", "tf")]
                    and len(gids) == 6, "recorder ready lacks six prior genuine packet streams")
            ready = row
            continue
        require(kind in ("odom", "tf") and robot in ROBOTS, "passive receipt kind/robot differs")
        if ready is None and row.get("driver_identity_match") is False and stamp(row["message"]) < begin:
            unqualified_startup += 1
            continue
        gid = packet_publisher(row, robot, kind)
        require((robot, kind) not in gids or gids[(robot, kind)] == gid, "actual driver publisher GID changed")
        gids[(robot, kind)] = gid
        message = row["message"]
        if kind == "tf":
            require(type(row["transform_index"]) is int and row["transform_index"] >= 0
                    and row["tf_message"]["transforms"][row["transform_index"]] == message,
                    "selected driver transform differs from its actual received TFMessage")
        clock = stamp(message)
        source = publications[robot].get(clock)
        require(source is not None and message == source[0]["odometry" if kind == "odom" else "transform"],
                "actual received packet differs from native published payload/source")
        key = (robot, kind, clock)
        require(key not in receipts, "duplicate actual received source packet")
        receipts[key] = (message, ref)
    require(recorder_config is not None and ready is not None, "actual passive recorder never became ready")
    result["passive_recorder"] = {"ready_reference_clock_ns": ready["clock_ns"],
                                  "unqualified_pre_ready_startup_packets": unqualified_startup}
    for robot in ROBOTS:
        for clock in publications[robot]:
            if begin <= clock <= end:
                require(all((robot, kind, clock) in receipts for kind in ("odom", "tf")),
                        "native publication has no complete actual odometry+TF packet receipt")
        result["robots"][robot]["actual_publisher_gids"] = {kind: gids.get((robot, kind)) for kind in ("odom", "tf")}

    def received(robot, message):
        clock = stamp(message)
        actual = receipts.get((robot, "odom", clock))
        require(actual is not None and actual[0] == message,
                "selected pipeline odometry differs from actual received driver packet")
        return clock

    guard = {robot: {} for robot in ROBOTS}
    guard_order = {robot: [] for robot in ROBOTS}

    def latest(order, clock):
        index = bisect.bisect_right(order, (clock, math.inf))
        return order[index - 1] if index else None

    for row, _ in inputs.rows(directory / "motion_safety.jsonl"):
        identity(row)
        value = row["payload"]
        if row["kind"] == "own_odom":
            robot, message = value["robot"], value["message"]
            sequence = value["input_sequence"]
            require(sequence not in guard[robot], "duplicate actual guard odometry ingress sequence")
            guard[robot][sequence] = (stamp(message), message)
            bisect.insort(guard_order[robot], (stamp(message), sequence))
        elif (row["kind"] == "decision" and begin <= value["clock_ns"] <= end
              and value.get("started") is True and value.get("phase_kind") != "stop"):
            robot, own = value["robot"], value.get("own_state")
            require(isinstance(own, dict), "normal guard lacks a selected real own source")
            sequence = own["input_sequences"]["odom"]
            actual = guard[robot].get(sequence)
            require(actual and (actual[0], sequence) == latest(guard_order[robot], value["clock_ns"])
                    and seconds_ns(own["odom_source_stamp"]) == actual[0],
                    "guard selected source is not latest actually received causal odometry")
            received(robot, actual[1])
            result["selected_received"]["guard"][robot] += 1
    ingress = {robot: {} for robot in ROBOTS}
    ingress_order = {robot: [] for robot in ROBOTS}
    for row, _ in inputs.rows(directory / "information_states.jsonl"):
        identity(row)
        value = row["payload"]
        if row["kind"] == "odom_ingress" and value["admission"] == "queued":
            robot, sequence = value["robot"], value["input_sequence"]
            require(sequence not in ingress[robot], "duplicate actual information ingress sequence")
            ingress[robot][sequence] = (value["source_ns"], value["raw"])
            bisect.insort(ingress_order[robot], (value["source_ns"], sequence))
        elif row["kind"] == "state_selection" and begin <= row["clock_ns"] <= end:
            robot, sequence = value["robot"], value.get("odom_input_sequence")
            require(sequence is not None, "controlled information selection lacks actual odometry")
            actual = ingress[robot].get(sequence)
            require(actual and (actual[0], sequence) == latest(ingress_order[robot], row["clock_ns"])
                    and actual[0] == value["odom_source_ns"] == stamp(actual[1]),
                    "information selected source is not latest admitted received causal odometry")
            received(robot, actual[1])
            result["selected_received"]["information"][robot] += 1
    require(all(count > 0 for role in result["selected_received"].values() for count in role.values()),
            "missing three-robot actual selected-received coverage")
    result["passed"] = True
    return result


def audit(directory, freeze):
    directory = Path(directory).resolve()
    inputs = Inputs()
    result = {"schema": "mr3-independent-world-odometry-cadence-v1", "freeze": freeze,
              "episodes": [], "errors": [], "missing": [],
              "scope": "new20ms WORLD odometry/driverTF, actual received-source and unchanged34ms actuation; "
                       "not a body repair, continuous safety, original34 roles or loaded-ELF custody PASS"}
    require(re.fullmatch(r"[0-9a-f]{40}", freeze), "exact40hex freeze required")
    episodes = [directory] if (directory / "metadata.json").exists() else sorted(directory.glob("worker*/episode*"))
    if not episodes:
        result["missing"].append("no actual episode directories")
    for episode in episodes:
        try:
            result["episodes"].append(audit_episode(episode, freeze, inputs))
        except FileNotFoundError as error:
            result["missing"].append({"episode": str(episode), "path": error.filename})
        except (OSError, ValueError, TypeError, KeyError, IndexError, StopIteration, ArithmeticError) as error:
            result["errors"].append({"episode": str(episode), "error": repr(error)})
    result["status"] = "FAIL" if result["errors"] else "INCOMPLETE" if result["missing"] else "PASS"
    try:
        inputs.verify_unchanged()
    except (OSError, ValueError) as error:
        result["errors"].append({"error": str(error)})
        result["status"] = "FAIL"
    result["passed"] = result["status"] == "PASS"
    result["inputs"] = inputs.bindings
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; preserve the original result")
    result = audit(args.directory, args.freeze)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": result["passed"], "status": result["status"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
