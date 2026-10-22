"""Independent proxy trace checks; no environment, model or optimizer is run.

Every returned observation is re-encoded. Candidate/mask construction is
replayed only for each reset, first returned step and last returned step.
This bounded interface audit supplies no native or training qualification.
"""

import argparse
import ast
from functools import lru_cache
import gzip
import hashlib
import importlib.util
import inspect
import json
import math
import os
from pathlib import Path
import re
import random
import subprocess
import sys
import time
from types import ModuleType

import numpy as np

ROOT = Path(__file__).resolve().parents[7]
PURE = ROOT / "ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration"
SCHEMA = "mr3-proxy2d-trace-v1"
CONTRACT = "mr3-own-known-shared-unknown-v1"
EXACT_SEED_RULE = "exact-point-bridge-v1"
EXACT_NAVIGATION_RULE = "mr3-navigation-geometric-staging-v6-exact-seed-v1"
EXACT_SEED_RULE_V2 = "exact-point-bridge-v2"
EXACT_NAVIGATION_RULES = {
    EXACT_SEED_RULE: EXACT_NAVIGATION_RULE,
    EXACT_SEED_RULE_V2: "mr3-navigation-geometric-staging-v7-exact-seed-v2",
}
EXACT_SEED_RULES = tuple(EXACT_NAVIGATION_RULES)
SEED_PROBE_RULES = {"seed_probe": EXACT_SEED_RULE, "seed_probe_v2": EXACT_SEED_RULE_V2}
NATIVE_FREEZE = "c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90"
ERRORS = (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, EOFError, RuntimeError,
          AssertionError, subprocess.SubprocessError)
VERIFIED_COUNTS = ("verified_action_count", "verified_uniform_action_count", "verified_actor_record_count",
                   "verified_step_return_count")


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def parse(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def process_identity(pid):
    raw = Path(f"/proc/{pid}/stat").read_text()
    fields = raw[raw.rfind(")") + 2:].split()
    return {"pid": pid, "parent": int(fields[1]), "group": int(fields[2]),
            "session": int(fields[3]), "start_ticks": int(fields[19]), "state": fields[0]}


@lru_cache(maxsize=1)
def native_builder():
    """Load the declared pure source closure without adding ROS to paths."""
    names = ("multi_robot_exploration", "multi_robot_exploration.mr3_episode",
             "multi_robot_exploration.mr3_reach_geometry",
             "multi_robot_exploration.mr3_seed_certificate",
             "multi_robot_exploration.mr3_observation")
    previous = {name: sys.modules.get(name) for name in names}
    try:
        package = ModuleType(names[0])
        package.__path__ = []
        sys.modules[names[0]] = package
        for name in names[1:]:
            path = PURE / (name.rsplit(".", 1)[1] + ".py")
            spec = importlib.util.spec_from_file_location(name, path)
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            spec.loader.exec_module(module)
        return sys.modules[names[-1]].build_snapshot
    finally:
        for name, value in previous.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def source_proof(freeze):
    require(isinstance(freeze, str) and re.fullmatch("[0-9a-f]{40}", freeze), "exact source freeze required")
    paths = [Path(__file__), Path(__file__).with_name("observation.py"),
             Path(__file__).with_name("proxy2d_codec.py"), PURE / "mr3_episode.py", PURE / "mr3_observation.py",
             PURE / "mr3_reach_geometry.py", PURE / "mr3_seed_certificate.py"]
    stable, proof = {}, {}
    for path in paths:
        raw = path.read_bytes()
        relative = path.relative_to(ROOT).as_posix()
        frozen = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=ROOT,
                                         stderr=subprocess.PIPE)
        require(raw == frozen, "audit/actor source differs from exact freeze: " + relative)
        stable[path] = raw
        proof[relative] = {"sha256": sha(raw), "git_source": freeze + ":" + relative}
    return proof, stable


def tensor_proofs(snapshot):
    from .observation import encode_snapshot
    return {name: {"shape": list(value.shape), "dtype": str(value.dtype),
                   "sha256": sha(np.ascontiguousarray(value).tobytes())}
            for name, value in encode_snapshot(snapshot).items()}


def seed_checks(params):
    """Recompute only received navigation-map provenance and seed diagnostics.

    No path field, frontier, candidate or mask is constructed here. The pure
    source's state normalization, native clearance graph and seed diagnostic
    functions are the same frozen functions used by build_snapshot.
    """
    functions = native_builder().__globals__
    seed_rule = params.get("seed_rule")
    require(seed_rule in EXACT_SEED_RULES, "seed-only check requires explicit exact rule")
    now, epoch = float(params["now"]), params["epoch"]
    require(math.isfinite(now) and isinstance(epoch, str) and bool(epoch),
            "seed-only clock/epoch is invalid")
    require(len(params["robots"]) == 3, "seed-only robot inventory differs")
    states = {robot["name"]: functions["_robot_state"](robot, now) for robot in params["robots"]}
    require(set(states) == {"tb1", "tb2", "tb3"}, "seed-only robot inventory differs")
    checked = {}
    for name in ("tb1", "tb2", "tb3"):
        entry = params["navigation_maps"].get(name)
        reason = "missing_received_navigation_map"
        metadata = {"source": "delivered_navigation_map", "missing": True,
            "epoch": None, "sequence": None, "version": None, "source_stamp": None, "received_stamp": None,
            "source_age_sec": None, "received_age_sec": None, "source_metadata_missing": True,
            "payload_sha256": None, "native_shape": None, "native_resolution_m": None,
            "native_origin_m": None, "unavailable_reason": reason,
            "seed_cell": None, "seed_cell_clearance_m": None, "seed_pose_cell_offset_m": None,
            "seed_pose_clearance_lower_bound_m": None, "seed_required_clearance_m": functions["CLEARANCE_M"],
            "seed_rejection_reason": reason, "seed_rule": seed_rule,
            "seed_point_bridge_certificate": None}
        if entry is not None and entry.get("grid") is not None:
            grid = functions["_received_grid"](entry["grid"])
            resolution = functions["_finite"](entry.get("resolution"))
            origin = entry.get("origin", ())
            require(resolution is not None and resolution > 0 and len(origin) == 2
                    and all(functions["_finite"](value) is not None for value in origin),
                    "seed-only delivered map geometry is invalid")
            origin = tuple(float(value) for value in origin)
            source = functions["_finite"](entry.get("source_stamp"))
            received = functions["_finite"](entry.get("received_stamp"))
            metadata.update(missing=not bool(grid.size), epoch=entry.get("epoch"), sequence=entry.get("sequence"),
                version=entry.get("version"), source_stamp=source, received_stamp=received,
                source_age_sec=functions["_age"](now, source), received_age_sec=functions["_age"](now, received),
                source_metadata_missing=source is None or received is None, payload_sha256=entry.get("payload_sha256"),
                native_shape=list(grid.shape), native_resolution_m=resolution, native_origin_m=list(origin),
                unavailable_reason=None)
            invalid_epoch = metadata["epoch"] is not None and metadata["epoch"] != epoch
            future = any(stamp is not None and stamp > now + 1e-6 for stamp in (source, received))
            if invalid_epoch or future:
                reason = "cross_epoch" if invalid_epoch else "future_map"
                metadata.update(missing=True, unavailable_reason=reason, seed_rejection_reason=reason)
            elif grid.size:
                traversable, clearance = functions["native_traversable"](grid, resolution)
                _, _, diagnostic = functions["_seed_diagnostics"](
                    grid, traversable, clearance, states[name], resolution, origin, seed_rule=seed_rule)
                metadata.update(diagnostic)
                if diagnostic["seed_rejection_reason"] is not None:
                    metadata["unavailable_reason"] = "robot_seed_not_observed_safe"
            else:
                metadata.update(unavailable_reason="empty_received_own_map",
                                seed_rejection_reason="empty_received_own_map")
        checked[name] = metadata
    return checked


