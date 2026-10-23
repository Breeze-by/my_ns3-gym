"""Versioned offline audit: prove a stopped goal never submitted to Nav2.

The original function is called first, its verdict is retained, and its whole
protocol replay is called again on a detached view after exact unsent proof.
No event or native receipt is manufactured; no on-disk evidence is modified.
Only the frozen peer-envelope safety branch is supported by this version.
"""

import copy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess
from types import CodeType


METHOD = "mr3-protocol-proven-unsent-peer-stop-v2"
W7 = "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a"
ROS = "ros2_ws/ros2-multi-robot-automap/"
AUDITOR = ROS + "scripts/audit_mr3_env.py"
ORIGINAL_AUDITOR_SHA = "25ce0b466d988595934f26a0cfb7a81a445632b1e755f2462b80698371b272e8"
PINS = {
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_adapter.py':
        'd9121970b18e86a524ad4aad591a64661555bc15c0a59bf425896324473eecfc',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_protocol.py':
        '5a2b90efd162b19a35964750002fe549413fec6e07f9679ea611d3fe6b1e4ada',
    ROS + 'src/multi_robot_exploration/multi_robot_exploration/mr3_transport.py':
        '426d9b777c2150bb690de3266c973dedfc8fe8da3fa36c7bf37cbe3c31d70eca',
    ROS + 'scripts/audit_mr3_env.py':
        '5ba60bc89f3c87059cd5d4342fa433de25548c7d95c66ea0ce7708eb4ae8dad2',
}
ROBOTS = ("tb1", "tb2", "tb3")
OLD_CLOSURE_ERROR = "goal lacks native send/result/protocol terminal closure"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def ns(value):
    require(type(value) in (int, float), "timestamp must be numeric")
    result = Decimal(str(value)) * 1_000_000_000
    require(result.is_finite() and result == result.to_integral_value(),
            "timestamp is not finite integer nanoseconds")
    return int(result)


def code_identity(code):
    """Compare executable code, excluding source filename/line-number metadata."""
    def constant(value):
        if isinstance(value, CodeType):
            return code_identity(value)
        if isinstance(value, tuple):
            return tuple(constant(item) for item in value)
        return value
    return (code.co_code, tuple(constant(x) for x in code.co_consts),
            code.co_names, code.co_varnames, code.co_freevars, code.co_cellvars,
            code.co_argcount, code.co_posonlyargcount, code.co_kwonlyargcount,
            code.co_flags, code.co_stacksize, getattr(code, "co_exceptiontable", b""))


