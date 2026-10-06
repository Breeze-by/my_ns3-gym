#!/usr/bin/env python3
"""Verify immutable task/safety sources and static transport equivalence."""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types

ROOT = Path(__file__).resolve().parents[3]
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src/multi_robot_exploration"))
import run_p3b_fault_matrix as matrix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", default="d8d361bfd9d81e0c7a00c428ea66cfac4b3a1a76")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("do not overwrite source evidence")
    files = [PROJECT / "src/multi_robot_exploration/multi_robot_exploration" / name for name in
             ("control.py", "battery_manager.py", "task_evaluator.py", "target_detector.py", "tf_ingress_sampler.py")]
    for directory in ("src/multi_robot/params", "src/multi_robot/worlds", "src/slam_toolbox/src", "src/slam_toolbox/config", "src/merge_map/merge_map"):
        files.extend(path for path in (PROJECT / directory).rglob("*") if path.is_file() and path.suffix != ".pyc" and "__pycache__" not in path.parts)
    rows = []
    for path in files:
        relative = path.relative_to(ROOT)
        old = subprocess.check_output(["git", "show", f"{args.baseline}:{relative}"], cwd=ROOT)
        current = path.read_bytes()
        assert old == current, f"task/safety source changed: {relative}"
        rows.append({"path": str(relative), "sha256": hashlib.sha256(current).hexdigest()})
    fault_path = PROJECT / "src/multi_robot_exploration/multi_robot_exploration/fault_model.py"
    old_bytes = subprocess.check_output(["git", "show", f"{args.baseline}:{fault_path.relative_to(ROOT)}"], cwd=ROOT)
    old = types.ModuleType("p3c_frozen_transport")
    sys.modules[old.__name__] = old
    exec(compile(old_bytes, "frozen_fault_model.py", "exec"), old.__dict__)
    current_matrix = matrix.run_matrix()
    matrix.DeterministicFaultTransport, matrix.FaultConfig = old.DeterministicFaultTransport, old.FaultConfig
    baseline_matrix = matrix.run_matrix()
    assert current_matrix == baseline_matrix, "static fault transport event semantics changed"
    navigation = PROJECT / "src/multi_robot_exploration/multi_robot_exploration/navigation_gateway.py"
    original_navigation = ast.parse(subprocess.check_output(["git", "show", f"{args.baseline}:{navigation.relative_to(ROOT)}"], cwd=ROOT))
    class RemoveOutcomeTrace(ast.NodeTransformer):
        def visit_Expr(self, node):
            call = node.value
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr == "record_local_event" and call.args and isinstance(call.args[0], ast.Constant) and call.args[0].value == "navigation_outcome":
                return None
            return self.generic_visit(node)
    current_navigation = RemoveOutcomeTrace().visit(ast.parse(navigation.read_text()))
    assert ast.dump(current_navigation) == ast.dump(original_navigation), "navigation behavior changed beyond outcome tracing"
    metrics_dir = PROJECT / "src/multi_robot_exploration/multi_robot_exploration"
    checks = []
    for name, allowed in (("metrics_node.py", {"/gateway/metrics"}), ("gateway_panel.py", set())):
        tree = ast.parse((metrics_dir / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_publisher":
                assert len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and node.args[1].value in allowed
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                assert node.func.id != "ActionClient", "monitor action client is forbidden"
        assert "/gazebo/model_states" not in (metrics_dir / name).read_text()
        checks.append({"path": name, "allowed_application_publishers": sorted(allowed), "sha256": hashlib.sha256((metrics_dir/name).read_bytes()).hexdigest()})
    result = {"status": "PASS", "baseline": args.baseline, "immutable_files": rows,
              "static_protocol_matrix": current_matrix, "static_protocol_equivalence": True,
              "navigation_ast_equivalence_except_outcome_trace": True, "monitor_sources": checks}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
    print(json.dumps({"status": "PASS", "immutable_files": len(rows), "protocol_cells": len(current_matrix["matrix"])}))


if __name__ == "__main__":
    main()
