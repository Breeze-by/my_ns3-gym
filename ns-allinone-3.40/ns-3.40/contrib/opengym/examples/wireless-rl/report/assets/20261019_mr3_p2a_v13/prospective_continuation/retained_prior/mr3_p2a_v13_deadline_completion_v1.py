"""Prospective V13 deadline completion and distinct38-role qualification.

/tmp evidence tool, not frozen runtime. Original V13 matrix remains FAIL. Uses
only the frozen Runner/readers; never changes a task/physics predicate or cap.
Execution needs a new explicit engineering authorization and actual balance.
"""
import argparse
import copy
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import threading

ROOT=Path('/home/zhuyulab/ns3-workspace')
WIRELESS=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
sys.path.insert(0,str(WIRELESS))
from mr3_learning import native_custody as custody
from mr3_learning import preparation as prep
FREEZE='0063aa233ba3008ddcc1eb09ea8068112eea3965'
RESET=Path('/tmp/mr3_p2a_v13_reset_completion_v2.py')
RESET_SHA='3dd3e75b1d3be168099579d3b3aa9dcba8e8421c2b8f95a149dc6a7f3a85b275'
PLAN_SCHEMA='mr3-p2a-v13-deadline-completion-plan-v1'
RUN_SCHEMA='mr3-p2a-v13-deadline-completion-execution-v1'
WAIT_SCHEMA='mr3-p2a-v13-deadline-completion-actual-outer-wait-v1'
FINAL_SCHEMA='mr3-p2a-v13-deadline-completion-final-absence-v1'
QUAL_SCHEMA='mr3-p2a-v13-completed-38-role-qualification-v1'
BALANCE_SCHEMA='mr3-p2a-external-accounted-balance-v1'
AUTH_SCHEMA='mr3-p2a-engineering-budget-acceptance-v1'
CAP=Decimal('8500')
WORK='6200'
CLOSE='120'
PPO_RESERVE=Decimal('900')
ROLES=('full','drive','information','peer','control','settled','cadence','closure')


def require(value,message):
    if not value: raise ValueError(message)


def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def spec(path):
    path=Path(path).resolve(); raw=path.read_bytes()
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}


def js(path): return custody.parse(Path(path).read_bytes())


def check_spec(value):
    require(spec(value['path'])==value,'bound input changed: '+value['path'])


def reset_tool():
    require(sha(RESET)==RESET_SHA,'separately bound reset tool changed')
    module_spec=importlib.util.spec_from_file_location('mr3_v13_reset_completion_bound',RESET)
    module=importlib.util.module_from_spec(module_spec); module_spec.loader.exec_module(module)
    return module


def replace_paths(value,old,new):
    if isinstance(value,str): return value.replace(str(old),str(new)).replace('{freeze}',FREEZE)
    if isinstance(value,list): return [replace_paths(v,old,new) for v in value]
    if isinstance(value,dict): return {k:replace_paths(v,old,new) for k,v in value.items()}
    return value


def deadline_stage(base,evidence):
    original=base['stages'][3]
    require(original['stage']=='deadline' and original['expected_episodes']==1
            and tuple(j['role'] for j in original['audits'] if j.get('role'))==ROLES,
            'original deadline scientific-role inventory differs')
    old=Path(original['watcher']['output']).parent
    stage=replace_paths(copy.deepcopy(original),old,evidence)
    argv=stage['native']['argv']
    require(argv.count('--work-wall-seconds')==1
            and prep.argument(argv,'--work-wall-seconds')=='4500'
            and prep.argument(argv,'--close-reserve-seconds')==CLOSE
            and prep.argument(argv,'--workers')=='1'
            and prep.argument(argv,'--schedule')=='open:101'
            and prep.argument(argv,'--steps')=='300' and argv.count('--deadline-probe')==1,
            'original deadline workload/native contract differs')
    argv[argv.index('--work-wall-seconds')+1]=WORK
    stage['native']['id']='native'
    stage['watcher']['id']='watcher'
    stage['wall_seconds']=str(CAP)
    stage['original_stage_wall_seconds']=original['wall_seconds']
    stage['native_argv_delta']={'flag':'--work-wall-seconds','old':'4500','new':WORK}
    # Original workload, run-id, domains, ports, all audit argv/math and DAG remain.
    return stage


def reset_proof(paths):
    tool=reset_tool()
    return tool.verify_reset(*(Path(paths[k]) for k in ('plan','summary','final','outer')))


