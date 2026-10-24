"""Artificial original-dispatcher checks, without native/physical credit."""
import copy
import unittest
from mr3_learning.decisive_probe import Probe
from mr3_learning.audit_decisive_stimulus import replay
from .test_reach_outward_cancel_v3_producer import Fixture
from .test_reach_masked_cancel_producer import accept, finish_cancels


class DecisiveProbeTests(unittest.TestCase):
    def test_independent_replay_accepts_events_and_rejects_tampering(self):
        f,p=Fixture(),Probe();rows=[];decisions=[];prior=None
        for t in range(33):
            if t==3:f.complete_all('SUCCEEDED',2.5)
            s=f.snapshot(t,path=t*.1,complete=True,speed=.08 if t in (12,22) else 0.)
            rows.append(dict(snapshot=copy.deepcopy(s),info=dict(command=prior)))
            if t==32:break
            action=p.choose(s);planned=copy.deepcopy(p.pending);info=f.apply(s,action)
            prior=copy.deepcopy(info['command']);p.submitted(info)
            decisions.append(dict(planned=planned,command=prior))
            accept(f,t+.1)
            if 9 in (action//100,action//10%10,action%10):finish_cancels(f,t)
        self.assertEqual(len(replay(rows,decisions,32)),3)
        wrong=copy.deepcopy(rows);wrong[12]['snapshot']['robots'][0]['v']=.079
        with self.assertRaisesRegex(ValueError,'moving'):replay(wrong,decisions,32)
        wrong=copy.deepcopy(decisions);wrong[0]['planned']['purposes']['tb1']='qualified1'
        with self.assertRaisesRegex(ValueError,'relabel'):replay(rows,wrong,32)

    def test_finite_warmup_then_two_real_dispatcher_cancels(self):
        fixture, probe = Fixture(), Probe()
        for t in range(32):
            if t == 3:
                fixture.complete_all('SUCCEEDED', 2.5)
            snapshot = fixture.snapshot(t, path=t*.1, complete=True, speed=.08 if t in (12,22) else 0.)
            action = probe.choose(snapshot)
            self.assertTrue(snapshot['joint_action_mask'][action])
            probe.submitted(fixture.apply(snapshot, action))
            accept(fixture,t+.1)
            if 9 in (action//100,action//10%10,action%10):
                finish_cancels(fixture,t)
        self.assertTrue(probe.result()['received_coverage_passed'],probe.result())
        for slots in probe.slots.values():
            self.assertEqual([s['purpose'] for s in slots],['warmup','qualified1','qualified2'])
            self.assertNotIn('wait_command_id',slots[0])
            self.assertTrue(all(s['wait_requested']-s['accepted']>=5 for s in slots[1:]))

    def test_actual_masks_cannot_be_overridden(self):
        snapshot=Fixture().snapshot(0,path=0.,complete=True)
        snapshot['per_robot_action_mask']=[[False]*10 for _ in range(3)]
        snapshot['joint_action_mask']=[False]*1000
        snapshot['joint_action_mask'][888]=True
        with self.assertRaisesRegex(ValueError,'no original legal'):
            Probe().choose(snapshot)

    def test_missing_path_is_not_zero_and_baseline_is_not_refreshed(self):
        f,p=Fixture(),Probe()
        s=f.snapshot(0,path=None,complete=False)
        p.submitted(f.apply(s,p.choose(s)));accept(f,.1)
        p.observe(f.snapshot(1,path=None,complete=False))
        self.assertTrue(all('baseline' not in x[0] for x in p.slots.values()))
        p.observe(f.snapshot(2,path=0.,complete=True))
        p.observe(f.snapshot(3,path=.9,complete=True))
        self.assertTrue(all(x[0]['baseline']==0 for x in p.slots.values()))

    def test_qualified_early_success_cannot_become_warmup_or_retry(self):
        f,p=Fixture(),Probe()
        s=f.snapshot(0,path=0.,complete=True)
        p.submitted(f.apply(s,p.choose(s)));accept(f,.1)
        for slots in p.slots.values():slots[0]['purpose']='qualified1'
        f.complete_all('SUCCEEDED',2.5)
        s=f.snapshot(3,path=.2,complete=True)
        self.assertEqual(p.choose(s),888)
        self.assertEqual(len(p.failures),3)
        self.assertTrue(all(len(slots)==1 and slots[0]['purpose']=='qualified1' for slots in p.slots.values()))

    def test_wait_requires_five_seconds_and_positive_motion(self):
        f,p=Fixture(),Probe()
        s=f.snapshot(0,path=0.,complete=True)
        p.submitted(f.apply(s,p.choose(s)));accept(f,.1)
        p.observe(f.snapshot(1,path=0.,complete=True))
        for slots in p.slots.values():slots[0]['purpose']='qualified1'
        for t,speed,path in [(4,.2,.2),(6,-.2,.2),(6,.079,.2),(6,.08,.049)]:
            s=f.snapshot(t,path=path,complete=True,speed=speed)
            self.assertFalse(p.moving(s,0,p.slots['tb1'][0]))
        s=f.snapshot(6,path=.05,complete=True,speed=.08)
        self.assertTrue(p.moving(s,0,p.slots['tb1'][0]))

    def test_returned_command_and_epoch_are_bound(self):
        f,p=Fixture(),Probe();s=f.snapshot(0,path=0.,complete=True)
        action=p.choose(s);info=f.apply(s,action)
        wrong=copy.deepcopy(info);wrong['command']['observation_digest']='foreign'
        with self.assertRaisesRegex(ValueError,'returned command'):p.submitted(wrong)
        with self.assertRaisesRegex(ValueError,'unresolved'):p.choose(s)
        p.submitted(info)
        s['epoch']='foreign'
        with self.assertRaisesRegex(ValueError,'cross epoch'):p.observe(s)

    def test_bounded_warmup_failure_is_not_hidden(self):
        f,p=Fixture(),Probe();s=f.snapshot(0,path=0.,complete=True)
        p.submitted(f.apply(s,p.choose(s)));accept(f,.1)
        p.observe(f.snapshot(32,path=0.,complete=True))
        self.assertEqual(len(p.failures),3)
        self.assertFalse(p.result()['received_coverage_passed'])


if __name__=='__main__':unittest.main()
