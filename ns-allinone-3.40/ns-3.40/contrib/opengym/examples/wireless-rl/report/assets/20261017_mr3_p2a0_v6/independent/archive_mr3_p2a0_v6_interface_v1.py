"""Losslessly preserve the complete closed v6 interface and original audit outcomes."""
from pathlib import Path
from decimal import Decimal
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tarfile

REPO = Path('/home/zhuyulab/ns3-workspace')
W = REPO/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261017_mr3_p2a0_v6'
I = A/'independent'
ACCOUNT = A/'accounting'
PACK = Path('/tmp/v6_selected_interface')
NATIVE = A/'native/interface'
FREEZE = '448ceb6a26e9fef1f1c47e26292ba64c1b93c732'
sha = lambda b: hashlib.sha256(b).hexdigest()
load = lambda p: json.loads(p.read_text())
ns = lambda value: int(Decimal(str(value))*1_000_000_000)

def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as out:
        out.write(json.dumps(value, indent=2, allow_nan=False)+'\n')

def copy(path, directory, compress=False):
    raw = path.read_bytes()
    target = directory/(path.name+('.gz' if compress else ''))
    target.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        data = io.BytesIO()
        with gzip.GzipFile(filename='', mode='wb', fileobj=data, mtime=0) as out:
            out.write(raw)
        encoded = data.getvalue()
    else:
        encoded = raw
    if target.exists():
        assert target.read_bytes() == encoded, str(target)
    else:
        with target.open('xb') as out:
            out.write(encoded)
    assert (gzip.decompress(encoded) if compress else encoded) == raw
    return {'source': str(path), 'selected': str(target.relative_to(A)),
            'encoding': 'gzip' if compress else 'identity', 'raw_bytes': len(raw),
            'raw_sha256': sha(raw), 'selected_bytes': len(encoded),
            'selected_sha256': sha(encoded)}

before = load(Path('/tmp/mr3_p2a0_v6_assets_before_native_archive_v1.json'))
for r in before['files']:
    assert sha((A/r['path']).read_bytes()) == r['sha256']
m = load(PACK/'manifest.json')
for r in m['files']:
    encoded = (PACK/r['selected']).read_bytes()
    raw = gzip.decompress(encoded) if r['encoding']=='gzip' else encoded
    assert len(encoded)==r['selected_bytes'] and sha(encoded)==r['selected_sha256']
    assert len(raw)==r['raw_bytes'] and sha(raw)==r['raw_sha256']
    assert raw==Path(r['source']).read_bytes()
assert m['source_files']==411
assert sum('/drive_model_' in x['selected'] for x in m['files'])==3
assert sum('/drive_tb' in x['selected'] and x['selected'].endswith('.jsonl.gz') for x in m['files'])==3
shutil.copytree(PACK, NATIVE)
rows=[]
for p in sorted(Path('/tmp').glob('mr3_p2a0_v6_interface*')):
    if p.is_file() and p.suffix in ('.json','.txt','.log'):
        if p.suffix=='.json':
            json.loads(p.read_text())
        rows.append(copy(p, ACCOUNT if p.name.endswith('_launch.json') or p.suffix=='.log' else I,
                         p.suffix=='.log'))
for n in ['mr3_p2a0_v6_source_preflight.json','mr3_p2a0_v6_binaryproof.json',
          'source_bindings_448ceb6a26e9.json','source_bindings_448ceb6a26e9.tar.gz',
          'mr3_p2a0_v6_buildproof_preflight.py','mr3_readonly_v4_interface_review.py',
          'mr3_readonly_terminal_live.py','mr3_readonly_v6_drive_math_live.py',
          'mr3_v6_guard_drive_latency.py','mr3_p2a_package.py']:
    rows.append(copy(Path('/tmp')/n,I))
rows.append(copy(Path(__file__),I))
source=load(Path('/tmp/source_bindings_448ceb6a26e9.json'))
encoded=Path('/tmp/source_bindings_448ceb6a26e9.tar.gz').read_bytes()
assert sha(encoded)==source['encoded_sha256']
raw_tar=gzip.decompress(encoded)
with tarfile.open(fileobj=io.BytesIO(raw_tar)) as archive:
    assert len(archive.getmembers())==source['source_count']==95
    for r in source['files']:
        raw=archive.extractfile(r['path']).read()
        assert len(raw)==r['bytes'] and sha(raw)==r['sha256']
        assert raw==subprocess.check_output(['git','show',FREEZE+':'+r['path']],cwd=REPO)
