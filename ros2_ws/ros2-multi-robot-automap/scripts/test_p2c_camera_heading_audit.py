"""Typed dispatch counterexamples for camera headings; no mission credit."""
import base64
import copy
import gzip
import json
import math
from dataclasses import replace

import numpy as np
import pytest
from nav_msgs.msg import Odometry
from rclpy.serialization import deserialize_message, serialize_message

from multi_robot_exploration import control
from p2c_global_audit import audit_motion, bind_sources, geometry_world, global_mission_audit, scalar_budget
from test_p2c_observer_heading_audit import fixture, stamp, write_sources


def camera_fixture():
    event, rows, state, _ = fixture()
    world = event['world']
    world.update(target=None, observer=None, confirmations={}, charge_intents={}, planned_return_routes={},
                 pending_orientation_times={}, search_views=[], pending_views={}, completed_legs={'tb1':0})
    world['sources'].pop('headquarters/target_detection')
    rows = [(topic, message) for topic, message in rows if not topic.endswith('/target_detection')]
    event.update(kind='exploration_camera_heading', task_phase='EXPLORE', nominal_orientation_time_sec=60.)
    return event, rows, state


def reprice(event):
    grid, maps = geometry_world(event)
    event['required_energy'] = scalar_budget(event, grid, maps, event['complete_task_route'],
                                            event['requested_position'], event['waiting_time_budget_sec'])


def test_camera_point_protects_middle_of_original_dense_reserved_segment():
    event, _, _ = camera_fixture()
    x, y = event['requested_position']
    event['world']['live_routes']['tb2'] = [(x-.025, y-1.7999), (x+.025, y-1.7999)]
    assert all(math.dist(event['requested_position'], point) > 1.8 for point in event['world']['live_routes']['tb2'])
    with pytest.raises(AssertionError): audit_motion(event)


def test_ordinary_dispatch_also_protects_a_real_heading_peer_continuously():
    event, _, _ = camera_fixture()
    world = event['world']
    x, y = world['positions']['tb1']
    route = [(x-.025+index*.05, y-1.7999) for index in range(-20,22)]
    world['positions']['tb1'] = route[0]
    world['positions']['tb2'] = (x,y)
    world['live_routes']['tb2'] = [(x,y)]
    event.update(kind='exploration', nominal_orientation_time_sec=0., waiting_time_budget_sec=0.,
                 route=route, complete_task_route=route, requested_position=route[-1])
    reprice(event)
    assert all(math.dist((x,y), point) > 1.8 for point in route)
    assert audit_motion(event) == len(route)
    # Full global ledger validation separately requires this allocation to
    # correspond to an actual sent and still unclosed heading generation.
    world['pending_orientation_times'] = {'tb2':60.}
    with pytest.raises(AssertionError): audit_motion(event)


def test_short_measured_connector_cannot_cross_unknown_between_known_endpoints():
    event, _, _ = camera_fixture()
    world = event['world']
    raw = np.zeros((80, 80), dtype=np.int16)
    raw[10, 11] = -1
    for name in ('source_map', 'planning_map'):
        saved = world[name]
        world[name] = control.grid_audit_evidence(raw, .05, (0.,0.), saved['source'], 9.5, 9.5)
    world['return_maps']['tb1'] = dict(world['source_map'])
    world['positions']['tb1'] = (.545, .540)
    world['battery_states']['tb1'].update(charge_x=.545, charge_y=.540)
    event['requested_position'] = (.555, .555)
    event['route'] = event['complete_task_route'] = [world['positions']['tb1'], event['requested_position']]
    reprice(event)
    assert math.dist(*event['route']) < .02
    assert raw[10,10] == raw[11,11] == 0
    with pytest.raises(AssertionError): audit_motion(event, owned=True)


