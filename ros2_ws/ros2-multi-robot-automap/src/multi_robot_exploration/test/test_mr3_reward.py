"""Reward anti-repetition, finite task endings and isolated evaluator RPC checks."""

from collections import deque
import copy
import json
from pathlib import Path
from types import MethodType, SimpleNamespace

import numpy as np
import pytest
from std_msgs.msg import String
from nav_msgs.msg import OccupancyGrid
import rclpy
from std_msgs.msg import Header

from multi_robot_exploration.mr3_reward import RewardLedger, RewardWeights
from multi_robot_exploration.mr3_information import map_digest
from multi_robot_exploration.mr3_task_contract import (
    compare_contract_occupancy_grid, sample_contract_occupancy_grid,
)
from multi_robot_exploration.task_evaluator import TaskEvaluator


def mask(*indices):
    result = np.zeros((2, 5), dtype=bool)
    result.ravel()[list(indices)] = True
    return result


def ledger(initial=None):
    return RewardLedger("epoch", 10., np.ones((2, 5), bool),
                        mask() if initial is None else initial)


def advance(book, sequence=1, start=10., end=11., current=None, **kwargs):
    return book.advance(
        epoch="epoch", sequence=sequence, step_start=start, step_end=end,
        current_correct_free_mask=mask() if current is None else current,
        collision_events=kwargs.pop("collision_events", 0),
        goal_switches=kwargs.pop("goal_switches", 0),
        rejected_actions=kwargs.pop("rejected_actions", 0), **kwargs,
    )


def test_startup_known_map_is_not_rewarded_and_input_masks_are_detached():
    initial = mask(0, 1)
    book = ledger(initial)
    initial[:] = False
    result = advance(book, current=mask(0, 1, 2))
    assert result["initial_correct_free_cells"] == 2
    assert result["new_correct_free_cells"] == 1
    assert result["reward_terms"]["coverage"] == 1.


def test_repeated_upload_regression_loop_closure_and_new_regions_cannot_farm_reward():
    book = ledger()
    snapshots = (mask(0, 1), mask(0, 1), mask(), mask(2, 3), mask(0, 1), mask(2, 3))
    results = [advance(book, index + 1, 10. + index, 11. + index, current)
               for index, current in enumerate(snapshots)]
    assert [result["new_correct_free_cells"] for result in results] == [2, 0, 0, 2, 0, 0]
    assert sum(result["reward_terms"]["coverage"] for result in results) == 4.
    assert results[-1]["current_correct_free_cells"] == 2
    assert results[-1]["rewarded_correct_free_cells"] == 4


def test_duplicate_sequence_is_detached_idempotent_and_conflicts_do_not_advance():
    book = ledger()
    first = advance(book, current=mask(1))
    first["reward_terms"]["coverage"] = 999.
    duplicate = advance(book, current=mask(1))
    assert duplicate["reward_terms"]["coverage"] == 1.
    with pytest.raises(ValueError, match="conflicting"):
        advance(book, current=mask(2))
    assert advance(book, 2, 11., 12., mask(2))["new_correct_free_cells"] == 1


@pytest.mark.parametrize("edit", [
    {"epoch": "old-epoch"}, {"sequence": 2}, {"step_start": 9.},
    {"step_end": 9.}, {"collision_events": -1}, {"rejected_actions": True},
])
def test_invalid_sequence_time_epoch_or_counters_leave_ledger_unchanged(edit):
    book = ledger()
    fields = dict(epoch="epoch", sequence=1, step_start=10., step_end=11.,
                  current_correct_free_mask=mask(), collision_events=0,
                  goal_switches=0, rejected_actions=0)
    fields.update(edit)
    with pytest.raises(ValueError):
        book.advance(**fields)
    assert book.last_sequence == 0 and not book.sealed


def test_finite_task_deadline_is_termination_and_precedes_success_or_external_cut():
    result = advance(ledger(), end=310., current=np.ones((2, 5), bool),
                     terminal_reason="coverage_reached", external_truncation="sampler_cut")
    assert result["terminated"] and not result["truncated"]
    assert result["reason"] == "timeout"
    assert result["reward_terms"]["failure"] == -20.
    assert result["reward_terms"]["success"] == 0.
    assert result["remaining_sim_time"] == 0.


