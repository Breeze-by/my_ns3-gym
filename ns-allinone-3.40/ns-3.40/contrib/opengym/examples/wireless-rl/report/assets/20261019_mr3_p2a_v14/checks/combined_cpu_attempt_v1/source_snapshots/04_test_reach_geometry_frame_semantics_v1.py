"""Per-frame full certificates ANDed: synthetic conditional geometry only.

These tests distinguish an intentional per-frame directional proof from
isotropic min-distance/max-reach scalar contraction. No plant or mode proof.
"""
import importlib.util
from fractions import Fraction as F
from pathlib import Path
import sys
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "mr3_v14_frame_semantics_under_test", Path(__file__).with_name("reach_geometry_v1.py"))
G = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = G
_SPEC.loader.exec_module(G)


def certificate(map_delta, raw_delta):
    normal = G.normal([G.Direction((1, 0), (1, 0), F(0))])
    return G.pair_certificate(map_delta, raw_delta, (0, 0), normal, G.disk(),
                              legacy_hard_gates_passed=True,
                              common_world_odom_calibrated=True)


class PerFrameCertificateSemanticsTests(unittest.TestCase):
    def test_map_short_away_raw_long_toward_are_independently_sufficient(self):
        # map uses its own away support and .5512 threshold; raw independently
        # retains full longitudinal.144 and passes its own .6952 threshold.
        result = certificate((-F(3, 5), 0), (F(9, 10), 0))
        self.assertTrue(result["map"]["accepted"])
        self.assertTrue(result["raw"]["accepted"])
        self.assertTrue(result["accepted"])
        self.assertEqual(F(result["map"]["required_centre_distance_m"]), F(689, 1250))
        self.assertEqual(F(result["raw"]["required_centre_distance_m"]), F(869, 1250))
        self.assertEqual(result["map"]["retained_longitudinal_m"][0], "0")
        self.assertEqual(F(result["raw"]["retained_longitudinal_m"][0]), F(18, 125))
        # A unified min-distance/max-D contraction would reject this case;
        # that is deliberately not the selected per-frame AND semantics.
        self.assertLess(F(3, 5), F(result["raw"]["required_centre_distance_m"]))
        self.assertIs(result["mathematical_geometry_only"], True)
        self.assertIs(result["native_admission"], False)

    def test_neither_one_frames_distance_nor_its_discount_can_rescue_the_other(self):
        cases = [
            # Far raw cannot override a failing extra map necessary gate.
            ((-F(27, 50), 0), (F(9, 10), 0), "map", "raw"),
            # Map nonclosing cannot discount the raw approaching direction.
            ((-F(3, 5), 0), (F(3, 5), 0), "raw", "map"),
        ]
        for mapped, raw, failing, passing in cases:
            with self.subTest(failing=failing):
                result = certificate(mapped, raw)
                self.assertFalse(result[failing]["accepted"])
                self.assertTrue(result[passing]["accepted"])
                self.assertFalse(result["accepted"])
                self.assertIs(result["native_admission"], False)


if __name__ == "__main__":
    unittest.main()
