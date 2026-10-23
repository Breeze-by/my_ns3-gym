"""One fixed V68 descriptor; same-PID entry, actual wait, full soft fee gate."""
import time
ENTERED_NS = time.monotonic_ns()
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261024_mr3_p2a_v68_probe_stimulus_description'
OLD = A.parent/'20261024_mr3_p2a_v67_owned_stream_qualification'
MODULE = 'report.assets.20261024_mr3_p2a_v68_probe_stimulus_description.run_description_v1'
STATE = Path('/tmp/mr3_p2a_v68_parent_v1')
SPEC = A/'description_spec_v1.json'
OUTPUT = Path('/tmp/mr3_p2a_v68_probe_stimulus_description_v1.json')
CAP, WORK = Decimal('120'), Decimal('60')
ENTRY, CEILING = Decimal('110187.6667339046018'), Decimal('180000')
OLD_G = '50c740a64754aaa2dc3f2707cf5b0159eb929a28'
LEDGER_SHA = '0a5cc4cf558578c4ce3cf32628049850a247aef6756440977dba5214dbebaa00'
CONSUMER_SHA = 'ea5c786ec06b3fb1b45658cb645f376bb6bde86c788f593f9bd1751b79ffd71c'
KEYS = {'dev':'st_dev','ino':'st_ino','mode':'st_mode','size':'st_size',
        'mtime_ns':'st_mtime_ns','ctime_ns':'st_ctime_ns'}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    def unique(pairs):
        result={}
        for key,value in pairs:
            require(key not in result,'duplicate JSON key')
            result[key]=value
        return result
    return json.loads(raw,object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value,stream,indent=2,allow_nan=False)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())


def identity(pid):
    try:
        tail=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
        return dict(pid=pid,start_ticks=int(tail[19]),parent=int(tail[1]),
                    group=int(tail[2]),session=int(tail[3]),state=tail[0])
    except (OSError,ValueError,IndexError):
        return None


def same(left, right):
    return (type(left) is dict and type(right) is dict and all(
        type(left.get(k)) is int and left[k]>0 and left[k]==right.get(k) for k in ('pid','start_ticks')))


def git(*argv):
    return subprocess.check_output(['git',*argv],cwd=ROOT,timeout=10,stderr=subprocess.PIPE)


def clean_freeze(freeze):
    require(type(freeze) is str and re.fullmatch('[0-9a-f]{40}',freeze),'exact CLI freeze required')
    require(git('rev-parse','HEAD').decode().strip()==freeze
            ==git('rev-parse','origin/main').decode().strip()
            and not git('status','--porcelain','--untracked-files=all'),'clean HEAD==origin/main==CLI freeze required')


def proof(path, maximum=2*1024*1024):
    path=Path(path)
    require(path.is_absolute() and '..' not in path.parts and path.resolve(strict=True)==path,'noncanonical bound path')
    before=path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size<=maximum,'not regular or over metadata/source cap')
    with path.open('rb') as stream:
        require(all(getattr(os.fstat(stream.fileno()),v)==getattr(before,v) for v in KEYS.values()),'opened object changed')
        raw=stream.read(maximum+1)
    after=path.lstat()
    require(len(raw)==before.st_size and all(getattr(before,v)==getattr(after,v) for v in KEYS.values()),'bound bytes changed')
    return raw,dict(path=str(path),bytes=len(raw),sha256=sha(raw),stat={k:getattr(after,v) for k,v in KEYS.items()})


