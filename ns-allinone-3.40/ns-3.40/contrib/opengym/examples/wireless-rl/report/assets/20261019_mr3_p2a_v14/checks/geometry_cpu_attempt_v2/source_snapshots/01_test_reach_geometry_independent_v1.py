"""Independent adversarial tests for *conditional geometry*, not plant validity.

All fixtures are exact synthetic reach-set hypotheses. A geometric `accepted`
result never supplies a live mode, continuous model, actor eligibility, or
native execution permission. Root runs this file with a finite CPU runner.
"""
import importlib.util
from dataclasses import FrozenInstanceError
from fractions import Fraction as F
import math
from pathlib import Path
import sys
import unittest


_SPEC = importlib.util.spec_from_file_location(
    "mr3_v14_independent_geometry_under_test",
    Path(__file__).with_name("reach_geometry_v1.py"))
G = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = G
_SPEC.loader.exec_module(G)

# Independent exact contract values, not copied from runtime implementation.
R = F(39, 5000)
BODY = F(1, 4)
MARGIN = F(1, 50)
LONGITUDINAL = F(18, 125)


def direction(map_axis, raw_axis=None, angle=F(0)):
    return G.Direction(map_axis, map_axis if raw_axis is None else raw_axis, angle)


def pair(mapped, raw=None, left=None, right=None, ages=(0, 0), **flags):
    declarations = {"legacy_hard_gates_passed": True,
                    "common_world_odom_calibrated": True}
    declarations.update(flags)
    return G.pair_certificate(
        mapped, mapped if raw is None else raw, ages,
        G.disk() if left is None else left,
        G.disk() if right is None else right, **declarations)


def independent_lagrange_enclosure(x, sine):
    """Taylor polynomial of degree104 with a two-sided derivative remainder.

    This is an independent symmetric Lagrange bound, not the implementation's
    alternating-tail truncation. Every sine/cosine derivative has absolute
    value <=1 on the real line. All arithmetic below is rational.
    """
    x = F(x)
    degree = 104
    polynomial = F(0)
    for power in range(degree + 1):
        residue = power % 4
        coefficient = ((0, 1, 0, -1) if sine else (1, 0, -1, 0))[residue]
        if coefficient:
            polynomial += coefficient * x**power / math.factorial(power)
    error = abs(x)**(degree + 1) / math.factorial(degree + 1)
    return polynomial - error, polynomial + error


