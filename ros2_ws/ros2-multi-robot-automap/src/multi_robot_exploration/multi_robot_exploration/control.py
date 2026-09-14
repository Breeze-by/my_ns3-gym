import rclpy
from rclpy.node import Node
from nav_msgs.msg import OccupancyGrid, Odometry
from geometry_msgs.msg import PoseStamped, Twist
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from geometry_msgs.msg import Pose
from std_msgs.msg import Float32MultiArray

import numpy as np
import subprocess
import heapq, math, time, threading
import scipy.interpolate as si
import datetime
from action_msgs.msg import GoalStatus
import os
from ament_index_python.packages import get_package_share_directory

lookahead_distance = 0.5  # forward looking distance
speed = 0.4  # maximum speed
expansion_size = 7  # wall expansion coefficient
target_error = 0.15  # margin of error to target
max_target_distance_m = 7.5
min_frontier_group_size = 6
min_target_separation = 0.8
map_edge_margin_m = 0.5
obstacle_clearance_m = 0.45
max_goal_failures = 3
occupied_threshold = 50

VISITED = []
BAD_TARGETS = []


def frontierB(matrix):
    for i in range(len(matrix)):
        for j in range(len(matrix[i])):
            if matrix[i][j] == 0.0:
                if i > 0 and matrix[i-1][j] < 0:
                    matrix[i][j] = 2
                elif i < len(matrix)-1 and matrix[i+1][j] < 0:
                    matrix[i][j] = 2
                elif j > 0 and matrix[i][j-1] < 0:
                    matrix[i][j] = 2
                elif j < len(matrix[i])-1 and matrix[i][j+1] < 0:
                    matrix[i][j] = 2
    return matrix

def assign_groups(matrix):
    group = 1
    groups = {}
    for i in range(len(matrix)):
        for j in range(len(matrix[0])):
            if matrix[i][j] == 2:
                group = dfs(matrix, i, j, group, groups)
    return matrix, groups

def dfs(matrix, i, j, group, groups):
    if i < 0 or i >= len(matrix) or j < 0 or j >= len(matrix[0]):
        return group
    if matrix[i][j] != 2:
        return group
    if group in groups:
        groups[group].append((i, j))
    else:
        groups[group] = [(i, j)]
    matrix[i][j] = 0
    dfs(matrix, i + 1, j, group, groups)
    dfs(matrix, i - 1, j, group, groups)
    dfs(matrix, i, j + 1, group, groups)
    dfs(matrix, i, j - 1, group, groups)
    dfs(matrix, i + 1, j + 1, group, groups)  # lower right diagonal
    dfs(matrix, i - 1, j - 1, group, groups)  # upper left cross
    dfs(matrix, i - 1, j + 1, group, groups)  # upper right cross
    dfs(matrix, i + 1, j - 1, group, groups)  # lower left diagonal
    return group + 1

def fGroups(groups):
    sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
    top_five_groups = [g for g in sorted_groups[:8] if len(g[1]) >= min_frontier_group_size]
    return top_five_groups

def calculate_centroid(x_coords, y_coords):
    n = len(x_coords)
    sum_x = sum(x_coords)
    sum_y = sum(y_coords)
    mean_x = sum_x / n
    mean_y = sum_y / n
    centroid = (mean_x, mean_y)
    return centroid

def visitedControl(targetP):
    global VISITED
    for k in VISITED + BAD_TARGETS:
        d = math.sqrt((k[0] - targetP[0])**2 + (k[1] - targetP[1])**2)
        if d < min_target_separation:
            return True
    return False

def inflate_obstacles(data, width, height, clearance_cells):
    data = np.array(data).reshape(height, width)
    wall = np.where(data >= occupied_threshold)
    for i in range(-clearance_cells, clearance_cells + 1):
        for j in range(-clearance_cells, clearance_cells + 1):
            if i == 0 and j == 0:
                continue
            x = wall[0] + i
            y = wall[1] + j
            x = np.clip(x, 0, height - 1)
            y = np.clip(y, 0, width - 1)
            data[x, y] = 100
    return data

def meters_to_cells(distance, resolution):
    return max(1, int(math.ceil(distance / resolution)))

