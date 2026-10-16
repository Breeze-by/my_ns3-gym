"""CPU-only reproduction of a secondary original-audit round omission error."""

import ast
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np
import torch
from sb3_contrib import MaskablePPO

from mr3_learning.audit_ppo import audit_rollout, native_decisions, policy_replay


ROOT = Path("/home/zhuyulab/ns3-workspace")
RUN = Path(__file__).resolve().parent
FREEZE = "de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3"
WIRELESS = "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=RUN / "v5_original_audit_cascade_review_v1.json")
    output = parser.parse_args().output
    assert not output.exists()
    original_path = RUN / "audit_v5_original.json"
    original, summary, metadata = (load(RUN / name) for name in (
        "audit_v5_original.json", "summary.json", "metadata.json"))
    assert original["freeze"] == metadata["freeze"] == summary["freeze"] == FREEZE
    assert not original["passed"] and len(original["source_proof"]) == 44
    source = {}
    # Native worker/evaluator are intentionally not checked against current
    # bytes: they now have independent prospective repair write ownership.
    for name in ("audit_ppo.py", "audit_scalar.py", "observation.py", "policy.py",
                 "model.py", "rollout.py"):
        relative = WIRELESS + "mr3_learning/" + name
        frozen = subprocess.check_output(["git", "show", FREEZE + ":" + relative], cwd=ROOT)
        assert (ROOT / relative).read_bytes() == frozen
        source[relative] = {"sha256": hashlib.sha256(frozen).hexdigest(),
                            "native_git_source": FREEZE + ":" + relative,
                            "current_actor_or_auditor_bytes_equal": True}
    auditor_source = (ROOT / WIRELESS / "mr3_learning/audit_ppo.py").read_text()
    auditor_lines = auditor_source.splitlines()
    function = [node for node in ast.parse(auditor_source).body
                if isinstance(node, ast.FunctionDef) and node.name == "audit_run"][0]
    control_flow_source = {"first_line": 435, "last_line": 474,
                           "source": "\n".join(auditor_lines[434:474])}
    assert function.lineno <= 435 <= function.end_lineno
    listed = sorted([row for row in summary["episodes"] if "/round0000/" in row["directory"]],
                    key=lambda row: row["episode_index"])
    assert len(listed) == 4
    original_episodes = {Path(row["directory"]): row for row in original["episodes"]}
    torch.set_num_threads(1)
    model = MaskablePPO.load(RUN / "initial.zip", device="cpu")
    assert model.gamma == model.gae_lambda == 1.
    full, omitted, episode_proof = [], [], []
    for recorded in listed:
        directory = Path(recorded["directory"])
        decisions, api = native_decisions(directory)
        assert len(decisions) == recorded["decisions"] and api == recorded["api_records"]
        policy = policy_replay(model, decisions, deterministic=False)
        old = original_episodes[directory]
        included = bool(old["native"]["passed"] and not old["scalar"]["errors"])
        start, end = len(full), len(full) + len(decisions)
        episode_proof.append({"worker_id": recorded["worker_id"],
                              "episode_index": recorded["episode_index"],
                              "native_decisions": len(decisions), "native_api": api,
                              "complete_archive_start_offset": start,
                              "complete_archive_end_offset_exclusive": end,
                              "original_native_passed": old["native"]["passed"],
                              "original_episode_errors": old["errors"],
                              "included_by_original_audit_run_control_flow": included,
                              "collecting_policy_cpu_replay": policy,
                              "native_data_sha256": {name: sha(directory / name) for name in (
                                  "metadata.json", "transitions.jsonl", "summary.json")}})
        full.extend(decisions)
        if included:
            omitted.extend(decisions)
    assert [row["native_decisions"] for row in episode_proof] == [53, 11, 128, 60]
    assert [row["included_by_original_audit_run_control_flow"] for row in episode_proof] == [
        True, False, True, True]
    assert len(full) == 252 and len(omitted) == 241
    with np.load(RUN / "rollout_0000.npz", allow_pickle=False) as archive:
        stored_mask = archive["obs_action_mask"].copy()
    complete_mask = np.stack([row["observation"]["action_mask"] for row in full])[:, None]
    partial_mask = np.stack([row["observation"]["action_mask"] for row in omitted])[:, None]
    assert np.array_equal(stored_mask, complete_mask)
    assert not np.array_equal(stored_mask, partial_mask)
    common = min(len(stored_mask), len(partial_mask))
    unequal = np.any(stored_mask[:common] != partial_mask[:common], axis=(1, 2))
    first = int(np.flatnonzero(unequal)[0])
    try:
        audit_rollout(RUN / "rollout_0000.npz", omitted, gamma=1., gae_lambda=1.)
        raise AssertionError("partial241-row expectation unexpectedly accepted252-row archive")
    except ValueError as error:
        partial_error = str(error)
    assert partial_error == "rollout tensor differs from native received snapshot: action_mask"
    assert "round 0: " + partial_error in original["errors"]
    complete_replay = audit_rollout(RUN / "rollout_0000.npz", full,
                                    gamma=metadata["gamma_per_second"],
                                    gae_lambda=metadata["lambda_per_second"])
    result = {
        "schema": "mr3-p2a-v5-original-audit-cascade-review-v1",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "native_source_freeze": FREEZE, "original_full_audit_sha256": sha(original_path),
        "original_full_audit_passed": original["passed"],
        "original_full_audit_errors_preserved": original["errors"],
        "original_pre_repair_source_proof_entries": len(original["source_proof"]),
        "source_scope": "Original full source proof was captured before prospective ROS edits. "
                        "Only unchanged actor/mask/learner/auditor bytes are checked now; no "
                        "load_native_gates/full-run audit or current worker/evaluator pin is invoked.",
        "unchanged_actor_auditor_source": source,
        "original_control_flow_source": control_flow_source,
        "episode_accounting": episode_proof,
        "cascade": {
            "cause": "Original audit_run raises on worker1 native protocol gate before native_decisions "
                     "and rounds.append. It then compares a reduced241-row expectation with the "
                     "complete252-row archive. action_mask is the first checked observation field.",
            "stored_shape": list(stored_mask.shape), "partial_expected_shape": list(partial_mask.shape),
            "shape_mismatch_alone_causes_array_equal_false": True,
            "first_cropped_alignment_mismatch_index_zero_based": first,
            "stored_first_mismatch_snapshot_digest": full[first]["snapshot_digest"],
            "partial_expected_first_mismatch_snapshot_digest": omitted[first]["snapshot_digest"],
            "stored_first_mismatch_legal_action_count": int(stored_mask[first].sum()),
            "partial_first_mismatch_legal_action_count": int(partial_mask[first].sum()),
            "stored_worker_at_first_mismatch": 1 if 53 <= first < 64 else None,
            "partial_expected_worker_at_first_mismatch": 2 if 53 <= first < 181 else None,
            "cropped_mismatched_rows": int(unequal.sum()),
            "reproduced_partial_audit_error": partial_error,
        },
        "complete_four_episode_replay": complete_replay,
        "conclusion": "Secondary omission/alignment error, not evidence of actual round0 mask corruption. "
                      "Complete4-episode CPU collecting-policy/native tensor/mask/reward/GAE replay passes. "
                      "This does not convert original whole-pilot FAIL toPASS or erase worker1 protocol, "
                      "round3 invalid40ms/partial-attempt, missing finalcheckpoint or incomplete-run errors.",
        "future_reporting_recommendation": "Retain failed native verdicts, but reconstruct closed-round "
                                           "tensor evidence independently of acceptance or explicitly mark "
                                           "round replay blocked/incomplete. Never silently compare a missing-episode "
                                           "subset with a complete archive or grant failed samples training credit.",
        "reproduction_script_sha256": sha(Path(__file__)),
        "reproduction": "From wireless-rl with PYTHONNOUSERSITE=1, conda ns3gym Python runpy.run_path "
                        "this script. For an independent rerun supply --output /tmp/unique_name.json; "
                        "it reads closed round0 only and never overwrites an existing JSON.",
        "scope": "CPU-only parsing/policy replay. No ROS/native/simulator/GPU/optimizer/control calls, "
                 "no source/gate/evidence edits; only this new ignored review/script are written.",
    }
    with output.open("x") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
        handle.write("\n")
    print(json.dumps({"artifact": str(output), "sha256": sha(output),
                      "original_full_passed": original["passed"],
                      "stored_rows": len(full), "partial_expected_rows": len(omitted),
                      "first_cropped_mismatch": first, "complete_replay_passed": True,
                      "preupdate_errors": complete_replay["pre_update_replay_max_abs_error"]}))


if __name__ == "__main__":
    main()
