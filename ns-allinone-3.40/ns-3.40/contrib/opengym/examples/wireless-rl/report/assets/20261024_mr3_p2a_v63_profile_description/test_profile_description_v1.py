"""Two short artificial groups; never open either original saved profile."""
import copy
import cProfile
import hashlib
import json
from pathlib import Path
import tempfile
import time
import unittest

import describe_partial_profiles_v1 as reader

HERE = Path(__file__).resolve().parent


class ProfileDescriptionTests(unittest.TestCase):
    def test_whole_module_bound_original_function_describes_only_synthetic_pstats(self):
        source = Path(reader.OLD_SOURCE['path']).read_bytes()
        function = reader.old_description_function(source)
        self.assertEqual(function.__code__.co_filename, reader.OLD_SOURCE['path'])
        self.assertEqual(function.__code__.co_firstlineno, 68)
        with tempfile.TemporaryDirectory(prefix='v63-synthetic-profile-') as name:
            path = Path(name)/'synthetic.pstats'
            profile = cProfile.Profile()
            profile.runcall(sum, range(15))
            profile.dump_stats(path)
            raw = path.read_bytes()
            description = function(raw)
            self.assertGreater(description['function_count'], 0)
            self.assertTrue(description['top_self'])
            self.assertEqual(description['timing_scope'],
                'cProfile function elapsed time; waiting included; cumulative rows overlap; not CPU or C++ kernel decomposition')
            bound = dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
            reads = reader.Reads(time.monotonic_ns())
            self.assertEqual(reads.read(bound,profile=True),raw)
            reads.finish()
            self.assertEqual(reads.profile_bytes,len(raw))
            self.assertEqual(len(reads.bindings),1)
        with self.assertRaises(ValueError):
            reader.old_description_function(source+b'\n')

    def test_pending_limits_pins_inventory_and_extra_profile_reject(self):
        pending=json.loads((HERE/'spec_v1.json').read_text())
        pending['admitted']=False  # Artificial negative remains valid after canonical admission.
        with self.assertRaisesRegex(ValueError,'not admitted'):
            reader.validate_spec(pending)
        admitted=copy.deepcopy(pending)
        admitted['admitted']=True
        admitted['closed_inventory'].update(bytes=1,sha256='a'*64)
        reader.validate_spec(admitted)
        mutations=[('extra',lambda value:value['profiles'].append(copy.deepcopy(value['profiles'][0]))),
                   ('float_pin',lambda value:value['profiles'][0].update(bytes=402910.0)),
                   ('missing_inventory',lambda value:value['closed_inventory'].update(sha256=None)),
                   ('raised_work',lambda value:value['resource'].update(work_wall_seconds=61)),
                   ('other_path',lambda value:value['profiles'][0].update(path='/tmp/other.pstats'))]
        for name,mutate in mutations:
            with self.subTest(name=name):
                value=copy.deepcopy(admitted);mutate(value)
                with self.assertRaises(ValueError):reader.validate_spec(value)
        entries=[dict(original=row['path'],original_bytes=row['bytes'],original_sha256=row['sha256'])
                 for row in reader.PROFILES]
        inventory=dict(schema='mr3-v62-opaque-closed-inventory-v1',entries=entries)
        self.assertEqual(len(reader.inventory_members(inventory)),2)
        inventory['entries'][0]['original_sha256']='0'*64
        with self.assertRaises(ValueError):reader.inventory_members(inventory)


if __name__=='__main__':
    unittest.main()
