# Disabled independent-reader CPU candidate

No candidate, test or harness has been executed while preparing these files.
The byte copy `reader_baseline_v1.py` is the actual canonical reader source,
SHA256 `555327657319000a313acba44fc35d548743ab04f0689d9ea1aa3b8c2e3864ed`.
The candidate imports only `fractions`, `functools` and `math`; it never imports
the production geometry/support code or another agent's numeric implementation.

Only two kernels change. Public `sqrt_interval` performs the original `_q` and
negative check before consulting an LRU256 keyed by canonical Fraction. Cached
results are immutable two-Fraction tuples; precision remains 96 bits. The
existing public trig LRU256 is retained, including its old direct-input alias
behavior. The actual directional caller validates angle with `_q` first. Any
future public-entry correction must be separately versioned, declared and
validated, rather than smuggled into an equivalence optimization.

For `x=p/q`, the candidate evaluates the exact old 43-term degree84 cosine and
degree85 sine polynomials over `85! q^85` and `86! q^86`. Homogeneous Horner with
`z=p²,w=q²` computes `sum(c[k] z^k w^(42-k))` using integer coefficients
`(-1)^k 85!/(2k)!` and `(-1)^k 86!/(2k+1)!`. The returned numerators are
`cos_poly*q-p^85` and `sin_poly*p*q+p^86`. These are algebraically the old
Lagrange bounds, with no coefficient, degree, remainder or angle-domain change.

`_q`, `_point` and `direction_support_upper` must have complete matching ASTs
against the frozen byte baseline. Whole Fraction values, exception types and
messages, canonical JSON, root enclosures, cold/warm aliases, cache eviction,
immutability, deterministic random vectors and artificial raw/map pair
compositions are compared. Pair compositions exercise base/U/2R/4R, left/right
normal signs, sign-union maximum and raw/map conjunction; they are not a
substitute for the existing complete source/intent/calibration/auditor tests.
No existing caller or gate file is modified.

Root may run exactly one source-sealed artificial CPU harness after review:

```
/usr/bin/python3 -B /tmp/mr3_p2a_v47_reader_cpu_candidate/harness_cli.py --output NEW_RESULT.json --profile-dir NEW_PROFILE_DIRECTORY
```

The harness runs nine unittest methods, then four fixed scenarios for each
model: 64 distinct cold trig inputs, 64 distinct cold norms, 256 warm norm
calls, and two passes over the fixed 76 directional inputs (152 calls).
Each scenario gets a separate unprofiled timing and cProfile execution, with
identical setup and exact numeric SHA comparison. These are local artificial
CPU measurements, not activity fees, native throughput, task quality or
qualification. There is no adaptive benchmark or timing-based candidate choice.

The optional separate role `--export-numeric-inputs NEW.json` writes only the
fixed directional inputs as exact numerator/denominator pairs. Agents may
share these inputs for coverage but must not import each other's math.
