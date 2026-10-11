"""Independently check dispatched routes against the original local obstacles."""
import base64
import gzip
import json
import math
import zlib

import numpy as np
from scipy.spatial import cKDTree


def decode(saved):
    assert saved['encoding'] == 'zlib_base64_int16_le'
    grid = np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])), dtype='<i2')
    assert grid.size == math.prod(saved['shape'])
    grid = grid.reshape(saved['shape'])
    assert grid.ndim == 2 and grid.size and np.isfinite(saved['resolution']) and saved['resolution'] > 0
    assert len(saved['origin']) == 2 and np.isfinite(saved['origin']).all()
    return grid


def sampled_route(route, resolution):
    """Half-cell samples and travelled metres, independent of the planner."""
    points = [tuple(route[0])]
    distances = [0.]
    travelled = 0.
    for start, end in zip(route, route[1:]):
        length = math.dist(start, end)
        count = max(1, math.ceil(length/(resolution/2)))
        for i in range(1, count+1):
            points.append(tuple(a+(b-a)*i/count for a, b in zip(start, end)))
            distances.append(travelled+length*i/count)
        travelled += length
    return points, distances


def check_route(saved, route, local=False):
    grid = decode(saved)
    resolution, origin = saved['resolution'], saved['origin']
    occupied = np.argwhere(grid > 0)
    tree = cKDTree([(origin[0]+(col+.5)*resolution, origin[1]+(row+.5)*resolution)
                   for row, col in occupied]) if len(occupied) else None
    seen_safe = False
    previous = None
    points, travelled = sampled_route(route, resolution)
    for point, distance in zip(points, travelled):
        cell = (math.floor((point[1]-origin[1])/resolution), math.floor((point[0]-origin[0])/resolution))
        inside = 0 <= cell[0] < grid.shape[0] and 0 <= cell[1] < grid.shape[1]
        value = int(grid[cell]) if inside else -1
        assert value <= 0, ('occupied outbound point', point, cell)
        if not local:
            assert inside and value == 0, ('unknown outbound planning point', point, cell)
        if previous is not None and all(abs(a-b) == 1 for a, b in zip(cell, previous)):
            for cross in ((cell[0], previous[1]), (previous[0], cell[1])):
                if 0 <= cross[0] < grid.shape[0] and 0 <= cross[1] < grid.shape[1]:
                    assert grid[cross] <= 0, ('occupied diagonal corner', cross)
        safe = tree is None or tree.query(point)[0]+1e-8 >= .35
        if not safe:
            assert not seen_safe and distance <= .6+1e-8 and inside and value == 0, 'invalid initial clearance escape'
        seen_safe |= safe
        previous = cell


def audit_outbound(event):
    saved = event['outbound_map_route']
    assert saved['clearance_m'] == .35
    route = saved['route']
    assert route and all(len(point) == 2 and np.isfinite(point).all() for point in route)
    assert math.dist(route[0], event['current_position']) <= 1e-8
    assert math.dist(route[-1], event['requested_position']) <= 1e-8
    for key, tag, source in (
            ('local_map', 'ap_delivered_robot_map', event['robot']+'/map_snapshot'),
            ('planning_map', 'ap_delivered_planning_map', 'headquarters/fused_map_snapshot')):
        geometry = saved[key]
        assert geometry['source'] == tag
        assert geometry['source_time'] == event['inputs'][source]['source_time']
        assert 0 <= event['event_time']-geometry['source_time'] <= 5.
        check_route(geometry, route, local=key == 'local_map')
    return len(route)


