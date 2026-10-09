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
