"""Qt communication monitor and a separate fault-service client node."""

from collections import deque
import json
import math
from pathlib import Path
import signal

from python_qt_binding.QtCore import QPointF, QTimer, Qt
from python_qt_binding.QtGui import QColor, QPainter, QPen, QPolygonF
from python_qt_binding.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout,
    QHeaderView, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)
import rclpy
from rclpy.executors import ExternalShutdownException, SingleThreadedExecutor
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rcl_interfaces.srv import SetParametersAtomically
from std_msgs.msg import String

from .gateway_config import FAULT_DEFAULTS
from .gateway_metrics import task_degradation_index, validate_pair_configuration


def transient_qos():
    return QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE, durability=DurabilityPolicy.TRANSIENT_LOCAL)


def shown(value, suffix=""):
    return "—" if value is None else f"{value:.3g}{suffix}"


class MonitorNode(Node):
    """No application publishers or service/action clients."""

    def __init__(self):
        super().__init__("gateway_monitor")
        self.enable_console = bool(self.declare_parameter("enable_fault_console", True).value)
        self.snapshot = None
        self.create_subscription(String, "/gateway/metrics", self.receive, transient_qos())

    def receive(self, message):
        self.snapshot = json.loads(message.data)


class FaultControlNode(Node):
    """Only communication configuration, with an optimistic revision guard."""

    def __init__(self):
        super().__init__("gateway_fault_console")
        self.configuration = None
        self.feedback = "等待gateway配置"
        self.pending = None
        self.client = self.create_client(SetParametersAtomically, "/gateway/configure")
        self.create_subscription(String, "/gateway/fault_configuration", self.receive, transient_qos())

    def receive(self, message):
        state = json.loads(message.data)
        if not self.configuration or state.get("ledger_path") != self.configuration.get("ledger_path") or state["revision"] >= self.configuration["revision"]:
            self.configuration = state

    def apply(self, values):
        if not self.configuration or self.pending or not self.client.service_is_ready():
            self.feedback = "配置服务尚未就绪，或上次请求仍在等待"
            return
        request = SetParametersAtomically.Request()
        changes = {key: value for key, value in values.items() if value != self.configuration["requested"][key]}
        changes["expected_revision"] = int(self.configuration["revision"])
        request.parameters = [Parameter(key, value=value).to_parameter_msg() for key, value in changes.items()]
        self.pending = self.client.call_async(request)
        self.feedback = "等待配置服务确认；当前生效值仍见下方"
        self.pending.add_done_callback(self.applied)

    def applied(self, future):
        try:
            result = future.result().result
            if result.successful:
                acknowledged = json.loads(result.reason)
                self.receive(String(data=result.reason))
                self.feedback = (f"已应用版本 {acknowledged['revision']}，仿真时刻 "
                                 f"{acknowledged['effective_sim_time']:.3f} s")
            else:
                self.feedback = "拒绝：" + result.reason
        except Exception as error:
            self.feedback = "请求失败：" + str(error)
        finally:
            self.pending = None


