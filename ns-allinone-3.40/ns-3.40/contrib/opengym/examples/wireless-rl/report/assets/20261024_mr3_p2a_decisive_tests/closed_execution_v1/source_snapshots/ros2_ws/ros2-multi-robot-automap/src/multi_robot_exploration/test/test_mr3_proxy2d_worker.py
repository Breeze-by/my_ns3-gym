"""Stubbed plant/evaluator protocol fixtures; never run a proxy episode."""

from collections import deque
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration.mr3_protocol import GoalDispatcher
from multi_robot_exploration.mr3_episode import elapsed_ns
from multi_robot_exploration.mr3_proxy2d_navigation import ProxyNavigator
from multi_robot_exploration.mr3_proxy2d_reward import ProxyReward
from multi_robot_exploration.mr3_reward import RewardLedger
from multi_robot_exploration.mr3_transport import IdealTransport, ReceivedStore


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/mr3_proxy2d_worker.py"
SPEC = importlib.util.spec_from_file_location("mr3_proxy2d_worker_cpu_fixture", SCRIPT)
worker_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(worker_module)
ROBOTS = ("tb1", "tb2", "tb3")


def test_evaluator_profile_has_separate_output_without_mutating_parent(monkeypatch, tmp_path):
    monkeypatch.setenv("MR3_PROXY2D_PROFILE_OUTPUT", str(tmp_path / "worker.pstats"))
    environment = worker_module.evaluator_environment(tmp_path)
    assert environment["MR3_PROXY2D_PROFILE_OUTPUT"] == str(tmp_path / "evaluator.pstats")
    assert worker_module.os.environ["MR3_PROXY2D_PROFILE_OUTPUT"] == str(tmp_path / "worker.pstats")


def test_evaluator_profile_remains_off_in_normal_mode(monkeypatch, tmp_path):
    monkeypatch.delenv("MR3_PROXY2D_PROFILE_OUTPUT", raising=False)
    assert "MR3_PROXY2D_PROFILE_OUTPUT" not in worker_module.evaluator_environment(tmp_path)


@pytest.mark.parametrize("dtype", [np.int8, np.int16])
def test_map_packing_is_detached_cdr_identical_for_noncontiguous_source(dtype):
    from rclpy.serialization import deserialize_message, serialize_message
    value = worker(.1)
    values = np.arange(-1, 101, dtype=dtype).reshape(6, 17)[:, ::2]
    before = values.copy()
    value.world.map_record = lambda name: {"grid": values, "source_stamp": .1,
        "resolution": .05, "origin": (-1., -2.)}
    captured = []
    value.information = SimpleNamespace(set_time=lambda _: None,
        receive_local_map=lambda name, grid: captured.append((name, grid)),
        publish_maps=lambda: None, snapshot_inputs=lambda: {"navigation_maps": {}})
    value.update_maps()
    assert [name for name, _ in captured] == list(ROBOTS)
    for _, message in captured:
        expected = copy.deepcopy(message)
        expected.data = values.ravel().tolist()
        assert message == expected and message.data.tobytes() == expected.data.tobytes()
        assert deserialize_message(serialize_message(message), type(message)) == deserialize_message(
            serialize_message(expected), type(expected))
    assert np.array_equal(before, values)
    values[:] = 11
    assert list(captured[0][1].data) == before.ravel().tolist()


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
                "delta_sim_time": elapsed_ns(fields["step_start"], fields["step_end"]) / 1e9,
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


@pytest.mark.parametrize("start", [.1, 3.1, 7.1, 127.1])
def test_integer_physical_span_equals_original_reward_clock_for_one_second(start):
    value = step_boundary_fixture(start)
    result = value.step(888)
    truth = np.ones((2, 2), dtype=bool)
    original = RewardLedger(value.epoch, start, truth, np.zeros_like(truth))
    expected = original.advance(epoch=value.epoch, sequence=1, step_start=start, step_end=start + 1.,
        current_correct_free_mask=np.zeros_like(truth), collision_events=0,
        goal_switches=0, rejected_actions=0)
    assert result["info"]["physical_dt"] == expected["delta_sim_time"] == 1.
    assert result["info"]["dt"] == result["info"]["physical_dt"]
    assert result["snapshot"]["source_stamp"] == (round(start * 1e9) + 1_000_000_000) / 1e9


