"""Typed receiving permission for the existing exclusive Nav2 stream.

This never assigns a goal/generation to an unstamped Twist, selects a goal,
changes Reach geometry, reanchors a tracker or rearms the encoder servo.
"""
import copy
import json
import math
import re

from .mr3_episode import timestamp_ns
from .mr3_reach_runtime import H_NS, PUB_NS, model_check

PROFILE = "mr3-owned-stream-authority-v3"
PROTOCOL = "mr3-motion-authority-v1"
ACK = "mr3-motion-authority-ack-v1"
ROBOTS = ("tb1", "tb2", "tb3")
LEASE_NS = 2_000_000_000  # Existing navigation lease, not a new tunable budget.


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def owner_key(value):
    return value["goal_id"], value["native_goal_uuid"], value["owner_grant_sequence"]


def from_accepted_owner(dispatcher, robot, handles, authority_sequence, clock_ns, *, accepted_goal_id):
    """Only the actual accepted callback may call this producer constructor."""
    state = dispatcher.states[robot]
    handle = handles.get(state.goal_id)
    require(state.goal_id == accepted_goal_id and handle is not None and state.accepted is True and state.phase == "active" and not state.cancel_requested
            and state.goal_id is not None and handle.accepted is True,
            "no actual currently accepted navigation owner")
    require(clock_ns == timestamp_ns(dispatcher._now), "producer clock is not the actual dispatcher frontier")
    native_uuid = bytes(handle.goal_id.uuid)
    require(len(native_uuid) == 16 and integer(authority_sequence, 1), "invalid native owner identity")
    return {"schema": PROTOCOL, "epoch": dispatcher.epoch, "robot": robot,
            "operation": "grant", "authority_sequence": authority_sequence,
            "owner_grant_sequence": authority_sequence, "goal_id": state.goal_id,
            "native_goal_uuid": native_uuid.hex(), "owner_command_id": state.command["command_id"],
            "source_clock_ns": clock_ns, "owner_accept_received_clock_ns": timestamp_ns(state.accepted_at),
            "lease_until_ns": timestamp_ns(state.lease_until)}


def identity_key(value):
    return value["goal_id"], value["native_goal_uuid"]


def from_canceling_owner(dispatcher, grant, authority_sequence, clock_ns):
    """Publish this and call native cancel immediately at the same legal event.

    No storage/rest/ACK wait is a precondition for making the native cancel call.
    """
    state = dispatcher.states[grant["robot"]]
    require(clock_ns == timestamp_ns(dispatcher._now), "producer clock is not the actual dispatcher frontier")
    require(state.accepted is True and state.cancel_requested is True
            and state.goal_id == grant["goal_id"] and state.command["command_id"] == grant["owner_command_id"],
            "cancel does not own the actual accepted goal")
    require(integer(authority_sequence, grant["authority_sequence"] + 1), "authority sequence did not advance")
    result = copy.deepcopy(grant)
    result.update(operation="revoke", authority_sequence=authority_sequence,
                  source_clock_ns=clock_ns, lease_until_ns=clock_ns)
    return result


def from_terminal_owner(dispatcher, grant, authority_sequence, clock_ns, *, terminal_goal_id, status):
    """For a genuine terminal callback; this does NOT issue native cancellation."""
    state = dispatcher.states[grant["robot"]]
    require(type(status) is int and status in (4, 5, 6)
            and terminal_goal_id == state.goal_id == grant["goal_id"] and state.accepted is True
            and state.command["command_id"] == grant["owner_command_id"],
            "terminal is not the current actual native owner")
    require(clock_ns == timestamp_ns(dispatcher._now)
            and integer(authority_sequence, grant["authority_sequence"]+1), "invalid terminal revoke frontier")
    message = copy.deepcopy(grant)
    message.update(operation="revoke", authority_sequence=authority_sequence,
                   source_clock_ns=clock_ns, lease_until_ns=clock_ns)
    return message


def issue_owned_cancel(dispatcher, grant, authority_sequence, clock_ns, publish, native_cancel):
    message = from_canceling_owner(dispatcher, grant, authority_sequence, clock_ns)
    # Publication is not delivery. Never wait for ACK/rest before the native
    # attempt, and still attempt native cancel if publication raises.
    try:
        publish(copy.deepcopy(message))
    finally:
        future = native_cancel()
    return message, future


