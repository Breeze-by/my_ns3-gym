"""Exact best-first admission with bounded scores and expensive price checks."""
import random

import pytest

from multi_robot_exploration.control import lazy_priority_candidates


@pytest.mark.parametrize('seed', range(12))
def test_lazy_order_equals_full_stable_sort_with_skipped_candidates(seed):
    rng = random.Random(seed)
    rows = [(i, rng.randrange(1, 20), rng.choice((0, .25, .5, 1)))
            for i in range(200)]
    calls = []
    def evaluate(row):
        calls.append(row[0])
        return None if row[2] == 0 else (row[0], row[1] * row[2])
    expected = [(i, bound * factor) for i, bound, factor in rows if factor]
    expected.sort(key=lambda row: -row[1])
    actual = list(lazy_priority_candidates(rows, evaluate,
                                          lambda row: row[1], lambda row: row[1]))
    assert actual == expected
    assert len(calls) == len(set(calls)) == len(rows)


def test_unused_low_priority_prices_are_never_computed():
    calls = []
    def evaluate(row):
        calls.append(row)
        return row
    stream = lazy_priority_candidates([10, 1, 9, 2], evaluate, float, float)
    assert next(stream) == 10
    assert calls == [10]
    assert next(stream) == 9
    assert calls == [10, 9]


def test_lowered_actual_score_requires_pricing_competing_upper_bound():
    calls = []
    def evaluate(row):
        calls.append(row)
        return row / 10 if row == 10 else row
    stream = lazy_priority_candidates([10, 5, 4], evaluate, float, float)
    assert next(stream) == 5
    assert calls == [10, 5]
    assert list(stream) == [4, 1]


@pytest.mark.parametrize('score', [11, float('inf'), float('nan')])
def test_invalid_priority_bound_fails_before_yield(score):
    with pytest.raises(ValueError):
        next(lazy_priority_candidates([10], lambda _: score, float, float))


@pytest.mark.parametrize('bound', [float('inf'), float('nan')])
def test_nonfinite_upper_bound_fails_before_pricing(bound):
    def evaluate(_):
        raise AssertionError('invalid bound must fail before pricing')
    with pytest.raises(ValueError):
        next(lazy_priority_candidates([10], evaluate, lambda _: bound, float))


def test_refined_gain_bound_is_requeued_before_expensive_budget_price():
    calls = []
    def evaluate(row):
        calls.append(row); return row
    stream = lazy_priority_candidates([100, 50, 20], evaluate, float, float,
        refine_bound=lambda row: 1 if row == 100 else row)
    assert next(stream) == 50 and calls == [50]
    assert list(stream) == [20, 1] and calls == [50, 20, 1]


@pytest.mark.parametrize('seed', range(12))
def test_two_stage_stable_order_matches_full_gain_and_budget_evaluation(seed):
    rng = random.Random(seed)
    rows = [(i, rng.randrange(1, 30), rng.choice((0, .25, 1)),
             rng.choice((0, .25, .5, 1))) for i in range(200)]
    def refine(row):
        i, bound, gain_factor, budget_factor = row
        return None if gain_factor == 0 else (i, bound * gain_factor, budget_factor)
    def evaluate(row):
        i, gain_bound, factor = row
        return None if factor == 0 else (i, gain_bound * factor)
    expected = [(i, bound * gain * budget) for i, bound, gain, budget in rows if gain and budget]
    expected.sort(key=lambda row: -row[1])
    assert list(lazy_priority_candidates(rows, evaluate, lambda row: row[1],
        lambda row: row[1], refine_bound=refine)) == expected


def test_invalid_refined_bound_fails_before_budget_price():
    def evaluate(_):
        raise AssertionError('invalid refined bound must fail before budget')
    with pytest.raises(ValueError):
        next(lazy_priority_candidates([10], evaluate, float, float,
                                      refine_bound=lambda _: 11))
