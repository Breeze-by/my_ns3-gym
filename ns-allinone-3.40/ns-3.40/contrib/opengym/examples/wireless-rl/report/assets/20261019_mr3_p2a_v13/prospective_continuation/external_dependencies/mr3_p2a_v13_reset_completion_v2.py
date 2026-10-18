"""Prospective reset-only read-only completion; never starts native or PPO.

The original matrix remains FAIL. This separately SHA-bound /tmp tool may run
only the nine actually unsubmitted reset jobs. Old leaves are immutable inputs.
"""
import argparse
import ast
import copy
from decimal import Decimal
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path('/home/zhuyulab/ns3-workspace')
WIRELESS = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
sys.path.insert(0, str(WIRELESS))
from mr3_learning import native_custody as custody
from mr3_learning import preparation as prep

FREEZE = '0063aa233ba3008ddcc1eb09ea8068112eea3965'
BASE_PLAN = WIRELESS / 'report/assets/20261019_mr3_p2a_v13/predeclared_plan_v13.json'
BASE_SHA = '15d1ec389105e45a445871b069e5b01ec49ffa609e1cb0318bb5246b4cd6ec0d'
MATRIX = Path('/tmp/mr3_p2a_v13_matrix_evidence')
SUMMARY = MATRIX / 'summary.json'
FINAL = Path('/tmp/mr3_p2a_v13_matrix_final_closure.json')
OUTER = Path('/tmp/mr3_p2a_v13_matrix_execution_receipt.json')
ACCOUNTING = Path('/tmp/mr3_p2a_v13_accounting_root_v1.json')
CUSTODY_SHA = '4edcdb6b33105e274c1c908c9d78e8c5d24461ff6733ed0f976e41bad3f2d928'
PREP_SHA = '850ab8947f711033f3f2fd17ef57d32098c02d569c1bea0f5cf58aaff8acd767'
PENDING = ('fifo_007', 'input_008', 'fifo_008', 'input', 'angular',
           'physical_per_episode', 'physics', 'fifo_manifest', 'closure')
