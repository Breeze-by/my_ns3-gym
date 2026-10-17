"""Append-only archival of v9 launcher CPU originals; no test/native execution."""
from pathlib import Path
import gzip
import hashlib
import json

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261017_mr3_p2a0_v9'
I=A/'independent/launcher_offline'
I.mkdir(parents=True,exist_ok=True)
sha=lambda b:hashlib.sha256(b).hexdigest()
rows=[]

def capture(source, relative, note='original stored bytes'):
    raw=source.read_bytes(); compressed=source.suffix in ('.log','.txt');destination=I/(relative+('.gz' if compressed else ''));destination.parent.mkdir(parents=True,exist_ok=True)
    if destination.exists():
        encoded=destination.read_bytes(); assert (gzip.decompress(encoded) if compressed else encoded)==raw,destination
    else:
        encoded=gzip.compress(raw,mtime=0) if compressed else raw
        with destination.open('xb') as out:out.write(encoded)
    assert (gzip.decompress(encoded) if compressed else encoded)==raw
    rows.append({'source':str(source),'selected':str(destination.relative_to(I)),'encoding':'gzip' if compressed else 'identity','raw_bytes':len(raw),'raw_sha256':sha(raw),'encoded_bytes':len(encoded),'encoded_sha256':sha(encoded),'note':note})

for path in sorted(Path('/tmp').glob('mr3_p2a0_v9_plan_launcher*')):
    if path.is_file() and path.suffix in ('.json','.py','.log','.txt'):capture(path,'originals/'+path.name)
for name in ('mr3_p2a0_v9_contract_static_runtime_final_v1.json','mr3_p2a0_v9_runtime_minimal_repair_review_v1.json','mr3_p2a0_v9_runtime_producer_review_v1.json'):
    path=Path('/tmp')/name;capture(path,'originals/'+name)
path=Path('/tmp/mr3_p2a0_v9_buildproof_preflight_before_ready_reconstructed_v1.py')
assert sha(path.read_bytes())=='fa87b3e9c4cf8ad0c68098b344cd04dfaa6dede27dbdcfd5cedcc5852de86221'
capture(path,'historical_source/'+path.name,'post-hoc exact-byte reconstruction by removing the later readiness assertion; matches first CPU receipt SHA, not an original retained file')
for name in ('predeclared_plan_v9.json','mr3_p2a0_v9_buildproof_preflight.py','mr3_p2a0_v9_launch_stage.py','mr3_p2a0_v9_plan_launcher_tests_v1.py'):
    path=Path('/tmp/mr3_p2a0_v9_draft')/name;capture(path,'draft_final/'+name,'final draft bytes, identical to handed-off canonical source; not a substitute for earlier draft bytes')
current=[A/'predeclared_plan_v9.json']+[A/'independent'/name for name in ('mr3_p2a0_v9_buildproof_preflight.py','mr3_p2a0_v9_launch_stage.py','mr3_p2a0_v9_plan_launcher_tests_v1.py')]
final_four_before={str(p):sha(p.read_bytes()) for p in current}
for path in current:
    expected=Path('/tmp/mr3_p2a0_v9_draft')/path.name;assert path.read_bytes()==expected.read_bytes()
review=json.loads(Path('/tmp/mr3_p2a0_v9_runtime_producer_review_v1.json').read_bytes())
for binding in review['source_bindings']:
    path=Path(binding['path']);assert sha(path.read_bytes())==binding['sha256'];capture(path,'reviewed_source/'+path.name,'actual final producer/test source reviewed; no native execution by this review')
static=json.loads(Path('/tmp/mr3_p2a0_v9_contract_static_runtime_final_v1.json').read_bytes())
for path,expected in [(A/'independent/mr3_p2a0_v9_contract_checks.py','7d9c65dc6173b3dab38e80cc36b4a81f84d647cebe878e252724ea0c2e15badb'),(W/'mr3_learning/audit_ppo.py',static['audit_sha256']),(W/'MR3_ENV_CONTRACT.md',static['env_sha256'])]:
    assert sha(path.read_bytes())==expected;capture(path,'reviewed_source/'+path.name)
launch=ROOT/'ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py';assert sha(launch.read_bytes())==static['reviewed_pins'][str(launch.relative_to(ROOT))];capture(launch,'reviewed_source/'+launch.name)
capture(Path(__file__),'archive_launcher_offline_v1.py','exact archive tool source; no source modifications outside this subtree')
available={row['raw_sha256'] for row in rows};unretained=[]
for path in sorted(Path('/tmp').glob('mr3_p2a0_v9_plan_launcher*.json')):
    value=json.loads(path.read_bytes())
    for key in ('sources','source_sha256','source_before','source_after'):
        entries=value.get(key,{})
        if not isinstance(entries,dict):continue
        for name,digest in entries.items():
            if isinstance(digest,str) and len(digest)==64 and digest not in available:
                unretained.append({'receipt':str(path),'field':key,'source_path':name,'recorded_source_sha256':digest,'status':'historical exact draft bytes not retained; final bytes are not relabelled as this source'})
for row in rows:
    raw=Path(row['source']).read_bytes();encoded=(I/row['selected']).read_bytes();decoded=gzip.decompress(encoded) if row['encoding']=='gzip' else encoded
    assert raw==decoded and len(raw)==row['raw_bytes'] and sha(raw)==row['raw_sha256'] and len(encoded)==row['encoded_bytes'] and sha(encoded)==row['encoded_sha256']
final_four_after={str(p):sha(p.read_bytes()) for p in current};assert final_four_before==final_four_after
payload={'schema':'mr3-v9-launcher-offline-originals-v1','passed':True,'files':rows,'unretained_historical_draft_references':unretained,'final_four_before':final_four_before,'final_four_after':final_four_after,'final_four_unchanged':True,'scope':'Append-only selected CPU originals, initial style FAILs, each actual13test stdout, versioned receipts and retained/reconstructed/final source with exact scope. Test repeats and two layouts are not unique test counts. No early information-reader source SHA/exec is invented; that review was messages only. No native/GPU/commit, no writes outside launcher_offline. Not the final asset inventory.'}
manifest=I/'originals_manifest_v1.json'
with manifest.open('x') as out:json.dump(payload,out,indent=2);out.write('\n')
receipt={'schema':'mr3-v9-launcher-offline-archive-receipt-v1','passed':True,'manifest':str(manifest),'manifest_sha256':sha(manifest.read_bytes()),'files':len(rows),'raw_bytes':sum(x['raw_bytes'] for x in rows),'encoded_bytes':sum(x['encoded_bytes'] for x in rows),'all_original_encoded_decoded_SHA_verified':True,'final_four_unchanged':True,'unretained_historical_references_explicit':len(unretained),'native_runs':0,'scope':'Archival only; canonical writes limited to launcher_offline subtree.'}
Path('/tmp/mr3_p2a0_v9_launcher_archive_receipt_v1.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt))
