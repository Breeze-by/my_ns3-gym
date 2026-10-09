"""A transient discovery race rejects a snapshot without hiding other errors."""
import pytest
from rclpy.impl.implementation_singleton import rclpy_implementation
from multi_robot_exploration import bypass_audit
import p2c_native_graph as graph


def test_disappearing_node_is_incomplete_discovery(monkeypatch):
    def gone(*args):
        raise rclpy_implementation.NodeNameNonExistentError('node vanished')
    monkeypatch.setattr(bypass_audit, 'graph_snapshot', gone)
    with pytest.raises(AssertionError, match='discovery changed') as error:
        graph.complete_native_graph(None, 2)
    assert isinstance(error.value.__cause__, rclpy_implementation.NodeNameNonExistentError)


def test_other_graph_errors_remain_visible(monkeypatch):
    def broken(*args):
        raise RuntimeError('unrelated graph error')
    monkeypatch.setattr(bypass_audit, 'graph_snapshot', broken)
    with pytest.raises(RuntimeError, match='unrelated graph error'):
        graph.complete_native_graph(None, 2)


def test_endpoint_race_in_bypass_check_is_also_incomplete(monkeypatch):
    monkeypatch.setattr(bypass_audit, 'graph_snapshot', lambda *args: {'nodes': {}})
    monkeypatch.setattr(bypass_audit, 'expected_runtime_nodes', lambda *args: set())
    monkeypatch.setattr(graph, 'native_tf_ingress_audit', lambda *args: None)
    def gone(*args):
        raise rclpy_implementation.NodeNameNonExistentError('node vanished')
    monkeypatch.setattr(bypass_audit, 'runtime_violations', gone)
    with pytest.raises(AssertionError, match='discovery changed'):
        graph.complete_native_graph(None, 2)
