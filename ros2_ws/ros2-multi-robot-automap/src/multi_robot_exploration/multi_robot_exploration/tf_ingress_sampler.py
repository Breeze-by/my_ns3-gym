"""Robot-side TF source sampling before the multi-endpoint gateway executor.

Forward only a new native map->odom sample, without changing its validity stamp.
Repeated TF and odom/base traffic otherwise saturate the gateway's Humble Python
wait-set even though its existing candidate throttle discards them later.
"""
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from tf2_msgs.msg import TFMessage


class TfIngressSampler(Node):
    def __init__(self):
        super().__init__('gateway_tf_ingress')
        robot = str(self.declare_parameter('robot_name', 'tb1').value)
        self.last_source_stamp = -1
        self.publisher = self.create_publisher(TFMessage, f'/{robot}/gateway/source_tf', QoSProfile(depth=1))
        # Native safety owns ordering, future deferral and the original TTL.
        # Filter body transforms before its DDS queue, but forward every
        # relevant original sample, including duplicates and invalid futures.
        self.native_publisher = self.create_publisher(TFMessage, f'/{robot}/battery/source_tf', QoSProfile(depth=1))
        # A bounded mixed-TF queue must retain relevant transforms across body
        # bursts. Consumer TTLs still reject old sources after any backlog.
        self.create_subscription(TFMessage, f'/{robot}/tf', self.observe,
                                 QoSProfile(depth=100, reliability=ReliabilityPolicy.BEST_EFFORT))

    def observe(self, message):
        relevant = [t for t in message.transforms
                    if t.header.frame_id.lstrip('/').endswith('map')
                    and t.child_frame_id.lstrip('/').endswith('odom')]
        if not relevant:
            return
        self.native_publisher.publish(TFMessage(transforms=relevant))
        transform = max(relevant, key=lambda t: t.header.stamp.sec*10**9+t.header.stamp.nanosec)
        stamp = transform.header.stamp.sec*10**9+transform.header.stamp.nanosec
        if stamp <= self.last_source_stamp:
            return
        self.publisher.publish(TFMessage(transforms=[transform]))
        self.last_source_stamp = stamp


def main(args=None):
    rclpy.init(args=args)
    node = TfIngressSampler()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
