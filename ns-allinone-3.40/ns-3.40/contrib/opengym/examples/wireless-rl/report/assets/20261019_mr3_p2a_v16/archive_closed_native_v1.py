"""Archive closed V16 FAIL bytes; no simulator, GPU or scientific PASS."""
from pathlib import Path
import hashlib,json,tarfile
ROOT=Path('/home/zhuyulab/ns3-workspace')
SOURCE=ROOT/'ros2_ws/ros2-multi-robot-automap/log/mr3_p2a_reach_v16'
OUT=Path(__file__).resolve().parent/'closed_execution'
ARCHIVE=OUT/'native_closed_v1.tar.gz'
MANIFEST=OUT/'native_closed_manifest_v1.json'
assert not ARCHIVE.exists() and not MANIFEST.exists()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
files=sorted(p for p in SOURCE.rglob('*') if p.is_file())
rows=[{'path':str(p.relative_to(SOURCE)),'bytes':p.stat().st_size,'sha256':sha(p)} for p in files]
with tarfile.open(ARCHIVE,'x:gz',compresslevel=3) as tar:
 for p in files:tar.add(p,arcname=str(p.relative_to(SOURCE)),recursive=False)
with tarfile.open(ARCHIVE,'r:gz') as tar:
 members=tar.getmembers()
 assert [p.name for p in members]==[r['path'] for r in rows]
 for m,r in zip(members,rows):
  h=hashlib.sha256();count=0
  with tar.extractfile(m) as f:
   for b in iter(lambda:f.read(1024*1024),b''):h.update(b);count+=len(b)
  assert h.hexdigest()==r['sha256'] and count==r['bytes']
for p,r in zip(files,rows):assert p.stat().st_size==r['bytes'] and sha(p)==r['sha256']
assert sorted(str(p.relative_to(SOURCE)) for p in SOURCE.rglob('*') if p.is_file())==[r['path'] for r in rows]
value={'schema':'mr3-v16-closed-native-byte-archive-v1','source_freeze':'d307a0b248a87bf1c03b41f4f7df4cb221253ac9','source_root':str(SOURCE),'source_files':rows,'source_bytes':sum(r['bytes'] for r in rows),'archive':{'path':str(ARCHIVE),'bytes':ARCHIVE.stat().st_size,'sha256':sha(ARCHIVE)},'all_archived_bytes_replayed':True,'source_unchanged':True,'scientific_pass_claimed':False,'native_experiment_reexecuted':False}
with MANIFEST.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
print(json.dumps({'files':len(rows),'source_bytes':value['source_bytes'],'archive_bytes':value['archive']['bytes'],'passed_byte_integrity':True}))
