"""One opt-in startup sensor collection; draft guard forbids native admission."""
import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import threading
import time

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v20_sensor'
OLD_A=W/'report/assets/20261018_mr3_p2a0_v19'
PREFIX=Path('/tmp/mr3_p2a0_v20_sensor')


def require(value,message):
    if not value:raise ValueError(message)


def sha(raw):return hashlib.sha256(raw).hexdigest()


def read(path):
    raw=Path(path).read_bytes()
    return json.loads(raw),{'path':str(path),'sha256':sha(raw)}


def dump(path,value,mode='x'):
    with Path(path).open(mode) as stream:
        stream.write(json.dumps(value,indent=2,allow_nan=False)+'\n')


def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def transport_environment(base,transport,system=False):
    environment=dict(base)
    if system:
        removed={'PYTHONPATH','LD_LIBRARY_PATH','AMENT_PREFIX_PATH','CMAKE_PREFIX_PATH',
                 'COLCON_PREFIX_PATH','ROS_PACKAGE_PATH','PYTHONHOME','VIRTUAL_ENV',
                 'GAZEBO_PLUGIN_PATH','GAZEBO_MODEL_PATH','GAZEBO_RESOURCE_PATH'}
        environment={key:value for key,value in environment.items()
                     if key not in removed and not key.startswith('CONDA')}
        environment['PATH']='/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'
    environment.pop('PYTHONPATH',None)
    environment.pop('MR3_PHYSICS_DIAGNOSTIC_CONFIG_FILE',None)
    environment.update(PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
                       ROS_DOMAIN_ID='170',GAZEBO_MASTER_URI='http://127.0.0.1:13451',TURTLEBOT3_MODEL='waffle')
    for key,value in transport.items():
        if key=='profile_sha256':continue
        if value is None:environment.pop(key,None)
        else:environment[key]=value
    return environment


def wait_ready(child,path,configuration,expected_source_sha,timeout):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if child.poll() is not None:
            raise RuntimeError('recorder exited before ready')
        if path.exists():
            raw=path.read_bytes()
            # A known exclusive creator may still be filling its first JSON.
            if not raw.endswith(b'\n'):
                time.sleep(.05)
                continue
            try:
                value=json.loads(raw)
            except json.JSONDecodeError as error:
                if error.pos >= len(raw.rstrip()) or error.msg.startswith('Unterminated'):
                    time.sleep(.05)
                    continue
                raise
            require(value.get('schema')=='mr3-startup-sensor-recorder-ready-v1'
                    and value.get('ready') is True,'invalid recorder ready receipt')
            for key in ('run_directory','output_directory','expected_freeze','stop_marker'):
                require(value.get(key)==configuration[key],'recorder ready identity differs:'+key)
            require(value.get('config_sha256')==sha(json.dumps(configuration,indent=2).encode()+b'\n'),
                    'recorder did not read exact runtime config')
            require(value.get('compiled_source_sha256')==expected_source_sha,'recorder compiled source differs')
            require(type(value.get('process_id')) is int and value['process_id']==child.pid,
                    'recorder ready PID differs from owned child')
            require(type(value.get('subscriptions')) is list and len(value['subscriptions'])==22,
                    'recorder ready subscriptions differ')
            return value,{'path':str(path),'sha256':sha(raw)}
        time.sleep(.05)
    raise RuntimeError('recorder ready wall guard expired')


def run_child(command,environment,console,cwd):
    with console.open('x') as output:
        child=subprocess.Popen(command,cwd=cwd,env=environment,stdout=output,stderr=subprocess.STDOUT)
    return child