class PureBuilder:
    """Own a system-Python pure-function worker; no ROS or environment is made."""

    def __init__(self):
        from .ipc import JsonLinePeer
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        environment.update(PYTHONNOUSERSITE="1", PYTHONDONTWRITEBYTECODE="1", CUDA_VISIBLE_DEVICES="")
        self.argv = ["/usr/bin/python3", "-B", "-m", "mr3_learning.audit_proxy2d", "--pure-builder"]
        self.started_ns = time.monotonic_ns()
        self.process = subprocess.Popen(self.argv,
            cwd=Path(__file__).resolve().parent.parent, env=environment,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        self.peer = JsonLinePeer(self.process.stdout.fileno(), self.process.stdin.fileno())
        self.identity = process_identity(self.process.pid)
        self.sequence = 0
        self.build_calls = 0
        self.seed_calls = 0
        self.receipt = None

    def __enter__(self):
        return self

    def __exit__(self, *unused):
        self.close()

    def __call__(self, **params):
        self.build_calls += 1
        return self._request("build", params)["snapshot"]

    def seed_checks(self, **params):
        self.seed_calls += 1
        return self._request("seed_checks", params)["seed_checks"]

    def _request(self, operation, params):
        from .proxy2d_codec import encode_arrays
        self.sequence += 1
        self.peer.send({"operation": operation, "sequence": self.sequence, "params": encode_arrays(params)})
        result = self.peer.receive(60.)
        require(result.get("sequence") == self.sequence and result.get("ok") is True,
                "pure actor rebuild failed: " + str(result.get("error")))
        return result

    def close(self):
        if self.receipt is not None:
            return self.receipt
        if self.process.stdin is not None:
            self.process.stdin.close()
        try:
            code = self.process.wait(timeout=5.)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5.)
            raise RuntimeError("pure actor rebuild worker did not close normally")
        finally:
            self.process.stdout.close()
        self.receipt = {"argv": self.argv, "pid": self.process.pid,
                        "child_identity": self.identity,
                        "started_monotonic_ns": self.started_ns, "ended_monotonic_ns": time.monotonic_ns(),
                        "returncode": code, "actual_waited": True, "pure_build_calls": self.build_calls,
                        "pure_seed_check_calls": self.seed_calls, "pure_requests": self.sequence}
        require(code == 0, "pure actor rebuild worker failed to close")
        return self.receipt


def pure_builder_server():
    """System Python/SciPy executes only original build_snapshot on supplied data."""
    from .proxy2d_codec import decode_arrays
    build = native_builder()
    for raw in sys.stdin.buffer:
        request = parse(raw)
        try:
            require(request.get("operation") in ("build", "seed_checks"), "unsupported pure rebuild operation")
            params = decode_arrays(request["params"])
            inspect.signature(build).bind(**params)
            operation = request["operation"]
            response = {"sequence": request["sequence"], "ok": True,
                        "snapshot" if operation == "build" else "seed_checks":
                            build(**params) if operation == "build" else seed_checks(params)}
        except ERRORS as error:
            response = {"sequence": request.get("sequence"), "ok": False, "error": str(error)}
        sys.stdout.buffer.write(canonical(response) + b"\n")
        sys.stdout.buffer.flush()


def _no_truth(value):
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = key.lower().replace("_", "").replace("-", "")
            require("truth" not in normalized and "evaluator" not in normalized,
                    "private truth/evaluator data in actor parameters")
            _no_truth(item)
    elif isinstance(value, list):
        for item in value:
            _no_truth(item)


def actor_record(directory, row, *, rebuild=False, builder=None):
    """Validate an actual saved actor call, with optional full deterministic replay."""
    from .proxy2d_codec import decode_arrays
    directory = Path(directory).resolve()
    snapshot, reference = row["snapshot"], row["actor_input_ref"]
    relative = reference["path"]
    require(isinstance(relative, str) and re.fullmatch(r"inputs/[0-9a-f]{64}\.json\.gz", relative),
            "actor input reference is not content addressed")
    path = directory / relative
    require(path.resolve().is_relative_to(directory), "actor input escaped its episode")
    raw = path.read_bytes()
    decoded = gzip.decompress(raw)
    encoded = parse(decoded)
    require(canonical(encoded) == decoded and sha(decoded) == reference["sha256"]
            == Path(relative).name.removesuffix(".json.gz"), "actor input bytes/digest differ")
    _no_truth(encoded)
    params = decode_arrays(encoded)
    allowed = {"raw_grid", "resolution", "origin", "robots", "now", "epoch", "map_version", "sequence",
               "map_source_stamp", "map_received_stamp", "map_sources", "task_start", "robot_maps", "navigation_maps",
               "seed_rule"}
    require(set(params) <= allowed, "unknown actor construction parameter")
    seed_rule = params.get("seed_rule", "legacy")
    require(seed_rule in ("legacy", *EXACT_SEED_RULES), "unknown actor seed rule")
    navigation = params.get("navigation_maps")
    require(isinstance(navigation, dict) and set(navigation) == {"tb1", "tb2", "tb3"}
            and all(isinstance(value, dict) and value.get("composition_version") == CONTRACT
                    for value in navigation.values()), "explicit received navigation composition is required")
    candidate_rule = snapshot.get("candidate_rule", {})
    require(snapshot.get("schema") == "mr3-observation-v3"
            and candidate_rule.get("version") == (EXACT_NAVIGATION_RULES[seed_rule] if seed_rule in EXACT_SEED_RULES
                                                    else "mr3-navigation-geometric-staging-v5")
            and snapshot["candidate_rule"].get("navigation_composition") == CONTRACT,
            "proxy actor silently changed snapshot/candidate/navigation contract")
    require((candidate_rule.get("seed_rule") == seed_rule if seed_rule in EXACT_SEED_RULES
             else "seed_rule" not in candidate_rule), "actor seed rule and snapshot contract differ")
    grids = [params.get("raw_grid"), *[value.get("grid") for value in navigation.values()]]
    require(all(isinstance(grid, np.ndarray) and grid.ndim == 2
                and grid.dtype in (np.dtype("int8"), np.dtype("int16"))
                and np.all((grid >= -1) & (grid <= 100))
                for grid in grids), "received actor grids must be two-dimensional int8/int16 occupancy arrays")
    require(snapshot["epoch"] == params["epoch"] == row["epoch"]
            and snapshot["sequence"] == params["sequence"]
            and snapshot["map_version"] == params["map_version"]
            and snapshot["source_stamp"] == params["now"], "actor call/snapshot identity differs")
    expected = tensor_proofs(snapshot)
    require(row["tensor_proofs"] == expected, "encoded tensor dtype/shape/bytes differ")
    if rebuild or seed_rule in EXACT_SEED_RULES:
        owned = PureBuilder() if builder is None else None
        try:
            selected = owned if owned is not None else builder
            if seed_rule in EXACT_SEED_RULES:
                checks = selected.seed_checks(**params)
                require(set(snapshot.get("path_maps", {})) == set(checks), "seed path-map inventory differs")
                for name, expected_seed in checks.items():
                    actual = snapshot["path_maps"][name]
                    actual_seed = {key: value for key, value in actual.items()
                                   if key.startswith("seed_") or key in expected_seed}
                    require(canonical(actual_seed) == canonical(expected_seed),
                            "received seed provenance/point/bridge certificate differs: " + name)
            if rebuild:
                replay = selected(**params)
                require(canonical(replay) == canonical(snapshot), "candidate/mask/full snapshot replay differs")
        finally:
            if owned is not None:
                owned.close()
    return {"input_path": str(path), "input_encoded_sha256": sha(raw),
            "input_canonical_sha256": sha(decoded), "input_bytes": len(raw),
            "snapshot_digest": snapshot["digest"], "tensor_proofs": expected,
            "full_snapshot_rebuilt": rebuild, "seed_rule": seed_rule,
            "exact_seed_certificate_source_replayed": seed_rule in EXACT_SEED_RULES,
            "exact_seed_robot_checks": 3 if seed_rule in EXACT_SEED_RULES else 0}, (path, raw)


def _duration(row, previous=None, resetting=False):
    for key in ("dt", "physical_dt", "reward"):
        value = row[key]
        require(type(value) in (int, float) and math.isfinite(value), "nonfinite/typed transition scalar")
    require(type(row["terminated"]) is bool and type(row["truncated"]) is bool
            and not (row["terminated"] and row["truncated"]), "invalid terminal/truncation flags")
    if resetting:
        require(row["dt"] == row["physical_dt"] == row["reward"] == 0
                and not row["terminated"] and not row["truncated"] and row.get("reason") is None,
                "reset must be live with zero duration/reward")
        return
    elapsed = round(row["snapshot"]["source_stamp"] * 10**9) - round(previous["source_stamp"] * 10**9)
    require(round(row["physical_dt"] * 10**9) == elapsed and 0 <= row["dt"] <= row["physical_dt"]
            and 0 < elapsed <= 1_000_000_000, "transition physical/reward time differs")
    if not row["terminated"]:
        require(elapsed == 1_000_000_000 and row["dt"] == 1., "nonterminal step is not exactly one second")
    if row["reason"] == "timeout":
        require(row["terminated"] and not row["truncated"], "deadline must terminate before external cut")
    if row["snapshot"].get("task_elapsed_sec", 0) >= 300.:
        require(row["terminated"] and row["reason"] == "timeout", "300-second deadline was not terminal")
    if row["truncated"]:
        require(row["reason"] in ("external_sampler_limit", "external_truncation"),
                "external cut lacks its declared truncation reason")


