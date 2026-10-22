#!/usr/bin/env python3
"""Explicit 2D proxy worker/evaluator roles over the existing JSONL pipe.

No ROS graph, Gazebo, Nav2 or learner model is created. The evaluator role is a
different process: truth and RewardLedger never enter the actor IPC response.
"""
import argparse
from array import array
from collections import deque
import copy
import gzip
import importlib.util
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time
import traceback

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
W = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, W / "mr3_learning" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ipc = load("proxy_ipc", "ipc.py")
codec = load("proxy_codec", "proxy2d_codec.py")


def set_stamp(stamp, value):
    ns = round(value * 1e9)
    stamp.sec, stamp.nanosec = divmod(ns, 10**9)


def evaluator_environment(directory):
    environment = dict(os.environ)
    if environment.get("MR3_PROXY2D_PROFILE_OUTPUT"):
        environment["MR3_PROXY2D_PROFILE_OUTPUT"] = str(directory / "evaluator.pstats")
    return environment


class ProxyWorker:
    def __init__(self, directory, epoch, scene, seed, *, mapper="endpoint", mapper_library=None,
                 seed_rule="legacy", start_graph_rule="original-seed-cell"):
        from multi_robot_exploration.mr3_observation import SEED_RULES, validate_start_graph_rule
        if type(seed_rule) is not str or seed_rule not in SEED_RULES:
            raise ValueError("unsupported seed rule")
        validate_start_graph_rule(start_graph_rule, seed_rule=seed_rule)
        from multi_robot_exploration.mr3_proxy2d_world import ProxyWorld
        from multi_robot_exploration.mr3_proxy2d_information import ProxyInformation
        from multi_robot_exploration.mr3_proxy2d_navigation import ProxyNavigator
        from multi_robot_exploration.mr3_protocol import GoalDispatcher
        from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore
        from multi_robot_exploration.mr3_activity import ReceivedActivity
        self.directory, self.epoch = directory, epoch
        self.scene, self.seed = scene, seed
        self.world = ProxyWorld(scene, seed,mapper=mapper,mapper_library=mapper_library,epoch=epoch)
        if mapper == "karto":
            import hashlib
            loaded = {str(Path(line.split()[-1]).resolve())
                for line in Path('/proc/self/maps').read_text().splitlines()
                if 'libkartoSlamToolbox.so' in line or 'libmr3_karto_adapter.so' in line}
            self.world.metadata["loaded_native_artifacts"] = [
                {"path":p,"sha256":hashlib.sha256(Path(p).read_bytes()).hexdigest()}
                for p in sorted(loaded)]
        seed_options = {} if seed_rule == "legacy" else {"seed_rule": seed_rule}
        if start_graph_rule != "original-seed-cell":
            seed_options["start_graph_rule"] = start_graph_rule
        self.information = ProxyInformation(epoch, **seed_options)
        self.navigator = ProxyNavigator(**seed_options)
        if seed_rule != "legacy":
            self.world.metadata["seed_rule"] = seed_rule
        if start_graph_rule != "original-seed-cell":
            self.world.metadata["start_graph_rule"] = start_graph_rule
        self.events = deque()
        self.dispatcher = GoalDispatcher(epoch, self.events.append)
        self.protocol = IdealTransport(epoch)
        self.receipts = ReceivedStore(epoch)
        self.activity = ReceivedActivity(epoch)
        self.history = {name: deque(maxlen=16) for name in self.dispatcher.robots}
        self.endpoint_goals, self.nav_metadata = {}, {}
        self.goal_switches = self.rejected_actions = self.sequence = self.steps = 0
        self.state_sequence = 0
        self.last_heartbeat_ns = -1
        self.protocol_log = gzip.open(directory / "protocol.jsonl.gz", "wt", compresslevel=1)
        self.evaluator_log = (directory / "evaluator.stderr.log").open("wb")
        self.evaluator = subprocess.Popen([
            "/usr/bin/python3", "-B", str(Path(__file__).resolve()), "--role", "evaluator",
            "--directory", str(directory), "--epoch", epoch, "--scene", scene, "--seed", str(seed),
        ], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.evaluator_log,
            env=evaluator_environment(directory))
        self.eval_peer = ipc.JsonLinePeer(self.evaluator.stdout.fileno(), self.evaluator.stdin.fileno())
        stat = Path(f"/proc/{self.evaluator.pid}/stat").read_text().rsplit(")", 1)[1].split()
        (directory / "evaluator_identity.json").write_text(json.dumps({
            "pid": self.evaluator.pid, "parent": int(stat[1]), "start_ticks": int(stat[19]),
            "state": stat[0]}, indent=2) + "\n")
        self.finished = False

    @property
    def now(self):
        return self.world.time_ns / 1e9

    def evaluate(self, operation, **fields):
        self.eval_peer.send({"operation": operation, **codec.encode_arrays(fields)})
        response = self.eval_peer.receive(30.)
        if not response.get("ok"):
            raise RuntimeError("isolated proxy evaluator failed: " + str(response))
        return response["result"]

    def record(self, kind, **values):
        self.protocol_log.write(json.dumps({"kind": kind, "epoch": self.epoch,
            "clock_ns": self.world.time_ns, **values}, sort_keys=True) + "\n")

    def update_states(self):
        from nav_msgs.msg import Odometry
        from geometry_msgs.msg import TransformStamped
        samples = self.world.own_sensors()
        self.information.set_time(self.now)
        for name, sample in samples.items():
            state = sample["odom"]
            odom, transform = Odometry(), TransformStamped()
            odom.header.frame_id, odom.child_frame_id = name + "/odom", name + "/base_footprint"
            set_stamp(odom.header.stamp, state["source_stamp"])
            odom.pose.pose.position.x, odom.pose.pose.position.y = state["x"], state["y"]
            odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = math.sin(state["yaw"] / 2), math.cos(state["yaw"] / 2)
            odom.twist.twist.linear.x, odom.twist.twist.angular.z = state["v"], state["w"]
            transform.header.frame_id, transform.child_frame_id = "map", name + "/odom"
            set_stamp(transform.header.stamp, state["source_stamp"])
            transform.transform.rotation.w = 1.
            self.information.send_estimated_state(name, odom, transform)
        self.information.deliver()
        self.state_sequence += 1
        robots = self.delivered_robots()
        self.activity.update({"epoch": self.epoch, "sequence": self.state_sequence, "robots": robots}, self.now)

    def update_maps(self):
        from nav_msgs.msg import OccupancyGrid
        self.information.set_time(self.now)
        for name in self.dispatcher.robots:
            source = self.world.map_record(name)
            grid = OccupancyGrid()
            grid.header.frame_id = "map"
            set_stamp(grid.header.stamp, source["source_stamp"])
            grid.info.resolution = float(source["resolution"])
            grid.info.height, grid.info.width = source["grid"].shape
            grid.info.origin.position.x, grid.info.origin.position.y = map(float, source["origin"])
            grid.info.origin.orientation.w = 1.
            values = source["grid"]
            grid.data = (array("b", values.tobytes(order="C")) if values.dtype == np.dtype("int8")
                         else values.ravel().tolist())
            self.information.receive_local_map(name, grid)
        self.information.publish_maps()
        self.navigation_maps = self.information.snapshot_inputs()["navigation_maps"]

    def delivered_robots(self):
        navigation = self.dispatcher.navigation()
        robots = []
        for name in self.dispatcher.robots:
            record = self.information.received.get("state", name)
            if record is None:
                raise ValueError("no actually delivered estimated state")
            value = record.payload
            value.update(name=name, epoch=self.epoch, valid=True, source_stamp=record.source_stamp,
                         received_stamp=record.received_stamp, sequence=record.sequence, version=record.version)
            value["navigation"] = {**navigation[name], **self.nav_metadata.get(name, {}),
                                   "progress_m": self.activity.snapshot(name)["estimated_path_m"]}
            value["activity"] = self.activity.snapshot(name)
            value["history"] = list(self.history[name])
            robots.append(value)
        return robots

    def snapshot(self):
        from multi_robot_exploration.mr3_observation import build_snapshot
        self.sequence += 1
        robots = self.delivered_robots()
        for robot in robots:
            self.history[robot["name"]].append({k: robot[k] for k in ("x", "y", "source_stamp")})
        params = {**self.information.snapshot_inputs(), "robots": robots, "now": self.now,
                  "epoch": self.epoch, "sequence": self.sequence, "task_start": self.start_ns / 1e9}
        self.last_snapshot = build_snapshot(**params)
        self.last_inputs = codec.encode_arrays(params)
        return self.last_snapshot

    def flush_protocol(self):
        while self.events:
            event = self.events.popleft()
            self.record("dispatcher_event", event=event)
            if event["type"] in ("send_goal", "cancel_goal"):
                self.protocol.send("command", event["robot"], event, source_stamp=event["stamp"], now=self.now)
        for record in self.protocol.deliver(self.receipts, self.now):
            value, name = record.payload, record.source
            self.record("proxy_delivery", envelope=record.to_dict())
            if record.stream == "command":
                if value["type"] == "send_goal":
                    if (value.get("epoch") != self.epoch or value.get("robot") != name
                            or not value.get("goal_id")
                            or value.get("created_at", math.inf) > self.now
                            or value.get("expires_at", -1) <= self.now
                            or value.get("lease_until", -1) <= self.now):
                        raise ValueError("proxy endpoint rejected stale/expired goal delivery")
                    self.endpoint_goals[name] = {"x": value["x"], "y": value["y"], "goal_id": value["goal_id"]}
                    responses = [("accept", True)]
                else:
                    current = self.endpoint_goals.get(name)
                    if current is not None and current["goal_id"] != value["goal_id"]:
                        raise ValueError("proxy cancellation refers to another actual owner")
                    self.endpoint_goals.pop(name, None)
                    responses = [("cancel", True), ("result", "CANCELED")]
                for kind, result in responses:
                    self.protocol.send("receipt", name, {"type": kind, "goal_id": value["goal_id"], "value": result},
                                       source_stamp=self.now, now=self.now)
            elif record.stream == "receipt":
                self.nav_metadata[name] = {"source_stamp": record.source_stamp,
                    "received_stamp": record.received_stamp, "sequence": record.sequence}
                method = {"accept": self.dispatcher.on_accept, "cancel": self.dispatcher.on_cancel_response,
                          "result": self.dispatcher.on_result}[value["type"]]
                method(name, value["goal_id"], value["value"], self.now)
            elif record.stream == "heartbeat":
                self.dispatcher.renew(name, value["goal_id"], self.epoch, self.now, value["expires_at"])

    def heartbeat(self):
        if self.world.time_ns - self.last_heartbeat_ns < 200_000_000:
            return
        self.last_heartbeat_ns = self.world.time_ns
        for name, state in self.dispatcher.states.items():
            if state.goal_id is not None and not state.cancel_requested:
                self.protocol.send("heartbeat", name, {"goal_id": state.goal_id, "expires_at": self.now + 2.},
                                   source_stamp=self.now, now=self.now)

    def private_state(self):
        # The returned object is passed only to the private evaluator pipe.
        return self.world.evaluation_state()

    def goal_counts(self):
        return {name: state.accepted_goal_count for name, state in self.dispatcher.states.items()}

    def map_arguments(self):
        inputs = self.information.snapshot_inputs()
        return {"grid": inputs["raw_grid"], "resolution": inputs["resolution"], "origin": inputs["origin"]}

    def reset(self):
        self.world.reset()
        self.world.apply_commands({name: (0., 0.) for name in self.dispatcher.robots})
        for _ in range(5):
            self.world.advance()
        self.start_ns = self.world.time_ns
        self.information.set_time(self.now)
        self.update_maps()
        self.activity.start(self.now)
        self.update_states()
        snapshot = self.snapshot()
        diagnostic = self.evaluate("initialize", **self.map_arguments(), start_time=self.now)
        (self.directory / "proxy_model.json").write_text(json.dumps(self.world.metadata, indent=2) + "\n")
        return self.payload(snapshot, diagnostic, physical_dt=0., resetting=True)

    def payload(self, snapshot, diagnostic, *, physical_dt, resetting=False):
        return {"snapshot": snapshot, "proxy_actor_inputs": self.last_inputs,
                "reward": 0. if resetting else diagnostic["reward"],
                "terminated": False if resetting else diagnostic["terminated"],
                "truncated": False if resetting else diagnostic["truncated"],
                "info": {"epoch": self.epoch, "dt": 0. if resetting else diagnostic["delta_sim_time"],
                         "physical_dt": physical_dt, "reason": diagnostic.get("reason"),
                         "proxy_only": True, "training_eligible": False,
                         "reward_diagnostics": diagnostic,
                         "watermarks": {"map_version": snapshot["map"]["version"], "state_sequence": self.state_sequence}}}

    def advance_quantum(self, *, stopping=False):
        self.heartbeat()
        self.flush_protocol()
        self.flush_protocol()
        self.dispatcher.tick(self.now)
        self.flush_protocol()
        if stopping:
            commands = {name: (0., 0.) for name in self.dispatcher.robots}
        else:
            states = {v["name"]: v for v in self.delivered_robots()}
            maps = self.navigation_maps
            samples = self.world.own_sensors()
            goals = {name: goal for name, goal in self.endpoint_goals.items()
                     if not self.dispatcher.stopped and self.dispatcher.states[name].phase == "active"
                     and not self.dispatcher.states[name].cancel_requested}
            commands, reached = self.navigator.commands(states, goals, maps,
                                                        {n: v["scan"] for n, v in samples.items()}, self.now)
            for name in reached:
                goal = self.endpoint_goals.pop(name, None)
                if goal:
                    self.protocol.send("receipt", name, {"type": "result", "goal_id": goal["goal_id"],
                        "value": "SUCCEEDED"}, source_stamp=self.now, now=self.now)
        self.world.apply_commands(commands)
        self.world.advance()
        self.dispatcher.tick(self.now)
        self.information.set_time(self.now)
        self.update_states()  # Current controlled state delivery, every 20 ms.
        return self.evaluate("check", physical_state=self.private_state(), now=self.now,
                             navigation_failed=self.dispatcher.failed)

    def close_goals(self, reason):
        self.dispatcher.safety_stop(self.now, reason)
        deadline = self.world.time_ns + 10_000_000_000
        while not self.dispatcher.closed:
            if self.world.time_ns >= deadline:
                raise RuntimeError("proxy goal ownership closure timed out")
            self.advance_quantum(stopping=True)
        self.world.apply_commands({name: (0., 0.) for name in self.dispatcher.robots})

    def step(self, action, external_truncation=None):
        from multi_robot_exploration.mr3_observation import decode_joint_action
        if self.finished or type(action) is not int or not 0 <= action < 1000:
            raise ValueError("closed episode or invalid joint action")
        snapshot = self.last_snapshot
        if not snapshot["joint_action_mask"][action]:
            raise ValueError("joint action not in its actual preceding mask")
        start_ns = self.world.time_ns
        start = start_ns / 1e9
        for name, choice in zip(self.dispatcher.robots, decode_joint_action(action)):
            state = self.dispatcher.states[name]
            if choice < 8 and state.goal_id is not None:
                self.goal_switches += 1
            candidate = snapshot["candidates"][choice] if choice < 8 else None
            result = self.dispatcher.submit(name, "GOAL" if choice < 8 else "KEEP" if choice == 8 else "WAIT",
                self.now, snapshot["sequence"], self.steps + 1, self.now + 2.,
                goal=None if candidate is None else {k: candidate[k] for k in ("x", "y")},
                command_epoch=self.epoch, created_at=self.now)
            if result not in ("sent", "kept", "waiting", "switch_pending"):
                raise RuntimeError("masked action rejected by original dispatcher: " + result)
        reason = None
        for _ in range(50):
            check = self.advance_quantum()
            reason = check.get("terminal_reason")
            if reason:
                break
        self.update_maps()
        inspection = self.evaluate("inspect", **self.map_arguments(), physical_state=self.private_state(),
                                  goal_counts=self.goal_counts(), navigation_closed=self.dispatcher.closed)
        if reason is None and inspection.get("coverage_candidate"):
            reason = "coverage_reached"
        end_ns = self.world.time_ns
        end = end_ns / 1e9
        boundary_snapshot = self.snapshot()
        boundary_inputs = self.last_inputs
        boundary_maps = self.map_arguments()
        boundary_physical = self.private_state()
        boundary_goals = self.goal_counts()
        if reason or external_truncation:
            self.close_goals(reason or external_truncation)
        if reason == "coverage_reached" and self.world.time_ns - self.start_ns >= 300_000_000_000:
            raise RuntimeError("proxy coverage candidate did not close before the task deadline")
        self.steps += 1
        diagnostic = self.evaluate("advance", **boundary_maps, sequence=self.steps,
            step_start=start, step_end=end, physical_state=boundary_physical, goal_counts=boundary_goals,
            navigation_closed=self.dispatcher.closed, goal_switches=self.goal_switches,
            rejected_actions=self.rejected_actions, external_truncation=external_truncation, terminal_reason=reason)
        self.last_inputs = boundary_inputs
        result = self.payload(boundary_snapshot, diagnostic, physical_dt=(end_ns - start_ns) / 1e9)
        self.finished = result["terminated"] or result["truncated"]
        return result

    def close(self):
        try:
            if not self.dispatcher.closed:
                self.close_goals("external_close")
            self.evaluate("close")
            self.evaluator.stdin.close()
            returncode = self.evaluator.wait(timeout=10.)
            if returncode:
                raise RuntimeError("proxy evaluator did not close normally")
            (self.directory / "backend_summary.json").write_text(json.dumps({
                "epoch": self.epoch, "scene": self.scene, "seed": self.seed,
                "returned_steps": self.steps, "navigation_closed": self.dispatcher.closed,
                "navigation_failed": self.dispatcher.failed, "final_physical_time": self.now,
                "final_snapshot_time": self.last_snapshot["source_stamp"],
                "closure_tail_seconds": self.now - self.last_snapshot["source_stamp"],
                "blocked_quanta": self.navigator.blocked_quanta,
                "proxy_only": True, "native_qualification": False,
                "evaluator_returncode": returncode,
            }, indent=2) + "\n")
        finally:
            self.world.close()
            if self.evaluator.poll() is None:
                self.evaluator.terminate()
                self.evaluator.wait(timeout=10.)
            self.evaluator_log.close()
            self.protocol_log.close()


