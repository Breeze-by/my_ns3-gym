"""Independent replay of paused evaluator-clock/terminal ACK receipts.

This proves serialization after the evaluator freezes its terminal time. It
does not claim that all safety producers have drained at each physics boundary.
The original contact, command, scalar and 20ms terminal gates remain separate.
"""

from decimal import Decimal
import gzip
import hashlib
import json
from pathlib import Path


METHOD = "mr3-evaluator-clock-terminal-receipt-audit-v1"
PROTOCOL = "mr3-evaluator-clock-terminal-ack-v1"
QUANTUM_NS = 20_000_000


def require(value, message):
    if not value:
        raise ValueError(message)


def ns(value):
    require(type(value) in (int, float), "phase time is not numeric")
    result = Decimal(str(value)) * 1_000_000_000
    require(result.is_finite() and result == result.to_integral_value(),
            "phase time is not exact finite nanoseconds")
    return int(result)


def read(directory, name, lines=False):
    path = directory / name
    if not path.exists():
        path = path.with_name(path.name + ".gz")
    payload = path.read_bytes()
    decoded = gzip.decompress(payload) if path.suffix == ".gz" else payload
    value = ([json.loads(line) for line in decoded.decode().splitlines() if line.strip()]
             if lines else json.loads(decoded))
    return value, {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest(),
                   "decoded_sha256": hashlib.sha256(decoded).hexdigest()}


