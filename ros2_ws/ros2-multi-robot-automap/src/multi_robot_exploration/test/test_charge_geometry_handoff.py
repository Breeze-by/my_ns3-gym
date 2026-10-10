"""Fresh source epochs must reprice a deferred low-energy point preference."""
import copy
import dataclasses
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import control as c
from p2c_charge_handoff import charge_geometry_handoff_audit
from test_exploration_resume import conditional_snapshot_node


FIXTURE = Path(__file__).parent/'fixtures/p2c_v69_charge_handoff_inputs.json.gz'
assert hashlib.sha256(FIXTURE.read_bytes()).hexdigest() == '5d0e1b6f13613b0706861b663293a0b31571b1c789188f917c6cc0b155ecc800'
with gzip.open(FIXTURE, 'rt') as stream:
    REFERENCE = json.load(stream)
ROOMS = next(row['event'] for row in REFERENCE['snapshots']
             if row['case'] == 'dev_rooms202' and row['event']['stage'] == 'candidate_budget')


def reference_assign():
    source = REFERENCE['original_assign']
    assert hashlib.sha256(source.encode()).hexdigest() == REFERENCE['original_assign_sha256']
    scope = dict(vars(c))
    exec(compile(source, '<939a77f frozen original assign>', 'exec'), scope)
    return scope['assign_idle_robots']


def snapshot_node(event):
    data = copy.deepcopy(event['diagnostic_inputs'])
    data.update(event_time=event['planning_started_at_sec'], inputs=copy.deepcopy(event['inputs_at_start']))
    node, sent = conditional_snapshot_node(data, copy.deepcopy(data['exploration_resume_intents']))
    node.robot_states = dict(data['robot_states'])
    node.enable_rally = data['enable_rally']
    node.initial_search_next = dict(data['initial_search_next'])
    node.successful_exploration_legs = dict(data['successful_exploration_legs'])
    node.initial_search_views = dict(enumerate(data['initial_search_views']))
    node.initial_search_visits = dict(enumerate(data['initial_search_visits']))
    node.target_search_visits = data['target_search_visits']
    node.rally_charge_requested = data['rally_charge_requested']
    node.goal_routes = data['goal_routes']
    node.goal_targets = {name: None if goal is None else c.Assignment(
        **{**goal, 'viewpoint': c.Viewpoint(**goal['viewpoint'])})
        for name, goal in data['goal_targets'].items()}
    node.active_exclusions = lambda: data['exclusions']
    node.goal_handles = {name: None for name in node.robot_states}
    node.exploration_charge_budgets = {}
    node.exploration_return_yields = {}
    requests, private = [], []
    node.charge_request_publishers = {name: SimpleNamespace(publish=lambda msg: requests.append(json.loads(msg.data)))
                                    for name in node.robot_states}
    node.consumed_publisher = SimpleNamespace(publish=lambda msg: private.append(json.loads(msg.data)))
    node.target_information_gain = lambda x, y: c.HeadquartersControl.target_information_gain(node, x, y)
    node.map_height, node.map_width = node.map_data.shape
    node.goal_initial_gain = dict.fromkeys(node.robot_states, 0)
    return node, sent, requests, private


def decision(node, sent):
    return json.dumps(dict(sent=[(name, dataclasses.asdict(a)) for name, a in sent],
        choices=node.exploration_travel_choices, charge=node.rally_charge_requested,
        pending=getattr(node, 'pending_exploration_return_yield', None)),
        sort_keys=True, default=dataclasses.asdict)


@pytest.mark.parametrize('index', range(len(REFERENCE['snapshots'])))
def test_uninterrupted_geometry_choices_after_first_charge_remain_unchanged(index):
    event = REFERENCE['snapshots'][index]['event']
    before, old_goals, _, _ = snapshot_node(event)
    after, new_goals, _, _ = snapshot_node(event)
    # The initial replenishment policy has its own frozen-budget comparison.
    # This conditional geometry regression deliberately excludes that policy.
    for node in (before, after):
        for state in node.battery_states.values():
            state['charge_count'] = max(1, state.get('charge_count', 0))
    reference_assign()(before)
    c.HeadquartersControl.assign_idle_robots(after)
    assert decision(before, old_goals) == decision(after, new_goals)


def hint(node):
    return dict(robot='tb2', point=(-4.912139965045528, -1.917408218455651),
        context=('EXPLORE', False, tuple(sorted(node.participating_robots())), None),
        generated_at=node.now()-.5)


