"""Exact geometric counterexamples, independent of a native plant claim."""
from dataclasses import FrozenInstanceError
from fractions import Fraction as F
import math
import unittest

from multi_robot_exploration import mr3_reach_geometry as g

R, BODY, MARGIN, DISTANCE = F(39, 5000), F(1, 4), F(1, 50), F(18, 125)


def direction(mapped, raw=None, angle=0):
    return g.Direction(mapped, mapped if raw is None else raw, angle)


def pair(mapped, raw=None, left=None, right=None, ages=(0, 0), **flags):
    options = dict(legacy_hard_gates_passed=True, common_world_odom_calibrated=True)
    options.update(flags)
    return g.pair_certificate(mapped, mapped if raw is None else raw, ages,
                              g.disk() if left is None else left,
                              g.disk() if right is None else right, **options)


class ReachGeometryTests(unittest.TestCase):
    def test_complete_disk_diameter_and_both_terminal_reserves_are_indispensable(self):
        self.assertEqual(abs(R-(-R)), 2*R)
        self.assertEqual((g.disk().buffer_m, g.normal().buffer_m, g.transition().buffer_m), (2*R, 2*R, 4*R))
        boundary = 2*BODY+MARGIN+4*R
        self.assertTrue(pair((boundary, 0))["geometric_necessary"])
        self.assertFalse(pair((boundary-F(1, 10**12), 0))["geometric_necessary"])
        for kind, buffer, longitudinal in (("disk", R, 0), ("normal", R, DISTANCE), ("transition", 2*R, DISTANCE)):
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                g.Reach(kind, buffer, longitudinal)

    def test_publication_cannot_replace_transition_with_smaller_normal(self):
        away = direction((-1, 0))
        distance = 2*BODY+MARGIN+5*R
        self.assertTrue(pair((distance, 0), left=g.normal([away]))["geometric_necessary"])
        self.assertFalse(pair((distance, 0), left=g.transition([away]))["geometric_necessary"])

    def test_opposite_raw_bearing_and_raw_heading_cannot_borrow_map_discount(self):
        result = pair((-F(3, 5), 0), (F(3, 5), 0), left=g.normal([direction((1, 0))]))
        self.assertTrue(result["map"]["necessary_condition_met"])
        self.assertFalse(result["raw"]["necessary_condition_met"])
        self.assertFalse(result["geometric_necessary"])
        result = pair((F(3, 5), 0), left=g.normal([direction((-1, 0), (1, 0))]))
        self.assertFalse(result["geometric_necessary"])
        self.assertEqual(result["map"]["retained_longitudinal_m"][0], "0")
        self.assertEqual(F(result["raw"]["retained_longitudinal_m"][0]), DISTANCE)

    def test_union_of_signs_and_unknown_cone_keep_whole_longitudinal(self):
        away, toward = direction((-1, 0)), direction((1, 0))
        self.assertTrue(pair((F(3, 5), 0), left=g.normal([away]))["geometric_necessary"])
        for reach in (g.normal([away, toward]), g.normal(), g.normal([direction((-1, 0), angle=2)])):
            result = pair((F(3, 5), 0), left=reach)
            self.assertFalse(result["geometric_necessary"])
            self.assertEqual(F(result["raw"]["retained_longitudinal_m"][0]), DISTANCE)

    def test_exact_boundary_nextafter_and_stale_or_future_age_have_no_epsilon(self):
        boundary = 2*BODY+MARGIN+4*R
        below, above = (math.nextafter(float(boundary), value) for value in (-math.inf, math.inf))
        self.assertFalse(pair((below, 0))["geometric_necessary"])
        self.assertTrue(pair((above, 0))["geometric_necessary"])
        self.assertTrue(pair((2, 0), ages=(500_000_000, 500_000_000))["geometric_necessary"])
        for ages in ((-1, 0), (0, 500_000_001), (True, 0), (0., 0)):
            with self.subTest(ages=ages), self.assertRaises(ValueError):
                pair((2, 0), ages=ages)

    def test_conditional_translation_exists_at_original_three_robot_spacing(self):
        reach = g.normal([direction((1, 0), angle=F(1, 10))])
        for dy in (-F(9, 20), F(9, 20)):
            result = pair((-F(9, 20), dy), left=reach, ages=(50_000_000, 50_000_000))
            self.assertTrue(result["geometric_necessary"])
            self.assertTrue(result["conditional_on_declared_reach_sets"])
            self.assertNotIn("native_admission", result)
            self.assertNotIn("accepted", result)

    def test_exact_tangent_and_axis_scaling_do_not_hide_position_uncertainty(self):
        self.assertTrue(g.nonclosing((1, 0), (0, 1), 0, 0))
        self.assertFalse(g.nonclosing((1, 0), (0, 1), 0, F(1, 10**12)))
        self.assertTrue(g.nonclosing((-1, 0), (1, 0), 0, 1))
        self.assertFalse(g.nonclosing((-1, 0), (1, 0), 0, math.nextafter(1., math.inf)))
        self.assertEqual(g.nonclosing((-2, 1), (1, 0), F(1, 10), F(1, 10)),
                         g.nonclosing((-2, 1), (1000, 0), F(1, 10), F(1, 10)))

    def test_full_residual_includes_unadmitted_reverse_and_lateral_speed(self):
        self.assertTrue(g.residual_within_bound(F(1, 5), F(1, 200), (1,)))
        self.assertFalse(g.residual_within_bound(-F(1, 5), 0, (1,)))
        self.assertFalse(g.residual_within_bound(F(1, 5), F(11, 1000), (1,)))
        self.assertFalse(g.residual_within_bound(F(1, 5), 0, ()))

    def test_mutable_declaration_aliases_and_truthy_flags_do_not_enter_certificate(self):
        mapped = [-1, 0]; declared = direction(mapped)
        reach = g.normal([declared]); mapped[0] = 1
        self.assertEqual(reach.directions[0].map_axis, (-1, 0))
        with self.assertRaises(FrozenInstanceError):
            declared.half_angle = 1
        for flags in ({"legacy_hard_gates_passed": 1}, {"common_world_odom_calibrated": "yes"}):
            with self.assertRaises(ValueError):
                pair((10, 0), **flags)
        for key in ("legacy_hard_gates_passed", "common_world_odom_calibrated"):
            self.assertFalse(pair((10, 0), **{key: False})["geometric_necessary"])
        for bad in (True, math.nan, math.inf, "1"):
            with self.assertRaises(ValueError):
                g.exact(bad)


if __name__ == "__main__":
    unittest.main()
