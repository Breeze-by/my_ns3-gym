"""Read-only dispatch audit of the global executor and its original DDS inputs.

Route sampling and scalar energy reconstruction are independent of the new
planner. Qualified contact paths use the existing reviewed return algorithm.
This checks admission, not Nav2 trajectory fidelity or hardware guarantees.
"""
import base64
import gzip
import json
import math
import zlib
from collections import defaultdict

import numpy as np
from scipy.spatial import cKDTree


def decode(saved):
    assert saved['encoding'] == 'zlib_base64_int16_le'
    grid = np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])), dtype='<i2')
    assert grid.size == math.prod(saved['shape']) and len(saved['shape']) == 2
    assert math.isfinite(saved['resolution']) and saved['resolution'] > 0
    assert len(saved['origin']) == 2 and np.isfinite(saved['origin']).all()
    return grid.reshape(saved['shape'])


def samples(route, resolution):
    assert route and all(len(p) == 2 and np.isfinite(p).all() for p in route)
    yield tuple(route[0]), 0.
    distance = 0.
    for start, end in zip(route, route[1:]):
        length = math.dist(start, end)
        count = max(1, math.ceil(length / (resolution / 2)))
        for i in range(1, count + 1):
            yield tuple(a + (b - a) * i / count for a, b in zip(start, end)), distance + length * i / count
        distance += length


def check_route(saved, route, local=False):
    grid = decode(saved)
    resolution, origin = saved['resolution'], saved['origin']
    occupied = np.argwhere(grid > 0)
    tree = cKDTree([(origin[0] + (c + .5) * resolution, origin[1] + (r + .5) * resolution)
                   for r, c in occupied]) if len(occupied) else None
    safe_seen = False
    previous = None
    for point, travelled in samples(route, resolution):
        cell = math.floor((point[1] - origin[1]) / resolution), math.floor((point[0] - origin[0]) / resolution)
        inside = 0 <= cell[0] < grid.shape[0] and 0 <= cell[1] < grid.shape[1]
        value = int(grid[cell]) if inside else -1
        assert value <= 0, ('occupied route', point)
        if not local:
            assert inside and value == 0, ('unknown planning route', point)
        if previous is not None and all(abs(a - b) == 1 for a, b in zip(cell, previous)):
            for cross in ((cell[0], previous[1]), (previous[0], cell[1])):
                if 0 <= cross[0] < grid.shape[0] and 0 <= cross[1] < grid.shape[1]:
                    assert grid[cross] <= 0, ('occupied diagonal corner', cross)
        safe = tree is None or tree.query(point)[0] + 1e-8 >= .35
        if not safe:
            assert not safe_seen and travelled <= .6 + 1e-8 and inside and value == 0
        safe_seen |= safe
        previous = cell


def geometry_world(event):
    world = event['world']
    source, planned = world['source_map'], world['planning_map']
    assert source['source_time'] == planned['source_time'] == world['sources']['headquarters/fused_map_snapshot']
    assert source['resolution'] == planned['resolution'] and source['origin'] == planned['origin']
    raw, grid = decode(source), decode(planned)
    assert raw.shape == grid.shape
    changed = set(map(tuple, np.argwhere(raw != grid)))
    declared = {tuple(cell) for cell in world['self_return_cells'].values()}
    assert changed == declared
    for robot, (row, col) in world['self_return_cells'].items():
        assert planned['resolution'] * math.sqrt(2) <= .1
        assert 1 <= row < grid.shape[0] - 1 and 1 <= col < grid.shape[1] - 1
        assert raw[row, col] >= 50 and grid[row, col] == 0
        window = raw[row-1:row+2, col-1:col+2].copy()
        window[1, 1] = 0
        assert np.all(window == 0)
        point = world['positions'][robot]
        assert (row, col) == (math.floor((point[1] - planned['origin'][1]) / planned['resolution']),
                              math.floor((point[0] - planned['origin'][0]) / planned['resolution']))
    local = {}
    for robot, saved in world['return_maps'].items():
        assert saved['source_time'] == world['sources'][robot + '/map_snapshot']
        local[robot] = dict(data=decode(saved), resolution=saved['resolution'], origin=saved['origin'])
    for key, source_time in world['sources'].items():
        ttl = 60. if key.endswith('/target_detection') else 2. if key.endswith(('/pose_state', '/frame_state')) else 5.
        assert math.isfinite(source_time) and 0 <= event['event_time'] - source_time <= ttl
    for robot, state in world['battery_states'].items():
        assert state['stamp_sec'] == world['sources'][robot + '/battery_state']
    return grid, local