PLAN_SCHEMA = 'mr3-v13-reset-readonly-completion-plan-v1'
RUN_SCHEMA = 'mr3-v13-reset-readonly-completion-execution-v1'
WAIT_SCHEMA = 'mr3-v13-reset-readonly-completion-actual-wait-v1'
FINAL_SCHEMA = 'mr3-v13-reset-readonly-completion-final-absence-v1'
DEFERRED_SCHEMA = 'mr3-native-custody-deferred-closure-v1'
CAP = Decimal('600')
ORIGINAL_SHA = {
 str(SUMMARY): 'c9a8bcaa48a77ad91eaa7edca05f53cdaeb76780a1aba472592e8735bd3b19f7',
 str(FINAL): 'b076c947670bf6d9f311ed7cc443d877ad7bc46e7140656fc27ae3aa95e2ca52',
 str(OUTER): '582c5f64e06d33c6715369851e0a57b683d594520c1e634094402cf767941a61',
 str(ACCOUNTING): 'c20eaf358270cb6981ae5973fc9c8caf6a27f1f3c9368d712a4445230e3864ee',
 str(MATRIX/'reset/stage.json'): '46f376891e29e24eb994a3cf26c9e76740335e50db21f4e88608f07994a13b0d',
 str(MATRIX/'reset/native.json'): '2fb3fcb096e9014c9e26ead8392801df0226d4c41f76859f796929b722466c82',
 str(MATRIX/'reset/live_custody.json'): '9f96db6402bd5af44e0cf9582fa3558ad1fae2b66ba651adeca513935bea2005',
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def spec(path):
    path = Path(path).resolve()
    raw = path.read_bytes()
    return {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}


def js(path):
    return custody.parse(Path(path).read_bytes())


def check_spec(value):
    require(spec(value['path']) == value, 'bound input changed: ' + value['path'])


def same_identity(left, right):
    return bool(left and right and all(left.get(k) == right.get(k) for k in ('pid','parent','group','session','start_ticks')))


def current_absence(final, identity=prep.identity):
    require(final.get('saved_identity_count') == 539 and len(final['identities']) == 539,
            'original final absence inventory is not exactly539')
    rows, seen = [], set()
    for row in final['identities']:
        old = row['saved']
        key = old['pid'], old['start_ticks']
        require(type(key[0]) is int and type(key[1]) is int and key not in seen
                and row['same_identity_present'] is False, 'invalid original saved identity')
        seen.add(key)
        now = identity(key[0])
        require(now is None or now['start_ticks'] != key[1],
                'old saved identity remains, including zombie: ' + str(key))
        rows.append({'saved': old, 'current': now, 'gone': True})
    return rows


def classify(base, summary, final, outer, accounting):
    require(base['schema'] == 'mr3-preparation-plan-v1' and len(base['source_bindings']) == 279
            and len(base['library_bindings']) == 10, 'original source/library inventory differs')
    require(summary['schema'] == 'mr3-preparation-execution-v1' and summary['freeze'] == FREEZE
            and summary['plan_sha256'] == BASE_SHA and summary['passed'] is False
            and summary['all_submitted_children_waited'] is True
            and summary['within_matrix_wall_allocation'] is True
            and 'source_end_error' not in summary and summary['signals_sent'] == 0
            and summary['gpu_calls'] == summary['optimizer_steps'] == 0,
            'original closed execution differs')
    stages = summary['stages']
    require([s['stage'] for s in stages] == list(prep.STAGES), 'original stage order differs')
    require(all(s['passed'] is True and s['status'] == 'PASS' and s['error'] is None
                and s['skipped_audits'] == [] for s in stages[:2]), 'earlier stage failed')
    reset = stages[2]
    require(reset['status'] == 'FAIL' and reset['passed'] is False and reset['error'] is None
            and reset['within_stage_wall_allocation'] is False
            and Decimal(reset['wall_seconds']) > Decimal(reset['effective_stage_wall_cap_seconds'])
            and reset['budget_skipped_before_native'] is False
            and [s['id'] for s in reset['skipped_audits']] == list(PENDING)
            and all(s['status'] == 'SKIPPED' and s['reason'] == 'stage_wall_allocation_exhausted'
                    for s in reset['skipped_audits']), 'reset failure is not solely declared wall allocation')
    require(stages[3]['status'] == 'SKIPPED'
            and stages[3]['reason'] == 'prior_failure_or_insufficient_balance', 'deadline was not unsubmitted')
    for stage in stages[:3]:
        for key in ('native', 'watcher'):
            row = stage[key]
            require(row['returncode'] == 0 and row['passed'] is True and row['errors'] == []
                    and row['execution_kind'] == 'subprocess_waited', 'old native/watch failure')
        require(all(r['passed'] is True and (
                    r['returncode'] == 0 and r['errors'] == [] if r['execution_kind'] == 'subprocess_waited' else
                    r['execution_kind'] == 'fifo_manifest' and r['returncode'] is None
                    and all(m['passed'] is True and m['returncode'] == 0 and m['execution_kind'] == 'subprocess_waited' for m in r['members']))
                    for r in stage['audits'].values()), 'old submitted consumer failed')
    expected_done = {j['id'] for j in base['stages'][2]['audits']} - set(PENDING)
    require(set(reset['audits']) == expected_done and len(expected_done) == 20,
            'reset submitted inventory differs')
    require(final['schema'] == 'mr3-p2a-v9-final-coordinator-closure-v1'
            and final['freeze'] == FREEZE and final['closure_passed'] is True
            and final['all_saved_identities_gone'] is True and final['execution_passed'] is False
            and final['passed'] is False, 'original final closure is not retained failed-execution/clean-absence')
    require(outer['schema'] == 'mr3-p2a-v9-outer-actual-wait-v1' and outer['freeze'] == FREEZE
            and outer['plan_sha256'] == BASE_SHA and outer['returncode'] == 1 and outer['errors'] == [],
            'original actual outer wait differs')
    for path in (SUMMARY, OUTER):
        require(final['inputs'][str(path)]['sha256'] == sha(path), 'old final did not bind exact summary/wait')
    require(accounting['schema'] == 'mr3-p2a-external-root-accounting-v1'
            and accounting['freeze'] == FREEZE and accounting['budget_pool'] == 'engineering'
            and accounting['cumulative_used_wall_seconds'] == '23675.6332411916018'
            and accounting['remaining_wall_seconds'] == '6324.3667588083982'
            and Decimal(accounting['cumulative_used_wall_seconds']) + Decimal(accounting['remaining_wall_seconds']) == Decimal('30000')
            and accounting['accounted_through_wall_monotonic_ns'] >= final['wall_monotonic_ns'],
            'external engineering accounting differs')
    return reset


def pushed_runtime_admission():
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT).decode().strip()
    head, remote, dirty = git('rev-parse','HEAD'), git('rev-parse','origin/main'), git('status','--porcelain')
    require(head == FREEZE and not dirty, 'runtime HEAD must be exact clean0063')
    argv = ['git','merge-base','--is-ancestor',FREEZE,'origin/main']
    actual = subprocess.run(argv,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    require(actual.returncode == 0, 'runtime0063 is not a pushed ancestor of origin/main')
    require(git('rev-parse','origin/main') == remote, 'remote ref changed during pushed-ancestor proof')
    return {'runtime_head':head,'remote_current_head':remote,'clean_worktree':True,
            'ancestor_check_actual_argv':argv,'ancestor_check_actual_returncode':actual.returncode,
            'semantics':'Runtime HEAD and every bound source remain exact0063; origin/main may be a reporting descendant. Actual git merge-base --is-ancestor0063 origin/main rc0 proves the runtime freeze was pushed. No ref rewrite or cross-runtime source substitution.'}


def source_check(base):
    require(sha(custody.__file__) == CUSTODY_SHA and sha(prep.__file__) == PREP_SHA,
            'frozen orchestration/identity helper changed')
    proof = pushed_runtime_admission()
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT)
    require(sha(BASE_PLAN) == BASE_SHA, 'original sealed plan changed')
    for rel, expected in base['source_bindings'].items():
        require(sha(ROOT / rel) == expected
                and hashlib.sha256(git('show', FREEZE + ':' + rel)).hexdigest() == expected,
                'frozen source differs: ' + rel)
    for path, expected in base['library_bindings'].items():
        require(sha(path) == expected, 'frozen ELF differs: ' + path)
    proof.update(source_git_freeze=FREEZE,source_bindings_verified=len(base['source_bindings']),elf_bindings_verified=len(base['library_bindings']))
    return proof


