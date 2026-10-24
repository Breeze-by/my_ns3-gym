"""Artificial masked-cancel lifecycle and per-call G720 V3 differential; no native inputs."""
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock,patch

from mr3_learning import benchmark as b,supervisor
from .test_reach_outward_cancel_v3_producer import Fixture
from .mr3_probe_lifecycle_fixture import _action_masks
import os
ROOT=Path('/home/zhuyulab/ns3-workspace')
G='720cd4e194eeb2e9f14a86ed9204f6110d72173b'
REL='ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/benchmark.py'
GOLD=subprocess.check_output(['git','show',G+':'+REL],cwd=ROOT)
assert hashlib.sha256(GOLD).hexdigest()=='72360f3a786635a02e13d83d9afe9035afa556047e2ea50fe7c71d55c62b9e7b'
NAMES={'_probe_v2_number','_probe_nonapproaching_goal_action','_probe_goal_order',
       'probe_action_reach_v3','record_probe_reach_v3_submission','finish_probe_reach_v3'}
old={'math':math}
tree=ast.parse(GOLD);nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in NAMES]
assert len(nodes)==len(NAMES)
exec(compile(ast.Module(body=nodes,type_ignores=[]),'G720:'+REL,'exec'),old)
EVENTS=[]

def canon(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def outcome(fn,*args):
    try:return {'return':fn(*args),'error':None}
    except Exception as e:return {'return':None,'error':{'type':type(e).__name__,'message':str(e)}}

def compare(test,method,arguments,left,right,label):
    a=outcome(old[method],*copy.deepcopy(arguments),left)
    z=outcome(getattr(b,method),*copy.deepcopy(arguments),right)
    EVENTS.append(dict(label=label,method=method,old_outcome=a,new_outcome=z,
        old_diagnostics_sha256=hashlib.sha256(canon(left)).hexdigest(),new_diagnostics_sha256=hashlib.sha256(canon(right)).hexdigest(),
        whole_canonical_JSON_equal=canon(left)==canon(right)))
    test.assertEqual(a,z,label);test.assertEqual(canon(left),canon(right),label)
    return a

def finish_cancels(f,t):
    f.advance(t+.1);pending=[(n,s.goal_id) for n,s in f.dispatcher.states.items() if s.goal_id is not None and s.cancel_requested]
    for n,g in pending:f.dispatcher.on_cancel_response(n,g,True,t+.1)
    f.advance(t+.2)
    for n,g in pending:f.dispatcher.on_result(n,g,'CANCELED',t+.2)


def accept(f,when):
    f.advance(when)
    for n,s in f.dispatcher.states.items():
        if s.goal_id is not None and s.phase=='accepting':f.dispatcher.on_accept(n,s.goal_id,True,when)


class MaskedCancelTests(unittest.TestCase):
    def test_V3_each_call_matches_actual_G720_returns_full_JSON_and_errors(self):
        for variant in ('positive','zero','none','late_source','stale','natural_success','aborted','external_cancel'):
            with self.subTest(variant=variant):
                f=Fixture();left={};right={}
                for t in range(32):
                    if t==3 and variant in ('natural_success','aborted','external_cancel'):
                        f.complete_all({'natural_success':'SUCCEEDED','aborted':'ABORTED','external_cancel':'CANCELED'}[variant],2.5)
                    path=None if variant=='none' or t==0 else (0. if variant=='zero' else .1) if t<6 else .2 if t<14 else .25 if t<19 else .4
                    snap=f.snapshot(t,path=path,complete=t!=0 and variant!='none',speed=.08 if t in (6,19) else 0.,
                        path_source=.05 if variant=='late_source' and t==1 else None)
                    if variant=='stale' and t==6:snap['robots'][0]['fresh']=False
                    if t==2:snap['robots'][0]['w']=.2
                    snap['digest']=hashlib.sha256(canon({k:v for k,v in snap.items() if k!='digest'})).hexdigest()
                    a=compare(self,'probe_action_reach_v3',[snap],left,right,variant+':choose'+str(t));self.assertIsNone(a['error'])
                    info=f.apply(snap,a['return'])
                    a=outcome(old['record_probe_reach_v3_submission'],left,copy.deepcopy(info));z=outcome(b.record_probe_reach_v3_submission,right,copy.deepcopy(info))
                    EVENTS.append(dict(label=variant+':record'+str(t),method='record_probe_reach_v3_submission',old_outcome=a,new_outcome=z,
                        whole_canonical_JSON_equal=canon(left)==canon(right),old_diagnostics_sha256=hashlib.sha256(canon(left)).hexdigest(),new_diagnostics_sha256=hashlib.sha256(canon(right)).hexdigest()))
                    self.assertEqual(a,z);self.assertEqual(canon(left),canon(right))
                    if t in (0,13):accept(f,t+.1)
                    if t in (6,19):finish_cancels(f,t)
                last=f.snapshot(32,path=None if variant=='none' else .4,complete=variant!='none')
                compare(self,'finish_probe_reach_v3',[last],left,right,variant+':finish')

    def test_V3_pending_malformed_not_submitted_and_boundary_errors_match_G720(self):
        f=Fixture();s=f.snapshot(0,path=None,complete=False);left={};right={}
        compare(self,'probe_action_reach_v3',[s],left,right,'pending first')
        compare(self,'probe_action_reach_v3',[s],left,right,'pending duplicate')
        for variant in ('not_submitted','bad_command','badflag'):
            l=copy.deepcopy(left);r=copy.deepcopy(right)
            info={'action_submitted':False} if variant=='not_submitted' else {'command':{}} if variant=='bad_command' else {'action_submitted':0}
            a=outcome(old['record_probe_reach_v3_submission'],l,copy.deepcopy(info));z=outcome(b.record_probe_reach_v3_submission,r,copy.deepcopy(info))
            self.assertEqual(a,z);self.assertEqual(canon(l),canon(r));EVENTS.append(dict(label=variant,method='record',old_outcome=a,new_outcome=z,whole_canonical_JSON_equal=canon(l)==canon(r)))
        compare(self,'finish_probe_reach_v3',[f.snapshot(31,path=0.)],copy.deepcopy(left),copy.deepcopy(right),'bad final boundary')
        invalid=copy.deepcopy(s);invalid['task_elapsed_sec']=float('nan')
        compare(self,'probe_action_reach_v3',[invalid],{},{} ,'invalid clock')

    def test_old_V2_three_functions_remain_literal_G720_bytes(self):
        current=Path(b.__file__).read_text();ct=ast.parse(current);gt=ast.parse(GOLD)
        for name in ('probe_action_reach_v2','record_probe_reach_v2_submission','finish_probe_reach_v2'):
            a=next(n for n in ct.body if isinstance(n,ast.FunctionDef) and n.name==name)
            z=next(n for n in gt.body if isinstance(n,ast.FunctionDef) and n.name==name)
            self.assertEqual(ast.get_source_segment(current,a),ast.get_source_segment(GOLD.decode(),z))

    def test_masked_original_legal_approach_is_allowed_without_safety_claim(self):
        f=Fixture();s=f.snapshot(0,path=None,complete=False)
        s['candidates'][0].update(x=2.,y=2.,path_distances_m=[3.,None,None])
        s['per_robot_action_mask'],s['joint_action_mask'],s['mask_reasons']=_action_masks(s['robots'],s['candidates'],0.)
        d={};action=b.probe_action_reach_masked_cancel_v1(s,d)
        self.assertEqual(action//100,0);self.assertTrue(s['joint_action_mask'][action])
        self.assertTrue(all(s['per_robot_action_mask'][i][c] for i,c in enumerate((action//100,action//10%10,action%10))))
        self.assertFalse(b._probe_nonapproaching_goal_action(s,action))
        request=d['reach_masked_cancel_v1_stimulus']['decisions'][0]
        self.assertEqual(request['goal_filter'],'original_per_robot_and_joint_masks_only_v1')
        self.assertEqual(request['goal_rank'],'goal_count_min_path_second_reverse_sum_path_action_v1')
        self.assertNotIn('reach_v3_stimulus',d)

    def test_masked_max_min_path_beats_larger_sum_without_threshold(self):
        f=Fixture();s=f.snapshot(0,path=None,complete=False)
        paths=[[10.,4.,0.],[4.,.1,0.],[0.,0.,4.]]
        for c,t in enumerate(s['candidates']):
            t.update(x=2.,y=float(c*4),valid=c<3,reachable=[c<3]*3,
                     path_distances_m=[paths[i][c] for i in range(3)] if c<3 else [None]*3)
        s['per_robot_action_mask'],s['joint_action_mask'],s['mask_reasons']=_action_masks(s['robots'],s['candidates'],0.)
        self.assertTrue(s['joint_action_mask'][12]);self.assertTrue(s['joint_action_mask'][102])
        self.assertEqual(b.probe_action_reach_masked_cancel_v1(s,{}),102)
        self.assertGreater(10.+.1+4.,4.+4.+4.)

    def test_masked_true_zero_path_allowed_but_missing_negative_nonfinite_and_badcoords_fail(self):
        f=Fixture();s=f.snapshot(0,path=None,complete=False,long_available=False)
        s['candidates'][2]['path_distances_m'][2]=0.
        self.assertEqual(b.probe_action_reach_masked_cancel_v1(s,{}),12)
        for bad in (None,-.001,float('nan'),float('inf'),True):
            wrong=copy.deepcopy(s);wrong['candidates'][2]['path_distances_m'][2]=bad
            with self.assertRaisesRegex(ValueError,'invalid coordinates or declared path'):b.probe_action_reach_masked_cancel_v1(wrong,{})
        for owner,key in ((s['robots'][2],'yaw'),(s['candidates'][2],'x')):
            old=owner[key];owner[key]=None
            with self.assertRaises(ValueError):b.probe_action_reach_masked_cancel_v1(s,{})
            owner[key]=old

    def test_masked_honors_false_joint_and_per_bits_including_KEEP(self):
        f=Fixture();s=f.snapshot(0,path=None,complete=False);d={}
        best=b.probe_action_reach_masked_cancel_v1(copy.deepcopy(s),d)
        s['joint_action_mask'][best]=False
        self.assertNotEqual(b.probe_action_reach_masked_cancel_v1(s,{}),best)
        for row in s['per_robot_action_mask']:
            for i in range(10):row[i]=False
        s['joint_action_mask']=[False]*1000;s['joint_action_mask'][888]=True
        with self.assertRaisesRegex(ValueError,'no original legal joint'):b.probe_action_reach_masked_cancel_v1(s,{})

    def test_masked_full32_six_goal_real_dispatcher_and_once_baselines(self):
        f=Fixture();d={};snapshots=[];infos=[]
        for t in range(32):
            path=None if t==0 else .1 if t<6 else .2 if t<14 else .25 if t<19 else .4
            s=f.snapshot(t,path=path,complete=t!=0,speed=.08 if t in (6,19) else 0.)
            action=b.probe_action_reach_masked_cancel_v1(s,d)
            snapshots.append(copy.deepcopy(s));info=f.apply(s,action);b.record_probe_reach_masked_cancel_v1_submission(d,info);infos.append(copy.deepcopy(info))
            if t in (0,13):accept(f,t+.1)
            if t in (6,19):finish_cancels(f,t)
        last=f.snapshot(32,path=.4);snapshots.append(last);b.finish_probe_reach_masked_cancel_v1(last,d)
        state=d['reach_masked_cancel_v1_stimulus'];self.assertTrue(state['coverage_passed'])
        self.assertEqual(sum(e['type']=='send_goal' for e in f.events),6);self.assertEqual(len(state['decisions']),32)
        self.assertTrue(all(s['baseline_capture_count']==1 for r in state['rounds'].values() for s in r.values()))
        target=os.environ.get('MR3_MASKED_ARTIFICIAL_TRACE_OUTPUT')
        if target:
            with Path(target).open('x') as stream:json.dump(dict(epoch=last['epoch'],snapshots=snapshots,infos=infos,diagnostics=d,actual_dispatcher_events=f.events,
                scope='artificial actual Python producer/dispatcher/mask only; command created/expiry fields absent from Fixture.apply, not native wire'),stream,indent=2)

    def test_masked_natural_terminal_and_late_accept_preserve_failure_no_goal_retry(self):
        for variant in ('natural','late_accept'):
            f=Fixture();d={}
            for t in range(32):
                if variant=='natural' and t==3:f.complete_all('SUCCEEDED',2.5)
                s=f.snapshot(t,path=None if t==0 else .1 if t<6 else .2,complete=t!=0,speed=.08 if t==6 else 0.)
                action=b.probe_action_reach_masked_cancel_v1(s,d);b.record_probe_reach_masked_cancel_v1_submission(d,f.apply(s,action))
                if t==0 and variant=='natural':accept(f,.1)
                if t==2 and variant=='late_accept':accept(f,2.1)
            with self.assertRaisesRegex(ValueError,'coverage unavailable'):b.finish_probe_reach_masked_cancel_v1(f.snapshot(32,path=.2),d)
            self.assertEqual(sum(e['type']=='send_goal' for e in f.events),3)
            self.assertFalse(d['reach_masked_cancel_v1_stimulus']['coverage_passed'])
            if variant=='late_accept':
                self.assertTrue(all(row['accepted_at_ns']==2100000000 for row in d['reach_masked_cancel_v1_stimulus']['rounds']['initial'].values()))
                self.assertTrue(any(row['reason']=='acceptance_outside_bounded_opportunity' for row in d['reach_masked_cancel_v1_stimulus']['coverage_failures']))

    def test_new_token_real_Supervisor_RPC_worker_guard_and_metadata_forwarding(self):
        token=supervisor.PREPARATION_PROBE_REACH_MASKED_CANCEL_V1
        supervisor.validate_preparation_profile('mr3-reach-v1',token)
        with self.assertRaises(ValueError):supervisor.validate_preparation_profile('legacy',token)
        self.assertEqual(supervisor._preparation_goal_metadata(token),{'goal_filter':supervisor.MASKED_CANCEL_GOAL_FILTER,'goal_rank':supervisor.MASKED_CANCEL_GOAL_RANK})
        self.assertEqual(supervisor._preparation_goal_metadata(supervisor.PREPARATION_PROBE_REACH_V3),{})
        worker=supervisor.ROS_ROOT/'scripts/mr3_env_worker.py';tree=ast.parse(worker.read_bytes(),filename=str(worker));selected=None;metadata_if=None
        for fn in ast.walk(tree):
            if isinstance(fn,ast.FunctionDef) and fn.name=='__init__':
                for i,n in enumerate(fn.body[:-1]):
                    if isinstance(n,ast.Assign) and any(isinstance(t,ast.Attribute) and t.attr=='preparation_probe_version' for t in n.targets):selected=[n,fn.body[i+1]]
        for n in ast.walk(tree):
            if isinstance(n,ast.If) and isinstance(n.test,ast.Compare) and any(isinstance(x,ast.Constant) and x.value==token for x in ast.walk(n.test)) and any(isinstance(x,ast.Constant) and x.value==supervisor.MASKED_CANCEL_GOAL_RANK for x in ast.walk(n)):
                metadata_if=n
        self.assertIsNotNone(selected);self.assertIsNotNone(metadata_if)
        def compile_guard(body,args):
            fn=ast.parse('def run('+args+'):\n    pass').body[0];fn.body=body
            ns={};exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(worker),'exec'),ns);return ns['run']
        guard=compile_guard(selected,'self, request');metaguard=compile_guard([metadata_if],'self, metadata')
        with tempfile.TemporaryDirectory() as tmp:
            su=supervisor.Supervisor(run_id='masked-toy',output_root=tmp,safety_contract='mr3-reach-v1',preparation_probe_version=token)
            calls=[];process=SimpleNamespace(pid=99999999,stdin=SimpleNamespace(fileno=lambda:0),stdout=SimpleNamespace(fileno=lambda:0))
            def rpc(op,**request):calls.append((op,request));return {'snapshot':{'epoch':su.episode.epoch}}
            with patch.object(su,'close'),patch.object(su,'_rpc',side_effect=rpc),patch.object(supervisor.subprocess,'Popen',return_value=process),patch.object(supervisor,'process_identity',return_value={'pid':99999999,'start_ticks':1}),patch.object(supervisor,'JsonLinePeer'),patch.object(supervisor.threading,'Thread',return_value=MagicMock()),patch.object(supervisor,'ros_environment',return_value={}):su.reset('open',101)
            try:
                request=calls[0][1];self.assertEqual(request['preparation_probe_version'],token);self.assertEqual(request['quantum_steps'],20)
                fake=SimpleNamespace(safety_contract='mr3-reach-v1');guard(fake,request);meta={};metaguard(fake,meta)
                self.assertEqual(meta,supervisor._preparation_goal_metadata(token))
                paths=list(Path(tmp).rglob('supervisor_metadata.json'));self.assertEqual(len(paths),1)
                saved=json.loads(paths[0].read_text())
                self.assertEqual({k:saved[k] for k in ('goal_filter','goal_rank')},meta)
            finally:su.episode.output.close()
        for contract,version in (('legacy',token),('mr3-reach-v1',False),('mr3-reach-v1','unknown')):
            with self.assertRaises(ValueError):guard(SimpleNamespace(safety_contract=contract),{'preparation_probe_version':version})

    def test_actual_benchmark_metadata_names_new_family_without_outward_alias(self):
        path=Path(b.__file__);tree=ast.parse(path.read_bytes(),filename=str(path));main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        selected=[n for n in main.body if isinstance(n,ast.If) and any(isinstance(x,ast.Constant) and x.value=='masked_cancel_v1_original_masks_external_actions' for x in ast.walk(n))]
        self.assertEqual(len(selected),1)
        fn=ast.parse('def run(args,metadata):\n    pass').body[0];fn.body=selected
        ns=dict(b.__dict__);exec(compile(ast.fix_missing_locations(ast.Module(body=[fn],type_ignores=[])),str(path),'exec'),ns)
        for version,expected in ((supervisor.PREPARATION_PROBE_REACH_MASKED_CANCEL_V1,'masked_cancel_v1_original_masks_external_actions'),(supervisor.PREPARATION_PROBE_REACH_V3,'unchanged_v6_external_actions')):
            meta={};ns['run'](SimpleNamespace(safety_contract='mr3-reach-v1',preparation_motion_probe=True,preparation_probe_version=version),meta)
            self.assertEqual(meta['preparation_fixture_implementation'],expected)
            self.assertEqual({k:meta[k] for k in ('goal_filter','goal_rank') if k in meta},supervisor._preparation_goal_metadata(version))
        self.assertNotIn('help="external engineering inputs: prefer outward legal goals; no policy"',path.read_text())

    def test_second_reverse_is_only_a_soft_tie_after_minimum_path(self):
        f=Fixture();d={}
        for t in range(13):
            snap=f.snapshot(t,path=None if t==0 else .1 if t<6 else .2,complete=t!=0,speed=.08 if t==6 else 0.)
            if t==2:snap['robots'][0]['w']=.2
            snap['digest']=hashlib.sha256(canon({k:v for k,v in snap.items() if k!='digest'})).hexdigest()
            a=b.probe_action_reach_masked_cancel_v1(snap,d);b.record_probe_reach_masked_cancel_v1_submission(d,f.apply(snap,a))
            if t==0:accept(f,.1)
            if t==6:finish_cancels(f,6)
        snap=f.snapshot(13,path=.2)
        snap['candidates'][0].update(x=1.6,y=0.,path_distances_m=[1.6,None,None])
        snap['candidates'][3].update(x=-1.6,y=-.1,path_distances_m=[1.5,None,None])
        snap['per_robot_action_mask'],snap['joint_action_mask'],snap['mask_reasons']=_action_masks(snap['robots'],snap['candidates'],13.)
        snap['digest']=hashlib.sha256(canon({k:v for k,v in snap.items() if k!='digest'})).hexdigest()
        self.assertEqual(b.probe_action_reach_masked_cancel_v1(snap,copy.deepcopy(d)),45)
        snap['candidates'][3]['path_distances_m'][0]=1.6
        snap['digest']=hashlib.sha256(canon({k:v for k,v in snap.items() if k!='digest'})).hexdigest()
        tied=copy.deepcopy(d);self.assertEqual(b.probe_action_reach_masked_cancel_v1(snap,tied),345)
        self.assertEqual(tied['goal_decisions'][-1]['selected_reverse_robots'],['tb1'])
        no_reference=copy.deepcopy(d);no_reference['reference_turn_samples']={}
        self.assertEqual(b.probe_action_reach_masked_cancel_v1(snap,no_reference),45)


if __name__=='__main__':unittest.main()
