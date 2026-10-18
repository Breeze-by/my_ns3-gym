"""CPU-only proof and differential fixtures for a bounded raw-selection memo."""
from collections import deque
import copy
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import time
from types import ModuleType
import unittest
ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
FREEZE = '2500e9e7837a9efc208772d5dc6cf0373ebcb551'
REL = str((W / 'mr3_learning/audit_motion.py').relative_to(ROOT))
OLD = '    def selected_own(name, target, tracker=None):\n        selected, selected_sequences = sources[name], sequences[name]\n        if causal_selection:\n            selected, selected_sequences = causal_own_inputs(\n                histories[name], sequences[name], target)\n        return own_state(name, selected, selected_sequences, epoch, tracker, target,\n                         full_velocity=full_velocity)\n'
NEW = '    own_selection_cache = {}\n\n    def selected_own(name, target, tracker=None):\n        selected, selected_sequences = sources[name], sequences[name]\n        if causal_selection:\n            key = (name, target, tuple(sequences[name].items()))\n            cached = own_selection_cache.get(name)\n            if cached is None or cached[0] != key:\n                cached = (key, causal_own_inputs(histories[name], sequences[name], target))\n                own_selection_cache[name] = cached\n            selected, selected_sequences = cached[1]\n        return own_state(name, selected, selected_sequences, epoch, tracker, target,\n                         full_velocity=full_velocity)\n'

def git_bytes(relative):
    return subprocess.check_output(['git', 'show', FREEZE + ':' + relative], cwd=ROOT)

original = git_bytes(REL).decode()
assert original.count(OLD) == 1
candidate = original.replace(OLD, NEW)
assert candidate.count(NEW) == 1 and candidate.replace(NEW, OLD) == original
assert (ROOT / REL).read_bytes() == original.encode()

def module(source, name):
    m = ModuleType(name)
    m.__file__ = str(ROOT / REL)
    exec(compile(source, m.__file__, 'exec'), m.__dict__)
    return m

base, proposed = module(original, 'original_motion'), module(candidate, 'candidate_motion')

def selection(block, sources, histories, sequences, *, causal=True):
    count, selected_dicts = [0], []
    env = dict(base.__dict__)
    raw, own = base.causal_own_inputs, base.own_state
    def tracked(histories, sequences, target):
        count[0] += 1
        return raw(histories, sequences, target)
    def record(name, selected, selected_sequences, epoch, tracker, target, **kw):
        selected_dicts.append(dict(selected_sequences))
        return own(name, selected, selected_sequences, epoch, tracker, target, **kw)
    env.update(causal_own_inputs=tracked, own_state=record)
    text = 'def factory(sources, histories, sequences, epoch, causal_selection, full_velocity):\n' + block + '    return selected_own\n'
    exec(compile(text, '<exact-selected-own-block>', 'exec'), env)
    return env['factory'](sources, histories, sequences, 'cpu', causal, True), count, selected_dicts


def fixture():
    histories = {name: {stream: deque(maxlen=256) for stream in ('odom', 'tf')} for name in base.ROBOTS}
    sequences = {name: dict.fromkeys(('odom', 'tf', 'request', 'decision'), 0) for name in base.ROBOTS}
    sources = {name: {} for name in base.ROBOTS}
    return sources, histories, sequences


def message(stream, stamp, position=0.):
    sec, nano = divmod(stamp + (200_000_000 if stream == 'tf' else 0), 10**9)
    header = {'stamp': {'sec': sec, 'nanosec': nano}, 'frame_id': 'odom' if stream == 'odom' else 'map'}
    q = {'x': 0., 'y': 0., 'z': 0., 'w': 1.}
    point = {'x': position, 'y': 0., 'z': 0.}
    if stream == 'tf':
        return {'header': header, 'child_frame_id': 'odom', 'transform': {'translation': point, 'rotation': q}}
    return {'header': header, 'child_frame_id': 'base_footprint', 'pose': {'pose': {'position': point, 'orientation': q}},
            'twist': {'twist': {axis: {'x': 0., 'y': 0., 'z': 0.} for axis in ('linear', 'angular')}}}


def append(f, name, stream, stamp, position=0.):
    sources, histories, sequences = f
    sequences[name][stream] += 1
    value = message(stream, stamp, position)
    sources[name][stream] = value
    histories[name][stream].append((sequences[name][stream], value))
    return value


