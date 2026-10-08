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
        task_state=phase, exploration_resume_intents={}, successful_exploration_legs={}, battery_modes={name: "ACTIVE"},
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
    assert node.successful_exploration_legs.get('tb1',0)==int(success and phase in ('EXPLORE','FOUND_UNCONFIRMED'))


@pytest.mark.parametrize("navigation,remaining", [((2., 3.), True), ((7.5, 3.), True), ((8.,3.),False)])
def test_safe_prefix_keeps_intent_until_the_interrupted_frontier_is_reached(navigation, remaining):
    node=finish_node(assignment(8., 3., navigation=navigation))
    node.exploration_resume_intents['tb1']=(8., 3., 1000)
    control.HeadquartersControl.finish_goal(node, "tb1", True)
    assert bool(node.exploration_resume_intents)==remaining


@pytest.mark.parametrize('phase,success,remaining',[
    ('EXPLORE',True,True),('FOUND_UNCONFIRMED',True,True),
    ('RALLY',True,False),('EXPLORE',False,False)])
def test_new_viewpoint_prefix_creates_intent_without_a_battery_interruption(phase,success,remaining):
    node=finish_node(assignment(8.,3.,navigation=(2.,3.)),phase,preempted=False)
    control.HeadquartersControl.finish_goal(node,'tb1',success)
    assert bool(node.exploration_resume_intents)==remaining
    if remaining:assert node.exploration_resume_intents['tb1']==(8.,3.,1000)


def test_non_preempted_navigation_failure_clears_a_previous_prefix_intent():
    node=finish_node(assignment(8.,3.,navigation=(2.,3.)),preempted=False)
    node.exploration_resume_intents['tb1']=(8.,3.,1000)
    control.HeadquartersControl.finish_goal(node,'tb1',False)
    assert not node.exploration_resume_intents


def test_physical_failure_drops_intent_instead_of_resuming():
    node=finish_node(assignment(8., 3.))
    node.exploration_resume_intents['tb1']=(8., 3., 1000)
    node.battery_modes['tb1']='FAILED'
    control.HeadquartersControl.finish_goal(node, 'tb1', False, blacklist=False)
    assert not node.exploration_resume_intents and node.robot_states['tb1']=='failed'


@pytest.mark.parametrize("reason", ["resume", "low_value", "unfunded", "observed", "blocked", "stale", "returning"])
def test_resume_preference_uses_existing_admission_and_falls_back(monkeypatch, reason):
    grid=np.zeros((60, 100), dtype=int)
    old=assignment(8., 3., gain=100 if reason=='observed' else 1000,
        utility=10 if reason=='low_value' else 70)
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


def test_continuation_weight_has_a_finite_utility_tradeoff():
    assert control.frontier_scheduling_score(60.,True)>control.frontier_scheduling_score(100.,False)
    assert control.frontier_scheduling_score(10.,True)<control.frontier_scheduling_score(100.,False)


def test_successful_new_prefix_preserves_a_useful_viewpoint_in_the_saved_delivered_snapshot():
    import base64,json,zlib
    from pathlib import Path
    f=json.loads((Path(__file__).parent/'fixtures/p2c_v18_prefix_reassignment.json').read_text())
    e=f['current_navigation_event'];prior=f['prior_navigation_event'];maps={}
    for key,s in [('planning',e['planning_map']),('source',e['source_map']),*e['return_maps'].items()]:
        maps[key]=dict(data=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape']),
            resolution=s['resolution'],origin=s['origin'])
    intended=prior['travel_preference']['target'];prefix=prior['requested_position']
    result_node=finish_node(assignment(*intended,gain=f['prior_information_gain'],navigation=prefix),preempted=False)
    control.HeadquartersControl.finish_goal(result_node,'tb1',True)
    assert result_node.exploration_resume_intents['tb1'][:2]==tuple(intended)
    node,sent=conditional_snapshot_node(e,result_node.exploration_resume_intents)
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(sent)==1 and sent[0][0]=='tb1'
    selected=sent[0][1]
    assert np.linalg.norm(np.array([selected.x,selected.y])-intended)<=control.MIN_TARGET_SEPARATION_M
    assert selected.viewpoint.information_gain>max(200.,.2*f['prior_information_gain'])
    assert node.exploration_travel_choices['tb1']['resume_intent']==tuple(intended)+(f['prior_information_gain'],)
    # Conditional snapshot fixture, with no original history/reservation replay.
    # An empty intent on the same reconstructed inputs selects the nearby task.
    node.robot_states['tb1']='idle';node.exploration_resume_intents={};node.goal_routes={};sent.clear()
    control.HeadquartersControl.assign_idle_robots(node)
    assert sent and np.linalg.norm(np.array([sent[0][1].x,sent[0][1].y])-intended)>control.MIN_TARGET_SEPARATION_M