def sources(freeze, rows):
    """Only 13 source/spec/closed-metadata files; never either data original."""
    clean_freeze(freeze)
    raw,spec_proof=proof(SPEC,262144);spec=decode(raw)
    require(spec.get('admitted') is True and spec.get('execution_freeze')=='CLI_EXACT_PUSHED_FREEZE'
            and spec.get('schema')=='mr3-v68-fixed-received-stimulus-description-spec-v1','not admitted fixed V68 spec')
    require(spec['activity_to_describe']['freeze']==OLD_G and spec['activity_to_describe']['actual_returncode']==1
            and spec['output']['path']==str(OUTPUT),'fixed old FAIL/output differs')
    budget=spec['engineering_budget_candidate']
    require(budget['complete_parent_seconds']=='120' and budget['consumer_work_seconds']=='60'
            and Decimal(budget['entry_seconds'])==ENTRY and Decimal(budget['ceiling_seconds'])==CEILING
            and Decimal(budget['remaining_seconds'])==CEILING-ENTRY,'fixed resource arithmetic differs')
    expected={SPEC:spec_proof, A/'run_description_v1.py':None}
    require(len(spec['source_bindings'])==8 and len({v['path'] for v in spec['source_bindings']})==8,'eight unique interpretation/consumer sources required')
    for row in spec['source_bindings']:
        path=ROOT/row['path'];require(path.is_relative_to(ROOT) and '..' not in path.parts,'source outside repository')
        expected[path]=row
    consumer=expected.get(A/'describe_probe_v1.py')
    require(type(consumer) is dict and consumer['sha256']==CONSUMER_SHA and consumer['bytes']==28112,'golden consumer differs')
    fixed_metadata={'inventory':OLD/'closed_inventory_v1.json',
                    'previous_accounting':OLD/'closure_ledger_v1.json',
                    'fixed_input_reference':OLD/'checks/v68_fixed_inputs_v1.json'}
    for key,path in fixed_metadata.items():
        require(spec[key]['path']==str(path),'fixed closed metadata path differs: '+key)
        expected[path]=spec[key]
    require(len(expected)==13 and not set(map(Path,[v['path'] for v in spec['inputs']])) & set(expected),
            'source set must exclude both originals')
    saved={}
    for path,wanted in sorted(expected.items(),key=lambda x:str(x[0])):
        current_raw,current=proof(path)
        if wanted is not None:
            require(current['bytes']==wanted['bytes'] and current['sha256']==wanted['sha256'],'source/metadata pin differs: '+str(path))
            if 'stat' in wanted:require(current['stat']==wanted['stat'],'saved metadata stat differs: '+str(path))
        require(current_raw==git('show',freeze+':'+str(path.relative_to(ROOT))),'bound bytes absent/different in execution Git: '+str(path))
        rows.append(current);saved[path]=current_raw
    ledger=decode(saved[fixed_metadata['previous_accounting']])
    require(len(saved[fixed_metadata['previous_accounting']])==7828 and sha(saved[fixed_metadata['previous_accounting']])==LEDGER_SHA,
            'exact actual V67 ledger bytes differ')
    require(ledger['passed'] is True and ledger['activity_passed'] is False and ledger['execution_freeze']==OLD_G
            and type(ledger['actual_root_tool_session_id']) is int and ledger['actual_root_tool_session_id']==57699
            and type(ledger['actual_root_tool_returncode']) is int and ledger['actual_root_tool_returncode']==1
            and ledger['actual_before_after_equal'] is True and ledger['all_saved_main_identities_fresh_gone'] is True
            and ledger['capacity_qualified'] is False and ledger['P2A_complete'] is False
            and Decimal(ledger['engineering_cumulative_seconds'])==ENTRY
            and Decimal(ledger['engineering_ceiling_seconds'])==CEILING
            and Decimal(ledger['engineering_remaining_seconds'])==CEILING-ENTRY
            and Decimal(ledger['pilot_added_parent_union_seconds'])==0
            and Decimal(ledger['validation_added_parent_union_seconds'])==0
            and CEILING-ENTRY>=CAP,'actual closed entry is not funded/typed FAIL metadata')
    refs=decode(saved[fixed_metadata['fixed_input_reference']])
    require(refs['schema']=='mr3-v68-fixed-input-reference-from-v67-inventory-v1'
            and refs['evidence_freeze']==OLD_G and refs['inventory']==spec['inventory']
            and refs['total_original_bytes']==sum(v['expected_bytes'] for v in spec['inputs']),
            'fixed original reference/inventory relation differs')
    require([(r['original'],r['original_bytes'],r['original_sha256']) for r in refs['inputs']]
            ==[(r['path'],r['expected_bytes'],r['expected_sha256']) for r in spec['inputs']],
            'original input reference pins differ')
    clean_freeze(freeze)
    return spec,saved


