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
ASSET = WIRELESS / "report/assets/20261018_mr3_p2a0_v26_capture"
TEMP = Path("/tmp")
LEARNER_PYTHON = Path('/home/zhuyulab/miniconda3/envs/ns3gym/bin/python')
PRIOR_ENGINEERING_WALL_SECONDS = 1369.6459453934804


def read_receipt(path):
    raw = path.read_bytes()
    return json.loads(raw), {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def launch_admission(plan, stage, freeze):
    stages = plan["stages"]
    index = next(i for i, value in enumerate(stages) if value["stage"] == stage)
    records = []
    audits = []
    assert plan["prior_engineering_cost"]["wall_seconds"] == PRIOR_ENGINEERING_WALL_SECONDS
    elapsed = PRIOR_ENGINEERING_WALL_SECONDS
    for i, specification in enumerate(stages):
        path = TEMP / ("mr3_p2a0_v26_" + specification["stage"] + "_launch.json")
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
        preceding_wall_seconds=elapsed, prior_engineering_wall_seconds=PRIOR_ENGINEERING_WALL_SECONDS,
        remaining_before_stage_seconds=remaining,
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
    plan_raw = (ASSET / "predeclared_plan_v26.json").read_bytes()
    plan = json.loads(plan_raw)
    assert plan['readiness']['status'] == 'ready' and not plan['readiness']['pending_bindings'], 'V26 template not finalized'
    assert plan["schema"] == "mr3-p2a0-predeclaration-v26"
    preflight, preflight_binding = read_receipt(TEMP / "mr3_p2a0_v26_source_preflight.json")
    assert preflight.get("passed") is True and preflight["freeze"] == freeze
    assert preflight["plan_sha256"] == hashlib.sha256(plan_raw).hexdigest()
    worker_helper = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v25_smoother/independent/mr3_v25_stage_worker_bindings_v1.py'
    worker_raw = worker_helper.read_bytes()
    worker_expected = '3b685448644d5e1ad50adf3f551107120e13c692865a4e7f6bc0facd2c844e70'
    worker_pins = {row['path']: row['sha256'] for row in plan['independent_source_bindings']}
    if (hashlib.sha256(worker_raw).hexdigest() != worker_expected
            or worker_pins.get(str(worker_helper.relative_to(ROOT))) != worker_expected):
        raise ValueError('immutable A25 worker helper source/plan SHA differs')
    worker_namespace = {}
    exec(compile(worker_raw, str(worker_helper), 'exec'), worker_namespace)
    validate_worker_bindings = worker_namespace['validate_worker_bindings']
    for specification in plan["stages"]:
        validate_worker_bindings(specification)
    sys.path.insert(0, str(WIRELESS))
    from mr3_learning.supervisor import process_identity
    # One lock for the whole matrix prevents concurrent admission and duplicate launches.
    with (TEMP / "mr3_p2a0_v26_launch.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        specification, budget = launch_admission(plan, stage, freeze)
        assert specification["command"][0] == str(LEARNER_PYTHON), "unbound learner interpreter"
        command = [str(LEARNER_PYTHON), "-u", *specification["command"][1:]]
        receipt = TEMP / ("mr3_p2a0_v26_" + stage + "_launch.json")
        console = TEMP / ("mr3_p2a0_v26_" + stage + "_console.log")
        started = time.monotonic()
        record = dict(
            schema="mr3-p2a0-native-launch-v2", freeze=freeze, stage=stage,
            status="reserved", command_argv=command, cwd=str(WIRELESS),
            launcher_identity=process_identity(os.getpid()), start_utc=utc_now(),
            start_monotonic=started, console=str(console), budget=budget,
            source_preflight=preflight_binding, plan_sha256=hashlib.sha256(plan_raw).hexdigest(),
            worker_bindings=specification["worker_bindings"])
        write_record(receipt, record, "x")
        process = None
        code = None
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
                    code = process.wait()
                    cleanup["returncode"] = code
                    cleanup["benchmark_parent_after"] = process_identity(process.pid)
                except BaseException as cleanup_error:
                    cleanup["wait_error"] = repr(cleanup_error)
            record.update(status="failed", passed=False, returncode=code, error=repr(error),
                          primary_failure=("benchmark_returncode_nonzero" if code not in (None, 0)
                                           else "launcher_exception"),
                          exception_owned_cleanup=cleanup,
                          wall_duration_sec=time.monotonic() - started, end_utc=utc_now())
            write_record(receipt, record, "w")
            raise
        write_record(receipt, record, "w")
        print(json.dumps(record), flush=True)
        return 0 if record["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
