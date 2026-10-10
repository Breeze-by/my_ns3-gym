import copy
import gzip
import json
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import pytest
from rclpy.task import Future
from rclpy.time import Time

from multi_robot_exploration import control as c
from p2c_outbound_routes import decode
from p2c_preparation_approach import preparation_approach_audit
from p2c_preparation_approach import bind_original_positions


def original():
    with gzip.open(Path(__file__).with_name('fixtures')/'p2c_v68_preparation_inputs.json.gz','rt') as f:
        return json.load(f)


def node(monkeypatch):
    data=original();failed=data['failed_assignment'];survey=data['original_survey']
    now=[survey['event_time']];names=sorted(failed['robot_positions']);maps=failed['return_maps']
    n=SimpleNamespace(enable_battery=True,enable_rally=True,task_state='FOUND',
        now=lambda:now[0],clock=now,survey_robot=survey['robot'],target_observing_robot=survey['robot'],
        survey_heading_only=False,survey_cancel_requested=False,survey_goal_handle=Mock(),survey_goal_pending=False,
        survey_leg_route=survey['outbound_map_route']['route'],survey_leg_source_time=survey['dispatch_goal_source_time_sec'],
        survey_attempts=1,rally_preparation_approaches={},robot_positions=copy.deepcopy(failed['robot_positions']),
        robot_states={k:'idle' for k in names},goal_handles={k:None for k in names},
        rally_goal_handles={k:None for k in names},rally_goal_pending={k:False for k in names},
        rally_leg_routes={k:() for k in names},rally_leg_poses={},rally_goal_started_at={k:None for k in names},
        rally_yield_requested={k:False for k in names},rally_battery_preempted={k:False for k in names},
        rally_targets={},rally_final_targets={},return_yield_targets={},rally_charge_requested={},
        target=failed['target'],target_received_source_time=survey['inputs']['headquarters/target_detection']['source_time'],
        battery_states=copy.deepcopy(failed['battery_states']),battery_modes={k:'ACTIVE' for k in names},
        rally_attempts={k:0 for k in names},rally_max_retries=2,rally_position_tolerance=.35,goal_timeout_sec=60.,
        map_data=decode(failed['planning_map']),resolution=failed['planning_map']['resolution'],origin=failed['planning_map']['origin'],
        map_received_at=failed['planning_map']['source_time'],
        robot_maps={k:dict(data=decode(v),resolution=v['resolution'],origin=v['origin']) for k,v in maps.items()},
        robot_map_received_at={k:v['source_time'] for k,v in maps.items()},
        robot_odom_received_at={k:survey['inputs'][k+'/pose_state']['source_time'] for k in names},
        robot_tf_received_at={k:survey['inputs'][k+'/frame_state']['source_time'] for k in names},
        robot_nav_clients={k:Mock() for k in names},consumed_publisher=Mock(),get_logger=lambda:Mock())
    n.participating_robots=lambda:names
    n.get_clock=lambda:SimpleNamespace(now=lambda:Time(seconds=n.now()))
    n.input_freshness_details=lambda:copy.deepcopy(survey['inputs'])
    n.fresh_robot_inputs=lambda:all(0<=n.now()-v['source_time']<=v['ttl_sec'] for k,v in n.input_freshness_details().items() if k!='headquarters/target_detection')
    n.fresh_target=MethodType(c.HeadquartersControl.fresh_target,n)
    n.send_rally_goal=MethodType(c.HeadquartersControl.send_rally_goal,n)
    n.record_navigation_decision=MethodType(c.HeadquartersControl.record_navigation_decision,n)
    monkeypatch.setattr(c.HeadquartersControl,'defer_action_done_callback',lambda *args:None)
    for client in n.robot_nav_clients.values():client.server_is_ready.return_value=True
    return n,data


def ledger(n,path):
    path.write_text(''.join(call.args[0].data+'\n' for call in n.consumed_publisher.publish.call_args_list))


def test_original_reserved_and_funded_preparation_keeps_all_original_counters(monkeypatch,tmp_path):
    n,data=node(monkeypatch);before=n.map_data.tobytes()
    c.HeadquartersControl.prepare_rally_approaches(n)
    n.robot_nav_clients['tb1'].send_goal_async.assert_not_called()
    assert n.robot_nav_clients['tb2'].send_goal_async.call_count==1
    assert n.rally_attempts=={'tb1':0,'tb2':0} and n.survey_attempts==1 and not n.rally_targets
    c.HeadquartersControl.prepare_rally_approaches(n)
    assert n.robot_nav_clients['tb2'].send_goal_async.call_count==1 and n.map_data.tobytes()==before
    event=json.loads(n.consumed_publisher.publish.call_args_list[0].args[0].data)
    assert event['rally_preparation']['path_distance_m']==pytest.approx(data['conditional_geometry']['path_distance_m'])
    assert event['rally_preparation']['required_energy']==pytest.approx(data['conditional_geometry']['required_energy'])
    p=tmp_path/'ledger.jsonl';survey=data['original_survey'];p.write_text(json.dumps(survey)+'\n'+json.dumps(event)+'\n')
    assert preparation_approach_audit(p,True)['decisions']==1


