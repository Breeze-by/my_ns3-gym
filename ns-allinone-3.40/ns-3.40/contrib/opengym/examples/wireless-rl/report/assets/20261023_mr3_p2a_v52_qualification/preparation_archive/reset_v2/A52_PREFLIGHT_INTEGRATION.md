# Unapplied reset-reader registration candidate v2

This directory preserves v1 unchanged and supplies a new review-only patch against the same 23e909380b470039bd5680cf2d07710dca71097e baseline. No reader or tests have been imported or executed. No original runtime artifact has been read. Do not apply the patch while any bound source is frozen.

The production entry remains `mr3_learning.audit_reach_reset_workload`, with fixed profile `mr3-reach-reset-outward-cancel-v1`; only the unique whole PROBE_VERSION assignment is projected in the two exact pinned V17 sources. No native/physics/math/safety gates change. New Reach builders register the profile and all six source paths (entry, shared helper, V17 pair, fixed V3/V4 leaves); validator still rejects missing/unknown registration. Legacy preparation and immutable readers remain untouched.

In the new A52 preflight, after loading and validating the newly sealed plan and checking its exact execution freeze, BEFORE launch, call:

```python
from mr3_learning import audit_reach_reset_workload as reset_reader
reset_reader_entry = reset_reader.verify_reader_readiness(plan, freeze)
# Preserve this exact source-only receipt in the exclusive preflight output.
```

The helper checks six fixed source registrations, current bytes against plan SHA and exact Git freeze, immutable pins, then really calls load_reader('angular') and load_reader('physics'). Both new constants, canonical original module paths, exact inverse source SHA and the entire literal-change list are required. It also loads both unchanged fixed leaf definitions with the same whole-source helper and validates their declared paths/pins and audit definitions. It calls no audit function, reads no native metadata/telemetry and does not create a physical PASS. Exceptions must abort preflight; do not catch them as an expected mathematical FAIL.

Keep existing full current/Git/plan source validation, preparation gates, actual system-Python `-m mr3_learning.audit_reach_reset_workload --help`, complete workload/argv validation, 12EP/30 mandatory roles, and original per-episode physics dependency. Bind this entry and shared helper in all new source inventories/actual-wait receipts. The actual load helper is additional readiness verification, not a replacement for plan validation or source gates. Never change V50 preflight/results retrospectively.

Focused future CPU command after canonical application and source sealing (NOT RUN):

```
PYTHONNOUSERSITE=1 conda run --no-capture-output -n ns3gym python -B -m pytest -q mr3_learning/tests/test_reach_reset_workload.py mr3_learning/tests/test_reach_qualification.py
```

Root should resolve and bind the active ns3gym interpreter in the actual-wait wrapper before execution; system-Python module-help/readiness is a separate source-sealed root check. There are 26 test method definitions in the new test file, not 26 executed checks. Actual projected reader fixtures use only fresh synthetic toy JSON, preserve expected original mathematical FAIL, and explicitly reject any source-loading error as false readiness. An additional missing-leaf fixture demonstrates that absence is a source failure, never borrowed math/qualification credit. Missing entry/helper/leaf source inventory, wrong current/Git/pin, wrong loaded constant and inverse, and leaf import exception are explicit negative fixtures.

Attribution correction: reach_audit_projection.py is NOT one of the 24 original runtime source_proof/import-pin sources for the planned single-EP profile. Changing that helper would not inherently invalidate that particular old source proof; the root's sequencing of profile before production reset-registration changes remains deliberate measurement isolation. The shared helper is independently executed by this new reset entry and MUST be bound by the new preparation/preflight/outer source inventory.

No old FAIL is reclassified; no P2A or native qualification credit is created by this patch or source-only preflight.
