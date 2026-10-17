import gzip,hashlib,json,shutil,sys,time
from pathlib import Path
root=Path('/home/zhuyulab/ns3-workspace')
freeze='26534fae40409e266376baf0995fb15dc0223e4b'
stage=sys.argv[1]
assert stage in ('interface','terminal','reset','deadline')
source=root/('ros2_ws/ros2-multi-robot-automap/log/mr3_p2a0/mr3_p2a0_20261017_v9_'+stage)
target=Path('/tmp/mr3_p2a0_v9_selected_native')/stage
launch=json.loads(Path('/tmp/mr3_p2a0_v9_'+stage+'_launch.json').read_text())
assert launch['status']=='completed' and launch['freeze']==freeze
assert not target.exists()
target.mkdir(parents=True)
chunk=1024*1024
def digest(path,decoded=False):
 h=hashlib.sha256(); size=0
 with (gzip.open if decoded else open)(path,'rb') as stream:
  for b in iter(lambda:stream.read(chunk),b''):h.update(b);size+=len(b)
 return size,h.hexdigest()
started=time.monotonic();rows=[];duplicates=[];caches=[]
for p in sorted(source.rglob('*')):
 if not p.is_file():continue
 if p.suffix=='.pyc' or '__pycache__' in p.parts:caches.append(str(p.relative_to(source)));continue
 if p.suffix=='.gz' and p.with_suffix('').is_file() and digest(p,True)==digest(p.with_suffix('')):
  duplicates.append(str(p.relative_to(source)));continue
 rel=p.relative_to(source);compress=p.suffix in ('.log','.jsonl','.csv','.zip') or p.name=='resources.json'
 out=target/(str(rel)+'.gz' if compress else rel);out.parent.mkdir(parents=True,exist_ok=True)
 stat=p.stat()
 with p.open('rb') as a,out.open('xb') as b:
  if compress:
   with gzip.GzipFile(filename='',mode='wb',fileobj=b,mtime=0) as gz:shutil.copyfileobj(a,gz,chunk)
  else:shutil.copyfileobj(a,b,chunk)
 assert (stat.st_size,stat.st_mtime_ns)==(p.stat().st_size,p.stat().st_mtime_ns),str(p)
 raw=digest(p);selected=digest(out)
 assert digest(out,compress)==raw,str(out)
 rows.append(dict(source=str(p),selected=str(out.relative_to(target)),encoding='gzip' if compress else 'identity',raw_bytes=raw[0],raw_sha256=raw[1],selected_bytes=selected[0],selected_sha256=selected[1]))
manifest=dict(schema='mr3-p2a-selected-originals-v1',freeze=freeze,stage=stage,source=str(source),selection='All closed run files excluding byte-duplicate sibling gzip copies and Python cache; originals retained in place.',source_files=len(rows),raw_bytes=sum(r['raw_bytes'] for r in rows),selected_bytes=sum(r['selected_bytes'] for r in rows),files=rows,duplicate_encoded_copies_not_selected=duplicates,excluded_python_cache=caches)
with (target/'manifest.json').open('x') as out:json.dump(manifest,out,indent=2,allow_nan=False)
print(json.dumps(dict(passed=True,stage=stage,source_files=len(rows),raw_bytes=manifest['raw_bytes'],selected_bytes=manifest['selected_bytes'],wall_seconds=time.monotonic()-started,manifest=str(target/'manifest.json'),manifest_sha256=digest(target/'manifest.json')[1])),flush=True)
