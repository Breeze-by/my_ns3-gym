"""Reject startup/default Nav2 geometry without changing the frozen stimulus."""
import copy
import hashlib
import json
import sys

import pytest
import rclpy.action
from nav_msgs.msg import OccupancyGrid

import stage_p2c_return_probe as wrapper
from check_p2c_blackout import nav2_readiness_audit
from run_p2d_baseline import PROJECT_ROOT
from run_p3c5_audit import staging_apparatus


POSES={'tb1':[0.,-2.45,0.],'tb2':[0.,2.45,0.]}


def grid():
    message=OccupancyGrid()
    message.header.frame_id='map'
    message.header.stamp.sec=10
    message.info.width=message.info.height=100
    message.info.resolution=.1
    message.info.origin.position.x=message.info.origin.position.y=-5.
    message.info.origin.orientation.w=1.
    message.data=[0]*10000
    return message


@pytest.mark.parametrize('invalid',[None,'missing','frame','future','stale','resolution',
    'width','data','default_bounds','nonfinite','rotation'])
def test_readiness_requires_real_recent_map_covering_all_stage_positions(invalid):
    message=grid()
    if invalid=='missing':message=None
    if invalid=='frame':message.header.frame_id='odom'
    if invalid=='future':message.header.stamp.sec=12
    if invalid=='stale':message.header.stamp.sec=8
    if invalid=='resolution':message.info.resolution=0.
    if invalid=='width':message.info.width=0
    if invalid=='data':message.data=[]
    if invalid=='default_bounds':message.info.origin.position.x=message.info.origin.position.y=0.
    if invalid=='nonfinite':message.info.origin.position.x=float('nan')
    if invalid=='rotation':message.info.origin.orientation.z=.1
    assert wrapper.nav2_map_ready(message,[pose[:2] for pose in POSES.values()],11.) is (invalid is None)


def readiness():
    return [dict(event='nav2_staging_readiness',robot=name,observer_time=10.,ready=True,
        map_header_time=9.5,frame='map',width=100,height=100,resolution=.1,
        origin=[-5.,-5.],orientation=[0.,0.,0.,1.],data_length=10000) for name in POSES]


@pytest.mark.parametrize('invalid',[None,'missing','false','after','old','stale_map','future_map',
    'bounds','frame','rotation','shape','nonfinite'])
def test_independent_reader_rejects_invalid_or_missing_readiness_witness(invalid):
    records=readiness()
    staging=[dict(event='staging_requested',robot=name,observer_time=10.1) for name in POSES]
    row=records[0]
    if invalid=='missing':records=records[1:]
    if invalid=='false':row['ready']=False
    if invalid=='after':row['observer_time']=10.2
    if invalid=='old':row['observer_time']=7.
    if invalid=='stale_map':row['map_header_time']=7.
    if invalid=='future_map':row['map_header_time']=11.
    if invalid=='bounds':row['origin']=[0.,0.]
    if invalid=='frame':row['frame']='odom'
    if invalid=='rotation':row['orientation'][2]=.1
    if invalid=='shape':row['data_length']=100
    if invalid=='nonfinite':row['resolution']=float('nan')
    if invalid is None:assert len(nav2_readiness_audit(records,staging,POSES))==2
    else:
        with pytest.raises(AssertionError):nav2_readiness_audit(records,staging,POSES)


def test_wrapper_adapts_the_frozen_function_local_import_and_restores_it(tmp_path,monkeypatch):
    base=PROJECT_ROOT/'scripts/stage_p3b5_return_probe.py'
    config=tmp_path/'config.json'
    config.write_text(json.dumps(dict(staging_base_content_sha256=hashlib.sha256(base.read_bytes()).hexdigest(),
                                    return_staging=dict(poses=POSES))))
    monkeypatch.setattr(sys,'argv',['stage_p2c_return_probe.py','--config',str(config),
        '--output',str(tmp_path/'staging.jsonl'),'--owner-pid','123'])
    original_client=rclpy.action.ActionClient
    def frozen_import():
        from rclpy.action import ActionClient
        assert ActionClient is not original_client and issubclass(ActionClient,original_client)
        raise RuntimeError('frozen exit')
    monkeypatch.setattr(wrapper.original,'main',frozen_import)
    with pytest.raises(RuntimeError,match='frozen exit'):wrapper.main()
    assert rclpy.action.ActionClient is original_client


def test_legacy_staging_default_is_preserved_and_unrecognized_apparatus_rejected():
    assert staging_apparatus({}).name=='stage_p3b5_return_probe.py'
    assert staging_apparatus({'staging_apparatus_script':'stage_p2c_return_probe.py'}).name=='stage_p2c_return_probe.py'
    with pytest.raises(ValueError):staging_apparatus({'staging_apparatus_script':'../../anything.py'})


@pytest.mark.parametrize('difference',[2.3e-13,1e-6])
def test_reader_accepts_equivalent_float_clock_conversions_but_rejects_actual_future(difference):
    records=readiness()
    for row in records:row['observer_time']=10.+difference
    staging=[dict(event='staging_requested',robot=name,observer_time=10.) for name in POSES]
    if difference<1e-9:assert len(nav2_readiness_audit(records,staging,POSES))==2
    else:
        with pytest.raises(AssertionError):nav2_readiness_audit(records,staging,POSES)


@pytest.mark.parametrize('invalid',[None,'single','duplicate','short','future','stale','mode','nonfinite'])
def test_delivered_active_requires_distinct_fresh_sources_over_original_heartbeat(invalid):
    states=[dict(mode='ACTIVE',stamp_sec=9.),dict(mode='ACTIVE',stamp_sec=9.5)]
    if invalid=='single':states=states[:1]
    if invalid=='duplicate':states[1]['stamp_sec']=9.
    if invalid=='short':states[1]['stamp_sec']=9.4
    if invalid=='future':states[1]['stamp_sec']=11.
    if invalid=='stale':states[0]['stamp_sec']=4.
    if invalid=='mode':states[1]['mode']='RETURNING'
    if invalid=='nonfinite':states[1]['stamp_sec']=float('nan')
    assert wrapper.delivered_active_stable(states,10.) is (invalid is None)
    records=readiness()
    for row in records:row['delivered_battery_records']=copy.deepcopy(states)
    staging=[dict(event='staging_requested',robot=name,observer_time=10.1) for name in POSES]
    if invalid is None:assert len(nav2_readiness_audit(records,staging,POSES,True))==2
    else:
        with pytest.raises(AssertionError):nav2_readiness_audit(records,staging,POSES,True)
