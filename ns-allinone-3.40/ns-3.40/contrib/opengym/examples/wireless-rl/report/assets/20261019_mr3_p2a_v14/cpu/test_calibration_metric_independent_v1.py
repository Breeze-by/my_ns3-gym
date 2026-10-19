"""Independent synthetic metric tests; none proves a native sensor/plant model.

The parent finite CPU runner owns execution and receipts.  In particular, an
accepted result remains conditional on actual coefficient/source calibration,
the declared WORLD component bound and IEEE operation semantics.
"""
from fractions import Fraction as F
import importlib.util
import math
from pathlib import Path
import sys
import unittest


_DIRECTORY = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "mr3_v14_independent_calibration_under_test",
    _DIRECTORY / "calibration_metric_v1.py")
M = importlib.util.module_from_spec(_SPEC)
sys.path.insert(0, str(_DIRECTORY))
try:
    _SPEC.loader.exec_module(M)
finally:
    sys.path.pop(0)

# Independent IEEE binary64 constants, rather than importing the tested ones.
U = F(1, 2**53)
ETA = F(1, 2**1075)
LIMIT = F(1, 100)
WORLD_COMPONENT_BOUND = F(3, 10)


def binary(value):
    return F.from_float(value) if type(value) is float else F(value)


def rounded(value):
    """An exact rational's IEEE binary64 RN result, including subnormals."""
    return F.from_float(float(value))


def independent_conversion(c, s, x, y, fused):
    """One sum with two RN products, or one RN product followed by an FMA.

    Fraction evaluates the exact products/sum before the requested rounding.
    This does not require the host Python to expose math.fma.
    """
    if fused:
        return (rounded(c*x + rounded(s*y)),
                rounded(c*y + rounded(-s*x)))
    return (rounded(rounded(c*x) + rounded(s*y)),
            rounded(rounded(c*y) + rounded(-s*x)))


def actual_residual_squared(c, s, x, y, signs):
    """Exact orthonormal calibrated-axis residual, without a square root."""
    forward, lateral = c*x+s*y, c*y-s*x
    wrong = ((forward < 0 and -1 not in signs)
             or (forward > 0 and 1 not in signs))
    return (lateral*lateral + (forward*forward if wrong else 0)) / (c*c+s*s)