@pytest.mark.parametrize('qualified', [True, False])
def test_other_native_return_can_parallel_only_with_qualified_clear_corridor(tmp_path, qualified):
    from test_p2c_charge_demand_audit import helper_fixture, write_sources as write_many_sources
    event, rows, states = helper_fixture(actor_slot=None)
    world = event['world']
    position = world['positions']['tb1']
    world.update(pending_orientation_times={}, search_views=[], pending_views={})
    world['battery_states']['tb2']['charge_x'] = world['positions']['tb2'][0]+1.
    event.update(kind='exploration_camera_heading', requested_position=position, requested_yaw=0.,
        route=[position], complete_task_route=[position], task_phase='EXPLORE',
        nominal_orientation_time_sec=60., waiting_time_budget_sec=60.)
    if not qualified:
        raw = np.zeros((80,80), dtype=np.int16)
        raw[:,40] = 100
        world['battery_states']['tb2']['charge_x'] = position[0]-1.
        for name in ('source_map', 'planning_map'):
            saved = world[name]
            world[name] = control.grid_audit_evidence(raw, saved['resolution'], saved['origin'], saved['source'], 9.5, 9.5)
        for robot in world['return_maps']: world['return_maps'][robot] = dict(world['source_map'])
    reprice(event)
    for topic, message in rows:
        if topic.endswith('/battery_state'): message.data=json.dumps(states[topic.split('/')[-2]])
    if qualified:
        assert audit_motion(event) == 1
        write_many_sources(tmp_path, rows, states)
        assert bind_sources([event], tmp_path/'navigation_inputs.jsonl.gz', tmp_path/'safety_events.jsonl') == 3
    else:
        with pytest.raises(AssertionError): audit_motion(event)


@pytest.mark.parametrize('corruption', [None, 'unconfirmed', 'translation', 'hidden_translation', 'already_aligned',
    'wrong_bin', 'zero_time', 'zero_wait', 'short_timeout', 'wrong_phase', 'target', 'soft_demand',
    'issued', 'native', 'not_required', 'owned', 'unfunded', 'near_body', 'landing', 'soft_corridor',
    'stale_pose', 'future_frame', 'stale_battery'])
def test_camera_heading_initial_admission_has_full_original_contract(corruption):
    event, _, _ = camera_fixture()
    world = event['world']
    position = world['positions']['tb1']
    if corruption == 'unconfirmed': event['task_phase'] = 'FOUND_UNCONFIRMED'
    if corruption == 'translation':
        event['requested_position'] = (position[0]+.01, position[1])
        event['route'] = event['complete_task_route'] = [position, event['requested_position']]
        reprice(event)
    if corruption == 'hidden_translation': event['complete_task_route'] = [position, (position[0]+.01, position[1]), position]
    if corruption == 'already_aligned': world['yaws']['tb1'] = .25
    if corruption == 'wrong_bin': event['requested_yaw'] = .1
    if corruption == 'zero_time': event['nominal_orientation_time_sec'] = 0.
    if corruption == 'zero_wait': event['waiting_time_budget_sec'] = 0.; reprice(event)
    if corruption == 'short_timeout': world['goal_timeout_sec'] = 30.
    if corruption == 'wrong_phase': event['task_phase'] = 'RALLY'
    if corruption == 'target': world['target'] = position
    if corruption == 'soft_demand':
        world['charge_intents']['tb1'] = dict(slot='main', reason='unfunded_search', required_energy=50., destination=position, park_for=None)
    if corruption == 'issued': world['charge_pending'] = ['tb1']
    if corruption == 'native': world['battery_states']['tb1']['mode'] = 'RETURNING'
    if corruption == 'not_required': world['required'] = []
    if corruption == 'owned': world['live_routes']['tb1'] = [position]
    if corruption == 'unfunded': world['battery_states']['tb1']['energy'] = event['required_energy']
    if corruption == 'near_body': world['positions']['tb2'] = (position[0]+.59, position[1])
    if corruption == 'landing':
        raw = np.zeros((80, 80), dtype=np.int16)
        cell = control.world_to_grid(*position, world['planning_map']['resolution'], 0., 0.)
        raw[cell[0], cell[1]+4] = 100
        for name in ('source_map', 'planning_map'):
            saved = world[name]
            world[name] = control.grid_audit_evidence(raw, saved['resolution'], saved['origin'], saved['source'], 9.5, 9.5)
    if corruption == 'soft_corridor':
        from p2c_global_audit import contact
        world['positions']['tb2'] = (position[0]+2., position[1])
        world['battery_states']['tb2'] = {**world['battery_states']['tb1'], 'charge_x':position[0]-1.}
        world['return_maps']['tb2'] = copy.deepcopy(world['return_maps']['tb1'])
        for kind in ('map_snapshot', 'pose_state', 'frame_state', 'battery_state'):
            world['sources']['tb2/'+kind] = world['sources']['tb1/'+kind]
        world['charge_intents']['tb2'] = dict(slot='main', reason='unfunded_search', required_energy=50., destination=position, park_for=None)
        grid, maps = geometry_world(event)
        world['planned_return_routes']['tb2'] = contact(world, grid, maps, 'tb2', world['positions']['tb2'])['route']
    if corruption == 'stale_pose': world['sources']['tb1/pose_state'] = 7.9
    if corruption == 'future_frame': world['sources']['tb1/frame_state'] = 10.1
    if corruption == 'stale_battery': world['sources']['tb1/battery_state'] = 4.9
    if corruption in (None, 'unconfirmed'):
        assert audit_motion(event) == 1
    else:
        with pytest.raises(AssertionError): audit_motion(event)


