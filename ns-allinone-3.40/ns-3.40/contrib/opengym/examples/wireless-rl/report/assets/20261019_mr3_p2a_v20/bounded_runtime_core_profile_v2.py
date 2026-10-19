#!/usr/bin/python3
"""One engineering diagnostic: profile the untouched core after its real loader.

The exact frozen audit_episode performs all its original preparation. Its
_audit_records slot is wrapped only in this process, forwarding the original
argument objects to the original callable. A cooperative 120s SIGALRM begins
at that boundary. Original V19 failure and v1 diagnostic defects are retained.
"""
import argparse
import cProfile
from decimal import Decimal
import hashlib
import inspect
import io
import json
import marshal
import os
from pathlib import Path
import pstats
import signal
import sys
import time


SUPPORT = Path(__file__).resolve().with_name('bounded_runtime_profile_v1.py')
SUPPORT_SHA = 'c6c1ad5de215fc480498b6ca7376517c389bfb8d351b69ac8b5358ad7c7fcd5b'
SCHEMA = 'mr3-v20-original-runtime-core-bounded-profile-v2'
sys.dont_write_bytecode = True


def require(value,message):
    if not value:
        raise ValueError(message)


def load_support():
    raw = SUPPORT.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SUPPORT_SHA,'immutable v1 diagnostic support changed')
    namespace = {'__file__':str(SUPPORT),'__name__':'mr3_v20_locked_profile_support'}
    exec(compile(raw,str(SUPPORT),'exec'),namespace)
    return namespace


def code_binding(function):
    return {'name':function.__name__,'qualified_name':function.__qualname__,
            'file':function.__code__.co_filename,'first_line':function.__code__.co_firstlineno,
            'marshal_code_sha256':hashlib.sha256(marshal.dumps(function.__code__)).hexdigest(),
            'source_sha256':hashlib.sha256(inspect.getsource(function).encode()).hexdigest(),
            'signature':str(inspect.signature(function))}


