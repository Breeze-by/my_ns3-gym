"""Bounded P2A route-decision experiments; no qualification or learning entry."""
import argparse
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import threading
import time

from . import reach_preparation as prep, native_custody_reach as custody
from .audit_reach_diagnostic import bound_sources
from .preparation import identity

ROOT = prep.WORKSPACE
W = ROOT / prep.WIRELESS_RELATIVE
A = W / 'report/assets/20261024_mr3_p2a_decisive_tests'
OLD = W / 'report/assets/20261024_mr3_p2a_v71_masked_stimulus_qualification'
OUT = Path('/tmp/mr3_p2a_decisive_tests_v1')
NATIVE = ROOT / 'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_decisive_tests_v1'
PYTHON = '/home/zhuyulab/miniconda3/envs/ns3gym/bin/python'
PILOT_REMAINING = Decimal('2905.9547395464029')
RESERVATION = 26000
require, dump, sha = prep.require, prep.dump, prep.sha


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def prepare():
    """Keep old ELF/build evidence, refresh every actual Python/source binding."""
    binding = json.loads((OLD/'native_custody_binding_v1.json').read_bytes())
    old = json.loads((OLD/'plan_v1.json').read_bytes())
    paths = set(old['source_bindings']) | prep.source_inventory(ROOT)
    paths.update(str(p.relative_to(ROOT)) for p in A.glob('*') if p.is_file() and p.suffix in ('.py','.md','.json'))
    paths -= {str((A/name).relative_to(ROOT)) for name in ('binding.json','feasibility.json','capacity.json')}
    sources = {name:sha(ROOT/name) for name in sorted(paths)}
    native, _ = custody.load_implementation()
    for spec in binding['binaries'].values():
        current = native.file_proof(spec['path'])
        require(current['sha256'] == spec['sha256'] and current['bytes'] == spec['bytes'], 'native ELF changed')
        spec.update(current)
    binding['source_bindings'] = [dict(path=p,sha256=d) for p,d in sources.items()]
    binding['qualification_wrappers'] = [row for row in binding['source_bindings'] if '/mr3_learning/' in row['path']]
    dump(A/'binding.json',binding)
    sources[str((A/'binding.json').relative_to(ROOT))] = sha(A/'binding.json')
    for arm, workers, steps in (('feasibility',1,96),('capacity',2,64)):
        run = NATIVE/arm
        path = A/(arm+'.json')
        argv = ([PYTHON,'-B','-m','mr3_learning.decisive_probe','--plan',str(path)] if arm == 'feasibility' else
            [PYTHON,'-B','-m','mr3_learning.benchmark','--workers','2','--schedule','open:101',
             '--steps','64','--run-id',arm,'--output-root',str(NATIVE),'--base-domain','212',
             '--base-port','15911','--safety-contract','mr3-reach-v1','--seed-rule','exact-point-bridge-v2',
             '--start-graph-rule','point-attachment-3x3-v1','--reach-geometry-rule','cone-support-v2',
             '--diagnostic-uniform-seed','41','--work-wall-seconds','6000','--close-reserve-seconds','180'])
        plan = dict(schema='mr3-reach-feasibility-diagnostic-plan-v1',
            diagnostic_contract='mr3-p2a-decisive-tests-v1', arm=arm, robots_per_environment=3,
            qualification=False, training_eligible=False, optimizer_steps=0, gpu_calls=0,
            safety_contract='mr3-reach-v1', expected_episodes=workers, steps_per_episode=steps,
            run_directory=str(run), output_directory=str(OUT/arm), native_argv=argv,
            native_wall_seconds=6000, audit_wall_seconds=6000, complete_parent_reservation=RESERVATION,
            custody_binding=str(A/'binding.json'), source_bindings=sources,
            library_bindings=old['library_bindings'],
            pilot_budget_changed=False, capacity_qualified=False, automatic_policy_entry_allowed=False)
        for key in ('seed_rule','start_graph_rule','reach_geometry_rule','map_output_packing_profile',
                    'actuation_profile','motion_authority_profile','sensor_source_profile'):
            plan[key] = old[key]
        dump(path,plan)
    print(json.dumps(dict(source_count=len(sources), plans=['feasibility','capacity'])))


