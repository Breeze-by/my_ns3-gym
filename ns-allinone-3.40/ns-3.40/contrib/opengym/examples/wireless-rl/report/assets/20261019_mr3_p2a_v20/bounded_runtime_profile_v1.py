#!/usr/bin/python3
"""One engineering-charged, cooperative-alarm profile of the frozen reader.

The original V19 failure is not reclassified. This invokes the unmodified
audit_episode once for performance diagnosis, never for new qualification.
SIGALRM is cooperative in CPython: handler delivery can follow the requested
deadline. Both that delay and the complete actual child wall time are retained.
"""
import argparse
import cProfile
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
import marshal
import os
from pathlib import Path
import pstats
import signal
import stat
import subprocess
import sys
import time


ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
ROS = ROOT/'ros2_ws/ros2-multi-robot-automap'
EPISODE = ROS/'log/mr3_p2a_reach_v19/mr3_p2a_reach_v19_interface/worker0/episode001_open_101'
READER = W/'mr3_learning/audit_reach_runtime.py'
FREEZE = '3631c788ca46e03a52f34ad48c41611761c17f1e'
READER_SHA = '62f4a7e010e1b339eb7bbe7754c56e71baea46dc084b3792d44ec3f1e7ae89d8'
SCHEMA = 'mr3-v20-original-runtime-bounded-profile-v1'
ROBOTS = ('tb1','tb2','tb3')
ARTIFACTS = ('metadata.json','transitions.jsonl',
    *('drive_'+name+'.jsonl' for name in ROBOTS),
    *('odometry_'+name+'.jsonl' for name in ROBOTS),
    'motion_safety.jsonl','physics.jsonl','drive_phase_worker.jsonl',
    'control_phase_worker.jsonl','information_states.jsonl')
sys.dont_write_bytecode = True


class DiagnosticTimeout(BaseException):
    """Cannot be swallowed by an original reader's except Exception."""


