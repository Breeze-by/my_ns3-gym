"""Independent synthetic CPU model-obligation tests, initially unexecuted.

No ROS/native/GPU or experimental data reader. Passing these tests would
validate conditional geometry, not a plant premise or native admission.
Root runs this file with a finite CPU runner after source review.
"""
from fractions import Fraction as Q
import importlib.util
import math
from pathlib import Path
import sys
import unittest

_SPEC = importlib.util.spec_from_file_location(
    "mr3_v14_pair_model_obligations_under_test",
    Path(__file__).with_name("reach_geometry_v1.py"))
G = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = G
_SPEC.loader.exec_module(G)


def independent_series_interval(x, sine):
    """Independent factorial evaluation, much deeper than the core recurrence."""
    powers = [2*n+1 if sine else 2*n for n in range(82)]
    terms = [(-1 if n % 2 else 1)*x**power/Q(math.factorial(power))
             for n, power in enumerate(powers)]
    return sum(terms), sum(terms[:-1])  # odd81 lower, even80 upper


class PairModelObligationsTests(unittest.TestCase):
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
        nominal,(rx,ry)=G.residual_components(Q(4,25),Q(1,1000),(1,))
        self.assertEqual(nominal,Q(4,25))  # target0 is not actual body rest
        self.assertLessEqual(rx*rx+ry*ry,limit2)
        _,(rx,ry)=G.residual_components(Q(4,25),0,())
        self.assertGreater(rx*rx+ry*ry,limit2)
        _,(rx,ry)=G.residual_components(-Q(2,100),0,(1,))
        self.assertGreater(rx*rx+ry*ry,limit2)
        _,(rx,ry)=G.residual_components(-Q(8,10000),Q(13,10000),(1,))
        self.assertLessEqual(rx*rx+ry*ry,limit2)

    def test_original_body_stop_time_and_path_constants_are_retained(self):
        speed, reaction, padding, decel = Q(3,10), Q(16,100), Q(2,100), Q(1,2)
        self.assertEqual(G.BACKUP_HORIZON, reaction+speed/decel+padding)
        self.assertEqual(G.BACKUP_HORIZON, Q(39,50))
        self.assertEqual(G.STOP_LONGITUDINAL,
                         speed*(reaction+padding)+speed*speed/(2*decel))
        self.assertEqual(G.STOP_LONGITUDINAL, Q(18,125))
        self.assertEqual(G.RESIDUAL_SPEED, Q(1,100))
        self.assertEqual(G.R, G.RESIDUAL_SPEED*G.BACKUP_HORIZON)

    def test_reach_cannot_drop_finite_residual_terminal_or_bridge(self):
        for kind, buffer, longitudinal in (
                ('normal',G.R,G.STOP_LONGITUDINAL),
                ('isotropic_stop',G.R,G.STOP_LONGITUDINAL),
                ('transition',2*G.R,G.STOP_LONGITUDINAL),
                ('normal',2*G.R,G.STOP_LONGITUDINAL-Q(1,10**12)),
                ('disk',G.R,0)):
            with self.assertRaises(ValueError):
                G.Reach(kind,buffer,longitudinal)
        with self.assertRaises(ValueError):
            G.Reach('isotropic_stop',2*G.R,G.STOP_LONGITUDINAL,
                    (self.direction((-1,0)),))

    def test_terminal_disk_is_not_a_permanent_stop_point(self):
        # A finite actual stop path D is compatible with subsequent movement
        # inside a distinct terminal disk; D alone cannot cover all future.
        stop_point = G.STOP_LONGITUDINAL
        future_point = stop_point+G.R
        self.assertLessEqual(abs(future_point-stop_point),G.R)
        self.assertGreater(abs(future_point),G.STOP_LONGITUDINAL)
        self.assertEqual(G.normal().buffer_m,G.R+G.R)
        self.assertEqual(G.transition().buffer_m,2*G.R+G.R+G.R)

    def test_finite_residual_bound_does_not_imply_old_whole_segment_L1(self):
        residual = Q(8,1000)
        self.assertTrue(G.residual_within_bound(0,residual,()))
        self.assertLessEqual(residual*G.BACKUP_HORIZON,G.R)
        self.assertGreater(residual*Q(300),G.R)
        # An explicit path entirely inside the fixed anchor disk has positive
        # total variation and returns to its anchor. No sample is discarded.
        points = [Q(0),G.R,Q(0),-G.R,Q(0)]
        path = sum(abs(b-a) for a,b in zip(points,points[1:]))
        self.assertTrue(all(abs(x)<=G.R for x in points))
        self.assertEqual(points[-1]-points[0],0)
        self.assertEqual(path,4*G.R)
        self.assertGreater(path,G.R)

    def test_two_dimensional_residual_boundary_and_one_exact_increment(self):
        # .006 wrong-sign forward plus .008 lateral has exact norm .01.
        self.assertTrue(G.residual_within_bound(-Q(3,500),Q(4,500),(1,)))
        self.assertFalse(G.residual_within_bound(-Q(3,500),
                                                Q(4,500)+Q(1,10**12),(1,)))
        # Both individual components can be <=.01 while their norm exceeds it.
        self.assertFalse(G.residual_within_bound(-Q(9,1000),Q(9,1000),(1,)))

    def test_fixed_sign_declaration_is_not_rebuilt_after_the_sample(self):
        self.assertFalse(G.residual_within_bound(-Q(2,100),0,(1,)))
        self.assertTrue(G.residual_within_bound(-Q(2,100),0,(-1,)))
        # The contrast is why a real mode certificate must bind its original
        # signs before motion. This pure function does not supply that lease.
        for malformed in ([1],(True,),(1,1),(0,),(-1,-1)):
            with self.assertRaises(ValueError):
                G.residual_components(Q(1,10),0,malformed)

    def test_empty_signs_mean_full_rest_not_a_zero_target_shortcut(self):
        self.assertTrue(G.residual_within_bound(Q(16,100),0,(1,)))
        self.assertFalse(G.residual_within_bound(Q(16,100),0,()))
        self.assertFalse(G.residual_within_bound(Q(16,100),0,(-1,)))
        self.assertEqual(G.residual_components(0,0,()),(Q(0),(Q(0),Q(0))))

    def test_small_residual_is_not_the_global_body_speed_or_pose_gate(self):
        self.assertTrue(G.residual_within_bound(1,0,(1,)))
        self.assertGreater(Q(1)**2,G.SPEED**2)
        self.assertFalse(self.certificate((10,0),G.normal(),G.disk(),
                                          legacy=False)['accepted'])
        # Likewise, an orthogonal basis is a separate calibration hypothesis.
        vx,vy = Q(3,500),Q(4,500)
        self.assertEqual(vx*vx+vy*vy,(-vy)*(-vy)+vx*vx)  # exact 90deg basis
        self.assertNotEqual(vx*vx+vy*vy,(2*vx)*(2*vx)+vy*vy)

    def test_residual_numeric_payloads_have_no_boolean_or_nan_escape(self):
        for bad in (True,False,float('nan'),float('inf')):
            with self.assertRaises(ValueError):
                G.residual_within_bound(bad,0,(1,))
            with self.assertRaises(ValueError):
                G.residual_within_bound(0,bad,(1,))

    def test_next_guard_and_actuator_selection_fit_existing_reaction(self):
        guard_period = Q(20,1000)
        actuator_frame = Q(34,1000)
        reaction = Q(16,100)
        self.assertEqual(guard_period+actuator_frame,Q(54,1000))
        self.assertLess(guard_period+actuator_frame,reaction)
        # This is only command-selection timing. The actual body-stop H/D
        # obligations remain distinct external plant premises.
        self.assertLess(reaction,G.BACKUP_HORIZON)

    def test_global_angular_cone_covers_old_w_not_only_new_request(self):
        age,omega_bound = Q(20,1000),Q(6,5)
        half_angle=omega_bound*(age+G.BACKUP_HORIZON)
        self.assertEqual(half_angle,Q(24,25))
        old_w,new_w,old_hold=Q(3,10),Q(0),Q(34,1000)
        self.assertGreater(old_w*old_hold,new_w*G.BACKUP_HORIZON)
        max_old_new_integral=(old_w*old_hold
                              +omega_bound*(G.BACKUP_HORIZON-old_hold))
        self.assertLessEqual(omega_bound*age+max_old_new_integral,half_angle)

    def test_backup_deadline_does_not_restart_at_actual_actuation(self):
        commit=Q(10)
        selection=commit+Q(54,1000)
        original_deadline=commit+G.BACKUP_HORIZON
        invalid_restarted_deadline=selection+G.BACKUP_HORIZON
        self.assertGreater(invalid_restarted_deadline,original_deadline)
        self.assertEqual(original_deadline-commit,Q(39,50))
        finite_endpoint=original_deadline
        self.assertEqual(G.RESIDUAL_SPEED*(finite_endpoint-commit),G.R)
        self.assertGreater(G.RESIDUAL_SPEED*(finite_endpoint-commit+Q(1,10**9)),G.R)

    def test_future_and_source_endpoint_are_strict_independent_hypotheses(self):
        # Exact source-age endpoint remains eligible; +1ns and future do not.
        self.assertTrue(self.certificate((10,0),G.disk(),G.disk(),
                                         (500_000_000,500_000_000))['accepted'])
        for ages in ((500_000_001,0),(-1,0)):
            with self.assertRaises(ValueError):
                self.certificate((10,0),G.disk(),G.disk(),ages)
        # Body norm, terminal-disk permanence, and actual endpoint ownership
        # still are not inferred from this source-age check or a geometry PASS.
        self.assertFalse(self.certificate((10,0),G.disk(),G.disk(),
                                          calibrated=False)['native_admission'])



if __name__ == '__main__':
    unittest.main()
