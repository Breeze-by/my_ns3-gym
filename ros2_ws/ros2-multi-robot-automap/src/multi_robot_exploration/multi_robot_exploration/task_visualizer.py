import json

from gazebo_msgs.srv import SpawnEntity
from geometry_msgs.msg import Pose
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String


def disc_sdf(radius, rgba):
    color = " ".join(str(value) for value in rgba)
    return f"""<?xml version="1.0"?>
<sdf version="1.6">
  <model name="task_region">
    <static>true</static>
    <link name="region">
      <visual name="disc">
        <cast_shadows>false</cast_shadows>
        <geometry>
          <cylinder><radius>{radius}</radius><length>0.01</length></cylinder>
        </geometry>
        <material>
          <ambient>{color}</ambient>
          <diffuse>{color}</diffuse>
        </material>
      </visual>
    </link>
  </model>
</sdf>"""


def rally_markers(payload):
    event = json.loads(payload)
    markers = []
    for robot, pose in sorted(event["poses"].items()):
        markers.append((robot, float(pose["x"]), float(pose["y"])))
    return markers


class TaskVisualizer(Node):
    def __init__(self):
        super().__init__("task_visualizer")
        robot_count = int(self.declare_parameter("robot_count", 2).value)
        charge_xs = list(self.declare_parameter("charge_xs", [0.0]).value)
        charge_ys = list(self.declare_parameter("charge_ys", [0.0]).value)
        if robot_count < 1 or len(charge_xs) < robot_count or len(
            charge_ys
        ) < robot_count:
            raise ValueError("charging coordinates do not cover every robot")

        start_radius = float(
            self.declare_parameter("start_radius_m", 1.0).value
        )
        target_radius = float(
            self.declare_parameter("target_radius_m", 3.0).value
        )
        target_x = float(self.declare_parameter("target_x", -4.0).value)
        target_y = float(self.declare_parameter("target_y", 4.0).value)
        show_target = bool(
            self.declare_parameter("show_target_region", False).value
        )
        if start_radius <= 0 or target_radius <= 0:
            raise ValueError("region radii must be positive")

        self.client = self.create_client(SpawnEntity, "/spawn_entity")
        self.queue = []
        self.names = set()
        self.pending = None
        if show_target:
            self.enqueue(
                "task_region_target_detection",
                target_x,
                target_y,
                0.006,
                target_radius,
                (0.85, 0.10, 0.10, 0.10),
            )
        self.enqueue(
            "task_region_start_charge",
            0.0,
            0.0,
            0.012,
            start_radius,
            (0.10, 0.35, 0.95, 0.16),
        )
        for index in range(robot_count):
            self.enqueue(
                f"task_region_charger_tb{index + 1}",
                float(charge_xs[index]),
                float(charge_ys[index]),
                0.020,
                0.25,
                (0.10, 0.85, 0.25, 0.48),
            )

        qos = QoSProfile(depth=1)
        qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        qos.reliability = ReliabilityPolicy.RELIABLE
        self.assignment_subscription = self.create_subscription(
            String,
            "/rally_assignments",
            self.rally_callback,
            qos,
        )
        self.timer = self.create_timer(0.2, self.spawn_next)

    def enqueue(self, name, x, y, z, radius, rgba):
        if name in self.names:
            return
        self.names.add(name)
        request = SpawnEntity.Request()
        request.name = name
        request.xml = disc_sdf(radius, rgba)
        request.initial_pose = Pose()
        request.initial_pose.position.x = x
        request.initial_pose.position.y = y
        request.initial_pose.position.z = z
        request.initial_pose.orientation.w = 1.0
        self.queue.append(request)

    def rally_callback(self, message):
        try:
            markers = rally_markers(message.data)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            self.get_logger().error(f"Invalid rally assignments: {error}")
            return
        for robot, x, y in markers:
            name = f"task_region_rally_{robot}"
            self.enqueue(
                name,
                x,
                y,
                0.028,
                0.18,
                (1.00, 0.55, 0.05, 0.65),
            )

    def spawn_next(self):
        if self.pending is not None:
            if not self.pending.done():
                return
            try:
                response = self.pending.result()
                if not response.success:
                    self.get_logger().warning(response.status_message)
            except Exception as error:
                self.get_logger().error(f"Could not draw task region: {error}")
            self.pending = None
        if not self.queue or not self.client.service_is_ready():
            return
        request = self.queue.pop(0)
        self.pending = self.client.call_async(request)
        self.get_logger().info(f"Drawing Gazebo region {request.name}.")


def main(args=None):
    rclpy.init(args=args)
    node = TaskVisualizer()
    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
