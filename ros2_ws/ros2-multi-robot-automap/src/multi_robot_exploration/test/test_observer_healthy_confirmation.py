import copy,json,math
from unittest.mock import Mock

import pytest

from multi_robot_exploration import control as c
from test_rally_observation_recovery import observer_node
from check_p2c_gate import observer_heading_audit


def quiet_node(age):
    node,client=observer_node();node.target_received_source_time=100.-age
    node.consumed_publisher=Mock()
    node.input_freshness_details=lambda:{'headquarters/target_detection':dict(source_time=100.-age,age_sec=age),
        **{'tb1/'+kind:dict(source_time=100.,age_sec=0.) for kind in ('pose_state','frame_state','battery_state')}}
    node.fresh_target=lambda:0.<=age<=60.
    return node,client


@pytest.mark.parametrize('age',[0.,.5,1.,4.9,5.,5.01,6.,60.,60.01,-.1])
def test_turn_only_after_original_observer_heartbeat_window(age):
    node,client=quiet_node(age)
    expected=5.<age<=60.
    assert c.HeadquartersControl.restore_observer_heading(node) is expected
    assert client.send_goal_async.called is expected
    if 0.<=age<=5.:
        event=json.loads(node.consumed_publisher.publish.call_args.args[0].data)
        assert observer_heading_audit([event],True)['quiet_holds']==1
        assert node.survey_goal_handle is None and not node.survey_goal_pending
    else:assert not node.consumed_publisher.publish.called


def test_quiet_witness_throttles_without_renewing_target_source():
    node,client=quiet_node(.5)
    assert not c.HeadquartersControl.restore_observer_heading(node)
    assert not c.HeadquartersControl.restore_observer_heading(node)
    assert node.consumed_publisher.publish.call_count==1 and not client.send_goal_async.called
    assert node.target_received_source_time==99.5


def test_undetected_target_keeps_null_camera_metadata_without_heading_witnesses():
    result=observer_heading_audit([],True,None,.35,None)
    assert result['quiet_holds']==result['heading_turns']==0 and result['status']=='PASS'


@pytest.mark.parametrize('radius,fov',[(None,None),(None,math.pi/2),(3.,None),
    (float('nan'),math.pi/2),(3.,float('inf')),(3.,0.),(3.,3*math.pi)])
def test_real_heading_witness_requires_finite_delivered_camera_metadata(radius,fov):
    node,_=quiet_node(.5);c.HeadquartersControl.restore_observer_heading(node)
    event=json.loads(node.consumed_publisher.publish.call_args.args[0].data)
    with pytest.raises(AssertionError,match='heading witness lacks camera metadata'):
        observer_heading_audit([event],True,radius,.35,fov)


@pytest.mark.parametrize('bad',[None,'healthy_turn','expired_quiet','future','heading','range','source','pose'])
def test_reader_rejects_forged_confirmation_and_heading_witnesses(bad):
    node,_=quiet_node(.5);c.HeadquartersControl.restore_observer_heading(node)
    e=json.loads(node.consumed_publisher.publish.call_args.args[0].data)
    if bad=='healthy_turn':e.update(event='coordinator_navigation_decision',kind='target_observation_heading',current_position=e['position'],requested_position=e['position'])
    if bad=='expired_quiet':e['inputs']['headquarters/target_detection'].update(source_time=94.,age_sec=6.);e['target_source_time']=94.
    if bad=='future':e['inputs']['headquarters/target_detection'].update(source_time=101.,age_sec=-1.)
    if bad=='heading':e['desired_yaw']+=.2
    if bad=='range':e['target'][1]+=10.
    if bad=='source':e['target_source_time']-=1.
    if bad=='pose':e['inputs']['tb1/frame_state'].update(source_time=97.,age_sec=3.)
    if bad is None:assert observer_heading_audit([e],True)['quiet_holds']==1
    else:
        with pytest.raises(AssertionError):observer_heading_audit([e],True)