def require(value,message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def parse(raw):
    def unique(items):
        value = {}
        for key,item in items:
            require(key not in value,'duplicate JSON member: '+key)
            value[key] = item
        return value
    return json.loads(raw,object_pairs_hook=unique,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite JSON: '+value)))


def stat_identity(value):
    return [value.st_dev,value.st_ino,value.st_size,value.st_mtime_ns,value.st_ctime_ns,
            stat.S_IMODE(value.st_mode)]


def fingerprint(path):
    path = Path(path)
    fd = os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    with os.fdopen(fd,'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode),'input is not a regular file: '+str(path))
        digest,size = hashlib.sha256(),0
        for block in iter(lambda:stream.read(1024*1024),b''):
            digest.update(block);size += len(block)
        require(stat_identity(before) == stat_identity(os.fstat(stream.fileno()))
                == stat_identity(path.lstat()) and size == before.st_size,
                'input changed while hashing: '+str(path))
    return {'path':str(path),'sha256':digest.hexdigest(),'bytes':size,'stat':stat_identity(before)}


def write_json(path,value):
    with path.open('x',encoding='utf-8') as stream:
        json.dump(value,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')


def true_argv():
    raw = Path('/proc/self/cmdline').read_bytes()
    require(raw.endswith(b'\0') and raw[:-1],'actual argv missing')
    values = raw[:-1].split(b'\0');require(all(values),'empty actual argv argument')
    return [os.fsdecode(value) for value in values]


def identity():
    data = Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return {'pid':os.getpid(),'parent':int(data[1]),'start_ticks':int(data[19])}


def load_reader(path):
    relative = str(path.relative_to(ROOT))
    argv = ['git','show',FREEZE+':'+relative]
    child = subprocess.run(argv,cwd=ROOT,capture_output=True,check=False)
    raw = path.read_bytes()
    require(child.returncode == 0 and child.stdout == raw and sha(raw) == READER_SHA,
            'reader differs from original exact V19 Git blob')
    specification = importlib.util.spec_from_file_location('mr3_v20_frozen_runtime_profile',path)
    require(specification is not None and specification.loader is not None,'reader loader unavailable')
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    require(module.CONTRACT == 'mr3-reach-v1' and tuple(module.ROBOTS) == ROBOTS
            and callable(module.audit_episode),'original reader interface differs')
    return module,{'freeze':FREEZE,'git_source':FREEZE+':'+relative,'sha256':sha(raw),
                   'actual_argv':argv,'actual_waited':True,'returncode':child.returncode}


def profile_outputs(output,profiler):
    profiler.create_stats()
    path = output/'original_audit_partial.prof'
    with path.open('xb') as stream:marshal.dump(profiler.stats,stream)
    result = {'profile':fingerprint(path),'top40':{},'ranked_functions':{}}
    for order,index in (('cumulative',3),('tottime',2)):
        text = io.StringIO()
        statistics = pstats.Stats(profiler,stream=text)
        statistics.strip_dirs().sort_stats(order).print_stats(40)
        path = output/('original_audit_partial.'+order+'.txt')
        with path.open('x',encoding='utf-8') as stream:stream.write(text.getvalue())
        result['top40'][order] = fingerprint(path)
        result['ranked_functions'][order] = [
            {'file':key[0],'line':key[1],'function':key[2],'primitive_calls':value[0],
             'calls':value[1],'tottime_seconds':value[2],'cumtime_seconds':value[3]}
            for key,value in sorted(profiler.stats.items(),key=lambda item:item[1][index],reverse=True)[:20]]
    result['total_calls'] = sum(value[1] for value in profiler.stats.values())
    result['primitive_calls'] = sum(value[0] for value in profiler.stats.values())
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode',type=Path,required=True)
    parser.add_argument('--reader-source',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=int,choices=(120,),required=True)
    args = parser.parse_args(argv)
    require(args.episode == EPISODE and args.reader_source == READER,'diagnostic input scope differs')
    require(args.output_dir.is_absolute() and args.output_dir.is_relative_to(Path('/tmp'))
            and not args.output_dir.exists() and not args.output_dir.is_symlink(),
            'output must be a new absolute directory in /tmp')
    require(os.environ.get('PYTHONPATH') is None and os.environ.get('PYTHONNOUSERSITE') == '1'
            and os.environ.get('PYTHONDONTWRITEBYTECODE') == '1'
            and os.environ.get('CUDA_VISIBLE_DEVICES') == '', 'explicit CPU environment differs')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0),'process already has an alarm')
    started = time.monotonic_ns();output = args.output_dir;output.mkdir(mode=0o755)
    result = {'schema':SCHEMA,'scope':'engineering_charged_readonly_performance_diagnostic_only',
        'diagnostic_completed':False,'original_audit_invoked':False,'original_audit_completed':False,
        'timed_out':False,'scientific_pass_claimed':False,'native_admission':False,
        'qualification_passed':False,'original_v19_failure_retained':True,'native_runs':0,'gpu_calls':0,
        'actual_argv':true_argv(),'identity':identity(),'started_monotonic_ns':started,
        'alarm_seconds':args.seconds,'timeout_semantics':'CPython cooperative SIGALRM, not a hard wall guarantee',
        'errors':[]}
    sources,inputs = {},{}
    profiler = cProfile.Profile()
    try:
        for path in (Path(__file__).resolve(),READER,EPISODE/'metadata.json'):
            sources[str(path)] = fingerprint(path)
        metadata = parse((EPISODE/'metadata.json').read_bytes())
        require(metadata['freeze'] == FREEZE and metadata['safety_contract'] == 'mr3-reach-v1'
                and type(metadata['epoch']) is str and metadata['epoch'],'original episode identity differs')
        result.update(freeze=FREEZE,epoch=metadata['epoch'])
        for name in ARTIFACTS:
            path = EPISODE/name
            if not path.exists():path = Path(str(path)+'.gz')
            inputs[name] = fingerprint(path)
        result.update(sources_before=sources,inputs_before=inputs)
        module,result['reader_source_proof'] = load_reader(READER)
        write_json(output/'intent.json',result)

        def expired(signum,frame):
            delivered = time.monotonic_ns()
            result.update(alarm_delivered_monotonic_ns=delivered,
                          alarm_delivery_delay_ns=delivered-result['planned_alarm_monotonic_ns'])
            raise DiagnosticTimeout('original audit exceeded requested cooperative alarm')

        previous_handler = signal.signal(signal.SIGALRM,expired)
        result['audit_started_monotonic_ns'] = time.monotonic_ns()
        result['alarm_arm_before_monotonic_ns'] = time.monotonic_ns()
        result['planned_alarm_monotonic_ns'] = result['alarm_arm_before_monotonic_ns']+args.seconds*10**9
        signal.setitimer(signal.ITIMER_REAL,float(args.seconds))
        result['alarm_arm_return_monotonic_ns'] = time.monotonic_ns()
        try:
            result['original_audit_invoked'] = True
            original = profiler.runcall(module.audit_episode,EPISODE,FREEZE)
            result['original_audit_completed'] = True
        except DiagnosticTimeout:
            result['timed_out'] = True
        finally:
            profiler.disable()
            signal.setitimer(signal.ITIMER_REAL,0.0)
            signal.signal(signal.SIGALRM,previous_handler)
            result['audit_ended_monotonic_ns'] = time.monotonic_ns()
        if result['original_audit_completed']:
            write_json(output/'original_audit_returned_result.json',original)
            result['original_result_artifact'] = fingerprint(output/'original_audit_returned_result.json')
        result['profile_outputs'] = profile_outputs(output,profiler)
        result['sources_after'] = {name:fingerprint(Path(name)) for name in sources}
        result['inputs_after'] = {name:fingerprint(Path(row['path'])) for name,row in inputs.items()}
        require(result['sources_after'] == sources and result['inputs_after'] == inputs,
                'original source or input changed during diagnostic')
        result.update(source_unchanged=True,inputs_unchanged=True,diagnostic_completed=True)
    except BaseException as error:
        profiler.disable();signal.setitimer(signal.ITIMER_REAL,0.0)
        result['errors'].append({'type':type(error).__name__,'message':str(error)})
        result['partial_outputs_preserved'] = True
        if 'profile_outputs' not in result:
            try:result['profile_outputs'] = profile_outputs(output,profiler)
            except BaseException as profile_error:
                result['errors'].append({'type':type(profile_error).__name__,'message':str(profile_error)})
    result['ended_monotonic_ns'] = time.monotonic_ns()
    result['actual_total_wall_seconds'] = str(Decimal(result['ended_monotonic_ns']-started)/10**9)
    if 'audit_ended_monotonic_ns' in result:
        result['actual_audit_wall_seconds'] = str(Decimal(result['audit_ended_monotonic_ns']
            -result['audit_started_monotonic_ns'])/10**9)
    write_json(output/'result.json',result)
    print(json.dumps({'schema':SCHEMA,'diagnostic_completed':result['diagnostic_completed'],
        'original_audit_completed':result['original_audit_completed'],'timed_out':result['timed_out'],
        'scientific_pass_claimed':False,'errors':result['errors'],'result':str(output/'result.json')}))
    return 0 if result['diagnostic_completed'] and not result['errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