class ExactReachGeometryTests(unittest.TestCase):
    def assert_geometry_only(self, certificate):
        self.assertIs(certificate["mathematical_geometry_only"], True)
        self.assertIs(certificate["native_admission"], False)

    def test_independent_contract_constants_and_factories(self):
        self.assertEqual((G.R, G.BODY, G.GEOMETRY_MARGIN, G.STOP_LONGITUDINAL),
                         (R, BODY, MARGIN, LONGITUDINAL))
        self.assertEqual(G.SOURCE_MAX_NS, 500_000_000)
        for reach, buffer in [(G.disk(), 2*R), (G.normal(), 2*R),
                              (G.transition(), 4*R)]:
            self.assertEqual(reach.buffer_m, buffer)
        self.assertEqual(G.disk().longitudinal_m, 0)
        self.assertEqual(G.normal().longitudinal_m, LONGITUDINAL)
        self.assertEqual(G.transition().longitudinal_m, LONGITUDINAL)

    def test_two_R_is_sharp_for_a_fixed_anchor_not_R(self):
        anchor = F(0)
        current, future = anchor + R, anchor - R
        self.assertEqual(abs(current - future), 2*R)
        self.assertGreater(abs(current - future), R)
        with self.assertRaises(ValueError):
            G.Reach("disk", R, F(0))
        # Both robots may independently move through their entire diameters.
        boundary = 2*BODY + MARGIN + 4*R
        self.assertTrue(pair((boundary, 0))["accepted"])
        self.assertFalse(pair((boundary-F(1, 10**12), 0))["accepted"])

    def test_exact_binary64_nextafter_neighbours_never_get_an_epsilon(self):
        threshold = 2*BODY + MARGIN + 4*R
        rounded = float(threshold)
        below = math.nextafter(rounded, -math.inf)
        above = math.nextafter(rounded, math.inf)
        self.assertLess(F.from_float(below), threshold)
        self.assertGreater(F.from_float(above), threshold)
        self.assertFalse(pair((below, 0))["accepted"])
        yes = pair((above, 0))
        self.assertTrue(yes["accepted"])
        self.assert_geometry_only(yes)
        self.assertEqual(G.exact(rounded), F.from_float(rounded))

    def test_half_second_closed_endpoint_and_one_ns_stale_future(self):
        yes = pair((2, 0), ages=(500_000_000, 500_000_000))
        self.assertTrue(yes["accepted"])
        self.assertEqual(F(yes["uncertainty_m"]), F(3, 10))
        for ages in [(500_000_001, 0), (0, 500_000_001), (-1, 0),
                     (True, 0), (0.0, 0), (F(1), 0), (0,), (0, 0, 0)]:
            with self.subTest(ages=ages), self.assertRaises(ValueError):
                pair((2, 0), ages=ages)

    def test_nearer_raw_or_nearer_map_cannot_be_hidden_by_the_other(self):
        for mapped, raw, failing in [((1, 0), (F(1, 2), 0), "raw"),
                                    ((F(1, 2), 0), (1, 0), "map")]:
            with self.subTest(failing=failing):
                result = pair(mapped, raw)
                self.assertFalse(result["accepted"])
                self.assertFalse(result[failing]["accepted"])
                self.assert_geometry_only(result)

    def test_equal_distance_opposite_bearing_requires_both_direction_checks(self):
        # Map places the peer behind, while raw puts it in front at the same
        # distance. A scalar distance cap alone cannot detect this error.
        left = G.normal([direction((1, 0))])
        result = pair((-F(3, 5), 0), (F(3, 5), 0), left=left)
        self.assertTrue(result["map"]["accepted"])
        self.assertFalse(result["raw"]["accepted"])
        self.assertEqual(result["map"]["retained_longitudinal_m"][0], "0")
        self.assertEqual(F(result["raw"]["retained_longitudinal_m"][0]), LONGITUDINAL)
        self.assertFalse(result["accepted"])
        reverse = pair((F(3, 5), 0), (-F(3, 5), 0), left=left)
        self.assertFalse(reverse["map"]["accepted"])
        self.assertTrue(reverse["raw"]["accepted"])
        self.assertFalse(reverse["accepted"])

    def test_raw_heading_opposite_map_heading_also_retains_longitudinal(self):
        left = G.normal([direction((-1, 0), (1, 0))])
        result = pair((F(3, 5), 0), left=left)
        self.assertTrue(result["map"]["accepted"])
        self.assertFalse(result["raw"]["accepted"])
        self.assertFalse(result["accepted"])

    def test_every_possible_signed_heading_must_be_nonclosing(self):
        away, toward = direction((-1, 0)), direction((1, 0))
        only_away = pair((F(3, 5), 0), left=G.normal([away]))
        self.assertTrue(only_away["accepted"])
        self.assertFalse(pair((F(3, 5), 0), left=G.normal([away, toward]))["accepted"])
        unknown = pair((F(3, 5), 0), left=G.normal())
        self.assertFalse(unknown["accepted"])
        self.assertEqual(F(unknown["raw"]["retained_longitudinal_m"][0]), LONGITUDINAL)

    def test_uncertain_cone_falls_back_to_full_isotropic_longitudinal(self):
        result = pair((F(3, 5), 0), left=G.normal([direction((-1, 0), angle=2)]))
        self.assertFalse(result["accepted"])
        for frame in ("map", "raw"):
            self.assertEqual(result[frame]["direction_checks"][0], [False])
            self.assertEqual(F(result[frame]["retained_longitudinal_m"][0]), LONGITUDINAL)

    def test_original_three_robot_spacing_has_a_conditional_away_translation(self):
        # Exact original positions: tb1=(0,-.45),tb2=(0,.45),tb3=(.45,0).
        # Hypotheses: tb3 NORMAL away in+x, peers independently DISK.
        # This is reach geometry availability only, not actual mode witnesses.
        reach = G.normal([direction((1, 0), angle=F(1, 10))])
        for dy in (-F(9, 20), F(9, 20)):
            result = pair((-F(9, 20), dy), left=reach,
                          ages=(50_000_000, 50_000_000))
            self.assertTrue(result["accepted"])
            self.assert_geometry_only(result)
        self.assertTrue(pair((0, F(9, 10)), ages=(50_000_000, 50_000_000))["accepted"])

    def test_swapping_robots_preserves_the_exact_pair_verdict(self):
        left = G.normal([direction((-1, 0), angle=F(1, 10))])
        right = G.transition([direction((1, 0), angle=F(1, 10))])
        first = pair((F(7, 10), 0), left=left, right=right,
                     ages=(40_000_000, 60_000_000))
        second = pair((-F(7, 10), 0), left=right, right=left,
                      ages=(60_000_000, 40_000_000))
        self.assertEqual(first["accepted"], second["accepted"])
        self.assertEqual(first["map"]["required_centre_distance_m"],
                         second["map"]["required_centre_distance_m"])

    def test_omitted_lateral_or_terminal_R_has_an_exact_counterexample(self):
        # Removing either one R from NORMAL would lower required distance byR.
        # Pick a distance strictly between the weakened and complete thresholds.
        weak = 2*BODY + MARGIN + 3*R
        complete = 2*BODY + MARGIN + 4*R
        witness_distance = (weak + complete) / 2
        self.assertGreater(witness_distance, weak)
        self.assertLess(witness_distance, complete)
        # Full allowed perturbations: own transientR+terminalR, peer diameter2R.
        self.assertLess(witness_distance-4*R, 2*BODY+MARGIN)
        self.assertFalse(pair((witness_distance, 0),
                              left=G.normal([direction((-1, 0))]))["accepted"])
        for omitted in ("lateral", "terminal"):
            with self.subTest(omitted=omitted), self.assertRaises(ValueError):
                G.Reach("normal", R, LONGITUDINAL, (direction((-1, 0)),))

    def test_old_disk_to_normal_bridge_2R_cannot_disappear_at_publication(self):
        # A zero-delay normal substitution forgets the old disk diameter.
        distance = 2*BODY + MARGIN + 5*R
        away = direction((-1, 0))
        self.assertTrue(pair((distance, 0), left=G.normal([away]))["accepted"])
        self.assertFalse(pair((distance, 0), left=G.transition([away]))["accepted"])
        with self.assertRaises(ValueError):
            G.Reach("transition", 2*R, LONGITUDINAL, (away,))

    def test_sideways_small_does_not_bound_unadmitted_backward_forward_component(self):
        vy, wrong_sign_vx = F(0), F(1, 50)
        self.assertLessEqual(abs(vy), F(1, 100))
        self.assertGreater(vy*vy+wrong_sign_vx*wrong_sign_vx, F(1, 100)**2)
        # Geometry is conditional on the full physical residual premise;
        # the prototype cannot turn observedvy0 into a native model proof.
        result = pair((2, 0), left=G.normal())
        self.assertTrue(result["accepted"])
        self.assert_geometry_only(result)

    def test_future_mode_or_unknown_calibration_is_not_inferred_from_geometry(self):
        for flags in [{"common_world_odom_calibrated": False},
                      {"legacy_hard_gates_passed": False}]:
            with self.subTest(flags=flags):
                result = pair((10, 0), **flags)
                self.assertFalse(result["accepted"])
                self.assert_geometry_only(result)
        # Even both explicit geometric hypothesestrue never mean actor/native.
        self.assert_geometry_only(pair((10, 0)))


