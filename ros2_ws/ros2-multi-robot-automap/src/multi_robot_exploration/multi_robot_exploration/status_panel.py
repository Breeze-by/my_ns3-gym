import json
import math
import signal

from action_msgs.msg import GoalStatus, GoalStatusArray
from nav_msgs.msg import Odometry
from python_qt_binding.QtCore import QTimer
from python_qt_binding.QtWidgets import (
    QApplication,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


ACTIVE_NAV_STATUSES = {
    GoalStatus.STATUS_ACCEPTED,
    GoalStatus.STATUS_EXECUTING,
    GoalStatus.STATUS_CANCELING,
}


def activity_text(task_state, battery_mode, nav_active, is_detector=False):
    if battery_mode == "FAILED" or task_state == "FAILED":
        return "故障"
    if task_state == "COMPLETE":
        return "任务完成"
    if battery_mode == "RETURNING":
        return "返回充电位"
    if battery_mode == "CHARGING":
        return "充电中"
    if task_state == "RALLY":
        return "前往集合点" if nav_active else "集合等待"
    if task_state == "FOUND":
        if is_detector:
            return "目标区勘察" if nav_active else "准备集合"
        return "等待集合"
    if task_state == "FOUND_UNCONFIRMED":
        return "自主探索（确认中）" if nav_active else "确认目标"
    if task_state == "EXPLORE":
        return "自主探索" if nav_active else "等待探索目标"
    return "等待任务数据"


def navigation_text(statuses):
    if any(status in ACTIVE_NAV_STATUSES for status in statuses):
        return "执行中"
    if not statuses:
        return "无数据"
    labels = {
        GoalStatus.STATUS_SUCCEEDED: "已到达",
        GoalStatus.STATUS_ABORTED: "已中止",
        GoalStatus.STATUS_CANCELED: "已取消",
        GoalStatus.STATUS_UNKNOWN: "未知",
    }
    return labels.get(statuses[-1], "空闲")


class StatusNode(Node):
    def __init__(self):
        super().__init__("robot_status_panel")
        self.robot_count = int(self.declare_parameter("robot_count", 2).value)
        self.task_state = "等待中"
        self.detecting_robot = None
        self.robots = {
            f"tb{index}": {
                "pose": None,
                "linear": 0.0,
                "angular": 0.0,
                "battery": {},
                "nav": [],
            }
            for index in range(1, self.robot_count + 1)
        }
        qos = QoSProfile(depth=1)
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        qos.reliability = ReliabilityPolicy.RELIABLE
        self.input_subscriptions = [
            self.create_subscription(
                String, "/task_state", self.task_callback, qos
            ),
            self.create_subscription(
                String,
                "/target_detection",
                self.target_detection_callback,
                qos,
            ),
        ]
        for name in self.robots:
            self.input_subscriptions.extend(
                [
                    self.create_subscription(
                        Odometry,
                        f"/{name}/odom",
                        lambda msg, robot=name: self.odom_callback(msg, robot),
                        10,
                    ),
                    self.create_subscription(
                        String,
                        f"/{name}/battery_state",
                        lambda msg, robot=name: self.battery_callback(
                            msg, robot
                        ),
                        qos,
                    ),
                    self.create_subscription(
                        GoalStatusArray,
                        f"/{name}/navigate_to_pose/_action/status",
                        lambda msg, robot=name: self.nav_callback(msg, robot),
                        10,
                    ),
                ]
            )

    def task_callback(self, message):
        self.task_state = message.data

    def target_detection_callback(self, message):
        try:
            self.detecting_robot = str(json.loads(message.data)["robot"])
        except (KeyError, TypeError, json.JSONDecodeError):
            self.get_logger().warning("Invalid target detection event.")

    def odom_callback(self, message, robot):
        pose = message.pose.pose
        twist = message.twist.twist
        yaw = math.degrees(
            math.atan2(
                2.0
                * (pose.orientation.w * pose.orientation.z),
                1.0 - 2.0 * pose.orientation.z * pose.orientation.z,
            )
        )
        self.robots[robot]["pose"] = (pose.position.x, pose.position.y, yaw)
        self.robots[robot]["linear"] = math.hypot(
            twist.linear.x, twist.linear.y
        )
        self.robots[robot]["angular"] = twist.angular.z

    def battery_callback(self, message, robot):
        try:
            self.robots[robot]["battery"] = json.loads(message.data)
        except (TypeError, json.JSONDecodeError):
            self.get_logger().warning(f"Invalid battery state from {robot}.")

    def nav_callback(self, message, robot):
        self.robots[robot]["nav"] = [
            status.status for status in message.status_list
        ]


class StatusPanel(QWidget):
    HEADERS = (
        "机器人",
        "正在执行",
        "Nav2",
        "电池模式",
        "电量",
        "位置 x, y, yaw°",
        "线速度 m/s",
        "角速度 rad/s",
    )

    def __init__(self, node):
        super().__init__()
        self.node = node
        self.setWindowTitle("多机器人任务状态")
        self.resize(1050, 160 + 38 * node.robot_count)
        layout = QVBoxLayout(self)
        self.global_state = QLabel()
        layout.addWidget(self.global_state)
        self.table = QTableWidget(node.robot_count, len(self.HEADERS))
        self.table.setHorizontalHeaderLabels(self.HEADERS)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(200)
        self.refresh()

    def refresh(self):
        self.global_state.setText(f"全局任务阶段：{self.node.task_state}")
        for row, (name, state) in enumerate(self.node.robots.items()):
            statuses = state["nav"]
            nav_active = any(
                status in ACTIVE_NAV_STATUSES for status in statuses
            )
            battery = state["battery"]
            battery_mode = battery.get("mode", "未启用/无数据")
            capacity = float(battery.get("capacity", 0.0))
            energy = float(battery.get("energy", 0.0))
            energy_text = (
                f"{energy:.1f}/{capacity:.1f} ({100 * energy / capacity:.0f}%)"
                if capacity > 0
                else "—"
            )
            pose = state["pose"]
            pose_text = (
                f"{pose[0]:.2f}, {pose[1]:.2f}, {pose[2]:.0f}"
                if pose is not None
                else "—"
            )
            values = (
                name,
                activity_text(
                    self.node.task_state,
                    battery_mode,
                    nav_active,
                    name == self.node.detecting_robot,
                ),
                navigation_text(statuses),
                battery_mode,
                energy_text,
                pose_text,
                f"{state['linear']:.3f}",
                f"{state['angular']:.3f}",
            )
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))


def main(args=None):
    rclpy.init(args=args)
    app = QApplication.instance() or QApplication([])
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    node = StatusNode()
    panel = StatusPanel(node)
    panel.show()
    spin_timer = QTimer()

    def spin_once():
        if rclpy.ok():
            try:
                rclpy.spin_once(node, timeout_sec=0.0)
            except (KeyboardInterrupt, ExternalShutdownException):
                app.quit()
        else:
            app.quit()

    spin_timer.timeout.connect(spin_once)
    spin_timer.start(20)
    try:
        app.exec_()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
