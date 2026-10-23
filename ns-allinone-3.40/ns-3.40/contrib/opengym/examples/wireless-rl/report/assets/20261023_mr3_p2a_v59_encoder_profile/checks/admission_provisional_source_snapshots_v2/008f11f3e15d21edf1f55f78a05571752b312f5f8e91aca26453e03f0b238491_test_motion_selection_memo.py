"""Exercise the real private memo against the uncached raw-selection functions."""

import ast
from collections import deque
import copy
import inspect
import unittest

from mr3_learning import audit_motion as base


def selection(memoized, sources, histories, sequences, *, causal=True):
    count, selected_dicts = [0], []
    env = dict(base.__dict__)
    raw, own = base.causal_own_inputs, base.own_state

    def tracked(histories, sequences, target):
        count[0] += 1
        return raw(histories, sequences, target)

    def record(name, selected, selected_sequences, epoch, tracker, target, **options):
        selected_dicts.append(dict(selected_sequences))
        return own(name, selected, selected_sequences, epoch, tracker, target, **options)

    if memoized:
        # Exercise the production closure without adding a production testing API
        # or copying its cache implementation into this test.
        outer = ast.parse(inspect.getsource(base._audit_records)).body[0]
        cache = next(node for node in outer.body if isinstance(node, ast.Assign)
                     and any(isinstance(target, ast.Name) and target.id == "own_selection_cache"
                             for target in node.targets))
        selected = next(node for node in outer.body if isinstance(node, ast.FunctionDef)
                        and node.name == "selected_own")
        arguments = ast.arguments(posonlyargs=[], args=[ast.arg(arg=name) for name in
            ("sources", "histories", "sequences", "epoch", "causal_selection", "full_velocity")],
            kwonlyargs=[], kw_defaults=[], defaults=[])
        factory = ast.FunctionDef(name="factory", args=arguments,
            body=[copy.deepcopy(cache), copy.deepcopy(selected),
                  ast.Return(value=ast.Name(id="selected_own", ctx=ast.Load()))], decorator_list=[])
        module = ast.fix_missing_locations(ast.Module(body=[factory], type_ignores=[]))
        env.update(causal_own_inputs=tracked, own_state=record)
        exec(compile(module, "<production-selected-own>", "exec"), env)
        fn = env["factory"](sources, histories, sequences, "cpu", causal, True)
    else:
        def fn(name, target, tracker=None):
            selected, selected_sequences = sources[name], sequences[name]
            if causal:
                selected, selected_sequences = tracked(histories[name], sequences[name], target)
            return record(name, selected, selected_sequences, "cpu", tracker, target,
                          full_velocity=True)
    return fn, count, selected_dicts


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
        return f, selection(False, *f, causal=causal), selection(True, *f, causal=causal)

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


if __name__ == "__main__":
    unittest.main()
