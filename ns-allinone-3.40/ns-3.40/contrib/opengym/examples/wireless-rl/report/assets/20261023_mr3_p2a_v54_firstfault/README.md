# V54 resource-only FIRSTFAULT successor — not executed on raw

V53 real FAIL is preserved: the1,000,000-line ceiling stopped motion parsing
at1,000,001 lines and2267972220/2458997272 bytes; root reports no other schema/
field error and no work cutoff. UNKNOWN_PARTIAL_PARSE is retained, not rewritten.
V53 parent229.413776461s remains charged in the opening ledger.

This candidate is a NEW prospective version, not an overwrite/retry of V53:

- Fixed same two original ROS files, exact epoch/window/SHAs and unchanged A52
  closed_inventory_v1 reference. Seven interpretation source pins still1fa.
- line ceiling2,000,000; cooperative work480s; full parent fee cap600s. Driver
  allows declared consumer work<=590. No hard-kill/realtime claim; overrun is
  fully charged FAIL. No parser/selection/math/safety change or optimization.
- Source/plan/activity schemas and canonical destinations use V54; consumer is
  firstfault_extract_v3.py, driver run_firstfault_v1.py. Exact future freeze
  remains CLI, avoiding a self-referential commit hash in tracked JSON.
- Opening U90102.9195132536018/C120000/R29897.0804867463982; reservation600.
  Pilot/final0 added and their historical quotas unchanged. A~249s full-read
  estimate comes from V53 partial throughput, NOT an observed full read or a
  guarantee. Original V52/V53 failures and fees remain immutable.

`resource_only_manifest_v1.json` records exact canonical A53 baseline SHAs and
literal replacements. Inverse replacements restore all four complete A53
source/test bytes. The unified patch is `resource_only_v53_to_v54.patch`.
`spec_v1.json` and `scope_v1.json` are fully hash-linked for root's eventual
canonical copy/source seal; they grant no permission to invoke from this/tmp
candidate. No actual two-input raw read/hash has occurred here.

CPU21 synthetic tests actually PASS under exclusive reach_execution --scope cpu:
`/tmp/mr3_p2a_v54_firstfault_cpu_v2/actual_wait.json`, elapsed0.170796105s,
source_before==source_after. Separate `freshgone_v1.json` confirms both saved
CPU identities381699/381708 gone. All stream fixtures are tiny BytesIO records,
including a reduced synthetic line limit; no million-line native test.

The prior CPU_v1 setup has an incorrect support --source path, fails before test
Popen, and has no actual_wait. It is preserved with the actual tool traceback
and exact command in `/tmp/mr3_p2a_v54_firstfault_cpu_v1/setup_failure.json`.
Only the command was corrected in the exclusive second CPU attempt; no source
changed between those attempts. Both CPU activities add0 engineering fee.

Formal root command after closure/canonicalization/new commit and push:

    /usr/bin/python3 -B A54/run_firstfault_v1.py --freeze EXACT_NEW40

All formal outputs are exclusive /tmp/mr3_p2a_v54... paths. The complete outer
parent interval is the single fee; nested intervals are not added. Entry/post
metadata spans are recorded separately. Final external tool reap/fresh-gone and
source/inventory review remain root obligations after formal execution.
