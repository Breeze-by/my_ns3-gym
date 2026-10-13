"""Reject forged heading budgets and typed source evidence; no physics credit."""
import base64
import copy
import gzip
import json
import math

import numpy as np
import pytest
from geometry_msgs.msg import TransformStamped
from nav_msgs.msg import OccupancyGrid, Odometry
from rclpy.serialization import serialize_message
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration import control
from p2c_global_audit import audit_motion, bind_sources, contact, geometry_world, global_mission_audit, scalar_budget


def stamp(header, seconds):
    header.stamp.sec = int(seconds)
    header.stamp.nanosec = round((seconds-int(seconds))*1e9)


def fixture():
    grid = OccupancyGrid()
    stamp(grid.header, 9.5)
    grid.info.width = grid.info.height = 80
    grid.info.resolution = float(np.float32(.1))
    grid.info.origin.orientation.w = 1.
    grid.data = [0]*6400
    raw = np.asarray(grid.data, dtype=np.int16).reshape((80, 80))
    resolution = grid.info.resolution
    source = control.grid_audit_evidence(raw, resolution, (0., 0.), 'ap_delivered_fused_map', 9.5, 9.5)
    planned = {**source, 'source': 'ap_delivered_planning_map'}
    local = {**source, 'source': 'ap_delivered_robot_map'}
    odom = Odometry()
    stamp(odom.header, 9.8)
    odom.pose.pose.position.x = odom.pose.pose.position.y = 1.
    odom.pose.pose.orientation.z = math.sin(1.2/2)
    odom.pose.pose.orientation.w = math.cos(1.2/2)
    frame = TransformStamped()
    stamp(frame.header, 9.7)
    frame.header.frame_id, frame.child_frame_id = 'map', 'odom'
    frame.transform.translation.x = frame.transform.translation.y = 2.
    frame.transform.rotation.z = math.sin(.3/2)
    frame.transform.rotation.w = math.cos(.3/2)
    position = (2.+math.cos(.3)-math.sin(.3), 2.+math.sin(.3)+math.cos(.3))
    state = dict(mode='ACTIVE', stamp_sec=9.5, energy=80., capacity=100., charge_target_fraction=.8,
        charge_x=position[0], charge_y=position[1], charge_radius_m=.8, move_cost_per_m=1.,
        idle_cost_per_sec=.02, return_path_factor=2., nominal_speed_mps=.18,
        return_safety_margin=8., charge_duration_sec=6.)
    target = (position[0]+1.5, position[1])
    world = dict(source_map=source, planning_map=planned, self_return_cells={},
        return_maps={'tb1':local}, positions={'tb1':position}, yaws={'tb1':1.5},
        battery_states={'tb1':state}, sources={'headquarters/fused_map_snapshot':9.5,
            'tb1/map_snapshot':9.5, 'tb1/pose_state':9.8, 'tb1/frame_state':9.7,
            'tb1/battery_state':9.5, 'headquarters/target_detection':4.},
        required=['tb1'], target=target, observer='tb1', confirmations={'tb1':4.},
        live_routes={}, charge_pending=[], target_fov_rad=math.pi/2, goal_timeout_sec=60.)
    event = dict(robot='tb1', kind='target_observation_heading', route=[position],
        complete_task_route=[position], requested_position=position, requested_yaw=0.,
        world=world, event_time=10., budget_evaluated_at_sec=9.9, waiting_time_budget_sec=60.)
    grid_data, maps = geometry_world(event)
    event['required_energy'] = scalar_budget(event, grid_data, maps, [position], position, 60.)
    detection = dict(robot='tb1', target_x=target[0], target_y=target[1], stamp_sec=4.,
        max_distance_m=3., field_of_view_deg=90., _gateway={'source_time':4.})
    rows = [('/merge_map', grid), ('/gateway/received/tb1/map', grid),
        ('/gateway/received/tb1/odom', odom), ('/tb1/odom', copy.deepcopy(odom)),
        ('/gateway/received/tb1/tf', TFMessage(transforms=[frame])),
        ('/tb1/tf', TFMessage(transforms=[copy.deepcopy(frame)])),
        ('/gateway/received/tb1/battery_state', String(data=json.dumps(state))),
        ('/gateway/received/target_detection', String(data=json.dumps(detection)))]
    return event, rows, state, detection


@pytest.mark.parametrize('corruption', [None, 'translation', 'hidden_translation', 'wrong_heading',
    'already_aligned', 'fresh_self', 'missing_self', 'future_confirmation', 'fresh_alternate',
    'not_observer', 'charge_pending', 'owned', 'returning', 'missing_wait', 'short_timer',
    'wrong_fov', 'far_target', 'stale_map', 'stale_pose', 'stale_frame', 'stale_battery',
    'stale_target', 'future_target', 'unfunded', 'unsafe_cell', 'near_peer'])
