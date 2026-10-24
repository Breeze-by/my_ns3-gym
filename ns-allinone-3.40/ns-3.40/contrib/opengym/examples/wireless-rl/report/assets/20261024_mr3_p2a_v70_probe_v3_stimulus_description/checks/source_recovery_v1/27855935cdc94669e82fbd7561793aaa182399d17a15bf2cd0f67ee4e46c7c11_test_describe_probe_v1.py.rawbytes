"""Artificial producer-generated transitions; no original V69 input or consumer main."""
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
from mr3_learning.tests.test_reach_outward_cancel_v3_producer import Fixture,consume as produce
from mr3_learning import benchmark
spec=importlib.util.spec_from_file_location('fixed_v70_description',HERE/'describe_probe_v1.py')
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
        _,info=produce(f,diag,snap)
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
    try:benchmark.finish_probe_reach_v3(last,diag)
    except ValueError as exc:error=str(exc)
    summary=dict(freeze=m.ORIGINAL_FREEZE,safety_contract='mr3-reach-v1',preparation_probe_version=m.PROBE,
        workers=1,schedule=[['open',101]],passed=error is None,
        workers_results=[dict(worker_id=0,error=error,episodes=[dict(epoch=f.dispatcher.epoch,scene='open',seed=101,
            transitions=32,preparation_probe_diagnostics=diag)])])
    return transitions,summary,f.dispatcher.epoch


class DescribeV3Tests(unittest.TestCase):
    def test_complete_actual_python_producer_lifecycle_has_exact_independent_match(self):
        t,s,e=trace();d=m.describe(t,s,e)
        self.assertTrue(d['passed']);self.assertTrue(all(d['comparisons'].values()))
        self.assertTrue(d['independent_coverage_passed']);self.assertEqual(len(d['tb3_received_timeline']),33)
        self.assertTrue(all(len(x['current_round']['candidates'])==8 for x in d['tb3_received_timeline']))
        self.assertEqual(d['tb3_received_timeline'][0]['activity']['estimated_path_m'],None)
        self.assertLess(len(m.canonical(d)),m.LIMITS['max_output_bytes'])

    def test_succeeded_aborted_and_unsolicited_canceled_are_described_as_distinct_real_failures(self):
        for terminal in ('SUCCEEDED','ABORTED','CANCELED'):
            with self.subTest(terminal=terminal):
                t,s,e=trace(terminal=terminal);d=m.describe(t,s,e)
                self.assertTrue(d['passed']);self.assertFalse(d['independent_coverage_passed']);self.assertTrue(d['original_FAIL_preserved'])
                events=d['tb3_first_observed_terminals'];self.assertEqual(len(events),1)
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
        s['workers_results'][0]['episodes'][0]['preparation_probe_diagnostics']['reach_v3_stimulus']['rounds']['initial']['tb3']['baseline_path_m']=0.
        forged=m.describe(t,s,e);self.assertFalse(forged['passed']);self.assertFalse(forged['comparisons']['whole_stimulus_state_equal'])

    def test_old_source_defers_capture_and_never_refreshes_baseline(self):
        t,s,e=trace(old_source=True);d=m.describe(t,s,e)
        self.assertTrue(d['passed']);saved=d['robot_rounds'][2]['reconstructed']
        self.assertEqual(saved['baseline_observed_ns'],2*10**9);self.assertEqual(saved['baseline_capture_count'],1)
        self.assertEqual(saved['baseline_path_m'],.1)

    def test_short_goal_and_long_available_alternatives_are_reported_without_a_threshold(self):
        for long_available in (False,True):
            t,s,e=trace(long_available=long_available);d=m.describe(t,s,e);self.assertTrue(d['passed'])
            first=d['initial_bank_and_joint_rank'];rows=first['robots'][2]['candidates'];chosen=[x for x in rows if x['chosen']]
            self.assertEqual(len(chosen),1);self.assertEqual(chosen[0]['path_distance_m'],1.6 if long_available else .8)
            if long_available:self.assertTrue(any(x['currently_eligible'] and x['path_distance_m']==.8 for x in rows))
            legal=first['all_original_legal_nonapproach_joint_choices'];subset=[x for x in legal if x['in_V3_desired_subset']]
            self.assertEqual(min(subset,key=lambda x:tuple(x['rank']))['action'],first['selected_action'])
            self.assertTrue(all(x['action'] in range(1000) for x in legal))

    def test_cleanup_wait_and_owned_later_bank_are_not_counterfactual_goal_credit(self):
        t,s,e=trace(terminal='SUCCEEDED');d=m.describe(t,s,e)
        owned=d['tb3_received_timeline'][1]['current_round'];self.assertFalse(owned['GOAL_common']['unowned'])
        cleanup=[r for r in d['tb3_received_timeline'] if r['current_round']['mode']=='bounded_cleanup_wait_no_credit']
        self.assertTrue(cleanup);self.assertNotIn('wait_command_id',d['robot_rounds'][2]['reconstructed'])

    def test_post_snapshot_command_binding_and_digest_tamper_fail_closed(self):
        t,s,e=trace();t[1]['info']['command']['observation_sequence']=t[1]['snapshot']['sequence']
        with self.assertRaisesRegex(ValueError,'previous snapshot'):m.describe(t,s,e)
        t,s,e=trace();t[1]['snapshot']['robots'][2]['v']=.123
        with self.assertRaisesRegex(ValueError,'digest'):m.describe(t,s,e)

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
