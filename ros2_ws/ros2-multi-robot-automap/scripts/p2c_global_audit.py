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


def nominal_peer_wait(event, grid, maps):
    """Independently rebuild the existing nominal all-peer waiting price."""
    from multi_robot_exploration import control
    world=event['world']
    if not world['battery_states']:
        return 0.
    bases,travel,charge_times={},{},{}
    assert set(event['final_poses'])==set(world['required'])
    for peer,final in event['final_poses'].items():
        local_grid=control.constrained_return_grid(grid,world['planning_map']['resolution'],
            world['planning_map']['origin'],maps[peer],{})
        _,nominal=control.plan_rally_leg(control.RallyPose(*final),local_grid,
            world['planning_map']['resolution'],world['planning_map']['origin'],world['positions'][peer])
        assert nominal,('missing complete nominal peer approach',peer)
        state=world['battery_states'][peer]
        full=(world['positions'][peer],*nominal)
        travel[peer]=sum(math.dist(a,b) for a,b in zip(full,full[1:]))/state['nominal_speed_mps']
        bases[peer]=scalar_budget({**event,'robot':peer},grid,maps,full,final[:2],5.)
        returning=contact(world,grid,maps,peer,world['positions'][peer])
        charge_times[peer]=(returning['path_distance_m']*state['return_path_factor']/state['nominal_speed_mps']
            +state['charge_duration_sec']+state.get('return_recovery_wait_sec',30.))
    _,waits=control.rally_wait_requirements(bases,world['battery_states'],
        {peer:state['mode'] for peer,state in world['battery_states'].items()},travel,charge_times)
    return waits[event['robot']]


def angle_error(first, second):
    assert math.isfinite(first) and math.isfinite(second)
    return abs(math.atan2(math.sin(first-second), math.cos(first-second)))


def audit_charge_demands(event, grid, maps):
    """Soft funding intentions may plan a corridor but never own navigation."""
    world = event['world']
    if 'charge_intents' not in world:
        return
    intents = world['charge_intents']
    planned = world['planned_return_routes']
    assert len(intents) <= 2 and set(planned) <= set(intents)
    slots = []
    for robot, demand in intents.items():
        assert robot in world['positions'] and robot in world['battery_states']
        assert robot not in world['charge_pending'], 'unissued demand declared as an issued owner'
        assert demand['slot'] in ('main', 'deferred')
        slots.append(demand['slot'])
        assert math.isfinite(demand['required_energy']) and demand['required_energy'] >= 0
        assert isinstance(demand['reason'], str) and (demand['park_for'] is None or isinstance(demand['park_for'], str))
        assert demand['destination'] is None or (len(demand['destination']) == 2 and np.isfinite(demand['destination']).all())
        if robot in planned:
            assert world['battery_states'][robot]['mode'] == 'ACTIVE', 'planned soft corridor for a native owner'
            rebuilt = contact(world, grid, maps, robot, world['positions'][robot])
            assert np.asarray(planned[robot]).shape == np.asarray(rebuilt['route']).shape
            assert np.allclose(planned[robot], rebuilt['route'], rtol=0, atol=1e-8), 'unrebuilt planned return corridor'
    assert len(slots) == len(set(slots)), 'duplicate charge intent slot'


def audit_clearance_beneficiary(event, grid, maps):
    world, actor, beneficiary = event['world'], event['robot'], event['beneficiary']
    assert beneficiary != actor and beneficiary in world['positions'] and beneficiary in world['battery_states']
    assert beneficiary in world['required'], 'clearance beneficiary is no longer a current participant'
    mode = world['battery_states'][beneficiary]['mode']
    if event['kind'] == 'local_return_yield':
        assert mode in ('RETURNING', 'CHARGING'), 'local yield lacks an actual native returner'
    else:
        assert (mode in ('RETURNING', 'CHARGING') or (mode == 'ACTIVE'
                and (beneficiary in world['charge_pending'] or beneficiary in world.get('charge_intents', {})))), \
                'charge clearance lacks a current demand or issued owner'
    for kind, ttl in (('pose_state', 2.), ('frame_state', 2.), ('map_snapshot', 5.), ('battery_state', 5.)):
        source = world['sources'][beneficiary+'/'+kind]
        assert 0 <= event['event_time']-source <= ttl, 'stale clearance beneficiary'
    reserved = contact(world, grid, maps, beneficiary, world['positions'][beneficiary])['route']
    if (mode == 'ACTIVE' and beneficiary in world.get('charge_intents', {})
            and beneficiary not in world['charge_pending']):
        assert beneficiary in world['planned_return_routes'], 'missing planned demand return corridor'
        assert np.allclose(reserved, world['planned_return_routes'][beneficiary], rtol=0, atol=1e-8)
    distances = [min(math.dist(point, other) for other in reserved) for point in event['route']]
    assert distances[-1] >= 1.8
    assert all(after+world['planning_map']['resolution'] >= min(before, 1.8)
               for before, after in zip(distances, distances[1:])), 'nonmonotone return clearance'