def test_external_cut_is_truncation_and_seals_without_task_failure_penalty():
    book = ledger()
    result = advance(book, end=10.4, external_truncation="collector_budget")
    assert result["truncated"] and not result["terminated"]
    assert result["reward_terms"]["failure"] == 0.
    assert result["delta_sim_time"] == pytest.approx(.4)
    assert result["reward_terms"]["time"] == pytest.approx(-.4 / 300.)
    with pytest.raises(ValueError, match="already terminal or truncated"):
        advance(book, 2, 10.4, 11.4)
    assert advance(book, end=10.4, external_truncation="collector_budget") == result


def test_success_only_pays_once_and_last_short_step_uses_actual_dt():
    book = ledger()
    result = advance(book, end=10.02, terminal_reason="coverage_reached")
    assert result["terminated"] and not result["truncated"]
    assert result["reward_terms"]["success"] == 10.
    assert result["reward_terms"]["time"] == pytest.approx(-.02 / 300.)
    assert advance(book, end=10.02, terminal_reason="coverage_reached") == result


def test_contact_and_task_failure_both_penalize_and_cannot_be_paid_by_coverage():
    contact = advance(ledger(), current=np.ones((2, 5), bool), collision_events=1)
    timeout = advance(ledger(), end=310.)
    assert contact["reward_terms"]["collision"] == -20.
    assert contact["reward_terms"]["failure"] == -20.
    assert contact["reward"] < timeout["reward"] < 0.
    with pytest.raises(ValueError, match="cannot be classified"):
        advance(ledger(), collision_events=1, terminal_reason="coverage_reached")


def test_whole_episode_coverage_reward_is_bounded_despite_flips():
    book = ledger()
    total = 0.
    for index in range(100):
        result = advance(book, index + 1, 10. + index, 11. + index, mask(index % 10))
        total += result["reward_terms"]["coverage"]
    assert total == 10. and book.rewarded_correct_count == 10


def test_invalid_and_switch_penalties_use_monotone_actual_cumulative_counters():
    book = ledger()
    first = advance(book, goal_switches=2, rejected_actions=3)
    assert first["reward_terms"]["switch"] == -.02
    assert first["reward_terms"]["invalid"] == pytest.approx(-.15)
    second = advance(book, 2, 11., 12., goal_switches=2, rejected_actions=3)
    assert second["reward_terms"]["switch"] == second["reward_terms"]["invalid"] == 0.
    with pytest.raises(ValueError, match="counters regressed"):
        advance(book, 3, 12., 13.)


def test_infrastructure_crash_is_not_invented_as_a_normal_task_terminal():
    with pytest.raises(ValueError, match="infrastructure is a worker exception"):
        advance(ledger(), terminal_reason="worker_crash")


def test_truth_or_outside_roi_cannot_be_marked_correct_free():
    free = np.ones((2, 5), bool)
    free[0, 0] = False
    book = RewardLedger("epoch", 10., free, mask())
    with pytest.raises(ValueError, match="occupied or outside"):
        advance(book, current=mask(0))


def test_reward_weights_prevent_coverage_cancelling_failure_or_profitable_collision():
    with pytest.raises(ValueError, match="failure penalty"):
        RewardWeights(failure=10.)
    with pytest.raises(ValueError, match="contact penalty"):
        RewardWeights(collision=11.)


def test_extracted_sampling_preserves_contract_metrics_with_rotated_fractional_map():
    truth = SimpleNamespace(occupied=np.array([[False, True], [False, False]]),
                            roi_mask=np.ones((2, 2), bool), origin_x=-.025,
                            origin_y=.025, resolution=.05)
    data = np.array([-1, 100, 0, 0, 0, 100, -1, 0, 100], dtype=np.int8)
    sampled = sample_contract_occupancy_grid(truth, data, 3, 3, .05, (-.05, -.05), np.pi / 2)
    metrics = compare_contract_occupancy_grid(truth, data, 3, 3, .05, (-.05, -.05), np.pi / 2)
    correct_free = (sampled >= 0) & (sampled < 50) & ~truth.occupied
    assert metrics["correct_free_cell_count"] == int(correct_free.sum())
    assert metrics["false_free_cell_count"] == int(((sampled >= 0) & (sampled < 50)
                                                   & truth.occupied).sum())
    assert metrics["truth_free_cell_count"] == 3


