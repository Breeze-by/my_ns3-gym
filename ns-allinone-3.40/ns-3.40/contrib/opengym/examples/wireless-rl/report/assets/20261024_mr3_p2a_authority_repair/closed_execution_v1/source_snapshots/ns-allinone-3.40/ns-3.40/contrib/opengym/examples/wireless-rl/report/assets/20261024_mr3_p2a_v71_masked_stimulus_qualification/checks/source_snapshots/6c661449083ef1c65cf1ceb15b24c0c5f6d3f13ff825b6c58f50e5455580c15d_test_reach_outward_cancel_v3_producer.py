"""Artificial received lifecycle with actual dispatcher and canonical masks."""
import copy
import ast
import hashlib
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import unittest

from mr3_learning import benchmark, supervisor
from .mr3_probe_lifecycle_fixture import Lifecycle, NAMES, ACTION_MASK_WHOLE_FILE_SHA256

choose=benchmark.probe_action_reach_v3
record=benchmark.record_probe_reach_v3_submission
finish=benchmark.finish_probe_reach_v3


class Fixture(Lifecycle):
    def snapshot(self, when, *, path=0., complete=True, path_source=None, **kwargs):
        value=super().snapshot(when,path=path,**kwargs)
        value['source_stamp']=when
        for robot in value['robots']:
            robot['activity'].update(schema='mr3-received-activity-v1',epoch=value['epoch'],
                state_sequence=value['sequence'],path_observation_complete=complete,
                last_odom_source_stamp=when if path_source is None else path_source)
        value['digest']=hashlib.sha256(json.dumps({k:v for k,v in value.items() if k!='digest'},
            sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        return value


def consume(fixture, diagnostics, snapshot):
    action=choose(snapshot,diagnostics)
    info=fixture.apply(snapshot,action)
    record(diagnostics,info)
    return action,info


def start():
    f=Fixture();d={};s=f.snapshot(0,path=None,complete=False)
    action,info=consume(f,d,s)
    return f,d,action,info


class ProbeV3Tests(unittest.TestCase):
    def test_goal0_null_path_uses_real_legal_masks_and_no_zero_baseline(self):
        f,d,action,info=start()
        self.assertEqual(info['synthetic_dispatch_status'],['sent']*3)
        self.assertTrue(all(c<8 for c in (action//100,action//10%10,action%10)))
        for saved in d['reach_v3_stimulus']['rounds']['initial'].values():
            self.assertIsNone(saved['submitted_activity']['estimated_path_m'])
            self.assertFalse(saved['submitted_activity']['path_observation_complete'])
            self.assertEqual(saved['baseline_capture_count'],0)
            self.assertNotIn('baseline_path_m',saved)
        self.assertEqual(len(ACTION_MASK_WHOLE_FILE_SHA256),64)

    def test_short_legal_candidate_is_allowed_but_long_masked_one_is_not(self):
        f=Fixture();s=f.snapshot(0,path=None,complete=False,long_available=False);d={}
        action,_=consume(f,d,s)
        self.assertTrue(all(c in (0,1,2) for c in (action//100,action//10%10,action%10)))
        self.assertTrue(s['joint_action_mask'][action])

    def test_preaccept_old_source_negative_path_and_wrong_owner_never_capture(self):
        for variant in ('preaccept','old_source','negative','wrong_goal','unowned','incomplete'):
            with self.subTest(variant=variant):
                f,d,_,_=start()
                if variant!='preaccept':f.accept_all(.1)
                s=f.snapshot(1,path=-.1 if variant=='negative' else .1,
                             complete=variant!='incomplete',path_source=.05 if variant=='old_source' else 1.)
                if variant=='wrong_goal':s['robots'][0]['navigation']['goal_id']='other'
                if variant=='unowned':s['robots'][0]['navigation']['owned']=False
                consume(f,d,s)
                self.assertEqual(d['reach_v3_stimulus']['rounds']['initial']['tb1']['baseline_capture_count'],0)

    def test_delayed_capture_is_once_and_preserves_observation_identity(self):
        f,d,_,_=start();f.accept_all(.1)
        consume(f,d,f.snapshot(1,path=None,complete=False))
        s=f.snapshot(2,path=.5,path_source=1.9);consume(f,d,s)
        saved=copy.deepcopy(d['reach_v3_stimulus']['rounds']['initial']['tb1'])
        self.assertEqual(saved['baseline_path_m'],.5)
        self.assertEqual(saved['baseline_capture_count'],1)
        self.assertEqual(saved['baseline_snapshot_sequence'],s['sequence'])
        self.assertEqual(saved['baseline_snapshot_digest'],s['digest'])
        self.assertEqual(saved['baseline_path_source_ns'],1900000000)
        consume(f,d,f.snapshot(3,path=50.))
        now=d['reach_v3_stimulus']['rounds']['initial']['tb1']
        self.assertEqual({k:v for k,v in now.items() if k.startswith('baseline_')},
                         {k:v for k,v in saved.items() if k.startswith('baseline_')})

    def test_original_commitment_forward_speed_and_new_path_are_all_required(self):
        f,d,_,_=start();f.accept_all(.1);consume(f,d,f.snapshot(1,path=.5))
        self.assertEqual(consume(f,d,f.snapshot(5,speed=.08,path=1.))[0],888)
        self.assertEqual(consume(f,d,f.snapshot(6,speed=.08,path=.54))[0],888)
        self.assertEqual(consume(f,d,f.snapshot(7,speed=-.08,path=.6))[0],888)
        action,info=consume(f,d,f.snapshot(8,speed=.08,path=.6))
        self.assertEqual(action,999);self.assertEqual(info['synthetic_dispatch_status'],['waiting']*3)
        self.assertTrue(all('wait_command_id' in s for s in d['reach_v3_stimulus']['rounds']['initial'].values()))

    def test_exact_point_zero_baseline_then_point05_uses_original_float_comparison(self):
        f,d,_,_=start();f.accept_all(.1);consume(f,d,f.snapshot(1,path=0.))
        self.assertEqual(consume(f,d,f.snapshot(6,speed=.08,path=.05))[0],999)

    def test_cleanup_without_baseline_never_gets_scientific_wait_credit(self):
        f,d,_,_=start();f.accept_all(.1)
        action,_=consume(f,d,f.snapshot(10,speed=0.,path=None,complete=False))
        self.assertEqual(action,999)
        self.assertTrue(all('wait_command_id' not in s for s in d['reach_v3_stimulus']['rounds']['initial'].values()))
        with self.assertRaisesRegex(ValueError,'coverage unavailable'):finish(f.snapshot(32,path=None,complete=False),d)

    def test_natural_terminal_before_first_legal_wait_does_not_count_as_cancel(self):
        f,d,_,_=start();f.accept_all(.1);consume(f,d,f.snapshot(1,path=.1))
        f.complete_all('SUCCEEDED',3.)
        consume(f,d,f.snapshot(6,path=.2))
        self.assertTrue(all('wait_command_id' not in s and 'cancel_terminal_observed_ns' not in s
                            for s in d['reach_v3_stimulus']['rounds']['initial'].values()))
        with self.assertRaisesRegex(ValueError,'coverage unavailable'):finish(f.snapshot(32,path=.2),d)

    def test_full32_two_round_six_goal_lifecycle_and_real_wait_masks(self):
        f=Fixture();d={};snapshots=[];infos=[]
        for t in range(32):
            path=None if t==0 else .1 if t<6 else .2 if t<14 else .25 if t<19 else .4
            speed=.08 if t in (6,19) else 0.
            snapshot=f.snapshot(t,path=path,complete=t!=0,speed=speed)
            snapshots.append(copy.deepcopy(snapshot))
            _,info=consume(f,d,snapshot);infos.append(copy.deepcopy(info))
            if t in (0,13):f.accept_all(t+.1)
            if t in (6,19):
                f.advance(t+.1)
                for name,state in f.dispatcher.states.items():
                    f.dispatcher.on_cancel_response(name,state.goal_id,True,t+.1)
                f.complete_all('CANCELED',t+.2)
        last=f.snapshot(32,path=.4);snapshots.append(copy.deepcopy(last));finish(last,d)
        target=os.environ.get('MR3_V3_ARTIFICIAL_TRACE_OUTPUT')
        if target:
            with Path(target).open('x') as stream:json.dump({'epoch':last['epoch'],'snapshots':snapshots,
                'infos':infos,'diagnostics':d,'actual_dispatcher_events':f.events,
                'scope':'artificial genuine Python dispatcher/masks only; no native or original input'},stream,indent=2)
        state=d['reach_v3_stimulus']
        self.assertTrue(state['coverage_passed']);self.assertEqual(len(state['decisions']),32)
        self.assertEqual(sum(e['type']=='send_goal' for e in f.events),6)
        self.assertEqual(sum('wait_command_id' in s for r in state['rounds'].values() for s in r.values()),6)
        self.assertTrue(all(s['baseline_capture_count']==1 for r in state['rounds'].values() for s in r.values()))

    def test_real_supervisor_reset_forwards_v3_exactly_into_dummy_worker_rpc(self):
        with tempfile.TemporaryDirectory(prefix='probe-v3-rpc-') as tmp:
            su=supervisor.Supervisor(run_id='v3-cpu', output_root=tmp, safety_contract='mr3-reach-v1',
                preparation_probe_version=supervisor.PREPARATION_PROBE_REACH_V3)
            calls=[]
            process=SimpleNamespace(pid=99999999,stdin=SimpleNamespace(fileno=lambda:0),
                                    stdout=SimpleNamespace(fileno=lambda:0))
            def rpc(op,**request):
                calls.append((op,request));return {'snapshot':{'epoch':su.episode.epoch}}
            with patch.object(su,'close'), patch.object(su,'_rpc',side_effect=rpc), \
                 patch.object(supervisor.subprocess,'Popen',return_value=process), \
                 patch.object(supervisor,'process_identity',return_value={'pid':99999999,'start_ticks':1}), \
                 patch.object(supervisor,'JsonLinePeer'), patch.object(supervisor.threading,'Thread',return_value=MagicMock()), \
                 patch.object(supervisor,'ros_environment',return_value={}):
                su.reset('open',101)
            try:
                self.assertEqual(calls[0][0],'reset')
                self.assertEqual(calls[0][1]['preparation_probe_version'],supervisor.PREPARATION_PROBE_REACH_V3)
                self.assertEqual(calls[0][1]['safety_contract'],'mr3-reach-v1')
                self.assertEqual(calls[0][1]['quantum_steps'],20)
            finally:su.episode.output.close()

    def test_actual_worker_request_guard_accepts_only_explicit_typed_reach_tokens(self):
        path=supervisor.WORKSPACE/'ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py'
        tree=ast.parse(path.read_bytes(),filename=str(path));selected=None
        for function in ast.walk(tree):
            if isinstance(function,ast.FunctionDef) and function.name=='__init__':
                for i,node in enumerate(function.body[:-1]):
                    if (isinstance(node,ast.Assign) and any(isinstance(t,ast.Attribute)
                            and t.attr=='preparation_probe_version' for t in node.targets)):
                        selected=[node,function.body[i+1]]
        self.assertIsNotNone(selected)
        wrapper=ast.parse('def validate(self, request):\n    pass\n').body[0];wrapper.body=selected
        namespace={};exec(compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),str(path),'exec'),namespace)
        for token in (supervisor.PREPARATION_PROBE_REACH_V2,supervisor.PREPARATION_PROBE_REACH_V3):
            namespace['validate'](SimpleNamespace(safety_contract='mr3-reach-v1'),{'preparation_probe_version':token})
        for contract,token in (('legacy',supervisor.PREPARATION_PROBE_REACH_V3),('mr3-reach-v1',None),
                               ('mr3-reach-v1',False),('mr3-reach-v1','unknown')):
            with self.assertRaises(ValueError):namespace['validate'](SimpleNamespace(safety_contract=contract),{'preparation_probe_version':token})

    def test_v3_metadata_has_no_retired_distance_or_long_path_contract(self):
        _,d,_,_=start();request=d['reach_v3_stimulus']['decisions'][0]
        self.assertIn('eligible_goal_candidates',request)
        self.assertNotIn('eligible_long_goal_candidates',request)
        self.assertFalse(any('nominal' in key or 'screen' in key for key in request))
        note=d['goal_decisions'][0]
        self.assertEqual(note['scope'],'original legal nonapproach stimulus subset; not actor availability or physical proof')
        self.assertFalse(any('nominal' in key or 'screen' in key for key in note))

    def test_current_activity_epoch_and_path_source_cannot_cross_baseline(self):
        for variant in ('wrong_epoch','backward','future','null'):
            with self.subTest(variant=variant):
                f,d,_,_=start();f.accept_all(.1);consume(f,d,f.snapshot(1,path=.5))
                s=f.snapshot(6,speed=.08,path=.6);activity=s['robots'][0]['activity']
                if variant=='wrong_epoch':activity['epoch']='other'
                elif variant=='backward':activity['last_odom_source_stamp']=.5
                elif variant=='future':activity['last_odom_source_stamp']=7.
                else:activity['last_odom_source_stamp']=None
                action,_=consume(f,d,s)
                self.assertEqual(action//100,8)
                self.assertNotIn('wait_command_id',d['reach_v3_stimulus']['rounds']['initial']['tb1'])

    def test_mixed_or_legacy_profile_rejects_v3_token(self):
        token=supervisor.PREPARATION_PROBE_REACH_V3
        supervisor.validate_preparation_profile('mr3-reach-v1',token)
        with self.assertRaises(ValueError):supervisor.validate_preparation_profile('legacy',token)
        with self.assertRaises(ValueError):supervisor.validate_preparation_profile('mr3-reach-v1',token+'unknown')


if __name__=='__main__':unittest.main()