def test_stationary_heading_audit_rebuilds_original_contract(corruption):
    event, _, _, _ = fixture()
    world = event['world']
    if corruption == 'translation':
        event['route'][-1] = event['requested_position'] = (4., 4.)
    if corruption == 'hidden_translation': event['complete_task_route'].insert(0, (4., 4.))
    if corruption == 'wrong_heading': event['requested_yaw'] = .1
    if corruption == 'already_aligned': world['yaws']['tb1'] = 0.
    if corruption == 'fresh_self': world['confirmations']['tb1'] = 5.
    if corruption == 'missing_self': world['confirmations'].clear()
    if corruption == 'future_confirmation': world['confirmations']['tb1'] = 11.
    if corruption == 'fresh_alternate': world['confirmations']['tb2'] = 9.
    if corruption == 'not_observer': world['observer'] = 'tb2'
    if corruption == 'charge_pending': world['charge_pending'] = ['tb1']
    if corruption == 'owned': world['live_routes']['tb1'] = event['route']
    if corruption == 'returning': world['battery_states']['tb1']['mode'] = 'RETURNING'
    if corruption == 'missing_wait':
        event['waiting_time_budget_sec'] = 0.
        grid, maps = geometry_world(event)
        event['required_energy'] = scalar_budget(event, grid, maps, event['route'], event['requested_position'])
    if corruption == 'short_timer': world['goal_timeout_sec'] = event['waiting_time_budget_sec'] = 30.
    if corruption == 'wrong_fov': world['target_fov_rad'] = math.pi
    if corruption == 'far_target': world['target'] = (7., 7.)
    if corruption == 'stale_map': world['sources']['tb1/map_snapshot'] = 4.
    if corruption == 'stale_pose': world['sources']['tb1/pose_state'] = 7.9
    if corruption == 'stale_frame': world['sources']['tb1/frame_state'] = 7.9
    if corruption == 'stale_battery': world['sources']['tb1/battery_state'] = 4.
    if corruption == 'stale_target': world['sources']['headquarters/target_detection'] = -50.1
    if corruption == 'future_target': world['sources']['headquarters/target_detection'] = 10.1
    if corruption == 'unfunded': world['battery_states']['tb1']['energy'] = event['required_energy']
    if corruption == 'unsafe_cell':
        raw = np.zeros((80, 80), dtype=np.int16)
        row, col = control.world_to_grid(*world['positions']['tb1'], world['planning_map']['resolution'], 0., 0.)
        raw[row, col+1] = 100
        for name in ('source_map', 'planning_map'):
            old = world[name]
            world[name] = control.grid_audit_evidence(raw, old['resolution'], old['origin'], old['source'], 9.5, 9.5)
    if corruption == 'near_peer': world['positions']['tb2'] = (world['positions']['tb1'][0]+.2, world['positions']['tb1'][1])
    if corruption is None:
        assert audit_motion(event) == 1
    else:
        with pytest.raises(AssertionError): audit_motion(event)


def write_sources(tmp_path, rows, state):
    capture = tmp_path/'navigation_inputs.jsonl.gz'
    with gzip.open(capture, 'wt') as stream:
        for topic, message in rows:
            received = 4. if topic.endswith('/target_detection') else 9.9
            stream.write(json.dumps(dict(topic=topic, received_sim_time=received,
                cdr=base64.b64encode(serialize_message(message)).decode()))+'\n')
    native = tmp_path/'safety_events.jsonl'
    native.write_text(json.dumps(dict(topic='/tb1/battery_state', data=state))+'\n')
    return capture, native


@pytest.mark.parametrize('corruption', [None, 'world_yaw', 'delivered_odom_yaw', 'delivered_tf_yaw',
    'native_odom_yaw', 'native_tf_yaw', 'missing_native_odom', 'missing_native_tf',
    'wrong_source_stamp', 'wrong_detection_fov', 'wrong_detection_range', 'missing_confirmation',
    'received_fresh_observer'])