class Differential(unittest.TestCase):
    def paired(self, f=None, causal=True):
        f = fixture() if f is None else f
        return f, selection(OLD, *f, causal=causal), selection(NEW, *f, causal=causal)

    def same(self, old, new, name='tb1', target=10**9, trackers=(None, None)):
        outputs = []
        for (fn, _, _), tracker in zip((old, new), trackers):
            try: outputs.append(('return', fn(name, target, tracker)))
            except Exception as e: outputs.append((type(e).__name__, str(e)))
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(old[2], new[2])
        return outputs[0]

    def test_repeated_complete_inputs_fresh_own_dict_and_no_raw_mutation(self):
        f, old, new = self.paired()
        for stream in ('odom', 'tf'): append(f, 'tb1', stream, 10**9)
        snapshot = copy.deepcopy(f)
        first = self.same(old, new)[1]
        second = self.same(old, new)[1]
        self.assertEqual(first, second); self.assertIsNot(first, second)
        self.assertEqual(old[1][0], 2); self.assertEqual(new[1][0], 1)
        self.assertEqual(f, snapshot)

    def test_request_and_decision_each_invalidate_complete_sequence_result(self):
        f, old, new = self.paired()
        for stream in ('odom', 'tf'): append(f, 'tb1', stream, 10**9)
        self.same(old, new)
        for field in ('request', 'decision'):
            f[2]['tb1'][field] += 1
            self.same(old, new)
            self.assertEqual(new[2][-1][field], f[2]['tb1'][field])
        self.assertEqual(new[1][0], 3)

    def test_same_clock_new_ingress_and_equal_stamp_tie_use_highest_sequence(self):
        f, old, new = self.paired()
        for stream in ('odom', 'tf'): append(f, 'tb1', stream, 10**9)
        self.same(old, new)
        append(f, 'tb1', 'odom', 10**9, 2.)
        result = self.same(old, new)[1]
        self.assertEqual(result['x'], 2.); self.assertEqual(result['input_sequences']['odom'], 2)
        self.assertEqual(new[1][0], 2)

    def test_out_of_order_future_source_and_target_change_preserve_max_eligible(self):
        f, old, new = self.paired()
        append(f, 'tb1', 'tf', 900_000_000)
        for stamp in (10**9, 900_000_000, 1_040_000_000): append(f, 'tb1', 'odom', stamp, stamp / 10**9)
        for target, selected in ((10**9, 1), (950_000_000, 2), (1_040_000_000, 3), (10**9, 1)):
            result = self.same(old, new, target=target)[1]
            self.assertEqual(result['input_sequences']['odom'], selected)
        self.assertEqual(new[1][0], 4)

    def test_bounded_eviction_invalidates_old_highest_stamp(self):
        f, old, new = self.paired()
        append(f, 'tb1', 'tf', 10**9)
        append(f, 'tb1', 'odom', 10**9, 1.)
        for _ in range(255): append(f, 'tb1', 'odom', 900_000_000, .9)
        self.assertEqual(self.same(old, new)[1]['x'], 1.)
        append(f, 'tb1', 'odom', 900_000_000, .8)
        self.assertEqual(self.same(old, new)[1]['x'], .8)
        self.assertEqual(new[1][0], 2)

    def test_invalid_raw_stamp_raises_same_original_error_on_every_attempt(self):
        f, old, new = self.paired()
        for stream in ('odom', 'tf'): append(f, 'tb1', stream, 10**9)
        self.same(old, new)
        bad = append(f, 'tb1', 'odom', 10**9)
        bad['header']['stamp']['nanosec'] = 10**9
        for _ in range(2): self.assertEqual(self.same(old, new), ('ValueError', 'invalid raw source stamp'))
        self.assertEqual(new[1][0], 3)

    def test_absent_or_future_only_input_preserves_none_without_fake_selected_state(self):
        f, old, new = self.paired()
        for _ in range(2): self.assertEqual(self.same(old, new), ('return', None))
        append(f, 'tb1', 'odom', 1_040_000_000)
        append(f, 'tb1', 'tf', 1_040_000_000)
        self.assertEqual(self.same(old, new), ('return', None))
        self.assertEqual(new[1][0], 2)

    def test_certificate_is_rebuilt_on_every_cache_hit(self):
        class Tracker:
            def __init__(self): self.calls = 0
            def certificate(self, clock): self.calls += 1; return {'call': self.calls, 'clock': clock}
        f, old, new = self.paired()
        for stream in ('odom', 'tf'): append(f, 'tb1', stream, 10**9)
        trackers = (Tracker(), Tracker())
        for value in (1, 2): self.assertEqual(self.same(old, new, trackers=trackers)[1]['settled_turn']['call'], value)
        self.assertEqual(new[1][0], 1); self.assertEqual(trackers[1].calls, 2)

    def test_per_robot_entry_is_bounded_and_does_not_share_other_raw_sources(self):
        f, old, new = self.paired()
        for robot, name in enumerate(base.ROBOTS):
            for stream in ('odom', 'tf'): append(f, name, stream, 10**9, robot if stream == 'odom' else 0.)
        for _ in range(2):
            for robot, name in enumerate(base.ROBOTS): self.assertEqual(self.same(old, new, name=name)[1]['x'], robot)
        self.assertEqual(new[1][0], 3)
        cache = dict(zip(new[0].__code__.co_freevars, (c.cell_contents for c in new[0].__closure__)))['own_selection_cache']
        self.assertEqual(set(cache), set(base.ROBOTS)); self.assertEqual(len(cache), 3)

    def test_noncausal_mode_never_uses_memo_or_causal_scanner(self):
        f, old, new = self.paired(causal=False)
        for stream in ('odom', 'tf'): append(f, 'tb1', stream, 10**9)
        self.same(old, new)
        f[0]['tb1']['odom'] = message('odom', 10**9, 2.)
        self.assertEqual(self.same(old, new)[1]['x'], 2.)
        self.assertEqual(new[1][0], 0)


