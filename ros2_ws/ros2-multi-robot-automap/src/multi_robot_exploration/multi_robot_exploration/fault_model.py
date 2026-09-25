"""Deterministic, bounded P3B transport; time and ACKs are supplied by callers."""

import hashlib
import heapq
import math
from dataclasses import dataclass, field


RELIABLE_TYPES = frozenset((
    "target_detection", "navigation_goal", "navigation_cancel",
    "navigation_result", "battery_failure", "task_state",
))
STATE_TYPES = frozenset((
    "map_snapshot", "fused_map_snapshot", "pose_state", "frame_state",
    "battery_state", "task_state", "target_observation",
))


def source_time(envelope):
    return envelope.generation_time.sec + envelope.generation_time.nanosec / 1e9


def message_id(envelope):
    return ":".join(str(value) for value in (
        envelope.message_type, envelope.sender, envelope.recipient,
        envelope.sequence, envelope.correlation_id,
    ))


@dataclass(frozen=True)
class FaultConfig:
    loss_rate: float = 0.0
    delay_sec: float = 0.0
    duplicate_rate: float = 0.0
    reorder_window: int = 0
    seed: int = 1
    ack_timeout_sec: float = 5.0
    max_retries: int = 2
    queue_capacity: int = 4096
    drop_types: tuple = ()

    def __post_init__(self):
        for value in (self.loss_rate, self.duplicate_rate):
            if not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError("probability must be finite and in [0, 1]")
        if not math.isfinite(self.delay_sec) or self.delay_sec < 0:
            raise ValueError("delay must be finite and non-negative")
        if not math.isfinite(self.ack_timeout_sec) or self.ack_timeout_sec <= 0:
            raise ValueError("ACK timeout must be finite and positive")
        if min(self.reorder_window, self.max_retries) < 0 or self.queue_capacity < 0:
            raise ValueError("invalid retry, reorder, or capacity setting")


@dataclass
class DeliveryAttempt:
    message_id: str
    envelope: object
    direction: str
    attempt: int
    enqueue_time: float
    admit_time: float
    due_time: float
    duplicate: bool = False
    metadata: dict = field(default_factory=dict)


