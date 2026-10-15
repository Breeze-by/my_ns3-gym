#!/usr/bin/env python3
"""Read saved P1C benchmarks; write analysis only to a new, external output path.

Pure stdlib. Never starts ROS, a simulator, a learner, or a GPU query. Resource
counters belong to the entire host/driver. This is not the semantic auditor.
"""

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def distribution(values):
    ordered = sorted(float(value) for value in values if finite(value))
    if not ordered:
        return {"count": 0, "min": None, "mean": None, "p50": None,
                "p90": None, "p95": None, "max": None, "sum": None}

    def quantile(q):
        where = (len(ordered) - 1) * q
        low = int(where)
        high = min(low + 1, len(ordered) - 1)
        return ordered[low] + (ordered[high] - ordered[low]) * (where - low)

    return {"count": len(ordered), "min": ordered[0], "mean": statistics.mean(ordered),
            "p50": quantile(.5), "p90": quantile(.9), "p95": quantile(.95),
            "max": ordered[-1], "sum": sum(ordered)}


def read_json(path):
    data = path.read_bytes() if path.exists() else gzip.decompress(
        path.with_suffix(path.suffix + ".gz").read_bytes())
    return json.loads(data)


def read_rows(path):
    if path.exists():
        source = path.open("rb")
    else:
        source = gzip.open(path.with_suffix(path.suffix + ".gz"), "rb")
    with source:
        return [json.loads(line) for line in source]


def process_scan_summary(receipts):
    """Aggregate recorded v3 scan maxima; legacy absence remains unmeasured."""
    measured = []
    for receipt in receipts:
        stats = receipt.get("process_scan_statistics")
        if stats is None:
            continue
        if (not isinstance(stats, dict) or type(stats.get("count")) is not int
                or stats["count"] < 0
                or any(not finite(stats.get(key)) or stats[key] < 0
                       for key in ("max_scan_wall_sec", "max_observed_interval_sec"))):
            raise ValueError("invalid recorded process_scan_statistics")
        measured.append(stats)
    return {
        "receipt_count": len(receipts), "measured_receipt_count": len(measured),
        "unmeasured_receipt_count": len(receipts) - len(measured),
        "all_receipts_measured": bool(receipts) and len(measured) == len(receipts),
        "count": sum(row["count"] for row in measured) if measured else None,
        "max_scan_wall_sec": max(row["max_scan_wall_sec"] for row in measured)
        if measured else None,
        "max_observed_interval_sec": max(row["max_observed_interval_sec"] for row in measured)
        if measured else None,
        "scope": ("all ownership scans, monitor and RPC; actual monotonic start-to-start "
                  "interval includes scanning/wait/scheduling; no 50ms coverage promise"),
        "missing_scope": "legacy/v2 missing fields are unmeasured, never zero-filled",
    }


def resource_summary(samples):
    total, busy, intervals, invalid = 0, 0, [], 0
    for left, right in zip(samples, samples[1:]):
        delta = right["cpu_total_ticks"] - left["cpu_total_ticks"]
        idle = right["cpu_idle_ticks"] - left["cpu_idle_ticks"]
        if delta <= 0 or not 0 <= idle <= delta:
            invalid += 1
            continue
        total += delta
        busy += delta - idle
        intervals.append(100. * (delta - idle) / delta)
    cards = {}
    for sample in samples:
        for index, utilization, used_mib, total_mib in sample.get("gpu", []):
            row = cards.setdefault(str(index), {"sample_count": 0, "max_utilization_percent": 0,
                                   "peak_used_mib": 0, "reported_total_mib": set()})
            row["sample_count"] += 1
            row["max_utilization_percent"] = max(row["max_utilization_percent"], utilization)
            row["peak_used_mib"] = max(row["peak_used_mib"], used_mib)
            row["reported_total_mib"].add(total_mib)
    for row in cards.values():
        row["reported_total_mib"] = sorted(row["reported_total_mib"])
    available = [row["mem_available_kib"] for row in samples]
    used = [row["mem_total_kib"] - row["mem_available_kib"] for row in samples]
    return {
        "scope": "whole-host counters and whole-device driver reports; no process attribution",
        "sample_count": len(samples), "invalid_cpu_delta_intervals": invalid,
        "observed_resource_wall_sec": (samples[-1]["monotonic"] - samples[0]["monotonic"]
                                       if len(samples) > 1 else 0.),
        "host_cpu_total_tick_delta": total, "host_cpu_busy_tick_delta": busy,
        "host_cpu_tick_weighted_utilization_percent": 100. * busy / total if total else None,
        "host_cpu_interval_utilization_percent": distribution(intervals),
        "cpu_definition": "1-idle_delta/total_delta; idle includes iowait; host capacity=100%",
        "host_mem_available_min_bytes": min(available) * 1024 if available else None,
        "host_mem_used_estimate_peak_bytes": max(used) * 1024 if used else None,
        "memory_definition": "MemTotal-MemAvailable, not RSS and not a sum of process memory",
        "owned_rss_bytes": None, "owned_rss_measured": False,
        "gpu_driver_per_card": cards,
        "gpu_query_failure_samples": sum(
            bool(row.get("gpu_query_error")) or row.get("gpu_query_returncode", 0) != 0
            for row in samples),
    }