@pytest.mark.parametrize("start", [.1, 3.1, 7.1, 127.1])
def test_twenty_millisecond_terminal_span_excludes_real_closure_tail(start):
    value = step_boundary_fixture(start, tail=.4)
    def first_terminal(**kwargs):
        value.world.time_ns += 20_000_000
        return {"terminal_reason": "collision"}
    value.advance_quantum = first_terminal
    value.private_state = lambda: {"captured_at": value.now,
        "path_lengths": {name: 1. for name in ROBOTS}, "collision_events": 1}
    result = value.step(888)
    endpoint = (round(start * 1e9) + 20_000_000) / 1e9
    truth = np.ones((2, 2), dtype=bool)
    original = RewardLedger(value.epoch, start, truth, np.zeros_like(truth))
    expected = original.advance(epoch=value.epoch, sequence=1, step_start=start, step_end=endpoint,
        current_correct_free_mask=np.zeros_like(truth), collision_events=1,
        goal_switches=0, rejected_actions=0, terminal_reason="collision")
    assert result["terminated"] and result["info"]["reason"] == "collision"
    assert result["info"]["physical_dt"] == expected["delta_sim_time"] == .02
    assert result["info"]["dt"] == result["info"]["physical_dt"]
    assert result["snapshot"]["source_stamp"] == endpoint
    assert value.reward_calls[0]["physical_state"]["captured_at"] == endpoint
    assert value.now == (round(start * 1e9) + 420_000_000) / 1e9


def prepare_deadline_step(value, start_ns, *, task_start_ns=100_000_000):
    """Use real protocol, check and reward kernels around a dummy 20ms clock."""
    value.world.time_ns = start_ns
    value.start_ns = task_start_ns
    value.finished, value.sequence, value.state_sequence = False, 1, 1
    value.goal_switches = value.rejected_actions = 0
    value.last_heartbeat_ns = -1
    value.paths = {name: 0. for name in ROBOTS}
    value.applied_commands, value.private_checks, value.reward_calls = [], [], []
    value.world.commands = {name: (0., 0.) for name in ROBOTS}
    def apply(commands):
        value.world.commands = copy.deepcopy(commands)
        value.applied_commands.append((value.world.time_ns, copy.deepcopy(commands)))
    def advance():
        for name in ROBOTS:
            value.paths[name] += abs(value.world.commands[name][0]) * .02
        value.world.time_ns += 20_000_000
    value.world.apply_commands, value.world.advance = apply, advance
    value.world.own_sensors = lambda: {name: {"scan": {}} for name in ROBOTS}
    value.information = SimpleNamespace(set_time=lambda now: None)
    value.navigation_maps = {}
    value.delivered_robots = lambda: [{"name": name} for name in ROBOTS]
    value.navigator = SimpleNamespace(commands=lambda states, goals, maps, scans, now:
        ({name: (.12, 0.) if name in goals else (0., 0.) for name in ROBOTS}, []))
    value.observed_failures = []
    value.update_states = lambda: value.observed_failures.append((value.world.time_ns, value.dispatcher.failed))
    value.update_maps = lambda: None
    value.map_arguments = lambda: {"grid": np.zeros((2, 2), dtype=np.int16),
                                  "resolution": .25, "origin": (0., 0.)}
    value.private_state = lambda: {"time_ns": value.world.time_ns,
        "path_lengths": dict(value.paths), "collision_events": 0,
        "contact_events": [], "native_contact_monitoring": False}
    def snapshot():
        value.sequence += 1
        value.last_snapshot = {"sequence": value.sequence, "source_stamp": value.now,
            "map_version": 1, "map": {"version": 1}, "joint_action_mask": [True] * 1000,
            "candidates": [], "navigation": value.dispatcher.navigation()}
        value.last_inputs = {"actor_time": value.now}
        return copy.deepcopy(value.last_snapshot)
    value.snapshot = snapshot
    snapshot()
    free = np.ones((2, 2), dtype=bool)
    correct = np.zeros_like(free)
    ledger = RewardLedger(value.epoch, task_start_ns / 1e9, free, correct)
    if start_ns > task_start_ns:
        ledger.advance(epoch=value.epoch, sequence=1, step_start=task_start_ns / 1e9,
            step_end=start_ns / 1e9, current_correct_free_mask=correct,
            collision_events=0, goal_switches=0, rejected_actions=0)
    value.steps = ledger.last_sequence
    evaluator = ProxyReward.__new__(ProxyReward)
    evaluator._ledger = ledger  # No truth loader, ProxyWorld, Node or process.
    def evaluate(operation, **fields):
        if operation == "check":
            value.private_checks.append(copy.deepcopy(fields))
            return evaluator.check(**fields)
        if operation == "inspect":
            return {"coverage_candidate": False}
        assert operation == "advance"
        value.reward_calls.append(copy.deepcopy(fields))
        return ledger.advance(epoch=value.epoch, sequence=fields["sequence"],
            step_start=fields["step_start"], step_end=fields["step_end"],
            current_correct_free_mask=correct, collision_events=fields["physical_state"]["collision_events"],
            goal_switches=fields["goal_switches"], rejected_actions=fields["rejected_actions"],
            terminal_reason=fields["terminal_reason"], external_truncation=fields["external_truncation"])
    value.evaluate = evaluate
    return value