def contact(world, grid, maps, robot, point):
    from multi_robot_exploration import control
    state = world['battery_states'][robot]
    rows = control.qualified_return_candidates(grid, world['planning_map']['resolution'],
        world['planning_map']['origin'], point, (state['charge_x'], state['charge_y']),
        state['charge_radius_m'], maps.get(robot))
    choice = min((row for row in rows if row['qualified']),
                 key=lambda row: (row['path_distance_m'], row['source'] != 'local'), default=None)
    assert choice is not None, ('missing qualified return', robot, point)
    return choice


def scalar_budget(event, grid, maps, route, destination, wait=0.):
    world, robot = event['world'], event['robot']
    if not world['battery_states']:
        return 0.
    state = world['battery_states'][robot]
    evaluated = event['budget_evaluated_at_sec']
    assert math.isfinite(evaluated) and evaluated <= event['event_time']
    sources = world['sources']
    map_age = max(evaluated - sources[key] for key in
        ('headquarters/fused_map_snapshot', robot + '/map_snapshot') if key in sources)
    pose_age = max(evaluated - sources[robot + '/' + kind] for kind in ('pose_state', 'frame_state'))
    assert 0 <= map_age <= 5. and 0 <= pose_age <= 2. and math.isfinite(wait) and wait >= 0
    move, idle = state['move_cost_per_m'], state['idle_cost_per_sec']
    speed, factor = state['nominal_speed_mps'], state['return_path_factor']
    assert move >= 0 and idle >= 0 and speed > 0 and factor >= 1
    def returning(distance):
        motion = distance * factor + .3 * (pose_age + 1.)
        return (motion * move + (motion / speed + state.get('return_recovery_wait_sec', 30.)
                + map_age + pose_age + 1.) * idle + state['return_safety_margin'])
    current = contact(world, grid, maps, robot, world['positions'][robot])
    endpoint = contact(world, grid, maps, robot, destination)
    length = sum(math.dist(a, b) for a, b in zip(route, route[1:]))
    task = length * 1.25 * (move + idle / speed) + returning(endpoint['path_distance_m'])
    return max(task, returning(current['path_distance_m'])) + idle * wait


