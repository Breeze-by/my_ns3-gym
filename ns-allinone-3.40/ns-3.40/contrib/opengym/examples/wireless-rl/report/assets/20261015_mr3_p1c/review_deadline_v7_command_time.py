#!/usr/bin/env python3
"""Read only the closed deadline probe; replay commands and scalar terminal reward.

This adds a scoped independent review, not native, contact-timing, spatial truth,
policy, or 95% success credit. Existing auditors, bindings and results stay intact.
"""

import argparse
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys


TIME_SHA = "4787ca8d2e6b4d7ba06b3d5a3c1ead82fe6f079485a790c5b940f2ba7636c3b9"


def load_time_helper():
    path = Path(__file__).with_name("audit_command_time_v7.py")
    if hashlib.sha256(path.read_bytes()).hexdigest() != TIME_SHA:
        raise ValueError("immutable command-time helper changed")
    spec = importlib.util.spec_from_file_location("deadline_v7_time_helper", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def review_rows(time_helper, audit, transitions, events, epoch):
    require, ns = audit.require, audit.nanoseconds
    require(len(transitions) == 301 and transitions[0]["kind"] == "reset"
            and all(row["kind"] == "step" for row in transitions[1:]),
            "expected one reset and300 completed API steps")
    timing = time_helper.audit_command_times(events, transitions, epoch, auditor=audit)
    require(timing["passed"] is True and timing["commands_checked"] ==
            timing["accepted_commands"] == 300 and timing["rejected_commands"] == 0,
            "all300 commands must be legal and accepted")
    reset = transitions[0]
    initial = reset["info"]["reward_diagnostics"]
    start_ns = ns(reset["snapshot"]["source_stamp"])
    require(reset["info"]["epoch"] == epoch and initial["sequence"] == 0
            and initial["reward"] == 0 and initial["initial_correct_free_cells"] > 0,
            "initial free cells must not receive startup reward")
    receipts = {}
    for line, event in enumerate(events, 1):
        if event["kind"] == "action":
            payload = event["payload"]
            require(payload["action"] == 888 and payload["choices"] == [8, 8, 8]
                    and payload["results"] == {name: "kept" for name in audit.ROBOTS},
                    "a KEEP command did not produce three kept receipts")
            receipts[payload["command_id"]] = (line, event)
    require(not any(event["kind"] == "native_send" or event["kind"] == "protocol"
                    and event["payload"].get("type") == "send_goal" for event in events),
            "deadline KEEP probe unexpectedly sent a navigation goal")
    terms, failure_steps, counterexamples = {}, [], []
    for sequence, row in enumerate(transitions[1:], 1):
        info, reward = row["info"], row["info"]["reward_diagnostics"]
        command = info["command"]
        line, receipt = receipts[command["command_id"]]
        expected_start = start_ns + (sequence - 1) * 1_000_000_000
        expected_end = expected_start + 1_000_000_000
        require(command["epoch"] == epoch and command["command_id"] == sequence
                and command["action"] == 888 and ns(command["created_at"]) == expected_start
                and ns(command["expires_at"]) - ns(command["created_at"]) == 2_000_000_000
                and ns(receipt["stamp"]) == expected_start,
                f"step{sequence} command/receipt/TTL boundary differs")
        require(reward["epoch"] == epoch and reward["sequence"] == sequence
                and ns(reward["step_start"]) == expected_start
                and ns(reward["effective_step_end"]) == ns(reward["requested_step_end"]) ==
                ns(row["snapshot"]["source_stamp"]) == expected_end
                and info["dt"] == info["physical_dt"] == reward["delta_sim_time"] == 1.,
                f"step{sequence} does not have contiguous honest one-second endpoints")
        terminal = sequence == 300
        require(row["terminated"] is terminal and row["truncated"] is False
                and reward["terminated"] is terminal and reward["truncated"] is False
                and reward["reason"] == ("timeout" if terminal else None),
                f"step{sequence} terminal classification differs")
        require(type(reward["rejected_actions_delta"]) is int
                and reward["rejected_actions_delta"] == 0
                and reward["reward_terms"]["invalid"] == 0.
                and type(reward["new_correct_free_cells"]) is int
                and reward["new_correct_free_cells"] == reward["rewarded_correct_free_cells"] == 0
                and reward["initial_correct_free_cells"] == initial["initial_correct_free_cells"]
                and reward["reward_terms"]["coverage"] == 0.,
                f"step{sequence} has rejection penalty or pays startup/repeated free cells")
        require(reward["reward_weights"]["failure"] == 20.
                and reward["reward_terms"]["failure"] == (-20. if terminal else 0.),
                f"step{sequence} must pay the failure term only once at timeout")
        if reward["reward_terms"]["failure"]:
            failure_steps.append(sequence)
        for name, value in reward["reward_terms"].items():
            require(audit.number(value), "nonfinite scalar reward term")
            terms.setdefault(name, []).append(value)
        require(math.isclose(math.fsum(reward["reward_terms"].values()), row["reward"],
                             rel_tol=0., abs_tol=1e-9), "raw reward terms do not sum")
        delta = command["expires_at"] - command["created_at"]
        if delta > 2.:
            witness = {
                "command_id": sequence,
                "observation_sequence": command["observation_sequence"],
                "created_at": command["created_at"], "expires_at": command["expires_at"],
                "literal_float_difference_repr": repr(delta),
                "endpoint_interval_ns": 2_000_000_000,
                "receipt_stamp": receipt["stamp"], "receipt_kind": "action",
                "results": receipt["payload"]["results"], "rejected_actions_delta": 0,
                "invalid_reward": reward["reward_terms"]["invalid"],
                "transition_jsonl_line": sequence + 1, "adapter_jsonl_line": line,
                "old_literal_float_guard_would_reject": True,
                "current_integer_endpoint_guard_correctly_accepted": True}
            counterexamples.append(witness)
    require(counterexamples, "this actual probe lacks the requested float-boundary witness")
    sums = {name: math.fsum(values) for name, values in terms.items()}
    last = transitions[-1]["info"]["reward_diagnostics"]
    require(ns(last["effective_step_end"]) - start_ns == 300_000_000_000
            and last["remaining_sim_time"] == 0. and last["elapsed_sim_time"] == 300.
            and failure_steps == [300] and sums["failure"] == -20.
            and sums["invalid"] == sums["coverage"] == 0., "final deadline/ledger totals differ")
    return {"commands_checked": 300, "accepted_commands": 300, "rejected_commands": 0,
            "robot_keep_receipts": 900, "native_goals_sent": 0, "start_time_ns": start_ns,
            "end_time_ns": ns(last["effective_step_end"]), "elapsed_ns": 300_000_000_000,
            "terminated": True, "truncated": False, "termination_reason": "timeout",
            "failure_penalty_sequences": failure_steps, "reward_term_sums": sums,
            "initial_correct_free_cells": initial["initial_correct_free_cells"],
            "newly_rewarded_cells": 0, "counterexample_count": len(counterexamples),
            "correctly_accepted_float_boundary_witnesses": counterexamples,
            "command_time_replay": timing}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--phase-audit", required=True, type=Path)
    parser.add_argument("--scalar-audit", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("output exists; choose a new review path")
    time_helper = load_time_helper()
    audit, source_proof = time_helper.load_auditor()
    evidence = audit.Evidence(args.directory)
    metadata, summary = evidence.json("metadata.json"), evidence.json("summary.json")
    epoch = metadata["epoch"]
    audit.require(metadata["freeze"] == args.freeze and summary["epoch"] == epoch
                  and summary["transition_count"] == 300 and summary["launch_returncode"] == 0,
                  "not the complete same-freeze deadline episode")
    audit.audit_processes(evidence.json("supervisor_metadata.json"),
                          evidence.json("supervisor_shutdown.json"), epoch)
    transitions, events = evidence.rows("transitions.jsonl"), evidence.rows("adapter.jsonl")
    detail = review_rows(time_helper, audit, transitions, events, epoch)
    physics = audit.audit_physics(evidence.rows("physics.jsonl"), epoch, detail["start_time_ns"])
    audit.require(physics["last_time_ns"] == detail["end_time_ns"],
                  "actual closed physical receipts disagree with deadline end")
    evaluation = evidence.json(epoch + ".json")
    audit.require(evaluation["termination_reason"] == "timeout" and evaluation["success"] is False
                  and audit.nanoseconds(evaluation["start_sim_time_sec"]) ==
                  detail["start_time_ns"]
                  and audit.nanoseconds(evaluation["end_sim_time_sec"]) == detail["end_time_ns"],
                  "evaluator terminal source differs")
    phase = json.loads(args.phase_audit.read_text())
    scalar = json.loads(args.scalar_audit.read_text())
    audit.require(phase["passed"] is True and phase["errors"] == []
                  and phase["freeze"] == scalar["freeze"] == args.freeze
                  and scalar["passed_scalar_checks"] is True, "existing audit verdict differs")
    primary = next(row for row in phase["episodes"] if row["epoch"] == epoch)
    existing = next(row for row in scalar["episodes"] if row["epoch"] == epoch)
    audit.require(primary["protocol"]["command_time"] == detail.pop("command_time_replay")
                  and existing["transitions"] == 300 and existing["newly_rewarded_cells"] == 0
                  and existing["rejected_action_bindings"] == [] and existing["errors"] == []
                  and existing["evaluation_reason"] == "timeout",
                  "raw review/existing audit differs")
    for name, value in detail["reward_term_sums"].items():
        audit.require(math.isclose(value, existing["reward_term_sums"][name],
                                   rel_tol=0., abs_tol=1e-8), "scalar reward aggregate differs")
    audit.require(all(primary["evidence_sha256"][name] == digest
                      for name, digest in evidence.hashes.items()), "raw evidence SHA differs")
    result = {"schema": "mr3-v7-deadline-command-time-review-v1", "passed": True,
              "freeze": args.freeze, "epoch": epoch, "directory": str(args.directory),
              "scope": "closed deadline command/receipt/physical-time/scalar-reward review only; "
                       "no spatial truth replay, independent18-contact timing "
                       "or new native credit",
              "review": detail, "physics": physics, "evidence_sha256": evidence.hashes,
              "existing_audits": [{"path": str(path), "sha256": hashlib.sha256(
                  path.read_bytes()).hexdigest()}
                  for path in (args.phase_audit, args.scalar_audit)],
              "reused_time_helper_sha256": TIME_SHA, "original_auditor_sha256": source_proof,
              "review_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "command": [sys.executable, "-B", str(Path(__file__)),
                          *(sys.argv[1:] if argv is None else argv)]}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": True, "commands": 300,
                      "counterexamples": detail["counterexample_count"],
                      "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
