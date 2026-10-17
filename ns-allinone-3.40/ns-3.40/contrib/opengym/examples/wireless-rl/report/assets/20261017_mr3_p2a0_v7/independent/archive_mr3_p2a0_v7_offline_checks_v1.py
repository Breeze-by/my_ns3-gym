"""Preserve v7 offline receipts without changing their original path declarations."""
from pathlib import Path
import gzip
import hashlib
import io
import json

R=Path('/home/zhuyulab/ns3-workspace')
A=R/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261017_mr3_p2a0_v7'
I=A/'independent'
I.mkdir(exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
seeds=[p for p in Path('/tmp').glob('mr3_p2a0_v7_*.json')
       if any(x in p.name for x in ('checks','review','static','schema_example'))
       and 'before_checks_archive' not in p.name]
paths=set(seeds)
def scan(value):
    if isinstance(value,dict):
        for key,child in value.items():
            scan(key)
            scan(child)
    elif isinstance(value,list):
        for child in value:
            scan(child)
    elif isinstance(value,str) and value.startswith('/tmp/') and '\n' not in value and ' ' not in value:
        paths.add(Path(value))
for p in seeds:
    scan(json.loads(p.read_text()))
for pattern in ['mr3_p2a0_v7_drive*.log','mr3_p2a0_v7_drive*.txt','mr3_p2a0_v7_contract*.txt']:
    paths.update(Path('/tmp').glob(pattern))
for name in ['mr3_v7_drive_static_verify.py','mr3_p2a0_v7_buildproof_preflight.py',
             'mr3_independent_drive_trace_v3_before_release_scope.py',
             'mr3_independent_drive_trace_v3_tests_before_release_scope.py']:
    paths.add(Path('/tmp')/name)
paths.add(Path(__file__))
rows=[]
excluded=[]
missing=[]
deferred=[]
reused=[]
for p in sorted(paths):
    if p.name in ('mr3_independent_drive_trace_v3.py','mr3_independent_drive_trace_v3_tests.py'):
        deferred.append({'source':str(p),'reason':'Final tagged consumer still being edited. Original review bytes saved under before_release_scope alias; final source/checks archived separately once ready.'})
        continue
    if not p.is_file():
        missing.append(str(p))
        continue
    raw=p.read_bytes()
    if raw.startswith(b'\x7fELF'):
        excluded.append({'source':str(p),'bytes':len(raw),'sha256':sha(raw),'reason':'Reproducible pure CPU executable; compile/run argv and outputs preserved, no ELF copied.'})
        continue
    if p.name.startswith('mr3_p2a0_v6_'):
        old=A.parent/'20261017_mr3_p2a0_v6/independent'/p.name
        encoded_old=Path(str(old)+'.gz')
        if old.is_file() and old.read_bytes()==raw:
            reused.append({'source':str(p),'canonical':str(old.relative_to(A.parent)),'encoding':'identity','raw_sha256':sha(raw)})
            continue
        if encoded_old.is_file() and gzip.decompress(encoded_old.read_bytes())==raw:
            reused.append({'source':str(p),'canonical':str(encoded_old.relative_to(A.parent)),'encoding':'gzip','raw_sha256':sha(raw),'encoded_sha256':sha(encoded_old.read_bytes())})
            continue
    compress=p.suffix in ('.txt','.log')
    target=I/(p.name+('.gz' if compress else ''))
    if compress:
        sink=io.BytesIO()
        with gzip.GzipFile(filename='',mode='wb',fileobj=sink,mtime=0) as out:
            out.write(raw)
        encoded=sink.getvalue()
    else:
        encoded=raw
    if target.exists():
        assert target.read_bytes()==encoded,str(target)
    else:
        with target.open('xb') as out:
            out.write(encoded)
    assert (gzip.decompress(encoded) if compress else encoded)==raw
    rows.append({'source':str(p),'selected':str(target.relative_to(A)),
                 'encoding':'gzip' if compress else 'identity','raw_bytes':len(raw),'raw_sha256':sha(raw),
                 'selected_bytes':len(encoded),'selected_sha256':sha(encoded)})
prior=json.loads(Path('/tmp/mr3_p2a0_v7_assets_before_checks_archive_v1.json').read_text())
for r in prior['files']:
    assert sha((A/r['path']).read_bytes())==r['sha256']
formal=json.loads((A/'build_drive_binary_v7.json').read_text())
so=A/'binary/libmr3_gazebo_diff_drive.so.gz'
assert sha(so.read_bytes())==formal['archived_library_encoded_sha256']
assert sha(gzip.decompress(so.read_bytes()))==formal['library_sha256']
result={'schema':'mr3-p2a0-v7-offline-check-originals-v1','passed':True,
        'base_source_freeze':'448ceb6a26e9fef1f1c47e26292ba64c1b93c732',
        'files':rows,'historical_canonical_reuse':reused,'excluded_test_executables':excluded,
        'deferred_current_consumer_sources':deferred,'unavailable_referenced_paths':missing,
        'prior_assets_checked_unchanged':len(prior['files']),
        'intentional_current_binary_unchanged':{'path':'binary/libmr3_gazebo_diff_drive.so.gz','decoded_sha256':formal['library_sha256']},
        'historical_review_source_aliases':{
            '/tmp/mr3_independent_drive_trace_v3.py':'independent/mr3_independent_drive_trace_v3_before_release_scope.py',
            '/tmp/mr3_independent_drive_trace_v3_tests.py':'independent/mr3_independent_drive_trace_v3_tests_before_release_scope.py'},
        'scope':'Original offline receipts copied unchanged. All stdout .txt/.log losslessly gzip with raw/encoded SHA mapping; old paths inside receipts remain original. Intermediate/failing histories retained. No new tests/native or physical credit.'}
out=I/'offline_checks_originals_manifest_v1.json'
with out.open('x') as stream:
    stream.write(json.dumps(result,indent=2,allow_nan=False)+'\n')
print(json.dumps({'manifest':str(out),'sha256':sha(out.read_bytes()),'copied':len(rows),
                  'gzip_stdout':sum(x['encoding']=='gzip' for x in rows),'historical_reused':len(reused),
                  'excluded_ELF':len(excluded),'deferred':len(deferred),'missing':missing},indent=2))
