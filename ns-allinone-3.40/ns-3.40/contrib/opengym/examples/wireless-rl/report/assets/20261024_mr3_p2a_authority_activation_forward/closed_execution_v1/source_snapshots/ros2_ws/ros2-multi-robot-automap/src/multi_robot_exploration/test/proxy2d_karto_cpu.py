"""Finite artificial sensor/ABI checks; no World, real scene or episode."""

import argparse
import ctypes as C
import json
import math
import os
from pathlib import Path
import sys
import unittest

import numpy as np

from multi_robot_exploration.mr3_proxy2d_karto import KartoSensorMapper
from test_mr3_proxy2d_mapping_quality import artificial_truth, metrics, QUALITY
from multi_robot_exploration.task_evaluator import mr3_quality_pass


LIBRARY = None


def mapper(**kwargs):
    config = dict(shape=(4, 12), resolution=1., origin=(0., 0.),
                  library_path=LIBRARY, epoch="tb1/epoch1", angles=[0.], frame_offset=(0., 0.))
    config.update(kwargs)
    return KartoSensorMapper(**config)


def add(m, seq, ranges=(3.,), pose=(.5, .5, 0.), clock=None):
    return m.integrate(seq, seq * 50_000_000 if clock is None else clock,
                       pose, m._angles.copy(), ranges)


def equal_state(a, b):
    return all(np.array_equal(a[k], b[k]) for k in ("grid", "passes", "hits"))