def check(plan_path, freeze, clean=False):
    path = Path(plan_path)
    declared = json.loads(path.read_bytes())
    require(declared.get('diagnostic_contract') == 'mr3-p2a-decisive-tests-v1', 'wrong decisive scope')
    plan,proof,stable = bound_sources(path,declared['run_directory'],freeze,ROOT)
    require(plan['arm'] in ('feasibility','capacity') and plan['native_wall_seconds']==6000
        and plan['audit_wall_seconds']==6000 and plan['complete_parent_reservation']==RESERVATION,
        'resource scope changed')
    require(plan['expected_episodes']==(1 if plan['arm']=='feasibility' else 2)
        and plan['steps_per_episode']==(96 if plan['arm']=='feasibility' else 64), 'workload changed')
    require(plan['native_argv'][0:3]==[PYTHON,'-B','-m']
        and plan['native_argv'][3] == ('mr3_learning.decisive_probe' if plan['arm']=='feasibility' else 'mr3_learning.benchmark'),
        'not a declared non-learning entry')
    for name,digest in plan['library_bindings'].items():
        require(sha(name)==digest, 'native library changed')
    if clean:
        require(git('rev-parse','HEAD')==git('rev-parse','origin/main')==freeze and not git('status','--porcelain'),
                'clean pushed exact freeze required')
    custody.verify_binding(ROOT,freeze,plan['custody_binding'])
    from .reach_gates import _load_versioned_native_gates
    profiles={k:plan[k] for k in ('seed_rule','start_graph_rule','map_output_packing_profile',
        'reach_geometry_rule','actuation_profile','motion_authority_profile')}
    _load_versioned_native_gates(ROOT,freeze,proof,plan['source_bindings'],plan['custody_binding'],**profiles)
    return plan


def run_arm(path, freeze, parent_deadline):
    start=time.monotonic_ns()
    plan=check(path,freeze,clean=True)
    out,run=Path(plan['output_directory']),Path(plan['run_directory'])
    require(not out.exists() and not run.exists(),'exclusive experiment; no retry')
    out.mkdir()
    module,_=prep.load_executor()
    lock=threading.Lock()
    with (out/'ledger.jsonl').open('x') as ledger:
        def record(**row):
            with lock:
                ledger.write(json.dumps(dict(monotonic_ns=time.monotonic_ns(),**row))+'\n');ledger.flush()
        runner=module.Runner(out,W,freeze,sha(path),record)
        def job(name,argv,output=None):
            return dict(id=name,argv=list(map(str,argv)),output=str(output or out/(name+'_result.json')),
                receipt=str(out/(name+'_command.json')),console=str(out/(name+'.log')),required=True)
        common=['/usr/bin/python3','-B','-m','mr3_learning.native_custody_reach']
        capture,ready,stop=(out/n for n in ('live_custody.json','ready.json','stop.json'))
        watcher=runner.spawn(job('watcher',[*common,'watch','--run-directory',run,'--freeze',freeze,
            '--binding',plan['custody_binding'],'--ready-file',ready,'--stop-file',stop,'--output',capture],capture))
        native=None
        error=None
        try:
            deadline=time.monotonic()+30
            while not ready.exists():
                require(watcher['process'] is not None and watcher['process'].poll() is None and time.monotonic()<deadline,
                        'live custody not ready')
                time.sleep(.05)
            actual=custody.read_ready_receipt(custody.Reader(),ready,freeze,sha(plan['custody_binding']))
            require(all(actual['watcher_identity'][k]==watcher['value']['process_identity'][k] for k in ('pid','start_ticks')),
                    'watcher identity mismatch')
            print(json.dumps(dict(event='native_start',arm=plan['arm'],monotonic_ns=time.monotonic_ns())),flush=True)
            native=runner.command(job('native',plan['native_argv'],run/'benchmark_summary.json'))
        except Exception as failure:
            error=repr(failure)
        finally:
            boundary=({'launch_receipt':dict(path=native['receipt'],sha256=sha(native['receipt']))} if native else
                      {'native_not_started':True,'reason':'pre_native_admission_failure'})
            dump(stop,dict(schema=custody.SCHEMA_STOP,safety_contract='mr3-reach-v1',freeze=freeze,**boundary))
            watched=runner.finish(watcher)
        episodes=sorted(run.glob('worker*/episode*/metadata.json'))
        print(json.dumps(dict(event='native_closed',arm=plan['arm'],episodes=len(episodes),
            native_rc=None if native is None else native['returncode'],watcher_passed=watched['passed'])),flush=True)
        audits={};skipped=[]
        audit_deadline=min(parent_deadline,time.monotonic_ns()+plan['audit_wall_seconds']*10**9)
        def audit_job(name,module_name,directory,extra=(),python='/usr/bin/python3'):
            output=out/(name+'_result.json')
            return job(name,[python,'-B','-m',module_name,directory,'--freeze',freeze,*extra,'--output',output],output)
        fifo_jobs=[audit_job(f'fifo_{i:03d}','mr3_learning.audit_reach_peer_control',m.parent,
                            ['--plan',path]) for i,m in enumerate(episodes)]
        # Diagnose independent roles even after another diagnostic role FAILs;
        # never convert a failed/missing result into qualification.
        def batch(jobs):
            with ThreadPoolExecutor(max_workers=4) as pool:
                futures=[]
                for j in jobs:
                    if time.monotonic_ns()<audit_deadline:
                        futures.append((j,pool.submit(runner.command,j)))
                    else:skipped.append(j['id'])
                for j,future in futures:
                    audits[j['id']]=future.result()
        if episodes and watched['passed']:
            batch(fifo_jobs)
            manifest=out/'fifo_manifest.json'
            leaves=[dict(episode_directory=str(m.parent),path=j['output'],sha256=sha(j['output']))
                for m,j in zip(episodes,fifo_jobs) if Path(j['output']).exists()]
            dump(manifest,leaves)
            jobs=[]
            for i,m in enumerate(episodes):
                jobs.append(audit_job(f'information_{i:03d}','mr3_learning.audit_reach_information',m.parent))
            jobs.append(audit_job('cadence','mr3_learning.audit_reach_cadence',run))
            if plan['arm']=='feasibility':
                jobs.append(audit_job('stimulus','mr3_learning.audit_decisive_stimulus',run))
            if len(leaves)==len(episodes) and all(audits[j['id']]['passed'] for j in fifo_jobs):
                extra=['--plan',path]
                for leaf in leaves:extra+=['--fifo-result',leaf['path']]
                jobs.append(audit_job('full','mr3_learning.audit_reach_diagnostic',run,extra,PYTHON))
            else:skipped.append('full_missing_passed_fifo')
            batch(jobs)
            if len(leaves)==len(episodes) and time.monotonic_ns()<audit_deadline:
                output=out/'closure_result.json'
                audits['closure']=runner.command(job('closure',[*common,'review','--run-directory',run,
                    '--freeze',freeze,'--binding',plan['custody_binding'],'--capture',capture,
                    '--launch-receipt',out/'native_command.json','--fifo-receipts',manifest,
                    '--expected-episodes',len(episodes),'--output',output],output))
            else:skipped.append('closure')
        else:skipped.append('all_audits_missing_episodes_or_custody')
        source_after=True
        try:bound_sources(path,run,freeze,ROOT)
        except Exception as failure:source_after=False;error=repr(failure)
        ended=time.monotonic_ns()
        result=dict(arm=plan['arm'],freeze=freeze,plan_sha256=sha(path),coordinator_identity=identity(os.getpid()),
            started_monotonic_ns=start,ended_monotonic_ns=ended,parent_wall_seconds=str(Decimal(ended-start)/10**9),
            native=native,watcher=watched,audits=audits,skipped=skipped,error=error,source_after_equal=source_after,
            expected_episodes=plan['expected_episodes'],actual_episodes=len(episodes),qualification=False,training_eligible=False,
            all_submitted_children_waited=True,capacity_qualified=False,automatic_policy_entry_allowed=False)
        result['diagnostic_passed']=bool(native and native['passed'] and watched['passed'] and not skipped and not error
            and source_after and len(episodes)==plan['expected_episodes'] and audits and all(a['passed'] for a in audits.values()))
        if plan['arm']=='capacity':
            result['fits_existing_pilot_wall_budget']=Decimal(result['parent_wall_seconds'])<=PILOT_REMAINING
            result['optimistic_sampling_cost_only_no_policy_compute']=True
        dump(out/'summary.json',result)
        print(json.dumps({k:result[k] for k in ('arm','diagnostic_passed','parent_wall_seconds','skipped','error')}),flush=True)
        return result