@pytest.mark.parametrize('reason',['pose_expired','target_expired','no_battery','rally_phase','heading_only','different_observer',
    'canceled_survey','no_survey','partial_assignment','charge_requested','returning','charging','failed','shutdown',
    'unfunded','unavailable_server','blocked_map','blocked_local','shared_survey_corridor'])
def test_preparation_rejects_unqualified_or_conflicting_state(monkeypatch,reason):
    n,_=node(monkeypatch)
    if reason=='pose_expired':n.clock[0]+=3.
    elif reason=='target_expired':n.target_received_source_time-=61.
    elif reason=='no_battery':n.enable_battery=False
    elif reason=='rally_phase':n.task_state='RALLY'
    elif reason=='heading_only':n.survey_heading_only=True
    elif reason=='different_observer':n.target_observing_robot='tb2'
    elif reason=='canceled_survey':n.survey_cancel_requested=True
    elif reason=='no_survey':n.survey_goal_handle=None
    elif reason=='partial_assignment':n.rally_targets={'tb1':c.RallyPose(0.,0.,0.)}
    elif reason=='charge_requested':n.rally_charge_requested['tb2']=n.now()
    elif reason in ('returning','charging','failed'):n.battery_modes['tb2']=reason.upper()
    elif reason=='shutdown':n.shutdown_requested=True
    elif reason=='unfunded':n.battery_states['tb2']['energy']=.1
    elif reason=='unavailable_server':n.robot_nav_clients['tb2'].server_is_ready.return_value=False
    elif reason=='blocked_map':n.map_data=n.map_data.copy();n.map_data[:]=100
    elif reason=='blocked_local':
        n.robot_maps['tb2']['data']=n.robot_maps['tb2']['data'].copy();n.robot_maps['tb2']['data'][:]=100
    else:n.survey_leg_route=[n.robot_positions['tb2'],n.survey_leg_route[-1]]
    c.HeadquartersControl.prepare_rally_approaches(n)
    assert not n.rally_preparation_approaches and not any(n.rally_goal_pending.values())
    for client in n.robot_nav_clients.values():client.send_goal_async.assert_not_called()
    assert n.rally_attempts=={'tb1':0,'tb2':0} and n.survey_attempts==1


def test_private_publication_cannot_extend_old_sources(monkeypatch):
    n,_=node(monkeypatch);n.consumed_publisher.publish.side_effect=lambda msg:n.clock.__setitem__(0,n.now()+3.)
    c.HeadquartersControl.prepare_rally_approaches(n)
    n.robot_nav_clients['tb2'].send_goal_async.assert_not_called()
    assert not n.rally_preparation_approaches and n.rally_attempts['tb2']==0


def test_pending_preparation_is_canceled_on_late_acceptance_then_consumed(monkeypatch,tmp_path):
    n,data=node(monkeypatch);c.HeadquartersControl.prepare_rally_approaches(n)
    assert c.HeadquartersControl.stop_rally_preparation(n) and n.rally_yield_requested['tb2']
    handle=Mock();handle.accepted=True;response=Future();response.set_result(handle)
    n.survey_goal_handle=None
    c.HeadquartersControl.rally_goal_response(n,'tb2',response)
    handle.cancel_goal_async.assert_called_once();assert not n.rally_goal_pending['tb2']
    result=Future();result.set_result(SimpleNamespace(status=5))
    c.HeadquartersControl.rally_goal_result(n,'tb2',handle,result)
    assert not c.HeadquartersControl.stop_rally_preparation(n) and n.rally_attempts['tb2']==0
    assert n.rally_goal_handles['tb2'] is None and not n.rally_leg_routes['tb2']
    p=tmp_path/'ledger.jsonl';ledger(n,p);p.write_text(json.dumps(data['original_survey'])+'\n'+p.read_text())
    assert preparation_approach_audit(p,True)['closed_futures']==1


@pytest.mark.parametrize('failure',['rejected','exception'])
def test_preparation_response_failure_closes_without_spending_rally_retries(monkeypatch,failure):
    n,_=node(monkeypatch);c.HeadquartersControl.prepare_rally_approaches(n);response=Future()
    if failure=='rejected':response.set_result(None)
    else:response.set_exception(RuntimeError('synthetic response failure'))
    c.HeadquartersControl.rally_goal_response(n,'tb2',response)
    assert not n.rally_goal_pending['tb2'] and n.rally_attempts['tb2']==0
    assert json.loads(n.consumed_publisher.publish.call_args.args[0].data)['event']=='coordinator_rally_preparation_finished'


