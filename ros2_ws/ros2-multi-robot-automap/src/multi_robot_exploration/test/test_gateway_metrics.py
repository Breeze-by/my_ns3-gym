from dataclasses import replace
from types import SimpleNamespace

import pytest

from multi_robot_exploration.fault_model import DeterministicFaultTransport, FaultConfig
from multi_robot_exploration.gateway_config import FAULT_DEFAULTS, updated_configuration
from multi_robot_exploration.gateway_metrics import LedgerMetrics, distribution, freshness, age_summary, task_degradation_index


def packet(sequence=1, kind="pose_state"):
    return SimpleNamespace(message_type=kind, sender="tb1", recipient="headquarters",
                           sequence=sequence, correlation_id=0, payload_length=100)


def collect(config, entries, end, accept=False):
    metrics = LedgerMetrics()
    transport = DeterministicFaultTransport(config, metrics.ingest)
    for identity, source, ttl, reliable in entries:
        transport.enqueue(identity, packet(len(metrics.messages)+1), "uplink", source, reliable,
                          source_time=source, ttl_sec=ttl)
    transport.poll(end)
    if accept:
        for event in list(metrics.events):
            if event["event"] == "delivered" and not event.get("duplicate"):
                metrics.ingest({**event, "event": "accepted"})
    return metrics


def test_attempts_retries_and_logical_bytes_are_distinct_and_conserved():
    metrics = collect(FaultConfig(loss_rate=1, max_retries=2, ack_timeout_sec=.25), [("m", 0, 2, True)], 1)
    report = metrics.report(0, 1.001, "uplink")
    assert report["counts"]["generated_bytes"] == 100
    assert report["counts"]["attempted_bytes"] == 300
    assert report["counts"]["retry_attempts"] == 2
    assert report["attempt_pdr"] == 0
    assert report["retry_rate"] == pytest.approx(2/3)
    assert report["counts"]["ledger_terminal_without_delivery_messages"] == 1
    assert metrics.audit()["status"] == "PASS"


def test_duplicates_do_not_inflate_pdr_goodput_or_primary_attempts():
    metrics = collect(FaultConfig(duplicate_rate=1), [("m", 0, 2, False)], .1, accept=True)
    report = metrics.report(0, 1, "uplink")
    assert report["counts"]["duplicate_copies"] == 1
    assert report["counts"]["delivered_attempts"] == 1
    assert report["goodput_bytes_per_sec"] == 100
    assert report["logical_pdr"] == 1
    assert metrics.audit()["status"] == "PASS"


def test_queue_rejection_and_transmitted_ttl_expiry_reconcile_separately():
    overflow = collect(FaultConfig(queue_capacity=1, delay_sec=1), [("a", 0, 2, False), ("b", 0, 2, False)], 1.1)
    c = overflow.report(0, 2)["counts"]
    assert c["generated_messages"] == 2 and c["admitted_messages"] == 1
    assert c["queue_overflow_attempts"] == 1 and c["ledger_never_admitted_messages"] == 1
    assert overflow.audit()["status"] == "PASS"
    expired = collect(FaultConfig(delay_sec=3), [("a", 0, 2, False)], 3.1)
    c = expired.report(0, 4)["counts"]
    assert c["ttl_expired_attempts"] == 1 and c["dropped_tx_attempts"] == 1
    assert c["ledger_terminal_without_delivery_messages"] == 1
    assert expired.audit()["status"] == "PASS"


def test_missing_delivery_is_unknown_aoi_and_not_fresh():
    metrics = collect(FaultConfig(loss_rate=1), [("a", 0, 2, False)], 3)
    row = metrics.report(0, 3)
    assert row["aoi"]["mean"] is None
    assert row["aoi"]["p95"] is None
    assert row["aoi"]["no_data_sec"] == 3
    assert row["aoi"]["fresh_ratio"] == 0


def test_aoi_integrates_source_age_and_never_rolls_back_old_versions():
    part = freshness([(0, 0, 2), (2.5, 2, 2), (3, 1, 2)], 0, 4, 0)
    row = age_summary([part])
    assert row["mean"] == pytest.approx(1.25)
    assert row["max"] == 2.5
    assert row["p95"] == pytest.approx(2.3, abs=1e-6)
    assert row["fresh_ratio"] == .875
    assert row["first_source_stale_time"] == 2
    assert row["first_freshness_recovery_time"] == 2.5
    assert row["recovery_count"] == 1
    assert row["recovery_time_mean_sec"] == .5


