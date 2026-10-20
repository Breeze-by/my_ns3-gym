"""CPU-only tiny maps and setter loops; no world, native reader or learner."""
from array import array
import copy
import hashlib
import json
from pathlib import Path
import statistics
import time
from types import ModuleType

from nav_msgs.msg import OccupancyGrid
import numpy as np
from rclpy.serialization import deserialize_message, serialize_message

from merge_map import merge_map as current


DIRECTORY = Path(__file__).resolve().parent
legacy_path = Path('/tmp/mr3_map_packing_cpu_v1/source_merge_map_before.py.txt')
legacy_raw = legacy_path.read_bytes()
legacy = ModuleType('legacy_map_packing_fixture')
exec(compile(legacy_raw, str(legacy_path), 'exec'), legacy.__dict__)


def make_grid(rng, index, fractional):
    grid = OccupancyGrid()
    grid.header.frame_id = 'map'
    grid.header.stamp.sec = index + 1
    grid.info.map_load_time.sec = index
    grid.info.resolution = .25
    grid.info.width, grid.info.height = 12, 8
    grid.info.origin.position.x = index * (.13 if fractional else .25)
    grid.info.origin.position.y = index * (-.17 if fractional else -.25)
    grid.info.origin.orientation.w = 1.
    grid.data = rng.integers(-1, 101, size=96).tolist()
    return grid


rng = np.random.default_rng(29)
equivalence_count = 0
for fractional in (False, True):
    for _ in range(8):
        maps = [make_grid(rng, index, fractional) for index in range(3)]
        before = copy.deepcopy(maps)
        for name in ('merge_maps', 'merge_navigation_map'):
            args = (maps,) if name == 'merge_maps' else (maps[0], maps[1])
            expected = getattr(legacy, name)(*args)
            actual = getattr(current, name)(*args)
            assert actual == expected and actual.data.tobytes() == expected.data.tobytes()
            assert deserialize_message(serialize_message(actual), OccupancyGrid) == expected
            assert maps == before
            equivalence_count += 1

# Isolate only output conversion plus the real ROS setter, not map algorithms.
raster = np.resize(np.arange(-1, 101, dtype=np.int16), (32, 48))
expected_bytes = raster.astype(np.int8).tobytes()
iterations, trials = 100, {'legacy_list': [], 'packed_array': []}
for trial in range(5):
    order = ('legacy_list', 'packed_array') if trial % 2 == 0 else ('packed_array', 'legacy_list')
    for mode in order:
        message = OccupancyGrid()
        started = time.perf_counter_ns()
        for _ in range(iterations):
            message.data = (raster.ravel().tolist() if mode == 'legacy_list'
                            else array('b', raster.astype(np.int8).tobytes()))
        elapsed = time.perf_counter_ns() - started
        assert message.data.tobytes() == expected_bytes
        trials[mode].append(elapsed)

result = {'schema': 'mr3-map-packing-synthetic-cpu-v1', 'passed': True,
    'classification': 'tiny pure-map fixtures and local setter mechanism only',
    'legacy_source_sha256': hashlib.sha256(legacy_raw).hexdigest(),
    'current_source_sha256': hashlib.sha256(Path(current.__file__).read_bytes()).hexdigest(),
    'exact_whole_message_and_data_byte_comparisons': equivalence_count,
    'input_mutation': False, 'native_runs': 0, 'world_episodes': 0,
    'setter_timing': {'shape': list(raster.shape), 'iterations_per_trial': iterations,
        'trials_ns': trials,
        'median_batch_ns': {key: statistics.median(value) for key, value in trials.items()},
        'scope': 'not whole-step or qualified training throughput; no extrapolated speedup'}}
(DIRECTORY / 'packing_mechanism_result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result, indent=2))
