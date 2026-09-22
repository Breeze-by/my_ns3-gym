import argparse
import json
from pathlib import Path
import time

from ament_index_python.packages import get_package_share_directory
import rclpy
from rclpy.action.graph import (
    get_action_client_names_and_types_by_node,
    get_action_server_names_and_types_by_node,
)
from rclpy.node import Node


def manifest_path():
    installed = Path(
        get_package_share_directory("multi_robot_exploration")
    ) / "config" / "p3a_forbidden_bypasses.json"
    if installed.exists():
        return installed
    return (
        Path(__file__).resolve().parents[1]
        / "config"
        / "p3a_forbidden_bypasses.json"
    )


def source_violations(manifest, package_root):
    violations = []
    for rule in manifest["source_rules"]:
        path = (package_root / rule["file"]).resolve()
        text = path.read_text(encoding="utf-8")
        for literal in rule["forbidden_literals"]:
            if literal in text:
                violations.append(
                    {
                        "kind": "source",
                        "file": str(path),
                        "literal": literal,
                    }
                )
    return violations


def split_node_name(full_name):
    namespace, _, name = full_name.rpartition("/")
    return name, namespace or "/"


def expected_runtime_nodes(manifest, robot_count):
    nodes = set(manifest["runtime_rules"]["central_nodes"])
    nodes.update(
        f"/tb{index}/global_costmap/global_costmap"
        for index in range(1, robot_count + 1)
    )
    return nodes


def runtime_violations(node, manifest, robot_count):
    rules = manifest["runtime_rules"]
    violations = []
    legacy_forbidden = {
        template.format(index=index)
        for index in range(1, robot_count + 1)
        for template in rules["forbidden_topic_templates"]
    }
    forbidden_subscribers = {
        template.format(index=index)
        for index in range(1, robot_count + 1)
        for template in rules.get(
            "forbidden_subscriber_topic_templates",
            rules["forbidden_topic_templates"],
        )
    }
    forbidden_publishers = {
        template.format(index=index)
        for index in range(1, robot_count + 1)
        for template in rules.get("forbidden_publisher_topic_templates", [])
    }
    for full_name in rules["central_nodes"]:
        name, namespace = split_node_name(full_name)
        if full_name not in {
            f"{ns.rstrip('/')}/{node_name}"
            for node_name, ns in node.get_node_names_and_namespaces()
        }:
            violations.append({"kind": "runtime", "missing_node": full_name})
            continue
        subscribers = {
            topic
            for topic, _ in node.get_subscriber_names_and_types_by_node(
                name, namespace
            )
        }
        publishers = {
            topic
            for topic, _ in node.get_publisher_names_and_types_by_node(
                name, namespace
            )
        }
        for topic in sorted(subscribers & forbidden_subscribers):
            violations.append(
                {
                    "kind": "runtime",
                    "direction": "subscriber",
                    "node": full_name,
                    "topic": topic,
                }
            )
        for topic in sorted(publishers & forbidden_publishers):
            violations.append(
                {
                    "kind": "runtime",
                    "direction": "publisher",
                    "node": full_name,
                    "topic": topic,
                }
            )
        topics = set()
        topics.update(
            topic
            for topic, _ in node.get_subscriber_names_and_types_by_node(
                name, namespace
            )
        )
        topics.update(
            topic
            for topic, _ in node.get_publisher_names_and_types_by_node(
                name, namespace
            )
        )
        for topic in sorted(topics & legacy_forbidden):
            if topic in forbidden_subscribers or topic in forbidden_publishers:
                continue
            violations.append(
                {"kind": "runtime", "node": full_name, "topic": topic}
            )

    for index in range(1, robot_count + 1):
        full_name = f"/tb{index}/global_costmap/global_costmap"
        name, namespace = split_node_name(full_name)
        if full_name not in {
            f"{ns.rstrip('/')}/{node_name}"
            for node_name, ns in node.get_node_names_and_namespaces()
        }:
            violations.append({"kind": "runtime", "missing_node": full_name})
            continue
        topics = {
            topic
            for topic, _ in node.get_subscriber_names_and_types_by_node(
                name, namespace
            )
        }
        if rules["robot_forbidden_topic"] in topics:
            violations.append(
                {
                    "kind": "runtime",
                    "node": full_name,
                    "topic": rules["robot_forbidden_topic"],
                }
            )
    return violations


def graph_snapshot(node):
    snapshot = {"nodes": {}}
    for name, namespace in sorted(
        set(node.get_node_names_and_namespaces())
    ):
        full_name = f"{namespace.rstrip('/')}/{name}"
        snapshot["nodes"][full_name] = {
            "publishers": node.get_publisher_names_and_types_by_node(
                name, namespace
            ),
            "subscribers": node.get_subscriber_names_and_types_by_node(
                name, namespace
            ),
            "clients": node.get_client_names_and_types_by_node(
                name, namespace
            ),
            "services": node.get_service_names_and_types_by_node(
                name, namespace
            ),
            "action_clients": get_action_client_names_and_types_by_node(
                node, name, namespace
            ),
            "action_servers": get_action_server_names_and_types_by_node(
                node, name, namespace
            ),
        }
    return snapshot


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-count", type=int, default=2)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--wait-sec", type=float, default=10.0)
    parser.add_argument("--graph-output", type=Path)
    parsed = parser.parse_args(args)

    path = manifest_path()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    package_root = path.resolve().parents[1]
    violations = source_violations(manifest, package_root)
    snapshot = None
    if not parsed.source_only:
        rclpy.init()
        node = Node("p3a_bypass_audit")
        deadline = time.monotonic() + parsed.wait_sec
        expected = expected_runtime_nodes(manifest, parsed.robot_count)
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
            discovered = {
                f"{namespace.rstrip('/')}/{name}"
                for name, namespace in node.get_node_names_and_namespaces()
            }
            if expected <= discovered:
                break
        violations.extend(runtime_violations(node, manifest, parsed.robot_count))
        snapshot = graph_snapshot(node)
        node.destroy_node()
        rclpy.shutdown()

    if parsed.graph_output and snapshot is not None:
        parsed.graph_output.parent.mkdir(parents=True, exist_ok=True)
        parsed.graph_output.write_text(
            json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8"
        )

    result = {
        "manifest": str(path),
        "robot_count": parsed.robot_count,
        "pass": not violations,
        "violations": violations,
        "graph_output": str(parsed.graph_output) if parsed.graph_output else None,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
