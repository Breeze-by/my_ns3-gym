"""New preInit metadata boundary only; no old suite, SDK, ROS or native."""
from pathlib import Path
import ast
import copy
import hashlib
import importlib.util
import unittest

B = Path(__file__).resolve().parent
P = B / 'mr3_v24_corrector_custody_v3.py'
spec = importlib.util.spec_from_file_location('v24_preinit_custody', P)
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

class PreInitBoundary(unittest.TestCase):
    def setUp(self):
        self.binding = {'sources': {key: {'sha256': str(i)*64} for i, key in enumerate(h.SOURCE_FIELDS)},
                        'library': {'resolved': '/fixed/corrector.so'},
                        'ode_library': {'resolved': '/fixed/ode.so'}}
        common = {'schema': 'mr3-ray-box-corrector-audit-v1', 'epoch': 'synthetic_epoch', 'process_id': 300}
        config = dict(common, kind='configuration', plugin_type='SystemPlugin',
                      loaded_library_path='/fixed/corrector.so', actual_ode_library_path='/fixed/ode.so',
                      **{key: value['sha256'] for key, value in self.binding['sources'].items()})
        install = dict(common, kind='installed', world='p1c_open', world_clock_ns=0,
                       installation_phase='world_created_during_load_before_world_init',
                       world_iterations=None, world_iterations_available=False,
                       world_iterations_unavailable_reason='counter_initialized_only_in_World_Init',
                       world_lookup_succeeded=True, physics_available=True, physics_type='ode',
                       native_ode_world_available=True, failed_preconditions=[],
                       world_load_completed=False, world_sensors_initialized=False,
                       model_sensor_count=0, world_running_getter=True,
                       registered_pair=['dRayClass', 'dBoxClass'],
                       native_ode_quickstep_iterations=150, physics_max_step_size_sec=.001)
        counts = dict(callback_calls=20, hits=2, misses=18, nonzero_nearparallel_calls=1, callback_errors=0)
        self.rows = [config, install, dict(common, kind='plugin_destructor_snapshot', **counts),
                     dict(common, kind='process_lifetime_summary', **counts)]

    def review(self, rows=None):
        rows = self.rows if rows is None else rows
        raw = b''.join(h.canonical(row)+b'\n' for row in rows)
        return h.ledger_review(raw, self.binding, 'synthetic_epoch', 300, 'p1c_open',
                               h.sha(h.canonical(rows[0])+b'\n'))

    def reject_install(self, changes):
        for key, value in changes:
            with self.subTest(key=key, value=value):
                rows = copy.deepcopy(self.rows)
                rows[1][key] = value
                with self.assertRaises((ValueError, KeyError)):
                    self.review(rows)

    def test_preinit_records_null_without_promoting_running_getter_to_false_gate(self):
        for value in (True, False):
            self.rows[1]['world_running_getter'] = value
            result = self.review()
            self.assertTrue(result['passed'])
            self.assertIsNone(result['installed']['world_iterations'])
            self.assertIs(result['installed']['world_iterations_available'], False)
            self.assertIs(result['installed']['world_running_getter'], value)

    def test_exact_phase_and_unavailable_counter_no_zero_fallback(self):
        self.reject_install([('installation_phase', 'world_init'), ('world_iterations', 0),
                             ('world_iterations', False), ('world_iterations_available', 0),
                             ('world_iterations_available', True),
                             ('world_iterations_unavailable_reason', 'unknown')])
        for key in ('installation_phase', 'world_iterations_available', 'world_iterations_unavailable_reason'):
            rows = copy.deepcopy(self.rows)
            del rows[1][key]
            with self.assertRaises((ValueError, KeyError)):
                self.review(rows)

    def test_defined_preinit_guards_and_typed_no_sensor_count(self):
        self.reject_install([('world_lookup_succeeded', False), ('world_lookup_succeeded', 1),
                             ('physics_available', False), ('native_ode_world_available', False),
                             ('physics_type', 'bullet'), ('failed_preconditions', ['missing']),
                             ('failed_preconditions', False), ('world_load_completed', True), ('world_load_completed', 0),
                             ('world_sensors_initialized', True), ('world_sensors_initialized', 0),
                             ('model_sensor_count', 1), ('model_sensor_count', False),
                             ('world_clock_ns', 1), ('world_clock_ns', False),
                             ('world_running_getter', 0), ('world_running_getter', None)])

    def test_original_native_readback_and_counter_failures_still_reject(self):
        self.reject_install([('native_ode_quickstep_iterations', 50),
                             ('native_ode_quickstep_iterations', 150.0),
                             ('physics_max_step_size_sec', .002),
                             ('physics_max_step_size_sec', float('nan')),
                             ('registered_pair', ['dRayClass', 'dSphereClass'])])
        for key, value in [('callback_errors', 1), ('callback_calls', 0), ('callback_calls', False)]:
            rows = copy.deepcopy(self.rows)
            rows[-1][key] = value
            with self.assertRaises(ValueError):
                self.review(rows)

    def test_original_closed_order_source_and_identity_still_reject(self):
        for index, key, value in [(0, 'compiled_source_sha256', 'f'*64),
                                  (1, 'process_id', True), (1, 'epoch', 'other')]:
            rows = copy.deepcopy(self.rows)
            rows[index][key] = value
            with self.assertRaises(ValueError):
                self.review(rows)
        with self.assertRaises(ValueError):
            self.review(self.rows[:-1])

    def test_only_exact_predicate_inverse_recovers_old_whole_bytes_and_ast(self):
        original = Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/'
                        'opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v22_ray_box/'
                        'independent/mr3_v22_corrector_custody_v2.py')
        before = original.read_bytes()
        self.assertEqual(hashlib.sha256(before).hexdigest(),
                         '862e5b9aa674258975b5ac913d61125bc4b97d036cd6dec08d6296037619386d')
        final = P.read_text()
        start = "    require(type(install['world_clock_ns'])"
        end = '    snapshots ='
        original_text = before.decode()
        previous = original_text[original_text.index(start):original_text.index(end, original_text.index(start))]
        current = final[final.index(start):final.index(end, final.index(start))]
        self.assertEqual(final.count(current), 1)
        recovered = final.replace(current, previous, 1)
        self.assertEqual(recovered.encode(), before)
        self.assertEqual(ast.dump(ast.parse(recovered)), ast.dump(ast.parse(before)))

if __name__ == '__main__':
    unittest.main(verbosity=2)
