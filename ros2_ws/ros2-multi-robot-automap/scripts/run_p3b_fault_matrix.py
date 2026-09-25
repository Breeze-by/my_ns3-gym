#!/usr/bin/env python3
"""Run the deterministic P3B application-transport fault matrix.

This gate is intentionally ROS/Gazebo independent.  It proves the protocol
semantics before any ns-3 bridge is introduced.
"""

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

from multi_robot_exploration.fault_model import (
    DeterministicFaultTransport,
    FaultConfig,
)


def envelope(sequence):
    return SimpleNamespace(message_type="map_snapshot", sequence=sequence)


def run_matrix():
    rows = []
    for seed in (101, 202, 303):
        for direction in ("uplink", "downlink"):
            for loss_rate in (0.0, 0.1, 1.0):
                for delay_sec in (0.0, 0.5, 2.0):
                    events = []
                    transport = DeterministicFaultTransport(
                        FaultConfig(
                            loss_rate=loss_rate,
                            delay_sec=delay_sec,
                            seed=seed,
                            ack_timeout_sec=0.25,
                            max_retries=2,
                        ),
                        events.append,
                    )
                    transport.enqueue(
                        f"{direction}-{seed}-1", envelope(1), direction, 0.0,
                        reliable=True, ttl_sec=10.0,
                    )
                    deliveries = transport.poll(delay_sec)
                    drops = [
                        event for event in events if event["event"] == "drop"
                    ]
                    rows.append(
                        {
                            "seed": seed,
                            "direction": direction,
                            "loss_rate": loss_rate,
                            "delay_sec": delay_sec,
                            "deliveries_at_delay": len(deliveries),
                            "drop_events": len(drops),
                            "events": events,
                        }
                    )

    reorder_events = []
    reorder = DeterministicFaultTransport(
        FaultConfig(delay_sec=0.0, reorder_window=2, seed=7),
        reorder_events.append,
    )
    for sequence in (1, 2):
        reorder.enqueue(f"reorder-{sequence}", envelope(sequence), "uplink", 0.0)
    reordered = [attempt.envelope.sequence for attempt in reorder.poll(0.1)]

    ttl_events = []
    ttl = DeterministicFaultTransport(
        FaultConfig(delay_sec=2.0, seed=9), ttl_events.append
    )
    ttl.enqueue("ttl", envelope(1), "uplink", 0.0, ttl_sec=0.5)
    assert ttl.poll(2.0) == []
    assert ttl_events[-1]["reason"] in ("expired", "expired_in_flight", "expired_before_tx")

    loss100 = next(
        row for row in rows
        if row["direction"] == "uplink"
        and row["loss_rate"] == 1.0
        and row["delay_sec"] == 0.0
    )
    assert loss100["deliveries_at_delay"] == 0
    retry_events = []
    retry = DeterministicFaultTransport(
        FaultConfig(loss_rate=1.0, ack_timeout_sec=0.25, max_retries=2),
        retry_events.append,
    )
    retry.enqueue("retry", envelope(1), "uplink", 0.0, reliable=True)
    for when in (0.0, 0.25, 0.5, 0.75):
        retry.poll(when)
    assert sum(event["event"] == "drop" for event in retry_events) == 3
    assert not retry.acknowledge("retry", 1.0)
    assert reordered == [2, 1]
    return {
        "schema_version": 1,
        "seeds": [101, 202, 303],
        "matrix": rows,
        "reorder_sequence": reordered,
        "ttl_drop_reason": ttl_events[-1]["reason"],
        "status": "PASS",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("log/p3b_fault_matrix_20260925.json"),
    )
    args = parser.parse_args()
    result = run_matrix()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "output": str(args.output)}))


if __name__ == "__main__":
    raise SystemExit(main())