def profile_outputs(output,profiler,fingerprint):
    # Capture before pstats: Stats(profiler) clears the profiler.stats attribute.
    profiler.create_stats()
    snapshot = dict(profiler.stats)
    path = output/'original_core_partial.prof'
    with path.open('xb') as stream:marshal.dump(snapshot,stream)
    result = {'profile':fingerprint(path),'top40':{},'ranked_functions':{},
              'total_calls':sum(row[1] for row in snapshot.values()),
              'primitive_calls':sum(row[0] for row in snapshot.values()),
              'total_profiled_tottime_seconds':sum(row[2] for row in snapshot.values()),
              'function_entries':len(snapshot)}
    for order,index in (('cumulative',3),('tottime',2)):
        text = io.StringIO()
        pstats.Stats(str(path),stream=text).strip_dirs().sort_stats(order).print_stats(40)
        text_path = output/('original_core_partial.'+order+'.txt')
        with text_path.open('x',encoding='utf-8') as stream:stream.write(text.getvalue())
        result['top40'][order] = fingerprint(text_path)
        result['ranked_functions'][order] = [
            {'file':key[0],'line':key[1],'function':key[2],'primitive_calls':row[0],
             'calls':row[1],'tottime_seconds':row[2],'cumtime_seconds':row[3]}
            for key,row in sorted(snapshot.items(),key=lambda item:item[1][index],reverse=True)[:20]]
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--episode',type=Path,required=True)
    parser.add_argument('--reader-source',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    parser.add_argument('--seconds',type=int,choices=(120,),required=True)
    args = parser.parse_args(argv)
    support = load_support()
    ROOT,EPISODE,READER,FREEZE = (support[key] for key in ('ROOT','EPISODE','READER','FREEZE'))
    fingerprint,write_json = support['fingerprint'],support['write_json']
    DiagnosticTimeout = support['DiagnosticTimeout']
    require(args.episode == EPISODE and args.reader_source == READER,'original V19 input scope differs')
    require(args.output_dir.is_absolute() and args.output_dir.is_relative_to(Path('/tmp'))
            and not args.output_dir.exists() and not args.output_dir.is_symlink(),
            'output must be a new absolute /tmp directory')
    require(os.environ.get('PYTHONPATH') is None and os.environ.get('PYTHONNOUSERSITE') == '1'
            and os.environ.get('PYTHONDONTWRITEBYTECODE') == '1'
            and os.environ.get('CUDA_VISIBLE_DEVICES') == '', 'explicit CPU environment differs')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0,0.0),'process already has an alarm')
    started = time.monotonic_ns();output = args.output_dir;output.mkdir(mode=0o755)
    result = {'schema':SCHEMA,'scope':'engineering_charged_original_core_performance_diagnostic_only',
        'diagnostic_completed':False,'original_audit_invoked':False,'original_audit_completed':False,
        'original_core_completed':False,'core_call_count':0,'timed_out':False,
        'scientific_pass_claimed':False,'native_admission':False,'qualification_passed':False,
        'original_v19_failure_retained':True,'v1_timeout_and_report_defect_retained':True,
        'native_runs':0,'gpu_calls':0,'actual_argv':support['true_argv'](),
        'identity':support['identity'](),'started_monotonic_ns':started,
        'alarm_seconds':args.seconds,'timeout_semantics':'CPython cooperative SIGALRM, not a hard wall guarantee',
        'original_loader_and_prechecks_skipped':False,'errors':[]}
    sources,inputs = {},{}
    profiler = cProfile.Profile()
    module = original_core = None
    try:
        for path in (Path(__file__).resolve(),SUPPORT,READER,EPISODE/'metadata.json'):
            sources[str(path)] = fingerprint(path)
        require(sources[str(SUPPORT)]['sha256'] == SUPPORT_SHA,'v1 support changed after byte-bound load')
        metadata = support['parse']((EPISODE/'metadata.json').read_bytes())
        require(metadata['freeze'] == FREEZE and metadata['safety_contract'] == 'mr3-reach-v1',
                'original episode identity differs')
        result.update(freeze=FREEZE,epoch=metadata['epoch'])
        for name in support['ARTIFACTS']:
            path = EPISODE/name
            if not path.exists():path = Path(str(path)+'.gz')
            inputs[name] = fingerprint(path)
        module,result['reader_source_proof'] = support['load_reader'](READER)
        original_core = module._audit_records
        result.update(sources_before=sources,inputs_before=inputs,
                      original_core_before=code_binding(original_core),
                      original_audit_before=code_binding(module.audit_episode))
        callable_ids = {name:id(value) for name,value in vars(module).items() if callable(value)}
        write_json(output/'intent.json',result)

        def wrapped_core(*args,**kwargs):
            result['core_call_count'] += 1
            require(result['core_call_count'] == 1,'original core was invoked more than once')
            require(module._audit_records is wrapped_core,'core wrapper slot changed')
            result['core_entered_monotonic_ns'] = time.monotonic_ns()
            result['forwarded_argument_identity'] = {
                'positional':[{'id':id(value),'type':type(value).__name__} for value in args],
                'keyword':{key:{'id':id(value),'type':type(value).__name__} for key,value in kwargs.items()}}

            def expired(signum,frame):
                delivered = time.monotonic_ns()
                result.update(alarm_delivered_monotonic_ns=delivered,
                    alarm_delivery_delay_ns=delivered-result['planned_alarm_monotonic_ns'])
                raise DiagnosticTimeout('original core exceeded requested cooperative alarm')

            old_handler = signal.signal(signal.SIGALRM,expired)
            result['alarm_arm_before_monotonic_ns'] = time.monotonic_ns()
            result['planned_alarm_monotonic_ns'] = result['alarm_arm_before_monotonic_ns']+args_seconds*10**9
            signal.setitimer(signal.ITIMER_REAL,float(args_seconds))
            result['alarm_arm_return_monotonic_ns'] = time.monotonic_ns()
            write_json(output/'core_entered.json',{
                'identity':result['identity'],'core_entered_monotonic_ns':result['core_entered_monotonic_ns'],
                'planned_alarm_monotonic_ns':result['planned_alarm_monotonic_ns'],
                'original_core':result['original_core_before'],
                'in_memory_only':True,'arguments_forwarded_without_copy_or_reconstruction':True})
            result['core_profile_started_monotonic_ns'] = time.monotonic_ns()
            try:
                original = profiler.runcall(original_core,*args,**kwargs)
                result['original_core_completed'] = True
                return original
            except DiagnosticTimeout:
                result['timed_out'] = True
                raise
            finally:
                profiler.disable();signal.setitimer(signal.ITIMER_REAL,0.0)
                signal.signal(signal.SIGALRM,old_handler)
                result['core_ended_monotonic_ns'] = time.monotonic_ns()
                module._audit_records = original_core

        args_seconds = args.seconds
        result['wrapper_code'] = code_binding(wrapped_core)
        module._audit_records = wrapped_core
        result['original_audit_started_monotonic_ns'] = time.monotonic_ns()
        try:
            result['original_audit_invoked'] = True
            original = module.audit_episode(EPISODE,FREEZE)
            result['original_audit_completed'] = True
        except DiagnosticTimeout:
            require(result['timed_out'] is True,'timeout did not originate at original core boundary')
        finally:
            profiler.disable();signal.setitimer(signal.ITIMER_REAL,0.0)
            module._audit_records = original_core
            result['original_audit_ended_monotonic_ns'] = time.monotonic_ns()
        require(result['core_call_count'] == 1,'original audit did not reach exactly one original core call')
        result['original_core_after'] = code_binding(original_core)
        result['original_audit_after'] = code_binding(module.audit_episode)
        require(result['original_core_after'] == result['original_core_before']
                and result['original_audit_after'] == result['original_audit_before']
                and callable_ids == {name:id(value) for name,value in vars(module).items() if callable(value)},
                'original reader callable identity/code was changed')
        result['wrapper_scope_proof'] = {
            'only_replaced_symbol':'_audit_records','restored_original_identity':module._audit_records is original_core,
            'original_callable_code_unchanged':True,'other_original_callable_identities_unchanged':True,
            'forwarding_expression':'profiler.runcall(original_core, *args, **kwargs)',
            'in_memory_only':True,'source_file_modified':False,'checks_skipped_or_replaced':False}
        if result['original_audit_completed']:
            write_json(output/'original_audit_returned_result.json',original)
            result['original_result_artifact'] = fingerprint(output/'original_audit_returned_result.json')
        result['profile_outputs'] = profile_outputs(output,profiler,fingerprint)
        require(result['profile_outputs']['total_calls'] > 0,'original core profile is empty')
        result['sources_after'] = {name:fingerprint(Path(name)) for name in sources}
        result['inputs_after'] = {name:fingerprint(Path(row['path'])) for name,row in inputs.items()}
        require(result['sources_after'] == sources and result['inputs_after'] == inputs,
                'original source or input changed during diagnostic')
        result.update(source_unchanged=True,inputs_unchanged=True,diagnostic_completed=True)
    except BaseException as error:
        profiler.disable();signal.setitimer(signal.ITIMER_REAL,0.0)
        if module is not None and original_core is not None:module._audit_records = original_core
        result['errors'].append({'type':type(error).__name__,'message':str(error)})
        result['partial_outputs_preserved'] = True
        if 'profile_outputs' not in result:
            try:result['profile_outputs'] = profile_outputs(output,profiler,fingerprint)
            except BaseException as profile_error:
                result['errors'].append({'type':type(profile_error).__name__,'message':str(profile_error)})
    result['ended_monotonic_ns'] = time.monotonic_ns()
    result['actual_total_wall_seconds'] = str(Decimal(result['ended_monotonic_ns']-started)/10**9)
    if 'core_ended_monotonic_ns' in result:
        result['actual_core_wall_seconds'] = str(Decimal(result['core_ended_monotonic_ns']
            -result['core_profile_started_monotonic_ns'])/10**9)
    write_json(output/'result.json',result)
    print(json.dumps({'schema':SCHEMA,'diagnostic_completed':result['diagnostic_completed'],
        'original_audit_completed':result['original_audit_completed'],'timed_out':result['timed_out'],
        'scientific_pass_claimed':False,'errors':result['errors'],'result':str(output/'result.json')}))
    return 0 if result['diagnostic_completed'] and not result['errors'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
