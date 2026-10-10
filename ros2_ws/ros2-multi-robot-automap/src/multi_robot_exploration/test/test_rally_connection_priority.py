"""Spend the unchanged survey allowance on a peer missing the rally approach."""
import copy
import json
from unittest.mock import Mock

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_rally_proposal_handoff import node_fixture, records


def disconnected_node():
    node, clock, phases, _ = node_fixture()
    grid = np.zeros((90, 100), dtype=np.int16)
    grid[:, 50] = 100
    grid[75:, :] = -1
    node.map_data = node.source_map_data = grid
    node.robot_maps = {name: dict(data=grid, resolution=.1, origin=(0., 0.))
                       for name in node.robot_positions}
    node.target = (2., 3.)
    node.robot_positions = {'tb1': (1.5, 2.5), 'tb2': (7.5, 3.5)}
    node.target_observing_robot = 'tb1'
    node.active_batteries_ready = lambda: True
    node.last_rally_candidate_log = 0.
    node.survey_attempts = 5
    node.fail_task = Mock()
    return node, clock, phases


def test_actual_failed_search_prioritizes_disconnected_peer_before_optional_information(monkeypatch):
    node, _, phases = disconnected_node()
    connection = Mock(return_value=True)
    information = Mock(return_value=True)
    monkeypatch.setattr(c.HeadquartersControl, 'survey_rally_connection', connection)
    monkeypatch.setattr(c.HeadquartersControl, 'survey_target_frontiers', information)
    c.HeadquartersControl.update_mission(node)
    assert connection.call_args.args == (node, node.robot_positions, 'tb2', 10.)
    information.assert_not_called()
    assert node.survey_attempts == 5 and not phases
    node.fail_task.assert_not_called()
    diagnostic = records(node)[-1]['geometry_diagnostics']
    assert diagnostic['reason'] == 'disconnected_rally_approach' and diagnostic['robot'] == 'tb2'
    assert diagnostic['stratified'] and diagnostic['candidate_count'] >= 2


@pytest.mark.parametrize('reason,robot', [('insufficient_candidates', None),
    ('infeasible_assignment', None), ('disconnected_rally_approach', 'tb1')])
def test_other_failures_and_observer_keep_original_information_order(monkeypatch, reason, robot):
    node, _, _ = disconnected_node()
    def search(*args, **kwargs):
        kwargs['geometry_diagnostics'].update(reason=reason, robot=robot)
        return {}
    monkeypatch.setattr(c, 'assign_rally_poses', search)
    connection = Mock(return_value=True)
    information = Mock(return_value=True)
    monkeypatch.setattr(c.HeadquartersControl, 'survey_rally_connection', connection)
    monkeypatch.setattr(c.HeadquartersControl, 'survey_target_frontiers', information)
    c.HeadquartersControl.update_mission(node)
    information.assert_called_once()
    connection.assert_not_called()
    assert node.survey_attempts == 5


def priority_evidence():
    node, _, _ = disconnected_node()
    diagnostics = {}
    geometry = c.HeadquartersControl.delivered_return_maps(node)
    assert not c.assign_rally_poses(node.map_data, .1, (0., 0.), node.robot_positions,
        node.target, battery_states=node.battery_states, observer_robot='tb1',
        return_maps=geometry, geometry_diagnostics=diagnostics)
    c.HeadquartersControl.record_rally_assignment(node, node.robot_positions, geometry, .1,
        evaluated_at=10., geometry_diagnostics=diagnostics)
    assert c.HeadquartersControl.survey_rally_connection(node, node.robot_positions, 'tb2', 10.)
    assignment, proposal = records(node)[-2:]
    assert proposal['prioritized_names'] == ['tb2']
    assert {row[0] for row in proposal['candidates']} == {'tb2'}
    return assignment, proposal


def test_reader_rebuilds_missing_approach_and_original_filtered_ranking(tmp_path):
    from p2c_rally_connection import rally_connection_audit
    assignment, proposal = priority_evidence()
    path = tmp_path/'events.jsonl'
    path.write_text('\n'.join(json.dumps(e) for e in (assignment, proposal))+'\n')
    result = rally_connection_audit(path, True)
    assert result['disconnected_approaches_rebuilt'] == 1 and result['actual_dispatches'] == 0


@pytest.mark.parametrize('change', ['robot', 'count', 'map', 'position', 'source', 'target', 'candidates'])
def test_reader_rejects_unbound_or_false_priority(change):
    from p2c_rally_connection import audit_geometry, audit_priority
    assignment, proposal = map(copy.deepcopy, priority_evidence())
    if change == 'robot': proposal['prioritized_names'] = ['tb1']
    if change == 'count': assignment['geometry_diagnostics']['candidate_count'] += 1
    if change == 'map': proposal['planning_map']['source_time'] = 9.
    if change == 'position': proposal['robot_positions']['tb2'] = [2., 3.]
    if change == 'source': proposal['inputs']['tb2/pose_state']['source_time'] = 9.
    if change == 'target': proposal['target'] = [2.1, 3.]
    if change == 'candidates': proposal['candidates'][0][1] += .1
    with pytest.raises(AssertionError):
        audit_priority(proposal, assignment)
        audit_geometry(proposal)


def test_exhausted_survey_allowance_still_fails_before_an_action(monkeypatch):
    from test_rally_observation_recovery import observer_node
    node, client = observer_node()
    node.survey_attempts = node.num_robots*(1+node.rally_max_retries)
    node.task_state = 'FOUND'
    assert not c.HeadquartersControl.send_survey_goal(node, 'tb1', c.RallyPose(3.05, 2.05, 0.))
    node.fail_task.assert_called_once_with('rally_survey_failed:tb1')
    client.send_goal_async.assert_not_called()
