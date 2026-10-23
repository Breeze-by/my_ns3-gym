"""One read-only observation of fixed V67 closed metadata; never audit raw."""
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import stat

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
PLAN = W / 'report/assets/20261024_mr3_p2a_v67_owned_stream_qualification/plan_v1.json'
PLAN_SHA = 'feb5330fbacfa6925a7b57674204ab7e356e1e3fbb2a614086dd6236ccf041d0'
FREEZE = '50c740a64754aaa2dc3f2707cf5b0159eb929a28'
OUT = Path('/tmp/mr3_p2a_v67_closed_capacity_observations_v1')
CAP = 2 * 1024 * 1024


def read(path, proofs):
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > CAP:
        raise ValueError('metadata is not regular or exceeds predeclared 2MiB: ' + str(path))
    raw = path.read_bytes()
    after = path.lstat()
    if not raw.endswith(b'\n') or any(getattr(before, k) != getattr(after, k) for k in
            ('st_dev','st_ino','st_size','st_mtime_ns','st_ctime_ns')):
        raise ValueError('metadata not closed/stable: ' + str(path))
    value = json.loads(raw)
    proofs.append({'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest()})
    return value


def write(name, value):
    destination = OUT / name
    with destination.open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')
    return {'path':str(destination),'bytes':destination.stat().st_size,
            'sha256':hashlib.sha256(destination.read_bytes()).hexdigest()}


def base(stage, scope, proofs):
    return {'schema':'mr3-v67-closed-capacity-observation-v1','stage':stage,'scope':scope,
            'freeze':FREEZE,'plan_sha256':PLAN_SHA,'inputs':proofs,'capacity_qualified':False,
            'observer_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'automatic_policy_entry_allowed':False,'root_tool_reaped_by_this_observer':False,
            'scientific_raw_or_result_streams_read':False,'independent_scientific_gate_rerun':False,
            'canonical_writes':False,'nested_seconds_are_not_additional_parent_fees':True}


def command(row):
    keys=('id','role','required','passed','returncode','execution_kind','wall_seconds',
          'started_wall_monotonic_ns','ended_wall_monotonic_ns','output','output_sha256','receipt','errors')
    return {key:row.get(key) for key in keys}


def native(stage, proofs):
    receipt = read(stage['native']['receipt'], proofs)
    if receipt.get('execution_kind') != 'subprocess_waited' or type(receipt.get('returncode')) is not int:
        raise ValueError('native receipt does not describe an actual completed wait')
    if receipt.get('freeze') != FREEZE or receipt.get('plan_sha256') != PLAN_SHA:
        raise ValueError('native receipt freeze/plan differs')
    value = base(stage['stage'],'native actually waited; whole stage may still be active',proofs)
    value['native_command'] = command(receipt)
    destination = Path(stage['native']['output'])
    if destination.exists() and 'output_sha256' in receipt:
        summary = read(destination, proofs)
        if proofs[-1]['sha256'] != receipt['output_sha256'] or summary.get('freeze') != FREEZE:
            raise ValueError('native summary does not match its actual receipt SHA/freeze')
        value['benchmark'] = {key:summary.get(key) for key in
            ('passed','workers','valid_transitions','wall_sec_including_all_attempts','effective_transition_per_wall_sec')}
        episodes=[]
        for worker in summary['workers_results']:
            shutdowns = {row.get('epoch'):row for row in worker.get('shutdown_receipts',[])}
            for episode in worker['episodes']:
                row={key:episode.get(key) for key in ('epoch','scene','seed','transitions','startup_wall_sec',
                    'transition_wall_sec','wall_sec_including_startup_and_closure','terminated','truncated','reason','output_directory')}
                row['worker_id']=worker['worker_id']
                dt=sum((Decimal(str(v)) for v in episode.get('dt_values',[])),Decimal(0))
                row['task_sim_seconds_from_actual_dt_values']=str(dt)
                row['dt_record_count']=len(episode.get('dt_values',[]))
                row['zero_dt_count']=sum(v==0 for v in episode.get('dt_values',[]))
                transition=episode.get('transition_wall_sec')
                row['transition_wall_per_task_sim_second']=(str(Decimal(str(transition))/dt)
                    if transition is not None and dt>0 else None)
                whole,startup=episode.get('wall_sec_including_startup_and_closure'),episode.get('startup_wall_sec')
                row['nonstartup_nontransition_residual_seconds']=(str(Decimal(str(whole))-Decimal(str(startup))-Decimal(str(transition)))
                    if all(v is not None for v in (whole,startup,transition)) else None)
                row['pure_closure_wall_seconds']=None
                row['closure_timing_note']='No separate closure timer in this summary; residual includes closure AND other uninstrumented episode work.'
                closed=shutdowns.get(episode.get('epoch'))
                row['shutdown']={key:closed.get(key) for key in ('worker_returncode','forced_shutdown','failed_sample',
                    'remaining_owned_processes','remaining_owned_zombies')} if closed is not None else None
                episodes.append(row)
        value['episodes']=episodes
    return value


def closed_stage(stage, proofs):
    directory=Path(stage['native']['receipt']).parent
    value=read(directory/'stage.json',proofs)
    if value.get('stage') != stage['stage'] or value.get('status') not in ('PASS','FAIL','SKIPPED'):
        raise ValueError('not a final structured stage status')
    result=base(stage['stage'],'closed stage small metadata only; full parent may remain active',proofs)
    result['stage_result']={key:value.get(key) for key in ('status','passed','wall_seconds',
        'within_stage_wall_allocation','effective_stage_wall_cap_seconds','budget_allocation','skipped_audits','error')}
    jobs=[]
    declared={row['id']:row for row in stage['audits']}
    intervals=[]
    for name,row in value.get('audits',{}).items():
        item=command(row);item['declared_role']=declared.get(name,{}).get('role')
        item['declared_required']=declared.get(name,{}).get('required',True)
        if row.get('execution_kind')=='subprocess_waited':
            actual=read(row['receipt'],proofs)
            for key in ('freeze','plan_sha256','id','execution_kind','returncode','passed',
                        'started_wall_monotonic_ns','ended_wall_monotonic_ns','wall_seconds','output_sha256'):
                expected=FREEZE if key=='freeze' else PLAN_SHA if key=='plan_sha256' else row.get(key)
                if actual.get(key)!=expected:raise ValueError('closed audit receipt differs: '+name+'/'+key)
            intervals.append((row['started_wall_monotonic_ns'],row['ended_wall_monotonic_ns']))
        jobs.append(item)
    result['audits']=jobs
    result['required_role_statuses']=[{'id':name,'role':spec['role'],
        'passed':value.get('audits',{}).get(name,{}).get('passed')}
        for name,spec in declared.items() if spec.get('role') and spec.get('required',True)]
    result['native']=command(value['native']) if value.get('native') else None
    result['watcher']=command(value['watcher']) if value.get('watcher') else None
    end=value.get('native',{}).get('ended_wall_monotonic_ns') if value.get('native') else None
    result['native_end_to_last_audit_wait_end_seconds']=(str(Decimal(max(hi for _,hi in intervals)-end)/10**9)
        if intervals and end is not None else None)
    result['audit_first_spawn_to_last_wait_end_seconds']=(str(Decimal(max(hi for _,hi in intervals)-min(lo for lo,_ in intervals))/10**9)
        if intervals else None)
    result['full_audit_command_wall_seconds']=value.get('audits',{}).get('full',{}).get('wall_seconds')
    return result


def main():
    proofs=[];plan=read(PLAN,proofs)
    if proofs[-1]['sha256']!=PLAN_SHA:raise ValueError('fixed V67 plan differs')
    created=[]
    for stage in plan['stages']:
        for kind,path,function in [('native',Path(stage['native']['receipt']),native),
                                  ('stage',Path(stage['native']['receipt']).parent/'stage.json',closed_stage)]:
            name=stage['stage']+'_'+kind+'_closed_v1.json'
            if path.exists() and not (OUT/name).exists():
                inputs=list(proofs)
                created.append(write(name,function(stage,inputs)))
    outer=Path('/tmp/mr3_p2a_reach_v67_matrix_wait/actual_wait.json')
    if outer.exists() and not (OUT/'matrix_actual_wait_closed_v1.json').exists():
        inputs=list(proofs);wait=read(outer,inputs)
        if wait.get('actual_waited') is not True or type(wait.get('actual_returncode')) is not int:
            raise ValueError('matrix outer wait is incomplete')
        summary=read(Path(plan['output_directory'])/'summary.json',inputs)
        if summary.get('freeze')!=FREEZE or summary.get('plan_sha256')!=PLAN_SHA:
            raise ValueError('matrix summary freeze/plan differs')
        if any(wait.get('child_identity',{}).get(k)!=summary.get('coordinator_identity',{}).get(k)
               for k in ('pid','start_ticks')):
            raise ValueError('matrix actual wait does not join coordinator identity')
        value=base('matrix','actual matrix child waited; Root complete parent remains externally owned',inputs)
        value['outer_wait']={k:wait.get(k) for k in ('actual_waited','actual_returncode','actual_child_wait_seconds',
            'started_monotonic_ns','ended_monotonic_ns','source_unchanged','passed','errors','actual_argv')}
        value['matrix_summary']={k:summary.get(k) for k in ('passed','charged_wall_seconds',
            'within_matrix_wall_allocation','all_submitted_children_waited','source_end_error')}
        value['stage_statuses']=[{k:row.get(k) for k in ('stage','status','passed','wall_seconds','reason','error')}
                                 for row in summary['stages']]
        created.append(write('matrix_actual_wait_closed_v1.json',value))
    print(json.dumps({'new_closed_milestones':created,'capacity_qualified':False}))


if __name__=='__main__':main()