R=Path(m['source']);E=R/'worker0/episode001_open_101'
trans=[json.loads(x) for x in (E/'transitions.jsonl').read_text().splitlines()]
physics=[json.loads(x) for x in (E/'physics.jsonl').read_text().splitlines()]
adapter=[json.loads(x) for x in (E/'adapter.jsonl').read_text().splitlines()]
steps=[x for x in trans if x['kind']=='step'];resets=[x for x in trans if x['kind']=='reset']
actions=[x for x in adapter if x['kind']=='action']
release=trans[0]['info']['release_time_ns'];last=ns(trans[-1]['snapshot']['source_stamp']);end=physics[-1]['end_time_ns']
assert len(steps)==len(actions)==20 and len(resets)==1
assert last-release==sum(ns(x['info']['physical_dt']) for x in steps)==20_000_000_000
assert end-last==220_000_000 and release-physics[0]['start_time_ns']==13_000_000
returned_ids={x['info']['command']['command_id'] for x in steps}
unreturned=[x['payload']['command_id'] for x in actions if x['payload']['command_id'] not in returned_ids]
assert not unreturned
benchmark=load(R/'benchmark_summary.json');launch=load(Path('/tmp/mr3_p2a0_v6_interface_launch.json'))
full=load(Path('/tmp/mr3_p2a0_v6_interface_full_audit.json'));angular=load(Path('/tmp/mr3_p2a0_v6_interface_fixed_angular_v1.json'));physical=load(Path('/tmp/mr3_p2a0_v6_interface_fixed_physics_v1.json'));drive=load(Path('/tmp/mr3_p2a0_v6_interface_drive_review_v1.json'))
assert full['passed'] and angular['passed'] and physical['passed'] and not drive['passed']
assert len(full['source_bindings'])==95 and launch['freeze']==FREEZE
write(ACCOUNT/'interface_accounting_v1.json',{
    'schema':'mr3-p2a0-v6-interface-accounting-v1','freeze':FREEZE,
    'benchmark_raw_passed':benchmark['passed'],'overall_preparation_passed':False,
    'returned_reset_api_rows':len(resets),'returned_step_api_rows':len(steps),
    'actual_adapter_actions':len(actions),'unreturned_action_ids':unreturned,
    'release_time_ns':release,'last_returned_snapshot_ns':last,'final_physics_clock_ns':end,
    'returned_effective_ns':sum(ns(x['info']['dt']) for x in steps),
    'returned_physical_ns':sum(ns(x['info']['physical_dt']) for x in steps),
    'cleanup_physics_ns':end-last,'controlled_warmup_alignment_ns':release-physics[0]['start_time_ns'],
    'post_release_physics_ns':end-release,'benchmark_wall_sec':benchmark['wall_sec_including_all_attempts'],
    'launcher_wall_sec':launch['wall_duration_sec'],'launcher_returncode':launch['returncode'],
    'stage_outcomes':{'interface':{'status':'FAIL','cause':'required new independent driver reader fails; original result retained','native_full_audit_passed':full['passed'],'fixed_angular_passed':angular['passed'],'fixed_physics_passed':physical['passed'],'fixed_driver_passed':drive['passed'],'fixed_driver_error':drive['episodes'][0]['error']},
                      'terminal':{'status':'SKIP','reason':'required interface reader failed; declared stop rule'},
                      'reset':{'status':'SKIP','reason':'required interface reader failed; declared stop rule'},
                      'deadline':{'status':'SKIP','reason':'required interface reader failed; declared stop rule'}},
    'scope':'Actual normal truncated engineering prefix; reader/harness failure is retained separately from successful existing native/scalar/physical subaudits. No95%/policy/GPU/pilot credit; no second-stage native run.'})
write(I/'interface_originals_manifest_v1.json',{
    'schema':'mr3-p2a0-v6-interface-original-reviews-v1','freeze':FREEZE,'files':rows,
    'native_manifest':'native/interface/manifest.json','native_manifest_sha256':sha((NATIVE/'manifest.json').read_bytes()),
    'scope':'Original reviews, scripts and source payloads copied losslessly; original FAIL outputs are unchanged.'})
for r in before['files']:
    assert sha((A/r['path']).read_bytes())==r['sha256']
write(I/'interface_archive_verification_v1.json',{
    'schema':'mr3-p2a0-v6-interface-canonical-verification-v1','passed':True,'freeze':FREEZE,
    'prior_assets_unchanged':len(before['files']),'prior_asset_bindings':before['files'],
    'native_source_files':m['source_files'],'raw_bytes':m['raw_bytes'],'selected_bytes':m['selected_bytes'],
    'native_selected_encoded_sha_decoded_sha_original_equal':True,
    'effective_sdf_count':3,'drive_raw_jsonl_count':3,
    'source_payload_files':95,'source_payload_encoded_sha256':sha(encoded),
    'source_payload_decoded_tar_sha256':sha(raw_tar),'source_payload_matches_exact_git_bytes':True,
    'original_reviews_archived':len(rows),'detached_full_audit_rerun':False,
    'scope':'Exact native/review/source archive only; original95-binding full auditPASS and required original driverFAIL both retained. No detached replacement audit or change to result.'})
files=[{'path':str(p.relative_to(A)),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())}
       for p in sorted(A.rglob('*')) if p.is_file()]
write(A/'inventory_native_v2.json',{'schema':'mr3-p2a0-v6-native-inventory-v2','freeze':FREEZE,
    'self_excluded':True,'prefreeze_assets_preserved':len(before['files']),'files':files,
    'scope':'Native interface and contemporaneous original independent evidence appended after original prefreeze assets; laterdiagnostics require separate incremental inventory.'})
print(json.dumps({'passed':True,'native_files':m['source_files'],'raw_bytes':m['raw_bytes'],
                  'selected_bytes':m['selected_bytes'],'originals':len(rows),'source_files':95,
                  'prior_assets_unchanged':len(before['files']),'inventory_files':len(files),
                  'inventory_sha256':sha((A/'inventory_native_v2.json').read_bytes())},indent=2))
