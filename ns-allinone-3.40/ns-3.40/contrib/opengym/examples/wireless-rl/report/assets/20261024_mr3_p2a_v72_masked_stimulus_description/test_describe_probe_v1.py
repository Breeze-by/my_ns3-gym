"""Artificial producer-generated transitions; no original V71 input or consumer main."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
sys.path.insert(0,str(W))
# Real producer is used only to GENERATE artificial diagnostics; independent consumer imports no producer.
from mr3_learning.tests.test_reach_outward_cancel_v3_producer import Fixture
from mr3_learning.tests.mr3_probe_lifecycle_fixture import _action_masks
from mr3_learning import benchmark
spec=importlib.util.spec_from_file_location('fixed_v72_description',HERE/'describe_probe_v1.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def trace(*,terminal=None,zero=False,no_path=False,long_available=True,old_source=False):
    f=Fixture();diag={};rows=[];infos=[]
    for t in range(32):
        if terminal is not None and t==3:
            f.advance(2.5);state=f.dispatcher.states['tb3'];f.dispatcher.on_result('tb3',state.goal_id,terminal,2.5)
        path=None if no_path or t==0 else (0. if zero else .1) if t<6 else .2 if t<14 else .25 if t<19 else .4
        speed=.08 if t in (6,19) else 0.
        snap=f.snapshot(t,path=path,complete=not no_path and t!=0,speed=speed,long_available=long_available,
            path_source=.05 if old_source and t==1 else None)
        action=benchmark.probe_action_reach_masked_cancel_v1(snap,diag)
        info=f.apply(snap,action);benchmark.record_probe_reach_masked_cancel_v1_submission(diag,info)
        # Construct the actual worker envelope explicitly. Fixture.apply used its synthetic1.5s lease;
        # these two command fields are constructed2s worker-schema data, not saved native wire evidence.
        info['epoch']=f.dispatcher.epoch;info['command'].update(created_at=float(t),expires_at=float(t+2))
        info['dt']=1.;info['physical_dt']=1.
        rows.append({'kind':'reset' if t==0 else 'step','snapshot':copy.deepcopy(snap)})
        infos.append(copy.deepcopy(info))
        if t in (0,13):
            f.advance(t+.1)
            for name,state in f.dispatcher.states.items():
                if state.goal_id is not None and state.phase=='accepting':f.dispatcher.on_accept(name,state.goal_id,True,t+.1)
        if t in (6,19):
            f.advance(t+.1)
            pending=[(name,state.goal_id) for name,state in f.dispatcher.states.items() if state.goal_id is not None and state.cancel_requested]
            for name,goal in pending:f.dispatcher.on_cancel_response(name,goal,True,t+.1)
            f.advance(t+.2)
            for name,goal in pending:f.dispatcher.on_result(name,goal,'CANCELED',t+.2)
    last=f.snapshot(32,path=None if no_path else .4,complete=not no_path,long_available=long_available)
    snapshots=[r['snapshot'] for r in rows]+[last]
    transitions=[{'kind':'reset','snapshot':snapshots[0]}]+[
        {'kind':'step','snapshot':snapshots[i+1],'info':infos[i]} for i in range(32)]
    error=None
    try:benchmark.finish_probe_reach_masked_cancel_v1(last,diag)
    except ValueError as exc:error=str(exc)
    summary=dict(freeze=m.ORIGINAL_FREEZE,safety_contract='mr3-reach-v1',preparation_probe_version=m.PROBE,
        workers=1,schedule=[['open',101]],passed=error is None,goal_filter=m.GOAL_FILTER,goal_rank=m.GOAL_RANK,
        workers_results=[dict(worker_id=0,error=error,episodes=[dict(epoch=f.dispatcher.epoch,scene='open',seed=101,
            transitions=32,preparation_probe_diagnostics=diag)])])
    return transitions,summary,f.dispatcher.epoch


class DescribeMaskedTests(unittest.TestCase):
    def test_complete_actual_python_producer_lifecycle_has_exact_independent_match(self):
        t,s,e=trace();d=m.describe(t,s,e)
        self.assertTrue(d['passed']);self.assertTrue(all(d['comparisons'].values()))
        self.assertTrue(d['independent_coverage_passed']);self.assertEqual(len(d['received_timeline']),33)
        self.assertTrue(all(len(x['robots'][2]['current_round']['candidates'])==8 for x in d['received_timeline']))
        self.assertEqual(d['received_timeline'][0]['robots'][2]['activity']['estimated_path_m'],None)
        self.assertLess(len(m.canonical(d)),m.LIMITS['max_output_bytes'])

    def test_succeeded_aborted_and_unsolicited_canceled_are_described_as_distinct_real_failures(self):
        for terminal in ('SUCCEEDED','ABORTED','CANCELED'):
            with self.subTest(terminal=terminal):
                t,s,e=trace(terminal=terminal);d=m.describe(t,s,e)
                self.assertTrue(d['passed']);self.assertFalse(d['independent_coverage_passed']);self.assertTrue(d['original_FAIL_preserved'])
                events=[x for x in d['first_observed_terminals'] if x['robot']=='tb3'];self.assertEqual(len(events),1)
                self.assertIn(terminal,events[0]['classification'])
                self.assertEqual(events[0]['navigation']['last_terminal'],terminal)
                self.assertEqual(events[0]['actual_delivery_or_terminal_generation_time'],'UNKNOWN_FROM_THESE_TWO_INPUTS')
                saved=d['robot_rounds'][2]['reconstructed'];self.assertNotIn('wait_command_id',saved)
                self.assertNotIn('cancel_terminal_observed_ns',saved)
                self.assertTrue(any(x['reason']=='goal_terminal_without_confirmed_stimulus_cancel' for x in d['independent_coverage_failures']))

    def test_true_zero_baseline_is_captured_once(self):
        t,s,e=trace(zero=True);d=m.describe(t,s,e)
        self.assertTrue(d['passed']);saved=d['robot_rounds'][2]['reconstructed']
        self.assertEqual(saved['baseline_path_m'],0.);self.assertEqual(saved['baseline_capture_count'],1)
        self.assertEqual(saved['baseline_snapshot_sequence'],t[1]['snapshot']['sequence'])
        self.assertEqual(saved['baseline_snapshot_digest'],t[1]['snapshot']['digest'])

    def test_missing_or_none_path_is_not_zero_and_forged_persisted_zero_is_rejected(self):
        t,s,e=trace(no_path=True);d=m.describe(t,s,e)
        self.assertTrue(d['passed']);saved=d['robot_rounds'][2]['reconstructed']
        self.assertEqual(saved['baseline_capture_count'],0);self.assertNotIn('baseline_path_m',saved)
        s['workers_results'][0]['episodes'][0]['preparation_probe_diagnostics'][m.STATE_KEY]['rounds']['initial']['tb3']['baseline_path_m']=0.
        forged=m.describe(t,s,e);self.assertFalse(forged['passed']);self.assertFalse(forged['comparisons']['whole_stimulus_state_equal'])

    def test_old_source_defers_capture_and_never_refreshes_baseline(self):
        t,s,e=trace(old_source=True);d=m.describe(t,s,e)
        self.assertTrue(d['passed']);saved=d['robot_rounds'][2]['reconstructed']
        self.assertEqual(saved['baseline_observed_ns'],2*10**9);self.assertEqual(saved['baseline_capture_count'],1)
        self.assertEqual(saved['baseline_path_m'],.1)

    def test_short_goal_and_long_available_alternatives_are_reported_without_a_threshold(self):
        for long_available in (False,True):
            t,s,e=trace(long_available=long_available);d=m.describe(t,s,e);self.assertTrue(d['passed'])
            first=d['goal_opportunity_bank_and_joint_distributions'][0];rows=first['robots'][2]['candidates']
            chosen=m.choices(first['selected']['action'])[2]
            self.assertEqual(rows[chosen]['path_distance_m'],1.6 if long_available else .8)
            if long_available:self.assertTrue(any(x['currently_eligible'] and x['path_distance_m']==.8 for x in rows))
            selected_count=str(first['selected']['GOAL_count'])
            self.assertEqual(first['current_lifecycle_desired_subset'][selected_count]['best_under_fixed_rank']['action'],first['selected']['action'])
            self.assertTrue(all(a in range(1000) for g in first['original_per_AND_joint_true'].values() for a in g['actions']))

    def test_cleanup_wait_and_owned_later_bank_are_not_counterfactual_goal_credit(self):
        t,s,e=trace(terminal='SUCCEEDED');d=m.describe(t,s,e)
        owned=d['received_timeline'][1]['robots'][2]['current_round'];self.assertFalse(owned['GOAL_common']['unowned'])
        cleanup=[r for r in d['received_timeline'] if r['robots'][2]['current_round']['mode']=='bounded_cleanup_wait_no_credit']
        self.assertTrue(cleanup);self.assertNotIn('wait_command_id',d['robot_rounds'][2]['reconstructed'])

    def test_post_snapshot_command_binding_and_digest_tamper_fail_closed(self):
        t,s,e=trace();t[1]['info']['command']['observation_sequence']=t[1]['snapshot']['sequence']
        with self.assertRaisesRegex(ValueError,'previous snapshot'):m.describe(t,s,e)
        t,s,e=trace();t[1]['snapshot']['robots'][2]['v']=.123
        with self.assertRaisesRegex(ValueError,'digest'):m.describe(t,s,e)

    def test_three_GOAL_priority_and_longer_two_one_GOAL_masked_alternatives_are_reported(self):
        f=Fixture();snap=f.snapshot(0,path=None,complete=False,long_available=False)
        for c,target in enumerate(snap['candidates']):
            target.update(valid=c<5,reachable=[c in (0,3),c in (1,4),c==2],
                x=float(c*3),y=5.,path_distances_m=[.1 if c==0 else 5. if c==3 else None,
                    .1 if c==1 else 4. if c==4 else None,.1 if c==2 else None])
        snap['per_robot_action_mask'],snap['joint_action_mask'],snap['mask_reasons']=_action_masks(snap['robots'],snap['candidates'],0.)
        for action in (12,348,388):self.assertTrue(snap['joint_action_mask'][action])
        # Artificial conservative original joint bits: preserve the actual helper's True bits, then close all other choices.
        snap['joint_action_mask']=[a in (12,348,388) and value for a,value in enumerate(snap['joint_action_mask'])]
        snap['digest']=m.sha(m.canonical({k:v for k,v in snap.items() if k!='digest'}))
        state=dict(epoch=snap['epoch'],rounds={r:{n:{} for n in m.ROBOTS} for r in m.ROUNDS},decisions=[],coverage_failures=[],last_clock_ns=-1)
        refs={};request,_,records,legal=m.select(snap,state,refs)
        self.assertEqual(request['action'],benchmark.probe_action_reach_masked_cancel_v1(snap,{}))
        self.assertEqual(request['action'],12)
        d=m.joint_distribution(snap,refs,request,records,legal)
        self.assertEqual(d['current_lifecycle_desired_subset']['3']['actions'],[12])
        self.assertEqual(d['current_lifecycle_desired_subset']['2']['best_under_fixed_rank']['minimum_selected_path_m'],4.)
        self.assertEqual(d['current_lifecycle_desired_subset']['1']['best_under_fixed_rank']['minimum_selected_path_m'],5.)
        self.assertTrue(all(x['has_larger_minimum_selected_path'] for x in d['lower_GOAL_count_comparisons'] if x['lower_GOAL_count'] in (1,2)))

    def test_exact_per_AND_joint_bits_are_used_and_no_missing_bit_is_reconstructed(self):
        f=Fixture();snap=f.snapshot(0,path=None,complete=False)
        state=dict(epoch=snap['epoch'],rounds={r:{n:{} for n in m.ROBOTS} for r in m.ROUNDS},decisions=[],coverage_failures=[],last_clock_ns=-1)
        request,_,records,legal=m.select(snap,state,{})
        removed=request['action'];snap['joint_action_mask'][removed]=False
        state['last_clock_ns']=-1
        request,_,records,legal=m.select(snap,state,{})
        d=m.joint_distribution(snap,{},request,records,legal)
        self.assertNotIn(removed,[a for group in d['original_per_AND_joint_true'].values() for a in group['actions']])
        for row in snap['per_robot_action_mask']:row[:]=[False]*10
        snap['joint_action_mask']=[a==888 for a in range(1000)]
        with self.assertRaisesRegex(ValueError,'original legal masked'):m.select(snap,state,{})

    def test_zero_legal_GOAL_path_is_not_missing_and_bad_legal_path_is_data_failure(self):
        f=Fixture();snap=f.snapshot(0,path=None,complete=False,long_available=False)
        snap['candidates'][2]['path_distances_m'][2]=0.
        state=lambda:dict(epoch=snap['epoch'],rounds={r:{n:{} for n in m.ROBOTS} for r in m.ROUNDS},decisions=[],coverage_failures=[],last_clock_ns=-1)
        request,_,records,legal=m.select(snap,state(),{})
        self.assertEqual(request['action'],12)
        self.assertEqual(m.joint_distribution(snap,{},request,records,legal)['selected']['minimum_selected_path_m'],0.)
        for bad in (None,-.1,True,float('inf')):
            broken=copy.deepcopy(snap);broken['candidates'][2]['path_distances_m'][2]=bad
            with self.assertRaisesRegex(ValueError,'invalid path'):m.select(broken,state(),{})

    def test_every_robot_and_both_rounds_are_described_without_native_terminal_time_claim(self):
        t,s,e=trace();d=m.describe(t,s,e)
        self.assertTrue(d['passed']);self.assertEqual(len(d['robot_rounds']),6)
        self.assertEqual([r['name'] for r in d['received_timeline'][0]['robots']],list(m.ROBOTS))
        self.assertEqual({(x['robot'],x['round']) for x in d['first_observed_terminals']},{(n,r) for n in m.ROBOTS for r in m.ROUNDS})
        self.assertTrue(all(x['actual_delivery_or_terminal_generation_time']=='UNKNOWN_FROM_THESE_TWO_INPUTS' for x in d['first_observed_terminals']))

    def test_unadmitted_pending_input_pins_refuse_before_any_actual_original_open(self):
        # This negative is independent of the installed real scope/admission value.
        spec={'schema':'mr3-v72-fixed-received-masked-cancel-description-spec-v1','admitted':False}
        self.assertFalse(spec['admitted'])
        with self.assertRaisesRegex(ValueError,'unadmitted'):m.validate_admission(spec,'0'*40)

    def test_strict_json_rejects_duplicate_and_nonfinite(self):
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}'):
            with self.assertRaises(ValueError):m.decode(raw)

    def test_fixed_file_single_read_counts_and_saved_stat_are_actual(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'x';p.write_bytes(b'abc');counts=[]
            raw,stamp=m.fixed_file(p,3,counts.append)
            self.assertEqual(raw,b'abc');self.assertEqual(counts,[3]);self.assertEqual(stamp[3],3)
            with self.assertRaises(ValueError):m.fixed_file(p,2,counts.append)
            q=Path(tmp)/'link';q.symlink_to(p)
            with self.assertRaises(ValueError):m.fixed_file(q,3)


if __name__=='__main__':unittest.main()
