import copy
import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from multi_robot_exploration import control


def proposal_node():
    clock=[11.];source=[10.]
    choices=(('tb1',control.RallyPose(4.,3.,.5)),('tb3',control.RallyPose(5.,3.,.7)))
    proposal=dict(target=(6.,4.),names=('tb1','tb2','tb3'),choices=choices,cursor=0,generated_at=10.)
    inputs=lambda: {n+'/'+kind:dict(source_time=source[0],ttl_sec=ttl)
        for n in proposal['names'] for kind,ttl in (('pose_state',2.),('frame_state',2.),('battery_state',5.))}
    node=SimpleNamespace(task_state='FOUND',target=(6.,4.),pending_rally_connection=proposal,
        battery_modes=dict.fromkeys(proposal['names'],'ACTIVE'),target_observing_robot='tb2',
        survey_goal_handle=None,survey_goal_pending=False,robot_states=dict.fromkeys(proposal['names'],'idle'),
        target_scan_robot=None,target_scan_handle=None,consumed_publisher=Mock(),send_survey_goal=Mock(return_value=True),
        now=lambda:clock[0],input_freshness_details=inputs,
        participating_robots=lambda:list(proposal['names']),active_batteries_ready=lambda:True,
        fresh_robot_inputs=lambda:0<=clock[0]-source[0]<=2.,fresh_target=lambda:True)
    return node,clock,source


@pytest.mark.parametrize('condition',('target','participants','phase','battery'))
def test_changed_task_context_discards_points_without_dispatch(condition):
    node,_,_=proposal_node()
    if condition=='target':node.target=(7.,4.)
    if condition=='participants':node.participating_robots=lambda:['tb1','tb2']
    if condition=='phase':node.task_state='RALLY'
    if condition=='battery':node.active_batteries_ready=lambda:False
    assert not control.HeadquartersControl.admit_rally_connection(node)
    assert node.pending_rally_connection is None and not node.send_survey_goal.called


@pytest.mark.parametrize('condition',('expired','survey_pending','survey_accepted','ordinary_pending','scan_pending','scan_accepted'))
def test_waits_for_current_sources_and_closed_actions(condition):
    node,clock,_=proposal_node();original=copy.deepcopy(node.pending_rally_connection)
    if condition=='expired':clock[0]=13.
    if condition=='rewound':clock[0]=9.
    if condition=='survey_pending':node.survey_goal_pending=True
    if condition=='survey_accepted':node.survey_goal_handle=object()
    if condition=='ordinary_pending':node.robot_states['tb3']='active'
    if condition=='scan_pending':node.target_scan_robot='tb3'
    if condition=='scan_accepted':node.target_scan_handle=object()
    assert control.HeadquartersControl.admit_rally_connection(node)
    assert node.pending_rally_connection==original and not node.send_survey_goal.called


def test_expired_failed_trial_retries_same_geometry_only_after_new_delivery():
    node,clock,source=proposal_node()
    def expired(*args):clock[0]=13.;return False
    node.send_survey_goal.side_effect=expired
    assert control.HeadquartersControl.admit_rally_connection(node)
    assert node.pending_rally_connection['cursor']==0 and node.send_survey_goal.call_count==1
    assert control.HeadquartersControl.admit_rally_connection(node)
    assert node.send_survey_goal.call_count==1
    source[0]=13.;node.send_survey_goal.side_effect=None
    assert control.HeadquartersControl.admit_rally_connection(node)
    assert node.pending_rally_connection is None and node.send_survey_goal.call_count==2
    events=[json.loads(call.args[0].data) for call in node.consumed_publisher.publish.call_args_list]
    assert events[0]['fresh_after'] is False and events[1]['accepted'] is True
    assert events[1]['inputs']['tb1/pose_state']['source_time']==13.


def test_fresh_veto_advances_to_next_point_without_repricing_as_a_goal():
    node,_,_=proposal_node();node.send_survey_goal.side_effect=[False,True]
    assert control.HeadquartersControl.admit_rally_connection(node)
    assert [call.args[0] for call in node.send_survey_goal.call_args_list]==['tb1','tb3']
    assert node.pending_rally_connection is None


def test_exhaustion_returns_to_original_bounded_preparation_policy():
    node,_,_=proposal_node();node.send_survey_goal.return_value=False
    assert not control.HeadquartersControl.admit_rally_connection(node)
    assert node.pending_rally_connection is None and node.send_survey_goal.call_count==2


def test_new_observer_is_skipped_without_reusing_old_observer_assignment():
    node,_,_=proposal_node();node.target_observing_robot='tb1'
    assert control.HeadquartersControl.admit_rally_connection(node)
    assert node.send_survey_goal.call_args.args[0]=='tb3'


def test_clock_rewind_discards_pre_reset_geometry():
    node,clock,_=proposal_node();clock[0]=9.
    assert not control.HeadquartersControl.admit_rally_connection(node)
    assert node.pending_rally_connection is None and not node.send_survey_goal.called
