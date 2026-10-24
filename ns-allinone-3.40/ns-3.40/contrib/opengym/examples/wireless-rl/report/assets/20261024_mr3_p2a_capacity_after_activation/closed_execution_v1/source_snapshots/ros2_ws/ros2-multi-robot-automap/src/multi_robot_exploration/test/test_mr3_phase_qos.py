"""Exercise the actual phase endpoint factory statements with native rclpy QoS."""

import ast
import copy
import json
from pathlib import Path
import time
from types import SimpleNamespace

import pytest
import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import (
    DurabilityPolicy, QoSCompatibility, QoSProfile, ReliabilityPolicy, qos_check_compatible,
)
from std_msgs.msg import String


ROOT = Path(__file__).resolve().parents[3]
PACKAGE = ROOT / "src/multi_robot_exploration/multi_robot_exploration"
TOPICS = {"state": "/mr3/state_phase_ack", "peer": "/mr3/peer_phase_ack",
          "motion": "/motion_safety/control_ack"}


def constructor(path, class_name):
    tree = ast.parse(path.read_text())
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef)
               and node.name == class_name)
    return next(node for node in cls.body if isinstance(node, ast.FunctionDef)
                and node.name == "__init__")


def assignment(function, name, attribute=False):
    matches = [node for node in ast.walk(function) if isinstance(node, ast.Assign)
               and any((isinstance(target, ast.Attribute) and target.attr == name
                        if attribute else isinstance(target, ast.Name) and target.id == name)
                       for target in node.targets)]
    assert len(matches) == 1
    return matches[0]


def topic_loop(function, topics):
    matches = [node for node in ast.walk(function) if isinstance(node, ast.For)
               and {item.value for item in ast.walk(node.iter)
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                    and item.value.startswith("/")} == set(topics)]
    assert len(matches) == 1
    return matches[0]


def execute(statements, namespace, filename):
    # No profiles are reconstructed by the test. These exact production
    # statements call the real Node factories and resolve integer defaults in
    # the installed rclpy. Unrelated services, timers and control are omitted.
    tree = ast.Module(body=copy.deepcopy(statements), type_ignores=[])
    exec(compile(tree, str(filename), "exec"), namespace)


@pytest.fixture(scope="module")
def endpoints():
    context = Context()
    rclpy.init(args=[], context=context, domain_id=230)
    nodes = []
    executor = None
    try:
        for name in ("worker", "information", "peer", "guard"):
            nodes.append(Node("mr3_phase_qos_" + name, context=context))
        worker_node, state_node, peer_node, guard_node = nodes
        received = []
        worker = SimpleNamespace(
            node=worker_node, subscriptions=[],
            receive_control_phase=lambda name, value: received.append((name, value)))
        common = {"String": String, "QoSProfile": QoSProfile,
                  "DurabilityPolicy": DurabilityPolicy, "ReliabilityPolicy": ReliabilityPolicy,
                  "json": json, "callback": lambda callback: callback}
        worker_path = ROOT / "scripts/mr3_env_worker.py"
        function = constructor(worker_path, "Worker")
        execute([assignment(function, "qos"), topic_loop(function, TOPICS.values())],
                {**common, "self": worker}, worker_path)

        state_path = PACKAGE / "mr3_information.py"
        function = constructor(state_path, "IdealInformation")
        execute([assignment(function, "map_qos"),
                 assignment(function, "state_phase_publisher", attribute=True)],
                {**common, "self": state_node}, state_path)

        peer_path = PACKAGE / "peer_obstacles.py"
        function = constructor(peer_path, "PeerObstacles")
        execute([assignment(function, "phase_ack_pub", attribute=True)],
                {**common, "self": peer_node}, peer_path)

        guard = SimpleNamespace(subscriptions=[], receive_dependency=lambda *args: None)
        guard_path = PACKAGE / "mr3_motion_control.py"
        function = constructor(guard_path, "MotionControlPhase")
        execute([assignment(function, "durable"), assignment(function, "publisher", True),
                 topic_loop(function, (TOPICS["state"], TOPICS["peer"]))],
                {**common, "self": guard, "node": guard_node}, guard_path)
        subscriptions = {subscription.topic_name: subscription
                         for subscription in worker.subscriptions}
        publishers = {"state": state_node.state_phase_publisher,
                      "peer": peer_node.phase_ack_pub, "motion": guard.publisher}
        dependencies = {subscription.topic_name: subscription
                        for subscription in guard.subscriptions}
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(worker_node)
        yield publishers, subscriptions, dependencies, received, executor, nodes
    finally:
        if executor is not None:
            executor.shutdown(timeout_sec=2.)
        for node in reversed(nodes):
            node.destroy_node()
        rclpy.shutdown(context=context)


