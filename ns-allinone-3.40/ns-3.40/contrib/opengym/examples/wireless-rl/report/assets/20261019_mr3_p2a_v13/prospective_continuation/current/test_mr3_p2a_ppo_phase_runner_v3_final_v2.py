"""CPU-only counts/schema/source admission and real finite failure outer wait."""
import ast
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

def load(path,name):
    definition=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(definition);definition.loader.exec_module(m);return m
PATH=Path('/tmp/mr3_p2a_ppo_phase_runner_v3_final_v2.py');m=load(PATH,'ppo_v3_test')

class PPOV3CPU(unittest.TestCase):
    def fixture(self):
        return {'completed':True,'error':None,'cleanup_errors':[],'native_accounting_errors':[],
                'decisions':16,'collector_observed_decisions':16,'native_recorded_decisions':16,
                'api_records':18,'collector_observed_api_records':18,'quota_reached':True,'optimizer_updates':4}

    def test_minimum_native16_and_positive_updates(self):
        s=self.fixture();m.check_ppo_counts('minimum',s,{})
        for key,value in (('decisions',15),('optimizer_updates',0),('quota_reached',False)):
            altered=copy.deepcopy(s);altered[key]=value
            with self.assertRaises(ValueError):m.check_ppo_counts('minimum',altered,{})

    def test_returned_and_native_counts_cannot_diverge(self):
        s=self.fixture();s['native_recorded_decisions']=17
        with self.assertRaises(ValueError):m.check_ppo_counts('minimum',s,{})

    def test_original_pilot_quota_and_fresh_weights(self):
        s=self.fixture();m.check_ppo_counts('pilot',s,{'checkpoint':None})
        with self.assertRaises(ValueError):m.check_ppo_counts('pilot',s,{'checkpoint':'engineering.zip'})
        s.update(decisions=1871,collector_observed_decisions=1871,native_recorded_decisions=1871)
        with self.assertRaises(ValueError):m.check_ppo_counts('pilot',s,{'checkpoint':None})

    def test_final_only_validation_three_strict_successes_no_updates(self):
        s=self.fixture();s.update(optimizer_updates=0,schedule_completed=True,episodes=[{}, {}, {}])
        m.check_ppo_counts('validation',s,{}, {'task_successes':3,'task_failures':[]})
        for full in ({'task_successes':2,'task_failures':[]},{'task_successes':3,'task_failures':['failure']}):
            with self.assertRaises(ValueError):m.check_ppo_counts('validation',s,{},full)
        s['optimizer_updates']=1
        with self.assertRaises(ValueError):m.check_ppo_counts('validation',s,{})

    def test_original_v2_retained_functions_exact_ast(self):
        def functions(path):return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text()).body if isinstance(n,ast.FunctionDef)}
        base,new=functions(m.V2),functions(PATH)
        self.assertEqual(m.digest(m.V2),m.V2_SHA)
        for name in ('require','digest','inputs_reader','check_ppo_counts','outer','final_absence'):
            self.assertEqual(base[name],new[name],name)
        self.assertNotEqual(m.SCHEMA,'mr3-p2a-ppo-phase-execution-v1')
        self.assertEqual(m.QUALIFICATION_SCHEMA,'mr3-p2a-v13-completed-38-role-qualification-v1')
        self.assertNotIn('mr3-preparation-execution-v1',ast.get_source_segment(PATH.read_text(),next(n for n in ast.parse(PATH.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='check_prerequisites')))

    def test_actual_git_exact_clean_published_ancestor(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            def git(*argv):return subprocess.check_output(['git',*argv],cwd=root,stderr=subprocess.DEVNULL,text=True).strip()
            git('init','-q');git('config','user.name','CPU fixture');git('config','user.email','cpu@example.invalid')
            f=root/'source';f.write_text('freeze');git('add','source');git('commit','-qm','freeze');freeze=git('rev-parse','HEAD')
            f.write_text('report');git('commit','-qam','later evidence');remote=git('rev-parse','HEAD')
            git('update-ref','refs/remotes/origin/main',remote);git('checkout','--detach','-q',freeze)
            self.assertEqual(m.check_runtime_git(root,freeze)['remote_head_at_admission'],remote)
            f.write_text('dirty')
            with self.assertRaisesRegex(ValueError,'exact clean'):m.check_runtime_git(root,freeze)
            git('checkout','--','source');git('checkout','--detach','-q',remote)
            with self.assertRaisesRegex(ValueError,'exact clean'):m.check_runtime_git(root,freeze)
            f.write_text('unpublished');git('commit','-qam','unpublished');unpublished=git('rev-parse','HEAD')
            with self.assertRaisesRegex(ValueError,'not published'):m.check_runtime_git(root,unpublished)

    def test_real_finite_failure_outer_wait_and_independent_absence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);evidence=root/'evidence';wait=root/'wait.json';final=root/'final.json'
            forward=['--plan',str(root/'MISSING.json'),'--evidence',str(evidence),'--balance',str(root/'MISSING_BALANCE.json'),
                     '--prior-summary',str(root/'MISSING_PRIOR.json'),'--prior-final-closure',str(root/'MISSING_FINAL.json'),
                     '--qualification',str(root/'MISSING_QUALIFICATION.json'),'--freeze','0063aa233ba3008ddcc1eb09ea8068112eea3965','--phase','minimum']
            run=subprocess.run([sys.executable,'-B',str(PATH),'outer','--freeze','0063aa233ba3008ddcc1eb09ea8068112eea3965','--phase','minimum','--output',str(wait),'--',*forward],capture_output=True,text=True)
            self.assertEqual(run.returncode,1,run.stderr)
            self.assertEqual(json.loads(wait.read_text())['returncode'],1)
            run=subprocess.run([sys.executable,'-B',str(PATH),'final-absence','--receipt',str(wait),'--evidence',str(evidence),'--output',str(final),'--freeze','0063aa233ba3008ddcc1eb09ea8068112eea3965','--phase','minimum'],capture_output=True,text=True)
            self.assertEqual(run.returncode,1,run.stderr)
            proof=json.loads(final.read_text());self.assertTrue(proof['closure_passed']);self.assertFalse(proof['execution_passed'])
            self.assertFalse(proof['passed']);self.assertEqual(proof['saved_identity_count'],2)

    def test_qualification_tail_overrun_or_missing_actual_boundaries_rejected(self):
        from types import SimpleNamespace
        completion=m.completion_tool()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);q=root/'synthetic_negative_qualification.json';q.write_text('{}')
            args=SimpleNamespace(freeze=completion.FREEZE,qualification=q)
            tail_path=root/'negative_tail.json'
            tail={'schema':'mr3-p2a-external-root-accounting-v1','freeze':completion.FREEZE,
                  'phase':'preparation_qualification_tail','budget_pool':'engineering',
                  'engineering_ceiling_wall_seconds':'34000','total_phase_wall_allocation_seconds':'100',
                  'charged_wall_seconds':'100.000000001','within_allocation':True,'cumulative_within_ceiling':True}
            tail_path.write_text(json.dumps(tail));balance={'qualification_tail_accounting':completion.spec(tail_path)}
            with self.assertRaisesRegex(ValueError,'new100'):m.check_qualification_tail(balance,args,{},completion,lambda p:Path(p).read_bytes(),completion.js)
            tail.update(charged_wall_seconds='10',prior_used_wall_seconds='24000',cumulative_used_wall_seconds='24010',
                        remaining_wall_seconds='9990',qualification=completion.spec(q),qualifier_tool=completion.spec(m.DEADLINE),basis=[])
            tail_path.write_text(json.dumps(tail));balance['qualification_tail_accounting']=completion.spec(tail_path)
            with self.assertRaisesRegex(ValueError,'basis omitted'):m.check_qualification_tail(balance,args,{},completion,lambda p:Path(p).read_bytes(),completion.js)

    def test_claimed_absence_cannot_hide_live_finite_launcher(self):
        from types import SimpleNamespace
        import time
        completion=m.completion_tool()
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);q=root/'synthetic_negative_qualification.json';q.write_text('{}')
            previous=root/'synthetic_previous.json';previous.write_text('{}')
            args=SimpleNamespace(freeze=completion.FREEZE,qualification=q)
            started=time.monotonic_ns();child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(.05)'])
            saved=m.prep.identity(child.pid);launcher=m.prep.identity(os.getpid());child.wait();ended=time.monotonic_ns()
            # Deliberately forged metadata, never an assertion this CPU child ran
            # qualify. The actual currently live launcher must be rejected.
            paths={k:str(root/k) for k in ('plan','summary','final','outer')}
            qualification={'deadline_completion_paths':paths,'external_tail_accounting':completion.spec(previous)}
            argv=['/usr/bin/python3','-B',str(m.DEADLINE),'qualify']
            for name in ('plan','summary','final','outer'):argv += ['--'+name,paths[name]]
            argv += ['--accounting',str(previous),'--output',str(q)]
            wait_path=root/'synthetic_wait.json'
            wait={'schema':'mr3-preparation-command-receipt-v1','freeze':completion.FREEZE,'id':'qualify',
                  'execution_kind':'subprocess_waited','returncode':0,'errors':[],'passed':True,'argv':argv,'command_argv':argv,
                  'output':str(q),'output_sha256':m.digest(q),'process_identity':saved,
                  'launcher_identity':launcher,'coordinator_identity':launcher,
                  'started_wall_monotonic_ns':started,'ended_wall_monotonic_ns':ended}
            wait_path.write_text(json.dumps(wait))
            tail={'schema':'mr3-p2a-external-root-accounting-v1','freeze':completion.FREEZE,'phase':'preparation_qualification_tail',
                  'budget_pool':'engineering','engineering_ceiling_wall_seconds':'34000','total_phase_wall_allocation_seconds':'100',
                  'charged_wall_seconds':'10','within_allocation':True,'cumulative_within_ceiling':True,
                  'prior_used_wall_seconds':'24000','cumulative_used_wall_seconds':'24010','remaining_wall_seconds':'9990',
                  'qualification':completion.spec(q),'qualifier_tool':completion.spec(m.DEADLINE),
                  'qualifier_actual_wait':completion.spec(wait_path),'deadline_accounting':completion.spec(previous),
                  'qualifier_absence':{'all_saved_identities_gone':True,'identities':[
                      {'saved':saved,'current':None,'same_identity_present':False},
                      {'saved':launcher,'current':None,'same_identity_present':False}]}}
            tail['basis']=[tail[k] for k in ('qualification','qualifier_tool','qualifier_actual_wait','deadline_accounting')]
            path=root/'synthetic_tail.json';path.write_text(json.dumps(tail))
            with self.assertRaisesRegex(ValueError,'identity remains'):
                m.check_qualification_tail({'qualification_tail_accounting':completion.spec(path)},args,qualification,completion,lambda p:Path(p).read_bytes(),completion.js)

if __name__=='__main__':unittest.main()
