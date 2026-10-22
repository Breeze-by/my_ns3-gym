# V42 derived-only interpretation of the closed V41 interface failure

This note reads only `/tmp/mr3_p2a_v42_native_diagnosis/extract_v1.json` and
current source. It does not reopen native files, rerun a consumer, change a
physics verdict, or execute a World. Derived JSON SHA256:
`47a4e0cdb3740abfd663e382a550350898aa3232f7593f8ccd08586df8bf2b04`,
3,189,288 bytes. Evidence freeze is
`47224c51c1c525c55093dce26b374d1ccb07eb06`; the later extraction activity
freeze supplied by the owner is `f96b9801957a80b22bf9096df3691173961ef417`.

## Evidence completeness

All nine input streams have full-byte SHA/byte-count and stable-stat receipts.
Task statistics cover all 1,602 logged reach decisions per robot, from release
40.28s through the last returned boundary 72.28s. There are 32 real transitions.
These are descriptive records, not a new physics/safety qualification.

The selected payload is bounded, **not complete in every channel**.
`descriptive_selection_complete=false`; dropped counts are driver_tb2=39,
driver_tb3=218, publisher_raw_odom_tb2=102, publisher_raw_odom_tb3=102.
There are 1,617 retained selections and no extraction errors. In particular,
absence of a selected tb3 driver/independent-publisher row is not absence of
that source event. Received raw-odom/reach/final-Twist windows remain available.

## What stopped tb3

This is not merely an upstream controller that chose rotation without asking
to translate. The complete task-level reach statistics show:

| Field | tb3 |
|---|---:|
| positive-v requests | 1280 |
| positive-v outputs | 0 |
| positive request with final linear veto | 1280 |
| request v=0, w!=0 | 0 |
| final v=0, w!=0 | 379 |
| linear_brake_preserve_requested_turn | 379 |
| reach_transition_envelope | 855 |
| reach_hold | 46 |
| request_unavailable_zero | 238 |
| reach_clear | 82 |
| reach_zero | 2 |

tb3 remains D after the initial HOLD qualification: D=1551, HOLD=50, STOP=1;
there is no accepted X/N transition in these task records. All 379 turn-only
outputs are the explicit reach filter preserving the upstream request's turn,
not a new heading selected by the guard.

At 41.30s (`motion_safety.jsonl` original line 47312), the recorded request is
v=.2, w=.2368421053, publisher identity valid and supported. Output is
[0,.2368421053], reason `linear_brake_preserve_requested_turn`. The rejected
prospective X checks fail for both peers, in both map and raw frames:

| peer | map/raw centre distance, approximately | required | retained longitudinal |
|---|---|---|---|
| tb1 | .63631317 / .63631323 | .7408 | [.144,0] |
| tb2 | .63636757 / .63636763 | .7405 | [.144,0] |

At 45.72s (line 73242), request [.1894736842,0] is instead reduced to [0,0],
reason `reach_transition_envelope`. Thus once Nav2 reduces its own angular
request to zero near its desired heading, the guard has no turn component to
preserve and the robot waits at the blocked D-to-X boundary.

This persists near both native cancels. At 50.28s (line 100779), request
[.1894736842,0] is rejected by tb1: map/raw distance .650529/.636315 versus
.7252 required; tb2's pair passes. At 68.28s (line 202474), request
[.1789473684,0] is rejected by tb1: .692269/.678045 versus .7231; tb2 is now
well separated and passes. These source rows establish the recorded veto;
they do not certify a hypothetical command rejected by the current profile.

## Probe timing and targets

tb3 actually receives the initial target (.900944568,.101948970) at 40.28s
(adapter line 26), from pose approximately (.4514933,0), yaw .0008123.
The second target (4.78327668,.86658724) is sent at 53.28s (line 1569), from
pose approximately (.4515073,.0000186), yaw .1699576. Both are generally east,
away from the two initially western peers. The second target is not a
successful escape from the guard's geometric restriction.

WAIT occurs at elapsed 10s and 28s, with real native cancels at 50.28s and
68.28s (adapter lines 1237 and 3335). The preceding sampled tb3 speeds are
about .0000351 and .0000273m/s, far below the probe's .08m/s moving trigger.
The source rule has a fixed bounded-deadline WAIT at those elapsed times;
the selected input files do not contain the producer's internal reason field.
No native cancel is promoted to a meaningful moving-stop sample merely because
the probe planned and submitted WAIT.