def verify_profile_subset(proof_path):
    """Only immutable e61c first-boundary predicate; never its32-step CLI."""
    proof,proof_ref=read(proof_path)
    helper_path=W/'report/assets/20261018_mr3_p2a0_v18/independent/mr3_independent_stop_observer_v1.py'
    require(sha(helper_path.read_bytes())=='e61ce4e00907ab35e196f7abe9fadfd9da099af3542f98dc773d593c33ca2b65',
            'immutable e61c profile helper changed')
    helper=load(helper_path,'sensor_profile_subset')
    inputs={}
    ledger=helper.profile_record(proof['profile']['ledger_path'],inputs,proof['profile']['ledger_sha256'])
    binding_path=Path(proof['runtime_binding']['path']);raw=binding_path.read_bytes()
    require(sha(raw)==proof['runtime_binding']['sha256'],'actual runtime binding changed')
    before,after=helper.validate_profile(ledger,proof,raw,json.loads(raw))
    require(ledger['mode']=='iters150','sensor collection requires actual isolated150 profile')
    return {'passed':True,'helper_path':str(helper_path),'helper_sha256':sha(helper_path.read_bytes()),
            'functions':['profile_record','validate_profile'],'admission_proof':proof_ref,
            'ledger_inputs':inputs,'runtime_binding':proof['runtime_binding'],
            'clock_ns':ledger['sim_time_ns'],'world_iterations':ledger['world_iterations'],
            'setter_call_count':ledger['setter_call_count'],'before':before,'after':after,
            'scope':'Existing first-boundary native/cached50to150, setter1 and other-field invariants only; not e61c CLI/1ms coverage/32step physical or matrix credit.'}


def verify_actual_workload(summary,metadata,path,returncode):
    """Preserve ordinary benchmark verdict, accepting genuine protocol end as data."""
    require(summary.get('freeze')==metadata['freeze'] and summary['workers']==1
            and summary['steps_per_episode']==4, 'actual ordinary workload differs')
    require(summary.get('preparation_motion_probe') is False
            and summary.get('preparation_parameter_review') is False,'ordinary benchmark gained preparation flags')
    workers=summary['workers_results']
    require(len(workers)==1 and workers[0].get('error') is None,'worker infrastructure failure')
    episodes=workers[0]['episodes']
    require(len(episodes)==1 and episodes[0]['epoch']==metadata['epoch'],'actual episode identity differs')
    require(Path(path).stat().st_size<=10485760,'unexpectedly large four-step protocol ledger')
    raw=Path(path).read_bytes()
    require(len(raw)<=10485760,'unexpectedly large four-step protocol ledger')
    rows=[json.loads(line) for line in raw.splitlines()]
    require(rows and rows[0]['kind']=='reset' and sum(row['kind']=='reset' for row in rows)==1,
            'one actual reset record required')
    steps=rows[1:]
    require(all(row['kind']=='step' for row in steps) and len(steps)<=4,'actual step ceiling exceeded')
    for row in rows:
        require(type(row['terminated']) is bool and type(row['truncated']) is bool,
                'actual protocol termination flags must be booleans')
        require(row['info']['epoch']==metadata['epoch'],'protocol epoch differs')
    require(type(summary['valid_transitions']) is int and type(episodes[0]['transitions']) is int
            and summary['valid_transitions']==episodes[0]['transitions']==len(steps),
            'summary and returned protocol step counts differ')
    last=steps[-1] if steps else rows[0]
    ended=last['terminated'] or last['truncated']
    if ended:
        require(episodes[0].get('terminated') is last['terminated']
                and episodes[0].get('truncated') is last['truncated']
                and episodes[0].get('reason')==last['info'].get('reason'),
                'terminal summary does not bind actual final protocol row')
    require(ended or len(steps)==4,'short workload without actual protocol termination')
    require((returncode==0 and summary.get('passed') is True)
            or (returncode==1 and summary.get('passed') is False and ended),
            'ordinary benchmark failure is not an actual protocol terminal outcome')
    return {'requested_steps':4,'actual_returned_resets':1,'actual_returned_steps':len(steps),
            'actual_saved_api_records':len(rows),'original_benchmark_passed':summary['passed'],
            'original_benchmark_returncode':returncode,'actual_protocol_ended':ended,
            'last_terminated':last['terminated'],'last_truncated':last['truncated'],
            'last_reason':last['info'].get('reason'),'protocol':{'path':str(path),'sha256':sha(raw)},
            'scope':'Actual typed RPC outcome retained; early real task end is not relabeled benchmark/task success.'}