def bind_prior():
    for path, expected in ORIGINAL_SHA.items():
        require(sha(path) == expected, 'fixed original evidence SHA differs: ' + path)
    base, summary, final, outer, accounting = map(js, (BASE_PLAN, SUMMARY, FINAL, OUTER, ACCOUNTING))
    reset = classify(base, summary, final, outer, accounting)
    bindings = {str(p): spec(p) for p in (BASE_PLAN, SUMMARY, FINAL, OUTER, ACCOUNTING, MATRIX / 'reset/stage.json')}
    require(js(MATRIX / 'reset/stage.json') == reset, 'old reset stage/summary differs')
    for stage in summary['stages'][:3]:
        for value in [stage['native'], stage['watcher'], *stage['audits'].values()]:
            receipt = Path(value['receipt']) if 'receipt' in value else None
            if receipt is not None: require(js(receipt) == value, 'actual saved command receipt differs')
            require(value['output_sha256'] == sha(value['output']), 'actual saved output differs')
            output = js(value['output'])
            if isinstance(output,dict):
                require(output.get('passed') is True and output.get('freeze', FREEZE) == FREEZE,
                        'old actual result is not a genuinePASS')
            else:
                require(value['execution_kind']=='fifo_manifest' and type(output) is list
                        and len(output)==len(value['members']), 'old aggregate kind/members differ')
                for member in value['members']:
                    require(member['sha256']==sha(member['path']), 'old aggregate member bytes differ')
            for p in (receipt, Path(value['output']), Path(value['console']) if 'console' in value else None):
                if p is not None: bindings[str(p)] = spec(p)
    for stage in summary['stages'][:3]:
        native_output = js(stage['native']['output'])
        workers = native_output['workers_results']
        for worker in workers:
            abort_key = 'work_wall_abort' if stage['stage'] == 'terminal' else 'preparation_abort'
            require(worker['error'] is None and worker[abort_key]['requested'] is False,
                    'unexpected original worker error or cooperative abort')
            for episode in worker['episodes']:
                if stage['stage'] == 'terminal':
                    require(native_output['terminal_probe'] is True
                            and '--terminal-probe' in stage['native']['argv']
                            and episode['terminated'] is True and episode['truncated'] is False
                            and episode['reason'] == 'navigation_failure'
                            and ('diagnostic_failure_arm' in episode or 'diagnostic_failure_terminal' in episode),
                            'terminal outcome is not the predeclared P1C diagnostic probe')
                else:
                    require(episode['terminated'] is False and episode['truncated'] is True,
                            'unexpected non-probe task termination')
                path = Path(episode['output_directory']) / 'summary.json'
                closed = js(path)
                require(closed['failures'] == [] and closed['native_failures'] == []
                        and closed['launch_returncode'] == 0
                        and closed['closed']['navigation_failure'] is False,
                        'unexpected closed native/model/task failure')
                bindings[str(path)] = spec(path)
    for job in base['stages'][2]['audits']:
        if job['id'] in PENDING:
            require(all(not Path(job[key]).exists() for key in ('output','receipt','console') if key in job),
                    'an originally unsubmitted output appeared or would be reused')
    # All metadata/log originals read by the original external final absence are
    # SHA-bound too; this is hashing closed bytes, not re-running a scientific gate.
    for path, expected in final['inputs'].items():
        got = spec(path)
        require(got['sha256'] == expected['sha256'] and got['bytes'] == expected['bytes'],
                'original final input changed')
        bindings[path] = got
    return base, summary, reset, bindings