def audit_observer_heading(event, grid, maps):
    """A funded stationary heading repair is neither translation nor detection."""
    from multi_robot_exploration import control
    world, robot, now = event['world'], event['robot'], event['event_time']
    position = world['positions'][robot]
    assert robot == world['observer'] and world['target'] is not None
    assert robot not in world['live_routes'] and robot not in world['charge_pending']
    assert all(state['mode'] != 'RETURNING' for state in world['battery_states'].values())
    assert all(np.allclose(point, position, rtol=0, atol=1e-8)
               for point in (*event['route'], *event['complete_task_route']))
    assert np.allclose(event['requested_position'], position, rtol=0, atol=1e-8)
    assert np.isfinite(world['target']).all() and math.dist(position, world['target']) <= 2.65
    source = world['sources']['headquarters/target_detection']
    assert 0 <= now-source <= 60.
    confirmations = world['confirmations']
    assert robot in confirmations and math.isfinite(confirmations[robot]) and now-confirmations[robot] > 5.
    for peer, stamp in confirmations.items():
        assert math.isfinite(stamp) and stamp <= now
        assert (peer == robot or world['battery_states'].get(peer, {}).get('mode', 'ACTIVE') != 'ACTIVE'
                or now-stamp > 5.), 'fresh alternate observer'
    heading = math.atan2(world['target'][1]-position[1], world['target'][0]-position[0])
    assert angle_error(event['requested_yaw'], heading) <= 1e-8
    # These are the original detector FOV and survey timer in this gate.
    assert math.isclose(world['target_fov_rad'], math.pi/2, abs_tol=1e-8)
    assert angle_error(world['yaws'][robot], heading) > world['target_fov_rad']/4
    assert math.isclose(world['goal_timeout_sec'], 60., abs_tol=1e-8)
    assert math.isclose(event['waiting_time_budget_sec'], world['goal_timeout_sec'], abs_tol=1e-8)
    constrained = control.constrained_return_grid(grid, world['planning_map']['resolution'],
        world['planning_map']['origin'], maps[robot], {}) if robot in maps else grid
    safe = control.traversable_grid(constrained, world['planning_map']['resolution'], .35)
    cell = control.world_to_grid(*position, world['planning_map']['resolution'], *world['planning_map']['origin'])
    assert 0 <= cell[0] < safe.shape[0] and 0 <= cell[1] < safe.shape[1] and safe[cell]
    assert all(peer == robot or math.dist(position, other)+1e-8 >= .35
               for peer, other in world['positions'].items()), 'unsafe stationary peer clearance'


def point_segment_distance(point, start, end):
    dx, dy = end[0]-start[0], end[1]-start[1]
    square = dx*dx+dy*dy
    fraction = min(1., max(0., ((point[0]-start[0])*dx+(point[1]-start[1])*dy)/square)) if square else 0.
    return math.dist(point, (start[0]+fraction*dx, start[1]+fraction*dy))


def segment_separation(first, second, third, fourth):
    ux, uy = second[0]-first[0], second[1]-first[1]
    vx, vy = fourth[0]-third[0], fourth[1]-third[1]
    denominator = ux*vy-uy*vx
    if denominator:
        dx, dy = third[0]-first[0], third[1]-first[1]
        t, s = (dx*vy-dy*vx)/denominator, (dx*uy-dy*ux)/denominator
        if 0 <= t <= 1 and 0 <= s <= 1:
            return 0.
    return min(point_segment_distance(first, third, fourth), point_segment_distance(second, third, fourth),
               point_segment_distance(third, first, second), point_segment_distance(fourth, first, second))


