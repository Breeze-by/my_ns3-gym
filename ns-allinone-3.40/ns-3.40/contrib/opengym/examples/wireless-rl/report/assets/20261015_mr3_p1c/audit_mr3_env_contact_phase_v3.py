#!/usr/bin/env python3
"""Offline fixed-source contact-phase and independent command-time auditing.

Reuse the immutable v2 task-phase proof without changing its contact gates.
Require an explicit episode freeze whose Git blobs and current executable bytes
match this revision's fixed source pins. No ROS or simulator is initialized.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


METHOD = "mr3-contact-task-phase-and-command-time-v3"
BASE_NAME = "audit_mr3_env_contact_phase_v2.py"
BASE_SHA256 = "3ce800bfa0455d25a1c3257635c7c4d593478082bbbf1c4dab6a10eed2fc6991"
COMMAND_NAME = "audit_command_time_v7.py"
COMMAND_SHA256 = "4787ca8d2e6b4d7ba06b3d5a3c1ead82fe6f079485a790c5b940f2ba7636c3b9"
ROS = "ros2_ws/ros2-multi-robot-automap/"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
PINNED_RUNTIME = {
    ROS + "scripts/audit_mr3_env.py":
        "25ce0b466d988595934f26a0cfb7a81a445632b1e755f2462b80698371b272e8",
    ROS + "scripts/audit_mr3_adapter_probe.py":
        "fdd415da1b01d7da6219d21a2fa8e184484b696d33c3e736bde8ca165bb65e6a",
    ROS + "scripts/ros_smoke_test.py":
        "f130b1157b4855089d51a6b1f22e57e0b5683b40624cc8697e3bb76fb3659d1a",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_contacts.py":
        "9d661498b3748d409dbb59ccd59524d5152d85ec93ee30128aebaf0a8a09fa17",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/task_evaluator.py":
        "bd0c2e43dbbb4258e4e1ee537fbdbe512211576eb930d5f8862d787dc73e48af",
    ROS + "scripts/mr3_env_worker.py":
        "930be78a0763d69dfa102c662ac8713ee970e421a56193f92257e65ce0e67dac",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py":
        "b20f6b492f91cb943247ebcc29bd16497983d17c23cc458f1be16fa24b9958d5",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_protocol.py":
        "fb08097170b3f0e8423fa11dde2567c618d4d0d48be220e6cfbfc9538c37c147",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_episode.py":
        "9145d2ad23789b252e32f0afdfe18cf2eeec8e2c7e9ca7e89127a532288e411b",
    ROS + "src/multi_robot_exploration/multi_robot_exploration/mr3_observation.py":
        "e4f1c4ec51c8c0280fba32e47d189c1234eee44093612692e2d032efe26b388b",
}
PINNED_DOCUMENTS = {
    WIRELESS + "MR3_TASK_CONTRACT.md":
        "fcc1cedbc524a3d55443c887201f13f58fbd442e5600f1d8ad5cad84b7346c48",
    WIRELESS + "MR3_ENV_CONTRACT.md":
        "f05bf13b8848fb93347327ce4bb03672eed9938f84ef52db9ab000537cd95593",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def repository_root():
    return next(parent for parent in Path(__file__).resolve().parents
                if (parent / ".git").exists())


def validate_freeze(freeze):
    require(isinstance(freeze, str) and re.fullmatch(r"[0-9a-f]{40}", freeze) is not None,
            "an explicit exact40-hex pushed source freeze is required")


def load_pinned_module(name, path, expected):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected,
            "fixed offline helper SHA mismatch: " + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_git_runtime(root, freeze):
    """A matching worktree alone cannot bind the claimed episode Git freeze."""
    validate_freeze(freeze)
    proof = {}
    for relative, expected in PINNED_RUNTIME.items():
        payload = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=root)
        digest = hashlib.sha256(payload).hexdigest()
        require(digest == expected, "fixed Git runtime/source SHA mismatch: " + relative)
        proof[relative] = digest
    return proof


def load_components(freeze, root=None):
    """Load a separate v2 instance with this revision's fixed source bindings."""
    validate_freeze(freeze)
    root = repository_root() if root is None else Path(root)
    directory = Path(__file__).resolve().parent
    base = load_pinned_module("mr3_phase_v3_base_v2", directory / BASE_NAME, BASE_SHA256)
    command = load_pinned_module("mr3_phase_v3_command_time", directory / COMMAND_NAME,
                                 COMMAND_SHA256)
    base.FREEZE = freeze
    base.METHOD = METHOD
    base.PINNED_RUNTIME = dict(PINNED_RUNTIME)
    base.PINNED_DOCUMENTS = dict(PINNED_DOCUMENTS)
    require(all(PINNED_RUNTIME.get(path) == digest
                for path, digest in command.PINNED_AUDITORS.items()),
            "command-time original auditor pins differ from this revision")
    git_proof = verify_git_runtime(root, freeze)
    audit, proof = base.load_auditor(root)
    for relative, digest in git_proof.items():
        proof[relative].update(git_blob_sha256=digest, git_source=freeze + ":" + relative)
    return base, audit, command, proof


def corrected_audit(base, audit, command, directories, *, matrix=False, expected_fault=False):
    """Add the command gate after the original protocol check, restoring both hooks."""
    original = audit.audit_protocol

    def protocol_with_time(rows, transitions, epoch, allow_incomplete=False):
        protocol = original(rows, transitions, epoch, allow_incomplete)
        timing = command.audit_command_times(rows, transitions, epoch, allow_incomplete,
                                             auditor=audit)
        require(timing.get("passed") is True,
                "independent command-time gate: " + "; ".join(timing.get("errors", [])))
        return {**protocol, "command_time": timing}

    try:
        audit.audit_protocol = protocol_with_time
        return base.corrected_audit(audit, directories, matrix=matrix,
                                    expected_fault=expected_fault)
    finally:
        audit.audit_protocol = original


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--matrix", action="store_true")
    parser.add_argument("--expected-fault", action="store_true")
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error("audit output exists; choose a new path")
    if (args.matrix and args.expected_fault) or (not args.matrix and len(args.directories) != 1):
        parser.error("use --matrix for multiple directories; faults come from benchmark metadata")
    base, audit, command, proof = load_components(args.freeze)
    result = corrected_audit(base, audit, command, args.directories, matrix=args.matrix,
                             expected_fault=args.expected_fault)
    original_schema = result["schema"]
    result["schema"] = "mr3-p1c-contact-phase-audit-v3"
    result["offline_contact_phase_audit"] = {
        "method": METHOD,
        "wrapper_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "freeze": args.freeze, "frozen_sources": proof,
        "original_auditor_schema": original_schema,
        "only_overridden_functions": ["audit_contacts", "audit_protocol"],
        "base_v2": {"path": BASE_NAME, "sha256": BASE_SHA256,
                    "contact_logic_modified": False},
        "command_time_gate": {"path": COMMAND_NAME, "sha256": COMMAND_SHA256,
                              "method": command.METHOD,
                              "order": "original audit_protocol, then independent command time"},
        "original_results_modified": False,
        "source_invariant": (
            "start once; no monitor/latch reset; every task gap/age failure latches"),
        "ready_payload_limitation": "raw initial reward_ready payload was not saved",
        "scope": "fixed-source offline task-phase and command-time gates; no new native credit",
    }
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, sort_keys=True, allow_nan=False)
        output.write("\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"],
                      "audit": str(args.output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
