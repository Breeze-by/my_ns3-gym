"""Stubbed plant/evaluator protocol fixtures; never run a proxy episode."""

from collections import deque
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration.mr3_protocol import GoalDispatcher
from multi_robot_exploration.mr3_proxy2d_navigation import ProxyNavigator
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/mr3_proxy2d_worker.py"
SPEC = importlib.util.spec_from_file_location("mr3_proxy2d_worker_cpu_fixture", SCRIPT)
worker_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker_module)
ROBOTS = ("tb1", "tb2", "tb3")


def worker(now=1.):
    """Bypass production construction: no World, process, file or evaluator."""
    value = worker_module.ProxyWorker.__new__(worker_module.ProxyWorker)
    value.epoch = "proxy-protocol-fixture"
    value.world = SimpleNamespace(time_ns=round(now * 1e9))
    value.events = deque()
    value.dispatcher = GoalDispatcher(value.epoch, value.events.append)
    value.protocol = IdealTransport(value.epoch)
    value.receipts = ReceivedStore(value.epoch)
    value.endpoint_goals, value.nav_metadata = {}, {}
    value.records = []
    value.record = lambda kind, **fields: value.records.append((kind, copy.deepcopy(fields)))
    return value


def start_goal(value, robot="tb1", *, expiry=3.):
    assert value.dispatcher.submit(robot, "GOAL", value.now, 1, 1, expiry,
        goal={"x": 2., "y": 0.}, command_epoch=value.epoch, created_at=value.now) == "sent"


def test_accept_and_cancel_are_distinct_deliveries_and_only_terminal_closes_owner():
    value = worker()
    start_goal(value)
    assert value.dispatcher.states["tb1"].phase == "accepting"
    assert not value.endpoint_goals and not value.dispatcher.closed
    value.flush_protocol()
    assert "tb1" in value.endpoint_goals
    assert value.dispatcher.states["tb1"].phase == "accepting"
    value.flush_protocol()
    assert value.dispatcher.states["tb1"].phase == "active"
    assert value.dispatcher.states["tb1"].accepted_goal_count == 1
    value.dispatcher.safety_stop(value.now, "external_cut")
    value.flush_protocol()
    assert "tb1" not in value.endpoint_goals
    assert not value.dispatcher.closed
    value.world.time_ns = 1_200_000_000
    value.flush_protocol()
    assert value.dispatcher.states["tb1"].cancel_accepted is True
    assert not value.dispatcher.closed, "a cancel response is not terminal ownership release"
    value.world.time_ns = 1_400_000_000
    value.flush_protocol()
    assert value.dispatcher.closed
    assert value.dispatcher.states["tb1"].last_terminal == "CANCELED"


def test_late_expired_command_never_installs_a_new_executable_endpoint_goal():
    value = worker()
    start_goal(value)
    value.world.time_ns = 3_100_000_000
    with pytest.raises(ValueError, match="stale/expired"):
        value.flush_protocol()
    assert "tb1" not in value.endpoint_goals, "delivery after original expires_at must not start motion"


def test_private_physics_and_raw_odometry_do_not_replace_delivered_navigation_inputs():
    value = worker()
    value.heartbeat = lambda: None
    value.private_state = lambda: {"collision_events": 0, "path_lengths": {name: 0. for name in ROBOTS},
                                   "poses": "evaluator-only poison"}
    delivered = [{"name": name, "x": float(index * 3), "y": 0., "yaw": 0.,
                  "source_stamp": 1., "received_stamp": 1., "valid": True}
                 for index, name in enumerate(ROBOTS)]
    value.delivered_robots = lambda: copy.deepcopy(delivered)
    maps = {name: {"grid": np.full((5, 5), -1, dtype=np.int16),
                   "resolution": .2, "origin": (-.5, -.5), "payload_sha256": name}
            for name in ROBOTS}
    value.information = SimpleNamespace(snapshot_inputs=lambda: {"navigation_maps": maps}, set_time=lambda now: None)
    value.navigation_maps = maps
    scans = {name: {"ranges": np.ones(4), "angles": np.array((0., 1., 2., 3.))} for name in ROBOTS}
    value.world.own_sensors = lambda: {name: {"scan": scans[name], "odom": {"x": 999.}} for name in ROBOTS}
    def no_raw_map(*args, **kwargs):
        raise AssertionError("navigation must use actual delivered navigation_maps")
    value.world.map_record = no_raw_map
    captured = {}
    def commands(states, goals, navigation, local_scans, now):
        captured.update(states=states, maps=navigation, scans=local_scans, now=now)
        assert all("poses" not in state and state["x"] != 999. for state in states.values())
        return {name: (0., 0.) for name in ROBOTS}, []
    value.navigator = SimpleNamespace(commands=commands)
    value.world.apply_commands = lambda commands: None
    value.world.advance = lambda: setattr(value.world, "time_ns", value.world.time_ns + 20_000_000)
    value.update_states = lambda: None
    private = []
    value.evaluate = lambda operation, **fields: private.append((operation, fields)) or {"terminal_reason": None}
    value.advance_quantum()
    assert captured["maps"] is maps
    assert captured["scans"]["tb1"] is scans["tb1"]
    assert private[0][0] == "check" and private[0][1]["physical_state"]["poses"] == "evaluator-only poison"


