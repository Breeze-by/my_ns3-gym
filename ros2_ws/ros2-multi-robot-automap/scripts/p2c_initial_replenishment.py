"""Rebuild a policy top-up separately from the current physical trip cost."""
import json
import math
from types import SimpleNamespace

import numpy as np
from multi_robot_exploration import control
from p2c_return_preparation import audit_preparation, decode_grid


def initial_replenishment_audit(ledger, enabled=False, native_capture=None, require_completion_hold=False, map_capture=None):
    native = {}
    if enabled:
        assert native_capture is not None and native_capture.is_file()
        for line in native_capture.open():
            row = json.loads(line)
            if row['topic'].endswith('/battery_state'):
                name = row['topic'].split('/')[1]
                native.setdefault(name, []).append(row['data'])
    decisions_by_robot, commands, outcomes, navigation, holds = {}, {}, {}, {}, []
    for line in ledger.open():
        event = json.loads(line)
        kind = event.get('event')
        if kind == 'coordinator_navigation_decision':
            source = event.get('dispatch_goal_source_time_sec', event['event_time'])
            decisions_by_robot.setdefault(event['robot'], []).append((source, event['kind']))
            navigation.setdefault(event['robot'], []).append(event)
        elif kind == 'coordinator_initial_exploration_completion_hold':
            holds.append(event)
        elif kind == 'enqueue' and event.get('message_type') == 'navigation_goal':
            commands.setdefault((event['recipient'], event['correlation_id']), event.get('source_time', event['event_time']))
        elif kind == 'navigation_outcome':
            outcomes.setdefault((event['recipient'], event['correlation_id']), (event['event_time'], event['status']))
    successes = {}
    for key, (at, status) in outcomes.items():
        if key not in commands or status != 4:
            continue
        source = commands[key]
        if not math.isfinite(source) or not math.isfinite(at) or at < source:
            continue
        candidates = [(stamp, kind) for stamp, kind in decisions_by_robot.get(key[0], [])
                      if 0 <= source - stamp <= 2.]
        if not candidates:
            continue
        latest = max(stamp for stamp, _ in candidates)
        kinds = {kind for stamp, kind in candidates if stamp == latest}
        if len(kinds) == 1 and kinds <= {'exploration', 'initial_visual_search'}:
            successes.setdefault(key[0], []).append(at)
    audit_completion_holds(holds, navigation, commands, successes, native, require_completion_hold, map_capture)
    decisions, robots = 0, set()
    for line in ledger.open():
        event = json.loads(line)
        kind = event.get('event')
        if kind != 'coordinator_charge_decision':
            continue
        if enabled:
            assert 'initial_replenishment' in event
        saved = event.get('initial_replenishment')
        if saved is None:
            continue
        assert enabled, 'undeclared initial replenishment'
        assert saved['strategy'] == 'initial_near_home_replenishment'
        assert event['task_phase'] in ('EXPLORE', 'FOUND_UNCONFIRMED')
        assert event.get('opportunity_lookahead') is None
        assert audit_preparation(event) == 'charge'
        name, now = event['robot'], event['event_time']
        preparation, state = event['return_preparation'], saved['battery_state']
        positions, modes = preparation['robot_positions'], preparation['battery_modes']
        assert modes[name] == 'ACTIVE' and state == preparation['battery_states'][name]
        assert type(state['charge_count']) is int and state['charge_count'] == 0
        completed = saved['completed_exploration_legs']
        assert type(completed) is int and 1 <= completed <= sum(
            at <= saved['trip_evaluated_at_sec'] for at in successes.get(name, []))
        source = event['inputs'][name + '/battery_state']['source_time']
        assert state['stamp_sec'] == source
        original = [row for row in native.get(name, []) if row['stamp_sec'] <= source]
        assert original, 'missing original native charge history'
        previous = max(original, key=lambda row: row['stamp_sec'])
        assert previous['mode'] == 'ACTIVE' and type(previous['charge_count']) is int and previous['charge_count'] == 0
        for key in ('capacity', 'charge_target_fraction', 'charge_x', 'charge_y', 'charge_radius_m'):
            assert state[key] == previous[key]
        evaluated, trip_at = saved['evaluated_at_sec'], saved['trip_evaluated_at_sec']
        assert math.isfinite(trip_at) and math.isfinite(evaluated) and trip_at <= evaluated <= now
        for key, sample in event['inputs'].items():
            if key == 'headquarters/target_detection':
                continue
            assert 0 <= trip_at - sample['source_time'] <= sample['ttl_sec']
            assert 0 <= now - sample['source_time'] <= sample['ttl_sec']
            assert math.isclose(now - sample['source_time'], sample['age_sec'], abs_tol=1e-8)
        planning = preparation['planning_map']
        raw = decode_grid(planning)
        maps = {robot: dict(data=decode_grid(row), resolution=row['resolution'], origin=row['origin'])
                for robot, row in preparation['return_maps'].items()}
        active = {robot for robot, mode in modes.items() if mode != 'FAILED'}
        node = SimpleNamespace(now=lambda: trip_at, battery_modes=modes,
            battery_states=preparation['battery_states'], robot_positions=positions,
            map_data=raw, resolution=planning['resolution'], origin=planning['origin'],
            map_received_at=planning['source_time'], robot_maps=maps,
            robot_map_received_at={robot: row['source_time'] for robot, row in preparation['return_maps'].items()},
            robot_odom_received_at={robot: event['inputs'][robot + '/pose_state']['source_time'] for robot in active},
            robot_tf_received_at={robot: event['inputs'][robot + '/frame_state']['source_time'] for robot in active})
        assert saved['frontier_position'] == event['frontier_position']
        required = control.HeadquartersControl.exploration_required_energy(node, name,
            saved['trip_distance_m'], saved['frontier_position'], trip_at)
        assert required is not None and math.isclose(required, saved['trip_required_energy'], abs_tol=1e-8)
        target = state['capacity'] * state['charge_target_fraction']
        assert required < state['energy'] < target
        assert target == saved['charge_target_energy'] == event['required_energy']
        assert event['available_energy'] == state['energy']
        home, position, radius = saved['home'], saved['robot_position'], state['charge_radius_m']
        assert position == positions[name] and home == [state['charge_x'], state['charge_y']]
        assert control.PATH_CLEARANCE_M < math.dist(position, home) <= 2 * radius
        goal, route = control.plan_rally_leg(control.RallyPose(*home, 0.), raw,
            planning['resolution'], planning['origin'], position, 2 * radius,
            blocked_positions=[point for robot, point in positions.items() if robot != name],
            clearance_m=control.PATH_CLEARANCE_M, visible_only=True, local_map=maps[name])
        assert goal is not None and math.dist((goal.x, goal.y), home) <= radius - .2
        assert np.allclose([goal.x, goal.y, goal.yaw], saved['contact_goal'], atol=1e-10, rtol=0.)
        assert np.allclose(route, saved['contact_route'], atol=1e-10, rtol=0.)
        decisions += 1
        robots.add(name)
    return dict(enabled=enabled, status='PASS', policy_requests=decisions,
        robots=sorted(robots), first_goal_completion_holds=len(holds), completion_hold_declared=require_completion_hold,
        scope='One initial near-home replenishment after actual ordinary success; scheduling threshold and current full trip cost rebuilt separately. Native credit and physical return remain separate original audits.')