class IndependentCalibrationTests(unittest.TestCase):
    def test_float_coefficients_can_underreport_physical_norm(self):
        # Typical binary32 coefficients near a pi/4 rotation: q is below one.
        c = s = 0.7071067690849304
        q = binary(c)**2 + binary(s)**2
        self.assertLess(q, 1)
        # The old direct-body norm would pass exact .01; physical norm does not.
        body_x, body_y = LIMIT, F(0)
        direct_body_norm_squared = body_x*body_x+body_y*body_y
        self.assertEqual(direct_body_norm_squared, LIMIT*LIMIT)
        self.assertGreater(LIMIT*LIMIT/q, LIMIT*LIMIT)
        certificate = M.residual_certificate(LIMIT, 0, c, s, ())
        self.assertFalse(certificate["accepted"])
        self.assertEqual(F(certificate["coefficient_norm_squared"]), q)

    def test_q_above_one_is_used_instead_of_forced_unit_metric(self):
        c, s = F(1), F(1, 2**20)
        q = c*c+s*s
        self.assertGreater(q, 1)
        certificate = M.residual_certificate(LIMIT, 0, c, s, ())
        self.assertTrue(certificate["accepted"])
        self.assertEqual(F(certificate["coefficient_norm_squared"]), q)
        self.assertLess(F(certificate["residual_norm_squared_upper"]), LIMIT*LIMIT)

    def test_signed_forward_residual_is_not_lateral_only(self):
        self.assertTrue(M.residual_certificate(F(1, 5), F(1, 200), 1, 0, (1,))["accepted"])
        self.assertFalse(M.residual_certificate(-F(1, 5), F(1, 200), 1, 0, (1,))["accepted"])
        self.assertTrue(M.residual_certificate(-F(1, 5), F(1, 200), 1, 0, (-1,))["accepted"])
        self.assertFalse(M.residual_certificate(F(1, 5), F(1, 200), 1, 0, (-1,))["accepted"])

    def test_stop_retains_declared_family_but_hold_uses_full_speed(self):
        # A zero target is not an input which erases the existing signed family.
        # Moving forward can be ordinary braking under old +S, not a rest disk.
        body = (F(1, 5), 0)
        self.assertTrue(M.residual_certificate(*body, 1, 0, (1,))["accepted"])
        self.assertFalse(M.residual_certificate(*body, 1, 0, ())["accepted"])
        self.assertFalse(M.residual_certificate(F(4, 500), F(4, 500), 1, 0, ())["accepted"])
        self.assertTrue(M.residual_certificate(F(3, 500), F(3, 500), 1, 0, ())["accepted"])

    def test_two_sign_family_is_explicit_and_does_not_erase_lateral(self):
        self.assertTrue(M.residual_certificate(F(1, 5), F(1, 200), 1, 0, (-1, 1))["accepted"])
        self.assertTrue(M.residual_certificate(-F(1, 5), F(1, 200), 1, 0, (1, -1))["accepted"])
        self.assertFalse(M.residual_certificate(0, F(11, 1000), 1, 0, (-1, 1))["accepted"])
        # The geometry must separately check every announced direction cone.
        self.assertFalse(M.residual_certificate(0, F(11, 1000), 1, 0, ())["accepted"])

    def test_symbolic_nonfused_error_bound(self):
        for c, s in ((F(1), F(0)), (F(3, 5), F(-4, 5)),
                     (F(1, 2), F(1, 2)), (F(0), F(-1))):
            # Bound two product errors, then the sum's error independently.
            total = WORLD_COMPONENT_BOUND*(abs(c)+abs(s))
            product_error = U*total+2*ETA
            sum_error = U*(total+product_error)+ETA
            derived = product_error+sum_error
            with self.subTest(c=c, s=s):
                self.assertEqual(derived, (2*U+U*U)*total+(3+2*U)*ETA)
                self.assertEqual(M.conversion_error(c, s), derived)
                # One RN product then FMA has no larger worst-case envelope.
                one_product = U*WORLD_COMPONENT_BOUND*abs(s)+ETA
                fused = one_product+U*(total+one_product)+ETA
                self.assertLessEqual(fused, derived)

    def test_subnormal_rounding_needs_absolute_eta(self):
        minimum = F(1, 2**1074)
        self.assertEqual(rounded(minimum/2), 0)  # exact halfway, even zero
        self.assertEqual(abs(rounded(minimum/2)-minimum/2), ETA)
        relative_only = (2*U+U*U)*(minimum/2)
        self.assertLess(relative_only, ETA)
        self.assertGreaterEqual(M.conversion_error(F(1, 2), 0, minimum), ETA)
        # FMA does not make underflow disappear either.
        bx, _ = independent_conversion(F(1, 2), 0, minimum, 0, True)
        self.assertEqual(abs(bx-minimum/2), ETA)

    def test_exact_certified_boundary_has_no_epsilon(self):
        error = M.conversion_error(1, 0)
        by = LIMIT-error
        at = M.residual_certificate(0, by, 1, 0, (-1, 1))
        outside = M.residual_certificate(0, by+ETA, 1, 0, (-1, 1))
        self.assertEqual(F(at["residual_norm_squared_upper"]), LIMIT*LIMIT)
        self.assertTrue(at["accepted"])
        self.assertFalse(outside["accepted"])

    def test_nextafter_cannot_turn_rejected_lateral_into_acceptance(self):
        at = M.residual_certificate(0., .01, 1., 0., (1,))
        farther = M.residual_certificate(0., math.nextafter(.01, math.inf), 1., 0., (1,))
        self.assertFalse(at["accepted"])
        self.assertFalse(farther["accepted"])
        self.assertGreater(F(farther["residual_norm_squared_upper"]),
                           F(at["residual_norm_squared_upper"]))

    def test_independent_rounded_conversion_residual_enclosure(self):
        coefficients = ((1., 0.), (0., -1.), (.6, -.8),
                        (.7071067690849304, .7071067690849304),
                        (1., 2.**-20))
        velocities = ((.3, -.3), (.2, .005), (-.2, .005), (.006, -.006),
                      (1.e-200, -1.e-200),
                      (float.fromhex("0x0.0000000000001p-1022"), 0.))
        for c0, s0 in coefficients:
            c, s = binary(c0), binary(s0)
            error = M.conversion_error(c, s)
            for x0, y0 in velocities:
                x, y = binary(x0), binary(y0)
                self.assertLessEqual(max(abs(x), abs(y)), WORLD_COMPONENT_BOUND)
                for fused in (False, True):
                    bx, by = independent_conversion(c, s, x, y, fused)
                    self.assertLessEqual(abs(bx-(c*x+s*y)), error)
                    self.assertLessEqual(abs(by-(c*y-s*x)), error)
                    for signs in ((), (1,), (-1,), (-1, 1)):
                        with self.subTest(c=c0, s=s0, x=x0, y=y0,
                                          fused=fused, signs=signs):
                            cert = M.residual_certificate(bx, by, c, s, signs)
                            physical = actual_residual_squared(c, s, x, y, signs)
                            self.assertGreaterEqual(F(cert["residual_norm_squared_upper"]), physical)
                            if cert["accepted"]:
                                self.assertLessEqual(physical, LIMIT*LIMIT)

    def test_malformed_coefficients_numeric_values_and_signs_reject(self):
        for bad in (True, False, math.inf, -math.inf, math.nan, "0.0", None, complex(1)):
            for field in ("body_x", "body_y", "c", "s", "world_component_bound", "residual_limit"):
                kwargs = dict(body_x=0, body_y=0, c=1, s=0, admitted_signs=(1,))
                kwargs[field] = bad
                with self.subTest(field=field, bad=repr(bad)), self.assertRaises(ValueError):
                    M.residual_certificate(**kwargs)
        for c, s in ((0, 0), (F(1001, 1000), 0), (0, -F(1001, 1000))):
            with self.subTest(c=c, s=s), self.assertRaises(ValueError):
                M.residual_certificate(0, 0, c, s, ())
        for signs in ([1], {1}, "1", None, (True,), (1.,), (0,), (2,), (1, 1)):
            with self.subTest(signs=repr(signs)), self.assertRaises(ValueError):
                M.residual_certificate(0, 0, 1, 0, signs)
        for field in ("world_component_bound", "residual_limit"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                M.residual_certificate(0, 0, 1, 0, (), **{field: -F(1, 1000)})

    def test_accepted_metric_never_claims_sensor_or_heading_or_native_proof(self):
        certificate = M.residual_certificate(0, 0, 1, 0, ())
        self.assertTrue(certificate["accepted"])
        self.assertTrue(certificate["conditional_calibrated_basis_only"])
        self.assertFalse(certificate["physical_heading_cone_calibration_proved"])
        self.assertFalse(certificate["native_admission"])
        self.assertEqual(F(certificate["declared_world_component_bound"]), WORLD_COMPONENT_BOUND)


if __name__ == "__main__":
    unittest.main()
