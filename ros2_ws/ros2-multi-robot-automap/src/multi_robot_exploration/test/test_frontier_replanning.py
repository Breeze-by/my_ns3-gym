import math
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from multi_robot_exploration import control


@pytest.mark.parametrize('condition,cancel',[
    ('moving_to_observed_frontier',True),('final_frontier_still_useful',False),
    ('no_alternative',False),('alternative_unfunded',False),('stale_map',False),
    ('near_waypoint',False),('already_canceling',False),('camera_search',False),
    ('peer_reserved_route',False),('local_return',False),
])
def test_stale_final_frontier_replans_during_progress_only_to_admissible_work(condition,cancel):
    grid=np.zeros((120,120),dtype=np.int16);grid[75:100,20:40]=-1
    if condition=='final_frontier_still_useful':grid[20:40,85:105]=-1
    if condition=='no_alternative':grid[:]=0
    position=(2.05,2.05)
    if condition=='near_waypoint':position=(6.65,3.05)
    current=control.Assignment(control.Viewpoint(0,30,80,30,90,1000,30),
        8.05,3.05,8.,10.,7.05,3.05)
    handle=Mock();logger=Mock();names=('tb1','tb2')
    node=SimpleNamespace(task_state='EXPLORE',target_search_active=condition=='camera_search',
        now=lambda:100.,goal_timeout_sec=60.,goal_handles={'tb1':handle,'tb2':None},
        goal_started_at={'tb1':90.,'tb2':None},goal_last_progress_at={'tb1':99.,'tb2':None},
        goal_targets={'tb1':current,'tb2':None},goal_initial_gain={'tb1':1000,'tb2':0},
        cancel_requested={'tb1':condition=='already_canceling','tb2':False},
        fresh_robot_inputs=lambda:condition!='stale_map',map_data=grid,resolution=.1,origin=(0.,0.),
        robot_positions={'tb1':position,'tb2':(11.05,11.05)},
        robot_states={'tb1':'active','tb2':'idle'},goal_routes=dict.fromkeys(names,()),
        frontier_cache=None,battery_modes=dict.fromkeys(names,'ACTIVE'),enable_battery=True,
        battery_states={'tb1':dict(energy=9. if condition=='alternative_unfunded' else 80.,
            charge_x=1.05,charge_y=1.05,move_cost_per_m=1.,idle_cost_per_sec=.02,
            return_path_factor=2.,nominal_speed_mps=.18,return_safety_margin=8.)},
        get_logger=lambda:logger)
    if condition=='peer_reserved_route':
        node.robot_states['tb2']='active';node.robot_positions['tb2']=(1.05,2.65)
        node.goal_routes['tb2']=((1.05,2.65),(10.55,2.65))
    if condition=='local_return':node.battery_modes['tb2']='RETURNING'
    queries=[]
    def gain(x,y):
        queries.append((x,y))
        return control.visible_unknown_gain(grid,control.world_to_grid(x,y,.1,0.,0.),20.)
    node.target_information_gain=gain
    node.exploration_battery_factor=lambda *args:control.HeadquartersControl.exploration_battery_factor(node,*args)
    control.HeadquartersControl.cancel_stalled_goals(node)
    assert handle.cancel_goal_async.called is cancel
    assert queries==([(current.x,current.y)] if condition not in ('stale_map','already_canceling') else [])
    if cancel:
        assert node.cancel_requested['tb1']
        assert 'frontier already observed' in logger.warn.call_args.args[0]
        # Accepted work remains owned until its original result, not replaced
        # immediately by a speculative second action.
        assert node.goal_handles['tb1'] is handle and node.robot_states['tb1']=='active'
