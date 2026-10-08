import math
from unittest.mock import patch

import numpy as np
import pytest

from multi_robot_exploration import control as c


@pytest.mark.parametrize('masked_route', ['reachable', 'temporarily_missing'])
def test_funded_observer_prefers_a_side_pose_and_missing_routes_keep_fallback(monkeypatch, masked_route):
    # A narrow entrance with a free side alcove. Parking at its centre seals
    # both peers' later home-to-rally paths; the alcove preserves observation.
    grid=np.full((80,130),100,dtype=int)
    grid[35:46,:120]=0
    grid[15:46,45:56]=0
    grid[30:65,80:120]=0
    grid[30:60,:40]=0
    target=(6.5,4.)
    poses=[c.RallyPose(x,y,math.atan2(target[1]-y,target[0]-x))
           for x,y in ((5.,4.),(5.,2.5),(9.,4.))]
    monkeypatch.setattr(c,'rally_pose_candidates',lambda *args:poses)
    positions={'tb1':(5.,4.),'tb2':(1.,4.),'tb3':(2.,4.)}
    states={n:dict(mode='ACTIVE',energy=40. if n=='tb1' else 1.,
                  charge_x=p[0],charge_y=p[1],capacity=100.,charge_target_fraction=.8,
                  nominal_speed_mps=.18,idle_cost_per_sec=.02,move_cost_per_m=1.,
                  return_path_factor=2.,return_safety_margin=8.,charge_duration_sec=6.)
            for n,p in positions.items()}
    if masked_route=='temporarily_missing':
        monkeypatch.setattr(c,'plan_rally_leg',lambda *args,**kwargs:(None,()))
    with patch.object(c,'path_distance_grid',wraps=c.path_distance_grid) as fields:
        assigned=c.assign_rally_poses(grid,.1,(0.,0.),positions,target,
                                     battery_states=states,observer_robot='tb1')
    assert len(assigned)==3
    if masked_route=='reachable':
        assert assigned['tb1']!=poses[0]
        for name in ('tb2','tb3'):
            assert c.plan_rally_leg(assigned[name],grid,.1,(0.,0.),positions[name],
                blocked_positions=[(assigned['tb1'].x,assigned['tb1'].y)])[1]
        # Shared masked distance fields are per observer pose/home, rather
        # than recomputed for every complete candidate permutation.
        assert sum(call.kwargs.get('goal_mask') is not None for call in fields.call_args_list)==3
        assert fields.call_count<=15
    else:
        assert assigned['tb1']==poses[0]


def test_funded_nonobserver_also_leaves_the_charged_peers_entrance_free(monkeypatch):
    grid=np.full((80,130),100,dtype=int)
    grid[35:46,:120]=0
    grid[15:46,45:56]=0
    grid[30:65,80:120]=0
    grid[30:60,:40]=0
    target=(6.5,4.)
    poses=[c.RallyPose(x,y,math.atan2(target[1]-y,target[0]-x))
           for x,y in ((5.,4.),(5.,2.5),(9.,4.))]
    monkeypatch.setattr(c,'rally_pose_candidates',lambda *args:poses)
    positions={'tb1':(9.,4.),'tb2':(5.,4.),'tb3':(1.,4.)}
    states={n:dict(mode='ACTIVE',energy=40. if n!='tb3' else 1.,
                  charge_x=p[0],charge_y=p[1],capacity=100.,charge_target_fraction=.8,
                  nominal_speed_mps=.18,idle_cost_per_sec=.02,move_cost_per_m=1.,
                  return_path_factor=2.,return_safety_margin=8.,charge_duration_sec=6.)
            for n,p in positions.items()}
    with patch.object(c,'path_distance_grid',wraps=c.path_distance_grid) as fields:
        assigned=c.assign_rally_poses(grid,.1,(0.,0.),positions,target,
                                     battery_states=states,observer_robot='tb1')
    assert assigned['tb1']==poses[2] and assigned['tb2']==poses[1]
    assert c.plan_rally_leg(assigned['tb3'],grid,.1,(0.,0.),positions['tb3'],
        blocked_positions=[(assigned[n].x,assigned[n].y) for n in ('tb1','tb2')])[1]
    assert sum(call.kwargs.get('goal_mask') is not None for call in fields.call_args_list)==3
    assert fields.call_count<=15
