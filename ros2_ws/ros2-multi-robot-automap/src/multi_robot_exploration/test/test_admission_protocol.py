from copy import deepcopy
import pytest

from multi_robot_exploration.admission_protocol import (
    Candidate, EndpointQueue, AdmissionCoordinator, LOCAL_CAPACITY,
)


def candidate(identity="pose_state:tb1:headquarters:1:0", source=10.0, ttl=2.0):
    return Candidate(identity, "pose_state", "tb1", "headquarters", 1, source, source+ttl, 704, "EXPLORE")


def actors():
    wires, events, releases = [], [], []
    def emit(role, sender, recipient, payload, now, ttl, ref=None, attempt=1):
        identity = f"{role}:{sender}:{recipient}:{len(wires)+1}:0"
        wires.append(dict(role=role, sender=sender, recipient=recipient, payload=deepcopy(payload),
                          now=now, ttl=ttl, ref=ref, attempt=attempt, identity=identity))
        return identity
    return EndpointQueue("tb1", emit, releases.append, events.append), AdmissionCoordinator(emit, events.append), wires, events, releases


def deliver(ap, wire, now):
    ap.receive(wire["role"], wire["sender"], wire["payload"], now, wire["identity"], wire["now"])


def test_only_delivered_candidate_and_request_authorize_single_payload():
    endpoint, ap, wires, events, releases = actors()
    payload = object()
    endpoint.offer(candidate(), payload, 10)
    assert len(wires) == 2 and not releases and not ap.candidates
    deliver(ap, wires[1], 10.1)
    assert len(wires) == 2
    deliver(ap, wires[0], 10.2)
    grant = wires[-1]
    assert grant["role"] == "grant" and grant["payload"]["expires"] == 11.2
    assert not releases
    endpoint.receive_grant(grant["payload"], 10.3, grant["identity"])
    endpoint.receive_grant(grant["payload"], 10.4, grant["identity"])
    assert releases == [payload]
    assert events[-1]["local_wait_sec"] == pytest.approx(.3)


def test_hidden_queue_changes_do_not_change_ap_observations_or_decisions():
    endpoint, ap, wires, _, _ = actors()
    baseline = ap.observation(10)
    endpoint.offer(candidate(), b"hidden", 10)
    assert ap.observation(10) == baseline
    ap.receive("heartbeat", "tb1", {"pending_count": 1}, 10.1, "heartbeat1", 10)
    delivered = ap.observation(10.1)
    endpoint.close()
    assert ap.observation(10.1) == delivered
    assert delivered["remote_current_queue"] is None
    assert delivered["heartbeats"]["tb1"]["reported_pending_count"] == 1
    assert not hasattr(ap, "pending") and not hasattr(ap, "endpoint_queues")


def test_lost_summary_request_and_grant_retry_is_bounded_without_ttl_renewal():
    endpoint, _, wires, events, releases = actors()
    endpoint.offer(candidate(), b"data", 10)
    for now in (10.75, 11.5, 11.9, 12, 20):
        endpoint.tick(now)
    assert len(wires) == 6 and max(w["attempt"] for w in wires) == 3
    assert all(w["now"]+w["ttl"] == 12 for w in wires)
    assert not endpoint.pending and not releases
    assert events[-1]["reason"] == "source_expired"


@pytest.mark.parametrize("change", [{"version": 2}, {"payload_length": 705},
    {"deadline": 13.0}, {"expires": 12.1}, {"expires": float("nan")}, {"expires": 10.1}])
def test_grant_must_match_live_source_candidate(change):
    endpoint, ap, wires, _, releases = actors()
    endpoint.offer(candidate(), b"data", 10)
    deliver(ap, wires[0], 10.05)
    deliver(ap, wires[1], 10.1)
    grant = wires[-1]["payload"] | change
    with pytest.raises(ValueError):
        endpoint.receive_grant(grant, 10.2, "grant")
    assert not releases and endpoint.pending


@pytest.mark.parametrize("change", [{"sender": "tb2"}, {"deadline": 10.0},
    {"source_time": float("inf")}, {"payload_length": -1}, {"version": 0}, {"extra": 1}])
def test_ap_rejects_invalid_or_cross_robot_summaries(change):
    _, ap, _, _, _ = actors()
    with pytest.raises(ValueError):
        ap.receive("candidate", "tb1", candidate().summary() | change, 10, "wire", 10)


def test_expired_or_cross_robot_request_never_produces_a_grant():
    _, ap, wires, _, _ = actors()
    ap.receive("candidate", "tb1", candidate().summary(), 10, "candidate", 10)
    ap.receive("request", "tb2", {"candidate_id": candidate().message_id}, 10.1, "request", 10)
    ap.receive("request", "tb1", {"candidate_id": candidate().message_id}, 12, "request2", 11)
    assert not wires
    ap.prune(12)
    assert not ap.candidates


def test_stale_heartbeat_does_not_replace_received_snapshot():
    _, ap, _, _, _ = actors()
    ap.receive("heartbeat", "tb1", {"pending_count": 2}, 11, "new", 10)
    ap.receive("heartbeat", "tb1", {"pending_count": 9}, 11.1, "old", 9)
    assert ap.observation(12)["heartbeats"]["tb1"]["reported_pending_count"] == 2


def test_closed_local_queue_is_fully_accounted():
    endpoint, _, _, events, _ = actors()
    endpoint.offer(candidate(), b"data", 10)
    endpoint.close()
    assert events[-1]["reason"] == "episode_closed" and not endpoint.pending


def test_source_expired_offer_never_generates_control_traffic():
    endpoint, _, wires, events, _ = actors()
    endpoint.offer(candidate(), b"data", 12)
    assert not wires and events[-1]["reason"] == "source_expired"
