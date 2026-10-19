"""Independent synthetic CPU validation DESIGN, initially unexecuted.

No ROS/native/GPU or experimental data reader. Passing these tests would
validate conditional geometry, not a plant premise or native admission.
Run explicitly with --geometry PATH after reviewing the unsealed design.
"""
import argparse
from fractions import Fraction as Q
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import unittest

DEFAULT_CORE = Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14/cpu/reach_geometry_v1.py')
G = None


def residual_components(vx, vy, signed_set):
    """Analysis definition, not a replacement velocity controller.

    A zero target during braking retains the previous committed signed_set.
    Giving an empty set instead models a fully rest/disk longitudinal part.
    """
    vx, vy = Q(vx), Q(vy)
    if any(type(sign) is not int or sign not in (-1, 1) for sign in signed_set):
        raise ValueError('invalid committed signed set')
    admitted = any(sign*vx > 0 for sign in signed_set)
    nominal_v = vx if admitted else Q(0)
    return nominal_v, vx-nominal_v, vy


def independent_series_interval(x, sine):
    """Independent factorial evaluation, much deeper than the core recurrence."""
    powers = [2*n+1 if sine else 2*n for n in range(82)]
    terms = [(-1 if n % 2 else 1)*x**power/Q(math.factorial(power))
             for n, power in enumerate(powers)]
    return sum(terms), sum(terms[:-1])  # odd81 lower, even80 upper


