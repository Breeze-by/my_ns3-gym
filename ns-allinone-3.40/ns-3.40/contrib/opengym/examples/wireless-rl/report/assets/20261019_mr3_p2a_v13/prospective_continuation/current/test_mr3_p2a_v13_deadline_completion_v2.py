"""CPU structural/failure-boundary tests; no native/scientific reader started."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

PATH=Path('/tmp/mr3_p2a_v13_deadline_completion_v2.py')
def load():
    definition=importlib.util.spec_from_file_location('completion_test',PATH)
    value=importlib.util.module_from_spec(definition);definition.loader.exec_module(value);return value
m=load()

class CompletionCPU(unittest.TestCase):
    def test_only_declared_native_wall_and_exclusive_evidence_delta(self):
        base=json.loads((m.WIRELESS/'report/assets/20261019_mr3_p2a_v13/predeclared_plan_v13.json').read_text())
        old=copy.deepcopy(base);new=m.deadline_stage(base,Path('/tmp/prospective_deadline_cpu_only'))
        self.assertEqual(base,old)
        self.assertEqual(m.prep.argument(new['native']['argv'],'--work-wall-seconds'),'6200')
        restored=copy.deepcopy(new['native']['argv']);restored[restored.index('--work-wall-seconds')+1]='4500'
        self.assertEqual(restored,old['stages'][3]['native']['argv'])
        self.assertEqual(new['run_directory'],old['stages'][3]['run_directory'])
        self.assertEqual([j['id'] for j in new['audits']],[j['id'] for j in old['stages'][3]['audits']])
        self.assertEqual([j['depends_on'] for j in new['audits']],[j['depends_on'] for j in old['stages'][3]['audits']])
        self.assertEqual(new['watcher']['ready'],'/tmp/prospective_deadline_cpu_only/custody_ready.json')
        for new_job,old_job in zip(new['audits'],old['stages'][3]['audits']):
            if 'argv' in old_job:
                restored=[x.replace('/tmp/prospective_deadline_cpu_only','/tmp/mr3_p2a_v13_matrix_evidence/deadline').replace(m.FREEZE,'{freeze}') for x in new_job['argv']]
                self.assertEqual(restored,old_job['argv'])

    def test_changed_original_workload_or_role_rejected(self):
        base=json.loads((m.WIRELESS/'report/assets/20261019_mr3_p2a_v13/predeclared_plan_v13.json').read_text())
        for mutation in ('steps','role'):
            changed=copy.deepcopy(base)
            if mutation=='steps':
                argv=changed['stages'][3]['native']['argv'];argv[argv.index('--steps')+1]='299'
            else: changed['stages'][3]['audits'][0]['role']='substitute'
            with self.assertRaises(ValueError):m.deadline_stage(changed,Path('/tmp/not_run'))

    def native_fixture(self):
        ep={'transitions':300,'dt_values':[1.0]*300,'terminated':True,'truncated':False,'reason':'timeout'}
        summary={'passed':True,'freeze':m.FREEZE,'workers':1,'robots_per_worker':3,'schedule':[['open',101]],
                 'steps_per_episode':300,'deadline_probe':True,'terminal_probe':False,'valid_transitions':300,
                 'workers_results':[{'error':None,'work_wall_abort':{'requested':False},'episodes':[ep]}]}
        rows=[{'kind':'reset'}]+[{'kind':'step','info':{'dt':1.0,'command':{'action':888,'command_id':i}},
                                'terminated':i==300,'truncated':False} for i in range(1,301)]
        return summary,rows

    def test_actual_keep_count_and_true_timeout_required(self):
        summary,rows=self.native_fixture();m.check_deadline_native(summary,rows)
        for kind in ('count','action','zero_tail','early_terminal'):
            s,r=copy.deepcopy(summary),copy.deepcopy(rows)
            if kind=='count':r.pop()
            elif kind=='action':r[127]['info']['command']['action']=999
            elif kind=='zero_tail':r[300]['info']['dt']=0.0
            else:r[150]['terminated']=True
            with self.assertRaises(ValueError):m.check_deadline_native(s,r)

    def test_current_balance_and_old_approval_cannot_admit(self):
        base={'schema':m.BALANCE_SCHEMA,'freeze':m.FREEZE,'budget_pool':'engineering','for_phase':'deadline_completion',
              'available_wall_seconds':'6324.3667588083982','accounted_through_wall_monotonic_ns':5,'basis':[{}]}
        with self.assertRaisesRegex(ValueError,'8500'):m.check_balance(base,{'wall_monotonic_ns':4})
        old=m.WIRELESS/'report/assets/20261019_mr3_p2a_v8/budget_acceptance_20261019.json'
        base.update(available_wall_seconds='10000',basis=[m.spec(old)],acceptance=m.spec(old))
        with self.assertRaisesRegex(ValueError,'new explicit user'):m.check_balance(base,{'wall_monotonic_ns':4})

    def test_draft_proposal_cannot_admit(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'synthetic_negative_acceptance.json'
            old=json.loads((m.WIRELESS/'report/assets/20261019_mr3_p2a_v8/budget_acceptance_20261019.json').read_text())
            draft=Path('/tmp/mr3_p2a_v13_engineering_continuation_budget_proposal_v1.json')
            old.update(previous_ceiling_wall_seconds=30000,cumulative_engineering_ceiling_wall_seconds=34000,
                       accepted_proposal=str(draft),accepted_proposal_sha256=m.sha(draft))
            path.write_text(json.dumps(old))
            balance={'schema':m.BALANCE_SCHEMA,'freeze':m.FREEZE,'budget_pool':'engineering','for_phase':'deadline_completion',
                     'available_wall_seconds':'10000','accounted_through_wall_monotonic_ns':5,
                     'basis':[m.spec(path)],'acceptance':m.spec(path)}
            with self.assertRaisesRegex(ValueError,'sealed new'):m.check_balance(balance,{'wall_monotonic_ns':4})

    def test_actual_output_failure_not_hidden_by_receipt_pass(self):
        with tempfile.TemporaryDirectory() as td:
            out,receipt=Path(td)/'output.json',Path(td)/'receipt.json'
            out.write_text(json.dumps({'passed':False,'freeze':m.FREEZE}))
            job={'id':'full','role':'full','output':str(out),'argv':['/usr/bin/true']}
            row={'passed':True,'output':str(out),'output_sha256':m.sha(out),'execution_kind':'subprocess_waited',
                 'returncode':0,'errors':[],'argv':job['argv'],'receipt':str(receipt)}
            receipt.write_text(json.dumps(row))
            with self.assertRaisesRegex(ValueError,'scientific consumer'):m.check_jobs({'audits':[job]},{'full':row})
            with self.assertRaisesRegex(ValueError,'missing/extra'):m.check_jobs({'audits':[job]}, {})

    def test_old_matrix_is_not_new_qualification(self):
        with self.assertRaises(ValueError):m.verify_qualification('/tmp/mr3_p2a_v13_matrix_evidence/summary.json')
        with tempfile.TemporaryDirectory() as td:
            fake=json.loads(Path('/tmp/mr3_p2a_v13_matrix_evidence/summary.json').read_text());fake['passed']=True
            path=Path(td)/'synthetic_wrong_schema.json';path.write_text(json.dumps(fake))
            with self.assertRaisesRegex(ValueError,'explicit distinct38'):m.verify_qualification(path)

    def test_external_tail_overrun_is_failure(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'account.json'
            account={'schema':'mr3-p2a-external-root-accounting-v1','freeze':m.FREEZE,'phase':'deadline_completion',
                     'budget_pool':'engineering','engineering_ceiling_wall_seconds':'34000','charged_wall_seconds':'8500.000000001'}
            path.write_text(json.dumps(account))
            with self.assertRaisesRegex(ValueError,'actual external final'):m.check_external_completion_accounting(path,[],{'total_batch_wall_seconds':'8499','wall_monotonic_ns':1})

    def test_real_finite_outer_wait_and_independent_failure_absence(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);evidence=root/'evidence';wait=root/'wait.json';final=root/'final.json'
            command=[sys.executable,'-B',str(PATH),'outer','--plan',str(root/'MISSING.json'),
                     '--balance',str(root/'MISSING_BALANCE.json'),'--evidence',str(evidence),'--output',str(wait)]
            child=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            self.assertEqual(child.returncode,1,child.stderr)
            real=json.loads(wait.read_text());self.assertEqual(real['returncode'],1)
            self.assertEqual(real['errors'],[])
            closed=subprocess.run([sys.executable,'-B',str(PATH),'final-absence','--receipt',str(wait),
                                   '--evidence',str(evidence),'--output',str(final)],capture_output=True,text=True)
            self.assertEqual(closed.returncode,1,closed.stderr)
            proof=json.loads(final.read_text());self.assertTrue(proof['closure_passed'])
            self.assertFalse(proof['execution_passed']);self.assertFalse(proof['passed'])
            self.assertEqual(proof['saved_identity_count'],2)
            self.assertTrue(all(not row['same_identity_present'] for row in proof['identities']))
            self.assertTrue(json.loads((evidence/'summary.json').read_text())['errors'][0].startswith('FileNotFoundError('))

if __name__=='__main__':unittest.main()
