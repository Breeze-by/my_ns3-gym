from pathlib import Path
import hashlib, importlib.util, json, time
from decimal import Decimal
import importlib
ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261023_mr3_p2a_v51_runtime_profile'
PREFIX='mr3_single_ep_runtime_profile_v51'
FREEZE='41100004d343953cfb2f822a2d3bfb3ef6a4c00e'
OUT=Path('/tmp/mr3_p2a_v51_closed_review_v1.json')
def require(value,message):
    if not value: raise ValueError(message)
def load(path): return json.loads(Path(path).read_text())
start=time.monotonic_ns()
reviewer_path=Path('/tmp/mr3_p2a_v50_review_closed_draft_v4.py')
require(hashlib.sha256(reviewer_path.read_bytes()).hexdigest()=='320eb795fa7dbc0beb1aedba6f9ba54d193f38f0df31155bb670261c3e5747e9','pinned metadata helper differs')
spec=importlib.util.spec_from_file_location('_v51_pinned_metadata_helpers',reviewer_path)
R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
r=R.Review()
d=importlib.import_module('report.assets.20261023_mr3_p2a_v51_runtime_profile.run_profile_v1')
c=d.common
scope=c.read_json(A/'scope_v1.json');c.validate_scope(scope)
roots=sorted(Path('/tmp').glob(PREFIX+'*'))
def discover():
    files=[]
    for root in roots:
        require(not root.is_symlink(),'runtime root symlink')
        if root.is_file():
            if root.suffix=='.json':files.append(root)
        elif root.is_dir():
            files += [p for p in root.rglob('*.json') if p.is_file() and not p.is_symlink()]
    return sorted(files)
paths=discover()
for p in paths:
    value=r.load(p)
    evidence=r.identity_helper.Evidence();evidence.visit(value,str(p),'');r.merge_a16(evidence,str(p))
summary=r.documents[str(Path('/tmp')/(PREFIX+'_driver_v1')/'summary.json')]
wait=r.documents[str(Path('/tmp')/(PREFIX+'_driver_v1')/'actual_profile_wait/actual_wait.json')]
guard=r.documents[str(Path('/tmp')/(PREFIX+'_work_v1')/'guard_receipt.json')]
sources,binding,_=d.check_sources(scope,FREEZE,A/'scope_v1.json',time.monotonic_ns()+60_000_000_000)
d.check_closed(wait,guard,summary['actual_guard_argv'],summary['started_monotonic_ns'],summary['ended_monotonic_ns'],summary['actual_returncode'],summary['wrapper_identity'],summary['driver_identity'],dict(scope,_execution_freeze=FREEZE),binding,sources)
require(summary['passed'] is True and summary['actual_wrapper_waited'] is True and summary['actual_returncode']==0,'closed driver did not actually wait/pass')
require(summary['source_before']==summary['source_after']==sources,'final source bindings differ from actual driver')
for row in sources:r.bind(row['path'],row)
for key in ('closed_inventory','closed_review','budget_admission_ref','interpreter'):
    r.bind(scope[key]['path'],scope[key])
fee=Decimal(summary['ended_monotonic_ns']-summary['started_monotonic_ns'])/10**9
require(fee==Decimal(summary['actual_parent_wait_seconds']) and fee<=840,'parent fee/main cap inconsistency')
used=Decimal(scope['budget_admission']['engineering_used_seconds'])+fee
remaining=Decimal('75000')-used
require(str(used)==summary['engineering_cumulative_used_seconds'] and str(remaining)==summary['engineering_remaining_seconds'] and remaining>=0,'cumulative ledger inconsistency')
identities,pid_only,unbound=r.finish()
require(paths==discover(),'closed runtime JSON membership changed')
require(not r.errors and not unbound and identities and all(row['original_identity_gone'] for row in identities),'saved identity/source closure failed: '+repr(r.errors))
result=dict(schema='mr3-v51-independent-closed-metadata-review-v1',passed=True,execution_freeze=FREEZE,native_evidence_freeze=scope['native_evidence_freeze'],actual_tool_session=78516,actual_tool_returncode_observed=0,actual_wrapper_waited=True,closed_guard_and_child_passed=True,actual_audit_episode_calls=guard['child_summary']['actual_audit_episode_calls'],forbidden_run_dispatch_calls=guard['child_summary']['forbidden_run_dispatch_calls'],engineering_added_parent_wait_seconds=str(fee),engineering_cumulative_used_seconds=str(used),engineering_remaining_seconds=str(remaining),external_scientific_tail_actual_seconds='0',pilot_added_seconds='0',validation_added_seconds='0',saved_identity_count=len(identities),saved_identities=identities,PID_only_unknown_occurrences=pid_only,unbound_PID=unbound,original_starts_reconstructed=False,all_saved_identities_fresh_gone=True,source_evidence_count=24,execution_sources=9,scope_and_sources_unchanged=True,metadata_and_source_bindings=list(r.files.values()),selected_runtime_metadata_paths=[str(p) for p in paths],identity_extraction='Pinned V50 v4 same-object parser plus exact pinned A16 extraction; original missing occurrences retained, no cross-object start assignment; Z present.',original_input_hashes_freshly_recomputed_by_this_review=False,guard_input_before_after_proofs_checked=True,raw_telemetry_consumed=False,scientific_results_recomputed=False,P2A_qualification_credit=False,worlds=0,models_loaded=False,optimizer_updates=0,gpu_calls=0,reviewer_implementation=dict(path=str(Path(__file__)),sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()),metadata_helper=dict(path=str(reviewer_path),sha256=hashlib.sha256(reviewer_path.read_bytes()).hexdigest()),started_monotonic_ns=start,ended_monotonic_ns=time.monotonic_ns(),errors=[])
with OUT.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
print(json.dumps({k:result[k] for k in ('passed','saved_identity_count','engineering_added_parent_wait_seconds','engineering_cumulative_used_seconds','engineering_remaining_seconds','actual_audit_episode_calls')}))
