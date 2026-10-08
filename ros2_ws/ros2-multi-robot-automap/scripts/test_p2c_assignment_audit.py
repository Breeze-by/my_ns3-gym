import copy

import numpy as np
import pytest

from check_p2c_gate import rally_assignment_audit
from multi_robot_exploration import control as c


@pytest.mark.parametrize('corruption', [None,'source','time','map_content','self_return','wall_time','feasible'])
def test_assignment_failure_audit_binds_delivered_maps_and_rebuilds_real_infeasibility(corruption):
    grid=np.zeros((50,100),dtype=np.int16);grid[:,45]=100
    if corruption=='feasible':grid[:,45]=0
    e=dict(event='coordinator_rally_assignment_failed',event_time=11.,
        inputs={'headquarters/fused_map_snapshot':dict(source_time=10.)},
        planning_map=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_planning_map',10.,10.),
        source_map=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_fused_map',10.,10.),
        robot_positions={'tb1':(1.05,2.05)},current_positions={'tb1':(1.05,2.05)},
        target=(8.05,2.05),objective='minimax',hold_sec=5.,
        battery_states=None,observer_robot=None,return_maps={},self_return_cells={},
        computation_wall_sec=.012)
    e=copy.deepcopy(e)
    if corruption=='source':e['planning_map']['source']='hidden_native_map'
    if corruption=='time':e['event_time']=16.
    if corruption=='map_content':
        grid[5,5]=100
        e['source_map']=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_fused_map',10.,10.)
    if corruption=='self_return':e['self_return_cells']={'tb1':(5,5)}
    if corruption=='wall_time':e['computation_wall_sec']=-.1
    if corruption is None:assert rally_assignment_audit([e])['failed_assignments_rebuilt']==1
    else:
        with pytest.raises((AssertionError,ValueError)):rally_assignment_audit([e])
