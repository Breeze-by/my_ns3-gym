"""Offline inventory of all closed v7 selected evidence; never controls processes."""

import argparse
from datetime import datetime, timezone
from decimal import Decimal
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import re


FREEZE = "cdb1f5947302a0b3a071b78a9077e61b8e6b6a7a"
ARCHIVE_SHA = "d9011aa26a2a603246ab3f8847769ee43b6e592f887e26a1ea20b1dfae375beb"
STAGES = ("clock", "pilot", "terminal", "workers1", "workers2", "workers4", "fault", "deadline")


def require(value, reason):
    if not value:
        raise ValueError(reason)


def read(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def proc_identity(pid):
    try:
        fields = (Path("/proc") / str(pid) / "stat").read_text().rsplit(")", 1)[1].split()
        return {"pid": pid, "start_ticks": int(fields[19]), "state": fields[0]}
    except FileNotFoundError:
        return None


def ns(value):
    return int(round(Decimal(str(value)) * 1_000_000_000))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    require(args.freeze == FREEZE, "unexpected source freeze")
    require(not args.output.exists(), "output exists; preserve evidence")
    assets = Path(__file__).resolve().parent
    root = next(parent for parent in assets.parents if (parent / ".git").exists())
    selected = assets / "native_v7"
    tool = assets / "archive_mr3_v7_closed.py"
    require(digest(tool) == ARCHIVE_SHA, "archive helper changed")
    spec = importlib.util.spec_from_file_location("pinned_v7_archive_inventory", tool)
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    helper.freeze = FREEZE
    helper.binding_guard(FREEZE)

    verified, manifest_paths, original_paths, selected_paths = {}, [], set(), set()

    def checked(path, expected):
        path = path.resolve()
        if path not in verified:
            verified[path] = digest(path)
        require(verified[path] == expected, "SHA mismatch: " + str(path))

    for manifest in sorted(selected.rglob("manifest.json")):
        value = read(manifest)
        require(value["source_freeze"] == FREEZE and value["originals_modified"] is False,
                "manifest scope differs")
        require(len(value["files"]) == value["original_file_count"], "manifest count differs")
        for item in value["files"]:
            original, copy = root / item["original"], root / item["selected"]
            checked(original, item["original_sha256"])
            checked(copy, item["selected_sha256"])
            require(original.stat().st_size == item["original_bytes"]
                    and copy.stat().st_size == item["selected_bytes"], "size mismatch")
            data = copy.read_bytes()
            decoded = gzip.decompress(data) if item["encoding"].startswith("gzip") else data
            require(hashlib.sha256(decoded).hexdigest() == item["decoded_selected_sha256"]
                    == item["original_sha256"] and item["decoded_matches_original"] is True,
                    "decoded bytes differ")
            original_paths.add(original)
            selected_paths.add(copy)
        for key in ("independent_review", "primary_audit"):
            if key in value:
                checked(root / value[key]["path"], value[key]["sha256"])
        for pair in value.get("audits_copied_losslessly", []):
            for reference in (pair["original"], pair["selected"]):
                checked(root / reference["path"], reference["sha256"])
            require(pair["original"]["sha256"] == pair["selected"]["sha256"],
                    "copied audit differs")
        manifest_paths.append({"path": str(manifest.relative_to(root)), "sha256": digest(manifest)})

    stages, identities, bare, epochs = {}, {}, [], set()
    api = physical_ns = commands = accepted = rejected = normal = prefix = 0
    sdk_starts = sdk_clean = serial = finalized = raw_streams = 0
    for stage in STAGES:
        directory = selected / stage
        require((directory / "manifest.json").exists(), "stage not archived: " + stage)
        review = read(directory / "independent_review.json")
        if stage == "clock":
            require(review["passed"] is True and review["source_freeze"] == FREEZE,
                    "clock review failed")
            summary = read(directory / "summary.json")
            for key in ("server_pid", "helper_pid", "stop_cli_pid"):
                bare.append({"unit": "clock", "role": key, "pid": summary[key]})
            stages[stage] = {"component_only": True, "receipts": review["receipt_count"],
                             "clock_samples": review["clock_sample_count"]}
            continue
        require(review["passed_declared_audits"] is True and review["source_freeze"] == FREEZE,
                "stage review failed: " + stage)
        stage_api = 0
        for episode in review["episodes"]:
            epoch = episode["epoch"]
            require(epoch not in epochs, "reused epoch")
            epochs.add(epoch)
            original = Path(episode["directory"])
            leaf = directory / original.parent.name / original.name
            shutdown = read(leaf / "supervisor_shutdown.json")
            require(shutdown["epoch"] == epoch and not shutdown["remaining_owned_processes"]
                    and not shutdown["remaining_owned_zombies"], "saved owned survivors")
            local = {item["pid"]: item for item in shutdown["owned_processes_seen"]}
            for item in shutdown["owned_processes_seen"]:
                require(type(item["start_ticks"]) is int and item["start_ticks"] > 0,
                        "missing real start ticks")
                key = (item["pid"], item["start_ticks"])
                identities.setdefault(key, {"pid": key[0], "start_ticks": key[1], "epochs": []})[
                    "epochs"].append(epoch)
            rows = [json.loads(line) for line in gzip.decompress(
                (leaf / "transitions.jsonl.gz").read_bytes()).splitlines()]
            require(rows[0]["kind"] == "reset", "missing actual reset")
            steps = rows[1:]
            count = episode["transitions"]["transition_count"]
            require(len(steps) == count, "API count mismatch")
            stage_api += count
            for row in steps:
                require(row["info"]["dt"] == row["info"]["physical_dt"], "physical dt differs")
                physical_ns += ns(row["info"]["physical_dt"])
            timing = episode["protocol"]["command_time"]
            require(timing["passed"] is True, "command time gate failed")
            commands += timing["commands_checked"]
            accepted += timing["accepted_commands"]
            rejected += timing["rejected_commands"]
            text = gzip.decompress((leaf / "launch.log.gz").read_bytes()).decode()
            starts = re.findall(r"^\[INFO\] \[([^\]]+)\]: process started with pid \[(\d+)\]$",
                                text, re.MULTILINE)
            cleans = re.findall(
                r"^\[INFO\] \[([^\]]+)\]: process has finished cleanly \[pid (\d+)\]$",
                text, re.MULTILINE)
            sdk_starts += len(starts)
            sdk_clean += len(cleans)
            if episode["complete_episode_credit"]:
                normal += 1
                actual = helper.review_episode(root / original, read(root / review[
                    "primary_audit"]["path"])["episodes"][review["episodes"].index(episode)])
                serial += actual["serial_sigint_count"]
                finalized += actual["nav2_actual_FINALIZED_responses"]
                raw_streams += episode["contacts"]["raw_stream_count"]
                require(len(starts) == len(cleans) == 38, "normal SDK clean count differs")
                for role, pid in (("server", actual["native_server_pid"]),
                                  ("stop_cli", actual["native_stop_cli_pid"])):
                    if pid not in local:
                        bare.append({"unit": epoch, "role": role, "pid": pid})
                require(read(leaf / "summary.json")["closed"]["pending_goal_count"] == 0,
                        "normal goal ownership not closed")
            else:
                prefix += 1
                require(stage == "fault" and count == 4 and shutdown["worker_returncode"] == -9
                        and shutdown["forced_shutdown"] is True
                        and not (leaf / "summary.json").exists(), "fault scope differs")
            if stage == "deadline":
                require(count == 300 and all(row["info"]["dt"] == 1 for row in steps),
                        "deadline steps differ")
                start = rows[0]["info"]["release_time_ns"]
                end = ns(steps[-1]["snapshot"]["source_stamp"])
                require(end - start == 300_000_000_000, "deadline endpoints differ")
                require(all(not row["terminated"] and not row["truncated"] for row in steps[:-1])
                        and steps[-1]["terminated"] and not steps[-1]["truncated"]
                        and steps[-1]["info"]["reward_diagnostics"]["reason"] == "timeout",
                        "deadline terminal differs")
                require(timing["commands_checked"] == timing["accepted_commands"] == 300
                        and timing["rejected_commands"] == 0 and all(
                            item["valid"] and item["action"] == 888
                            and item["ttl_ns"] == 2_000_000_000 for item in timing["bindings"]),
                        "deadline KEEP command differs")
                require(all(row["info"]["reward_diagnostics"]["rejected_actions_delta"] == 0
                            and row["info"]["reward_diagnostics"]["reward_terms"]["invalid"] == 0
                            for row in steps), "deadline invalid penalty")
                stages[stage] = {"start_time_ns": start, "end_time_ns": end,
                                 "terminated": True, "truncated": False, "reason": "timeout",
                                 "KEEP_accepted": 300, "invalid_penalty": 0,
                                 "native_goals": episode["protocol"]["goal_count"]}
        api += stage_api
        stages.setdefault(stage, {})["returned_API"] = stage_api
        stages[stage]["complete_episodes"] = review["complete_episode_count"]

    survivors = []
    for item in identities.values():
        current = proc_identity(item["pid"])
        item["current_proc"] = current
        if current and current["start_ticks"] == item["start_ticks"]:
            survivors.append(item)
    for item in bare:
        item["current_proc"] = proc_identity(item["pid"])
    require(not survivors and not any(item["current_proc"] for item in bare),
            "owned survivor or ambiguous present bare PID")
    require(api == 594 and physical_ns == 592_020_000_000 and normal == 23 and prefix == 1,
            "final probe inventory differs")
    result = {"schema": "mr3-p1c-v7-final-native-inventory-v1", "passed_inventory_checks": True,
              "source_freeze": FREEZE, "checked_at_utc": datetime.now(timezone.utc).isoformat(),
              "scope": "Closed saved engineering evidence and current /proc identity check; "
                       "not acceptance, policy training, SDK fix, 95% mapping or network credit. "
                       "No active offline matrix output consumed and no native process controlled.",
              "stages": stages, "returned_API": api, "sampled_physical_time_ns": physical_ns,
              "complete_episodes": normal, "incomplete_killed_prefixes": prefix,
              "submitted_commands": commands, "accepted_commands": accepted,
              "rejected_commands": rejected, "rejection_scope": "One retained navigation_changed_"
              "since_observation rejection; no command-time-invalid rejection in v7.",
              "actual_team_SDK_starts_including_prefix": sdk_starts,
              "actual_team_SDK_clean0_exits_including_prefix": sdk_clean,
              "normal_serial_SIGINT_clean_barriers": serial,
              "normal_actual_FINALIZED_responses": finalized,
              "normal_raw_contact_streams": raw_streams,
              "prefix_credit": {"normal_shutdown": False, "full_episode": False,
                                "complete_contact": False, "complete_reward": False},
              "manifests": manifest_paths, "manifest_count": len(manifest_paths),
              "unique_original_files_verified": len(original_paths),
              "unique_selected_original_artifacts_verified": len(selected_paths),
              "raw_original_bytes": sum(path.stat().st_size for path in original_paths),
              "selected_original_bytes": sum(path.stat().st_size for path in selected_paths),
              "owned_pid_start_ticks_count": len(identities),
              "owned_identities": sorted(identities.values(), key=lambda item: item["pid"]),
              "bare_unit_scoped_PIDs_without_saved_start_ticks": bare,
              "remaining_exact_owned_or_zombie": [], "ambiguous_present_bare_PIDs": [],
              "identity_scope": "Real saved start_ticks only. Bare PIDs require absence in /proc; "
                                "never exempted by a numeric PID from a different epoch.",
              "helper": {"path": str(Path(__file__).relative_to(root)),
                         "sha256": digest(Path(__file__))}}
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    summary_keys = ("passed_inventory_checks", "returned_API", "sampled_physical_time_ns",
                    "complete_episodes", "incomplete_killed_prefixes", "submitted_commands",
                    "accepted_commands", "rejected_commands", "manifest_count",
                    "unique_original_files_verified", "unique_selected_original_artifacts_verified",
                    "owned_pid_start_ticks_count")
    print(json.dumps({key: result[key] for key in summary_keys}
                     | {"output_sha256": digest(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
