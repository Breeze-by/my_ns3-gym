"""Dummy callables only: no world, episode, IPC, learner or formal profile."""

import os
from pathlib import Path
import pstats
import subprocess
import sys

import pytest

from multi_robot_exploration.mr3_proxy2d_profile import run_profiled


def parse_profile(output):
    stats = pstats.Stats(str(output))
    assert stats.total_calls > 0
    assert any(name == "operation" for _, _, name in stats.stats)


@pytest.mark.parametrize("value", [None, 0, 9, object()])
def test_return_identity_and_exclusive_claim_before_call(tmp_path, value):
    output = tmp_path / "dummy.prof"
    calls = []

    def operation():
        assert output.exists() and output.stat().st_size == 0
        calls.append(1)
        return value

    assert run_profiled(operation, output) is value
    assert calls == [1]
    parse_profile(output)


@pytest.mark.parametrize("error", [SystemExit(0), SystemExit(9), RuntimeError("dummy failure")])
def test_exception_identity_is_propagated_and_profile_is_saved(tmp_path, error):
    output = tmp_path / "dummy.prof"

    def operation():
        raise error

    with pytest.raises(type(error)) as raised:
        run_profiled(operation, output)
    assert raised.value is error
    parse_profile(output)


def test_existing_output_is_unchanged_and_callable_is_not_run(tmp_path):
    output = tmp_path / "dummy.prof"
    raw = b"previous profile bytes"
    output.write_bytes(raw)
    calls = []
    with pytest.raises(FileExistsError):
        run_profiled(lambda: calls.append(1), output)
    assert calls == [] and output.read_bytes() == raw


@pytest.mark.parametrize("behavior,expected", [("return None", 0), ("return 9", 9),
    ("raise SystemExit(7)", 7), ("raise RuntimeError('dummy failure')", 1)])
def test_real_entry_point_exit_status_is_preserved(tmp_path, behavior, expected):
    output = tmp_path / "child.prof"
    script = ("import sys\nfrom pathlib import Path\n"
        "from multi_robot_exploration.mr3_proxy2d_profile import run_profiled\n"
        "def operation():\n    " + behavior + "\n"
        "sys.exit(run_profiled(operation, Path(sys.argv[1])) or 0)\n")
    environment = os.environ.copy()
    environment.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
    result = subprocess.run([sys.executable, "-B", "-c", script, str(output)],
        env=environment, capture_output=True, text=True, timeout=10.)
    assert result.returncode == expected
    assert result.stdout == ""
    if expected == 1:
        assert "RuntimeError: dummy failure" in result.stderr
    else:
        assert result.stderr == ""
    parse_profile(output)
