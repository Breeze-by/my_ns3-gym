# V13 minimum: independent measurement-contract review

This is a read-only review of the closed episode at runtime freeze
`0063aa233ba3008ddcc1eb09ea8068112eea3965`, not a new science consumer or
simulator experiment. No repository, source, threshold, policy, or original
failure was changed.

The first failure is `motion_safety.jsonl` line/sequence 107887, callback
simulation clock 56.98: tb3, `active settled turn total drift budget exceeded`.
The immediately preceding own-odometry row 107886 has real source time 56.995;
the odometry callback can arrive before the matching `/clock` callback, as the
existing tracker explicitly documents. The causal state selected by a decision
at clock 56.98 can therefore still be source 56.975. These are distinct records,
not evidence of an invented or substituted clock.

From activation anchor source 45.275 through violating source 56.995, all 587
raw received odometry payloads equal their corresponding native publications.
Their XY pose chords sum to **0.007800136333791129 m**, exactly the recorded
tracker accumulator, over 11.72 seconds. The bound is 0.0078 m. Net endpoint
displacement is only 0.0008845287405065454 m; replacing total travel with net
displacement would change the original safety contract. Maximum sampled chord
speed is 0.000933653016870293 m/s and maximum raw planar twist norm is
0.0009291055640853354 m/s, both below 0.01 m/s. The trapezoidal integral of raw
planar speed is 0.007849770639666924 m, consistent in scale with the accumulated
pose travel. This is an accumulation failure, not the V12 instantaneous peak.

The measurement path does not support these proposed explanations:

- Vertical velocity is not included. `SettledTurnTracker.observe` uses
  `hypot(linear.x, linear.y)`; z is only checked for finiteness. The native
  WORLD producer writes XY and angular z, and all 587 linear-z fields are zero.
- SLAM or map-to-odom jumps do not enter this accumulator. It uses the original
  own-odometry pose XY in one unchanged odom frame.
- The producer does not mistake a bare center-of-gravity velocity for the
  footprint-origin velocity. Gazebo 11.10.2 `Model::WorldLinearVel` delegates
  to its canonical link; `Link::WorldLinearVel()` requests offset zero; the ODE
  overload subtracts that link's inertial CoG before `dBodyGetRelPointVel`.
  The spawned direct SDF's first link is `base_footprint` with zero relative
  pose, and the zero-pose base joint connects `base_link`. Model and canonical
  footprint origin therefore coincide under this contract. The explicit
  `base_link` inertial offset (-0.064, 0, 0.048) does not prove a CoG mix-up.
- The float yaw projection rotates world XY only. Its maximum norm scale error
  on these samples is 3.750289923054595e-8, and that projection does not affect
  the pose chord accumulator at all.

All 345 native actuator updates in the interval request zero center linear
velocity, and every applied rim-pair mean is zero. Actual measured wheel-joint
rim-pair means range from -0.00041299477518391 to 0.00042678461277977087 m/s.
Joint targets do not establish zero body-center travel in a constrained rigid
body with wheel/ground/caster interactions. The evidence shows non-ideal small
ongoing motion under nominal zero translation. It does not identify a specific
ODE solver defect, collision event, contact impulse, friction error, or inertial
parameter as the cause. This normal training episode has no independent full
link-origin/CoG/3D velocity/contact-impulse observer stream to establish one.

The original invariant promises both instantaneous rest speed and a fixed
whole-uninterrupted-zero-line-segment travel budget. Arbitrarily long turning
with nonzero drift can satisfy the first and violate the second. Lower angular
deployment speed alone does not establish the second. A defensible next change
must establish an explicit physical finite-turn/stop contract or actuator
response using local measurements, then prospectively freeze and revalidate
all affected math/native gates. Resetting the same uninterrupted accumulator,
using net displacement, dropping small chords, filtering peaks, or loosening
the threshold would hide this counterexample and is not a repair.

Reproduction uses only the standard library and libm:

```sh
rtk proxy env -u PYTHONPATH PYTHONNOUSERSITE=1 PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 -B /tmp/mr3_p2a_v13_minimum_measurement_contract_review_v1.py
```

The actual executed command has already completed, return code 0, child wait
5.654110385 seconds. Its initial result, script, console and actual-wait receipt
remain alongside this note. The JSON contains exact source and raw-data SHA256
values, the existing official-source snapshot URLs and verified SHA256 values,
all 587 source-pinned samples, and all 345 actuator updates.

Result JSON SHA256:
`11dbbac3c9fd1d3c72eb842f63a38926bf6fb1eb152c25d45451f67b0d81a1e5`.

Script SHA256:
`24e53ae302feb018654d99097dea1497697e49d4f5aa9819496dec0f071bfa5a`.