class AdapterChecks(unittest.TestCase):
    def test_native_counter_threshold_and_padding(self):
        with mapper(shape=(4, 5)) as m:
            add(m, 0)
            a = m.snapshot()
            self.assertEqual(a["grid"].shape, (4, 5))
            self.assertEqual((a["passes"][0, 3], a["hits"][0, 3], a["grid"][0, 3]), (2, 1, -1))
            add(m, 1)
            b = m.snapshot()
            self.assertEqual((b["passes"][0, 3], b["hits"][0, 3], b["grid"][0, 3]), (4, 2, 100))
            self.assertEqual(b["grid"][0, 1], -1)
            add(m, 2)
            self.assertEqual(m.grid()[0, 1], 0)

    def test_duplicate_noop_and_identical_new_scan_accumulates(self):
        with mapper() as m:
            self.assertTrue(add(m, 5))
            a = m.snapshot()
            self.assertFalse(add(m, 5))
            self.assertTrue(equal_state(a, m.snapshot()))
            self.assertTrue(add(m, 6))
            self.assertEqual(m.version, 2)
            self.assertEqual(m.snapshot()["hits"].sum(), 2)

    def test_conflicting_id_and_stale_clock_are_atomic(self):
        with mapper() as m:
            add(m, 5)
            a = m.snapshot()
            for seq, ranges, pose, clock in ((5, (4.,), (.5,.5,0.), None),
                    (5, (3.,), (.6,.5,0.), None), (5,(3.,),(.5,.5,0.),1),
                    (4,(3.,),(.5,.5,0.),None), (6,(3.,),(.5,.5,0.),250_000_000)):
                with self.subTest(seq=seq, pose=pose, clock=clock), self.assertRaises(ValueError):
                    add(m, seq, ranges, pose, clock)
                self.assertTrue(equal_state(a, m.snapshot()))
                self.assertEqual(m.version, 1)

    def test_input_payload_and_exports_are_detached(self):
        with mapper() as m:
            pose, angles, ranges = np.array([.5,.5,0.]), np.array([0.]), np.array([3.])
            m.integrate(0, 0, pose, angles, ranges)
            pose[0], angles[0], ranges[0] = 99., 99., 99.
            a = m.snapshot()
            for k in ("grid", "passes", "hits"):
                a[k][:] = 0
            self.assertEqual(m.snapshot()["hits"].sum(), 1)
            self.assertFalse(add(m, 0))

    def test_three_robots_fresh_epoch_and_lifecycle(self):
        with mapper(epoch="tb1/a") as a, mapper(epoch="tb2/a") as b, mapper(epoch="tb3/a") as c:
            add(a, 0)
            self.assertEqual(b.snapshot()["passes"].sum(), 0)
            self.assertEqual(c.snapshot()["passes"].sum(), 0)
            a.close()
            with mapper(epoch="tb1/b") as fresh:
                self.assertEqual(fresh.version, 0)
                self.assertEqual(fresh.snapshot()["passes"].sum(), 0)
                add(fresh, 0)
            add(b, 0)
            add(c, 0)
        a.close()
        with self.assertRaises(RuntimeError):
            a.grid()

    def test_native_min_max_skipped_and_threshold_nohit(self):
        with mapper() as m:
            for seq, r in enumerate((.12, 10.)):
                add(m, seq, (r,))
            self.assertEqual(m.snapshot()["passes"].sum(), 0)
            self.assertEqual(m.version, 2)
        with mapper(range_threshold=2.) as m:
            for seq in range(3):
                add(m, seq, (3.,))
            a = m.snapshot()
            self.assertEqual(a["hits"].sum(), 0)
            self.assertEqual(a["passes"][0,2], 3)
            self.assertEqual(a["grid"][0,2], 0)
            self.assertEqual(a["passes"][0,3], 0)
        with mapper(range_threshold=2.) as m:
            add(m, 0, (2.-.5e-6,))
            self.assertEqual(m.snapshot()["hits"].sum(), 0)

    def test_partial_consumed_once_not_atomic_reject(self):
        with mapper(shape=(4,5)) as m:
            add(m, 0, (9.,))
            a = m.snapshot()
            self.assertEqual(a["status"], "partial_out_of_map")
            self.assertGreater(a["passes"].sum(), 0)
            self.assertEqual(a["hits"].sum(), 0)
            self.assertFalse(add(m, 0, (9.,)))
            self.assertTrue(equal_state(a, m.snapshot()))
            add(m, 1, (9.,))
            self.assertEqual(m.snapshot()["passes"].sum(), 2*a["passes"].sum())

    def test_estimated_body_and_extrinsic_applied_once(self):
        with mapper(shape=(10,10), resolution=.1, origin=(0.,0.), frame_offset=(-.064,0.),
                    frame_yaw=.2) as m:
            pose = (.5,.5,math.pi/2)
            add(m, 0, (.3,), pose)
            sensor = (.5,.436,math.pi/2+.2)
            point = (sensor[0]+.3*math.cos(sensor[2]), sensor[1]+.3*math.sin(sensor[2]))
            x,y = m.world_to_grid(*point)
            self.assertEqual(m.snapshot()["hits"][y,x], 1)
            self.assertEqual(m.snapshot()["hits"].sum(), 1)

    def test_declared_center_phase_and_signed_boundary_ties(self):
        with mapper(origin=(-2.,-2.)) as m:
            # Preserve native Round, including the lower-edge half-away tie.
            for x, expected in ((-2.,-1),(-1.5,0),(-1.,1),(-.5,1),(0.,2),(.5,2)):
                self.assertEqual(m.world_to_grid(x,x), (expected,expected))
            self.assertEqual(m.snapshot()["origin"], (-2.,-2.))

    def test_full_360_native_uniform_scan_and_per_beam_weight(self):
        angles = np.linspace(0.,6.28,360)
        with mapper(angles=angles) as m:
            add(m, 0, np.full(360,.13), (5.5,1.5,0.))
            a = m.snapshot()
            self.assertEqual(a["hits"][1,5], 360)
            self.assertEqual(a["passes"][1,5], 720)

    def test_invalid_inputs_do_not_consume_or_mutate(self):
        with mapper() as m:
            a = m.snapshot()
            for seq, clock, pose, angles, ranges in ((-1,0,(.5,.5,0.),[0.],[3.]),
                    (0,-1,(.5,.5,0.),[0.],[3.]), (0,0,(float("nan"),0.,0.),[0.],[3.]),
                    (0,0,(.5,.5,0.),[.1],[3.]), (0,0,(.5,.5,0.),[0.],[]),
                    (0,0,(.5,.5,0.),[0.],[float("inf")]),
                    (0,0,(.5,.5,0.),[0.],[.1]), (0,0,(.5,.5,0.),[0.],[10.1])):
                with self.subTest(pose=pose, angles=angles, ranges=ranges), self.assertRaises(ValueError):
                    m.integrate(seq,clock,pose,angles,ranges)
                self.assertTrue(equal_state(a,m.snapshot()))
                self.assertEqual(m.version,0)

    def test_invalid_sensor_configuration(self):
        for changes in (dict(angles=[0.,.1,.25]), dict(angles=[0.,0.]),
                dict(shape=(0,5)), dict(shape=(2000,2000)), dict(resolution=0.),
                dict(range_threshold=.1), dict(max_scans=6301), dict(epoch="")):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                mapper(**changes)

    def test_finite_budget_and_duplicate_after_exhaustion(self):
        with mapper(max_scans=2) as m:
            add(m,0)
            add(m,1)
            a = m.snapshot()
            self.assertFalse(add(m,1))
            with self.assertRaises(ValueError):
                add(m,2)
            self.assertTrue(equal_state(a,m.snapshot()))

    def test_native_bad_count_rejected_before_mutation(self):
        with mapper(angles=[-.1,0.,.1]) as m:
            a = m.snapshot()
            ranges = np.array([3.,3.],dtype=np.float64)
            status = m._lib.mr3_karto_add_scan(m._handle,
                ranges.ctypes.data_as(C.POINTER(C.c_double)),2,.5,.5,0.)
            self.assertEqual(status,-1)
            self.assertTrue(equal_state(a,m.snapshot()))
            add(m,0,(3.,3.,3.))