def audit_completion_holds(events, navigation, commands, successes, native, required, capture):
    """A continuation needs a real earlier command and fresh full safety inputs."""
    from p2c_outbound_routes import bind_original_maps, audit_outbound
    from p2c_navigation_dispatch import sample_deadline

    for event in events:
        assert required, 'undeclared initial ordinary completion hold'
        name, now = event['robot'], event['event_time']
        accepted, timeout, progress = (event[key] for key in
            ('goal_accepted_at_sec', 'goal_timeout_sec', 'last_progress_at_sec'))
        assert event['strategy'] == 'funded_first_near_home_goal'
        assert event['task_phase'] in ('EXPLORE', 'FOUND_UNCONFIRMED')
        assert math.isfinite(now) and math.isfinite(accepted) and timeout == 60.
        assert 0 <= now - accepted < timeout
        assert progress is None or (math.isfinite(progress) and accepted <= progress <= now
            and not (now - accepted >= 10. and now - progress >= 20.))
        assert type(event['completed_exploration_legs']) is int and event['completed_exploration_legs'] == 0
        assert not any(at <= now for at in successes.get(name, []))
        candidates = [row for row in navigation.get(name, []) if row['event_time'] <= accepted]
        assert candidates, 'continuation without original navigation'
        decision = max(candidates, key=lambda row:row['event_time'])
        assert decision['kind'] in ('exploration', 'initial_visual_search')
        assert decision['requested_position'] == event['requested_position']
        source = decision.get('dispatch_goal_source_time_sec', decision['event_time'])
        assert any(robot == name and 0 <= stamp - source <= 2. and stamp <= accepted
            for (robot, _), stamp in commands.items()), 'missing original command'
        modes, states, positions = (event[key] for key in ('battery_modes', 'battery_states', 'robot_positions'))
        state = states[name]
        assert modes[name] == state['mode'] == 'ACTIVE' and event['robot_states'][name] == 'active'
        assert 'RETURNING' not in modes.values()
        assert type(state['charge_count']) is int and state['charge_count'] == 0
        battery_source = event['inputs'][name + '/battery_state']['source_time']
        assert state['stamp_sec'] == battery_source
        originals = [row for row in native.get(name, []) if row['stamp_sec'] <= battery_source]
        assert any(row == state for row in originals), 'missing matching original native battery state'
        home = [state['charge_x'], state['charge_y']]
        destination = event['requested_position']
        assert .35 < math.dist(destination, home) <= 2 * state['charge_radius_m']
        assert 0 < state['charge_target_fraction'] <= 1 and state['capacity'] > 0
        assert event['required_energy'] < state['energy'] < state['capacity'] * state['charge_target_fraction']
        evaluated = event['evaluated_at_sec']
        assert accepted <= evaluated <= now
        for key, sample in event['inputs'].items():
            sample_deadline(key, sample)
            assert 0 <= evaluated - sample['source_time'] <= sample['ttl_sec']
            assert 0 <= now - sample['source_time'] <= sample['ttl_sec']
            assert math.isclose(now - sample['source_time'], sample['age_sec'], abs_tol=1e-8)
        audit_outbound(event)
        saved = event['outbound_map_route']; route = saved['route']
        distance = sum(math.dist(a, b) for a, b in zip(route, route[1:]))
        assert distance <= 5. and math.isclose(distance, event['remaining_distance_m'], abs_tol=1e-8)
        assert event['current_position'] == positions[name]
        assert all(not control.routes_conflict(route, (point,), .6)
            for peer, point in positions.items() if peer != name and point is not None)
        expected = {peer:control.remaining_rally_route(saved, positions[peer])
            for peer, saved in event['goal_routes'].items() if peer != name
            and event['robot_states'][peer] == 'active' and saved}
        assert set(expected) == set(event['remaining_peer_routes'])
        assert all(np.array_equal(expected[peer], event['remaining_peer_routes'][peer]) for peer in expected)
        assert all(event['robot_states'][peer] == 'active' and not control.routes_conflict(route, reserved, 1.8)
            for peer, reserved in event['remaining_peer_routes'].items())
        planning, local = saved['planning_map'], saved['local_map']
        raw = decode_grid(planning)
        maps = {name:dict(data=decode_grid(local), resolution=local['resolution'], origin=local['origin'])}
        node = SimpleNamespace(now=lambda:evaluated, battery_modes=modes, battery_states=states,
            robot_positions=positions, map_data=raw, resolution=planning['resolution'], origin=planning['origin'],
            map_received_at=planning['source_time'], robot_maps=maps,
            robot_map_received_at={name:local['source_time']},
            robot_odom_received_at={name:event['inputs'][name+'/pose_state']['source_time']},
            robot_tf_received_at={name:event['inputs'][name+'/frame_state']['source_time']})
        combined = control.constrained_return_grid(raw, node.resolution, node.origin, maps[name])
        endpoint = control.world_to_grid(*destination, node.resolution, *node.origin)
        assert control.traversable_grid(combined, node.resolution, .45)[endpoint]
        required_energy = control.HeadquartersControl.exploration_required_energy(node, name, distance, destination, evaluated)
        assert required_energy is not None and math.isclose(required_energy, event['trip_required_energy'], abs_tol=1e-8)
        wait = state['idle_cost_per_sec'] * (accepted + timeout - evaluated)
        assert math.isclose(wait, event['remaining_wait_energy'], abs_tol=1e-8)
        assert math.isclose(required_energy + wait, event['required_energy'], abs_tol=1e-8)
        gain = control.visible_unknown_gain(raw, control.world_to_grid(*event['frontier_position'], node.resolution, *node.origin),
            control.INFORMATION_RADIUS_M / node.resolution)
        assert gain == event['remaining_information_gain']
        assert control.goal_is_stale(event['initial_information_gain'], gain, now - accepted)
    if events:
        assert capture is not None and capture.is_file()
        bind_original_maps(events, capture)
