# Disabled reported-line support CPU candidate

This is a new mathematical admission candidate, not an equivalent replacement
of v1 and not production/native/plant qualification. There are no evidence-file,
Node, World, policy, transport or command interfaces here. Original v1 sources,
defaults, gates and FAILs stay intact. No test has been executed by the author.

The prototype imports the current pure `mr3_reach_geometry` constants/types and
its certified 42-term rational trigonometric bounds. A future runner must bind
the precise reference source and this new source. The runtime cone constructor
is reproduced only as an artificial-fixture helper, with phi=1.2*(age+.78).

## Sets, signs and separation implication

For one frame let reported relative position be delta = p_right-p_left,
d=|delta|>0 and fixed reported normal n=delta/d. Each original Reach is the
Minkowski sum of its isotropic residual buffer and longitudinal sectors:
S={r*u:0<=r<=L, u in the union of admitted heading cones}. With no directions,
the longitudinal set remains the full L disk; a D set has L=0. Sector radius
zero is included. Different signs/headings are a union: support is their maximum,
not their sum or minimum. The two robots' supports are added.

For every allowed displacement and centre-position uncertainty e with |e|<=U,
the final relative centre's projection on this same fixed n is at least

    d - h_left(n) - h_right(-n) - buffer_left - buffer_right - U.

Therefore requiring this lower bound >= 2*BODY+.02 is a sufficient separation
certificate for all members of those declared sets. It is not a proof of an
actual future displacement, provenance, causal mode, physical-model validity,
or continuous plant response. Both independently reported map and raw frames
must pass, with all original hard gates and calibration flags true.

U=.3*(age_left+age_right) is preserved as a full outer additive reserve. Ages
remain integers in [0,.5s]. BODY=.25, R=.01*.78=.0078, D/N buffer=2R,
X buffer=4R, L=.144, heading rate=1.2 and horizon=.78 are unchanged.

## One cone upper bound

Let nonzero axis a, angle phi and reported delta be exact rational inputs.
For a rotated axis a(t), |t|<=phi, the unnormalized projection is

    dot(a,delta)*cos(t) + cross(a,delta)*sin(t).

When dot<0 and certified cos_lower(phi)>0 (hence phi<pi/2), this is at most

    H = dot*cos_lower(phi) + abs(cross)*sin_upper(phi).

The sign on the cosine coefficient matters: multiplying its lower bound by
negative dot produces an upper bound. The cross contribution is nonnegative.
For dot>=0, a nonacute/unsupported cone, absent directions, or a nonpositive
normalization lower bound, retain full L. No approximate fallback can admit.

To explicitly retain the old robust-direction U assumption as additional
conservatism, this candidate always uses

    N = H + U*axis_norm_upper
    q_upper = clamp(N / (axis_norm_lower*delta_norm_lower), 0, 1)
    h_upper_m = L*q_upper.

If N<=0, use zero directly rather than divide a negative numerator by a lower
bound. H and U*|a| have units metres times the dimensionless axis magnitude;
the denominator has the same units, q is dimensionless and L*q has metres.
The extra directional length is approximately L*U/d, NOT U. The original full
outer U remains, so this is explicitly extra conservatism rather than a hidden
subtraction. With all bounds exact, the added term can only increase support.
Clamping to 1 is safe because unit projection of radius<=L never exceeds L;
clamping at zero accounts for the included origin.

The original `nonclosing(delta,a,phi,U)==True` branch is preserved as exactly
zero support. Its certified inequality already proves the whole sector is
robustly nonclosing; reusing this branch also preserves v1's accepted zeros.
No measured/current command angular speed is substituted for the 1.2 bound.

## Exact square-root enclosure and final comparison

For rational x>=0 and s=2**96, let k=isqrt(floor(x*s*s)). Then
(k/s)^2<=x<((k+1)/s)^2. If (k/s)^2=x, both bounds equal k/s. Otherwise the upper
is (k+1)/s. There is no floating-point epsilon or assumed accurate libm sqrt.
A tiny positive norm whose lower bound is zero falls back to full L.

Each direction ratio uses a positive lower bound for its denominator and an
upper bound in its nonnegative numerator. The displayed upper/lower roots are
not converted to floats and are not reused as admission tolerances.

After forming exact rational upper lengths h_l,h_r, let
B=.52+U+buffers and C=B+h_l+h_r. The final test is exactly

    delta.dot(delta) > 0 and delta.dot(delta) >= C*C.

The equality boundary is retained. A zero reported delta has no separating
normal and is rejected. Source axes are never silently normalized or repaired;
a zero/nonfinite axis or unsupported input is rejected by original validation.

## Relation to old PASS

For any direction old nonclosing True yields the same zero. If all a robot's
directions were nonclosing, its new support is zero, matching old. Otherwise
old retained L and every new support is between zero and L, so the union's
maximum is <=L. No-direction cases retain full L. All buffers/U/body/hard
flags and map/raw conjunction are identical. Thus for nonzero delta, new C<=old
required distance in each frame. Old v1 geometric PASS implies new geometric
PASS. The old zero-delta gate always rejects because the fixed body reserve is
positive; no zero-delta exception creates a counterexample. The converse is
not claimed. This is a proof refinement under the original sets, not physical
gate equivalence or permission to register it implicitly.

## Artificial checks and their evidentiary limits

`test_support_prototype_v1.py` uses only constructed rational/simple numeric
inputs. It checks exact square-root enclosure, old/new implication, old-zero
preservation, closing/tangent/obtuse/absent-direction fallbacks, scaled and zero
axes, sector-origin clipping, union max, right-normal sign, both X reserves,
map/raw disagreement, strict source/hard-gate bounds, exact threshold equality,
and the tiny-norm fallback. A fixed artificial triangle uses axes (1,0), peers
delta=(-.45,+/-.45), unchanged runtime phi and fixed ages; it does not load or
claim acceptance of a native source row.

An independent trigonometric numeric oracle computes the actual cone support
from endpoint/interior angles. Numerical oracle comparisons and fixed random
cases are counterexample searches and implementation checks, not the proof
above. No angular sampling result is promoted to a continuous-set guarantee.
No parameter sweep or per-native-frame fitting is included.

Before any future production use: independent proof/code review and actual CPU
checks must close, a new explicit scientific/profile version must be declared,
all necessary runtime/intent/readers/source registries must agree, and fresh
bounded native qualification must establish the unchanged non-geometric gates.
The original physics FAIL remains a FAIL; no PPO eligibility is granted here.
