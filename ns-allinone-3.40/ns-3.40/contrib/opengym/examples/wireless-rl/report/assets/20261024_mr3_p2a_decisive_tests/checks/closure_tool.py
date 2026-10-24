"""Post-reap metadata and lossless byte archive; no scientific rejudgment."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import time

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261024_mr3_p2a_decisive_tests'
OUT=Path('/tmp/mr3_decisive_close_v1')
G='0649f057c38410a14761c5c98a13bd3f496bc1d2'
H=W/'report/assets/20261022_mr3_p2a_v45_preparation_classification/collect_closed_v1.py'
assert hashlib.sha256(H.read_bytes()).hexdigest()=='63d52ce389b7d61fa67f5080fa556b1f32e47b79e389800f9de55e97c40abf06'
spec=importlib.util.spec_from_file_location('original_opaque_archive',H)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.A=A;m.DEST=A/'closed_execution_v1'
ROOTS=[Path('/tmp')/n for n in ('mr3_decisive_root_v1','mr3_p2a_decisive_tests_v1',
    'mr3_decisive_capacity_root_v1','mr3_decisive_capacity_continuation_v1',
    'mr3_decisive_entry_v1','mr3_decisive_cpu_v1','mr3_decisive_cpu_v2')]
NATIVE=ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_decisive_tests_v1'
ROOTS.append(NATIVE)


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:json.dump(value,stream,indent=2,ensure_ascii=False);stream.write('\n')


def main():
    started=time.monotonic_ns();OUT.mkdir(exist_ok=False)
    assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()==G
    assert not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT)
    waits=[json.loads((p/'actual_wait.json').read_bytes()) for p in (ROOTS[0],ROOTS[2])]
    assert all(x['actual_waited'] is True and type(x['actual_returncode']) is int and x['source_unchanged'] is True for x in waits)
    saved={}
    def add(row,origin):
        assert type(row) is dict and type(row.get('pid')) is int and type(row.get('start_ticks')) is int,origin
        saved.setdefault((row['pid'],row['start_ticks']),dict(identity=row,origins=[]))['origins'].append(origin)
    for p in ROOTS[:-1]:
        for receipt in p.rglob('*_command.json'):
            row=json.loads(receipt.read_bytes())
            if row.get('schema')=='mr3-reach-native-wait-v1':
                assert row.get('execution_kind')=='subprocess_waited',str(receipt)
                add(row['process_identity'],str(receipt))
                add(row['coordinator_identity'],str(receipt)+':coordinator')
        for receipt in p.glob('actual_wait.json'):
            row=json.loads(receipt.read_bytes());assert row['actual_waited'] is True
            add(row['child_identity'],str(receipt)+':child');add(row['coordinator_identity'],str(receipt)+':coordinator')
    firstboot=json.loads((ROOTS[1]/'bootstrap.json').read_bytes());add(firstboot['owner'],'first bootstrap owner')
    for p in NATIVE.glob('*/worker*/episode*/supervisor_shutdown.json'):
        row=json.loads(p.read_bytes());assert row['remaining_owned_processes']==[] and row['remaining_owned_zombies']==[]
        for ident in row['owned_processes_seen']:add(ident,str(p))
        metadata=json.loads((p.parent/'supervisor_metadata.json').read_bytes());add(metadata['worker_identity'],str(p.parent/'supervisor_metadata.json'))
    for record in saved.values():m.require_absent(record['identity'])
    write(OUT/'saved_absence.json',dict(saved_identity_count=len(saved),identities=list(saved.values()),
        all_saved_identities_fresh_absent=True,nonowned_ancestors_not_claimed=True,forced_status_not_reclassified=True))
    plan=json.loads((A/'capacity.json').read_bytes())
    sources={ROOT/p:h for p,h in plan['source_bindings'].items()}
    for p in (A/'capacity.json',A/'feasibility.json',A/'capacity_continuation.py',A/'capacity_continuation_scope.json'):
        sources[p]=hashlib.sha256(p.read_bytes()).hexdigest()
    process=subprocess.Popen(['git','cat-file','--batch'],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE)
    source_rows=[]
    try:
        for p,expected in sorted(sources.items()):
            before=m.regular_stamp(p);raw=p.read_bytes();assert hashlib.sha256(raw).hexdigest()==expected
            process.stdin.write((G+':'+str(p.relative_to(ROOT))+'\n').encode());process.stdin.flush()
            header=process.stdout.readline().split();assert len(header)==3 and header[1]==b'blob',str(p)
            size=int(header[2]);frozen=process.stdout.read(size);assert process.stdout.read(1)==b'\n' and frozen==raw
            assert m.regular_stamp(p)==before
            source_rows.append(dict(path=str(p),sha256=expected,bytes=len(raw),stat=before,current_git_equal=True))
    finally:
        process.stdin.close();assert process.wait()==0
    elf=[]
    for name,expected in plan['library_bindings'].items():
        p=Path(name);p=p if p.is_absolute() else ROOT/p
        before=m.regular_stamp(p.resolve());digest,size=m.digest_stream(p.open('rb'));assert digest==expected and m.regular_stamp(p.resolve())==before
        elf.append(dict(literal_path=str(p),resolved_path=str(p.resolve()),sha256=digest,bytes=size,stat=before))
    write(OUT/'source_closure.json',dict(freeze=G,sources=source_rows,libraries=elf,passed=True))
    def inventory():
        files={};links={};directories={}
        for root in ROOTS:
            assert root.is_dir() and not root.is_symlink()
            for parent,dirs,names in os.walk(root,followlinks=False):
                parent=Path(parent);directories[str(parent)]=m.stamp(parent.lstat())
                for name in list(dirs):
                    p=parent/name
                    if p.is_symlink():links[str(p)]=dict(stat=m.stamp(p.lstat()),literal=os.readlink(p));dirs.remove(name)
                for name in names:
                    p=parent/name
                    if p.is_symlink():links[str(p)]=dict(stat=m.stamp(p.lstat()),literal=os.readlink(p))
                    else:files[p]=m.regular_stamp(p)
        return files,links,directories
    files,links,dirs=inventory();selected={}
    for p,before in files.items():
        root=next(r for r in ROOTS if p.is_relative_to(r))
        label='native' if root==NATIVE else 'tmp/'+root.name
        target,compressed=m.target_for(label,p.relative_to(root),p)
        selected[p]=dict(target=target,compressed=compressed,stat=before)
    for row in source_rows:
        p=Path(row['path']);target,compressed=m.target_for('source_snapshots',p.relative_to(ROOT),p)
        selected[p]=dict(target=target,compressed=compressed,stat=row['stat'])
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures=[pool.submit(m.archive,p,row) for p,row in selected.items()]
        archived=[f.result() for f in futures]
    assert inventory()==(files,links,dirs),'closed roots changed during opaque archive'
    limit=32*1024*1024
    for row in archived:
        p=A/row['canonical']
        if p.stat().st_size<=limit:continue
        segments=[];combined=hashlib.sha256();total=0
        with p.open('rb') as stream:
            index=0
            while chunk:=stream.read(limit):
                index+=1;q=Path(str(p)+f'.part{index:04d}')
                with q.open('xb') as output:output.write(chunk)
                actual=q.read_bytes();assert actual==chunk
                combined.update(actual);total+=len(actual)
                segments.append(dict(path=str(q.relative_to(A)),sha256=hashlib.sha256(actual).hexdigest(),bytes=len(actual)))
        assert combined.hexdigest()==row['canonical_sha256'] and total==row['canonical_bytes']
        row['canonical_segments']=segments;row['canonical_unsplit_path']=row.pop('canonical');row['segment_concatenation_verified']=True;p.unlink()
    elapsed=(time.monotonic_ns()-started)/1e9
    inventory_result=dict(schema='mr3-decisive-closed-byte-inventory-v1',roots=list(map(str,ROOTS)),
        regular_count=len(files),regular_bytes=sum(v['size'] for v in files.values()),links=links,
        source_snapshot_count=len(source_rows),archived=archived,all_submitted_writers_waited=True,
        source_and_closed_roots_stable=True,all_decoded_original_bytes_verified=True,wall_seconds=elapsed)
    write(A/'closed_inventory.json',inventory_result)
    fee=sum((Decimal(x['actual_child_wait_seconds']) for x in waits),Decimal(0))
    ledger=dict(schema='mr3-decisive-engineering-ledger-v1',entry='112685.3057936486018',
        engineering_added_seconds=str(fee),engineering_cumulative_seconds=str(Decimal('112685.3057936486018')+fee),
        engineering_ceiling_seconds='180000',engineering_remaining_seconds=str(Decimal('180000')-Decimal('112685.3057936486018')-fee),
        actual_complete_parent_waits=waits,nested_not_added=True,pilot_changed=False,final_changed=False,
        P2A_complete=False,capacity_qualified=False,automatic_policy_entry_allowed=False,
        closure_archival_cpu_engineering_added_seconds='0')
    write(A/'closure_ledger.json',ledger)
    write(OUT/'summary.json',dict(passed=True,regular_count=len(files),source_count=len(source_rows),
        saved_identities=len(saved),raw_bytes=inventory_result['regular_bytes'],
        archived_bytes=sum(r['canonical_bytes'] for r in archived),wall_seconds=elapsed))
    print(json.dumps(json.loads((OUT/'summary.json').read_bytes())),flush=True)


if __name__=='__main__':main()
