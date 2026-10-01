"""Bounded startup-only spawning, confirmed against Gazebo model presence.

Humble's spawn_entity.py bounds service discovery but waits forever for a reply.
Gazebo may insert the model and lose that reply. Send once, confirm the physical
entity, and fail within the wall-clock budget if insertion did not happen.
This node exits before task execution; truth never enters task decisions.
"""
import argparse
import math
from pathlib import Path
import time
import xml.etree.ElementTree as ET

from gazebo_msgs.msg import ModelStates
from gazebo_msgs.srv import GetModelList, SpawnEntity
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.utilities import remove_ros_args


class ModelInventory:
    """Retry only read requests; a spawn request is never repeated."""

    def __init__(self, node):
        self.node = node
        self.client = node.create_client(GetModelList, '/get_model_list')
        self.pending = None
        self.next_query = 0.

    def poll(self, now):
        if self.pending is not None:
            future, started = self.pending
            if future.done():
                try:
                    response = future.result()
                    if response is not None and response.success:
                        self.node.model_names = set(response.model_names)
                except Exception as error:
                    self.node.get_logger().warn(f'Model inventory query failed: {error}')
                self.pending = None
                self.next_query = now + .5
            elif now - started >= 2.:
                self.client.remove_pending_request(future)
                future.cancel()
                self.pending = None
        if self.pending is None and now >= self.next_query and self.client.service_is_ready():
            self.pending = self.client.call_async(GetModelList.Request()), now


def finish_spawn(node, future, deadline, *, clock=time.monotonic,
                 spin=rclpy.spin_once, okay=rclpy.ok, inventory=None):
    while okay() and clock() < deadline:
        if inventory is not None:
            inventory.poll(clock())
        if future.done():
            response = future.result()
            if response is None or not response.success:
                node.get_logger().error("Spawn rejected: " + str(response))
                return False
        if node.entity in (node.model_names or set()):
            node.get_logger().info(
                f"Confirmed Gazebo entity {node.entity}; reply_received={future.done()}"
            )
            return True
        spin(node, timeout_sec=min(.1, max(0., deadline-clock())))
    node.get_logger().error(f"Entity {node.entity} not confirmed within spawn wall timeout")
    return False


def main(args=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-file', required=True)
    parser.add_argument('-entity', required=True)
    parser.add_argument('-robot_namespace', default='')
    parser.add_argument('-timeout', type=float, default=90.)
    for key in ('x', 'y', 'z', 'R', 'P', 'Y'):
        parser.add_argument('-'+key, type=float, default=0.)
    options = parser.parse_args(remove_ros_args(args=args)[1:])
    if not math.isfinite(options.timeout) or options.timeout <= 0:
        parser.error('timeout must be finite and positive')
    if not all(math.isfinite(getattr(options, key)) for key in ('x', 'y', 'z', 'R', 'P', 'Y')):
        parser.error('spawn pose must be finite')
    xml = Path(options.file).read_text()
    ET.fromstring(xml)
    rclpy.init(args=args)
    node = Node('spawn_entity_checked')
    node.entity, node.model_names = options.entity, None

    def observe(message):
        node.model_names = set(message.name)

    node.create_subscription(ModelStates, '/gazebo/model_states', observe, qos_profile_sensor_data)
    inventory = ModelInventory(node)
    deadline = time.monotonic() + options.timeout
    success = False
    try:
        while rclpy.ok() and node.model_names is None and time.monotonic() < deadline:
            inventory.poll(time.monotonic())
            rclpy.spin_once(node, timeout_sec=.1)
        if node.model_names is None or options.entity in node.model_names:
            node.get_logger().error('No fresh model inventory, or entity already exists; refusing spawn')
        else:
            client = node.create_client(SpawnEntity, '/spawn_entity')
            if client.wait_for_service(timeout_sec=max(0., deadline-time.monotonic())):
                request = SpawnEntity.Request()
                request.name, request.xml = options.entity, xml
                request.robot_namespace = options.robot_namespace
                p = request.initial_pose
                p.position.x, p.position.y, p.position.z = options.x, options.y, options.z
                sr, cr = math.sin(options.R/2), math.cos(options.R/2)
                sp, cp = math.sin(options.P/2), math.cos(options.P/2)
                sy, cy = math.sin(options.Y/2), math.cos(options.Y/2)
                p.orientation.x, p.orientation.y = sr*cp*cy-cr*sp*sy, cr*sp*cy+sr*cp*sy
                p.orientation.z, p.orientation.w = cr*cp*sy-sr*sp*cy, cr*cp*cy+sr*sp*sy
                success = finish_spawn(node, client.call_async(request), deadline, inventory=inventory)
            else:
                node.get_logger().error('Spawn service unavailable within wall timeout')
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return 0 if success else 1
