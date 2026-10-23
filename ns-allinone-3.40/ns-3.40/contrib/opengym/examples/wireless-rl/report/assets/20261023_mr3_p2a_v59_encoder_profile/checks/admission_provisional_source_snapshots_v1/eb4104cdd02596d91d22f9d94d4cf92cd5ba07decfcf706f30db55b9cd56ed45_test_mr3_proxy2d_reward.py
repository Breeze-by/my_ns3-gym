"""Synthetic private-evaluator fixtures; no replay, episode, policy or native."""

import copy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import mr3_proxy2d_reward as module
from multi_robot_exploration.mr3_reward import RewardLedger


ROBOTS = ("tb1", "tb2", "tb3")


def evaluator(monkeypatch, *, initial=None, start=10.):
    occupied = np.zeros((4, 4), dtype=bool)
    occupied[-1, :] = True
    truth = SimpleNamespace(occupied=occupied, roi_mask=np.ones((4, 4), dtype=bool),
                            origin_x=0., origin_y=0., resolution=1.)
    contract = SimpleNamespace(data={"coverage_threshold": .95,
        "quality": {"min_observed_accuracy": .95, "min_occupied_iou": .2,
                    "max_false_free_ratio": .02},
        "participation": {"min_path_length_m": 1., "min_goal_count": 1}})
    captured = []
    def load(path, world):
        captured.append((path, world))
        return contract
    monkeypatch.setattr(module, "load_task_contract", load)
    monkeypatch.setattr(module, "load_contract_truth", lambda world, selected: truth)
    value = module.ProxyReward("open", "proxy-fixture")
    initial = np.full((4, 4), -1, dtype=np.int16) if initial is None else initial
    reset = value.initialize(initial, 1., (0., 0.), start)
    return value, truth, reset, captured


def perfect(truth):
    return np.where(truth.occupied, 100, 0).astype(np.int16)


def physical(path=1., contacts=0):
    # Extra world-private fields must not leave the evaluator response.
    return {"path_lengths": {name: path for name in ROBOTS}, "collision_events": contacts,
            "truth": "explicit private fixture", "poses": {name: {"x": 42.} for name in ROBOTS}}


def arguments(sequence=1, start=10., end=11., *, path=1., contacts=0, closed=True):
    return {"sequence": sequence, "step_start": start, "step_end": end,
            "physical_state": physical(path, contacts), "goal_counts": {name: 1 for name in ROBOTS},
            "navigation_closed": closed, "goal_switches": 0, "rejected_actions": 0}


def test_initial_actual_snapshot_seeds_seq0_without_reward_and_uses_current_source_paths(monkeypatch):
    initial = np.full((4, 4), -1, dtype=np.int16)
    initial[0, 0] = 0
    value, truth, reset, captured = evaluator(monkeypatch, initial=initial)
    assert reset["sequence"] == 0 and reset["reward"] == 0.
    assert reset["initial_correct_free_cells"] == 1
    assert not reset["proxy_task_success"] and not reset["terminated"]
    assert str(captured[0][0]).endswith("src/multi_robot/config/mr3_p1a/open.json")
    assert str(captured[0][1]).endswith("src/multi_robot/worlds/p1c_open.world")
    result = value.advance(initial, 1., (0., 0.), **arguments(path=0., closed=False))
    assert result["new_correct_free_cells"] == 0
    assert result["reward_terms"]["coverage"] == 0.
    with pytest.raises(ValueError, match="already bound"):
        value.initialize(initial, 1., (0., 0.), 10.)


def test_reward_scalar_values_are_the_original_ledger_not_a_proxy_formula(monkeypatch):
    value, truth, _, _ = evaluator(monkeypatch)
    expected = RewardLedger("proxy-fixture", 10., ~truth.occupied,
                            np.zeros_like(truth.occupied))
    observed = np.full((4, 4), -1, dtype=np.int16)
    observed[0, :2] = 0
    params = arguments(path=0., closed=False)
    params.update(goal_switches=1, rejected_actions=1)
    actual = value.advance(observed, 1., (0., 0.), **params)
    mask = np.zeros((4, 4), dtype=bool)
    mask[0, :2] = True
    original = expected.advance(epoch="proxy-fixture", sequence=1, step_start=10., step_end=11.,
        current_correct_free_mask=mask, collision_events=0, goal_switches=1, rejected_actions=1)
    assert {key: actual[key] for key in original} == original
    empty = np.full((4, 4), -1, dtype=np.int16)
    next_params = arguments(2, 11., 12., path=0., closed=False)
    next_params.update(goal_switches=1, rejected_actions=1)
    regressed = value.advance(empty, 1., (0., 0.), **next_params)
    assert regressed["new_correct_free_cells"] == 0
    replay_params = arguments(3, 12., 13., path=0., closed=False)
    replay_params.update(goal_switches=1, rejected_actions=1)
    restored = value.advance(observed, 1., (0., 0.), **replay_params)
    assert restored["new_correct_free_cells"] == 0


def test_coverage_candidate_requires_quality_participation_and_no_proxy_contact(monkeypatch):
    value, truth, _, _ = evaluator(monkeypatch)
    known = perfect(truth)
    for fault in ("quality", "path", "goals", "contact"):
        image, state, goals = known.copy(), physical(), {name: 1 for name in ROBOTS}
        if fault == "quality": image[:] = 0
        elif fault == "path": state["path_lengths"]["tb3"] = .999
        elif fault == "goals": goals["tb3"] = 0
        else: state["collision_events"] = 1
        result = value.inspect(image, 1., (0., 0.), physical_state=state, goal_counts=goals)
        assert not result["coverage_candidate"], fault
    candidate = value.inspect(known, 1., (0., 0.), physical_state=physical(),
                              goal_counts={name: 1 for name in ROBOTS})
    assert candidate["coverage_candidate"]
    assert not candidate["proxy_success_gates_closed"]
    assert not candidate["metrics"]["navigation_protocol_closed"]
    assert value._ledger.last_sequence == 0


