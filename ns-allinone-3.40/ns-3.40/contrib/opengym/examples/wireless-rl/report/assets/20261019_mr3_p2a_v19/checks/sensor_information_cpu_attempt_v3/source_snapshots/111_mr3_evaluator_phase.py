"""Scalar evaluator-clock/terminal handshake, without ROS, truth or producer drains."""

import copy

from .mr3_episode import TASK_FAILURE_REASONS, timestamp_ns


PHASE_PROTOCOL = "mr3-evaluator-clock-terminal-ack-v1"
QUANTUM_NS = 20_000_000
PHASE_WALL_GUARD_SEC = 10.


def _nanoseconds(value):
    if type(value) is not int or value < 0:
        raise ValueError("invalid_phase_nanoseconds")
    return value


def _request(value, epoch):
    if not isinstance(value, dict) or set(value) != {
            "epoch", "request_id", "target_time_ns"}:
        raise ValueError("invalid_phase_request_fields")
    if value["epoch"] != epoch:
        raise ValueError("wrong_phase_epoch")
    if not isinstance(value["request_id"], str) or not value["request_id"]:
        raise ValueError("invalid_phase_request_id")
    _nanoseconds(value["target_time_ns"])


def _terminal(value, epoch, target, previous):
    if value is None:
        return
    if not isinstance(value, dict) or set(value) != {
            "epoch", "end_sim_time_sec", "termination_reason"}:
        raise ValueError("invalid_phase_terminal_fields")
    if value["epoch"] != epoch:
        raise ValueError("wrong_phase_terminal_epoch")
    if value["termination_reason"] not in TASK_FAILURE_REASONS | {"coverage_reached"}:
        raise ValueError("invalid_phase_terminal_reason")
    end = value["end_sim_time_sec"]
    if type(end) not in (int, float):
        raise ValueError("invalid_phase_terminal_time")
    end = timestamp_ns(end)
    if end < (target if previous is None else previous):
        raise ValueError("phase_terminal_predates_previous_ack")
    if end > target or target - end > QUANTUM_NS:
        raise ValueError("phase_terminal_outside_quantum")


class EvaluatorPhase:
    """One pending request; exact repeats replay their immutable scalar ACK."""

    def __init__(self, epoch):
        self.epoch = epoch
        self.pending = None
        self.responses = {}
        self.last_target_ns = None
        self.last_clock_ns = None

    def _clock(self, clock_ns):
        _nanoseconds(clock_ns)
        if self.last_clock_ns is not None and clock_ns < self.last_clock_ns:
            raise ValueError("evaluator_phase_clock_regressed")
        self.last_clock_ns = clock_ns

    def request(self, request, clock_ns, terminal, wall_ns):
        _request(request, self.epoch)
        self._clock(clock_ns)
        _nanoseconds(wall_ns)
        previous = self.responses.get(request["request_id"])
        if previous is not None:
            if previous[0] != request:
                raise ValueError("phase_request_id_conflict")
            return copy.deepcopy(previous[1])
        if self.pending is not None:
            if self.pending[0] != request:
                raise ValueError("phase_request_pending_conflict")
        else:
            target = request["target_time_ns"]
            if self.last_target_ns is not None and target != self.last_target_ns + QUANTUM_NS:
                raise ValueError("phase_target_not_next_quantum")
            self.pending = (copy.deepcopy(request), wall_ns + round(PHASE_WALL_GUARD_SEC * 1e9))
        return self.poll(clock_ns, terminal, wall_ns)

    def poll(self, clock_ns, terminal, wall_ns):
        self._clock(clock_ns)
        _nanoseconds(wall_ns)
        if self.pending is None:
            return None
        request, deadline = self.pending
        target = request["target_time_ns"]
        if wall_ns >= deadline:
            raise TimeoutError("evaluator_phase_clock_wall_timeout")
        if clock_ns < target:
            return None
        if clock_ns > target:
            raise ValueError("evaluator_phase_clock_ahead_of_target")
        _terminal(terminal, self.epoch, target, self.last_target_ns)
        response = {"schema": PHASE_PROTOCOL, **request, "ok": True,
                    "evaluator_clock_ns": clock_ns,
                    "status": "LIVE" if terminal is None else "TERMINAL",
                    "terminal": copy.deepcopy(terminal)}
        self.responses[request["request_id"]] = (request, copy.deepcopy(response))
        self.last_target_ns = target
        self.pending = None
        return response


class PhaseClient:
    """Require a matching ACK to be consumed once before the next policy quantum."""

    def __init__(self, epoch):
        self.epoch = epoch
        self.number = 0
        self.pending = None
        self.response = None
        self.consumed = {}
        self.last_target_ns = None
        self.terminal = None

    def begin(self, target_ns):
        _nanoseconds(target_ns)
        if self.pending is not None or self.terminal is not None:
            raise ValueError("phase_client_not_ready_for_request")
        if self.last_target_ns is not None and target_ns != self.last_target_ns + QUANTUM_NS:
            raise ValueError("phase_target_not_next_quantum")
        self.number += 1
        self.pending = {"epoch": self.epoch, "request_id": f"phase{self.number}",
                        "target_time_ns": target_ns}
        return copy.deepcopy(self.pending)

    def receive(self, response, physical_ns, clock_ns):
        if not isinstance(response, dict) or response.get("epoch") != self.epoch:
            raise ValueError("wrong_phase_ack_epoch")
        identity = response.get("request_id")
        if not isinstance(identity, str) or not identity:
            raise ValueError("invalid_phase_ack_request_id")
        if identity in self.consumed:
            if response != self.consumed[identity]:
                raise ValueError("phase_ack_duplicate_conflict")
            return False
        if self.pending is None or identity != self.pending["request_id"]:
            raise ValueError("unbound_phase_ack")
        if response.get("ok") is not True:
            raise ValueError("evaluator_phase_rejected: " + str(response.get("error")))
        if set(response) != {"schema", "epoch", "request_id", "target_time_ns", "ok",
                             "evaluator_clock_ns", "status", "terminal"}:
            raise ValueError("invalid_phase_ack_fields")
        target = self.pending["target_time_ns"]
        if (response["schema"] != PHASE_PROTOCOL or response["target_time_ns"] != target
                or type(response["target_time_ns"]) is not int
                or type(response["evaluator_clock_ns"]) is not int
                or response["evaluator_clock_ns"] != target
                or _nanoseconds(physical_ns) != target or _nanoseconds(clock_ns) != target):
            raise ValueError("phase_ack_clock_or_target_mismatch")
        _terminal(response["terminal"], self.epoch, target, self.last_target_ns)
        if response["status"] != ("LIVE" if response["terminal"] is None else "TERMINAL"):
            raise ValueError("phase_ack_status_conflict")
        if self.response is not None and self.response != response:
            raise ValueError("phase_ack_duplicate_conflict")
        self.response = copy.deepcopy(response)
        return True

    def consume(self):
        if self.pending is None or self.response is None:
            raise ValueError("phase_ack_not_received")
        response = self.response
        self.consumed[self.pending["request_id"]] = response
        self.last_target_ns = self.pending["target_time_ns"]
        self.terminal = response["terminal"]
        self.pending = self.response = None
        return copy.deepcopy(response)

    def before_advance(self, physical_ns):
        if (self.pending is not None or self.last_target_ns != _nanoseconds(physical_ns)
                or self.terminal is not None):
            raise ValueError("policy_quantum_requires_consumed_live_phase_ack")