def prepare(args):
    require(not args.output.exists() and not args.evidence.exists(),'new plan/evidence paths required')
    tool=reset_tool()
    original=tool.verify_original()
    base=original['base_plan']
    tool.source_check(base)
    paths={k:str(getattr(args,'reset_'+k)) for k in ('plan','summary','final','outer')}
    # Paths may be prospective at declaration time. They become required actual
    # successful inputs at run admission; no passed/reset result is synthesized.
    stage=deadline_stage(base,args.evidence)
    require(not Path(stage['run_directory']).exists(),'original unsubmitted deadline output already exists')
    value={'schema':PLAN_SCHEMA,'freeze':FREEZE,'tool':spec(__file__),'reset_tool':spec(RESET),
           'base_plan':spec(tool.BASE_PLAN),'plan_sha256':tool.BASE_SHA,
           'original_matrix_passed':False,'old_passed_scientific_roles':26,
           'required_new_reset_roles':4,'required_new_deadline_roles':8,
           'qualification_schema':QUAL_SCHEMA,'reset_completion_paths':paths,
           'source_bindings':base['source_bindings'],'library_bindings':base['library_bindings'],
           'input_bindings':original['input_bindings'],'evidence_directory':str(args.evidence),
           'stage':stage,'total_batch_wall_allocation_seconds':str(CAP),
           'native_work_wall_seconds':WORK,'native_close_reserve_seconds':CLOSE,
           'engineering_minimum_ppo_reserve_seconds':str(PPO_RESERVE),
           'reserve_is_proven_upper_bound':False,'native_admitted':False,
           'execution_requires_new_explicit_authorization_and_actual_balance':True,
           'overrun_verdict':'FAIL; all actual costs retained; no signal/retry/refund or pool transfer',
           'source_admission':{'required_HEAD':FREEZE,'required_worktree':'clean','published_rule':'git merge-base --is-ancestor FREEZE origin/main must return0; remote may contain later evidence commits','remote_head_at_declaration':subprocess.check_output(['git','rev-parse','origin/main'],cwd=ROOT,text=True).strip()},
           'scope':'Future separate completion only. Old matrix FAIL and original cap remain unchanged.'}
    prep.dump(args.output,value)
    return 0


def check_plan(path):
    plan=js(path); tool=reset_tool()
    require(plan['schema']==PLAN_SCHEMA and plan['freeze']==FREEZE
            and plan['tool']==spec(__file__) and plan['reset_tool']==spec(RESET)
            and plan['base_plan']==spec(tool.BASE_PLAN) and plan['plan_sha256']==tool.BASE_SHA
            and plan['original_matrix_passed'] is False
            and plan['old_passed_scientific_roles']==26
            and plan['required_new_reset_roles']==4 and plan['required_new_deadline_roles']==8
            and plan['qualification_schema']==QUAL_SCHEMA and plan['native_admitted'] is False
            and plan['execution_requires_new_explicit_authorization_and_actual_balance'] is True
            and plan['total_batch_wall_allocation_seconds']==str(CAP)
            and plan['native_work_wall_seconds']==WORK
            and plan['native_close_reserve_seconds']==CLOSE
            and plan['engineering_minimum_ppo_reserve_seconds']==str(PPO_RESERVE)
            and plan['reserve_is_proven_upper_bound'] is False
            and plan['source_admission']['required_HEAD']==FREEZE
            and plan['source_admission']['required_worktree']=='clean'
            and plan['source_admission']['published_rule']=='git merge-base --is-ancestor FREEZE origin/main must return0; remote may contain later evidence commits',
            'completion declaration differs')
    original=tool.verify_original(); base=original['base_plan']; tool.source_check(base)
    require(plan['source_bindings']==base['source_bindings']
            and plan['library_bindings']==base['library_bindings']
            and plan['input_bindings']==original['input_bindings']
            and plan['stage']==deadline_stage(base,Path(plan['evidence_directory'])),
            'completion declaration changed original sources/math/argv/DAG')
    for value in plan['input_bindings'].values(): check_spec(value)
    return plan,original


