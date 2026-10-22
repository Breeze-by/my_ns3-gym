"""One bounded parse of the predeclared V37 corridors protocol journal.

This selects recorded dispatcher/delivery evidence only. It does not rerun a
dispatcher, reconstruct a queue, decode actor inputs or run a World. Missing
records never establish that a message was not generated, queued or sent.
"""
import argparse
from decimal import Decimal
import gzip
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import subprocess


ROOT = Path("/home/zhuyulab/ns3-workspace")
W = ROOT / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
ROS = ROOT / "ros2_ws/ros2-multi-robot-automap"
PACKAGE = ROS / "src/multi_robot_exploration/multi_robot_exploration"
A37 = W / "report/assets/20261022_mr3_p2a_v37_point_graph"
PROTOCOL = A37 / ("closed_execution/point_graph_probe_v1/stages/group3/worker2/"
                  "episode001_corridors_101/protocol.jsonl.gz")
INVENTORY = A37 / "closed_inventory_v1.json"
PROTOCOL_BYTES = 23618
PROTOCOL_SHA256 = "506e4e491f1a1993b9481f79ef09b1080efdb5de94a7faa5b5906ec69f4ee3e5"
EPOCH = "proxy2d_w2_e1_f96a1433"
EVIDENCE_FREEZE = "13e95f29fcc094b19c42fbdeb7d9a76644dee0e9"
GOAL_SUFFIXES = ("tb3:46", "tb3:53", "tb1:53", "tb2:51")
GOALS = tuple(EPOCH + ":" + suffix for suffix in GOAL_SUFFIXES)
WINDOW_NS = (52_100_000_000, 54_300_000_000)
BEFORE_NS = 54_100_000_000
MAX_ROWS = 10000
MAX_DECODED_BYTES = 8_000_000
MAX_METADATA_BYTES = 4_000_000
RELIABLE = frozenset(("command", "receipt", "heartbeat", "ack"))
STREAMS = RELIABLE | {"state", "peer_state", "map", "shared_map"}
SCHEMA = "mr3-v38-fixed-protocol-forensic-v1"


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate JSON field")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def read_limited(path, limit=MAX_METADATA_BYTES):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, "file exceeds byte limit")
    return raw


def identity():
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return {"pid": os.getpid(), "parent": int(fields[1]), "group": int(fields[2]),
            "session": int(fields[3]), "start_ticks": int(fields[19])}


def seconds(value):
    require(type(value) in (int, float) and math.isfinite(value) and value >= 0,
            "invalid recorded protocol timestamp")
    return Decimal(str(value))


def delivery_timing(envelope, clock_ns, previous):
    source, generated, received = (seconds(envelope[key]) for key in (
        "source_stamp", "generated_stamp", "received_stamp"))
    lag = received - generated
    result = {"source_stamp": envelope["source_stamp"],
        "generated_stamp": envelope["generated_stamp"], "received_stamp": envelope["received_stamp"],
        "received_minus_generated_seconds": str(lag),
        "received_minus_source_seconds": str(received - source),
        "worker_clock_minus_received_seconds": str(Decimal(clock_ns) / 10**9 - received),
        "previous_actual_delivery_line_1based": None,
        "generated_gap_from_previous_actual_delivery_seconds": None,
        "received_gap_from_previous_actual_delivery_seconds": None,
        "labels": ["recorded_delivery_only"]}
    if lag > 0:
        result["labels"].append("positive_recorded_generation_to_receipt_lag")
        if envelope["stream"] == "heartbeat":
            result["labels"].append("heartbeat_generated_before_its_recorded_receipt")
    if previous is not None:
        before = previous["record"]["envelope"]
        result.update(previous_actual_delivery_line_1based=previous["line_1based"],
            generated_gap_from_previous_actual_delivery_seconds=str(generated - seconds(before["generated_stamp"])),
            received_gap_from_previous_actual_delivery_seconds=str(received - seconds(before["received_stamp"])))
    return result


