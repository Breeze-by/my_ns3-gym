#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path
import os
import signal
import tempfile
import time
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_prefix, get_package_share_directory

from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    RegisterEventHandler,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
    SetEnvironmentVariable,
    TimerAction,
)
from launch.conditions import IfCondition
from launch.event_handlers import OnProcessExit, OnProcessStart, OnShutdown
from launch.events import Shutdown, matches_action
from launch.events.process import SignalProcess
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from launch_ros.actions import Node
from nav2_common.launch import RewrittenYaml


# Candidate helpers to insert in the existing launch file. No standalone node.
PHYSICS_DIAGNOSTIC_ENV = "MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE"


def diagnostic_read(path):
    path = Path(path)
    with path.open("rb") as stream:
        before = os.fstat(stream.fileno())
        raw = stream.read()
        after = os.fstat(stream.fileno())
    linked = path.stat()

    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns)
    if identity(before) != identity(after) or identity(after) != identity(linked):
        raise ValueError("diagnostic input changed while read")
    return raw, hashlib.sha256(raw).hexdigest()


def diagnostic_json(raw):
    def unique(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate diagnostic JSON key")
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError("nonfinite diagnostic JSON")))


def prepare_physics_diagnostic(config_path, *, adapter_mode, stepped_mode,
                               robot_count, epoch, audit_path, world, seed,
                               package_prefix):
    if not config_path:
        return None
    if not (adapter_mode and stepped_mode and robot_count == 3 and epoch and audit_path):
        raise ValueError("physics diagnostic requires stepped three-robot adapter epoch/audit")
    config_file = Path(config_path)
    audit = Path(audit_path)
    if not config_file.is_absolute() or not audit.is_absolute():
        raise ValueError("physics diagnostic requires absolute config/audit paths")
    episode = audit.parent.resolve(strict=True)
    raw, input_sha = diagnostic_read(config_file)
    config = diagnostic_json(raw)
    observer_only = (type(config) is dict and
                     config.get("schema") == "mr3-physics-diagnostic-config-v2" and
                     config.get("mode") == "observer_only")
    expected = {"schema", "run_directory", "episode_relative_directory", "scene", "seed",
                "mode", "capture_start_ns", "capture_end_ns", "observer_library"}
    if not observer_only:
        expected.add("profile_library")
    if (type(config) is not dict or set(config) not in (expected, expected | {"ray_provenance"}) or
            (not observer_only and config["schema"] != "mr3-physics-diagnostic-config-v1")):
        raise ValueError("unknown physics diagnostic config schema/fields")
    if not observer_only and config["mode"] not in ("baseline", "iters150"):
        raise ValueError("unknown physics diagnostic mode")
    if type(config["seed"]) is not int or config["seed"] < 0 or str(config["seed"]) != str(seed):
        raise ValueError("physics diagnostic seed mismatch")
    if (type(config["scene"]) is not str or config["scene"] not in ("open", "rooms", "corridors")
            or Path(world).name != f"p1c_{config['scene']}.world"):
        raise ValueError("physics diagnostic scene mismatch")
    for key in ("capture_start_ns", "capture_end_ns"):
        if type(config[key]) is not int or not 0 <= config[key] <= 9223372036854775807:
            raise ValueError("physics diagnostic window must use finite nonnegative int64 ns")
    if config["capture_end_ns"] <= config["capture_start_ns"]:
        raise ValueError("physics diagnostic capture window must increase")
    if (type(config["run_directory"]) is not str or
            type(config["episode_relative_directory"]) is not str):
        raise ValueError("physics diagnostic run/episode path must be strings")
    run = Path(config["run_directory"])
    relative = Path(config["episode_relative_directory"])
    required_relative = Path("worker0") / f"episode001_{config['scene']}_{config['seed']}"
    if (not run.is_absolute() or relative != required_relative or
            str(run.resolve(strict=True)) != str(run) or
            (run / relative).resolve(strict=True) != episode):
        raise ValueError("physics diagnostic exact run/first-episode mismatch")

    libraries = {}
    for key, filename in (("observer_library", "libmr3_stop_response_observer.so"),
                          ("profile_library", "libmr3_physics_diagnostic_profile.so")):
        if observer_only and key == "profile_library":
            continue
        spec = config[key]
        if type(spec) is not dict or set(spec) != {"path", "sha256", "source_sha256"}:
            raise ValueError("physics diagnostic library fields mismatch")
        selected = Path(package_prefix) / "lib" / filename
        if type(spec["path"]) is not str or spec["path"] != str(selected):
            raise ValueError("physics diagnostic library must use reviewed canonical target")
        for field in ("sha256", "source_sha256"):
            digest = spec[field]
            if (type(digest) is not str or len(digest) != 64 or
                    any(ch not in "0123456789abcdef" for ch in digest)):
                raise ValueError("physics diagnostic digest must be lowercase SHA256")
        resolved = selected.resolve(strict=True)
        _, digest = diagnostic_read(resolved)
        if digest != spec["sha256"]:
            raise ValueError("physics diagnostic library SHA mismatch")
        libraries[key] = {**spec, "resolved_path": str(resolved)}

    ray = None
    if "ray_provenance" in config:
        spec = config["ray_provenance"]
        required = {"enabled", "library", "library_sha256", "source_sha256",
                    "start_ns", "end_ns", "sensor_link", "sensor_name"}
        if (type(spec) is not dict or set(spec) != required or
                spec["enabled"] is not True or spec["sensor_link"] != "base_scan" or
                spec["sensor_name"] != "hls_lfcd_lds"):
            raise ValueError("ray provenance fields/sensor/enabled mismatch")
        if (type(spec["start_ns"]) is not int or spec["start_ns"] != 0 or
                type(spec["end_ns"]) is not int or spec["end_ns"] != 300000000000):
            raise ValueError("ray provenance requires fixed diagnostic window")
        selected = Path(package_prefix) / "lib" / "libmr3_ray_provenance_observer.so"
        if type(spec["library"]) is not str or spec["library"] != str(selected):
            raise ValueError("ray provenance requires fixed canonical library")
        for field in ("library_sha256", "source_sha256"):
            digest = spec[field]
            if (type(digest) is not str or len(digest) != 64 or
                    any(ch not in "0123456789abcdef" for ch in digest)):
                raise ValueError("ray provenance digest must be lowercase SHA256")
        resolved = selected.resolve(strict=True)
        _, digest = diagnostic_read(resolved)
        if digest != spec["library_sha256"]:
            raise ValueError("ray provenance library SHA mismatch")
        ray = {**spec, "resolved_path": str(resolved),
               "outputs": {name: str(episode / f"ray_{name}.jsonl")
                           for name in ("tb1", "tb2", "tb3")}}

    world_path = Path(world).resolve(strict=True)
    _, world_sha = diagnostic_read(world_path)
    binding = {
        "schema": ("mr3-physics-diagnostic-binding-v2" if observer_only else
                   "mr3-physics-diagnostic-binding-v1"), "epoch": epoch,
        "episode_directory": str(episode), "config_source": str(config_file.resolve(strict=True)),
        "config_sha256": input_sha, "mode": config["mode"],
        "world_name": f"p1c_{config['scene']}", "world_path": str(world_path),
        "world_sha256": world_sha, "seed": config["seed"],
        "capture_start_ns": config["capture_start_ns"],
        "capture_end_ns": config["capture_end_ns"], **libraries,
        "observer_outputs": {name: str(episode / f"physics_{name}.jsonl")
                             for name in ("tb1", "tb2", "tb3")}}
    if observer_only:
        binding["physics_intervention"] = "none_observer_only"
        binding["observer_paused_only"] = True
    else:
        binding["profile_output_path"] = str(episode / "physics_profile.jsonl")
    if ray is not None:
        binding["ray_provenance"] = ray
    binding_path = episode / "physics_diagnostic_binding.json"
    binding_raw = (json.dumps(binding, sort_keys=True, allow_nan=False) + "\n").encode()
    with binding_path.open("xb") as stream:
        stream.write(binding_raw)
    return {"binding": binding, "binding_path": str(binding_path),
            "binding_sha256": hashlib.sha256(binding_raw).hexdigest()}


