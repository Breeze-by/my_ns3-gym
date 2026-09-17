import json
import math

from gazebo_msgs.msg import ModelStates
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from std_msgs.msg import String

from .task_evaluator import load_truth_grid


def _normalize_angle(angle):
    return math.atan2(math.sin(angle), math.cos(angle))


def line_of_sight_clear(truth, start, end):
    """Return whether the segment stays inside known truth-free cells."""
    distance = math.dist(start, end)
    steps = max(1, math.ceil(distance / (truth.resolution / 2)))
    height, width = truth.occupied.shape
    for index in range(1, steps):
        fraction = index / steps
        x = start[0] + fraction * (end[0] - start[0])
        y = start[1] + fraction * (end[1] - start[1])
        column = math.floor((x - truth.origin_x) / truth.resolution)
        row = math.floor((y - truth.origin_y) / truth.resolution)
        if not 0 <= row < height or not 0 <= column < width:
            return False
        if truth.occupied[row, column]:
            return False
    return True


def target_visible(robot_pose, target, truth, max_distance, field_of_view):
    x, y, yaw = robot_pose
    distance = math.dist((x, y), target)
    if distance > max_distance:
        return False
    bearing = math.atan2(target[1] - y, target[0] - x)
    if abs(_normalize_angle(bearing - yaw)) > field_of_view / 2:
        return False
    return line_of_sight_clear(truth, (x, y), target)


def update_confirmation(streaks, visible_robots, required_frames):
    for robot in streaks:
        streaks[robot] = streaks[robot] + 1 if robot in visible_robots else 0
    return next(
        (
            robot
            for robot in sorted(visible_robots)
            if streaks[robot] >= required_frames
        ),
        None,
    )


def _yaw(pose):
    orientation = pose.orientation
    return math.atan2(
        2 * (orientation.w * orientation.z + orientation.x * orientation.y),
        1 - 2 * (orientation.y**2 + orientation.z**2),
    )


class TargetDetector(Node):
    def __init__(self):
        super().__init__("target_detector")
        robot_count = self.declare_parameter("robot_count", 2).value
        world_file = self.declare_parameter("world_file", "").value
        self.target_model = self.declare_parameter(
            "target_model", "search_target"
        ).value
        self.max_distance = self.declare_parameter(
            "max_distance_m", 3.0
        ).value
        fov_degrees = self.declare_parameter("field_of_view_deg", 90.0).value
        self.field_of_view_degrees = fov_degrees
        self.field_of_view = math.radians(fov_degrees)
        self.required_frames = self.declare_parameter(
            "confirmation_frames", 3
        ).value
        if robot_count < 1 or self.required_frames < 1:
            raise ValueError("robot_count and confirmation_frames must be positive")
        if not world_file or self.max_distance <= 0 or not 0 < fov_degrees <= 360:
            raise ValueError("world_file, distance, and field of view are invalid")

        self.truth = load_truth_grid(world_file)
        self.robot_names = [
            f"tb{index}" for index in range(1, robot_count + 1)
        ]
        self.streaks = {name: 0 for name in self.robot_names}
        self.observation_state = "EXPLORE"
        self.confirmed = False

        state_qos = QoSProfile(depth=1)
        state_qos.durability = DurabilityPolicy.TRANSIENT_LOCAL
        state_qos.reliability = ReliabilityPolicy.RELIABLE
        self.observation_publisher = self.create_publisher(
            String, "/target_observation", state_qos
        )
        self.detection_publisher = self.create_publisher(
            String, "/target_detection", state_qos
        )
        self.subscription = self.create_subscription(
            ModelStates,
            "/gazebo/model_states",
            self._model_states_callback,
            10,
        )
        self._publish_observation("EXPLORE")

    def _publish_observation(self, state):
        if state == self.observation_state and state != "EXPLORE":
            return
        self.observation_state = state
        message = String()
        message.data = state
        self.observation_publisher.publish(message)

    def _model_states_callback(self, message):
        if self.confirmed or self.target_model not in message.name:
            return
        poses = dict(zip(message.name, message.pose))
        target_pose = poses[self.target_model]
        target = (target_pose.position.x, target_pose.position.y)
        visible = set()
        for robot in self.robot_names:
            pose = poses.get(robot)
            if pose is None:
                continue
            robot_pose = (pose.position.x, pose.position.y, _yaw(pose))
            if target_visible(
                robot_pose,
                target,
                self.truth,
                self.max_distance,
                self.field_of_view,
            ):
                visible.add(robot)

        confirmed_robot = update_confirmation(
            self.streaks, visible, self.required_frames
        )
        if confirmed_robot is not None:
            self.confirmed = True
            self._publish_observation("FOUND")
            event = String()
            event.data = json.dumps(
                {
                    "robot": confirmed_robot,
                    "target_model": self.target_model,
                    "target_x": target[0],
                    "target_y": target[1],
                    "confirmation_frames": self.required_frames,
                    "max_distance_m": self.max_distance,
                    "field_of_view_deg": self.field_of_view_degrees,
                    "stamp_sec": self.get_clock().now().nanoseconds / 1e9,
                },
                sort_keys=True,
            )
            self.detection_publisher.publish(event)
            self.get_logger().info(
                f"Target confirmed by {confirmed_robot} at {target}"
            )
        elif visible:
            self._publish_observation("FOUND_UNCONFIRMED")
        elif self.observation_state == "FOUND_UNCONFIRMED":
            self._publish_observation("EXPLORE")


def main(args=None):
    rclpy.init(args=args)
    detector = TargetDetector()
    try:
        rclpy.spin(detector)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        detector.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
