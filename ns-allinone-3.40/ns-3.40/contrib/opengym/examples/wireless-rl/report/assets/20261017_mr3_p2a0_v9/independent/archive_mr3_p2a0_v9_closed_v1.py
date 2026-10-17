import gzip,hashlib,io,json,shutil,subprocess,tarfile
from pathlib import Path
root=Path('/home/zhuyulab/ns3-workspace')
w=root/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
a=w/'report/assets/20261017_mr3_p2a0_v9'
freeze='26534fae40409e266376baf0995fb15dc0223e4b'
chunk=1024*1024
def digest(p,decoded=False):
 h=hashlib.sha256();size=0
 with (gzip.open if decoded else open)(p,'rb') as stream:
  for b in iter(lambda:stream.read(chunk),b''):h.update(b);size+=len(b)
 return size,h.hexdigest()
def write(p,d):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(d,f,indent=2,allow_nan=False);f.write('\n')
def preserve(p,out,compress=False):
 out.parent.mkdir(parents=True,exist_ok=True)
 if not out.exists():
  with p.open('rb') as source,out.open('xb') as sink:
   if compress:
    with gzip.GzipFile(filename='',mode='wb',fileobj=sink,mtime=0) as encoded:shutil.copyfileobj(source,encoded,chunk)
   else:shutil.copyfileobj(source,sink,chunk)
 raw=digest(p);selected=digest(out)
 assert digest(out,compress)==raw
 return dict(source=str(p),selected=str(out.relative_to(a)),encoding='gzip' if compress else 'identity',raw_bytes=raw[0],raw_sha256=raw[1],selected_bytes=selected[0],selected_sha256=selected[1])
before=[]
paths=subprocess.check_output(['git','ls-tree','-r','--name-only',freeze,'--',str(a.relative_to(root))],cwd=root,text=True).splitlines()
for rel in paths:
 raw=subprocess.check_output(['git','show',freeze+':'+rel],cwd=root);p=root/rel
 assert digest(p)==(len(raw),hashlib.sha256(raw).hexdigest())
 before.append(dict(path=str(p.relative_to(a)),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
native=[]
for stage in ('interface',):
 source=Path('/tmp/mr3_p2a0_v9_selected_native')/stage
 target=a/'native'/stage
 manifest=json.loads((source/'manifest.json').read_text())
 for row in manifest['files']:
  raw=(row['raw_bytes'],row['raw_sha256']);selected=(row['selected_bytes'],row['selected_sha256'])
  assert digest(Path(row['source']))==raw and digest(source/row['selected'])==selected
  assert digest(source/row['selected'],row['encoding']=='gzip')==raw
 if not target.exists():shutil.copytree(source,target)
 assert (source/'manifest.json').read_bytes()==(target/'manifest.json').read_bytes()
 for row in manifest['files']:
  assert digest(target/row['selected'])==(row['selected_bytes'],row['selected_sha256'])
 native.append(dict(stage=stage,source_files=manifest['source_files'],raw_bytes=manifest['raw_bytes'],selected_bytes=manifest['selected_bytes'],manifest=str((target/'manifest.json').relative_to(a)),manifest_sha256=digest(target/'manifest.json')[1]))
original_paths=set()
for pattern in ('mr3_p2a0_v9_interface*','mr3_p2a0_v9_initial*','mr3_p2a0_v9_information_closed*','mr3_p2a0_v9_readonly_monitor*','mr3_v9*','mr3_readonly_v9*'):
 original_paths.update(p for p in Path('/tmp').glob(pattern) if p.is_file() and p.suffix in ('.json','.log','.txt','.py','.gz'))
for name in ('mr3_p2a0_v9_source_preflight.json','mr3_p2a0_v9_binaryproof.json','source_bindings_26534fae4040.json','source_bindings_26534fae4040.tar.gz','mr3_p2a0_v9_root_audit_runner_v1.py','mr3_p2a0_v9_root_audit_runner_diagnostic_v2.py','mr3_p2a0_v9_pack_native_v1.py','mr3_p2a0_v9_preflight_console_v1.log'):
 original_paths.add(Path('/tmp')/name)
original_paths.add(Path(__file__))
originals=[]
for p in sorted(original_paths):
 assert p.is_file(),str(p)
 if p.suffix=='.json':json.loads(p.read_text())
 directory=a/('accounting' if p.name.endswith('_launch.json') or p.suffix=='.log' else 'independent')
 compress=p.suffix in ('.log','.txt') or p.stat().st_size>1000000
 out=directory/(p.name+('.gz' if compress else ''))
 originals.append(preserve(p,out,compress))
source=json.loads(Path('/tmp/source_bindings_26534fae4040.json').read_text())
pack=Path('/tmp/source_bindings_26534fae4040.tar.gz')
assert digest(pack)[1]==source['encoded_sha256']
with tarfile.open(pack,'r:gz') as tar:
 assert len(tar.getmembers())==len(source['files'])==97
 for row in source['files']:
  raw=tar.extractfile(row['path']).read()
  assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
  assert raw==subprocess.check_output(['git','show',freeze+':'+row['path']],cwd=root)
for row in before:assert digest(a/row['path'])==(row['bytes'],row['sha256'])
write(a/'independent/native_originals_manifest_v1.json',dict(schema='mr3-p2a0-v9-native-original-reviews-v1',freeze=freeze,files=originals,native=native,scope='Original native interface startup FAIL with zero task samples and all observer errors retained; terminal/reset/deadline not attempted. No mixed-freeze matrix credit.'))
write(a/'independent/native_archive_verification_v1.json',dict(schema='mr3-p2a0-v9-native-canonical-verification-v1',passed=True,freeze=freeze,prefreeze_assets_verified_against_git=len(before),prefreeze_asset_bindings=before,native=native,source_payload_files=97,source_payload_sha256=digest(pack)[1],source_payload_matches_exact_git_bytes=True,original_reviews_archived=len(originals),scope='Archive byte integrity only; zero-task-sample native startup FAIL remains. Helpers reuse prior streaming archive logic; no native retry.'))
files=[dict(path=str(p.relative_to(a)),bytes=p.stat().st_size,sha256=digest(p)[1]) for p in sorted(a.rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix!='.pyc']
write(a/'inventory_native_v1.json',dict(schema='mr3-p2a0-v9-native-inventory-v1',freeze=freeze,self_excluded=True,prefreeze_assets_preserved=len(before),files=files))
print(json.dumps(dict(passed=True,native=native,originals=len(originals),prefreeze_assets_preserved=len(before),inventory_files=len(files),inventory_sha256=digest(a/'inventory_native_v1.json')[1])),flush=True)