OLD_BLOCK = '''            require(same and current["state"]!="Z","stage coordinator not currently the same live saved identity")
            result["coordinator"]={"scope":launch["launcher_identity_scope"],"saved":coordinator,
                                   "current":current,"same_identity_present":same,"live":True,
                                   "counted_native_owned":False,
                                   "final_external_coordinator_absence_required":True}
'''
NEW_BLOCK = '''            deferred = require_deferred_absence(args,coordinator,read,proc_root)
            require(not same,"old stage coordinator still present, including zombie")
            result["coordinator"]={"scope":"deferred_after_original_external539_absence","saved":coordinator,
                                   "current":current,"same_identity_present":same,"live":False,
                                   "counted_native_owned":False,"deferred_absence":deferred,
                                   "final_external_coordinator_absence_required":True}
'''


def transformed_review():
    require(sha(custody.__file__) == CUSTODY_SHA, 'immutable original custody source changed')
    original = inspect.getsource(custody.review)
    require(original.count(OLD_BLOCK) == 1, 'original live-parent block differs')
    changed = original.replace(OLD_BLOCK, NEW_BLOCK, 1)
    require(changed.replace(NEW_BLOCK, OLD_BLOCK, 1) == original, 'whole function inverse differs')
    space = dict(vars(custody), require_deferred_absence=require_deferred_absence)
    exec(compile(changed, '<explicit-deferred-original-review>', 'exec'), space)
    provenance = {'original_module_path': str(Path(custody.__file__).resolve()),
        'original_module_sha256': CUSTODY_SHA,
        'original_review_sha256': hashlib.sha256(original.encode()).hexdigest(),
        'effective_review_sha256': hashlib.sha256(changed.encode()).hexdigest(),
        'original_block_sha256': hashlib.sha256(OLD_BLOCK.encode()).hexdigest(),
        'deferred_block_sha256': hashlib.sha256(NEW_BLOCK.encode()).hexdigest(),
        'whole_function_inverse_equals_original': True,
        'scope': 'Only synchronous live old-coordinator condition/result replaced by exact original external539 absence and current recheck of every saved identity. All other original closure predicates and original helpers unchanged. Not the original synchronous role byte identity.'}
    return space['review'], provenance


def require_deferred_absence(args, coordinator, read, proc_root):
    plan = custody.parse(read(args.completion_plan))
    for name in ('original_summary', 'original_final', 'original_outer'):
        binding = plan[name]
        raw = read(binding['path'])
        require(hashlib.sha256(raw).hexdigest() == binding['sha256'], 'deferred prior binding changed')
    final = custody.parse(read(plan['original_final']['path']))
    require(final['schema'] == 'mr3-p2a-v9-final-coordinator-closure-v1' and final['freeze'] == FREEZE
            and final['closure_passed'] is True and final['all_saved_identities_gone'] is True
            and final['execution_passed'] is False and final['passed'] is False,
            'deferred prior closure scope differs')
    summary = custody.parse(read(plan['original_summary']['path']))
    require(same_identity(coordinator, summary['coordinator_identity']), 'deferred coordinator differs from old matrix')
    require(final['inputs'][plan['original_summary']['path']]['sha256'] == plan['original_summary']['sha256'],
            'deferred final does not bind exact old summary')
    require(Path(proc_root) == Path('/proc'), 'deferred review requires actual current /proc')
    rows = current_absence(final)
    require(any((x['saved']['pid'], x['saved']['start_ticks']) == (coordinator['pid'],coordinator['start_ticks'])
                for x in rows), 'old coordinator absent from original539 inventory')
    return {'original_final': plan['original_final'], 'saved_identity_count': len(rows),
            'all_original_saved_identities_gone_now': True, 'identities': rows}