def route_separation(first, second):
    assert first and second
    return min(segment_separation(a, b, c, d)
               for a, b in zip(first, (*first[1:], first[-1]))
               for c, d in zip(second, (*second[1:], second[-1])))


def camera_known_connector(saved, route):
    grid, resolution, origin = decode(saved), saved['resolution'], saved['origin']
    for start, end in zip(route, (*route[1:], route[-1])):
        cuts = {0., 1.}
        for axis in (0, 1):
            delta = end[axis]-start[axis]
            if delta:
                lower = math.floor((min(start[axis], end[axis])-origin[axis])/resolution)
                upper = math.floor((max(start[axis], end[axis])-origin[axis])/resolution)
                for boundary in range(lower+1, upper+1):
                    t = (origin[axis]+boundary*resolution-start[axis])/delta
                    if 0 < t < 1:
                        cuts.add(t)
        cuts = sorted(cuts)
        for t in (*cuts, *((a+b)/2 for a, b in zip(cuts, cuts[1:]))):
            point = tuple(a+t*(b-a) for a, b in zip(start, end))
            row, column = math.floor((point[1]-origin[1])/resolution), math.floor((point[0]-origin[0])/resolution)
            assert 0 <= row < grid.shape[0] and 0 <= column < grid.shape[1] and grid[row, column] == 0, 'unknown camera connector interval'


def camera_map_clearance(saved, route):
    grid, resolution, origin = decode(saved), saved['resolution'], saved['origin']
    columns = [math.floor((point[0]-origin[0])/resolution) for point in route]
    rows = [math.floor((point[1]-origin[1])/resolution) for point in route]
    margin = math.ceil(.35/resolution)+1
    r0, c0 = max(0, min(rows)-margin), max(0, min(columns)-margin)
    r1, c1 = min(grid.shape[0], max(rows)+margin+1), min(grid.shape[1], max(columns)+margin+1)
    for row, column in np.argwhere(grid[r0:r1, c0:c1] > 0):
        obstacle = (origin[0]+(column+c0+.5)*resolution, origin[1]+(row+r0+.5)*resolution)
        assert all(point_segment_distance(obstacle, start, end)+1e-8 >= .35
                   for start, end in zip(route, (*route[1:], route[-1]))), 'unsafe continuous camera map clearance'


def audit_camera_heading(event, grid, maps, owned=False):
    """Only a verified real owner may reprice a measured drift connector."""
    from multi_robot_exploration import control
    world, robot = event['world'], event['robot']
    current, goal = np.asarray(world['positions'][robot]), np.asarray(event['requested_position'])
    assert event['task_phase'] in ('EXPLORE', 'FOUND_UNCONFIRMED') and world['target'] is None
    assert robot in maps and robot in world['battery_states']
    assert robot in world['required'] and robot not in world['live_routes']
    assert robot not in world['charge_pending'] and robot not in world['charge_intents']
    assert 'nominal_orientation_time_sec' in event
    assert event['nominal_orientation_time_sec'] == event['waiting_time_budget_sec'] == world['goal_timeout_sec'] == 60.
    assert angle_error(event['requested_yaw'], round(event['requested_yaw']/(math.pi/8))*(math.pi/8)) <= 1e-8
    assert math.dist(current, goal) <= (.02+1e-8 if owned else 1e-8)
    if not owned:
        assert angle_error(event['requested_yaw'], world['yaws'][robot]) > .25
    constrained = control.constrained_return_grid(grid, world['planning_map']['resolution'],
        world['planning_map']['origin'], maps[robot], {})
    resolution, origin = world['planning_map']['resolution'], world['planning_map']['origin']
    endpoint = control.world_to_grid(*goal, resolution, *origin)
    landing = control.traversable_grid(constrained, resolution, .45)
    assert 0 <= endpoint[0] < landing.shape[0] and 0 <= endpoint[1] < landing.shape[1] and landing[endpoint]
    safe = control.traversable_grid(constrained, resolution, .35)
    delta = goal-current
    length = float(np.linalg.norm(delta))
    for route in (event['route'], event['complete_task_route']):
        assert np.allclose(route[0], current, rtol=0, atol=1e-8) and np.allclose(route[-1], goal, rtol=0, atol=1e-8)
        assert sum(math.dist(a, b) for a, b in zip(route, route[1:])) <= length+1e-8, 'hidden camera translation'
        camera_known_connector(world['planning_map'], route)
        for saved in (world['planning_map'], world['return_maps'][robot]):
            camera_map_clearance(saved, route)
        for peer, position in world['positions'].items():
            if peer == robot:
                continue
            for start, end in zip(route, (*route[1:], route[-1])):
                assert point_segment_distance(position, start, end)+1e-8 >= .6, 'unsafe continuous camera connector body clearance'
        for point, _ in samples(route, resolution):
            cell = control.world_to_grid(*point, resolution, *origin)
            assert 0 <= cell[0] < safe.shape[0] and 0 <= cell[1] < safe.shape[1] and safe[cell]
            assert all(peer == robot or math.dist(point, position)+1e-8 >= .6
                       for peer, position in world['positions'].items()), 'unsafe camera connector body clearance'
        assert all(not control.routes_conflict(route, reserved, 1.8)
                   for peer, reserved in world['planned_return_routes'].items() if peer != robot)
        reserved = [other for peer, other in (*world['live_routes'].items(), *world['planned_return_routes'].items()) if peer != robot]
        reserved += [contact(world, grid, maps, peer, world['positions'][peer])['route']
                     for peer, state in world['battery_states'].items()
                     if peer != robot and (state['mode'] in ('RETURNING', 'CHARGING') or peer in world['charge_pending'])]
        assert all(route_separation(route, other)+1e-8 >= 1.8 for other in reserved), 'unsafe continuous camera return reservation'


