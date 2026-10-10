"""Rebuild a policy top-up separately from the current physical trip cost."""
import json
import math
from types import SimpleNamespace

import numpy as np
from multi_robot_exploration import control
from p2c_return_preparation import audit_preparation, decode_grid


def initial_replenishment_audit(ledger, enabled=False, native_capture=None):
    native = {}
    if enabled:
        assert native_capture is not None and native_capture.is_file()
        for line in native_capture.open():
            row = json.loads(line)
            if row['topic'].endswith('/battery_state'):
                name = row['topic'].split('/')[1]
                native.setdefault(name, []).append(row['data'])
    decisions_by_robot, commands, outcomes = {}, {}, {}
    for line in ledger.open():
        event = json.loads(line)
        kind = event.get('event')
        if kind == 'coordinator_navigation_decision':
            source = event.get('dispatch_goal_source_time_sec', event['event_time'])
            decisions_by_robot.setdefault(event['robot'], []).append((source, event['kind']))
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
        robots=sorted(robots), scope='One initial near-home replenishment after actual ordinary success; scheduling threshold and current full trip cost rebuilt separately. Native credit and physical return remain separate original audits.')