def evaluator_main(args, peer):
    from multi_robot_exploration.mr3_proxy2d_reward import ProxyReward
    evaluator = ProxyReward(args.scene, args.epoch)
    with gzip.open(args.directory / "private_evaluator.jsonl.gz", "wt", compresslevel=1) as stream:
        while True:
            request = peer.receive(120.)
            operation = request.pop("operation")
            fields = codec.decode_arrays(request)
            try:
                result = {} if operation == "close" else getattr(evaluator, operation)(**fields)
                response = {"ok": True, "result": result}
            except Exception as error:
                response = {"ok": False, "error": repr(error)}
            stream.write(json.dumps({"operation": operation, "request": request, "response": response}) + "\n")
            peer.send(response)
            if operation == "close":
                return


def main():
    from multi_robot_exploration.mr3_observation import SEED_RULES, validate_start_graph_rule
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", choices=("worker", "evaluator"), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--epoch", required=True)
    parser.add_argument("--scene", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--mapper", choices=("endpoint","karto"),default="endpoint")
    parser.add_argument("--mapper-library",type=Path)
    parser.add_argument("--seed-rule", choices=SEED_RULES, default="legacy")
    parser.add_argument("--start-graph-rule", choices=("original-seed-cell", "point-attachment-3x3-v1"),
                        default="original-seed-cell")
    args = parser.parse_args()
    validate_start_graph_rule(args.start_graph_rule, seed_rule=args.seed_rule)
    peer = ipc.JsonLinePeer(sys.stdin.fileno(), sys.stdout.fileno())
    if args.role == "evaluator":
        return evaluator_main(args, peer)
    worker, failed = None, False
    try:
        while True:
            request = peer.receive(120.)
            operation = request.pop("operation")
            try:
                if operation == "reset":
                    if worker is not None:
                        raise RuntimeError("one process per proxy episode")
                    kwargs = {"mapper": args.mapper, "mapper_library": args.mapper_library}
                    if args.seed_rule != "legacy":
                        kwargs["seed_rule"] = args.seed_rule
                    if args.start_graph_rule != "original-seed-cell":
                        kwargs["start_graph_rule"] = args.start_graph_rule
                    worker = ProxyWorker(args.directory, args.epoch, args.scene, args.seed, **kwargs)
                    result = worker.reset()
                elif operation == "close":
                    if worker is not None:
                        worker.close()
                        worker = None
                    peer.send({"ok": True, "result": {"closed": True}})
                    break
                elif operation == "step" and worker is not None:
                    result = worker.step(**request)
                else:
                    raise ValueError("invalid proxy operation")
                peer.send({"ok": True, "result": result})
            except Exception as error:
                failed = True
                traceback.print_exc(file=sys.stderr)
                peer.send({"ok": False, "error": repr(error)})
                break
    finally:
        if worker is not None:
            worker.close()
    return 1 if failed else 0


if __name__ == "__main__":
    profile_output = os.environ.get("MR3_PROXY2D_PROFILE_OUTPUT")
    if profile_output:
        from multi_robot_exploration.mr3_proxy2d_profile import run_profiled
        sys.exit(run_profiled(main, Path(profile_output)) or 0)
    sys.exit(main() or 0)