def reward_evaluator():
    clock, responses = [11.], []
    metrics = {"correct_free_coverage_ratio": .5, "known_coverage_ratio": .6,
               "observed_accuracy": .97, "occupied_iou": .3, "false_free_ratio": .01}
    node = SimpleNamespace(
        episode_id="epoch", start_sim_time=10., finalized=False, final_result=None,
        reward_ledger=ledger(), reward_requests={}, pending_reward_requests={},
        reward_reset_bound=True, reward_map_cache=deque(maxlen=8),
        reward_events=[], reward_switch_goal_ids=set(), training_external_cut=None,
        training_acknowledged=False, training_ack_deadline_wall=None,
        training_ack_wall_guard_sec=90., training_reward_enabled=True,
        navigation_protocol_closed=False, pending_training_finalize=None,
        latest_map=None, latest_map_received_sim_time=None, map_message_count=0,
        contact_monitor=SimpleNamespace(summary=lambda end: {"event_count": 0}),
        task_contract=SimpleNamespace(data={
            "quality": {"min_observed_accuracy": .95, "min_occupied_iou": .2,
                        "max_false_free_ratio": .02},
            "participation": {"min_path_length_m": 1., "min_goal_count": 1},
        }),
        path_lengths={name: 2. for name in ("tb1", "tb2", "tb3")},
        goal_ids={name: {name} for name in ("tb1", "tb2", "tb3")},
        _now=lambda: clock[0], _timer_callback=lambda: None,
        _map_metrics=lambda: metrics, _reward_correct_free_mask=lambda: mask(0, 1),
        reward_response_publisher=SimpleNamespace(publish=lambda message: responses.append(
            json.loads(message.data))),
        reward_ready_publisher=SimpleNamespace(publish=lambda message: None),
        get_logger=lambda: SimpleNamespace(error=lambda message: None),
    )
    for name in ("_publish_reward_response", "_reward_request_callback", "_reward_event_callback",
                 "_reward_map_watermark", "_reward_expected_record", "_queue_reward_request",
                 "_drain_reward_requests",
                 "_training_finalize_callback", "training_exit_ready"):
        setattr(node, name, MethodType(getattr(TaskEvaluator, name), node))

    def finalize(reason):
        node.finalized = True
        node.final_result = {"termination_reason": reason, "end_sim_time_sec": clock[0],
                             "collision_events": 0}
    node.finalize = finalize
    return node, clock, responses


def request(node, **changes):
    payload = dict(epoch="epoch", sequence=1, step_start=10., step_end=11.)
    payload.update(changes)
    node._reward_request_callback(String(data=json.dumps(payload)))


def test_rpc_repeated_request_returns_frozen_response_without_later_map_recomputation():
    node, _, responses = reward_evaluator()
    request(node)
    first = copy.deepcopy(responses[-1])
    node._reward_correct_free_mask = lambda: np.ones((2, 5), bool)
    request(node)
    assert responses[-1] == first
    request(node, external_truncation=True)
    assert responses[-1]["error"] == "reward_sequence_conflict"
    assert all(not isinstance(value, np.ndarray) for value in first.values())
    assert "truth_free_cell_count" in first and "grid" not in json.dumps(first)


def test_rpc_uses_actual_protocol_switch_reject_events_and_rejects_learner_counters():
    node, _, responses = reward_evaluator()
    for event in (
        dict(epoch="epoch", stamp=10.2, kind="protocol",
             payload=dict(type="cancel_goal", reason="switch", goal_id="first")),
        dict(epoch="epoch", stamp=10.3, kind="action_rejected", payload={}),
        dict(epoch="epoch", stamp=12., kind="action_rejected", payload={}),
        dict(epoch="old", stamp=10.3, kind="action_rejected", payload={}),
    ):
        node._reward_event_callback(String(data=json.dumps(event)))
    request(node, rejected_actions=0)
    assert responses[-1]["error"] == "invalid_reward_request_fields"
    request(node)
    assert responses[-1]["goal_switches_delta"] == 1
    assert responses[-1]["rejected_actions_delta"] == 1


def test_rpc_future_request_waits_for_local_clock_watermark():
    node, clock, responses = reward_evaluator()
    clock[0] = 10.98
    request(node)
    assert not responses and 1 in node.pending_reward_requests
    clock[0] = 11.
    node._drain_reward_requests()
    assert responses[-1]["effective_step_end"] == 11.
    assert not node.pending_reward_requests


def test_rpc_partial_terminal_step_is_clipped_to_original_evaluator_end():
    node, clock, responses = reward_evaluator()
    node.finalized = True
    node.final_result = dict(end_sim_time_sec=10.4, termination_reason="coverage_reached",
                             collision_events=0)
    clock[0] = 10.4
    request(node)
    result = responses[-1]
    assert result["terminated"] and result["effective_step_end"] == 10.4
    assert result["delta_sim_time"] == pytest.approx(.4)
    assert not node.training_exit_ready()
    node._training_finalize_callback(String(data=json.dumps(
        dict(epoch="epoch", ack_sequence=1, reason="task_terminal"))))
    assert node.training_exit_ready()