def audit_motion(event, *, owned=False):
    from multi_robot_exploration import control
    grid, maps = geometry_world(event)
    world, robot, kind = event['world'], event['robot'], event['kind']
    audit_charge_demands(event, grid, maps)
    if robot in world.get('charge_intents', {}):
        assert kind in ('local_return_yield', 'charge_clearance', 'rally_yield',
                        'target_observation_heading', 'target_reacquisition_scan'), 'ordinary work for a charge demand actor'
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
            if peer in world.get('pending_orientation_times', {}):
                assert route_separation(route, live)+1e-8 >= 1.8, 'ordinary route crosses a real heading owner reservation'
    if kind in ('local_return_yield', 'charge_clearance') and 'charge_intents' in world:
        audit_clearance_beneficiary(event, grid, maps)
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
            assert event['waiting_time_budget_sec']+1e-8>=nominal_peer_wait(event,grid,maps)+5., 'incomplete fleet wait budget'
    elif kind=='rally_yield':
        assert event['beneficiary'] in event['final_poses']
        assert event['waiting_time_budget_sec']+1e-8>=max(30.,nominal_peer_wait(event,grid,maps))+5., 'unfunded refuge waiting'
    elif kind=='target_observation_heading':
        audit_observer_heading(event, grid, maps)
    elif kind=='exploration_camera_heading':
        audit_camera_heading(event, grid, maps, owned)
    expected = scalar_budget(event, grid, maps, complete, destination, event['waiting_time_budget_sec'])
    if kind=='rally':
        expected=max(expected,scalar_budget(event,grid,maps,route,event['requested_position'],
            event['waiting_time_budget_sec']))
    assert math.isclose(expected, event['required_energy'], abs_tol=1e-6)
    if world['battery_states']:
        assert world['battery_states'][robot]['energy'] > expected
    return len(route)