def append_physics_observer(model, robot_name, diagnostic):
    binding = diagnostic["binding"]
    if robot_name not in ("tb1", "tb2", "tb3") or model.count("</model>") != 1:
        raise ValueError("diagnostic requires one model and an active canonical robot")
    name = f"mr3_stop_response_observer_{robot_name}"
    if name in model:
        raise ValueError("diagnostic observer already present")
    fields = {
        "epoch": binding["epoch"], "robot": robot_name,
        "output_path": binding["observer_outputs"][robot_name], "base_link": "base_link",
        "right_joint": "wheel_right_joint", "left_joint": "wheel_left_joint",
        "start_ns": str(binding["capture_start_ns"]), "end_ns": str(binding["capture_end_ns"])}
    if binding.get("observer_paused_only") is True:
        fields["paused_only"] = "true"
    filename = escape(binding["observer_library"]["path"], {'"': "&quot;"})
    block = (f'  <plugin name="{name}" filename="{filename}">\n' +
             "".join(f"    <{key}>{escape(value)}</{key}>\n" for key, value in fields.items()) +
             "  </plugin>\n")
    rendered = model.replace("</model>", block + "</model>", 1)
    if rendered.replace(block, "", 1) != model:
        raise ValueError("diagnostic changed original model bytes")
    return rendered


def append_ray_provenance(model, robot_name, diagnostic):
    binding = diagnostic["binding"]
    if "ray_provenance" not in binding:
        return model
    if robot_name not in ("tb1", "tb2", "tb3") or model.count("</model>") != 1:
        raise ValueError("ray provenance requires one model and active robot")
    ray = binding["ray_provenance"]
    name = f"mr3_ray_provenance_observer_{robot_name}"
    if name in model:
        raise ValueError("ray provenance observer already present")
    fields = {"output_path": ray["outputs"][robot_name], "epoch": binding["epoch"],
              "robot": robot_name, "sensor_link": ray["sensor_link"],
              "sensor_name": ray["sensor_name"], "start_ns": str(ray["start_ns"]),
              "end_ns": str(ray["end_ns"])}
    filename = escape(ray["library"], {"\"": "&quot;"})
    tree = ET.fromstring(model).find("model")
    links = tree.findall("link[@name='base_scan']")
    sensors = links[0].findall("sensor[@name='hls_lfcd_lds']") if len(links) == 1 else []
    if len(sensors) != 1 or sensors[0].attrib != {"name": "hls_lfcd_lds", "type": "ray"}:
        raise ValueError("ray provenance requires unique canonical ray sensor")
    block = (f'        <plugin name="{name}" filename="{filename}">\n' +
             "".join(f"          <{key}>{escape(value)}</{key}>\n" for key, value in fields.items()) +
             "        </plugin>\n")
    link_start = model.index('<link name="base_scan">')
    link_end = model.index("</link>", link_start)
    sensor_start = model.index('<sensor name="hls_lfcd_lds" type="ray">', link_start, link_end)
    sensor_end = model.index("      </sensor>", sensor_start, link_end)
    rendered = model[:sensor_end] + block + model[sensor_end:]
    if rendered.replace(block, "", 1) != model:
        raise ValueError("ray provenance changed original model bytes")
    return rendered


def drive_spawn_model(model_path, robot_name, audit_path, epoch, tagged_commands=False,
                      *, physics_diagnostic=None):
    """Select target protocol/audit tags without changing physical model bytes."""
    if type(tagged_commands) is not bool or (tagged_commands and not epoch):
        raise ValueError("tagged drive requires an explicit adapter epoch")
    with open(model_path, encoding="utf-8") as stream:
        model = stream.read()
    tags = {
        "mr3_audit_path": (os.path.join(os.path.dirname(audit_path), f"drive_{robot_name}.jsonl")
                           if audit_path else ""),
        "mr3_epoch": epoch,
        "mr3_tagged_commands": "true" if tagged_commands else "false",
    }
    for tag, value in tags.items():
        placeholder = f"<{tag}/>"
        if model.count(placeholder) != 1:
            raise ValueError(f"drive model requires exactly one {tag} placeholder")
        model = model.replace(placeholder, f"<{tag}>{escape(value)}</{tag}>")
    if physics_diagnostic is not None:
        model = append_physics_observer(model, robot_name, physics_diagnostic)
        model = append_ray_provenance(model, robot_name, physics_diagnostic)
    if audit_path:
        destination = os.path.join(os.path.dirname(audit_path), f"drive_model_{robot_name}.sdf")
        with open(destination, "x", encoding="utf-8") as stream:
            stream.write(model)
        return destination
    with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=f"_{robot_name}.sdf", delete=False) as stream:
        stream.write(model)
        return stream.name


