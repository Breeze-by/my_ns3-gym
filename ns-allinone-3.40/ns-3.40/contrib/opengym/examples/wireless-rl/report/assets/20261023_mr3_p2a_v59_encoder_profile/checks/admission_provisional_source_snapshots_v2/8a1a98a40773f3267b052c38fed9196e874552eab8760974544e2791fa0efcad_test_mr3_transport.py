"""Delivery, source-age, epoch, queue and snapshot invariants without ROS."""

import json

import pytest

from multi_robot_exploration.mr3_transport import (
    COMMAND_TTL_SEC, Envelope, EXECUTION_LEASE_SEC, IdealTransport,
    ReceivedStore, STREAM_PERIODS,
)


def message(**overrides):
    values = dict(epoch="episode-a", stream="state", source="tb1", source_stamp=1.0,
                  generated_stamp=1.0, sequence=1, version=1, payload={"x": [2.0]})
    values.update(overrides)
    return Envelope.create(**values)


def test_source_payload_and_received_snapshot_cannot_be_mutated_by_caller():
    payload = {"grid": [-1, 0, 100]}
    transport = IdealTransport("episode-a")
    envelope = transport.send("map", "tb1", payload, source_stamp=1.0, now=1.0)
    payload["grid"][0] = 100
    store = ReceivedStore("episode-a")
    assert store.get("map", "tb1") is None
    transport.deliver(store, 1.0)
    snapshot = store.snapshot()
    snapshot[("map", "tb1")].payload["grid"][0] = 42
    assert envelope.payload["grid"] == [-1, 0, 100]
    assert store.get("map", "tb1").payload["grid"] == [-1, 0, 100]
    with pytest.raises(TypeError):
        snapshot[("state", "tb2")] = envelope
    restored = json.loads(json.dumps(envelope.to_dict()))
    assert restored["payload"] == payload | {"grid": [-1, 0, 100]}


def test_received_store_rejects_cross_epoch_duplicate_and_regressing_sources():
    store = ReceivedStore("episode-a")
    assert store.receive(message(), 1.1)
    for invalid in (
        message(epoch="episode-b", sequence=2),
        message(),
        message(sequence=2, source_stamp=0.9),
        message(sequence=2, version=0),
        message(sequence=2, generated_stamp=2.0),
    ):
        assert not store.receive(invalid, 1.2)
    assert store.get("state", "tb1").sequence == 1
    assert len(store.rejected) == 5


def test_repeat_map_delivery_refreshes_receive_age_only():
    store, transport = ReceivedStore("episode-a"), IdealTransport("episode-a")
    for now in (2.0, 3.0):
        transport.send("map", "tb1", {"data": [-1, 0]}, source_stamp=1.0, now=now, version=7)
        assert len(transport.deliver(store, now)) == 1
    record = store.get("map", "tb1")
    assert (record.source_stamp, record.received_stamp, record.version) == (1.0, 3.0, 7)


def test_latest_data_replacement_and_delivery_cadence():
    store, transport = ReceivedStore("episode-a"), IdealTransport("episode-a")
    transport.send("state", "tb1", {"x": 1}, source_stamp=1.0, now=1.0)
    assert len(transport.deliver(store, 1.0)) == 1
    transport.send("state", "tb1", {"x": 2}, source_stamp=1.01, now=1.01)
    transport.send("state", "tb1", {"x": 3}, source_stamp=1.02, now=1.02)
    assert transport.pending_count == 1
    assert transport.deliver(store, 1.05) == ()
    assert store.get("state", "tb1").payload == {"x": 1}
    assert len(transport.deliver(store, 1.1)) == 1
    assert store.get("state", "tb1").payload == {"x": 3}


def test_reliable_ownership_queue_fails_explicitly_and_preserves_fifo():
    transport = IdealTransport("episode-a", reliable_capacity=2)
    store = ReceivedStore("episode-a")
    for command in ("goal", "cancel"):
        transport.send("command", "hub", {"kind": command}, source_stamp=1.0, now=1.0)
    with pytest.raises(BufferError):
        transport.send("ack", "tb1", {}, source_stamp=1.0, now=1.0)
    delivered = transport.deliver(store, 1.0)
    assert [record.payload["kind"] for record in delivered] == ["goal", "cancel"]
    assert transport.pending_count == 0


def test_receipts_and_heartbeat_are_serviced_at_five_hertz():
    transport, store = IdealTransport("episode-a"), ReceivedStore("episode-a")
    for stamp in (1.0, 1.01):
        transport.send("heartbeat", "hub", {"goal_id": "g1"}, source_stamp=stamp, now=stamp)
    assert len(transport.deliver(store, 1.01)) == 1
    assert transport.deliver(store, 1.1) == ()
    assert len(transport.deliver(store, 1.21)) == 1
    assert STREAM_PERIODS["map"] == 1.0
    assert STREAM_PERIODS["state"] == 0.1
    assert STREAM_PERIODS["receipt"] == STREAM_PERIODS["heartbeat"] == 0.2
    assert COMMAND_TTL_SEC == EXECUTION_LEASE_SEC == 2.0


def test_transport_never_relabels_another_episode_delivery():
    transport, store = IdealTransport("episode-a"), ReceivedStore("episode-b")
    transport.send("state", "tb1", {}, source_stamp=1.0, now=1.0)
    assert transport.deliver(store, 1.0) == ()
    assert not store.snapshot()


def test_timer_sampled_delivery_keeps_actual_timestamp_without_double_throttle():
    transport, store = IdealTransport("episode-a"), ReceivedStore("episode-a")
    for stamp in (1.001, 1.1):
        transport.send("state", "tb1", {}, source_stamp=stamp, now=stamp)
        assert len(transport.deliver(store, stamp, sampled=True)) == 1
    assert store.get("state", "tb1").received_stamp == 1.1


def test_receive_time_rewind_does_not_refresh_a_record():
    store = ReceivedStore("episode-a")
    assert store.receive(message(), 2.0)
    assert not store.receive(message(sequence=2), 1.5)
    assert store.get("state", "tb1").received_stamp == 2.0


@pytest.mark.parametrize("overrides", [
    {"source_stamp": float("nan")}, {"generated_stamp": -1.0},
    {"source_stamp": 2.0}, {"sequence": 0}, {"version": -1},
    {"payload": {"x": float("inf")}}, {"epoch": ""}, {"stream": "truth"},
])
def test_invalid_envelopes_are_rejected(overrides):
    with pytest.raises(ValueError):
        message(**overrides)