def bind_sources(events, capture, native_path, charge_events=(), view_events=()):
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
        if event.get('kind') in ('target_observation_heading', 'exploration_camera_heading'):
            robot = event['robot']
            for kind, suffix in (('pose_state', 'odom'), ('frame_state', 'tf')):
                wanted[(f'/{robot}/{suffix}', round(world['sources'][robot+'/'+kind]*1e9))]
    for event in charge_events:
        wanted[(f"/gateway/received/{event['robot']}/battery_state", round(event['battery_source_time']*1e9))]
    for event in view_events:
        for kind, suffix in (('pose_source_time', 'odom'), ('frame_source_time', 'tf')):
            for prefix in ('/gateway/received', ''):
                wanted[(f"{prefix}/{event['robot']}/{suffix}", round(event[kind]*1e9))]
    matched = set()
    wanted_topics = {key[0] for key in wanted}
    with gzip.open(capture, 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            topic = row['topic']
            if topic not in wanted_topics:
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
                    q = msg.pose.pose.orientation
                    yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
                    original[key].append((msg.pose.pose.position.x, msg.pose.pose.position.y, yaw,
                                          q.x, q.y, q.z, q.w))
            elif isinstance(msg, TFMessage):
                for transform in msg.transforms:
                    if not (transform.header.frame_id.lstrip('/').endswith('map')
                            and transform.child_frame_id.lstrip('/').endswith('odom')):
                        continue
                    key = topic, transform.header.stamp.sec * 10**9 + transform.header.stamp.nanosec
                    if key in wanted:
                        t, q = transform.transform.translation, transform.transform.rotation
                        yaw = math.atan2(2*(q.w*q.z+q.x*q.y), 1-2*(q.y*q.y+q.z*q.z))
                        original[key].append((t.x, t.y, yaw, q.x, q.y, q.z, q.w))
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
                and (robot not in world.get('yaws', {}) or angle_error(oyaw+yaw, world['yaws'][robot]) <= 1e-8)
                for x, y, oyaw, *_ in odoms for tx, ty, yaw, *_ in frames), ('missing actual pose/TF/yaw', robot)
            if event.get('kind') in ('target_observation_heading', 'exploration_camera_heading') and robot == event['robot']:
                native_odoms = original[f'/{robot}/odom', round(sources[robot+'/pose_state']*1e9)]
                native_frames = original[f'/{robot}/tf', round(sources[robot+'/frame_state']*1e9)]
                assert any(np.allclose(odom, native_odom, rtol=0, atol=1e-8)
                    and np.allclose(frame, native_frame, rtol=0, atol=1e-8)
                    and np.allclose((frame[0]+math.cos(frame[2])*odom[0]-math.sin(frame[2])*odom[1],
                        frame[1]+math.sin(frame[2])*odom[0]+math.cos(frame[2])*odom[1]),
                        world['positions'][robot], rtol=0, atol=1e-8)
                    and angle_error(odom[2]+frame[2], world['yaws'][robot]) <= 1e-8
                    for odom in odoms for frame in frames for native_odom in native_odoms for native_frame in native_frames
                ), ('missing exact native and delivered heading source', robot)
            if world['battery_states']:
                state = world['battery_states'][robot]
                assert state in native[robot], ('missing exact native battery', robot)
                assert state in original[f'/gateway/received/{robot}/battery_state',
                    round(sources[robot + '/battery_state'] * 1e9)], ('missing delivered battery', robot)
        if world['target'] is not None:
            rows = original['/gateway/received/target_detection', round(sources['headquarters/target_detection'] * 1e9)]
            assert any(np.allclose((row['target_x'], row['target_y']), world['target'], rtol=0, atol=1e-8)
                       and (event.get('kind') != 'target_observation_heading'
                            or math.isclose(row['max_distance_m'], 3., abs_tol=1e-8)
                            and math.isclose(math.radians(row['field_of_view_deg']), world['target_fov_rad'], abs_tol=1e-8))
                       for row in rows), 'missing original delivered detection'
        for robot,stamp in world.get('confirmations',{}).items():
            rows=original['/gateway/received/target_detection',round(stamp*1e9)]
            assert any(row['robot']==robot and (event.get('kind') != 'target_observation_heading'
                or np.allclose((row['target_x'],row['target_y']),world['target'],rtol=0,atol=1e-8))
                for row in rows), 'missing producer-specific confirmation'
    for event in charge_events:
        robot, state, source = event['robot'], event['battery_state'], event['battery_source_time']
        assert state['stamp_sec'] == source and 0 <= event['event_time']-source <= 5.
        assert state in native[robot], ('missing exact native charge transition', robot)
        assert state in original[f'/gateway/received/{robot}/battery_state', round(source*1e9)], ('missing delivered charge transition', robot)
    for event in view_events:
        robot = event['robot']
        odoms = original[f'/gateway/received/{robot}/odom', round(event['pose_source_time']*1e9)]
        frames = original[f'/gateway/received/{robot}/tf', round(event['frame_source_time']*1e9)]
        native_odoms = original[f'/{robot}/odom', round(event['pose_source_time']*1e9)]
        native_frames = original[f'/{robot}/tf', round(event['frame_source_time']*1e9)]
        assert any(np.allclose(odom, native_odom, rtol=0, atol=1e-8)
            and np.allclose(frame, native_frame, rtol=0, atol=1e-8)
            and np.allclose((frame[0]+math.cos(frame[2])*odom[0]-math.sin(frame[2])*odom[1],
                frame[1]+math.sin(frame[2])*odom[0]+math.cos(frame[2])*odom[1]), event['position'], rtol=0, atol=1e-8)
            and angle_error(odom[2]+frame[2], event['yaw']) <= 1e-8
            for odom in odoms for frame in frames for native_odom in native_odoms for native_frame in native_frames
        ), ('missing exact native and delivered applied camera view source', robot)
    return len(required)


