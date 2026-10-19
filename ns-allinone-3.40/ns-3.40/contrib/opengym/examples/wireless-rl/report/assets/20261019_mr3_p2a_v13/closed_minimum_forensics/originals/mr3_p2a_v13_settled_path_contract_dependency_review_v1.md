# Fixed whole-segment drift contract: static dependency review

The original .0078m condition is explicit for the entire active zero-linear segment, including angular stops/reversals and later parking tail until actual nonzero-linear storage/end. It is .01m/s×.78s numerically, but is not inferred from the separate finite .78s/.144m braking theorem. Runtime and immutable independent settled_v3 both accumulate raw XY chords and forbid repeated-grant resets; an existing regression rejects a return toward the anchor even when net displacement is small.

Candidate clearance/arrival geometry (.29/.39/.78m), received peer radius .25+.04+.26(age+.55), and .50m overlap gate do not manage this budget. The launch wires the final guard and received-only peer costmap; no existing centre-hold controller is selected.

No present parameter switch supplies the missing guarantee. Shim CLOSED_LOOP is angular-only feedback and was already enabled. Smoother CLOSED_LOOP merely substitutes odometry for the slew origin; command0 with small measured residual still produces0. Existing driver already uses wheel feedback: all345 active pre-crossing wheel updates had alpha1 and symmetric issued targets. Body residual cannot be eliminated by changing the paired limiter when it is inactive.

A possible future engineering candidate is a separately audited local body-velocity regulator with wheel feedback, saturation and integrator control, using existing own local measured odometry. It must preserve requested Nav2 motion, per-wheel slew, true source/clock causality, stopping envelopes and every original gate. It has no validated implementation here; bounded tracking/pose error alone cannot prove whole-segment total variation, and differential drive has no lateral control input. A regulator that injects nonzero linear requests solely to restart the certificate is not an acceptable repair.

A rolling .0078 interpretation, relaxed thresholds, net displacement, data filtering, changed measured reference, physical idealization or changed model friction/torque is a separate scientific contract change requiring explicit approval. Any actual new-control implementation needs new source/ELF identity, prospective physical evidence, full same-freeze preparation and a fresh minimum under a newly allocated execution plan. This review performs no native run or formal consumer and supplies no safety/95% credit.

Exact source SHA, line excerpts, finite/active distinctions and proof obligations: `mr3_p2a_v13_settled_path_contract_dependency_review_v1.json`.