def bind_original_maps(events, capture):
    """Bind local cells and the unchanged bounded planning heuristic to raw CDR."""
    from rclpy.serialization import deserialize_message
    from nav_msgs.msg import OccupancyGrid

    wanted = {}
    for index, event in enumerate(events):
        for key, topic in (('local_map', '/'+event['robot']+'/map'), ('planning_map', '/merge_map')):
            saved = event['outbound_map_route'][key]
            if saved is None:
                continue
            wanted.setdefault((topic, round(saved['source_time']*1e9)), []).append((index, event, key))
    required = {(index, label) for rows in wanted.values() for index, _, label in rows}
    found = set()
    with gzip.open(capture, 'rt') as stream:
        for line in stream:
            row = json.loads(line)
            if row['topic'] not in {key[0] for key in wanted}:
                continue
            msg = deserialize_message(base64.b64decode(row['cdr']), OccupancyGrid)
            key = (row['topic'], msg.header.stamp.sec*10**9+msg.header.stamp.nanosec)
            if key not in wanted:
                continue
            original = np.asarray(msg.data).reshape(msg.info.height, msg.info.width)
            # A mapper can publish different contents with the same header.
            # Match each witness independently; an earlier nonmatching version
            # must neither reject nor stand in for a later exact raw sample.
            for index, event, label in wanted[key]:
                if (index, label) in found:
                    continue
                saved = event['outbound_map_route'][label]
                grid = decode(saved)
                if (tuple(original.shape) != tuple(saved['shape']) or msg.info.resolution != saved['resolution']
                        or tuple(saved['origin']) != (msg.info.origin.position.x, msg.info.origin.position.y)):
                    continue
                if label == 'local_map':
                    if not np.array_equal(original, grid):
                        continue
                else:
                    changed = set(map(tuple, np.argwhere(original != grid)))
                    declared = set(map(tuple, event.get('planning_map_self_return_cells', {}).values()))
                    if changed != declared:
                        continue
                    valid = True
                    for r, col in changed:
                        if not (original[r, col] >= 50 and grid[r, col] == 0 and saved['resolution']*math.sqrt(2) <= .1
                                and 1 <= r < grid.shape[0]-1 and 1 <= col < grid.shape[1]-1):
                            valid = False
                            break
                        window = original[r-1:r+2, col-1:col+2].copy();window[1,1] = 0
                        if not np.all(window == 0):
                            valid = False
                            break
                    if not valid:
                        continue
                found.add((index, label))
    assert found == required, ('missing matching original outbound source map', required-found)
    return len(wanted)


def audit_exploration_returns(event, required=False):
    """Rebuild ordinary traffic's complete safety-return reservations."""
    if (event['kind'] not in ('exploration', 'initial_visual_search') or not event.get('battery_states')
            or event.get('task_phase') not in ('EXPLORE', 'FOUND_UNCONFIRMED')):
        return None
    if required:
        assert 'exploration_pending_charge_requests' in event and 'exploration_safety_returns' in event
    states = event['battery_states']
    pending = event.get('exploration_pending_charge_requests', {})
    busy = bool(pending) or any(state['mode'] == 'RETURNING' for state in states.values())
    saved = event.get('exploration_safety_returns')
    if not busy:
        assert saved is None
        return None
    assert saved is not None, 'ordinary traffic lacks safety-return reservations'
    assert event['task_phase'] in ('EXPLORE', 'FOUND_UNCONFIRMED') and saved['clearance_m'] == 1.8
    assert states == saved['battery_states'] and event['robot_positions'] == saved['robot_positions']
    modes = saved['battery_modes']
    assert modes == {name: state['mode'] for name, state in states.items()}
    now, inputs = event['event_time'], saved['inputs']
    assert 0 <= now-saved['evaluated_at_sec'] <= 2.
    for name, stamp in pending.items():
        assert name in states and modes[name] != 'FAILED' and math.isfinite(stamp) and stamp <= now
    active = {name for name, mode in modes.items() if mode != 'FAILED'}
    for name in active:
        assert all(name+'/'+kind in inputs and name+'/'+kind in event['inputs']
                   for kind in ('pose_state', 'frame_state', 'map_snapshot', 'battery_state'))
        assert states[name]['stamp_sec'] == inputs[name+'/battery_state']['source_time']
    for key, sample in inputs.items():
        limit = 2. if key.endswith(('/pose_state', '/frame_state')) else 5.
        assert math.isfinite(sample['source_time']) and 0 < sample['ttl_sec'] <= limit
        assert 0 <= now-sample['source_time'] <= sample['ttl_sec']
        assert key in event['inputs'] and event['inputs'][key]['source_time'] == sample['source_time']
    from multi_robot_exploration import control
    planning, source = saved['planning_map'], saved['source_map']
    assert planning['source_time'] == source['source_time'] == inputs['headquarters/fused_map_snapshot']['source_time']
    assert planning['resolution'] == source['resolution'] and planning['origin'] == source['origin']
    positions = saved['robot_positions']
    grid, cells = control.planning_grid_without_self_returns(decode(source), planning['resolution'], planning['origin'],
        {name: point for name, point in positions.items() if modes[name] in ('ACTIVE', 'UNKNOWN')})
    assert np.array_equal(grid, decode(planning))
    assert {name: list(cell) for name, cell in cells.items()} == saved['self_return_cells']
    maps = {}
    for name, geometry in saved['return_maps'].items():
        assert geometry['source_time'] == inputs[name+'/map_snapshot']['source_time']
        maps[name] = dict(data=decode(geometry), resolution=geometry['resolution'], origin=geometry['origin'])
    assert active <= maps.keys()
    rebuilt = control.rally_return_reservations(grid, planning['resolution'], planning['origin'], positions,
        states, modes, set(pending), return_maps=maps)
    assert rebuilt is not None and rebuilt and set(rebuilt) == set(saved['protected_routes'])
    assert all(np.array_equal(route, saved['protected_routes'][name]) for name, route in rebuilt.items())
    name = event['robot']
    assert modes[name] == 'ACTIVE' and name not in rebuilt
    original = saved['admitted_route']
    assert original and np.array_equal(original, event['outbound_map_route']['route'][1:])
    position = positions[name]
    nearest = min(range(len(original)), key=lambda index: math.dist(position, original[index]))
    remaining = [position, *original[nearest if math.dist(position, original[nearest]) <= .35 else 0:]]
    assert np.array_equal(remaining, saved['route'])
    assert all(math.dist(point, other) >= 1.8 for point in remaining
               for reserved in rebuilt.values() for other in reserved), 'ordinary route enters safety-return reservation'
    return saved


