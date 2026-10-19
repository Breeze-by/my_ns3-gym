"""Deterministic ideal transport contract for the three-robot P1B adapter.

Times are simulation seconds within one explicitly selected episode epoch. State
snapshots are sampled at 10 Hz, full occupancy snapshots at 1 Hz, and navigation
receipts / heartbeat renewals at 5 Hz. No map delta or compression is used.
Map and state queues retain only the latest unsent value per source. Command,
ACK and receipt queues are reliable ordered bounded queues: overflow raises
instead of silently losing ownership information. Ideal delivery has zero delay
when a stream is serviced; a later gateway replaces delivery, not these records.

Commands have a 2 s generated-time TTL. A distinct 2 s execution lease is renewed
by explicit 5 Hz heartbeat commands for the same epoch and goal ID; a duplicate
command is never a lease renewal. The goal-owner state machine, rather than this
transport, handles expiry, cancel confirmation and fail-closed stopping. Queue
reliability does not claim delivery after a crash or actual Wi-Fi reliability.

Payloads are JSON values stored as immutable canonical JSON bytes. Access returns
an independent decoded value; callers cannot mutate a queued/delivered snapshot.
This defines future payload structure, not a gateway or ns-3 byte-transport proof.
"""

from collections import deque
from dataclasses import dataclass, replace
import json
import math
from types import MappingProxyType


STATE_PERIOD_SEC = 0.1
MAP_PERIOD_SEC = 1.0
RECEIPT_PERIOD_SEC = 0.2
COMMAND_TTL_SEC = 2.0
EXECUTION_LEASE_SEC = 2.0
STREAM_PERIODS = MappingProxyType({
    'state': STATE_PERIOD_SEC, 'peer_state': STATE_PERIOD_SEC,
    'map': MAP_PERIOD_SEC, 'shared_map': MAP_PERIOD_SEC,
    'receipt': RECEIPT_PERIOD_SEC, 'heartbeat': RECEIPT_PERIOD_SEC,
    'command': 0.0, 'ack': 0.0,
})
LATEST_STREAMS = frozenset(('state', 'peer_state', 'map', 'shared_map'))