def verify_sources(root, freeze, original):
    require(isinstance(freeze, str) and re.fullmatch("[0-9a-f]{40}", freeze),
            "native freeze must be an exact Git commit identity")
    root = Path(root)
    proof = {}

    def git_source(revision, relative):
        try:
            return subprocess.check_output(["git", "show", revision + ":" + relative],
                                           cwd=root, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError("protocol audit Git source unavailable: " + revision + ":"
                             + relative) from error

    for relative, expected in PINS.items():
        frozen = git_source(freeze, relative)
        require(hashlib.sha256(frozen).hexdigest() == expected
                and (root / relative).read_bytes() == frozen,
                "runtime/current source differs from exact unsent proof: " + relative)
        proof[relative] = {"sha256": expected, "git_source": freeze + ":" + relative}
    payload = git_source(W7, AUDITOR)
    require(hashlib.sha256(payload).hexdigest() == ORIGINAL_AUDITOR_SHA,
            "original W7 auditor source pin changed")
    # Compile the normative source for code comparison; do not patch its AST.
    module = compile(payload, "normative-original", "exec")
    functions = [x for x in module.co_consts
                 if isinstance(x, CodeType) and x.co_name == "audit_protocol"]
    require(len(functions) == 1 and hasattr(original, "__code__")
            and code_identity(original.__code__) == code_identity(functions[0]),
            "supplied original protocol function is not the immutable W7 implementation")
    proof["original_protocol_function"] = {
        "normative_git_source": W7 + ":" + AUDITOR,
        "auditor_sha256": ORIGINAL_AUDITOR_SHA, "executable_code_identity_equal": True}
    return proof


def prove_command_envelope(rows, send_index, delivery_index, epoch, robot):
    """Replay the suppressed robot's reliable default-version command stream.

    The pinned flush_protocol_events records each send/cancel immediately before
    IdealTransport.send(command, robot, payload, source_stamp=payload.stamp,
    now=flush_now), with no explicit version. The reliable queue does not
    collapse commands. Thus per-key sequences count those exact producers,
    version equals sequence, and every logged accepted delivery must consume
    the next producer. ReceivedStore epoch/monotonic watermarks remain checked.
    This check is limited to the known suppressed command's stream prefix.
    """
    producers, consumed, previous = [], 0, None
    for index, row in enumerate(rows[:delivery_index + 1]):
        event = row["payload"]
        if (row["kind"] == "protocol" and event["robot"] == robot
                and event["type"] in ("send_goal", "cancel_goal")):
            producers.append((index, row))
        elif (row["kind"] == "delivery" and event.get("stream") == "command"
              and event.get("source") == robot):
            require(event.get("epoch") == epoch, "command envelope epoch differs")
            sequence, version = event.get("sequence"), event.get("version")
            require(type(sequence) is int and sequence > 0
                    and type(version) is int and version == sequence
                    and sequence == consumed + 1 and sequence <= len(producers),
                    "command envelope sequence/version is invalid, stale or skipped")
            producer_index, producer = producers[sequence - 1]
            require(producer_index < index and event["payload"] == producer["payload"]
                    and ns(event["source_stamp"]) == ns(producer["payload"]["stamp"])
                    and ns(event["generated_stamp"]) == ns(producer["stamp"])
                    and 0 <= ns(event["source_stamp"]) <= ns(event["generated_stamp"])
                    <= ns(event["received_stamp"]) == ns(row["stamp"]),
                    "command envelope does not bind exact producer payload/timestamps")
            if previous is not None:
                require(sequence > previous["sequence"] and version >= previous["version"]
                        and all(ns(event[field]) >= ns(previous[field]) for field in (
                            "source_stamp", "generated_stamp", "received_stamp")),
                        "command envelope regresses a ReceivedStore watermark")
            consumed, previous = sequence, event
            if index == delivery_index:
                require(producer_index == send_index,
                        "suppressed delivery consumed another command producer")
                return {"epoch": epoch, "stream": "command", "source": robot,
                        "sequence": sequence, "version": version,
                        "source_stamp_ns": ns(event["source_stamp"]),
                        "generated_stamp_ns": ns(event["generated_stamp"]),
                        "received_stamp_ns": ns(event["received_stamp"]),
                        "replayed_accepted_stream_prefix": consumed,
                        "producer_line": send_index + 1, "delivery_line": index + 1}
    raise ValueError("suppressed command is not an accepted command-stream envelope")


def prove_unsent(rows, transitions, epoch):
    """Prove each sole stopped-unsent branch and replay every logical owner."""
    require(transitions and transitions[0]["kind"] == "reset"
            and transitions[-1]["terminated"] is True
            and transitions[-1]["truncated"] is False
            and transitions[-1]["info"]["reason"] == "navigation_failure",
            "unsent correction requires a closed genuine navigation-failure episode")
    require(rows, "missing adapter events")
    previous_ns = -1
    for row in rows:
        require(row.get("epoch") == epoch and ns(row["stamp"]) >= previous_ns,
                "adapter epoch/time order is invalid")
        previous_ns = ns(row["stamp"])
    commands = {}
    snapshots = {row["snapshot"]["sequence"]: row["snapshot"] for row in transitions}
    for step in transitions[1:]:
        if step["info"].get("action_submitted", True) is False:
            continue
        command = step["info"]["command"]
        identity = command["command_id"]
        require(type(identity) is int and identity not in commands,
                "duplicate or invalid submitted command")
        commands[identity] = command
    suppressed = [(index, row) for index, row in enumerate(rows)
                  if row["kind"] == "edge_goal_not_sent"]
    require(suppressed, "closure difference lacks an explicit edge_goal_not_sent")
    suppressed_ids = [row["payload"]["goal_id"] for _, row in suppressed]
    require(len(set(suppressed_ids)) == len(suppressed_ids), "duplicate unsent suppression")
    owners = dict.fromkeys(ROBOTS)
    sends, terminals, native, native_results = {}, {}, {}, {}
    for index, row in enumerate(rows):
        event = row["payload"]
        if row["kind"] == "protocol":
            name, goal = event["robot"], event.get("goal_id")
            require(name in owners, "unknown logical owner")
            if event["type"] == "send_goal":
                require(owners[name] is None and goal not in sends,
                        "duplicate goal or new logical goal before owned terminal")
                owners[name] = goal
                sends[goal] = (index, event)
            elif event["type"] == "protocol_terminal":
                require(owners[name] == goal and goal not in terminals,
                        "unbound/duplicate logical terminal")
                terminals[goal] = (index, event)
                owners[name] = None
        elif row["kind"] == "native_send":
            goal = event["goal_id"]
            require(goal not in native, "duplicate native send")
            native[goal] = index
        elif row["kind"] == "delivery" and event.get("stream") == "receipt":
            receipt = event["payload"]
            if receipt["type"] == "result":
                goal = receipt["goal_id"]
                require(goal not in native_results, "duplicate native result")
                native_results[goal] = index
    require(not any(owners.values()) and set(sends) == set(terminals),
            "logical goal ownership remains unresolved")
    removed, bindings = set(), []
    for edge_index, edge in suppressed:
        goal = edge["payload"]["goal_id"]
        require(edge["payload"] == {"goal_id": goal, "reason": "stopped"},
                "only exact stopped suppression is supported")
        require(goal in sends and goal in terminals, "suppression lacks unique logical lifecycle")
        send_index, send = sends[goal]
        terminal_index, terminal = terminals[goal]
        name, command_id = send["robot"], send["command_id"]
        require(type(command_id) is int and command_id in commands
                and goal == f"{epoch}:{name}:{command_id}", "unbound suppressed goal identity")
        command = commands[command_id]
        require(command["epoch"] == epoch and send["epoch"] == epoch
                and terminal["epoch"] == epoch and terminal["command_id"] == command_id
                and terminal["robot"] == name and terminal["status"] == "CANCELED"
                and send_index < edge_index < terminal_index,
                "wrong unsent command/epoch/terminal/order")
        edge_ns = ns(edge["stamp"])
        require(ns(send["stamp"]) == ns(rows[send_index]["stamp"])
                <= edge_ns == ns(terminal["stamp"])
                == ns(rows[terminal_index]["stamp"])
                and ns(command["created_at"]) == ns(send["created_at"])
                and ns(command["expires_at"]) == ns(send["expires_at"])
                == ns(send["lease_until"])
                and ns(command["created_at"]) <= edge_ns < ns(command["expires_at"])
                and 0 < ns(command["expires_at"]) - ns(command["created_at"]) <= 2_000_000_000,
                "unsent time/lease/TTL proof differs")
        actions = [(i, row["payload"]) for i, row in enumerate(rows)
                   if row["kind"] in ("action", "action_rejected", "action_duplicate")
                   and row["payload"].get("command_id") == command_id]
        require(len(actions) == 1 and rows[actions[0][0]]["kind"] == "action"
                and actions[0][0] < send_index, "unbound/duplicate/rejected action receipt")
        action_index, action = actions[0]
        snapshot = snapshots[command["observation_sequence"]]
        choices = [command["action"] // 100, command["action"] // 10 % 10,
                   command["action"] % 10]
        choice = choices[ROBOTS.index(name)]
        require(action["observation_sequence"] == command["observation_sequence"]
                == send["observation_version"]
                and action["observation_digest"] == command["observation_digest"]
                == snapshot["digest"]
                and action["candidate_version"] == snapshot["candidate_version"]
                and action["action"] == command["action"]
                and action["choices"] == choices and choice < 8
                and snapshot["joint_action_mask"][command["action"]] is True
                and action["results"][name] in ("sent", "switch_pending"),
                "suppressed send is not the exact legal sampled GOAL")
        target = snapshot["candidates"][choice]
        require(send["goal"] == {"x": target["x"], "y": target["y"]}
                and send["x"] == target["x"] and send["y"] == target["y"],
                "suppressed target differs from sampled candidate")
        stops = [(i, row) for i, row in enumerate(rows)
                 if send_index < i < edge_index and row["kind"] == "safety_stop"]
        require(len(stops) == 1 and ns(stops[0][1]["stamp"]) <= edge_ns
                and json.loads(stops[0][1]["payload"]["reason"]) == {
                    "component": "peer_obstacles", "reason": "peer_body_envelopes_overlap"},
                "missing/duplicate/non-peer safety stop before suppression")
        deliveries = [(i, row) for i, row in enumerate(rows)
                      if row["kind"] == "delivery"
                      and row["payload"].get("stream") == "command"
                      and row["payload"]["payload"].get("goal_id") == goal]
        require(len(deliveries) == 1 and stops[0][0] < deliveries[0][0] < edge_index
                and deliveries[0][1]["payload"]["source"] == name
                and deliveries[0][1]["payload"]["payload"] == send
                and ns(deliveries[0][1]["stamp"]) == edge_ns
                and ns(deliveries[0][1]["payload"]["received_stamp"]) == edge_ns,
                "suppressed edge is not the unique exact delivered goal")
        envelope_proof = prove_command_envelope(
            rows, send_index, deliveries[0][0], epoch, name)
        require(goal not in native and goal not in native_results,
                "suppressed goal was actually native-sent/result-bearing")
        for row in rows:
            event = row["payload"]
            if row["kind"] == "delivery" and event.get("stream") == "receipt":
                require(event["payload"].get("goal_id") != goal,
                        "unsent goal has native acceptance/cancel/result receipt")
            if row["kind"] == "rpc_error" or "handle" in row["kind"]:
                require(event.get("goal_id") != goal, "unsent goal has RPC/handle evidence")
            if row["kind"] == "protocol" and event.get("goal_id") == goal:
                require(event["type"] in ("send_goal", "protocol_terminal"),
                        "unsent goal has native cancellation/acceptance/protocol failure")
        observations = [(i, row["payload"]) for i, row in enumerate(rows)
                        if i > terminal_index and row["kind"] == "observation"]
        require(observations, "no saved observation proves unsent owner/lease release")
        for _, observed in observations:
            nav = observed["robots"][ROBOTS.index(name)]["navigation"]
            require(nav["goal_id"] is None and nav["owned"] is False
                    and nav["command_id"] is None and nav["lease_until"] is None
                    and nav["accepted_at"] is None and nav["requested_at"] is None
                    and nav["phase"] in ("idle", "failed")
                    and nav["last_goal_id"] == goal and nav["last_terminal"] == "CANCELED",
                    "unsent ownership/lease not released or later resurrected")
        removed.update((send_index, terminal_index))
        bindings.append({"goal_id": goal, "robot": name, "command_id": command_id,
                         "source_observation_sequence": snapshot["sequence"],
                         "source_observation_digest": snapshot["digest"],
                         "action_line": action_index + 1, "send_line": send_index + 1,
                         "safety_stop_line": stops[0][0] + 1,
                         "command_delivery_line": deliveries[0][0] + 1,
                         "edge_not_sent_line": edge_index + 1,
                         "logical_terminal_line": terminal_index + 1,
                         "release_observation_lines": [i + 1 for i, _ in observations],
                         "accepted_command_envelope_proof": envelope_proof,
                         "native_send_or_any_receipt_absent": True,
                         "owner_and_lease_release_proven": True})
    require(set(sends) - set(native) == set(suppressed_ids)
            and set(native) == set(native_results)
            and set(terminals) - set(native_results) == set(suppressed_ids),
            "set difference includes an unproven or actually sent goal without result")
    return bindings, removed


class ProtocolAuditor:
    """Attach only to an already source-pinned original auditor in a new wrapper."""

    def __init__(self, original, root, freeze):
        self.original = original
        self.freeze = freeze
        self.source_proof = verify_sources(root, freeze, original)
        self.receipts = []

    def __call__(self, rows, transitions, epoch, allow_incomplete=False):
        receipt = {"method": METHOD, "audited_freeze": self.freeze,
                   "original_errors": [], "original_passed": False,
                   "passed": False, "source_proof": self.source_proof}
        self.receipts.append(receipt)
        try:
            original_result = self.original(rows, transitions, epoch, allow_incomplete)
            receipt.update(original_passed=True, original_result=original_result)
        except (ValueError, KeyError, TypeError, IndexError) as error:
            receipt["original_errors"].append(str(error))
            if str(error) != OLD_CLOSURE_ERROR:
                raise
        try:
            special = any(row["kind"] == "edge_goal_not_sent" for row in rows)
            if not special:
                require(receipt["original_passed"], "original closure error has no unsent proof")
                receipt["passed"] = True
                return {**original_result, "versioned_unsent_audit": receipt}
            require(not allow_incomplete,
                    "unsent correction never grants incomplete-episode credit")
            require(not receipt["original_passed"],
                    "suppression event conflicts with original complete native lifecycle")
            bindings, removed = prove_unsent(rows, transitions, epoch)
            detached = [copy.deepcopy(row) for i, row in enumerate(rows) if i not in removed]
            corrected = self.original(detached, transitions, epoch, False)
            receipt.update(passed=True, bindings=bindings,
                           detached_view_removed_lines=[i + 1 for i in sorted(removed)],
                           detached_original_result=corrected,
                           original_evidence_modified=False,
                           native_receipts_synthesized=False)
            return {**corrected, "versioned_unsent_audit": receipt}
        except (ValueError, KeyError, TypeError, IndexError) as error:
            receipt["new_error"] = str(error)
            raise