def outbound_route_audit(path, required=False, capture=None, require_return_reservations=False, native_capture=None):
    if not required:
        return None
    events = [];vetoes = 0;vertices = 0;protected_events = []
    for line in path.open():
        event = json.loads(line)
        if event.get('event') == 'coordinator_navigation_map_veto':
            assert event['reason'] == 'outbound_local_obstacle'
            vetoes += 1
        if event.get('event') != 'coordinator_navigation_decision':
            continue
        vertices += audit_outbound(event)
        saved = audit_exploration_returns(event, require_return_reservations)
        if saved is not None:
            protected_events.append(event)
        events.append(event)
    sources = bind_original_maps(events, capture) if capture is not None else None
    return_sources = body_sources = native_sources = 0
    if protected_events:
        assert capture is not None and native_capture is not None
        bindings = [dict(robot=name, outbound_map_route=dict(local_map=geometry, planning_map=saved['planning_map']),
            planning_map_self_return_cells=saved['self_return_cells'])
            for event in protected_events for saved in (event['exploration_safety_returns'],)
            for name, geometry in saved['return_maps'].items()]
        return_sources = bind_original_maps(bindings, capture)
        from p2c_preparation_approach import bind_original_positions
        body_sources = bind_original_positions([dict(inputs=event['inputs'],
            rally_preparation=event['exploration_safety_returns']) for event in protected_events], capture, .2)
        originals = {}
        for line in native_capture.open():
            row = json.loads(line)
            if row['topic'].endswith('/battery_state'):
                originals.setdefault(row['topic'].split('/')[1], []).append(row['data'])
        for event in protected_events:
            for name, state in event['exploration_safety_returns']['battery_states'].items():
                assert state in originals.get(name, []), 'missing exact native safety-return battery source'
                native_sources += 1
    return dict(status='PASS', decisions=len(events), vertices=vertices, map_vetoes=vetoes,
                original_source_maps=sources,
                return_reservations_declared=require_return_reservations, independent_return_decisions=len(protected_events),
                return_source_maps=return_sources, return_pose_frame_sources=body_sources, return_native_battery_sources=native_sources,
                scope='Dispatch-time planned routes and original map/source binding; no claim that Nav2 follows every vertex or that execution remains connected')