def build_jobs(base, reset, evidence, completion_plan):
    replacements = {j['output']: str(evidence / (j['id'] + '_output.json'))
                    for j in base['stages'][2]['audits'] if j['id'] in PENDING}
    jobs = []
    for old in base['stages'][2]['audits']:
        if old['id'] not in PENDING:
            continue
        job = copy.deepcopy(old)
        job['output'] = replacements[old['output']]
        job['original_depends_on'] = list(job['depends_on'])
        job['depends_on'] = [x for x in job['depends_on'] if x not in reset['audits']]
        job.pop('receipt', None)
        job.pop('console', None)
        if 'argv' in job:
            job['argv'] = [FREEZE if x == '{freeze}' else replacements.get(x, x) for x in job['argv']]
            if job['id'] == 'closure':
                require(job['argv'][:5] == ['/usr/bin/python3','-m','mr3_learning.native_custody','review','--run-directory'],
                        'old closure argv prefix differs')
                job['argv'] = ['/usr/bin/python3','-B',str(Path(__file__).resolve()),'deferred-custody',
                               '--completion-plan',str(completion_plan),*job['argv'][4:]]
        jobs.append(job)
    require([j['id'] for j in jobs] == list(PENDING), 'new reset job inventory differs')
    return jobs


def prepare(args):
    require(not args.output.exists() and not args.evidence.exists(), 'new outputs must be exclusive')
    base, summary, reset, bindings = bind_prior()
    runtime_proof = source_check(base)
    current_absence(js(FINAL))
    _, inverse = transformed_review()
    plan = {'schema':PLAN_SCHEMA,'freeze':FREEZE,'ready':True,
        'scope':'Reset read-only completion only. Original matrix remainsFAIL; deadline8 and PPO are unstarted and inadmissible.',
        'tool':spec(__file__),'tool_version':2,'runtime_source_proof_at_prepare':runtime_proof,
        'base_plan':spec(BASE_PLAN),'original_summary':spec(SUMMARY),
        'original_final':spec(FINAL),'original_outer':spec(OUTER),'accounting':spec(ACCOUNTING),
        'input_bindings':bindings,'source_bindings':base['source_bindings'],'library_bindings':base['library_bindings'],
        'evidence_directory':str(args.evidence),'wall_allocation_seconds':'600',
        'engineering_opening_seconds':'6324.3667588083982','minimum_reserved_seconds':'900',
        'post_batch_engineering_lower_bound_before_actual_tail_seconds':'5724.3667588083982',
        'final_external_absence_required':True,'original_matrix_passed':False,
        'original_passed_roles':26,'old_reset_passed_roles':7,'new_reset_roles':['input','angular','physics','closure'],
        'completed_roles_if_new_batch_passes':30,'total_required_roles':38,'deadline_roles_unstarted':8,
        'ppo_admission':False,'deferred_custody':inverse,'old_completed_reset_jobs':reset['audits'],
        'jobs':build_jobs(base,reset,args.evidence,args.output)}
    prep.dump(args.output,plan)
    print(json.dumps({'plan':str(args.output),'sha256':sha(args.output),'ready':True,'scientific_consumers_executed':0}))
    return 0


def check_plan(path, *, source_proof_out=None):
    plan = js(path)
    require(plan['schema'] == PLAN_SCHEMA and plan['freeze'] == FREEZE and plan['ready'] is True
            and plan['wall_allocation_seconds'] == '600' and plan['ppo_admission'] is False,
            'completion plan identity/scope differs')
    check_spec(plan['tool'])
    require(plan['tool']['path'] == str(Path(__file__).resolve()), 'completion tool path differs')
    for binding in plan['input_bindings'].values():
        check_spec(binding)
    base, summary, reset, bindings = bind_prior()
    actual_proof = source_check(base)
    if source_proof_out is not None: source_proof_out.append(actual_proof)
    current_absence(js(FINAL))
    require(plan['input_bindings'] == bindings
            and all(plan[key] == spec(path) for key,path in (('base_plan',BASE_PLAN),('original_summary',SUMMARY),('original_final',FINAL),('original_outer',OUTER),('accounting',ACCOUNTING)))
            and plan['source_bindings'] == base['source_bindings'] and plan['library_bindings'] == base['library_bindings']
            and plan['old_completed_reset_jobs'] == reset['audits']
            and plan['jobs'] == build_jobs(base,reset,Path(plan['evidence_directory']),Path(path)),
            'completion argv/DAG/old members differ from exact approved derivation')
    return plan