def remove_drive_spawn_model(event, context, *, path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    return []


class OrderedRosShutdown:
    """Close actual launch processes serially while Gazebo's ROS clock stays alive."""

    protocol = "nav2-finalized_then_serial-ros_then_gazebo-v1"

    def __init__(self, epoch, is_server, stop_native):
        self.epoch = epoch
        self.is_server = is_server
        self.stop_native = stop_native
        self.processes = []
        self.phase = "running"
        self.pending = None
        self.timer = None
        self.queue = []
        self.stop_action = None
        self.receipt_index = 0
        self.signal_sequence = 0

    def receipt(self, event, **payload):
        self.receipt_index += 1
        return LogInfo(msg="MR3_ORDERED_SHUTDOWN " + json.dumps({
            "schema": "mr3-ordered-ros-shutdown-v1", "protocol": self.protocol,
            "epoch": self.epoch, "receipt_index": self.receipt_index,
            "wall_monotonic_ns": time.monotonic_ns(), "event": event, **payload,
        }, sort_keys=True))

    @staticmethod
    def identity(record):
        started = record["started"]
        return {
            "process_start_index": record["index"], "action_id": id(started.action),
            "process_name": started.process_name, "pid": started.pid,
            "role": record["role"],
        }

    def fail(self, reason, **payload):
        if self.phase == "failed":
            return []
        self.phase = "failed"
        if self.timer is not None:
            self.timer.cancel()
        return [
            self.receipt("error", reason=reason, **payload),
            LogInfo(msg="ERROR: MR3_ROS_SHUTDOWN_ERROR " + json.dumps({
                "reason": reason, "epoch": self.epoch, **payload,
            }, sort_keys=True)),
            EmitEvent(event=Shutdown(reason="Ordered ROS shutdown failed: " + reason)),
        ]

    def started(self, event, context):
        if any(record["started"].action is event.action or record["started"].pid == event.pid
               for record in self.processes):
            return self.fail("duplicate_process_identity", pid=event.pid,
                             process_name=event.process_name)
        role = ("gazebo_server" if self.is_server(event) else
                "native_stop_cli" if event.action is self.stop_action else "owned_ros")
        record = {"started": event, "index": len(self.processes) + 1,
                  "role": role, "returncode": None}
        self.processes.append(record)
        result = [self.receipt("process_started", **self.identity(record), argv=list(event.cmd))]
        if self.phase != "running" and role == "owned_ros" and not context.is_shutdown:
            result.extend(self.fail("process_started_during_shutdown", **self.identity(record)))
        return result

    def exited(self, event, context):
        record = next((item for item in self.processes
                       if item["started"].action is event.action), None)
        if record is None:
            return self.fail("exit_without_start", pid=event.pid, process_name=event.process_name)
        # Humble prepends newly registered handlers. A specific evaluator/native
        # handler may observe this same SDK event before the global tracker.
        if record.get("exit_event") is event:
            return []
        if (record["started"].pid != event.pid
                or record["started"].process_name != event.process_name
                or record["returncode"] is not None):
            return self.fail("exit_identity_mismatch", **self.identity(record))
        record["returncode"] = event.returncode
        record["exit_event"] = event
        controlled = record is self.pending
        result = [self.receipt(
            "process_exited", **self.identity(record), returncode=event.returncode,
            controlled=controlled, signal_sequence=self.signal_sequence if controlled else None,
        )]
        if record["role"] == "owned_ros" and event.returncode != 0:
            result.extend(self.fail("nonzero_process_exit", **self.identity(record),
                                    returncode=event.returncode))
        elif controlled and self.phase == "draining" and not context.is_shutdown:
            self.timer.cancel()
            self.pending = None
            result.extend(self.next_process(context))
        return result

    def begin(self, event, context):
        if self.phase != "running":
            return []
        result = self.exited(event, context)
        if self.phase != "running":
            return result
        evaluator = next((record for record in self.processes
                          if record["started"].action is event.action
                          and record["started"].pid == event.pid
                          and record["started"].process_name == event.process_name), None)
        if evaluator is None or evaluator["returncode"] != 0 or event.returncode != 0:
            return result + self.fail("evaluator_exit_not_verified", pid=event.pid,
                                      returncode=event.returncode)
        self.phase = "draining"
        self.queue = [record for record in reversed(self.processes)
                      if record["role"] == "owned_ros" and record["returncode"] is None]
        return result + [self.receipt(
            "begin", evaluator_pid=event.pid, evaluator_returncode=event.returncode,
            remaining=[self.identity(record) for record in self.queue],
        ), *self.next_process(context)]

    def next_process(self, context):
        while self.queue and self.queue[0]["returncode"] is not None:
            self.queue.pop(0)
        if not self.queue:
            self.phase = "native"
            return [self.receipt("ros_complete", signaled_count=self.signal_sequence),
                    *self.stop_native(context)]
        self.pending = self.queue.pop(0)
        self.signal_sequence += 1
        record = self.pending

        def timed_out(timer_context):
            if self.phase != "draining" or self.pending is not record or timer_context.is_shutdown:
                return []
            return self.fail("process_exit_timeout_10_wall_sec", **self.identity(record))

        self.timer = TimerAction(period=10.0, actions=[OpaqueFunction(function=timed_out)])
        return [
            self.receipt("signal", **self.identity(record), signal="SIGINT",
                         signal_sequence=self.signal_sequence),
            EmitEvent(event=SignalProcess(
                signal_number=signal.SIGINT,
                process_matcher=matches_action(record["started"].action),
            )),
            self.timer,
        ]

    def completed(self):
        server = next((record for record in self.processes
                       if record["role"] == "gazebo_server"), None)
        cli = next((record for record in self.processes
                    if record["role"] == "native_stop_cli"), None)
        if self.phase != "native" or server is None or cli is None or any(
                record["returncode"] != 0 for record in self.processes):
            return self.fail("native_completion_not_verified")
        self.phase = "done"
        return [self.receipt("complete", server_pid=server["started"].pid,
                             stop_cli_pid=cli["started"].pid,
                             server_returncode=0, stop_cli_returncode=0)]


def launch_setup(context, *args, **kwargs):
    actions = []
    shutdown_order = None

    # ========= Runtime launch arguments =========
    robot_count_cfg = LaunchConfiguration("robot_count")
    use_sim_time = LaunchConfiguration("use_sim_time")
    enable_drive = LaunchConfiguration("enable_drive")
    enable_rviz = LaunchConfiguration("enable_rviz")
    enable_merge_rviz = LaunchConfiguration("enable_merge_rviz")
    enable_gzclient = LaunchConfiguration("enable_gzclient")
    gazebo_seed = LaunchConfiguration("gazebo_seed")
    world_name = LaunchConfiguration("world")
    spawn_timeout = LaunchConfiguration("spawn_timeout")
    auto_save_map = LaunchConfiguration("auto_save_map")
    goal_timeout = LaunchConfiguration("exploration_goal_timeout_sec")
    response_timeout = LaunchConfiguration("navigation_response_timeout_sec")
    cancel_timeout = LaunchConfiguration("navigation_cancel_timeout_sec")
    nav2_ready_timeout = LaunchConfiguration("nav2_ready_timeout_sec")
    enable_task_evaluator = LaunchConfiguration("enable_task_evaluator")
    evaluation_episode_id = LaunchConfiguration("evaluation_episode_id")
    evaluation_output_dir = LaunchConfiguration("evaluation_output_dir")
    evaluation_duration = LaunchConfiguration("evaluation_duration_sec")
    evaluation_coverage = LaunchConfiguration("evaluation_coverage_threshold")
    evaluation_contract = LaunchConfiguration("evaluation_contract_path")
    stop_on_evaluation = LaunchConfiguration("stop_on_evaluation_complete")

    try:
        robot_count = int(robot_count_cfg.perform(context))
    except ValueError:
        raise ValueError("robot_count must be an integer between 1 and 4") from None

    # ========= Available robots =========
    # Add more robots here if needed. robot_count will select the first N robots.
    all_robots = [
        {
            "name": "tb1",
            "x_pose": "0.0",
            "y_pose": "-0.45",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
        {
            "name": "tb2",
            "x_pose": "0.0",
            "y_pose": "0.45",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
        {
            "name": "tb3",
            "x_pose": "0.45",
            "y_pose": "0.0",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
        {
            "name": "tb4",
            "x_pose": "-0.45",
            "y_pose": "0.0",
            "z_pose": "0.01",
            "roll": "0.00",
            "pitch": "0.00",
            "yaw": "0.00",
        },
    ]

    if not 1 <= robot_count <= len(all_robots):
        raise ValueError("robot_count must be an integer between 1 and 4")
    robots = all_robots[:robot_count]
    execution_mode = LaunchConfiguration("execution_mode").perform(context)
    if execution_mode not in ("baseline", "adapter"):
        raise ValueError("execution_mode must be baseline or adapter")
    adapter_mode = execution_mode == "adapter"
    probe_mode = IfCondition(LaunchConfiguration("adapter_probe")).evaluate(context)
    stepped_mode = IfCondition(LaunchConfiguration("mr3_stepped")).evaluate(context)
    training_reward = IfCondition(LaunchConfiguration("training_reward_enabled")).evaluate(context)
    terminal_probe = IfCondition(LaunchConfiguration("training_terminal_probe")).evaluate(context)
    plant_stimulus_arm = LaunchConfiguration("mr3_plant_stimulus_arm").perform(context)
    if plant_stimulus_arm not in ("", "continuous", "pulse"):
        raise ValueError("unknown mr3_plant_stimulus_arm")
    if plant_stimulus_arm and not (adapter_mode and stepped_mode and training_reward
                                  and robot_count == 3):
        raise ValueError("plant stimulus requires stepped three-robot training adapter")
    if plant_stimulus_arm:
        if world_name.perform(context) != "p1c_open.world":
            raise ValueError("plant stimulus requires the fixed open diagnostic world")
        # Explicit engineering fixture, identical in both arms. Keep the normal
        # research spawn untouched and retain the original peer safety bounds.
        for robot, x in zip(robots, ("-1.6", "0.0", "1.6")):
            robot.update(x_pose=x, y_pose="0.0")
    if stepped_mode and not adapter_mode:
        raise ValueError("mr3_stepped requires adapter mode")
    if training_reward and (not adapter_mode or not evaluation_contract.perform(context)
                            or not IfCondition(enable_task_evaluator).evaluate(context)):
        raise ValueError(
            "training_reward_enabled requires adapter mode and MR3 contract evaluator")
    if terminal_probe and (not training_reward or not stepped_mode):
        raise ValueError("training_terminal_probe requires isolated rewards and stepped mode")
    if adapter_mode and robot_count != 3:
        raise ValueError("MR3 adapter requires robot_count=3")
    if adapter_mode and IfCondition(enable_drive).evaluate(context):
        raise ValueError("MR3 adapter requires enable_drive=false")
    if probe_mode and (not adapter_mode or not evaluation_contract.perform(context)
                       or not IfCondition(enable_task_evaluator).evaluate(context)):
        raise ValueError("adapter_probe requires adapter mode and enabled MR3 contract evaluator")
    episode_epoch = LaunchConfiguration("mr3_episode_epoch")

    print(f"\n[INFO] Requested robot_count = {robot_count}")
    print(f"[INFO] Active robots = {[robot['name'] for robot in robots]}\n")

    # ========= Package paths =========
    multi_robot_share = get_package_share_directory("multi_robot")
    model_path = os.path.join(multi_robot_share, "models")
    existing_model_path = os.environ.get("GAZEBO_MODEL_PATH", "")
    actions.append(SetEnvironmentVariable(
        "GAZEBO_MODEL_PATH",
        os.pathsep.join(path for path in (model_path, existing_model_path) if path),
    ))
    merge_map_share = get_package_share_directory("merge_map")
    nav_launch_dir = os.path.join(multi_robot_share, "launch", "nav2_bringup")

    my_robot = "turtlebot3_waffle"

    urdf = os.path.join(multi_robot_share, "urdf", my_robot + ".urdf")
    model = os.path.join(multi_robot_share, "models", my_robot, "model.sdf")
    world_filename = world_name.perform(context)
    if os.path.basename(world_filename) != world_filename:
        raise ValueError("world must be a filename from multi_robot/worlds")
    world = os.path.join(multi_robot_share, "worlds", world_filename)
    if not os.path.isfile(world):
        raise ValueError(f"world does not exist: {world_filename}")

    map_file_path = os.path.join(multi_robot_share, "maps", "turtlebot3_world.yaml")

    remappings = [("/tf", "tf"), ("/tf_static", "tf_static")]

    # ========= Start merge_map and headquarters control =========
    merge_map_node = Node(
        package="merge_map",
        executable="merge_map",
        name="merge_map",
        parameters=[
            {
                "frame_id": "map",
                "output_topic": "/merge_map",
                "robot_count": robot_count,
                "use_sim_time": use_sim_time,
            }
        ],
        output="screen",
    )
    adapter_audit_path = LaunchConfiguration("mr3_audit_path").perform(context)
    if plant_stimulus_arm and not (adapter_audit_path and episode_epoch.perform(context)):
        raise ValueError("plant stimulus requires explicit audit path and episode epoch")
    physics_diagnostic = prepare_physics_diagnostic(
        context.environment.get(PHYSICS_DIAGNOSTIC_ENV, ""),
        adapter_mode=adapter_mode, stepped_mode=stepped_mode, robot_count=robot_count,
        epoch=episode_epoch.perform(context), audit_path=adapter_audit_path, world=world,
        seed=gazebo_seed.perform(context), package_prefix=get_package_prefix("multi_robot"))
    if physics_diagnostic is not None:
        actions.append(LogInfo(msg="MR3_PHYSICS_DIAGNOSTIC_SELECTED " +
                               json.dumps(physics_diagnostic, sort_keys=True)))
    if adapter_mode:
        if adapter_audit_path:
            actions.append(Node(
                package="multi_robot", executable="mr3_odometry_recorder",
                name="mr3_odometry_recorder", output="screen",
                parameters=[{"use_sim_time": use_sim_time,
                             "episode_epoch": episode_epoch,
                             "output_path": os.path.join(os.path.dirname(adapter_audit_path),
                                                         "driver_odometry_receipts.jsonl")}],
            ))
        actions.append(Node(
            package="multi_robot_exploration", executable="mr3_information",
            name="mr3_information", output="screen",
            parameters=[{"use_sim_time": use_sim_time, "robot_count": 3,
                         "episode_epoch": episode_epoch, "tf_validity_lead_sec": .2,
                         "stepped_mode": stepped_mode,
                         "state_audit_path": (
                             os.path.join(os.path.dirname(adapter_audit_path),
                                          "information_states.jsonl")
                             if adapter_audit_path else "")}],
        ))
    else:
        actions.append(merge_map_node)
    if evaluation_contract.perform(context):
        contact_reducer = Node(
            package="multi_robot", executable="mr3_contact_reducer",
            name="mr3_contact_reducer", output="screen",
            parameters=[{"use_sim_time": use_sim_time}],
        )
        actions.append(contact_reducer)
        actions.append(RegisterEventHandler(OnProcessExit(
            target_action=contact_reducer,
            on_exit=lambda event, event_context: (
                [EmitEvent(event=Shutdown(reason="Contact reducer exited"))]
                if not event_context.is_shutdown and not (
                    shutdown_order is not None and shutdown_order.phase != "running"
                ) else []
            ),
        )))
    actions.append(Node(
        package="multi_robot_exploration", executable="peer_obstacles",
        name="peer_obstacles", output="screen",
        parameters=[{"robot_count": robot_count, "use_sim_time": use_sim_time,
                     "task_release_start": adapter_mode,
                     "episode_epoch": episode_epoch,
                     "stepped_mode": stepped_mode,
                     "phase_audit_path": (
                         os.path.join(os.path.dirname(adapter_audit_path), "peer_phase.jsonl")
                         if adapter_audit_path and stepped_mode else ""),
                     "tf_source_lead_sec": .2 if adapter_mode else 0.}],
        remappings=([
            (f"/{robot['name']}/{topic}", f"/mr3/received/{robot['name']}/{topic}")
            for robot in robots for topic in ("odom", "tf")
        ] if adapter_mode else []),
    ))
    if adapter_mode:
        actions.append(Node(
            package="multi_robot_exploration", executable="motion_safety",
            name="motion_safety", output="screen",
            parameters=[{"use_sim_time": use_sim_time, "episode_epoch": episode_epoch,
                         "stepped_mode": stepped_mode,
                         "mr3_diagnostic_enabled": bool(plant_stimulus_arm),
                         "audit_path": (os.path.join(os.path.dirname(adapter_audit_path),
                                                     "motion_safety.jsonl")
                                        if adapter_audit_path else "")}],
        ))

    merge_rviz = Node(
        package="rviz2",
        executable="rviz2",
        name="merge_map_rviz",
        output="screen",
        arguments=[
            "-d",
            os.path.join(merge_map_share, "config", "map_merge_tb1_tb2.rviz"),
        ],
        parameters=[{"use_sim_time": use_sim_time}],
        condition=IfCondition(enable_merge_rviz),
        remappings=([("/merge_map", "/mr3/received/map")] if adapter_mode else []),
    )
    actions.append(merge_rviz)

    control_node = Node(
        package="multi_robot_exploration",
        executable="mr3_adapter" if adapter_mode else "control",
        name="mr3_adapter" if adapter_mode else "headquarters_control",
        parameters=[
            {
                "robot_count": robot_count,
                "auto_save_map": auto_save_map,
                "use_sim_time": use_sim_time,
                "goal_timeout_sec": goal_timeout,
                "navigation_response_timeout_sec": response_timeout,
                "navigation_cancel_timeout_sec": cancel_timeout,
                "require_task_monitor_ready": bool(evaluation_contract.perform(context)),
                **({"episode_epoch": episode_epoch, "stepped_mode": stepped_mode,
                    "audit_path": LaunchConfiguration("mr3_audit_path")} if adapter_mode else {}),
            }
        ],
        output="screen",
    )

    nav2_ready_gate = Node(
        package="multi_robot_exploration",
        executable="nav2_ready_gate",
        name="nav2_ready_gate",
        parameters=[
            {
                "robot_count": robot_count,
                "timeout_sec": nav2_ready_timeout,
            }
        ],
        output="screen",
    )

    task_evaluator = Node(
        package="multi_robot_exploration",
        executable="task_evaluator",
        name="task_evaluator",
        parameters=[
            {
                "use_sim_time": use_sim_time,
                "robot_count": robot_count,
                "episode_id": evaluation_episode_id,
                "world_file": world,
                "gazebo_seed": gazebo_seed,
                "output_dir": evaluation_output_dir,
                "max_duration_sec": evaluation_duration,
                "coverage_threshold": evaluation_coverage,
                "task_contract_path": evaluation_contract,
                "allow_probe_finalize": probe_mode,
                "training_reward_enabled": training_reward,
                "training_terminal_probe": terminal_probe,
            }
        ],
        output="screen",
        condition=IfCondition(enable_task_evaluator),
        remappings=([("/merge_map", "/mr3/received/map")] if adapter_mode else []),
    )
    # ========= Gazebo =========
    step_plugin = (os.path.join(get_package_prefix("multi_robot"), "lib", "libmr3_gazebo_step.so")
                   if stepped_mode else None)
    clock_parameters = (os.path.join(multi_robot_share, "config", "mr3_step_clock.yaml")
                        if stepped_mode else None)
    if stepped_mode and not os.path.isfile(step_plugin):
        raise ValueError(f"installed MR3 stepping plugin does not exist: {step_plugin}")
    ray_box_plugin = None
    ray_box_audit_path = None
    if stepped_mode:
        ray_box_plugin = os.path.join(get_package_prefix("multi_robot"),
                                     "lib", "libmr3_ray_box_corrector.so")
        if not os.path.isfile(ray_box_plugin):
            raise ValueError(f"installed MR3 ray-box corrector does not exist: {ray_box_plugin}")
        ray_box_directory = (Path(adapter_audit_path).parent.resolve(strict=True)
                             if adapter_audit_path else
                             Path(tempfile.mkdtemp(prefix="mr3_ray_box_corrector_")))
        ray_box_audit_path = str(ray_box_directory / "ray_box_corrector.jsonl")
    server_state = {
        "started": None, "environment": None, "exited": False, "stopping": False,
        "server_returncode": None, "stop_cli_returncode": None,
    }

    def remember_gzserver(event, event_context):
        if not event.cmd or os.path.basename(event.cmd[0]) != "gzserver" or world not in event.cmd:
            return []
        if server_state["started"] is not None:
            return [
                LogInfo(msg="ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR ambiguous_owned_server"),
                EmitEvent(event=Shutdown(reason="Ambiguous owned Gazebo server")),
            ]
        server_state["started"] = event
        server_state["environment"] = dict(
            event_context.environment if event.env is None else event.env
        )
        return [
            LogInfo(msg=f"Owned Gazebo server {event.process_name} started with pid={event.pid}"),
            LogInfo(msg="MR3_GAZEBO_SERVER_START " + json.dumps({
                "pid": event.pid, "process_name": event.process_name, "argv": list(event.cmd),
                "stepped_mode": stepped_mode, "selected_step_plugin": step_plugin,
                "selected_ray_box_plugin": ray_box_plugin,
                "ray_box_audit_path": ray_box_audit_path,
                "selected_clock_parameters": clock_parameters,
                "gazebo_plugin_path": server_state["environment"].get("GAZEBO_PLUGIN_PATH"),
            }, sort_keys=True)),
        ]

    def owned_gzserver_exited(event, event_context):
        started = server_state["started"]
        if started is None or not (
            event.action is started.action and event.pid == started.pid
            and event.process_name == started.process_name
        ):
            return []
        server_state["exited"] = True
        server_state["server_returncode"] = event.returncode
        if not server_state["stopping"] and not event_context.is_shutdown:
            return [
                LogInfo(msg=(
                    "ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR "
                    f"server_exited_before_evaluation exit_code={event.returncode}"
                )),
                EmitEvent(event=Shutdown(reason="Gazebo exited before evaluation completion")),
            ]
        result = []
        if event.returncode != 0:
            result.append(LogInfo(msg=(
                f"ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR server_exit_code={event.returncode}"
            )))
        if not event_context.is_shutdown and (
            event.returncode != 0
            or (server_state["stopping"] and server_state["stop_cli_returncode"] == 0)
        ):
            if shutdown_order is not None and event.returncode == 0:
                result.extend(shutdown_order.exited(event, event_context))
                result.extend(shutdown_order.completed())
            result.append(EmitEvent(event=Shutdown(
                reason="Owned Gazebo server exited after evaluation"
            )))
        return result

    def native_stop_timeout(event_context):
        if event_context.is_shutdown or (
            server_state["server_returncode"] == 0 and server_state["stop_cli_returncode"] == 0
        ):
            return []
        reason = "stop_cli_exit" if server_state["exited"] else "server_exit"
        return [
            LogInfo(msg=f"ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR {reason}_timeout_10_wall_sec"),
            EmitEvent(event=Shutdown(reason="Gazebo native stop timed out")),
        ]

    def native_stop_cli_exited(event, event_context):
        server_state["stop_cli_returncode"] = event.returncode
        result = []
        if event.returncode != 0:
            result.append(LogInfo(msg=(
                f"ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR stop_cli_exit_code={event.returncode}"
            )))
        if not event_context.is_shutdown and (
            event.returncode != 0 or server_state["server_returncode"] == 0
        ):
            if shutdown_order is not None and event.returncode == 0:
                result.extend(shutdown_order.exited(event, event_context))
                result.extend(shutdown_order.completed())
            result.append(EmitEvent(event=Shutdown(reason="Gazebo native stop completed")))
        return result

    def evaluation_finished(event, event_context):
        if (
            not IfCondition(stop_on_evaluation).evaluate(event_context)
            or event_context.is_shutdown or server_state["stopping"]
        ):
            return []
        if shutdown_order is not None:
            return shutdown_order.begin(event, event_context)
        return start_native_stop(event_context)

    def start_native_stop(event_context):
        server_state["stopping"] = True
        if server_state["started"] is None:
            return [
                LogInfo(msg="ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR owned_server_not_started"),
                EmitEvent(event=Shutdown(reason="Owned Gazebo server was not started")),
            ]
        if server_state["exited"]:
            return [
                LogInfo(msg="ERROR: MR3_GAZEBO_NATIVE_STOP_ERROR server_exited_before_evaluation"),
                EmitEvent(event=Shutdown(reason="Gazebo exited before evaluation completion")),
            ]
        stop_command = ExecuteProcess(
            cmd=["gz", "topic", "-p", "/gazebo/server/control", "-m", "stop: true"],
            name="mr3_gazebo_native_stop", output="screen", shell=False,
            env=server_state["environment"],
        )
        result = []
        if shutdown_order is not None:
            shutdown_order.stop_action = stop_command
            result.append(shutdown_order.receipt(
                "gz_stop", server_pid=server_state["started"].pid,
                signaled_count=shutdown_order.signal_sequence,
            ))
        return result + [
            RegisterEventHandler(OnProcessExit(
                target_action=stop_command,
                on_exit=native_stop_cli_exited,
            )),
            stop_command,
            TimerAction(period=10.0, actions=[OpaqueFunction(function=native_stop_timeout)]),
        ]

    actions.extend([
        RegisterEventHandler(OnProcessStart(on_start=remember_gzserver),
                             condition=IfCondition(
                                 "false" if stepped_mode else stop_on_evaluation)),
        RegisterEventHandler(OnProcessExit(on_exit=owned_gzserver_exited),
                             condition=IfCondition(stop_on_evaluation)),
        RegisterEventHandler(OnProcessExit(
            target_action=task_evaluator, on_exit=evaluation_finished,
        )),
    ])
    if stepped_mode:
        from scripts import GazeboRosPaths

        model_export, plugin_export, media_export = GazeboRosPaths.get_paths()
        gazebo_environment = {
            key: os.pathsep.join(value for value in (exported, context.environment.get(key, ""))
                                 if value)
            for key, exported in (("GAZEBO_MODEL_PATH", model_export),
                                  ("GAZEBO_PLUGIN_PATH", plugin_export),
                                  ("GAZEBO_RESOURCE_PATH", media_export))
        }
        gazebo_environment["MR3_RAY_BOX_CORRECTOR_AUDIT_PATH"] = ray_box_audit_path
        gazebo_environment["MR3_RAY_BOX_CORRECTOR_EPOCH"] = episode_epoch.perform(context)
        diagnostic_system_args = []
        if physics_diagnostic is not None and "profile_library" in physics_diagnostic["binding"]:
            diagnostic_system_args = [
                "-s", physics_diagnostic["binding"]["profile_library"]["path"]]
            gazebo_environment[PHYSICS_DIAGNOSTIC_ENV] = physics_diagnostic["binding_path"]
        # Humble's included gzserver launch appends extra_gazebo_args after the ROS '--'.
        # Gazebo treats that tail as positional pass-through, so load the system plugin
        # explicitly before the ROS argument section, with separate argv tokens.
        gzserver_cmd = ExecuteProcess(
            cmd=["/usr/bin/gzserver", world, ["--seed=", gazebo_seed],
                 "-s", "libgazebo_ros_init.so", "-s", "libgazebo_ros_factory.so",
                 "-s", "libgazebo_ros_force_system.so",
                 "-s", ray_box_plugin, "-s", step_plugin,
                 *diagnostic_system_args,
                 "--ros-args", "--params-file", clock_parameters, "--"],
            output="both", additional_env=gazebo_environment,
        )
    else:
        gzserver_cmd = IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(get_package_share_directory("gazebo_ros"),
                             "launch", "gzserver.launch.py")
            ),
            launch_arguments={
                "world": world, "seed": gazebo_seed, "server_required": "false",
            }.items(),
        )
    actions.append(gzserver_cmd)
    if stepped_mode:
        shutdown_order = OrderedRosShutdown(
            episode_epoch.perform(context), lambda event: event.action is gzserver_cmd,
            start_native_stop,
        )

        def ordered_process_started(event, event_context):
            return (shutdown_order.started(event, event_context)
                    + remember_gzserver(event, event_context))

        # Register before the first launch process can generate a start event.
        actions[0:0] = [
            RegisterEventHandler(OnProcessStart(on_start=ordered_process_started)),
            RegisterEventHandler(OnProcessExit(on_exit=shutdown_order.exited)),
        ]

    gzclient_cmd = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(
                get_package_share_directory("gazebo_ros"),
                "launch",
                "gzclient.launch.py",
            )
        ),
        condition=IfCondition(enable_gzclient),
    )
    actions.append(gzclient_cmd)

    # ========= Spawn robots sequentially =========
    last_spawn_action = None
    nav_bringups = []

    for robot in robots:
        robot_name = robot["name"]
        namespace = "/" + robot_name
        spawn_model = drive_spawn_model(
            model, robot_name, adapter_audit_path, episode_epoch.perform(context), adapter_mode,
            physics_diagnostic=physics_diagnostic)
        if not adapter_audit_path:
            actions.append(RegisterEventHandler(OnShutdown(
                on_shutdown=lambda event, event_context, path=spawn_model:
                remove_drive_spawn_model(event, event_context, path=path))))

        params_file = os.path.join(
            multi_robot_share,
            "params",
            f"nav2_params_{robot_name}_0.yaml",
        )
        if adapter_mode:
            # Keep local sensing and every Nav2 parameter unchanged; only the
            # two global static-map inputs use the declared robot-side copy.
            param_rewrites = {
                "global_costmap.global_costmap.ros__parameters.map_topic":
                    f"/{robot_name}/navigation_map",
                "global_costmap.global_costmap.ros__parameters.static_layer.map_topic":
                    f"/{robot_name}/navigation_map",
            }
            if plant_stimulus_arm and robot_name == "tb3":
                param_rewrites.update({
                    "velocity_smoother.ros__parameters.mr3_diagnostic_enabled": "true",
                    "velocity_smoother.ros__parameters.mr3_diagnostic_epoch":
                        episode_epoch.perform(context),
                    "velocity_smoother.ros__parameters.mr3_diagnostic_arm": plant_stimulus_arm,
                })
            params_file = RewrittenYaml(
                source_file=params_file, convert_types=True,
                param_rewrites=param_rewrites,
            )

        print(f"Namespace: {namespace}, PARAM Config: {params_file}\n")

        robot_state_publisher = Node(
            package="robot_state_publisher",
            executable="robot_state_publisher",
            namespace=namespace,
            output="screen",
            parameters=[
                {
                    "use_sim_time": use_sim_time,
                    "publish_frequency": 10.0,
                }
            ],
            remappings=remappings,
            arguments=[urdf],
        )

        spawn_robot = Node(
            package="gazebo_ros",
            executable="spawn_entity.py",
            arguments=[
                "-file",
                spawn_model,
                "-entity",
                robot_name,
                "-robot_namespace",
                namespace,
                "-timeout",
                spawn_timeout,
                "-x",
                robot["x_pose"],
                "-y",
                robot["y_pose"],
                "-z",
                robot["z_pose"],
                "-R",
                robot["roll"],
                "-P",
                robot["pitch"],
                "-Y",
                robot["yaw"],
            ],
            output="screen",
        )

        bringup_cmd = IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(nav_launch_dir, "bringup_launch.py")
            ),
            launch_arguments={
                # SLAM is started below with the project's multi-robot launch.
                # Keep this true so Nav2 does not also start AMCL and publish a
                # competing map->odom transform while the map is being built.
                "slam": "True",
                "namespace": namespace,
                "cmd_vel_output": "cmd_vel_unguarded" if adapter_mode else "cmd_vel",
                "behavior_cmd_vel": "cmd_vel_nav" if adapter_mode else "cmd_vel",
                "use_namespace": "True",
                "map": map_file_path,
                "map_server": "False",
                "params_file": params_file,
                "default_bt_xml_filename": os.path.join(
                    get_package_share_directory("nav2_bt_navigator"),
                    "behavior_trees",
                    "navigate_to_pose_w_replanning_and_recovery.xml",
                ),
                "autostart": "True",
                "use_sim_time": use_sim_time,
                "log_level": "warn",
            }.items(),
        )

        slam_toolbox_node = IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                os.path.join(
                    get_package_share_directory("slam_toolbox"),
                    "launch",
                    "online_async_multirobot_launch.py",
                )
            ),
            launch_arguments={
                "namespace": namespace,
                "use_sim_time": use_sim_time,
            }.items(),
        )

        robot_actions = [
            robot_state_publisher,
            spawn_robot,
            slam_toolbox_node,
        ]

        if last_spawn_action is None:
            for action in robot_actions:
                actions.append(action)
        else:
            spawn_robot_event = RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=last_spawn_action,
                    on_exit=robot_actions,
                )
            )
            actions.append(spawn_robot_event)

        nav_bringups.append(bringup_cmd)

        last_spawn_action = spawn_robot

    if plant_stimulus_arm:
        _, launch_sha = diagnostic_read(Path(__file__))
        _, selected_world_sha = diagnostic_read(world)
        fixture = {
            "schema": "mr3-fixed-sparse-plant-fixture-v1",
            "epoch": episode_epoch.perform(context), "arm": plant_stimulus_arm,
            "world_path": world, "world_sha256": selected_world_sha,
            "launch_source_sha256": launch_sha,
            "spawn_argument_values": {robot["name"]: {
                key: robot[key] for key in ("x_pose", "y_pose", "z_pose", "roll", "pitch", "yaw")}
                for robot in robots},
            "scope": "pre-execution spawn configuration; actual pose requires passive native observations",
        }
        target = Path(adapter_audit_path).parent / "plant_fixture_binding.json"
        with target.open("x") as stream:
            stream.write(json.dumps(fixture, sort_keys=True, allow_nan=False) + "\n")

    # ========= RViz and optional drive nodes =========
    # Start RViz only after the last robot has been spawned.
    # By default enable_rviz is false to reduce CPU/GPU load.
    if last_spawn_action is not None:
        staggered_nav = [
            TimerAction(
                period=10.0 + 45.0 * index,
                actions=[bringup],
            )
            for index, bringup in enumerate(nav_bringups)
        ]
        staggered_nav.append(nav2_ready_gate)
        actions.append(
            RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=last_spawn_action,
                    on_exit=staggered_nav,
                )
            )
        )

        def start_control_when_ready(event, context):
            if event.returncode == 0:
                return [
                    LogInfo(msg="Nav2 ready; starting cooperative exploration."),
                    control_node,
                    task_evaluator,
                ]
            return [
                LogInfo(
                    msg=(
                        "ERROR: Nav2 readiness failed; cooperative exploration "
                        "was not started."
                    )
                )
            ]

        actions.append(
            RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=nav2_ready_gate,
                    on_exit=start_control_when_ready,
                )
            )
        )

        for robot in robots:
            robot_name = robot["name"]
            namespace = "/" + robot_name

            rviz_config_file = os.path.join(
                multi_robot_share,
                "rviz",
                f"multi_robot_maping_{robot_name}.rviz",
            )

            print(f"Namespace: {namespace}, RViz Config: {rviz_config_file}\n")

            rviz_cmd = IncludeLaunchDescription(
                PythonLaunchDescriptionSource(
                    os.path.join(nav_launch_dir, "rviz_launch.py")
                ),
                launch_arguments={
                    "use_sim_time": use_sim_time,
                    "namespace": namespace,
                    "use_namespace": "True",
                    "rviz_config": rviz_config_file,
                    "log_level": "warn",
                }.items(),
                condition=IfCondition(enable_rviz),
            )

            drive_turtlebot3 = Node(
                package="turtlebot3_gazebo",
                executable="turtlebot3_drive",
                namespace=namespace,
                output="screen",
                condition=IfCondition(enable_drive),
            )

            post_spawn_event = RegisterEventHandler(
                event_handler=OnProcessExit(
                    target_action=last_spawn_action,
                    on_exit=[rviz_cmd, drive_turtlebot3],
                )
            )

            actions.append(post_spawn_event)

    return actions