def grid_to_world(row, column, resolution, originX, originY):
    return (
        (column + 0.5) * resolution + originX,
        (row + 0.5) * resolution + originY,
    )

def is_cell_safe(raw_grid, row, column, resolution):
    """A navigation target must be known free, away from walls, and inside map bounds."""
    height, width = raw_grid.shape
    edge_margin = meters_to_cells(map_edge_margin_m, resolution)
    obstacle_clearance = meters_to_cells(obstacle_clearance_m, resolution)

    if row < edge_margin or row >= height - edge_margin:
        return False
    if column < edge_margin or column >= width - edge_margin:
        return False
    if raw_grid[row, column] != 0:
        return False

    r0 = max(0, row - obstacle_clearance)
    r1 = min(height, row + obstacle_clearance + 1)
    c0 = max(0, column - obstacle_clearance)
    c1 = min(width, column + obstacle_clearance + 1)
    window = raw_grid[r0:r1, c0:c1]
    return not np.any(window >= occupied_threshold)

def findClosestGroup(raw_grid, groups, current, resolution, originX, originY, last_target=None):
    best_target = None
    best_score = float('-inf')  # A large negative number to ensure proper comparison
    for i in range(len(groups)):
        group_cells = groups[i][1]
        centroid = calculate_centroid([p[0] for p in group_cells], [p[1] for p in group_cells])
        safe_cells = [p for p in group_cells if is_cell_safe(raw_grid, p[0], p[1], resolution)]
        if not safe_cells:
            continue

        row, column = min(
            safe_cells,
            key=lambda p: math.sqrt((centroid[0] - p[0])**2 + (centroid[1] - p[1])**2)
        )
        target_world = grid_to_world(row, column, resolution, originX, originY)
        distance_m = math.sqrt(
            ((current[0] - row) * resolution)**2 + ((current[1] - column) * resolution)**2
        )
        if distance_m > max_target_distance_m:
            continue
        if last_target and math.sqrt((target_world[0] - last_target[0]) ** 2 + (target_world[1] - last_target[1]) ** 2) < min_target_separation:
            continue
        if visitedControl(target_world):
            continue

        group_size = len(group_cells)
        score = group_size / (distance_m + 1.0)
        if score > best_score:
            best_score = score
            best_target = target_world
    return best_target

def mark_bad_target(target):
    global BAD_TARGETS
    for k in BAD_TARGETS:
        d = math.sqrt((k[0] - target[0])**2 + (k[1] - target[1])**2)
        if d < min_target_separation:
            return
    BAD_TARGETS.append(target)

def exploration(data, width, height, resolution, column, row, originX, originY, choice, last_target=None):
    global VISITED
    f = 1
    if row < 0 or row >= height or column < 0 or column >= width:
        return None
    raw_grid = np.array(data).reshape(height, width)
    obstacle_clearance = meters_to_cells(obstacle_clearance_m, resolution)
    frontier_grid = inflate_obstacles(raw_grid, width, height, obstacle_clearance)
    frontier_grid[row][column] = 0  # Robot Current Location
    frontier_grid = frontierB(frontier_grid)
    frontier_grid, groups = assign_groups(frontier_grid)
    groups = fGroups(groups)

    if len(groups) == 0:
        f = -1
    else:
        coordinate = findClosestGroup(
            raw_grid,
            groups,
            (row, column),
            resolution,
            originX,
            originY,
            last_target=last_target,
        )
        if coordinate is None:
            f = -1
        else:
            VISITED.append(coordinate)
    if f == -1:
        return None
    else:
        return coordinate

def get(choice):
    now = datetime.datetime.now()
    time_string = now.strftime("%H:%M:%S")
    print(f"[BILGI] {time_string}: {choice+1}. ROAD REQUEST RECEIVED BY THE ROBOT")

def response(choice):
    now = datetime.datetime.now()
    time_string = now.strftime("%H:%M:%S")
    print(f"[BILGI] {time_string}: {choice+1}. ROAD REQUEST ANSWER SENT TO THE ROBOT")

