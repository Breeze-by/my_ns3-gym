"""Original occupied probe and expired coordinator confirmation regressions."""
import copy
import gzip
import json
import math
from pathlib import Path
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from std_msgs.msg import String
from multi_robot_exploration import control as c
from p2c_return_preparation import decode_grid
from test_delivered_snapshot_ingress import Receiver
from test_prepared_rally_dispatch import node as prepared_node

FIXTURE=json.load(gzip.open(Path(__file__).parent/'fixtures/p2c_v91_blocked_rally_probe.json.gz','rt'))

def original_node():
    h,clock=prepared_node();e=FIXTURE['original_event'];names=list(e['robot_positions'])
    h.robot_positions={n:tuple(p) for n,p in e['robot_positions'].items()}
    h.map_data=decode_grid(e['planning_map']);h.resolution=e['planning_map']['resolution'];h.origin=e['planning_map']['origin']
    h.map_self_return_cells=e['planning_map_self_return_cells']
    h.robot_maps={n:dict(data=decode_grid(g),resolution=g['resolution'],origin=g['origin']) for n,g in e['return_maps'].items()}
    h.battery_states=copy.deepcopy(e['battery_states']);h.battery_modes=dict(e['battery_modes'])
    h.target=tuple(FIXTURE['original_hint']['target']);h.target_observing_robot='tb1'
    h.rally_targets={n:c.RallyPose(*p) for n,p in e['targets'].items()}
    h.rally_final_targets={n:c.RallyPose(*p) for n,p in e['final_targets'].items()}
    h.rally_dispatch_order=e['dispatch_order'][:];h.rally_arrived=dict(e['arrived'])
    h.rally_charge_requested={};h.defer_action_done_callback=Mock()
    # Controlled fresh epoch; original geometry/models/energy remain intact.
    h.map_received_at=h.target_received_source_time=clock[0]
    for attr in ('robot_map_received_at','robot_odom_received_at','robot_tf_received_at','battery_state_received_at'):
        setattr(h,attr,dict.fromkeys(names,clock[0]))
    for state in h.battery_states.values():state['stamp_sec']=clock[0]
    return h,clock

def body_probe(h):
    blocked=[p for n,p in h.robot_positions.items() if n!='tb3']
    return c.rally_survey_pose(h.map_data,h.resolution,h.origin,h.robot_positions['tb3'],h.target,
        local_map=h.robot_maps['tb3'],blocked_positions=blocked)

def test_original_occupied_point_and_body_aware_complete_plan():
    h,_=original_node();old=c.rally_survey_pose(h.map_data,h.resolution,h.origin,h.robot_positions['tb3'],h.target,local_map=h.robot_maps['tb3'])
    assert (old.x,old.y,old.yaw)==pytest.approx(FIXTURE['results']['frozen']['point'])
    blocked=[p for n,p in h.robot_positions.items() if n!='tb3']
    old_plan=c.plan_rally_leg(old,h.map_data,h.resolution,h.origin,h.robot_positions['tb3'],c.MAX_NAVIGATION_LEG_M,
        blocked_positions=blocked,visible_only=False,local_map=h.robot_maps['tb3'])
    assert old_plan[0] is None
    point=body_probe(h)
    assert (point.x,point.y,point.yaw)==pytest.approx(FIXTURE['results']['prototype']['point'])
    plan=c.plan_rally_leg(point,h.map_data,h.resolution,h.origin,h.robot_positions['tb3'],c.MAX_NAVIGATION_LEG_M,
        blocked_positions=blocked,visible_only=False,local_map=h.robot_maps['tb3'])
    assert plan[0] is not None and plan[1]
    assert (plan[0].x,plan[0].y,plan[0].yaw)==pytest.approx(FIXTURE['results']['prototype']['goal'])

def test_no_probe_when_every_known_cell_is_body_blocked():
    raw=np.zeros((12,12),dtype=np.int8)
    bodies=[c.grid_to_world(row,col,1.,0.,0.) for row in range(12) for col in range(12)]
    assert c.rally_survey_pose(raw,1.,(0.,0.),(1.5,1.5),(9.5,9.5),blocked_positions=bodies) is None