def active_deadline_fixture(kind, remaining_ns, *, task_deadline=False):
    initial_ns = 298_100_000_000 if task_deadline else 1_100_000_000
    value = worker(initial_ns / 1e9)
    assert value.dispatcher.submit("tb1", "GOAL", value.now, 1, 0, value.now + 2.,
        goal={"x": 2., "y": 0.}, command_epoch=value.epoch, created_at=value.now) == "sent"
    value.flush_protocol()
    value.flush_protocol()
    assert value.dispatcher.states["tb1"].phase == "active"
    if kind == "execution":
        goal_id = value.dispatcher.states["tb1"].goal_id
        # Keep the original 2s lease alive with real, bounded renewals; only
        # the unchanged 60s execution deadline may expire in this fixture.
        for elapsed in range(1, 60):
            now = (initial_ns + elapsed * 1_000_000_000) / 1e9
            assert value.dispatcher.renew("tb1", goal_id, value.epoch, now, now + 2.) == "renewed"
        deadline_ns = initial_ns + 60_000_000_000
    else:
        deadline_ns = initial_ns + 2_000_000_000
    prepare_deadline_step(value, deadline_ns - remaining_ns)
    if kind == "lease":
        value.heartbeat = lambda: None  # Explicit missing delivery, not KEEP renewal.
    return value, deadline_ns


@pytest.mark.parametrize("kind,reason", [("lease", "goal_lease_expired"),
                                       ("execution", "navigation_execution_timeout")])
def test_new_quantum_boundary_ticks_before_state_publication_and_terminal_check(kind, reason):
    value, deadline = active_deadline_fixture(kind, 40_000_000)
    first = value.advance_quantum()
    assert value.world.time_ns == deadline - 20_000_000
    assert first["terminal_reason"] is None and not value.dispatcher.failed
    second = value.advance_quantum()
    assert value.world.time_ns == deadline
    assert second["terminal_reason"] == "navigation_failure" and second["terminated"]
    assert value.dispatcher.states["tb1"].failure == reason
    assert value.observed_failures[-1] == (deadline, True)
    assert value.private_checks[-1]["navigation_failed"] is True


@pytest.mark.parametrize("kind,reason", [("lease", "goal_lease_expired"),
                                       ("execution", "navigation_execution_timeout")])
