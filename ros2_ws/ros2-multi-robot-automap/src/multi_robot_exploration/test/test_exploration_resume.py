"""A charging interruption preserves intent, while fresh admission owns motion."""
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import control


def assignment(x, y, gain=1000, utility=10, navigation=None):
    point = navigation or (x, y)
    return control.Assignment(
        control.Viewpoint(1, 30, 40, 30, 41, gain, 10),
        x, y, 3., utility, *point,
    )


@pytest.mark.parametrize("intent,gain,factor,expected", [
    ((4., 3., 1000), 1000, 1., True),
    (None, 1000, 1., False),
    ((8., 3., 1000), 1000, 1., False),
    ((4., 3., 1000), 200, 1., False),
    ((4., 3., 5000), 900, 1., False),
    ((4., 3., 1000), 1000, .25, False),
    ((4., 3., 1000), 1000, float('nan'), False),
])
def test_current_frontier_must_still_be_near_useful_and_funded(intent, gain, factor, expected):
    assert control.interrupted_frontier_is_useful(assignment(4., 3., gain), intent, factor) is expected


def finish_node(goal, phase="EXPLORE", preempted=True):
    name="tb1"
    dictionaries={field: {name: None} for field in (
        "goal_handles", "goal_started_at", "goal_last_progress_at", "goal_best_distance",
        "goal_last_position", "goal_known_count", "goal_initial_gain", "goal_routes",
        "cancel_requested", "robot_states")}
    return SimpleNamespace(
        **dictionaries, goal_targets={name: goal}, battery_preempted={name: preempted},
        task_state=phase, exploration_resume_intents={}, battery_modes={name: "ACTIVE"},
        target_history=[], bad_targets=[], now=lambda: 10., check_exploration_completion=lambda: None,
    )


@pytest.mark.parametrize("phase,preempted,success,remember", [
    ("EXPLORE", True, False, True),
    ("FOUND_UNCONFIRMED", True, False, True),
    ("RALLY", True, False, False),
    ("EXPLORE", False, False, False),
    ("EXPLORE", True, True, False),
])
def test_only_battery_interrupted_search_goals_are_remembered(phase, preempted, success, remember):
    node=finish_node(assignment(4., 3.), phase, preempted)
    control.HeadquartersControl.finish_goal(node, "tb1", success, blacklist=False)
    assert bool(node.exploration_resume_intents)==remember
    if remember:
        assert node.exploration_resume_intents['tb1']==(4., 3., 1000)
    assert node.goal_targets['tb1'] is None and node.goal_routes['tb1']==()
    assert not node.bad_targets


@pytest.mark.parametrize("navigation,remaining", [((2., 3.), True), ((7.5, 3.), False)])
def test_safe_prefix_keeps_intent_until_the_interrupted_frontier_is_reached(navigation, remaining):
    node=finish_node(assignment(8., 3., navigation=navigation))
    node.exploration_resume_intents['tb1']=(8., 3., 1000)
    control.HeadquartersControl.finish_goal(node, "tb1", True)
    assert bool(node.exploration_resume_intents)==remaining


def test_physical_failure_drops_intent_instead_of_resuming():
    node=finish_node(assignment(8., 3.))
    node.exploration_resume_intents['tb1']=(8., 3., 1000)
    node.battery_modes['tb1']='FAILED'
    control.HeadquartersControl.finish_goal(node, 'tb1', False, blacklist=False)
    assert not node.exploration_resume_intents and node.robot_states['tb1']=='failed'


@pytest.mark.parametrize("reason", ["resume", "unfunded", "observed", "blocked", "stale", "returning"])
def test_resume_preference_uses_existing_admission_and_falls_back(monkeypatch, reason):
    grid=np.zeros((60, 100), dtype=int)
    old=assignment(8., 3., gain=100 if reason=='observed' else 1000)
    new=assignment(2., 3., utility=100)
    if reason=='blocked':
        grid[:, 70:72]=100
    def candidates(*args, **kwargs):
        return [(a.utility, 'tb1', a.viewpoint.group_id, a) for a in (old,new)], {
            'frontier_groups': 2, 'groups_with_viewpoints': 2, 'candidate_assignments': 2}
    monkeypatch.setattr(control, 'robot_candidate_assignments', candidates)
    sent=[]
    node=SimpleNamespace(
        task_state='EXPLORE', map_data=grid, resolution=.1, origin=(0.,0.),
        robot_positions={'tb1':(5.,3.)}, robot_maps={'tb1':{}}, robot_states={'tb1':'idle'},
        battery_modes={'tb1':'RETURNING' if reason=='returning' else 'ACTIVE'},
        frontier_cache=control.prepare_frontier_data(grid,.1),
        input_robot_names=lambda:['tb1'], participating_robots=lambda:['tb1'],
        fresh_robot_inputs=lambda:reason!='stale', active_exclusions=lambda:[],
        exploration_battery_factor=lambda name,destination_distance,destination:
            .25 if reason=='unfunded' and destination==(8.,3.) else 1.,
        exploration_resume_intents={'tb1':(8.,3.,1000)},
        goal_targets={}, goal_routes={}, goal_initial_gain={'tb1':0},
        target_information_gain=lambda *args:1000,
        get_logger=lambda:SimpleNamespace(info=lambda *args:None,warn=lambda *args:None),
        send_goal=lambda name,goal:sent.append(goal),
    )
    control.HeadquartersControl.assign_idle_robots(node)
    if reason in ('stale','returning'):
        assert not sent and node.exploration_resume_intents
    elif reason=='resume':
        assert len(sent)==1 and sent[0].x==8. and node.exploration_resume_intents
    else:
        assert len(sent)==1 and sent[0].x==2. and not node.exploration_resume_intents