class CompletionRunner(prep.Runner):
    def __init__(self, *args, old_completed, **kwargs):
        super().__init__(*args, **kwargs)
        self.old_completed = old_completed
    def aggregate(self, job, completed):
        require(not set(completed) & set(self.old_completed), 'old completed job would be replayed')
        return super().aggregate(job, {**self.old_completed, **completed})


def deferred(args):
    actual_proofs=[]
    plan = check_plan(args.completion_plan,source_proof_out=actual_proofs)
    args.require_parameters = False
    func, provenance = transformed_review()
    result = func(args)
    result['runtime_source_proof'] = actual_proofs[0]
    result['original_review_schema'] = result['schema']
    result['schema'] = DEFERRED_SCHEMA
    result['implementation_provenance'] = {**provenance,'effective_entry':spec(__file__),
                                          'completion_plan':spec(args.completion_plan)}
    result['scope'] = 'Deferred historical custody after original539 external absence; original synchronous closure was never submitted. No original matrix PASS or physical/task/PPO qualification implied.'
    prep.dump(args.output,result)
    return 0 if result['passed'] else 1


def run(args):
    started = time.monotonic_ns()
    initial_plan = js(args.plan)
    directory = Path(initial_plan['evidence_directory'])
    directory.mkdir(exist_ok=False)
    result = {'schema':RUN_SCHEMA,'freeze':FREEZE,'plan_sha256':sha(args.plan),'passed':False,'errors':[],
        'coordinator_identity':prep.identity(os.getpid()),'started_wall_monotonic_ns':started,
        'original_matrix_passed':False,'original_passed_roles':26,'deadline_roles_unstarted':8,
        'ppo_admission':False,'final_external_absence_required':True,'new_native_calls':0,'gpu_calls':0,'signals_sent':0}
    ledger_lock = threading.Lock()
    with (directory/'ledger.jsonl').open('x') as ledger:
        def record(**value):
            with ledger_lock:
                ledger.write(json.dumps({'wall_monotonic_ns':time.monotonic_ns(),**value})+'\n');ledger.flush()
        try:
            actual_proofs=[]
            plan=check_plan(args.plan,source_proof_out=actual_proofs)
            result['runtime_source_proof_before']=actual_proofs[0]
            runner=CompletionRunner(directory,WIRELESS,FREEZE,sha(args.plan),record,
                                    old_completed=plan['old_completed_reset_jobs'])
            completed, skipped=prep.run_audits(plan['jobs'],runner,started+int(CAP*10**9))
            result.update(new_jobs=completed,skipped_jobs=skipped)
            required=[j for j in plan['jobs'] if j.get('required',True)]
            require(all(completed.get(j['id'],{}).get('execution_kind')=='subprocess_waited'
                        and type(completed[j['id']].get('returncode')) is int
                        and completed[j['id']].get('errors')==[]
                        for j in plan['jobs'] if j.get('kind','command')=='command' and j['id'] in completed),
                    'a submitted scientific command lacked a genuine clean wait receipt')
            require(not skipped and all(completed.get(j['id'],{}).get('passed') is True for j in required),
                    'required reset-only completion job failed/skipped')
            for binding in plan['input_bindings'].values():check_spec(binding)
            result['runtime_source_proof_end']=source_check(js(BASE_PLAN))
            current_absence(js(FINAL));check_spec(plan['tool'])
            result['passed']=True
        except BaseException as error:
            result['errors'].append(repr(error))
        ended=time.monotonic_ns()
        result.update(ended_wall_monotonic_ns=ended,charged_wall_seconds=str(Decimal(ended-started)/10**9),
                      wall_allocation_seconds='600',within_allocation=ended-started<=int(CAP*10**9),
                      all_submitted_children_waited=True)
        actual_new_roles=[j['role'] for j in initial_plan.get('jobs',[]) if j.get('role') and result.get('new_jobs',{}).get(j['id'],{}).get('passed') is True]
        result.update(scientific_role_inventory=[
                          {'stage':stage['stage'],'role':row['role'],'provenance':'original_actual_pass',
                           'output':row['output'],'output_sha256':row['output_sha256'],'receipt':row['receipt']}
                          for stage in js(SUMMARY)['stages'][:3] for row in stage['audits'].values() if row.get('role')] + [
                          {'stage':'reset','role':j['role'],'provenance':'new_deferred_custody' if j['id']=='closure' else 'new_original_mathematical_consumer',
                           'output':result['new_jobs'][j['id']]['output'],'output_sha256':result['new_jobs'][j['id']]['output_sha256']}
                          for j in initial_plan.get('jobs',[]) if j.get('role') in actual_new_roles],
                      new_passed_reset_roles=actual_new_roles,completed_scientific_roles=26+len(actual_new_roles),
                      total_required_roles=38,reset_scientific_complete=result['passed'],all38_scientific_complete=False)
        if not result['within_allocation']:
            result['passed']=False;result['errors'].append('new batch wall allocation exceeded; actual cost remains charged')
        record(event='reset_readonly_completion_closed',passed=result['passed'],errors=result['errors'])
    prep.dump(directory/'summary.json',result)
    return 0 if result['passed'] else 1


