# V59 explicit packed overlay supplement — no activity archive has been split

The v1 collector only produces complete canonical wrappers. Splitting is a separate, explicit post-collector operation. This supplement leaves `/tmp/mr3_p2a_v59_review_closed_draft_v1.py`, `/tmp/mr3_p2a_v59_collect_closed_draft_v1.py`, and the original workflow document unchanged.

## Established implementation and inventory shape

The actual V52 implementation is `report/assets/20261023_mr3_p2a_v52_qualification/checks/closure_v2/tools/mr3_p2a_v52_packed_overlay_v2.py`. Its admitted representation is `report/assets/20261023_mr3_p2a_v52_qualification/packed_overlay_v1/manifest.json`. V52 left `closed_inventory_v1.json` unchanged (SHA `63efb61cc7b2abaf723b3824399d203a1a0b288465a367110eabcb5ec565ccf7`): the inventory still records the whole original wrappers and raw byte proofs. The separate overlay maps its 92314505-byte and 214063938-byte wrappers to two and four ordered parts, each at most 67108864 bytes. Local whole wrappers remain present. Exact path-only local Git ignore rules exclude them from Git only after part verification.

The unchanged splitter is `report/assets/20261019_mr3_p2a_v13/closed_continuation/checks/pack_cpu.py`, SHA `4cb98f6e0b4ab06bd5f0faa45bc343ccd644c5f2feeb109ded60595f383150a5`, calling only `split_archive`. It copies opaque packed bytes, computes each part SHA, then rereads parts in order to verify full packed SHA and size against the original wrapper. It neither opens raw scientific originals nor decodes/recompresses gzip.

## Separate V59 candidate

`/tmp/mr3_p2a_v59_packed_overlay_draft_v1.py` is the V52 v2 adaptation for exact B `783aec55353ecb93385ffe305300ab760f9c24fe` and the unchanged V59 collector v1 SHA recorded in the candidate. Eleven artificial byte/Git fixtures actually passed, including exact boundary size, literal ignore escaping, corrupt parts, changed whole wrapper, failed/present collector rejection, path traversal, tracked overlarge rejection, restore overwrite/tamper rejection, and explicit preservation-mode boundaries. Fixture gzip/tar operations were patched to fail, and fixture PID absence checks were mocked. This proves the small CPU tool behavior only; no actual V59 archive/inventory was consumed or split.

## Selection after actual collector completion

First require root's actual tool 53492 reap and the completed metadata review/opaque collector. The overlay additionally requires the collector's real `scope=cpu`, rc0, source-before/after-unchanged actual-wait receipt, exact collector source SHA/argv/freeze, and fresh absence of its two saved coordinator/child identities. Its inventory SHA must be the exact actual completed inventory SHA.

Inspect `closed_inventory_v1.json` entry sizes only after closure. Select exactly entries with `canonical_bytes > 67108864`. If none exist, skip the overlay entirely. Do not infer sizes from live logs or preemptively choose paths. Run the overlay before staging any overlarge whole wrapper; it refuses already tracked selected blobs rather than hiding them.

From wireless-rl, the operation is:

```bash
rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a_v59_packed_overlay_draft_v1.py build --inventory-sha256 "$V59_CLOSED_INVENTORY_SHA256" --collector-actual-wait "$V59_COLLECTOR_ACTUAL_WAIT"
```

For execution, wrap that exact command in the existing `mr3_learning.reach_execution --scope cpu` actual-wait protocol with a new exclusive `/tmp/mr3_p2a_v59_packed_overlay_actual_wait_v1` output. Declare the overlay script, immutable splitter/copier, exact collector script, completed collector wait, and base inventory as sources. Preserve any failed output/receipt; require actual rc0/source unchanged and fresh CPU IDs gone before admitting/staging the overlay. This draft has not run against an actual archive.

## Representation and Git staging

The script writes `packed_overlay_v1/parts/NNNN/closed.tar.gz.partNNNN`, a pending manifest and then a complete manifest. Each mapping preserves exact original raw path/bytes/SHA, original whole wrapper path/bytes/SHA/codec, and every part's index, offset, relative path, bytes and SHA. Concatenation must cover every packed byte in order. Existing immutable base inventory raw decoded-byte proofs remain authoritative; the overlay does not rerun that decode.

The whole original inventory and whole wrapper bytes are retained unchanged. Only after all parts pass does the script write slash-anchored, escaped exact path patterns in `closed_execution/.gitignore`; it verifies that no unrelated original is newly ignored. Part `.gitattributes` sets `-text -whitespace`. No broad basename rule, deletion, truncation, recompression or rewriting of old inventory entries occurs. A failed overlay keeps originals and partial evidence, and cannot publish a final PASS manifest.

Stage base inventory, overlay parts/manifests/attributes, local exact-path ignore file, and all other inventory entries while respecting these ignore rules. Do not force-add the entire archive directory, which would bypass the intentional exclusion of the large whole wrappers. Before commit, inspect staged blob sizes and require every new V59 artifact blob to stay within 67108864 bytes; metadata/part mappings provide the whole-wrapper scientific custody.

Both `closed` and explicitly labelled `preserve-evidence` collector modes can represent bytes, but collector argv mode must equal inventory mode and the saved-identity claim must agree. A preservation-only overlay never grants scientific or owned-identity closure.

## Restore

```bash
rtk proxy /usr/bin/python3 -B /tmp/mr3_p2a_v59_packed_overlay_draft_v1.py restore --manifest "$V59_OVERLAY_MANIFEST" --canonical "$V59_EXACT_CANONICAL_PATH" --output /tmp/mr3_p2a_v59_restored_wrapper_v1.gz
```

Choose the canonical path from the actual manifest. Restore validates safe relative paths, no symlink aliases, consecutive indices/offsets, each part SHA/size, and the full reconstructed packed SHA/size. Output is exclusive; existing files and partial failed reconstructions remain preserved. Restoring packed bytes does not decode the scientific stream or change its old verdict.