class DeterministicFaultTransport:
    """Inject independent per-attempt loss with a bounded drop-tail queue."""

    def __init__(self, config, event_callback=None):
        self.config = config
        self.event_callback = event_callback
        self._events = []
        self._ordinal = 0
        self._pending = {}
        self._inflight = 0

    def _emit(self, event, attempt, now, **extra):
        if self.event_callback:
            self.event_callback({
                **attempt.metadata, "event": event, "time": now,
                "message_id": attempt.message_id, "direction": attempt.direction,
                "attempt": attempt.attempt, "duplicate": attempt.duplicate,
                "enqueue_time": attempt.enqueue_time,
                "admit_time": attempt.admit_time, **extra,
            })

    def _push(self, when, kind, attempt):
        self._ordinal += 1
        heapq.heappush(self._events, (when, self._ordinal, kind, attempt))

    def _sample(self, attempt, kind):
        key = f"{self.config.seed}:{attempt.message_id}:{attempt.attempt}:{kind}"
        return int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64

    def enqueue(self, identity, envelope, direction, now, reliable=False,
                source_time=None, ttl_sec=0.0):
        if identity in self._pending:
            return False
        generated = now if source_time is None else source_time
        metadata = {
            "source_time": generated, "ttl_sec": ttl_sec,
            "message_type": envelope.message_type,
            "sender": getattr(envelope, "sender", ""),
            "recipient": getattr(envelope, "recipient", ""),
            "sequence": envelope.sequence, "version": envelope.sequence,
            "correlation_id": getattr(envelope, "correlation_id", 0),
            "payload_length": getattr(envelope, "payload_length", 0),
        }
        attempt = DeliveryAttempt(identity, envelope, direction, 1, now, now, now,
                                  metadata=metadata)
        self._emit("enqueue", attempt, now)
        self._pending[identity] = (attempt, reliable)
        return self._transmit(attempt, now)

    def _expired(self, attempt, now):
        ttl = attempt.metadata["ttl_sec"]
        return ttl > 0 and now >= attempt.metadata["source_time"] + ttl

    def _transmit(self, attempt, now):
        if self._expired(attempt, now):
            self._emit("drop", attempt, now, drop_time=now, reason="expired_before_tx")
            self._pending.pop(attempt.message_id, None)
            return False
        attempt.admit_time = now
        if self.config.queue_capacity and self._inflight >= self.config.queue_capacity:
            self._emit("drop", attempt, now, drop_time=now, reason="queue_overflow")
            self._retry_timer(attempt, now)
            return False
        attempt.metadata = {**attempt.metadata, "tx_time": now}
        self._emit("admitted", attempt, now)
        self._emit("tx", attempt, now)
        # Reorder is scheduled from message identity, never callback/poll batching.
        extra = 0.0
        if self.config.reorder_window > 1:
            slot = (attempt.envelope.sequence - 1) % self.config.reorder_window
            extra = (self.config.reorder_window - 1 - slot) * 0.05
        attempt.due_time = now + self.config.delay_sec + extra
        self._inflight += 1
        self._push(attempt.due_time, "delivery", attempt)
        self._retry_timer(attempt, now)
        return True

    def _retry_timer(self, attempt, now):
        state = self._pending.get(attempt.message_id)
        if state and state[1]:
            self._push(now + self.config.ack_timeout_sec, "retry", attempt)
        elif "tx_time" not in attempt.metadata:
            self._pending.pop(attempt.message_id, None)

    def acknowledge(self, identity, now):
        state = self._pending.pop(identity, None)
        if state is None:
            return False
        self._emit("acknowledged", state[0], now, ack_time=now)
        return True

    def poll(self, now):
        """Advance scheduled events, preserving scheduled (not wall) timestamps."""
        deliveries = []
        while self._events and self._events[0][0] <= now:
            when, _, kind, attempt = heapq.heappop(self._events)
            state = self._pending.get(attempt.message_id)
            if kind == "retry":
                if state is None or state[0] is not attempt:
                    continue
                if attempt.attempt > self.config.max_retries or self._expired(attempt, when):
                    self._emit("failed", attempt, when, reason="retry_exhausted_or_deadline")
                    self._pending.pop(attempt.message_id, None)
                    continue
                retry = DeliveryAttempt(
                    attempt.message_id, attempt.envelope, attempt.direction,
                    attempt.attempt + 1, attempt.enqueue_time, when, when,
                    metadata={key: value for key, value in attempt.metadata.items()
                              if key != "tx_time"},
                )
                self._pending[retry.message_id] = (retry, True)
                self._emit("retry_scheduled", retry, when)
                self._transmit(retry, when)
                continue
            self._inflight -= 1
            if self._expired(attempt, when):
                self._emit("drop", attempt, when, drop_time=when, reason="expired_in_flight")
            elif kind != "duplicate" and (
                attempt.envelope.message_type in self.config.drop_types
                or self._sample(attempt, "loss") < self.config.loss_rate
            ):
                self._emit("drop", attempt, when, drop_time=when, reason="loss")
            else:
                self._emit("delivered", attempt, when, delivery_time=when)
                deliveries.append(attempt)
                if (
                    kind != "duplicate"
                    and self._sample(attempt, "duplicate")
                    < self.config.duplicate_rate
                ):
                    duplicate = DeliveryAttempt(
                        attempt.message_id, attempt.envelope, attempt.direction,
                        attempt.attempt, attempt.enqueue_time, attempt.admit_time,
                        when + 0.01, True, dict(attempt.metadata),
                    )
                    if (
                        not self.config.queue_capacity
                        or self._inflight < self.config.queue_capacity
                    ):
                        self._inflight += 1
                        self._push(duplicate.due_time, "duplicate", duplicate)
                    else:
                        self._emit(
                            "drop", duplicate, when, drop_time=when,
                            reason="queue_overflow",
                        )
            if state and not state[1]:
                self._pending.pop(attempt.message_id, None)
        return deliveries