@pytest.mark.parametrize("span_ns", [500_000_000, 1_000_000_000])
def test_deadline_inside_or_at_last_step_quantum_returns_real_failure_and_closes(kind, reason, span_ns):
    value, deadline = active_deadline_fixture(kind, span_ns)
    result = value.step(888)
    assert result["terminated"] and not result["truncated"]
    assert result["info"]["reason"] == "navigation_failure"
    assert result["info"]["physical_dt"] == result["info"]["dt"] == span_ns / 1e9
    assert result["snapshot"]["source_stamp"] == result["proxy_actor_inputs"]["actor_time"] == deadline / 1e9
    assert value.reward_calls[0]["step_end"] == deadline / 1e9
    assert value.reward_calls[0]["physical_state"]["time_ns"] == deadline
    assert value.dispatcher.closed and value.dispatcher.states["tb1"].last_terminal == "CANCELED"
    assert value.dispatcher.states["tb1"].failure == reason
    failures = [fields["event"] for kind_, fields in value.records
                if kind_ == "dispatcher_event" and fields["event"]["type"] == "protocol_failure"]
    assert len(failures) == 1 and failures[0]["reason"] == reason
    assert 0 < value.world.time_ns - deadline <= 10_000_000_000
    assert all(all(command == (0., 0.) for command in commands.values())
               for clock, commands in value.applied_commands if clock >= deadline)
    assert value.paths == value.reward_calls[0]["physical_state"]["path_lengths"]
    commands_before = copy.deepcopy(value.dispatcher._last_command)
    with pytest.raises(ValueError, match="closed episode"):
        value.step(888)
    assert value.dispatcher._last_command == commands_before


def test_late_fifo_accept_does_not_renew_expired_lease_and_still_closes_real_owner():
    value = worker(1.1)
    assert value.dispatcher.submit("tb1", "GOAL", value.now, 1, 0, 3.1,
        goal={"x": 2., "y": 0.}, command_epoch=value.epoch, created_at=value.now) == "sent"
    command = value.events.popleft()
    stale = {"type": "result", "goal_id": "old-owner", "value": "CANCELED"}
    value.protocol.send("receipt", "tb1", stale, source_stamp=2.9, now=2.9)
    value.protocol.send("command", "tb1", command, source_stamp=1.1, now=1.1)
    value.protocol.send("receipt", "tb1", stale, source_stamp=2.9, now=2.9)
    value.world.time_ns = 2_900_000_000
    value.flush_protocol()  # Command delivered; accept is behind the older receipt.
    assert value.dispatcher.states["tb1"].phase == "accepting"
    prepare_deadline_step(value, 2_900_000_000)
    result = value.step(888)
    assert result["terminated"] and result["info"]["reason"] == "navigation_failure"
    assert result["info"]["physical_dt"] == result["info"]["dt"] == .2
    assert result["snapshot"]["source_stamp"] == 3.1
    assert value.dispatcher.states["tb1"].failure == "goal_lease_expired"
    assert value.dispatcher.closed and value.dispatcher.states["tb1"].last_terminal == "CANCELED"
    accepted = [fields["envelope"] for kind_, fields in value.records if kind_ == "proxy_delivery"
                and fields["envelope"]["stream"] == "receipt"
                and fields["envelope"]["payload"].get("type") == "accept"]
    assert len(accepted) == 1 and accepted[0]["generated_stamp"] == 2.9
    assert accepted[0]["received_stamp"] > 3.1
    assert result["snapshot"]["navigation"]["tb1"]["accepted_goal_count"] == 0
    assert value.dispatcher.states["tb1"].accepted_goal_count == 1


def test_task_deadline_still_wins_over_same_boundary_protocol_failure_and_external_cut():
    value, deadline = active_deadline_fixture("lease", 1_000_000_000, task_deadline=True)
    result = value.step(888, external_truncation="external_sampler_limit")
    assert deadline == 300_100_000_000
    assert result["terminated"] and not result["truncated"] and result["info"]["reason"] == "timeout"
    assert result["info"]["dt"] == result["info"]["physical_dt"] == 1.
    assert value.dispatcher.failed and value.dispatcher.states["tb1"].failure == "goal_lease_expired"
    assert value.private_checks[-1]["navigation_failed"] is True
    assert value.dispatcher.closed
