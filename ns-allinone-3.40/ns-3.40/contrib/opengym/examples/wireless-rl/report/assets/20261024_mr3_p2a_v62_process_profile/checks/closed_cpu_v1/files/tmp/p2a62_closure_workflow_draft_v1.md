# V62 post-reap metadata / opaque archive workflow

This is preparation only. The reviewer and collector have not been executed by closure_docs. Original activity80831 has root-confirmed real rc1; its immutable FAIL, forced shutdown and partial profiles stay unchanged. No native, scientific audit, raw-log parse or pstats decode is part of this closure.

1. Keep HEAD=origin/main=`81e63f50699073286c9773dcb92106de63fdf4ca` and clean until metadata review closes. Root already recorded real80831 reap in `/tmp/mr3_p2a_v62_root_tool_v1/actual_tool_wait_v1.json`, schema `mr3-v62-root-actual-tool-reap-v1`.
2. Root runs and actually reaps:

   ```sh
   rtk proxy /bin/bash --noprofile --norc /tmp/p2a62_metadata_cpu_v1.sh
   ```

   Output `/tmp/p2a62_closed_metadata_review_v1.json` plus `/tmp/p2a62_metadata_actual_wait_v1/actual_wait.json`. Success is consistency/accounting/fresh saved-identity closure, not a profile/native PASS. It keeps the original shutdown headers (`worker_returncode=-15`, `forced_shutdown=True`, `failed_sample=True`, original remaining-process and zombie arrays) and does not claim normal shutdown. Six pre-exec transport ancestors remain nonowned and are not checked for absence.

3. Only after the real metadata tool reap0, root writes exclusive `/tmp/p2a62_metadata_tool_wait_v1.json`:

   ```json
   {
     "schema": "mr3-v62-closure-cpu-actual-tool-reap-v1",
     "stage": "metadata",
     "session_id": "REPLACE_WITH_ACTUAL_INTEGER_TOOL_SESSION",
     "actual_waited": true,
     "actual_returncode_observed": 0,
     "observed_monotonic_ns": "REPLACE_WITH_ACTUAL_INTEGER_OBSERVATION"
   }
   ```

   The placeholders above are explanatory, not an executable receipt. Failed attempts and original sources/waits stay intact; never overwrite them or fabricate an rc/start tick.

4. Root may then execute and actually reap the opaque collector:

   ```sh
   rtk proxy /bin/bash --noprofile --norc /tmp/p2a62_archive_cpu_v1.sh
   ```

   Only three runtime roots are traversed: `/tmp/mr3_p2a_v62_parent_v1`, `/tmp/mr3_p2a_v62_root_tool_v1`, `/tmp/mr3_p2a_v62_open101_8step_profile_v1`. Every regular original, including partial pstats/raw logs, is gzip-wrapped and restored for full byte-count/SHA comparison by the unchanged V45 helper. Links are lstat/readlink metadata only, never followed. Bounded4 scheduling stops new submissions after observed failure, joins all started writers and retains completed/partial targets. No old500MB inputs,342 mapped libraries or committed preparation CPU directories are copied.

5. Primary output is A62 `closed_inventory_v1.json`, schema `mr3-v62-opaque-closed-inventory-v1`; regular rows are `entries[]` with `original`, `original_bytes`, `original_sha256`, `source_stat_before/after`, `canonical`, `canonical_bytes/SHA`, `decoded_bytes/SHA` and `decoded_bytes_verified`. `original` remains the real input path; outer canonical wrappers are not new original pstats. Membership/stable stats and current1051 sources/12 ELF/Git are checked after all writers join.

6. `oversized_canonical_files` lists any actual >64MiB wrapper. No automatic split, deletion or source-inventory rewrite occurs. Choose an explicit byte-preserving overlay only if the actual closed inventory requires it; lossless byte PASS does not change activityFAIL or by itself assert Git size bounds.

7. Closing CPU sources, actual waits, real tool-reap observations and fresh CPU identities belong to a distinct after-copy supplemental inventory; neither the primary archive nor its immutable membership is backfilled with the collector's own later receipt. Root writes ledger/report/front/index after frozen source writers truly close. Fee remains the actual complete parent180.893159791, entry108886.5066566616018/C150000, resultingU109067.3998164526018/R40932.6001835473982; nested launch/reader and root-tool wall are not added. Closing CPU scope adds engineering0.

The next proposed V63 is a new bounded description of exactly the two available original main.pstats, pinned by V62 `entries[].original_bytes/original_sha256`; its own spec remains pending until this inventory is actually complete. No guard enlargement, V62 retry, new qualification/learning or automatic pilot/final entry is implied. P2A remains incomplete and capacity=False.
