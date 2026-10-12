"""Known-space checks use delivered visits and preserve route/energy admission."""
import math
import copy
import base64
import zlib
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_exploration_charging import charge_node,assignment,install_candidates
from test_exploration_resume import finish_node
from test_relative_frontier_travel import travel_event
from geometry_msgs.msg import PoseStamped


@pytest.mark.parametrize('blocked',[False,True,'unknown'])
def test_known_view_faces_unvisited_known_free_sector_and_respects_occlusion(blocked):
    grid=np.zeros((60,60),dtype=int);interest=np.zeros_like(grid,dtype=bool)
    interest[20:40,32:44]=True
    if blocked:grid[:,31]=-1 if blocked=='unknown' else 100
    gain,yaw=c.known_search_view(grid,(30,30),15,interest)
    if blocked:assert gain==0
    else:assert gain>100 and abs(math.atan2(math.sin(yaw),math.cos(yaw)))<=math.pi/8


@pytest.mark.parametrize('invalid',['valid','stale_odom','stale_frame','future','nan','phase'])
def test_visit_preference_records_only_fresh_delivered_pose_sources(invalid):
    node=SimpleNamespace(initial_search_visits={},task_state='EXPLORE',now=lambda:10.,
        robot_positions={'tb1':(2.,3.)},robot_odom_received_at={'tb1':9.},robot_tf_received_at={'tb1':9.5})
    if invalid=='stale_odom':node.robot_odom_received_at['tb1']=7.9
    if invalid=='stale_frame':node.robot_tf_received_at['tb1']=7.9
    if invalid=='future':node.robot_tf_received_at['tb1']=10.1
    if invalid=='nan':node.robot_positions['tb1']=(float('nan'),3.)
    if invalid=='phase':node.task_state='RALLY'
    c.HeadquartersControl.record_initial_search_visit(node,'tb1')
    assert bool(node.initial_search_visits)==(invalid=='valid')
    if invalid=='valid':
        row=next(iter(node.initial_search_visits.values()))
        assert row['position']==[2.,3.] and row['pose_source_time']==9. and row['frame_source_time']==9.5
        node.robot_positions['tb1']=(2.1,3.1)
        c.HeadquartersControl.record_initial_search_visit(node,'tb1')
        assert len(node.initial_search_visits)==1


@pytest.mark.parametrize('visual,success,prefix,preempted,next_visual',[
    (False,True,False,False,True),(True,True,False,False,False),
    (True,True,True,False,True),(False,True,True,False,False),
    (True,False,False,True,True),(True,False,False,False,False)])
def test_search_alternates_only_after_full_viewpoint_success(visual,success,prefix,preempted,next_visual):
    goal=assignment(8.,3.);goal=c.Assignment(goal.viewpoint,goal.x,goal.y,goal.path_distance_m,
        goal.utility,2. if prefix else goal.x,goal.y)
    node=finish_node(goal,preempted=preempted)
    node.enable_rally=True
    node.initial_search_next={'tb1':visual};node.initial_search_goals={'tb1':visual}
    c.HeadquartersControl.finish_goal(node,'tb1',success)
    assert node.initial_search_next['tb1']==next_visual


@pytest.mark.parametrize('energy',[80.,10.])
def test_known_space_purpose_keeps_full_return_admission_and_charging(monkeypatch,energy):
    node,requests,_,sent=charge_node();node.robot_states['tb2']='active'
    node.enable_rally=True
    node.battery_states['tb1']['energy']=energy;node.battery_states['tb2']['energy']=80.
    node.robot_tf_received_at=dict.fromkeys(node.robot_positions,10.)
    node.initial_search_next={'tb1':True};node.initial_search_goals={};node.initial_search_visits={}
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.,utility=10000.)]})
    c.HeadquartersControl.assign_idle_robots(node)
    if energy==80.:
        assert sent and not requests and node.initial_search_goals['tb1']
        f=node.exploration_travel_choices['tb1'];assert f['search_kind']=='known_space'
        assert f['required_energy']<energy and f['nominal_blocked_positions']==[node.robot_positions['tb2']]
        a=sent[0][1]
        if math.dist((a.x,a.y),(a.navigation_x,a.navigation_y))<=c.NAVIGATION_POSITION_TOLERANCE_M:
            assert a.navigation_yaw==f['view_yaw']
    else:
        # The accepted peer action drains before serial charging; no unfunded dispatch.
        assert not sent and not requests
        node.robot_states['tb2']='idle';node.battery_modes['tb2']='CHARGING'
        c.HeadquartersControl.assign_idle_robots(node)
        assert not sent


def test_empty_known_space_interest_falls_back_to_original_mapping(monkeypatch):
    node,requests,_,sent=charge_node();node.battery_states['tb1']['energy']=80.
    node.enable_rally=True
    node.robot_states['tb2']='active';node.battery_states['tb2']['energy']=80.
    node.initial_search_next={'tb1':True};node.initial_search_goals={};node.initial_search_visits={}
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:[])
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    c.HeadquartersControl.assign_idle_robots(node)
    assert sent and not requests and not node.initial_search_goals['tb1']


def test_visual_endpoints_keep_original_clearance_and_preserve_final_yaw():
    grid=np.zeros((80,100),dtype=int);grid[:,65:68]=100
    rows=c.known_space_search_candidates(grid,.1,(0.,0.),'tb1',(2.,3.),[(2.,3.)],face_interest=True)
    assert rows
    safe=c.traversable_grid(grid,.1,c.ROBOT_CLEARANCE_M)
    for _,_,_,a in rows:
        assert safe[a.viewpoint.row,a.viewpoint.column] and a.navigation_yaw is not None


