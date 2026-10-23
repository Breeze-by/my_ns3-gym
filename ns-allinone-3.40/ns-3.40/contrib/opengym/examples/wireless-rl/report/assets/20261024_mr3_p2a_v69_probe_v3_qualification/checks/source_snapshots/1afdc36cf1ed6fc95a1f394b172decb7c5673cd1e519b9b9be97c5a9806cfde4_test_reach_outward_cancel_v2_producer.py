"""Current canonical v2 producer and actual protocol/masks; no native inputs."""
import ast
import copy
import hashlib
import subprocess
from pathlib import Path
import unittest
from mr3_learning import benchmark
from mr3_learning.supervisor import WORKSPACE as ROOT
from .mr3_probe_lifecycle_fixture import Lifecycle
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
choose=benchmark.probe_action_reach_v2
record=benchmark.record_probe_reach_v2_submission
finish=benchmark.finish_probe_reach_v2
tree=ast.parse(Path(benchmark.__file__).read_text())
assert Path(benchmark.__file__).resolve()==(W/'mr3_learning/benchmark.py').resolve()
BASELINE_COMMIT='935b466bd076002afdfe161b55a508938de2a8b0'
BASELINE_SHA256='ec77b8284b74e5757e8ce1ec18e0fdbbd508fa42945d8217a6db9272ed16805a'
class ProducerTests(unittest.TestCase):
    def snap(self,life,t,*,moving=True):
        if t<=6:x=.2*t;speed=.2 if t else 0.
        elif t<13:x=1.21;speed=0.
        elif t<=19:x=1.21+.2*(t-13);speed=.2 if t>13 else 0.
        else:x=2.42;speed=0.
        snap=life.snapshot(float(t),x=x,speed=speed if moving else 0.,path=x)
        snap['source_stamp']=float(t)
        if t>=13:
            for goal in snap['candidates']:goal['x']+=1.21
        return snap

    def cancel(self,life,t):
        life.advance(t+.05)
        for name,state in life.dispatcher.states.items():
            life.dispatcher.on_cancel_response(name,state.goal_id,True,t+.05)
        self.assertFalse(life.dispatcher.closed)
        life.complete_all(5,t+.1)

    def test_two_rounds_all_three_real_owners_complete_exactly32_submissions(self):
        life,diag=Lifecycle(),{}
        for t in range(32):
            snap=self.snap(life,t);action=choose(snap,diag)
            self.assertTrue(snap['joint_action_mask'][action])
            record(diag,life.apply(snap,action))
            if t in (0,13):
                self.assertEqual(action,345);life.accept_all(t+.1)
            if t in (6,19):
                self.assertEqual(action,999);self.cancel(life,t)
            if t==7:
                self.assertFalse(any('handoff_observed_ns' in s for s in diag['reach_v2_stimulus']['rounds']['initial'].values()))
        finish(self.snap(life,32),diag)
        state=diag['reach_v2_stimulus']
        self.assertTrue(state['coverage_passed'])
        self.assertEqual(len(state['decisions']),32)
        self.assertEqual(len([e for e in life.events if e['type']=='send_goal']),6)
        self.assertEqual(len([e for e in life.events if e['type']=='cancel_goal']),6)

    def test_short_candidates_keep_masks_and_fail_coverage_without_retry(self):
        life,diag=Lifecycle(),{}
        for t in range(32):
            snap=self.snap(life,t,moving=False)
            for goal in snap['candidates']:goal['valid']=False
            # Recompute original masks after removing received candidates.
            from .mr3_probe_lifecycle_fixture import _action_masks
            snap['per_robot_action_mask'],snap['joint_action_mask'],_= _action_masks(snap['robots'],snap['candidates'],float(t))
            action=choose(snap,diag);record(diag,life.apply(snap,action))
        with self.assertRaisesRegex(ValueError,'coverage unavailable'):finish(self.snap(life,32,moving=False),diag)
        self.assertFalse(diag['reach_v2_stimulus']['coverage_passed'])
        self.assertEqual([e for e in life.events if e['type']=='send_goal'],[])

    def test_real_success_before_commitment_never_counts_idle_wait_as_cancel(self):
        life,diag=Lifecycle(),{}
        snap=self.snap(life,0);record(diag,life.apply(snap,choose(snap,diag)));life.accept_all()
        snap=self.snap(life,1);self.assertFalse(snap['per_robot_action_mask'][0][9]);self.assertEqual(choose(snap,diag),888)
        record(diag,life.apply(snap,888));life.complete_all(4,3.9)
        snap=self.snap(life,10,moving=False);record(diag,life.apply(snap,choose(snap,diag)))
        snap=self.snap(life,13,moving=False);self.assertEqual(choose(snap,diag),888)
        self.assertTrue(diag['reach_v2_stimulus']['coverage_failures'])
        self.assertEqual([e for e in life.events if e['type']=='cancel_goal'],[])

    def test_cancel_acceptance_without_terminal_does_not_enable_second_goal(self):
        life,diag=Lifecycle(),{}
        for t in range(7):
            snap=self.snap(life,t);record(diag,life.apply(snap,choose(snap,diag)))
            if t==0:life.accept_all()
        life.advance(6.05)
        for name,state in life.dispatcher.states.items():life.dispatcher.on_cancel_response(name,state.goal_id,True,6.05)
        snap=self.snap(life,13,moving=False);self.assertEqual(choose(snap,diag),888)
        self.assertFalse(life.dispatcher.closed)
        self.assertFalse(any('cancel_terminal_observed_ns' in row for row in diag['reach_v2_stimulus']['rounds']['initial'].values()))

    def test_unsubmitted_or_wrong_command_never_latches_scientific_wait(self):
        life,diag=Lifecycle(),{}
        for t in range(6):
            snap=self.snap(life,t);record(diag,life.apply(snap,choose(snap,diag)))
            if t==0:life.accept_all()
        snap=self.snap(life,6);self.assertEqual(choose(snap,diag),999)
        bad={'command':dict(epoch=snap['epoch'],command_id=True,action=999,
            observation_sequence=snap['sequence'],observation_digest=snap['digest'])}
        with self.assertRaises(ValueError):record(diag,bad)
        record(diag,{'action_submitted':False})
        self.assertFalse(any('wait_command_id' in row for row in diag['reach_v2_stimulus']['rounds']['initial'].values()))
        self.assertEqual([e for e in life.events if e['type']=='cancel_goal'],[])

    def test_external_stop_cannot_confirm_a_merely_submitted_wait(self):
        life,diag=Lifecycle(),{}
        for t in range(6):
            snap=self.snap(life,t);record(diag,life.apply(snap,choose(snap,diag)))
            if t==0:life.accept_all()
        snap=self.snap(life,6);self.assertEqual(choose(snap,diag),999)
        # A worker can return the genuinely published command even when its
        # adapter action was rejected. Another stop cause must not earn credit.
        record(diag,{'command':dict(epoch=snap['epoch'],command_id=snap['sequence'],
            action=999,observation_sequence=snap['sequence'],observation_digest=snap['digest'])})
        life.dispatcher.safety_stop(6.,'task_failure')
        self.cancel(life,6)
        choose(self.snap(life,7,moving=False),diag)
        members=diag['reach_v2_stimulus']['rounds']['initial']
        self.assertFalse(any('cancel_terminal_observed_ns' in row for row in members.values()))
        self.assertTrue(diag['reach_v2_stimulus']['coverage_failures'])

    def test_legacy_selector_function_ASTs_unchanged(self):
        # Exact historical source bytes are an immutable test oracle only.
        data=subprocess.check_output(['git','show',BASELINE_COMMIT+':'+
            'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/benchmark.py'],cwd=ROOT)
        self.assertEqual(hashlib.sha256(data).hexdigest(),BASELINE_SHA256)
        original=ast.parse(data.decode())
        for name in ('_probe_goal_order','probe_action','probe_action_v3','probe_action_v4',
                     'probe_action_v5','probe_action_v6','record_probe_v4_submission'):
            a=next(node for node in original.body if isinstance(node,ast.FunctionDef) and node.name==name)
            b=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name==name)
            self.assertEqual(ast.dump(a),ast.dump(b))
