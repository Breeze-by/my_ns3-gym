from action_msgs.msg import GoalStatus

from multi_robot_exploration.status_panel import (
    activity_text,
    navigation_text,
)


def test_activity_prioritizes_terminal_and_battery_modes():
    assert activity_text("FAILED", "ACTIVE", True) == "故障"
    assert activity_text("COMPLETE", "ACTIVE", False) == "任务完成"
    assert activity_text("EXPLORE", "RETURNING", True) == "返回充电位"
    assert activity_text("RALLY", "CHARGING", False) == "充电中"


def test_activity_describes_exploration_and_rally_navigation():
    assert activity_text("EXPLORE", "ACTIVE", True) == "自主探索"
    assert activity_text("EXPLORE", "ACTIVE", False) == "等待探索目标"
    assert activity_text("RALLY", "ACTIVE", True) == "前往集合点"
    assert activity_text("RALLY", "ACTIVE", False) == "集合等待"
    assert activity_text("FOUND", "ACTIVE", True, True) == "目标区勘察"
    assert activity_text("FOUND", "ACTIVE", False, False) == "等待集合"


def test_navigation_status_prefers_any_active_goal():
    assert navigation_text([]) == "无数据"
    assert navigation_text([GoalStatus.STATUS_SUCCEEDED]) == "已到达"
    assert navigation_text(
        [GoalStatus.STATUS_SUCCEEDED, GoalStatus.STATUS_EXECUTING]
    ) == "执行中"