def test_mapping_only_mode_keeps_original_frontier_dispatch(monkeypatch):
    node,requests,_,sent=charge_node();node.enable_rally=False
    node.battery_states['tb1']['energy']=80.;node.robot_states['tb2']='active'
    node.battery_states['tb2']['energy']=80.
    node.initial_search_next={'tb1':True};node.initial_search_visits=None;node.initial_search_goals={}
    monkeypatch.setattr(c,'known_space_search_candidates',lambda *a,**k:pytest.fail('mapping-only search changed'))
    install_candidates(monkeypatch,{'tb1':[assignment(4.,3.)]})
    c.HeadquartersControl.assign_idle_robots(node)
    assert sent and not requests and not node.initial_search_goals['tb1']


def test_real_known_candidate_passes_navigation_publication_and_independent_reader():
    from check_p2c_gate import exploration_travel_audit
    node,requests,decisions,_=charge_node();node.enable_rally=True
    node.robot_states['tb2']='active';node.source_map_data=node.map_data
    for state in node.battery_states.values():state.update(energy=80.,mode='ACTIVE',stamp_sec=10.)
    node.robot_tf_received_at=dict.fromkeys(node.robot_positions,10.)
    node.initial_search_next={'tb1':True};node.initial_search_visits={};node.initial_search_goals={}
    node.input_freshness_details=lambda:{'headquarters/fused_map_snapshot':dict(source_time=10.,age_sec=0.,ttl_sec=5.),
        **{name+'/'+kind:dict(source_time=10.,age_sec=0.,ttl_sec=ttl)
           for name in node.robot_positions for kind,ttl in (('pose_state',2.),('frame_state',2.),('battery_state',5.))}}
    def publish(name,a):
        goal=PoseStamped();goal.pose.position.x=a.navigation_x;goal.pose.position.y=a.navigation_y
        yaw=a.navigation_yaw or 0.;goal.pose.orientation.z=math.sin(yaw/2.);goal.pose.orientation.w=math.cos(yaw/2.)
        c.HeadquartersControl.record_navigation_decision(node,name,'initial_visual_search',goal)
    node.send_goal=publish
    c.HeadquartersControl.assign_idle_robots(node)
    assert not requests and len(decisions)==1
    assert type(decisions[0]['travel_preference']['frontier_group_id']) is int
    assert exploration_travel_audit(decisions,True,True,True,True)['initial_visual_witnesses']==1


def visual_event():
    e=travel_event();e['kind']='initial_visual_search';f=e['travel_preference']
    grid=np.frombuffer(zlib.decompress(base64.b64decode(e['planning_map']['grid'])),
        dtype='<i2').reshape(e['planning_map']['shape'])
    cell=c.world_to_grid(*f['target'],.1,0.,0.)
    visits=[dict(source='ap_delivered_pose_history',robot='tb1',position=[2.1,3.1],
        observed_at_sec=9.,pose_source_time=8.5,frame_source_time=8.7)]
    interest=c.known_search_interest(grid,.1,(0.,0.),[v['position'] for v in visits]+list(e['robot_positions'].values()))
    gain,yaw=c.known_search_view(grid,cell,c.INFORMATION_RADIUS_M/.1,interest)
    assert gain>0
    f.update(search_kind='known_space',initial_search_visits=visits,view_yaw=yaw,
        information_gain=gain,frontier_group_id=cell[0]*grid.shape[1]+cell[1],frontier_group_size=1,
        nominal_blocked_positions=f['blocked_positions'],excluded_targets=[],continuation_weight=1.)
    assert f['own_nominal_distance_m']==f['planned_distance_m']
    f['base_utility']=gain/(f['own_nominal_distance_m']+1.)
    f['adjusted_utility']=f['base_utility']*f['factor']
    f['scheduling_score']=f['adjusted_utility']
    e.update(requested_position=f['target'],requested_yaw=yaw)
    return e


@pytest.mark.parametrize('bad',[None,'gain','yaw','dispatched_yaw','source','stale_pose',
    'stale_frame','future','duplicate','group','unmasked','base','undeclared'])
def test_visual_witness_rebuilds_known_sight_orientation_and_delivered_history(bad):
    from check_p2c_gate import exploration_travel_audit
    e=copy.deepcopy(visual_event());f=e['travel_preference'];visit=f['initial_search_visits'][0]
    if bad=='gain':f['information_gain']+=1
    if bad=='yaw':f['view_yaw']+=.1
    if bad=='dispatched_yaw':e['requested_yaw']+=.1
    if bad=='source':visit['source']='native_truth'
    if bad=='stale_pose':visit['pose_source_time']=6.
    if bad=='stale_frame':visit['frame_source_time']=6.
    if bad=='future':visit['observed_at_sec']=11.
    if bad=='duplicate':f['initial_search_visits'].append(copy.deepcopy(visit))
    if bad=='group':f['frontier_group_id']+=1
    if bad=='unmasked':f['nominal_blocked_positions']=[]
    if bad=='base':f['base_utility']+=1.
    if bad is None:
        assert exploration_travel_audit([e],True,True,True,True)['initial_visual_witnesses']==1
    else:
        with pytest.raises((AssertionError,KeyError)):
            exploration_travel_audit([e],True,True,True,bad!='undeclared')