def audit_episode(directory):
    directory = Path(directory)
    proof = {}

    def load(name, lines=False):
        value, proof[name] = read(directory, name, lines)
        return value

    metadata = load("metadata.json")
    epoch = metadata["epoch"]
    require(metadata.get("evaluator_phase_protocol") == PROTOCOL,
            "native episode does not declare reviewed evaluator phase protocol")
    worker = load("evaluator_phase_worker.jsonl", True)
    evaluator = load("evaluator_phase_evaluator.jsonl", True)
    transitions = load("transitions.jsonl", True)
    physics = load("physics.jsonl", True)
    evaluation = load(epoch + ".json")
    require(transitions and transitions[0]["kind"] == "reset", "phase reset missing")
    start = transitions[0]["info"]["release_time_ns"]
    end = ns(transitions[-1]["snapshot"]["source_stamp"])
    require(type(start) is int and end >= start and (end - start) % QUANTUM_NS == 0,
            "phase snapshot boundaries are not aligned")
    targets = list(range(start, end + 1, QUANTUM_NS))
    policy_physics = [row for row in physics
                      if row["start_time_ns"] >= start and row["end_time_ns"] <= end
                      and row["steps"] > 0]
    require(len(policy_physics) == len(targets) - 1,
            "phase ACK count does not bind every native policy quantum")
    for index, row in enumerate(policy_physics):
        require(row["epoch"] == epoch and row["ok"] is True and row["paused"] is True
                and row["steps"] == 20 and row["step_ns"] == 1_000_000
                and row["end_iterations"] - row["start_iterations"] == 20
                and row["start_time_ns"] == targets[index]
                and row["end_time_ns"] == targets[index + 1],
                "phase receipt is not the matching paused 20-tick physical step")

    requests, published, received, consumed, permits = {}, {}, {}, {}, []
    for rows, side in ((worker, "worker"), (evaluator, "evaluator")):
        previous_wall = -1
        previous_clock = -1
        for row in rows:
            wall = row["wall_monotonic_ns"]
            require(row["epoch"] == epoch and type(wall) is int and wall >= previous_wall,
                    "phase receipt epoch/wall order differs")
            previous_wall = wall
            clock = row[side + "_clock_ns"]
            require(type(clock) is int and clock >= max(0, previous_clock),
                    "phase receipt real clock is invalid or regresses")
            previous_clock = clock
            kind = row["kind"]
            if side == "worker" and kind == "advance_permitted":
                permits.append(row)
                continue
            expected = ({"request", "ack_received", "ack_consumed"} if side == "worker"
                        else {"request_received", "ack_published"})
            require(kind in expected, "unknown phase receipt kind")
            payload = row["request" if kind in ("request", "request_received") else "ack"]
            identity = payload["request_id"]
            if kind in ("request", "request_received"):
                require(clock <= payload["target_time_ns"],
                        "phase request receiver clock is already ahead of target")
                key = (side, identity)
                require(key not in requests, "duplicate phase request receipt")
                requests[key] = row
            else:
                destination = (published if kind == "ack_published" else
                               consumed if kind == "ack_consumed" else received)
                if destination is received:
                    destination.setdefault(identity, []).append(row)
                else:
                    require(identity not in destination, "duplicate phase publish/consume")
                    destination[identity] = row

    identities = ["phase" + str(index + 1) for index in range(len(targets))]
    require(set(requests) == {(side, identity) for side in ("worker", "evaluator")
                              for identity in identities}
            and set(published) == set(received) == set(consumed) == set(identities),
            "phase requests/published/received/consumed identities do not close")
    require(len(permits) == len(targets) - 1, "phase advance permits do not close")
    previous_consumed = None
    terminal = None
    for index, (identity, target) in enumerate(zip(identities, targets)):
        request = {"epoch": epoch, "request_id": identity, "target_time_ns": target}
        left, right = requests[("worker", identity)], requests[("evaluator", identity)]
        published_row, consumed_row = published[identity], consumed[identity]
        ack = published_row["ack"]
        require(left["request"] == right["request"] == request,
                "phase request target/epoch/identity differs")
        require(set(ack) == {"schema", "epoch", "request_id", "target_time_ns", "ok",
                             "evaluator_clock_ns", "status", "terminal"}
                and ack["schema"] == PROTOCOL and ack["ok"] is True
                and all(ack[key] == value for key, value in request.items())
                and type(ack["target_time_ns"]) is int
                and type(ack["evaluator_clock_ns"]) is int
                and ack["evaluator_clock_ns"] == target
                and published_row["evaluator_clock_ns"] == target,
                "phase ACK did not prove evaluator real clock exactly at target")
        require(terminal is None, "phase request followed a consumed terminal ACK")
        terminal = ack["terminal"]
        require(ack["status"] == ("LIVE" if terminal is None else "TERMINAL"),
                "phase ACK status differs from terminal")
        if terminal is not None:
            require(set(terminal) == {"epoch", "end_sim_time_sec", "termination_reason"}
                    and terminal["epoch"] == epoch
                    and ns(terminal["end_sim_time_sec"]) == ns(evaluation["end_sim_time_sec"])
                    and terminal["termination_reason"] == evaluation["termination_reason"],
                    "phase terminal differs from immutable evaluator terminal")
            frozen = ns(terminal["end_sim_time_sec"])
            require(index > 0 and targets[index - 1] <= frozen <= target
                    and target - frozen <= QUANTUM_NS,
                    "phase terminal predates previous ACK or exceeds one quantum")
        require(left["wall_monotonic_ns"] <= right["wall_monotonic_ns"]
                <= published_row["wall_monotonic_ns"], "phase request/publication order differs")
        for row in received[identity]:
            duplicate_after_consume = (row["wall_monotonic_ns"]
                                       >= consumed_row["wall_monotonic_ns"])
            require(row["ack"] == ack
                    and row["worker_clock_ns"] == row["worker_physical_ns"]
                    and (target <= row["worker_clock_ns"] <= end if duplicate_after_consume
                         else row["worker_clock_ns"] == target)
                    and row["wall_monotonic_ns"] >= published_row["wall_monotonic_ns"],
                    "phase received ACK has wrong payload/clock/order")
        require(consumed_row["ack"] == ack
                and consumed_row["worker_clock_ns"] == target
                and consumed_row["worker_physical_ns"] == target
                and left["worker_clock_ns"] == left["worker_physical_ns"] == target
                and min(row["wall_monotonic_ns"] for row in received[identity])
                <= consumed_row["wall_monotonic_ns"],
                "phase ACK was not received then consumed at paused boundary")
        if previous_consumed is not None:
            permit = permits[index - 1]
            require(permit["worker_clock_ns"] == permit["worker_physical_ns"]
                    == target - QUANTUM_NS
                    and permit["next_target_time_ns"] == target
                    and previous_consumed["wall_monotonic_ns"] <= permit["wall_monotonic_ns"]
                    <= left["wall_monotonic_ns"],
                    "physical advance preceded consumption of the previous LIVE ACK")
        previous_consumed = consumed_row
    return {"method": METHOD, "passed": True, "epoch": epoch,
            "initial_and_policy_acks": len(targets), "policy_quanta": len(policy_physics),
            "terminal_ack": terminal, "source_receipts": proof,
            "duplicate_scope": ("exact stale ACK deliveries allowed; repeated request/publication "
                                "receipts fail this single-publication audit"),
            "scope": "frozen evaluator terminal serialization; no producer-drain/network claim"}
