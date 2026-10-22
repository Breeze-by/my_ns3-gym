#!/usr/bin/python3
"""Run only after V45 driver exit: metadata/hash/proc review, never replay.

No production/reader modules, models, native input streams or geometry kernels
are imported. A PASS here concerns evidence consistency/closure. P2A credit is
a separate conjunction of actual qualification, update and strict task reports.
"""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261022_mr3_p2a_v45_preparation_classification'
PREFIX = Path('/tmp/mr3_p2a_reach_v45')
PLAN_SHA = '0964c074510e0601d23b33b5493e71e6dd95e945adb24dda621649d76f1bd8b5'
ENTRY = Decimal('50048.2440707956018')
CAPS = {'engineering': Decimal('75000'), 'pilot': Decimal('2905.9547395464029'),
        'validation': Decimal('9000')}
RULES = {'safety_contract':'mr3-reach-v1', 'seed_rule':'exact-point-bridge-v2',
         'start_graph_rule':'point-attachment-3x3-v1', 'reach_geometry_rule':'cone-support-v2'}


def decimal(value):
    if type(value) not in (str, int, float):
        raise ValueError('invalid decimal')
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('nonfinite decimal')
    return result


def proc(identity):
    try:
        fields=(Path('/proc')/str(identity['pid'])/'stat').read_text().rsplit(')',1)[1].split()
        return {'pid':identity['pid'], 'start_ticks':int(fields[19]), 'state':fields[0],
                'parent':int(fields[1]), 'group':int(fields[2]), 'session':int(fields[3])}
    except FileNotFoundError:
        return None


def union(rows, scope):
    intervals=sorted((r['started_monotonic_ns'],r['ended_monotonic_ns'])
                     for r in rows if r['scope']==scope)
    total=0;lo=hi=None
    for begin,end in intervals:
        if lo is None:lo,hi=begin,end
        elif begin<=hi:hi=max(hi,end)
        else:total+=hi-lo;lo,hi=begin,end
    return Decimal(total+(hi-lo if lo is not None else 0))/10**9


