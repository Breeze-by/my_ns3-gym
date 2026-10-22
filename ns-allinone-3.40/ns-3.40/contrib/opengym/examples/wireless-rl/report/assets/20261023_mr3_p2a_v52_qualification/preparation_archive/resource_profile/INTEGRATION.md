# Unapplied resource-profile increment v1

This is a review-only increment **after** `/tmp/mr3_v51_reset_workload_patch_v2/candidate/mr3_learning/reach_preparation.py` (SHA `a4d1f5b121530c233df7f8dcd8b98f93ce5ace70a6f5a3f77df93f97aea67daf`). Apply reset-v2 first, then this increment, only when root permits canonical source changes. No candidate imports/tests or native/raw consumer have run; no repository/proof source changed. The synthetic amounts in the test are NOT a real budget proposal.

Files:

- `resource_profile_increment_v1.patch`: full repository-relative incremental patch.
- `candidate/mr3_learning/reach_preparation.py`: combined reset-v2 + resource candidate.
- `candidate/mr3_learning/tests/test_reach_engineering_block.py`: 10 unexecuted test-method definitions, with table-driven negatives and stubbed qualification/PPO boundaries.
- `baseline/…/reach_preparation.py`: exact reset-v2 input snapshot.
- `ast_static_result_v1.json`: AST-only result. Only existing `build_plan` and `validate_plan` change; `_bounded_reservation`, allocator/qualification functions and `preparation.py` SHA remain unchanged. This is not CPU PASS.

The new profile is exactly `autonomous-engineering-block-v1`. Old default and `bounded-original-workload-v1` keep their original allocations/upper limits/plan fields. New profile arithmetic can exceed the old wall limits but cannot exceed its one sealed finite resource declaration. Minimum1800/native1150, pilot/final, 12EP/30roles, steps/seeds/close120 and every scientific/source gate remain unchanged. No V50 role reuse or mixed-freeze qualification is admitted.

## Resource input and normalized ledger

`engineering_resource` is a canonical repository-relative `{path, sha256, bytes}` input spec. Its JSON has the exact schema exercised in the test:

```
schema = mr3-reach-autonomous-engineering-block-v1
decision_maker = agent
authority_basis = user-autonomous-continuation
numeric_user_approval_claimed = false
previous_accounting = {path, sha256, bytes}
engineering_used_seconds / engineering_ceiling_seconds / engineering_remaining_seconds
matrix_wall_seconds / stage_wall_seconds{four stages} / native_wall_seconds{four stages}
close_reserve_seconds=120 / preflight_wall_seconds / minimum_wall_seconds=1800
external_wall_seconds / total_reservation_seconds
```

Every amount must be finite nonboolean; U may be zero, others must be positive. Require U+R=C, total=matrix+preflight+minimum+external≤R, stage sum≤matrix, and 120<native<stage. Metadata attribution, unique JSON keys, canonical paths, exact SHA/bytes and distinct resource/ledger inputs are checked.

Root has reported the original V51 review uses `engineering_cumulative_used_seconds`. **Do not modify that original.** Supply the separately planned canonical `closure_ledger_v1.json` with `passed=true` and `engineering_cumulative_seconds`; this latter value must equal U. The resource validator binds that normalized ledger's bytes. The new activity preparer must additionally verify its original driver/review references using their actual SHA/bytes and close semantics, and bind those originals in the new source inventory. Normalization is not permission to manufacture or refund prior fees.

`engineering_resource_budget(spec, workspace)` returns normalized `budget`, `stage_wall_seconds`, `native_wall_seconds`, `source_bindings`. Both the resource JSON and normalized prior ledger become required plan source bindings. Every returned budget field and stage/native allocation is checked against its repeated plan value. New ceiling C remains unchosen until root's measured-cost decision; do not fill it from test data or claim numeric user approval.

## Exact integration points for the four NEW activity scripts

Do not edit the closed V50 scripts or blindly copy their monetary assertions.

1. **prepare**: verify V51 normalized ledger and its bound original closure records. Read the new resource spec; call `resource = preparation.engineering_resource_budget(spec)`. Then call the real builder with:

   ```python
   preparation.build_plan(...,
       engineering_remaining_seconds=resource['budget']['engineering_remaining_seconds'],
       reservation_profile=preparation.AUTONOMOUS_RESOURCE_PROFILE,
       engineering_resource=spec)
   ```

   Do not pass legacy `reservation`. Do not overwrite the returned budget with V50 `75000/16000/18220`, `approved_cumulative_engineering_seconds` or its old authorization attribution. Bind the resource spec, normalized ledger, original closure references and current CPU/readiness/source/ELF evidence; set the new activity paths consistently. Keep policy registry/minimum requirements as before.

2. **plan_check**: `load_plan` already validates the sealed resource, strict repeated fields, registrations and full original workload. Check all three unchanged `stage_spec`s and new plan/run/qualification paths. Reject unknown profiles; remove only the V50-specific old profile/matrix equality in this NEW script. Do not weaken source, reader or scientific gates.

3. **preflight**: use the same resource spec and normalized result rather than duplicate constants. Require plan/source/current Git equality, full post-V51 evidence binding and exactly the normalized budget/maps. Run reset-v2 `verify_reader_readiness(plan, freeze)` and existing executor/full/controlled/peer/cadence/PPO/native-gate definition readiness, with original environment separation. Source-only readiness must abort on import/projection failure; it creates no physical credit.

4. **driver**: before launching its first child, validate the new plan and resource spec; derive C/U/R/M/preflight/minimum/external from the normalized fields. Record the resource binding/profile and delegated attribution in entry metadata. Enforce actual preflight≤P, matrix≤M, full parent interval-union accounting, external tail≤E, and qualification→minimum only if actual remaining≥1800+unused external reserve. At completion compare U+actual engineering union to C. Never use V50 hardcoded `ENGINEERING_CEILING` or entry schema. Pilot/final stay independently charged against their unchanged original quotas/caps.

The shared `preparation.py` allocator/executor remains pinned and unchanged; it already consumes declared wall numbers. Its deadline stops submissions but drains real submitted work, so phase reservations still need measured margins. No claim of hard OS termination is added.

## Focused future CPU, not run here

After canonical application and new source sealing, root should run the new test together with existing `test_reach_reservation`, `test_reach_qualification`, `test_reach_training_admission`, `test_reach_reset_workload`, and relevant policy/actual new four-script fixture checks. Existing reservation tests protect old behavior. New fixtures reject attribution/ledger/SHA/nonfinite/unknown profile and plan divergence, preserve full roles/workload, round-trip entirely synthetic qualification, then show valid admission reaches only a mocked first-mkdir boundary and changed resources reject before mkdir/model/native/GPU.

Before any native chain, the four-script CPU must cover the same resource spec through prepare→plan_check→preflight→driver admission, parent-fee arithmetic and minimum's leftover reserve. Qualification/PPO call `load_plan` again; do not defer this compatibility check until after expensive native execution. New tracked tests must be included in dynamic source inventory/CPU classification before plan sealing.

Only real future same-freeze qualification and learning/strict final outcomes can provide P2A credit. All old FAIL and cumulative fees remain.
