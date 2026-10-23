"""Seal completed V52 metadata/archival CPU receipts. Never consume raw traces."""

from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import stat
import time


HERE = Path(__file__).resolve().parent
ASSET = HERE.parents[1]
W = ASSET.parents[2]
INDEX = HERE / "source_recovery_index_v1.json"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    path = Path(path)
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), "not a regular file: " + str(path))
    raw = path.read_bytes()
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns,
             before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size,
             after.st_mtime_ns, after.st_ctime_ns), "file changed: " + str(path))
    return raw, {"path": str(path.relative_to(W)), "bytes": len(raw),
                 "sha256": hashlib.sha256(raw).hexdigest()}


def decode(raw):
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate JSON member")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                          ValueError("nonfinite JSON: " + value)))


def bound(spec):
    raw, observed = read(W / spec["path"])
    require(observed["sha256"] == spec["sha256"] and
            observed["bytes"] == spec["bytes"], "bound bytes differ: " + spec["path"])
    return raw


def absence(saved):
    pid, start = saved["pid"], saved["start_ticks"]
    require(type(pid) is int and pid > 0 and type(start) is int and start > 0,
            "invalid saved process identity")
    result = {"saved_identity": saved, "observed_monotonic_ns": time.monotonic_ns()}
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        end = raw.rfind(")")
        require(end >= 0 and int(raw[:raw.index("(")].strip()) == pid,
                "malformed process stat")
        fields = raw[end + 2:].split()
        state, current_start = fields[0], int(fields[19])
        result.update(same_identity_present=current_start == start,
                      observed_state=state, observed_start_ticks=current_start,
                      reason="same_start_present_including_Z" if current_start == start
                             else "PID_reused_with_different_start")
    except FileNotFoundError:
        result.update(same_identity_present=False, observed_state=None,
                      reason="proc_stat_absent")
    except (OSError, ValueError, IndexError) as error:
        result.update(same_identity_present=None, reason="unreadable_or_malformed",
                      error=repr(error))
    require(result["same_identity_present"] is False,
            "saved CPU process is present or unreadable: " + str(result))
    return result


def main():
    index_raw, index_binding = read(INDEX)
    index = decode(index_raw)
    require(index["schema"] == "mr3-v52-closure-cpu-source-recovery-v1", "index schema")
    source_lookup = {}
    for spec in index["sources"]:
        bound(spec)
        key = (spec["original_path"], spec["sha256"], spec["bytes"])
        require(key not in source_lookup, "duplicate recovery source")
        source_lookup[key] = spec
    for spec in index["copied_artifacts"]:
        bound(spec)

    checks, observations, seen = [], [], set()
    for check in index["checks"]:
        raw, receipt_binding = read(W / check["receipt"])
        receipt = decode(raw)
        require(receipt["schema"] == "mr3-reach-outer-actual-wait-v1" and
                receipt["scope"] == "cpu", "unexpected actual-wait scope/schema")
        require(receipt["actual_waited"] is True and
                type(receipt["actual_returncode"]) is int and
                receipt["actual_returncode"] == check["expected_actual_returncode"],
                "actual waited returncode differs")
        require(receipt["passed"] is check["expected_original_passed"] and
                receipt["errors"] == [] and receipt["source_unchanged"] is True and
                receipt["source_before"] == receipt["source_after"],
                "original outcome/source stability differs")
        start, end = receipt["started_monotonic_ns"], receipt["ended_monotonic_ns"]
        require(type(start) is int and type(end) is int and 0 < start < end <= time.monotonic_ns(),
                "invalid actual interval")
        seconds = Decimal(end - start) / 10**9
        require(Decimal(receipt["actual_child_wait_seconds"]) == seconds,
                "actual seconds differ from integer interval")
        console_raw, console_binding = read((W / check["receipt"]).parent / "console.log")
        require(console_binding["sha256"] == receipt["console"]["sha256"],
                "original console SHA differs")
        for spec in receipt["source_before"]:
            require((spec["path"], spec["sha256"], spec["bytes"]) in source_lookup,
                    "source recovery is incomplete")
        for key in ("coordinator_identity", "child_identity"):
            saved = receipt[key]
            pair = (saved["pid"], saved["start_ticks"])
            if pair not in seen:
                observations.append(absence(saved))
                seen.add(pair)
        checks.append({"name": check["name"], "actual_wait": receipt_binding,
                       "console": console_binding, "original_passed": receipt["passed"],
                       "actual_returncode": receipt["actual_returncode"],
                       "actual_child_wait_seconds": str(seconds),
                       "bound_source_count": len(receipt["source_before"]),
                       "source_unchanged": True,
                       "artificial_tests": check["artificial_tests"]})

    inventory_raw, inventory_binding = read(ASSET / "closed_inventory_v1.json")
    require(inventory_binding["sha256"] ==
            "63efb61cc7b2abaf723b3824399d203a1a0b288465a367110eabcb5ec565ccf7",
            "immutable inventory differs")
    inventory = decode(inventory_raw)
    require(inventory["byte_archive_complete"] is True and
            (inventory["files"], inventory["original_bytes"], inventory["canonical_bytes"],
             inventory["link_count"]) == (7772, 15628170281, 1293834289, 0),
            "closed inventory metadata differs")
    overlay_raw, overlay_binding = read(ASSET / "packed_overlay_v1/manifest.json")
    require(overlay_binding["sha256"] ==
            "0b5d73736e9560982ca6234cb49e59d589de21e83d40ddeff3ead1abcb6104ad",
            "final overlay manifest differs")
    overlay = decode(overlay_raw)
    require(overlay["passed"] is True and overlay["status"] == "COMPLETE" and
            overlay["base_inventory"]["sha256"] == inventory_binding["sha256"] and
            overlay["replacement_file_count"] == 2 and
            sum(len(row["parts"]) for row in overlay["representations"]) == 6 and
            overlay["max_packed_blob_bytes"] == 67108864,
            "overlay metadata differs")
    result = {"schema": "mr3-v52-closed-cpu-evidence-v1", "passed": True,
              "scope": "cpu", "engineering_added_seconds": "0",
              "source_recovery_index": index_binding, "checks": checks,
              "saved_cpu_identity_count": len(observations),
              "saved_cpu_identity_observations": observations,
              "all_saved_cpu_identities_fresh_gone": True,
              "post_main_CPU_identities_included_in_main_611": False,
              "first_overlay_CPU_FAIL_preserved": True,
              "immutable_archive_inventory": inventory_binding,
              "packed_representation_manifest": overlay_binding,
              "raw_or_packed_archive_bytes_read": False,
              "scientific_results_recomputed": False,
              "review_archive_overlay_rerun": False,
              "own_checker_identity_in_this_result": False,
              "own_checker_identity_note": "Check this separately after actual tool reap.",
              "producer_pid": os.getpid()}
    with (HERE / "closed_cpu_evidence_v1.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    print(json.dumps({"passed": True, "checks": len(checks),
                      "saved_cpu_identity_count": len(observations)}))


if __name__ == "__main__":
    main()