def test_heading_yaw_is_bound_to_exact_typed_native_and_delivered_sources(tmp_path, corruption):
    event, rows, state, detection = fixture()
    if corruption == 'world_yaw': event['world']['yaws']['tb1'] += .1
    topics = dict(rows)
    if corruption in ('delivered_odom_yaw', 'native_odom_yaw'):
        topic = '/gateway/received/tb1/odom' if corruption.startswith('delivered') else '/tb1/odom'
        topics[topic].pose.pose.orientation.z = math.sin(.2)
        topics[topic].pose.pose.orientation.w = math.cos(.2)
    if corruption in ('delivered_tf_yaw', 'native_tf_yaw'):
        topic = '/gateway/received/tb1/tf' if corruption.startswith('delivered') else '/tb1/tf'
        topics[topic].transforms[0].transform.rotation.z = math.sin(.2)
        topics[topic].transforms[0].transform.rotation.w = math.cos(.2)
    if corruption == 'missing_native_odom': rows = [(t,m) for t,m in rows if t != '/tb1/odom']
    if corruption == 'missing_native_tf': rows = [(t,m) for t,m in rows if t != '/tb1/tf']
    if corruption == 'wrong_source_stamp': stamp(topics['/tb1/odom'].header, 9.9)
    if corruption == 'wrong_detection_fov': detection['field_of_view_deg'] = 180.
    if corruption == 'wrong_detection_range': detection['max_distance_m'] = 4.
    if corruption in ('wrong_detection_fov', 'wrong_detection_range'):
        topics['/gateway/received/target_detection'].data = json.dumps(detection)
    if corruption == 'missing_confirmation': event['world']['confirmations']['tb1'] = 3.
    if corruption == 'received_fresh_observer':
        fresh = {**detection, 'robot':'tb2', 'stamp_sec':9., '_gateway':{'source_time':9.}}
        rows.append(('/gateway/received/target_detection', String(data=json.dumps(fresh))))
    capture, native = write_sources(tmp_path, rows, state)
    if corruption in (None, 'received_fresh_observer'):
        assert bind_sources([event], capture, native) == 2
    else:
        with pytest.raises(AssertionError): bind_sources([event], capture, native)


def test_legacy_dispatch_keeps_its_existing_position_only_source_requirement(tmp_path):
    event, rows, state, _ = fixture()
    event['kind'] = 'exploration'
    event['world'].pop('yaws')
    rows = [(topic, msg) for topic, msg in rows if topic not in ('/tb1/odom', '/tb1/tf')]
    capture, native = write_sources(tmp_path, rows, state)
    assert bind_sources([event], capture, native) == 2


def test_heading_proof_cannot_self_authorize_an_existing_navigation_owner():
    event, _, _, _ = fixture()
    event['event'] = 'coordinator_global_motion_revalidation'
    event['owned'] = True
    event['world']['live_routes']['tb1'] = event['route']
    with pytest.raises(AssertionError): audit_motion(event)


@pytest.mark.parametrize('corruption', [None, 'missing_owner', 'closed_owner', 'wrong_generation',
    'changed_position', 'changed_yaw', 'changed_role', 'stale_current_source', 'charge_pending',
    'unexcluded_owner', 'forged_applied_source', 'hidden_revalidation_confirmation'])
def test_heading_revalidation_requires_original_live_generation_and_immutable_goal(tmp_path, corruption):
    event, rows, state, _ = fixture()
    admission = {**event, 'event':'coordinator_global_motion_admission', 'generation':1}
    sent = dict(event='coordinator_global_motion_sent', robot='tb1', generation=1, stamp_sec=10.)
    proof = {**copy.deepcopy(admission), 'event':'coordinator_global_motion_revalidation', 'event_time':10.1}
    validated = dict(event='coordinator_global_motion_revalidated', robot='tb1', generation=1, validated_at_sec=10.1)
    closed = dict(event='coordinator_global_motion_closed', robot='tb1', generation=1, status=4, error='')
    confirmation = dict(event='coordinator_global_confirmation', robot='tb1', source_time=4., event_time=4.)
    ledger = [confirmation, admission, sent, proof, validated, closed]
    if corruption == 'missing_owner': ledger.remove(sent)
    if corruption == 'closed_owner': ledger.insert(3, dict(closed))
    if corruption == 'wrong_generation': proof['generation'] = 2
    if corruption == 'changed_position': proof['requested_position'] = (4., 4.)
    if corruption == 'changed_yaw': proof['requested_yaw'] = .1
    if corruption == 'changed_role': proof['kind'] = 'rally'
    if corruption == 'stale_current_source': proof['world']['sources']['tb1/pose_state'] = 7.9
    if corruption == 'charge_pending': proof['world']['charge_pending'] = ['tb1']
    if corruption == 'unexcluded_owner': proof['world']['live_routes']['tb1'] = proof['route']
    if corruption == 'forged_applied_source':
        confirmation['source_time'] = 3.
        admission['world']['confirmations']['tb1'] = proof['world']['confirmations']['tb1'] = 3.
    if corruption == 'hidden_revalidation_confirmation':
        ledger.insert(3, dict(event='coordinator_global_confirmation', robot='tb2', source_time=9., event_time=10.05))
    write_sources(tmp_path, rows, state)
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in ledger))
    if corruption is None:
        audited = global_mission_audit(tmp_path, True)
        assert audited['sent'] == audited['closed'] == audited['current_revalidations'] == 1
        assert not audited['pending_at_owned_shutdown']
    else:
        with pytest.raises(AssertionError): global_mission_audit(tmp_path, True)