def verify_original():
    base, summary, reset, bindings = bind_prior()
    actual_proof = source_check(base)
    gone = current_absence(js(FINAL))
    return {'base_plan':base,'summary':summary,'reset':reset,'input_bindings':bindings,'old_saved_absence':gone,'actual_runtime_source_proof':actual_proof}


def verify_reset(plan_path, summary_path, final_path, outer_path):
    actual_proofs=[]
    plan = check_plan(Path(plan_path),source_proof_out=actual_proofs)
    summary, final, wait = map(js,(summary_path,final_path,outer_path))
    require(summary['schema']==RUN_SCHEMA and summary['freeze']==FREEZE and summary['passed'] is True
            and summary['plan_sha256']==sha(plan_path) and summary['skipped_jobs']==[]
            and summary['within_allocation'] is True and summary['original_matrix_passed'] is False
            and summary['completed_scientific_roles']==30 and summary['new_passed_reset_roles']==['input','angular','physics','closure']
            and summary['all38_scientific_complete'] is False and summary['ppo_admission'] is False,
            'reset-only completion execution differs')
    require(wait['schema']==WAIT_SCHEMA and wait['freeze']==FREEZE and wait['returncode']==0 and wait['errors']==[]
            and wait['tool']==spec(__file__) and wait['plan']==spec(plan_path) and same_identity(wait['coordinator_identity'],summary['coordinator_identity']),
            'reset completion actual wait differs')
    require(final['schema']==FINAL_SCHEMA and final['freeze']==FREEZE and final['passed'] is True and final['closure_passed'] is True
            and final['execution_passed'] is True and final['all_saved_identities_gone'] is True
            and final['plan']==spec(plan_path) and final['tool']==spec(__file__)
            and final['inputs'][str(Path(summary_path).resolve())]['sha256']==sha(summary_path)
            and final['inputs'][str(Path(outer_path).resolve())]['sha256']==sha(outer_path),
            'reset completion independent final absence differs')
    for path,expected in final['inputs'].items():
        actual=spec(path)
        require(actual['sha256']==expected['sha256'] and actual['bytes']==expected['bytes'],
                'completion final input bytes changed')
    require(set(summary['new_jobs'])==set(PENDING),'new completion jobs differ')
    for job in plan['jobs']:
        row=summary['new_jobs'][job['id']]
        require(row['output']==job['output'] and row['output_sha256']==sha(row['output']), 'new completion result path/bytes differ')
        if job.get('required',True):require(row['passed'] is True,'required completion member failed')
        if job.get('kind','command')=='command':
            require(type(row['returncode']) is int and row['execution_kind']=='subprocess_waited'
                    and row['argv']==job['argv'] and row['errors']==[] and js(row['receipt'])==row,
                    'new real wait receipt/argv differs')
            if job.get('required',True):
                output=js(row['output'])
                require(row['returncode']==0 and output.get('passed') is True
                        and output.get('freeze',FREEZE)==FREEZE,
                        'required result is not actual rc0 and outputPASS')
        if job['id']=='closure':
            report=js(row['output'])
            require(report['schema']==DEFERRED_SCHEMA
                    and report['implementation_provenance']['whole_function_inverse_equals_original'] is True
                    and report['implementation_provenance']['original_module_sha256']==CUSTODY_SHA,
                    'deferred closure identity differs')
    for row in final['identities']:
        old=row['saved'];now=prep.identity(old['pid'])
        require(row['same_identity_present'] is False
                and (now is None or now['start_ticks']!=old['start_ticks']),'completion identity is still present')
    return {'plan':plan,'summary':summary,'final':final,'outer':wait,'completed_scientific_roles':30,'ppo_admission':False,'actual_runtime_source_proof':actual_proofs[0]}


