"""Launch one declared finite stage; reject retries, failed predecessors and spent budget."""
import datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path("/home/zhuyulab/ns3-workspace")
WIRELESS = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
ASSET = WIRELESS / "report/assets/20261018_mr3_p2a0_v22_ray_box"
TEMP = Path("/tmp")


def read_receipt(path):
    raw = path.read_bytes()
    return json.loads(raw), {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def launch_admission(plan, stage, freeze):
    stages = plan["stages"]
    index = next(i for i, value in enumerate(stages) if value["stage"] == stage)
    records = []
    audits = []
    elapsed = 0.0
    for i, specification in enumerate(stages):
        path = TEMP / ("mr3_p2a0_v22_" + specification["stage"] + "_launch.json")
        if i >= index:
            assert not path.exists(), "stage already attempted or later stage exists: " + str(path)
            continue
        previous, binding = read_receipt(path)
        assert previous["freeze"] == freeze and previous["stage"] == specification["stage"]
        assert previous.get("status") == "completed", "previous launch incomplete"
        assert previous.get("returncode") == 0 and previous.get("passed") is True, "prior failure"
        duration = previous["wall_duration_sec"]
        assert isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0
        assert duration <= specification["wall_ceiling_seconds"], "previous ceiling exceeded"
        elapsed += duration
        records.append({**binding, "wall_duration_sec": duration})
        # Summary is supplementary; every declared formal independent receipt is mandatory.
        summary, summary_binding = read_receipt(
            Path(specification["run_directory"]) / "benchmark_summary.json")
        assert summary.get("freeze") == freeze and summary.get("passed") is True
        audits.append(summary_binding)
        for formal in specification["required_audit_receipts"]:
            receipt, formal_binding = read_receipt(Path(formal))
            assert receipt.get("passed") is True, "formal audit missing PASS: " + formal
            if "freeze" in receipt:
                assert receipt["freeze"] == freeze, "formal audit freeze mismatch: " + formal
            audits.append(formal_binding)
    remaining = plan["max_total_wall_seconds"] - elapsed
    specification = stages[index]
    assert remaining >= specification["wall_ceiling_seconds"], "insufficient remaining wall budget"
    assert not Path(specification["run_directory"]).exists(), "run directory already exists"
    return specification, dict(
        max_total_wall_seconds=plan["max_total_wall_seconds"],
        preceding_wall_seconds=elapsed, remaining_before_stage_seconds=remaining,
        stage_wall_ceiling_seconds=specification["wall_ceiling_seconds"],
        preceding_launch_receipts=records, preceding_formal_receipts=audits,
        scope="stage duration; no timeout signal; excess fails and blocks later stages")


def write_record(path, record, mode):
    with path.open(mode) as output:
        output.write(json.dumps(record, indent=2) + "\n")


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def main():
    if "MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE" in os.environ:
        raise ValueError("production matrix forbids diagnostic physics/ray-observer configuration")
    stage, freeze = sys.argv[1:]
    assert subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip() == freeze
    assert subprocess.check_output(
        ["git", "rev-parse", "@{u}"], cwd=ROOT, text=True).strip() == freeze, "not pushed"
    assert not subprocess.check_output(
        ["git", "status", "--porcelain"], cwd=ROOT, text=True), "source not clean"
    plan_raw = (ASSET / "predeclared_plan_v22.json").read_bytes()
    plan = json.loads(plan_raw)
    assert plan['readiness']['status'] == 'ready' and not plan['readiness']['pending_bindings'], 'V22 template not finalized'
    assert plan["schema"] == "mr3-p2a0-predeclaration-v22"
    preflight, preflight_binding = read_receipt(TEMP / "mr3_p2a0_v22_source_preflight.json")
    assert preflight.get("passed") is True and preflight["freeze"] == freeze
    assert preflight["plan_sha256"] == hashlib.sha256(plan_raw).hexdigest()
    sys.path.insert(0, str(WIRELESS))
    from mr3_learning.supervisor import process_identity
    # One lock for the whole matrix prevents concurrent admission and duplicate launches.
    with (TEMP / "mr3_p2a0_v22_launch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        specification, budget = launch_admission(plan, stage, freeze)
        command = [sys.executable, "-u", *specification["command"][1:]]
        receipt = TEMP / ("mr3_p2a0_v22_" + stage + "_launch.json")
        console = TEMP / ("mr3_p2a0_v22_" + stage + "_console.log")
        started = time.monotonic()
        record = dict(
            schema="mr3-p2a0-native-launch-v2", freeze=freeze, stage=stage,
            status="reserved", command_argv=command, cwd=str(WIRELESS),
            launcher_identity=process_identity(os.getpid()), start_utc=utc_now(),
            start_monotonic=started, console=str(console), budget=budget,
            source_preflight=preflight_binding, plan_sha256=hashlib.sha256(plan_raw).hexdigest())
        write_record(receipt, record, "x")
        process = None
        try:
            with console.open("x") as output:
                process = subprocess.Popen(command, cwd=WIRELESS, stdout=output,
                                           stderr=subprocess.STDOUT)
                record.update(status="running", benchmark_parent=process_identity(process.pid),
                              benchmark_parent_pid=process.pid)
                write_record(receipt, record, "w")
                print(json.dumps(record), flush=True)
                code = process.wait()
            duration = time.monotonic() - started
            cumulative = budget["preceding_wall_seconds"] + duration
            within = (duration <= budget["stage_wall_ceiling_seconds"]
                      and cumulative <= budget["max_total_wall_seconds"])
            summary, binding = read_receipt(
                Path(specification["run_directory"]) / "benchmark_summary.json")
            benchmark_passed = (summary.get("passed") is True
                                and summary.get("freeze") == freeze)
            record.update(
                status="completed", returncode=code, wall_duration_sec=duration, end_utc=utc_now(),
                benchmark_parent_after=process_identity(process.pid),
                cumulative_wall_seconds=cumulative, within_wall_budget=within,
                benchmark_summary=binding, passed=code == 0 and within and benchmark_passed,
                pass_scope="launch/benchmark/budget; independent audits also required")
        except BaseException as error:
            # A launcher/reporting exception must not orphan the already-owned finite run.
            # Do not signal, retry, create a new epoch or rewrite a native outcome.
            cleanup = dict(scope="wait for the same owned finite benchmark; no signals/retry")
            if process is not None:
                cleanup["benchmark_parent_pid"] = process.pid
                try:
                    cleanup["returncode"] = process.wait()
                    cleanup["benchmark_parent_after"] = process_identity(process.pid)
                except BaseException as cleanup_error:
                    cleanup["wait_error"] = repr(cleanup_error)
            record.update(status="failed", passed=False, error=repr(error),
                          exception_owned_cleanup=cleanup,
                          wall_duration_sec=time.monotonic() - started, end_utc=utc_now())
            write_record(receipt, record, "w")
            raise
        write_record(receipt, record, "w")
        print(json.dumps(record), flush=True)
        return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