def audit_motion(event):
    from multi_robot_exploration import control
    grid, maps = geometry_world(event)
    world, robot, kind = event['world'], event['robot'], event['kind']
    route = event['route']
    assert np.allclose(route[0], world['positions'][robot], rtol=0, atol=1e-8)
    assert np.allclose(route[-1], event['requested_position'], rtol=0, atol=1e-8)
    assert world['battery_states'].get(robot, {}).get('mode', 'ACTIVE') == 'ACTIVE'
    check_route(world['planning_map'], route)
    if robot in world['return_maps']:
        check_route(world['return_maps'][robot], route, local=True)
    for peer, position in world['positions'].items():
        if peer != robot:
            assert all(math.dist(point, position) + 1e-8 >= .35 for point in route[2:])
    for peer, live in world['live_routes'].items():
        if peer != robot:
            assert not control.routes_conflict(route, live, 1.8), ('overlapping owned routes', robot, peer)
    for peer, state in world['battery_states'].items():
        if state['mode'] in ('RETURNING', 'CHARGING') or peer in world['charge_pending']:
            reserved = contact(world, grid, maps, peer, world['positions'][peer])['route']
            if peer == robot:
                raise AssertionError('new navigation for a protected returner')
            if kind in ('local_return_yield', 'charge_clearance') and event['beneficiary'] == peer:
                distances = [min(math.dist(p, other) for other in reserved) for p in route]
                assert distances[-1] >= 1.8
                assert all(after + world['planning_map']['resolution'] >= min(before, 1.8)
                           for before, after in zip(distances, distances[1:]))
            else:
                assert not control.routes_conflict(route, reserved, 1.8)
    complete = event['complete_task_route']
    check_route(world['planning_map'], complete)
    if robot in world['return_maps']:
        check_route(world['return_maps'][robot], complete, local=True)
    destination = event['requested_position']
    if kind == 'rally':
        assert set(event['final_poses']) == set(world['required'])
        final = event['final_poses'][robot]
        destination = final[:2]
        assert np.allclose(complete[-1], destination, rtol=0, atol=1e-8)
        assert event['waiting_time_budget_sec'] >= 5.
        assert world['target'] is not None
        for peer, pose in event['final_poses'].items():
            assert control.rally_target_view(grid, world['planning_map']['resolution'],
                world['planning_map']['origin'], pose[:2], world['target'], 2.65)
            assert all(other == peer or math.dist(pose[:2], p[:2]) >= .8
                       for other, p in event['final_poses'].items())
        if world['battery_states']:
            bases, travel, charge_times = {}, {}, {}
            for peer, final in event['final_poses'].items():
                local_grid = control.constrained_return_grid(grid, world['planning_map']['resolution'],
                    world['planning_map']['origin'], maps[peer], {})
                _, nominal = control.plan_rally_leg(control.RallyPose(*final), local_grid,
                    world['planning_map']['resolution'], world['planning_map']['origin'], world['positions'][peer])
                assert nominal, ('missing complete nominal peer approach', peer)
                state = world['battery_states'][peer]
                full = (world['positions'][peer], *nominal)
                travel[peer] = sum(math.dist(a,b) for a,b in zip(full,full[1:])) / state['nominal_speed_mps']
                bases[peer] = scalar_budget({**event,'robot':peer},grid,maps,full,final[:2],5.)
                returning = contact(world,grid,maps,peer,world['positions'][peer])
                charge_times[peer] = (returning['path_distance_m']*state['return_path_factor'] / state['nominal_speed_mps']
                    + state['charge_duration_sec'] + state.get('return_recovery_wait_sec',30.))
            _, waits = control.rally_wait_requirements(bases,world['battery_states'],
                {peer:state['mode'] for peer,state in world['battery_states'].items()},travel,charge_times)
            assert event['waiting_time_budget_sec'] + 1e-8 >= waits[robot] + 5., 'incomplete fleet wait budget'
    expected = scalar_budget(event, grid, maps, complete, destination, event['waiting_time_budget_sec'])
    if kind=='rally':
        expected=max(expected,scalar_budget(event,grid,maps,route,event['requested_position'],
            event['waiting_time_budget_sec']))
    assert math.isclose(expected, event['required_energy'], abs_tol=1e-6)
    if world['battery_states']:
        assert world['battery_states'][robot]['energy'] > expected
    return len(route)