def ledger_fixture(tmp_path, corruption=None, drift=.019, history=False):
    admission, rows, state = camera_fixture()
    admission.update(event='coordinator_global_motion_admission', generation=1)
    goal = admission['requested_position']
    proof = copy.deepcopy(admission)
    proof.update(event='coordinator_global_motion_revalidation', event_time=10.2, budget_evaluated_at_sec=10.15)
    current = (goal[0]-drift, goal[1])
    proof['world']['positions']['tb1'] = current
    proof['world']['yaws']['tb1'] = 0.
    proof['world']['sources'].update({'tb1/pose_state':10.05, 'tb1/frame_state':10.04})
    proof['route'] = proof['complete_task_route'] = [current, goal]
    proof['world']['pending_orientation_times'] = {'tb1':60.}
    proof['world']['pending_views'] = {'tb1':[*goal, 0.]}
    reprice(proof)
    topics = dict(rows)
    for topic in ('/gateway/received/tb1/odom', '/tb1/odom'):
        odom = copy.deepcopy(topics[topic])
        stamp(odom.header, 10.05)
        odom.pose.pose.position.x -= drift*math.cos(.3)
        odom.pose.pose.position.y += drift*math.sin(.3)
        odom.pose.pose.orientation.z, odom.pose.pose.orientation.w = math.sin(-.3/2), math.cos(-.3/2)
        rows.append((topic, odom))
    for topic in ('/gateway/received/tb1/tf', '/tb1/tf'):
        transform = copy.deepcopy(topics[topic])
        stamp(transform.transforms[0].header, 10.04)
        rows.append((topic, transform))
    sent = dict(event='coordinator_global_motion_sent', robot='tb1', generation=1, stamp_sec=10.)
    validated = dict(event='coordinator_global_motion_revalidated', robot='tb1', generation=1, validated_at_sec=10.2)
    closed = dict(event='coordinator_global_motion_closed', robot='tb1', generation=1, status=4, error='')
    ledger = [admission, sent, proof, validated, closed]
    if history:
        view = dict(source='ap_delivered_pose_and_heading_history', robot='tb1', position=list(goal), yaw=1.5,
                    observed_at_sec=9.9, pose_source_time=9.8, frame_source_time=9.7)
        producer = dict(event='coordinator_global_search_view_applied', event_time=9.9,
            task_phase='EXPLORE',
            view_key=[math.floor(goal[0]/.5), math.floor(goal[1]/.5), math.floor((1.5+math.pi)/(math.pi/8))%16], **view)
        admission['world']['search_views'] = proof['world']['search_views'] = [copy.deepcopy(view)]
        ledger.insert(0, producer)
    if corruption == 'forged_revalidation': ledger.remove(sent)
    if corruption == 'old_generation': proof['generation'] = 2
    if corruption == 'changed_goal': proof['requested_position'] = (goal[0]+.001, goal[1])
    if corruption == 'changed_yaw': proof['requested_yaw'] = math.pi/8
    if corruption == 'changed_role': proof['kind'] = 'exploration'
    if corruption == 'closed_owner': ledger.insert(2, copy.deepcopy(closed))
    if corruption == 'missing_time': proof['world']['pending_orientation_times'] = {}
    if corruption == 'zero_time': proof['world']['pending_orientation_times']['tb1'] = 0.
    if corruption == 'fake_owner': admission['world']['pending_orientation_times'] = {'tb2':60.}
    if corruption == 'unsafe_start': proof['world']['positions']['tb2'] = (current[0]-.59, current[1])
    if corruption == 'unsafe_end': proof['world']['positions']['tb2'] = (goal[0]+.59, goal[1])
    if corruption == 'unsafe_mid': proof['world']['positions']['tb2'] = (goal[0]-drift/2, goal[1]-.59995)
    if corruption == 'corridor_mid': proof['world']['live_routes']['tb2'] = [(goal[0]-drift/2, goal[1]-1.79999)]
    if corruption == 'source_yaw': proof['world']['yaws']['tb1'] = .1
    if corruption == 'missing_native': rows = [(topic,msg) for topic,msg in rows if topic != '/tb1/odom']
    if corruption == 'omit_schema':
        for item in ledger:
            if 'world' in item:
                for field in ('pending_orientation_times', 'search_views', 'pending_views'): item['world'].pop(field)
                item.pop('nominal_orientation_time_sec')
    if corruption == 'replayed_view':
        position = [2.+math.cos(.7)-math.sin(.7), 2.+math.sin(.7)+math.cos(.7)]
        repeat = {**producer, 'event_time':10.1, 'observed_at_sec':10.1, 'frame_source_time':10.08,
            'position':position, 'yaw':1.9,
            'view_key':[math.floor(position[0]/.5), math.floor(position[1]/.5), math.floor((1.9+math.pi)/(math.pi/8))%16]}
        for topic in ('/gateway/received/tb1/tf', '/tb1/tf'):
            transform = copy.deepcopy(topics[topic])
            stamp(transform.transforms[0].header, 10.08)
            transform.transforms[0].transform.rotation.z = math.sin(.7/2)
            transform.transforms[0].transform.rotation.w = math.cos(.7/2)
            rows.append((topic, transform))
        ledger.insert(3, repeat)
    if corruption == 'hidden_applied_view': proof['world']['search_views'] = []
    if corruption == 'unapplied_view': ledger.remove(producer)
    if corruption == 'forged_view_yaw':
        producer['yaw'] += .01
        admission['world']['search_views'][0]['yaw'] += .01
    if corruption == 'stale_view': producer['observed_at_sec'] = producer['event_time'] = 12.
    if corruption == 'future_view': producer['frame_source_time'] = 10.
    if corruption == 'view_wrong_phase': producer['task_phase'] = 'RALLY'
    if corruption == 'view_source_regression':
        older = {**producer, 'robot':'tb2', 'event_time':9.95, 'observed_at_sec':9.95, 'pose_source_time':9.75}
        for suffix in ('odom', 'tf'):
            for prefix in ('/gateway/received', ''):
                message = copy.deepcopy(topics[prefix+'/tb1/'+suffix])
                if suffix == 'odom': stamp(message.header,9.75)
                rows.append((prefix+'/tb2/'+suffix, message))
        ledger.insert(1, older)
        admission['world']['search_views'][0] = {field:older[field] for field in admission['world']['search_views'][0]}
    if corruption == 'fake_pending': proof['world']['pending_views']['tb2'] = [*goal,0.]
    write_sources(tmp_path, rows, state)
    with gzip.open(tmp_path/'navigation_inputs.jsonl.gz', 'rt') as stream:
        captured = [json.loads(line) for line in stream]
    for item in captured: item['received_sim_time'] = 10.15
    with gzip.open(tmp_path/'navigation_inputs.jsonl.gz', 'wt') as stream:
        stream.write(''.join(json.dumps(item)+'\n' for item in captured))
    (tmp_path/'manifest.json').write_text(json.dumps(dict(config=dict(global_algorithm=dict(stationary_camera_heading='declared generic role')))))
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in ledger))
    return proof


