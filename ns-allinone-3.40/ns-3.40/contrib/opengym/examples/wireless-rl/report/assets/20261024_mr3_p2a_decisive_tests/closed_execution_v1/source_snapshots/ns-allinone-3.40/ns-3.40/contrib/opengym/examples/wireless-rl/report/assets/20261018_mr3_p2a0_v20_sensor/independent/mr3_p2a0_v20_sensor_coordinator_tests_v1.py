"""No ROS/Gazebo: tiny owned fake children plus immutable small profile predicate."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).parent


def load(name):
    path=ROOT/name
    spec=importlib.util.spec_from_file_location(path.stem,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


RUN=load('mr3_p2a0_v20_sensor_run_v1.py')
PRE=load('mr3_p2a0_v20_sensor_preflight_v1.py')
FREEZE='1'*40
SOURCE='2'*64
FAKE=r"""import hashlib,json,os,pathlib,sys,time
mode=sys.argv[1]
if mode=='recorder':
 config=json.loads(pathlib.Path(sys.argv[2]).read_bytes());case=sys.argv[3]
 ready={'schema':'mr3-startup-sensor-recorder-ready-v1','ready':True,'run_directory':config['run_directory'],'output_directory':config['output_directory'],'expected_freeze':config['expected_freeze'],'config_sha256':hashlib.sha256(pathlib.Path(sys.argv[2]).read_bytes()).hexdigest(),'compiled_source_sha256':('3'*64 if case=='bad_ready' else '2'*64),'process_id':os.getpid(),'subscriptions':[{'topic':'/fake'+str(i),'type':'fake','qos':{}} for i in range(22)],'epoch_binding':'awaiting_worker_metadata','stop_marker':config['stop_marker']}
 pathlib.Path(config['output_directory']).mkdir()
 raw=json.dumps(ready,indent=2)+'\n'
 with pathlib.Path(config['ready_path']).open('x') as output:
  output.write(raw[:2]);output.flush()
  if case=='partial_ready':time.sleep(.08)
  output.write(raw[2:]);output.flush()
 deadline=time.monotonic()+.8
 while not pathlib.Path(config['stop_marker']).exists() and time.monotonic()<deadline:time.sleep(.01)
 normal=pathlib.Path(config['stop_marker']).exists()
 final={'schema':'mr3-startup-sensor-recorder-final-v1','capture_completed':normal,'normal_stop':normal,'failed':not normal,'epoch':'e','records':0,'samples':0,'topic_counts':{'/tf':0,'/tb1/tf':0},'parameter_states':{'tb1':'unavailable','tb2':'unavailable','tb3':'unavailable'},'cdr_bytes':0,'unbound_epoch_samples':0,'source_sha256':('4'*64 if case=='bad_final' else '2'*64),'source_scope':'CPU fake process only'}
 pathlib.Path(config['output_directory'],'final.json').write_text(json.dumps(final)+'\n')
 raise SystemExit(0 if normal else 1)