class ExactTaylorAndProtocolTests(unittest.TestCase):
    def test_taylor_encloses_independent_lagrange_bounds(self):
        for x in (F(0), F(1, 3), F(1), F(2),
                  F.from_float(math.nextafter(2.0, -math.inf))):
            with self.subTest(angle=x):
                slo, shi, clo, chi = G.sin_cos_bounds(x)
                sl, su = independent_lagrange_enclosure(x, True)
                cl, cu = independent_lagrange_enclosure(x, False)
                self.assertLessEqual(slo, sl)
                self.assertLessEqual(su, shi)
                self.assertLessEqual(clo, cl)
                self.assertLessEqual(cu, chi)
        self.assertEqual(G.sin_cos_bounds(0), (F(0), F(0), F(1), F(1)))
        for angle in (-F(1, 10**12), math.nextafter(2.0, math.inf)):
            with self.subTest(angle=angle), self.assertRaises(ValueError):
                G.sin_cos_bounds(angle)

    def test_tangent_and_uncertainty_boundaries_are_exact(self):
        self.assertTrue(G.nonclosing((1, 0), (0, 1), 0, 0))
        self.assertFalse(G.nonclosing((1, 0), (0, 1), F(1, 10**9), 0))
        self.assertFalse(G.nonclosing((1, 0), (0, 1), 0, F(1, 10**9)))
        self.assertTrue(G.nonclosing((-1, 0), (1, 0), 0, 1))
        self.assertFalse(G.nonclosing((-1, 0), (1, 0), 0,
                                     F.from_float(math.nextafter(1.0, math.inf))))
        self.assertEqual(G.nonclosing((-2, 1), (1, 0), F(1, 10), F(1, 10)),
                         G.nonclosing((-2, 1), (1000, 0), F(1, 10), F(1, 10)))

    def test_direction_and_reach_do_not_retain_mutable_declaration_aliases(self):
        mapped, raw = [-1, 0], [-1, 0]
        d = direction(mapped, raw, F(0))
        declared = [d]
        reach = G.normal(declared)
        mapped[0], raw[0] = 1, 1
        declared.clear()
        self.assertEqual(d.map_axis, (F(-1), F(0)))
        self.assertEqual(d.raw_axis, (F(-1), F(0)))
        self.assertEqual(reach.directions, (d,))
        self.assertTrue(pair((F(3, 5), 0), left=reach)["accepted"])
        with self.assertRaises(FrozenInstanceError):
            d.half_angle = F(1)

    def test_nonfinite_bool_and_incomplete_reach_declarations_fail_closed(self):
        for value in (True, "0.5", math.inf, -math.inf, math.nan):
            with self.subTest(value=value), self.assertRaises(ValueError):
                G.exact(value)
        for constructor in [
            lambda: direction((0, 0)),
            lambda: direction((1, 0), angle=-1),
            lambda: direction((1, 0), angle=math.nextafter(2.0, math.inf)),
            lambda: G.Reach("unknown", 2*R, LONGITUDINAL),
            lambda: G.Reach("disk", 2*R, LONGITUDINAL),
            lambda: G.Reach("normal", 2*R, LONGITUDINAL-F(1, 10**12)),
            lambda: G.Reach("transition", 4*R-F(1, 10**12), LONGITUDINAL),
            lambda: G.Reach("isotropic_stop", 2*R, LONGITUDINAL, (direction((1, 0)),)),
            lambda: pair((10, 0), common_world_odom_calibrated=1),
            lambda: pair((10, 0), legacy_hard_gates_passed=1),
            lambda: pair((True, 0)),
            lambda: pair((math.nan, 0)),
        ]:
            with self.subTest(constructor=constructor), self.assertRaises(ValueError):
                constructor()


if __name__ == "__main__":
    unittest.main()