def test_external_cut_waits_for_navigation_closure_before_diagnostic_finalize():
    node, _, responses = reward_evaluator()
    request(node, external_truncation="collector_budget")
    assert responses[-1]["truncated"] and not node.finalized
    finish = String(data=json.dumps(dict(epoch="epoch", ack_sequence=1,
                                         reason="external_truncation")))
    node._training_finalize_callback(finish)
    assert not node.finalized and node.pending_training_finalize is not None
    node.navigation_protocol_closed = True
    node._training_finalize_callback(finish)
    assert node.final_result["termination_reason"] == "training_external_truncation"
    assert node.training_acknowledged


def test_training_ack_wall_guard_is_separate_and_works_while_clock_is_paused():
    node, _, _ = reward_evaluator()
    node.training_ack_deadline_wall = 0.
    with pytest.raises(RuntimeError, match="wall guard"):
        node.training_exit_ready()


def cached_map(node, free_cells, received=10.):
    grid = OccupancyGrid()
    grid.header.frame_id = "map"
    grid.header.stamp.sec = int(received)
    grid.info.width, grid.info.height, grid.info.resolution = 5, 2, 1.
    grid.info.origin.orientation.w = 1.
    data = np.full(10, -1, dtype=np.int8)
    data[list(free_cells)] = 0
    grid.data = data.tolist()
    node.latest_map = grid
    node.map_message_count += 1
    node.latest_map_received_sim_time = received
    node.reward_map_cache.append({
        "message": grid, "received_stamp": received,
        "received_sequence": node.map_message_count, "payload_sha256": map_digest(grid),
    })
    return map_digest(grid)


def test_reset_sequence_zero_binds_exact_first_actor_map_without_startup_reward():
    node, clock, responses = reward_evaluator()
    node.reward_reset_bound = False
    node.truth = SimpleNamespace(occupied=np.zeros((2, 5), bool), roi_mask=np.ones((2, 5), bool),
                                 origin_x=0., origin_y=0., resolution=1.)
    node._reward_correct_free_mask = MethodType(TaskEvaluator._reward_correct_free_mask, node)
    first_digest = cached_map(node, [0, 1, 2], received=10.)
    clock[0] = 10.
    request(node, sequence=0, step_end=10., expected_map_sha256=first_digest)
    reset = copy.deepcopy(responses[-1])
    assert reset["reward"] == 0. and reset["reset_bound"]
    assert reset["initial_correct_free_cells"] == 3
    request(node, sequence=0, step_end=10., expected_map_sha256=first_digest)
    assert responses[-1] == reset
    clock[0] = 11.
    request(node, expected_map_sha256=first_digest)
    assert responses[-1]["new_correct_free_cells"] == 0
    newer_digest = cached_map(node, [0, 1, 2, 3], received=11.)
    request(node, sequence=0, step_end=10., expected_map_sha256=newer_digest)
    assert responses[-1]["error"] == "reward_sequence_conflict"


def test_reset_binding_cannot_use_a_map_delivered_after_the_reset_watermark():
    node, _, responses = reward_evaluator()
    node.reward_reset_bound = False
    digest = cached_map(node, [0], received=10.02)
    request(node, sequence=0, step_end=10., expected_map_sha256=digest)
    assert responses[-1]["error"] == "reward_reset_map_is_from_the_future"
    assert not node.reward_reset_bound


def test_normal_step_cannot_use_old_map_hash_when_current_map_has_advanced():
    node, _, responses = reward_evaluator()
    old_digest = cached_map(node, [0], received=10.)
    cached_map(node, [0, 1], received=11.)
    request(node, expected_map_sha256=old_digest)
    assert responses[-1]["error"] == "reward_expected_map_is_older_than_current_map"
    assert node.reward_ledger.last_sequence == 0


def test_hash_pairing_waits_for_map_callback_and_wall_guard_cannot_be_refreshed():
    node, _, responses = reward_evaluator()
    digest = cached_map(node, [0], received=11.)
    record = node.reward_map_cache.pop()
    node.latest_map = None
    request(node, expected_map_sha256=digest)
    deadline = node.pending_reward_requests[1]["deadline_wall"]
    node._drain_reward_requests()
    assert node.pending_reward_requests[1]["deadline_wall"] == deadline
    node.latest_map = record["message"]
    node.reward_map_cache.append(record)
    node._drain_reward_requests()
    assert responses[-1]["expected_map_paired"]
    assert responses[-1]["map_watermark"]["payload_sha256"] == digest


