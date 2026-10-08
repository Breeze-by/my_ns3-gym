"""Read-only P3C.5 payload, protocol, observability and conditional-cost audit."""
from collections import Counter, defaultdict
import bisect
import math

from .admission_protocol import (
    CONTROL_TYPES, ORDINARY_TYPES, MAX_CONTROL_ATTEMPTS, CONTROL_RETRY_SEC, GRANT_LEASE_SEC,
)
from .gateway_metrics import LedgerMetrics, event_stamp


def distribution(values):
    values = sorted(values)
    if not values:
        return {"n": 0, "min": None, "p50": None, "p95": None, "p99": None, "max": None}
    def percentile(p):
        return values[min(len(values)-1, math.ceil(p*len(values))-1)]
    return {"n": len(values), "min": values[0], "p50": percentile(.5),
            "p95": percentile(.95), "p99": percentile(.99), "max": values[-1]}


def audit_protocol(records, enabled):
    """Verify the actual received-information boundary and every local candidate."""
    generated, received, accepted, queued, released, discarded = {}, {}, {}, {}, {}, {}
    decisions, observations = 0, 0
    grants, control_attempts = {}, {}
    for e in records:
        kind, identity = e["event"], e.get("message_id")
        if kind == "generated":
            assert identity not in generated, "logical message generated twice"
            generated[identity] = e
        if kind == "control_received":
            assert identity in generated, "control receipt without original generation"
            received[identity] = e
        if kind == "accepted":
            accepted[identity] = e
        if kind == "local_queue_enter":
            assert e["candidate_id"] not in queued, "local candidate queued twice"
            queued[e["candidate_id"]] = e
        if kind == "local_discard":
            assert e["candidate_id"] in queued and e["candidate_id"] not in released
            assert e["candidate_id"] not in discarded
            discarded[e["candidate_id"]] = e
        if kind == "admission_decision":
            candidate, request = (received[e[name]] for name in ("candidate_wire_id", "request_wire_id"))
            assert candidate["message_type"] == "candidate" and request["message_type"] == "request"
            assert max(candidate["ledger_index"], request["ledger_index"]) < e["ledger_index"]
            assert max(event_stamp(candidate), event_stamp(request)) <= e["decision_time"]+1e-8
            summary = generated[e["candidate_wire_id"]]["control_payload"]
            assert summary["message_id"] == generated[e["request_wire_id"]]["control_payload"]["candidate_id"] == e["candidate_id"]
            original = generated[e["candidate_id"]]
            for field in ("message_type", "sender", "recipient", "version", "payload_length", "task_phase"):
                assert summary[field] == original[field], f"candidate changed {field}"
            for wire in (candidate, request):
                assert wire["sender"] == original["sender"] and wire["recipient"] == original["recipient"]
                assert wire["direction"] == "uplink"
            assert abs(summary["source_time"]-original["source_time"]) < 1e-8
            assert abs(summary["deadline"]-original["deadline"]) < 1e-8
            assert e["decision_time"] < summary["deadline"]
            grant_wire = generated[e["grant_wire_id"]]
            assert grant_wire["message_type"] == "grant" and grant_wire["direction"] == "downlink"
            assert grant_wire["sender"] == "headquarters" and grant_wire["recipient"] == original["sender"]
            grant = grant_wire["control_payload"]
            assert set(grant) == {"candidate_id", "version", "payload_length", "deadline", "expires"}
            assert grant["candidate_id"] == e["candidate_id"] and grant["deadline"] == summary["deadline"]
            for field in ("version", "payload_length"):
                assert type(grant[field]) is int and grant[field] == summary[field], f"grant changed {field}"
            assert e["decision_time"] < grant["expires"] <= min(e["decision_time"]+GRANT_LEASE_SEC, summary["deadline"])+1e-8
            assert e["grant_wire_id"] not in grants, "grant decision recorded twice"
            grants[e["grant_wire_id"]] = e
            decisions += 1
        if kind == "admission_release":
            identity = e["candidate_id"]
            assert identity in queued and identity not in released and identity not in discarded
            grant_receipt = received[e["grant_wire_id"]]
            grant = generated[e["grant_wire_id"]]["control_payload"]
            assert e["grant_wire_id"] in grants, "release without a bound AP decision"
            assert grants[e["grant_wire_id"]]["ledger_index"] < grant_receipt["ledger_index"]
            assert grant_receipt["ledger_index"] < e["ledger_index"]
            assert grant["candidate_id"] == identity and event_stamp(e) < grant["expires"]
            assert abs(e["local_wait_sec"]-max(0, event_stamp(e)-event_stamp(queued[identity]))) < 1e-6
            released[identity] = e
        if kind == "enqueue" and e.get("direction") == "uplink" and e.get("message_type") in ORDINARY_TYPES and enabled:
            assert identity in released, "ordinary payload transmitted without delivered grant"
            assert released[identity]["ledger_index"] < e["ledger_index"]
            assert e["source_time"] == generated[identity]["source_time"], "admission renewed source TTL"
        if kind == "admission_observation":
            observation = e["observation"]
            fields = {"policy", "remote_current_queue", "queue_information", "heartbeats",
                      "received_candidates", "received_requests", "delivered_history"}
            assert fields <= set(observation) <= fields | {"ap_local_downlink_pending_count"}
            assert observation.get("ap_local_downlink_pending_count", 0) == 0
            assert observation["remote_current_queue"] is None
            for item in observation["received_candidates"]+observation["received_requests"]+list(observation["heartbeats"].values()):
                receipt = received[item["wire_id"]]
                assert receipt["ledger_index"] < e["ledger_index"]
                assert item["wire_id"] in accepted and accepted[item["wire_id"]]["ledger_index"] < e["ledger_index"]
                assert item["delivery_time"] <= event_stamp(e)+1e-8
                assert abs(item["delivery_time"]-event_stamp(receipt)) < 1e-8
            for item in observation["received_candidates"]:
                wire = generated[item["wire_id"]]
                assert wire["message_type"] == "candidate"
                assert item == {**wire["control_payload"], "wire_id": item["wire_id"],
                                "delivery_time": item["delivery_time"]}, "AP candidate differs from delivered content"
            for item in observation["received_requests"]:
                wire = generated[item["wire_id"]]
                assert wire["message_type"] == "request"
                assert item == {**wire["control_payload"], "sender": wire["sender"], "wire_id": item["wire_id"],
                                "delivery_time": item["delivery_time"]}, "AP request differs from delivered content"
            for sender, item in observation["heartbeats"].items():
                wire = generated[item["wire_id"]]
                assert wire["message_type"] == "heartbeat"
                assert set(item) == {"reported_pending_count", "source_time", "delivery_time", "wire_id", "age_sec", "stale"}
                assert wire["sender"] == sender and item["reported_pending_count"] == wire["control_payload"]["pending_count"]
                assert item["source_time"] == wire["source_time"]
                assert abs(item["age_sec"]-max(0, event_stamp(e)-item["source_time"])) < 1e-8
                assert item["stale"] == (event_stamp(e)-item["source_time"] >= 2)
            for item in observation["delivered_history"]:
                assert item["message_id"] in accepted
                receipt = accepted[item["message_id"]]
                assert receipt["ledger_index"] < e["ledger_index"]
                assert item == {"message_id": item["message_id"], "source_time": receipt["source_time"],
                                "delivery_time": event_stamp(receipt)}, "AP history differs from accepted information"
            observations += 1
        if kind == "generated" and e.get("message_type") in ("candidate", "request"):
            assert 1 <= e["control_attempt"] <= MAX_CONTROL_ATTEMPTS
            original = generated[e["candidate_id"]]
            assert e["source_time"]+e["ttl_sec"] <= original["deadline"]+1e-5, "control retry renewed data deadline"
            key = (e["candidate_id"], e["message_type"])
            previous = control_attempts.get(key)
            assert e["control_attempt"] == (previous["control_attempt"]+1 if previous else 1)
            if previous:
                assert e["source_time"]-previous["source_time"] >= CONTROL_RETRY_SEC-1e-8, "control retry too early"
            control_attempts[key] = e
    assert set(queued) == set(released) | set(discarded), "local queue does not reconcile at episode closure"
    if enabled:
        assert decisions > 0 and observations > 0 and queued
    else:
        assert not queued and not decisions and not observations
    return {"status": "PASS", "scope": "full raw ledger, including startup and closure",
            "local_generated": len(queued), "released": len(released),
            "discarded": len(discarded), "discard_reasons": dict(Counter(e["reason"] for e in discarded.values())),
            "ap_decisions": decisions, "observation_samples": observations,
            "remote_current_queue_unknown": True, "all_decisions_bound_to_received_controls": True,
            "local_wait_sec": distribution([e["local_wait_sec"] for e in released.values()])}