def test_expired_original_sources_retain_only_geometry_and_send_no_charge_or_goal():
    node, sent, requests, private = snapshot_node(ROOMS)
    clock = [node.now()]
    node.now = lambda: clock[0]
    original = node.exploration_battery_factor
    def expire(*args):
        result = original(*args)
        clock[0] = ROOMS['source_deadline_sec']+.01
        return result
    node.exploration_battery_factor = expire
    c.HeadquartersControl.assign_idle_robots(node)
    preference = node.pending_exploration_charge_geometry
    assert preference['robot'] == 'tb2'
    assert set(preference) == {'robot', 'point', 'context', 'generated_at'}
    assert preference['generated_at'] == ROOMS['planning_started_at_sec']
    assert not sent and not requests and not node.rally_charge_requested
    assert private[-1]['event'] == 'coordinator_planning_lease_expired'
    assert private[-1]['charge_geometry_preference']['point'] == list(preference['point'])


def test_next_fresh_callback_rebuilds_one_robot_and_preserves_other_body_sources(monkeypatch):
    node, _, _, private = snapshot_node(ROOMS)
    node.pending_exploration_charge_geometry = hint(node)
    generated = []
    original = c.robot_candidate_assignments
    original_visual = c.known_space_search_candidates
    def record(*args, **kwargs):
        generated.append(args[3])
        return original(*args, **kwargs)
    monkeypatch.setattr(c, 'robot_candidate_assignments', record)
    def visual(*args, **kwargs):
        generated.append(args[3])
        return original_visual(*args, **kwargs)
    monkeypatch.setattr(c, 'known_space_search_candidates', visual)
    c.HeadquartersControl.assign_idle_robots(node)
    assert generated and set(generated) == {'tb2'}
    event = next(row for row in private if row['event'] == 'coordinator_charge_geometry_handoff')
    assert event['candidate_robot_names'] == ['tb2']
    assert all(name+'/'+kind in event['inputs'] for name in node.participating_robots()
               for kind in ('pose_state', 'frame_state', 'map_snapshot', 'battery_state'))
    assert node.rally_charge_requested or node.pending_exploration_return_yield


@pytest.mark.parametrize('change', ('expired', 'phase', 'active_peer', 'pending_charge'))
def test_invalid_handoff_returns_to_current_ordinary_generator(monkeypatch, change):
    node, _, _, private = snapshot_node(ROOMS)
    preference = hint(node)
    if change == 'expired':
        preference['generated_at'] = node.now()-10.01
    elif change == 'phase':
        preference['context'] = ('FOUND_UNCONFIRMED', *preference['context'][1:])
    elif change == 'active_peer':
        node.robot_states['tb1'] = 'active'
    else:
        node.rally_charge_requested['tb3'] = node.now()
    node.pending_exploration_charge_geometry = preference
    generated = []
    monkeypatch.setattr(c, 'robot_candidate_assignments',
        lambda *args, **kwargs: (generated.append(args[3]) or ([], dict(frontier_groups=0, groups_with_viewpoints=0))))
    c.HeadquartersControl.assign_idle_robots(node)
    assert all(row['event'] != 'coordinator_charge_geometry_handoff' for row in private)
    assert generated and set(generated) != {'tb2'}


def test_fresh_higher_energy_reprices_current_trip_instead_of_reusing_old_charge():
    node, sent, requests, _ = snapshot_node(ROOMS)
    node.pending_exploration_charge_geometry = hint(node)
    node.battery_states['tb2']['energy'] = 80.
    c.HeadquartersControl.assign_idle_robots(node)
    assert not requests and not node.rally_charge_requested
    assert sent and all(name == 'tb2' for name, _ in sent)
    assert node.exploration_travel_choices['tb2']['required_energy'] < 80.


def test_replaced_unknown_map_cannot_use_the_old_point_route_or_charge():
    node, sent, requests, _ = snapshot_node(ROOMS)
    node.pending_exploration_charge_geometry = hint(node)
    unknown = c.immutable_grid_snapshot(np.full(node.map_data.shape, -1, dtype=np.int16), node.map_data.shape)
    node.map_data = node.source_map_data = unknown
    node.robot_maps = {name: dict(data=unknown, resolution=node.resolution, origin=node.origin)
                       for name in node.robot_maps}
    c.HeadquartersControl.assign_idle_robots(node)
    assert not sent and not requests and not node.rally_charge_requested