def check_balance(balance,reset_final):
    require(balance['schema']==BALANCE_SCHEMA and balance['freeze']==FREEZE
            and balance['budget_pool']=='engineering' and balance['for_phase']=='deadline_completion'
            and type(balance['accounted_through_wall_monotonic_ns']) is int
            and balance['accounted_through_wall_monotonic_ns']>=reset_final['wall_monotonic_ns'],
            'completion balance is not actual engineering accounting after reset final')
    available=Decimal(balance['available_wall_seconds'])
    require(available>=CAP+PPO_RESERVE and balance['basis'],
            'engineering balance must cover8500 completion plus900 minimum PPO reserve')
    for value in balance['basis']: check_spec(value)
    acceptance=balance['acceptance']; check_spec(acceptance)
    auth=js(acceptance['path'])
    require(auth['schema']==AUTH_SCHEMA and auth['status']=='USER_APPROVED'
            and Decimal(auth['previous_ceiling_wall_seconds'])==Decimal('30000')
            and Decimal(auth['cumulative_engineering_ceiling_wall_seconds'])==Decimal('34000')
            and auth['user_message']
            and auth['pilot_remaining_decisions']==1870
            and Decimal(auth['pilot_remaining_wall_seconds_decimal'])==Decimal('2905.9547395464029')
            and auth['pilot_expanded'] is False and auth['validation_expanded'] is False,
            'new explicit user acceptance did not retain original pools')
    proposal=(Path(acceptance['path']).parent/auth['accepted_proposal']).resolve()
    require(sha(proposal)==auth['accepted_proposal_sha256'],'accepted sealed proposal bytes differ')
    declared=js(proposal)
    require(declared['schema']=='mr3-p2a-v13-engineering-continuation-budget-proposal-v2'
            and declared['status']=='SEALED_PROPOSAL_AWAITING_USER_APPROVAL'
            and declared['runtime_freeze']==FREEZE
            and Decimal(declared['proposed_cumulative_engineering_ceiling'])==Decimal(auth['cumulative_engineering_ceiling_wall_seconds'])
            and Decimal(declared['proposed_cumulative_engineering_ceiling'])==Decimal('34000')
            and Decimal(declared['current_user_engineering_ceiling'])==Decimal('30000')
            and Decimal(declared['requested_ceiling_increase'])==Decimal('4000'),
            'accepted proposal is not the sealed new same-runtime ceiling')
    accounting=balance['accounting']; check_spec(accounting); actual=js(accounting['path'])
    require(actual['schema']=='mr3-p2a-external-root-accounting-v1'
            and actual['freeze']==FREEZE and actual['budget_pool']=='engineering'
            and actual['phase']=='post_user_authorization_balance'
            and Decimal(actual['remaining_wall_seconds'])==available
            and Decimal(actual['cumulative_used_wall_seconds'])+available==Decimal(auth['cumulative_engineering_ceiling_wall_seconds'])
            and actual['accounted_through_wall_monotonic_ns']==balance['accounted_through_wall_monotonic_ns']
            and any(v==accounting for v in balance['basis']),
            'actual latest account/available balance/accepted ceiling do not match')
    approved_account=declared['current_accounting']; check_spec(approved_account)
    approved_actual=js(approved_account['path'])
    require(Decimal(auth['charged_on_entry_decimal'])==Decimal(approved_actual['cumulative_used_wall_seconds'])
            and Decimal(auth['remaining_on_entry_decimal'])+Decimal(auth['charged_on_entry_decimal'])==Decimal(auth['cumulative_engineering_ceiling_wall_seconds'])
            and Decimal(actual['cumulative_used_wall_seconds'])>=Decimal(auth['charged_on_entry_decimal'])
            and approved_actual['accounted_through_wall_monotonic_ns']>=reset_final['wall_monotonic_ns'],
            'acceptance entry account and later actual charging do not match')
    return balance


def check_deadline_native(summary,episode_rows):
    require(summary['passed'] is True and summary['freeze']==FREEZE
            and summary['workers']==1 and summary['robots_per_worker']==3
            and summary['schedule']==[['open',101]] and summary['steps_per_episode']==300
            and summary['deadline_probe'] is True and summary['terminal_probe'] is False
            and summary['valid_transitions']==300 and len(summary['workers_results'])==1,
            'deadline actual300KEEP/native workload differs')
    worker=summary['workers_results'][0]
    require(worker['error'] is None and worker['work_wall_abort']['requested'] is False
            and len(worker['episodes'])==1,'deadline worker abort/error/attempt differs')
    ep=worker['episodes'][0]
    require(ep['transitions']==300 and ep['dt_values']==[1.0]*300
            and ep['terminated'] is True and ep['truncated'] is False and ep['reason']=='timeout',
            'deadline must retain real300s task timeout and all300 one-second transitions')
    require(len(episode_rows)==301 and episode_rows[0]['kind']=='reset'
            and all(row['kind']=='step' and row['info']['dt']==1.0
                    and row['info']['command']['action']==888
                    and row['info']['command']['command_id']==i
                    and row['terminated'] is (i==300) and row['truncated'] is False
                    for i,row in enumerate(episode_rows[1:],1)),
            'actual transitions are not the complete ordered300KEEP sequence')
    return ep