def audit_traffic(records, start, end, enabled):
    engine = LedgerMetrics()
    for e in records:
        engine.ingest(e)
    conservation = engine.audit()
    assert conservation["status"] == "PASS", conservation["errors"]
    protocol = audit_protocol(records, enabled)
    phase_changes = [(start, "EXPLORE")]
    for e in records:
        if e["event"] == "generated" and e.get("message_type") == "task_state" and start <= event_stamp(e) <= end:
            phase_changes.append((event_stamp(e), e["task_phase"]))
    phase_changes.sort(key=lambda item: item[0])  # Preserve ledger order for simultaneous phases.
    timeline = []
    for stamp, phase in phase_changes:
        if not timeline or phase != timeline[-1][1]:
            timeline.append((stamp, phase))
    phase_times = [item[0] for item in timeline]
    durations = Counter()
    for i, (stamp, phase) in enumerate(timeline):
        durations[phase] += max(0, (timeline[i+1][0] if i+1 < len(timeline) else end)-stamp)
    def phase_at(t):
        return timeline[max(0, bisect.bisect_right(phase_times, t)-1)][1]
    info, groups, bursts = {}, {}, Counter()
    samples = defaultdict(list)
    queues = defaultdict(list)
    costs = []
    def group(event, phase):
        robot = event.get("application_robot") or (event.get("sender") if event.get("direction") == "uplink" else event.get("recipient"))
        key = (phase, event["message_type"], event["direction"], robot)
        if key not in groups:
            groups[key] = Counter()
        return key, groups[key]
    for e in records:
        identity, kind, stamp = e.get("message_id"), e["event"], event_stamp(e)
        if identity and kind in ("generated", "enqueue") and identity not in info:
            assert "envelope_cdr_bytes" in e and "uncompressed_payload_length" in e, "missing byte measurement"
            info[identity] = e
        if not start <= stamp < end:
            continue
        phase = phase_at(stamp)
        if kind == "metrics_tick":
            for direction, item in e["queues"].items():
                for metric in ("in_flight", "pending_reliable_or_unresolved", "scheduled_events"):
                    queues[(phase, direction, metric)].append(item[metric])
        if kind == "local_queue_audit":
            for robot, depth in e["pending"].items():
                queues[(phase, robot, "local_pending")].append(depth)
        if not identity or identity not in info:
            if kind == "local_discard":
                key, counts = group(e, phase)
                counts["local_discarded_messages"] += 1
            if kind == "admission_release":
                key, _ = group(e, phase)
                samples[(key, "local_wait_sec")].append(e["local_wait_sec"])
            continue
        meta = info[identity]
        key, counts = group(meta, phase)
        size, wire = int(meta["payload_length"]), int(meta["envelope_cdr_bytes"])
        if kind == "generated" or (kind == "enqueue" and meta["event"] == "enqueue"):
            counts["generated_messages"] += 1
            counts["generated_payload_bytes"] += size
            counts["generated_envelope_cdr_bytes"] += wire
            counts["uncompressed_payload_bytes"] += meta["uncompressed_payload_length"]
            counts["control_retry_messages"] += int(meta.get("control_attempt", 1) > 1)
            bursts[(int(stamp-start), meta["direction"], meta["message_type"])] += 1
            samples[(key, "payload_bytes")].append(size)
            samples[(key, "envelope_cdr_bytes")].append(wire)
            samples[(key, "ttl_sec")].append(meta["ttl_sec"])
        if kind == "tx":
            counts["tx_attempts"] += 1
            counts["tx_payload_bytes"] += size
            counts["tx_envelope_cdr_bytes"] += wire
            counts["transport_retry_attempts"] += int(e["attempt"] > 1)
            samples[(key, "transport_queue_wait_sec")].append(max(0, e["tx_time"]-e["enqueue_time"]))
            costs.append({"message_id": identity, "attempt": e["attempt"], "sim_time": stamp,
                "ledger_index": e["ledger_index"], "source_time": meta["source_time"],
                "version": meta["version"], "ttl_sec": meta["ttl_sec"], "deadline": meta["deadline"],
                "enqueue_time": e["enqueue_time"], "tx_time": e["tx_time"],
                "candidate_id": meta.get("candidate_id"), "control_attempt": meta.get("control_attempt"),
                "phase": phase, "message_type": meta["message_type"], "direction": meta["direction"],
                "robot": key[3], "control_role": meta["control_role"], "payload_bytes": size,
                "envelope_cdr_bytes": wire, "serialization_sec_per_mbps": wire*8/1e6,
                "tx_energy_j_per_watt_per_mbps": wire*8/1e6, "actual_airtime_sec": None,
                "actual_radio_energy_j": None})
        if kind == "delivered" and not e.get("duplicate"):
            counts["delivered_attempts"] += 1
            counts["delivered_payload_bytes"] += size
            samples[(key, "source_to_delivery_sec")].append(e["delivery_time"]-e["source_time"])
            samples[(key, "transport_delay_sec")].append(e["delivery_time"]-e["tx_time"])
        if kind == "drop":
            counts["drop_attempts"] += 1
            counts["expired_attempts"] += int("expired" in e.get("reason", ""))
            counts["queue_overflow_attempts"] += int(e.get("reason") == "queue_overflow")
        if kind == "accepted":
            counts["accepted_messages"] += 1
            counts["accepted_payload_bytes"] += size
        if kind == "expired":
            counts["receiver_expired_messages"] += 1
    rows = []
    for key, counts in sorted(groups.items()):
        phase, message_type, direction, robot = key
        duration = durations[phase]
        rows.append({"phase": phase, "message_type": message_type, "direction": direction, "robot": robot,
            "phase_duration_sec": duration, "counts": dict(counts),
            "generated_hz": counts["generated_messages"]/duration if duration else None,
            "offered_payload_bps": counts["generated_payload_bytes"]*8/duration if duration else None,
            "tx_envelope_cdr_bps": counts["tx_envelope_cdr_bytes"]*8/duration if duration else None,
            "compression_payload_fraction": counts["generated_payload_bytes"]/counts["uncompressed_payload_bytes"]
                if counts["uncompressed_payload_bytes"] else None,
            "distributions": {name: distribution(values) for (selected, name), values in samples.items() if selected == key}})
    aoi, phase_aoi = [], []
    for key in sorted(engine.routes):
        report = engine.report(start, end, *key)
        aoi.append({"direction": key[0], "message_type": key[1], "sender": key[2], "recipient": key[3],
                    "aoi": report["aoi"]})
        for phase in durations:
            intervals = [(stamp, timeline[i+1][0] if i+1 < len(timeline) else end)
                         for i, (stamp, value) in enumerate(timeline) if value == phase]
            for left, right in intervals:
                if right > left:
                    phase_aoi.append({"phase": phase, "direction": key[0], "message_type": key[1],
                        "sender": key[2], "recipient": key[3], "start": left, "end": right,
                        "aoi": engine.report(left, right, *key)["aoi"]})
    one_second = defaultdict(Counter)
    for cost in costs:
        one_second[int(cost["sim_time"]-start)][cost["direction"]] += cost["envelope_cdr_bytes"]
    windows = [{"relative_second": second, "duration_sec": min(1, end-start-second),
                "uplink_cdr_bytes": one_second[second]["uplink"],
                "downlink_cdr_bytes": one_second[second]["downlink"]}
               for second in range(math.ceil(end-start))]
    offered = [(w["uplink_cdr_bytes"]+w["downlink_cdr_bytes"])*8/w["duration_sec"] for w in windows]
    role_bytes = Counter()
    for cost in costs:
        role_bytes[cost["control_role"]] += cost["envelope_cdr_bytes"]
    return {"status": "PASS", "scope": "actual native interval, clipped at the predeclared horizon",
        "start_sim_time": start, "end_sim_time": end, "duration_sec": end-start,
        "phase_duration_sec": dict(durations), "strata": rows, "aoi_streams": aoi, "phase_aoi_streams": phase_aoi,
        "queue_distributions": [{"phase": key[0], "direction_or_robot": key[1], "metric": key[2],
                                  "distribution": distribution(values)} for key, values in sorted(queues.items())],
        "one_second_cdr_bps": distribution(offered), "tx_cdr_bytes_by_role": dict(role_bytes),
        "one_second_windows": windows,
        "total_tx_cdr_bytes": sum(role_bytes.values()), "control_cdr_fraction":
            1-role_bytes["data"]/sum(role_bytes.values()) if role_bytes else None,
        "bursts": [{"relative_second": key[0], "direction": key[1], "message_type": key[2], "generated_count": value}
                    for key, value in sorted(bursts.items())],
        "protocol": protocol, "conservation": conservation,
        "physical_accounting": {"actual_airtime_sec": None, "actual_radio_energy_j": None,
            "serialization_sec_per_mbps": sum(role_bytes.values())*8/1e6,
            "tx_energy_j_per_watt_per_mbps": sum(role_bytes.values())*8/1e6,
            "status": "conditional coefficients only; no PHY/MAC, rate or calibrated radio power",
            "task_energy_unit": "distance/time model units, not joules"}}, costs
