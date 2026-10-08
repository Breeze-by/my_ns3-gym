import copy

import numpy as np
import pytest

from check_p2c_gate import ap_return_veto_audit
from multi_robot_exploration import control as c


@pytest.mark.parametrize('corruption',[None,'local_source','fused_source','time','cost','qualified','route'])
def test_ap_veto_binds_current_delivered_inputs_and_rebuilds_full_candidates(corruption):
    fused=np.zeros((60,100),dtype='<i2');local=fused.copy();local[:,45:48]=100
    position,home=(2.05,3.05),(8.05,3.05)
    local_map=dict(data=local,resolution=.1,origin=(0.,0.))
    e=dict(event='coordinator_return_map_veto',event_time=11.,robot='tb1',destination=position,
        home=home,radius=.8,inputs={'headquarters/fused_map_snapshot':dict(source_time=10.),
        'tb1/map_snapshot':dict(source_time=10.5)},
        fused_map=c.grid_audit_evidence(fused,.1,(0.,0.),'ap_delivered_planning_map',10.,10.),
        local_map=c.grid_audit_evidence(local,.1,(0.,0.),'ap_delivered_robot_map',10.5,10.5),
        candidates=c.qualified_return_candidates(fused,.1,(0.,0.),position,home,.8,local_map))
    e=copy.deepcopy(e)
    if corruption=='local_source':e['local_map']['source_time']=10.4
    if corruption=='fused_source':e['fused_map']['source']='native_hidden'
    if corruption=='time':e['event_time']=16.
    if corruption=='cost':e['candidates'][1]['path_distance_m']+=1.
    if corruption=='qualified':e['candidates'][1]['qualified']=True
    if corruption=='route':e['candidates'][1]['route']=((2.,1.),)
    if corruption is None:assert ap_return_veto_audit([e])['delivered_return_vetoes']==1
    else:
        with pytest.raises((AssertionError,ValueError)):ap_return_veto_audit([e])
