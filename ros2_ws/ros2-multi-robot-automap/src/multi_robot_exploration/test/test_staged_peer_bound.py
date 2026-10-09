"""Private local-route proofs tighten sorting without authorizing navigation."""
import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_candidate_battery_bound import conditional_charge


REFERENCE = json.loads((Path(__file__).parent / 'fixtures/p2c_v39_staged_bound_reference.json').read_text())


def reference_assign():
    assert hashlib.sha256(REFERENCE['function'].encode()).hexdigest() == REFERENCE['function_sha256']
    namespace = dict(vars(c))
    exec(compile(REFERENCE['function'], '<10860f4 independent assign reference>', 'exec'), namespace)
    return namespace['assign_idle_robots']


@pytest.mark.parametrize('stage', sorted(REFERENCE['snapshots']))
def test_actual_abandoned_choices_headings_charge_intents_and_budgets_remain_equal(stage):
    event = REFERENCE['snapshots'][stage]
    expected = conditional_charge(event, reference_assign())
    assert expected['sent']
    assert conditional_charge(event, c.HeadquartersControl.assign_idle_robots) == expected


def state():
    return dict(mode='ACTIVE', energy=100., charge_x=.55, charge_y=.55,
                charge_radius_m=.8, move_cost_per_m=1., idle_cost_per_sec=.02,
                return_path_factor=2., nominal_speed_mps=.18,
                return_safety_margin=5., return_recovery_wait_sec=30.)


@pytest.mark.parametrize('seed', range(8))
def test_local_proof_covers_all_legal_ages_and_all_qualified_fused_shortcuts(seed):
    rng = np.random.default_rng(seed)
    grid = np.zeros((70, 90), dtype=np.int16)
    grid[25:45, 35] = 100
    local = dict(data=c.immutable_grid_snapshot(grid, grid.shape), resolution=.1, origin=(0., 0.))
    s = state()
    position, destination = (.55, 1.55), (rng.uniform(5., 7.), rng.uniform(1., 5.))
    approach = rng.uniform(6., 15.)
    assert c.local_peer_funded_for_lease(s, position, approach, destination, local, {})
    # An imperfect fused map may add unknowns or offer a shorter qualified
    # path; its minimum cannot exceed the already qualified local route.
    fused = grid.copy()
    fused[rng.random(grid.shape) < .02] = -1
    cache = {}
    distances = [min(r['path_distance_m'] for r in c.qualified_return_candidates(
        fused, .1, (0., 0.), point, (.55, .55), .8, local, cache) if r['qualified'])
        for point in (position, destination)]
    for map_age in (0., 1., 4.9, 5.):
        for pose_age in (0., .7, 1.9, 2.):
            model = (1., .02, 2., .18, 5., 30., map_age, pose_age)
            required = max(c.battery_assignment_required_energy(0., distances[0], *model),
                           c.battery_assignment_required_energy(approach, distances[1], *model))
            assert required < s['energy']


@pytest.mark.parametrize('override', [dict(mode='RETURNING'), dict(energy=math.inf),
    dict(energy=math.nan), dict(energy=0.), dict(move_cost_per_m=-1.),
    dict(idle_cost_per_sec=-1.), dict(nominal_speed_mps=0.), dict(return_path_factor=.5)])
def test_invalid_or_unfunded_metadata_cannot_supply_a_discount(override):
    grid = np.zeros((70, 90), dtype=np.int16)
    local = dict(data=grid, resolution=.1, origin=(0., 0.))
    assert not c.local_peer_funded_for_lease({**state(), **override}, (.55, 1.55),
                                           8., (6.55, 3.55), local, {})


def test_missing_local_route_is_inconclusive_even_when_fused_route_can_fund_peer():
    local = dict(data=np.full((70, 90), -1, dtype=np.int16), resolution=.1, origin=(0., 0.))
    fused = np.zeros((70, 90), dtype=np.int16)
    position, destination = (.55, 1.55), (6.55, 3.55)
    assert not c.local_peer_funded_for_lease(state(), position, 8., destination, local, {})
    assert any(r['qualified'] for r in c.qualified_return_candidates(
        fused, .1, (0., 0.), destination, (.55, .55), .8, local, {}))


def test_changed_writable_map_rebuilds_proof_geometry():
    grid = np.zeros((70, 90), dtype=np.int16)
    local = dict(data=grid, resolution=.1, origin=(0., 0.))
    cache = {}
    args = (state(), (.55, 1.55), 8., (6.55, 3.55), local, cache)
    assert c.local_peer_funded_for_lease(*args)
    grid[:, 35] = 100
    assert not c.local_peer_funded_for_lease(*args)


@pytest.mark.parametrize('seed', range(12))
def test_ordered_refinements_preserve_fully_priced_stable_sort_and_ties(seed):
    rng = np.random.default_rng(seed)
    scores = rng.integers(0, 8, size=60).tolist()
    rows = [(i, float(score)+12.) for i, score in enumerate(scores)]
    def first(row): return row[0], scores[row[0]]+5.
    def second(row): return row[0], scores[row[0]]+1.
    def evaluate(row): return row[0], float(scores[row[0]])
    actual = list(c.lazy_priority_candidates(rows, evaluate, lambda r: r[1],
                 lambda r: r[1], refine_bound=(first, second)))
    expected = sorted([(i, float(score)) for i, score in enumerate(scores)], key=lambda r: -r[1])
    assert actual == expected


def test_second_refinement_rejection_never_calls_price():
    calls = []
    actual = list(c.lazy_priority_candidates([9., 5.], lambda r: calls.append(r) or r,
        float, float, refine_bound=(lambda r: r, lambda r: None if r == 9. else r)))
    assert actual == [5.] and calls == [5.]


def test_each_refinement_must_obey_its_previous_bound():
    with pytest.raises(ValueError, match='refined candidate bound exceeds'):
        next(c.lazy_priority_candidates([9.], float, float, float,
             refine_bound=(lambda r: 5., lambda r: 6.)))


def test_source_expiring_inside_peer_proof_revokes_all_provisional_commands(monkeypatch):
    event = REFERENCE['snapshots']['candidate_budget']
    records = []
    def expire(node):
        current = [event['planning_started_at_sec']]
        node.now = lambda: current[0]
        node.consumed_publisher = SimpleNamespace(publish=lambda msg: records.append(json.loads(msg.data)))
        def proof(*args, **kwargs):
            current[0] = event['source_deadline_sec']+.01
            return True
        monkeypatch.setattr(c, 'local_peer_funded_for_lease', proof)
        c.HeadquartersControl.assign_idle_robots(node)
    actual = conditional_charge(event, expire)
    assert not actual['sent'] and not actual['requests']
    assert any(e['event']=='coordinator_planning_lease_expired'
               and e['stage']=='candidate_generation' for e in records)
