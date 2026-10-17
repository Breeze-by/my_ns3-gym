"""Small stdlib actual-main scheduler fixtures; no real formal/native subprocess."""
import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SOURCE=Path(__file__).with_name('mr3_p2a0_v12_audit_stage.py')
ROOT=Path('/home/zhuyulab/ns3-workspace')
OLD_PLAN=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v11/predeclared_plan_v11.json'
FREEZE='a'*40


class SchedulerTests(unittest.TestCase):
    def exercise(self, stage, mutation=None):
        directory=Path(tempfile.mkdtemp(prefix='mr3_v12_scheduler_fixture_'))
        root=directory/'root';wireless=root/'wireless';wireless.mkdir(parents=True)
        assets=root/'assets';local=assets/'20261017_mr3_p2a0_v10/independent';local.mkdir(parents=True)
        outputs=directory/'outputs';outputs.mkdir();run=root/'run'
        count={'interface':1,'reset':8}[stage]
        for index in range(count):(run/f'worker{index//4}'/f'episode{index%4+1:03d}').mkdir(parents=True)
        plan=json.loads(OLD_PLAN.read_text())
        for row in plan['stages']:
            row['run_directory']=str(run)
            row['required_audit_receipts']=[str(outputs/Path(v.replace('v11','v12')).name)for v in row['required_audit_receipts']]
            for key in('information','peer','control','settled_turn'):
                argv=row[key+'_audit_command_template'];argv[2]=str(run)
                argv[argv.index('--output')+1]=str(outputs/Path(argv[argv.index('--output')+1].replace('v11','v12')).name)
        selected=next(x for x in plan['stages']if x['stage']==stage)
        if mutation=='main_exception':
            selected['peer_audit_command_template']=['/usr/bin/python3','not_executed.py',str(run)]
        tracked=root/'fixture_source';tracked.write_bytes(b'explicit mocked binding\n')
        plan['independent_source_bindings']=[{'path':'fixture_source','sha256':hashlib.sha256(tracked.read_bytes()).hexdigest()}]
        plan_path=assets/'20261017_mr3_p2a0_v12/predeclared_plan_v12.json';plan_path.parent.mkdir();plan_path.write_text(json.dumps(plan))
        prefix='mr3_p2a0_v12_'+stage
        if mutation=='collision':(outputs/(prefix+'_drive_review_v1.json')).write_bytes(b'ORIGINAL KEEP\n')
        namespace={'__name__':'scheduler_fixture','__file__':str(SOURCE)}
        exec(compile(SOURCE.read_bytes(),str(SOURCE),'exec'),namespace)
        namespace.update(ROOT=root,WIRELESS=wireless,ASSETS=assets,LOCAL=local)
        namespace['Path']=lambda value:outputs if str(value)=='/tmp'else Path(value)
        lock=threading.Lock();state={'active':0,'maximum':0,'started':[],'finished':[],'fifos':set(),'physical_done':False,'pool_checked':False,'closure_checked':False}
        def check_output(command,**kwargs):
            if command==['git','rev-parse','HEAD']:return FREEZE+'\n'
            self.assertEqual(command,['git','status','--porcelain']);return ''
        def fake_run(command,**kwargs):
            self.assertEqual(kwargs['cwd'],wireless)
            self.assertNotIn('PYTHONPATH',kwargs['env'])
            script='full'if command[1:3]==['-m','mr3_learning.audit_preparation']else Path(command[1]).name
            closure=script=='mr3_v12_multiepoch_closure_binary_review_v1.py'
            output=(outputs/(prefix+'_closure_binary_review_v1.json')if closure else Path(command[command.index('--output')+1]))
            with lock:
                state['active']+=1;state['maximum']=max(state['maximum'],state['active']);state['started'].append(script)
            try:
                # All waits belong to explicit fake subprocesses, never a native process.
                time.sleep(.01)
                if mutation=='job_exception'and script=='mr3_independent_drive_trace_v5.py':
                    raise OSError('synthetic audit spawn failure')
                if script=='mr3_independent_drive_trace_v5.py':
                    self.assertEqual(command[command.index('--binary-proof')+1],'/tmp/mr3_p2a0_v12_binaryproof.json')
                if script in('mr3_independent_physics_review.py','mr3_independent_angular_interface_v1.py','mr3_p2a0_v4_independent_input_episode_review_v1.py'):
                    self.assertNotIn('--freeze',command)
                if script=='mr3_independent_physics_matrix_v8.py':
                    with lock:self.assertTrue(state['physical_done']);state['pool_checked']=True
                    raw=Path(command[command.index('--per-episode-report')+1]);self.assertFalse(json.loads(raw.read_text())['passed'])
                if closure:
                    with lock:self.assertEqual(len(state['fifos']),count);state['closure_checked']=True
                    self.assertEqual(command[command.index('--prefix')+1],prefix)
                passed=True;code=0
                if stage=='reset'and script=='mr3_independent_physics_review.py':passed=False;code=1
                if mutation=='pool_fail'and script=='mr3_independent_physics_matrix_v8.py':passed=False;code=1
                if mutation=='leaf_fail'and script=='mr3_p2a0_v4_independent_input_episode_review_v1.py'and output.name.endswith('_episode001_input_v1.json'):passed=False;code=1
                self.assertFalse(output.exists())
                output.write_text(json.dumps({'passed':passed,'freeze':FREEZE,'fixture_only':True}))
                kwargs['stdout'].write(json.dumps({'argv':command,'fixture_only':True})+'\n')
                with lock:
                    if script=='mr3_v10_fifo_phase_review.py':state['fifos'].add(command[2])
                    if stage=='reset'and script=='mr3_independent_physics_review.py':state['physical_done']=True
                return subprocess.CompletedProcess(command,code)
            finally:
                with lock:state['active']-=1;state['finished'].append(script)
        namespace['subprocess']=type('FakeSubprocess',(),{'STDOUT':subprocess.STDOUT,'check_output':staticmethod(check_output),'run':staticmethod(fake_run)})
        oldargv=sys.argv;sys.argv=[str(SOURCE),stage,FREEZE]
        try:
            with contextlib.redirect_stdout(io.StringIO()):code=namespace['main']()
        finally:sys.argv=oldargv
        result=json.loads((outputs/(prefix+'_audit_execution_v1.json')).read_text())
        self.assertEqual(state['active'],0)
        self.assertCountEqual(state['started'],state['finished'])
        self.assertTrue(result['all_submitted_jobs_finished'])
        self.assertLessEqual(state['maximum'],4)
        self.assertEqual(result['max_workers'],4)
        return result,state,outputs,code

    def test_reset_four_workers_both_dependencies_and_raw_fail_retained(self):
        result,state,outputs,code=self.exercise('reset')
        self.assertEqual(code,0);self.assertTrue(result['passed']);self.assertEqual(state['maximum'],4)
        self.assertTrue(state['pool_checked']and state['closure_checked']);self.assertEqual(len(result['commands']),26)
        raw=next(x for x in result['commands']if x['label']=='physical_per_episode_v1')
        self.assertFalse(raw['passed']);self.assertFalse(raw['required_success']);self.assertEqual(raw['returncode'],1)
        self.assertEqual(len(json.loads((outputs/'mr3_p2a0_v12_reset_input_review_v1.json').read_text())['episodes']),8)

    def test_interface_original_cli_paths_and_dependency(self):
        result,state,_,code=self.exercise('interface')
        self.assertEqual(code,0);self.assertTrue(result['passed']);self.assertEqual(len(result['commands']),11)
        self.assertEqual(state['maximum'],4);self.assertTrue(state['closure_checked'])

    def test_pool_failure_does_not_skip_or_orphan_other_audits(self):
        result,state,_,code=self.exercise('reset','pool_fail')
        self.assertEqual(code,1);self.assertFalse(result['passed']);self.assertEqual(len(state['finished']),26)

    def test_worker_spawn_exception_drains_every_other_audit(self):
        result,state,_,code=self.exercise('interface','job_exception')
        self.assertEqual(code,1);self.assertFalse(result['passed']);self.assertEqual(len(state['finished']),11)
        failed=next(x for x in result['commands']if x['label']=='drive_review_v1');self.assertIn('synthetic audit spawn failure',failed['error'])

    def test_main_scheduling_exception_drains_already_owned_jobs(self):
        result,state,_,code=self.exercise('interface','main_exception')
        self.assertEqual(code,1);self.assertFalse(result['passed']);self.assertTrue(result['runner_errors'])
        self.assertEqual(len(state['finished']),3)

    def test_existing_output_not_overwritten_others_drained(self):
        result,state,outputs,code=self.exercise('interface','collision')
        self.assertEqual(code,1);self.assertFalse(result['passed']);self.assertEqual(len(state['finished']),10)
        self.assertEqual((outputs/'mr3_p2a0_v12_interface_drive_review_v1.json').read_bytes(),b'ORIGINAL KEEP\n')

    def test_failed_leaf_retained_all_eight_complete(self):
        result,state,outputs,code=self.exercise('reset','leaf_fail')
        self.assertEqual(code,1);self.assertFalse(result['passed']);self.assertEqual(len(state['finished']),26)
        aggregate=json.loads((outputs/'mr3_p2a0_v12_reset_input_review_v1.json').read_text())
        self.assertFalse(aggregate['passed']);self.assertEqual(len(aggregate['episodes']),8)


if __name__=='__main__':unittest.main()
