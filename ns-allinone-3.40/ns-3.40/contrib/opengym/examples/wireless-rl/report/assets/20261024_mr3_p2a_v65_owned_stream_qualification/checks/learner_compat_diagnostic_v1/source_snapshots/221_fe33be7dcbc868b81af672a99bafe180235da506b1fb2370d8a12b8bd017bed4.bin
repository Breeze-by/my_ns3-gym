"""Additional finite ABI/concurrency checks; no World, truth or quality model.

Run explicitly with --library EXISTING_ABI_ELF --output EXCLUSIVE_JSON.
This neither builds a library nor imports the earlier quality consumer.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import ctypes as C
import json
import os
from pathlib import Path
import sys
from threading import Barrier
import unittest

import numpy as np

from multi_robot_exploration.mr3_proxy2d_karto import KartoSensorMapper, _library


LIBRARY = None
U32_MAX = (1 << 32) - 1
BAD_HANDLE = (1 << 64) - 1


def pointer(array, kind):
    return array.ctypes.data_as(C.POINTER(kind))


def create(library, **changes):
    config = dict(width=5, height=4, resolution=1., origin_x=0., origin_y=0.,
                  beams=1, angle_min=0., angle_step=.1, range_min=.12,
                  range_max=10., threshold=10., offset_x=0., offset_y=0.,
                  offset_yaw=0., max_scans=1)
    config.update(changes)
    return library.mr3_karto_create(*(config[key] for key in (
        "width", "height", "resolution", "origin_x", "origin_y", "beams",
        "angle_min", "angle_step", "range_min", "range_max", "threshold",
        "offset_x", "offset_y", "offset_yaw", "max_scans")))


@contextmanager
def raw_grid(library, **config):
    handle = create(library, **config)
    if not handle:
        raise RuntimeError(library.mr3_karto_error())
    try:
        yield handle
    finally:
        if library.mr3_karto_destroy(handle) != 0:
            raise RuntimeError(library.mr3_karto_error())


def snapshot(library, handle, shape=(4, 5)):
    passes = np.empty(shape, dtype=np.uint32)
    hits = np.empty(shape, dtype=np.uint32)
    grid = np.empty(shape, dtype=np.int8)
    result = library.mr3_karto_export(handle, pointer(passes, C.c_uint32),
        pointer(hits, C.c_uint32), pointer(grid, C.c_int8), grid.size)
    if result != 0:
        raise RuntimeError(library.mr3_karto_error())
    return passes, hits, grid


def add_raw(library, handle, ranges=(3.,), pose=(.5, .5, 0.)):
    readings = np.array(ranges, dtype=np.float64)
    return library.mr3_karto_add_scan(handle, pointer(readings, C.c_double),
                                    readings.size, *pose)


class ExtraAdapterChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.library, _ = _library(LIBRARY)

    def assertStateEqual(self, expected, actual):
        for old, new in zip(expected, actual):
            np.testing.assert_array_equal(old, new)

    def test_raw_bad_handles_reject_without_writing_outputs(self):
        library = self.library
        for handle in (0, BAD_HANDLE):
            with self.subTest(handle=handle):
                self.assertEqual(add_raw(library, handle), -1)
                self.assertIn(b"unknown or destroyed handle", library.mr3_karto_error())
                passes = np.full((4, 5), 123, dtype=np.uint32)
                hits = np.full((4, 5), 456, dtype=np.uint32)
                grid = np.full((4, 5), 77, dtype=np.int8)
                self.assertEqual(library.mr3_karto_export(handle,
                    pointer(passes, C.c_uint32), pointer(hits, C.c_uint32),
                    pointer(grid, C.c_int8), 20), -1)
                self.assertTrue(np.all(passes == 123))
                self.assertTrue(np.all(hits == 456))
                self.assertTrue(np.all(grid == 77))
                x, y = C.c_int32(123), C.c_int32(456)
                self.assertEqual(library.mr3_karto_world_to_grid(handle, .5, .5,
                    C.byref(x), C.byref(y)), -1)
                self.assertEqual((x.value, y.value), (123, 456))
                self.assertEqual(library.mr3_karto_destroy(handle), -1)

    def test_destroyed_handle_never_aliases_a_new_live_instance(self):
        library = self.library
        old = create(library)
        self.assertNotEqual(old, 0)
        self.assertEqual(library.mr3_karto_destroy(old), 0)
        self.assertEqual(library.mr3_karto_destroy(old), -1)
        with raw_grid(library) as fresh:
            self.assertNotEqual(old, fresh)
            before = snapshot(library, fresh)
            self.assertEqual(add_raw(library, old), -1)
            self.assertStateEqual(before, snapshot(library, fresh))
            self.assertEqual(add_raw(library, fresh), 0)

    def test_raw_create_rejects_counter_overflow_budget_without_affecting_live_map(self):
        library = self.library
        beams = 4096
        overflowing_scans = U32_MAX // (2 * beams) + 1
        with raw_grid(library) as live:
            before = snapshot(library, live)
            for budget in (0, overflowing_scans):
                with self.subTest(budget=budget):
                    handle = create(library, beams=beams, angle_step=.001,
                                    max_scans=budget)
                    if handle:
                        library.mr3_karto_destroy(handle)
                    self.assertEqual(handle, 0)
                    self.assertIn(b"scan budget could overflow", library.mr3_karto_error())
                    self.assertStateEqual(before, snapshot(library, live))
            self.assertEqual(add_raw(library, live), 0)

    def test_raw_partial_consumes_native_budget_exactly_once(self):
        library = self.library
        with raw_grid(library, max_scans=1) as handle:
            self.assertEqual(add_raw(library, handle, (9.,)), 1)
            partial = snapshot(library, handle)
            self.assertGreater(int(partial[0].sum()), 0)
            self.assertEqual(int(partial[1].sum()), 0)
            self.assertEqual(add_raw(library, handle, (.13,)), -1)
            self.assertIn(b"scan budget exhausted", library.mr3_karto_error())
            self.assertStateEqual(partial, snapshot(library, handle))

    def test_raw_huge_start_preflight_is_atomic_and_does_not_consume_budget(self):
        library = self.library
        with raw_grid(library) as handle:
            before = snapshot(library, handle)
            self.assertEqual(add_raw(library, handle, (.13,), (2_000_000.5, .5, 0.)), -1)
            self.assertIn(b"safe native lattice", library.mr3_karto_error())
            self.assertStateEqual(before, snapshot(library, handle))
            self.assertEqual(add_raw(library, handle, (.13,)), 0)
            self.assertEqual(int(snapshot(library, handle)[1].sum()), 1)

    def test_raw_huge_endpoint_preflight_is_atomic_and_does_not_consume_budget(self):
        library = self.library
        with raw_grid(library, range_max=2_000_000., threshold=2_000_000.) as handle:
            before = snapshot(library, handle)
            self.assertEqual(add_raw(library, handle, (1_500_000.,)), -1)
            self.assertIn(b"safe native lattice", library.mr3_karto_error())
            self.assertStateEqual(before, snapshot(library, handle))
            self.assertEqual(add_raw(library, handle, (.13,)), 0)

    def test_raw_work_limit_checks_all_beams_before_any_ray_mutation(self):
        library = self.library
        # Every endpoint is within the 1e6 lattice guard; the aggregate work
        # exceeds 8e6 visits. A correct preflight never walks these long rays.
        with raw_grid(library, beams=16, angle_step=.0001,
                      range_max=800_000., threshold=800_000.) as handle:
            before = snapshot(library, handle)
            self.assertEqual(add_raw(library, handle, np.full(16, 750_000.)), -1)
            self.assertIn(b"ray-work limit", library.mr3_karto_error())
            self.assertStateEqual(before, snapshot(library, handle))
            self.assertEqual(add_raw(library, handle, np.full(16, .13)), 0)
            after = snapshot(library, handle)
            self.assertEqual(int(after[0].sum()), 32)
            self.assertEqual(int(after[1].sum()), 16)

    def test_raw_invalid_payloads_reject_before_mutation_and_scan_consumption(self):
        library = self.library
        with raw_grid(library) as handle:
            before = snapshot(library, handle)
            for ranges, pose in (((float("nan"),), (.5,.5,0.)),
                    ((float("inf"),), (.5,.5,0.)), ((-.1,), (.5,.5,0.)),
                    ((.13,), (float("nan"),.5,0.)), ((.13,), (.5,.5,float("inf")))):
                with self.subTest(ranges=ranges, pose=pose):
                    self.assertEqual(add_raw(library, handle, ranges, pose), -1)
                    self.assertStateEqual(before, snapshot(library, handle))
            self.assertEqual(library.mr3_karto_add_scan(handle, None, 1, .5, .5, 0.), -1)
            self.assertStateEqual(before, snapshot(library, handle))
            self.assertEqual(add_raw(library, handle, (.13,)), 0)

    def test_duplicate_concurrency_commits_one_scan_and_one_native_update(self):
        # Simultaneous delivery of one exact source scan must still be a no-op
        # for every caller after the first, even though ctypes releases the GIL.
        workers = 8
        gate = Barrier(workers)
        with KartoSensorMapper((4, 5), 1., (0., 0.), library_path=LIBRARY,
                epoch="tb1/concurrent", angles=[0.], frame_offset=(0., 0.),
                max_scans=1) as mapper:
            def duplicate(_):
                gate.wait(timeout=5.)
                return mapper.integrate(7, 350_000_000, (.5,.5,0.), [0.], [3.])

            with ThreadPoolExecutor(max_workers=workers) as pool:
                outcomes = list(pool.map(duplicate, range(workers)))
            self.assertEqual(outcomes.count(True), 1)
            self.assertEqual(outcomes.count(False), workers - 1)
            actual = mapper.snapshot()
            self.assertEqual((actual["version"], actual["source_scan_id"],
                              actual["source_clock_ns"]), (1, 7, 350_000_000))
            self.assertEqual(int(actual["passes"].sum()), 5)
            self.assertEqual(int(actual["hits"].sum()), 1)

    def test_native_error_is_thread_local_across_different_rejections(self):
        library = self.library
        gate = Barrier(2)
        with raw_grid(library) as handle:
            before = snapshot(library, handle)

            def rejected(unknown):
                if unknown:
                    result = add_raw(library, BAD_HANDLE)
                else:
                    result = library.mr3_karto_add_scan(handle, None, 1, .5, .5, 0.)
                gate.wait(timeout=5.)  # Both errors exist before either reads it.
                return result, library.mr3_karto_error()

            with ThreadPoolExecutor(max_workers=2) as pool:
                unknown, bad_count = list(pool.map(rejected, (True, False)))
            self.assertEqual(unknown, (-1, b"unknown or destroyed handle"))
            self.assertEqual(bad_count, (-1, b"null ranges or wrong beam count"))
            self.assertStateEqual(before, snapshot(library, handle))
            self.assertEqual(add_raw(library, handle), 0)


def identity():
    fields = Path("/proc/self/stat").read_text().rsplit(")", 1)[1].split()
    return dict(pid=os.getpid(), parent=int(fields[1]), group=int(fields[2]),
                session=int(fields[3]), start_ticks=int(fields[19]))


def main():
    global LIBRARY
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    LIBRARY = args.library.resolve(strict=True)
    # Reject an existing result before loading/calling the ABI library.
    with args.output.open("x") as stream:
        result = unittest.TextTestRunner(stream=sys.stderr, verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(ExtraAdapterChecks))
        loaded = sorted({line.split()[-1] for line in Path("/proc/self/maps").read_text().splitlines()
                         if "libkartoSlamToolbox.so" in line})
        document = dict(schema="mr3-p2a-v30-karto-adapter-extra-cpu-v1",
            passed=result.wasSuccessful(), tests=result.testsRun,
            failures=len(result.failures), errors=len(result.errors),
            identity=identity(), loaded_karto_paths=loaded,
            production_enabled=False, qualification=False, training_eligible=False,
            native_credit=False)
        json.dump(document, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
