"""Pure saved-evidence/monitor regressions; no ROS, native, GPU or training."""

import hashlib
import json
from types import SimpleNamespace

import pytest

import audit_mr3_env_contact_phase_v2 as PHASE


ROOT = PHASE.repository_root()
AUDIT, SOURCE_PROOF = PHASE.load_auditor(ROOT)
FIXTURES = PHASE.load_module("contact_phase_original_fixtures", ROOT / PHASE.ROS /
                             "src/multi_robot_exploration/test/test_mr3_env_audit.py")
EPOCH = FIXTURES.EPOCH


def save(directory, name, value):
    (directory / name).write_text(json.dumps(value))


def save_rows(directory, name, rows):
    (directory / name).write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.fixture
def episode(tmp_path):
    FIXTURES.write_fixture(tmp_path)
    FIXTURES.add_initial_inputs_handshake(tmp_path)
    metadata = json.loads((tmp_path / "metadata.json").read_text())
    metadata.update(freeze=PHASE.FREEZE, command=[
        "ros2", "launch", "execution_mode:=adapter", "mr3_stepped:=true",
        "training_reward_enabled:=true", "enable_task_evaluator:=true", "robot_count:=3",
        "evaluation_episode_id:=" + EPOCH, "mr3_episode_epoch:=" + EPOCH])
    save(tmp_path, "metadata.json", metadata)
    samples = AUDIT.Evidence(tmp_path).rows("transitions.jsonl")
    samples[0]["info"]["scheduler"] = "mr3-physical-20ms-v1"
    save_rows(tmp_path, "transitions.jsonl", samples)
    adapter = AUDIT.Evidence(tmp_path).rows("adapter.jsonl")
    adapter.append({"kind": "task_start", "epoch": EPOCH, "stamp": 10.,
                    "payload": {"start_sim_time_sec": 10.}})
    adapter.sort(key=lambda row: (row["stamp"], row["kind"] != "task_start"))
    save_rows(tmp_path, "adapter.jsonl", adapter)
    evaluator = json.loads((tmp_path / (EPOCH + ".json")).read_text())
    evaluator.update(start_sim_time_sec=10., end_sim_time_sec=12.02,
                     task_start_barrier="controller_release",
                     contact_subscription_started_sim_time_sec=9.3,
                     contact_subscription_bootstrap_state="contact_subscriptions_started",
                     contact_clock_overflow_diagnostic=None, control_failure="")
    for components in evaluator["contact_monitor_summary"]["components"].values():
        for row in components.values():
            row.update(last_source_time_sec=12., last_receipt_time_sec=12.02)
    row = evaluator["contact_monitor_summary"]["components"]["tb1"]["base"]
    row.update(max_receipt_gap_sec=1.42, max_source_gap_sec=.447)
    save(tmp_path, EPOCH + ".json", evaluator)
    return tmp_path, evaluator


def phase_result(episode):
    directory, evaluator = episode
    return PHASE.audit_contact_phase(AUDIT, evaluator, (directory / "launch.log").read_text(),
                                     EPOCH, PHASE.release_context(AUDIT, directory))


def test_source_and_document_pins_match_the_exact_c8d_evidence_contract():
    assert len(SOURCE_PROOF) == 9
    assert PHASE.PINNED_RUNTIME[PHASE.ROS + "scripts/audit_mr3_env.py"] == (
        "25ce0b466d988595934f26a0cfb7a81a445632b1e755f2462b80698371b272e8")
    assert all(row["source"].startswith(PHASE.FREEZE + ":")
               for path, row in SOURCE_PROOF.items() if path in PHASE.PINNED_DOCUMENTS)


def test_runtime_source_tamper_is_rejected_before_audit(monkeypatch, tmp_path):
    (tmp_path / "source.py").write_text("changed")
    monkeypatch.setattr(PHASE, "PINNED_RUNTIME", {
        "source.py": hashlib.sha256(b"original").hexdigest()})
    monkeypatch.setattr(PHASE, "PINNED_DOCUMENTS", {})
    with pytest.raises(ValueError, match="runtime/source SHA mismatch"):
        PHASE.verify_sources(tmp_path)


def test_document_hash_mismatch_is_rejected(monkeypatch):
    monkeypatch.setattr(PHASE, "PINNED_RUNTIME", {})
    monkeypatch.setattr(PHASE, "PINNED_DOCUMENTS", {
        PHASE.WIRELESS + "MR3_TASK_CONTRACT.md": "bad"})
    with pytest.raises(ValueError, match="document SHA mismatch"):
        PHASE.verify_sources(ROOT)