def outer(args):
    require(not args.output.exists(),'outer wait receipt already exists')
    started=time.monotonic_ns();own=prep.identity(os.getpid())
    argv=[sys.executable,'-B',str(Path(__file__).resolve()),'run','--plan',str(args.plan)]
    child=subprocess.Popen(argv,cwd=WIRELESS,env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1'))
    saved=prep.identity(child.pid);errors=[]
    while True:
        try:rc=child.wait();break
        except BaseException as error:errors.append(repr(error))
    prep.dump(args.output,{'schema':WAIT_SCHEMA,'freeze':FREEZE,'plan':spec(args.plan),'tool':spec(__file__),
        'outer_identity':own,'coordinator_identity':saved,'actual_argv':argv,'returncode':rc,'errors':errors,
        'started_wall_monotonic_ns':started,'ended_wall_monotonic_ns':time.monotonic_ns()})
    return rc


def collect_identities(value, saved):
    if isinstance(value,dict):
        if type(value.get('pid')) is int and type(value.get('start_ticks')) is int:
            saved[(value['pid'],value['start_ticks'])]=value
        for x in value.values():collect_identities(x,saved)
    elif isinstance(value,list):
        for x in value:collect_identities(x,saved)


def final_absence(args):
    read=custody.Reader()
    wait=custody.parse(read(args.receipt));plan=custody.parse(read(args.plan))
    require(wait['schema']==WAIT_SCHEMA and wait['freeze']==FREEZE and wait['plan']==spec(args.plan)
            and wait['tool']==spec(__file__),'actual outer wait/tool/plan differs')
    directory=Path(plan['evidence_directory']);summary=custody.parse(read(directory/'summary.json'))
    require(summary['schema']==RUN_SCHEMA and summary['plan_sha256']==sha(args.plan)
            and same_identity(summary['coordinator_identity'],wait['coordinator_identity']),'completion coordinator differs')
    saved={};collect_identities(wait,saved);collect_identities(summary,saved)
    old=custody.parse(read(plan['original_final']['path']));collect_identities(old,saved)
    for path in sorted(directory.glob('*.json')):
        collect_identities(custody.parse(read(path)),saved)
    for line in read(directory/'ledger.jsonl').splitlines():collect_identities(custody.parse(line),saved)
    rows=[]
    for (pid,start),value in sorted(saved.items()):
        now=prep.identity(pid);rows.append({'saved':value,'current':now,'same_identity_present':bool(now and now['start_ticks']==start)})
    clean=bool(rows) and all(not r['same_identity_present'] for r in rows)
    read.finish();ended=time.monotonic_ns();elapsed=ended-wait['started_wall_monotonic_ns']
    within=elapsed<=int(CAP*10**9)
    execution=wait['returncode']==0 and wait['errors']==[] and summary['passed'] is True and within
    execution=execution and plan.get('schema')==PLAN_SCHEMA and plan.get('tool')==wait['tool']
    result={'schema':FINAL_SCHEMA,'freeze':FREEZE,'passed':clean and execution,'closure_passed':clean,
        'execution_passed':execution,'all_saved_identities_gone':clean,'saved_identity_count':len(rows),
        'identities':rows,'inputs':read.bindings,'plan':spec(args.plan),'tool':spec(__file__),
        'wall_monotonic_ns':ended,'total_batch_wall_seconds':str(Decimal(elapsed)/10**9),'within_allocation':within,
        'wall_allocation_seconds':'600','original_matrix_passed':False,'all38_scientific_complete':False,
        'deadline_roles_unstarted':8,'ppo_admission':False,
        'scope':'Reset-only completion external absence. Outer entry through this read/recheck; root additionally charges actual tool wait/write tail and rejects any >600 total. Original FAIL remains; no deadline/PPO credit.'}
    prep.dump(args.output,result)
    return 0 if result['passed'] else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare');p.add_argument('--output',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True)
    p=sub.add_parser('run');p.add_argument('--plan',type=Path,required=True)
    p=sub.add_parser('outer');p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('final-absence')
    for name in ('plan','receipt','output'):p.add_argument('--'+name,type=Path,required=True)
    p=sub.add_parser('deferred-custody')
    for name in ('completion-plan','run-directory','binding','capture','launch-receipt','fifo-receipts','output'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--expected-episodes',type=int,required=True);p.add_argument('--freeze',required=True)
    args=parser.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path):setattr(args,key,value.resolve())
    return {'prepare':prepare,'run':run,'outer':outer,'final-absence':final_absence,'deferred-custody':deferred}[args.mode](args)


if __name__=='__main__':raise SystemExit(main())