def quality_cases():
    """Predetermined 4-face and +2mm cases, not task success or bias estimates."""
    truth = artificial_truth([(.375,.5,0.,.25,.5)], (0.,0.,1.,1.))
    results = []
    for name, pose in (("lower_x",(0.,.525,0.)),("upper_x",(.75,.525,math.pi)),
                       ("lower_y",(.375,0.,math.pi/2)),("upper_y",(.375,1.,-math.pi/2))):
        with mapper(shape=truth.occupied.shape,resolution=.05,origin=(0.,0.)) as m:
            for seq in range(8):
                add(m,seq,(.25,),pose)
            actual=metrics(truth,m.grid())
            results.append({"id": name,"metrics":actual,"quality_pass":mr3_quality_pass(actual,QUALITY)})
    for bias in (0.,.002):
        with mapper(shape=truth.occupied.shape,resolution=.05,origin=(0.,0.)) as m:
            for seq in range(32):
                add(m,seq,(.25+bias,),(.75,.525,math.pi))
            actual=metrics(truth,m.grid())
            results.append({"id":f"upper_x_32_bias_{bias}","metrics":actual,
                            "quality_pass":mr3_quality_pass(actual,QUALITY)})
    return results


def identity():
    fields=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return dict(pid=os.getpid(),parent=int(fields[1]),group=int(fields[2]),
                session=int(fields[3]),start_ticks=int(fields[19]))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    LIBRARY=args.library.resolve(strict=True)
    result=unittest.TextTestRunner(stream=sys.stderr,verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(AdapterChecks))
    cases=quality_cases() if result.wasSuccessful() else []
    loaded=sorted({line.split()[-1] for line in Path('/proc/self/maps').read_text().splitlines()
                   if 'libkartoSlamToolbox.so' in line})
    document=dict(schema='mr3-p2a-v30-karto-adapter-cpu-v1',
        passed=result.wasSuccessful(),tests=result.testsRun,failures=len(result.failures),
        errors=len(result.errors),quality_cases=cases,identity=identity(),loaded_karto_paths=loaded,
        production_enabled=False,qualification=False,training_eligible=False)
    with args.output.open('x') as stream:
        json.dump(document,stream,indent=2,allow_nan=False)
        stream.write('\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