@pytest.mark.parametrize('applied_before_heading', [False, True])
def test_observer_capture_receipt_cannot_substitute_for_coordinator_application(tmp_path, applied_before_heading):
    event, rows, state, detection = fixture()
    fresh = {**detection, 'robot':'tb2', 'stamp_sec':9., '_gateway':{'source_time':9.}}
    rows.append(('/gateway/received/target_detection', String(data=json.dumps(fresh))))
    capture, _ = write_sources(tmp_path, rows, state)
    # Both independent capture receipts precede the proof. Only the actual
    # coordinator application ledger determines its serialized input state.
    with gzip.open(capture, 'rt') as stream:
        captured = [json.loads(line) for line in stream]
    captured[-1]['received_sim_time'] = 9.9
    with gzip.open(capture, 'wt') as stream:
        stream.write(''.join(json.dumps(row)+'\n' for row in captured))
    own = dict(event='coordinator_global_confirmation', robot='tb1', source_time=4., event_time=4.)
    alternate = dict(event='coordinator_global_confirmation', robot='tb2', source_time=9.,
                     event_time=9.9 if applied_before_heading else 10.1)
    admission = {**event, 'event':'coordinator_global_motion_admission', 'generation':1}
    sent = dict(event='coordinator_global_motion_sent', robot='tb1', generation=1, stamp_sec=10.)
    closed = dict(event='coordinator_global_motion_closed', robot='tb1', generation=1, status=4, error='')
    ledger = ([own, alternate, admission, sent, closed] if applied_before_heading
              else [own, admission, sent, alternate, closed])
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in ledger))
    if applied_before_heading:
        with pytest.raises(AssertionError, match='omitted an applied producer'):
            global_mission_audit(tmp_path, True)
    else:
        assert global_mission_audit(tmp_path, True)['sent'] == 1


@pytest.mark.parametrize('omit_applied_confirmation', [False, True])
def test_charge_world_cannot_replace_applied_confirmation_history(tmp_path, omit_applied_confirmation):
    heading, rows, state, detection = fixture()
    state['energy'] = 12.
    heading['world']['sources']['headquarters/target_detection'] = 5.05
    for topic, message in rows:
        if topic.endswith('/battery_state'):
            message.data = json.dumps(state)
    alternate = {**detection, 'robot':'tb2', 'stamp_sec':5.05, '_gateway':{'source_time':5.05}}
    rows.append(('/gateway/received/target_detection', String(data=json.dumps(alternate))))
    # This otherwise valid charge proof carries an older producer map. It
    # cannot overwrite the independent ledger of coordinator applications.
    charge_world = copy.deepcopy(heading['world'])
    charge_world['completed_legs'] = {'tb1':1}
    charge = dict(event='coordinator_global_charge_admission', event_time=10., robot='tb1',
        world=charge_world, budget_evaluated_at_sec=9.9, required_energy=20.,
        destination=heading['requested_position'], desired_task_route=heading['route'],
        desired_task_budget_at_sec=9.9, desired_task_wait_sec=0., reason='low_energy_after_actual_work')
    grid, maps = geometry_world(charge)
    position = charge_world['positions']['tb1']
    charge['current_return_required'] = scalar_budget(charge, grid, maps, [position], position)
    charge['return_route'] = contact(charge_world, grid, maps, 'tb1', position)['route']
    heading['event_time'] = 10.2
    if not omit_applied_confirmation:
        heading['world']['confirmations']['tb2'] = 5.05
    own = dict(event='coordinator_global_confirmation', robot='tb1', source_time=4., event_time=4.)
    applied = dict(event='coordinator_global_confirmation', robot='tb2', source_time=5.05, event_time=5.05)
    admission = {**heading, 'event':'coordinator_global_motion_admission', 'generation':1}
    ledger = [own, applied, charge,
        dict(event='coordinator_global_charge_sent', robot='tb1', stamp_sec=10.), admission,
        dict(event='coordinator_global_motion_sent', robot='tb1', generation=1, stamp_sec=10.2),
        dict(event='coordinator_global_motion_closed', robot='tb1', generation=1, status=4, error='')]
    write_sources(tmp_path, rows, state)
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in ledger))
    if omit_applied_confirmation:
        with pytest.raises(AssertionError, match='omitted an applied producer'):
            global_mission_audit(tmp_path, True)
    else:
        audited = global_mission_audit(tmp_path, True)
        assert audited['sent'] == audited['closed'] == audited['charge_admissions'] == 1
