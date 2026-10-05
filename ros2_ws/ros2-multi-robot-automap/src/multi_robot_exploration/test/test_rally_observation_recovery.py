import math
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Time

from multi_robot_exploration import control


def observer_node():
    names=('tb1','tb2')
    client=Mock();client.server_is_ready.return_value=True
    node=SimpleNamespace(
        target_observing_robot='tb1',target=(2.05,4.05),target_view_distance=3.,
        robot_positions={'tb1':(2.05,2.05),'tb2':(8.05,8.05)},robot_yaws={'tb1':2.5},
        robot_states=dict.fromkeys(names,'idle'),goal_handles=dict.fromkeys(names),
        battery_modes=dict.fromkeys(names,'ACTIVE'),enable_battery=True,
        battery_states={name:dict(energy=20.,charge_x=1.05 if name=='tb1' else 8.05,
            charge_y=1.05 if name=='tb1' else 8.05,move_cost_per_m=1.,idle_cost_per_sec=.02,
            return_path_factor=2.,nominal_speed_mps=.18,return_safety_margin=8.) for name in names},
        rally_charge_requested={},return_yield_targets={},rally_leg_routes=dict.fromkeys(names,()),
        rally_goal_handles=dict.fromkeys(names),rally_goal_pending=dict.fromkeys(names,False),
        survey_goal_handle=None,survey_goal_pending=False,survey_attempts=0,
        map_data=np.zeros((100,100),dtype=np.int16),resolution=.1,origin=(0.,0.),
        fresh_robot_inputs=lambda:True,fresh_target=lambda:True,
        rally_position_tolerance=.35,goal_timeout_sec=60.,num_robots=2,rally_max_retries=2,
        robot_nav_clients={'tb1':client},record_navigation_decision=Mock(),survey_goal_response=Mock(),
        get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(to_msg=lambda:Time(sec=100))),
        fail_task=Mock(),rally_charge_budgets={'tb1':99.})
    return node,client


@pytest.mark.parametrize('condition,admitted', [
    ('waiting',True),('already_facing',False),('no_target',False),('stale_target',False),
    ('stale_map',False),('returning_peer',False),('own_charge_admitted',False),
    ('live_frontier',False),('pending_rally',False),('low_energy',False),
    ('unknown',False),('static_wall',False),('peer_body',False),('live_route',False),('no_slot',False),
])
def test_waiting_observer_turn_funds_own_return_and_obeys_admission(condition,admitted):
    node,client=observer_node()
    if condition=='already_facing':node.robot_yaws['tb1']=math.pi/2
    if condition=='no_target':node.target=None
    if condition=='stale_target':node.fresh_target=lambda:False
    if condition=='stale_map':node.fresh_robot_inputs=lambda:False
    if condition=='returning_peer':node.battery_modes['tb2']='RETURNING'
    if condition=='own_charge_admitted':node.rally_charge_requested['tb1']=99.
    if condition=='live_frontier':node.goal_handles['tb1']=object()
    if condition=='pending_rally':node.rally_goal_pending['tb1']=True
    if condition=='low_energy':node.battery_states['tb1']['energy']=9.
    if condition=='unknown':node.map_data[20,20]=-1
    if condition=='static_wall':node.map_data[20,22]=100
    if condition=='peer_body':node.robot_positions['tb2']=(2.45,2.05)
    if condition=='no_slot':node.rally_max_concurrent=1;node.rally_goal_pending['tb2']=True
    if condition=='live_route':
        node.rally_goal_handles['tb2']=object();node.rally_leg_routes['tb2']=((2.05,1.),(2.05,3.))
    assert control.HeadquartersControl.restore_observer_heading(node) is admitted
    assert client.send_goal_async.called is admitted
    if admitted:
        goal=client.send_goal_async.call_args.args[0].pose
        assert (goal.pose.position.x,goal.pose.position.y)==node.robot_positions['tb1']
        assert math.atan2(2*goal.pose.orientation.w*goal.pose.orientation.z,
            1-2*goal.pose.orientation.z**2)==pytest.approx(math.pi/2)
        assert node.record_navigation_decision.call_args.args[1]=='target_observation_heading'
        assert node.survey_heading_only and node.rally_charge_budgets['tb1']==99.


def test_heading_success_does_not_claim_map_survey_progress_or_final_arrival():
    node,_=observer_node();handle=object();node.survey_goal_handle=handle
    node.survey_goal_started_at=90.;node.survey_robot='tb1';node.survey_heading_only=True
    node.survey_cancel_requested=False;node.survey_battery_preempted=False
    node.rally_probe_targets=set();node.rally_probe_robot=None;node.rally_final_targets={}
    node.rally_prepare_started_at=80.;node.rally_arrived={'tb1':False}
    node.now=lambda:100.;node.get_logger=lambda:Mock()
    control.HeadquartersControl.survey_goal_result(node,handle,
        SimpleNamespace(result=lambda:SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED)))
    assert node.rally_prepare_started_at==80. and node.rally_arrived=={'tb1':False}
    assert node.survey_goal_handle is None and not node.survey_heading_only


def test_connector_survey_uses_known_frontier_around_target_dead_end():
    # Known U-shaped route initially moves away from the target; the missing
    # connecting corridor is unknown. Straight-line target descent cannot help.
    grid=np.full((100,100),-1,dtype=np.int16)
    grid[10:30,10:80]=0;grid[10:80,60:80]=0;grid[60:80,30:80]=0
    grid[60:80,10:25]=0
    position=(3.05,6.55);target=(1.55,6.55)
    assert control.rally_survey_pose(grid,.1,(0.,0.),position,target) is None
    sent=[]
    node=SimpleNamespace(map_data=grid,resolution=.1,origin=(0.,0.),target=target,
        task_state='FOUND',
        robot_positions={'tb1':position,'tb2':(1.55,6.55)},
        battery_modes={'tb1':'ACTIVE','tb2':'ACTIVE'},target_observing_robot='tb2',
        send_survey_goal=lambda name,pose:sent.append((name,pose)) or True)
    assert control.HeadquartersControl.survey_rally_connection(node,node.robot_positions)
    name,pose=sent[0]
    assert name=='tb1'
    cell=control.world_to_grid(pose.x,pose.y,.1,0.,0.)
    safe=control.traversable_grid(grid,.1,control.ROBOT_CLEARANCE_M)
    assert safe[cell] and grid[cell]==0
    planned=control.plan_rally_leg(pose,grid,.1,(0.,0.),position,visible_only=True)
    assert planned[0] is not None and planned[1]
    assert all(grid[control.world_to_grid(*p,.1,0.,0.)]==0 for p in planned[1])
    # Updating a copy with real observations can later connect the regions;
    # choosing the survey must never fabricate those cells in the original.
    assert np.all(grid[30:60,10:30]==-1)
