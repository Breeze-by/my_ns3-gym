"""Every geometry witness must bind exact raw contents despite shared stamps."""
import base64
import copy
import gzip
import json

import numpy as np
import pytest
from rclpy.serialization import serialize_message

from multi_robot_exploration import control
from p2c_rally_connection import bind_geometry_maps
from test_p2c_outbound_routes import event_and_cdr


@pytest.mark.parametrize('case',['matching_second','matching_first','each_version','one_unmatched',
    'missing','wrong_shape','wrong_resolution','wrong_origin','unrecorded_clear','invalid_clear','valid_clear'])
def test_exact_source_versions_and_bounded_self_return_vetoes(tmp_path,case):
    event,rows,msg=event_and_cdr()
    proposal=dict(planning_map=event['outbound_map_route']['planning_map'],planning_map_self_return_cells={})
    other=copy.deepcopy(msg);other.data[300]=100
    raw=lambda m:dict(topic='/merge_map',cdr=base64.b64encode(serialize_message(m)).decode())
    samples=[raw(other),rows[1]];proposals=[proposal]
    if case=='matching_first':samples.reverse()
    if case in ('each_version','one_unmatched'):
        grid=np.zeros((40,40),dtype=np.int16);grid.ravel()[300 if case=='each_version' else 200]=100
        proposals.append(dict(planning_map=control.grid_audit_evidence(grid,msg.info.resolution,(0.,0.),
            'ap_delivered_planning_map',10.,10),planning_map_self_return_cells={}))
    if case=='missing':samples=[]
    if case=='wrong_shape':proposal['planning_map']['shape']=[20,80]
    if case=='wrong_resolution':proposal['planning_map']['resolution']=.2
    if case=='wrong_origin':proposal['planning_map']['origin']=[.5,0.]
    if case in ('unrecorded_clear','invalid_clear','valid_clear'):
        from nav_msgs.msg import OccupancyGrid
        from rclpy.serialization import deserialize_message
        msg.info.resolution=.05;msg=deserialize_message(serialize_message(msg),OccupancyGrid)
        grid=np.zeros((40,40),dtype=np.int16)
        proposal['planning_map']=control.grid_audit_evidence(grid,msg.info.resolution,(0.,0.),
            'ap_delivered_planning_map',10.,10)
        if case!='unrecorded_clear':proposal['planning_map_self_return_cells']={'tb1':[7,20]}
        msg.data[300]=-1 if case=='invalid_clear' else 100;samples=[raw(msg)]
    path=tmp_path/'raw.jsonl.gz'
    with gzip.open(path,'wt') as stream:
        for row in samples:stream.write(json.dumps(row)+'\n')
    if case in ('matching_second','matching_first','each_version','valid_clear'):
        assert bind_geometry_maps(proposals,path)==1
    else:
        with pytest.raises(AssertionError):bind_geometry_maps(proposals,path)
