"""Invalid unsealed attempts close native ownership without fabricated rewards."""

import copy
import json
from types import SimpleNamespace

import pytest
from std_msgs.msg import String

from multi_robot_exploration.task_evaluator import TaskEvaluator


def fixture(sealed=False):
    evaluator = TaskEvaluator.__new__(TaskEvaluator)
    evaluator.episode_id = "epoch"
    evaluator.robot_names = ["tb1", "tb2", "tb3"]
    evaluator.reward_ledger = SimpleNamespace(sealed=sealed, last_sequence=3)
    evaluator.reward_requests = {3: ("unchanged", {"reward": -4.})}
    evaluator.infrastructure_abort = None
    evaluator.infrastructure_abort_ack = None
    evaluator.navigation_protocol_closed = False
    evaluator.training_acknowledged = False
    evaluator.finalized = False
    evaluator.pending_stop_ack = None
    evaluator._now = lambda: 20.
    events = []
    evaluator.infrastructure_failure_publisher = SimpleNamespace(
        publish=lambda value: events.append(("failure_publication", json.loads(value.data))))
    evaluator._publish_reward_response = lambda value: events.append(
        ("response", copy.deepcopy(value)))

    def finalize(reason):
        events.append(("finalize", reason))
        evaluator.finalized = True

    evaluator.finalize = finalize
    return evaluator, events


def request(stage, **fields):
    return String(data=json.dumps({"epoch": "epoch", "reason": "infrastructure_failure",
                                   "operation": stage, **fields}))


def closure(**fields):
    return String(data=json.dumps({"epoch": "epoch", "robot_names": ["tb1", "tb2", "tb3"],
                                   "pending_goal_count": 0, "navigation_failure": False,
                                   "start_sim_time_sec": None, "stop_sim_time_sec": 20.,
                                   **fields}))


def test_begin_real_pre_release_closure_then_worker_finalize_without_reward_mutation():
    evaluator, events = fixture()
    before = copy.deepcopy(evaluator.reward_requests)
    evaluator._infrastructure_abort_callback(request("begin"))
    assert events[0][0] == "failure_publication" and len(events) == 2
    assert events[-1][1]["kind"] == "training_infrastructure_abort_started"
    evaluator._infrastructure_abort_callback(request("begin"))
    assert len(events) == 3 and sum(kind == "failure_publication" for kind, _ in events) == 1
    evaluator._stopped_callback(closure())
    assert evaluator.navigation_protocol_closed and not evaluator.finalized
    evaluator._infrastructure_abort_callback(request("finalize"))
    assert events[-2] == ("finalize", "shutdown")
    assert events[-1][1]["kind"] == "training_infrastructure_abort_ack"
    assert events[-1][1]["invalid_sample"] is True
    assert evaluator.training_acknowledged
    assert evaluator.reward_requests == before
    assert evaluator.reward_ledger.last_sequence == 3 and not evaluator.reward_ledger.sealed


def test_invalid_abort_cannot_finalize_a_sealed_training_ledger():
    evaluator, events = fixture(sealed=True)
    evaluator._infrastructure_abort_callback(request("begin"))
    assert evaluator.infrastructure_abort is None and not evaluator.finalized
    assert len(events) == 1 and events[0][1]["kind"] == "training_infrastructure_abort_error"
    assert "sealed" in events[0][1]["error"]


@pytest.mark.parametrize("mutation", [{"epoch": "old"}, {"reason": "task_terminal"},
                                      {"operation": True}, {"extra": 1}])
def test_abort_request_does_not_accept_another_epoch_or_normal_task_reason(mutation):
    evaluator, events = fixture()
    evaluator._infrastructure_abort_callback(request("begin", **mutation))
    assert evaluator.infrastructure_abort is None and not evaluator.finalized
    assert events[-1][1]["kind"] == "training_infrastructure_abort_error"


def test_finalize_without_begin_or_actual_goal_closure_is_rejected():
    evaluator, events = fixture()
    evaluator._infrastructure_abort_callback(request("finalize"))
    assert "lacks begin" in events[-1][1]["error"]
    evaluator._infrastructure_abort_callback(request("begin"))
    evaluator._infrastructure_abort_callback(request("finalize"))
    assert "actual navigation closure" in events[-1][1]["error"]
    assert not evaluator.finalized


@pytest.mark.parametrize("mutation", [{"epoch": "old"}, {"pending_goal_count": True},
                                      {"pending_goal_count": 1}, {"navigation_failure": 0}])
def test_infrastructure_closure_still_requires_real_typed_zero_goal_ack(mutation):
    evaluator, events = fixture()
    evaluator._infrastructure_abort_callback(request("begin"))
    evaluator._stopped_callback(closure(**mutation))
    assert not evaluator.navigation_protocol_closed and not evaluator.finalized
    assert events[-1][1]["kind"] == "training_infrastructure_abort_error"


def test_future_native_closure_is_retained_until_its_actual_clock():
    evaluator, _ = fixture()
    evaluator._infrastructure_abort_callback(request("begin"))
    message = closure(stop_sim_time_sec=20.02)
    evaluator._stopped_callback(message)
    assert evaluator.pending_stop_ack is message and not evaluator.navigation_protocol_closed
    evaluator._now = lambda: 20.02
    evaluator._stopped_callback(message)
    assert evaluator.navigation_protocol_closed


def test_abort_wait_does_not_let_periodic_failure_synthesize_a_task_terminal():
    evaluator, events = fixture()
    evaluator._infrastructure_abort_callback(request("begin"))
    evaluator._control_failure_callback(String(data="actual existing failure"))
    evaluator._timer_callback()
    assert evaluator.control_failure == "actual existing failure"
    assert not evaluator.finalized and len(events) == 2


def test_abort_freezes_release_and_pending_reward_processing():
    evaluator, events = fixture()
    evaluator._infrastructure_abort_callback(request("begin"))
    pending = {9: {"unprocessed_actual_request": True}}
    evaluator.pending_reward_requests = copy.deepcopy(pending)
    evaluator._release_callback(object())
    evaluator._drain_reward_requests()
    evaluator._reward_request_callback(String(data='{"sequence":9}'))
    assert evaluator.pending_reward_requests == pending
    assert evaluator.reward_ledger.last_sequence == 3 and not evaluator.reward_ledger.sealed
    assert events[-1][1]["kind"] == "training_infrastructure_abort_error"


def test_actual_navigation_failure_is_not_hidden_by_invalid_cleanup_ack():
    evaluator, events = fixture()
    evaluator._infrastructure_abort_callback(request("begin"))
    evaluator._stopped_callback(closure(navigation_failure=True))
    evaluator._infrastructure_abort_callback(request("finalize"))
    assert evaluator.stop_acknowledgment["navigation_failure"] is True
    assert events[-1][1]["invalid_sample"] is True
    assert events[-2] == ("finalize", "shutdown")
