"""Artificial pending-to-activation checks; no native/physical credit."""
import copy,importlib.util,unittest
from pathlib import Path
R=Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap')
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
from multi_robot_exploration import mr3_motion_authority as core
f=load('phase_actual_feed',R/'src/multi_robot_exploration/test/test_mr3_reach_runtime_independent.py')
class Tests(unittest.TestCase):
 def setup_gate(self):
  feed=f.Feed().disk();gate=core.MotionAuthority(f.EPOCH,'tb1','g');now=feed.now
  p=dict(schema=core.PROTOCOL,epoch=f.EPOCH,robot='tb1',operation='grant',authority_sequence=1,
    owner_grant_sequence=1,goal_id=f.EPOCH+':tb1:1',native_goal_uuid='11'*16,owner_command_id=1,
    source_clock_ns=now,owner_accept_received_clock_ns=now,lease_until_ns=now+2_000_000_000)
  return feed,gate,p
 def receive(self,g,p,now):return g.receive(p,publisher_gid='g',clock_ns=now,latest_raw_sequence=7)
 def test_missing_stop_is_pending_never_motion_and_fresh_phase_sets_floor(self):
  feed,g,p=self.setup_gate();r=self.receive(g,p,feed.now)
  self.assertEqual(r['state'],'PENDING');self.assertIsNone(g.fault)
  request=dict(sequence=7,v=.2,w=.1)
  self.assertEqual(g.input(request,clock_ns=feed.now)['effective_request'],[0.,0.])
  actual=feed.r.causal_applied;feed.r.causal_applied=None
  self.assertIsNone(g.observe_stop(feed.r,feed.now,latest_raw_sequence=7));self.assertEqual(g.state,'PENDING')
  feed.r.causal_applied=actual
  ack=g.observe_stop(feed.r,feed.now,latest_raw_sequence=7)
  self.assertEqual(ack['stage'],'authority_activated');self.assertEqual(ack['witness']['clock_ns'],feed.now)
  self.assertEqual(g.input(request,clock_ns=feed.now)['effective_request'],[0.,0.])
  self.assertEqual(g.input(dict(request,sequence=8),clock_ns=feed.now)['effective_request'],[.2,.1])
 def test_pending_expiry_and_revoke_cannot_activate(self):
  for mode in ('expiry','revoke'):
   feed,g,p=self.setup_gate();self.receive(g,p,feed.now)
   if mode=='expiry':
    g.input(dict(sequence=8,v=.2,w=0.),clock_ns=p['lease_until_ns'])
   else:
    revoke=dict(p,operation='revoke',authority_sequence=2,lease_until_ns=feed.now)
    self.receive(g,revoke,feed.now)
   self.assertEqual(g.state,'REVOKED');self.assertIn(core.identity_key(p),g.retired)
   self.assertEqual(g.input(dict(sequence=9,v=.2,w=0.),clock_ns=p['lease_until_ns'])['effective_request'],[0.,0.])
 def test_pending_renewal_never_grants_motion_or_changes_owner(self):
  feed,g,p=self.setup_gate();self.receive(g,p,feed.now)
  renewal=dict(p,operation='renew',authority_sequence=2,source_clock_ns=feed.now+20_000_000,lease_until_ns=feed.now+2_020_000_000)
  self.assertEqual(self.receive(g,renewal,feed.now+20_000_000)['state'],'PENDING')
  self.assertEqual(g.callback_floor,0)
  bad=dict(renewal,authority_sequence=3,native_goal_uuid='22'*16)
  self.assertEqual(self.receive(g,bad,feed.now+20_000_000)['rejected_condition'],'renew_not_active_owner')
  self.assertEqual(g.input(dict(sequence=99,v=.2,w=0.),clock_ns=feed.now+20_000_000)['effective_request'],[0.,0.])
if __name__=='__main__':unittest.main(verbosity=2)