def renewal_from_owner(dispatcher, grant, authority_sequence, clock_ns):
    state = dispatcher.states[grant["robot"]]
    require(clock_ns == timestamp_ns(dispatcher._now), "producer clock is not the actual dispatcher frontier")
    require(state.accepted is True and state.phase == "active" and not state.cancel_requested
            and state.goal_id == grant["goal_id"], "renewal no longer owns navigation")
    result = copy.deepcopy(grant)
    result.update(operation="renew", authority_sequence=authority_sequence,
                  source_clock_ns=clock_ns, lease_until_ns=timestamp_ns(state.lease_until))
    return result


def normal_zero_witness(tracker, clock_ns, not_before_ns, *, after_real_motion):
    """Read genuine already-validated tracker receipts; never accept ready=True.

    Existing qualified() covers HOLD/N. D keeps the already established fixed
    disk certificate; this read-only check adds no anchor or geometry rule.
    Initial encoder-hold can honestly write nonzero correction at target zero.
    After real nonzero application, require the actual APPLIED rim values zero.
    """
    if (tracker.fault is not None or tracker.stopped or tracker.release_ns is None
            or tracker.epoch is None or not integer(clock_ns) or not integer(not_before_ns)
            or clock_ns < not_before_ns or tracker.role not in ("HOLD", "N", "D")):
        return None
    if tracker.zero_publication is None or tracker.zero_storage is None:
        return None
    if clock_ns-tracker.zero_publication < PUB_NS or clock_ns-tracker.zero_storage < H_NS:
        return None
    disk = (tracker.role == "D" and tracker.current_intent is not None
            and tracker.current_intent.get("role") == "D"
            and tracker.current_intent.get("anchor") == tracker.anchor)
    if not (disk or tracker.qualified(clock_ns)):
        return None
    applied = tracker.causal_applied
    if applied is None or tracker.last_applied != applied:
        return None
    target = applied["target"]
    if (target["linear_x"] != 0 or target["angular_z"] != 0
            or target["clock_ns"] < not_before_ns or applied["source_clock_ns"] < target["clock_ns"]):
        return None
    stored = tracker.storage.pending[tracker.robot].get(target["decision_sequence"])
    if (stored is None or stored["cmd_seq"] != applied["cmd_seq"]
            or stored["source_clock_ns"] != target["clock_ns"]
            or stored["decision_sequence"] != target["decision_sequence"]
            or stored["linear_x"] != 0 or stored["angular_z"] != 0):
        return None
    rest = tracker.rest
    if len(rest) != 3 or tracker.latest_raw is None or tracker.latest_raw[0] <= applied["source_clock_ns"]:
        return None
    for source, raw in rest:
        if (not not_before_ns <= source <= clock_ns or clock_ns-source > 100_000_000
                or source not in tracker.calibrations
                or not model_check(raw, tracker.calibrations[source], ())["metric_necessary"]):
            return None
    rims_zero = all(all(value == 0 for value in pair["applied_rim_mps"]) for pair in applied["pairs"])
    if after_real_motion and not rims_zero:
        return None
    return {"schema": "mr3-normal-zero-authority-witness-v1", "epoch": tracker.epoch,
            "robot": tracker.robot, "clock_ns": clock_ns, "not_before_ns": not_before_ns,
            "zero_publication_since_ns": tracker.zero_publication,
            "zero_storage_since_ns": tracker.zero_storage, "storage": copy.deepcopy(stored),
            "applied": copy.deepcopy(applied), "actual_rims_zero": rims_zero,
            "after_real_nonzero_application": after_real_motion,
            "rest": [{"source_clock_ns": source, "odometry": copy.deepcopy(raw),
                      "calibration": copy.deepcopy(tracker.calibrations[source])} for source, raw in rest],
            "reach_role": tracker.role, "anchor": copy.deepcopy(tracker.anchor),
            "permanent_stop": False, "continuous_physics_proved": False}