def check_jobs(stage,audits):
    require(set(audits)=={j['id'] for j in stage['audits']},'required deadline DAG has missing/extra jobs')
    bindings={}
    for job in stage['audits']:
        value=audits[job['id']]
        require(value['passed'] is True and value['output']==job['output']
                and value['output_sha256']==sha(job['output']),'deadline actual job/output differs')
        if job.get('kind')=='fifo_manifest':
            require(value['execution_kind']=='fifo_manifest' and value['returncode'] is None
                    and len(value['members'])==1,'deadline FIFO aggregate differs')
            for member in value['members']:
                require(member['passed'] is True and member['returncode']==0
                        and member['sha256']==sha(member['path']),'deadline FIFO leaf differs')
        else:
            require(value['execution_kind']=='subprocess_waited' and value['returncode']==0
                    and value['errors']==[] and value['argv']==job['argv']
                    and js(value['receipt'])==value,'deadline real wait/argv differs')
            output=js(job['output'])
            require(output.get('passed') is True and output.get('freeze',FREEZE)==FREEZE,
                    'deadline scientific consumer did not pass')
        for key in ('output','receipt','console'):
            if value.get(key): bindings[value[key]]=spec(value[key])
    return bindings


def run(args):
    started=time.monotonic_ns(); args.evidence.mkdir(parents=True,exist_ok=False)
    result={'schema':RUN_SCHEMA,'freeze':FREEZE,'passed':False,'errors':[],
            'tool':spec(__file__),'coordinator_identity':prep.identity(os.getpid()),
            'started_wall_monotonic_ns':started,'total_batch_wall_allocation_seconds':str(CAP),
            'original_matrix_passed':False,'budget_pool':'engineering','signals_sent':0,'gpu_calls':0,'optimizer_steps':0,
            'all_38_scientific_roles_passed':False,'final_external_coordinator_absence_required':True}
    ledger_lock=threading.Lock()
    with (args.evidence/'ledger.jsonl').open('x') as ledger:
        def record(**value):
            with ledger_lock:
                ledger.write(json.dumps({'wall_monotonic_ns':time.monotonic_ns(),**value})+'\n');ledger.flush()
        try:
            plan,original=check_plan(args.plan)
            require(str(args.evidence)==plan['evidence_directory'],'evidence differs from exclusive declaration')
            reset=reset_proof(plan['reset_completion_paths'])
            balance=check_balance(js(args.balance),reset['final'])
            result.update(plan=spec(args.plan),reset_completion_paths=plan['reset_completion_paths'],
                          reset_completion_final=spec(plan['reset_completion_paths']['final']),
                          opening_external_balance=spec(args.balance),stage=plan['stage'])
            stage=plan['stage']; run_directory=Path(stage['run_directory'])
            require(not run_directory.exists(),'no replay of previously attempted deadline')
            result['run_directory']=str(run_directory)
            require('MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE' not in os.environ,'no diagnostic physics env')
            runner=prep.Runner(args.evidence,WIRELESS,FREEZE,sha(args.plan),record)
            watch=runner.spawn(stage['watcher']);native=None
            try:
                ready=Path(stage['watcher']['ready']); limit=time.monotonic()+30
                while True:
                    require(watch['process'] is not None and watch['process'].poll() is None,'watcher exited before ready')
                    require(time.monotonic()<limit,'watcher ready timeout')
                    if ready.exists() and ready.read_bytes().endswith(b'\n'):
                        value=custody.read_ready_receipt(custody.Reader(),ready,FREEZE,sha(prep.argument(stage['watcher']['argv'],'--binding')))
                        require(all(value['watcher_identity'][k]==watch['value']['process_identity'][k] for k in ('pid','start_ticks')),'ready watcher identity differs')
                        break
                    time.sleep(.05)
                reset_tool().source_check(original['base_plan'])
                require(started+int(CAP*10**9)-time.monotonic_ns()>int((Decimal(WORK)+Decimal(CLOSE))*10**9),
                        'source/ready cost exhausted native plus close reserve before admission')
                native=runner.command(stage['native'])
            finally:
                stop=Path(prep.argument(stage['watcher']['argv'],'--stop-file'))
                boundary=({'schema':'mr3-native-custody-stop-v1','freeze':FREEZE,'launch_receipt':{'path':native['receipt'],'sha256':sha(native['receipt'])}}
                          if native is not None and native['execution_kind']=='subprocess_waited' else
                          {'schema':'mr3-native-custody-stop-v1','freeze':FREEZE,'native_not_started':True,'reason':'pre_native_admission_failure'})
                prep.dump(stop,boundary);result['watcher']=runner.finish(watch);result['native']=native
            require(native is not None and native['passed'] and result['watcher']['passed'],'deadline native/watch failed')
            summary=js(stage['native']['output']); ep=summary['workers_results'][0]['episodes'][0]
            rows=[custody.parse(line) for line in (Path(ep['output_directory'])/'transitions.jsonl').read_bytes().splitlines()]
            check_deadline_native(summary,rows)
            completed,skipped=prep.run_audits(stage['audits'],runner,started+int(CAP*10**9))
            result.update(audits=completed,skipped_audits=skipped,native_summary=summary)
            require(not skipped,'deadline required consumers skipped')
            result['actual_output_bindings']=check_jobs(stage,completed)
            reset_tool().source_check(original['base_plan']);reset_proof(plan['reset_completion_paths'])
            result['passed']=True
        except BaseException as error: result['errors'].append(repr(error))
        ledger.flush()
        events=[custody.parse(line) for line in (args.evidence/'ledger.jsonl').read_bytes().splitlines()]
        spawned={(r['process_identity']['pid'],r['process_identity']['start_ticks']) for r in events if r.get('event')=='child_spawned'}
        waited={(r['process_identity']['pid'],r['process_identity']['start_ticks']) for r in events if r.get('event')=='child_waited' and type(r.get('returncode')) is int}
        all_waited=spawned<=waited
        if not all_waited:
            result['passed']=False;result['errors'].append('actual spawned child lacks real wait receipt')
        ended=time.monotonic_ns()
        result.update(ended_wall_monotonic_ns=ended,charged_wall_seconds=str(Decimal(ended-started)/10**9),
                      within_total_batch_wall_allocation=ended-started<=int(CAP*10**9),
                      all_submitted_children_waited=all_waited)
        if not result['within_total_batch_wall_allocation']:
            result['passed']=False;result['errors'].append('completion wall allocation exceeded; actual cost remains charged')
        record(event='deadline_completion_closed',passed=result['passed'],errors=result['errors'])
    prep.dump(args.evidence/'summary.json',result)
    return 0 if result['passed'] else 1


