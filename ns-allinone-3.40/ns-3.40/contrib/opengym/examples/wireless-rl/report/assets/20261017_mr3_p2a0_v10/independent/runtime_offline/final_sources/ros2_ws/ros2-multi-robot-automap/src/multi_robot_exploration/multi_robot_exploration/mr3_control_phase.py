"""Typed requests for a paused state -> obstacle -> guard execution boundary."""

import copy
import hashlib
import json

from multi_robot_exploration.mr3_drive_phase import ROBOTS, valid_output


PROTOCOL = "mr3-controlled-execution-phase-v1"
WALL_GUARD_SEC = 10.
COMPONENTS = ("state", "peer", "motion")


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def valid_motion_status(value, epoch, target, stop=False):
    if (not isinstance(value, dict) or value.get("schema") != "mr3-motion-safety-status-v1"
            or value.get("epoch") != epoch or type(value.get("clock_ns")) is not int
            or value["clock_ns"] != target or type(value.get("ready")) is not bool
            or value.get("completion_scope") != "publication_and_local_topic_receipt"
            or not isinstance(value.get("decision_sequences"), dict)
            or set(value["decision_sequences"]) != set(ROBOTS)
            or any(type(sequence) is not int or sequence <= 0
                   for sequence in value["decision_sequences"].values())
            or not isinstance(value.get("outputs"), dict)
            or set(value["outputs"]) != set(ROBOTS)
            or any(not valid_output(output) for output in value["outputs"].values())):
        return False
    if stop:
        return (value.get("phase_kind") == "stop" and value["ready"] is False
                and all(output == {"linear_x": 0., "angular_z": 0.}
                        for output in value["outputs"].values()))
    return "phase_kind" not in value


class ControlPhaseClient:
    """One outstanding real request, with immutable, typed, idempotent receipts.

    The worker owns the ordering between components. A receipt acknowledges
    actual node callbacks/publication or target storage; never physical motion.
    """

    def __init__(self, epoch):
        if not isinstance(epoch, str) or not epoch:
            raise ValueError("execution epoch is required")
        self.epoch = epoch
        self.number = 0
        self.pending = None
        self.response = None
        self.completed = {}
        self.abandoned = set()
        self.last_clock = None
        self.stopped = False

    def begin(self, component, operation, target, request_id=None, **references):
        if (component not in COMPONENTS or operation not in ("takeover", "commit", "stop")
                or (operation == "stop" and component != "motion")
                or type(target) is not int or target < 0
                or (self.last_clock is not None and target < self.last_clock)
                or self.pending is not None):
            raise ValueError("invalid or overlapping execution phase request")
        if self.stopped and operation != "stop":
            raise ValueError("a stopped execution phase cannot resume")
        if set(references) & {"schema", "epoch", "target_time_ns", "operation"}:
            raise ValueError("execution references cannot replace request identity")
        self.number += 1
        request_id = request_id if request_id is not None else f"control{self.number}"
        if (not isinstance(request_id, str) or not request_id
                or (component, request_id) in self.completed
                or (component, request_id) in self.abandoned):
            raise ValueError("execution request identity was already used")
        request = {"schema": f"mr3-{component}-phase-request-v1", "epoch": self.epoch,
                   "request_id": request_id, "target_time_ns": target,
                   "operation": operation, **copy.deepcopy(references)}
        if component == "motion":
            request["schema"] = "mr3-motion-control-request-v1"
        canonical(request)
        self.pending = {"component": component, "request": request}
        self.response = None
        self.last_clock = target
        if operation == "stop":
            self.stopped = True
        return copy.deepcopy(request)

    def receive(self, component, value, physical_ns, clock_ns):
        if not isinstance(value, dict):
            raise ValueError("execution phase receipt must be an object")
        if value.get("epoch") != self.epoch:
            return False
        request_id = value.get("request_id")
        if (component, request_id) in self.abandoned:
            if (value.get("ok") is False and not (
                    component == "state" and value.get("error") == "state_phase_task_terminal"
                    and value.get("scope") == "terminal_cancelled_uncommitted_state_phase"
                    and isinstance(value.get("terminal_notice"), dict))):
                raise ValueError("abandoned execution request reported an actual failure")
            return False
        previous = self.completed.get((component, request_id))
        if previous is not None:
            if previous != hashlib.sha256(canonical(value).encode()).hexdigest():
                raise ValueError("completed execution receipt changed")
            return False
        pending = self.pending
        if (pending is None or pending["component"] != component
                or request_id != pending["request"]["request_id"]):
            raise ValueError("unexpected execution phase receipt")
        request = pending["request"]
        target = request["target_time_ns"]
        schema = ("mr3-motion-control-ack-v1" if component == "motion"
                  else f"mr3-{component}-phase-ack-v1")
        if (value.get("schema") != schema or value.get("operation") != request["operation"]
                or type(value.get("target_time_ns")) is not int
                or value["target_time_ns"] != target or type(value.get("clock_ns")) is not int
                or not 0 <= value["clock_ns"] <= target or type(physical_ns) is not int
                or type(clock_ns) is not int or physical_ns != target or clock_ns != target
                or type(value.get("ok")) is not bool):
            raise ValueError("execution phase clock/identity differs")
        if value["ok"] is True and value["clock_ns"] != target:
            raise ValueError("successful execution phase did not reach the target clock")
        if value["ok"] is False:
            if not isinstance(value.get("error"), str) or not value["error"]:
                raise ValueError("execution failure receipt needs an error")
            self.stopped = True
        elif component == "motion":
            status = value.get("status")
            stop = isinstance(status, dict) and status.get("phase_kind") == "stop"
            if (request["operation"] == "stop" and not stop) or not valid_motion_status(
                    status, self.epoch, target, stop=stop):
                raise ValueError("execution motion receipt has an invalid status")
            if stop:
                self.stopped = True
        elif request["operation"] == "commit":
            state = value if component == "state" else value.get("state_commit")
            if (not isinstance(state, dict) or type(state.get("state_sequence")) is not int
                    or state["state_sequence"] <= 0
                    or not isinstance(state.get("bundle_sha256"), str)
                    or len(state["bundle_sha256"]) != 64
                    or any(c not in "0123456789abcdef" for c in state["bundle_sha256"])):
                raise ValueError("execution state watermark is invalid")
            if component == "peer" and canonical(state) != canonical(request.get("state_commit")):
                raise ValueError("peer receipt is bound to a different state commit")
        if self.response is not None and canonical(self.response) != canonical(value):
            raise ValueError("execution phase receipt changed while pending")
        self.response = copy.deepcopy(value)
        return True

    def consume(self, allow_error=False):
        if self.pending is None or self.response is None:
            raise RuntimeError("execution phase receipt is incomplete")
        component = self.pending["component"]
        response = copy.deepcopy(self.response)
        self.completed[(component, response["request_id"])] = hashlib.sha256(
            canonical(response).encode()).hexdigest()
        self.pending = None
        self.response = None
        if response["ok"] is not True and not allow_error:
            raise RuntimeError("execution phase rejected: " + canonical(response))
        return response

    def abandon_for_stop(self):
        """Retain failed request identity while allowing only a permanent zero stop."""
        if self.pending is not None:
            self.abandoned.add((self.pending["component"], self.pending["request"]["request_id"]))
        self.pending = None
        self.response = None
        self.stopped = True