def extract_protocol(raw, *, expected_sha256=PROTOCOL_SHA256, expected_bytes=PROTOCOL_BYTES,
                     expected_epoch=EPOCH):
    """Pure bounded extractor; fixture overrides do not change the fixed CLI."""
    require(len(raw) == expected_bytes and sha(raw) == expected_sha256,
            "fixed compressed protocol SHA/bytes differ")
    selected, previous, last_before = {}, {}, {}
    window_lines, goals = [], {goal: [] for goal in GOALS}
    first_failure, consumed, count, previous_clock = None, 0, 0, -1

    def select(entry, label):
        retained = selected.setdefault(entry["line_1based"], entry)
        if label not in retained["selection_labels"]:
            retained["selection_labels"].append(label)

    # Exactly one decompression/parse traversal. Every row is epoch checked,
    # including rows outside the selection window and four fixed goal IDs.
    with gzip.GzipFile(fileobj=io.BytesIO(raw)) as stream:
        for line_number in range(1, MAX_ROWS + 1):
            line = stream.readline(MAX_DECODED_BYTES - consumed + 1)
            if not line:
                break
            consumed += len(line)
            require(consumed <= MAX_DECODED_BYTES, "decoded protocol byte limit exceeded")
            row = parse(line)
            require(isinstance(row, dict) and row.get("epoch") == expected_epoch, "protocol row epoch differs")
            clock = row.get("clock_ns")
            require(type(clock) is int and clock >= previous_clock and clock >= 0,
                    "worker clock is invalid or reversed")
            previous_clock, count = clock, line_number
            require(row.get("kind") in ("dispatcher_event", "proxy_delivery"), "unknown worker protocol record kind")
            entry = {"line_1based": line_number, "raw_line_sha256": sha(line),
                     "raw_line": line.decode("utf-8"), "record": row, "selection_labels": []}
            if row["kind"] == "proxy_delivery":
                envelope = row.get("envelope")
                require(isinstance(envelope, dict) and envelope.get("epoch") == expected_epoch
                        and envelope.get("stream") in STREAMS and envelope.get("source") in ("tb1", "tb2", "tb3")
                        and type(envelope.get("sequence")) is int and envelope["sequence"] >= 1
                        and type(envelope.get("version")) is int and envelope["version"] >= 0
                        and isinstance(envelope.get("payload"), dict), "invalid delivered envelope identity")
                key = (envelope["stream"], envelope["source"])
                entry["delivery_timing"] = delivery_timing(envelope, clock, previous.get(key))
                previous[key] = entry
                if clock < BEFORE_NS:
                    last_before[key] = entry
                if envelope["stream"] in RELIABLE and WINDOW_NS[0] <= clock <= WINDOW_NS[1]:
                    window_lines.append(line_number)
                    select(entry, "reliable_delivery_in_closed_worker_clock_window")
                goal = envelope["payload"].get("goal_id")
            else:
                event = row.get("event")
                require(isinstance(event, dict) and event.get("epoch") == expected_epoch
                        and event.get("robot") in ("tb1", "tb2", "tb3")
                        and isinstance(event.get("type"), str), "invalid dispatcher event identity")
                stamp = seconds(event.get("stamp"))
                entry["dispatcher_timing"] = {"event_stamp": event["stamp"],
                    "worker_clock_minus_event_stamp_seconds": str(Decimal(clock) / 10**9 - stamp)}
                goal = event.get("goal_id")
                if event["type"] == "protocol_failure" and first_failure is None:
                    first_failure = line_number
                    select(entry, "first_recorded_protocol_failure_in_full_epoch_prefix")
            if goal in goals:
                goals[goal].append(line_number)
                select(entry, "full_prefix_fixed_goal:" + goal)
        # At most one extra byte checks the row bound; no 10001st JSON decode.
        require(not stream.read(1), "protocol row limit exceeded")
    for key, entry in sorted(last_before.items()):
        select(entry, "last_recorded_delivery_strictly_before_worker_clock_54_1:" + ":".join(key))
    return {"parsed_rows": count, "decoded_bytes": consumed, "decompression_passes": 1,
        "selection_clock": "recorded worker clock_ns; envelope timestamps are separately preserved",
        "window_inclusive_ns": list(WINDOW_NS), "strict_before_ns": BEFORE_NS,
        "selection_index": {"reliable_deliveries_in_window": window_lines,
            "fixed_goal_history": goals, "first_protocol_failure": first_failure,
            "last_delivery_strictly_before": [{"stream": key[0], "source": key[1],
                "line_1based": entry["line_1based"]} for key, entry in sorted(last_before.items())]},
        "selected_rows": [selected[key] for key in sorted(selected)],
        "limits": {"rows": MAX_ROWS, "decoded_bytes": MAX_DECODED_BYTES},
        "limitations": ["absence of a journal record does not prove a message was not generated, queued or sent",
            "generation gaps and receipt gaps refer only to consecutive actually recorded deliveries of the same stream/source",
            "positive recorded delivery lag does not reconstruct a queue or establish the cause of a protocol failure",
            "no queue reconstruction, protocol state replay, actor/World/truth consumption, task or native qualification"]}