def applied_heading_confirmations(event, confirmations):
    if event.get('kind') == 'target_observation_heading':
        assert event['world']['confirmations'] == confirmations, 'heading omitted an applied producer confirmation'


def charge_ownership(event, issued, required=False):
    if required or 'charge_intents' in event['world']:
        assert 'charge_intents' in event['world'] and 'planned_return_routes' in event['world'], 'missing charge ownership proof schema'
        assert set(event['world']['charge_pending']) == set(issued), 'omitted or forged issued charge owner'
        if event.get('kind') is not None:
            assert event['robot'] not in issued, 'navigation for an issued charge owner'


VIEW_FIELDS = ('source', 'robot', 'position', 'yaw', 'observed_at_sec', 'pose_source_time', 'frame_source_time')


def search_view_key(view):
    assert view['source'] == 'ap_delivered_pose_and_heading_history'
    assert len(view['position']) == 2 and np.isfinite(view['position']).all() and math.isfinite(view['yaw'])
    assert all(math.isfinite(view[key]) for key in ('observed_at_sec', 'pose_source_time', 'frame_source_time'))
    return (*[math.floor(value/.5) for value in view['position']],
            math.floor((view['yaw']+math.pi)/(math.pi/8)) % 16)


def camera_ownership(event, owners, admissions, history):
    world = event['world']
    assert all(key in world for key in ('pending_orientation_times', 'search_views', 'pending_views')), 'missing camera proof schema'
    expected = {robot:60. for robot, token in owners.items() if admissions[token]['kind'] == 'exploration_camera_heading'}
    assert world['pending_orientation_times'] == expected, 'omitted or forged real heading allocation'
    views = {}
    for view in world['search_views']:
        assert set(view) == set(VIEW_FIELDS)
        key = search_view_key(view)
        assert key not in views and view['pose_source_time'] <= event['event_time'] and view['frame_source_time'] <= event['event_time']
        views[key] = view
    assert views == history, 'search history differs from actually applied physical views'
    for robot, view in world['pending_views'].items():
        assert robot in owners and robot in world['required'], 'predicted camera view without a real owner'
        original = admissions[owners[robot]]
        assert original['kind'] in ('exploration', 'exploration_camera_heading')
        assert np.allclose(view, (*original['requested_position'], original['requested_yaw']), rtol=0, atol=1e-8), 'predicted view differs from immutable goal'
    if event.get('kind') is not None:
        assert 'nominal_orientation_time_sec' in event, 'missing motion orientation allocation'
        assert event['nominal_orientation_time_sec'] == (60. if event['kind'] == 'exploration_camera_heading' else 0.)


