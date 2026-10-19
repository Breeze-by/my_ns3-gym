"""CPU fixture checks for automatic owned-consumer timeout and real wait."""
import json
from pathlib import Path
import subprocess
import sys


asset = Path(__file__).resolve().parent
helper = asset / "bounded_read_only_child_v1.py"
for name, wall, code, expected_rc in (
    ("bounded_helper_positive_v1", 3, "print('finite fixture complete')", 0),
    ("bounded_helper_timeout_v1", 1, "import time; time.sleep(30)", 1),
):
    output = asset / "checks" / name
    result = subprocess.run([sys.executable, "-B", str(helper), "--output", str(output),
                             "--wall-seconds", str(wall), "--", sys.executable, "-B", "-c", code],
                            capture_output=True, text=True)
    assert result.returncode == expected_rc, result
    receipt = json.loads((output / "actual_wait.json").read_text())
    assert receipt["actual_waited"]
    assert receipt["timed_out"] is (expected_rc != 0)
    assert receipt["actual_returncode"] == (0 if expected_rc == 0 else -2)
    assert len(receipt["signals_sent"]) == expected_rc
    if expected_rc:
        assert receipt["signals_sent"][0]["signal"] == "SIGINT"
        assert receipt["signals_sent"][0]["monotonic_ns"] >= receipt["started_monotonic_ns"] + 10**9
    pid = receipt["child_identity"]["pid"]
    assert not Path(f"/proc/{pid}").exists(), pid
    print(name, "PASS", result.stdout.strip())
