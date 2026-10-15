#!/usr/bin/env python3
"""Reproduce v6 float-time defects using frozen source and a pure CPU harness."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import types


FREEZE = "c8d483228ecb0105c905459578eddbb4a23d4520"
ROS = "ros2_ws/ros2-multi-robot-automap/"
PACKAGE = ROS + "src/multi_robot_exploration/multi_robot_exploration/"


def ns(value):
    return round(value * 1e9)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; preserve the original diagnosis")
    root = next(parent for parent in Path(__file__).resolve().parents
                if (parent / ".git").exists())
    sources = {}
    for relative in (PACKAGE + "mr3_protocol.py", PACKAGE + "mr3_adapter.py",
                     PACKAGE + "mr3_observation.py", ROS + "scripts/mr3_env_worker.py"):
        payload = subprocess.check_output(["git", "show", FREEZE + ":" + relative], cwd=root)
        sources[relative] = {"sha256": hashlib.sha256(payload).hexdigest(),
                             "source": FREEZE + ":" + relative}
        if relative.endswith("mr3_protocol.py"):
            module = types.ModuleType("frozen_v6_protocol")
            sys.modules[module.__name__] = module
            exec(compile(payload, FREEZE + ":" + relative, "exec"), module.__dict__)
    dispatcher = module.GoalDispatcher
    cases = []

    def setup(start, accepted=False, legacy_expiry=False):
        instance = dispatcher("boundary", lambda event: None)
        expiry = start + 2. if legacy_expiry else (ns(start) + 2_000_000_000) / 1e9
        assert instance.submit("tb1", "GOAL", start, 1, 1, expiry,
                               {"x": 1., "y": 2.}, created_at=start) == "sent"
        goal_id = instance.states["tb1"].goal_id
        if accepted:
            assert instance.on_accept("tb1", goal_id, True, start) == "active"
        return instance, goal_id

    def renew(instance, goal_id, start, count):
        for step in range(1, count + 1):
            now = (ns(start) + step * 1_000_000_000) / 1e9
            assert instance.renew("tb1", goal_id, "boundary", now,
                                  (ns(now) + 2_000_000_000) / 1e9) == "renewed"

    for kind, start, duration in (("response_timeout", 6.08, 10),
                                  ("execution_timeout", 5.07, 60)):
        instance, goal_id = setup(start, kind == "execution_timeout")
        renew(instance, goal_id, start, duration - 1)
        end = (ns(start) + duration * 1_000_000_000) / 1e9
        instance.tick(end)
        cases.append({"case": kind, "start": start, "end": end,
                      "float_delta": end - start, "delta_ns": ns(end) - ns(start),
                      "observed_failure": instance.states["tb1"].failure,
                      "required_failure": "navigation_" + kind,
                      "owner_retained": not instance.closed})
    instance, goal_id = setup(1.08, True)
    renew(instance, goal_id, 1.08, 5)
    assert instance.submit("tb1", "WAIT", 6.08, 2, 2, 8.08, created_at=6.08) == "waiting"
    instance.tick(16.08)
    cases.append({"case": "cancel_timeout", "start": 6.08, "end": 16.08,
                  "float_delta": 16.08 - 6.08, "delta_ns": ns(16.08) - ns(6.08),
                  "observed_failure": instance.states["tb1"].failure,
                  "required_failure": "navigation_cancel_timeout",
                  "owner_retained": not instance.closed})
    instance, goal_id = setup(5.03, True)
    renew(instance, goal_id, 5.03, 5)
    result = instance.submit("tb1", "WAIT", 10.03, 2, 2, 12.03, created_at=10.03)
    cases.append({"case": "commitment", "accepted_at": 5.03, "true_end": 10.03,
                  "generated_commitment_until": instance.states["tb1"].commitment_until,
                  "delta_ns": ns(10.03) - ns(5.03), "observed_wait_result": result,
                  "required_wait_result": "waiting",
                  "old_observation_mask_locked": instance.states["tb1"].commitment_until > 10.03})
    instance, goal_id = setup(6.03, True, True)
    instance.tick(8.03)
    cases.append({"case": "lease", "created": 6.03, "generated_expiry": 6.03 + 2.,
                  "true_expiry": 8.03, "delta_ns": ns(8.03) - ns(6.03),
                  "observed_failure": instance.states["tb1"].failure,
                  "required_failure": "goal_lease_expired", "owner_retained": not instance.closed})
    cases.append({"case": "heartbeat", "previous": 5.07, "now": 5.27,
                  "float_delta": 5.27 - 5.07, "delta_ns": ns(5.27) - ns(5.07),
                  "observed_due": 5.27 - 5.07 >= .2, "required_due": True})
    for created, expiry in ((254.6, 256.6), (255.6, 257.6)):
        cases.append({"case": "adapter_command_ttl", "created": created, "expires": expiry,
                      "float_delta": expiry - created, "ttl_ns": ns(expiry) - ns(created),
                      "observed_adapter_time_valid": created <= created < expiry
                      and 0 < expiry - created <= 2., "required_adapter_time_valid": True})
    reproduced = (all(row.get("observed_failure") is None for row in cases
                      if "observed_failure" in row)
                  and cases[3]["observed_wait_result"] == "commitment_locked"
                  and cases[3]["old_observation_mask_locked"] is True
                  and cases[5]["observed_due"] is False
                  and all(row["observed_adapter_time_valid"] is False for row in cases[6:]))
    result = {"schema": "mr3-v6-command-time-boundary-diagnostic-v1", "freeze": FREEZE,
              "scope": "pure arithmetic and frozen unmodified GoalDispatcher; no ROS/native run",
              "source_sha256": sources, "cases": cases,
              "defects_reproduced": reproduced, "cases_count": len(cases),
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "command": [sys.executable, "-B", str(Path(__file__)),
                          *(sys.argv[1:] if argv is None else argv)]}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"defects_reproduced": reproduced, "cases_count": len(cases),
                      "output": str(args.output)}))
    return 0 if reproduced else 1


if __name__ == "__main__":
    raise SystemExit(main())
