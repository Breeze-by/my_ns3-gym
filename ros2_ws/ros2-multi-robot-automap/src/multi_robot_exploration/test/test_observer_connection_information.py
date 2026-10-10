"""Observer mapping and conservative peer reinspection share the existing guards."""
import copy
import gzip
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from rclpy.time import Time
from multi_robot_exploration import control as c
from p2c_outbound_routes import decode
from p2c_preparation_approach import audit_preparation, preparation_approach_audit
from p2c_observer_information import observer_information_audit
from check_p2c_gate import target_survey_audit
from test_target_information_survey import survey_node
from test_rally_preparation import node as preparation_fixture


def original():
    path=Path(__file__).parent/'fixtures/p2c_v78_observer_connection.json.gz'
    saved=json.load(gzip.open(path,'rt'))
    assert saved['source_ref']=='41407f2a55a918f794091fbbb928c2ac516249cc'
    return saved


def apply_snapshot(node,event):
    node.clock=[event['event_time']];node.now=lambda:node.clock[0]
    node.get_clock=lambda:SimpleNamespace(now=lambda:Time(seconds=node.now()))
    node.target=event['target'];node.target_observing_robot=event['observer_robot']
    node.target_received_source_time=event['inputs']['headquarters/target_detection']['source_time']
    node.robot_positions=copy.deepcopy(event['current_positions'])
    node.map_data=decode(event['planning_map']);node.source_map_data=decode(event['source_map'])
    node.resolution=event['planning_map']['resolution'];node.origin=event['planning_map']['origin']
    node.map_received_at=event['planning_map']['source_time'];node.map_self_return_cells=event['self_return_cells']
    node.robot_maps={n:dict(data=decode(g),resolution=g['resolution'],origin=g['origin']) for n,g in event['return_maps'].items()}
    node.battery_states=copy.deepcopy(event['battery_states']);node.battery_modes={n:s['mode'] for n,s in node.battery_states.items()}
    for attribute,kind in [('robot_odom_received_at','pose_state'),('robot_tf_received_at','frame_state'),
        ('robot_map_received_at','map_snapshot'),('battery_state_received_at','battery_state')]:
        setattr(node,attribute,{n:event['inputs'][n+'/'+kind]['source_time'] for n in node.robot_positions})
    node.input_freshness_details=lambda:c.HeadquartersControl.input_freshness_details(node)
    node.input_robot_names=lambda:list(node.robot_positions)
    node.message_freshness_timeout_sec=5.
    node.fresh_robot_inputs=lambda:all(0<=row['age_sec']<=row['ttl_sec'] for key,row in node.input_freshness_details().items()
        if key!='headquarters/target_detection')
    node.fresh_target=lambda:c.HeadquartersControl.fresh_target(node)
    node.participating_robots=lambda:list(node.robot_positions)


def information_node(index=0):
    saved=original();event=saved['failed_assignments'][index]
    node,client,events=survey_node();apply_snapshot(node,event)
    return node,client,events,event


@pytest.mark.parametrize('index',[0,1])
def test_original_observer_information_dispatch_is_fully_funded_and_independently_bound(tmp_path,index):
    node,client,events,failed=information_node(index);before=node.map_data.tobytes()
    assert c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions,'tb2',failed['event_time'])
    decision=next(e for e in events if e.get('kind')=='target_information_survey')
    expected=original()['observer_information']['cases'][index]['selected_event']
    assert decision['robot']=='tb1' and decision['requested_position']==expected['requested_position']
    assert decision['target_survey_selection']['choice']==expected['target_survey_selection']['choice']
    assert node.map_data.tobytes()==before and client.send_goal_async.call_count==1
    assert target_survey_audit([decision],True,3.,.35,True,True)['target_information_survey_witnesses']==1
    path=tmp_path/'ledger.jsonl';path.write_text(json.dumps(failed)+'\n'+json.dumps(decision)+'\n')
    assert observer_information_audit(path,True)['observer_information_dispatches']==1


def test_priority_is_dispatched_once_and_does_not_regenerate_the_pool(monkeypatch):
    node,client,_,failed=information_node()
    assert c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions,'tb2',failed['event_time'])
    before=node.survey_attempts
    monkeypatch.setattr(c,'target_survey_candidates',lambda *a,**k:pytest.fail('used priority regenerated candidates'))
    assert not c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions,'tb2',failed['event_time'])
    assert client.send_goal_async.call_count==1 and node.survey_attempts==before


def test_return_to_a_previous_context_does_not_dispatch_its_priority_again(monkeypatch):
    node,_,_,failed=information_node();target=node.target
    node.send_survey_goal=Mock(return_value=True)
    assert c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions,'tb2',failed['event_time'])
    node.target=[target[0]+.1,target[1]]
    assert c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions,'tb2',failed['event_time'])
    node.target=target
    monkeypatch.setattr(c,'target_survey_candidates',lambda *a,**k:pytest.fail('earlier context regenerated candidates'))
    assert not c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions,'tb2',failed['event_time'])
    assert node.send_survey_goal.call_count==2


@pytest.mark.parametrize('reason',['stale_pose','stale_target','no_battery','rally_phase','missing_observer',
    'same_observer','missing_peer','future_assignment','missing_assignment','inactive_observer','unfunded','live_survey','blocked_local'])
