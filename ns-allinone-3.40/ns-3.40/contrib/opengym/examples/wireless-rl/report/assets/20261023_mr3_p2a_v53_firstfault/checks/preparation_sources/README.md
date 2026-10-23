# Disabled V53 two-input FIRSTFAULT candidate

No checkout changes and no original raw bytes consumed. Do not invoke the
extractor with real inputs before root's new source seal/scope and review.

- `firstfault_extract_v1.py`: pure stdlib descriptive consumer. Fixed V52
  deadline epoch, motion + startup inputs, 244.48..244.62 callback-time window.
  It records exact first per-kind payloads in physical file order; the production
  `normal_control_model_invalid`/`reach_model_failure` payload contains robot,
  reason and actual source/commit clock. It does not run Reach mathematics.
- `preregister_spec_v1.json`: deliberately admitted=false and pending raw SHA/
  canonical inventory SHA. Fill only from the immutable A52 closed_inventory_v1
  original/original_sha256/original_bytes rows; do not derive a new input set.
  The 7 logger/interpreter source pins already equal current bytes and Git1fa.
- New execution freeze is a required CLI argument, not embedded self-referential
  Git SHA in the tracked spec. The new consumer is checked against its own new
  Git/source seal; it is never claimed to belong to the old evidence freeze.
- No partial parse can return PASS or say an absent fault was NOT_RECORDED.
  Relevant malformed selected fields reject. Full file SHA and stat remain
  required; partial time/line/byte failures retain a failed prefix description.
- Error list is capped24 per input; counters cap128 distinct kinds; selection
  uses fixed finite kind/robot/feed buckets, not arbitrary row IDs. Max256
  selected records and2MiB output; overflow returns explicit FAIL.
- The root-owned engineering wrapper must bind this source/spec/inventory and
  perform real owned-child wait/closure. Work cutoff240s is cooperative; the
  full parent engineering fee cap300s and tail are prospective reservations,
  not invented consumed fees or proof of OS hard realtime.

Formal interface after installation/sealing:

    /usr/bin/python3 -B A53/firstfault_extract_v1.py --spec A53/spec_v1.json --freeze EXACT_NEW40 --output EXCLUSIVE_NEW.json

Artificial CPU only was actually executed through reach_execution --scope cpu.
Receipt `/tmp/mr3_p2a_v53_firstfault_cpu_v1/actual_wait.json` records the exact
argv and seven source_before/source_after bindings. Result14testsPASS/rc0,
actual child wait0.227115563s. `freshgone_v1.json` separately verifies both saved
CPU identities gone. Tests use BytesIO and never call main/provenance or open
any native path. No actual diagnostic/qualification credit is claimed.