def execute(freeze):
    start=time.monotonic_ns()
    require(not OUT.exists(),'decisive experiment already attempted')
    OUT.mkdir()
    owner=identity(os.getpid());ancestors=[];pid=owner['parent']
    while pid>0 and len(ancestors)<16:
        row=identity(pid)
        if row is None:break
        ancestors.append(row);pid=row['parent']
    dump(OUT/'bootstrap.json',dict(started_monotonic_ns=start,owner=owner,ancestors=ancestors,freeze=freeze))
    results=[];error=None
    try:
        for arm in ('feasibility','capacity'):
            # Keep the other arm independent, but do not start on missing source,
            # custody/cleanup or insufficient complete remaining reservation.
            if time.monotonic_ns()+12000*10**9>start+RESERVATION*10**9:
                error='insufficient remaining complete arm reservation';break
            result=run_arm(A/(arm+'.json'),freeze,start+RESERVATION*10**9)
            results.append(result)
            if not result['source_after_equal'] or result['error'] or not result['watcher']['passed']:
                error='source/custody/entry failure prevents next native arm';break
            if not result['audits'].get('closure',{}).get('passed'):
                error='closure not proved; next native arm not admitted';break
    except Exception as failure:error=repr(failure)
    end=time.monotonic_ns()
    result=dict(schema='mr3-p2a-decisive-experiments-v1',freeze=freeze,owner=owner,
        started_monotonic_ns=start,ended_monotonic_ns=end,
        engineering_added_seconds=str(Decimal(end-start)/10**9),reservation_seconds=RESERVATION,
        arms=results,error=error,qualification=False,training_eligible=False,P2A_complete=False,
        optimizer_updates=0,policy_calls=0,all_submitted_children_waited=True)
    dump(OUT/'summary.json',result)
    print(json.dumps(dict(event='complete',error=error,engineering_seconds=result['engineering_added_seconds'])),flush=True)
    return 0 if error is None and len(results)==2 else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('prepare','check','run'))
    parser.add_argument('--freeze');parser.add_argument('--plan',type=Path)
    args=parser.parse_args()
    if args.operation=='prepare':prepare();return 0
    if args.operation=='check':check(args.plan,args.freeze);print('source/build/profile entry PASS');return 0
    return execute(args.freeze)


if __name__=='__main__':
    raise SystemExit(main())
