"""Independent WORLD-heading residual oracles, without a physical proof claim."""
from fractions import Fraction as F
import math
import unittest

from multi_robot_exploration import mr3_velocity_metric as m

LIMIT, U, ETA = F(1, 100), F(1, 2**53), F(1, 2**1075)


def binary(value):
    return F.from_float(value) if type(value) is float else F(value)


def rounded(value):
    return F.from_float(float(value))


def measured(c, s, x, y, fused):
    if fused:
        return rounded(c*x+rounded(s*y)), rounded(c*y+rounded(-s*x))
    return rounded(rounded(c*x)+rounded(s*y)), rounded(rounded(c*y)+rounded(-s*x))


def world_residual_squared(x, y, heading, signs):
    hx, hy = heading
    forward, lateral = hx*x+hy*y, -hy*x+hx*y
    wrong = forward < 0 and -1 not in signs or forward > 0 and 1 not in signs
    return (lateral*lateral+(forward*forward if wrong else 0))/(hx*hx+hy*hy)


class VelocityMetricTests(unittest.TestCase):
    def test_physical_heading_cannot_be_guessed_from_conversion_coefficients(self):
        # A 90-degree conversion basis, physical heading +worldX, worldv=(.2,0).
        value = m.physical_residual_certificate(0, -F(1, 5), 0, 1, (1, 0), (1,))
        self.assertTrue(value["metric_necessary"])
        self.assertFalse(m.residual_certificate(0, -F(1, 5), 0, 1, (1,))["metric_necessary"])
        self.assertFalse(m.physical_residual_certificate(0, -F(1, 5), 0, 1, (1, 0), (-1,))["metric_necessary"])
        self.assertFalse(m.physical_residual_certificate(F(1, 50), -F(1, 5), 0, 1, (1, 0), (1,))["metric_necessary"])

    def test_physical_metric_accounts_for_nonunit_coefficients_and_heading_scale(self):
        c = s = .7071067690849304
        q = binary(c)**2+binary(s)**2
        self.assertLess(q, 1)
        self.assertFalse(m.physical_residual_certificate(LIMIT, 0, c, s, (1, 0), ())["metric_necessary"])
        first = m.physical_residual_certificate(F(1, 1000), F(1, 500), F(1, 2), F(1, 2), (3, 4), (1,))
        scaled = m.physical_residual_certificate(F(1, 1000), F(1, 500), F(1, 2), F(1, 2), (30, 40), (1,))
        self.assertEqual(first["residual_norm_squared_upper"], scaled["residual_norm_squared_upper"])
        self.assertEqual(F(first["coefficient_norm_squared"]), F(1, 2))

    def test_independent_world_projection_is_enclosed_after_rounded_conversion(self):
        coefficients = ((1., 0.), (0., -1.), (.7071067690849304, .7071067690849304))
        worlds = ((.2, .005), (-.2, .005), (.006, -.006), (1.e-200, -1.e-200))
        headings = ((F(1), F(0)), (F(0), F(1)), (F(3), F(4)))
        for c0, s0 in coefficients:
            c, s = binary(c0), binary(s0)
            for x0, y0 in worlds:
                x, y = binary(x0), binary(y0)
                for fused in (False, True):
                    bx, by = measured(c, s, x, y, fused)
                    for heading in headings:
                        for signs in ((), (1,), (-1,), (-1, 1)):
                            with self.subTest(c=c0, s=s0, world=(x0, y0), h=heading, signs=signs, fused=fused):
                                cert = m.physical_residual_certificate(bx, by, c, s, heading, signs)
                                actual = world_residual_squared(x, y, heading, signs)
                                self.assertGreaterEqual(F(cert["residual_norm_squared_upper"]), actual)
                                if cert["metric_necessary"]:
                                    self.assertLessEqual(actual, LIMIT*LIMIT)

    def test_symbolic_rounding_error_includes_absolute_subnormal_error(self):
        c, s, v = F(3, 5), -F(4, 5), F(3, 10)
        total = v*(abs(c)+abs(s))
        products = U*total+2*ETA
        independently_derived = products+U*(total+products)+ETA
        self.assertEqual(m.conversion_error(c, s), independently_derived)
        minimum = F(1, 2**1074)
        self.assertEqual(abs(rounded(minimum/2)-minimum/2), ETA)
        self.assertGreaterEqual(m.conversion_error(F(1, 2), 0, minimum), ETA)

    def test_exact_residual_boundary_and_one_subnormal_step_have_no_tolerance(self):
        error = m.conversion_error(1, 0)
        boundary = LIMIT-error
        self.assertTrue(m.physical_residual_certificate(0, boundary, 1, 0, (1, 0), (-1, 1))["metric_necessary"])
        self.assertFalse(m.physical_residual_certificate(0, boundary+ETA, 1, 0, (1, 0), (-1, 1))["metric_necessary"])
        self.assertFalse(m.physical_residual_certificate(0, math.nextafter(.01, math.inf), 1, 0, (1, 0), (1,))["metric_necessary"])

    def test_stop_keeps_signed_family_and_never_drops_unadmitted_or_lateral_velocity(self):
        self.assertTrue(m.physical_residual_certificate(F(1, 5), F(1, 200), 1, 0, (1, 0), (1,))["metric_necessary"])
        self.assertFalse(m.physical_residual_certificate(F(1, 5), F(1, 200), 1, 0, (1, 0), ())["metric_necessary"])
        self.assertFalse(m.physical_residual_certificate(-F(1, 5), 0, 1, 0, (1, 0), (1,))["metric_necessary"])
        self.assertFalse(m.physical_residual_certificate(0, F(11, 1000), 1, 0, (1, 0), (-1, 1))["metric_necessary"])

    def test_bad_scalars_unknown_axis_and_boolean_signs_fail_closed(self):
        for bad in (True, False, "0", math.inf, math.nan):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                m.physical_residual_certificate(bad, 0, 1, 0, (1, 0), (1,))
        for c, s, axis, signs in ((0, 0, (1, 0), (1,)), (1.01, 0, (1, 0), (1,)),
                                   (1, 0, (0, 0), (1,)), (1, 0, (True, 0), (1,)),
                                   (1, 0, (1, 0), (True,)), (1, 0, (1, 0), [1]),
                                   (1, 0, (1, 0), (1, 1))):
            with self.subTest(c=c, s=s, axis=axis, signs=signs), self.assertRaises(ValueError):
                m.physical_residual_certificate(0, 0, c, s, axis, signs)

    def test_metric_result_names_conditions_and_cannot_supply_execution_permission(self):
        value = m.physical_residual_certificate(0, 0, 1, 0, (1, 0), ())
        self.assertTrue(value["metric_necessary"])
        self.assertTrue(value["conditional_on_heading_and_world_component_bound"])
        self.assertFalse(value["physical_heading_calibration_proved"])
        self.assertNotIn("accepted", value)
        self.assertNotIn("native_admission", value)


if __name__ == "__main__":
    unittest.main()
