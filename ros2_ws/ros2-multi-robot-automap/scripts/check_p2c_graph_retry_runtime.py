#!/usr/bin/env python3
"""Controlled actual DDS discovery race; synthetic endpoints, no task run."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import sys
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--child', choices=('original', 'retry'))
args = parser.parse_args()
root = Path(__file__).resolve().parents[1]
baseline = '6834560329e3b6fab09177747fc23e4ff23f9081'
git_root = root.parents[1]
relative = (root / 'scripts/p2c_native_graph.py').relative_to(git_root)
old_source = subprocess.check_output(['git', 'show', f'{baseline}:{relative}'], cwd=git_root)
os.environ['ROS_DOMAIN_ID'] = '216'

if args.child:
    from multi_robot_exploration import bypass_audit
    import p2c_native_graph
    from rclpy.node import Node
    from rclpy.impl.implementation_singleton import rclpy_implementation
    original_snapshot = bypass_audit.graph_snapshot
    attempted = False

    def racing_snapshot(node):
        global attempted
        if attempted:
            return original_snapshot(node)
        attempted = True
        gone = Node('p2c_vanished_discovery_endpoint')
        row = (gone.get_name(), gone.get_namespace())
        inventory = set(node.get_node_names_and_namespaces()) | {row}
        gone.destroy_node()
        deadline = time.monotonic() + 2.
        while True:
            try:
                node.get_publisher_names_and_types_by_node(*row)
            except rclpy_implementation.NodeNameNonExistentError:
                break
            assert time.monotonic() < deadline, 'deleted node remained discoverable'
            time.sleep(.02)

        class StaleInventory:
            def get_node_names_and_namespaces(self):
                return list(inventory)

            def __getattr__(self, name):
                return getattr(node, name)

        print('CONTROLLED_REAL_NODE_DELETED', flush=True)
        # The stale inventory is controlled; endpoint queries use real rclpy.
        return original_snapshot(StaleInventory())

    bypass_audit.graph_snapshot = racing_snapshot
    if args.child == 'original':
        exec(compile(old_source, f'{baseline}:{relative}', 'exec'), p2c_native_graph.__dict__)
    prefix = args.output
    sys.argv = [str(root / 'scripts/observe_p3b5.py'), '--output', str(prefix.with_suffix('.events.jsonl')),
                '--robot-count', '2', '--native-tf-graph-output', str(prefix.with_suffix('.graph.json'))]
    runpy.run_path(sys.argv[0], run_name='__main__')
    raise SystemExit(0)

assert not args.output.exists()
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import String
from tf2_msgs.msg import TFMessage
from multi_robot_exploration.bypass_audit import expected_runtime_nodes, manifest_path, split_node_name
from p2c_native_graph import native_tf_ingress_audit

rclpy.init()
nodes, publishers, children, results = {}, [], [], []
qos = QoSProfile(depth=20, reliability=ReliabilityPolicy.RELIABLE,
                 durability=DurabilityPolicy.TRANSIENT_LOCAL)


def add(full):
    if full not in nodes:
        name, namespace = split_node_name(full)
        nodes[full] = Node(name, namespace=namespace)
    return nodes[full]


def spin_for(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        for node in nodes.values():
            rclpy.spin_once(node, timeout_sec=.003)


try:
    for full in expected_runtime_nodes(json.loads(manifest_path().read_text()), 2):
        add(full)
    for robot in ('tb1', 'tb2'):
        ingress = add(f'/{robot}/gateway_tf_ingress')
        ingress.create_subscription(TFMessage, f'/{robot}/tf', lambda m: None, 20)
        ingress.create_publisher(TFMessage, f'/{robot}/battery/source_tf', 1)
        ingress.create_publisher(TFMessage, f'/{robot}/gateway/source_tf', 1)
        battery = add(f'/{robot}/battery_manager')
        battery.create_subscription(TFMessage, f'/{robot}/battery/source_tf', lambda m: None, 20)
        pub = battery.create_publisher(String, f'/{robot}/battery_state', qos)
        pub.publish(String(data=json.dumps(dict(mode='ACTIVE', return_count=0, charge_count=0))))
        publishers.append(pub)
    probe = nodes['/tb1/battery_manager'].create_publisher(String, '/tb1/battery_return_audit', qos)
    spin_for(1.)
    for variant in ('original', 'retry'):
        prefix = args.output.with_name(args.output.stem + '_' + variant)
        graph, events, log = (prefix.with_suffix(suffix) for suffix in ('.graph.json', '.events.jsonl', '.log'))
        assert not any(path.exists() for path in (graph, events, log))
        command = [sys.executable, str(Path(__file__).resolve()), '--output', str(prefix), '--child', variant]
        env = os.environ.copy()
        env['P3B5_OBSERVER_OWNER_PID'] = str(os.getpid())
        with log.open('w') as stream:
            child = subprocess.Popen(command, env=env, cwd=root, stdout=stream, stderr=subprocess.STDOUT)
            children.append(child)
            deadline = time.monotonic() + 12.
            while time.monotonic() < deadline and child.poll() is None and not graph.exists():
                probe.publish(String(data=json.dumps(dict(event='component_delivery_probe', stage='during_retry'))))
                spin_for(.1)
            if variant == 'original':
                assert child.poll() == 1 and not graph.exists(), 'original did not reject with its real discovery exception'
                assert 'NodeNameNonExistentError' in log.read_text()
                results.append(dict(variant=variant, returncode=child.returncode,
                                    original_exception_reproduced=True, graph_saved=False))
            else:
                assert child.poll() is None and graph.exists(), 'retry did not complete a fresh native graph'
                audit = native_tf_ingress_audit(json.loads(graph.read_text()), 2, True)
                probe.publish(String(data=json.dumps(dict(event='component_delivery_probe', stage='after_retry'))))
                spin_for(1.)
                child.send_signal(signal.SIGINT)
                child.wait(timeout=10)
                assert child.returncode == 0
                rows = [json.loads(line) for line in events.read_text().splitlines()]
                stages = {row['data'].get('stage') for row in rows if isinstance(row['data'], dict)
                          and row['data'].get('event') == 'component_delivery_probe'}
                assert {'during_retry', 'after_retry'} <= stages
                assert log.read_text().count('CONTROLLED_REAL_NODE_DELETED') == 1
                results.append(dict(variant=variant, returncode=child.returncode, graph_saved=True,
                                    delivery_continued=True, complete_graph=audit))
finally:
    for child in children:
        if child.poll() is None:
            child.send_signal(signal.SIGINT)
            child.wait(timeout=10)
    for node in nodes.values():
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()

result = dict(status='PASS', scope='Controlled stale inventory after real node deletion; actual DDS/rclpy observer and retry, no Gazebo/Nav2 mission',
              baseline_commit=baseline, baseline_reader_sha256=hashlib.sha256(old_source).hexdigest(),
              reader_sha256=hashlib.sha256((root / 'scripts/p2c_native_graph.py').read_bytes()).hexdigest(),
              observer_sha256=hashlib.sha256((root / 'scripts/observe_p3b5.py').read_bytes()).hexdigest(), variants=results)
args.output.write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