def _time(value, field):
    value = float(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError(f'{field} must be a finite nonnegative simulation time')
    return value


@dataclass(frozen=True)
class Envelope:
    """A source-owned sequence/version with an immutable full payload snapshot."""

    epoch: str
    stream: str
    source: str
    source_stamp: float
    generated_stamp: float
    sequence: int
    version: int
    payload_json: str
    received_stamp: float | None = None

    @classmethod
    def create(cls, *, epoch, stream, source, source_stamp, generated_stamp,
               sequence, version, payload):
        if not isinstance(epoch, str) or not epoch or not isinstance(source, str) or not source:
            raise ValueError('epoch and source must be nonempty strings')
        if stream not in STREAM_PERIODS:
            raise ValueError(f'Unsupported stream: {stream}')
        if not isinstance(sequence, int) or sequence < 1:
            raise ValueError('sequence must be a positive integer')
        if not isinstance(version, int) or version < 0:
            raise ValueError('version must be a nonnegative integer')
        stamp = _time(source_stamp, 'source_stamp')
        generated = _time(generated_stamp, 'generated_stamp')
        if stamp > generated + 1e-9:
            raise ValueError('a source timestamp cannot be in the future')
        encoded = json.dumps(payload, allow_nan=False, sort_keys=True, separators=(',', ':'))
        return cls(epoch, stream, source, stamp, generated, sequence, version, encoded)

    @property
    def payload(self):
        """Return a caller-owned copy; modifying it cannot mutate this envelope."""
        return json.loads(self.payload_json)

    def to_dict(self):
        return {
            'epoch': self.epoch, 'stream': self.stream, 'source': self.source,
            'source_stamp': self.source_stamp, 'generated_stamp': self.generated_stamp,
            'sequence': self.sequence, 'version': self.version,
            'received_stamp': self.received_stamp, 'payload': self.payload,
        }


class ReceivedStore:
    """Only explicit deliveries advance a source; epoch changes require a new store."""

    def __init__(self, epoch):
        if not isinstance(epoch, str) or not epoch:
            raise ValueError('epoch must be a nonempty string')
        self.epoch = epoch
        self._records = {}
        self.rejected = []

    def receive(self, envelope, now):
        now = _time(now, 'received_stamp')
        reason = None
        if envelope.epoch != self.epoch:
            reason = 'cross_epoch'
        elif envelope.generated_stamp > now + 1e-9:
            reason = 'future_delivery'
        else:
            previous = self._records.get((envelope.stream, envelope.source))
            if previous and (
                envelope.sequence <= previous.sequence
                or envelope.version < previous.version
                or envelope.source_stamp < previous.source_stamp - 1e-9
                or envelope.generated_stamp < previous.generated_stamp - 1e-9
                or now < previous.received_stamp - 1e-9
            ):
                reason = 'older_or_duplicate'
        if reason:
            self.rejected.append((reason, envelope.stream, envelope.source, envelope.sequence))
            return False
        self._records[(envelope.stream, envelope.source)] = replace(envelope, received_stamp=now)
        return True

    def get(self, stream, source):
        return self._records.get((stream, source))

    def snapshot(self):
        return MappingProxyType(dict(self._records))


class IdealTransport:
    """Explicitly service full snapshots, with latest-data and bounded FIFO queues."""

    def __init__(self, epoch, reliable_capacity=64):
        if not isinstance(epoch, str) or not epoch:
            raise ValueError('epoch must be a nonempty string')
        if reliable_capacity < 1:
            raise ValueError('reliable_capacity must be positive')
        self.epoch = epoch
        self.reliable_capacity = reliable_capacity
        self._latest = {}
        self._reliable = deque()
        self._sequences = {}
        self._last_delivery = {}

    def send(self, stream, source, payload, *, source_stamp, now, version=None):
        key = (stream, source)
        sequence = self._sequences.get(key, 0) + 1
        envelope = Envelope.create(
            epoch=self.epoch, stream=stream, source=source,
            source_stamp=source_stamp, generated_stamp=now, sequence=sequence,
            version=sequence if version is None else version, payload=payload,
        )
        if stream in LATEST_STREAMS:
            self._latest[key] = envelope
        else:
            if len(self._reliable) >= self.reliable_capacity:
                raise BufferError('reliable ownership queue is full')
            self._reliable.append(envelope)
        self._sequences[key] = sequence
        return envelope

    @property
    def pending_count(self):
        return len(self._latest) + len(self._reliable)

    def deliver(self, store, now, *, sampled=False):
        """Deliver due entries; ``sampled`` means a source timer sets the cadence.

        Already sampled timer callbacks use their actual delivery timestamp and
        avoid a second throttle that could halve throughput when consecutive
        callbacks land slightly less than one nominal period apart.
        """
        now = _time(now, 'delivery_stamp')
        delivered = []
        for key, envelope in tuple(self._latest.items()):
            if self._due(envelope, now, sampled):
                del self._latest[key]
                if store.receive(envelope, now):
                    delivered.append(store.get(*key))
                self._last_delivery[key] = now
        # Preserve reliable FIFO order even when its head awaits its cadence.
        while self._reliable and self._due(self._reliable[0], now, sampled):
            envelope = self._reliable.popleft()
            if store.receive(envelope, now):
                delivered.append(store.get(envelope.stream, envelope.source))
            self._last_delivery[(envelope.stream, envelope.source)] = now
        return tuple(delivered)

    def _due(self, envelope, now, sampled):
        key = (envelope.stream, envelope.source)
        previous = self._last_delivery.get(key)
        return (
            envelope.generated_stamp <= now + 1e-9
            and (sampled or previous is None
                 or now - previous + 1e-9 >= STREAM_PERIODS[envelope.stream])
        )
