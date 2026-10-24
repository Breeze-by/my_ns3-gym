"""Native-service response fixtures; no ROS initialization or simulator execution."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest


SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location("mr3_worker_shutdown", SCRIPTS / "mr3_env_worker.py")
WORKER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(WORKER)


class Manage:
    class Request:
        SHUTDOWN = 4


class GetState:
    class Request:
        pass


class Clock:
    def __init__(self):
        self.wall_ns = 100 * 10**9

    def monotonic_ns(self):
        return self.wall_ns

    def monotonic(self):
        return self.wall_ns / 1e9


class Condition:
    def __init__(self, clock):
        self.clock = clock

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def wait(self, duration):
        self.clock.wall_ns += round(duration * 1e9)


def fixture(tmp_path, monkeypatch, *, unavailable=None, rejected=None,
            active=None, pending_response=None, moving_clock=None):
    clock = Clock()
    monkeypatch.setattr(WORKER.time, "monotonic_ns", clock.monotonic_ns)
    monkeypatch.setattr(WORKER.time, "monotonic", clock.monotonic)
    instance = WORKER.Worker.__new__(WORKER.Worker)
    instance.epoch = "shutdown-fixture"
    instance.directory = tmp_path
    instance.physical_ns = instance.clock_ns = 20 * 10**9
    instance.closed = {"epoch": instance.epoch, "pending_goal_count": 0,
                       "robot_names": ["tb1", "tb2", "tb3"]}
    instance.closed_received_clock_ns = instance.clock_ns
    instance.closed_received_wall_monotonic_ns = clock.wall_ns - 1000
    instance.nav2_shutdown_clients = []
    instance.ManageLifecycleNodes, instance.GetState = Manage, GetState
    instance.condition = Condition(clock)
    instance._healthy = lambda: None
    sent = []

    def client(service_type, service):
        def call(request):
            sent.append((service_type, service, getattr(request, "command", None)))
            clock.wall_ns += 1000000
            if service == moving_clock:
                instance.clock_ns += 20000000
            if service_type is Manage:
                response = SimpleNamespace(success=service != rejected)
            else:
                state = SimpleNamespace(id=3 if service == active else 4,
                                        label="active" if service == active else "finalized")
                response = SimpleNamespace(current_state=state)
            return SimpleNamespace(done=lambda: service != pending_response,
                                   result=lambda: response)

        return SimpleNamespace(service_is_ready=lambda: service != unavailable, call_async=call)

    instance.node = SimpleNamespace(create_client=client)
    instance._physics = lambda *args, **kwargs: pytest.fail("lifecycle must keep physics paused")
    return instance, sent


def test_shutdown_calls_real_services_in_robot_order_and_requires_all_18_final_states(
        tmp_path, monkeypatch):
    instance, sent = fixture(tmp_path, monkeypatch)
    result = instance._shutdown_nav2()
    assert result == json.loads((tmp_path / "nav2_shutdown.json").read_text())
    assert result["success"] and not result["failures"]
    assert result["protocol"] == WORKER.SHUTDOWN_PROTOCOL
    assert result["start_clock_ns"] == result["end_clock_ns"] == result["physical_time_ns"]
    assert len(sent) == len(instance.nav2_shutdown_clients) == 21
    expected = []
    for robot in ("tb1", "tb2", "tb3"):
        expected.append((Manage, f"/{robot}/lifecycle_manager_navigation/manage_nodes", 4))
        expected.extend((GetState, f"/{robot}/{node}/get_state", None)
                        for node in WORKER.NAV2_NODES)
    assert sent == expected
    assert sum(len(row["states"]) for row in result["robots"]) == 18
    operations = [item for robot in result["robots"]
                  for item in (robot["shutdown"], *robot["states"])]
    for left, right in zip(operations, operations[1:]):
        assert left["completed_wall_monotonic_ns"] <= right["request_wall_monotonic_ns"]
    assert result["wall_duration_sec"] == .021
    assert all(row["state"] == {"id": 4, "label": "finalized"}
               for robot in result["robots"] for row in robot["states"])
    with pytest.raises(FileExistsError):
        instance._shutdown_nav2()
    assert len(sent) == 21


def test_manager_success_does_not_substitute_for_an_active_node_state(tmp_path, monkeypatch):
    instance, sent = fixture(tmp_path, monkeypatch, active="/tb2/planner_server/get_state")
    with pytest.raises(RuntimeError, match="did not finalize"):
        instance._shutdown_nav2()
    result = json.loads((tmp_path / "nav2_shutdown.json").read_text())
    assert not result["success"] and result["failures"]
    assert result["robots"][-1]["shutdown"]["response"]["success"] is True
    assert result["robots"][-1]["states"][-1]["state"]["id"] == 3
    assert all("/tb3/" not in service for _, service, _ in sent)


def test_rejected_shutdown_is_not_retried_or_followed_by_state_fabrication(tmp_path, monkeypatch):
    service = "/tb2/lifecycle_manager_navigation/manage_nodes"
    instance, sent = fixture(tmp_path, monkeypatch, rejected=service)
    with pytest.raises(RuntimeError, match="rejected shutdown"):
        instance._shutdown_nav2()
    result = json.loads((tmp_path / "nav2_shutdown.json").read_text())
    assert not result["success"] and result["failures"]
    assert result["robots"][-1]["states"] == []
    assert [name for _, name, _ in sent].count(service) == 1


@pytest.mark.parametrize("kind", ["unavailable", "pending_response"])
def test_missing_service_or_response_uses_one_total_wall_guard_without_physics(
        tmp_path, monkeypatch, kind):
    service = "/tb1/lifecycle_manager_navigation/manage_nodes"
    instance, sent = fixture(tmp_path, monkeypatch, **{kind: service})
    with pytest.raises(TimeoutError):
        instance._shutdown_nav2()
    result = json.loads((tmp_path / "nav2_shutdown.json").read_text())
    assert not result["success"] and result["failures"]
    assert result["wall_duration_sec"] == WORKER.NAV2_SHUTDOWN_WALL_GUARD_SEC
    assert len(sent) == (0 if kind == "unavailable" else 1)
    assert result["start_clock_ns"] == result["end_clock_ns"]


@pytest.mark.parametrize("invalid", ["pending_goal", "foreign_epoch", "missing_receipt"])
def test_lifecycle_shutdown_requires_real_closed_goal_ack(tmp_path, monkeypatch, invalid):
    instance, sent = fixture(tmp_path, monkeypatch)
    if invalid == "pending_goal":
        instance.closed["pending_goal_count"] = 1
    elif invalid == "foreign_epoch":
        instance.closed["epoch"] = "previous"
    else:
        instance.closed_received_wall_monotonic_ns = None
    with pytest.raises(RuntimeError, match="real closed-goal"):
        instance._shutdown_nav2()
    assert sent == []
    assert not json.loads((tmp_path / "nav2_shutdown.json").read_text())["success"]


def test_unexpected_clock_motion_during_service_is_an_infrastructure_failure(
        tmp_path, monkeypatch):
    instance, sent = fixture(tmp_path, monkeypatch,
                             moving_clock="/tb1/controller_server/get_state")
    with pytest.raises(RuntimeError, match="clock changed"):
        instance._shutdown_nav2()
    result = json.loads((tmp_path / "nav2_shutdown.json").read_text())
    assert not result["success"] and len(sent) == 2
    assert result["start_clock_ns"] != result["end_clock_ns"]


@pytest.mark.parametrize("reject", [False, True])
def test_lifecycle_barrier_precedes_helper_close_and_finalize_and_failure_stops_both(
        tmp_path, monkeypatch, reject):
    service = "/tb1/lifecycle_manager_navigation/manage_nodes"
    instance, _ = fixture(tmp_path, monkeypatch, rejected=service if reject else None)
    events = []
    lifecycle = instance._shutdown_nav2

    def barrier():
        events.append("lifecycle_begin")
        result = lifecycle()
        events.append("lifecycle_finished")
        return result

    instance._shutdown_nav2 = barrier
    instance.Header = lambda: SimpleNamespace(stamp=SimpleNamespace(sec=0, nanosec=0))
    instance.stop_pub = SimpleNamespace(publish=lambda request: events.append("goal_stop"))
    instance.helper = SimpleNamespace(
        stdin=SimpleNamespace(close=lambda: events.append("helper_stdin_close")),
        stdout=SimpleNamespace(close=lambda: events.append("helper_stdout_close")),
        wait=lambda timeout: events.append("helper_wait"), returncode=0)
    instance.finalize_pub = object()
    instance.finalize_ack = {"epoch": instance.epoch, "ack_sequence": 4,
                             "kind": "training_finalize_ack", "reason": "task_terminal"}
    instance._publish = lambda publisher, value: events.append("finalize_request")
    instance.launch = SimpleNamespace(wait=lambda timeout: events.append("launch_wait"),
                                      returncode=0)
    instance.reward_number = 4
    instance.scene, instance.seed = "open", 101
    instance.failures, instance.finished = [], False
    instance.started_wall = WORKER.time.monotonic()
    (tmp_path / "launch.log").write_text("")
    module = SimpleNamespace(native_stop_receipt=lambda text: {"returncode": 0})
    monkeypatch.setitem(sys.modules, "run_mr3_adapter_probe", module)
    if reject:
        with pytest.raises(RuntimeError, match="rejected shutdown"):
            instance.shutdown_episode("task_terminal")
        assert events == ["goal_stop", "lifecycle_begin"]
        assert not (tmp_path / "summary.json").exists()
    else:
        instance.shutdown_episode("task_terminal")
        assert events == ["goal_stop", "lifecycle_begin", "lifecycle_finished",
                          "helper_stdin_close", "helper_wait", "helper_stdout_close",
                          "finalize_request", "launch_wait"]
        summary = json.loads((tmp_path / "summary.json").read_text())
        assert summary["shutdown_protocol"] == WORKER.SHUTDOWN_PROTOCOL
        assert summary["nav2_shutdown"] == instance.nav2_shutdown_receipt
        assert summary["training_finalize_request"] == instance.finalize_request
        assert summary["training_finalize_ack"] == instance.finalize_ack
