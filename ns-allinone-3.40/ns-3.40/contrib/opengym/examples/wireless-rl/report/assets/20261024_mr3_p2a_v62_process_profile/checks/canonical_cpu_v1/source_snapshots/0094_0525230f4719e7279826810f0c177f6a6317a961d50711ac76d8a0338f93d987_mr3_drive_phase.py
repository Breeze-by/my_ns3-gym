"""Exact native target-storage receipts, independent of policy observations."""

import math


PROTOCOL = "mr3-drive-target-consumed-v1"
ROBOTS = ("tb1", "tb2", "tb3")
WALL_GUARD_SEC = 10.


def valid_output(value):
    return (isinstance(value, dict) and set(value) == {"linear_x", "angular_z"}
            and all(type(value[key]) in (int, float) and abs(value[key]) <= limit
                    and math.isfinite(value[key])
                    for key, limit in (("linear_x", .26), ("angular_z", .8))))


class DrivePhaseClient:
    """Keep real receipts until their matching physical boundary consumes them.

    Receipt means the driver stored a tagged target. Physical response still
    requires the separately recorded wheel instructions and body measurements.
    """

    def __init__(self, epoch):
        self.epoch = epoch
        self.latest = {}
        self.pending = {name: {} for name in ROBOTS}

    def receive(self, value):
        if not isinstance(value, dict):
            raise ValueError("invalid native drive receipt fields")
        if value.get("epoch") != self.epoch:
            return False
        keys = {"schema", "epoch", "robot", "clock_ns", "decision_sequence",
                "source_clock_ns", "cmd_seq", "linear_x", "angular_z"}
        if (set(value) != keys or value.get("schema") != PROTOCOL
                or value.get("robot") not in ROBOTS
                or any(type(value.get(key)) is not int or value[key] < minimum
                       for key, minimum in (("clock_ns", 0), ("source_clock_ns", 0),
                                            ("decision_sequence", 1), ("cmd_seq", 1)))
                or value["source_clock_ns"] > value["clock_ns"]
                or not valid_output({key: value[key] for key in ("linear_x", "angular_z")})):
            raise ValueError("invalid native drive receipt")
        name = value["robot"]
        previous = self.latest.get(name)
        if previous is not None:
            if value == previous:
                return False
            if (value["cmd_seq"] <= previous["cmd_seq"]
                    or value["decision_sequence"] <= previous["decision_sequence"]
                    or value["source_clock_ns"] < previous["source_clock_ns"]
                    or value["clock_ns"] < previous["clock_ns"]):
                raise ValueError("native drive receipt regressed or changed identity")
        self.latest[name] = dict(value)
        self.pending[name][value["decision_sequence"]] = dict(value)
        return True

    def matching(self, motion):
        if (not isinstance(motion, dict) or motion.get("epoch") != self.epoch
                or type(motion.get("clock_ns")) is not int
                or motion["clock_ns"] < 0
                or not isinstance(motion.get("decision_sequences"), dict)
                or set(motion.get("decision_sequences", {})) != set(ROBOTS)
                or not isinstance(motion.get("outputs"), dict)
                or set(motion.get("outputs", {})) != set(ROBOTS)):
            raise ValueError("invalid exact motion boundary for drive consumption")
        target = motion["clock_ns"]
        result = {}
        for name in ROBOTS:
            sequence = motion["decision_sequences"][name]
            output = motion["outputs"][name]
            if type(sequence) is not int or sequence <= 0 or not valid_output(output):
                raise ValueError("invalid expected native drive target")
            ack = self.pending[name].get(sequence)
            if ack is None:
                return None
            if self.latest.get(name) != ack:
                raise ValueError("native drive target changed after matching receipt")
            if (ack["source_clock_ns"] != target or ack["clock_ns"] != target
                    or any(ack[key] != output[key] for key in ("linear_x", "angular_z"))):
                raise ValueError("native drive receipt does not match paused guard target")
            result[name] = dict(ack)
        return result

    def consume(self, motion):
        result = self.matching(motion)
        if result is None:
            raise RuntimeError("three native drive receipts are incomplete")
        for name in ROBOTS:
            sequence = result[name]["decision_sequence"]
            self.pending[name] = {key: row for key, row in self.pending[name].items()
                                  if key > sequence}
        return result
