import hashlib
import json
from pathlib import Path
import shutil

R=Path('/home/zhuyulab/ns3-workspace')
W=R/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v26_capture'
OLD=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
def copy(src,dst,expected):
    src,dst=Path(src),Path(dst)
    assert sha(src)==expected
    if dst.exists():
        assert sha(dst)==expected
        return
    dst.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(src,dst)
    assert sha(dst)==expected

ci_path=Path('/tmp/mr3_p2a0_v26_capture_consistency_proposal_v2/handoff_v2.json')
assert sha(ci_path)=='96b3a0bb4fe12ca6c25714dbaaca5f48ddd7e4ffe21096f5ee8a4a69af2bd74b'
ci=json.loads(ci_path.read_text());assert ci['source_status']=='STOP'
copy(ci['module']['source'],A/'independent/mr3_v26_smoother_custody_v2.py',ci['module']['sha256'])
harness=next(row for row in ci['files'] if Path(row['path']).name=='counterexamples_v1.py')
copy(harness['path'],A/'independent/counterexamples_v1.py',harness['sha256'])
auditor=W/'mr3_learning/audit_ppo.py'
assert sha(auditor) in ('7d1a1a70761115b2582d7c08315e42cce97ddacdae067e066fa1e5487853294d', ci['auditor']['sha256'])
assert sha(ci['auditor']['source'])==ci['auditor']['sha256']
shutil.copyfile(ci['auditor']['source'],auditor)

rt_path=Path('/tmp/mr3_p2a0_v26_matrix_proposal_v1/handoff_final_v1.json')
assert sha(rt_path)=='2300ec0bba5dd196b71c3c7caeebce908b5e50f0cc77f5881de88bd253ddb705'
rt=json.loads(rt_path.read_text());assert rt['source_status']==rt['metadata_status']=='STOP'
for row in rt['files']:
    if row['path'].endswith('predeclared_plan_v26.json'):
        draft_path=Path(row['source']);assert sha(draft_path)==row['sha256']
    else: copy(row['source'],R/row['path'],row['sha256'])

draft=json.loads(draft_path.read_text())
plan=json.loads(draft_path.read_text())
bindings={row['path']:row['sha256'] for row in plan['independent_source_bindings']}
oldplan=json.loads((OLD/'predeclared_plan_v25.json').read_text())
previous={row['path']:row['sha256'] for row in oldplan['independent_source_bindings']}
assert len(bindings)==230 and len(previous)==222
assert set(previous)<=set(bindings)
changed=[p for p in previous if previous[p]!=bindings[p]]
assert changed==[str(auditor.relative_to(R))]
assert sum(previous[p]==bindings[p] for p in previous)==221
assert len(set(bindings)-set(previous))==8
for path,digest in bindings.items(): assert sha(R/path)==digest,path
assert plan['max_api_records']==608 and plan['max_submitted_script_decisions']==596
assert plan['max_total_wall_seconds']==18000 and plan['native_admission_granted'] is False
assert sum(len(s['required_audit_receipts']) for s in plan['stages'])==34

plan['source_binding']='One new clean pushed exact40 V26 freeze supplied to every real CLI and receipt. A25 production C++/ENV/binaries and original34 mathematical gates retained. Only observational custody helper and its fixed shared-loader path/SHA change; no cross-freeze native PASS.'
plan['readiness']={'status':'ready','pending_bindings':[],
 'scope':'Root verified all230 actual bindings (221 old exact, one auditor identity refresh, eight additions). Actual native admission still requires fresh clean-pushed exact40 Conda preflight and passive watcher START before sole parent.'}
plan['new_source_bindings_pending']=[]
plan['authorized_current_binding_refresh_pending']['status']='root_reviewed_exact_current_source_declared; actual_fresh_freeze_preflight_required'
v25=plan['v25_smoother_clock_revision']
v25['status']='historical_V25_interface32_and_old_gates_passed_but_new_smoother_capture035_failed; later3_SKIPPED'
v25['historical_identity_scope']='current_auditor_sha256 and current_environment_sha256 in this V25 block are historical V25 identities; V26 actual pins are in independent_source_bindings.'
plan['v26_capture_revision']['root_review']='Exactac90/f45 source promotion after independent single-case green; V25 capture035 subpredicate remains unknown and originalFAIL unchanged. Fresh full4stage mandatory.'
changed_keys=[k for k in plan if plan[k]!=draft[k]]
assert set(changed_keys)=={'source_binding','readiness','new_source_bindings_pending','authorized_current_binding_refresh_pending','v25_smoother_clock_revision','v26_capture_revision'}
final=A/'predeclared_plan_v26.json'
final.write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
out={'schema':'mr3-v26-root-source-promotion-v1','passed':True,
 'draft_sha256':sha(draft_path),'final_plan_sha256':sha(final),'root_changed_top_keys':changed_keys,
 'actual_bindings':230,'old_exact':221,'old_changed':changed,'new_count':8,
 'mandatory_receipts':34,'max_API':608,'max_decisions':596,'ceiling':18000,
 'native_admission_granted':False,'Cxx_ENV_binaries_changed':False,
 'scope':'Source readiness only. Actual clean-pushed freeze preflight and full native matrix remain pending.'}
(A/'root_preparation').mkdir()
copy(__file__,A/'root_preparation/promote_and_finalize_v2.py',sha(__file__))
(A/'root_preparation/final_plan_receipt_v1.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps(out))
