"""An actual delivered visual snapshot needs mapping rays only on fallback."""
import json
from pathlib import Path

from test_exploration_resume import conditional_snapshot_node
from multi_robot_exploration import control


def visual_snapshot_node():
    saved = json.loads((Path(__file__).parent / 'fixtures/p2c_v31_visual_computation.json').read_text())
    e = saved['event']; node, sent = conditional_snapshot_node(e, {})
    node.input_robot_names = lambda: e['travel_preference']['eligible_robot_names']
    node.robot_maps.setdefault('tb1', None)
    node.robot_states = {name: 'idle' for name in node.robot_states}
    node.enable_rally = True; node.initial_search_next = {e['robot']: True}
    node.rally_charge_requested = {'tb1': e['event_time']}
    node.initial_search_visits = {i: v for i, v in enumerate(e['travel_preference']['initial_search_visits'])}
    node.initial_search_views = {i: v for i, v in enumerate(e['travel_preference']['initial_search_views'])}
    node.successful_exploration_legs = {e['robot']: 1}; node.target_search_visits = []
    node.exploration_travel_choices = {}; node.frontier_charge_lookahead = None
    return node, sent, e


def test_visual_admission_keeps_original_choice_without_computing_unused_mapping_rays(monkeypatch):
    node, sent, e = visual_snapshot_node()
    def unused(*args):
        raise AssertionError('unused frontier preparation ran during visual admission')
    monkeypatch.setattr(control, 'prepare_frontier_data', unused)
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(sent) == 1 and sent[0][0] == e['robot']
    assert [sent[0][1].navigation_x, sent[0][1].navigation_y] == e['requested_position']
    assert node.frontier_cache is None


def test_empty_visual_interest_still_builds_and_uses_original_mapping_fallback(monkeypatch):
    node, sent, e = visual_snapshot_node(); calls = []
    original = control.prepare_frontier_data
    def prepare(*args):
        result = original(*args); calls.append(result); return result
    monkeypatch.setattr(control, 'prepare_frontier_data', prepare)
    monkeypatch.setattr(control, 'known_space_search_candidates', lambda *args, **kwargs: [])
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(calls) == 1 and node.frontier_cache is calls[0]
    assert calls[0][0] and calls[0][2]
    assert sent and sent[0][0] == e['robot'] and sent[0][1].viewpoint.information_gain > 0
    assert 'initial_search_views' not in node.exploration_travel_choices[e['robot']]