def test_new_probe_passes_original_sender_and_full_energy_budget():
    h,_=original_node();point=body_probe(h)
    assert h.send_survey_goal('tb3',point)
    goal=h.robot_nav_clients['tb3'].send_goal_async.call_args.args[0].pose
    distance=sum(math.dist(a,b) for a,b in zip(h.survey_leg_route,h.survey_leg_route[1:]))
    required=h.exploration_required_energy('tb3',distance,(goal.pose.position.x,goal.pose.position.y))
    assert required is not None and required<h.battery_states['tb3']['energy']
    assert h.survey_attempts==1 and h.survey_goal_pending

@pytest.mark.parametrize('condition',['stale','future','unfunded','body','return','server'])
def test_original_sender_guards_still_reject(condition):
    h,clock=original_node();point=body_probe(h)
    if condition=='stale':clock[0]+=3.
    elif condition=='future':h.robot_tf_received_at['tb3']=clock[0]+1.
    elif condition=='unfunded':h.battery_states['tb3']['energy']=0.
    elif condition=='body':h.robot_positions['tb2']=(point.x,point.y)
    elif condition=='return':h.rally_charge_requested['tb2']=clock[0]
    elif condition=='server':h.robot_nav_clients['tb3'].server_is_ready.return_value=False
    assert not h.send_survey_goal('tb3',point)
    h.robot_nav_clients['tb3'].send_goal_async.assert_not_called()

def confirmation_receiver(phase='FOUND'):
    h=SimpleNamespace(task_state=phase,target=(-4.5,-.5),target_received_source_time=1.1,
        target_observer_confirmations={},robot_positions=dict.fromkeys(('tb1','tb2','tb3'),(0.,0.)),
        now=lambda:66.1,enable_rally=True,consumed_publisher=Mock(),get_logger=lambda:Mock())
    h.target_detection_callback=MethodType(c.HeadquartersControl.target_detection_callback,h)
    h.fresh_target=MethodType(c.HeadquartersControl.fresh_target,h)
    receiver=Receiver();receiver.subscribe('target',h.target_detection_callback)
    return h,receiver

def confirmation(source=66.,target=(-4.5,-.5)):
    return String(data=json.dumps(dict(robot='tb2',target_x=target[0],target_y=target[1],
        max_distance_m=3.,field_of_view_deg=90.,stamp_sec=source,
        _gateway=dict(source_time=source,delivery_time=source,message_id='controlled_target'))))

def test_confirmation_applies_at_entry_without_renewing_old_lease():
    h,r=confirmation_receiver();lease=h.target_received_source_time;message=confirmation()
    r.receive('target',message)
    assert h.target_received_source_time==lease and not h.fresh_target()
    r.drain()
    assert h.target_received_source_time==66. and h.fresh_target()
    assert lease==1.1 and h.now()-lease>c.TARGET_DETECTION_TTL_SEC
    event=json.loads(h.consumed_publisher.publish.call_args.args[0].data)
    assert event['source_time']==66. and event['event']=='target_reconfirmed'
    assert json.loads(message.data)['_gateway']['source_time']==66.

@pytest.mark.parametrize('condition',['stale','future','duplicate','changed','complete'])
def test_queued_confirmation_cannot_bypass_original_guards(condition):
    h,r=confirmation_receiver('COMPLETE' if condition=='complete' else 'FOUND')
    message=confirmation(1.1 if condition in ('stale','duplicate') else 69. if condition=='future' else 66.,
        (-4.4,-.5) if condition=='changed' else (-4.5,-.5))
    if condition=='duplicate':h.now=lambda:2.
    r.receive('target',message);r.drain()
    assert h.target_received_source_time==1.1 and h.target==(-4.5,-.5)
    h.consumed_publisher.publish.assert_not_called()
