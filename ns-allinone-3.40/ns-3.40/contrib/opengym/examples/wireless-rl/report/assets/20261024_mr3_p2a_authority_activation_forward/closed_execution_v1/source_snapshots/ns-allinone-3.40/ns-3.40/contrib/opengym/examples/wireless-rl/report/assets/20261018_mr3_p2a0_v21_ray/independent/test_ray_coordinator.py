"""Focused V21 new seams only; no repeats of old14, SDK, DDS, Gazebo or native."""
import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import tarfile
import unittest
from unittest import mock

HERE=Path(__file__).parent

def load(name):
    spec=importlib.util.spec_from_file_location(name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


class RayCoordinator(unittest.TestCase):
    def setUp(self):
        self.parent=load('mr3_p2a0_v21_ray_run_v1')
        self.pre=load('mr3_p2a0_v21_ray_preflight_v1')
        plan_path=HERE/'predeclared_plan_v21_ray.json'
        if not plan_path.exists():plan_path=HERE.parent/'predeclared_plan_v21_ray.json'
        self.plan=json.loads(plan_path.read_bytes())
        self.temp=tempfile.TemporaryDirectory(prefix='mr3_v21_ray_coordinator_CPU_')
        self.addCleanup(self.temp.cleanup);self.directory=Path(self.temp.name)

    def test_pending_actual_main_rejects_before_lock_config_or_child(self):
        (self.directory/'predeclared_plan_v21_ray.json').write_text(json.dumps(self.plan))
        with mock.patch.object(self.parent,'A',self.directory),mock.patch.object(sys,'argv',['parent','a'*40]),mock.patch.object(self.parent,'run_child') as child:
            with self.assertRaisesRegex(ValueError,'not ready'):self.parent.main()
            child.assert_not_called()
        self.assertEqual([p.name for p in self.directory.iterdir()],['predeclared_plan_v21_ray.json'])

    def test_exact_workload_budget_and_unknown_flags_refused(self):
        ready=copy.deepcopy(self.plan);ready.update(status='ready',pending=[],new_source_bindings_pending=[])
        self.pre.validate_sensor_plan(ready)
        for update in ('domain','steps','budget','flag'):
            changed=copy.deepcopy(ready)
            if update=='domain':changed['stages'][0]['domain']=170
            elif update=='steps':changed['stages'][0]['steps']=32
            elif update=='budget':changed['budget']['max_native_launcher_wall_seconds']=900.
            else:changed['stages'][0]['command']+=['--preparation-motion-probe']
            with self.subTest(update=update),self.assertRaises(ValueError):self.pre.validate_sensor_plan(changed)

    def test_actual_runtime103_dict_normalization_retains_every_sha(self):
        fixture=Path('/tmp/mr3_p2a0_v20_sensor_coordinator_proposal_v2/source_preflight_941ae862_original.json')
        if fixture.exists():raw=fixture.read_bytes()
        else:
            archive=Path('/home/zhuyulab/ns3-workspace/ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v20_sensor/offline/coordinator_v2/originals.tar.gz')
            with tarfile.open(archive) as stream:
                members=[m for m in stream.getmembers() if m.name.endswith('/source_preflight_941ae862_original.json')]
                self.assertEqual(len(members),1);raw=stream.extractfile(members[0]).read()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'69da6d8c53e64db67e6411e93add0b405a4a8ac2f01a527ce915c7b5f8db57b1')
        preflight=json.loads(raw);plan=self.plan
        self.assertEqual(len(preflight['source_bindings']),103)
        tree=ast.parse((HERE/'mr3_p2a0_v21_ray_run_v1.py').read_text())
        main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        assignment=next(n for n in main.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='bindings' for t in n.targets))
        namespace={'plan':plan,'preflight':preflight}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[assignment],type_ignores=[])),'actual_parent_binding_assignment','exec'),namespace)
        rows=namespace['bindings']
        self.assertEqual(rows[:len(plan['independent_source_bindings'])],plan['independent_source_bindings'])
        self.assertEqual(rows[len(plan['independent_source_bindings']):],
          [{'path':p,'sha256':v['sha256']} for p,v in preflight['source_bindings'].items()])
        self.assertEqual(len(rows),len(plan['independent_source_bindings'])+103)

    def write_streams(self):
        expected={'source_sha256':'a'*64,'installed_resolved_path':'/fixed/ray.so','process_id':123,'world_name':'p1c_open'}
        for robot in ('tb1','tb2','tb3'):
            common={'schema':'mr3-ray-provenance-audit-v1','epoch':'CPU_epoch','robot':robot,'process_id':123}
            ray={'index':0,'cached_length':1.,'geometry_range':1.12,'current_shortened_ray':True,
                 'cached_collision_name':'a::link::collision','collision_name_current_hit_valid':True,
                 'relative_start':[0.,0.,0.],'relative_end_after_collision':[1.,0.,0.],
                 'global_cast_start':[0.,0.,0.],'global_cast_end_before_collision':[3.,0.,0.],
                 'final_sensor_range':1.12}
            rows=[{**common,'kind':'configuration','record_sequence':1,'plugin_type':'SensorPlugin',
                   'compiled_source_sha256':'a'*64,'loaded_library_path':'/fixed/ray.so',
                   'world_name':'p1c_open','model_name':robot,'model_scoped_name':robot,
                   'sensor_link':'base_scan','sensor_name':'hls_lfcd_lds'},
                  {**common,'kind':'sensor_connected','record_sequence':2,'sensor_parent':robot+'::base_scan',
                   'sensor_scoped_name':'p1c_open::'+robot+'::base_scan::hls_lfcd_lds','ray_count':360},
                  {**common,'kind':'scan','record_sequence':3,'scan_sequence':1,'measurement_time_ns':200000000,
                   'sensor_parent':robot+'::base_scan',
                   'sensor_scoped_name':'p1c_open::'+robot+'::base_scan::hls_lfcd_lds',
                   'ray_count':360,'range_count':360,'final_range_one_to_one':True,
                   'rays':[{**ray,'index':i} for i in range(360)]}]
            (self.directory/f'ray_{robot}.jsonl').write_bytes(b''.join((json.dumps(row)+'\n').encode() for row in rows))
        return expected

    def test_basic_measurement_full_sha_three_streams_and_missing_rejected(self):
        expected=self.write_streams()
        result=self.parent.ray_availability(self.directory,'CPU_epoch',expected)
        self.assertTrue(result['passed'])
        for robot,report in result['robots'].items():
            raw=(self.directory/f'ray_{robot}.jsonl').read_bytes()
            self.assertEqual(report['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(report['bytes'],len(raw));self.assertEqual(report['scans'],1)
        (self.directory/'ray_tb2.jsonl').unlink()
        self.assertFalse(self.parent.ray_availability(self.directory,'CPU_epoch',expected)['passed'])

    def test_basic_measurement_bad_json_identity_partial_scan_error_fullhash_retained(self):
        for mutation in ('json','epoch','pid','partial','error'):
            expected=self.write_streams();path=self.directory/'ray_tb1.jsonl';rows=path.read_bytes().splitlines()
            if mutation=='json':rows[1]=b'{invalid JSON}'
            elif mutation=='error':
                value=json.loads(rows[-1]);value.update(kind='diagnostic_error',error='write_failed');rows[-1]=json.dumps(value).encode()
            else:
                value=json.loads(rows[-1])
                if mutation=='epoch':value['epoch']='other'
                elif mutation=='pid':value['process_id']=124
                else:value['rays']=value['rays'][:-1]
                rows[-1]=json.dumps(value).encode()
            raw=b'\n'.join(rows)+b'\n';path.write_bytes(raw)
            result=self.parent.ray_availability(self.directory,'CPU_epoch',expected)
            with self.subTest(mutation=mutation):
                self.assertFalse(result['passed'])
                self.assertEqual(result['robots']['tb1']['sha256'],hashlib.sha256(raw).hexdigest())
                self.assertTrue(result['robots']['tb1']['stat_stable'])


    def test_wrong_parent_scope_or_scan_drift_refused_with_full_stream_hash(self):
        for row_index, field, value in [(1,'sensor_parent','tb1::base_scan'),
                                        (1,'sensor_scoped_name','tb2::base_scan::hls_lfcd_lds'),
                                        (2,'sensor_parent','tb1::base_scan'),
                                        (2,'sensor_scoped_name','other::tb2::base_scan::hls_lfcd_lds'),
                                        (0,'world_name','wrong_world'),
                                        (0,'model_name','tb1'),
                                        (0,'model_scoped_name','other::tb2'),
                                        (0,'sensor_link','base_link'),
                                        (0,'sensor_name','other')]:
            expected=self.write_streams();path=self.directory/'ray_tb2.jsonl'
            rows=[json.loads(line) for line in path.read_bytes().splitlines()]
            rows[row_index][field]=value
            raw=b''.join((json.dumps(row)+'\n').encode() for row in rows);path.write_bytes(raw)
            result=self.parent.ray_availability(self.directory,'CPU_epoch',expected)
            with self.subTest(row=row_index,field=field):
                self.assertFalse(result['passed'])
                self.assertEqual(result['robots']['tb2']['sha256'],hashlib.sha256(raw).hexdigest())
                self.assertTrue(result['robots']['tb2']['stat_stable'])


if __name__=='__main__':unittest.main()
