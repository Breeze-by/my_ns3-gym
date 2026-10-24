# V72 fixed two-input received-description parent — pending

Canonical namespace is locked to `report/assets/20261024_mr3_p2a_v72_masked_stimulus_description`. This private parent forwards the actual A70 `run_description_v1.py` architecture. It does not run the old parent or consumer, and adds no generic command or scheduling interface.

The fixed future entry is:

```
cd /home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl
/usr/bin/python3 -B -m report.assets.20261024_mr3_p2a_v72_masked_stimulus_description.run_description_v1 --freeze EXACT_NEW_PUSHED_GIT_SHA
```

The entry creates exclusive `/tmp/mr3_p2a_v72_parent_v1`, saves its actual PID/start and first module-entry monotonic time, then execs the same fixed module with `--execute`. Consumer CLI is fixed to `describe_probe_v1 --freeze G --spec A72/description_spec_v1.json --output /tmp/mr3_p2a_v72_masked_stimulus_description_v1.json`. The admitted spec and all runtime source/metadata bytes must exist in the exact clean pushed Git freeze. Pending ledger and consumer constants are explicitly rejected before reading a source spec, and the consumer spec remains `admitted:false` until Root fills actual facts.

Continuous parent reservation is 120 seconds, including actual source precheck, recovery snapshots, the actual consumer wait, gaps and complete source postcheck. Consumer work remains 60 seconds, output remains at most 4MiB, both original inputs together remain subject to the consumer's fixed 4.25MiB cap. These are cooperative limits with a real final fee gate, not a hard real-time guarantee. Main and consumer actual waits are not added to the containing parent fee. Parent failure keeps actual returncode, partial description, unknown byte-count distinction and unknown cumulative accounting where entry proof is missing.

The original successful descriptor's activity is distinct from the failed source activity: V71 Root 65935 actually reaped rc1, source before/after 1123 equal, complete engineering fee 1215.240541991 seconds. V72 can only describe received state. It cannot rejudge that failure, claim physics/cancel/qualification/capacity, or enter policy. The actual A71 closure ledger is now materialized at /tmp/p2a71_closed_copyready_v2/closure_ledger_v1.json, 12092B / `de6b54d5e86b859b67414c3246d286284bd721efd5adda91c86fc75f9706e22b`, and will be installed unchanged at A71/closure_ledger_v1.json. Entry is `112581.2023765236018 / 180000`, remaining `67418.7976234763982`, with no pilot/final added cost.

Root supplied opaque archive pins only. The two exact retained regular original paths are the A71 interface benchmark summary and worker0/episode001_open_101/transitions.jsonl. Summary: 115580B / `a79168c823b823d7369611ff77c0da2041b7136d6f179f2b2b0d7af6d7007558`; transitions: 2355730B / `ed389323b631ccad29ebfce83edf18f1079b1919ae4f33b1597d73cf08ce7172`; total 2471310B. Archive inventory is 799822B / `2cdf667a9362544880502d85cbc99d1e478dd4a8d737c701065be3f5bc7694ab`, prospectively installed unchanged at A71/closed_inventory_v1.json. These pins came from `/tmp/p2a71_v72_fixed_input_pins_v1.json`, not by opening either original here.

The summary was already read by Root for closing metadata; transitions have undergone opaque byte copying/hash and stat observation but no semantic parse. Do not call this activity a first byte read. This parent reads neither data original; only the future consumer may perform the one new, scoped semantic consumption.

The actual source union remains 13: Native's exact consumer plus seven interpretation sources, then spec, parent itself, A71 inventory, ledger and fixed input references. The parent saves every one of these source blobs and verifies current bytes against Git before and after actual consumer execution. Data originals are explicitly excluded from this union. `parent_scope_draft_v1.json` is a documentation template only, not a new runtime admission layer; actual admission stays in Native's spec. All observed earlier ancestors are nonowned; no ancestor absence or killing is claimed. Actual parent and consumer saved identities require later Root real reap and fresh absence evidence.

Before any real consumption: receive actual ledger bytes/SHA, Native's final source manifest and artificial CPU proof; fill only those prospective pins, finish exact inverse/source evidence, install canonical files, run the final canonical CPU as required, stage every bound regular file, commit/push, verify clean HEAD==origin==G and exact bound blobs, then invoke the one fixed entry. No PPO/World/native or scientific-reader activity is part of this preparation.
