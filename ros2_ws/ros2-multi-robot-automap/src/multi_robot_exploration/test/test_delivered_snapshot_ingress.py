"""Replaceable DDS receipts do not mutate or renew active planning inputs."""
import threading
from types import SimpleNamespace

import pytest
from nav_msgs.msg import OccupancyGrid, Odometry
from geometry_msgs.msg import TransformStamped
from rosidl_runtime_py.convert import message_to_ordereddict
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.control import HeadquartersControl


class Receiver:
    def __init__(self):
        self.shutdown_requested = False
        self.clock_callback_group = object()
        self.received_snapshot_lock = threading.Lock()
        self.received_snapshot_callbacks = {}
        self.triggers = 0
        self.received_snapshot_guard = SimpleNamespace(trigger=self.trigger)
        self.context = SimpleNamespace(ok=lambda: True)
        self.subscriptions = {}

    def trigger(self):
        self.triggers += 1

    def create_subscription(self, kind, topic, callback, qos, **kwargs):
        self.subscriptions[topic] = (kind, callback, qos, kwargs)
        return self.subscriptions[topic]

    def subscribe(self, topic, callback, kind=String, qos=1):
        return HeadquartersControl.create_snapshot_subscription(self, kind, topic, callback, qos)

    def receive(self, topic, message):
        self.subscriptions[topic][1](message)

    def drain(self):
        HeadquartersControl.drain_received_snapshots(self)


@pytest.mark.parametrize('kind,topic', [
    (Odometry, '/gateway/received/tb1/odom'),
    (TFMessage, '/gateway/received/tb1/tf'),
    (OccupancyGrid, '/merge_map'),
    (String, '/gateway/received/tb1/battery_state'),
])
def test_subscription_and_complete_message_preserved(kind, topic):
    receiver = Receiver();applied = [];qos = object();message = kind()
    if hasattr(message, 'header'):
        message.header.stamp.sec = 17
        message.header.stamp.nanosec = 123456789
    if kind is String:
        message.data = '{"stamp_sec":17.123456789,"mode":"ACTIVE"}'
    if kind is TFMessage:
        transform = TransformStamped()
        transform.header.stamp.sec = 17
        transform.header.stamp.nanosec = 123456789
        transform.header.frame_id = 'tb1/map'
        transform.child_frame_id = 'tb1/odom'
        transform.transform.rotation.w = 1.
        message.transforms = [transform]
    original = message_to_ordereddict(message)
    subscription = receiver.subscribe(topic, applied.append, kind, qos)
    assert subscription[0] is kind and subscription[2] is qos
    assert subscription[3] == dict(callback_group=receiver.clock_callback_group)
    receiver.receive(topic, message)
    assert not applied and receiver.triggers == 1
    receiver.drain()
    assert len(applied) == 1 and applied[0] is message
    assert message_to_ordereddict(applied[0]) == original


def test_latest_per_declared_topic_and_bound():
    receiver = Receiver();applied = []
    for topic in ('pose', 'frame'):
        receiver.subscribe(topic, lambda msg,t=topic: applied.append((t,msg)))
    for i in range(500):
        receiver.receive('pose', String(data=str(i)))
        receiver.receive('frame', String(data=str(i)))
    assert len(receiver.received_snapshot_callbacks) == 2 and not applied
    receiver.drain()
    assert [(topic,msg.data) for topic,msg in applied] == [('pose','499'),('frame','499')]
    assert not receiver.received_snapshot_callbacks


def test_one_batch_preserves_receipts_during_application():
    receiver = Receiver();applied = []
    def apply(message):
        applied.append(message.data)
        if message.data == 'old':
            receiver.receive('pose', String(data='middle'))
            receiver.receive('pose', String(data='new'))
    receiver.subscribe('pose', apply)
    receiver.receive('pose', String(data='old'));receiver.drain()
    assert applied == ['old'] and len(receiver.received_snapshot_callbacks) == 1
    receiver.drain();assert applied == ['old','new']


def test_current_source_is_not_renewed_by_concurrent_receipt():
    receiver = Receiver();state = dict(source=1.1)
    receiver.subscribe('pose', lambda msg: state.update(source=float(msg.data)))
    lease = dict(source=state['source'],ttl=2.)
    worker = threading.Thread(target=lambda: receiver.receive('pose', String(data='4.0')))
    worker.start();worker.join(timeout=2.);assert not worker.is_alive()
    assert state['source'] == 1.1 and 4.1-lease['source'] > lease['ttl']
    receiver.drain()
    assert state['source'] == 4.0 and 4.1-state['source'] < lease['ttl']
    assert lease == dict(source=1.1,ttl=2.)


@pytest.mark.parametrize('queued', [False, True])
def test_shutdown_ignores_late_or_queued_state(queued):
    receiver = Receiver();applied = [];receiver.subscribe('pose', applied.append)
    if queued:receiver.receive('pose', String(data='queued'))
    receiver.shutdown_requested = True
    receiver.receive('pose', String(data='late'));receiver.drain()
    assert not applied and not receiver.received_snapshot_callbacks
    assert receiver.triggers == int(queued)


def test_live_guard_error_is_not_hidden():
    receiver = Receiver();receiver.subscribe('pose', lambda msg: None)
    def fail():raise RuntimeError('guard unavailable')
    receiver.received_snapshot_guard.trigger = fail
    with pytest.raises(RuntimeError,match='guard unavailable'):
        receiver.receive('pose', String(data='new'))


def test_guard_shutdown_race_is_ignored():
    receiver = Receiver();receiver.subscribe('pose', lambda msg: None)
    def close():
        receiver.shutdown_requested = True
        raise RuntimeError('context closed')
    receiver.received_snapshot_guard.trigger = close
    receiver.receive('pose', String(data='new'));receiver.drain()
    assert not receiver.received_snapshot_callbacks


def test_uninitialized_fixture_has_no_inbox():
    HeadquartersControl.drain_received_snapshots(SimpleNamespace())


@pytest.mark.parametrize('method', ['assign_idle_robots','update_mission','cancel_stalled_goals'])
def test_entry_applies_current_source_before_early_state_checks(method):
    receiver = Receiver();receiver.return_probe_paused = True
    receiver.task_state = 'COMPLETE';receiver.target_search_active = False
    receiver.source = 1.1
    receiver.subscribe('pose', lambda msg: setattr(receiver,'source',float(msg.data)))
    receiver.receive('pose', String(data='4.0'))
    getattr(HeadquartersControl, method)(receiver)
    assert receiver.source == 4.0 and not receiver.received_snapshot_callbacks