@pytest.mark.parametrize('corruption', [None, 'forged_revalidation', 'old_generation', 'changed_goal', 'changed_yaw',
    'changed_role', 'closed_owner', 'missing_time', 'zero_time', 'fake_owner', 'unsafe_start', 'unsafe_end',
    'source_yaw', 'missing_native', 'omit_schema', 'fake_pending', 'unsafe_mid', 'corridor_mid'])
def test_only_a_matching_real_owner_can_revalidate_original_small_drift(tmp_path, corruption):
    proof = ledger_fixture(tmp_path, corruption)
    # Merely naming an event revalidation never authorizes its translation.
    if proof['kind'] == 'exploration_camera_heading':
        with pytest.raises(AssertionError): audit_motion(proof)
    if corruption is None:
        audited = global_mission_audit(tmp_path, True)
        assert audited['sent'] == audited['closed'] == audited['current_revalidations'] == 1
    else:
        with pytest.raises(AssertionError): global_mission_audit(tmp_path, True)


@pytest.mark.parametrize('drift', [0., .019, .021])
def test_owned_yaw_arrival_keeps_owner_and_original_position_tolerance(tmp_path, drift):
    ledger_fixture(tmp_path, drift=drift)
    if drift <= .02:
        assert global_mission_audit(tmp_path, True)['current_revalidations'] == 1
    else:
        with pytest.raises(AssertionError): global_mission_audit(tmp_path, True)


