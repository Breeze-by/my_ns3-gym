"""Bounded adapter diagnostics never turn an incomplete task into success."""

from types import SimpleNamespace

from multi_robot_exploration.task_evaluator import TaskEvaluator


def test_probe_finalize_uses_distinct_incomplete_reason():
    reasons = []
    evaluator = SimpleNamespace(finalize=reasons.append)
    response = SimpleNamespace(success=False, message="")
    result = TaskEvaluator._probe_finalize_callback(evaluator, object(), response)
    assert result is response and response.success
    assert reasons == ["adapter_probe_shutdown"]
    assert "no task success" in response.message
