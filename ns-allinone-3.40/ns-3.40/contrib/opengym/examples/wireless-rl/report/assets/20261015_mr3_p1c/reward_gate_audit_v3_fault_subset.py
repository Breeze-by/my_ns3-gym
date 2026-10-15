#!/usr/bin/env python3
"""Replay v3 scalar checks for the three complete cells of a declared fault probe.

The killed four-step prefix is linked to its separate primary audits. It never
receives this helper's complete reward/contact/clean-closure credit.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HELPER_SHA256 = "895395075a881c6d74b809100e198be52a3c05a6710d24d873020b87223ff665"


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def load(path):
    return json.loads(path.read_text())


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--main-prefix-audit", action="append", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; choose a new path")
    helper = Path(__file__).with_name("reward_gate_audit_v3.py")
    require(hashlib.sha256(helper.read_bytes()).hexdigest() == HELPER_SHA256,
            "immutable scalar helper SHA mismatch")
    spec = importlib.util.spec_from_file_location("immutable_scalar_v3", helper)
    audit = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(audit)
    metadata = load(args.directory / "benchmark_metadata.json")
    require(metadata.get("fault_probe") is True and metadata.get("workers") == 2
            and metadata.get("steps_per_episode") == 8 and metadata.get("freeze") == args.freeze
            and metadata.get("schedule") == [["open", 101], ["open", 101]]
            and (args.directory / "benchmark_summary.json").is_file(),
            "not the closed declared two-worker/eight-step fault workload")
    episodes, excluded, errors = [], [], []
    for saved in sorted(args.directory.glob("worker*/episode*/supervisor_metadata.json")):
        directory = saved.parent
        worker = load(directory / "metadata.json")
        shutdown = load(directory / "supervisor_shutdown.json")
        require(worker.get("freeze") == args.freeze, "mixed episode source freeze")
        if (directory / "summary.json").is_file():
            require(shutdown.get("worker_returncode") == 0
                    and shutdown.get("forced_shutdown") is False
                    and shutdown.get("failed_sample") is False, "normal cell is not clean")
            result = audit.audit_episode(directory, args.freeze)
            require(result["transitions"] == 8, "normal cell has wrong sampling budget")
            episodes.append(result)
            errors.extend(result["errors"])
        else:
            require(directory.parent.name == "worker0" and directory.name == "episode001_open_101"
                    and shutdown.get("worker_returncode") == -9
                    and shutdown.get("forced_shutdown") is True
                    and shutdown.get("failed_sample") is True,
                    "excluded sample is not the declared killed worker prefix")
            references = []
            for path in args.main_prefix_audit:
                primary = load(path)
                require(primary.get("passed") is True and primary.get("epoch") == worker["epoch"]
                        and primary.get("freeze") == args.freeze
                        and primary.get("expected_infrastructure_fault") is True
                        and primary.get("complete_episode_credit") is False
                        and primary["transitions"]["complete"] is False
                        and primary["transitions"]["transition_count"] == 4,
                        "primary prefix reference does not match the excluded killed cell")
                references.append({"path": str(path),
                                   "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                   "schema": primary["schema"]})
            excluded.append({"directory": str(directory), "epoch": worker["epoch"],
                             "primary_prefix_transition_count": 4,
                             "primary_prefix_audit_sources": references,
                             "complete_episode_credit": False,
                             "aux_complete_reward_contact_clean_closure_credit": False})
    require(len(episodes) == 3 and len(excluded) == 1, "fault subset is incomplete")
    epochs = [row["epoch"] for row in episodes] + [row["epoch"] for row in excluded]
    identities = [(row["pid_identity"]["pid"], row["pid_identity"]["start_ticks"])
                  for row in episodes]
    require(len(set(epochs)) == 4 and len(set(identities)) == 3, "reset identity reused")
    result = {"schema": "mr3-reward-fault-completed-subset-audit-v3",
              "scope": "only three complete eight-step cells; no whole-fault reward audit, "
                       "spatial truth replay or independent 18-contact timing proof",
              "freeze": args.freeze, "entry_point": "reward_gate_audit_v3.audit_episode",
              "helper_sha256": HELPER_SHA256,
              "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "command": [sys.executable, "-B", str(Path(__file__)),
                          *(sys.argv[1:] if argv is None else argv)],
              "episodes": episodes, "excluded_killed_prefix": excluded,
              "completed_subset_transitions": 24, "reset_epoch_and_pid_unique": True,
              "completed_subset_scalar_checks_passed": not errors,
              "whole_fault_benchmark_reward_audit_performed": False, "errors": errors}
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, allow_nan=False)
        output.write("\n")
    print(json.dumps({"completed_subset_scalar_checks_passed": not errors,
                      "output": str(args.output), "errors": errors}))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