class MotionAuthority:
    """Per-robot receiving authority; owner token is not raw source generation."""
    def __init__(self, epoch, robot, publisher_gid):
        require(type(epoch) is str and epoch and robot in ROBOTS, "invalid authority context")
        require(type(publisher_gid) is str and publisher_gid, "missing configured authority publisher")
        self.epoch, self.robot, self.publisher_gid = epoch, robot, publisher_gid
        self.sequence = 0
        self.packet = self.owner = None
        self.state = "NONE"
        self.retired = set()
        self.fault = None
        self.callback_floor = 0
        self.received_clock_ns = None
        self.stop_not_before_ns = None
        self.ready = None
        self.after_real_motion = False
        self.last_decision_clock_ns = None

    def _invalid(self, reason):
        self.fault = reason
        self.ready = None
        return {"accepted": False, "reason": reason, "effective_permission": "zero_only"}

    def observe_stop(self, tracker, clock_ns, *, latest_raw_sequence=None):
        require(tracker.epoch == self.epoch and tracker.robot == self.robot, "stop evidence owner differs")
        if self.state == "PENDING" and clock_ns >= self.owner["lease_until_ns"]:
            self.state = "REVOKED"
            self.retired.add(identity_key(self.owner))
            self.stop_not_before_ns = clock_ns
            self.ready = None
        if self.state == "ACTIVE":
            return None
        if self.fault is not None:
            return None
        self.note_real_application(tracker)
        start = self.stop_not_before_ns
        if start is None:
            start = tracker.release_ns
        if start is None:
            return None
        self.ready = normal_zero_witness(tracker, clock_ns, start, after_real_motion=self.after_real_motion)
        if self.ready is None:
            return None
        if self.state == "PENDING":
            require(integer(latest_raw_sequence), "activation_missing_actual_raw_callback_floor")
            witness = self.ready
            self.state = "ACTIVE"
            self.callback_floor = latest_raw_sequence
            self.ready = None
            return {"schema": ACK, "epoch": self.epoch, "robot": self.robot,
                    "stage": "authority_activated", "state": "ACTIVE", "authority_sequence": self.sequence,
                    "owner": copy.deepcopy(self.owner), "received_clock_ns": self.received_clock_ns,
                    "activation_clock_ns": clock_ns, "callback_floor": self.callback_floor,
                    "witness": copy.deepcopy(witness)}
        return {"schema": ACK, "epoch": self.epoch, "robot": self.robot, "stage": "stop_obligation_ready",
                "authority_sequence": self.sequence, "owner": copy.deepcopy(self.owner),
                "received_clock_ns": self.received_clock_ns, "witness": copy.deepcopy(self.ready)}

    def receive(self, message, *, publisher_gid, clock_ns, latest_raw_sequence):
        if publisher_gid != self.publisher_gid:
            return self._invalid("authority_publisher_mismatch")
        try:
            keys = {"schema", "epoch", "robot", "operation", "authority_sequence", "owner_grant_sequence",
                    "goal_id", "native_goal_uuid", "owner_command_id", "source_clock_ns", "lease_until_ns",
                    "owner_accept_received_clock_ns"}
            require(type(message) is dict and set(message) == keys and message["schema"] == PROTOCOL
                    and message["epoch"] == self.epoch and message["robot"] == self.robot,
                    "authority_fields_or_context")
            require(all(integer(message[key], 1) for key in ("authority_sequence", "owner_grant_sequence", "owner_command_id"))
                    and integer(message["source_clock_ns"]) and integer(message["lease_until_ns"])
                    and integer(clock_ns) and integer(latest_raw_sequence)
                    and integer(message["owner_accept_received_clock_ns"])
                    and message["owner_accept_received_clock_ns"] <= message["source_clock_ns"] <= clock_ns
                    and message["owner_grant_sequence"] <= message["authority_sequence"],
                    "authority_clock_or_sequence")
            require(re.fullmatch(re.escape(self.epoch+":"+self.robot+":")+r"[1-9][0-9]*",message["goal_id"])
                    and re.fullmatch(r"[0-9a-f]{32}",message["native_goal_uuid"])
                    and message["goal_id"].rsplit(":",1)[1] == str(message["owner_command_id"]),
                    "authority_owner_identity")
            operation, sequence = message["operation"], message["authority_sequence"]
            require(operation in ("grant", "renew", "revoke"), "authority_operation")
            if sequence < self.sequence:
                return {"accepted": False, "reason": "stale_authority", "state": self.state}
            if sequence == self.sequence:
                if self.packet is not None and canonical(message) == canonical(self.packet):
                    return {"accepted": True, "reason": "duplicate", "state": self.state}
                return self._invalid("conflicting_authority_duplicate")
            if self.fault is not None:
                return {"accepted": False, "reason": "latched_authority_fault", "state": self.state}
            token = owner_key(message)
            identity = identity_key(message)
            if identity in self.retired and (operation == "grant" or self.owner is None
                    or identity != identity_key(self.owner)):
                return {"accepted": False, "reason": "retired_owner", "state": self.state}
            if operation in ("grant", "renew"):
                require(clock_ns < message["lease_until_ns"]
                        <= message["source_clock_ns"]+LEASE_NS, "invalid_authority_lease")
            if operation == "revoke":
                require(message["lease_until_ns"] == message["source_clock_ns"], "invalid_revoke_clock")
                # If grant delivery was reordered/lost, this still closes the
                # stream and rejects the later older grant. It grants nothing.
                if self.owner is not None and token != owner_key(self.owner):
                    return self._invalid("revoke_not_current_owner")
                self.retired.add(identity)
                self.owner = copy.deepcopy(message)
                self.state = "REVOKED"
                self.stop_not_before_ns = clock_ns
                self.ready = None
            elif operation == "renew":
                require(self.state in ("PENDING", "ACTIVE") and self.owner is not None and token == owner_key(self.owner),
                        "renew_not_active_owner")
                require(message["lease_until_ns"] > self.owner["lease_until_ns"], "authority_lease_not_extended")
            else:
                require(message["owner_grant_sequence"] == sequence and identity not in self.retired,
                        "retired_or_mismatched_grant")
                require(self.state not in ("PENDING", "ACTIVE"), "overlapping_owner_grant")
                # A well-formed owned request is not motion permission. Receipt
                # can race with witness invalidation; activation happens only
                # inside a normal control phase with newly reconstructed proof.
                self.owner = copy.deepcopy(message)
                self.state = "PENDING"
                self.ready = None
            if operation in ("grant", "renew"):
                self.owner = copy.deepcopy(message)
            self.sequence = sequence
            self.packet = copy.deepcopy(message)
            self.received_clock_ns = clock_ns
            return {"schema": ACK, "epoch": self.epoch, "robot": self.robot,
                    "authority_sequence": sequence, "stage": "authority_received",
                    "accepted": True, "state": self.state, "received_clock_ns": clock_ns,
                    "source_clock_ns": message["source_clock_ns"], "callback_floor": self.callback_floor,
                    "scope": "actual authority callback only, not target storage, motor or rest"}
        except (ValueError, TypeError, KeyError, AttributeError) as error:
            # Preserve the rejected predicate and pre-fault local proof. The
            # original fail-closed latch and zero permission remain unchanged.
            context = {"state": self.state, "authority_sequence": self.sequence,
                       "owner": copy.deepcopy(self.owner), "ready": copy.deepcopy(self.ready),
                       "callback_clock_ns": clock_ns, "stop_not_before_ns": self.stop_not_before_ns}
            result = self._invalid("invalid_authority")
            result.update(rejected_condition=str(error), rejection_context=context)
            return result

    def input(self, raw_request, *, clock_ns):
        """Return an effective [v,w], retaining original raw as separate data."""
        if (not integer(clock_ns) or self.last_decision_clock_ns is not None
                and clock_ns < self.last_decision_clock_ns):
            self._invalid("invalid_authority_decision_clock")
        else:
            self.last_decision_clock_ns = clock_ns
        if self.state in ("PENDING", "ACTIVE") and self.owner is not None and integer(clock_ns) and clock_ns >= self.owner["lease_until_ns"]:
            self.state = "REVOKED"
            self.retired.add(identity_key(self.owner))
            self.stop_not_before_ns = clock_ns
            self.ready = None
        fresh_callback = (isinstance(raw_request, dict) and integer(raw_request.get("sequence"), 1)
                          and raw_request["sequence"] > self.callback_floor)
        permit = self.fault is None and self.state == "ACTIVE" and fresh_callback
        output = [0.0, 0.0]
        if permit:
            values = [raw_request.get("v"), raw_request.get("w")]
            permit = all(type(value) in (int,float) and math.isfinite(value) for value in values)
            if permit:
                output = values
        return {"effective_request": output, "permission": "normal_reach" if permit else "zero_only",
                "authority_sequence": self.sequence, "owner": copy.deepcopy(self.owner),
                "state": self.state, "fault": self.fault, "callback_floor": self.callback_floor,
                "raw_input_sequence": raw_request.get("sequence") if isinstance(raw_request,dict) else None,
                "raw_goal_generation": None, "raw_goal_association": "UNKNOWN_UNSTAMPED_TWIST",
                "claim": "receiving permission only; callback floor is not generation time"}

    def note_validated_application(self, tracker, value):
        """Latch a real validated APPLIED receipt before deferred synchronize.

        receive_applied queues events. Looking only at last_applied here would
        miss a nonzero receipt overwritten by a zero before the next phase.
        """
        require(tracker.epoch == self.epoch and tracker.robot == self.robot, "application owner differs")
        require(type(value) is dict and tracker.applied_seen.get(value.get("actuation_sequence")) == value,
                "application was not validated by the actual tracker")
        if value["target"]["linear_x"] != 0 or value["target"]["angular_z"] != 0:
            self.after_real_motion = True

    def note_real_application(self, tracker):
        require(tracker.epoch == self.epoch and tracker.robot == self.robot, "application owner differs")
        row = tracker.last_applied
        if not self.after_real_motion and row is not None and (
                row["target"]["linear_x"] != 0 or row["target"]["angular_z"] != 0):
            self.after_real_motion = True
