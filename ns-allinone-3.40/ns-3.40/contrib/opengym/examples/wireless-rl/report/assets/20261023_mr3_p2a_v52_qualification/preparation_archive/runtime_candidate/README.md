# Disabled V52 runtime CPU candidate v1

This is only a /tmp candidate. No repository source changed; no candidate,
reader, test or raw native input has been executed by the author. The baseline
and retained artificial fixture bytes were checked against Git
23e909380b470039bd5680cf2d07710dca71097e. Root must seal and actually wait the
artificial CPU checks before considering a new canonical freeze.

Exactly three changes:

1. After the existing complete declaration validation, map each target sequence
   to the final declaration in original iteration order. This equals the old
   full related[-1] scan, including duplicates and future declarations. No new
   causal filtering or sorted ordering is introduced.
2. At the original ACK phase gate, lazily index only the component that is
   actually requested. Store all rows for each builtin-string request ID in
   original order. Non-string query IDs or any non-string ID within that
   component use the original equality scan. Thus list/dict IDs, bool/int
   equality, duplicates and malformed/unused components retain old behavior.
   Indices belong to one owned immutable parsed input within one replay call;
   they are not object-id caches and are never shared across roles or calls.
3. JSON object_pairs_hook receives a completed list of builtin-string keys.
   dict(items) preserves all unique entries and their insertion order; a length
   difference exactly detects duplicate keys. The same generic ValueError is
   raised at the same object hook, after already-parsed nested values. Public
   canonical(), every canonical parse check, nonfinite parse_constant hook,
   complete raw/decoded SHA, tail check and all arithmetic remain unchanged.

The second possible shallow-tree/canonical-validation optimization is NOT
implemented here: overflow, recursion and duplicate first-error priority need a
separate proof and fixtures before any removal of complete canonical checks.

Ten test method definitions are prepared, not ten executed passes. They compare
complete public JSON+SHA or exact exception type/args on frozen artificial
HOLD/support-mode records, duplicate/missing/reversed ACKs, lazy malformed and
earlier-error cases, non-string IDs, actual last-declaration expression,
original stop-deadline/terminal failures, gzip/plain strict JSON and input
proofs, mutation between fresh calls, and AST equality of unchanged math/public
canonical functions. One unique fixture import statement is removed to inject
the retained baseline reader; the fixture factories are otherwise unchanged.
Private package loading changes neither sys.path nor PYTHONPATH.

Shortest proposed actual CPU command, NOT RUN:

    /usr/bin/python3 -B -m unittest discover -s /tmp/mr3_p2a_v52_runtime_cpu_candidate_v1 -p test_runtime_candidate_v1.py -v

No native throughput or speedup is claimed. The derived V51 cProfile guided the
choice only: declaration scan 51.28s self, ACK scan 33.71s cumulative, JSON unique
51.62s self, complete original function 406.84s under profiling. Those are
nested timings, cannot be added as independent fees and do not predict native
ENV speed. A failed artificial check must be retained, not silently overwritten.