def reader_events():
    preference = dict(robot='tb1', point=[2., 3.], context=['EXPLORE', False, ['tb1', 'tb2'], None], generated_at=5.)
    expired = dict(event='coordinator_planning_lease_expired', event_time=7.1,
        planning_started_at_sec=5., source_deadline_sec=7., charge_geometry_preference=copy.deepcopy(preference),
        geometry_preferences=dict(context=copy.deepcopy(preference['context']), points={'tb1': [[2., 3.]]}))
    inputs = {'headquarters/fused_map_snapshot': dict(source_time=8., ttl_sec=5., age_sec=0.)}
    for name in ('tb1', 'tb2'):
        for kind, ttl in (('pose_state', 2.), ('frame_state', 2.), ('map_snapshot', 5.), ('battery_state', 5.)):
            inputs[name+'/'+kind] = dict(source_time=8., ttl_sec=ttl, age_sec=0.)
    handoff = dict(event='coordinator_charge_geometry_handoff', event_time=8., task_phase='EXPLORE',
        preference=copy.deepcopy(preference), candidate_robot_names=['tb1'],
        robot_states={'tb1': 'idle', 'tb2': 'idle'}, battery_modes={'tb1': 'ACTIVE', 'tb2': 'ACTIVE'}, inputs=inputs)
    return [expired, handoff]


def audit(tmp_path, events, enabled=True):
    ledger = tmp_path/'ledger.jsonl'
    ledger.write_text(''.join(json.dumps(row)+'\n' for row in events))
    return charge_geometry_handoff_audit(ledger, enabled)


def test_independent_reader_preserves_expired_origin_and_requires_all_new_body_sources(tmp_path):
    result = audit(tmp_path, reader_events())
    assert result['retained_geometry_count'] == result['current_handoff_count'] == 1
    assert not result['pending_geometry_at_stop']


@pytest.mark.parametrize('bad', ('authority', 'renewed_origin', 'unrecorded_point', 'live_origin',
    'missing_origin', 'duplicate', 'changed_point', 'too_old', 'phase', 'several_generators',
    'moving_peer', 'returning_peer', 'missing_frame', 'expired_frame', 'future_pose', 'age', 'map'))
def test_independent_reader_rejects_invalid_geometric_handoff(tmp_path, bad):
    events = reader_events()
    expired, handoff = events
    if bad == 'authority': expired['charge_geometry_preference']['required_energy'] = 15.
    elif bad == 'renewed_origin': expired['charge_geometry_preference']['generated_at'] = 7.1
    elif bad == 'unrecorded_point': expired['geometry_preferences']['points']['tb1'] = [[9., 9.]]
    elif bad == 'live_origin': expired['event_time'] = 6.9
    elif bad == 'missing_origin': events.pop(0)
    elif bad == 'duplicate': events.append(copy.deepcopy(handoff))
    elif bad == 'changed_point': handoff['preference']['point'][0] = 2.1
    elif bad == 'too_old': handoff['event_time'] = 15.01
    elif bad == 'phase': handoff['task_phase'] = 'FOUND'
    elif bad == 'several_generators': handoff['candidate_robot_names'].append('tb2')
    elif bad == 'moving_peer': handoff['robot_states']['tb2'] = 'active'
    elif bad == 'returning_peer': handoff['battery_modes']['tb2'] = 'RETURNING'
    elif bad == 'missing_frame': del handoff['inputs']['tb2/frame_state']
    elif bad == 'expired_frame': handoff['inputs']['tb2/frame_state']['source_time'] = 5.9
    elif bad == 'future_pose': handoff['inputs']['tb2/pose_state']['source_time'] = 8.01
    elif bad == 'age': handoff['inputs']['tb2/frame_state']['age_sec'] = .1
    else: handoff['inputs']['headquarters/fused_map_snapshot']['source_time'] = 2.9
    with pytest.raises((AssertionError, KeyError)):
        audit(tmp_path, events)


def test_pending_geometry_at_stop_is_not_reported_as_action_or_task_completion(tmp_path):
    result = audit(tmp_path, reader_events()[:1])
    assert result['pending_geometry_at_stop'] and result['current_handoff_count'] == 0


def test_optional_reader_allows_zero_handoffs_but_rejects_undeclared_events(tmp_path):
    assert audit(tmp_path, [], False)['current_handoff_count'] == 0
    with pytest.raises(AssertionError, match='undeclared'):
        audit(tmp_path, reader_events(), False)