class PairSafetyDesign(unittest.TestCase):
    def certificate(self, delta, left, right, ages=(0, 0), raw=None,
                    legacy=True, calibrated=True):
        result = G.pair_certificate(delta, delta if raw is None else raw,
                                    ages, left, right,
                                    legacy_hard_gates_passed=legacy,
                                    common_world_odom_calibrated=calibrated)
        self.assertIs(result['mathematical_geometry_only'], True)
        self.assertIs(result['native_admission'], False)
        return result

    def direction(self, axis, half=Q(0), raw=None):
        return G.Direction(tuple(axis), tuple(axis if raw is None else raw), half)

    def test_binary64_is_exact_and_invalid_types_fail(self):
        self.assertEqual(G.exact(0.1), Q.from_float(0.1))
        self.assertNotEqual(G.exact(0.1), Q(1, 10))
        for bad in (True, False, float('nan'), float('inf'), '0.1'):
            with self.assertRaises(ValueError):
                G.exact(bad)

    def test_trig_bounds_contain_independent_long_series(self):
        for x in (Q(0), Q(1, 10), Q(1), Q(2)):
            sl, sh, cl, ch = G.sin_cos_bounds(x)
            rsl, rsh = independent_series_interval(x, True)
            rcl, rch = independent_series_interval(x, False)
            self.assertLessEqual(sl, rsl)
            self.assertLessEqual(rsh, sh)
            self.assertLessEqual(cl, rcl)
            self.assertLessEqual(rch, ch)
        with self.assertRaises(ValueError):
            G.sin_cos_bounds(Q(2)+Q(1, 10**12))

    def test_nonclosing_uncertainty_square_has_correct_sign(self):
        self.assertTrue(G.nonclosing((1, 0), (-1, 0), Q(0), Q(1)))
        self.assertFalse(G.nonclosing((1, 0), (-1, 0), Q(0), Q(1)+Q(1,10**12)))
        self.assertTrue(G.nonclosing((1, 0), (-1, 0), Q(1), Q(1,2)))
        self.assertFalse(G.nonclosing((1, 0), (-1, 0), Q(1), Q(3,5)))
        self.assertTrue(G.nonclosing((1, 0), (0, 1), Q(0), Q(0)))
        self.assertFalse(G.nonclosing((1, 0), (0, 1), Q(1,100), Q(0)))

    def test_canonical_buffers_and_sharp_double_radius(self):
        r = Q(39, 5000)
        self.assertEqual(G.disk().buffer_m, 2*r)
        self.assertEqual(G.normal().buffer_m, 2*r)
        self.assertEqual(G.transition().buffer_m, 4*r)
        current, future, anchor = -r, r, Q(0)
        self.assertLessEqual(abs(current-anchor), r)
        self.assertLessEqual(abs(future-anchor), r)
        self.assertEqual(abs(future-current), 2*r)
        self.assertEqual(Q(1,100)*Q(39,50), r)

    def test_all_pair_minkowski_thresholds_exactly(self):
        cases = [(G.disk(), G.disk(), Q(5512,10000)),
                 (G.disk(), G.normal(), Q(6952,10000)),
                 (G.normal(), G.normal(), Q(8392,10000)),
                 (G.disk(), G.transition(), Q(7108,10000)),
                 (G.normal(), G.transition(), Q(8548,10000)),
                 (G.transition(), G.transition(), Q(8704,10000))]
        for left, right, distance in cases:
            self.assertTrue(self.certificate((distance,0),left,right)['accepted'])
            self.assertFalse(self.certificate((distance-Q(1,10**12),0),left,right)['accepted'])

    def test_bare_point_1596_does_not_include_new_normal_terminal(self):
        old_distance = Q(6796,10000)  # .52 + .0156 + .144
        result = self.certificate((old_distance,0),G.disk(),G.normal())
        self.assertFalse(result['accepted'])
        self.assertEqual(Q(result['raw']['required_centre_distance_m']), Q(6952,10000))

    def test_union_of_possible_signs_requires_every_cone(self):
        away = self.direction((-1,0))
        toward = self.direction((1,0))
        left = G.normal((away,toward))
        result = self.certificate((Q(3,5),0), left, G.disk())
        self.assertEqual(result['raw']['direction_checks'][0], [True,False])
        self.assertEqual(result['raw']['retained_longitudinal_m'][0], str(Q(18,125)))
        self.assertFalse(result['accepted'])

    def test_map_distance_cap_without_raw_bearing_is_insufficient(self):
        left = G.normal((self.direction((-1,0),raw=(1,0)),))
        result = self.certificate((Q(3,5),0),left,G.disk())
        self.assertTrue(result['map']['accepted'])
        self.assertFalse(result['raw']['accepted'])
        self.assertFalse(result['accepted'])
        far_map_small_raw = self.certificate((10,0),G.disk(),G.disk(),raw=(Q(1,10),0))
        self.assertFalse(far_map_small_raw['accepted'])

    def test_near_spawn_has_post_disk_reorientation_translation_witness(self):
        # Synthetic existence only. The guard does not choose these headings.
        # Global W*(age+H)=1.2*(.02+.78)=.96 includes the old-turn bridge.
        half = Q(6,5)*(Q(1,50)+Q(39,50))
        sw = G.transition((self.direction((-1,-2),half),))
        nw = G.transition((self.direction((-1,2),half),))
        d13 = (Q(45,100),Q(45,100))
        d23 = (Q(45,100),-Q(45,100))
        ages = (20_000_000,20_000_000)
        for delta,left,right in [((0,Q(9,10)),sw,nw),
                                 (d13,sw,G.disk()), (d23,nw,G.disk())]:
            result=self.certificate(delta,left,right,ages)
            self.assertTrue(result['accepted'])
            self.assertTrue(all(Q(x)==0 for x in result['raw']['retained_longitudinal_m']))

    def test_wide_cone_does_not_admit_initial_tb3_east(self):
        half=Q(24,25)
        east=G.transition((self.direction((1,0),half),))
        result=self.certificate((-Q(45,100),-Q(45,100)),east,G.disk(),
                                (20_000_000,20_000_000))
        self.assertFalse(result['accepted'])
        self.assertEqual(Q(result['raw']['retained_longitudinal_m'][0]),Q(18,125))

    def test_sources_calibration_and_old_hard_gates_never_disappear(self):
        for ages in ((-1,0),(0,500_000_001),(True,0)):
            with self.assertRaises(ValueError):
                self.certificate((10,0),G.disk(),G.disk(),ages)
        self.assertFalse(self.certificate((10,0),G.disk(),G.disk(),legacy=False)['accepted'])
        self.assertFalse(self.certificate((10,0),G.disk(),G.disk(),calibrated=False)['accepted'])
        self.assertFalse(self.certificate((Q(45,100),Q(45,100)),G.disk(),G.disk(),
                                          (500_000_000,500_000_000))['accepted'])

    def test_stop_target_keeps_forward_braking_and_counts_wrong_sign(self):
        limit2=Q(1,100)**2
        nominal,rx,ry=residual_components(Q(4,25),Q(1,1000),(1,))
        self.assertEqual(nominal,Q(4,25))  # target0 is not actual body rest
        self.assertLessEqual(rx*rx+ry*ry,limit2)
        _,rx,ry=residual_components(Q(4,25),0,())
        self.assertGreater(rx*rx+ry*ry,limit2)
        _,rx,ry=residual_components(-Q(2,100),0,(1,))
        self.assertGreater(rx*rx+ry*ry,limit2)
        _,rx,ry=residual_components(-Q(8,10000),Q(13,10000),(1,))
        self.assertLessEqual(rx*rx+ry*ry,limit2)


def main():
    global G
    parser=argparse.ArgumentParser()
    parser.add_argument('--geometry',type=Path,default=DEFAULT_CORE)
    args=parser.parse_args()
    source=args.geometry.resolve()
    module_name='mr3_v14_exact_geometry_independent_design'
    spec=importlib.util.spec_from_file_location(module_name,source)
    G=importlib.util.module_from_spec(spec)
    sys.modules[module_name]=G
    spec.loader.exec_module(G)
    print(json.dumps({'scope':'synthetic_cpu_conditional_geometry_only',
                      'geometry_source':str(source),
                      'geometry_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                      'native_admission':False,'plant_validated':False},sort_keys=True),flush=True)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(PairSafetyDesign))
    raise SystemExit(0 if result.wasSuccessful() else 1)


if __name__=='__main__':
    main()