def storage_inventory(directory):
    """Logical raw totals avoid counting a raw file and its .gz copy twice."""
    files = [path for path in directory.rglob("*") if path.is_file() and not path.is_symlink()
             and not path.name.startswith("audit") and not path.name.endswith("_audit.json")]
    groups = {}
    for path in files:
        relative = str(path.relative_to(directory))
        key = relative[:-3] if relative.endswith(".gz") else relative
        groups.setdefault(key, {})["gzip" if relative.endswith(".gz") else "raw"] = path
    result = []
    for relative, group in sorted(groups.items()):
        raw = group.get("raw")
        zipped = group.get("gzip")
        source = raw or zipped
        gzip_matches_raw = None
        if raw is not None:
            logical_size = raw.stat().st_size
            if zipped is not None:
                raw_digest, zipped_digest = hashlib.sha256(), hashlib.sha256()
                with raw.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024**2), b""):
                        raw_digest.update(chunk)
                with gzip.open(zipped, "rb") as handle:
                    for chunk in iter(lambda: handle.read(1024**2), b""):
                        zipped_digest.update(chunk)
                gzip_matches_raw = raw_digest.digest() == zipped_digest.digest()
        else:
            with gzip.open(zipped, "rb") as handle:
                logical_size = sum(len(chunk) for chunk in iter(lambda: handle.read(1024**2), b""))
        result.append({"path": relative, "logical_raw_bytes": logical_size,
                       "raw_copy_bytes": raw.stat().st_size if raw else 0,
                       "gzip_copy_bytes": zipped.stat().st_size if zipped else 0,
                       "gzip_matches_raw": gzip_matches_raw,
                       "compact_archive_bytes": (zipped if zipped and gzip_matches_raw is not False
                                                 else raw).stat().st_size,
                       "physical_apparent_bytes": sum(path.stat().st_size
                                                      for path in group.values()),
                       "physical_allocated_bytes": sum(path.stat().st_blocks * 512
                                                       for path in group.values()),
                       "read_path": str(source), "read_is_gzip": raw is None})
    return result


def storage_totals(rows):
    keys = ("logical_raw_bytes", "raw_copy_bytes", "gzip_copy_bytes", "compact_archive_bytes",
            "physical_apparent_bytes", "physical_allocated_bytes")
    return {key: sum(row[key] for row in rows) for key in keys}


def phase_storage(rows, release, end):
    """Observed byte partition; unparseable runtime logs stay unassigned."""
    totals = {kind: {phase: 0. for phase in ("fixed", "per_step", "unattributed")}
              for kind in ("raw", "compact_ratio_held")}
    fixed_names = {"metadata.json", "supervisor_metadata.json", "supervisor_shutdown.json",
                   "native_stop.json", "summary.json", "adapter.sha256"}
    for row in rows:
        name = Path(row["path"]).name
        counts = {"fixed": 0, "per_step": 0, "unattributed": 0}
        if name in fixed_names:
            counts["fixed"] = row["logical_raw_bytes"]
        elif name in ("adapter.jsonl", "physics.jsonl", "transitions.jsonl"):
            opener = gzip.open if row["read_is_gzip"] else open
            with opener(row["read_path"], "rb") as handle:
                for line in handle:
                    value = json.loads(line)
                    if name == "transitions.jsonl":
                        phase = "fixed" if value.get("kind") == "reset" else "per_step"
                    else:
                        stamp = (value.get("end_time_ns", 0) / 1e9
                                 if name == "physics.jsonl" else value.get("stamp"))
                        phase = ("unattributed" if not finite(stamp) else
                                 "fixed" if stamp <= release or stamp > end else "per_step")
                    counts[phase] += len(line)
        else:
            counts["unattributed"] = row["logical_raw_bytes"]
        ratio = (row["compact_archive_bytes"] / row["logical_raw_bytes"]
                 if row["logical_raw_bytes"] else 1.)
        for phase, amount in counts.items():
            totals["raw"][phase] += amount
            totals["compact_ratio_held"][phase] += amount * ratio
    return {"bytes": totals,
            "scope": ("warmup/reset and post-last-snapshot bytes fixed; "
                      "policy-window JSONL per-step; other logs unassigned"),
            "compression_scope": ("compact phases hold each file's observed whole-file "
                                  "gzip/raw ratio; not separately compressed phases")}


