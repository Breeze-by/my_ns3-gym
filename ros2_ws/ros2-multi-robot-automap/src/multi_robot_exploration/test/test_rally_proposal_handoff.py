"""Slow geometric search must yield before fresh authority is consumed."""
import copy
import json
import math
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from multi_robot_exploration import control as c


def node_fixture():
    names=['tb1','tb2'];clock=[10.];grid=np.zeros((60,100),dtype=np.int16)
    phases=[]
    node=SimpleNamespace(
        task_state='FOUND',enable_rally=True,enable_battery=True,now=lambda:clock[0],
        participating_robots=lambda:names[:],input_robot_names=lambda:names[:],
        last_input_availability=True,last_input_diagnostic_at=10.,message_freshness_timeout_sec=5.,
        battery_monitor_started_at=10.,battery_state_received_at=dict.fromkeys(names,10.),
        robot_odom_received_at=dict.fromkeys(names,10.),robot_tf_received_at=dict.fromkeys(names,10.),
        robot_map_received_at=dict.fromkeys(names,10.),map_received_at=10.,target_received_source_time=10.,
        stop_target_scan=lambda:False,goal_handles=dict.fromkeys(names),cancel_requested=dict.fromkeys(names,False),
        robot_states=dict.fromkeys(names,'idle'),survey_goal_handle=None,survey_goal_started_at=None,
        survey_goal_pending=False,map_data=grid,source_map_data=grid,resolution=.1,origin=(0.,0.),
        robot_maps={name:dict(data=grid,resolution=.1,origin=(0.,0.)) for name in names},
        target=(6.,3.),rally_targets={},rally_final_targets={},pending_rally_proposal=None,
        robot_positions={'tb1':(1.,2.),'tb2':(1.,4.)},battery_modes=dict.fromkeys(names,'ACTIVE'),
        battery_states={name:dict(mode='ACTIVE',energy=1000.,capacity=1000.,charge_x=1.,charge_y=3.,
            charge_target_fraction=.8) for name in names},rally_hold_sec=5.,target_observing_robot=None,
        last_rally_assignment_attempt=0.,rally_assignment_objective='minimax',
        use_map_safe_rally_order=False,detecting_robot='tb1',consumed_publisher=Mock(),
        publish_rally_assignments=Mock(),get_logger=lambda:Mock(),rally_charge_requested={},
    )
    node.fresh_robot_poses=lambda:c.HeadquartersControl.fresh_robot_poses(node)
    node.fresh_robot_inputs=lambda:c.HeadquartersControl.fresh_robot_inputs(node)
    node.input_freshness_details=lambda:c.HeadquartersControl.input_freshness_details(node)
    node.fresh_target=lambda:0<=clock[0]-node.target_received_source_time<=60.
    def publish(phase):phases.append(phase);node.task_state=phase
    node.publish_task_state=publish
    assignment={name:c.RallyPose(x,y,math.atan2(3.-y,6.-x))
                for name,x,y in [('tb1',4.55,2.55),('tb2',4.55,3.55)]}
    return node,clock,phases,assignment


def renew_delivered_inputs(node,clock):
    # Simulate callbacks consuming real new stamps, never renewing an old sample.
    stamp=clock[0]-.1
    node.map_received_at=stamp
    for stamps in (node.robot_odom_received_at,node.robot_tf_received_at,
                   node.robot_map_received_at,node.battery_state_received_at):
        for name in stamps:stamps[name]=stamp


def records(node):
    return [json.loads(call.args[0].data) for call in node.consumed_publisher.publish.call_args_list]


def test_expired_search_is_retained_then_admitted_once_from_new_delivered_inputs(monkeypatch):
    node,clock,phases,assignment=node_fixture()
    def slow(*args,**kwargs):clock[0]=13.2;return assignment
    search=Mock(side_effect=slow);monkeypatch.setattr(c,'assign_rally_poses',search)
    stamps=copy.deepcopy(node.robot_odom_received_at)
    c.HeadquartersControl.update_mission(node)
    assert search.call_count==1 and not phases and not node.rally_targets
    assert node.pending_rally_proposal['assignment']==assignment and node.robot_odom_received_at==stamps
    c.HeadquartersControl.update_mission(node)
    assert search.call_count==1 and not phases
    renew_delivered_inputs(node,clock)
    c.HeadquartersControl.update_mission(node)
    assert search.call_count==1 and phases==['RALLY']
    assert node.rally_targets==node.rally_final_targets==assignment and node.pending_rally_proposal is None
    assert set(node.rally_dispatch_order)==set(assignment)
    assert not node.rally_charge_requested and all(handle is None for handle in node.goal_handles.values())
    admission=records(node)[-1]
    assert admission['event']=='coordinator_rally_proposal_admitted' and not admission['budget_reused']
    assert admission['proposal_evaluated_at_sec']==10. and admission['event_time']==13.2
    assert admission['inputs']['tb1/pose_state']['source_time']==13.1


