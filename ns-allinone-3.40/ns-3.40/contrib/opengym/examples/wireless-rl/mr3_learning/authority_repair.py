"""Finite authority-v3 activation verification; no learning or qualification entry."""
import argparse
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import time

from . import decisive_tests as d
from .motion_authority_profile import MOTION_AUTHORITY_PROFILE
from .preparation import identity

A=d.W/'report/assets/20261024_mr3_p2a_authority_activation'
OUT=Path('/tmp/mr3_p2a_authority_activation_v1')
NATIVE=d.ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_authority_activation_v1'
CONTRACT='mr3-p2a-authority-activation-v3'
PRIOR=Decimal('116147.2793258256018')
CAP=Decimal('180000')


def prepare():
    old=json.loads((d.OLD/'plan_v1.json').read_bytes())
    base=json.loads((d.OLD/'native_custody_binding_v1.json').read_bytes())
    script=d.OLD/'make_native_binding_v1.py'
    spec=importlib.util.spec_from_file_location('authority_repair_build_binding',script)
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    binding=helper.update_driver_binding(base,A/'checks/native_build_v1/build_manifest_v1.json',
                                         A/'native_build_bridge_v1.json')
    binding['motion_authority_profile']=MOTION_AUTHORITY_PROFILE
    paths=set(old['source_bindings']) | d.prep.source_inventory(d.ROOT)
    paths.update(str(p.relative_to(d.ROOT)) for p in A.rglob('*') if p.is_file()
                 and 'source_snapshots' not in p.parts and p.suffix in ('.py','.sh','.json','.md','.xml','.log','.rawbytes'))
    paths-={str((A/n).relative_to(d.ROOT)) for n in ('binding.json','feasibility.json','capacity.json')}
    sources={p:d.sha(d.ROOT/p) for p in sorted(paths)}
    native,_=d.custody.load_implementation()
    for row in binding['binaries'].values():
        current=native.file_proof(row['path'])
        d.require(current['sha256']==row['sha256'] and current['bytes']==row['bytes'],'unexpected ELF drift')
        row.update(current)
    binding['source_bindings']=[dict(path=p,sha256=h) for p,h in sources.items()]
    binding['qualification_wrappers']=[r for r in binding['source_bindings'] if '/mr3_learning/' in r['path']]
    d.dump(A/'binding.json',binding);sources[str((A/'binding.json').relative_to(d.ROOT))]=d.sha(A/'binding.json')
    for arm in ('feasibility','capacity'):
        plan=json.loads((d.A/(arm+'.json')).read_bytes())
        path=A/(arm+'.json')
        argv=[v.replace(str(d.NATIVE),str(NATIVE)).replace(str(d.A),str(A)) for v in plan['native_argv']]
        plan.update(diagnostic_contract=CONTRACT,source_bindings=sources,custody_binding=str(A/'binding.json'),
            motion_authority_profile=MOTION_AUTHORITY_PROFILE,run_directory=str(NATIVE/arm),
            output_directory=str(OUT/arm),native_argv=argv)
        d.dump(path,plan)
    print(json.dumps(dict(prepared=True,source_count=len(sources),profile=MOTION_AUTHORITY_PROFILE)))


def execute(freeze):
    started=time.monotonic_ns();OUT.mkdir(exist_ok=False)
    owner=identity(os.getpid());ancestors=[];pid=owner['parent']
    while pid>0 and len(ancestors)<16:
        row=identity(pid)
        if row is None:break
        ancestors.append(row);pid=row['parent']
    d.dump(OUT/'bootstrap.json',dict(freeze=freeze,owner=owner,ancestors=ancestors,
                                   started_monotonic_ns=started,contract=CONTRACT))
    results=[];error=None
    try:
        for arm in ('feasibility','capacity'):
            d.require(time.monotonic_ns()+12000*10**9<=started+d.RESERVATION*10**9,
                      'insufficient complete arm reservation')
            result=d.run_arm(A/(arm+'.json'),freeze,started+d.RESERVATION*10**9)
            results.append(result)
            if not result['diagnostic_passed']:
                error='required repair diagnostic failed; dependent capacity not admitted';break
    except Exception as failure:error=repr(failure)
    ended=time.monotonic_ns();fee=Decimal(ended-started)/10**9
    result=dict(schema=CONTRACT,freeze=freeze,owner=owner,started_monotonic_ns=started,ended_monotonic_ns=ended,
        engineering_added_seconds=str(fee),engineering_used_seconds=str(PRIOR+fee),
        engineering_ceiling_seconds=str(CAP),engineering_remaining_seconds=str(CAP-PRIOR-fee),
        reservation_seconds=d.RESERVATION,arms=results,error=error,qualification=False,capacity_qualified=False,
        automatic_policy_entry_allowed=False,optimizer_updates=0,policy_calls=0,P2A_complete=False)
    d.dump(OUT/'summary.json',result)
    print(json.dumps(dict(event='complete',error=error,engineering_seconds=str(fee))),flush=True)
    return 0 if error is None and len(results)==2 else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('prepare','check','run'))
    parser.add_argument('--freeze');args=parser.parse_args()
    if args.operation=='prepare':prepare();return 0
    d.require(args.freeze is not None,'exact freeze required')
    if args.operation=='check':
        for arm in ('feasibility','capacity'):d.check(A/(arm+'.json'),args.freeze,clean=True)
        print(json.dumps(dict(passed=True,profile=MOTION_AUTHORITY_PROFILE)));return 0
    return execute(args.freeze)


if __name__=='__main__':raise SystemExit(main())
