#!/usr/bin/python3
"""Fixed contract-age artificial comparisons; no old tests/World/raw inputs.

This v2 only addresses the v1 timing angle-domain limitation. Each side loads
its own frozen baseline/candidate. Production and reader never share math.
"""
import argparse
import cProfile
from fractions import Fraction as Q
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import pstats
import time


ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261022_mr3_p2a_v48_support_cpu'
AGES = tuple(i*500_000_000//63 for i in range(64))
PHIS = tuple(Q(6, 5)*(Q(39, 50)+Q(age, 10**9)) for age in AGES)


def canonical(value):
    if type(value) is Q:
        return {'numerator_hex':format(value.numerator, 'x'),
                'denominator_hex':format(value.denominator, 'x')}
    if type(value) is float:
        return {'binary64_hex':value.hex()}
    if isinstance(value, (tuple, list)):
        return [canonical(v) for v in value]
    if isinstance(value, dict):
        return {k:canonical(v) for k, v in value.items()}
    return value


def encoded(value):
    return json.dumps(canonical(value), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def proof(path):
    path = Path(path).resolve(strict=True)
    before = path.stat(); raw = path.read_bytes(); after = path.stat()
    fields = lambda s:[s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]
    if fields(before) != fields(after):
        raise ValueError('bound source/profile changed: '+str(path))
    return {'path':str(path),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
            'stat':fields(after)}


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def production_cases(g, loader):
    templates = loader.pair_cases(g)
    cases, inputs = [], []
    for i, (age, phi) in enumerate(zip(AGES, PHIS)):
        template = templates[i % 12]
        family = 'exact_rational' if i % 2 == 0 else 'binary64_float'
        # A fixed linear rotation-like map keeps signs/union structure and
        # gives noninteger axes. Float coefficients retain their exact bits.
        c, s = ((Q(3, 5),Q(4, 5)) if i % 2 == 0 else (Q.from_float(.6),Q.from_float(.8)))
        rc, rs = ((Q(5, 13),Q(12, 13)) if i % 2 == 0 else (Q.from_float(.8),Q.from_float(.6)))
        def transformed(reach):
            directions = []
            for direction in reach.directions:
                mx,my = direction.map_axis; rx,ry = direction.raw_axis
                directions.append(g.Direction((c*mx-s*my,s*mx+c*my),
                    (rc*rx-rs*ry,rs*rx+rc*ry),phi))
            return g.Reach(reach.kind,reach.buffer_m,reach.longitudinal_m,tuple(directions))
        left,right = transformed(template[4]),transformed(template[5])
        case = ('contract_age_'+str(i)+'_'+template[0],template[1],template[2],
                (age,age),left,right,template[6],template[7])
        cases.append(case)
        def reach_input(reach):
            return {'kind':reach.kind,'buffer_m':reach.buffer_m,'longitudinal_m':reach.longitudinal_m,
                'directions':[{'map_axis':d.map_axis,'raw_axis':d.raw_axis,'half_angle':d.half_angle}
                              for d in reach.directions]}
        inputs.append({'id':case[0],'age_index':i,'age_ns':age,'phi':phi,
            'template_index':i%12,'template_id':template[0],'axis_family':family,
            'map_axis_transform_coefficients':(c,s),'raw_axis_transform_coefficients':(rc,rs),
            'map_delta':case[1],'raw_delta':case[2],'ages_ns':case[3],
            'left':reach_input(left),'right':reach_input(right),
            'legacy_hard_gates_passed':case[6],'common_world_odom_calibrated':case[7],
            'angle_used_by_direction':bool(left.directions or right.directions)})
    return cases,inputs


def reader_cases():
    rows = []
    for i, (age, phi) in enumerate(zip(AGES, PHIS)):
        bearing = (-Q(9,20), -Q(9,20)) if i%4 < 2 else (-Q(9,20), Q(9,20))
        axis = (Q(3,5),Q(4,5)) if i%2 == 0 else (.6,.8)
        rows.append({'id':'contract_age_'+str(i),'age_index':i,'age_ns':age,
            'bearing':bearing,'axis':axis,'angle':phi,
            'uncertainty':Q(3,10)*Q(2*age,10**9),'length':Q(18,125)})
    return rows


def clear_production(g,module):
    g._sin_cos_bounds.cache_clear()
    if hasattr(module,'_sqrt_bounds_cached'):
        module._sqrt_bounds_cached.cache_clear()


def clear_reader(module):
    module.trig_enclosure.cache_clear()
    if hasattr(module,'_sqrt_interval_q'):
        module._sqrt_interval_q.cache_clear()


def cache_info(module,geometry=None):
    values={}
    if geometry is not None:
        values['trig']=geometry._sin_cos_bounds.cache_info()._asdict()
    else:
        values['trig']=module.trig_enclosure.cache_info()._asdict()
    name='_sqrt_bounds_cached' if geometry is not None else '_sqrt_interval_q'
    if hasattr(module,name):values['sqrt']=getattr(module,name).cache_info()._asdict()
    return values


def measured(role,label,mode,module,call,clear,caches,profile_dir):
    def prepare():
        clear()
        if mode=='warm':call()
    prepare();before=caches();start=time.perf_counter_ns();values=call();end=time.perf_counter_ns()
    after=caches();result_bytes=encoded(values)
    per_case=[hashlib.sha256(encoded(value)).hexdigest() for value in values]
    prepare();profile_before=caches();profile=cProfile.Profile();profile.enable()
    try:profiled=call()
    finally:profile.disable()
    if encoded(profiled)!=result_bytes:
        raise AssertionError('profile changed exact public outputs: '+role+'/'+label+'/'+mode)
    dest=profile_dir/(role+'_'+label+'_'+mode+'.pstats')
    with dest.open('xb'):pass
    profile.dump_stats(str(dest))
    text=io.StringIO();pstats.Stats(profile,stream=text).strip_dirs().sort_stats('cumulative').print_stats(25)
    summary=dest.with_suffix('.txt')
    with summary.open('x') as stream:stream.write(text.getvalue())
    return {'role':role,'implementation':label,'cache_regime':mode,'timed_calls':len(values),
        'unprofiled_wall_ns':end-start,'complete_output_canonical_sha256':hashlib.sha256(result_bytes).hexdigest(),
        'per_case_canonical_sha256':per_case,'cache_before_timing':before,'cache_after_timing':after,
        'cache_before_profile':profile_before,'profile':proof(dest),'top25_cumulative':proof(summary),
        'warmup_calls_before_each_pass':len(values) if mode=='warm' else 0,
        'separate_same_input_profile_calls':len(values)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--profile-directory',required=True,type=Path)
    args=parser.parse_args()
    if args.output.exists() or args.profile_directory.exists():
        parser.error('exclusive output/profile-directory already exists; preserve originals')
    manifest_raw=(A/'source_manifest_v1.json').read_bytes()
    manifest=json.loads(manifest_raw)
    paths=[Path(__file__).resolve(),A/'source_manifest_v1.json',*[A/p for p in manifest['sources']]]
    source_before=[proof(p) for p in paths]
    if source_before[1]['sha256']!=hashlib.sha256(manifest_raw).hexdigest():
        raise ValueError('source manifest changed before its binding')
    for relative,spec in manifest['sources'].items():
        found=proof(A/relative)
        if (found['sha256'],found['bytes'])!=(spec['sha256'],spec['bytes']):
            raise ValueError('original A48 source differs: '+relative)
    args.profile_directory.mkdir(parents=True,exist_ok=False)
    records=[];errors=[];pinputs=[];rinputs=[];projection=[]
    try:
        # Loader definitions are reused; unittest suites/main are never called.
        pl=load(A/'production/harness_v1.py','_v48_contract_angle_production_loader_v2')
        g,pbase,pcandidate,projection=pl.load_modules()
        pcases,pinputs=production_cases(g,pl)
        rbase=load(A/'reader/reader_baseline_v1.py','_v48_contract_angle_reader_baseline_v2')
        rcandidate=load(A/'reader/reader_candidate_v1.py','_v48_contract_angle_reader_candidate_v2')
        rinputs=reader_cases()
        for label,module in (('baseline',pbase),('candidate',pcandidate)):
            for mode in ('cold','warm'):
                records.append(measured('production_full_pair',label,mode,module,
                    lambda module=module:[pl.run_pair(module,case) for case in pcases],
                    lambda module=module:clear_production(g,module),
                    lambda module=module:cache_info(module,g),args.profile_directory))
        for label,module in (('baseline',rbase),('candidate',rcandidate)):
            for role in ('reader_trig','reader_direction'):
                def call(module=module,role=role):
                    if role=='reader_trig':return [module.trig_enclosure(row['angle']) for row in rinputs]
                    return [module.direction_support_upper(row['bearing'],row['axis'],row['angle'],
                            row['uncertainty'],row['length']) for row in rinputs]
                for mode in ('cold','warm'):
                    records.append(measured(role,label,mode,module,call,
                        lambda module=module:clear_reader(module),lambda module=module:cache_info(module),
                        args.profile_directory))
        for role in ('production_full_pair','reader_trig','reader_direction'):
            values=[r for r in records if r['role']==role]
            if len(values)!=4 or len({r['complete_output_canonical_sha256'] for r in values})!=1:
                errors.append('exact own-baseline/candidate/cold/warm outputs differ: '+role)
    except BaseException as error:
        errors.append(repr(error))
    source_after=[proof(p) for p in paths]
    if source_before!=source_after:errors.append('source changed during this finite CPU role')
    result={'schema':'mr3-contract-angle-artificial-performance-v2','passed':not errors,'errors':errors,
        'source_before':source_before,'source_after':source_after,'source_stable':source_before==source_after,
        'contract_input_origin':'Exact contract formula only; no original telemetry, maps, model or scene used.',
        'age_ns_formula':'floor(i*500000000/63), i=0..63',
        'phi_formula':'(6/5)*(39/50+age_ns/1000000000)',
        'age_count':64,'age_ns':list(AGES),'phi_exact':canonical(PHIS),
        'production_input_pairing':'64 calls; template index i%12, each template5or6times; not64x12. Both endpoints use age_i and all their directions use phi_i. Structural map/raw deltas,reach kinds/signs,hard flags retained; declared fixed axis transforms give noninteger exact-rational/binary64 families.',
        'production_inputs':canonical(pinputs),'reader_inputs':canonical(rinputs),
        'production_input_sha256':hashlib.sha256(encoded(pinputs)).hexdigest(),
        'reader_input_sha256':hashlib.sha256(encoded(rinputs)).hexdigest(),
        'production_private_namespace_projection':projection,'measurements':records,
        'timing_design':'One unprofiled timing plus a separate same-input cProfile pass for each role/model/cold-or-warm combination. Cold resets once per workload; natural reuse inside it remains. Warm resets then pre-runs same full workload before each measured/profiled pass. Baseline precedes candidate; no randomization/statistical precision claim.',
        'scope_limits':['Not an observed source-age distribution or actual cache-miss rate.','Original disk/no-direction/zero-delta production templates can bypass trig; all64 declared phi inputs are retained but cold mode does not claim64 trig misses. The per-input angle_used_by_direction field and actual cache statistics expose this. Reader cold_trig explicitly evaluates all64.','No old18testgroups rerun and no additional independent test-group claim.','Each side must equal its own frozen bounds; production and reader bounds are not compared for numerical equality.','Original A48 v1 results, cold-sqrt regression and angle-domain caveat remain unchanged.','No new cold-sqrt benchmark in this v2, no threshold/tolerance/degree/precision tuning.','Kernel timings do not establish World/ENV/PPO capacity or fix reset readiness.'],
        'old_tests_rerun':0,'new_independent_test_groups_claimed':0,'native_or_World_run':False,
        'raw_originals_read':False,'models_loaded':False,'production_enabled':False,
        'native_qualification':False,'P2A_complete':False}
    with args.output.open('x') as stream:json.dump(result,stream,indent=2,allow_nan=False);stream.write('\n')
    print(json.dumps({'passed':result['passed'],'measurement_blocks':len(records),'errors':errors,
                      'old_tests_rerun':0,'native_qualification':False}))
    return 0 if result['passed'] else 1


if __name__=='__main__':raise SystemExit(main())
