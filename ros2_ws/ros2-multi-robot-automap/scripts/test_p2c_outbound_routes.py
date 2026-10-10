"""The outbound reader rejects source-map tampering independently of dispatch."""
import base64
import copy
import gzip
import json

import numpy as np
import pytest
from nav_msgs.msg import OccupancyGrid
from rclpy.serialization import deserialize_message, serialize_message

from multi_robot_exploration import control
from p2c_outbound_routes import audit_outbound, bind_original_maps


def event_and_cdr():
    msg=OccupancyGrid();msg.header.stamp.sec=10;msg.header.frame_id='map'
    msg.info.width=msg.info.height=40;msg.info.resolution=.1;msg.info.origin.orientation.w=1.
    msg.data=[0]*1600
    msg=deserialize_message(serialize_message(msg), OccupancyGrid)
    grid=np.zeros((40,40),dtype=np.int16)
    save=lambda tag:control.grid_audit_evidence(grid,msg.info.resolution,(0.,0.),tag,10.,10)
    event=dict(robot='tb1',event_time=10.,current_position=[1.05,1.05],requested_position=[2.05,1.05],
        inputs={'tb1/map_snapshot':dict(source_time=10.),'headquarters/fused_map_snapshot':dict(source_time=10.)},
        outbound_map_route=dict(clearance_m=.35,route=[[1.05,1.05],[2.05,1.05]],
            local_map=save('ap_delivered_robot_map'),planning_map=save('ap_delivered_planning_map')))
    rows=[dict(topic=topic,type='nav_msgs/msg/OccupancyGrid',cdr=base64.b64encode(serialize_message(msg)).decode())
          for topic in ('/tb1/map','/merge_map')]
    return event,rows,msg


@pytest.mark.parametrize('change', ['none','missing','local_cell','resolution','origin','unrecorded_fused'])
def test_raw_source_binding_detects_missing_or_changed_geometry(tmp_path,change):
    event,rows,msg=event_and_cdr()
    if change=='missing':rows=rows[:1]
    elif change=='local_cell':
        msg.data[300]=100;rows[0]['cdr']=base64.b64encode(serialize_message(msg)).decode()
    elif change=='resolution':event['outbound_map_route']['local_map']['resolution']=.2
    elif change=='origin':event['outbound_map_route']['local_map']['origin']=[.5,0.]
    elif change=='unrecorded_fused':
        msg.data[300]=100;rows[1]['cdr']=base64.b64encode(serialize_message(msg)).decode()
    capture=tmp_path/'originals.jsonl.gz'
    with gzip.open(capture,'wt') as f:
        for row in rows:f.write(json.dumps(row)+'\n')
    if change=='none':assert bind_original_maps([event],capture)==2
    else:
        with pytest.raises(AssertionError):bind_original_maps([event],capture)


@pytest.mark.parametrize('change', ['clearance','source','future','endpoint','interior'])
def test_dispatch_witness_cannot_relabel_an_unsafe_or_expired_route(change):
    event,_,msg=event_and_cdr();assert audit_outbound(event)==2
    if change=='clearance':event['outbound_map_route']['clearance_m']=.1
    elif change=='source':event['outbound_map_route']['local_map']['source_time']=9.
    elif change=='future':event['event_time']=9.9
    elif change=='endpoint':event['requested_position']=[3.05,1.05]
    elif change=='interior':
        grid=np.zeros((40,40),dtype=int);grid[10,15]=100
        event['outbound_map_route']['local_map']=control.grid_audit_evidence(
            grid,msg.info.resolution,(0.,0.),'ap_delivered_robot_map',10.,10)
    with pytest.raises(AssertionError):audit_outbound(event)


@pytest.mark.parametrize('case', ['matching_second', 'matching_first', 'each_version',
    'one_unmatched', 'wrong_geometry_only', 'invalid_first_clear', 'invalid_clear_only'])
def test_duplicate_headers_bind_every_witness_to_qualifying_raw_contents(tmp_path, case):
    event, rows, msg = event_and_cdr()
    changed = copy.deepcopy(msg);changed.data[300] = 100
    row = lambda m:dict(topic='/merge_map', type='nav_msgs/msg/OccupancyGrid',
                        cdr=base64.b64encode(serialize_message(m)).decode())
    samples = [rows[0], row(changed), rows[1]]
    events = [event]
    if case == 'matching_first':samples = [rows[0], rows[1], row(changed)]
    if case in ('each_version', 'one_unmatched'):
        other = copy.deepcopy(event)
        grid = np.zeros((40,40), dtype=np.int16);grid.ravel()[300 if case == 'each_version' else 200] = 100
        other['outbound_map_route']['planning_map'] = control.grid_audit_evidence(
            grid, msg.info.resolution, (0.,0.), 'ap_delivered_planning_map', 10., 10)
        events.append(other)
    if case == 'wrong_geometry_only':
        changed.info.resolution = .2;samples = [rows[0], row(changed)]
    if case in ('invalid_first_clear', 'invalid_clear_only'):
        msg.info.resolution = changed.info.resolution = .05
        msg = deserialize_message(serialize_message(msg), OccupancyGrid)
        for label, tag in [('local_map','ap_delivered_robot_map'),('planning_map','ap_delivered_planning_map')]:
            event['outbound_map_route'][label] = control.grid_audit_evidence(
                np.zeros((40,40), dtype=np.int16), msg.info.resolution, (0.,0.), tag, 10., 10)
        event['planning_map_self_return_cells'] = {'tb1':[7,20]}
        invalid = copy.deepcopy(changed);invalid.data[300] = -1
        local = dict(topic='/tb1/map', type='nav_msgs/msg/OccupancyGrid',
                     cdr=base64.b64encode(serialize_message(msg)).decode())
        samples = [local, row(invalid)] + ([] if case == 'invalid_clear_only' else [row(changed)])
    capture = tmp_path/'same_headers.jsonl.gz'
    with gzip.open(capture, 'wt') as stream:
        for sample in samples:stream.write(json.dumps(sample)+'\n')
    if case in ('one_unmatched', 'wrong_geometry_only', 'invalid_clear_only'):
        with pytest.raises(AssertionError):bind_original_maps(events, capture)
    else:
        assert bind_original_maps(events, capture) == 2
