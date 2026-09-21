import argparse
import json
from pathlib import Path
import time

from ament_index_python.packages import get_package_share_directory
import rclpy
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
    forbidden = {
        template.format(index=index)
        for index in range(1, robot_count + 1)
        for template in rules["forbidden_topic_templates"]
    }
    for full_name in rules["central_nodes"]:
        name, namespace = split_node_name(full_name)
        if full_name not in {
            f"{ns.rstrip('/')}/{node_name}"
            for node_name, ns in node.get_node_names_and_namespaces()
        }:
            violations.append({"kind": "runtime", "missing_node": full_name})
            continue
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
        for topic in sorted(topics & forbidden):
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


def main(args=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--robot-count", type=int, default=2)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--wait-sec", type=float, default=10.0)
    parsed = parser.parse_args(args)

    path = manifest_path()
    manifest = json.loads(path.read_text(encoding="utf-8"))
    package_root = path.resolve().parents[1]
    violations = source_violations(manifest, package_root)
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
        violations.extend(
            runtime_violations(node, manifest, parsed.robot_count)
        )
        node.destroy_node()
        rclpy.shutdown()

    result = {
        "manifest": str(path),
        "robot_count": parsed.robot_count,
        "pass": not violations,
        "violations": violations,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not violations else 1


if __name__ == "__main__":
    raise SystemExit(main())