def test_warmup_maximum_is_unchanged_diagnostic_and_original_fail_is_preserved(episode):
    directory, evaluator = episode
    before = {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    original_function = AUDIT.audit_contacts
    assert not AUDIT.audit_episode(directory)["passed"]
    result = PHASE.corrected_audit(AUDIT, [directory])
    assert result["passed"], result["errors"]
    assert AUDIT.audit_contacts is original_function
    assert not AUDIT.audit_episode(directory)["passed"]
    after = {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}
    assert before == after
    proof = result["contacts"]["contact_phase_proof"]
    assert proof["lifetime_gap_diagnostics"]["tb1/base"]["max_receipt_gap_sec"] == 1.42
    assert proof["task_gap_numeric_maxima"] is None and not proof["gap_endpoints_available"]
    assert not proof["paused_release"]["independent_raw_reward_ready_payload_available"]
    assert evaluator["contact_monitor_summary"]["components"]["tb1"]["base"][
        "max_receipt_gap_sec"] == 1.42


@pytest.mark.parametrize("case", [
    "schema", "epoch", "missing_component", "invalid", "duplicate", "current_stale",
    "age_stamp_disagree", "fresh_false", "ever_unhealthy", "latched", "wrong_limit",
    "missing_bootstrap", "zero_bootstrap", "late_bootstrap", "overflow_missing", "overflow",
    "clock_desync", "wrong_release", "missing_lifetime", "negative_lifetime", "nan_lifetime",
])
def test_task_gates_bootstrap_and_lifetime_number_validity_cannot_be_bypassed(episode, case):
    _, evaluator = episode
    summary = evaluator["contact_monitor_summary"]
    row = summary["components"]["tb1"]["base"]
    if case == "schema":
        evaluator["schema_version"] = 3
    elif case == "epoch":
        evaluator["episode_id"] = "other"
    elif case == "missing_component":
        summary["components"]["tb3"].pop("lidar")
    elif case == "invalid":
        row["invalid_timestamp_count"] = 1
    elif case == "duplicate":
        row["duplicate_message_count"] = 1
    elif case == "current_stale":
        row["receipt_age_sec"], row["last_receipt_time_sec"] = .6, 11.42
    elif case == "age_stamp_disagree":
        row["last_source_time_sec"] = 11.
    elif case == "fresh_false":
        summary["fresh"] = False
    elif case == "ever_unhealthy":
        summary["ever_unhealthy"] = True
    elif case == "latched":
        summary["latched_issues"] = {"tb1/base": "receipt_gap"}
    elif case == "wrong_limit":
        summary["max_age_sec"] = 1.
    elif case == "missing_bootstrap":
        evaluator.pop("contact_subscription_bootstrap_state")
    elif case in ("zero_bootstrap", "late_bootstrap"):
        evaluator["contact_subscription_started_sim_time_sec"] = (
            0. if case.startswith("zero") else 10.1)
    elif case == "overflow_missing":
        evaluator.pop("contact_clock_overflow_diagnostic")
    elif case == "overflow":
        evaluator["contact_clock_overflow_diagnostic"] = {"pending_count": 257}
    elif case == "clock_desync":
        evaluator["control_failure"] = "contact_clock_desynchronization"
    elif case == "wrong_release":
        evaluator["start_sim_time_sec"] = 9.9
    elif case == "missing_lifetime":
        row.pop("max_receipt_gap_sec")
    else:
        row["max_receipt_gap_sec"] = -1. if case == "negative_lifetime" else float("nan")
    assert not phase_result(episode)["passed"]


def test_raw_publication_sequence_gate_is_not_weakened(episode):
    directory, _ = episode
    path = directory / "launch.log"
    path.write_text(path.read_text().replace('"sequence_gaps": 0', '"sequence_gaps": 1', 1))
    result = phase_result(episode)
    assert not result["passed"] and not result["raw_sequence_audit_passed"]


@pytest.mark.parametrize("case", [
    "unstepped", "duplicate_parameter", "missing_seq0", "seq0_time", "snapshot_time",
    "physics_gap", "missing_task_start", "wrong_task_start", "missing_ready_handshake",
])
def test_paused_release_proof_requires_actual_causal_inputs(episode, case):
    directory, _ = episode
    if case in ("unstepped", "duplicate_parameter"):
        value = AUDIT.Evidence(directory).json("metadata.json")
        if case == "unstepped":
            value["command"] = [item.replace("mr3_stepped:=true", "mr3_stepped:=false")
                                for item in value["command"]]
        else:
            value["command"].append("mr3_stepped:=false")
        save(directory, "metadata.json", value)
    elif case in ("missing_seq0", "seq0_time", "snapshot_time", "missing_ready_handshake"):
        value = AUDIT.Evidence(directory).rows("transitions.jsonl")
        if case == "missing_seq0":
            value[0]["info"]["reward_diagnostics"]["reset_bound"] = False
        elif case == "seq0_time":
            value[0]["info"]["reward_diagnostics"]["effective_step_end"] = 10.02
        elif case == "snapshot_time":
            value[0]["snapshot"]["source_stamp"] = 10.02
        else:
            value[0]["info"].pop("initial_inputs_ready")
        save_rows(directory, "transitions.jsonl", value)
    elif case == "physics_gap":
        value = AUDIT.Evidence(directory).rows("physics.jsonl")
        value[1]["start_time_ns"] += 1000000
        save_rows(directory, "physics.jsonl", value)
    else:
        value = AUDIT.Evidence(directory).rows("adapter.jsonl")
        if case == "missing_task_start":
            value = [row for row in value if row["kind"] != "task_start"]
        else:
            next(row for row in value if row["kind"] == "task_start")["stamp"] = 10.02
        save_rows(directory, "adapter.jsonl", value)
    with pytest.raises((ValueError, KeyError)):
        PHASE.release_context(AUDIT, directory)


@pytest.mark.parametrize("crossing", [False, True])
def test_real_frozen_monitor_latches_task_or_cross_start_gap_even_after_recovery(crossing):
    module = PHASE.load_module(
        "c8d_contact_monitor_selftest", ROOT / PHASE.ROS /
        "src/multi_robot_exploration/multi_robot_exploration/mr3_contacts.py")
    monitor = module.ContactMonitor(AUDIT.ROBOTS, ("ground_plane::link::collision",))

    def update_all(stamp):
        sec = int(stamp)
        message = SimpleNamespace(header=SimpleNamespace(
            stamp=SimpleNamespace(sec=sec, nanosec=round((stamp - sec) * AUDIT.NS))), states=[])
        for robot in AUDIT.ROBOTS:
            for component in AUDIT.COMPONENTS:
                monitor.update(robot, component, message, stamp)

    update_all(.1)
    update_all(.8 if crossing else 1.)  # A large warmup maximum must stay recorded.
    monitor.start(1.)
    warmup = monitor.summary(1.)
    assert warmup["fresh"] and not warmup["ever_unhealthy"]
    assert warmup["components"]["tb1"]["base"]["max_receipt_gap_sec"] > .5
    update_all(1.4 if crossing else 1.6)
    summary = monitor.summary(1.4 if crossing else 1.6)
    assert summary["fresh"] and summary["ever_unhealthy"] and summary["latched_issues"]


def test_explicit_diagnostic_terminal_does_not_fake_contact_failure(episode):
    _, evaluator = episode
    evaluator["control_failure"] = "P1C_DIAGNOSTIC_FAILURE"
    evaluator["termination_reason"] = "navigation_failure"
    assert phase_result(episode)["passed"]


def test_fault_prefix_does_not_receive_complete_contact_credit_and_requires_freeze(episode):
    directory, _ = episode
    value = AUDIT.Evidence(directory).json("supervisor_shutdown.json")
    value.update(failed_sample=True, forced_shutdown=True, worker_returncode=-9)
    save(directory, "supervisor_shutdown.json", value)
    result = PHASE.corrected_audit(AUDIT, [directory], expected_fault=True)
    assert result["passed"] and not result["complete_episode_credit"] and "contacts" not in result
    metadata = AUDIT.Evidence(directory).json("metadata.json")
    metadata["freeze"] = "wrong"
    save(directory, "metadata.json", metadata)
    with pytest.raises(ValueError, match="including fault prefixes"):
        PHASE.corrected_audit(AUDIT, [directory], expected_fault=True)


def test_cli_adds_distinct_provenance_and_exclusive_output_without_modifying_inputs(episode):
    directory, _ = episode
    output = directory / "offline-new-result.json"
    assert PHASE.main([str(directory), "--output", str(output)]) == 0
    payload = json.loads(output.read_text())
    assert payload["schema"] == "mr3-p1c-contact-phase-audit-v2"
    assert payload["offline_contact_phase_audit"]["only_overridden_function"] == "audit_contacts"
    assert payload["offline_contact_phase_audit"]["original_results_modified"] is False
    before = output.read_bytes()
    with pytest.raises(SystemExit):
        PHASE.main([str(directory), "--output", str(output)])
    assert output.read_bytes() == before