def global_mission_audit(directory, required=False):
    if not required:
        return None
    events, admissions, owners, charge_proofs, revalidations = [], {}, {}, {}, {}
    completed,held_for={},defaultdict(dict)
    confirmations = {}
    issued_charges, charge_events = {}, []
    ownership_checks, cohort_worlds = [], []
    declared = json.loads((directory/'manifest.json').read_text()).get('config', {}) if (directory/'manifest.json').is_file() else {}
    charge_schema = 'charge_ownership' in declared.get('global_algorithm', {})
    camera_schema = 'stationary_camera_heading' in declared.get('global_algorithm', {})
    view_history, physical_sources, view_events, camera_checks = {}, {}, [], []
    sent = closed = revoked = charges = validated = 0
    for line in (directory / 'ledger.jsonl').open():
        event = json.loads(line)
        kind = event.get('event')
        if event.get('kind') == 'exploration_camera_heading':
            camera_schema = True
        if str(kind).startswith('coordinator_global_') and isinstance(event.get('world'), dict):
            cohort_worlds.append(event)
            if 'charge_intents' in event['world'] or 'planned_return_routes' in event['world']:
                charge_schema = True
            if any(key in event['world'] for key in ('pending_orientation_times', 'search_views', 'pending_views')):
                camera_schema = True
            camera_checks.append((event, dict(owners), dict(view_history)))
            if camera_schema:
                camera_ownership(event, owners, admissions, view_history)
        if kind == 'coordinator_global_search_view_applied':
            camera_schema = True
            assert event['task_phase'] in ('EXPLORE', 'FOUND_UNCONFIRMED')
            key = search_view_key(event)
            assert list(key) == event['view_key']
            robot, source = event['robot'], event['pose_source_time']
            assert source > physical_sources.get(robot, -math.inf), 'replayed physical odometry refreshed a camera bin'
            assert source >= view_history.get(key, {}).get('pose_source_time', -math.inf), 'older physical view replaced a newer camera bin'
            assert 0 <= event['event_time']-event['observed_at_sec'] <= 2.
            assert all(0 <= event['observed_at_sec']-event[field] <= 2. for field in ('pose_source_time', 'frame_source_time'))
            physical_sources[robot] = source
            view_history[key] = {field:event[field] for field in VIEW_FIELDS}
            view_events.append(event)
        elif kind == 'coordinator_global_confirmation':
            source = event['source_time']
            assert math.isfinite(source) and 0 <= event['event_time']-source <= 60.
            assert source > confirmations.get(event['robot'], -math.inf), 'nonmonotone applied producer confirmation'
            confirmations[event['robot']] = source
        elif kind == 'coordinator_global_motion_admission':
            applied_heading_confirmations(event, confirmations)
            ownership_checks.append((event, set(issued_charges)))
            charge_ownership(event, issued_charges, charge_schema)
            token = event['robot'], event['generation']
            assert token not in admissions
            assert event['robot'] not in owners, 'new admission for an actually owned robot'
            admissions[token] = event
        elif kind == 'coordinator_global_motion_sent':
            token = event['robot'], event['generation']
            assert token in admissions and event['robot'] not in owners
            saved = admissions[token]
            assert saved['kind']!='rally' or not held_for[event['robot']], 'returning before refuge dependency closes'
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
            completed[token]=event['status']
        elif kind=='coordinator_global_rally_yield_held':
            token=event['robot'],event['generation']
            assert completed.get(token)==4 and admissions[token]['kind']=='rally_yield'
            assert admissions[token]['beneficiary']==event['beneficiary']
            assert admissions[token]['final_poses'][event['beneficiary']]==event['final_pose']
            held_for[event['robot']][event['beneficiary']]=event['final_pose']
        elif kind=='coordinator_global_rally_yield_released':
            assert event['beneficiary'] in held_for[event['robot']]
            geometry_world(event)
            world,beneficiary=event['world'],event['beneficiary']
            if event['reason']=='beneficiary_complete':
                final=held_for[event['robot']][beneficiary]
                assert event['final_pose']==final and beneficiary not in owners
                assert world['battery_states'].get(beneficiary,{}).get('mode','ACTIVE')=='ACTIVE'
                assert math.dist(world['positions'][beneficiary],final[:2])<=.35
                assert any(robot==beneficiary and status==4 and admissions[token]['kind']=='rally'
                    and math.dist(admissions[token]['requested_position'],final[:2])<=.35
                    for token,status in completed.items() for robot in (token[0],))
            elif event['reason']=='target_unavailable':
                assert world['target'] is None
            else:
                assert event['reason']=='participant_unavailable'
                assert event['robot'] not in world['required'] or beneficiary not in world['required']
            held_for[event['robot']].pop(beneficiary)
            events.append(event)
        elif kind=='coordinator_global_rally_yields_reassigned':
            geometry_world(event)
            assert not owners and all(state['mode']=='ACTIVE' for state in event['world']['battery_states'].values())
            assert {robot:sorted(peers) for robot,peers in held_for.items() if peers}==event['yielded_for']
            assert set(event['final_poses'])==set(event['world']['required'])
            held_for.clear()
            events.append(event)
        elif kind == 'coordinator_global_motion_revalidation':
            applied_heading_confirmations(event, confirmations)
            ownership_checks.append((event, set(issued_charges)))
            charge_ownership(event, issued_charges, charge_schema)
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
            audit_motion(proof, owned=True)
            events.append(proof)
            validated += 1
        elif kind == 'coordinator_global_motion_revoked':
            revoked += 1
        elif kind == 'coordinator_global_charge_admission':
            ownership_checks.append((event, set(issued_charges)))
            charge_ownership(event, issued_charges, charge_schema)
            charge_proofs[event['robot']] = event
        elif kind in ('coordinator_global_charge_request_transition', 'coordinator_global_charge_request_closed'):
            charge_schema = True
            robot = event['robot']
            assert robot in issued_charges, 'transition without an issued charge request'
            request = issued_charges[robot]
            assert event['requested_at_sec'] == request['requested_at_sec']
            state, source = event['battery_state'], event['battery_source_time']
            assert state['stamp_sec'] == source and math.isfinite(source) and 0 <= event['event_time']-source <= 5.
            assert source > request['last_source'], 'nonmonotone applied charge state'
            if kind == 'coordinator_global_charge_request_transition':
                assert state['mode'] in ('RETURNING', 'CHARGING') and event['previous_mode'] == request['mode']
                request.update(observed_return_started=True, last_source=source, mode=state['mode'])
            else:
                assert event['observed_return_started'] == request['observed_return_started']
                if event['reason'] == 'native_cycle_closed':
                    assert state['mode'] == 'ACTIVE' and request['observed_return_started']
                elif event['reason'] == 'native_failure':
                    assert state['mode'] == 'FAILED'
                else:
                    assert event['reason'] == 'request_lease_ended' and state['mode'] == 'ACTIVE'
                    assert not request['observed_return_started'] and source >= request['requested_at_sec']+10.
                issued_charges.pop(robot)
            charge_events.append(event)
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
            charge_confirmations=world.get('confirmations',{})
            healthy={peer for peer,stamp in charge_confirmations.items() if 0<=event['event_time']-stamp<=5.
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
            if event.get('park_for') is not None:
                priced={**event,'budget_evaluated_at_sec':event['desired_task_budget_at_sec']}
                assert event['park_for'] in event['final_poses']
                assert event['desired_task_wait_sec']+1e-8>=max(30.,nominal_peer_wait(priced,grid,maps))+5.
            if event['reason']=='low_energy_after_actual_work':
                assert world['completed_legs'].get(robot,0)>0 and int(state.get('charge_count',0))==0
                desired=max(desired,.25*state['capacity']*state['charge_target_fraction'])
            assert math.isclose(desired,event['required_energy'],abs_tol=1e-6), 'unrebuilt post-charge task budget'
            if charge_schema:
                assert not issued_charges, 'concurrent issued charge requests'
            issued_charges[robot] = dict(requested_at_sec=dispatched['stamp_sec'],
                observed_return_started=False, last_source=state['stamp_sec'], mode=state['mode'])
            events.append(event)
            charges += 1
    if charge_schema:
        for event in cohort_worlds:
            assert 'charge_intents' in event['world'] and 'planned_return_routes' in event['world'], 'inconsistent charge ownership proof schema'
        for event, issued in ownership_checks:
            charge_ownership(event, issued, True)
    if camera_schema:
        for event, owned, history in camera_checks:
            camera_ownership(event, owned, admissions, history)
    bindings = bind_sources(events, directory / 'navigation_inputs.jsonl.gz', directory / 'safety_events.jsonl', charge_events, view_events)
    return dict(status='PASS', sent=sent, closed=closed, revoked=revoked, charge_admissions=charges,
        current_revalidations=validated,
        applied_charge_state_bindings=len(charge_events),
        applied_search_view_bindings=len(view_events),
        pending_issued_charge_requests_at_shutdown=issued_charges if charge_schema else 'LEGACY_NOT_INSTRUMENTED',
        refuge_dependencies_at_shutdown={robot:sorted(peers) for robot,peers in held_for.items() if peers},
        original_map_bindings=bindings, pending_at_owned_shutdown=sorted(owners),
        scope='Original DDS content, complete dispatch budgets, reservations and generation ownership; no physical success substitution')