def audit_episode(directory, freeze, *, builder=None, verify_sources=True, rng=None):
    directory = Path(directory).resolve()
    result = {"schema": "mr3-proxy2d-episode-trace-audit-v1", "directory": str(directory),
              "freeze": freeze, "passed": False, "errors": [], "qualification": False,
              "training_eligible": False, "native_credit": False, "step_attempts": 0,
              "step_returns": 0, "step_errors": 0, "records": 0,
              "event_count_scope": "raw parsed event rows, including the unverified suffix after a failure",
              "raw_event_counts_complete": False, "raw_close_records": 0, "raw_closed_true_records": 0,
              "raw_global_attempt_tickets": [],
              "validated_prefix_records": 0, "causal_validation_complete": False,
              "verified_count_scope": "action=preceding mask/digest/version; uniform=successful RNG comparison; "
                                      "actor=saved input/digest/tensor checks; return=settled duration/actor/timestamp checks",
              "attempt_start_wall_ns": [], "return_end_wall_ns": [],
              "actor_records": [], "full_rebuild_event_sequences": [],
              "scope": "All trace pairing, saved masks and tensor encodings; reset, first and last returned "
                       "steps receive full build_snapshot replay. Other candidate constructions are not replayed. "
                       "Received-only source architecture and hidden-truth perturbations require separate conformity evidence."}
    result.update({key: 0 for key in VERIFIED_COUNTS})
    stable, previous, pending, last_return = {}, None, None, None
    epoch, env_id, episode_index, closed, done = None, None, None, False, False
    processed_returns = 0
    try:
        if verify_sources:
            result["source_proof"], sources = source_proof(freeze)
            stable.update(sources)
        path = directory / "trace.jsonl.gz"
        raw_trace = path.read_bytes()
        stable[path] = raw_trace
        trace = gzip.decompress(raw_trace)
        result["trace_sha256"] = sha(raw_trace)
        lines = trace.splitlines()
        # Account for all readable event rows even if an earlier semantic
        # failure prevents a valid causal replay of the remaining suffix.
        rows = []
        for number, raw in enumerate(lines, 1):
            try:
                row = parse(raw)
                require(isinstance(row, dict), "trace row is not an object")
                rows.append((number, row))
            except ERRORS as error:
                result["errors"].append(f"trace row {number}: {error}")
        result["records"] = len(lines)
        result["raw_event_counts_complete"] = len(rows) == len(lines)
        result["raw_close_records"] = sum(row.get("event") == "close" for _, row in rows)
        result["raw_closed_true_records"] = sum(row.get("event") == "close" and row.get("closed") is True
                                                 for _, row in rows)
        result["raw_global_attempt_tickets"] = [row.get("global_attempt") for _, row in rows
                                                if row.get("event") == "step_attempt"]
        for key, event in (("step_attempts", "step_attempt"), ("step_returns", "step_return"),
                           ("step_errors", "step_error")):
            result[key] = sum(row.get("event") == event for _, row in rows)
        require(len(rows) == len(lines), "trace includes unreadable rows; event counts are only a readable lower bound")
        for number, row in rows:
            require(row.get("schema") == SCHEMA and type(row.get("event_sequence")) is int
                    and row["event_sequence"] == number
                    and row.get("proxy_only") is True, "trace identity/sequence/proxy declaration differs")
            require(not closed, "record after episode close")
            if epoch is None:
                epoch, env_id, episode_index = row["epoch"], row["env_id"], row["episode_index"]
                require(isinstance(epoch, str) and epoch and type(env_id) is int and env_id >= 0
                        and type(episode_index) is int and episode_index > 0, "invalid episode identity")
            require(row["epoch"] == epoch and row["env_id"] == env_id
                    and row["episode_index"] == episode_index, "mixed episode identity")
            event = row["event"]
            if event == "reset":
                require(number == 1 and previous is None, "reset duplicated or not first")
                _duration(row, resetting=True)
                report, binding = actor_record(directory, row, rebuild=True, builder=builder)
                result["seed_rule"] = report["seed_rule"]
                stable[binding[0]] = binding[1]
                result["actor_records"].append(report)
                result["full_rebuild_event_sequences"].append(number)
                previous = row["snapshot"]
            elif event == "step_attempt":
                require(previous is not None and pending is None and not done, "attempt without a live settled observation")
                mask = row["joint_action_mask"]
                action = row["action"]
                require(mask == previous["joint_action_mask"] and len(mask) == 1000
                        and all(type(value) is bool for value in mask)
                        and type(action) is int and 0 <= action < 1000 and mask[action]
                        and row["preceding_digest"] == previous["digest"]
                        and row["candidate_version"] == previous["candidate_version"],
                        "action/mask differs from actual preceding actor snapshot")
                result["verified_action_count"] += 1
                pending = row
                if rng is not None:
                    require(action == rng.choice([i for i, legal in enumerate(mask) if legal]),
                            "action differs from the declared independent uniform random stream")
                    result["verified_uniform_action_count"] += 1
                if "started_wall_ns" in row:
                    require(type(row["started_wall_ns"]) is int and row["started_wall_ns"] > 0,
                            "attempt start wall timestamp is invalid")
                    result["attempt_start_wall_ns"].append(row["started_wall_ns"])
                require(result["step_attempts"] <= 300, "episode exceeded 300 attempted ENV.step calls")
            elif event == "step_return":
                require(pending is not None, "return has no attempted ENV.step")
                require(row["snapshot"]["sequence"] > previous["sequence"], "old observation sequence returned")
                _duration(row, previous)
                report, binding = actor_record(directory, row, rebuild=processed_returns == 0, builder=builder)
                require(report["seed_rule"] == result["seed_rule"], "episode changed actor seed rule")
                stable[binding[0]] = binding[1]
                result["actor_records"].append(report)
                if report["full_snapshot_rebuilt"]:
                    result["full_rebuild_event_sequences"].append(number)
                processed_returns += 1
                if "ended_wall_ns" in row:
                    require(type(row["ended_wall_ns"]) is int and row["ended_wall_ns"] >= pending.get("started_wall_ns", 0),
                            "step returned before its actual attempt")
                    result["return_end_wall_ns"].append(row["ended_wall_ns"])
                previous, last_return, pending = row["snapshot"], row, None
                result["verified_step_return_count"] += 1
                done = row["terminated"] or row["truncated"]
            elif event == "step_error":
                require(pending is not None and isinstance(row.get("error"), str) and row["error"],
                        "step error has no actual attempt or diagnostic")
                pending, done = None, True
                result["errors"].append("actual ENV.step error retained: " + row["error"])
            elif event == "close":
                require(previous is not None and pending is None, "close omitted pending attempt settlement")
                require(row.get("closed") is True, "proxy close did not complete")
                closed = True
            else:
                raise ValueError("unknown trace event: " + str(event))
            result["validated_prefix_records"] = number
        require(closed and previous is not None and pending is None, "episode trace is not closed")
        require(result["step_attempts"] == result["step_returns"] + result["step_errors"],
                "attempt accounting excluded failed ENV.step calls")
        if last_return is not None and last_return["event_sequence"] not in result["full_rebuild_event_sequences"]:
            report, binding = actor_record(directory, last_return, rebuild=True, builder=builder)
            stable[binding[0]] = binding[1]
            result["last_return_full_rebuild"] = report
            result["full_rebuild_event_sequences"].append(last_return["event_sequence"])
        result["causal_validation_complete"] = True
    except ERRORS as error:
        result["errors"].append(str(error))
    try:
        require(stable and all(path.read_bytes() == raw for path, raw in stable.items()),
                "audit source or bound trace/input bytes changed")
        result["bound_bytes_unchanged"] = True
    except ERRORS as error:
        result["bound_bytes_unchanged"] = False
        result["errors"].append(str(error))
    result.update(epoch=epoch, env_id=env_id, episode_index=episode_index,
                  verified_actor_record_count=len(result["actor_records"]),
                  last_verified_return_terminal=(None if last_return is None else
                      {key: last_return[key] for key in ("terminated", "truncated", "reason")}),
                  verified_close=closed, closed=closed,
                  closed_scope="causal validation reached the close record; raw observed close counts are separate",
                  passed=closed and not result["errors"])
    result["verified_exact_seed_actor_records"] = sum(
        report.get("exact_seed_certificate_source_replayed") is True for report in result["actor_records"])
    result["verified_exact_seed_robot_checks"] = sum(
        report.get("exact_seed_robot_checks", 0) for report in result["actor_records"])
    return result


