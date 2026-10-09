"""Read-only reconstruction of exploration return corridors and funded escapes."""
import base64
import json
import math
from types import SimpleNamespace
import zlib

import numpy as np
from multi_robot_exploration import control


def decode_grid(saved):
    assert saved['encoding'] == 'zlib_base64_int16_le'
    return np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'], validate=True)),
                         dtype='<i2').reshape(saved['shape'])


def audit_preparation(event):
    now = event['event_time']
    saved = event['return_preparation']
    positions, states, modes = (saved[k] for k in ('robot_positions', 'battery_states', 'battery_modes'))
    returning = saved['returning']
    inputs = saved['inputs']
    assert returning in positions and modes[returning] in ('ACTIVE', 'RETURNING')
    assert all(p is not None and len(p) == 2 and all(math.isfinite(v) for v in p)
               for p in positions.values())
    assert saved['clearance_m'] == 1.8
    for key, sample in inputs.items():
        if key == 'headquarters/target_detection':
            continue
        limit = 2. if key.endswith(('/pose_state','/frame_state')) else 5.
        assert 0 < sample['ttl_sec'] <= limit
        assert math.isfinite(sample['source_time']) and 0 <= now-sample['source_time'] <= sample['ttl_sec']
        if key in event['inputs']:
            assert sample['source_time'] == event['inputs'][key]['source_time']
    for name, mode in modes.items():
        if mode != 'FAILED':
            assert {name+'/'+kind for kind in ('pose_state','frame_state','map_snapshot','battery_state')} <= inputs.keys()
    source, planning = saved['source_map'], saved['planning_map']
    assert source['source_time'] == planning['source_time'] == inputs['headquarters/fused_map_snapshot']['source_time']
    assert source['resolution'] == planning['resolution'] and source['origin'] == planning['origin']
    raw, grid = decode_grid(source), decode_grid(planning)
    expected = raw.copy()
    cells = {name:list(cell) for name, cell in saved['self_return_cells'].items()}
    for name, cell in cells.items():
        assert name in positions and raw[tuple(cell)] > 0
        assert tuple(cell) == control.world_to_grid(*positions[name], planning['resolution'], *planning['origin'])
        expected[tuple(cell)] = 0
    assert np.array_equal(expected, grid)
    original, original_cells = control.planning_grid_without_self_returns(raw, planning['resolution'], planning['origin'],
        {n:p for n,p in positions.items() if modes[n] in ('ACTIVE','UNKNOWN')})
    assert np.array_equal(original, grid) and cells == {n:list(cell) for n,cell in original_cells.items()}
    maps = {}
    for name, row in saved['return_maps'].items():
        assert row['source_time'] == inputs[name+'/map_snapshot']['source_time']
        assert 0 <= now-row['source_time'] <= 5.
        maps[name] = dict(data=decode_grid(row), resolution=row['resolution'], origin=row['origin'])
    active = {name for name, mode in modes.items() if mode != 'FAILED'}
    assert active <= maps.keys()
    rebuilt = control.rally_return_reservations(grid, planning['resolution'], planning['origin'],
        positions, states, modes, {returning}, return_maps=maps)
    assert rebuilt is not None and returning in rebuilt
    assert set(rebuilt) == set(saved['protected_routes'])
    for name, route in rebuilt.items():
        assert np.allclose(route, saved['protected_routes'][name], atol=1e-10, rtol=0.)
    if event['event'] == 'coordinator_charge_decision':
        assert event['robot'] == returning
        assert not any(control.routes_conflict((point,), rebuilt[returning], 1.8)
                       for name, point in positions.items() if name != returning)
        assert 0 <= now-saved['evaluated_at_sec'] <= 2.
        return 'charge'
    assert event['kind'] == 'exploration_return_yield'
    name, point = event['robot'], event['requested_position']
    assert name != returning and modes[name] == 'ACTIVE'
    assert event['task_phase'] in ('EXPLORE', 'FOUND_UNCONFIRMED')
    assert control.routes_conflict((positions[name],), rebuilt[returning], 1.8)
    assert not any(control.routes_conflict((point,), route, 1.8) for route in rebuilt.values())
    blocked = [p for other, p in positions.items() if other != name]
    target, route = control.plan_rally_leg(control.RallyPose(*point, event['requested_yaw']),
        grid, planning['resolution'], planning['origin'], positions[name], 5.,
        blocked_positions=blocked, clearance_m=.35, visible_only=True,
        local_map=maps[name] if 'outbound_map_route' in event else None)
    assert target is not None and math.dist((target.x, target.y), point) <= .02
    assert np.allclose(route, saved['route'], atol=1e-10, rtol=0.)
    for reserved in rebuilt.values():
        separation = [min(math.dist(p, q) for q in reserved) for p in route]
        assert all(b+planning['resolution'] >= min(a, 1.8) for a, b in zip(separation, separation[1:]))
    evaluated = saved['required_energy_evaluated_at_sec']
    assert 0 <= now-evaluated <= 2.
    node = SimpleNamespace(now=lambda:evaluated, battery_modes=modes, battery_states=states,
        robot_positions=positions, map_data=grid, resolution=planning['resolution'], origin=planning['origin'],
        map_received_at=planning['source_time'], robot_maps=maps,
        robot_map_received_at={n:r['source_time'] for n,r in saved['return_maps'].items()},
        robot_odom_received_at={n:inputs[n+'/pose_state']['source_time'] for n in active},
        robot_tf_received_at={n:inputs[n+'/frame_state']['source_time'] for n in active})
    distance = sum(math.dist(a,b) for a,b in zip(route,route[1:]))
    required = control.HeadquartersControl.exploration_required_energy(node, name, distance, point, evaluated)
    assert required is not None and math.isclose(required, saved['required_energy'], abs_tol=1e-8)
    assert float(states[name]['energy']) > required
    return 'yield'


def return_preparation_audit(path, required=False):
    if not required:
        return None
    counts = dict(charge=0, yield_moves=0)
    for line in path.open():
        event = json.loads(line)
        if event.get('event') != 'coordinator_charge_decision' and not (
            event.get('event') == 'coordinator_navigation_decision' and event.get('kind') == 'exploration_return_yield'):
            continue
        if event.get('event') == 'coordinator_charge_decision' and event['task_phase'] not in ('EXPLORE', 'FOUND_UNCONFIRMED'):
            continue  # Existing FOUND/RALLY coordination has its own guards.
        kind = audit_preparation(event)
        counts['charge' if kind == 'charge' else 'yield_moves'] += 1
    return dict(status='PASS', **counts, route_clearance_m=1.8, private_audit_only=True)
