import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
SOURCE=Path('/tmp/mr3_p2a0_v25_matrix_proposal_v1')
sha=lambda b:hashlib.sha256(b).hexdigest()
handoff=json.loads((SOURCE/'handoff_final_v1.json').read_text())
assert handoff['source_status']==handoff['metadata_status']=='STOP' and handoff['checks']['passed']
for row in handoff['files']:
    raw=Path(row['source']).read_bytes()
    assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
    dest=ROOT/row['path']
    assert dest.is_relative_to(A) and not dest.exists()
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(raw)
planpath=A/'predeclared_plan_v25.json'
original=planpath.read_bytes();plan=json.loads(original)
assert len(plan['independent_source_bindings'])==222
for row in plan['independent_source_bindings']:
    assert sha((ROOT/row['path']).read_bytes())==row['sha256'],row['path']
from importlib.util import spec_from_file_location,module_from_spec
spec=spec_from_file_location('v25_final_workers',A/'independent/mr3_v25_stage_worker_bindings_v1.py')
workers=module_from_spec(spec);spec.loader.exec_module(workers)
for stage in plan['stages']:workers.validate_worker_bindings(stage)
assert sum(len(stage['required_audit_receipts']) for stage in plan['stages'])==34
assert plan['max_api_records']==608 and plan['max_submitted_script_decisions']==596
assert plan['max_total_wall_seconds']==18000 and plan['prior_engineering_cost']['wall_seconds']==572.9355761036277
plan['authorization']='User continuation authorizes completing P2A.0. This exact full four-stage engineering plan may run once only after clean pushed exact40 source preflight passes; no PPO/pilot or later checkpoint.'
plan['source_binding']='One new clean pushed exact40 V25 freeze, supplied to every real CLI and receipt. Original110 runtime paths and original34 mathematical gates retained; only reviewed ENV/auditor identities update and fixed smoother custody appends. No cross-freeze native PASS.'
plan['readiness']=dict(status='ready',pending_bindings=[],scope='Root finalized all222 exact source bindings and reviewed deployment. Actual native admission still requires successful fresh clean-pushed exact40 preflight and passive watcher START before the sole matrix parent.')
plan['new_source_bindings_pending']=[]
plan['authorized_current_binding_refresh_pending']['status']='root_reviewed_exact_current_source_declared; actual_fresh_freeze_preflight_required'
plan['native_admission_granted']=False
plan['smoother_runtime_custody']['status']='ready_fixed_source_and_binary; live_per_episode_mapping_still_required'
old='OPEN_LOOP smoother wall timer can run while physics paused; its configured acceleration is not a sim-time physical acceleration proof'
assert plan['scope_limits'].count(old)==1
plan['scope_limits'][plan['scope_limits'].index(old)]='Historical V24 OPEN_LOOP wall timer advanced while physics paused. V25 uses node-clock timers; its finite component callback proof is not a continuous or physical acceleration proof.'
plan['v24_installation_revision']['status']='historical_V24_installation_passed_then_angular_failure_closed'
plan['v24_installation_revision']['interpretation_scope']='The auditor and ENV hashes in this historical V24 block remain the original V24 values; they are not current V25 source pins.'
plan['v25_smoother_clock_revision'].update(current_auditor_sha256='7d1a1a70761115b2582d7c08315e42cce97ddacdae067e066fa1e5487853294d',current_environment_sha256='41feac9a6d76adb839a615d7703e78e1b1c9f2ce22d55aba805387643536380e')
plan['new_execution_contracts']['nav2_smoother_timer']='Official1.1.20 activation and dynamic-frequency timers use the node clock; parameters/constraint arithmetic unchanged.'
plan['revision_reasons'].append('V25 repairs the evidenced smoother wall/simulation clock mismatch, actual canonical build and single stock/fixed component comparison pass, adds fixed source/ELF/per-episode mapping custody and derives worker addresses from actual stage CLI. All original34 mathematical and workload gates remain; this source declaration is not native/matrix PASS.')
planpath.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
final=planpath.read_bytes()
changed=[key for key in plan if json.loads(original).get(key)!=plan[key]]
expected={'authorization','source_binding','readiness','new_source_bindings_pending','authorized_current_binding_refresh_pending','smoother_runtime_custody','scope_limits','v24_installation_revision','v25_smoother_clock_revision','new_execution_contracts','revision_reasons'}
assert set(changed)==expected,changed
dest=A/'matrix_preparation';dest.mkdir()
manifest=json.loads((SOURCE/'manifest_final_v1.json').read_text())
files={}
for row in manifest['files']:
    raw=Path(row['source']).read_bytes()
    assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
    files[row['relative']]=raw
for name in ('manifest_final_v1.json','handoff_final_v1.json'):files[name]=(SOURCE/name).read_bytes()
buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
    for name,raw in sorted(files.items()):
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        info=tarfile.TarInfo(name);info.size=len(raw);info.mode=0o644
        tar.addfile(info,io.BytesIO(raw))
encoded=gzip.compress(buf.getvalue(),compresslevel=9,mtime=0)
with tarfile.open(fileobj=io.BytesIO(gzip.decompress(encoded)),mode='r:') as tar:
    assert {m.name:tar.extractfile(m).read() for m in tar.getmembers()}==files
for row in manifest['files']:assert sha(Path(row['source']).read_bytes())==row['sha256']
(dest/'originals.tar.gz').write_bytes(encoded)
for name in ('manifest_final_v1.json','handoff_final_v1.json'):shutil.copyfile(SOURCE/name,dest/name)
result=dict(schema='mr3-v25-root-final-source-plan-v1',draft_sha256=sha(original),final_sha256=sha(final),changed_top_keys=changed,source_bindings=222,mandatory_receipts=34,archive_sha256=sha(encoded),archive_bytes=len(encoded),archive_members=len(files),roundtrip=True,scope='Source-ready declaration only. Actual fresh exact40 Conda preflight required; native_admission_granted remains false until real admission receipts.')
(A/'root_preparation/final_plan_receipt_v1.json').write_text(json.dumps(result,indent=2)+'\n')
shutil.copyfile(Path(__file__),A/'root_preparation'/Path(__file__).name)
print(json.dumps(result))
