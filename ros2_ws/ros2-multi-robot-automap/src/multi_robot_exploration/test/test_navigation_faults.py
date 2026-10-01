from types import SimpleNamespace
from unittest.mock import Mock
import threading
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from multi_robot_interfaces.msg import GatewayEnvelope
from rclpy.serialization import serialize_message
from multi_robot_exploration.navigation_gateway import NavigationGateway


def test_cancel_before_delayed_goal_never_starts_nav2():
    node=SimpleNamespace(robot_name='tb1', now_sec=lambda:1., latest_downlink={},
                         record_local_event=Mock(),local_canceled=set(), local_goal_handles={},
                         state_lock=threading.RLock(),local_seen=set(),local_battery_mode='ACTIVE',
                         local_deadlines={},publish_result=Mock(),local_navigation=Mock())
    cancel=GatewayEnvelope(message_type='navigation_cancel',sender='headquarters',recipient='tb1',
                           sequence=2,correlation_id=7,ttl_sec=10.)
    NavigationGateway.downlink_callback(node,cancel)
    pose=PoseStamped();pose.header.frame_id='map';pose.pose.orientation.w=1.
    payload=serialize_message(pose)
    goal=GatewayEnvelope(message_type='navigation_goal',sender='headquarters',recipient='tb1',
                         sequence=1,correlation_id=7,ttl_sec=10.,payload=list(payload),payload_length=len(payload))
    NavigationGateway.downlink_callback(node,goal)
    node.local_navigation.send_goal_async.assert_not_called()
    node.publish_result.assert_called_once_with(7,GoalStatus.STATUS_ABORTED)


def test_local_deadline_cancels_once_without_any_central_context():
    handle=Mock()
    node=SimpleNamespace(local_deadlines={7:5.},now_sec=lambda:6.,local_canceled=set(),
                         local_goal_handles={7:handle},record_local_event=Mock(),publish_result=Mock())
    NavigationGateway.expire_local_commands(node)
    NavigationGateway.expire_local_commands(node)
    handle.cancel_goal_async.assert_called_once()
    node.publish_result.assert_called_once_with(7,GoalStatus.STATUS_ABORTED)
    node.record_local_event.assert_called_once_with('navigation_deadline',7,deadline=5.)
