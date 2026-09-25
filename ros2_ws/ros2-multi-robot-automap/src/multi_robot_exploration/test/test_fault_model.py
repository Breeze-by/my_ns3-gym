from types import SimpleNamespace

from multi_robot_exploration.fault_model import (
    DeterministicFaultTransport,
    FaultConfig,
)


def envelope(sequence=1, ttl_sec=10.0):
    return SimpleNamespace(message_type="target_detection", sequence=sequence)


def test_fixed_delay_and_seeded_loss_are_reproducible():
    events = []
    transport = DeterministicFaultTransport(
        FaultConfig(delay_sec=0.5, loss_rate=0.0, seed=7), events.append
    )
    assert transport.enqueue("m1", envelope(), "uplink", 1.0, reliable=True)
    assert transport.poll(1.49) == []
    assert len(transport.poll(1.5)) == 1
    assert any(event["event"] == "tx" for event in events)


def test_reliable_message_retries_until_ack_or_bound():
    events = []
    transport = DeterministicFaultTransport(
        FaultConfig(
            loss_rate=1.0,
            ack_timeout_sec=0.25,
            max_retries=2,
            seed=11,
        ),
        events.append,
    )
    transport.enqueue("m2", envelope(), "uplink", 0.0, reliable=True)
    transport.poll(0.0)
    transport.poll(0.25)
    transport.poll(0.5)
    transport.poll(0.75)
    assert [event["event"] for event in events].count("drop") == 3
    assert not transport.acknowledge("m2", 1.0)


def test_ttl_drops_delayed_message_and_duplicate_is_visible():
    events = []
    transport = DeterministicFaultTransport(
        FaultConfig(delay_sec=1.0, duplicate_rate=1.0, seed=3), events.append
    )
    transport.enqueue(
        "m3", envelope(ttl_sec=0.5), "downlink", 0.0, reliable=False, ttl_sec=0.5
    )
    assert transport.poll(1.0) == []
    assert events[-1]["reason"] in ("expired", "expired_in_flight", "expired_before_tx")


def test_queue_capacity_reports_overflow():
    events = []
    transport = DeterministicFaultTransport(
        FaultConfig(queue_capacity=1), events.append
    )
    assert transport.enqueue("first", envelope(), "uplink", 0.0)
    assert not transport.enqueue("second", envelope(2), "uplink", 0.0)
    assert events[-1]["reason"] == "queue_overflow"