def _trace_wall_coverage(report, group_start, collection_deadline, group_end):
    """Separate checked-prefix coverage from any observed clock violation."""
    result = {}
    for name, values, expected, lower, upper in (
            ("attempt_start", report["attempt_start_wall_ns"], report["step_attempts"], group_start, collection_deadline),
            ("return_end", report["return_end_wall_ns"], report["step_returns"], None, group_end)):
        result[name] = {"expected_raw_count": expected, "verified_timestamp_count": len(values),
                        "coverage_complete": report["raw_event_counts_complete"] and len(values) == expected,
                        "observed_out_of_bounds_count": sum(value > upper or (lower is not None and value < lower)
                                                            for value in values),
                        "lower_bound_ns": lower, "upper_bound_ns": upper}
    return result


def _activity_contract(summary):
    """Independent fixed-spec checks; absence retains the strict V22 contract."""
    cells = [[scene, seed] for scene in ("open", "rooms", "corridors") for seed in (101, 103)]
    if "activity_spec" not in summary:
        return {"kind": "legacy_v22", "groups": [1, 4], "cells": cells, "steps_per_episode": 300,
                "max_attempts": 9000, "activity_seconds": 3600, "group_wall_seconds": None}
    spec = summary["activity_spec"]
    require(isinstance(spec, dict) and spec.get("kind") in ("profile", "short_capacity", "full_behavior", "karto_profile", "karto_behavior", *SEED_PROBE_RULES),
            "unknown bounded proxy activity specification")
    profile = spec["kind"] in ("profile", "karto_profile")
    expected = {"schema": "mr3-proxy2d-activity-spec-v1", "kind": spec["kind"],
                "groups": [1] if profile else [1, 4], "cells": [["open", 101]] if profile else cells,
                "steps_per_episode": 8, "max_attempts": 8 if profile else 240,
                "activity_seconds": 600 if profile else 1800}
    if spec["kind"] in ("full_behavior", "karto_behavior", *SEED_PROBE_RULES):
        expected = {"schema": "mr3-proxy2d-activity-spec-v1", "kind": spec["kind"],
                    "groups": [3], "cells": [["open", 101], ["rooms", 101], ["corridors", 101]],
                    "worker_cells": [[[["open", 101]], [["rooms", 101]], [["corridors", 101]]]],
                    "steps_per_episode": 64 if spec["kind"] in SEED_PROBE_RULES else 300,
                    "max_attempts": 192 if spec["kind"] in SEED_PROBE_RULES else 900,
                    "activity_seconds": 1800 if spec["kind"] in SEED_PROBE_RULES else 3600}
    if spec["kind"] in SEED_PROBE_RULES:
        require(summary.get("seed_rule") == SEED_PROBE_RULES[spec["kind"]],
                "seed probe must explicitly declare the exact certificate rule")
    require(canonical(spec) == canonical(expected), "bounded proxy activity differs from its exact fixed specification")
    require(summary.get("activity_kind") == spec["kind"] and summary.get("profile_enabled") is profile
            and canonical(summary.get("scheduled_cells")) == canonical(expected["cells"]),
            "summary activity kind/profile/schedule differs from its fixed specification")
    walls = ([240] if profile else [900] if spec["kind"] in SEED_PROBE_RULES else
             [2100] if spec["kind"] in ("full_behavior", "karto_behavior") else [400, 800])
    return {**expected, "group_wall_seconds": walls}


def verify_run_sources(bindings, freeze):
    require(isinstance(bindings, dict) and bindings, "proxy run has no source inventory")
    required = {path.relative_to(ROOT).as_posix() for path in (
        *Path(__file__).parent.glob("*proxy2d*.py"), *PURE.glob("mr3_proxy2d_*.py"),
        PURE / "mr3_proxy2d_karto_native.cpp",
        *(ROOT / "ros2_ws/ros2-multi-robot-automap/src/slam_toolbox/lib/karto_sdk/include/karto_sdk").glob("*.h"),
        *(ROOT / "ros2_ws/ros2-multi-robot-automap/src/slam_toolbox/lib/karto_sdk/include/karto_sdk").glob("*.hpp"),
        PURE / "mr3_observation.py", PURE / "mr3_episode.py", PURE / "mr3_protocol.py",
        PURE / "mr3_reach_geometry.py", PURE / "mr3_seed_certificate.py",
        PURE / "mr3_transport.py", PURE / "mr3_activity.py", PURE / "mr3_reward.py",
        PURE / "mr3_information.py", PURE / "task_evaluator.py",
        ROOT / "ros2_ws/ros2-multi-robot-automap/scripts/mr3_proxy2d_worker.py",
        ROOT / "ros2_ws/ros2-multi-robot-automap/src/merge_map/merge_map/merge_map.py",
        Path(__file__).with_name("env.py"), Path(__file__).with_name("ipc.py"),
        Path(__file__).with_name("observation.py"))}
    require(required <= bindings.keys(), "proxy source inventory omitted a current execution/audit dependency")
    stable, proof = {}, {}
    forbidden = {"torch", "tensorflow", "stable_baselines3", "sb3_contrib"}
    inspected = []
    for relative, expected in sorted(bindings.items()):
        path = ROOT / relative
        require(not Path(relative).is_absolute() and path.resolve().is_relative_to(ROOT),
                "run source escaped workspace")
        raw = path.read_bytes()
        frozen = subprocess.check_output(["git", "show", freeze + ":" + relative], cwd=ROOT,
                                         stderr=subprocess.PIPE)
        require(raw == frozen and sha(raw) == expected, "run source differs from declared freeze: " + relative)
        stable[path] = raw
        proof[relative] = expected
        if "proxy2d" in path.name and path.suffix == ".py" and not any(
                part in ("tests", "test") for part in path.parts):
            tree = ast.parse(raw)
            for node in ast.walk(tree):
                names = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                         else [node.module or ""] if isinstance(node, ast.ImportFrom) else [])
                require(not any(name.split(".", 1)[0] in forbidden for name in names),
                        "proxy execution/audit source imports a learning framework")
            inspected.append(relative)
    require(inspected, "no proxy execution/audit sources were bound")
    return proof, stable, inspected


def verify_karto_manifest(summary, stable):
    """Independent current ELF and frozen manifest binding for explicit Karto."""
    require(summary.get("mapper") == "karto", "Karto activity used another mapper")
    ref = summary["native_manifest"]
    path = Path(ref["path"]).resolve()
    relative = path.relative_to(ROOT).as_posix()
    raw = path.read_bytes()
    require(sha(raw) == ref["sha256"] == summary["source_bindings"][relative],
            "native manifest differs from frozen source proof")
    stable[path] = raw
    manifest = parse(raw)
    require(manifest["schema"] == "mr3-proxy2d-karto-native-manifest-v1", "wrong native manifest schema")
    artifacts = manifest["artifacts"]
    require(len(artifacts)==2 and {Path(p["path"]).name for p in artifacts} ==
            {"libmr3_karto_adapter.so","libkartoSlamToolbox.so"}, "wrong native ELF inventory")
    for item in artifacts:
        file = Path(item["path"]).resolve(strict=True)
        body = file.read_bytes()
        require(str(file)==item["path"] and sha(body)==item["sha256"] and len(body)==item["bytes"],
                "current native ELF differs from declared build")
        stable[file] = body
    adapter = next(p["path"] for p in artifacts if Path(p["path"]).name=="libmr3_karto_adapter.so")
    require(summary["mapper_library"]==adapter, "collection uses another adapter ELF")
    return sorted(({"path":p["path"],"sha256":p["sha256"]} for p in artifacts),key=lambda p:p["path"])


