"""Stream-preserve closed v7 native interface and every original required result."""
from pathlib import Path
from decimal import Decimal
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tarfile

REPO = Path("/home/zhuyulab/ns3-workspace")
W = REPO / "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
A = W / "report/assets/20261017_mr3_p2a0_v7"
I, ACCOUNT = A / "independent", A / "accounting"
SOURCE = REPO / "ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v7_interface"
PACK, NATIVE = Path("/tmp/mr3_p2a0_v7_selected_interface"), A / "native/interface"
FREEZE = "01cfa040dcb73f8931dd11d66b69ce765cb8412f"
CHUNK = 1024 * 1024


def digest(path, decoded=False):
    h, size = hashlib.sha256(), 0
    opener = gzip.open if decoded else open
    with opener(path, "rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            h.update(block)
            size += len(block)
    return size, h.hexdigest()


def load(path):
    with path.open() as stream:
        return json.load(stream)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as output:
        json.dump(value, output, indent=2, allow_nan=False)
        output.write("\n")


def preserve(path, target, compress=False):
    target.parent.mkdir(parents=True, exist_ok=True)
    with path.open("rb") as source, target.open("xb") as sink:
        if compress:
            with gzip.GzipFile(filename="", mode="wb", fileobj=sink, mtime=0) as encoded:
                shutil.copyfileobj(source, encoded, CHUNK)
        else:
            shutil.copyfileobj(source, sink, CHUNK)
    raw_size, raw_sha = digest(path)
    encoded_size, encoded_sha = digest(target)
    assert digest(target, compress) == (raw_size, raw_sha), target
    return {"source": str(path), "encoding": "gzip" if compress else "identity",
            "raw_bytes": raw_size, "raw_sha256": raw_sha,
            "selected_bytes": encoded_size, "selected_sha256": encoded_sha}


before = [{"path": str(p.relative_to(A)), "bytes": p.stat().st_size,
           "sha256": digest(p)[1]} for p in sorted(A.rglob("*")) if p.is_file()]
assert not PACK.exists() and not NATIVE.exists()
PACK.mkdir(parents=True)
entries, duplicates = [], []
for path in sorted(SOURCE.rglob("*")):
    if not path.is_file() or path.suffix == ".pyc":
        continue
    if path.suffix == ".gz" and path.with_suffix("").is_file():
        if digest(path, True) == digest(path.with_suffix("")):
            duplicates.append(str(path.relative_to(SOURCE)))
            continue
    relative = path.relative_to(SOURCE)
    compress = path.suffix in (".log", ".jsonl", ".csv", ".zip") or path.name == "resources.json"
    selected = Path(str(relative) + ".gz") if compress else relative
    row = preserve(path, PACK / selected, compress)
    row["selected"] = str(selected)
    entries.append(row)
manifest = {"schema": "mr3-p2a-selected-originals-v1", "source": str(SOURCE),
            "selection": "All run files excluding byte-duplicate sibling gzip copies and Python cache.",
            "source_files": len(entries), "raw_bytes": sum(x["raw_bytes"] for x in entries),
            "selected_bytes": sum(x["selected_bytes"] for x in entries), "files": entries,
            "duplicate_encoded_copies_not_selected": duplicates}
write(PACK / "manifest.json", manifest)
for row in entries:
    assert digest(Path(row["source"])) == (row["raw_bytes"], row["raw_sha256"])
    assert digest(PACK / row["selected"]) == (row["selected_bytes"], row["selected_sha256"])
    assert digest(PACK / row["selected"], row["encoding"] == "gzip") == (row["raw_bytes"], row["raw_sha256"])
shutil.copytree(PACK, NATIVE)
assert sum("drive_model_" in x["selected"] for x in entries) == 3
assert sum("/drive_tb" in x["selected"] and x["selected"].endswith(".jsonl.gz") for x in entries) == 3
originals = []
for path in sorted(Path("/tmp").glob("mr3_p2a0_v7_interface*")):
    if not path.is_file() or path.suffix not in (".json", ".log", ".txt"):
        continue
    if path.suffix == ".json":
        load(path)
    directory = ACCOUNT if path.name.endswith("_launch.json") or path.suffix == ".log" else I
    compress = path.suffix in (".log", ".txt") or path.stat().st_size > 1_000_000
    target = directory / (path.name + (".gz" if compress else ""))
    row = preserve(path, target, compress)
    row["selected"] = str(target.relative_to(A))
    originals.append(row)
for name in ("mr3_p2a0_v7_source_preflight.json", "mr3_p2a0_v7_binaryproof.json",
             "source_bindings_01cfa040dcb7.json", "source_bindings_01cfa040dcb7.tar.gz",
             "mr3_readonly_v7_drive_process_monitor.py", "mr3_readonly_v7_body_live.py",
             "mr3_p2a0_v7_goal_guard_diagnostics_v1.py",
             "mr3_p2a0_v7_drive_target_ubsan_command_reconstruction_v1.json"):
    path = Path("/tmp") / name
    target = I / path.name
    row = preserve(path, target)
    row["selected"] = str(target.relative_to(A))
    originals.append(row)
row = preserve(Path(__file__), I / Path(__file__).name)
row["selected"] = str((I / Path(__file__).name).relative_to(A))
originals.append(row)
source = load(Path("/tmp/source_bindings_01cfa040dcb7.json"))
encoded = Path("/tmp/source_bindings_01cfa040dcb7.tar.gz").read_bytes()
assert hashlib.sha256(encoded).hexdigest() == source["encoded_sha256"]
with tarfile.open(fileobj=io.BytesIO(encoded), mode="r:gz") as archive:
    assert len(archive.getmembers()) == source["source_count"] == 97
    for row in source["files"]:
        raw = archive.extractfile(row["path"]).read()
        assert len(raw) == row["bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"]
        assert raw == subprocess.check_output(["git", "show", FREEZE + ":" + row["path"]], cwd=REPO)
episode = SOURCE / "worker0/episode001_open_101"
trans = [json.loads(x) for x in (episode / "transitions.jsonl").read_text().splitlines()]
physics = [json.loads(x) for x in (episode / "physics.jsonl").read_text().splitlines()]
adapter = [json.loads(x) for x in (episode / "adapter.jsonl").read_text().splitlines()]
steps = [x for x in trans if x["kind"] == "step"]
resets = [x for x in trans if x["kind"] == "reset"]
actions = [x for x in adapter if x["kind"] == "action"]
rejected = [x for x in adapter if x["kind"] == "action_rejected"]
submitted = actions + rejected
ns = lambda x: int(Decimal(str(x)) * 1_000_000_000)
release = trans[0]["info"]["release_time_ns"]
last = ns(trans[-1]["snapshot"]["source_stamp"])
end = physics[-1]["end_time_ns"]
returned = {x["info"]["command"]["command_id"] for x in steps}
unreturned = [x["payload"]["command_id"] for x in submitted if x["payload"]["command_id"] not in returned]
assert len(resets) == 1 and len(steps) == len(submitted) == 20 and not unreturned
assert last - release == sum(ns(x["info"]["physical_dt"]) for x in steps) == 20_000_000_000
benchmark = load(SOURCE / "benchmark_summary.json")
launch = load(Path("/tmp/mr3_p2a0_v7_interface_launch.json"))
full = load(Path("/tmp/mr3_p2a0_v7_interface_full_audit.json"))
angular = load(Path("/tmp/mr3_p2a0_v7_interface_fixed_angular_v1.json"))
physical = load(Path("/tmp/mr3_p2a0_v7_interface_fixed_physics_v1.json"))
drive = load(Path("/tmp/mr3_p2a0_v7_interface_drive_review_v1.json"))
assert not full["passed"] and not angular["passed"] and not physical["passed"] and drive["passed"]
assert full["native"]["passed"] and angular["sampled_bounds_passed"]
assert len(full["source_bindings"]) == 97 and full["freeze"] == FREEZE
activity = full["episodes"][0]["activity"]["latest_actor_activity"]
write(ACCOUNT / "interface_accounting_v1.json", {
    "schema": "mr3-p2a0-v7-interface-accounting-v1", "freeze": FREEZE,
    "benchmark_raw_passed": benchmark["passed"], "overall_preparation_passed": False,
    "returned_reset_api_rows": len(resets), "returned_step_api_rows": len(steps),
    "returned_api_rows": len(resets) + len(steps), "submitted_action_commands": len(submitted),
    "adapter_accepted_action_rows": len(actions), "adapter_rejected_action_rows": len(rejected),
    "rejected_actions": rejected, "unreturned_action_ids": unreturned,
    "release_time_ns": release, "last_returned_snapshot_ns": last, "final_physics_clock_ns": end,
    "returned_effective_ns": sum(ns(x["info"]["dt"]) for x in steps),
    "returned_physical_ns": sum(ns(x["info"]["physical_dt"]) for x in steps),
    "cleanup_physics_ns": end - last,
    "controlled_warmup_alignment_ns": release - physics[0]["start_time_ns"],
    "post_release_physics_ns": end - release,
    "benchmark_wall_sec": benchmark["wall_sec_including_all_attempts"],
    "launcher_wall_sec": launch["wall_duration_sec"], "launcher_returncode": launch["returncode"],
    "activity": activity, "stage_outcomes": {
        "interface": {"status": "FAIL", "native_full_audit_passed": full["native"]["passed"],
                      "full_preparation_passed": full["passed"], "full_errors": full["errors"],
                      "fixed_driver_passed": drive["passed"], "fixed_angular_passed": angular["passed"],
                      "sampled_angular_bounds_passed": angular["sampled_bounds_passed"],
                      "angular_missing": angular["missing"], "fixed_physics_passed": physical["passed"],
                      "cause": "required per-robot movement and angular/stopping stimulus coverage incomplete; bounds not relaxed"},
        **{stage: {"status": "SKIP", "reason": "required interface failed; predeclared stop rule"}
           for stage in ("terminal", "reset", "deadline")}},
    "scope": "Complete normal engineering truncated prefix; strict closure and actual tagged latency PASS are component evidence only. No95percent/PPO/GPU/pilot credit; no later native stages."})
write(I / "interface_originals_manifest_v1.json", {
    "schema": "mr3-p2a0-v7-interface-original-reviews-v1", "freeze": FREEZE,
    "files": originals, "native_manifest": "native/interface/manifest.json",
    "native_manifest_sha256": digest(NATIVE / "manifest.json")[1],
    "scope": "Original FAIL and PASS review bytes preserved exactly, with lossless gzip for stdout and large JSON."})
for row in before:
    assert digest(A / row["path"]) == (row["bytes"], row["sha256"])
write(I / "interface_archive_verification_v1.json", {
    "schema": "mr3-p2a0-v7-interface-canonical-verification-v1", "passed": True, "freeze": FREEZE,
    "prior_assets_unchanged": len(before), "prior_asset_bindings": before,
    "native_source_files": manifest["source_files"], "raw_bytes": manifest["raw_bytes"],
    "selected_bytes": manifest["selected_bytes"], "native_encoded_decoded_original_sha_equal": True,
    "effective_sdf_count": 3, "drive_raw_jsonl_count": 3, "source_payload_files": 97,
    "source_payload_encoded_sha256": hashlib.sha256(encoded).hexdigest(),
    "source_payload_matches_exact_git_bytes": True, "original_reviews_archived": len(originals),
    "detached_full_audit_rerun": False,
    "scope": "Archive byte integrity only. Original full97-source FAIL, actual driver PASS, angular/physical coverage FAIL retained; no detached replacement or relabel."})
files = [{"path": str(p.relative_to(A)), "bytes": p.stat().st_size, "sha256": digest(p)[1]}
         for p in sorted(A.rglob("*")) if p.is_file()]
write(A / "inventory_native_v2.json", {"schema": "mr3-p2a0-v7-native-inventory-v2", "freeze": FREEZE,
    "self_excluded": True, "prefreeze_assets_preserved": len(before), "files": files,
    "scope": "Original prefreeze inventory preserved; native and contemporaneous evidence appended."})
result = {"passed": True, "native_files": manifest["source_files"], "raw_bytes": manifest["raw_bytes"],
          "selected_bytes": manifest["selected_bytes"], "original_reviews": len(originals),
          "source_payload_files": 97, "prior_assets_unchanged": len(before), "inventory_files": len(files),
          "inventory_sha256": digest(A / "inventory_native_v2.json")[1]}
write(Path("/tmp/packing_mr3_p2a0_v7_interface_receipt.json"), result)
print(json.dumps(result, indent=2))
