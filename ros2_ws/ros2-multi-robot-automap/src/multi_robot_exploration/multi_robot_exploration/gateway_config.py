"""Validated application fault configuration; task and safety parameters are excluded."""

from dataclasses import asdict
import json
import math

from .fault_model import FaultConfig


FAULT_DEFAULTS = {
    "network_mode": "ideal", "uplink_loss_rate": 0.0, "downlink_loss_rate": 0.0,
    "uplink_delay_sec": 0.0, "downlink_delay_sec": 0.0, "duplicate_rate": 0.0,
    "reorder_window": 0, "reorder_step_sec": 0.05, "ack_timeout_sec": 5.0,
    "max_retries": 2, "queue_capacity": 0, "drop_message_types": "",
    "blackout_intervals": "[]",
}


def updated_configuration(current, changes):
    if not isinstance(changes, dict) or not changes or changes.keys() - FAULT_DEFAULTS.keys():
        raise ValueError("only the declared communication fault parameters are mutable")
    result = {**current, **changes}
    for name, default in FAULT_DEFAULTS.items():
        value = result[name]
        if type(default) is float:
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError(f"{name} requires a finite number")
            result[name] = float(value)
        elif type(value) is not type(default):
            raise ValueError(f"{name} requires {type(default).__name__}")
    if result["network_mode"] not in ("ideal", "fault"):
        raise ValueError("network_mode must be ideal or fault")
    if result["queue_capacity"] < 0:
        raise ValueError("queue capacity must be non-negative; 0 means 4096")
    # Validate requested faults even while ideal mode overrides their effect.
    configs_for({**result, "network_mode": "fault"}, 1)
    return result


def configs_for(values, seed, epoch=None):
    intervals = json.loads(values["blackout_intervals"])
    if not isinstance(intervals, list) or any(
        not isinstance(pair, list) or len(pair) != 2
        or any(type(x) not in (int, float) for x in pair) for pair in intervals
    ):
        raise ValueError("blackout_intervals requires JSON [[start,end], ...]")
    # Validate relative intervals before translating to the existing mission epoch.
    FaultConfig(blackout_intervals=tuple(tuple(pair) for pair in intervals))
    common = dict(
        duplicate_rate=values["duplicate_rate"], reorder_window=values["reorder_window"],
        reorder_step_sec=values["reorder_step_sec"], ack_timeout_sec=values["ack_timeout_sec"],
        max_retries=values["max_retries"], queue_capacity=values["queue_capacity"] or 4096,
        drop_types=tuple(filter(None, (x.strip() for x in values["drop_message_types"].split(",")))),
        blackout_intervals=tuple((epoch + a, epoch + b) for a, b in intervals) if epoch is not None else (),
    )
    configs = {}
    for direction, mask in (("uplink", 0x13579BDF), ("downlink", 0x2468ACE0)):
        settings = dict(common, loss_rate=values[f"{direction}_loss_rate"],
                        delay_sec=values[f"{direction}_delay_sec"], seed=seed ^ mask)
        if values["network_mode"] == "ideal":
            settings.update(loss_rate=0.0, delay_sec=0.0, duplicate_rate=0.0,
                            reorder_window=0, drop_types=(), blackout_intervals=(), queue_capacity=4096)
        configs[direction] = FaultConfig(**settings)
    return configs


def configuration_snapshot(values, transports, revision, now):
    return {"revision": revision, "effective_sim_time": now, "requested": dict(values),
            "effective": {key: asdict(transport.config) for key, transport in transports.items()},
            "semantics": "in-flight attempts retain their transmission configuration; new attempts use this revision"}