def execute_capture(plan,freeze,plan_path,preflight_proof,unchanged,live,prefix=PREFIX,cwd=W):
    """Finite owned children only; no signal/retry or fabricated physical PASS."""
    stage=plan['stages'][0];contract=plan['recorder_contract']
    record={'schema':'mr3-startup-sensor-execution-v1','freeze':freeze,
            'plan_sha256':sha(plan_path.read_bytes()),'source_preflight':preflight_proof,
            'stage':'iters150','status':'reserved','start_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'scope':'Capture process closure only; no32step/e61c/V6/matrix/physical-repair/PPO/150-selection credit.',
            'e61c':plan['e61c_consumer'],'errors':[],'parent_identity':live.identity(os.getpid())}
    receipt=Path(str(prefix)+'_execution_v1.json')
    dump(receipt,record)
    ledger_path=Path(str(prefix)+'_lifecycle_v1.jsonl')
    ledger=ledger_path.open('x')
    event_lock=threading.Lock()
    def event(kind,**fields):
        with event_lock:
            ledger.write(json.dumps({'kind':kind,'wall_monotonic_ns':time.monotonic_ns(),
                                      'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),**fields})+'\n');ledger.flush()
    recorder=benchmark=None;benchmark_code=None;recorder_code=None
    witness_thread=None;watch_stop=threading.Event();watch={'proof':None,'errors':[]}
    native_started=None
    config,_=read(ROOT/contract['config_template_binding']['path'])
    require(config['expected_freeze']=='{freeze}','runtime config template must contain only frozen placeholder')
    config['expected_freeze']=freeze
    config_path=Path(contract['config_runtime_path'])
    dump(config_path,config)
    bench_env=transport_environment(os.environ,plan['transport'])
    recorder_env=transport_environment(os.environ,plan['transport'],system=True)
    recorder_console=Path(str(prefix)+'_recorder_console_v1.log')
    benchmark_console=Path(str(prefix)+'_benchmark_console_v1.log')
    recorder_argv=[part.replace('{config}',str(config_path)) for part in contract['command']]
    record.update(recorder_argv=recorder_argv,benchmark_argv=stage['command'],
                  recorder_environment_selected={key:recorder_env.get(key) for key in plan['transport'] if key!='profile_sha256'},
                  recorder_config={'path':str(config_path),'sha256':sha(config_path.read_bytes())})
    try:
        unchanged()
        recorder=run_child(recorder_argv,recorder_env,recorder_console,cwd)
        record['recorder_identity']=live.identity(recorder.pid)
        event('recorder_started',identity=record['recorder_identity'],argv=recorder_argv)
        ready,proof=wait_ready(recorder,Path(config['ready_path']),config,
                               contract['source_sha256'],contract['ready_wait_wall_seconds'])
        record['recorder_ready']=proof
        event('recorder_ready_received',proof=proof,actual_ready=ready)
        unchanged()
        native_started=time.monotonic()
        benchmark=run_child(stage['command'],bench_env,benchmark_console,cwd)
        identity=live.identity(benchmark.pid)
        require(identity is not None,'benchmark identity unavailable')
        record.update(status='native_running',benchmark_identity=identity)
        dump(receipt,record,'w')
        event('benchmark_started_after_recorder_ready',identity=identity,argv=stage['command'])
        def observe():
            while not watch_stop.is_set():
                try:
                    path,proof=live.witness(plan_path,'iters150',freeze,identity,
                                            Path(str(prefix)+'_live_witness'))
                    watch['proof']={'path':str(path),'sha256':sha(Path(path).read_bytes())}
                    event('actual_loaded_libraries_bound',proof=watch['proof'])
                    return
                except FileNotFoundError:
                    watch_stop.wait(1.)
                except BaseException as error:
                    watch['errors'].append(repr(error));return
        witness_thread=threading.Thread(target=observe,name='readonly-sensor-live-witness')
        witness_thread.start()
        benchmark_code=benchmark.wait()
        record['native_wall_seconds']=time.monotonic()-native_started
        event('benchmark_naturally_closed',returncode=benchmark_code,native_wall_seconds=record['native_wall_seconds'])
    except BaseException as error:
        record['errors'].append(repr(error))
    finally:
        if benchmark is not None and benchmark_code is None:
            # Reap exact finite child, without sending a signal or replacement request.
            benchmark_code=benchmark.wait()
            record['native_wall_seconds']=time.monotonic()-native_started
            event('benchmark_reaped_after_parent_error',returncode=benchmark_code)
        watch_stop.set()
        if witness_thread is not None:witness_thread.join()
        if benchmark is not None and benchmark_code is not None:
            marker={'schema':'mr3-startup-sensor-recorder-stop-v1',
                    'run_directory':config['run_directory'],'freeze':freeze,'reason':'benchmark_closed'}
            try:
                dump(config['stop_marker'],marker)
                record['recorder_stop_marker']={'path':config['stop_marker'],'sha256':sha(Path(config['stop_marker']).read_bytes())}
                event('exclusive_stop_marker_after_benchmark_closed',marker=record['recorder_stop_marker'])
            except BaseException as error:record['errors'].append(repr(error))
        # If parent failed before benchmark launch, do not manufacture a closed
        # benchmark marker: recorder must terminate by its own finite wallguard.
        if recorder is not None:
            recorder_code=recorder.wait()
            event('recorder_naturally_closed',returncode=recorder_code)
    record.update(benchmark_returncode=benchmark_code,recorder_returncode=recorder_code,live_witness=watch)
    try:
        require(benchmark is not None and benchmark_code is not None,'ordinary benchmark never started')
        require(record['native_wall_seconds']<=900.,'actual native wall exceeds900; no retry/kill')
        summary,proof=read(Path(stage['run_directory'])/'benchmark_summary.json')
        record['benchmark_summary']=proof
        episode=Path(stage['run_directory'])/'worker0/episode001_open_101'
        metadata,_=read(episode/'metadata.json')
        require(metadata['freeze']==freeze,'actual episode source freeze differs')
        record['actual_workload']=verify_actual_workload(summary,metadata,episode/'transitions.jsonl',benchmark_code)
        require(watch['proof'] is not None and not watch['errors'],'live native load identity missing/failed')
        record['actual_profile_subset']=verify_profile_subset(watch['proof']['path'])
        require(recorder_code==0,'recorder failed/wallguard exit')
        final,proof=read(contract['manifest_path'])
        record['recorder_final']=proof
        metadata,_=read(Path(stage['run_directory'])/'worker0/episode001_open_101/metadata.json')
        require(metadata['freeze']==freeze and final['epoch']==metadata['epoch'], 'recorder final actual epoch/freeze differs')
        require(final.get('source_sha256')==contract['source_sha256'],'recorder final source differs')
        require(final.get('schema')=='mr3-startup-sensor-recorder-final-v1'
                and final.get('capture_completed') is True and final.get('normal_stop') is True
                and final.get('failed') is False,'recorder final process completion/identity/write failed')
        record['measurement_availability']={key:final.get(key) for key in
            ('epoch','records','samples','topic_counts','parameter_states','cdr_bytes','unbound_epoch_samples')}
        # No topic alias/frame/GID availability is converted into a hidden gate.
        # Missing streams limit interpretation and are retained verbatim.
    except BaseException as error:record['errors'].append(repr(error))
    try:
        require(benchmark is not None and benchmark_code is not None,'no closed native attempt; physical consumer skipped')
        job=stage['diagnostic_consumers'][0]
        old=load(OLD_A/'independent/mr3_p2a0_v19_run_diagnostics_v1.py','old_sensor_consumer_runner')
        consumer,value=old.run_consumer(job,job['command'],bench_env,
                                        Path(str(prefix)+'_original_physical4_console_v1.log'))
        record['original_physical_4step']=consumer
        episodes=value.get('episodes',[])
        require(not consumer['errors'] and len(episodes)==1 and not episodes[0].get('error')
                and episodes[0].get('closure',{}).get('passed') is True,'original strict native closure missing/failed')
        record['original_physical_passed']=value.get('passed')
        record['strict_native_closure_passed']=True
    except BaseException as error:record['errors'].append(repr(error))
    try:unchanged()
    except BaseException as error:record['errors'].append(repr(error))
    record.update(status='completed',capture_process_completed=not record['errors'],passed=not record['errors'],
                  pass_scope='Ready/recording/normal-stop/no-write-identity-error/strict-native-close only; measurement availability separately retained.',
                  end_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    for label,path in [('recorder_console',recorder_console),('benchmark_console',benchmark_console)]:
        if path.exists():record[label]={'path':str(path),'sha256':sha(path.read_bytes())}
    event('capture_process_result',passed=record['passed'],errors=record['errors'])
    ledger.close();record['lifecycle']={'path':str(ledger_path),'sha256':sha(ledger_path.read_bytes())}
    dump(receipt,record,'w')
    return record


def main():
    parser=argparse.ArgumentParser();parser.add_argument('freeze');args=parser.parse_args()
    require(re.fullmatch('[a-f0-9]{40}',args.freeze) is not None,'actual exact40 freeze required')
    plan_path=A/'predeclared_plan_v20_sensor.json';plan,planproof=read(plan_path)
    pre=load(Path(__file__).with_name('mr3_p2a0_v20_sensor_preflight_v1.py'),'sensor_preflight')
    pre.validate_sensor_plan(plan)
    preflight,preflight_proof=read(Path('/tmp/mr3_p2a0_v20_sensor_source_preflight_v1.json'))
    require(preflight.get('passed') is True and preflight['freeze']==args.freeze
            and preflight['plan_sha256']==planproof['sha256'],'actual source preflight missing/mismatched')
    bindings=plan['independent_source_bindings']+[
        {'path':path,'sha256':value['sha256']}
        for path,value in preflight['source_bindings'].items()]
    def unchanged():
        require(subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==args.freeze==
                subprocess.check_output(['git','rev-parse','@{u}'],cwd=ROOT,text=True).strip(),'source not exact pushed HEAD')
        require(not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT),'source not clean')
        require(sha(plan_path.read_bytes())==planproof['sha256'],'plan changed')
        for row in bindings:require(sha((ROOT/row['path']).read_bytes())==row['sha256'],'frozen source changed:'+row['path'])
        binary=Path(plan['recorder_contract']['executable_path']).read_bytes()
        require(sha(binary)==plan['recorder_contract']['executable_sha256'] and len(binary)==plan['recorder_contract']['executable_bytes'],'recorder actual binary changed')
    unchanged();pre.check_unused_resources()
    with Path(str(PREFIX)+'_single_attempt.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        template,_=read(ROOT/plan['recorder_contract']['config_template_binding']['path'])
        for path in [plan['stages'][0]['run_directory'],str(PREFIX)+'_execution_v1.json',
                     plan['recorder_contract']['config_runtime_path'],template['output_directory'],template['ready_path'],template['stop_marker']]:
            require(not Path(path).exists(),'existing sole-attempt artifact; no retry or overwrite:'+str(path))
        live=load(OLD_A/'independent/mr3_p2a0_v19_live_admission_v1.py','sensor_live_witness')
        result=execute_capture(plan,args.freeze,plan_path,preflight_proof,unchanged,live)
        print(json.dumps({'passed':result['passed'],'capture_process_completed':result['capture_process_completed'],
                          'original_physical_passed':result.get('original_physical_passed'),
                          'measurement_availability':result.get('measurement_availability'),'errors':result['errors']}))
        return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
