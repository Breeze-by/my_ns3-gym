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


def outbound_route_audit(path, required=False, capture=None):
    if not required:
        return None
    events = [];vetoes = 0;vertices = 0
    for line in path.open():
        event = json.loads(line)
        if event.get('event') == 'coordinator_navigation_map_veto':
            assert event['reason'] == 'outbound_local_obstacle'
            vetoes += 1
        if event.get('event') != 'coordinator_navigation_decision':
            continue
        vertices += audit_outbound(event)
        events.append(event)
    sources = bind_original_maps(events, capture) if capture is not None else None
    return dict(status='PASS', decisions=len(events), vertices=vertices, map_vetoes=vetoes,
                original_source_maps=sources,
                scope='Dispatch-time planned routes and original map/source binding; no claim that Nav2 follows every vertex or that execution remains connected')
