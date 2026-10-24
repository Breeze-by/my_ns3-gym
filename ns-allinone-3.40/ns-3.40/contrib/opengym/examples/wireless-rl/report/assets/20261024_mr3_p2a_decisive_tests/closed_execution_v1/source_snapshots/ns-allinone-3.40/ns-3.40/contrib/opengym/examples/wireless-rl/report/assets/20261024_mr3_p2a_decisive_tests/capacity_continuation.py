"""Close the failed behavior attempt and run the separately declared cost arm."""
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
W = HERE.parents[2]
ROOT = next(p for p in HERE.parents if (p/'.git').exists())
sys.path.insert(0, str(W))
from mr3_learning.decisive_tests import run_arm, require
from mr3_learning.preparation import identity


def assert_gone(saved):
    require(type(saved) is dict and type(saved.get('pid')) is int
            and type(saved.get('start_ticks')) is int, 'untyped saved identity')
    current = identity(saved['pid'])
    require(current is None or current['start_ticks'] != saved['start_ticks'], 'saved process still exists')
    return dict(saved=saved, current=current, same_saved_identity_absent=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--freeze',required=True)
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args()
    start=time.monotonic_ns()
    out=Path('/tmp/mr3_decisive_capacity_continuation_check_v1' if args.check_only
             else '/tmp/mr3_decisive_capacity_continuation_v1')
    out.mkdir(exist_ok=False)
    source={}
    for path in (Path(__file__).resolve(),HERE/'capacity_continuation_scope.json'):
        raw=path.read_bytes()
        require(raw == subprocess.check_output(['git','show',args.freeze+':'+str(path.relative_to(ROOT))],cwd=ROOT), 'continuation source differs from Git')
        source[str(path)]=raw
    scope=json.loads(source[str(HERE/'capacity_continuation_scope.json')])
    inputs={}
    for name,proof in scope['inputs'].items():
        raw=Path(name).read_bytes()
        require(len(raw)==proof['bytes'] and hashlib.sha256(raw).hexdigest()==proof['sha256'], 'first attempt input changed')
        inputs[name]=raw
    def document(suffix):
        matches=[raw for name,raw in inputs.items() if name.endswith(suffix)]
        require(len(matches)==1,'ambiguous fixed input')
        return json.loads(matches[0])
    rootwait=document('/actual_wait.json')
    require(rootwait['actual_waited'] is True and rootwait['actual_returncode']==1
            and rootwait['source_unchanged'] is True and rootwait['actual_child_wait_seconds']==scope['first_fee'], 'first failed parent is not closed')
    shutdown=document('/supervisor_shutdown.json')
    require(shutdown['remaining_owned_processes']==[] and shutdown['remaining_owned_zombies']==[], 'first owned closure incomplete')
    saved=list(shutdown['owned_processes_seen'])
    saved += [rootwait['coordinator_identity'],rootwait['child_identity'],document('/bootstrap.json')['owner']]
    for suffix in ('/native_command.json','/watcher_command.json'):
        row=document(suffix);require(row['execution_kind']=='subprocess_waited','child not actually waited')
        saved += [row['process_identity'],row['coordinator_identity']]
    metadata=document('/supervisor_metadata.json')
    def collect(value):
        if isinstance(value,dict):
            if type(value.get('pid')) is int and type(value.get('start_ticks')) is int:
                saved.append(value)
            else:
                for v in value.values():collect(v)
        elif isinstance(value,list):
            for v in value:collect(v)
    collect(metadata)
    unique={(s['pid'],s['start_ticks']):s for s in saved}
    closure=[assert_gone(s) for s in unique.values()]
    # This proves fresh absence of saved identities, not missing live custody.
    (out/'first_attempt_closure.json').write_text(json.dumps(dict(identities=closure,
        original_forced_shutdown=shutdown['forced_shutdown'],original_failed_sample=shutdown['failed_sample'],
        custody_pass_recovered=False,old_attempt_passed=False,nonowned_ancestors_not_claimed=True),indent=2)+'\n')
    rows=[json.loads(line) for line in next(raw for name,raw in inputs.items() if name.endswith('/transitions.jsonl')).splitlines()]
    adapter=[json.loads(line) for line in next(raw for name,raw in inputs.items() if name.endswith('/adapter.jsonl')).splitlines()]
    failures=[r for r in adapter if ('navigation_failure' in json.dumps(r) or
        any(x in json.dumps(r) for x in ('"last_failure": "','"failure_reason": "','"failure": "')))]
    description=dict(scope='fixed received fields only; no native/continuous-physics credit',
        transition_count=len(rows)-1,last_two_transitions=rows[-2:],
        adapter_matching_failure_rows=len(failures),first_failure_rows=failures[:6],last_failure_rows=failures[-6:],
        native_summary=document('/benchmark_summary.json'))
    (out/'first_attempt_description.json').write_text(json.dumps(description,indent=2)+'\n')
    require(all(Path(n).read_bytes()==b for n,b in inputs.items()),'first evidence changed')
    require(all(Path(n).read_bytes()==b for n,b in source.items()),'continuation changed')
    if args.check_only:
        print('fixed input / saved identity closure PASS; no native launched',flush=True)
        return 0
    plan=Path(scope['capacity_plan'])
    require(hashlib.sha256(plan.read_bytes()).hexdigest()==scope['capacity_plan_sha256'],'capacity plan changed')
    require(Decimal(scope['first_fee'])+scope['continuation_reservation_seconds']<=scope['original_reservation_seconds'], 'original reservation exceeded')
    result=run_arm(plan,args.freeze,start+scope['continuation_reservation_seconds']*10**9)
    require(all(Path(n).read_bytes()==b for n,b in source.items()),'continuation source changed')
    (out/'summary.json').write_text(json.dumps(dict(started_monotonic_ns=start,ended_monotonic_ns=time.monotonic_ns(),
        owner=identity(os.getpid()),result=result,old_failure_preserved=True,qualification=False),indent=2)+'\n')
    return 0 if result['diagnostic_passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