def test_unqualified_priority_never_spends_the_once_preference(reason):
    node,client,events,failed=information_node();peer='tb2';at=failed['event_time']
    if reason=='stale_pose':node.clock[0]+=3.
    if reason=='stale_target':node.target_received_source_time-=61.
    if reason=='no_battery':node.enable_battery=False
    if reason=='rally_phase':node.task_state='RALLY'
    if reason=='missing_observer':node.target_observing_robot=None
    if reason=='same_observer':peer='tb1'
    if reason=='missing_peer':peer='tb3'
    if reason=='future_assignment':at=node.now()+.1
    if reason=='missing_assignment':at=None
    if reason=='inactive_observer':node.battery_modes['tb1']='RETURNING'
    if reason=='unfunded':node.battery_states['tb1']['energy']=.1
    if reason=='live_survey':node.survey_goal_handle=Mock()
    if reason=='blocked_local':node.robot_maps['tb1']['data']=node.robot_maps['tb1']['data'].copy();node.robot_maps['tb1']['data'][:]=100
    assert not c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions,peer,at)
    client.send_goal_async.assert_not_called()
    assert not getattr(node,'observer_connection_information_dispatched',None)
    assert not any(e.get('kind')=='target_information_survey' for e in events)


def parallel_node(monkeypatch,index=0):
    saved=original();failed=saved['failed_assignments'][index]
    survey=copy.deepcopy(saved['observer_information']['cases'][index]['selected_event'])
    node,_=preparation_fixture(monkeypatch);apply_snapshot(node,failed)
    node.survey_robot=survey['robot'];node.survey_goal_handle=Mock()
    node.survey_leg_route=survey['outbound_map_route']['route'];node.survey_leg_source_time=survey['dispatch_goal_source_time_sec']
    return node,survey,failed


def test_original_unavailable_full_approach_can_use_a_current_funded_reinspection(monkeypatch,tmp_path):
    node,survey,_=parallel_node(monkeypatch)
    namespace=dict(vars(c));exec(compile(original()['parallel_reinspection']['original_method'],'<41407f2 original preparation>','exec'),namespace)
    namespace['prepare_rally_approaches'](node)
    assert not any(client.send_goal_async.called for client in node.robot_nav_clients.values())
    c.HeadquartersControl.prepare_rally_approaches(node)
    assert node.robot_nav_clients['tb2'].send_goal_async.call_count==1 and node.rally_attempts=={'tb1':0,'tb2':0}
    event=next(json.loads(call.args[0].data) for call in node.consumed_publisher.publish.call_args_list
        if json.loads(call.args[0].data).get('kind')=='rally_preparation_approach')
    audit_preparation(event,survey,True)
    with pytest.raises(AssertionError,match='undeclared'):audit_preparation(event,survey)
    path=tmp_path/'ledger.jsonl';path.write_text(json.dumps(survey)+'\n'+json.dumps(event)+'\n')
    assert preparation_approach_audit(path,True,None,.2,True)['decisions']==1


def test_fused_disconnected_original_still_has_no_parallel_reinspection(monkeypatch):
    node,_,_=parallel_node(monkeypatch,1)
    c.HeadquartersControl.prepare_rally_approaches(node)
    assert not any(client.send_goal_async.called for client in node.robot_nav_clients.values())
    assert not node.rally_preparation_approaches


@pytest.mark.parametrize('tamper',['cell','stage','rank','budget','wait','body','survey_overlap','source'])
def test_parallel_reader_rejects_weakened_geometry_budget_and_sources(monkeypatch,tamper):
    node,survey,_=parallel_node(monkeypatch);c.HeadquartersControl.prepare_rally_approaches(node)
    event=next(json.loads(call.args[0].data) for call in node.consumed_publisher.publish.call_args_list
        if json.loads(call.args[0].data).get('kind')=='rally_preparation_approach')
    saved=event['rally_preparation']
    if tamper=='cell':saved['connection_reinspection']['cell'][0]+=1
    if tamper=='stage':saved['stage_destination'][0]+=.1
    if tamper=='rank':saved['connection_reinspection']['fused_remaining_distance_m']-=.1
    if tamper=='budget':saved['required_energy']-=1.
    if tamper=='wait':saved['timeout_sec']=59.
    if tamper=='body':saved['robot_positions']['tb1']=event['requested_position']
    if tamper=='survey_overlap':saved['reserved_routes']=[event['outbound_map_route']['route']]
    if tamper=='source':event['outbound_map_route']['local_map']['source_time']-=1.
    with pytest.raises(AssertionError):audit_preparation(event,survey,True)


@pytest.mark.parametrize('tamper',['undeclared','missing_assignment','reason','peer','observer','target','participants','future','duplicate'])
def test_priority_reader_rejects_unbound_or_repeated_dispatches(tmp_path,tamper):
    node,_,events,failed=information_node()
    assert c.HeadquartersControl.survey_target_frontiers(node,node.robot_positions,'tb2',failed['event_time'])
    event=next(e for e in events if e.get('kind')=='target_information_survey');saved=event['target_survey_selection']['observer_connection_priority']
    if tamper=='reason':failed['geometry_diagnostics']['reason']='insufficient_candidates'
    if tamper=='peer':saved['disconnected_robot']='tb1'
    if tamper=='observer':saved['observer_robot']='tb2'
    if tamper=='target':saved['target'][0]+=.1
    if tamper=='participants':saved['participants'].pop()
    if tamper=='future':saved['assignment_evaluated_at_sec']=event['event_time']+.1
    rows=[] if tamper=='missing_assignment' else [failed]
    rows+=[event]
    if tamper=='duplicate':rows+=[event]
    path=tmp_path/'ledger.jsonl';path.write_text(''.join(json.dumps(e)+'\n' for e in rows))
    with pytest.raises(AssertionError):observer_information_audit(path,tamper!='undeclared')