def verify_conformity(directory, specification, freeze):
    """Recalculate expected/actual comparisons from sealed reference bytes.

    This does not repeat the formal six build_snapshot replays or integrate a
    proxy world. Producer ``passed`` flags never determine the verdict.
    """
    require(isinstance(freeze, str) and re.fullmatch("[0-9a-f]{40}", freeze), "exact source freeze required")
    path = Path(specification["path"])
    path = path if path.is_absolute() else Path(directory) / path
    raw = path.read_bytes()
    require(sha(raw) == specification["sha256"], "conformity receipt bytes changed")
    formal = parse(raw)
    versioned = formal.get("schema") == "mr3-proxy2d-conformity-v2"
    require(formal.get("schema") in ("mr3-proxy2d-conformity-v1", "mr3-proxy2d-conformity-v2")
            and formal.get("freeze") == freeze,
            "conformity receipt source identity differs")
    require((formal.get("seed_rule") in EXACT_SEED_RULES if versioned
             else formal.get("seed_rule", "legacy") == "legacy"), "conformity schema/seed rule differs")
    seed_rule = formal.get("seed_rule", "legacy")
    require(formal.get("errors") == [] and formal.get("input_bytes_unchanged") is True
            and all(formal.get(key) is False for key in ("qualification", "training_eligible", "native_credit")),
            "formal conformity has a retained error/unstable input or wrong credit scope")
    stable = {path: raw}

    def reference(spec):
        selected = Path(spec["path"])
        selected = selected if selected.is_absolute() else Path(directory) / selected
        content = selected.read_bytes()
        require(sha(content) == spec["sha256"] and len(content) == spec.get("bytes", len(content)),
                "conformity reference bytes differ: " + str(selected))
        require(stable.setdefault(selected, content) == content, "conformity reference changed between reads")
        return content

    required_sources = {selected.relative_to(ROOT).as_posix() for selected in (
        Path(__file__), Path(__file__).with_name("proxy2d_conformity.py"),
        Path(__file__).with_name("observation.py"), Path(__file__).with_name("proxy2d_codec.py"),
        PURE / "mr3_observation.py", PURE / "mr3_episode.py", PURE / "mr3_observation_archive.py",
        PURE / "mr3_proxy2d_world.py", PURE / "mr3_reward.py", PURE / "mr3_task_contract.py",
        PURE / "mr3_contacts.py", PURE / "mr3_transport.py",
        PURE.parents[1] / "multi_robot/models/turtlebot3_waffle/model.sdf",
        PURE.parents[1] / "multi_robot/config/mr3_p1a/open.json")}
    if versioned:
        required_sources.update((PURE / name).relative_to(ROOT).as_posix()
                                for name in ("mr3_reach_geometry.py", "mr3_seed_certificate.py"))
    require(required_sources <= formal["source_proof"].keys(), "conformity source proof omitted a required dependency")
    native_sources = {selected.relative_to(ROOT).as_posix() for selected in (
        PURE / "mr3_observation.py", PURE / "mr3_episode.py", PURE / "mr3_observation_archive.py",
        Path(__file__).with_name("observation.py"))}
    for relative, spec in formal["source_proof"].items():
        selected = ROOT / relative
        require(not Path(relative).is_absolute() and selected.resolve().is_relative_to(ROOT),
                "conformity source escaped workspace")
        payload = selected.read_bytes()
        require(sha(payload) == spec["sha256"] and payload == subprocess.check_output(
            ["git", "show", freeze + ":" + relative], cwd=ROOT, stderr=subprocess.PIPE),
            "formal conformity source differs from exact freeze")
        if relative in native_sources:
            original = subprocess.check_output(["git", "show", NATIVE_FREEZE + ":" + relative],
                                               cwd=ROOT, stderr=subprocess.PIPE)
            if versioned and selected == PURE / "mr3_observation.py":
                require(spec.get("legacy_reference") == {"git_source": NATIVE_FREEZE + ":" + relative,
                    "sha256": sha(original), "bytes": len(original)},
                    "versioned source omitted/changed its complete V21 observation reference")
            else:
                require(payload == original, "native observation/encoder source changed")
        stable[selected] = payload
    inventory_raw = reference(formal["native_inventory"])
    inventory_relative = (Path(__file__).resolve().parent.parent /
                          "report/assets/20261020_mr3_p2a_v21/native_inventory_v1.json").relative_to(ROOT).as_posix()
    require(inventory_raw == subprocess.check_output(["git", "show", freeze + ":" + inventory_relative],
                                                     cwd=ROOT, stderr=subprocess.PIPE),
            "native inventory differs from the frozen V21 closed-byte inventory")
    inventory = parse(inventory_raw)
    require(inventory.get("schema") == "mr3-closed-byte-inventory-v1", "native conformity inventory differs")
    for spec in formal["native_input_index"].values():
        content = reference(spec)
        original = inventory["files"][spec["inventory_relative_path"]]
        require(sha(content) == original["sha256"] and len(content) == original["bytes"],
                "native conformity input differs from original inventory")
    records = formal["native_records"]
    expected_selections = {(f"worker0/episode{number:03d}_open_101", selection)
                           for number in (1, 2) for selection in ("reset", "first_step", "last_step")}
    require(len(records) == 6 and {(row["episode"], row["selection"]) for row in records} == expected_selections,
            "six predeclared native snapshot selections were omitted/replaced")
    native_verified = []

    def native_reference(spec):
        indexed = formal["native_input_index"][spec["inventory_relative_path"]]
        require(all(spec[key] == indexed[key] for key in ("path", "sha256", "bytes", "inventory_relative_path")),
                "selected native reference is absent from its inventoried input index")
        return reference(spec)

    for row in records:
        require(row["native_freeze"] == "c38e3e8ddc034bc0bf0b0cc4578cb6600ae51d90",
                "native observation reference freeze changed")
        spec = row["native_snapshot_ref"]
        lines = native_reference(spec).splitlines()
        line = {"reset": 1, "first_step": 2, "last_step": 33}[row["selection"]]
        require(len(lines) == 33 and spec["line_1based"] == line and sha(lines[line - 1]) == spec["line_sha256"],
                "native snapshot selection/line bytes changed")
        original = parse(lines[line - 1])
        snapshot = original["snapshot"]
        manifest = parse(native_reference(row["manifest_ref"]))
        require(manifest["snapshot_digest"] == snapshot["digest"]
                and manifest["sequence"] == snapshot["sequence"], "native map manifest belongs to another snapshot")
        expected = {"snapshot_canonical_sha256": sha(canonical(snapshot)), "tensor_proofs": tensor_proofs(snapshot)}
        require(row["expected"] == expected == row["actual"], "native full snapshot/tensor comparison differs")
        native_verified.append({"episode": row["episode"], "selection": row["selection"],
                                "verified_expected_actual": expected,
                                "recovery_scope": row["robot_recovery_scope"]})
    exact_verified, exact_wait = [], None
    if versioned:
        exact_verified, exact_wait = verify_exact_conformity_records(
            directory, formal, expected_selections, reference, inventory)
        # The versioned review recovers the same seven original received map
        # roles and independently rebuilds the six new-version snapshots.
        for item in exact_verified:
            for spec in item.pop("_bound_files"):
                selected, content = spec
                require(stable.setdefault(selected, content) == content,
                        "versioned reference changed between reads")
    synthetic = parse(reference(formal["synthetic_result_ref"]))
    require(synthetic["cases"] == formal["synthetic_cases"], "synthetic cases differ from actual helper output")
    if versioned:
        require(synthetic.get("seed_rule") == seed_rule, "synthetic helper used another seed rule")
    require(all(type(synthetic.get(key)) is int and synthetic[key] == 0
                for key in ("native_runs", "gpu_calls", "optimizer_steps")), "synthetic helper acquired native/learning calls")
    cases = formal["synthetic_cases"]
    require(len(cases) == 3 and {case["id"] for case in cases} == {
        "forward_turn_stop_halved_integration", "hidden_obstacle_same_received_actor", "reward_truth_only_reward_branch"},
        "synthetic conformity obligation inventory changed")
    checked = []
    for case in cases:
        documents = {Path(spec["path"]).name: parse(reference(spec))
                     for spec in case["input_refs"] if Path(spec["path"]).suffix == ".json"}
        # Non-JSON asset references still bind their exact original bytes.
        for spec in case["input_refs"]:
            reference(spec)
        if case["id"] == "forward_turn_stop_halved_integration":
            states = documents["convergence_states.json"]
            first, second, before, after = (states[key] for key in ("first", "second", "stop_before", "stop_after"))
            robots = ("tb1", "tb2", "tb3")
            measured = {
                "pose_error_m": max(math.hypot(first["poses"][n]["x"] - second["poses"][n]["x"],
                                              first["poses"][n]["y"] - second["poses"][n]["y"]) for n in robots),
                "yaw_error_rad": max(abs(first["poses"][n]["yaw"] - second["poses"][n]["yaw"]) for n in robots),
                "path_error_m": max(abs(first["path_lengths"][n] - second["path_lengths"][n]) for n in robots),
                "collision_count_difference": abs(first["collision_events"] - second["collision_events"]),
                "stop_displacement_m": max(math.hypot(before["poses"][n]["x"] - after["poses"][n]["x"],
                                                     before["poses"][n]["y"] - after["poses"][n]["y"]) for n in robots)}
            bounds = {"pose_error_m": 1e-10, "yaw_error_rad": 1e-10, "path_error_m": 1e-10,
                      "collision_count_difference": 0, "stop_displacement_m": 0}
            require(case["comparison"] == "upper_bounds" and case["expected"] == bounds
                    and case["actual"] == measured and all(type(value) in (int, float)
                    and math.isfinite(value) and 0 <= value <= bounds[key] for key, value in measured.items()),
                    "independently recalculated20/10ms convergence differs")
        elif case["id"] == "hidden_obstacle_same_received_actor":
            actors = [documents[f"hidden_actor_{number}.json"] for number in (0, 1)]
            if versioned:
                require(all(actor["parameters"].get("seed_rule") == seed_rule
                            and actor["snapshot"]["candidate_rule"].get("seed_rule") == seed_rule
                            and actor["snapshot"]["candidate_rule"].get("version") == EXACT_NAVIGATION_RULES[seed_rule]
                            for actor in actors), "hidden-obstacle comparison did not exercise exact actor rule")
            hashes = [{"actor_parameters_sha256": sha(canonical(actor["parameters"])),
                       "snapshot_sha256": sha(canonical(actor["snapshot"]))} for actor in actors]
            require(case["comparison"] == "equal" and case["expected"] == hashes[0] == hashes[1] == case["actual"],
                    "hidden obstacle changed the recorded received-only actor call/output")
            worlds = [spec for spec in case["input_refs"] if Path(spec["path"]).name == "p1c_open.world"]
            require(len(worlds) == 2 and worlds[0]["sha256"] != worlds[1]["sha256"],
                    "hidden-obstacle case does not bind two different world geometries")
        else:
            from .proxy2d_codec import decode_arrays
            inputs = decode_arrays(documents["reward_truth_inputs.json"])
            require(canonical(documents["reward_truth_inputs.json"]["actor_before"]) ==
                    canonical(documents["reward_truth_inputs.json"]["actor_after"]), "truth-only change modified actor parameters")
            truth, correct = inputs["truth_free"], inputs["correct"]
            require(isinstance(correct, np.ndarray) and correct.dtype == np.bool_
                    and len(truth) == 2 and not np.array_equal(truth[0], truth[1])
                    and all(grid.dtype == np.bool_ and grid.shape == correct.shape and np.any(grid)
                            and not np.any(correct & ~grid) for grid in truth), "reward truth counterfactual is invalid")
            require(isinstance(inputs["initial_correct"], np.ndarray)
                    and inputs["initial_correct"].dtype == np.bool_
                    and inputs["initial_correct"].shape == correct.shape and not np.any(inputs["initial_correct"])
                    and inputs["epoch"] == "isolated" and inputs["sequence"] == 1
                    and inputs["start_sim_time"] == inputs["step_start"] == 0. and inputs["step_end"] == 1.
                    and all(type(inputs[key]) is int and inputs[key] == 0
                            for key in ("collision_events", "goal_switches", "rejected_actions"))
                    and inputs["terminal_reason"] is None and inputs["external_truncation"] is None,
                    "reward fixture is not the declared first one-second empty-ledger zero-event advance")
            weights_class = next(node for node in ast.parse((PURE / "mr3_reward.py").read_bytes()).body
                                 if isinstance(node, ast.ClassDef) and node.name == "RewardWeights")
            weights = {node.target.id: ast.literal_eval(node.value) for node in weights_class.body
                       if isinstance(node, ast.AnnAssign)}
            # This formal fixture is the first1s zero-event advance from an
            # empty initial-correct ledger, not a new reward-policy definition.
            rewards = [weights["coverage"] * int(np.count_nonzero(correct)) / int(np.count_nonzero(grid))
                       - weights["time"] / 300. for grid in truth]
            encoded = documents["reward_truth_inputs.json"]
            expected = {"actor_parameters_sha256": sha(canonical(encoded["actor_before"])),
                        "snapshot_sha256": sha(canonical(encoded["snapshot_before"])), "rewards": rewards}
            actual = {"actor_parameters_sha256": sha(canonical(encoded["actor_after"])),
                      "snapshot_sha256": sha(canonical(encoded["snapshot_after"])), "rewards": rewards}
            require(case["comparison"] == "equal" and case["expected"] == expected == actual == case["actual"],
                    "independently recalculated reward-only truth comparison differs")
        checked.append({"id": case["id"], "comparison_recalculated": True})
    waits = [formal["pure_builder_actual_wait"], formal["synthetic_actual_wait"]]
    if exact_wait is not None:
        waits.append(exact_wait)
    for wait in waits:
        identity = wait["child_identity"]
        require(wait["actual_waited"] is True and wait["returncode"] == 0
                and type(identity["pid"]) is int and identity["pid"] > 0
                and type(identity["start_ticks"]) is int and identity["start_ticks"] > 0
                and wait["started_monotonic_ns"] <= wait["ended_monotonic_ns"],
                "conformity pure/synthetic helper lacks its true successful wait")
    require(all(selected.read_bytes() == payload for selected, payload in stable.items()),
            "conformity/source/native/reference bytes changed during independent comparison")
    return {"schema": "mr3-proxy2d-independent-conformity-review-v2" if versioned
                      else "mr3-proxy2d-independent-conformity-review-v1", "freeze": freeze,
            "passed": True, "qualification": False, "training_eligible": False, "native_credit": False,
            "formal_reference": specification, "native_records": native_verified, "synthetic_cases": checked,
            "helper_actual_waits": waits, "reference_files_checked": len(stable),
            "formal_producer_pass_flags_used": False, "additional_native_snapshot_replays": len(exact_verified),
            "seed_rule": seed_rule, "exact_records": exact_verified,
            "additional_current_version_snapshot_replays": len(exact_verified),
            "additional_native_runs": 0,
            "native_snapshot_replay_scope": "pure current-legacy compatibility calls, no native execution",
            "legacy_reference_scope": "six original snapshots/tensors; not new native execution"}, stable


