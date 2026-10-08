"""Auditor counterexamples on an actual isolated ROS protocol trace."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from multi_robot_exploration.traffic_audit import audit_protocol, audit_traffic


def records():
    return json.loads((Path(__file__).parent/"fixtures/p3c5_ros_protocol.json").read_text())


def test_real_ros_control_bytes_and_all_cost_coefficients_reconcile():
    audit, costs = audit_traffic(records(), 10, 11.5, True)
    assert audit["protocol"]["released"] == 1
    assert audit["protocol"]["discarded"] == 0
    assert {"candidate", "request", "grant", "heartbeat", "data"} <= set(audit["tx_cdr_bytes_by_role"])
    assert sum(c["envelope_cdr_bytes"] for c in costs) == audit["total_tx_cdr_bytes"]
    assert all(c["actual_airtime_sec"] is None and c["actual_radio_energy_j"] is None for c in costs)
    assert sum(c["serialization_sec_per_mbps"] for c in costs) == pytest.approx(audit["physical_accounting"]["serialization_sec_per_mbps"])
    original = {e["message_id"]: e for e in records() if e["event"] == "generated"}
    for cost in costs:
        message = original[cost["message_id"]]
        assert cost["source_time"] == message["source_time"]
        assert cost["deadline"] == message["deadline"]
        assert cost["deadline"] == pytest.approx(cost["source_time"]+cost["ttl_sec"])


@pytest.mark.parametrize("mutation", ["hidden_queue", "undelivered_request", "bytes", "renewed_source", "no_release", "double_release", "missing_closure"])
def test_auditor_rejects_observability_and_admission_tampering(mutation):
    events = records()
    if mutation == "hidden_queue":
        next(e for e in events if e["event"] == "admission_observation")["observation"]["remote_current_queue"] = 0
    elif mutation == "undelivered_request":
        next(e for e in events if e["event"] == "admission_decision")["request_wire_id"] = "never_delivered"
    elif mutation == "bytes":
        next(e for e in events if e["event"] == "generated" and e["message_type"] == "candidate")["control_payload"]["payload_length"] += 1
    elif mutation == "renewed_source":
        next(e for e in events if e["event"] == "enqueue" and e["message_type"] == "pose_state")["source_time"] += 1
    elif mutation == "no_release":
        events = [e for e in events if e["event"] != "admission_release"]
    elif mutation == "double_release":
        index = next(i for i,e in enumerate(events) if e["event"] == "admission_release")
        events.insert(index+1, deepcopy(events[index]))
    elif mutation == "missing_closure":
        events = [e for e in events if e["event"] not in ("admission_release", "enqueue") or e.get("message_type") != "pose_state"]
        events = [e for e in events if e["event"] != "admission_release"]
    with pytest.raises((AssertionError, KeyError)):
        audit_protocol(events, True)


@pytest.mark.parametrize("mutation", ["candidate_source", "candidate_type", "candidate_phase",
                                     "request_sender", "heartbeat_age", "history_source",
                                     "extra_hidden_payload", "grant_version", "grant_size",
                                     "grant_recipient", "missing_decision", "retry_ordinal"])
def test_auditor_binds_delivered_content_and_exact_grant_fields(mutation):
    events = records()
    if mutation.startswith("candidate_"):
        if mutation == "candidate_source":
            item = next(e for e in events if e["event"] == "admission_observation"
                        and e["observation"]["received_candidates"])["observation"]["received_candidates"][0]
            item["source_time"] -= 1
        else:
            item = next(e for e in events if e["event"] == "generated"
                        and e["message_type"] == "candidate")["control_payload"]
            item["message_type" if mutation == "candidate_type" else "task_phase"] = "invented"
    elif mutation == "request_sender":
        next(e for e in events if e["event"] == "admission_observation"
             and e["observation"]["received_requests"])["observation"]["received_requests"][0]["sender"] = "tb2"
    elif mutation == "heartbeat_age":
        next(e for e in events if e["event"] == "admission_observation"
             and e["observation"]["heartbeats"])["observation"]["heartbeats"]["tb1"]["age_sec"] += 1
    elif mutation == "history_source":
        next(e for e in events if e["event"] == "admission_observation"
             and e["observation"]["delivered_history"])["observation"]["delivered_history"][0]["source_time"] -= 1
    elif mutation == "extra_hidden_payload":
        next(e for e in events if e["event"] == "admission_observation")["observation"]["hidden_payload"] = [1, 2, 3]
    elif mutation.startswith("grant_"):
        grant = next(e for e in events if e["event"] == "generated" and e["message_type"] == "grant")
        if mutation == "grant_recipient":
            grant["recipient"] = "tb2"
        else:
            grant["control_payload"]["version" if mutation == "grant_version" else "payload_length"] += 1
    elif mutation == "missing_decision":
        events = [e for e in events if e["event"] != "admission_decision"]
    elif mutation == "retry_ordinal":
        next(e for e in events if e["event"] == "generated" and e["message_type"] == "candidate")["control_attempt"] = 2
    with pytest.raises((AssertionError, KeyError)):
        audit_protocol(events, True)


def test_stopped_metrics_context_keeps_json_csv_sample_without_publishing():
    import io
    from types import SimpleNamespace
    from multi_robot_exploration.gateway_metrics import LedgerMetrics
    from multi_robot_exploration.metrics_node import MetricsNode

    engine = LedgerMetrics({"episode_start_sim_time": 10.0})
    for event in records():
        engine.ingest(event)
    node = SimpleNamespace(metrics=engine, read_ledger=lambda: None, inputs=True, last_sample=-1,
        history=[], samples=[], robots={}, latest_phase="EXPLORE", directory=Path("/tmp/p3c5_component"),
        saved_samples=io.StringIO(), csv_stream=io.StringIO(), csv_writer=None, task_result=lambda: None,
        context=SimpleNamespace(ok=lambda: False),
        publisher=SimpleNamespace(publish=lambda _: (_ for _ in ()).throw(AssertionError("stopped context"))))
    MetricsNode.poll(node)
    snapshot = json.loads(node.saved_samples.getvalue())
    assert snapshot["ledger_record_count"] == len(records())
    assert node.csv_stream.getvalue() and node.samples
