"""Wall-clock bounds and process ownership for observational native probes."""
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest
import ros_smoke_test as smoke


def child_factory(monkeypatch, code):
    original = subprocess.Popen
    children = []
    def start(*args, **kwargs):
        child = original([sys.executable, "-c", code], **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(smoke.subprocess, "Popen", start)
    return children


def test_native_constructor_or_cleanup_hang_cannot_escape_wall_deadline(monkeypatch):
    children = child_factory(monkeypatch, "import time; time.sleep(60)")
    started = time.monotonic()
    with pytest.raises(TimeoutError, match="wall deadline"):
        smoke.bounded_native_probe("message", {}, .3)
    assert time.monotonic() - started < 2.
    assert len(children) == 1 and children[0].returncode == -9


def test_launch_failure_stops_only_its_native_worker(monkeypatch):
    children = child_factory(monkeypatch, "import time; time.sleep(60)")
    launch = SimpleNamespace(poll=lambda: 42, returncode=42)
    with pytest.raises(RuntimeError, match="launch exited.*42"):
        smoke.bounded_native_probe("ready", {}, 60., launch)
    assert children[0].returncode == -9


def test_native_failure_is_not_a_successful_message_check(monkeypatch):
    children = child_factory(monkeypatch, "import sys; print('no receipt'); sys.exit(7)")
    with pytest.raises(RuntimeError, match="status=7.*no receipt"):
        smoke.bounded_native_probe("message", {}, 5.)
    assert children[0].returncode == 7


def test_ready_worker_must_exit_successfully_before_returning(monkeypatch):
    children = child_factory(monkeypatch, "pass")
    smoke.bounded_native_probe("ready", {}, 5.)
    assert children[0].returncode == 0