class Review:
    def __init__(self, freeze):
        self.freeze=freeze
        self.errors=[];self.credit_failures=[];self.files={};self.documents={};self.identities={}
        self.observed_scientific_failures=[]

    def check(self, condition, message):
        if not condition:self.errors.append(message)
        return bool(condition)

    def credit(self, condition, message):
        if not condition:self.credit_failures.append(message)
        return bool(condition)

    def scientific(self, condition, message, *, claimed_pass=False, evidence=None):
        if not condition:
            self.credit(False,message)
            self.observed_scientific_failures.append({'label':message,'passed':False,'evidence':evidence})
            if claimed_pass:self.check(False,'reported scientific PASS contradicts actual evidence: '+message)
        return bool(condition)

    def bind(self, path, expected=None):
        path=Path(path).resolve(strict=True)
        if path not in self.files:
            before=path.stat();h=hashlib.sha256();size=0
            with path.open('rb') as stream:
                for chunk in iter(lambda:stream.read(1024*1024),b''):
                    h.update(chunk);size+=len(chunk)
            after=path.stat()
            stamp=lambda s:[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
            self.check(stamp(before)==stamp(after),'file changed while binding: '+str(path))
            self.files[path]={'sha256':h.hexdigest(),'bytes':size,'stat':stamp(after)}
        value=self.files[path]
        if expected is not None:
            wanted=expected if type(expected) is str else expected['sha256']
            self.check(value['sha256']==wanted,'bound SHA differs: '+str(path))
            if type(expected) is dict and 'bytes' in expected:
                self.check(value['bytes']==expected['bytes'],'bound byte count differs: '+str(path))
        return {'path':str(path),**value}

    def identities_in(self, value, origin):
        if type(value) is dict:
            if type(value.get('pid')) is int and type(value.get('start_ticks')) is int:
                self.check(value['pid']>0 and value['start_ticks']>0,'invalid saved PID/start: '+origin)
                key=(value['pid'],value['start_ticks'])
                row=self.identities.setdefault(key,{'saved':value,'origins':[]})
                if origin not in row['origins']:row['origins'].append(origin)
            for child in value.values():self.identities_in(child,origin)
        elif type(value) is list:
            for child in value:self.identities_in(child,origin)

    def load(self, path, expected=None):
        path=Path(path).resolve(strict=True)
        if path.suffix!='.json':raise ValueError('metadata reader refuses non-JSON: '+str(path))
        self.bind(path,expected)
        if path not in self.documents:
            def pairs(values):
                result={}
                for key,value in values:
                    if key in result:raise ValueError('duplicate metadata key')
                    result[key]=value
                return result
            value=json.loads(path.read_bytes(),object_pairs_hook=pairs,
                parse_constant=lambda _:(_ for _ in ()).throw(ValueError('nonfinite metadata')))
            self.documents[path]=value;self.identities_in(value,str(path))
        return self.documents[path]

    def identity_and_rules(self, value, label, *, all_rules=False):
        self.check(value.get('freeze',self.freeze)==self.freeze,label+': freeze differs')
        for key,wanted in RULES.items():
            if all_rules or key in value:self.check(value.get(key)==wanted,label+': '+key+' differs')

    def child(self, child, label, *, pass_key='passed'):
        if child is None:return None
        kind=child.get('execution_kind')
        if kind=='subprocess_waited':
            own=self.load(child['receipt'])
            self.check(own==child,label+': saved command receipt differs')
            self.check(own.get('freeze')==self.freeze and own.get('plan_sha256')==PLAN_SHA,
                       label+': receipt freeze/plan differs')
            self.check(own.get('schema')=='mr3-reach-native-wait-v1'
                       and own.get('safety_contract')=='mr3-reach-v1',label+': command receipt profile differs')
            self.check(type(own.get('returncode')) is int and own.get('argv')==own.get('command_argv'),
                       label+': missing typed return code or command equality')
            result=self.load(child['output'],child['output_sha256']) if Path(child['output']).is_file() else None
            actual_pass=(not own.get('errors') and own.get('returncode')==0 and type(result) is dict
                         and result.get(pass_key) is True and result.get('freeze',self.freeze)==self.freeze)
            self.check(own.get('passed') is actual_pass,label+': waited child PASS disagrees with actual result/rc')
        elif kind in ('aggregate','fifo_manifest'):
            result=self.load(child['output'],child['output_sha256'])
            if kind=='aggregate':
                self.check(type(result) is dict and child.get('passed') is result.get('passed'),
                           label+': aggregate PASS disagrees with its result')
            else:
                self.check(type(result) is list and child.get('passed') is all(x.get('passed') is True for x in child.get('members',[])),
                           label+': FIFO manifest/member verdict differs')
        else:
            self.observed_scientific_failures.append({'label':label,'execution_kind':kind,'passed':child.get('passed')})
            return None
        if child.get('passed') is not True:
            self.observed_scientific_failures.append({'label':label,'passed':False,'errors':child.get('errors')})
        return result

    def finish(self):
        for path,wanted in self.files.items():
            current=path.stat()
            self.check([current.st_dev,current.st_ino,current.st_size,current.st_mtime_ns,current.st_ctime_ns]
                       ==wanted['stat'],'bound metadata/source changed before verdict: '+str(path))
        gone=[]
        for row in self.identities.values():
            current=proc(row['saved'])
            absent=current is None or current['start_ticks']!=row['saved']['start_ticks']
            self.check(absent,'saved identity remains present, including Z: '+str(row['saved']['pid']))
            gone.append({**row,'current':current,'original_identity_gone':absent,'zombie_counts_present':True})
        return gone


def run(freeze):
    r=Review(freeze)
    entry=r.load(Path(str(PREFIX)+'_driver_v1/entry.json'))
    # Fail immediately if called while the coordinator is still alive/Z. Do
    # not inspect partially written activity reports or wait/poll the activity.
    current=proc(entry['driver_identity'])
    if current is not None and current['start_ticks']==entry['driver_identity']['start_ticks']:
        raise ValueError('driver has not exited/reaped; refuse early review')
    driver=r.load(Path(str(PREFIX)+'_driver_v1/summary.json'))
    plan=r.load(A/'plan_v1.json',PLAN_SHA)
    r.check(entry['freeze']==driver['freeze']==freeze,'driver freeze differs')
    r.check(entry['driver_identity']==driver['driver_identity'],'driver saved identity differs')
    r.check(decimal(entry['engineering_entry_used_seconds'])==ENTRY,'engineering entry differs')
    ledger_path=Path(str(PREFIX)+'_driver_v1/ledger.jsonl')
    r.bind(ledger_path)
    rows=[json.loads(line) for line in ledger_path.read_bytes().splitlines()]
    r.check(rows==driver['actual_waits'],'driver ledger/summary differ')
    r.check(len({row['name'] for row in rows})==len(rows),'repeated submitted phase/no-retry violated')
    for row in rows:
        r.identities_in(row,'parent ledger '+row['name'])
        r.check(row['scope'] in CAPS and type(row['started_monotonic_ns']) is int
                and row['ended_monotonic_ns']>=row['started_monotonic_ns'],'invalid parent interval')
        r.check(decimal(row['actual_seconds'])==Decimal(row['ended_monotonic_ns']-row['started_monotonic_ns'])/10**9,
                'parent fee arithmetic differs: '+row['name'])
        outer=r.load(Path(row['outer'])/'actual_wait.json')
        r.check(outer['actual_waited'] is True and outer['source_unchanged'] is True
                and outer['source_before']==outer['source_after'],'outer wait/source stability differs: '+row['name'])
        r.check(row['started_monotonic_ns']<=outer['started_monotonic_ns']<=outer['ended_monotonic_ns']
                <=row['ended_monotonic_ns'],'inner receipt escapes complete parent interval')
        r.check(decimal(outer['actual_child_wait_seconds'])==Decimal(outer['ended_monotonic_ns']-outer['started_monotonic_ns'])/10**9,
                'inner actual wait arithmetic differs')
        r.check(row['scope']==outer['scope'] and row['actual_returncode']==outer['actual_returncode'],
                'outer returncode/scope differs: '+row['name'])
        r.check(row['wrapper_identity']==outer['coordinator_identity'],'wrapper/coordinator identity differs')
        if row.get('passed') is not True:
            r.observed_scientific_failures.append({'label':'submitted phase '+row['name'],'passed':False,
                'returncode':row.get('returncode'),'actual_returncode':row.get('actual_returncode'),
                'receipt_errors':row.get('receipt_errors')})
        for item in outer['source_after']:r.bind(item['path'],item)
        r.bind(outer['console']['path'],outer['console']) # Hash only, never parse logs.
    fees={scope:union(rows,scope) for scope in CAPS}
    for scope,key in (('engineering','engineering_added_union_seconds'),('pilot','pilot_added_union_seconds'),
                      ('validation','validation_added_union_seconds')):
        r.check(fees[scope]==decimal(driver[key]),'driver scope union differs: '+scope)
    r.check(ENTRY+fees['engineering']==decimal(driver['engineering_cumulative_used_seconds'])<=75000,
            'engineering cumulative fee/cap differs')
    external=sum((decimal(x['actual_seconds']) for x in rows if x['scope']=='engineering'
                  and x['name'] not in ('preflight','matrix','minimum')),Decimal(0))
    r.check(external==decimal(driver['engineering_external_actual_seconds']) and external<=300,'engineering external fee cap differs')
    for name,cap in (('matrix',18000),('minimum',1800)):
        for row in rows:
            if row['name']==name:r.check(decimal(row['actual_seconds'])<=cap,'parent cap exceeded: '+name)
    fee_gates={}
    for name in ('pilot','validation'):
        main=[x for x in rows if x['name']==name];final=[x for x in rows if x['name']==name+'_final']
        if main:
            r.check(fees[name]<=CAPS[name],name+' actual scope fee exceeds original cap')
            endpoint=(Decimal(final[-1]['ended_monotonic_ns']-main[0]['started_monotonic_ns'])/10**9 if final else None)
            ok=bool(final) and decimal(final[-1]['actual_seconds'])<=300 and fees[name]<=CAPS[name] and endpoint<=CAPS[name]
            fee_gates[name]={'passed':ok,'union_seconds':str(fees[name]),'endpoint_seconds':str(endpoint),'cap_seconds':str(CAPS[name])}
            r.credit(ok,name+' full main+external fee/deadline gate incomplete')
            if final:r.check(ok,name+' actual fee/endpoint exceeds original cap')
    # Current/frozen sources only. Do not follow qualification raw-input bindings.
    names=list(plan['source_bindings'])
    process=subprocess.run(['git','cat-file','--batch'],cwd=ROOT,
        input=('\n'.join(freeze+':'+name for name in names)+'\n').encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=False)
    cursor=0
    for name in names:
        r.bind(ROOT/name,plan['source_bindings'][name])
        end=process.stdout.find(b'\n',cursor);header=process.stdout[cursor:end].split();cursor=end+1
        if len(header)!=3 or header[1]!=b'blob':raise ValueError('frozen source is missing/nonblob: '+name)
        size=int(header[2]);payload=process.stdout[cursor:cursor+size];cursor+=size+1
        r.check(hashlib.sha256(payload).hexdigest()==plan['source_bindings'][name],'Git/plan source differs: '+name)
    r.check(process.returncode==0 and cursor==len(process.stdout),'Git batch source verification incomplete')
    for path,wanted in plan['library_bindings'].items():r.bind(path,wanted)
    matrix_path=Path(plan['output_directory'])/'summary.json'
    matrix=r.load(matrix_path) if matrix_path.exists() else None
    matrix_ok=False;role_count=0;matrix_epochs=[];matrix_stages=[]
    if matrix is not None:
        r.identity_and_rules(matrix,'matrix')
        r.check(matrix.get('schema')=='mr3-reach-preparation-execution-v1'
                and matrix.get('plan_sha256')==PLAN_SHA,'matrix schema/plan SHA differs')
        r.check([x['stage'] for x in matrix['stages']]==[x['stage'] for x in plan['stages'][:len(matrix['stages'])]],
                'matrix actual stage order differs from the fixed plan')
        for completed in matrix['stages']:
            declared=next(s for s in plan['stages'] if s['stage']==completed['stage'])
            if completed.get('status')=='SKIPPED':
                r.check(completed.get('passed') is not True and not completed.get('native')
                        and not completed.get('watcher') and not completed.get('audits'),
                        'SKIPPED matrix stage falsely includes submitted execution/PASS')
                matrix_stages.append({'stage':completed['stage'],'submitted':False,'passed':False,
                    'required_roles':sum(bool(j.get('role')) for j in declared['audits']),
                    'all_required_roles_passed':False,'status':'SKIPPED','reason':completed.get('reason')})
                r.observed_scientific_failures.append({'label':'matrix '+completed['stage'],'passed':False,
                    'status':'SKIPPED','reason':completed.get('reason')})
                continue
            outputs={}
            for child in [completed.get('native'),completed.get('watcher'),*completed.get('audits',{}).values()]:
                if child is not None:outputs[child['id']]=r.child(child,'matrix '+completed['stage']+'/'+child['id'])
            passed=completed.get('passed') is True and completed.get('status')=='PASS' and not completed.get('skipped_audits')
            required=[j for j in declared['audits'] if j.get('role')]
            all_roles=all(completed['audits'].get(j['id'],{}).get('passed') is True
                          and type(outputs.get(j['id'])) is dict and outputs[j['id']].get('passed') is True
                          for j in required)
            if completed.get('passed') is True:
                r.check(passed and all_roles and set(completed['audits'])=={j['id'] for j in declared['audits']}
                        and completed.get('within_stage_wall_allocation') is True,
                        'matrix stage falsely claims complete role PASS')
            role_count+=len(required) if passed and all_roles else 0
            matrix_stages.append({'stage':completed['stage'],'submitted':True,'passed':passed,
                'required_roles':len(required),'all_required_roles_passed':all_roles,'status':completed.get('status'),
                'error':completed.get('error')})
        for declared in plan['stages']:
            run=Path(declared['run_directory'])
            for path in sorted(run.glob('worker*/episode*/metadata.json')):
                meta=r.load(path);r.identity_and_rules(meta,'matrix EP',all_rules=True)
                supervisor_path=path.parent/'supervisor_metadata.json'
                if supervisor_path.exists():
                    saved=r.load(supervisor_path);r.identity_and_rules(saved,'matrix supervisor',all_rules=True)
                    r.check(saved['epoch']==meta['epoch'],'matrix supervisor epoch differs')
                else:
                    stage_pass=any(x['stage']==declared['stage'] and x['passed'] for x in matrix_stages)
                    r.scientific(False,'matrix attempted EP has no completed supervisor metadata: '+str(path.parent),
                                 claimed_pass=stage_pass)
                matrix_epochs.append(meta['epoch'])
                for name in ('summary.json','supervisor_shutdown.json','nav2_shutdown.json','native_stop.json','process_identities.json'):
                    if (path.parent/name).exists():r.load(path.parent/name)
        matrix_ok=(matrix.get('passed') is True and matrix.get('all_submitted_children_waited') is True
            and matrix.get('within_matrix_wall_allocation') is True and len(matrix_stages)==4 and role_count==30
            and len(matrix_epochs)==len(set(matrix_epochs))==12 and all(s['passed'] and s['all_required_roles_passed'] for s in matrix_stages))
    r.scientific(matrix_ok,'complete same-freeze 12EP/30-role native qualification matrix is not established',
                 claimed_pass=matrix is not None and matrix.get('passed') is True)
    qualification_path=Path(str(PREFIX)+'_qualification.json')
    qualification=r.load(qualification_path) if qualification_path.exists() else None
    qualified=(matrix_ok and qualification is not None and qualification.get('schema')=='mr3-reach-scientific-qualification-v1'
        and qualification.get('passed') is True and qualification.get('freeze')==freeze and qualification.get('plan_sha256')==PLAN_SHA
        and qualification.get('mandatory_roles')==30 and len(qualification.get('episodes',[]))==12
        and qualification.get('reach_geometry_rule')=='cone-support-v2' and qualification.get('old_profile_credit_reused') is False)
    if qualification is not None:
        r.check({x['epoch'] for x in qualification.get('episodes',[])}==set(matrix_epochs),
                'qualification episodes differ from actual matrix epochs')
        r.check(Path(qualification['outer_wait']).resolve()==Path(str(PREFIX)+'_matrix_wait/actual_wait.json').resolve(),
                'qualification binds another matrix outer wait')
    r.scientific(qualified,'fresh complete qualification receipt is not established',
                 claimed_pass=qualification is not None and qualification.get('passed') is True)
    policies={};pilot_checkpoint=None
    for name in ('minimum','pilot','validation'):
        declared=plan['policy_stages'][name];output=Path(declared['output_directory']);run=Path(declared['run_directory'])
        summary_path=output/'summary.json';final_path=Path(str(PREFIX)+'_'+name+'_final.json')
        if not summary_path.exists():
            submitted=any(row['name']==name for row in rows)
            policies[name]={'submitted':submitted,'passed':False,'stage_summary_present':False}
            r.credit(False,name+' was not completed')
            if submitted:r.observed_scientific_failures.append({'label':name,'passed':False,'reason':'submitted stage has no completed summary'})
            continue
        main=r.load(summary_path);r.identity_and_rules(main,name+' stage')
        r.check(main.get('plan_sha256')==PLAN_SHA and main.get('stage')==name,'policy stage/plan identity differs')
        for child in [main.get('native'),main.get('watcher'),*main.get('audits',{}).values()]:
            if child is not None:r.child(child,name+'/'+child['id'],pass_key='completed' if child['id']=='native' else 'passed')
        final=r.load(final_path) if final_path.exists() else None
        if final is not None:
            r.identity_and_rules(final,name+' final')
            r.check(final.get('stage')==name and final.get('reach_geometry_rule')=='cone-support-v2'
                    and final.get('summary_sha256')==r.files[summary_path.resolve()]['sha256'],
                    name+' final stage/rule/summary binding differs')
            main_outer=Path(str(PREFIX)+'_'+name+'_wait/actual_wait.json')
            r.check(Path(final['outer_wait']).resolve()==main_outer.resolve()
                    and final.get('outer_wait_sha256')==r.bind(main_outer)['sha256'],
                    name+' final binds another outer actual wait')
        native_path=run/'summary.json';metadata_path=run/'metadata.json'
        native=r.load(native_path) if native_path.exists() else None
        meta=r.load(metadata_path) if metadata_path.exists() else None
        full_child=main.get('audits',{}).get('full');full=(r.load(full_child['output'],full_child['output_sha256'])
            if full_child and Path(full_child['output']).is_file() else None)
        complete=(qualified and main.get('passed') is True and not main.get('errors') and not main.get('skipped_audits')
            and main.get('all_submitted_children_waited') is True and main.get('within_stage_wall_allocation') is True
            and final is not None and final.get('passed') is True and final.get('all_saved_identities_gone') is True
            and final.get('strict_custody_passed') is True and final.get('plan_sha256')==PLAN_SHA
            and full is not None and full.get('schema')=='mr3-reach-ppo-offline-audit-v1' and full.get('passed') is True
            and full.get('errors')==[] and native is not None and native.get('completed') is True
            and native.get('error') is None and native.get('cleanup_errors')==[] and native.get('native_accounting_errors')==[])
        main_evidence=(not main.get('errors') and not main.get('skipped_audits')
            and main.get('all_submitted_children_waited') is True and main.get('within_stage_wall_allocation') is True
            and (main.get('native') or {}).get('passed') is True and (main.get('watcher') or {}).get('passed') is True
            and bool(main.get('audits')) and all(x.get('passed') is True for x in main['audits'].values())
            and full is not None and full.get('passed') is True and full.get('errors')==[]
            and native is not None and native.get('completed') is True and native.get('error') is None
            and native.get('cleanup_errors')==[] and native.get('native_accounting_errors')==[])
        r.scientific(main_evidence,name+' required main scientific execution is incomplete or failed',
                     claimed_pass=main.get('passed') is True)
        if final is not None and final.get('passed') is True:
            r.check(main.get('passed') is True and final.get('all_saved_identities_gone') is True
                and final.get('strict_custody_passed') is True and final.get('within_stage_wall_allocation') is True,
                name+' external final falsely claims complete PASS')
        detail={'submitted':True,'passed':False,'stage_passed':main.get('passed'),'external_final_passed':final.get('passed') if final else None}
        if native is not None and meta is not None:
            # PPO summaries deliberately omit seed/start rules; actual admission
            # metadata and every episode carry those declarations.
            r.identity_and_rules(native,name+' native');r.identity_and_rules(meta,name+' metadata',all_rules=True)
            r.check(native.get('reach_geometry_rule')==RULES['reach_geometry_rule'],name+' native geometry rule differs')
            r.check(meta.get('reach_plan_sha256')==PLAN_SHA and meta.get('reach_qualification_sha256')==(r.files[qualification_path.resolve()]['sha256'] if qualification else None),
                    name+' admission qualification/plan hash differs')
            episodes=native.get('episodes',[]);attempts=native.get('native_attempts',[])
            actual=[Path(x).resolve() for x in main.get('actual_episode_directories',[])]
            attempted_dirs=[Path(x['directory']).resolve() for x in attempts]
            eligible_dirs=[Path(x['directory']).resolve() for x in episodes]
            r.check(len(attempted_dirs)==len(set(attempted_dirs)) and set(attempted_dirs)==set(actual),
                    name+' actual/native attempt inventory metadata differs')
            r.check(len(eligible_dirs)==len(set(eligible_dirs)) and set(eligible_dirs)<=set(attempted_dirs),
                    name+' closed episode inventory is not a unique subset of recorded attempts')
            all_attempts_eligible=(bool(actual) and set(eligible_dirs)==set(actual) and all(
                x.get('training_eligibility',{}).get('training_eligible') is True for x in episodes))
            r.scientific(all_attempts_eligible,name+' actual attempts are not all closed and eligible',
                claimed_pass=main.get('passed') is True,
                evidence={'actual_attempts':len(actual),'closed_episodes':len(episodes),
                    'eligibility':[{'directory':x.get('directory'),'training_eligibility':x.get('training_eligibility')}
                                   for x in episodes]})
            decisions=native.get('decisions');updates=native.get('optimizer_updates')
            r.check(type(decisions) is int and decisions>=0 and decisions==native.get('closed_episode_decisions')
                    ==sum(x['decisions'] for x in episodes),name+' closed-episode decision metadata totals differ')
            r.check(type(native.get('api_records')) is int and native['api_records']>=0
                    and native['api_records']==sum(x['api_records'] for x in episodes),name+' closed-episode API metadata totals differ')
            r.check(native.get('native_recorded_decisions')==sum(x['decisions'] for x in attempts)
                    and native.get('native_api_records')==sum(x['api_records'] for x in attempts),
                    name+' native attempt aggregate metadata totals differ')
            all_native_records_eligible=(decisions==native.get('native_recorded_decisions')
                                        and native.get('api_records')==native.get('native_api_records'))
            r.scientific(all_native_records_eligible,name+' native observed prefix exceeds closed eligible totals',
                claimed_pass=main.get('passed') is True,
                evidence={key:native.get(key) for key in ('decisions','closed_episode_decisions','native_recorded_decisions',
                    'api_records','native_api_records','collector_observed_decisions','collector_observed_api_records')})
            complete=complete and all_attempts_eligible and all_native_records_eligible
            checkpoint=run/'final.zip'
            checkpoint_ok=False
            if checkpoint.is_file():
                checkpoint_proof=r.bind(checkpoint,native.get('final_checkpoint_sha256'))
                checkpoint_ok=checkpoint_proof['bytes']>0 and native.get('final_checkpoint_sha256')==checkpoint_proof['sha256']
                if native.get('final_checkpoint_sha256') is not None:
                    r.check(checkpoint_ok,name+' declared final checkpoint SHA/bytes differs')
            elif native.get('final_checkpoint_sha256') is not None:
                r.check(False,name+' declares a final checkpoint SHA for a missing artifact')
            r.scientific(checkpoint_ok,name+' final checkpoint is unavailable or not fully recorded',
                         claimed_pass=main.get('passed') is True)
            complete=complete and checkpoint_ok
            if final and final.get('final_checkpoint'):
                r.check(final['final_checkpoint']['sha256']==native.get('final_checkpoint_sha256'),name+' final checkpoint evidence differs')
            if name in ('minimum','pilot'):
                rounds=full.get('rounds',[]) if full else []
                actual_changes=bool(rounds) and all(type(x.get('changed_parameter_tensors')) is int and x['changed_parameter_tensors']>0 for x in rounds)
                update_gate=(type(updates) is int and updates>0 and actual_changes
                             and (decisions==16 if name=='minimum' else 2<=decisions<=1870))
                r.scientific(update_gate,name+' positive independent update/decision gate is not established',
                             claimed_pass=main.get('passed') is True)
                complete=complete and update_gate
                if name=='pilot' and checkpoint_ok:pilot_checkpoint={'path':str(checkpoint.resolve()),'sha256':native.get('final_checkpoint_sha256')}
                detail['independent_positive_parameter_changes']=actual_changes
            else:
                strict=[]
                for episode in (full.get('episodes',[]) if full else []):
                    task=episode.get('task',{})
                    strict.append(not episode.get('errors') and task.get('success') is True
                        and decimal(task.get('correct_free_coverage_ratio',0))>=Decimal('.95')
                        and task.get('map_quality_pass') is True and task.get('robot_participation_pass') is True
                        and type(task.get('collision_events')) is int and task['collision_events']==0
                        and task.get('collision_monitoring_fresh') is True
                        and task.get('navigation_protocol_closed') is True and decimal(task.get('elapsed_sim_time_sec',300))<300)
                schedule=[('open',401),('open',402),('open',403)]
                same_checkpoint=pilot_checkpoint is not None and str(Path(meta.get('checkpoint','')).resolve())==pilot_checkpoint['path'] and native.get('input_checkpoint_sha256')==pilot_checkpoint['sha256']
                validation_gate=(type(updates) is int and updates==0 and native.get('schedule_completed') is True and len(episodes)==3
                    and [(x.get('scene'),x.get('seed')) for x in episodes]==schedule and meta.get('schedule')==[list(x) for x in schedule]
                    and len(strict)==3 and all(strict) and full is not None and full.get('task_successes')==3
                    and full.get('task_failures')==[] and same_checkpoint)
                r.scientific(validation_gate,'final-only three strict95 successes/zero-update/same-checkpoint gate is not established',
                             claimed_pass=main.get('passed') is True)
                complete=complete and validation_gate
                detail.update(strict_95_successes=sum(strict),final_only_schedule_complete=native.get('schedule_completed'),same_pilot_final_checkpoint=same_checkpoint,
                    frozen_weight_equality_basis='passed independent full audit; reviewer never loads models')
            for episode in actual:
                for filename in ('metadata.json','supervisor_metadata.json','summary.json','supervisor_shutdown.json','nav2_shutdown.json','native_stop.json'):
                    if (episode/filename).exists():
                        value=r.load(episode/filename)
                        if filename in ('metadata.json','supervisor_metadata.json'):
                            r.identity_and_rules(value,name+' actual EP '+filename,all_rules=True)
            detail.update(eligible_decisions=decisions,optimizer_updates=updates,closed_eligible_episodes=len(episodes),
                actual_attempts=len(actual),native_recorded_decisions=native.get('native_recorded_decisions'),
                native_api_records=native.get('native_api_records'),all_attempts_eligible=all_attempts_eligible,
                all_native_records_eligible=all_native_records_eligible,final_checkpoint=native.get('final_checkpoint_sha256'),
                native_completed=native.get('completed'),native_error=native.get('error'),
                native_cleanup_errors=native.get('cleanup_errors'),native_accounting_errors=native.get('native_accounting_errors'))
        complete=complete and (name=='minimum' or fee_gates.get(name,{}).get('passed') is True)
        if name=='pilot':complete=complete and policies.get('minimum',{}).get('passed') is True
        if name=='validation':complete=complete and policies.get('pilot',{}).get('passed') is True
        detail['passed']=bool(complete);policies[name]=detail;r.credit(complete,name+' independent complete update/task/closure conjunction is not established')
    # Current-activity external absence reports, plus all finalizers/outer
    # receipts above, contribute saved identities. Never read native JSONL/log.
    for row in rows:
        if row['name'].endswith('absence'):
            path=Path(str(PREFIX)+'_'+row['name']+'.json')
            if path.exists():
                absence=r.load(path)
                r.check(absence.get('passed') is True,'external absence did not PASS: '+row['name'])
    archive=A/'closed_inventory_v1.json'
    archive_fact=None
    if archive.exists():
        value=r.load(archive)
        archive_fact={'inventory':r.bind(archive),'schema':value.get('schema'),'entries':len(value.get('entries',[])),
                      'scope':'inventory metadata only; raw archive bytes not read or redecoded by this reviewer'}
    gone=r.finish()
    p2a=(driver.get('passed') is True and driver.get('completed_stages')==['matrix_qualification','minimum','pilot','validation']
        and qualified and all(policies.get(x,{}).get('passed') is True for x in ('minimum','pilot','validation')))
    r.check(driver.get('p2b_gateway_started') is False and driver.get('old_failures_preserved') is True,'P2B/old-failure boundary changed')
    return {'schema':'mr3-p2a-v45-independent-closed-review-v2','created_utc':datetime.now(timezone.utc).isoformat(),
        'passed':not r.errors,'status':'PASS' if not r.errors else 'FAIL','review_errors':r.errors,
        'activity_passed':driver.get('passed'),'independent_p2a_requirements_met':p2a and not r.errors,
        'credit_failures':r.credit_failures,'freeze':freeze,'plan_sha256':PLAN_SHA,
        'engineering_entry_seconds':str(ENTRY),'engineering_added_parent_union_seconds':str(fees['engineering']),
        'engineering_cumulative_seconds':str(ENTRY+fees['engineering']),'engineering_remaining_seconds':str(75000-ENTRY-fees['engineering']),
        'pilot_added_parent_union_seconds':str(fees['pilot']),'validation_added_parent_union_seconds':str(fees['validation']),
        'engineering_external_seconds':str(external),'policy_full_fee_gates':fee_gates,
        'fee_basis':'complete parent actual-wait scope union; nested inner waits never added again; endpoint includes metadata gaps',
        'matrix_stages':matrix_stages,'verified_matrix_role_count':role_count,'matrix_EP_count':len(matrix_epochs),
        'qualification_passed':bool(qualified),'policy_stages':policies,'saved_identities':gone,
        'all_saved_PID_start_identities_fresh_gone':all(x['original_identity_gone'] for x in gone),
        'observed_scientific_failures_preserved':r.observed_scientific_failures,'archive_metadata':archive_fact,
        'metadata_and_source_bindings':[{'path':str(path),**value} for path,value in r.files.items()],
        'reviewer_executed_tests_consumer_model_or_World':False,'raw_native_inputs_read':False,
        'verdict_layers':'review_errors concern metadata/source/fee/identity inconsistency or a false PASS; real failed/ineligible/incomplete scientific attempts remain credit_failures and observed_scientific_failures_preserved',
        'P2B_gateway_credit':False,'user_acceptance_is_separate_from_this_evidence_review':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',required=True)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    if re.fullmatch('[0-9a-f]{40}',args.freeze) is None:parser.error('exact freeze required')
    if args.output.exists():parser.error('exclusive review output exists')
    result=run(args.freeze)
    with args.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({k:result[k] for k in ('passed','activity_passed','independent_p2a_requirements_met','review_errors')}))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
