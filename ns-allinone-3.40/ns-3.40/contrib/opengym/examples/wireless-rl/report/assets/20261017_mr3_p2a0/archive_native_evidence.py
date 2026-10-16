import argparse,gzip,hashlib,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('target',type=Path);a=p.parse_args()
if a.target.exists():raise SystemExit('target already exists')
a.target.mkdir(parents=True)
entries=[];duplicates=[]
sha=lambda data:hashlib.sha256(data).hexdigest()
for source in sorted(a.source.rglob('*')):
 if not source.is_file():continue
 relative=source.relative_to(a.source);raw=source.read_bytes()
 if source.suffix=='.gz' and source.with_suffix('').exists():
  assert gzip.decompress(raw)==source.with_suffix('').read_bytes()
  duplicates.append(str(relative));continue
 compressed=source.suffix in ('.jsonl','.log')
 selected=Path(str(relative)+'.gz') if compressed else relative
 payload=gzip.compress(raw,mtime=0) if compressed else raw
 target=a.target/selected;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(payload)
 decoded=gzip.decompress(payload) if selected.suffix=='.gz' else payload
 entries.append({'source':str(relative),'selected':str(selected),'source_bytes':len(raw),'source_sha256':sha(raw),'selected_bytes':len(payload),'selected_sha256':sha(payload),'decoded_bytes':len(decoded),'decoded_sha256':sha(decoded),'encoding':'gzip' if selected.suffix=='.gz' else 'identity'})
manifest={'schema':'mr3-p2a0-selected-native-evidence-v1','source_root':str(a.source),'files':entries,'duplicate_encoded_copies_not_selected':duplicates,'file_count':len(entries),'source_bytes':sum(e['source_bytes'] for e in entries),'selected_bytes':sum(e['selected_bytes'] for e in entries)}
(a.target/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
for e in entries:
 data=(a.target/e['selected']).read_bytes();assert sha(data)==e['selected_sha256']
 decoded=gzip.decompress(data) if e['encoding']=='gzip' else data;assert sha(decoded)==e['decoded_sha256']
print(json.dumps({k:manifest[k] for k in ['file_count','source_bytes','selected_bytes']}))