def wait_command(argv, console):
    value=dict(actual_argv=argv,cwd=str(W),call_started_monotonic_ns=time.monotonic_ns(),
               actual_waited=False,actual_returncode=None,child_identity=None,wait_errors=[],spawn_error=None)
    process=None
    stream=Path(console).open('x')
    try:
        try:
            env=dict(os.environ,PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1')
            env.pop('PYTHONPATH',None);env.pop('PYTHONHOME',None)
            process=subprocess.Popen(argv,cwd=W,env=env,stdout=stream,stderr=subprocess.STDOUT)
            value['spawn_returned_monotonic_ns']=time.monotonic_ns()
            value['child_identity']=identity(process.pid)
            if value['child_identity'] is None:value['wait_errors'].append('real spawned identity unavailable')
        except BaseException as error:
            value['spawn_error']=repr(error)
        if process is not None:
            while True:
                try:
                    value['actual_returncode']=process.wait();value['actual_waited']=True;break
                except BaseException as error:
                    value['wait_errors'].append(repr(error))
    finally:
        try:stream.close()
        except BaseException as error:value['wait_errors'].append('console close: '+repr(error))
    value['ended_monotonic_ns']=time.monotonic_ns()
    value['actual_wait_seconds']=str(Decimal(value['ended_monotonic_ns']-value['call_started_monotonic_ns'])/10**9)
    try:value['console']={'path':str(console),'sha256':sha(Path(console).read_bytes()),'bytes':Path(console).stat().st_size}
    except BaseException as error:value['wait_errors'].append('console proof: '+repr(error))
    return value


def execute(freeze, initial_errors=()):
    errors=list(initial_errors);before=[];after=[];spec=None;entry_verified=False
    owner=identity(os.getpid());started=None;consumer=None;description={};output_proof=None
    try:
        bootstrap=decode((STATE/'bootstrap.json').read_bytes())
        require(bootstrap['execution_freeze']==freeze and same(bootstrap['bootstrap_identity'],owner)
                and type(bootstrap['complete_parent_started_monotonic_ns']) is int
                and 0<bootstrap['complete_parent_started_monotonic_ns']<=ENTERED_NS,'actual same-PID bootstrap/start unavailable')
        started=bootstrap['complete_parent_started_monotonic_ns']
        spec,saved=sources(freeze,before);entry_verified=True
        recovery=[];(STATE/'source_snapshots').mkdir()
        for path,raw in saved.items():
            snapshot=STATE/'source_snapshots'/(sha(raw)+'_'+path.name+'.rawbytes')
            if not snapshot.exists():snapshot.write_bytes(raw)
            require(snapshot.read_bytes()==raw,'source recovery differs')
            recovery.append({'original':str(path),'snapshot':str(snapshot),'bytes':len(raw),'sha256':sha(raw)})
        write(STATE/'source_recovery_v1.json',recovery)
        command=[freeze if value=='<new-exact-40hex-freeze>' else value for value in spec['prospective_cli']]
        require(command==['/usr/bin/python3','-B','-m',MODULE.rsplit('.',1)[0]+'.describe_probe_v1',
            '--freeze',freeze,'--spec',str(SPEC),'--output',str(OUTPUT)],'declared consumer argv differs')
        write(STATE/'entry.json',dict(execution_freeze=freeze,driver_identity=owner,
            complete_parent_started_monotonic_ns=started,source_before=before,
            actual_consumer_argv=command,no_automatic_retry=True,hard_realtime_claimed=False))
        require(not errors,'bootstrap exec failed')
        require(not OUTPUT.exists(),'consumer output exists; preserve old attempt')
        require(time.monotonic_ns()-started<int(CAP*10**9),'parent allocation exhausted before consumer submission')
        consumer=wait_command(command,STATE/'consumer.log')
        write(STATE/'execution.json',consumer)
        if OUTPUT.exists():
            raw,output_proof=proof(OUTPUT,1048576);value=decode(raw)
            description={k:value.get(k) for k in ('schema','passed','description_status','error','postcheck_error',
                'deadline_exceeded','raw_input_bytes_read','actual_work_seconds','execution_freeze','spec_sha256',
                'input_proofs','original_activity_passed','original_FAIL_preserved','root_cause',
                'native_or_physics_or_qualification_credit','identity')}
            require(same(value.get('identity'),consumer['child_identity']),'consumer output borrows another identity')
        require(consumer['actual_waited'] and consumer['actual_returncode']==0
                and not consumer['wait_errors'] and consumer['spawn_error'] is None,'consumer actual wait did not pass')
        require(description.get('schema')==spec['output']['schema'] and description.get('passed') is True
                and description.get('execution_freeze')==freeze and description.get('spec_sha256')==sha(saved[SPEC])
                and description.get('original_activity_passed') is False and description.get('original_FAIL_preserved') is True
                and description.get('native_or_physics_or_qualification_credit') is False
                and description.get('raw_input_bytes_read')==sum(v['expected_bytes'] for v in spec['inputs'])
                and Decimal(str(description.get('actual_work_seconds')))<=WORK,'complete fixed descriptor scope differs')
        require(description.get('input_proofs')==[{'path':r['path'],'bytes':r['expected_bytes'],'sha256':r['expected_sha256']}
                for r in spec['inputs']],'actual complete input proofs differ')
    except BaseException as error:
        errors.append(repr(error))
    finally:
        try:
            sources(freeze,after)
            if output_proof is not None:require(proof(OUTPUT,1048576)[1]==output_proof,'consumer derived output changed')
        except BaseException as error:
            errors.append('post-source: '+repr(error))
    ended=time.monotonic_ns();fee=Decimal(ended-started)/10**9 if started is not None else None
    if fee is not None and fee>CAP:errors.append('complete parent soft fee cap exceeded; all actual seconds retained')
    passed=bool(not errors and before and before==after and fee is not None and fee<=CAP
                and consumer and consumer['actual_waited'] and consumer['actual_returncode']==0 and description.get('passed') is True)
    result=dict(schema='mr3-v68-fixed-description-parent-result-v1',passed=passed,execution_freeze=freeze,
        driver_identity=owner,errors=errors,complete_parent_started_monotonic_ns=started,
        ended_monotonic_ns=ended,complete_parent_fee_known=fee is not None,
        actual_parent_seconds=str(fee) if fee is not None else None,
        observed_execute_lower_bound_seconds=str(Decimal(ended-ENTERED_NS)/10**9),
        engineering_entry_verified=entry_verified,engineering_entry_seconds=str(ENTRY),
        engineering_added_parent_union_seconds=str(fee) if fee is not None else None,
        engineering_cumulative_seconds=str(ENTRY+fee) if entry_verified and fee is not None else None,
        engineering_ceiling_seconds=str(CEILING),
        engineering_remaining_seconds=str(CEILING-ENTRY-fee) if entry_verified and fee is not None else None,
        source_before=before,source_after=after,post_source_check_attempted=True,
        consumer=consumer,consumer_output=output_proof,consumer_description=description,
        raw_input_bytes_read=description.get('raw_input_bytes_read') if consumer is not None else 0,
        fee_scope='same-PID bootstrap entry through post-source and final summary record boundary; nested wait not added',
        complete_parent_cap_seconds='120',consumer_work_seconds='60',hard_realtime_claimed=False,
        actual_root_tool_reap_and_driver_freshgone_required_externally=True,
        all_submitted_consumer_waited=consumer is None or consumer.get('actual_waited') is True,
        original_FAIL_rejudged=False,native_runs=0,model_runs=0,scientific_qualification=False,
        capacity_qualified=False,automatic_policy_entry_allowed=False,P2A_complete=False,
        pilot_added_parent_union_seconds='0',validation_added_parent_union_seconds='0')
    write(STATE/'summary.json',result)
    print(json.dumps({k:result[k] for k in ('passed','complete_parent_fee_known','actual_parent_seconds','raw_input_bytes_read')}),flush=True)
    return 0 if passed else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',required=True)
    parser.add_argument('--execute',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    require(Path(__file__).resolve()==A/'run_description_v1.py' and Path.cwd()==W,'canonical fixed parent/cwd required')
    require(re.fullmatch('[0-9a-f]{40}',args.freeze),'exact CLI freeze required')
    if args.execute:return execute(args.freeze)
    STATE.mkdir(exist_ok=False)
    owner=identity(os.getpid());require(owner is not None,'bootstrap identity unavailable')
    command=['/usr/bin/python3','-B','-m',MODULE,'--freeze',args.freeze,'--execute']
    write(STATE/'bootstrap.json',dict(schema='mr3-v68-same-pid-bootstrap-v1',execution_freeze=args.freeze,
        complete_parent_started_monotonic_ns=ENTERED_NS,bootstrap_identity=owner,
        observed_bootstrap_argv=sys.argv,exec_argv=command,
        start_scope='first observed Python bootstrap module entry; no unobserved earlier time invented'))
    try:
        os.execv(command[0],command)
    except BaseException as error:
        return execute(args.freeze,['bootstrap exec failed: '+repr(error)])


if __name__=='__main__':raise SystemExit(main())
