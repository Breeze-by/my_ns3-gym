# V50 closure v2: retained unknowns and separate byte preservation

This is a static draft only. No script, fixture, scientific reader, process
lookup, active runtime enumeration or archive was executed. The repository was
not changed. Frozen V50 remains `23e909380b470039bd5680cf2d07710dca71097e`.

The v1 scripts and note remain unchanged; exact extra copies and hashes are in
`/tmp/mr3_p2a_v50_closure_v1_preservation_v1.json`. New candidate scripts:

- `/tmp/mr3_p2a_v50_review_closed_draft_v2.py`
- `/tmp/mr3_p2a_v50_collect_closed_draft_v2.py`

## Identity semantics

Only an explicit same-object positive PID/start pair creates a saved identity.
Canonical positive decimal strings remain accepted, booleans/invalid starts
remain invalid. A matching current `/proc` start is present even for Z; a
different start is a different process. Missing/unreadable current process data
does not silently turn an unreadable saved pair into gone.

v2 also retains every PID-only occurrence, its exact source/JSON pointer/field,
and a fresh PID-only observation. It explicitly says original start unknown even
when that PID is absent now. It never uses the current `/proc` start as the
missing historical start, and never combines separate objects to fabricate a
pair. Explicitly observational/ancestry PID fields are retained separately and
do not become owned identities merely by being a numeric relation.

The original A16 global PID inventory-coverage distinction is preserved:

- A command receipt may contain a top-level PID without start and a separately
  saved `process_identity` object with an explicit pair. The PID-only occurrence
  remains unpaired and is not called gone. Its independently saved pair(s) can
  satisfy inventory coverage; the reviewer checks all those actual pairs and
  reports their original pointers. This is not a new cross-object identity.
- A saved PID with no independently saved start anywhere is explicitly listed
  in `pids_without_saved_start`, remains unknown, and fails identity inventory
  completeness. A prior absence report's unbound-PID list is retained even
  though it contains scalars rather than normalized identity objects.
- Malformed/conflicting same-object pairs and unreadable paired-ID lookups also
  prevent complete identity closure. New PID-named fields are retained rather
  than silently dropped; no original failure is rejudged.

The existing activity final-absence PASS/FAIL and its errors are always preserved
as original facts. A later metadata review is not an override of that result,
does not grant scientific qualification, and does not prove an unrecorded
process never existed. A16 inventory coverage is separate from an unsupported
claim that every original PID-only occurrence has a recovered identity.

## Two explicit archival modes

After root actually reaps the whole driver, the v2 reviewer reports three
separate results: metadata/source consistency, saved-identity completeness, and
whether a stable opaque preservation attempt is admissible.

`--mode closed` requires consistent reviewed bytes and complete identity
inventory, no globally unbound saved PID or malformed pair, and every explicit
saved pair freshly gone. It still does not require the science/task to have
passed. A genuine failed scientific attempt with properly closed processes is
fully archivable without changing its FAIL.

`--mode preserve-evidence` permits preserving original scientific/closure FAIL,
unknown identity, or a still-present/unreadable non-parent saved identity. It
requires the driver and every submitted parent/wrapper/inner child actually
waited and freshly gone, and stable reviewed metadata/source bytes/membership.
It records all original review/identity errors and new identity observations;
it does not claim native/scientific closure or final writer quiescence. This
mode is explicitly a byte snapshot, not an alternate way to get closure PASS.

Both modes keep the fixed roots and unchanged V45 lossless copier. Every source
file must match its initial stat before copying, its stat after copying and the
final complete root membership/stat snapshot. Every new compressed wrapper is
decompressed and SHA-checked against the opaque original bytes. A writer or
membership change causes archive failure, with partial copies and a failure
inventory preserved. A stable interval does not prove no unrecorded writer can
exist later. Known or unknown processes receive no signals from either tool.

These distinctions ensure an original FAIL does not itself prohibit evidence
preservation. They do not allow copying while the driver/phase parent is still
active, silently ignoring malformed metadata, mutating sources, overwriting a
partial archive, or pretending a preservation snapshot is full scientific
closure. An existing success or failure inventory/output is exclusive in either
mode; there is no silent retry under the other mode.

Future explicit invocation only, NOT RUN:

```bash
rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a_v50_review_closed_draft_v2.py \
  --freeze 23e909380b470039bd5680cf2d07710dca71097e \
  --output /tmp/mr3_p2a_v50_independent_closed_metadata_v2.json

rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a_v50_collect_closed_draft_v2.py \
  --freeze 23e909380b470039bd5680cf2d07710dca71097e \
  --closed-review /tmp/mr3_p2a_v50_independent_closed_metadata_v2.json \
  --mode closed
```

If actual identity closure is incomplete, root can prospectively select the
explicit `--mode preserve-evidence` instead before the sole archive attempt.
That selection cannot remove original errors or create P2A credit. The full
P2A scientific conjunction remains a separate final metadata review, as
described in the preserved v1 closure plan.
