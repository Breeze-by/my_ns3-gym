import copy
import json
import sys
from pathlib import Path

import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src/multi_robot_exploration/test'))
from test_rally_return_repair import node_fixture
from multi_robot_exploration import control
from check_p2c_gate import rally_repair_audit


@pytest.mark.parametrize('corruption',['none','underpriced','stale_frame','unsafe_pose','old_valid','renewed_map'])
def test_reader_binds_repair_geometry_budget_and_original_source_ages(corruption):
    # Synthetic publication from the constructed component; not a Gazebo trial.
    node,_,_=node_fixture()
    assert control.HeadquartersControl.repair_rally_return_target(node,'tb2')
    e=json.loads(node.consumed_publisher.publish.call_args[0][0].data)
    e=copy.deepcopy(e)
    if corruption=='underpriced':e['required_energy']-=1.
    if corruption=='stale_frame':e['inputs']['tb2/frame_state']['source_time']-=10.
    if corruption=='unsafe_pose':e['replacement']=e['old_target']
    if corruption=='old_valid':e['old_target']=e['replacement']
    if corruption=='renewed_map':e['local_map']['source_time']=e['event_time']
    if corruption=='none':
        assert rally_repair_audit([e])['funded_endpoint_repairs']==1
    else:
        with pytest.raises(AssertionError):rally_repair_audit([e])