@pytest.mark.parametrize('corruption', [None, 'replayed_view', 'hidden_applied_view', 'unapplied_view',
    'forged_view_yaw', 'stale_view', 'future_view', 'view_wrong_phase', 'view_source_regression'])
def test_camera_recency_uses_applied_physical_source_and_exact_cdr(tmp_path, corruption):
    ledger_fixture(tmp_path, corruption, history=True)
    if corruption is None:
        assert global_mission_audit(tmp_path, True)['applied_search_view_bindings'] == 1
    else:
        with pytest.raises(AssertionError): global_mission_audit(tmp_path, True)


@pytest.mark.parametrize('closed', [True, False])
def test_lost_predicted_gain_does_not_release_actual_heading_allocation(tmp_path, closed):
    ledger_fixture(tmp_path)
    ledger = [json.loads(line) for line in (tmp_path/'ledger.jsonl').read_text().splitlines()]
    ledger[2]['world']['pending_views'] = {}
    if not closed: ledger.pop()
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in ledger))
    audited = global_mission_audit(tmp_path, True)
    assert audited['pending_at_owned_shutdown'] == ([] if closed else ['tb1'])


@pytest.mark.parametrize('applied_before_proof', [False, True])
def test_capture_of_newer_physical_view_is_not_central_application(tmp_path, applied_before_proof):
    proof = ledger_fixture(tmp_path, history=True)
    with gzip.open(tmp_path/'navigation_inputs.jsonl.gz', 'rt') as stream:
        captured = [json.loads(line) for line in stream]
    for topic in ('/gateway/received/tb1/odom', '/tb1/odom'):
        source = next(item for item in reversed(captured) if item['topic'] == topic)
        message = deserialize_message(base64.b64decode(source['cdr']), Odometry)
        stamp(message.header, 10.1)
        message.pose.pose.orientation.z = math.sin((math.pi/8-.3)/2)
        message.pose.pose.orientation.w = math.cos((math.pi/8-.3)/2)
        captured.append(dict(topic=topic, received_sim_time=10.15,
                             cdr=base64.b64encode(serialize_message(message)).decode()))
    with gzip.open(tmp_path/'navigation_inputs.jsonl.gz', 'wt') as stream:
        stream.write(''.join(json.dumps(item)+'\n' for item in captured))
    position = proof['world']['positions']['tb1']
    applied = 10.15 if applied_before_proof else 10.3
    producer = dict(event='coordinator_global_search_view_applied', task_phase='EXPLORE', event_time=applied,
        source='ap_delivered_pose_and_heading_history', robot='tb1', position=list(position), yaw=math.pi/8,
        observed_at_sec=applied, pose_source_time=10.1, frame_source_time=10.04,
        view_key=[math.floor(position[0]/.5), math.floor(position[1]/.5),9])
    ledger = [json.loads(line) for line in (tmp_path/'ledger.jsonl').read_text().splitlines()]
    ledger.insert(3 if applied_before_proof else 5, producer)
    (tmp_path/'ledger.jsonl').write_text(''.join(json.dumps(item)+'\n' for item in ledger))
    if applied_before_proof:
        with pytest.raises(AssertionError): global_mission_audit(tmp_path, True)
    else:
        assert global_mission_audit(tmp_path, True)['applied_search_view_bindings'] == 2