@pytest.mark.parametrize('change',['occupied','unknown','clearance','occluded','target','participants',
    'separation','heading','outside','nonfinite'])
def test_pending_proposal_must_fit_current_geometry_target_and_participants(change):
    node,clock,phases,assignment=node_fixture()
    proposal=dict(assignment=assignment,target=tuple(node.target),evaluated_at=10.)
    node.pending_rally_proposal=proposal
    if change=='occupied':node.map_data[25,45]=100
    if change=='unknown':node.map_data[25,45]=-1
    if change=='clearance':node.map_data[25,47]=100
    if change=='occluded':node.map_data[28,53]=100
    if change=='target':node.target=(6.1,3.)
    if change=='participants':node.participating_robots=lambda:['tb1']
    if change=='separation':assignment['tb2']=assignment['tb1']
    if change=='heading':assignment['tb1']=c.RallyPose(4.55,2.55,0.)
    if change=='outside':assignment['tb1']=c.RallyPose(-10.,2.,0.)
    if change=='nonfinite':assignment['tb1']=c.RallyPose(float('nan'),2.,0.)
    assert not c.HeadquartersControl.admit_rally_proposal(node,proposal)
    assert node.pending_rally_proposal is None and not node.rally_targets and not phases
    node.publish_rally_assignments.assert_not_called()


@pytest.mark.parametrize('stream',['pose','frame','map','battery','target','shutdown'])
def test_pending_geometry_does_not_make_missing_expired_or_shutdown_authority_fresh(stream):
    node,clock,phases,assignment=node_fixture()
    proposal=dict(assignment=assignment,target=tuple(node.target),evaluated_at=9.)
    node.pending_rally_proposal=proposal
    if stream=='pose':node.robot_odom_received_at['tb1']=7.9
    if stream=='frame':node.robot_tf_received_at['tb1']=None
    if stream=='map':node.map_received_at=4.9
    if stream=='battery':node.battery_state_received_at['tb1']=4.9
    if stream=='target':node.target_received_source_time=-50.1
    if stream=='shutdown':node.shutdown_requested=True
    assert not c.HeadquartersControl.admit_rally_proposal(node,proposal)
    assert node.pending_rally_proposal is proposal and not node.rally_targets and not phases
    node.publish_rally_assignments.assert_not_called()


def test_order_computation_that_expires_a_lease_retains_points_without_publishing(monkeypatch):
    node,clock,phases,assignment=node_fixture()
    proposal=dict(assignment=assignment,target=tuple(node.target),evaluated_at=9.)
    node.pending_rally_proposal=proposal
    def slow(*args):clock[0]=12.1;return ['tb1','tb2']
    monkeypatch.setattr(c,'rally_dispatch_order',slow)
    assert not c.HeadquartersControl.admit_rally_proposal(node,proposal)
    assert node.pending_rally_proposal is proposal and not node.rally_targets and not phases
    node.publish_rally_assignments.assert_not_called()


@pytest.mark.parametrize('mode',['RETURNING','CHARGING'])
@pytest.mark.parametrize('stream',['fresh','pose','frame','map','battery','late_order','late_publication'])
def test_pending_proposal_keeps_inactive_participant_original_source_authority(mode,stream,monkeypatch):
    node,clock,_,assignment=node_fixture();node.battery_modes['tb2']=mode
    node.input_robot_names=lambda:['tb1']
    proposal=dict(assignment=assignment,target=tuple(node.target),evaluated_at=9.)
    node.pending_rally_proposal=proposal
    if stream in ('pose','frame','map','battery'):
        stamps={'pose':node.robot_odom_received_at,'frame':node.robot_tf_received_at,
            'map':node.robot_map_received_at,'battery':node.battery_state_received_at}[stream]
        stamps['tb2']=None if stream=='frame' else 7.9 if stream=='pose' else 4.9
    if stream=='late_order':
        def slow(*args):clock[0]=12.1;return ['tb1','tb2']
        monkeypatch.setattr(c,'rally_dispatch_order',slow)
    if stream=='late_publication':node.consumed_publisher.publish.side_effect=lambda msg:clock.__setitem__(0,12.1)
    assert c.HeadquartersControl.admit_rally_proposal(node,proposal) is (stream=='fresh')
    if stream=='fresh':
        event=records(node)[0]
        for kind in ('pose_state','frame_state','map_snapshot','battery_state'):
            assert event['inputs']['tb2/'+kind]['source_time']==10.
    else:
        assert node.pending_rally_proposal is proposal and not node.rally_targets
        node.publish_rally_assignments.assert_not_called()
