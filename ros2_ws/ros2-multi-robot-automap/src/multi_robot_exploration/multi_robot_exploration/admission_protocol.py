"""P3C.5 two-stage application admission, without a network capacity model.

Endpoint queues own payloads. The AP only receives metadata through receive().
The fixed always-grant policy measures protocol cost; it is not a scheduler.
"""

from dataclasses import dataclass
import math

CONTROL_TYPES = frozenset(("candidate", "request", "grant", "heartbeat"))
ORDINARY_TYPES = frozenset(("map_snapshot", "pose_state", "frame_state", "fused_map_snapshot"))
HEARTBEAT_SEC = 1.0
CONTROL_RETRY_SEC = 0.75
MAX_CONTROL_ATTEMPTS = 3
GRANT_LEASE_SEC = 1.0
LOCAL_CAPACITY = 4096


@dataclass(frozen=True)
class Candidate:
    message_id: str
    message_type: str
    sender: str
    recipient: str
    version: int
    source_time: float
    deadline: float
    payload_length: int
    task_phase: str

    def summary(self):
        return dict(self.__dict__)

    @classmethod
    def parse(cls, value, sender):
        if set(value) != set(cls.__dataclass_fields__):
            raise ValueError("candidate schema mismatch")
        candidate = cls(**value)
        if (candidate.sender != sender or candidate.recipient != "headquarters"
                or candidate.message_type not in ORDINARY_TYPES
                or not isinstance(candidate.message_id, str) or not candidate.message_id
                or type(candidate.version) is not int or candidate.version < 1
                or type(candidate.payload_length) is not int or candidate.payload_length < 0
                or not all(isinstance(t, (int, float)) and math.isfinite(t)
                           for t in (candidate.source_time, candidate.deadline))
                or candidate.deadline <= candidate.source_time
                or not isinstance(candidate.task_phase, str)):
            raise ValueError("invalid candidate metadata")
        return candidate


class AdmissionCoordinator:
    """AP state is a projection of delivered packets, never endpoint queues."""

    def __init__(self, emit, record):
        self.emit, self.record = emit, record
        self.candidates, self.requests, self.heartbeats, self.history = {}, {}, {}, {}

    def receive(self, role, sender, payload, now, wire_id, source):
        if role == "heartbeat":
            depth = payload.get("pending_count")
            if set(payload) != {"pending_count"} or type(depth) is not int or not 0 <= depth <= LOCAL_CAPACITY:
                raise ValueError("invalid heartbeat queue snapshot")
            previous = self.heartbeats.get(sender)
            if previous is None or source > previous["source_time"]:
                self.heartbeats[sender] = {"reported_pending_count": depth,
                    "source_time": source, "delivery_time": now, "wire_id": wire_id}
            return
        if role == "candidate":
            candidate = Candidate.parse(payload, sender)
            identity = candidate.message_id
            self.candidates[identity] = (candidate, wire_id, now)
        elif role == "request":
            identity = payload.get("candidate_id")
            if not isinstance(identity, str) or not identity or set(payload) != {"candidate_id"}:
                raise ValueError("invalid admission request")
            self.requests[identity] = (sender, wire_id, now)
        else:
            raise ValueError("unsupported AP control role")
        if identity not in self.candidates or identity not in self.requests:
            return
        candidate, candidate_wire, candidate_delivery = self.candidates[identity]
        request_sender, request_wire, request_delivery = self.requests[identity]
        if candidate.sender != request_sender or now >= candidate.deadline:
            return
        grant = {"candidate_id": identity, "version": candidate.version,
                 "payload_length": candidate.payload_length, "deadline": candidate.deadline,
                 "expires": min(now + GRANT_LEASE_SEC, candidate.deadline)}
        grant_wire = self.emit("grant", "headquarters", sender, grant, now,
                               grant["expires"] - now, identity, 1)
        self.record({"event": "admission_decision", "candidate_id": identity,
                     "candidate_wire_id": candidate_wire, "request_wire_id": request_wire,
                     "candidate_delivery_time": candidate_delivery, "request_delivery_time": request_delivery,
                     "grant_wire_id": grant_wire, "decision_time": now, "policy": "always_grant"})

    def prune(self, now):
        for identity, (candidate, _, _) in list(self.candidates.items()):
            if now >= candidate.deadline:
                self.candidates.pop(identity, None)
                self.requests.pop(identity, None)
        # Requests can precede lost summaries. Bound their retention as well.
        for identity, (_, _, received) in list(self.requests.items()):
            if now - received >= 5.0:
                self.requests.pop(identity, None)

    def note_delivery(self, sender, message_type, identity, source, now):
        self.history[(sender, message_type)] = {"message_id": identity, "source_time": source,
                                              "delivery_time": now}

    def observation(self, now):
        return {"policy": "always_grant", "remote_current_queue": None,
                "queue_information": "last delivered heartbeat snapshot; current queue unknown",
                "heartbeats": {sender: {**item, "age_sec": max(0.0, now-item["source_time"]),
                                        "stale": now-item["source_time"] >= 2.0}
                               for sender, item in sorted(self.heartbeats.items())},
                "received_candidates": [item[0].summary() | {"wire_id": item[1], "delivery_time": item[2]}
                                        for _, item in sorted(self.candidates.items())],
                "received_requests": [{"candidate_id": identity, "sender": item[0],
                    "wire_id": item[1], "delivery_time": item[2]} for identity, item in sorted(self.requests.items())],
                "delivered_history": [item for _, item in sorted(self.history.items())]}


