from pathlib import Path
import hashlib,importlib.util,json,os,stat,time
ROOT=Path('/home/zhuyulab/ns3-workspace');W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl';A=W/'report/assets/20261023_mr3_p2a_v51_runtime_profile';DEST=A/'closed_execution';INV=A/'closed_inventory_v1.json';FAIL=A/'closed_inventory_v1.failed.json'
LEGACY=W/'report/assets/20261022_mr3_p2a_v45_preparation_classification/collect_closed_v1.py';PIN='63d52ce389b7d61fa67f5080fa556b1f32e47b79e389800f9de55e97c40abf06'
def require(x,msg):
    if not x:raise ValueError(msg)
def load(p):return json.loads(Path(p).read_text())
require(hashlib.sha256(LEGACY.read_bytes()).hexdigest()==PIN,'pinned lossless copier differs')
spec=importlib.util.spec_from_file_location('_v51_lossless',LEGACY);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);m.A=A;m.DEST=DEST
review_path=Path('/tmp/mr3_p2a_v51_closed_review_v1.json');review=load(review_path)
require(review['passed'] and review['all_saved_identities_fresh_gone'] and review['actual_wrapper_waited'],'real runtime closure required')
require(not any(p.exists() for p in (DEST,INV,FAIL)),'exclusive archive target already exists')
extra=[Path(__file__),review_path,Path('/tmp/mr3_p2a_v51_close_metadata_v1.py'),Path('/tmp/mr3_p2a_v51_close_metadata_tool_launch_error_v0.json'),Path('/tmp/mr3_profile_installed_source_admission_v1.json'),Path('/tmp/mr3_profile_installed_source_admission_wait_v1')]
roots=[(p,'tmp',Path(p.name)) for p in sorted(Path('/tmp').glob('mr3_single_ep_runtime_profile_v51*'))]+[(p,'closure_tools',Path(p.name)) for p in extra]
def discover():
    result={};directories={}
    for root,label,suffix in roots:
        require(root.exists() and not root.is_symlink(),'missing/symlink root: '+str(root))
        pairs=[(root,suffix)] if root.is_file() else []
        if root.is_dir():
            for parent,names,files in os.walk(root,followlinks=False):
                parent=Path(parent);directories[str(parent)]=m.stamp(parent.lstat());names.sort();files.sort()
                for name in names:require(not (parent/name).is_symlink(),'directory symlink')
                for name in files:p=parent/name;pairs.append((p,suffix/p.relative_to(root)))
        for source,relative in pairs:
            before=m.regular_stamp(source);target,compressed=m.target_for(label,relative,source)
            require(source not in result,'duplicate source')
            result[source]=dict(target=target,compressed=compressed,stat=before)
    targets=[str(v['target']) for v in result.values()];require(len(targets)==len(set(targets)),'canonical target collision')
    return result,directories
def gone(row):
    p=Path('/proc')/str(row['pid'])/'stat'
    try:
        fields=p.read_text().rsplit(')',1)[1].split();return int(fields[19])!=row['start_ticks']
    except FileNotFoundError:return True
entries=[];current=None
try:
    for row in review['saved_identities']:require(gone(row),'saved runtime identity present, including Z')
    for row in review['metadata_and_source_bindings']:
        path=Path(row['path']);raw=path.read_bytes();require(hashlib.sha256(raw).hexdigest()==row['sha256'] and len(raw)==row['bytes'],'reviewed metadata/source bytes changed')
    guard=load('/tmp/mr3_single_ep_runtime_profile_v51_work_v1/guard_receipt.json')
    for row in guard['output_artifacts']:
        path=Path(row['path']);s=path.lstat();require([s.st_dev,s.st_ino,s.st_mode,s.st_size,s.st_mtime_ns,s.st_ctime_ns]==row['stat'],'guard artifact stat differs');raw=path.read_bytes();require(len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],'guard artifact bytes differ')
    before,dirs=discover();DEST.mkdir(exist_ok=False)
    for source,row in sorted(before.items()):current=str(source);entries.append(m.archive(source,row))
    require(discover()==(before,dirs),'runtime/tool membership or stats changed')
    for row in review['saved_identities']:require(gone(row),'saved runtime identity reappeared')
    value=dict(schema='mr3-v51-closed-byte-archive-v1',passed=True,byte_archive_complete=True,execution_freeze=review['execution_freeze'],native_evidence_freeze=review['native_evidence_freeze'],review_original_sha256=hashlib.sha256(review_path.read_bytes()).hexdigest(),actual_runtime_saved_identities=review['saved_identity_count'],all_saved_runtime_identities_fresh_gone=True,files=len(entries),original_bytes=sum(x['original_bytes'] for x in entries),canonical_bytes=sum(x['canonical_bytes'] for x in entries),link_count=0,entries=entries,unchanged_lossless_implementation=dict(path=str(LEGACY),sha256=PIN),scientific_results_recomputed=False,raw_original_V50_telemetry_read=False,new_qualification_credit=False,engineering_added_seconds='0',originals_deleted=False)
    m.write_json(INV,value);print(json.dumps({k:value[k] for k in ('passed','files','original_bytes','canonical_bytes','link_count')}))
except BaseException as error:
    m.write_json(FAIL,dict(passed=False,error=repr(error),last_source=current,completed_entries=entries,originals_deleted=False,partial_outputs_preserved=True));raise
