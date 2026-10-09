"""Directional search history is a preference, never a target-absence proof."""
import copy
import math
from types import SimpleNamespace

import numpy as np
import pytest

from multi_robot_exploration import control as c
from test_initial_known_search import visual_event


def view(position=(3.05, 3.05), yaw=0.):
    return dict(source='ap_delivered_pose_and_heading_history', robot='tb1',
        position=list(position), yaw=yaw, observed_at_sec=9.,
        pose_source_time=8.5, frame_source_time=8.7)


@pytest.mark.parametrize('yaw', [0., math.pi/2, math.pi, -math.pi/2])
def test_camera_cone_keeps_the_unseen_back_side_of_a_visited_position(yaw):
    grid = np.zeros((80, 80), dtype=int)
    history = view(yaw=yaw)
    actual = c.camera_search_interest(grid, .1, (0., 0.), [history])
    x, y = history['position']
    front = c.world_to_grid(x + math.cos(yaw), y + math.sin(yaw), .1, 0., 0.)
    back = c.world_to_grid(x - math.cos(yaw), y - math.sin(yaw), .1, 0., 0.)
    assert not actual[front] and actual[back]
    assert not c.known_search_interest(grid, .1, (0., 0.), [(x, y)])[back]
    assert np.array_equal(grid, np.zeros_like(grid))


@pytest.mark.parametrize('obstacle', [100, -1])
def test_current_occlusion_prevents_history_from_discounting_the_other_room(obstacle):
    grid = np.zeros((80, 80), dtype=int)
    grid[:, 36] = obstacle
    interest = c.camera_search_interest(grid, .1, (0., 0.), [view()])
    assert not interest[30, 34] and interest[30, 42]
    assert not interest[:, 36].any()
    grid[30, 36] = 0
    assert not c.camera_search_interest(grid, .1, (0., 0.), [view()])[30, 42]


def test_view_history_respects_range_and_angle_and_is_order_independent():
    grid = np.zeros((80, 80), dtype=int)
    east = view()
    north = view(yaw=math.pi/2)
    a = c.camera_search_interest(grid, .1, (0., 0.), [east, north])
    b = c.camera_search_interest(grid, .1, (0., 0.), [north, east, east])
    assert np.array_equal(a, b)
    assert not a[30, 40] and not a[40, 30]
    assert a[30, 51] and a[30, 20] and a[20, 30]
    assert c.camera_search_interest(grid, .1, (0., 0.), [view((-3., -3.))]).all()


@pytest.mark.parametrize('invalid', ['valid', 'stale_odom', 'stale_frame', 'future', 'nan', 'phase'])
def test_record_only_original_fresh_delivered_heading_and_preserve_position_history(invalid):
    node = SimpleNamespace(initial_search_visits={}, task_state='EXPLORE', now=lambda:10.,
        robot_positions={'tb1':(3.05, 3.05)}, robot_yaws={'tb1':0.},
        robot_odom_received_at={'tb1':9.}, robot_tf_received_at={'tb1':9.5})
    if invalid=='stale_odom':node.robot_odom_received_at['tb1']=7.9
    if invalid=='stale_frame':node.robot_tf_received_at['tb1']=7.9
    if invalid=='future':node.robot_tf_received_at['tb1']=10.1
    if invalid=='nan':node.robot_yaws['tb1']=float('nan')
    if invalid=='phase':node.task_state='RALLY'
    c.HeadquartersControl.record_initial_search_visit(node, 'tb1')
    assert bool(getattr(node, 'initial_search_views', {})) == (invalid=='valid')
    if invalid=='valid':
        saved = next(iter(node.initial_search_views.values()))
        assert saved['yaw']==0. and saved['pose_source_time']==9. and saved['frame_source_time']==9.5
        node.robot_yaws['tb1']=.1
        c.HeadquartersControl.record_initial_search_visit(node, 'tb1')
        assert len(node.initial_search_views)==1
        node.robot_yaws['tb1']=math.pi/2
        c.HeadquartersControl.record_initial_search_visit(node, 'tb1')
        assert len(node.initial_search_views)==2 and len(node.initial_search_visits)==1


def test_camera_search_returns_safe_reachable_candidates_with_reconstructible_yaw():
    grid = np.zeros((80, 80), dtype=int)
    grid[:, 60] = 100
    history = [view()]
    rows = c.known_space_search_candidates(grid, .1, (0., 0.), 'tb1', (3.05, 3.05),
        [(3.05, 3.05)], face_interest=True, camera_views=history)
    assert rows
    interest = c.camera_search_interest(grid, .1, (0., 0.), history)
    safe = c.traversable_grid(grid, .1, c.ROBOT_CLEARANCE_M)
    for _, _, _, a in rows:
        assert safe[a.viewpoint.row, a.viewpoint.column]
        gain, yaw = c.known_search_view(grid, (a.viewpoint.row, a.viewpoint.column), 20, interest)
        assert gain==a.viewpoint.information_gain and yaw==a.navigation_yaw


def camera_event():
    import base64, zlib
    e = copy.deepcopy(visual_event())
    f = e['travel_preference']
    s = e['planning_map']
    grid = np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])), dtype='<i2').reshape(s['shape'])
    views = [view((2.1, 3.1))]
    interest = c.camera_search_interest(grid, s['resolution'], s['origin'], views)
    cell = c.world_to_grid(*f['target'], s['resolution'], *s['origin'])
    gain, yaw = c.known_search_view(grid, cell, c.INFORMATION_RADIUS_M/s['resolution'], interest)
    f.update(initial_search_views=views,
        search_view_model=dict(radius_m=2., fov_rad=math.pi/2, heading_bins=16),
        information_gain=gain, view_yaw=yaw)
    f['base_utility']=gain/(f['own_nominal_distance_m']+1.)
    f['adjusted_utility']=f['base_utility']*f['factor']
    f['scheduling_score']=f['adjusted_utility']
    e['requested_yaw']=yaw
    return e


@pytest.mark.parametrize('bad', [None, 'missing', 'empty', 'source', 'duplicate', 'yaw', 'future',
    'stale_pose', 'stale_frame', 'radius', 'fov', 'bins', 'gain', 'heading'])
def test_independent_reader_rebuilds_delivered_history_current_sight_and_selected_sector(bad):
    from check_p2c_gate import exploration_travel_audit
    e=camera_event();f=e['travel_preference'];h=f['initial_search_views'][0]
    if bad=='missing':f.pop('initial_search_views')
    if bad=='empty':f['initial_search_views']=[]
    if bad=='source':h['source']='native_hidden_camera'
    if bad=='duplicate':f['initial_search_views'].append(copy.deepcopy(h))
    if bad=='yaw':h['yaw']=float('nan')
    if bad=='future':h['observed_at_sec']=11.
    if bad=='stale_pose':h['pose_source_time']=6.
    if bad=='stale_frame':h['frame_source_time']=6.
    if bad=='radius':f['search_view_model']['radius_m']=3.
    if bad=='fov':f['search_view_model']['fov_rad']=math.pi
    if bad=='bins':f['search_view_model']['heading_bins']=8
    if bad=='gain':f['information_gain']+=1
    if bad=='heading':f['view_yaw']+=.1
    if bad is None:
        assert exploration_travel_audit([e],True,True,True,True,False,True)['camera_aware_visual_witnesses']==1
    else:
        with pytest.raises((AssertionError,KeyError)):
            exploration_travel_audit([e],True,True,True,True,False,True)
