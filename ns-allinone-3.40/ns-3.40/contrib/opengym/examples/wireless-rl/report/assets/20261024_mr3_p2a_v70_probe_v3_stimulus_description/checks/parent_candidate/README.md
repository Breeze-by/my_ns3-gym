# V70 fixed two-input descriptor parent — fixed source candidate

Only `run_description_v1.py` is the canonical parent/entry candidate. The consumer, spec and tests are owned by encoder_native. Namespace is fixed at `20261024_mr3_p2a_v70_probe_v3_stimulus_description`; the parent uses `/tmp/mr3_p2a_v70_parent_v1`, and the one consumer output is `/tmp/mr3_p2a_v70_probe_v3_stimulus_description_v1.json`.

Reuse is the actual A68 same-PID bootstrap→exec→one consumer→real wait→post-source architecture, with no imported old activity main or budget. Complete parent has a 120-second soft fee gate; consumer work is 60 seconds. No timeout/cleanup or hard real-time guarantee is invented. Actual elapsed fee includes source work, gaps and the consumer wait once; nested duration is not added. The end timestamp is after post-source and before summary serialization, as stated precisely in the receipt.

Before input consumption, the parent requires an exact 40-hex pushed clean HEAD/origin, admitted frozen spec, original V69 FAIL identity/ledger, and source/spec/closed-metadata current bytes equal to Git. The fixed source set is 8 declared consumer/interpretation files + spec + this parent + V69 inventory + V69 closure ledger + A69/checks/v70_fixed_inputs_v1.json. Both original inputs are explicitly excluded from parent source hashing. The consumer alone opens its data originals, at the new declared scope. Already-read benchmark metadata and opaque archive hashing are disclosed; this is not a claim that either file has never had its bytes read.

Actual V69 ledger is now bound at 7546 bytes / SHA256 `66611664460ee339d9d1a7a54be32b1b64b8a45ee428681ce2418140683bf278`; the stopped consumer is 40491 bytes / SHA256 `4c9abc261949b56dbc3bd8618c0b3db7716d66500b0e689a8d4dfef37e9df838`. The spec remains admitted=False in the producer draft until Root installs and seals the exact final configuration. Known accounting is U=111360.1553685346018, C=180000, remaining=68639.8446314653982. C is an agent decision under continuous delegation, not a numeric user approval. Pilot/final balances remain unchanged. Original V69/V67/V2 failures remain failures; a successful description grants no native, physical, qualification, capacity, learning or P2A credit.

Prospective canonical launch from W only:

`/usr/bin/python3 -B -m report.assets.20261024_mr3_p2a_v70_probe_v3_stimulus_description.run_description_v1 --freeze <exact-pushed-40hex>`

The entry records its real identity and bootstrap start before same-PID exec. Root must separately observe the actual tool wait and saved parent disappearance. The child saves its actual identity; output identity must match the genuinely waited child. Missing/mismatched bootstrap identity leaves complete fee and cumulative accounting unknown rather than inventing a start. Child submission is exclusive; old outputs are never overwritten and no automatic retry is present.

Static review only: AST parsed; no parent, consumer, fixture, native, reader, raw input, profile or library execution/read occurred. Root and Native may inspect the small delta; no canonical files changed.

Interface adaptation is explicit: fixed schema and argv are parent constants; budget uses the actual `entry_cumulative_seconds` field; original summary False is received as the exact presence object `{present: true, value: false}`. A successful receipt also requires `raw_input_bytes_read_known` to be true. No optional prospective CLI or absent output.schema is assumed.