def projections(cells):
    eligible = [cell for cell in cells if cell["valid_for_extrapolation"]]
    result = {"source_episode_count": len(eligible),
              "source_scope": ("complete normal 16-step episodes only; "
                               "no fault prefixes/deadline KEEP episodes"),
              "limits": ("Observed-range/constant-cost model envelopes, not confidence intervals "
                         "or guaranteed bounds; map/log growth and failures may increase costs."),
              "unknowns": ["final Supervisor reap tail", "optimizer/checkpoint/replay storage",
                           "future map growth", "failure/retry rate", "external ROS log dirs"]}
    for horizon in (500000, 1500000):
        outputs = {}
        for length in (16, 300):
            episodes = math.ceil(horizon / length)
            wall = []
            storage = {kind: [] for kind in ("raw", "compact_ratio_held")}
            for cell in eligible:
                if cell["time_cost_model"]:
                    model = cell["time_cost_model"]
                    wall.append(episodes * model["recorded_fixed_wall_sec"]
                                + horizon * model["recorded_variable_wall_sec_per_transition"])
                for kind, parts in cell["phase_storage"]["bytes"].items():
                    low = episodes * (parts["fixed"] + parts["unattributed"])
                    low += horizon * parts["per_step"] / 16
                    high = episodes * parts["fixed"]
                    high += horizon * (parts["per_step"] + parts["unattributed"]) / 16
                    storage[kind].append((min(low, high), max(low, high)))
            outputs[str(length)] = {
                "episode_transition_budget": length, "episode_count": episodes,
                "serial_recorded_wall_sec_range": [min(wall), max(wall)] if wall else None,
                "storage_bytes_envelope": {
                    kind: [min(low for low, _ in rows), max(high for _, high in rows)]
                    if rows else None for kind, rows in storage.items()},
                "unattributed_cost_rule": ("unclassified bytes per episode or per observed step; "
                                           "identified startup stays fixed"),
            }
        result[str(horizon)] = outputs
    return result