if mode=='benchmark':
 directory=pathlib.Path(sys.argv[2]);case=sys.argv[3];directory.mkdir()
 episode=directory/'worker0/episode001_open_101';episode.mkdir(parents=True)
 (episode/'metadata.json').write_text(json.dumps({'freeze':'1'*40,'epoch':'e'})+'\n')
 count=2 if case in ('early_terminal','short_no_terminal') else 4
 terminated=case=='early_terminal';truncated=case!='early_terminal' and case!='short_no_terminal'
 reason='navigation_failure' if terminated else ('running' if not truncated else 'external_truncation')
 rows=[{'kind':'reset','terminated':False,'truncated':False,'info':{'epoch':'e','reason':'running'}}]
 for i in range(count):rows.append({'kind':'step','terminated':terminated if i==count-1 else False,'truncated':truncated if i==count-1 else False,'info':{'epoch':'e','reason':reason if i==count-1 else 'running'}})
 (episode/'transitions.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in rows))
 passed=case not in ('early_terminal','short_no_terminal')
 summary={'passed':passed,'freeze':'1'*40,'workers':1,'steps_per_episode':4,'valid_transitions':count,'preparation_motion_probe':False,'preparation_parameter_review':False,'workers_results':[{'error':None,'episodes':[{'epoch':'e','transitions':count,'terminated':terminated,'truncated':truncated,'reason':reason}]}]}
 (directory/'benchmark_summary.json').write_text(json.dumps(summary)+'\n')
 time.sleep(.1)
 raise SystemExit(1 if case in ('bad_benchmark','early_terminal','short_no_terminal') else 0)
if mode=='physical':
 path=pathlib.Path(sys.argv[2]);case=sys.argv[3]
 path.write_text(json.dumps({'passed':False,'episodes':[{'closure':{'passed':case!='bad_closure'}}]})+'\n')
 raise SystemExit(1)
"""


class SensorCoordinatorTests(unittest.TestCase):
    def plan(self,case='ok'):
        base=Path(self.directory.name)
        fake=base/'fake.py';fake.write_text(FAKE)
        run=base/'run'
        configuration={'schema':'mr3-startup-sensor-capture-config-v1','run_directory':str(run),
                       'episode_relative_directory':'worker0/episode001_open_101','output_directory':str(base/'capture'),
                       'ready_path':str(base/'ready.json'),'stop_marker':str(base/'stop.json'),
                       'expected_freeze':'{freeze}','expected_domain_id':170,'wall_guard_sec':1000,
                       'max_cdr_bytes':268435456,'max_records':1000000,'parameter_wall_guard_sec':20}
        template=base/'template.json';template.write_text(json.dumps(configuration,indent=2)+'\n')
        plan={'stages':[{'stage':'iters150','run_directory':str(run),
                        'command':[sys.executable,'-B',str(fake),'benchmark',str(run),case],
                        'diagnostic_consumers':[{'label':'original_physical_4step','required_capture_success':False,
                         'output':str(base/'physical.json'),'command':[sys.executable,'-B',str(fake),'physical',str(base/'physical.json'),case]}]}],
              'recorder_contract':{'source_sha256':SOURCE,'config_template_binding':{'path':str(template)},
               'config_runtime_path':str(base/'runtime.json'),'ready_wait_wall_seconds':.6,
               'manifest_path':str(base/'capture/final.json'),
               'command':[sys.executable,'-B',str(fake),'recorder','{config}',case]},
              'e61c_consumer':{'status':'SKIP','reason':'explicit4step CPU fake'},'transport':{}}
        path=base/'plan.json';path.write_text(json.dumps(plan)+'\n')
        return plan,path,base

    def setUp(self):
        self.directory=tempfile.TemporaryDirectory(prefix='mr3_v20_sensor_cpu_')
        self.addCleanup(self.directory.cleanup)

    def execute(self,case='ok',changed=False):
        plan,path,base=self.plan(case)
        old=RUN.verify_profile_subset
        RUN.verify_profile_subset=lambda _: {'passed':True,'scope':'Lifecycle CPU fake only; profile separately actual predicate tested.'}
        self.addCleanup(setattr,RUN,'verify_profile_subset',old)
        def witness(*args):
            p=base/'fake_witness.json';p.write_text(json.dumps({'passed':True})+'\n')
            return p,{'passed':True}
        count=[0]
        def unchanged():
            count[0]+=1
            if changed and count[0]>=3:raise ValueError('synthetic source changed')
        live=SimpleNamespace(identity=lambda pid:{'pid':pid,'start_ticks':1},witness=witness)
        result=RUN.execute_capture(plan,FREEZE,path,{'path':'CPU-preflight','sha256':'5'*64},
                                   unchanged,live,prefix=base/'result',cwd=base)
        return result,base

    def test_normal_close_keeps_physical_false_and_missing_alias_availability(self):
        result,base=self.execute()
        self.assertTrue(result['capture_process_completed'])
        self.assertFalse(result['original_physical_passed'])
        self.assertEqual(result['measurement_availability']['topic_counts'],{'/tf':0,'/tb1/tf':0})
        self.assertEqual(result['measurement_availability']['parameter_states']['tb1'],'unavailable')
        events=[json.loads(row) for row in (base/'result_lifecycle_v1.jsonl').read_text().splitlines()]
        kinds=[row['kind'] for row in events]
        self.assertLess(kinds.index('recorder_ready_received'),kinds.index('benchmark_started_after_recorder_ready'))
        self.assertLess(kinds.index('benchmark_naturally_closed'),kinds.index('exclusive_stop_marker_after_benchmark_closed'))

    def test_partial_ready_json_is_pending_until_complete(self):
        result,_=self.execute('partial_ready');self.assertTrue(result['passed'])

    def test_real_early_terminal_keeps_original_benchmark_false_without_capture_error(self):
        result,_=self.execute('early_terminal')
        self.assertTrue(result['capture_process_completed'])
        self.assertFalse(result['actual_workload']['original_benchmark_passed'])
        self.assertEqual(result['actual_workload']['actual_returned_steps'],2)
        self.assertEqual(result['actual_workload']['actual_saved_api_records'],3)
        self.assertEqual(result['benchmark_returncode'],1)

    def test_short_without_protocol_terminal_is_not_completed(self):
        result,_=self.execute('short_no_terminal');self.assertFalse(result['passed'])
        self.assertTrue(any('short workload' in error for error in result['errors']))

    def test_bad_ready_never_launches_native_and_no_false_stop_marker(self):
        result,base=self.execute('bad_ready')
        self.assertFalse(result['passed']);self.assertFalse((base/'run').exists())
        self.assertFalse((base/'stop.json').exists())
        self.assertNotIn('original_physical_4step',result)

    def test_benchmark_failure_is_preserved_and_recorder_stops_naturally(self):
        result,base=self.execute('bad_benchmark')
        self.assertFalse(result['passed']);self.assertEqual(result['benchmark_returncode'],1)
        self.assertEqual(result['recorder_returncode'],0);self.assertTrue((base/'stop.json').exists())

    def test_recorder_final_identity_failure_rejected(self):
        result,_=self.execute('bad_final');self.assertFalse(result['passed'])
        self.assertTrue(any('final source differs' in error for error in result['errors']))

    def test_strict_closure_failure_not_hidden_by_scientific_fail_scope(self):
        result,_=self.execute('bad_closure');self.assertFalse(result['passed'])
        self.assertTrue(any('strict native closure' in error for error in result['errors']))

    def test_changed_source_is_sticky_after_children_close(self):
        result,_=self.execute(changed=True);self.assertFalse(result['passed'])
        self.assertEqual(result['benchmark_returncode'],0);self.assertEqual(result['recorder_returncode'],0)
        self.assertTrue(any('source changed' in error for error in result['errors']))

    def test_draft_hard_rejects_and_exact4step_command_rejects_probe(self):
        plan=json.loads((ROOT/'predeclared_plan_v20_sensor.json').read_bytes())
        with self.assertRaisesRegex(ValueError,'not ready'):PRE.validate_sensor_plan(plan)
        plan.update(status='ready',pending=[],new_source_bindings_pending=[])
        PRE.validate_sensor_plan(plan)
        plan['stages'][0]['command'].append('--preparation-motion-probe')
        with self.assertRaisesRegex(ValueError,'ordinary four-step'):PRE.validate_sensor_plan(plan)

    def test_resource_scan_rejects_port_and_domain_without_dds(self):
        proc=Path(self.directory.name)/'proc';(proc/'net').mkdir(parents=True)
        (proc/'net/udp').write_text('header\n')
        (proc/'net/tcp').write_text('header\n')
        self.assertEqual(PRE.check_unused_resources(proc)['socket_conflicts'],[])
        (proc/'net/tcp').write_text('header\n0: 0100007F:348B 00000000:0000 0A\n')
        with self.assertRaisesRegex(ValueError,'occupied'):PRE.check_unused_resources(proc)
        (proc/'net/tcp').write_text('header\n');(proc/'123').mkdir();(proc/'123/environ').write_bytes(b'ROS_DOMAIN_ID=170\0')
        with self.assertRaisesRegex(ValueError,'occupied'):PRE.check_unused_resources(proc)

    def test_frozen_transport_not_inherited_conda_or_diagnostic_profile(self):
        transport=json.loads((ROOT/'predeclared_plan_v20_sensor.json').read_bytes())['transport']
        actual=RUN.transport_environment({'CONDA_PREFIX':'bad','PYTHONPATH':'bad',
            'MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE':'old','FASTDDS_DEFAULT_PROFILES_FILE':'bad'},transport,system=True)
        self.assertNotIn('CONDA_PREFIX',actual);self.assertNotIn('PYTHONPATH',actual)
        self.assertNotIn('MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE',actual)
        self.assertNotIn('FASTDDS_DEFAULT_PROFILES_FILE',actual)
        self.assertEqual(actual['ROS_LOCALHOST_ONLY'],'0');self.assertEqual(actual['ROS_DOMAIN_ID'],'170')

    def test_actual_immutable_profile_leaf_no32step_gate(self):
        path=Path('/tmp/mr3_p2a0_v19_iters150_live_witness/admission_proof.json')
        result=RUN.verify_profile_subset(path)
        self.assertTrue(result['passed']);self.assertEqual(result['setter_call_count'],1)
        self.assertEqual(result['before']['native_ode']['iters'],50)
        self.assertEqual(result['after']['native_ode']['iters'],150)
        self.assertIn('not e61c CLI',result['scope'])

    def test_actual_profile_leaf_rejects_other_parameter_mutation(self):
        base=Path(self.directory.name)
        original=json.loads(Path('/tmp/mr3_p2a0_v19_iters150_live_witness/admission_proof.json').read_bytes())
        raw=Path(original['profile']['ledger_path']).read_bytes();row=json.loads(raw)
        row['after']['native_ode']['erp']=.3
        changed=base/'profile.jsonl';changed.write_text(json.dumps(row)+'\n')
        original['profile']['ledger_path']=str(changed)
        original['profile']['ledger_sha256']=hashlib.sha256(changed.read_bytes()).hexdigest()
        proof=base/'proof.json';proof.write_text(json.dumps(original)+'\n')
        with self.assertRaisesRegex(ValueError,'changed_more_than_iters'):
            RUN.verify_profile_subset(proof)


if __name__=='__main__':unittest.main()