def verify_exact_conformity_records(directory, formal, expected_selections, reference, inventory):
    """Independently bind original sufficient inputs and replay only exact six."""
    from .proxy2d_codec import encode_arrays
    from .proxy2d_conformity import NativeInputs, recover_parameters
    records = formal["exact_records"]
    seed_rule = formal["seed_rule"]
    require(seed_rule in EXACT_SEED_RULES, "unknown exact conformity rule")
    require(len(records) == 6 and {(row["episode"], row["selection"]) for row in records} == expected_selections,
            "six exact-version snapshot selections were omitted/replaced")
    original = {(row["episode"], row["selection"]): row for row in formal["native_records"]}
    inventory_path = Path(formal["native_inventory"]["path"])
    if not inventory_path.is_absolute():
        inventory_path = Path(directory) / inventory_path
    inputs = NativeInputs(inventory["original_root"], inventory_path)
    checked = []
    builder = PureBuilder()
    try:
        for row in records:
            require(row.get("seed_rule") == seed_rule and row.get("native_freeze") == NATIVE_FREEZE,
                    "exact record version/reference source differs")
            old = original[row["episode"], row["selection"]]
            spec = old["native_snapshot_ref"]
            raw = inputs.read(spec["inventory_relative_path"])
            require(sha(raw) == spec["sha256"], "exact replay changed the original native record")
            native = parse(raw.splitlines()[spec["line_1based"] - 1])
            params, _ = recover_parameters(inputs, row["episode"], native)
            legacy_digest = sha(canonical(encode_arrays(params)))
            require(row["legacy_parameters_sha256"] == old["sufficient_parameter_sha256"] == legacy_digest,
                    "exact replay did not use the same original sufficient parameters")
            legacy = builder(**params)
            require(canonical(legacy) == canonical(native["snapshot"])
                    and tensor_proofs(legacy) == old["expected"]["tensor_proofs"],
                    "current legacy full snapshot/tensors differ from original native reference")
            params["seed_rule"] = seed_rule
            expected_input = canonical(encode_arrays(params))
            require(row["sufficient_parameter_sha256"] == sha(expected_input),
                    "exact replay changed parameters beyond the declared seed rule")
            body = reference(row["actor_record_ref"])
            actor = parse(body)
            path = Path(row["actor_record_ref"]["path"])
            if not path.is_absolute():
                path = Path(directory) / path
            report, binding = actor_record(path.parent, actor, rebuild=True, builder=builder)
            require(gzip.decompress(binding[1]) == expected_input,
                    "saved exact actor inputs differ from recovered original inputs")
            expected = {"snapshot_canonical_sha256": sha(canonical(actor["snapshot"])),
                        "tensor_proofs": tensor_proofs(actor["snapshot"])}
            require(row["actual"] == expected and row["exact_seed_robot_checks"] == 3,
                    "exact snapshot/tensor/seed comparison differs")
            checked.append({"episode": row["episode"], "selection": row["selection"],
                "seed_rule": seed_rule, "same_original_received_parameters_verified": True,
                "current_legacy_snapshot_and_tensors_equal_original": True,
                "full_current_snapshot_rebuilt": True, "verified": expected,
                "exact_seed_robot_checks": report["exact_seed_robot_checks"], "_bound_files": [binding]})
        inputs.verify()
        require(all(formal["native_input_index"].get(relative) == proof
                    for relative, proof in inputs.proofs.items()),
                "exact native input recovery escaped its declared original input index")
        for item in checked:
            item["_bound_files"].extend(inputs.stable.items())
    finally:
        failure = sys.exc_info()[1]
        wait = builder.close()
        if failure is not None:
            failure.pure_builder_failure_wait = wait
    return checked, wait