def conditional_snapshot_node(e,intents):
    import base64,zlib
    maps={}
    for key,s in [("planning",e["planning_map"]),("source",e["source_map"]),*e["return_maps"].items()]:
        maps[key]=dict(data=np.frombuffer(zlib.decompress(base64.b64decode(s["grid"])),dtype="<i2").reshape(s["shape"]),
            resolution=s["resolution"],origin=s["origin"])
    sent=[];grid=maps['planning'];states=e['battery_states']
    node=SimpleNamespace(enable_battery=True,task_state='EXPLORE',now=lambda:e['event_time'],
        map_data=grid['data'],resolution=grid['resolution'],origin=grid['origin'],
        source_map_data=maps['source']['data'],map_self_return_cells=e['self_return_cells'],
        map_received_at=e['planning_map']['source_time'],
        robot_positions=e['robot_positions'],robot_states={'tb1':'idle','tb2':'active'},
        battery_modes={name:state['mode'] for name,state in states.items()},battery_states=states,
        robot_maps={name:maps[name] for name in e['return_maps']},
        robot_map_received_at={name:s['source_time'] for name,s in e['return_maps'].items()},
        robot_odom_received_at={name:e['inputs'][name+'/pose_state']['source_time'] for name in states},
        robot_tf_received_at={name:e['inputs'][name+'/frame_state']['source_time'] for name in states},
        battery_state_received_at={name:e['inputs'][name+'/battery_state']['source_time'] for name in states},
        exploration_resume_intents=intents,rally_charge_requested={},
        input_robot_names=lambda:list(states),participating_robots=lambda:list(states),
        fresh_robot_inputs=lambda:True,active_exclusions=lambda:[],frontier_cache=None,
        goal_targets={},goal_routes={},goal_initial_gain={},last_no_assignment_log=-float('inf'),
        target_information_gain=lambda *args:1000,input_freshness_details=lambda:e['inputs'],
        get_logger=lambda:SimpleNamespace(info=lambda *args:None,warn=lambda *args:None),
        consumed_publisher=SimpleNamespace(publish=lambda *args:None),
        send_goal=lambda name,a:sent.append((name,a)))
    node.exploration_battery_factor=lambda *args:control.HeadquartersControl.exploration_battery_factor(node,*args)
    return node,sent


def test_low_value_continuation_yields_on_the_saved_delivered_snapshot():
    import json
    from pathlib import Path
    f=json.loads((Path(__file__).parent/'fixtures/p2c_v20_low_value_continuation.json').read_text())
    e=f['current_navigation_event'];prior=e['travel_preference']
    node,sent=conditional_snapshot_node(e,{'tb1':tuple(prior['resume_intent'])})
    control.HeadquartersControl.assign_idle_robots(node)
    assert len(sent)==1 and sent[0][0]=='tb1'
    chosen=node.exploration_travel_choices['tb1']
    assert 'resume_intent' not in chosen
    assert chosen['adjusted_utility']>control.FRONTIER_CONTINUATION_WEIGHT*prior['adjusted_utility']
    assert chosen['continuation_weight']==1.
    assert chosen['required_energy']<e['battery_states']['tb1']['energy']