class Curve(QWidget):
    def __init__(self, title, measures, parent=None):
        super().__init__(parent)
        self.title, self.measures = title, measures
        self.rows, self.reference, self.events = [], [], []
        self.setMinimumHeight(230)
        self.setAccessibleName(title)

    def paintEvent(self, _):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor("#f8fafc"))
        painter.setPen(QColor("#172033"))
        painter.drawText(10, 20, self.title)
        painter.drawText(10, 40, "蓝=上行 橙=下行；实线/虚线对应指标顺序，灰线=配对参考")
        left, top, right, bottom = 52, 58, self.width()-12, self.height()-28
        points = [r["elapsed_sim_time"] for r in self.rows + self.reference]
        x_min, x_max = min(points, default=0), max(points, default=1)
        x_max = max(x_max, x_min + 1)
        values = [fn(r) for r in self.rows+self.reference for _, fn in self.measures]
        thresholds = sorted({r["freshness_ttl_sec"] for r in self.rows if r.get("message_type") != "all" and r.get("freshness_ttl_sec") is not None}) if "AoI" in self.title else []
        values += thresholds
        maximum = max((v for v in values if v is not None and math.isfinite(v)), default=1) or 1
        for tick in range(5):
            y = bottom - (bottom-top)*tick/4
            painter.setPen(QPen(QColor("#dce3ed"), 1))
            painter.drawLine(left, int(y), right, int(y))
            painter.setPen(QColor("#465266"))
            painter.drawText(2, int(y)+4, f"{maximum*tick/4:.2g}")
        for threshold in thresholds:
            y = bottom-(bottom-top)*threshold/maximum
            painter.setPen(QPen(QColor("#c53939"), 1, Qt.DotLine))
            painter.drawLine(left, int(y), right, int(y))
            painter.drawText(left+5, int(y)-3, f"TTL {threshold:g}s")
        for rows, reference in ((self.reference, True), (self.rows, False)):
            for direction, color in (("uplink", "#1864ab"), ("downlink", "#d66a13")):
                for number, (_, getter) in enumerate(self.measures):
                    pen = QPen(QColor("#94a3b8" if reference else color), 1 if reference else 2)
                    if number:
                        pen.setStyle(Qt.DashLine)
                    painter.setPen(pen)
                    segment = []
                    for row in rows:
                        if row["direction"] != direction:
                            continue
                        value = getter(row)
                        if value is None:
                            if len(segment) > 1:
                                painter.drawPolyline(QPolygonF(segment))
                            segment = []
                        else:
                            segment.append(QPointF(left+(right-left)*(row["elapsed_sim_time"]-x_min)/(x_max-x_min),
                                                   bottom-(bottom-top)*value/maximum))
                    if len(segment) > 1:
                        painter.drawPolyline(QPolygonF(segment))
        for event in self.events:
            x = event.get("elapsed_sim_time", -1)
            if x_min <= x <= x_max and event["event"] in ("configuration_applied", "task_phase", "robot_failure"):
                pos = left+(right-left)*(x-x_min)/(x_max-x_min)
                painter.setPen(QPen(QColor("#8490a5"), 1, Qt.DotLine))
                painter.drawLine(int(pos), top, int(pos), bottom)
                painter.drawText(int(pos)+2, top+12, str(event.get("phase", "配置")))
        painter.setPen(QColor("#465266"))
        painter.drawText(left, bottom+20, f"{x_min:.1f} s")
        painter.drawText(right-55, bottom+20, f"{x_max:.1f} s")
        painter.drawText((left+right)//2-30, bottom+20, "仿真时间")


class FaultConsole(QWidget):
    def __init__(self, node):
        super().__init__()
        self.node, self.loaded_revision = node, None
        layout = QVBoxLayout(self)
        explanation = QLabel("在线修改应用层通信故障。按“应用”后以服务确认的仿真时刻生效；在途包按原发送配置结算。\n"
                             "源时间、消息TTL、导航期限和机器人本地安全保护保持原规则。曲线上的“配置”竖线与生效时刻对应。")
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        form = QFormLayout()
        self.editors = {}
        labels = {
            "network_mode": "模式", "uplink_loss_rate": "上行丢包 (%)", "downlink_loss_rate": "下行丢包 (%)",
            "uplink_delay_sec": "上行延迟 (仿真秒)", "downlink_delay_sec": "下行延迟 (仿真秒)",
            "duplicate_rate": "重复 (%)", "reorder_window": "乱序窗口 (0/1=关闭)",
            "reorder_step_sec": "乱序槽延迟 (秒)", "ack_timeout_sec": "ACK等待 (秒)",
            "max_retries": "最大重试次数", "queue_capacity": "每方向队列容量 (0=4096)",
            "drop_message_types": "丢弃类别 (逗号分隔)", "blackout_intervals": "断网区间 [[起,终],...] (任务起点相对秒)",
        }
        for name, default in FAULT_DEFAULTS.items():
            if name == "network_mode":
                widget = QComboBox()
                widget.addItems(["ideal", "fault"])
            elif type(default) is float:
                widget = QDoubleSpinBox()
                widget.setDecimals(3)
                widget.setRange(0.001 if name in ("ack_timeout_sec", "reorder_step_sec") else 0,
                                100 if "rate" in name else 3600)
                widget.setSingleStep(1 if "rate" in name else 0.1)
            elif type(default) is int:
                widget = QSpinBox()
                widget.setRange(0, 1000000)
            else:
                widget = QLineEdit()
            widget.setAccessibleName(labels[name])
            self.editors[name] = widget
            form.addRow(labels[name], widget)
        layout.addLayout(form)
        buttons = QHBoxLayout()
        self.apply_button = QPushButton("应用通信配置")
        self.apply_button.clicked.connect(self.apply)
        load = QPushButton("读入当前生效配置")
        load.clicked.connect(self.load)
        buttons.addWidget(self.apply_button)
        buttons.addWidget(load)
        layout.addLayout(buttons)
        self.feedback = QLabel()
        self.feedback.setWordWrap(True)
        layout.addWidget(self.feedback)
        self.active = QLabel()
        self.active.setWordWrap(True)
        layout.addWidget(self.active)
        layout.addStretch()

    def load(self):
        if not self.node.configuration:
            return
        for name, value in self.node.configuration["requested"].items():
            editor = self.editors[name]
            if isinstance(editor, QComboBox):
                editor.setCurrentText(value)
            elif isinstance(editor, QLineEdit):
                editor.setText(value)
            else:
                editor.setValue(value * 100 if "rate" in name else value)
        self.loaded_revision = self.node.configuration["revision"]

    def apply(self):
        if self.node.configuration and self.loaded_revision != self.node.configuration["revision"]:
            self.node.feedback = "配置版本已变化；请先读入当前生效配置，再修改并应用"
            return
        values = {}
        for name, editor in self.editors.items():
            if isinstance(editor, QComboBox):
                value = editor.currentText()
            elif isinstance(editor, QLineEdit):
                value = editor.text()
            else:
                value = editor.value() / 100 if "rate" in name else editor.value()
            values[name] = value
        self.node.apply(values)
        self.loaded_revision = None

    def refresh(self):
        if self.loaded_revision is None:
            if self.node.pending is None:
                self.load()
        self.feedback.setText(self.node.feedback)
        if self.node.configuration and self.loaded_revision != self.node.configuration["revision"] and self.node.pending is None:
            self.feedback.setText(self.node.feedback + "\n编辑值属于旧版本；请读入当前生效配置后再应用。")
        self.apply_button.setEnabled(bool(self.node.configuration) and self.node.pending is None
                                     and bool(self.node.configuration.get("fault_control_enabled", False)))
        if self.node.configuration:
            c = self.node.configuration
            up, down = c["effective"]["uplink"], c["effective"]["downlink"]
            self.active.setText(f"实际生效：版本{c['revision']} @ {c['effective_sim_time']:.3f}s；"
                                f"上行 loss={up['loss_rate']:.1%} delay={up['delay_sec']:.3g}s；"
                                f"下行 loss={down['loss_rate']:.1%} delay={down['delay_sec']:.3g}s\n"
                                f"队列容量={up['queue_capacity']}，ACK={up['ack_timeout_sec']}s，重试上限={up['max_retries']}")


class ByteShares(QWidget):
    def __init__(self):
        super().__init__()
        self.reports = []
        self.setMinimumHeight(100)
        self.setAccessibleName("按消息类别的发送字节堆叠")

    def paintEvent(self, _):
        painter = QPainter(self)
        palette = ("#1864ab", "#2a9d8f", "#d66a13", "#8064a2", "#b24c63", "#8490a5", "#a48822")
        types = sorted({r["message_type"] for r in self.reports})
        colors = {name: QColor(palette[i % len(palette)]) for i, name in enumerate(types)}
        for index, direction in enumerate(("uplink", "downlink")):
            counts = {name: sum(r["counts"]["attempted_bytes"] for r in self.reports
                                if r["direction"] == direction and r["message_type"] == name) for name in types}
            total, left = sum(counts.values()), 75
            painter.setPen(QColor("#172033"))
            painter.drawText(0, 20+index*28, direction)
            for name, count in counts.items():
                width = (self.width()-75)*count/total if total else 0
                painter.fillRect(int(left), 4+index*28, max(0, int(width)), 20, colors[name])
                left += width
        painter.setPen(QColor("#172033"))
        painter.drawText(0, 78, "发送字节（含重试）类别顺序：" + " · ".join(types))


class GatewayPanel(QWidget):
    def __init__(self, monitor, controller=None):
        super().__init__()
        self.monitor, self.controller = monitor, controller
        self.history = deque(maxlen=20000)
        self.reference, self.last_time = [], None
        self.reference_result = None
        self.reference_context = {}
        self.reference_is_ideal = False
        self.setWindowTitle("Gateway 通信指标与在线控台")
        self.resize(1250, 870)
        layout = QVBoxLayout(self)
        self.summary = QLabel("等待仿真时间指标；统计进程在headless模式下也继续保存数据。")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        tabs = self.tabs = QTabWidget()
        layout.addWidget(tabs)
        charts = QWidget()
        charts_layout = QVBoxLayout(charts)
        controls = QHBoxLayout()
        self.message_type = QComboBox()
        self.message_type.addItem("all")
        controls.addWidget(QLabel("曲线消息类别"))
        controls.addWidget(self.message_type)
        reference = QPushButton("加载同seed ideal/fault参考 windows.jsonl")
        reference.clicked.connect(self.load_reference)
        controls.addWidget(reference)
        charts_layout.addLayout(controls)
        grid = QGridLayout()
        definitions = [
            ("生成吞吐 / 有效接收 goodput (B/s)", [("offered", lambda r: r["offered_bytes_per_sec"]), ("goodput", lambda r: r["goodput_bytes_per_sec"])]),
            ("已结算发送尝试 PDR / loss", [("PDR", lambda r: r["attempt_pdr"]), ("loss", lambda r: r["attempt_loss_rate"])]),
            ("源→交付 p95 / 接收AoI p95 (s)", [("delay", lambda r: r["delays"]["source_to_delivery"]["p95"]), ("AoI", lambda r: r["aoi"]["p95"])]),
            ("在途队列 / retry比例；竖线=任务与配置事件", [("queue", lambda r: sum(v["in_flight"] for v in r["queues"].values()) if r["queues"] else None), ("retry", lambda r: r["retry_rate"])]),
        ]
        self.curves = []
        for index, (title, measures) in enumerate(definitions):
            curve = Curve(title, measures)
            self.curves.append(curve)
            grid.addWidget(curve, index//2, index%2)
        charts_layout.addLayout(grid)
        tabs.addTab(charts, "实时通信曲线")
        details = QWidget()
        details_layout = QVBoxLayout(details)
        details_layout.addWidget(QLabel("PDR分母为已结算attempt；有效接收与transport交付分列。p95少于20样本显示—。freshness按源时间/原TTL。"))
        self.byte_shares = ByteShares()
        details_layout.addWidget(self.byte_shares)
        self.table = QTableWidget(0, 11)
        self.table.setHorizontalHeaderLabels(["方向/类别/端点", "生成B", "发送B", "交付B", "有效B", "有效PDR", "E2E p95/n", "AoI p95", "fresh%", "过期/溢出/重试", "字节占比"])
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        details_layout.addWidget(self.table)
        self.task_details = QLabel()
        self.task_details.setWordWrap(True)
        details_layout.addWidget(self.task_details)
        tabs.addTab(details, "消息类别与任务")
        self.console = FaultConsole(controller) if controller else None
        if self.console:
            tabs.addTab(self.console, "在线通信故障控台")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(200)

    def load_reference(self):
        filename, _ = QFileDialog.getOpenFileName(self, "选择配对参考", "", "Metrics (*.jsonl)")
        if not filename:
            return
        try:
            rows = [json.loads(line) for line in Path(filename).read_text().splitlines()]
            if not rows or any("direction" not in r or "elapsed_sim_time" not in r for r in rows):
                raise ValueError("需要windows.jsonl格式")
            summary_path = Path(filename).with_name("summary.json")
            data = json.loads(summary_path.read_text()) if summary_path.is_file() else {}
            if not isinstance(data, dict):
                raise ValueError("summary.json需要对象格式")
        except (ValueError, OSError) as error:
            self.task_details.setText("参考读取失败：" + str(error))
            return
        current = self.monitor.snapshot
        if current and rows and any(rows[0].get(k) != current["context"].get(k) for k in ("gazebo_seed", "world", "mission_mode", "robot_count")):
            self.summary.setText("参考拒绝：world、seed或mission_mode不同，不能标为配对曲线。")
            return
        self.reference = rows
        self.reference_result = data.get("task_result")
        self.reference_context = data.get("context") or {}
        self.reference_is_ideal = all((r.get("configuration") or {}).get("requested", {}).get("network_mode", (r.get("configuration") or {}).get("legacy_declared_mode")) == "ideal" for r in rows)

    def refresh(self):
        if self.console:
            self.console.refresh()
        snapshot = self.monitor.snapshot
        if not snapshot:
            return
        if snapshot["sim_time"] != self.last_time:
            self.last_time = snapshot["sim_time"]
            self.history.extend(snapshot["window"] + snapshot.get("by_type_window", []))
        context = snapshot["context"]
        queue_text = []
        for report in snapshot["window"]:
            q = report["queues"].get(report["direction"], {})
            capacity = q.get("capacity", 0)
            ratio = 100*q.get("in_flight", 0)/capacity if capacity else None
            queue_text.append(f"{report['direction']}={q.get('in_flight', '—')}/{capacity or '—'} ({shown(ratio, '%')})")
        self.summary.setText(f"{context.get('episode_id')} | seed={context.get('gazebo_seed')} | {context.get('mission_mode')} | "
                             f"任务={snapshot['phase']} | 仿真 t={snapshot['elapsed_sim_time']:.2f}s | {snapshot['output_dir']}\n"
                             "曲线为实时暂定窗口，完整账本结算后保存final CSV/JSON/SVG；监控不发布任务命令。\n"
                             "在途队列/容量（利用率）：" + "; ".join(queue_text))
        types = sorted({r["message_type"] for r in snapshot["streams"]})
        for message_type in types:
            if self.message_type.findText(message_type) < 0:
                self.message_type.addItem(message_type)
        selected = self.message_type.currentText()
        current_rows = [r for r in self.history if r["message_type"] == selected and r["sim_time"] >= snapshot["sim_time"]-120]
        ref_rows = [r for r in self.reference if r.get("message_type") == selected and r.get("sender") == "all"]
        events = [{**event, "elapsed_sim_time": event.get("event_time", event.get("time", 0))-context["episode_start_sim_time"]}
                  for event in snapshot["timeline"]]
        for curve in self.curves:
            curve.rows, curve.reference, curve.events = current_rows, ref_rows, events
            curve.update()
        total = sum(r["counts"].get("attempted_bytes", 0) for r in snapshot["streams"])
        self.byte_shares.reports = snapshot["streams"]
        self.byte_shares.update()
        self.table.setRowCount(len(snapshot["streams"]))
        for row, report in enumerate(snapshot["streams"]):
            c, d = report["counts"], report["delays"]["source_to_delivery"]
            values = [f"{report['direction']}/{report['message_type']} {report['sender']}→{report['recipient']}",
                      *[str(c.get(key, 0)) for key in ("generated_bytes", "attempted_bytes", "delivered_bytes", "accepted_bytes")],
                      shown(report["application_pdr"]), f"{shown(d['p95'])}/{d['n']}", shown(report["aoi"]["p95"]),
                      shown(None if report["aoi"]["fresh_ratio"] is None else 100*report["aoi"]["fresh_ratio"]),
                      "/".join(str(c.get(k, 0)) for k in ("ttl_expired_attempts", "queue_overflow_attempts", "retry_attempts")),
                      f"{100*c.get('attempted_bytes', 0)/total:.1f}%" if total else "—"]
            for column, value in enumerate(values):
                self.table.setItem(row, column, QTableWidgetItem(value))
        robot_text = [f"{name}: {state.get('battery', {}).get('mode', '—')} E={state.get('battery', {}).get('energy', '—')} "
                      f"接收位姿={state.get('pose', '—')} 速度={state.get('velocity', '—')}" for name, state in snapshot["robots"].items()]
        degradation, pair_error = None, "原生结果未落盘或参考不是完整ideal"
        if self.reference_is_ideal and self.reference_result and snapshot.get("task_result"):
            try:
                validate_pair_configuration({"context": context, "task_result": snapshot["task_result"]},
                                            {"context": self.reference_context, "task_result": self.reference_result})
                degradation = task_degradation_index(self.reference_result, snapshot["task_result"])
                pair_error = "同配置核验通过"
            except ValueError as error:
                pair_error = str(error)
        task_text = f"与已加载ideal参考的TDI：{shown(degradation)}；{pair_error}"
        for label, task in (("当前", snapshot.get("task_result")), ("参考", self.reference_result)):
            if task:
                task_text += (f"\n{label}原生任务：{task.get('task_phase')} success={task.get('success')} partial={task.get('partial_completion')} "
                              f"原因={task.get('failure_reason') or task.get('termination_reason')}；完成={shown(task.get('completion_time_sec'))}s "
                              f"RMST300={task.get('completion_time_sec') if task.get('success') else 300}s；"
                              f"发现/RALLY={shown(task.get('time_to_detect_sec'))}/{shown(task.get('time_to_rally_sec'))}s；"
                              f"覆盖={shown(task.get('correct_free_coverage_ratio'))} 路径={shown(task.get('total_path_length_m'))}m "
                              f"最低电量={shown(task.get('battery_minimum_energy'))} 碰撞={task.get('collision_events')}")
        self.task_details.setText("\n".join([task_text] + robot_text + [f"最近事件：{event.get('event')} @ {event.get('event_time', event.get('time'))}" for event in snapshot["timeline"][-8:]]))


def main(args=None):
    rclpy.init(args=args)
    app = QApplication.instance() or QApplication([])
    monitor = MonitorNode()
    controller = FaultControlNode() if monitor.enable_console else None
    executor = SingleThreadedExecutor()
    executor.add_node(monitor)
    if controller:
        executor.add_node(controller)
    panel = GatewayPanel(monitor, controller)
    panel.show()
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    spin = QTimer()

    def poll():
        if not rclpy.ok():
            app.quit()
            return
        try:
            executor.spin_once(timeout_sec=0)
        except (KeyboardInterrupt, ExternalShutdownException):
            app.quit()

    spin.timeout.connect(poll)
    spin.start(10)
    try:
        app.exec_()
    finally:
        executor.shutdown()
        monitor.destroy_node()
        if controller:
            controller.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
