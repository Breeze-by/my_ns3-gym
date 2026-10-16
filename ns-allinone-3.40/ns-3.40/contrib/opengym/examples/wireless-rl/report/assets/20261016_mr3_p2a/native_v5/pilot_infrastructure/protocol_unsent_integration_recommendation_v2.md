# Non-applied post-run integration recommendation, v2

Do not apply while pilot or declared validation native stages are active.
The native/learner source freeze remains de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3.
Keep mr3_learning/audit_ppo.py, the native ROS implementation and canonical P1C
helpers byte-identical. The existing loader's native self/worktree equality
checks must continue to pass rather than be relaxed for a later auditor.

After all declared native stages close, add separate offline asset files for
protocol_unsent_candidate_v2.py, its tests, and a new versioned full-audit wrapper.
Pin the approved helper SHA256:
d852bb68139701ce6c0364c9516285c0dbf70b82180efe478011e4d4faa6a178
Pin test receipt/source as separate review evidence:
31cc4fad75ea662c6ca21885bb9459352e8ecfe60108a9a606306b4eb472ff38

The exact integration delta is a new wrapper; no native learner file needs editing:

```diff
+from mr3_learning import audit_ppo as native_audit
+# Load the external approved helper only after its literal SHA256 check.
+# ProtocolAuditor = loaded_approved_module.ProtocolAuditor
+
+native_freeze = "de7a805af9cd9bc7d1b24e60559ccc4d3054e4c3"
+original_loader = native_audit.load_native_gates
+protocol_wrappers = []
+
+def reviewed_loader(root, freeze):
+    if freeze != native_freeze:
+        raise ValueError("unsupported native freeze for proven-unsent correction")
+    components = original_loader(root, freeze)
+    phase, base, auditor, command, scalar, proof = components
+    reviewed = ProtocolAuditor(auditor.audit_protocol, root, freeze)
+    auditor.audit_protocol = reviewed
+    protocol_wrappers.append(reviewed)
+    return components
+
+try:
+    native_audit.load_native_gates = reviewed_loader
+    result = native_audit.audit_run(run_directory, native_freeze)
+finally:
+    native_audit.load_native_gates = original_loader
+
+# Write to a NEW exclusive output path; never overwrite original full audit.
+# Add explicitly distinct offline-auditor provenance and original-verdict link.
+result["offline_auditor"] = {
+    "method": "mr3-protocol-proven-unsent-peer-stop-v2",
+    "native_freeze": native_freeze,
+    "offline_auditor_git_freeze": verified_post_run_commit,
+    "offline_auditor_files": verified_post_run_blob_and_worktree_hashes,
+    "approved_helper_sha256": approved_helper_sha256,
+    "original_audit_path": original_audit_path,
+    "original_audit_sha256": original_audit_sha256,
+    "original_audit_passed": original_audit["passed"],
+    "original_audit_errors": original_audit["errors"],
+    "protocol_receipts": [receipt for wrapper in protocol_wrappers
+                          for receipt in wrapper.receipts],
+}
```

Before loading: prove the new wrapper/helper bytes equal their blobs in the
recorded later offline-auditor Git commit, and enforce the helper literal hash.
The unchanged original loader must still verify all 44 native/learner/task pins
against native freeze de7a and current matching runtime files. Record the imported
native_audit file's expected path and source SHA as well. The two commits have
different roles; new offline source is never represented as original native code.
Run/store the unmodified original full audit separately after the run closes.
The corrected report retains its exact original FAIL and the independent proof.

The factory changes only one in-memory protocol function. The original phase
wrapper still runs original contact/clock/physics/task checks and independent
command-time validation after that function. Scalar and policy/rollout/checkpoint
checks remain unchanged. A failure in any old or new check remains a failure.

The candidate removes only uniquely proven logical send/terminal records from a
detached replay view; it creates no native receipt and edits no raw event.
Original native status equality and positive cancellation receipt checks are
rerun and mutation-tested after the removed logical-only lifecycle.

Timing qualifier: record() reads self.now(), while flush_protocol_events receives
an earlier captured now. Equality is observed in the reviewed prefix and is a
conservative qualifier for the pinned serialized ROS-clock callback execution.
Do not claim the predicate supports arbitrary asynchronous/multithreaded producer
execution or future gateway transport. Unsupported evidence must fail closed.

V1 candidate and its receipt remain preserved as failed adversarial review.
V2 independent focused review passed 8 tests with nested adversarial cases in
4.484 CPU seconds, after the full 18-test suite passed in 9.516 seconds.