class EndpointQueue:
    def __init__(self, sender, emit, release, record):
        self.sender, self.emit, self.release, self.record = sender, emit, release, record
        self.pending = {}

    def offer(self, candidate, envelope, now):
        if candidate.message_id in self.pending:
            return
        self.record({"event": "local_queue_enter", "candidate_id": candidate.message_id,
                     "local_queue_depth": len(self.pending)+1})
        if now >= candidate.deadline or len(self.pending) >= LOCAL_CAPACITY:
            self.record({"event": "local_discard", "candidate_id": candidate.message_id,
                         "reason": "source_expired" if now >= candidate.deadline else "local_capacity"})
            return
        self.pending[candidate.message_id] = [candidate, envelope, now, -math.inf, 0]
        self._request(self.pending[candidate.message_id], now)

    def _request(self, item, now):
        candidate, _, _, _, attempts = item
        ttl = candidate.deadline-now
        attempts += 1
        self.emit("candidate", self.sender, "headquarters", candidate.summary(), now,
                  ttl, candidate.message_id, attempts)
        self.emit("request", self.sender, "headquarters", {"candidate_id": candidate.message_id},
                  now, ttl, candidate.message_id, attempts)
        item[3], item[4] = now, attempts

    def tick(self, now):
        for identity, item in list(self.pending.items()):
            if now >= item[0].deadline:
                self.pending.pop(identity)
                self.record({"event": "local_discard", "candidate_id": identity, "reason": "source_expired"})
            elif item[4] < MAX_CONTROL_ATTEMPTS and now-item[3] >= CONTROL_RETRY_SEC:
                self._request(item, now)

    def receive_grant(self, payload, now, wire_id):
        if set(payload) != {"candidate_id", "version", "payload_length", "deadline", "expires"}:
            raise ValueError("grant schema mismatch")
        item = self.pending.get(payload["candidate_id"])
        if item is None:
            return  # Duplicate or delayed grant never replays a payload.
        candidate, envelope, queued, _, _ = item
        if (payload["version"] != candidate.version or payload["payload_length"] != candidate.payload_length
                or payload["deadline"] != candidate.deadline
                or not isinstance(payload["expires"], (int, float)) or not math.isfinite(payload["expires"])
                or not now < payload["expires"] <= candidate.deadline):
            raise ValueError("grant does not authorize this live candidate")
        self.pending.pop(candidate.message_id)
        self.record({"event": "admission_release", "candidate_id": candidate.message_id,
                     "grant_wire_id": wire_id, "local_wait_sec": max(0.0, now-queued)})
        self.release(envelope)

    def close(self):
        for identity in list(self.pending):
            self.record({"event": "local_discard", "candidate_id": identity, "reason": "episode_closed"})
        self.pending.clear()