def test_coverage_success_waits_for_actual_proxy_navigation_closure(monkeypatch):
    value, truth, _, _ = evaluator(monkeypatch)
    image = perfect(truth)
    first = value.advance(image, 1., (0., 0.), **arguments(closed=False))
    assert not first["terminated"] and not first["proxy_task_success"]
    second = value.advance(image, 1., (0., 0.), **arguments(2, 11., 12.))
    assert second["terminated"] and second["reason"] == "coverage_reached"
    assert second["proxy_task_success"]
    assert second["reward_terms"]["success"] == 10.
    assert not second["native_task_success"] and not second["native_qualification"]
    assert all(gate is None for gate in second["native_gates_unprovided"].values())


def test_explicit_false_coverage_claim_rejects_before_reward_advances(monkeypatch):
    value, truth, _, _ = evaluator(monkeypatch)
    with pytest.raises(ValueError, match="lacks unchanged task gates"):
        value.advance(perfect(truth), 1., (0., 0.), **arguments(path=0.),
                      terminal_reason="coverage_reached")
    assert value._ledger.last_sequence == 0


def test_lightweight_checks_do_not_advance_ledger_and_deadline_wins(monkeypatch):
    value, truth, _, _ = evaluator(monkeypatch)
    assert value.check(physical(), 10.02)["terminal_reason"] is None
    assert value.check(physical(contacts=1), 10.02)["terminal_reason"] == "collision"
    assert value.check(physical(contacts=1), 10.02, navigation_failed=True)["terminal_reason"] == "navigation_failure"
    assert value.check(physical(contacts=1), 310., navigation_failed=True)["terminal_reason"] == "timeout"
    assert value._ledger.last_sequence == 0
    final = value.advance(perfect(truth), 1., (0., 0.), **arguments(end=310.),
                          terminal_reason="coverage_reached", external_truncation="sampler_limit")
    assert final["terminated"] and not final["truncated"]
    assert final["reason"] == "timeout" and not final["proxy_task_success"]
    assert final["reward_terms"]["success"] == 0.


def test_proxy_contact_and_external_cut_keep_original_failure_and_truncation_rules(monkeypatch):
    value, truth, _, _ = evaluator(monkeypatch)
    image = perfect(truth)
    failure = value.advance(image, 1., (0., 0.), **arguments(contacts=1))
    assert failure["terminated"] and failure["reason"] == "collision"
    assert not failure["proxy_task_success"]
    assert failure["reward_terms"]["collision"] == -20.
    assert failure["reward_terms"]["failure"] == -20.
    value, truth, _, _ = evaluator(monkeypatch)
    cut = value.advance(np.full((4, 4), -1, dtype=np.int16), 1., (0., 0.),
                        **arguments(path=0., closed=False), external_truncation="external_sampler_limit")
    assert cut["truncated"] and not cut["terminated"]
    assert cut["reason"] == "external_sampler_limit"


def test_duplicate_gate_inputs_are_bound_and_responses_contain_no_private_truth(monkeypatch):
    value, truth, _, _ = evaluator(monkeypatch)
    image = np.full((4, 4), -1, dtype=np.int16)
    params = arguments(path=0., closed=False)
    first = value.advance(image, 1., (0., 0.), **params)
    assert value.advance(image, 1., (0., 0.), **params) == first
    changed = copy.deepcopy(params)
    changed["physical_state"]["path_lengths"]["tb1"] = .5
    with pytest.raises(ValueError, match="conflicting gate"):
        value.advance(image, 1., (0., 0.), **changed)
    payload = json.dumps(first, allow_nan=False)
    assert "explicit private fixture" not in payload and "poses" not in payload
    assert "occupied\"" not in payload and "roi_mask" not in payload
    first["metrics"]["correct_free_coverage_ratio"] = 999.
    assert value.advance(image, 1., (0., 0.), **params)["metrics"]["correct_free_coverage_ratio"] == 0.


def test_invalid_counter_and_regressed_participation_do_not_mutate_ledger(monkeypatch):
    value, truth, _, _ = evaluator(monkeypatch)
    image = np.full((4, 4), -1, dtype=np.int16)
    value.advance(image, 1., (0., 0.), **arguments(path=.5, closed=False))
    for fault in ("path", "goals", "nan", "contact_type", "closure_type"):
        params = arguments(2, 11., 12., path=.5, closed=False)
        if fault == "path": params["physical_state"]["path_lengths"]["tb1"] = .4
        elif fault == "goals": params["goal_counts"]["tb1"] = 0
        elif fault == "nan": params["physical_state"]["path_lengths"]["tb1"] = float("nan")
        elif fault == "contact_type": params["physical_state"]["collision_events"] = True
        else: params["navigation_closed"] = "true"
        with pytest.raises(ValueError):
            value.advance(image, 1., (0., 0.), **params)
        assert value._ledger.last_sequence == 1


def test_unknown_scene_and_missing_seq0_are_rejected(monkeypatch):
    with pytest.raises(ValueError, match="three accepted"):
        module.ProxyReward("unseen", "proxy-fixture")
    value, truth, _, _ = evaluator(monkeypatch)
    value._ledger = None  # Explicit uninitialized fixture; not a reset API.
    with pytest.raises(ValueError, match="initialization"):
        value.advance(perfect(truth), 1., (0., 0.), **arguments())
