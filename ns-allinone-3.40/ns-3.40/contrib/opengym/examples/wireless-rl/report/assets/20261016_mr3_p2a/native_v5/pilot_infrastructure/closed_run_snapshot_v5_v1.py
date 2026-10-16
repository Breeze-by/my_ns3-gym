"""CPU-only immutable close accounting; no model construction or optimizer calls."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

import numpy as np
import torch


RUN = Path(__file__).resolve().parent
OUTPUT = RUN / "closed_run_snapshot_v5_v1.json"
FREEZE = "de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3"
assert not OUTPUT.exists(), "exclusive receipt already exists"
torch.set_num_threads(1)
assert not torch.cuda.is_initialized()
manifest = {}


def read(path):
    payload = path.read_bytes()
    manifest[str(path.relative_to(RUN))] = {
        "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}
    return payload


def load(path):
    return json.loads(read(path))


summary = load(RUN / "summary.json")
metadata = load(RUN / "metadata.json")
assert metadata["freeze"] == summary["freeze"] == FREEZE
assert summary["completed"] is False and summary["stop_reason"] == "infrastructure_error"
assert summary["error"] == "ValueError('terminal detection lag exceeded one 20ms quantum')"
assert summary["cleanup_errors"] == summary["native_accounting_errors"] == []
native_files = sorted(path for path in (RUN / "native").rglob("*") if path.is_file())
for path in native_files:
    read(path)
for name in ("resources.json", "progress.json", "sb3_metrics/progress.json", "initial.zip"):
    read(RUN / name)

native_attempts = []
for path in sorted((RUN / "native").glob("round*/worker*/episode*/transitions.jsonl")):
    steps, submitted, effective_ns, physical_ns, last = 0, 0, 0, 0, None
    for line in path.read_bytes().splitlines():
        row = json.loads(line)
        if row["kind"] != "step":
            continue
        info = row["info"]
        dt, physical = info["dt"], info["physical_dt"]
        action_submitted = info.get("action_submitted", True)
        assert type(action_submitted) is bool and 0 <= dt <= physical <= 1
        assert action_submitted or dt == physical == 0
        steps += 1
        submitted += int(action_submitted)
        effective_ns += round(dt * 1e9)
        physical_ns += round(physical * 1e9)
        last = row
    shutdown = json.loads((path.parent / "supervisor_shutdown.json").read_bytes())
    assert shutdown["remaining_owned_processes"] == []
    assert shutdown["remaining_owned_zombies"] == []
    assert shutdown["worker_returncode"] == 0 and shutdown["forced_shutdown"] is False
    native_attempts.append({
        "directory": str(path.parent.relative_to(RUN)), "api_records": steps,
        "submitted_actions": submitted, "effective_time_ns": effective_ns,
        "physical_time_ns": physical_ns, "epoch": last["info"]["epoch"],
        "last_reward_sequence": last["info"]["reward_diagnostics"]["sequence"],
        "last_dt": last["info"]["dt"], "last_physical_dt": last["info"]["physical_dt"],
        "owned_cleanup_empty": True,
    })
assert len(native_attempts) == 16
assert sum(row["api_records"] for row in native_attempts) == 876
assert sum(row["submitted_actions"] for row in native_attempts) == 876
assert sum(row["effective_time_ns"] for row in native_attempts) == 870120000000
assert sum(row["physical_time_ns"] for row in native_attempts) == 870200000000
for observed, recorded in zip(native_attempts, summary["native_attempts"]):
    assert observed["api_records"] == recorded["api_records"]
    assert observed["submitted_actions"] == recorded["decisions"]
    assert observed["effective_time_ns"] == recorded["effective_time_ns"]
    assert observed["physical_time_ns"] == recorded["physical_time_ns"]

rollout_files = sorted(RUN.glob("rollout_*.npz"))
assert [path.stem for path in rollout_files] == [f"rollout_{i:04d}" for i in range(3)]
rollouts = []
for path, expected in zip(rollout_files, (252, 250, 295)):
    rows = load(path.with_suffix(".json"))
    assert len(rows) == expected
    shapes = {}
    with np.load(io.BytesIO(read(path)), allow_pickle=False) as archive:
        for key in archive.files:
            values = archive[key]
            assert len(values) == expected and np.isfinite(values).all(), key
            shapes[key] = list(values.shape)
        assert archive["terminated"].sum() == 4
        assert not archive["truncated"].any()
    rollouts.append({"file": path.name, "rows": expected, "all_arrays_finite": True,
                     "terminal_episodes": 4, "array_shapes": shapes})

checkpoint_paths = sorted(RUN.glob("checkpoint_*.zip"))
assert [path.stem for path in checkpoint_paths] == [f"checkpoint_{i:04d}" for i in range(3)]
checkpoints = []
for index, path in enumerate(checkpoint_paths):
    payload = read(path)
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        data = json.loads(archive.read("data"))
        policy = torch.load(io.BytesIO(archive.read("policy.pth")), map_location="cpu",
                            weights_only=True)
        optimizer = torch.load(io.BytesIO(archive.read("policy.optimizer.pth")),
                               map_location="cpu", weights_only=True)
    assert data["_n_updates"] == (index + 1) * 4
    assert data["num_timesteps"] == sum((252, 250, 295)[:index + 1])
    assert data["gamma"] == data["gae_lambda"] == 1
    assert all(value.device.type == "cpu" and torch.isfinite(value).all()
               for value in policy.values())
    actor = {key: value for key, value in policy.items() if key.startswith("action_net.")}
    assert set(actor) == {"action_net.weight", "action_net.bias"}
    adam_steps = sorted({int(state["step"].item()) for state in optimizer["state"].values()})
    assert adam_steps == [(index + 1) * 16]
    for state in optimizer["state"].values():
        assert all(not torch.is_tensor(value) or torch.isfinite(value).all()
                   for value in state.values())
    checkpoints.append({
        "file": path.name, "num_timesteps": data["num_timesteps"],
        "ppo_epochs": data["_n_updates"], "all_policy_state_tensors_finite": True,
        "policy_state_tensor_keys": len(policy), "adam_state_entries": len(optimizer["state"]),
        "adam_steps": adam_steps, "all_adam_tensors_finite": True,
        "actor": {key: {"shape": list(value.shape), "elements": value.numel(),
                        "finite": bool(torch.isfinite(value).all()),
                        "max_abs": float(value.abs().max())} for key, value in actor.items()},
    })
assert not (RUN / "final.zip").exists()
assert not list(RUN.glob("rollout_0003.*"))
assert summary["optimizer_updates"] == 48 and summary["ppo_epochs"] == 12
assert summary["decisions"] == summary["closed_episode_decisions"] == 797
assert sum(row["decisions"] for row in summary["episodes"]) == 797
assert sum(row["decisions"] for row in summary["active_episodes"]) == 78
assert summary["collector_observed_decisions"] == 875
assert summary["native_recorded_decisions"] == 876

observer_files = ("raw_map_observer_v2.py", "raw_map_observer_preflight_repro_v2.py",
                  "raw_map_observer_preflight_validation_v2.json")
for name in observer_files:
    read(RUN / name)
observer_validation = json.loads((RUN / observer_files[2]).read_bytes())
assert observer_validation["observer_main_called"] is False
assert observer_validation["DDS_or_ROS_observer_started"] is False
assert manifest[observer_files[0]]["sha256"] == observer_validation["observer_script_sha256"]
assert manifest[observer_files[0]]["sha256"] == (
    "c40673f58e3aeecaa101e62afaf96ea474cdae714c731641de652335119bc651")
assert manifest[observer_files[1]]["sha256"] == (
    "f5e63d6ecb04912b9a3c8bcc5c54e9c0fb505be0d12c54b32d81ad366552cca6")
assert manifest[observer_files[2]]["sha256"] == (
    "fdaf10ff21096e93c276cfc17a84a34079312c128147b49c22953545d45f91ab")
read(Path(__file__).resolve())

# Refuse a mixed-time receipt if any hashed original changed during this CPU read.
for name, record in manifest.items():
    payload = (RUN / name).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == record["sha256"], name
assert not torch.cuda.is_initialized()
receipt = {
    "schema": "mr3-v5-infrastructure-stop-closed-accounting-v1",
    "utc_recorded": datetime.now(timezone.utc).isoformat(), "freeze": FREEZE,
    "status": "INCOMPLETE; infrastructure stop; validation SKIP per root; no final model",
    "command_argv": ["rtk", "proxy", "env", "PYTHONNOUSERSITE=1", "CUDA_VISIBLE_DEVICES=",
                     sys.executable, str(Path(__file__).resolve())],
    "error": summary["error"], "completed": False, "stop_reason": summary["stop_reason"],
    "wall_sec_including_all_attempts": summary["wall_sec_including_all_attempts"],
    "accounting": {
        "closed_saved_buffer_rows": 797, "closed_rounds": 3, "closed_episodes": 12,
        "actual_optimizer_steps": 48, "actual_ppo_epochs": 12,
        "collector_returned_submitted_actions": 875, "native_submitted_actions": 876,
        "native_api_records": 876, "unoptimized_round3_collector_rows": 78,
        "round3_native_rows": 79, "native_minus_collector": 1,
        "native_effective_sim_seconds": 870.12, "native_physical_sim_seconds": 870.2,
        "cleanup_errors": [], "native_accounting_errors": [],
        "round3_all_owned_closures_verified_empty": True,
    },
    "undelivered_terminal_row": {
        "epoch": native_attempts[-1]["epoch"], "worker": 3, "round": 3,
        "native_sequence": 24, "collector_returned_rows": 23, "dt": .68,
        "physical_dt": .72, "detection_lag_ns": 40000000,
        "strict_max_detection_lag_ns": 20000000,
        "scope": "Recorded native row remains preserved; excluded from saved PPO rollouts.",
    },
    "rollouts": rollouts, "checkpoints": checkpoints,
    "latest_checkpoint": "checkpoint_0002.zip", "final_zip_exists": False,
    "round3_saved_rollout_exists": False, "native_attempts": native_attempts,
    "observer_v2": {
        "status": "PREPARED AND UNEXECUTED; execution plans stopped by root",
        "artifacts": {name: manifest[name] for name in observer_files},
        "preflight_checks_passed": 8, "flake8_passed": True,
        "added_subscriptions": observer_validation["added_subscriptions"],
        "all_subscription_count": 16,
        "existing_capture_directories": [path.name for path in sorted(RUN.glob(
            "raw_map_observer_*")) if path.is_dir()],
        "execution_claim_basis": "Agent never called v2 main; parent explicitly confirms unused.",
    },
    "artifact_manifest": manifest, "originals_unchanged_after_read": True,
    "cpu_only": {"cuda_initialized": False, "model_constructed": False,
                 "policy_inference_calls": 0, "optimizer_calls": 0,
                 "ROS_native_observer_jobs": 0, "signals": 0, "tracked_edits": 0},
    "limits": [
        "Checkpoint0002 is the last saved round, not a selected/final/frozen evaluation model.",
        "Finite tensors establish numerical health only, not task reliability or acceptance.",
        "Round3 incomplete samples were never saved/optimized; all native originals are retained.",
        "Summary and raw artifacts are hashed exact close snapshots; no experiment history rewritten.",
        "No new observer execution, training, model selection, evaluation, or task-success claim.",
    ],
}
with OUTPUT.open("x") as target:
    target.write(json.dumps(receipt, indent=2, allow_nan=False) + "\n")
print(json.dumps({"receipt": str(OUTPUT), "sha256": hashlib.sha256(
    OUTPUT.read_bytes()).hexdigest(), "accounting": receipt["accounting"],
    "latest_checkpoint": checkpoints[-1], "observer_v2": receipt["observer_v2"]}, indent=2))
