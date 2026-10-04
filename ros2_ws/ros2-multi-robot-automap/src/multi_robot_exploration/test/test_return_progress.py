from types import SimpleNamespace
from unittest.mock import Mock
import math

import numpy as np
import pytest
from action_msgs.msg import GoalStatus
from builtin_interfaces.msg import Time

from multi_robot_exploration.battery_manager import BatteryManager, RETURNING


def manager(**changes):
    values=dict(
        mode=RETURNING, mission_terminal=False, robot_name='tb1',
        return_goal_handle=Mock(), return_goal_target=(3.,0.), map_position=(1.,0.),
        return_goal_cancel_requested=False, return_goal_best_distance=2.,
        return_goal_last_progress_at=0., return_goal_started_at=0.,
        return_goal_timeout_sec=60., get_logger=Mock(),
    )
    return SimpleNamespace(**{**values,**changes})


def test_no_waypoint_progress_cancels_once_and_retains_handle_until_result():
    node=manager()
    handle=node.return_goal_handle
    BatteryManager.monitor_return_progress(node,20.)
    BatteryManager.monitor_return_progress(node,21.)
    handle.cancel_goal_async.assert_called_once()
    assert node.return_goal_handle is handle and node.return_goal_cancel_requested


def test_progress_resets_idle_watchdog_without_resetting_total_leg_deadline():
    node=manager(map_position=(1.2,0.),return_goal_timeout_sec=30.)
    BatteryManager.monitor_return_progress(node,19.)
    assert node.return_goal_best_distance==pytest.approx(1.8)
    assert node.return_goal_last_progress_at==19. and node.return_goal_started_at==0.
    node.map_position=(1.4,0.)
    BatteryManager.monitor_return_progress(node,30.)
    node.return_goal_handle.cancel_goal_async.assert_called_once()


def test_valid_detour_may_initially_move_away_from_home_or_waypoint():
    node=manager(map_position=(.8,0.))
    BatteryManager.monitor_return_progress(node,15.)
    node.return_goal_handle.cancel_goal_async.assert_not_called()


@pytest.mark.parametrize('changes',[
    {'mode':'ACTIVE'}, {'mode':'CHARGING'}, {'mode':'FAILED'}, {'mission_terminal':True},
    {'return_goal_handle':None}, {'return_goal_target':None}, {'map_position':None},
])
def test_watchdog_does_not_act_without_its_live_local_return(changes):
    node=manager(**changes)
    BatteryManager.monitor_return_progress(node,100.)
    assert not node.return_goal_cancel_requested


def test_cancel_result_releases_old_leg_before_existing_retry_replans():
    node=manager(return_attempts=1,max_return_attempts=3,now=lambda:25.,
                 return_goal_cancel_requested=True,return_stage='charger')
    handle=node.return_goal_handle
    BatteryManager.return_goal_result(node,handle,Mock(result=lambda:SimpleNamespace(status=GoalStatus.STATUS_CANCELED)))
    assert node.return_goal_handle is None and node.return_goal_target is None
    assert node.return_goal_started_at is None and node.return_goal_last_progress_at is None
    assert not node.return_goal_cancel_requested and node.return_goal_due_at==26.


def test_late_result_cannot_clear_newer_local_return_tracking():
    node=manager()
    handle=node.return_goal_handle
    BatteryManager.return_goal_result(node,Mock(),Mock())
    assert node.return_goal_handle is handle and node.return_goal_target==(3.,0.)


def test_return_timeout_scales_with_the_actual_map_planned_leg():
    node=manager(return_attempts=0,max_return_attempts=3,navigation=Mock(),
        return_map=np.zeros((100,100),dtype=int),return_map_resolution=.1,
        return_map_origin=(-5.,-5.),map_position=(3.,0.),charge_x=0.,charge_y=0.,
        charge_radius=.8,nominal_speed=.18,return_escape_failed=False,
        return_goal_response=Mock(),
        get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(to_msg=lambda:Time(sec=10))))
    BatteryManager.send_return_goal(node)
    assert node.return_goal_pending and node.return_goal_target is not None
    assert node.return_goal_timeout_sec>30.
    node.navigation.send_goal_async.assert_called_once()


@pytest.mark.parametrize('yaw',[0.,math.pi/2,-math.pi/2])
def test_local_return_executor_preserves_the_map_planned_leg_heading(monkeypatch,yaw):
    from multi_robot_exploration import battery_manager as battery
    from multi_robot_exploration.control import RallyPose
    monkeypatch.setattr(battery,'plan_charging_leg',lambda *args:(RallyPose(2.,1.,yaw),((3.,0.),(2.,1.))))
    node=manager(return_attempts=0,max_return_attempts=3,navigation=Mock(),
        return_map=np.zeros((100,100),dtype=int),return_map_resolution=.1,
        return_map_origin=(-5.,-5.),map_position=(3.,0.),charge_x=0.,charge_y=0.,
        charge_radius=.8,nominal_speed=.18,return_escape_failed=False,
        return_goal_response=Mock(),
        get_clock=lambda:SimpleNamespace(now=lambda:SimpleNamespace(to_msg=lambda:Time(sec=10))))
    BatteryManager.send_return_goal(node)
    pose=node.navigation.send_goal_async.call_args.args[0].pose.pose
    assert (pose.position.x,pose.position.y)==(2.,1.)
    assert pose.orientation.z==pytest.approx(math.sin(yaw/2))
    assert pose.orientation.w==pytest.approx(math.cos(yaw/2))
