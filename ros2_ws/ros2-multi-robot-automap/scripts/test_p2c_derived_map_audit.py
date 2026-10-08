import base64
import copy
import hashlib
import json
import zlib

import numpy as np
import pytest

from check_p2c_gate import return_audit
from multi_robot_exploration import control as c
from test_constrained_return_search import delivered_fixture
from test_return_budget import manager


@pytest.mark.parametrize('corruption',[None,'cleared_obstacle','freshened_stamp','wrong_version','hidden_source'])
def test_native_derived_route_audit_reconstructs_both_original_sources(corruption,tmp_path):
    e,fused,local=delivered_fixture();state=e['battery_states']['tb1']
    pose=c.rally_pose_candidates(fused['data'],fused['resolution'],fused['origin'],e['target'])[0]
    node,events,_=manager(position=(pose.x,pose.y),home=(state['charge_x'],state['charge_y']))
    node.now=lambda:10.;node.last_odom_time=9.9;node.map_tf_source_time=9.8
    node.return_map_source_time=9.
    node.return_map_candidates={'local':(local['data'],local['resolution'],local['origin'],8.,4,'local'),
        'delivered_fused':(fused['data'],fused['resolution'],fused['origin'],9.,5,'delivered_fused')}
    node.begin_return('synthetic_derived_route_reader_fixture')
    assert events[-1]['budget']['map_source']=='constrained_fused'
    node.total_motion_distance=1.;node.total_energy_elapsed=5.;node.energy-=1.1
    node.now=lambda:15.;node.finish_return_audit('charger_stopped')
    events=copy.deepcopy(events)
    start=events[0];saved=start['map_evidence'];budget=start['budget']
    derived=next(r['map_evidence'] for r in saved['route_candidates'] if r['map_evidence']['source']=='constrained_fused')
    if corruption=='cleared_obstacle':
        grid=np.frombuffer(zlib.decompress(base64.b64decode(saved['grid'])),dtype='<i2').reshape(saved['shape']).copy()
        row,column=np.argwhere((grid==100)&(fused['data']!=100))[0];grid[row,column]=0
        encoded=base64.b64encode(zlib.compress(grid.tobytes())).decode()
        saved['grid']=derived['grid']=encoded
        budget['map_content_blake2b']=hashlib.blake2b(grid.tobytes(),digest_size=16).hexdigest()
    if corruption=='freshened_stamp':
        saved['source_time']=derived['source_time']=budget['map_source_time']=9.
        budget['map_age_sec']=1.
    if corruption=='wrong_version':saved['version']=derived['version']=budget['map_version']=7
    if corruption=='hidden_source':saved['source']=derived['source']=budget['map_source']='native_hidden_truth'
    path=tmp_path/'native.jsonl'
    path.write_text(''.join(json.dumps(dict(topic='/tb1/battery_return_audit',data=e))+'\n' for e in events))
    if corruption is None:assert return_audit(path,True,True)['charger_returns']==1
    else:
        with pytest.raises((AssertionError,KeyError,ValueError)):return_audit(path,True,True)
