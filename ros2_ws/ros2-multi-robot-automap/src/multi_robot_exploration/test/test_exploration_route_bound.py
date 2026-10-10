import dataclasses
import hashlib
import json
import math
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import control
from test_exploration_resume import conditional_snapshot_node
from outbound_reference import with_local_route_inputs


REFERENCE = json.loads((Path(__file__).parent / 'fixtures/p2c_v35_route_pricing_reference.json').read_text())


def reference_functions():
    namespace = dict(vars(control))
    for name, source in REFERENCE['functions'].items():
        assert hashlib.sha256(source.encode()).hexdigest() == REFERENCE['function_sha256'][name]
        exec(compile(with_local_route_inputs(source), '<7d9709b reference with local route input>', 'exec'), namespace)
    # The old candidate optimizer now receives the shared corrected planner;
    # its frozen route-admission bounds remain the comparison under test.
    namespace['plan_rally_leg'] = control.plan_rally_leg
    return namespace


def conditional_assignment(event, assign):
    d = event['diagnostic_inputs']
    e = dict(d, inputs=event['inputs_at_start'], event_time=event['planning_started_at_sec'])
    node, sent = conditional_snapshot_node(e, d['exploration_resume_intents'].copy())
    node.robot_states = d['robot_states'].copy()
    node.battery_modes = d['battery_modes'].copy()
    node.active_exclusions = lambda: d['exclusions']
    node.enable_rally = d['enable_rally']
    node.initial_search_next = d['initial_search_next'].copy()
    node.initial_search_visits = dict(enumerate(d['initial_search_visits']))
    node.initial_search_views = dict(enumerate(d['initial_search_views']))
    node.target_search_visits = d['target_search_visits'].copy()
    # Test the frozen route optimizer outside the separately tested camera-first
    # qualification; retain its original history, headings and gain candidates.
    node.successful_exploration_legs = dict.fromkeys(d['successful_exploration_legs'], 0)
    node.rally_charge_requested = d['rally_charge_requested'].copy()
    node.goal_routes = d['goal_routes'].copy()
    node.goal_targets = {n: None if a is None else control.Assignment(
        **{**a, 'viewpoint': control.Viewpoint(**a['viewpoint'])}) for n, a in d['goal_targets'].items()}
    # Isolate route/gain ordering on the saved geometry. These synthetic
    # endpoints omit native charging callbacks; the charge-reservation policy
    # has its own complete fixture and actual DDS/Future regression probe.
    with patch.object(control.HeadquartersControl, 'request_exploration_charge', return_value=False):
        assign(node)
    for choice in node.exploration_travel_choices.values():
        assert choice.get('camera_first_search') is None
        choice.pop('camera_first_search', None)
    return json.loads(json.dumps(dict(sent=sent, choices=node.exploration_travel_choices),
                                default=dataclasses.asdict))


@pytest.mark.parametrize('case', sorted(REFERENCE['snapshots']))
def test_unchanged_goals_headings_and_full_energy_on_actual_expired_inputs(case):
    event = REFERENCE['snapshots'][case]
    expected = conditional_assignment(event, reference_functions()['assign_idle_robots'])
    actual = conditional_assignment(event, control.HeadquartersControl.assign_idle_robots)
    assert expected['sent'] and actual == expected


def test_reserved_common_start_avoids_replanning_every_rooms_candidate(monkeypatch):
    calls = []
    original = control.plan_rally_leg
    def plan(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(control, 'plan_rally_leg', plan)
    result = conditional_assignment(REFERENCE['snapshots']['dev_rooms202'],
                                    control.HeadquartersControl.assign_idle_robots)
    assert result['sent'] and len(calls) < 30


def useful(plan, position, reservations):
    admitted = control.reserve_rally_prefix(plan, reservations)
    return admitted is not None and math.dist(position, (admitted[0].x, admitted[0].y)) > control.NAVIGATION_POSITION_TOLERANCE_M


@pytest.mark.parametrize('seed', range(12))
def test_false_bound_cannot_hide_useful_prefix_after_more_reservations(seed):
    rng = np.random.default_rng(seed)
    for _ in range(40):
        position = tuple(rng.uniform(-.4, .4, 2))
        route = tuple(map(tuple, np.cumsum(rng.uniform(-.25, .25, (20, 2)), axis=0)))
        plan = (control.RallyPose(*route[-1], 0.), route)
        reservations = [tuple(map(tuple, rng.uniform(-1, 1, (3, 2)))) for _ in range(rng.integers(0, 3))]
        if control.exploration_prefix_can_move(plan, position, reservations):
            continue
        assert not useful(plan, position, reservations)
        for point in route:
            assert not useful(plan, position, [*reservations, (point,)])


def test_loop_ending_at_start_keeps_a_possible_useful_intermediate_prefix():
    route = ((0., 0.), (1., 0.), (2., 0.), (4., 4.), (1., .5), (0., 0.))
    plan = control.RallyPose(0., 0., 0.), route
    assert not useful(plan, (0., 0.), [])
    assert control.exploration_prefix_can_move(plan, (0., 0.), [])
    assert useful(plan, (0., 0.), [(route[3],)])


@pytest.mark.parametrize('plan', [(None, ()), (control.RallyPose(.01, 0., 0.), ((0., 0.), (.01, 0.)))])
def test_missing_or_short_stationary_route_has_no_useful_prefix(plan):
    assert not control.exploration_prefix_can_move(plan, (0., 0.), [])


@pytest.mark.parametrize('seed', range(8))
def test_cached_visibility_preserves_exact_paths_and_body_escape(seed):
    rng = np.random.default_rng(seed)
    raw = np.zeros((72, 72), dtype=np.int16)
    raw[rng.random(raw.shape) < .045] = 100
    raw[30:42, 30:42] = 0
    resolution, origin, position = .1, (-3.6, -3.6), (0., 0.)
    blocked = [(.8, .3), (-1., .5)]
    old, new = {}, {}
    reference = reference_functions()['plan_rally_leg']
    for xy in rng.uniform(-3, 3, (24, 2)):
        pose = control.RallyPose(*xy, .6)
        arguments = (pose, raw, resolution, origin, position, 2.)
        kwargs = dict(blocked_positions=blocked, clearance_m=.35, visible_only=True)
        assert control.plan_rally_leg(*arguments, route_cache=new, **kwargs) == reference(*arguments, route_cache=old, **kwargs)
    assert len(new.get('visibility', {})) <= 2048
    assert all(isinstance(value, bool) for value in new.get('visibility', {}).values())


def test_visibility_memo_is_bounded_and_does_not_store_routes():
    raw = np.zeros((80, 80), dtype=np.int16)
    cache = {'field': (np.ones(raw.shape, dtype=bool), (40, 40), ((40, 40),),
                      control.path_distance_grid(np.ones(raw.shape, dtype=bool), (40, 40), True)),
             'visibility': {(i, -1): False for i in range(2048)}}
    pose, _ = control.plan_rally_leg(control.RallyPose(2., 0., 0.), raw, .1, (-4., -4.),
                                   (0., 0.), 2., visible_only=True, route_cache=cache)
    assert pose is not None and len(cache['visibility']) < 2048
    assert all(isinstance(value, bool) for value in cache['visibility'].values())