def audit_conformity(directory, conformity, freeze):
    """Writeable failure receipt for pre-collection independent admission."""
    result = {"schema": "mr3-proxy2d-independent-conformity-review-v1", "directory": str(Path(directory).resolve()),
              "freeze": freeze, "passed": False, "errors": [], "qualification": False,
              "training_eligible": False, "native_credit": False,
              "formal_producer_pass_flags_used": False, "additional_native_snapshot_replays": 0}
    try:
        path = Path(conformity).resolve()
        review, _ = verify_conformity(directory, {"path": str(path), "sha256": sha(path.read_bytes())}, freeze)
        result.update(review)
        result["bound_bytes_unchanged"] = True
    except ERRORS as error:
        result["errors"].append(str(error))
        if hasattr(error, "pure_builder_failure_wait"):
            result["pure_builder_failure_wait"] = error.pure_builder_failure_wait
    return result


def audit_run(directory, freeze):
    directory = Path(directory).resolve()
    result = {"schema": "mr3-proxy2d-capacity-audit-v1", "directory": str(directory), "freeze": freeze,
              "passed": False, "errors": [], "episodes": [], "qualification": False,
              "training_eligible": False, "native_credit": False, "step_attempts": 0,
              "step_returns": 0, "step_errors": 0,
              "event_count_scope": "raw parsed trace events; verified coverage is counted separately",
              "uniform_actions_independently_replayed": 0,
              "scope": "Independent finite proxy capacity/trace audit; no learning, native qualification, "
                       "long-training capacity, transfer or95% reliability credit."}
    result.update({key: 0 for key in VERIFIED_COUNTS})
    stable, builder = {}, None
    try:
        proof, sources = source_proof(freeze)
        stable.update(sources)
        summary_path = directory / "capacity_summary.json"
        raw = summary_path.read_bytes()
        stable[summary_path] = raw
        summary = parse(raw)
        require(summary.get("schema") == "mr3-proxy2d-capacity-summary-v1" and summary.get("freeze") == freeze,
                "capacity summary schema/freeze differs")
        seed_rule = summary.get("seed_rule", "legacy")
        require(seed_rule in ("legacy", *EXACT_SEED_RULES), "unknown capacity seed rule")
        result["seed_rule"] = seed_rule
        contract = _activity_contract(summary)
        bounded = contract["kind"] != "legacy_v22"
        result.update(activity_kind=contract["kind"], activity_spec=summary.get("activity_spec"),
                      full_matrix_credit=False)
        require(summary.get("qualification") is False and summary.get("training_eligible") is False
                and summary.get("native_credit") is False,
                "proxy summary acquired unapproved qualification/training credit")
        require(all(type(summary.get(key)) is int and summary[key] == 0
                    for key in ("policy_calls", "gpu_calls", "optimizer_steps")), "proxy run declared learning calls")
        bound, run_sources, inspected = verify_run_sources(summary["source_bindings"], freeze)
        stable.update(run_sources)
        native_artifacts = (verify_karto_manifest(summary,stable)
            if contract["kind"] in ("karto_profile","karto_behavior", *SEED_PROBE_RULES) else None)
        result.update(source_proof=proof, run_source_bindings=bound,
                      proxy_sources_without_learning_framework_imports=inspected)
        start, deadline, collection = (summary[key] for key in (
            "activity_started_ns", "activity_deadline_ns", "collection_deadline_ns"))
        require(all(type(value) is int for value in (start, deadline, collection))
                and 0 < start < collection < deadline
                and deadline - start == contract["activity_seconds"] * 10**9,
                "activity must share its exact declared wall budget with a real close/audit reservation")
        if bounded:
            collection_started = summary["collection_started_ns"]
            require(type(collection_started) is int and start <= collection_started
                    and collection - collection_started == (240 if contract["kind"] in ("profile", "karto_profile") else
                        900 if contract["kind"] in SEED_PROBE_RULES else
                        2100 if contract["kind"] in ("full_behavior", "karto_behavior") else 1200) * 10**9
                    and collection <= deadline - 120 * 10**9,
                    "bounded collection reservation differs from its exact fixed clock contract")
        result["conformity"], receipt = verify_conformity(directory, summary["conformity"], freeze)
        require(result["conformity"].get("seed_rule", "legacy") == seed_rule,
                "capacity and conformity seed rules differ")
        stable.update(receipt)
        if summary.get("closed") is not True or summary.get("errors") != []:
            result["errors"].append("proxy collection retained errors or is not actually closed: " + str(summary.get("errors")))
        require(summary.get("forbidden_framework_imports") == [], "collection retained imported learning frameworks")
        groups = summary["groups"]
        if [group["workers"] for group in groups] != contract["groups"]:
            result["errors"].append("single/four-environment activity inventory differs")
        discovered = {path.parent.resolve() for path in directory.rglob("trace.jsonl.gz")
                      if "conformity" not in path.relative_to(directory).parts}
        listed = [Path(item["directory"]).resolve() for group in groups for item in group["episodes"]]
        if len(listed) != len(set(listed)) or discovered != set(listed):
            result["errors"].append("attempted proxy episode inventory omitted/duplicated trace")
        require(not list(directory.rglob("*.zip")) and not list(directory.rglob("*.pt"))
                and not list(directory.rglob("*.pth")), "model/checkpoint artifact appeared in zero-learning activity")
        cells = {tuple(cell) for cell in contract["cells"]}
        builder = PureBuilder()
        epochs, audited = set(), set()
        result["group_capacity"] = []
        group_end = start
        for group_index, group in enumerate(groups):
            workers = group["workers"]
            allowed_workers = contract["groups"] if contract["kind"] in ("full_behavior", "karto_behavior", *SEED_PROBE_RULES) else (1, 4)
            require(type(workers) is int and workers in allowed_workers, "invalid environment-group identity")
            if not (type(group["started_ns"]) is int and type(group["ended_ns"]) is int
                    and group_end <= group["started_ns"] <= group["ended_ns"] <= deadline):
                result["errors"].append("group denominator is outside the common activity or overlaps sequential groups")
            group_end = group["ended_ns"]
            local_deadline = collection
            if bounded:
                wall = contract["group_wall_seconds"][group_index]
                local_deadline = min(collection, group["started_ns"] + wall * 10**9)
                require(type(group.get("wall_budget_seconds")) is int and group["wall_budget_seconds"] == wall
                        and type(group.get("deadline_ns")) is int and group["deadline_ns"] == local_deadline
                        and group["ended_ns"] <= local_deadline,
                        "bounded group exceeded/changed its independent wall reservation")
            capacity = {"workers": workers, "started_ns": group["started_ns"], "ended_ns": group["ended_ns"],
                        "step_attempts": 0, "step_returns": 0, "step_errors": 0,
                        "returned_steps_scope": "raw return events; duration/actor verification counted separately"}
            capacity.update({key: 0 for key in VERIFIED_COUNTS})
            for env_id in range(workers):
                expected_cells = (contract["worker_cells"][group_index][env_id]
                                  if contract["kind"] in ("full_behavior", "karto_behavior", *SEED_PROBE_RULES) else contract["cells"])
                local_cells = {tuple(cell) for cell in expected_cells}
                entries = sorted((item for item in group["episodes"] if item["env_id"] == env_id),
                                 key=lambda item: item["episode_index"])
                if not (len(entries) == len(local_cells)
                        and [item["episode_index"] for item in entries] == list(range(1, len(local_cells) + 1))
                        and {(item["scene"], item["seed"]) for item in entries} == local_cells):
                    result["errors"].append(f"group{workers}/worker{env_id}: six fixed scene/seed cells were omitted/replaced/retried")
                if bounded and [[item["scene"], item["seed"]] for item in entries] != expected_cells:
                    result["errors"].append(f"group{workers}/worker{env_id}: bounded fixed cell order differs")
                rng = random.Random(41 + 1000003 * env_id)
                uniform_stream_complete = True
                for item in entries:
                    episode = Path(item["directory"]).resolve()
                    if not episode.is_relative_to(directory) or episode in audited:
                        result["errors"].append("episode path escaped run or its trace was duplicated")
                        continue
                    audited.add(episode)
                    report = audit_episode(episode, freeze, builder=builder,
                                           rng=rng if uniform_stream_complete else None)
                    result["episodes"].append(report)
                    for key in ("step_attempts", "step_returns", "step_errors", *VERIFIED_COUNTS):
                        result[key] += report[key]
                        capacity[key] += report[key]
                    uniform_stream_complete = (uniform_stream_complete and report["raw_event_counts_complete"]
                                               and report["verified_uniform_action_count"] == report["step_attempts"])
                    result["errors"].extend(str(episode) + ": " + error for error in report["errors"])
                    try:
                        require(report.get("seed_rule", "legacy") == seed_rule,
                                "episode actor and capacity seed rules differ")
                        require(item["action_seed"] == 41 + 1000003 * env_id,
                                "independent random-stream seed differs")
                        require(report["env_id"] == env_id and report["episode_index"] == item["episode_index"]
                                and report["epoch"] not in epochs, "reset reused epoch or mixed environment identity")
                        if bounded:
                            metadata_path = episode / "episode.json"
                            metadata_raw = metadata_path.read_bytes()
                            stable[metadata_path] = metadata_raw
                            metadata = parse(metadata_raw)
                            require(metadata.get("seed_rule", "legacy") == seed_rule,
                                    "episode metadata and capacity seed rules differ")
                            if native_artifacts is not None:
                                model_path = episode / "proxy_model.json"
                                model_raw = model_path.read_bytes()
                                stable[model_path] = model_raw
                                model = parse(model_raw)
                                require(metadata.get("mapper")=="karto"
                                    and metadata.get("mapper_library")==summary["mapper_library"]
                                    and model.get("local_map")=="karto_native_addscan_fixed_grid_v1"
                                    and model.get("mapper")=="karto" and model.get("scan_budget")==6300
                                    and model.get("loaded_native_artifacts")==native_artifacts,
                                    "episode mapper/model/actual loaded native ELFs differ")
                            require(all(type(metadata[key]) is type(expected) and metadata[key] == expected for key, expected in (
                                ("scene", item["scene"]), ("seed", item["seed"]), ("env_id", env_id),
                                ("episode_index", item["episode_index"]), ("epoch", report["epoch"]), ("freeze", freeze)))
                                and metadata["profile_enabled"] is (contract["kind"] in ("profile", "karto_profile")),
                                "bounded episode metadata differs from its actual fixed cell/identity")
                            steps = contract["steps_per_episode"]
                            actual_steps = report["step_attempts"]
                            require(actual_steps == report["step_returns"] and 1 <= actual_steps <= steps
                                    and report["step_errors"] == 0 and report["causal_validation_complete"]
                                    and report["verified_action_count"] == report["verified_uniform_action_count"] == actual_steps
                                    and report["verified_step_return_count"] == actual_steps
                                    and report["verified_actor_record_count"] == actual_steps + 1,
                                    "bounded episode lacks complete verified coverage within its declared step ceiling")
                            terminal = report["last_verified_return_terminal"]
                            if contract["kind"] in ("full_behavior", "karto_behavior"):
                                require(terminal and terminal["terminated"] and not terminal["truncated"]
                                        and terminal["reason"] in ("coverage_reached", "timeout")
                                        and (terminal["reason"] != "timeout" or actual_steps == steps),
                                        "full behavior requires genuine task termination; external cuts are incomplete")
                            else:
                                require(terminal and ((terminal["terminated"] and terminal["reason"] in ("coverage_reached", "timeout"))
                                        or (terminal["truncated"]
                                        and actual_steps == steps and terminal["reason"] == "external_sampler_limit")),
                                        "bounded episode retained unsafe terminal or omitted its real declared external cut")
                    except ERRORS as error:
                        result["errors"].append(str(episode) + ": " + str(error))
                    report["wall_timestamp_coverage"] = _trace_wall_coverage(
                        report, group["started_ns"], local_deadline, group["ended_ns"])
                    for name, check in report["wall_timestamp_coverage"].items():
                        if not check["coverage_complete"]:
                            result["errors"].append(f"{episode}: {name} wall timestamp coverage incomplete: "
                                f"{check['verified_timestamp_count']}/{check['expected_raw_count']} verified")
                        if check["observed_out_of_bounds_count"]:
                            result["errors"].append(f"{episode}: {name} timestamp outside its declared wall bounds: "
                                                    f"{check['observed_out_of_bounds_count']} observed")
                    epochs.add(report["epoch"])
            wall = (group["ended_ns"] - group["started_ns"]) / 1e9
            capacity.update(wall_seconds_including_reset_and_close=wall,
                            returned_steps_per_wall_second=capacity["step_returns"] / wall if wall > 0 else None,
                            complete_six_cells_per_worker=len(cells) == 6 and all(
                                sum(item["env_id"] == env_id for item in group["episodes"]) == 6 for env_id in range(workers)),
                            complete_declared_cells_per_worker=all(
                                sum(item["env_id"] == env_id for item in group["episodes"]) ==
                                (len(contract["worker_cells"][group_index][env_id]) if contract["kind"] in ("full_behavior", "karto_behavior", *SEED_PROBE_RULES)
                                 else len(cells)) for env_id in range(workers)))
            result["group_capacity"].append(capacity)
        for episode in sorted(discovered - audited):
            report = audit_episode(episode, freeze, builder=builder)
            result["episodes"].append(report)
            result["errors"].append(str(episode) + ": trace is outside the declared worker/episode inventory")
            result["errors"].extend(str(episode) + ": " + error for error in report["errors"])
            for key in ("step_attempts", "step_returns", "step_errors", *VERIFIED_COUNTS):
                result[key] += report[key]
        require(result["step_attempts"] <= contract["max_attempts"]
                and result["step_attempts"] == result["step_returns"] + result["step_errors"],
                "global attempt budget excluded errors or was exceeded")
        if bounded:
            tickets = [ticket for report in result["episodes"] for ticket in report["raw_global_attempt_tickets"]]
            require(len(tickets) == result["step_attempts"] and all(type(ticket) is int for ticket in tickets)
                    and sorted(tickets) == list(range(1, result["step_attempts"] + 1))
                    and all(report["raw_global_attempt_tickets"] == sorted(report["raw_global_attempt_tickets"])
                            for report in result["episodes"]), "bounded global attempt tickets omitted/repeated/reordered a call")
        require(all(type(summary[key]) is int and summary[key] == result[key]
                    for key in ("step_attempts", "step_returns", "step_errors")),
                "summary attempt/return/error counters differ from original trace")
        require(time.monotonic_ns() <= deadline, "required independent audit exceeded the activity budget")
        result.update(declared_learning_calls={key: summary[key] for key in ("policy_calls", "gpu_calls", "optimizer_steps")},
                      activity_started_ns=start, activity_deadline_ns=deadline)
    except ERRORS as error:
        result["errors"].append(str(error))
    finally:
        if builder is not None:
            try:
                result["pure_builder_actual_wait"] = builder.close()
            except ERRORS as error:
                result["errors"].append("pure builder close: " + str(error))
    try:
        require(stable and all(path.read_bytes() == raw for path, raw in stable.items()),
                "run source/summary/conformity bytes changed during independent audit")
        result["bound_bytes_unchanged"] = True
    except ERRORS as error:
        result["bound_bytes_unchanged"] = False
        result["errors"].append(str(error))
    result["passed"] = bool(result["episodes"]) and not result["errors"]
    result["uniform_actions_independently_replayed"] = result["verified_uniform_action_count"]
    result["verified_exact_seed_actor_records"] = sum(
        item.get("verified_exact_seed_actor_records", 0) for item in result["episodes"])
    result["verified_exact_seed_robot_checks"] = sum(
        item.get("verified_exact_seed_robot_checks", 0) for item in result["episodes"])
    result["complete_short_capacity_matrix"] = result["passed"] and result.get("activity_kind") == "short_capacity"
    result["complete_full_behavior_diagnostic"] = result["passed"] and result.get("activity_kind") == "full_behavior"
    result["complete_seed_probe"] = result["passed"] and result.get("activity_kind") == "seed_probe"
    if result.get("activity_kind") == "seed_probe_v2":
        result["complete_seed_probe_v2"] = result["passed"]
    return result


def main(argv=None):
    if argv is None and sys.argv[1:] == ["--pure-builder"]:
        pure_builder_server()
        return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--conformity-only", type=Path)
    args = parser.parse_args(argv)
    require(not args.output.exists(), "preserve the original audit output")
    result = (audit_conformity(args.directory, args.conformity_only, args.freeze) if args.conformity_only
              else audit_run(args.directory, args.freeze) if (args.directory / "capacity_summary.json").is_file()
              else audit_episode(args.directory, args.freeze))
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