if __name__ == '__main__':
    start = time.monotonic_ns()
    stream = io.StringIO()
    custom = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Differential))
    sys.path.insert(0, str(W))
    tests_relative = str((W / 'mr3_learning/tests/test_audit_motion.py').relative_to(ROOT))
    tests_raw = git_bytes(tests_relative)
    suites = {}
    for label, implementation in (('original', base), ('candidate', proposed)):
        tests = ModuleType('frozen_motion_tests_' + label)
        tests.__file__ = str(ROOT / tests_relative)
        exec(compile(tests_raw, tests.__file__, 'exec'), tests.__dict__)
        tests._audit_records = implementation._audit_records
        result = unittest.TextTestRunner(stream=stream, verbosity=1).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
        suites[label] = {'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors), 'passed': result.wasSuccessful()}
    passed = custom.wasSuccessful() and all(value['passed'] for value in suites.values())
    candidate_path = Path('/tmp/mr3_p2a_v11_audit_motion_memo_candidate_v1.py')
    if passed:
        with candidate_path.open('x') as destination: destination.write(candidate)
    assert (ROOT / REL).read_bytes() == original.encode()
    receipt = {'schema': 'mr3-motion-local-selection-memo-cpu-v1', 'freeze': FREEZE, 'passed': passed,
        'source': REL, 'original_source_sha256': hashlib.sha256(original.encode()).hexdigest(),
        'candidate_source_sha256': hashlib.sha256(candidate.encode()).hexdigest(),
        'candidate_path': str(candidate_path) if passed else None,
        'exact_single_block_inverse_restores_original_bytes': candidate.replace(NEW, OLD) == original,
        'custom_cases': {'tests': custom.testsRun, 'failures': len(custom.failures), 'errors': len(custom.errors)},
        'original_frozen_motion_tests': suites,
        'frozen_motion_tests_sha256': hashlib.sha256(tests_raw).hexdigest(),
        'cache_bound': 'one last entry per existing robot, at most three; key=(name,target,tuple(complete sequences.items()))',
        'unchanged': 'own_state/certificate rebuilt on every call; raw/history/seq guards/errors/math/constants unchanged; only successful causal selection pairs cached',
        'mutation_proof': 'Frozen audit_motion writes raw callback histories only at strict+1 append; JSON rows have no shared object identities. own_state builds new value; actual frozen helper observe writes tracker/sample only, measured_velocity_error/guard_motion read raw. Cached selected maps and sequence copies are never returned directly.',
        'scope': 'Synthetic CPU fixtures and unchanged frozen motion unit tests only, no native/GPU/full audit yet; no positive scientific credit.',
        'wall_seconds': str(Decimal(time.monotonic_ns()-start)/Decimal(10**9)), 'observed_output': stream.getvalue()}
    Path('/tmp/mr3_p2a_v11_motion_memo_cpu_v1.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps({key: receipt[key] for key in ['passed','custom_cases','original_frozen_motion_tests','original_source_sha256','candidate_source_sha256','wall_seconds']}))
    print(stream.getvalue())
    raise SystemExit(0 if passed else 1)
