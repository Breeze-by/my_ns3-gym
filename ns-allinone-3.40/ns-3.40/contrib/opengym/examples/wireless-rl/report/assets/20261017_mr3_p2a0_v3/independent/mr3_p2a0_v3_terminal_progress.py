"""Read-only partial native reset status; never a final acceptance audit."""
import datetime
import json
from pathlib import Path
ROOT = Path("/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v3_terminal")
report = []
for episode in sorted(ROOT.glob("worker*/episode*")):
    path = episode / "transitions.jsonl"
    raw = path.read_bytes() if path.exists() else b""
    lines = raw.splitlines()
    if raw and not raw.endswith(b"\n"):
        lines = lines[:-1]
    rows = [json.loads(line) for line in lines if line]
    item = {"episode": str(episode.relative_to(ROOT)), "transition_rows": len(rows),
            "closed": (episode / "summary.json").exists()}
    if rows:
        snapshots = {row["snapshot"]["digest"]: row["snapshot"] for row in rows}
        path = episode / "adapter.jsonl"
        raw = path.read_bytes() if path.exists() else b""
        lines = raw.splitlines()
        if raw and not raw.endswith(b"\n"):
            lines = lines[:-1]
        audit = [json.loads(line) for line in lines if line]
        item["robots"] = {}
        for i, name in enumerate(("tb1", "tb2", "tb3")):
            legal = sum(any(ok and (a // (100, 10, 1)[i]) % 10 < 8
                            for a, ok in enumerate(s["joint_action_mask"]))
                        for s in snapshots.values())
            last = rows[-1]["snapshot"]
            r = last["robots"][i]
            sends = [row["payload"] for row in audit if row["kind"] == "native_send"
                     and row["payload"]["robot"] == name]
            receipts = [row["payload"]["payload"] for row in audit
                        if row["kind"] == "delivery" and row["payload"]["stream"] == "receipt"
                        and row["payload"]["source"] == name]
            accepted = sorted({r["goal_id"] for r in receipts
                               if r["type"] == "accept" and r["value"] is True})
            item["robots"][name] = {
                "snapshots": len(snapshots), "snapshots_with_joint_legal_goal": legal,
                "latest_target_cells": last["diagnostics"]["per_robot_reachable_target_cells"][i],
                "latest_seed_reason": last["path_maps"][name]["seed_rejection_reason"],
                "latest_phase": r["navigation"]["phase"], "native_send_count": len(sends),
                "actual_accepted_goal_ids": accepted,
                "latest_received_path_m": r["activity"]["estimated_path_m"],
                "latest_received_path_complete": r["activity"]["path_observation_complete"],
                "received_path_gt_0_05m": r["activity"]["estimated_path_m"] is not None
                                          and r["activity"]["estimated_path_m"] > .05,
            }
    report.append(item)
result = {"scope": "partial terminal KEEP integrity/availability observation; no movement credit",
          "observed_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
          "benchmark_complete": (ROOT / "benchmark_summary.json").exists(), "episodes": report}
with Path("/tmp/mr3_p2a0_v3_terminal_progress.jsonl").open("a") as output:
    output.write(json.dumps(result, sort_keys=True) + "\n")
print(json.dumps(result, indent=2))
