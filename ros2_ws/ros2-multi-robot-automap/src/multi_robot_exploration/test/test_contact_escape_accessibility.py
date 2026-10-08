import numpy as np
import pytest

from multi_robot_exploration import control as c


@pytest.mark.parametrize('seed', range(8))
def test_cached_reverse_accessibility_matches_original_forward_bfs_on_every_cell(seed):
    rng = np.random.default_rng(20261009+seed)
    raw = rng.choice([-1,0,100],size=(12,16),p=[.15,.7,.15])
    connected = (raw == 0) & (rng.random(raw.shape) < .08)
    for limit in (0,1,3,12):
        mask = c.contact_escape_accessibility(raw,connected,limit)
        for row,column in np.ndindex(raw.shape):
            start,_ = c.navigation_start_route(raw,connected,(row,column),limit)
            assert mask[row,column] == (start is not None)
    assert not c.contact_escape_accessibility(raw,np.zeros(raw.shape,dtype=bool),12).any()


def test_cached_accessibility_is_invalidated_by_a_mutable_map_change():
    raw = np.zeros((60,100),dtype=np.int16)
    raw[:,45] = 100
    cache = {}
    args = (raw,.1,(0.,0.),(2.05,3.05),(8.05,3.05),.8,cache,True)
    assert c.known_return_route(*args) == (None,())
    assert not cache['contact_accessible'][30,20]
    raw[25:37,45] = 0
    distance,route = c.known_return_route(*args)
    assert distance is not None and route


def test_stratified_candidates_find_visible_home_side_poses_missed_by_rings_and_are_bounded():
    raw = np.zeros((200,200),dtype=np.int16)
    raw[100:104,:] = 100
    raw[100:104,92:108] = 0
    target = (5.05,7.)
    sparse = c.rally_pose_candidates(raw,.05,(0.,0.),target)
    expanded = c.rally_pose_candidates(raw,.05,(0.,0.),target,False,True)
    assert expanded[:len(sparse)] == sparse and len(sparse)<len(expanded)<=464
    assert len({c.world_to_grid(p.x,p.y,.05,0.,0.) for p in expanded}) == len(expanded)
    for p in expanded[len(sparse):]:
        cell = c.world_to_grid(p.x,p.y,.05,0.,0.)
        assert 1.<=np.hypot(p.x-target[0],p.y-target[1])<=2.6
        assert c.traversable_grid(raw,.05,c.RALLY_CLEARANCE_M)[cell]
        assert c.has_known_line_of_sight(raw,cell,c.world_to_grid(*target,.05,0.,0.))
    home_side = [p for p in expanded if p.y<4.6]
    sparse_home = [p for p in sparse if p.y<4.6]
    assert not any(np.hypot(a.x-b.x,a.y-b.y)>=.8 for a in sparse_home for b in sparse_home)
    assert any(np.hypot(a.x-b.x,a.y-b.y)>=.8 for a in home_side for b in home_side)