def bind_sources(events, capture, native_path):
    """Bind exact content; identical stamps with different maps cannot substitute."""
    from nav_msgs.msg import OccupancyGrid, Odometry
    from rclpy.serialization import deserialize_message
    from std_msgs.msg import String
    from tf2_msgs.msg import TFMessage
    wanted, original = defaultdict(list), defaultdict(list)
    for index, event in enumerate(events):
        world = event['world']
        wanted[('/merge_map', round(world['source_map']['source_time'] * 1e9))].append(
            (index, 'source_map', world['source_map']))
        for robot, saved in world['return_maps'].items():
            wanted[(f'/gateway/received/{robot}/map', round(saved['source_time'] * 1e9))].append(
                (index, robot + '/map', saved))
        for robot in world['required']:
            for kind, suffix in (('pose_state', 'odom'), ('frame_state', 'tf'), ('battery_state', 'battery_state')):
                if robot + '/' + kind in world['sources']:
                    wanted[(f'/gateway/received/{robot}/{suffix}', round(world['sources'][robot + '/' + kind] * 1e9))]
        if world['target'] is not None:
            wanted[('/gateway/received/target_detection', round(world['sources']['headquarters/target_detection'] * 1e9))]
        for stamp in world.get('confirmations',{}).values():
            wanted[('/gateway/received/target_detection',round(stamp*1e9))]
    matched = set()
    with gzip.open(capture, 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            topic = row['topic']
            if topic not in {key[0] for key in wanted}:
                continue
            msg = deserialize_message(base64.b64decode(row['cdr']),
                OccupancyGrid if topic.endswith('map') else Odometry if topic.endswith('/odom')
                else TFMessage if topic.endswith('/tf') else String)
            if isinstance(msg, OccupancyGrid):
                key = topic, msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
                if key not in wanted:
                    continue
                for index, label, saved in wanted[key]:
                    if (index, label) in matched:
                        continue
                    if (tuple(saved['shape']) == (msg.info.height, msg.info.width)
                            and saved['resolution'] == msg.info.resolution
                            and tuple(saved['origin']) == (msg.info.origin.position.x, msg.info.origin.position.y)
                            and np.array_equal(decode(saved).ravel(), msg.data)):
                        matched.add((index, label))
            elif isinstance(msg, Odometry):
                key = topic, msg.header.stamp.sec * 10**9 + msg.header.stamp.nanosec
                if key in wanted:
                    original[key].append((msg.pose.pose.position.x, msg.pose.pose.position.y))
            elif isinstance(msg, TFMessage):
                for transform in msg.transforms:
                    if not (transform.header.frame_id.lstrip('/').endswith('map')
                            and transform.child_frame_id.lstrip('/').endswith('odom')):
                        continue
                    key = topic, transform.header.stamp.sec * 10**9 + transform.header.stamp.nanosec
                    if key in wanted:
                        t, q = transform.transform.translation, transform.transform.rotation
                        yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
                        original[key].append((t.x, t.y, yaw))
            else:
                data = json.loads(msg.data)
                stamp = data['_gateway']['source_time'] if topic.endswith('/target_detection') else data['stamp_sec']
                key = topic, round(stamp * 1e9)
                if key in wanted:
                    original[key].append(data)
    required = {(index, label) for rows in wanted.values() for index, label, _ in rows}
    assert matched == required, ('missing original source maps', required - matched)
    native = defaultdict(list)
    for line in native_path.open():
        row = json.loads(line)
        if row['topic'].endswith('/battery_state'):
            native[row['topic'].split('/')[1]].append(row['data'])
    for event in events:
        world, sources = event['world'], event['world']['sources']
        for robot in world['required']:
            odoms = original[f'/gateway/received/{robot}/odom', round(sources[robot + '/pose_state'] * 1e9)]
            frames = original[f'/gateway/received/{robot}/tf', round(sources[robot + '/frame_state'] * 1e9)]
            assert any(np.allclose((tx + math.cos(yaw)*x - math.sin(yaw)*y,
                ty + math.sin(yaw)*x + math.cos(yaw)*y), world['positions'][robot], rtol=0, atol=1e-8)
                for x, y in odoms for tx, ty, yaw in frames), ('missing actual pose/TF', robot)
            if world['battery_states']:
                state = world['battery_states'][robot]
                assert state in native[robot], ('missing exact native battery', robot)
                assert state in original[f'/gateway/received/{robot}/battery_state',
                    round(sources[robot + '/battery_state'] * 1e9)], ('missing delivered battery', robot)
        if world['target'] is not None:
            rows = original['/gateway/received/target_detection', round(sources['headquarters/target_detection'] * 1e9)]
            assert any(np.allclose((row['target_x'], row['target_y']), world['target'], rtol=0, atol=1e-8)
                       for row in rows), 'missing original delivered detection'
        for robot,stamp in world.get('confirmations',{}).items():
            rows=original['/gateway/received/target_detection',round(stamp*1e9)]
            assert any(row['robot']==robot for row in rows), 'missing producer-specific confirmation'
    return len(required)


def global_mission_audit(directory, required=False):
    if not required:
        return None
    events, admissions, owners, charge_proofs, revalidations = [], {}, {}, {}, {}
    sent = closed = revoked = charges = validated = 0
    for line in (directory / 'ledger.jsonl').open():
        event = json.loads(line)
        kind = event.get('event')
        if kind == 'coordinator_global_motion_admission':
            token = event['robot'], event['generation']
            assert token not in admissions
            admissions[token] = event
        elif kind == 'coordinator_global_motion_sent':
            token = event['robot'], event['generation']
            assert token in admissions and event['robot'] not in owners
            saved = admissions[token]
            for key, source in saved['world']['sources'].items():
                ttl=60. if key.endswith('/target_detection') else 2. if key.endswith(('/pose_state','/frame_state')) else 5.
                assert 0 <= event['stamp_sec']-source <= ttl, 'expired source at actual send'
            audit_motion(saved)
            owners[event['robot']] = token
            events.append(saved)
            sent += 1
        elif kind == 'coordinator_global_motion_closed':
            token = event['robot'], event['generation']
            previous = owners.pop(event['robot'], None)
            assert previous == token or (previous is None and token in admissions
                and str(event['error']).startswith('send_exception:')), 'old result released another generation'
            closed += 1
        elif kind == 'coordinator_global_motion_revalidation':
            token = event['robot'], event['generation']
            assert owners.get(event['robot']) == token
            original = admissions[token]
            assert (event['requested_position'] == original['requested_position']
                    and event['requested_yaw'] == original['requested_yaw']
                    and event['kind'] == original['kind']), 'revalidation changed an issued goal'
            revalidations[token] = event
        elif kind == 'coordinator_global_motion_revalidated':
            token = event['robot'], event['generation']
            assert owners.get(event['robot']) == token
            proof = revalidations.pop(token)
            for key, source in proof['world']['sources'].items():
                ttl=60. if key.endswith('/target_detection') else 2. if key.endswith(('/pose_state','/frame_state')) else 5.
                assert 0 <= event['validated_at_sec']-source <= ttl, 'expired current revalidation source'
            audit_motion(proof)
            events.append(proof)
            validated += 1
        elif kind == 'coordinator_global_motion_revoked':
            revoked += 1
        elif kind == 'coordinator_global_charge_admission':
            charge_proofs[event['robot']] = event
        elif kind == 'coordinator_global_charge_sent':
            dispatched = event
            event = charge_proofs.pop(dispatched['robot'])
            grid, maps = geometry_world(event)
            world, robot = event['world'], event['robot']
            expected = scalar_budget(event, grid, maps, (world['positions'][robot],), world['positions'][robot])
            assert math.isclose(expected, event['current_return_required'], abs_tol=1e-6)
            state = world['battery_states'][robot]
            assert expected < state['energy'] <= event['required_energy'] <= state['capacity'] * state['charge_target_fraction']
            assert robot not in owners and all(s['mode'] not in ('RETURNING', 'CHARGING') for s in world['battery_states'].values())
            confirmations=world.get('confirmations',{})
            healthy={peer for peer,stamp in confirmations.items() if 0<=event['event_time']-stamp<=5.
                and world['battery_states'].get(peer,{}).get('mode')=='ACTIVE'}
            assert healthy!={robot} or world.get('observer')!=robot, 'charging the sole healthy observer'
            rebuilt = contact(world,grid,maps,robot,world['positions'][robot])
            assert np.array_equal(rebuilt['route'],event['return_route'])
            if rebuilt['path_distance_m']>0:
                assert all(math.dist(point,position)>=1.8 for point in event['return_route']
                    for peer,position in world['positions'].items() if peer!=robot)
            assert all(0<=dispatched['stamp_sec']-source<=
                (60. if key.endswith('/target_detection') else 2. if key.endswith(('/pose_state','/frame_state')) else 5.)
                for key,source in world['sources'].items())
            assert event['desired_task_route'] and event['destination'] is not None
            desired = scalar_budget({**event,'budget_evaluated_at_sec':event['desired_task_budget_at_sec']},
                grid,maps,event['desired_task_route'],event['destination'],event['desired_task_wait_sec'])
            if event['reason']=='low_energy_after_actual_work':
                assert world['completed_legs'].get(robot,0)>0 and int(state.get('charge_count',0))==0
                desired=max(desired,.25*state['capacity']*state['charge_target_fraction'])
            assert math.isclose(desired,event['required_energy'],abs_tol=1e-6), 'unrebuilt post-charge task budget'
            events.append(event)
            charges += 1
    bindings = bind_sources(events, directory / 'navigation_inputs.jsonl.gz', directory / 'safety_events.jsonl')
    return dict(status='PASS', sent=sent, closed=closed, revoked=revoked, charge_admissions=charges,
        current_revalidations=validated,
        original_map_bindings=bindings, pending_at_owned_shutdown=sorted(owners),
        scope='Original DDS content, complete dispatch budgets, reservations and generation ownership; no physical success substitution')