def analyze(directory):
    directory = directory.resolve()
    metadata = read_json(directory / "benchmark_metadata.json")
    summary = read_json(directory / "benchmark_summary.json")
    resources = read_json(directory / "resources.json")
    inventory = storage_inventory(directory)
    cells, comparison_workers, shutdowns = [], [], []
    for worker in summary["workers_results"]:
        prefix = worker["episodes"][:2]
        if len(prefix) == 2 and all([cell["scene"], cell["seed"]] == ["open", 101]
                                    for cell in prefix):
            durations = [cell.get("wall_sec_including_startup_and_closure") for cell in prefix]
            if all(finite(value) and value > 0 for value in durations):
                comparison_workers.append({"worker_id": worker["worker_id"],
                                           "recorded_wall_sec": sum(durations),
                                           "transitions": sum(cell["transitions"]
                                                              for cell in prefix)})
        for index, cell in enumerate(worker["episodes"]):
            matches = sorted((directory / f"worker{worker['worker_id']}").glob(
                f"episode{index + 1:03d}_*"))
            if len(matches) != 1:
                raise ValueError("unique episode directory missing")
            episode = matches[0]
            shutdown = read_json(episode / "supervisor_shutdown.json")
            shutdowns.append(shutdown)
            rows = read_rows(episode / "transitions.jsonl")
            summary_exists = ((episode / "summary.json").exists()
                              or (episode / "summary.json.gz").exists())
            worker_summary = read_json(episode / "summary.json") if summary_exists else {}
            start = rows[0]["snapshot"]["source_stamp"]
            end = rows[-1]["snapshot"]["source_stamp"]
            normal_steps = [row["info"].get("step_wall_sec") for row in rows[1:]
                            if not row.get("terminated") and not row.get("truncated")]
            relative = str(episode.relative_to(directory)) + "/"
            files = [row for row in inventory if row["path"].startswith(relative)]
            n = cell["transitions"]
            wall = cell.get("wall_sec_including_startup_and_closure")
            api_wall = cell.get("transition_wall_sec")
            closure = worker_summary.get("cleanup_wall_sec")
            model = None
            if (n > 0 and all(finite(value) for value in (wall, api_wall, closure))
                    and wall >= api_wall >= closure >= 0):
                model = {"recorded_fixed_wall_sec": wall - api_wall + closure,
                         "recorded_variable_wall_sec_per_transition": (api_wall - closure) / n,
                         "scope": ("stationary API cost; closure removed before per-step scaling; "
                                   "final Supervisor tail unknown")}
            valid = bool(summary.get("passed") and n == 16 and cell.get("truncated")
                         and not cell.get("terminated")
                         and not cell.get("expected_infrastructure_fault")
                         and not metadata.get("fault_probe")
                         and not metadata.get("deadline_probe")
                         and not metadata.get("terminal_probe"))
            cells.append({"worker_id": worker["worker_id"], "episode_index": index,
                          "epoch": cell["epoch"], "scene": cell["scene"],
                          "seed": cell["seed"],
                          "transitions": n, "startup_wall_sec": cell.get("startup_wall_sec"),
                          "cell_recorded_wall_sec": wall,
                          "api_transition_total_wall_sec": api_wall,
                          "api_average_wall_sec_per_transition": api_wall / n if n else None,
                          "worker_normal_step_wall_sec": distribution(normal_steps),
                          "native_closure_wall_sec": closure,
                          "final_supervisor_cleanup_wall_sec": None,
                          "process_scan_statistics": shutdown.get("process_scan_statistics"),
                          "process_scan_measured": shutdown.get("process_scan_statistics")
                          is not None,
                          "valid_for_extrapolation": valid, "time_cost_model": model,
                          "storage": storage_totals(files),
                          "raw_bytes_per_transition": sum(row["logical_raw_bytes"]
                                                          for row in files) / n if n else None,
                          "phase_storage": phase_storage(files, start, end)})
    n = summary["valid_transitions"]
    comparison = {"eligible": False}
    if (summary.get("passed") is True
            and not metadata.get("fault_probe") and not metadata.get("deadline_probe")
            and not metadata.get("terminal_probe")
            and len(comparison_workers) == metadata["workers"]):
        denominator = max(worker["recorded_wall_sec"] for worker in comparison_workers)
        comparison = {"eligible": True,
                      "transitions": sum(worker["transitions"] for worker in comparison_workers),
                      "denominator_wall_sec": denominator,
                      "per_worker": comparison_workers,
                      "scope": ("first two open101; max_worker(sum recorded cell walls), "
                                "final reap tail absent")}
        comparison["effective_transition_per_wall_sec"] = comparison["transitions"] / denominator
    totals = storage_totals(inventory)
    return {
        "directory": str(directory), "freeze": metadata["freeze"], "workers": metadata["workers"],
        "schedule": metadata["schedule"], "summary_passed": summary.get("passed"),
        "fault_probe": metadata.get("fault_probe") is True,
        "deadline_probe": metadata.get("deadline_probe") is True,
        "terminal_probe": metadata.get("terminal_probe") is True,
        "wall_sec_including_all_attempts": summary["wall_sec_including_all_attempts"],
        "valid_transitions": n,
        "effective_transition_per_wall_sec": summary["effective_transition_per_wall_sec"],
        "computed_transition_per_wall_sec": n / summary["wall_sec_including_all_attempts"],
        "fair_comparison": comparison,
        "startup_wall_sec": distribution(cell["startup_wall_sec"] for cell in cells),
        "native_closure_wall_sec": distribution(cell["native_closure_wall_sec"] for cell in cells),
        "cell_api_average_wall_sec_per_transition": distribution(
            cell["api_average_wall_sec_per_transition"] for cell in cells),
        "timing_scope": ("worker step excludes native shutdown; API total includes last-step "
                         "closure; do not sum overlapping distributions"),
        "resources": resource_summary(resources), "storage": totals,
        "process_scan_statistics": process_scan_summary(shutdowns),
        "benchmark_raw_bytes_per_valid_transition": totals["logical_raw_bytes"] / n if n else None,
        "benchmark_compact_bytes_per_valid_transition": (totals["compact_archive_bytes"] / n
                                                         if n else None),
        "storage_scope": ("input dir only; raw+.gz paired by filename, logical bytes counted "
                          "once; compact uses existing .gz else raw; no new compression"),
        "cells": cells, "conditional_16_vs_300_step_projections": projections(cells),
        "input_hashes": {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
                         for name in ("benchmark_metadata.json", "benchmark_summary.json",
                                      "resources.json")
                         if (directory / name).exists()},
        "file_inventory": inventory,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    options = parser.parse_args()
    output = options.output.resolve()
    for directory in options.directories:
        if output.is_relative_to(directory.resolve()):
            parser.error("output must be outside all evidence directories")
    if output.exists():
        parser.error("output already exists; choose a new analysis filename")
    results = [analyze(directory) for directory in options.directories]
    freezes = {row["freeze"] for row in results}
    result = {"kind": "mr3-p1c-offline-resource-storage-draft", "semantic_audit": False,
              "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "host_attribution": "shared host/driver; owned RSS unavailable, never substituted",
              "freezes": sorted(freezes), "mixed_freeze_warning": len(freezes) > 1,
              "benchmarks": results,
              "same_freeze_aggregate_conditional_projections": (
                  projections([cell for row in results for cell in row["cells"]])
                  if len(freezes) == 1 else None)}
    with output.open("x") as handle:
        json.dump(result, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"output": str(output), "benchmark_count": len(results)}, sort_keys=True))


if __name__ == "__main__":
    main()