def ranking_snapshot(two=False, disconnected=False):
    from multi_robot_exploration.fleet_planning import FleetSnapshot
    raw = np.zeros((200,200),dtype=np.int16)
    if disconnected: raw[:,100] = 100
    positions = {'tb1':(2.525,2.525)}
    if two: positions['tb2'] = (7.525 if disconnected else 4.525,2.525)
    return FleetSnapshot('EXPLORE',10.,raw,.05,(0.,0.),positions,
        {robot:{'nominal_speed_mps':.18} for robot in positions},{},{},tuple(positions),
        required=tuple(positions))


def rank_heading(snapshot, robot, cells=frozenset()):
    from multi_robot_exploration.fleet_planning import MotionProposal
    position = snapshot.positions[robot]
    return MotionProposal(robot,'exploration_camera_heading',control.RallyPose(*position,0.),
        (position,),0.,0.,information_cells=cells,nominal_orientation_time_sec=60.)


def test_parallel_orientation_allocation_is_per_actor_and_not_zero_or_serial_sum():
    from multi_robot_exploration.fleet_planning import ExplorationObjective, MotionProposal
    snapshot = ranking_snapshot(two=True)
    objective = ExplorationObjective(snapshot, snapshot.grid == 0)
    headings = tuple(rank_heading(snapshot, robot) for robot in snapshot.positions)
    assert objective.ready_time(headings)-objective.ready_time(()) == pytest.approx(60.)
    ordinary = MotionProposal('tb2','exploration',control.RallyPose(9.525,2.525,0.),
        ((4.525,2.525),(9.525,2.525)),0.,0.)
    without = replace(headings[0],nominal_orientation_time_sec=0.)
    assert objective.ready_time((headings[0],ordinary))-objective.ready_time((without,ordinary)) == pytest.approx(60.-5/.18)
    single = ranking_snapshot()
    current = single.positions['tb1']
    goal = (current[0]+.019,current[1])
    single = replace(single,pending_orientation_times={'tb1':60.},
        pending_views={'tb1':control.RallyPose(*goal,0.)},live_routes={'tb1':(current,goal)})
    owned = ExplorationObjective(single,single.grid == 0)
    assert owned.ready_time(()) == pytest.approx(1.+60.+.019/.18)
    proposal = replace(rank_heading(single,'tb1'),pose=control.RallyPose(*goal,0.),route=(current,goal))
    assert owned.ready_time((proposal,)) == pytest.approx(owned.ready_time(()))


def test_all_historical_interest_zero_is_positive_and_fallback_prices_original_window():
    from multi_robot_exploration.fleet_planning import ExplorationObjective
    for disconnected in (False,True):
        snapshot = ranking_snapshot(two=disconnected,disconnected=disconnected)
        objective = ExplorationObjective(snapshot,np.zeros_like(snapshot.grid,dtype=bool))
        cells = frozenset({50*200+55,50*200+56})
        proposal = rank_heading(snapshot,'tb1',cells)
        assert objective.mass(cells) == .5
        assert objective.score((proposal,)) > objective.score(()) == 0.
        bound = objective.bound('tb1',proposal.pose,proposal.route,len(cells),1.,orientation_time=60.)
        assert bound >= objective.score((proposal,))
        assert proposal.route == (snapshot.positions['tb1'],)
        if disconnected:
            assert objective.ready_time((proposal,)) is None
            assert objective.score((proposal,)) == pytest.approx(control.exploration_utility(.5,0,60.*.18))
        else:
            assert objective.ready_time((proposal,)) == pytest.approx(61.)


def test_pending_camera_view_has_directional_known_potential_without_360_mapping_credit():
    from multi_robot_exploration.fleet_planning import ExplorationObjective
    snapshot = ranking_snapshot()
    raw = snapshot.grid.copy()
    unknown = {(50,65),(65,50),(50,35)}
    for cell in unknown:raw[cell] = -1
    position = snapshot.positions['tb1']
    snapshot = replace(snapshot,grid=raw,pending_orientation_times={'tb1':60.},
        live_routes={'tb1':(position,)},pending_views={'tb1':control.RallyPose(*position,0.)})
    objective = ExplorationObjective(snapshot,raw == 0)
    assert 50*200+55 in objective.committed and 50*200+45 not in objective.committed
    assert not {row*200+column for row,column in unknown} & objective.committed
    ordinary = ExplorationObjective(replace(snapshot,pending_orientation_times={}),raw == 0)
    assert {row*200+column for row,column in unknown} <= ordinary.committed
