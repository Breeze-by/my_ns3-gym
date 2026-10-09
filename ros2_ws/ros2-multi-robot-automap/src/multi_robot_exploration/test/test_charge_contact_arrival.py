"""Contact-boundary crossing must not cancel a budgeted return waypoint."""
from types import MethodType, SimpleNamespace
from unittest.mock import Mock
import pytest
from action_msgs.msg import GoalStatus
from multi_robot_exploration.battery_manager import BatteryManager, RETURNING, CHARGING
from test_return_budget import manager

@pytest.mark.parametrize('pending,accepted', [(True,False),(False,True),(True,True)])
def test_outer_contact_waits_for_pending_or_accepted_leg(pending,accepted):
    node,_,states=manager(position=(.3,0.),home=(0.,0.))
    node.mode=RETURNING;node.mode_started_at=10.
    node.return_goal_pending=pending;handle=Mock()
    node.return_goal_handle=handle if accepted else None
    BatteryManager.begin_charging(node)
    assert node.mode==RETURNING and node.mode_started_at==10.
    assert states==[] and node.return_cancels==0
    handle.cancel_goal_async.assert_not_called()

def test_completed_contact_leg_can_charge_without_changing_stable_duration():
    node,_,states=manager(position=(.3,0.),home=(0.,0.))
    node.mode=RETURNING;node.mode_started_at=10.;node.return_stage='charger'
    node.return_goal_handle=handle=Mock();node.return_attempts=1;node.max_return_attempts=3
    node.begin_charging=MethodType(BatteryManager.begin_charging,node)
    BatteryManager.return_goal_result(node,handle,Mock(result=lambda:SimpleNamespace(status=GoalStatus.STATUS_SUCCEEDED)))
    assert node.mode==CHARGING and node.return_goal_handle is None
    assert node.charge_stable_started_at is None and node.return_cancels==0
    assert states==[CHARGING]

def test_contact_wait_preserves_original_floor_and_cancel_owner_until_result():
    node,_,_=manager(position=(.3,0.),home=(0.,0.),energy=8.)
    node.mode=RETURNING;node.return_goal_handle=handle=Mock()
    BatteryManager.begin_charging(node)
    assert node.mode==RETURNING
    assert not node.guard_return_budget(11.,dict(required_energy=10.))
    assert node.mode=='FAILED' and node.failure_reason=='battery_return_reserve_depleted'
    assert node.return_goal_handle is handle
    handle.cancel_goal_async.assert_called_once()
