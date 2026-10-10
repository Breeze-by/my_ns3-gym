"""Frozen numerical equality and mutable-input isolation for exact ray reuse."""
import base64
import gzip
import hashlib
import json
import math
from pathlib import Path
import zlib

import numpy as np
import pytest

from multi_robot_exploration import control as c


FIXTURE=Path(__file__).parent/'fixtures/p2c_v72_camera_geometry.json.gz'
SAVED=json.load(gzip.open(FIXTURE,'rt'))
assert hashlib.sha256(SAVED['reference_function'].encode()).hexdigest()==SAVED['reference_function_sha256']
ENV=dict(np=np,math=math,INFORMATION_RADIUS_M=2.,INITIAL_SEARCH_VIEW_FOV_RAD=math.pi/2)
exec(SAVED['reference_function'],ENV)
original=ENV['camera_search_interest']


@pytest.mark.parametrize('saved',SAVED['samples'],ids=[r['case']+'_'+str(r['event_time']) for r in SAVED['samples']])
def test_original_delivered_maps_and_views_remain_bit_exact_cold_warm_and_changed(saved):
    s=saved['planning_map'];grid=np.frombuffer(zlib.decompress(base64.b64decode(s['grid'])),dtype='<i2').reshape(s['shape'])
    args=(s['resolution'],s['origin'],saved['views'])
    c.camera_search_ray_geometry.cache_clear()
    expected=original(grid,*args)
    first=c.camera_search_interest(grid,*args)
    second=c.camera_search_interest(grid,*args)
    assert np.array_equal(first,expected) and np.array_equal(second,expected)
    assert c.camera_search_ray_geometry.cache_info().hits>=len(args[-1])
    first[:]=False
    assert np.array_equal(c.camera_search_interest(grid,*args),expected)
    changed=grid.copy();changed[0,0]=-1 if grid[0,0]==0 else 0
    assert np.array_equal(c.camera_search_interest(changed,*args),original(changed,*args))


@pytest.mark.parametrize('seed',range(12))
def test_random_maps_off_map_views_and_array_layouts_match_frozen_math(seed):
    rng=np.random.default_rng(7300+seed)
    grid=rng.choice([-1,0,100],size=(61,82),p=[.12,.8,.08]).astype([np.int8,np.int16,np.int64][seed%3])
    if seed%2:grid=grid[:,::2]
    origin=tuple(rng.uniform(-4,4,2));res=[.05,.1,.2][seed%3]
    views=[dict(position=tuple(rng.uniform(-6,10,2)),yaw=float(rng.uniform(-math.pi,math.pi))) for _ in range(16)]
    assert np.array_equal(c.camera_search_interest(grid,res,origin,views),original(grid,res,origin,views))


def test_map_obstacles_and_unknowns_are_recomputed_with_warm_geometry():
    grid=np.zeros((80,80),dtype=int);v=[dict(position=[3.05,3.05],yaw=0.)]
    c.camera_search_ray_geometry.cache_clear();before=c.camera_search_interest(grid,.1,(0.,0.),v)
    assert not before[30,42]
    for obstacle in (-1,100):
        grid[:,36]=obstacle
        current=c.camera_search_interest(grid,.1,(0.,0.),v)
        assert current[30,42] and not current[:,36].any()
        assert np.array_equal(current,original(grid,.1,(0.,0.),v))
    assert c.camera_search_ray_geometry.cache_info().hits==2


def test_exact_key_fields_invalidate_and_bytes_backed_arrays_cannot_be_poisoned():
    c.camera_search_ray_geometry.cache_clear()
    args=((80,80),.1,(0.,0.),(3.05,3.05),0.)
    arrays=c.camera_search_ray_geometry(*args)
    for array in arrays:
        with pytest.raises(ValueError):array.ravel()[0]=0
        with pytest.raises(ValueError):array.setflags(write=True)
    for index,value in enumerate([(81,80),.10000000001,(1e-12,0.),(3.05+1e-12,3.05),1e-12]):
        changed=list(args);changed[index]=value;c.camera_search_ray_geometry(*changed)
    info=c.camera_search_ray_geometry.cache_info()
    assert info.misses==6 and info.hits==0
    assert c.camera_search_ray_geometry(*args) is arrays


def test_cache_has_a_fixed_512_entry_limit_and_empty_history_keeps_current_free_cells():
    c.camera_search_ray_geometry.cache_clear()
    for i in range(520):c.camera_search_ray_geometry((20,20),.2,(0.,0.),(i/1000.,0.),0.)
    info=c.camera_search_ray_geometry.cache_info()
    assert info.maxsize==info.currsize==512
    grid=np.array([[-1,0,100],[0,100,-1]])
    assert np.array_equal(c.camera_search_interest(grid,.1,(0.,0.),[]),grid==0)
    c.camera_search_ray_geometry.cache_clear()
