"""v16 workload adapter: v5/32 reset aggregate, unchanged fixed physical criteria."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROBOTS = ("tb1", "tb2", "tb3")
SCHEDULE = [["open", 101], ["open", 101], ["rooms", 101], ["corridors", 101]]
CONSUMER_SHA256 = "2516e394f60eac5dd24fd66b51c4c48fc37245090eb1626ebe1c7a3a23f8bafb"
CONSUMER_PATH = (Path(__file__).resolve().parents[2] / "20261017_mr3_p2a0_v3"
                 / "independent" / "mr3_independent_physics_review.py")
PROBE_VERSION = "mr3-p2a0-outward-cancel-v5"
FAMILIES = (("A_final_linear_zero", "stop_responses", "eligible_stop_events", "credited_sampled_stop_events"),
            ("B_native_cancel_end_to_end", "cancel_stop_responses", "eligible_cancel_stop_events", "credited_cancel_stop_events"))


def require(value, message):
    if not value:
        raise ValueError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def load(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(run_directory, report_path, freeze):
    run_directory, report_path = Path(run_directory), Path(report_path)
    require(re.fullmatch(r"[0-9a-f]{40}", freeze), "exact freeze required")
    require(sha(CONSUMER_PATH) == CONSUMER_SHA256, "immutable physical consumer SHA mismatch")
    metadata = load(run_directory / "benchmark_metadata.json")
    summary = load(run_directory / "benchmark_summary.json")
    for source in (metadata, summary):
        require(source["freeze"] == freeze and source["workers"] == 2
                and source["schedule"] == SCHEDULE and source["steps_per_episode"] == 32
                and source.get("preparation_probe_version") == PROBE_VERSION
                and source.get("preparation_motion_probe") is True
                and all(source.get(key) is False for key in
                        ("terminal_probe", "deadline_probe", "fault_probe")),
                "aggregate requires only the predeclared same-freeze two-worker reset matrix")
    require(summary["passed"] is True, "native reset benchmark did not pass")
    report = load(report_path)
    require(report["schema"] == "mr3-independent-raw-physics-closure-review-v1"
            and report["script_sha256"] == CONSUMER_SHA256,
            "per-episode consumer source/schema differs from predeclaration")
    expected = {(f"worker{worker}", f"episode{index + 1:03d}_{scene}_{seed}")
                for worker in (0, 1) for index, (scene, seed) in enumerate(SCHEDULE)}
    actual = {tuple(path.parts[-2:]) for path in run_directory.glob("worker*/episode*")
              if path.is_dir()}
    require(actual == expected and len(report["episodes"]) == 8,
            "reset evidence must contain exactly the declared eight episodes")
    observed, errors, episodes = set(), [], []
    coverage = {name: {"A": 0, "B": 0, "credited_events": [],
                       "maximum_credited_initial_planar_speed": None} for name in ROBOTS}
    proof = {"benchmark_metadata.json": sha(run_directory / "benchmark_metadata.json"),
             "benchmark_summary.json": sha(run_directory / "benchmark_summary.json"),
             "per_episode_report": {"path": str(report_path), "sha256": sha(report_path)}}
    for episode in report["episodes"]:
        identity = tuple(Path(episode["directory"]).parts[-2:])
        require(identity in expected and identity not in observed, "duplicate/non-reset episode report")
        observed.add(identity)
        directory = run_directory.joinpath(*identity)
        episode_metadata = load(directory / "metadata.json")
        require(episode_metadata["freeze"] == freeze and episode_metadata["epoch"] == episode["epoch"],
                "episode report does not bind this frozen reset instance")
        proof["/".join(identity) + "/metadata.json"] = sha(directory / "metadata.json")
        # New workload eligibility only; the physical response/closure pool below is unchanged.
        variants = [path for path in (directory / "transitions.jsonl",
                    directory / "transitions.jsonl.gz") if path.is_file()]
        require(len(variants) == 1, "missing/ambiguous v5 reset transitions")
        transition_path = variants[0]
        transition_raw = transition_path.read_bytes()
        transition_data = (gzip.decompress(transition_raw) if transition_path.suffix == ".gz"
                           else transition_raw)
        require(transition_data.endswith(b"\n"), "incomplete v5 reset transitions")
        transitions = [json.loads(line) for line in transition_data.splitlines()]
        require(len(transitions) == 33 and transitions[0]["kind"] == "reset"
                and all(item["kind"] == "step" for item in transitions[1:])
                and all(item["terminated"] is False and item["truncated"] is False
                        for item in transitions[1:-1])
                and transitions[-1]["terminated"] is False
                and transitions[-1]["truncated"] is True
                and transitions[-1]["info"]["reason"] == "external_sampler_limit",
                "v5 reset requires one actual reset and32 nonterminal steps ending external truncation")
        proof["/".join(identity) + "/transitions"] = {
            "path": str(transition_path), "bytes": len(transition_raw),
            "sha256": hashlib.sha256(transition_raw).hexdigest()}
        local = []
        closure = episode.get("closure", {})
        if (closure.get("passed") is not True or closure.get("errors")
                or not closure.get("checks") or not all(value is True for value in closure["checks"].values())
                or closure.get("still_present_saved_identities")
                or not (type(closure.get("started_processes")) is int
                        and closure["started_processes"] > 0
                        and closure["started_processes"] == closure.get("exited_processes"))):
            local.append("strict native closure failed")
        robots = episode.get("robots", {})
        require(set(robots) == set(ROBOTS), "missing raw physics robot")
        missing = []
        for name, robot in robots.items():
            prefix = name + ": "
            if robot.get("errors"):
                local.append(prefix + "raw odom identity/order/frame error")
            if not (type(robot.get("task_odom_samples")) is int and robot["task_odom_samples"] >= 3
                    and type(robot.get("raw_unique_odom_samples")) is int
                    and robot["raw_unique_odom_samples"] >= robot["task_odom_samples"]):
                local.append(prefix + "missing complete raw odom data")
            for field, limit in (("maximum_planar_speed_task", .30),
                                 ("maximum_angular_norm_task", 1.2),
                                 ("maximum_abs_angular_z_task", 1.2),
                                 ("maximum_raw_odom_chord_speed_task", .30)):
                if not finite(robot.get(field)) or robot[field] > limit:
                    local.append(prefix + field + " missing or exceeded")
            for field in ("maximum_planar_speed_all", "maximum_angular_norm_all",
                          "maximum_abs_angular_z_all"):
                if not finite(robot.get(field)):
                    local.append(prefix + field + " missing/nonfinite")
            gap = robot.get("maximum_task_source_gap_ns")
            if type(gap) is not int or not 0 < gap <= 100000000:
                local.append(prefix + "raw source sampling gap missing/exceeded .10s")
            violations = robot.get("bound_violation_counts", {})
            require(set(violations) == {"planar_speed_over_.30", "angular_norm_over_1.2",
                                        "chord_speed_over_.30"}, "missing raw bound counters")
            if any(type(value) is not int or value != 0 for value in violations.values()):
                local.append(prefix + "raw velocity/chord bound violation")
            credited_here = 0
            for category, field, eligible_count, credited_count in FAMILIES:
                events = robot[field]
                require(isinstance(events, list), "stop response list required")
                eligible = credited = 0
                for event in events:
                    require(event["event_category"] == category and type(event["eligible"]) is bool,
                            "stop family/eligibility differs from frozen consumer")
                    eligible += event["eligible"]
                    if event["eligible"] and (event.get("observed_nonrest_beyond_horizon") is True
                            or event["status"] == "observed_bound_violation"
                            or (finite(event.get("observed_odom_polyline_m"))
                                and event["observed_odom_polyline_m"] > .144)):
                        local.append(prefix + category + " eligible response violated stop bound")
                    if event["status"] != "sampled_response_within_declared_bounds":
                        continue
                    require(event["eligible"] and finite(event["initial_observed_planar_speed"])
                            and event["initial_observed_planar_speed"] >= .05
                            and type(event["prior_nonzero_command_span_ns"]) is int
                            and event["prior_nonzero_command_span_ns"] >= 100000000
                            and finite(event["observed_latency_sec"]) and event["observed_latency_sec"] <= .78
                            and finite(event["observed_odom_polyline_m"]) and event["observed_odom_polyline_m"] <= .144
                            and type(event["maximum_observation_gap_ns"]) is int
                            and 0 <= event["maximum_observation_gap_ns"] <= 100000000,
                            "credited stop lacks frozen meaningful/sampled bounds")
                    if category.startswith("B"):
                        require(bool(event.get("completion_evidence")), "B lacks actual cancel completion")
                    credited += 1
                    family = category[0]
                    coverage[name][family] += 1
                    coverage[name]["credited_events"].append({"episode": "/".join(identity),
                        "family": family, "event_clock_ns": event["event_clock_ns"],
                        "initial_observed_planar_speed": event["initial_observed_planar_speed"]})
                    maximum = coverage[name]["maximum_credited_initial_planar_speed"]
                    coverage[name]["maximum_credited_initial_planar_speed"] = max(
                        maximum or 0., event["initial_observed_planar_speed"])
                require(type(robot[eligible_count]) is int and robot[eligible_count] == eligible
                        and type(robot[credited_count]) is int and robot[credited_count] == credited,
                        "stop family count differs from original response records")
                credited_here += credited
            if not credited_here:
                missing.append(name)
        errors.extend("/".join(identity) + ": " + error for error in local)
        episodes.append({"episode": "/".join(identity), "raw_and_closure_passed": not local,
                         "errors": local, "missing_meaningful_stop_robots": missing,
                         "original_per_episode_passed": episode["passed"],
                         "original_per_episode_physical_evidence_complete": episode["physical_evidence_complete"],
                         "original_robot_physical_evidence_complete": {
                             name: robot["physical_evidence_complete"] for name, robot in robots.items()}})
    require(observed == expected, "missing reset episode report")
    for name, row in coverage.items():
        if not row["A"] and not row["B"]:
            errors.append(name + ": no meaningful A or B stop across the complete reset matrix")
    return {"schema": "mr3-independent-reset-physics-matrix-v2", "freeze": freeze,
            "passed": not errors, "errors": errors, "episodes": episodes,
            "probe_version": PROBE_VERSION, "steps_per_episode": 32,
            "robot_stop_coverage": coverage, "source_report_passed": report["passed"],
            "artifact_proof": proof,
            "scope": "predeclared v5 probe reset-only eight-episode/32-step aggregate: all raw speed/chord/angular "
                     "and strict closures, no eligible observed stop violation, one meaningful A/B "
                     "sampled stop per robot across this matrix; original per-episode missing is retained; "
                     "terminal/deadline excluded, activity gate separate, no continuous dynamics proof"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--per-episode-report", required=True, type=Path)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output exists")
    try:
        result = audit(args.directory, args.per_episode_report, args.freeze)
    except (OSError, ValueError, TypeError, KeyError, IndexError) as error:
        result = {"schema": "mr3-independent-reset-physics-matrix-v2", "passed": False,
                  "errors": [repr(error)]}
    result["script_sha256"] = sha(__file__)
    with args.output.open("x") as output:
        output.write(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"passed": result["passed"], "errors": result["errors"], "output": str(args.output)}))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
