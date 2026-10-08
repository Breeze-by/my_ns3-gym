"""Relevant TF ingress cannot alter energy/actions or renew source leases."""
import threading
from types import MethodType, SimpleNamespace

import numpy as np
import pytest
from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.battery_manager import BatteryManager
from test_return_budget import manager


def fixture():
    node, events, states = manager()
    node.native_frame_lock = threading.Lock()
    node.native_frame_inbox = {}
    node.native_frame_overflow = False
    node.native_frame_receipts = 0
    node.native_frame_guard = SimpleNamespace(trigger=lambda:None)
    node.frame_stamp_offset = .2
    node.previous_odom_position = (1., 2.)
    node.map_to_odom = None
    node.map_tf_source_time = None
    node.enqueue_native_tf = MethodType(BatteryManager.enqueue_native_tf, node)
    return node, events, states


def frame(source, relevant=True, x=3.):
    value = TransformStamped()
    stamp = source + .2
    value.header.stamp.sec = int(stamp)
    value.header.stamp.nanosec = round((stamp-int(stamp))*1e9)
    value.header.frame_id = 'tb1/map' if relevant else 'tb1/odom'
    value.child_frame_id = 'tb1/odom' if relevant else 'tb1/base_footprint'
    value.transform.rotation.w = 1.
    value.transform.translation.x = x
    return TFMessage(transforms=[value])


def test_body_tf_cannot_replace_relevant_tf_and_input_thread_cannot_act():
    node, events, states = fixture()
    for source in range(1, 12):
        node.enqueue_native_tf(frame(source))
        node.enqueue_native_tf(frame(source, False, x=99.))
    assert list(node.native_frame_inbox) == [11.]
    assert node.native_frame_receipts == 11
    assert node.map_tf_source_time is None and node.energy == 40.
    assert events == states == [] and node.mode == 'ACTIVE'
    node.drain_native_inputs()
    assert node.map_tf_source_time == 11. and node.map_position == (4., 2.)
    assert node.previous_odom_position == (1., 2.) and node.energy == 40.
    assert events == states == [] and not node.native_frame_inbox


def test_future_tf_waits_for_clock_and_invalid_future_does_not_poison():
    node, _, _ = fixture()
    node.enqueue_native_tf(frame(10.)); node.enqueue_native_tf(frame(12.))
    node.enqueue_native_tf(frame(100.))
    node.drain_native_inputs()
    assert node.map_tf_source_time == 10. and len(node.pending_native_inputs) == 1
    node.now = lambda:12.
    node.drain_native_inputs()
    assert node.map_tf_source_time == 12. and not node.pending_native_inputs
    node.enqueue_native_tf(frame(11., x=99.)); node.drain_native_inputs()
    assert node.map_tf_source_time == 12. and node.map_position == (4., 2.)


def test_inbox_does_not_relax_stale_pose_budget():
    node, _, _ = fixture()
    node.return_map = np.zeros((44, 44), dtype=np.int16)
    node.enqueue_native_tf(frame(8.)); node.drain_native_inputs()
    assert node.map_tf_source_time == pytest.approx(8.)
    assert node.current_return_budget() is None
    node.enqueue_native_tf(frame(11.)); node.drain_native_inputs()
    assert node.current_return_budget() is not None


def test_future_ingress_is_bounded_and_fails_in_serial_consumer():
    node, events, states = fixture()
    for index in range(129):
        node.enqueue_native_tf(frame(11.1 + index*.001))
    assert node.native_frame_overflow and not node.native_frame_inbox
    assert node.mode == 'ACTIVE' and events == states == []
    node.drain_native_inputs()
    assert node.mode == 'FAILED'


def test_concurrent_inputs_preserve_newest_source_and_original_meter():
    node, events, states = fixture()
    def send(reverse):
        values = range(1, 12) if not reverse else range(11, 0, -1)
        for source in values:
            node.enqueue_native_tf(frame(source))
            node.enqueue_native_tf(frame(source, False))
    threads = [threading.Thread(target=send, args=(reverse,)) for reverse in (False, True)]
    for thread in threads:thread.start()
    for thread in threads:thread.join()
    node.drain_native_inputs()
    assert node.map_tf_source_time == 11.
    assert node.energy == 40. and node.total_motion_distance == node.total_energy_elapsed == 0.
    assert events == states == []