def check_compatibility(producer, consumer):
    compatibility, reason = qos_check_compatible(producer, consumer)
    assert compatibility != QoSCompatibility.ERROR, reason
    if compatibility == QoSCompatibility.WARNING:
        # The installed checker cannot resolve declared SYSTEM_DEFAULT
        # liveliness. Check resolved native graph QoS separately below.
        assert reason == ("WARNING: Publisher liveliness is system_default and "
                          "subscription liveliness is system_default;")


def check_actual_graph(endpoints, component, dependency=False):
    node = endpoints[-1][0]
    source = {"state": "information", "peer": "peer", "motion": "guard"}[component]
    consumer = "guard" if dependency else "worker"
    deadline = time.monotonic() + 3.
    while True:
        pubs = [entry for entry in node.get_publishers_info_by_topic(TOPICS[component])
                if entry.node_name == "mr3_phase_qos_" + source]
        subs = [entry for entry in node.get_subscriptions_info_by_topic(TOPICS[component])
                if entry.node_name == "mr3_phase_qos_" + consumer]
        if len(pubs) == len(subs) == 1:
            compatibility, reason = qos_check_compatible(pubs[0].qos_profile, subs[0].qos_profile)
            assert compatibility == QoSCompatibility.OK, reason
            return
        assert time.monotonic() < deadline, "actual production-code endpoint discovery timeout"
        time.sleep(.01)


@pytest.mark.parametrize("component", ("state", "peer", "motion"))
def test_actual_ack_producer_is_compatible_with_actual_worker_subscription(endpoints, component):
    publishers, subscriptions, _, _, _, _ = endpoints
    producer = publishers[component].qos_profile
    consumer = subscriptions[TOPICS[component]].qos_profile
    check_compatibility(producer, consumer)
    check_actual_graph(endpoints, component)
    assert producer.durability == consumer.durability == DurabilityPolicy.TRANSIENT_LOCAL
    assert producer.reliability == consumer.reliability == ReliabilityPolicy.RELIABLE
    assert producer.depth == consumer.depth == 1


@pytest.mark.parametrize("component", ("state", "peer"))
def test_actual_state_peer_ack_producers_match_actual_guard_dependencies(endpoints, component):
    publishers, _, dependencies, _, _, _ = endpoints
    check_compatibility(publishers[component].qos_profile,
                        dependencies[TOPICS[component]].qos_profile)
    check_actual_graph(endpoints, component, dependency=True)


def test_all_three_actual_ack_factories_deliver_to_actual_worker_callback_statements(endpoints):
    publishers, subscriptions, _, received, executor, _ = endpoints
    for component, publisher in publishers.items():
        check_compatibility(publisher.qos_profile, subscriptions[TOPICS[component]].qos_profile)
        payload = {"purpose": "isolated actual-endpoint QoS regression", "component": component}
        publisher.publish(String(data=json.dumps(payload)))
    deadline = time.monotonic() + 5.
    while len(received) < 3 and time.monotonic() < deadline:
        executor.spin_once(timeout_sec=.02)
    assert sorted(name for name, _ in received) == ["motion", "peer", "state"]
    assert all(name == payload["component"] for name, payload in received)