## Why the present geometry is conservative here

`mr3_reach_runtime.reach_for` uses phi=1.2*(source_age+.78), while
`mr3_reach_geometry._one_geometry` discounts an entire robot's longitudinal
.144m only when **every** admitted directional cone is robustly nonclosing.
Otherwise it retains the whole .144m as an isotropic distance contribution.

In the initial geometry the peers are approximately northwest and southwest
of tb3, their bearing separation about pi/2. A direction nonclosing to both
has an available angular interval of about pi/2. A whole cone fits only if
its half-angle is at most about pi/4 (and the positive-U condition is stricter).
Even at source_age=0 the current half-angle is .936rad > pi/4. At the selected
41.30s frame, age about .049s makes phi about .995rad. So making source receipt
same-tick cannot by itself remove this initial binary-discount bottleneck.

The D-to-X reserve before longitudinal retention is
.52 + .0312 + .0156 + .0300 = .5968m for the tb1 pair. Retaining the full .144
raises it to .7408m. A directional sector's actual support toward this peer
can be much smaller than .144 even when it is not everywhere nonclosing.
Using the approximate initial heading/pose as intuition gives support near
.030m and a potential separation test near .627m. **That estimate is not an
implemented/certified acceptance of this native frame**: the exact axis,
normalization, cone bounds and both frames must be checked by a new proof.

This does not prove P2A impossible or the task unlearnable. Peers can change
separation and role; tb2 already moves and becomes distant. It identifies a
specific conservative admission bottleneck for this initial configuration.

## tb1: what same-tick evidence does and does not say

Both tb1 cancellation windows already contain zero final linear output at
every retained 20ms sample from cancel-120ms through cancel itself:
50.16–50.28s and 68.16–68.28s. The matching reach decisions are
`reach_transition_envelope` or `linear_brake_preserve_requested_turn` with
positive incoming v and final v=0. Therefore the two tb1 failures cannot be
explained solely as a post-cancel zero at the same tick being misclassified as
prior output. The retained pre-cancel zero span already covers the original
.10s prior-command criterion.

The adapter has only stamp/epoch/kind/payload, without wall time or record
sequence. Its event cannot be totally ordered against a same-sim-tick motion
callback using an invented timestamp. That uncertainty remains, but it does
not rescue these two moving-cancel samples. Earlier max raw speed .125m/s is
not evidence of active linear output immediately before either cancellation.
tb2 supplies the internal contrast: its corresponding final-output windows
still have positive v at each cancel and `reach_clear`. Original physics FAIL
and both per-event ineligibility findings remain unchanged.

## Executable next direction

Keep the existing reach profile and its historical verdicts intact. First
build a **disabled, explicit CPU mathematical candidate** for the same Reach
sets: bound each sector's support along the fixed reported line of centres,
instead of the binary nonclosing-or-full-longitudinal approximation. Keep
BODY, .02 margin, .3 position-age speed, .5s source limit, 1.2rad/s, .78s,
.144m, 2R/4R and U; require independent map/raw certificates and all existing
causal role/driver/calibration/freshness gates. A proof refinement is a new
admission version, not byte-equivalence and not automatic native permission.

For nominal delta with d=|delta| and n=delta/d, a sufficient separation proof
uses d >= .52 + buffers + U + h_left(n) + h_right(-n). Sector support must
include radius zero, take the maximum over a robot's union of admitted signs,
and sum only across the two robots. Certified rational trigonometric bounds
and strictly directed sqrt bounds can avoid heuristic epsilons. Preserve the
old nonclosing-zero branch and conservatively fall back to full L when the
new bound is unsupported. An extra U term in the support bound is acceptable
if its units/sign are proved and it remains an upper bound.

Required CPU work is a derivation and independent checks of tangent/closing
directions, non-unit axes, multiple signs, both X roles, positive U, zero axis,
near-threshold squared comparisons, and old-PASS-implies-new-PASS. Dense
angular samples are a counterexample search, not the proof of safety. Do not
silently replace the 1.2 bound with measured .206 or configured .3; any smaller
future plant contract requires its own prospective enforcement/evidence.

Only after that candidate and its independent review pass should a new
version's producer/intent/reader/source registrations and finite native entry
be prepared. A probe-only deadline/ranking adjustment would not resolve the
identified execution admission bottleneck. No PPO stage should borrow V41's
incomplete physical qualification.