def test_freshness_recovery_includes_unknown_prefix_and_retains_unresolved_tail():
    row = age_summary([freshness([(3, 3, 2)], 0, 8, 0)])
    assert row["no_data_sec"] == 3
    assert row["first_no_data_time"] == 0
    assert row["first_source_stale_time"] == 5
    assert row["first_freshness_recovery_time"] == 3
    assert row["recovery_time_max_sec"] == 3
    assert row["unrecovered_stale_sec"] == 3


def test_tdi_excludes_process_modes_and_uses_frozen_required_robot_count():
    ideal = {"mission_mode": "rally", "success": True, "task_phase": "COMPLETE", "robot_count": 3}
    partial = {"partial_completion": True, "required_robot_count": 2}
    assert task_degradation_index(ideal, partial) == pytest.approx(1/3)
    assert task_degradation_index({**ideal, "mission_mode": "target"}, partial) is None
    assert task_degradation_index({**ideal, "success": False}, partial) is None


def test_insufficient_quantile_samples_remain_null():
    assert distribution([1])["p50"] is None
    assert distribution(list(range(19)))["p95"] is None
    assert distribution(list(range(20)))["p95"] is not None
    assert distribution(list(range(99)))["p99"] is None


def test_pending_attempts_are_explicit_and_corrupted_stages_fail_audit():
    metrics = collect(FaultConfig(delay_sec=10), [("a", 0, 20, False)], 1)
    audit = metrics.audit()
    assert audit["status"] == "PASS" and audit["streams"][0]["in_flight_attempts"] == 1
    metrics.events = [e for e in metrics.events if e["event"] != "admitted"]
    for message in metrics.messages.values():
        message["events"] = [e for e in message["events"] if e["event"] != "admitted"]
    assert metrics.audit()["status"] == "FAIL"


@pytest.mark.parametrize("changes", [
    {"uplink_loss_rate": float("nan")}, {"uplink_loss_rate": 1.1}, {"downlink_delay_sec": -1},
    {"queue_capacity": -1}, {"max_retries": True}, {"reorder_window": 1.5},
    {"blackout_intervals": "[[3,2]]"}, {"blackout_intervals": "[false]"},
    {"navigation_command_deadline_sec": 1000}, {"fault_seed": 2}, {"use_sim_time": False},
])
def test_config_rejection_is_atomic_and_does_not_mutate_current(changes):
    original = dict(FAULT_DEFAULTS)
    with pytest.raises((ValueError, TypeError)):
        updated_configuration(original, changes)
    assert original == FAULT_DEFAULTS


def test_reconfiguration_does_not_retroactively_change_queued_delivery():
    events = []
    original = FaultConfig(delay_sec=2, loss_rate=0, queue_capacity=2)
    transport = DeterministicFaultTransport(original, events.append)
    transport.enqueue("old", packet(), "uplink", 0, source_time=0, ttl_sec=10)
    transport.reconfigure(replace(original, loss_rate=1, delay_sec=.5, queue_capacity=1), 1)
    # Capacity shrinks without deleting old in-flight data.
    transport.enqueue("new", packet(2), "uplink", .1, source_time=.1, ttl_sec=10)
    assert any(e.get("reason") == "queue_overflow" for e in events)
    assert [attempt.message_id for attempt in transport.poll(2.1)] == ["old"]
    transport.enqueue("new2", packet(3), "uplink", 3, source_time=3, ttl_sec=10)
    assert transport.poll(3.5) == []
    assert events[-1]["reason"] == "loss" and events[-1]["fault_revision"] == 1


def test_runtime_retries_use_new_configuration_without_changing_old_attempt():
    events = []
    config = FaultConfig(loss_rate=1, ack_timeout_sec=1, max_retries=2)
    transport = DeterministicFaultTransport(config, events.append)
    transport.enqueue("m", packet(kind="target_detection"), "uplink", 0, True, source_time=0, ttl_sec=10)
    transport.poll(0)
    transport.reconfigure(replace(config, loss_rate=0), 1)
    deliveries = transport.poll(1)
    assert len(deliveries) == 1 and deliveries[0].attempt == 2
    assert transport.acknowledge("m", 1)
    assert transport.poll(4) == []