def generate_launch_description():
    ld = LaunchDescription()
    ld.add_action(DeclareLaunchArgument(
        "execution_mode", default_value="baseline",
        description="baseline: handcrafted controller; "
                    "adapter: exclusive MR3 joint action endpoint.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "mr3_stepped", default_value="false",
        description="P1C paused physics stepping and explicit snapshot requests.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "training_reward_enabled", default_value="false",
        description="Enable isolated MR3 training reward with the explicit task contract.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "training_terminal_probe", default_value="false",
        description="Explicit P1C diagnostic-failure IPC probe; no task performance credit.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "mr3_plant_stimulus_arm", default_value="",
        description="Engineering-only genuine smoother stimulus: continuous or pulse; disabled by default.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "mr3_episode_epoch", default_value="mr3-p1b",
        description="Unique process-rebuilt episode identity for the ideal policy interface.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "mr3_audit_path", default_value="",
        description="Optional exclusive-create JSONL policy observation/protocol audit.",
    ))
    ld.add_action(DeclareLaunchArgument(
        "adapter_probe", default_value="false",
        description="Enable explicit incomplete-diagnostic finalization "
                    "for bounded adapter probes.",
    ))

    ld.add_action(
        DeclareLaunchArgument(
            "world",
            default_value="my_world.world",
            description="World filename installed by the multi_robot package.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "robot_count",
            default_value="3",
            description="Number of robots to spawn. MR3 uses 3; compatibility range: 1 to 4.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "use_sim_time",
            default_value="true",
            description="Use simulation time.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_drive",
            default_value="false",
            description="Enable turtlebot3_drive teleop-like drive node.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_rviz",
            default_value="false",
            description="Enable per-robot RViz windows. Default false to reduce load.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_merge_rviz",
            default_value="true",
            description="Enable the single global merged-map RViz window.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "enable_gzclient",
            default_value="true",
            description="Enable Gazebo GUI client.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "gazebo_seed",
            default_value="1",
            description="Gazebo random seed used for repeatable runs.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "spawn_timeout",
            default_value="90.0",
            description="Seconds each robot may wait for Gazebo spawn services.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "auto_save_map",
            default_value="true",
            description="Allow headquarters to save merged maps.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "exploration_goal_timeout_sec",
            default_value="60.0",
            description="Simulated seconds before canceling a stalled Nav2 goal.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "nav2_ready_timeout_sec",
            default_value="300.0",
            description="Wall seconds to wait for every Nav2 action server.",
        )
    )

    for name, description in (
        ("navigation_response_timeout_sec", "Simulated seconds to await goal acceptance."),
        ("navigation_cancel_timeout_sec",
         "Simulated seconds to await cancellation and a terminal result."),
    ):
        ld.add_action(DeclareLaunchArgument(name, default_value="10.0", description=description))
    ld.add_action(DeclareLaunchArgument(
        "stop_on_evaluation_complete", default_value="true",
        description="Stop the owned launch when the enabled evaluator exits.",
    ))

    ld.add_action(
        DeclareLaunchArgument(
            "enable_task_evaluator",
            default_value="false",
            description="Record task and ground-truth metrics.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_episode_id",
            default_value="episode",
            description="Identifier used for evaluator CSV and JSON files.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_output_dir",
            default_value="/tmp/multi_robot_evaluation",
            description="Directory for evaluator CSV and JSON files.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_duration_sec",
            default_value="0.0",
            description="Simulation seconds before a timeout result; 0 waits for shutdown.",
        )
    )

    ld.add_action(
        DeclareLaunchArgument(
            "evaluation_coverage_threshold",
            default_value="0.0",
            description="Correct-free coverage ratio that completes exploration.",
        )
    )

    ld.add_action(DeclareLaunchArgument(
        "evaluation_contract_path", default_value="",
        description="MR3 task contract JSON; empty preserves schema 3 evaluation.",
    ))

    ld.add_action(OpaqueFunction(function=launch_setup))

    return ld