@pytest.mark.parametrize('forgery',['required','energy','wait','path_length','body_mode','body_overlap',
    'survey_robot','survey_source','survey_route','survey_reservation','target','stage_destination',
    'repeated','rally_before_closed','finished_source'])
def test_independent_reader_rejects_unqualified_preparation(monkeypatch,tmp_path,forgery):
    n,data=node(monkeypatch);c.HeadquartersControl.prepare_rally_approaches(n)
    e=json.loads(n.consumed_publisher.publish.call_args.args[0].data);s=e['rally_preparation'];events=[data['original_survey'],e]
    if forgery=='required':s['required_energy']-=1.
    elif forgery=='energy':s['available_energy']+=1.
    elif forgery=='wait':s['timeout_sec']=59.
    elif forgery=='path_length':s['path_distance_m']-=1.
    elif forgery=='body_mode':s['battery_states']['tb1']['mode']='RETURNING'
    elif forgery=='body_overlap':s['robot_positions']['tb1']=e['outbound_map_route']['route'][2]
    elif forgery=='survey_robot':s['survey_robot']='tb2'
    elif forgery=='survey_source':s['survey_goal_source_time_sec']-=1e-6
    elif forgery=='survey_route':s['original_survey_route'][1][0]+=.01
    elif forgery=='survey_reservation':s['survey_reservation'][1][0]+=.01
    elif forgery=='target':s['target'][0]+=.01
    elif forgery=='stage_destination':s['stage_destination'][0]+=.01
    elif forgery=='repeated':events.append(copy.deepcopy(e))
    elif forgery=='rally_before_closed':events.append(dict(event='coordinator_navigation_decision',kind='rally'))
    else:events.append(dict(event='coordinator_rally_preparation_finished',robot='tb2',goal_source_time_sec=e['event_time']+1e-6))
    p=tmp_path/'ledger.jsonl';p.write_text(''.join(json.dumps(row)+'\n' for row in events))
    with pytest.raises((AssertionError,KeyError)):preparation_approach_audit(p,True)


def test_source_binding_allows_only_header_nanosecond_conversion(monkeypatch,tmp_path):
    n,data=node(monkeypatch);c.HeadquartersControl.prepare_rally_approaches(n)
    e=json.loads(n.consumed_publisher.publish.call_args.args[0].data)
    e['rally_preparation']['survey_goal_source_time_sec']-=1e-9
    p=tmp_path/'ledger.jsonl';p.write_text('\n'.join(json.dumps(row) for row in [data['original_survey'],e,
        dict(event='coordinator_rally_preparation_finished',robot='tb2',goal_source_time_sec=e['event_time']-1e-9)])+'\n')
    assert preparation_approach_audit(p,True)['closed_futures']==1


def test_body_witness_must_bind_original_pose_and_frame_cdr(monkeypatch,tmp_path):
    import base64
    from geometry_msgs.msg import TransformStamped
    from nav_msgs.msg import Odometry
    from tf2_msgs.msg import TFMessage
    from rclpy.serialization import serialize_message
    n,_=node(monkeypatch);c.HeadquartersControl.prepare_rally_approaches(n)
    e=json.loads(n.consumed_publisher.publish.call_args.args[0].data);raw=[]
    for name,point in e['rally_preparation']['robot_positions'].items():
        for suffix,kind in [('odom','pose_state'),('tf','frame_state')]:
            ns=round(e['inputs'][name+'/'+kind]['source_time']*1e9)+(200000000 if suffix=='tf' else 0)
            if suffix=='odom':
                msg=Odometry();msg.pose.pose.position.x,msg.pose.pose.position.y=point;dest=msg.header.stamp
            else:
                t=TransformStamped();t.header.frame_id='map';t.child_frame_id=name+'/odom';t.transform.rotation.w=1.
                msg=TFMessage(transforms=[t]);dest=t.header.stamp
            dest.sec,dest.nanosec=divmod(ns,10**9)
            raw.append(dict(topic='/'+name+'/'+suffix,cdr=base64.b64encode(serialize_message(msg)).decode()))
    capture=tmp_path/'raw.jsonl.gz'
    with gzip.open(capture,'wt') as f:f.write(''.join(json.dumps(row)+'\n' for row in raw))
    assert bind_original_positions([e],capture,.2)==4
    bad=copy.deepcopy(e);bad['rally_preparation']['robot_positions']['tb1'][0]+=.01
    with pytest.raises(AssertionError):bind_original_positions([bad],capture,.2)
    with pytest.raises(AssertionError):bind_original_positions([e],capture,0.)
