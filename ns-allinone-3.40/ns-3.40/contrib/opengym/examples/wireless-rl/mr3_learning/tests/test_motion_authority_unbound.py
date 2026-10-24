import copy,importlib.util,unittest
from pathlib import Path
from mr3_learning.tests.test_motion_authority_audit import graph,EPOCH
from mr3_learning import motion_authority_audit as a
class Tests(unittest.TestCase):
 def rows(self):
  rows=[]
  def put(kind,payload):rows.append(dict(schema='mr3-motion-safety-v1',epoch=EPOCH,record_sequence=len(rows)+1,kind=kind,payload=payload))
  put('configuration',dict(motion_authority_profile=a.PROFILE))
  for name in a.ROBOTS:
   expected=dict(effective_request=[0.,0.],permission='zero_only',state='UNBOUND',authority_sequence=0,owner=None,raw_goal_generation=None,raw_goal_association='UNKNOWN_UNSTAMPED_TWIST')
   put('reach_decision',dict(robot=name,motion_authority_profile=a.PROFILE,decision_sequence=1,motion_authority=expected,effective_request=[0.,0.]))
   identity=graph();identity['topic']='/'+name+'/mr3/motion_authority'
   put('authority_configuration',dict(robot=name,motion_authority_profile=a.PROFILE,publisher_identity=identity))
  return rows
 def test_prebinding_zero_permissions_survive_configuration_for_full_fifo(self):
  report,context=a.replay_motion(self.rows(),{n:{} for n in a.ROBOTS},EPOCH,0)
  for n in a.ROBOTS:
   self.assertEqual(report['robots'][n]['decisions'],1)
   self.assertEqual(context['gates'][n].decision_permissions[1]['state'],'UNBOUND')
   self.assertEqual(context['gates'][n].decision_permissions[1]['effective_request'],[0.,0.])
 def test_nonzero_or_forged_prebinding_permission_rejected(self):
  for attack in ('output','state','owner','profile','sequence'):
   rows=self.rows();p=rows[1]['payload']
   if attack=='output':p['effective_request']=[.1,0.]
   elif attack=='state':p['motion_authority']['state']='ACTIVE'
   elif attack=='owner':p['motion_authority']['owner']={'goal_id':'forged'}
   elif attack=='profile':p['motion_authority_profile']='legacy'
   else:p['decision_sequence']=True
   with self.subTest(attack=attack),self.assertRaises(ValueError):a.replay_motion(rows,{n:{} for n in a.ROBOTS},EPOCH,0)
if __name__=='__main__':unittest.main(verbosity=2)