def outer(args):
    require(not args.output.exists(),'outer receipt exists');started=time.monotonic_ns()
    argv=[sys.executable,'-B',str(Path(__file__).resolve()),'run','--plan',str(args.plan),
          '--evidence',str(args.evidence),'--balance',str(args.balance)]
    own=prep.identity(os.getpid());child=subprocess.Popen(argv,cwd=WIRELESS,env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1'))
    saved=prep.identity(child.pid);errors=[]
    while True:
        try: code=child.wait();break
        except BaseException as error: errors.append(repr(error))
    prep.dump(args.output,{'schema':WAIT_SCHEMA,'freeze':FREEZE,'tool':spec(__file__),
              'actual_outer_identity':own,'actual_coordinator_identity':saved,'actual_argv':argv,
              'returncode':code,'errors':errors,'started_wall_monotonic_ns':started,
              'ended_wall_monotonic_ns':time.monotonic_ns()})
    return code


def collect(value,saved):
    if isinstance(value,dict):
        if type(value.get('pid')) is int and type(value.get('start_ticks')) is int:
            saved[(value['pid'],value['start_ticks'])]=value
        for child in value.values(): collect(child,saved)
    elif isinstance(value,list):
        for child in value: collect(child,saved)


def final_absence(args):
    read=custody.Reader();read_js=lambda p:custody.parse(read(p))
    wait,summary=read_js(args.receipt),read_js(args.evidence/'summary.json')
    require(wait['schema']==WAIT_SCHEMA and summary['schema']==RUN_SCHEMA
            and wait['freeze']==summary['freeze']==FREEZE
            and wait['tool']==summary['tool']==spec(__file__)
            and all(wait['actual_coordinator_identity'][k]==summary['coordinator_identity'][k] for k in ('pid','start_ticks')),
            'deadline actual outer wait/source/coordinator differs')
    saved={};collect(wait,saved);collect(summary,saved)
    for path in sorted(args.evidence.rglob('*.json')): collect(read_js(path),saved)
    if summary.get('run_directory'):
        for name in ('supervisor_metadata.json','supervisor_shutdown.json'):
            for path in sorted(Path(summary['run_directory']).rglob(name)): collect(read_js(path),saved)
    for line in read(args.evidence/'ledger.jsonl').splitlines(): collect(custody.parse(line),saved)
    rows=[]
    for (pid,start),value in sorted(saved.items()):
        current=prep.identity(pid);rows.append({'saved':value,'current':current,'same_identity_present':bool(current and current['start_ticks']==start)})
    clean=bool(rows) and all(not r['same_identity_present'] for r in rows)
    read.finish();ended=time.monotonic_ns();elapsed=ended-wait['started_wall_monotonic_ns']
    within=elapsed<=int(CAP*10**9)
    execution=wait['returncode']==0 and wait['errors']==[] and summary['passed'] is True and within
    prep.dump(args.output,{'schema':FINAL_SCHEMA,'freeze':FREEZE,'tool':spec(__file__),
              'passed':clean and execution,'closure_passed':clean,'execution_passed':execution,
              'all_saved_identities_gone':clean,'saved_identity_count':len(rows),'identities':rows,
              'inputs':read.bindings,'wall_monotonic_ns':ended,'total_batch_wall_seconds':str(Decimal(elapsed)/10**9),
              'within_total_batch_wall_allocation':within,'total_batch_wall_allocation_seconds':str(CAP),
              'original_matrix_passed':False,'scope':'Actual outer entry through independent final read; root additionally charges actual final write/tool wait tail.8500 is not a proven upper bound.'})
    return 0 if clean and execution else 1


def verify_completion(plan_path,summary_path,final_path,outer_path):
    plan,original=check_plan(plan_path);summary=js(summary_path);final=js(final_path);wait=js(outer_path)
    require(summary['schema']==RUN_SCHEMA and summary['freeze']==FREEZE and summary['passed'] is True
            and summary['errors']==[] and summary['plan']==spec(plan_path)
            and summary['tool']==spec(__file__) and summary['stage']==plan['stage']
            and summary['original_matrix_passed'] is False and summary['signals_sent']==0
            and summary['gpu_calls']==summary['optimizer_steps']==0
            and summary['all_submitted_children_waited'] is True
            and summary['within_total_batch_wall_allocation'] is True
            and summary['skipped_audits']==[],'deadline completion execution did not pass exactly')
    require(wait['schema']==WAIT_SCHEMA and wait['freeze']==FREEZE and wait['tool']==spec(__file__)
            and wait['returncode']==0 and wait['errors']==[]
            and all(wait['actual_coordinator_identity'][k]==summary['coordinator_identity'][k] for k in ('pid','start_ticks')),
            'deadline genuine outer wait differs')
    require(final['schema']==FINAL_SCHEMA and final['freeze']==FREEZE and final['tool']==spec(__file__)
            and final['passed'] is True and final['closure_passed'] is True and final['execution_passed'] is True
            and final['all_saved_identities_gone'] is True and final['within_total_batch_wall_allocation'] is True
            and final['total_batch_wall_allocation_seconds']==str(CAP),'deadline independent final absence did not pass')
    for path in (summary_path,outer_path):
        require(final['inputs'][str(Path(path).resolve())]['sha256']==sha(path),'deadline final did not bind actual summary/wait')
    for row in final['identities']:
        saved=row['saved'];current=prep.identity(saved['pid'])
        require(row['same_identity_present'] is False and (current is None or current['start_ticks']!=saved['start_ticks']),
                'deadline saved identity still present, including zombie')
    require(len(final['identities'])==final['saved_identity_count']>0,'deadline final inventory differs')
    for path,value in final['inputs'].items():
        require(sha(path)==value['sha256'] and Path(path).stat().st_size==value['bytes'],'deadline final input changed')
    bindings=check_jobs(plan['stage'],summary['audits'])
    for key in ('native','watcher'):
        value=summary[key]
        require(value['execution_kind']=='subprocess_waited' and value['returncode']==0 and value['passed'] is True
                and value['errors']==[] and js(value['receipt'])==value
                and value['output_sha256']==sha(value['output']),'deadline native/watch real receipt differs')
    native=js(plan['stage']['native']['output']);ep=native['workers_results'][0]['episodes'][0]
    transitions=Path(ep['output_directory'])/'transitions.jsonl'
    check_deadline_native(native,[custody.parse(line) for line in transitions.read_bytes().splitlines()])
    reset=reset_proof(plan['reset_completion_paths'])
    check_spec(summary['opening_external_balance'])
    check_balance(js(summary['opening_external_balance']['path']),reset['final'])
    require(summary['actual_output_bindings']==bindings,'deadline final output inventory changed')
    for key in ('native','watcher'):
        require(summary[key]['argv']==plan['stage'][key]['argv'],'native/watch actual argv differs from declaration')
    reset_tool().source_check(original['base_plan'])
    return {'plan':plan,'summary':summary,'final':final,'outer':wait,'reset':reset,
            'original':original,'output_bindings':bindings,'transitions':spec(transitions)}


def role_inventory(checked):
    original=checked['original']
    role_rows=[]
    for stage in original['summary']['stages'][:3]:
        roles={j['id']:j.get('role') for j in original['base_plan']['stages'][prep.STAGES.index(stage['stage'])]['audits']}
        role_rows.extend({'stage':stage['stage'],'role':roles[name],'origin':'original_failed_matrix',
                          'receipt':spec(value['receipt']) if value.get('receipt') else None,'output':spec(value['output'])}
                         for name,value in stage['audits'].items() if roles.get(name))
    reset=checked['reset']
    role_rows.extend({'stage':'reset','role':name,'origin':'separate_reset_completion',
                      'receipt':spec(reset['summary']['new_jobs'][name]['receipt']) if reset['summary']['new_jobs'][name].get('receipt') else None,
                      'output':spec(reset['summary']['new_jobs'][name]['output'])}
                     for name in ('input','angular','physics','closure'))
    role_rows.extend({'stage':'deadline','role':name,'origin':'separate_deadline_completion',
                      'receipt':spec(checked['summary']['audits'][name]['receipt']),
                      'output':spec(checked['summary']['audits'][name]['output'])} for name in ROLES)
    require(len(role_rows)==38 and len({(r['stage'],r['role']) for r in role_rows})==38,
            'distinct original26 plus reset4 plus deadline8 inventory differs')
    return role_rows


def check_external_completion_accounting(path,paths,final):
    account=js(path)
    require(account['schema']=='mr3-p2a-external-root-accounting-v1'
            and account['freeze']==FREEZE and account['phase']=='deadline_completion'
            and account['budget_pool']=='engineering'
            and Decimal(account['engineering_ceiling_wall_seconds'])==Decimal('34000')
            and Decimal(account['charged_wall_seconds'])<=CAP
            and Decimal(account['charged_wall_seconds'])>=Decimal(final['total_batch_wall_seconds'])
            and Decimal(account['prior_used_wall_seconds'])+Decimal(account['charged_wall_seconds'])==Decimal(account['cumulative_used_wall_seconds'])
            and Decimal(account['cumulative_used_wall_seconds'])+Decimal(account['remaining_wall_seconds'])==Decimal('34000')
            and account['cumulative_within_ceiling'] is True
            and account['accounted_through_wall_monotonic_ns']>=final['wall_monotonic_ns'],
            'actual external final write/wait tail or cumulative charge exceeded allocation')
    for bound in account['basis']: check_spec(bound)
    require(all(spec(path) in account['basis'] for path in paths),'external tail accounting omitted actual completion boundary')
    return account


def qualify(args):
    checked=verify_completion(args.plan,args.summary,args.final,args.outer)
    check_external_completion_accounting(args.accounting,(args.plan,args.summary,args.final,args.outer),checked['final'])
    plan=checked['plan'];original=checked['original'];tool=reset_tool()
    role_rows=role_inventory(checked)
    paths=[args.plan,args.summary,args.final,args.outer,args.accounting,RESET,Path(__file__),
           *(Path(v) for v in plan['reset_completion_paths'].values())]
    bindings={str(Path(p).resolve()):spec(p) for p in paths}
    for row in role_rows:
        for key in ('receipt','output'):
            if row[key]: bindings[row[key]['path']]=row[key]
    for group in (original['input_bindings'],checked['output_bindings']): bindings.update(group)
    value={'schema':QUAL_SCHEMA,'freeze':FREEZE,'passed':True,'plan_sha256':tool.BASE_SHA,
           'original_matrix_passed':False,'original_matrix_verdict':'FAIL retained; engineering stage wall only',
           'old_saved_identity_count':539,'original_passed_scientific_roles':26,'new_reset_scientific_roles':4,
           'new_deadline_scientific_roles':8,'completed_scientific_roles':38,'roles':role_rows,
           'reset_completion_paths':plan['reset_completion_paths'],
           'deadline_completion_paths':{k:str(getattr(args,k)) for k in ('plan','summary','final','outer')},
           'deadline_final':spec(args.final),'external_tail_accounting':spec(args.accounting),
           'source_admission':{**plan['source_admission'],'remote_head_at_qualification':subprocess.check_output(['git','rev-parse','origin/main'],cwd=ROOT,text=True).strip()},
           'tool':spec(__file__),'reset_tool':spec(RESET),
           'source_bindings':plan['source_bindings'],'library_bindings':plan['library_bindings'],
           'input_bindings':bindings,'wall_monotonic_ns':time.monotonic_ns(),
           'ppo_admission_qualified':True,'scope':'Distinct same-runtime scientific completion26+4+8; never relabels original matrix PASS. Subsequent PPO still needs its original quotas, fresh actual external pool accounting and true wait/closure.'}
    prep.dump(args.output,value)
    return 0


def verify_qualification(path,read=None):
    value=js(path)
    require(value['schema']==QUAL_SCHEMA and value['freeze']==FREEZE and value['passed'] is True
            and value['original_matrix_passed'] is False and value['old_saved_identity_count']==539
            and value['original_passed_scientific_roles']==26 and value['new_reset_scientific_roles']==4
            and value['new_deadline_scientific_roles']==8 and value['completed_scientific_roles']==38
            and value['ppo_admission_qualified'] is True and value['tool']==spec(__file__)
            and value['reset_tool']==spec(RESET),'not the explicit distinct38-role qualification')
    paths=value['deadline_completion_paths']
    checked=verify_completion(*(Path(paths[k]) for k in ('plan','summary','final','outer')))
    require(value['deadline_final']==spec(paths['final'])
            and value['reset_completion_paths']==checked['plan']['reset_completion_paths']
            and value['source_bindings']==checked['plan']['source_bindings']
            and value['library_bindings']==checked['plan']['library_bindings']
            and value['plan_sha256']==checked['plan']['plan_sha256']
            and value['roles']==role_inventory(checked),
            'qualification no longer binds actual completion/38 unique roles')
    check_spec(value['external_tail_accounting'])
    check_external_completion_accounting(value['external_tail_accounting']['path'],[paths[k] for k in ('plan','summary','final','outer')],checked['final'])
    expected={(s['stage'],j['role']) for s in checked['original']['base_plan']['stages'] for j in s['audits'] if j.get('role')}
    require({(r['stage'],r['role']) for r in value['roles']}==expected,'qualification scientific role set differs')
    for bound in value['input_bindings'].values():
        check_spec(bound)
        if read is not None: read(bound['path'])
    if read is not None: read(path)
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='mode',required=True)
    p=sub.add_parser('prepare')
    for name in ('output','evidence','reset-plan','reset-summary','reset-final','reset-outer'): p.add_argument('--'+name,type=Path,required=True)
    for mode in ('run','outer'):
        p=sub.add_parser(mode)
        for name in ('plan','evidence','balance'): p.add_argument('--'+name,type=Path,required=True)
        if mode=='outer': p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('final-absence')
    for name in ('receipt','evidence','output'): p.add_argument('--'+name,type=Path,required=True)
    p=sub.add_parser('qualify')
    for name in ('plan','summary','final','outer','accounting','output'): p.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for key,value in vars(args).items():
        if isinstance(value,Path): setattr(args,key,value.resolve())
    return {'prepare':prepare,'run':run,'outer':outer,'final-absence':final_absence,'qualify':qualify}[args.mode](args)


if __name__=='__main__': raise SystemExit(main())
