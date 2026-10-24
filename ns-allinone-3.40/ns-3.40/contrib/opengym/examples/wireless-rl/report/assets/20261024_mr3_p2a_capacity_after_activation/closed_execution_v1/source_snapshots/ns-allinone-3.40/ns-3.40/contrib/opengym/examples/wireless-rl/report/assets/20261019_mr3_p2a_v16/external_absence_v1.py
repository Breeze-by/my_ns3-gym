"""Read closed evidence and /proc only; no scientific consumer or native import.

The result concerns saved PID/start identities at the actual lookup times. It
does not turn the failed native attempt into a scientific PASS, prove that an
unrecorded process never existed, or send any signal.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time

SCHEMA = "mr3-reach-external-process-absence-v1"
DEFAULT_RUN = "/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v16/mr3_p2a_reach_v16_interface"


def positive_integer(value):
    if type(value) is int and value > 0:
        return value
    if type(value) is str and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    raise ValueError("not a positive integer or canonical positive decimal string")


def parse(raw):
    def pairs(rows):
        result = {}
        for key, value in rows:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON: " + value)))


def pointer(key):
    return str(key).replace("~", "~0").replace("/", "~1")


class Evidence:
    def __init__(self):
        self.identities = {}
        self.pid_only = {}
        self.bindings = []
        self.errors = []
        self.launch_pids = set()
        self.documents = {}
        self.stat_before = {}

    def error(self, source, reason):
        self.errors.append({"source": source, "reason": str(reason)})

    def visit(self, value, source, location=""):
        if isinstance(value, list):
            for ordinal, child in enumerate(value):
                self.visit(child, source, location + "/" + str(ordinal))
            return
        if not isinstance(value, dict):
            return
        # Pair keys only within one original object. Never join a PID from one
        # record to an independently observed start time from another record.
        pairs = set()
        for start_key in value:
            if start_key == "start_ticks":
                candidates = ("pid",)
            elif start_key == "process_start_ticks":
                candidates = ("process_pid",) if "process_pid" in value else ("pid",)
            elif start_key.endswith("_start_ticks"):
                candidates = (start_key[:-len("start_ticks")] + "pid",)
            else:
                continue
            matches = [key for key in candidates if key in value]
            if not matches:
                self.error(source + location, "saved " + start_key + " has no same-object PID")
            for pid_key in matches:
                pairs.add((pid_key, start_key))
        local = {}
        for pid_key, start_key in sorted(pairs):
            occurrence = {"path": source, "json_pointer": location,
                          "pid_field": pid_key, "start_field": start_key,
                          "pid_value": value[pid_key], "start_value": value[start_key],
                          "pid_type": type(value[pid_key]).__name__,
                          "start_type": type(value[start_key]).__name__}
            try:
                identity = positive_integer(value[pid_key]), positive_integer(value[start_key])
            except ValueError as error:
                self.error(source + location, str(error) + ": " + repr(occurrence))
                continue
            local.setdefault(identity[0], set()).add(identity[1])
            self.identities.setdefault(identity, []).append(occurrence)
        if any(len(starts) > 1 for starts in local.values()):
            self.error(source + location, "same original object has conflicting start times for one PID")
        if "pid" in value:
            try:
                pid = positive_integer(value["pid"])
                self.pid_only.setdefault(pid, set()).add(source + location)
            except ValueError as error:
                self.error(source + location, "invalid saved PID: " + str(error))
        for key, child in value.items():
            if key == "raw_json" and isinstance(child, str) and ("pid" in child or "start_ticks" in child):
                try:
                    self.visit(parse(child), source, location + "/" + pointer(key) + "/@decoded_json")
                except (ValueError, TypeError) as error:
                    self.error(source + location, "identity-bearing raw_json cannot be decoded: " + str(error))
            self.visit(child, source, location + "/" + pointer(key))

    def consume(self, path):
        before = path.stat()
        self.stat_before[path] = before
        digest, size = hashlib.sha256(), 0
        try:
            if path.suffix == ".jsonl":
                # All actual producer field names are ASCII JSON. Bind every
                # byte, but decode only potential identity records; millions
                # of odometry/map values need no scientific interpretation.
                with path.open("rb") as stream:
                    for ordinal, line in enumerate(stream, 1):
                        digest.update(line); size += len(line)
                        if b"pid" in line or b"start_ticks" in line:
                            try:
                                self.visit(parse(line), str(path) + ":" + str(ordinal))
                            except (ValueError, TypeError, UnicodeError) as error:
                                self.error(str(path) + ":" + str(ordinal), error)
            else:
                raw = path.read_bytes()
                digest.update(raw); size = len(raw)
                if path.suffix == ".json":
                    value = parse(raw)
                    self.documents[str(path)] = value
                    self.visit(value, str(path))
                    raw = None
                # Some command consoles contain one pretty-printed JSON result.
                # Launch logging instead has prefixed, one-line shutdown JSON.
                if raw is not None:
                    try:
                        value = parse(raw)
                    except (ValueError, UnicodeError):
                        value = None
                    if value is not None:
                        self.visit(value, str(path))
                        raw = None
                if raw is not None:
                    for ordinal, line in enumerate(raw.decode("utf-8").splitlines(), 1):
                        source = str(path) + ":" + str(ordinal)
                        marker = "MR3_ORDERED_SHUTDOWN "
                        if marker in line:
                            event = parse(line.split(marker, 1)[1])
                            self.visit(event, source)
                            if "pid" in event:
                                self.launch_pids.add(positive_integer(event["pid"]))
                        elif line.lstrip().startswith("{") and ("pid" in line or "start_ticks" in line):
                            self.visit(parse(line), source)
                        match = re.search(r"process started with pid \[([0-9]+)\]", line)
                        if match:
                            self.launch_pids.add(positive_integer(match.group(1)))
        except (ValueError, TypeError, UnicodeError) as error:
            self.error(str(path), error)
        self.bindings.append({"path": str(path), "bytes": size, "sha256": digest.hexdigest()})
        after = path.stat()
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(before, key) != getattr(after, key) for key in fields):
            self.error(str(path), "input changed while being read")

    def finish(self):
        for path, before in self.stat_before.items():
            try:
                after = path.stat()
                if any(getattr(before, key) != getattr(after, key) for key in
                       ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")):
                    self.error(str(path), "closed input changed during absence check")
            except OSError as error:
                self.error(str(path), error)


def inspect(args):
    started = time.monotonic_ns()
    roots = [args.matrix.resolve(strict=True), args.outer.resolve(strict=True), args.run.resolve(strict=True)]
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(output)
    if any(output.is_relative_to(root) for root in roots):
        raise ValueError("output must be outside the closed evidence roots")
    evidence = Evidence()
    # The closed inventories preserve all observed owned PID/start identities.
    # Raw motion/odometry streams and map blobs contain no additional process
    # inventory; do not turn absence checking into a telemetry/science replay.
    paths = {path for root in roots for path in root.rglob("*.json")
             if path.is_file() and "execution_inputs" not in path.parts}
    paths.add(roots[0]/"ledger.jsonl")
    paths.update(path for path in roots[2].rglob("launch.log") if path.is_file())
    paths = sorted(paths)
    for path in paths:
        try:
            evidence.consume(path)
        except (OSError, ValueError, TypeError) as error:
            evidence.error(str(path), error)
    required = [roots[0]/"ledger.jsonl", roots[0]/"summary.json", roots[0]/"interface/live_custody.json",
                roots[0]/"interface/native.json", roots[0]/"interface/watcher.json", roots[1]/"actual_wait.json",
                roots[2]/"benchmark_summary.json"]
    for path in required:
        if path not in evidence.stat_before:
            evidence.error(str(path), "required closed input is missing or unreadable")
    if not list(roots[2].rglob("supervisor_shutdown.json")):
        evidence.error(str(roots[2]), "no saved supervisor shutdown inventory")
    live = evidence.documents.get(str(roots[0]/"interface/live_custody.json"), {})
    matrix = evidence.documents.get(str(roots[0]/"summary.json"), {})
    outer = evidence.documents.get(str(roots[1]/"actual_wait.json"), {})
    if live.get("closed") is not True or matrix.get("all_submitted_children_waited") is not True or outer.get("actual_waited") is not True:
        evidence.error("closed boundary", "custody closed / all submitted children waited / outer actual waited must be true")
    if not evidence.identities:
        evidence.error("saved identities", "empty identity set cannot prove absence")
    known_pids = {pid for pid, start in evidence.identities}
    unbound = sorted((set(evidence.pid_only) | evidence.launch_pids) - known_pids)
    if unbound:
        evidence.error("saved identities", "saved PID lacks any saved start identity: " + repr(unbound))
    present, reused, absent, unreadable = [], [], [], []
    observations_started = time.monotonic_ns()
    for pid, start in sorted(evidence.identities):
        lookup_ns = time.monotonic_ns()
        try:
            raw = (Path("/proc")/str(pid)/"stat").read_text()
            tail = raw.rsplit(")", 1)[1].split()
            current, state = int(tail[19]), tail[0]
            row = {"pid": pid, "saved_start_ticks": start, "current_start_ticks": current,
                   "state": state, "observed_monotonic_ns": lookup_ns}
            (present if current == start else reused).append(row)
        except (FileNotFoundError, ProcessLookupError):
            absent.append({"pid": pid, "start_ticks": start, "observed_monotonic_ns": lookup_ns})
        except (OSError, ValueError, IndexError) as error:
            unreadable.append({"pid": pid, "start_ticks": start, "error": repr(error)})
    evidence.finish()
    ended = time.monotonic_ns()
    passed = not (evidence.errors or present or unreadable)
    script_raw = Path(__file__).read_bytes()
    return {"schema": SCHEMA, "scope": "engineering_external_saved_identity_absence_only",
            "passed": passed, "all_saved_identities_absent": passed,
            "scientific_pass_claimed": False, "native_admission": False,
            "unrecorded_process_absence_claimed": False,
            "native_runs": 0, "gpu_calls": 0, "signals_sent": 0,
            "implementation": {"path": str(Path(__file__).resolve()), "bytes": len(script_raw),
                               "sha256": hashlib.sha256(script_raw).hexdigest()},
            "started_monotonic_ns": started, "lookup_started_monotonic_ns": observations_started,
            "ended_monotonic_ns": ended,
            "identity_rules": ["same-object pid/start_ticks", "same-object pid/process_start_ticks",
                               "same-object process_pid/process_start_ticks",
                               "same-object PREFIX_pid/PREFIX_start_ticks",
                               "positive JSON int or canonical decimal string; original types retained",
                               "ASCII producer field names; JSONL byte-bound stream scans decode all pid/start_ticks-bearing records",
                               "exact /proc start match including Z is present; PID reuse is a distinct identity"],
            "identity_count": len(evidence.identities),
            "identities": [{"pid": pid, "start_ticks": start, "occurrences": rows}
                           for (pid, start), rows in sorted(evidence.identities.items())],
            "present": present, "same_pid_different_start": reused, "absent_proc_stat": absent,
            "unreadable": unreadable, "saved_launch_pid_count": len(evidence.launch_pids),
            "pids_without_saved_start": unbound, "errors": evidence.errors,
            "input_bindings": evidence.bindings,
            "enumeration_scope": "All closed JSON inventories under matrix/outer/run plus matrix ledger and native launch process receipts; launch PID coverage against saved starts is mandatory.",
            "excluded_scope": "Raw motion/odometry/physics streams and execution_inputs map/costmap blobs are not process inventories. No actor/map truth, scientific consumer or continuous plant check executes."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, default=Path("/tmp/mr3_p2a_reach_v16_matrix"))
    parser.add_argument("--outer", type=Path, default=Path("/tmp/mr3_p2a_reach_v16_matrix_wait"))
    parser.add_argument("--run", type=Path, default=Path(DEFAULT_RUN))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = inspect(args)
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"schema": SCHEMA, "passed": result["passed"], "identity_count": result["identity_count"],
                      "present": result["present"], "unreadable": result["unreadable"],
                      "errors": result["errors"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
