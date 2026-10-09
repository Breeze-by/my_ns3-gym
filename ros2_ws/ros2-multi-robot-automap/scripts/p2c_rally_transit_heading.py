"""Rebuild the private geometric/lease support for an intermediate transit yaw."""
import base64
import json
import math
import zlib

import numpy as np
from multi_robot_exploration import control


def audit_transit_heading(event):
    saved = event['rally_transit_observer']
    now = event['event_time']; observer = saved['observer']
    assert event['kind'] == 'rally' and event['task_phase'] == 'RALLY' and observer != event['robot']
    assert saved['heartbeat_sec'] == 5.
    confirmation = saved['confirmation']
    assert confirmation['robot'] == observer and confirmation['target'] == saved['target']
    assert saved['observer_source_time'] == confirmation['source_time']
    assert saved['observer_source_time'] <= event['inputs']['headquarters/target_detection']['source_time']
    assert saved['view_distance_m'] == confirmation['view_distance_m']
    assert saved['view_fov_rad'] == confirmation['view_fov_rad']
    assert 0 <= now-saved['observer_source_time'] <= 5.
    assert saved['evaluated_at_sec'] <= now
    assert 0 < saved['position_tolerance_m'] <= .35
    assert 0 <= saved['linear_tolerance_mps'] <= .05
    assert 0 <= saved['angular_tolerance_radps'] <= .1
    position, yaw, velocity = saved['position'], saved['yaw'], saved['velocity']
    assert len(position) == len(velocity) == 2
    assert all(math.isfinite(x) for x in (*position, yaw, *velocity))
    assert 0 <= velocity[0] <= saved['linear_tolerance_mps']
    assert 0 <= velocity[1] <= saved['angular_tolerance_radps']
    assert math.dist(position, saved['final_pose'][:2]) <= saved['position_tolerance_m']
    for kind in ('pose_state','frame_state'):
        source = event['inputs'][observer+'/'+kind]['source_time']
        assert math.isfinite(source) and 0 <= now-source <= 2.
    grid = saved['map']
    assert grid['source'] == 'ap_delivered_planning_map'
    assert grid['source_time'] == grid['version'] == event['inputs']['headquarters/fused_map_snapshot']['source_time']
    assert 0 <= now-grid['source_time'] <= 5.
    assert grid['encoding'] == 'zlib_base64_int16_le'
    array = np.frombuffer(zlib.decompress(base64.b64decode(grid['grid'],validate=True)),dtype='<i2').reshape(grid['shape'])
    assert control.rally_target_view(array,grid['resolution'],grid['origin'],position,
        saved['target'],saved['view_distance_m']-saved['position_tolerance_m'])
    target_yaw = math.atan2(saved['target'][1]-position[1],saved['target'][0]-position[0])
    assert 0 < saved['view_fov_rad'] <= 2*math.pi
    assert abs(math.atan2(math.sin(target_yaw-yaw),math.cos(target_yaw-yaw))) <= saved['view_fov_rad']/4
    route = saved['route']
    assert len(route) >= 2 and all(len(p)==2 and all(math.isfinite(x) for x in p) for p in route)
    assert math.dist(route[-1],event['requested_position']) <= 1e-8
    assert control.world_to_grid(*event['requested_position'],grid['resolution'],*grid['origin']) != control.world_to_grid(
        *saved['participant_final_pose'][:2],grid['resolution'],*grid['origin'])
    assert abs(math.atan2(math.sin(event['requested_yaw']-saved['incoming_yaw']),
                         math.cos(event['requested_yaw']-saved['incoming_yaw']))) <= 1e-8
    incoming = control.route_arrival_yaw(route,saved['incoming_yaw'])
    assert abs(math.atan2(math.sin(incoming-saved['incoming_yaw']),math.cos(incoming-saved['incoming_yaw']))) <= 1e-8


def transit_heading_audit(path, required=False):
    if not required:
        return None
    count = 0
    confirmations = {}
    for line in path.open():
        event = json.loads(line)
        if event.get('event') in ('consumed','target_reconfirmed') and event.get('message_type') == 'target_detection':
            confirmations[event['robot']] = event['source_time']
        if event.get('event') == 'coordinator_navigation_decision' and 'rally_transit_observer' in event:
            saved = event['rally_transit_observer']
            assert confirmations.get(saved['observer']) == saved['observer_source_time'], 'missing original delivered peer confirmation'
            audit_transit_heading(event); count += 1
    return dict(status='PASS', supported_intermediate_legs=count,
                scope='Private delivered geometry/pose/velocity/heartbeat provenance; ordinary route, energy and native final hold retain their separate gates')