def check_inventory(inventory, canonical_path, expected_sha256, expected_bytes):
    require(inventory.get("schema") == "mr3-closed-byte-inventory-v1"
            and isinstance(inventory.get("files"), list), "wrong closed byte inventory schema")
    matches = [entry for entry in inventory["files"] if entry.get("canonical") == canonical_path]
    require(len(matches) == 1 and matches[0].get("sha256") == expected_sha256
            and matches[0].get("bytes") == expected_bytes, "fixed protocol omitted or changed in inventory")
    return matches[0]


def frozen_source_bindings(source_freeze):
    require(type(source_freeze) is str and re.fullmatch(r"[0-9a-f]{40}", source_freeze),
            "full source freeze required")
    result = {}
    for path in (Path(__file__).resolve(), ROS / "scripts/mr3_proxy2d_worker.py",
                 PACKAGE / "mr3_protocol.py", PACKAGE / "mr3_transport.py", INVENTORY):
        raw = read_limited(path)
        relative = path.relative_to(ROOT).as_posix()
        frozen = subprocess.check_output(["git", "show", source_freeze + ":" + relative],
                                         cwd=ROOT, stderr=subprocess.PIPE)
        require(raw == frozen, "current source/inventory differs from exact freeze: " + relative)
        result[str(path)] = {"sha256": sha(raw), "bytes": len(raw),
                             "git_source": source_freeze + ":" + relative}
    return result


def inspect_fixed_protocol(source_freeze):
    sources_before = frozen_source_bindings(source_freeze)
    require(PROTOCOL.resolve() == PROTOCOL and not PROTOCOL.is_symlink(),
            "fixed protocol path aliases another location")
    inventory_raw = read_limited(INVENTORY)
    inventory = parse(inventory_raw)
    entry = check_inventory(inventory, PROTOCOL.relative_to(W).as_posix(), PROTOCOL_SHA256, PROTOCOL_BYTES)
    raw = read_limited(PROTOCOL, PROTOCOL_BYTES)
    before = {str(INVENTORY): {"sha256": sha(inventory_raw), "bytes": len(inventory_raw)},
              str(PROTOCOL): {"sha256": sha(raw), "bytes": len(raw)}}
    extracted = extract_protocol(raw)
    after = {path: {"sha256": sha(content), "bytes": len(content)}
             for path in before for content in (read_limited(path),)}
    sources_after = {path: {**proof, "sha256": sha(content), "bytes": len(content)}
                     for path, proof in sources_before.items() for content in (read_limited(path),)}
    require(before == after, "protocol or inventory bytes changed during bounded inspection")
    require(sources_before == sources_after, "forensic source bytes changed during bounded inspection")
    return {"schema": SCHEMA, "source_freeze": source_freeze, "evidence_freeze": EVIDENCE_FREEZE,
        "epoch": EPOCH, "passed": True, "computation_passed": True,
        "source_bindings": sources_before, "source_bindings_after": sources_after, "source_stable": True,
        "input_bindings_before": before, "input_bindings_after": after, "input_stable": True,
        "inventoried_protocol": entry, **extracted, "qualification": False, "training_eligible": False,
        "native_credit": False, "task_success_claimed": False, "queue_reconstructed": False,
        "policy_calls": 0, "gpu_calls": 0, "optimizer_steps": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    with args.output.open("x") as stream:
        own_identity = identity()
        try:
            result = inspect_fixed_protocol(args.source_freeze)
            result["identity"] = own_identity
        except Exception as error:
            stream.write(json.dumps({"schema": SCHEMA, "source_freeze": args.source_freeze,
                "source_stable": False, "identity": own_identity, "passed": False,
                "computation_passed": False, "error": repr(error), "qualification": False,
                "training_eligible": False, "native_credit": False}, indent=2, allow_nan=False) + "\n")
            raise
        stream.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