class HeadquartersControl(Node):
    def __init__(self):
        super().__init__("headquarters_control")
        self.shutdown_initiated = False
        self.robots = {}  # Dictionary to hold robot data
        self.num_robots = self.declare_parameter("robot_count", 2).value

        # Subscribers for multiple robots dynamically
        self.map_sub = self.create_subscription(
            OccupancyGrid, "merge_map", self.map_callback, 10
        )
        self.robot_odom_subs = {}
        self.robot_nav_clients = {}
        self.robot_positions = {}
        self.subscription_cmd_vel = {}
        self.robot_states = {
            f"tb{i+1}": "idle" for i in range(self.num_robots)
        }
        self.goal_failures = {
            f"tb{i+1}": 0 for i in range(self.num_robots)
        }
        self.last_save_time = time.monotonic()
        self.save_in_progress = False
        self.auto_save_map = self.declare_parameter("auto_save_map", True).value
        self.save_map_interval_sec = self.declare_parameter(
            "save_map_interval_sec", 60.0
        ).value

        # Action clients and odometry subscribers for dynamic robots
        for i in range(self.num_robots):
            robot_name = f"tb{i + 1}"
            self.robot_odom_subs[robot_name] = self.create_subscription(
                Odometry, f"{robot_name}/odom", lambda msg, r=robot_name: self.robot_odom_callback(msg, r), 10
            )
            self.robot_nav_clients[robot_name] = ActionClient(self, NavigateToPose, f"{robot_name}/navigate_to_pose")
            self.subscription_cmd_vel[robot_name] = self.create_subscription(
                Twist, f"{robot_name}/cmd_vel", lambda msg, r=robot_name: self.robot_status_control(msg, r), 4
            )
            self.robot_positions[robot_name] = (0.0, 0.0)

        # State variables
        self.map_data = None
        self.resolution = None
        self.origin = None
        self.map_width = None
        self.map_height = None
        self.map_saved = False  # Flag to track if map is saved

        # Threads for goal navigation
        for i in range(self.num_robots):
            threading.Thread(target=self.start_exploration, args=(i + 1,), daemon=True).start()

        self.get_logger().info("Navigation to map center initialized.")

    def map_callback(self, msg):
        """Callback to handle the map data."""
        self.map_data = np.array(msg.data).reshape(msg.info.height, msg.info.width)
        self.resolution = msg.info.resolution
        self.origin = (msg.info.origin.position.x, msg.info.origin.position.y)
        self.map_width = msg.info.width
        self.map_height = msg.info.height

    def robot_odom_callback(self, msg, robot_name):
        """Callback to update robot position dynamically."""
        self.robot_positions[robot_name] = (msg.pose.pose.position.x, msg.pose.pose.position.y)

    def robot_status_control(self, msg, robot_name):
        """Command velocity control for individual robots."""
        pass

    def start_exploration(self, robot_number):
        """Logic to explore with the specified robot."""
        robot_name = f"tb{robot_number}"
        last_target = None  # To prevent sending the same goal repeatedly
        while rclpy.ok():
            if self.map_data is not None:
                robot_position = self.robot_positions[robot_name]
                # Check if the robot is idle before assigning a new goal
                if self.robot_states[robot_name] == "idle":
                    target = exploration(
                        self.map_data,
                        self.map_width,
                        self.map_height,
                        self.resolution,
                        int((robot_position[0] - self.origin[0]) / self.resolution),
                        int((robot_position[1] - self.origin[1]) / self.resolution),
                        self.origin[0],
                        self.origin[1],
                        robot_name,
                        last_target=last_target
                    )

                    if target:
                        last_target = target
                        self.get_logger().info(f"Target for {robot_name} is {target}")
                        self.robot_states[robot_name] = "active"  # Mark robot as active
                        self.send_goal(robot_name, target)
                else:
                    self.get_logger().debug(f"{robot_name} is currently busy.")
            time.sleep(8)
        # Check for exploration completion after all goals are completed
        self.check_exploration_completion()
            
    def send_goal(self, robot_name, target):
        """Send a navigation goal to the robot."""
        if robot_name in self.robot_nav_clients and self.robot_nav_clients[robot_name].wait_for_server(timeout_sec=2.0):
            goal = NavigateToPose.Goal()
            goal.pose.pose.position.x = target[0]
            goal.pose.pose.position.y = target[1]
            goal.pose.header.frame_id = "map"
            goal.pose.header.stamp = self.get_clock().now().to_msg()

            # Send goal and set up callbacks
            future = self.robot_nav_clients[robot_name].send_goal_async(goal, feedback_callback=self.feedback_callback)
            future.add_done_callback(lambda f: self.goal_response_callback(robot_name, target, f))
        else:
            self.get_logger().warn(f"Navigation action server for {robot_name} is not available.")
            self.robot_states[robot_name] = "idle"

    def feedback_callback(self, feedback_msg):
        """Handle feedback from the action server."""
        # Optionally process feedback, e.g., log progress
        pass

    def goal_response_callback(self, robot_name, target, future):
        """Handle action server acceptance, then wait for the final result."""
        goal_handle = future.result()
        if goal_handle is None or not goal_handle.accepted:
            self.get_logger().warn(f"{robot_name} rejected goal {target}; choosing another frontier.")
            mark_bad_target(target)
            self.goal_failures[robot_name] += 1
            self.robot_states[robot_name] = "idle"
            return

        result_future = goal_handle.get_result_async()
        result_future.add_done_callback(lambda f: self.goal_result_callback(robot_name, target, f.result()))

    def goal_result_callback(self, robot_name, target, result):
        """Handle the result of the goal."""
        if result.status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info(f"{robot_name} reached its goal!")
            self.goal_failures[robot_name] = 0
            self.robot_states[robot_name] = "idle"  # Mark as idle after completion
        else:
            self.goal_failures[robot_name] += 1
            self.get_logger().warn(
                f"{robot_name} failed goal {target} with status {result.status}; "
                f"failure count={self.goal_failures[robot_name]}"
            )
            mark_bad_target(target)
            if self.goal_failures[robot_name] >= max_goal_failures:
                VISITED.append(target)
                self.goal_failures[robot_name] = 0
            self.robot_states[robot_name] = "idle"  # Allow retries or new goals

        # Check if all robots are idle and trigger map saving
        self.check_exploration_completion()

    def check_exploration_completion(self):
        """Check if all robots are idle and exploration is complete."""
        now = time.monotonic()
        enough_time_elapsed = now - self.last_save_time >= self.save_map_interval_sec
        if (
            self.auto_save_map
            and self.map_data is not None
            and all(state == "idle" for state in self.robot_states.values())
            and enough_time_elapsed
            and not self.save_in_progress
        ):
            self.get_logger().info("All robots are idle. Saving the merged map.")
            self.save_in_progress = True
            self.last_save_time = now
            threading.Thread(target=self.save_map).start()
    
    
    def save_map(self):
        try:
            print("[BILGI] Saving the merged map...")
            subprocess.run([
                'ros2', 'run', 'nav2_map_server', 'map_saver_cli',
                '-t', '/merge_map',
                '-f', os.path.join(
                        get_package_share_directory('multi_robot'),
                        '../../../../src/saved_map/multi_robot_autonomous_mapping_of_'+str(self.num_robots)+'_robots'),
                '--ros-args',
                '-p', 'map_subscribe_transient_local:=true'
            ], check=True)
            print("[BILGI] Map saved successfully!")
        except subprocess.CalledProcessError as e:
            print(f"[HATA] Failed to save the map: {e}")
        except Exception as e:
            print(f"[HATA] Unexpected error during map saving: {e}")
        finally:
            self.save_in_progress = False

    def shutdown_node(self):
        if (
            self.auto_save_map
            and self.map_data is not None
            and not self.save_in_progress
        ):
            self.save_in_progress = True
            self.save_map()

                
def main(args=None):
    rclpy.init(args=args)
    control = HeadquartersControl()
    print(f"Number of robots: {control.num_robots}")

    try:
        rclpy.spin(control)
    except KeyboardInterrupt:
        control.exploration_active = False
        control.get_logger().info("Shutting down exploration.")
    except ExternalShutdownException:
        pass
    finally:
        if rclpy.ok():
            control.shutdown_node()
            control.get_logger().info("Node shutdown successfully.")
        control.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
