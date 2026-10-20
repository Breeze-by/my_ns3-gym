import gzip,hashlib,json,os
from pathlib import Path
base=Path('/home/zhuyulab/ns3-workspace/ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_proxy2d_v23')
roots=[base/'profile_v1',base/'short_capacity_v1']; records=[];bindings=[]
for root in roots:
 audit=json.loads((root/'independent_audit.json').read_text());assert audit['passed'] is True
 path=root/'stages/group1/worker0/episode001_open_101/trace.jsonl.gz';raw=path.read_bytes();rows=[json.loads(v) for v in gzip.decompress(raw).splitlines()];selected=[v for v in rows if v['event'] in ('reset','step_return')];assert len(selected)==9
 records.append(selected);bindings.append({'path':str(path),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'audit_path':str(root/'independent_audit.json'),'audit_sha256':hashlib.sha256((root/'independent_audit.json').read_bytes()).hexdigest()})
comparisons=[]
fields=('reward','dt','physical_dt','terminated','truncated','reason','action')
for left,right in zip(*records):
 differences=[key for key in fields if left.get(key)!=right.get(key)]
 tensors_equal=left['tensor_proofs']==right['tensor_proofs']
 comparisons.append({'event':left['event'],'left_sequence':left['event_sequence'],'right_sequence':right['event_sequence'],'tensor_proofs_equal':tensors_equal,'differing_scalars':differences,'passed':tensors_equal and not differences})
for spec in bindings:assert hashlib.sha256(Path(spec['path']).read_bytes()).hexdigest()==spec['sha256']
raw=Path('/proc/self/stat').read_text();f=raw[raw.rfind(')')+2:].split()
result={'schema':'mr3-proxy2d-encoded-prefix-comparison-v1','scope':'Only the fixed shared open101/group1/env0 reset+8-step prefix: saved previously verified encoded tensor dtype/shape/byte hashes, actions and transition scalars. No new world, actor replay, general equivalence or training speedup claim. Epoch/digests/goal IDs/raw actor parameters are outside this comparison.','input_bindings':bindings,'comparisons':comparisons,'passed':all(v['passed'] for v in comparisons),'identity':{'pid':os.getpid(),'start_ticks':int(f[19]),'parent':int(f[1]),'group':int(f[2]),'session':int(f[3])},'qualification':False,'training_eligible':False}
out=Path('/tmp/mr3_proxy2d_v23_pair_v1.json')
with out.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
print(json.dumps({'passed':result['passed'],'compared_rows':len(comparisons),'output':str(out)}));raise SystemExit(0 if result['passed'] else 1)