def test_reward_map_wait_is_bounded_even_without_simulation_clock_progress():
    node, _, responses = reward_evaluator()
    request(node, expected_map_sha256="0" * 64)
    node.pending_reward_requests[1]["deadline_wall"] = 0.
    node.training_exit_ready()
    assert responses[-1]["error"] == "reward_map_or_clock_watermark_wall_timeout"
    assert not node.pending_reward_requests


def test_advance_requires_the_one_time_reset_binding():
    node, _, responses = reward_evaluator()
    node.reward_reset_bound = False
    request(node)
    assert responses[-1]["error"] == "reward_reset_not_bound"


def test_zero_time_is_only_legal_for_actual_terminal_or_external_cut():
    with pytest.raises(ValueError, match="must advance simulation time"):
        advance(ledger(), end=10.)
    assert advance(ledger(), end=10., external_truncation=True)["truncated"]


def test_release_creates_provisional_ledger_and_publishes_truth_free_ready_message():
    node, clock, _ = reward_evaluator()
    ready = []
    digest = cached_map(node, [0, 1], received=10.)
    node.start_sim_time = None
    node.contact_subscription_started_sim_time_sec = 9.
    node.task_ready_published = True
    node.positions = {name: (0., 0.) for name in ("tb1", "tb2", "tb3")}
    node._drain_contacts = lambda now: None
    node.contact_monitor.start = lambda now: None
    node._update_coverage_times = lambda: None
    node.task_contract.sha256 = "contract-sha"
    node.truth = SimpleNamespace(occupied=np.zeros((2, 5), bool), roi_mask=np.ones((2, 5), bool),
                                 world_sha256="world-sha")
    node.get_logger = lambda: SimpleNamespace(info=lambda text: None)
    node.reward_ready_publisher = SimpleNamespace(publish=lambda message: ready.append(
        json.loads(message.data)))
    clock[0] = 10.
    message = Header(frame_id="map")
    message.stamp.sec = 10
    TaskEvaluator._release_callback(node, message)
    assert node.reward_ledger.last_sequence == 0
    assert ready[-1]["initial_map_payload_sha256"] == digest
    assert ready[-1]["epoch"] == "epoch" and not ready[-1]["reset_bound"]
    assert "grid" not in json.dumps(ready[-1])


def test_training_evaluator_constructs_with_real_ros_parameters_without_simulator():
    source = Path(__file__).resolve().parents[2] / "multi_robot"
    args = ["--ros-args", "-p", "training_reward_enabled:=true", "-p",
            "world_file:=" + str(source / "worlds/p1c_open.world"), "-p",
            "task_contract_path:=" + str(source / "config/mr3_p1a/open.json")]
    rclpy.init(args=args)
    node = None
    try:
        node = TaskEvaluator()
        assert node.training_reward_enabled and node.reward_ledger is None
        assert not node.reward_reset_bound and not node.training_exit_ready()
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.shutdown()


def test_terminal_reward_uses_frozen_evaluation_map_without_eating_later_actor_map():
    node, clock, responses = reward_evaluator()
    frozen_digest = cached_map(node, [0], received=10.4)
    frozen = node.latest_map
    actor_later = copy.deepcopy(frozen)
    actor_later.data = [0] * 10
    actor_digest = map_digest(actor_later)
    assert actor_digest != frozen_digest
    node.truth = SimpleNamespace(occupied=np.zeros((2, 5), bool), roi_mask=np.ones((2, 5), bool),
                                 origin_x=0., origin_y=0., resolution=1.)
    node._reward_correct_free_mask = MethodType(TaskEvaluator._reward_correct_free_mask, node)
    node.finalized = True
    node.final_result = dict(end_sim_time_sec=10.4, termination_reason="coverage_reached",
                             collision_events=0)
    clock[0] = 10.42
    request(node, expected_map_sha256=actor_digest)
    terminal = responses[-1]
    assert terminal["terminated"] and not terminal["truncated"]
    assert terminal["effective_step_end"] == 10.4
    assert terminal["new_correct_free_cells"] == 1
    assert terminal["map_watermark"]["payload_sha256"] == frozen_digest
    assert terminal["expected_actor_map_sha256"] == actor_digest
    assert not terminal["expected_map_paired"]
    assert terminal["map_pairing_scope"] == "terminal_evaluator_frozen_before_drain"
