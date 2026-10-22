"""Fixed artificial full-certificate timing, never a World capacity claim."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import time

import numpy as np

from multi_robot_exploration import mr3_seed_certificate as production


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    assets = Path(__file__).resolve().parent
    frozen = assets / 'frozen_reference_v1.py'
    expected_sha = '99bd4fdda76a5974d394a2e40177e7cbd5fb12308258c2ee096c5232c568e3cb'
    if hashlib.sha256(frozen.read_bytes()).hexdigest() != expected_sha:
        raise ValueError('old frozen reference bytes differ')
    spec = importlib.util.spec_from_file_location(
        'multi_robot_exploration._v39_frozen_benchmark_reference', frozen)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    if reference._segment_measurements is production._segment_measurements:
        raise ValueError('benchmark reference is production itself')
    root = Path('/home/zhuyulab/ns3-workspace')
    canonical = root / ('ros2_ws/ros2-multi-robot-automap/src/'
                        'multi_robot_exploration/multi_robot_exploration/mr3_seed_certificate.py')
    if Path(production.__file__).resolve() != canonical:
        raise ValueError('production import is not canonical source')

    q = reference.Q
    ring = np.zeros((21, 21), dtype=np.int8)
    ring[6:15, 6:15] = 100
    ring[8:13, 8:13] = 0
    corner = np.zeros((21, 21), dtype=np.int8)
    corner[13:, 16:] = 100
    res, origin = q(1, 20), (-q(21, 40), -q(21, 40))
    cases = [((q(0), q(0)), (q(x, 1000), q(y, 1000)))
             for x, y in ((0, 0), (2, 0), (0, 2), (25, 25), (-25, 25),
                          (50, 0), (100, 100), (-100, 0))]
    workloads = [(grid, start, end) for grid in (corner, ring) for start, end in cases]
    records = []
    first_digest = None
    for order in (('frozen_reference', 'production'), ('production', 'frozen_reference')):
        for name in order:
            module = reference if name == 'frozen_reference' else production
            started = time.perf_counter_ns()
            results = [module.certify_estimated_segment(grid, res, origin, start, end)
                       for _ in range(2) for grid, start, end in workloads]
            elapsed = time.perf_counter_ns() - started
            encoded = json.dumps(results, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
            digest = hashlib.sha256(encoded).hexdigest()
            if first_digest is None:
                first_digest = digest
            if digest != first_digest:
                raise ValueError('full public certificate outputs differ')
            records.append({'implementation': name, 'calls': len(results),
                            'elapsed_ns': elapsed, 'full_output_sha256': digest})
    result = {'schema': 'mr3-v39-fixed-full-certificate-microbenchmark-v1',
              'artificial_cpu_only': True, 'world_capacity_claim': False,
              'native_or_training_credit': False, 'engineering_increment_seconds': '0',
              'production_source': str(canonical),
              'production_sha256': hashlib.sha256(canonical.read_bytes()).hexdigest(),
              'reference_freeze': 'a44e1b844678ece45cfd377ea43e7ed65901cce3',
              'reference_sha256': expected_sha,
              'workloads': ['corner_obstacle', 'dense_unsafe_ring'],
              'calls_total': 128, 'full_outputs_equal': True, 'records': records}
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({'calls': 128, 'full_outputs_equal': True, 'records': records}))


if __name__ == '__main__':
    main()
