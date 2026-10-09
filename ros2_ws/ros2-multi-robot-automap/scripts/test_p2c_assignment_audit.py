import copy

import numpy as np
import pytest

from check_p2c_gate import rally_assignment_audit, rally_proposal_audit
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


@pytest.mark.parametrize('corruption', [None, 'missing_robot', 'wrong_pose', 'wrong_heading'])
def test_chosen_assignment_witness_requires_the_exact_complete_rebuilt_choice(corruption):
    grid=np.zeros((50,100),dtype=np.int16)
    positions={'tb1':(1.05,2.05)};target=(8.05,2.05)
    assigned=c.assign_rally_poses(grid,.1,(0.,0.),positions,target)
    assert assigned
    e=dict(event='coordinator_rally_assignment_chosen',event_time=11.,
        inputs={'headquarters/fused_map_snapshot':dict(source_time=10.)},
        planning_map=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_planning_map',10.,10.),
        source_map=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_fused_map',10.,10.),
        robot_positions=positions,current_positions=positions,target=target,
        objective='minimax',hold_sec=5.,battery_states=None,observer_robot=None,
        return_maps={},self_return_cells={},computation_wall_sec=.012,
        assignment={name:[pose.x,pose.y,pose.yaw] for name,pose in assigned.items()})
    if corruption=='missing_robot':e['assignment']={}
    if corruption=='wrong_pose':e['assignment']['tb1'][0]+=.1
    if corruption=='wrong_heading':e['assignment']['tb1'][2]+=.1
    if corruption is None:
        result=rally_assignment_audit([e])
        assert result['chosen_assignments_rebuilt']==1 and result['failed_assignments_rebuilt']==0
    else:
        with pytest.raises(AssertionError):rally_assignment_audit([e])


def proposal_records():
    grid=np.zeros((50,100),dtype=np.int16);target=[8.05,2.05]
    positions={'tb1':[1.05,2.05]}
    assigned=c.assign_rally_poses(grid,.1,(0.,0.),positions,target)
    assignment={name:[pose.x,pose.y,pose.yaw] for name,pose in assigned.items()}
    original=dict(event='coordinator_rally_assignment_chosen',event_time=10.,
        computation_completed_at_sec=13.,assignment=assignment,target=target,
        robot_positions=positions,battery_states=None)
    inputs={key:dict(source_time=13.1,age_sec=.1,ttl_sec=ttl) for key,ttl in {
        'headquarters/fused_map_snapshot':5.,'headquarters/target_detection':60.,
        'tb1/pose_state':2.,'tb1/frame_state':2.,'tb1/map_snapshot':5.}.items()}
    admitted=dict(event='coordinator_rally_proposal_admitted',event_time=13.2,
        proposal_evaluated_at_sec=10.,assignment=copy.deepcopy(assignment),target=target,
        required_robots=['tb1'],dispatch_order=['tb1'],inputs=inputs,
        planning_map=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_planning_map',13.1,13.1),
        source_map=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_fused_map',13.1,13.1),
        self_return_cells={},budget_reused=False,target_view_distance_m=3.,
        robot_positions=positions,map_safe_order=False,detecting_robot='tb1')
    return [original,admitted],grid


@pytest.mark.parametrize('corruption',[None,'old_reference','different_assignment','different_target',
    'participants','expired_pose','future_target','age','ttl','source','source_time',
    'old_budget','time','obstacle','heading','view_range','dispatch_order'])
def test_proposal_reader_binds_original_intent_and_checks_current_delivered_geometry(corruption):
    events,grid=proposal_records();old,e=events
    if corruption=='old_reference':e['proposal_evaluated_at_sec']=9.
    if corruption=='different_assignment':e['assignment']['tb1'][0]+=.1
    if corruption=='different_target':e['target']=[8.1,2.05]
    if corruption=='participants':e['required_robots'].append('tb2')
    if corruption=='expired_pose':e['inputs']['tb1/pose_state'].update(source_time=11.,age_sec=2.2)
    if corruption=='future_target':e['inputs']['headquarters/target_detection'].update(source_time=14.,age_sec=-.8)
    if corruption=='age':e['inputs']['tb1/pose_state']['age_sec']=0.
    if corruption=='ttl':e['inputs']['tb1/pose_state']['ttl_sec']=3.
    if corruption=='source':e['planning_map']['source']='native_hidden_map'
    if corruption=='source_time':e['planning_map']['source_time']=10.
    if corruption=='old_budget':e['budget_reused']=True
    if corruption=='time':e['event_time']=12.9
    if corruption=='obstacle':
        cell=c.world_to_grid(*e['assignment']['tb1'][:2],.1,0.,0.);grid[cell]=100
        e['planning_map']=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_planning_map',13.1,13.1)
        e['source_map']=c.grid_audit_evidence(grid,.1,(0.,0.),'ap_delivered_fused_map',13.1,13.1)
    if corruption=='heading':e['assignment']['tb1'][2]+=.1;old['assignment']['tb1'][2]+=.1
    if corruption=='view_range':e['target_view_distance_m']=.1
    if corruption=='dispatch_order':e['dispatch_order']=['tb1','tb1']
    if corruption is None:
        result=rally_proposal_audit(events,True)
        assert result['admitted_proposals']==result['deferred_proposals']==1 and not result['budget_reused']
    else:
        with pytest.raises((AssertionError,KeyError,ValueError)):rally_proposal_audit(events,True)


def test_declared_handoff_requires_an_actual_admission_witness():
    assert rally_proposal_audit([],False)['admitted_proposals']==0
    with pytest.raises(AssertionError):rally_proposal_audit([],True)