def test_protocol_expiry_stops_old_endpoint_before_the_next_physical_quantum():
    value = worker()
    start_goal(value)
    value.flush_protocol()
    value.flush_protocol()
    value.world.time_ns = 3_000_000_000
    value.heartbeat = lambda: None  # Explicit loss of renewals, not a new episode.
    value.private_state = lambda: {"collision_events": 0}
    value.information = SimpleNamespace(snapshot_inputs=lambda: {"navigation_maps": {}}, set_time=lambda now: None)
    value.navigation_maps = {}
    value.delivered_robots = lambda: [{"name": name} for name in ROBOTS]
    value.world.own_sensors = lambda: {name: {"scan": {}} for name in ROBOTS}
    def commands(states, goals, maps, scans, now):
        return {name: ((.12, 0.) if name in goals else (0., 0.)) for name in ROBOTS}, []
    value.navigator = SimpleNamespace(commands=commands)
    physical_commands = []
    value.world.apply_commands = lambda commands: physical_commands.append(commands)
    value.world.advance = lambda: setattr(value.world, "time_ns", value.world.time_ns + 20_000_000)
    value.update_states = lambda: None
    value.evaluate = lambda operation, **fields: {"terminal_reason": "navigation_failure"}
    value.advance_quantum()
    assert value.dispatcher.failed
    assert physical_commands[0]["tb1"] == (0., 0.), "expired lease cannot produce an extra moving quantum"


def test_local_unknown_navigation_grid_never_uses_hidden_true_free_space():
    navigation = ProxyNavigator()
    state = {"x": 0., "y": 0., "yaw": 0.}
    local = {"grid": np.full((21, 21), -1, dtype=np.int16), "resolution": .2,
             "origin": (-2.1, -2.1), "payload_sha256": "a" * 64}
    goal = {"x": 1., "y": 0.}
    velocity, reached = navigation.target_velocity("tb1", state, goal, local)
    assert velocity == (0., 0.) and not reached
    # The API has no truth argument; an unrelated full map cannot change it.
    hidden_full_free_map = np.zeros((21, 21), dtype=np.int16)
    hidden_full_free_map[:] = 100
    assert navigation.target_velocity("tb1", state, goal, local) == (velocity, reached)


def step_boundary_fixture(now=5., *, coverage=False, tail=.4):
    value = worker(now)
    value.finished, value.steps, value.sequence, value.state_sequence = False, 0, 1, 1
    value.start_ns, value.goal_switches, value.rejected_actions = 0, 0, 0
    value.last_snapshot = {"sequence": 1, "joint_action_mask": [True] * 1000,
                           "candidates": [], "source_stamp": now, "map_version": 1,
                           "map": {"version": 1}}
    value.last_inputs = {"actor_time": now}
    value.update_maps = lambda: None
    value.map_arguments = lambda: {"grid": np.zeros((2, 2), dtype=np.int16),
                                   "resolution": .2, "origin": (0., 0.)}
    value.private_state = lambda: {"captured_at": value.now,
        "path_lengths": {name: 1. for name in ROBOTS}, "collision_events": 0}
    def quantum(**kwargs):
        value.world.time_ns += 20_000_000
        return {"terminal_reason": None}
    value.advance_quantum = quantum
    def snapshot():
        value.sequence += 1
        value.last_snapshot = {"sequence": value.sequence, "source_stamp": value.now,
                               "map_version": 1, "map": {"version": 1}}
        value.last_inputs = {"actor_time": value.now}
        return copy.deepcopy(value.last_snapshot)
    value.snapshot = snapshot
    value.close_goals = lambda reason: setattr(value.world, "time_ns", value.world.time_ns + round(tail * 1e9))
    value.reward_calls = []
    def evaluate(operation, **fields):
        if operation == "inspect":
            return {"coverage_candidate": coverage}
        assert operation == "advance"
        value.reward_calls.append(copy.deepcopy(fields))
        reason = fields["terminal_reason"]
        truncated = reason is None and bool(fields["external_truncation"])
        return {"reward": 0., "terminated": reason is not None, "truncated": truncated,
                "reason": reason if reason is not None else fields["external_truncation"],
                "delta_sim_time": fields["step_end"] - fields["step_start"],
                "proxy_task_success": reason == "coverage_reached"}
    value.evaluate = evaluate
    return value


def test_external_cut_retains_actual_preclosure_actor_and_reward_boundary_with_real_tail():
    value = step_boundary_fixture()
    result = value.step(888, external_truncation="external_sampler_limit")
    assert value.now == 6.4
    assert result["snapshot"]["source_stamp"] == 6.
    assert result["proxy_actor_inputs"]["actor_time"] == 6.
    assert result["info"]["physical_dt"] == 1.
    assert result["info"]["dt"] == 1.
    assert value.reward_calls[0]["step_end"] == 6.
    assert value.reward_calls[0]["physical_state"]["captured_at"] == 6.
    assert value.finished and result["truncated"]


def test_coverage_candidate_cannot_become_success_after_closure_crosses_task_deadline():
    value = step_boundary_fixture(298.9, coverage=True, tail=.4)
    try:
        result = value.step(888)
    except RuntimeError as error:
        # A truthful bounded activity failure is allowed; claiming success is not.
        assert "deadline" in str(error)
    else:
        assert result["terminated"] and result["info"]["reason"] == "timeout"
        assert not result["info"]["reward_diagnostics"]["proxy_task_success"]
    assert value.now > 300.
    assert not any(call["terminal_reason"] == "coverage_reached" for call in value.reward_calls)
