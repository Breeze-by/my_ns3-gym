#!/usr/bin/python3
"""Derive V20 fees only from closed outer ns waits; keep every failed attempt."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path


def binding(path):
    raw = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}


def main():
    asset = Path(__file__).resolve().parent
    output = asset / "engineering_accounting_v1.json"
    assert not output.exists()
    closed = asset / "closed_diagnostics_v1"
    prior = asset.parent / "20261019_mr3_p2a_v19/engineering_accounting_v1.json"
    expected_prior = "2c77c344f9e8a6fe09d8b1769c56743ffb8272a7d0abd28814f1d40d4ff07b88"
    assert binding(prior)["sha256"] == expected_prior
    previous = Decimal("36483.3647801256018")
    ceiling = Decimal("52000")
    inputs = [
        (closed / "profile_v1_outer/actual_wait.json", 0),
        (closed / "profile_v2_outer/actual_wait.json", 1),
        (closed / "information_outer/actual_wait.json", -2),
    ]
    for name in ("runtime_regression_v1", "information_regression_v2"):
        inputs.append((asset / "closed_regressions" / name / "outer/actual_wait.json", 0))
    rows, intervals, identities = [], [], []

    def absent(identity, receipt_path):
        pid, ticks = identity["pid"], identity["start_ticks"]
        stat = Path(f"/proc/{pid}/stat")
        if stat.exists():
            value = stat.read_text()
            fields = value[value.rfind(")") + 2:].split()
            assert int(fields[19]) != ticks, (receipt_path, identity, "saved identity still present")
            status = "pid_reused_start_differs"
        else:
            status = "proc_stat_absent"
        identities.append({**identity, "receipt":str(receipt_path), "lookup":status})

    for path, expected_rc in inputs:
        receipt = json.loads(path.read_text())
        assert receipt["actual_waited"] and receipt["source_unchanged"]
        assert receipt["actual_returncode"] == expected_rc
        start, end = receipt["started_monotonic_ns"], receipt["ended_monotonic_ns"]
        assert type(start) is int and type(end) is int and end > start
        seconds = Decimal(end - start) / Decimal(10**9)
        assert seconds == Decimal(receipt["actual_child_wait_seconds"])
        intervals.append((start, end))
        rows.append({"receipt": binding(path), "actual_returncode": expected_rc,
                     "actual_child_wait_seconds": str(seconds), "charged_seconds": str(seconds)})
        for key in ("child_identity", "coordinator_identity"):
            absent(receipt[key], path)
    for name in ("runtime_regression_v1", "information_regression_v2"):
        path = asset/"closed_regressions"/name/"child/actual_wait.json"
        nested = json.loads(path.read_text())
        assert nested["actual_waited"] and nested["actual_returncode"] == 0
        assert nested["passed"] and not nested["timed_out"] and nested["signals_sent"] == []
        for key in ("child_identity", "coordinator_identity"):
            absent(nested[key], path)
    ordered = sorted(intervals)
    assert all(a[1] <= b[0] for a, b in zip(ordered, ordered[1:])), "outer fees overlap"
    fee = sum((Decimal(row["charged_seconds"]) for row in rows), Decimal(0))
    current = previous + fee
    result = {"schema": "mr3-v20-closed-engineering-accounting-v1", "passed": True,
              "prior_closed_accounting": binding(prior), "prior_cumulative_seconds": str(previous),
              "charged_outer_waits": rows, "new_actual_engineering_seconds": str(fee),
              "cumulative_seconds": str(current), "ceiling_seconds": str(ceiling),
              "remaining_seconds": str(ceiling - current), "outer_intervals_disjoint": True,
              "saved_outer_and_child_identities": identities,
              "saved_unique_identities_absent":len({(v["pid"], v["start_ticks"]) for v in identities}),
              "absence_scope":"five engineering outer receipts and two nested bounded-consumer receipts; generator cannot prove its own later absence",
              "charge_nested_waits_again": False, "cpu_preparation_and_packaging_charged": False,
              "original_v19_failure_retained": True, "pilot_decisions_remaining": 1870,
              "pilot_wall_seconds_remaining": "2905.9547395464029", "final_only_validations": 3,
              "scientific_qualification": False, "new_native_runs": 0, "gpu_calls": 0}
    with output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({k: result[k] for k in ("passed", "new_actual_engineering_seconds",
                                           "cumulative_seconds", "remaining_seconds")}))


if __name__ == "__main__":
    main()
