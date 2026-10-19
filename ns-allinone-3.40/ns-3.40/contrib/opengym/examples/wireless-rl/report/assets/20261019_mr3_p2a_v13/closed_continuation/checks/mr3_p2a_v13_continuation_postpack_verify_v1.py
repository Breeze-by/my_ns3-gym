"""Independent CPU verification after creator actual pack wait; no native/reader."""
from collections import Counter
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile
import time

OUT=Path('/tmp/mr3_p2a_v13_continuation_closed_packet_attempt_v1')
ROOT=Path('/home/zhuyulab/ns3-workspace')
FREEZE='0063aa233ba3008ddcc1eb09ea8068112eea3965'


def require(value,message):
    if not value:raise ValueError(message)


def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block)
    return digest.hexdigest()


def sig(path):
    s=Path(path).stat()
    return [s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns]


def bound(path):
    path=Path(path)
    return {'path':str(path),'bytes':path.stat().st_size,'sha256':sha(path)}


def identity(pid):
    try:raw=Path('/proc/%d/stat'%pid).read_text()
    except FileNotFoundError:return None
    fields=raw[raw.rfind(')')+2:].split()
    return {'pid':pid,'start_ticks':int(fields[19])}


class PartsReader(io.RawIOBase):
    def __init__(self,paths):
        self.paths=iter(paths)
        self.current=None
        super().__init__()
    def readable(self):return True
    def readinto(self,buffer):
        view=memoryview(buffer);used=0
        while used<len(view):
            if self.current is None:
                path=next(self.paths,None)
                if path is None:break
                self.current=path.open('rb')
            count=self.current.readinto(view[used:])
            if count:used+=count
            else:self.current.close();self.current=None
        return used
    def close(self):
        if self.current is not None:self.current.close();self.current=None
        super().close()


def main():
    manifest_path=OUT/'manifest.json';manifest=json.loads(manifest_path.read_bytes())
    wait=json.loads((OUT/'checks/pack_actual_child_wait.json').read_bytes())
    creator=json.loads((OUT/'checks/creator_actual_tool_results_final_v1.json').read_bytes())
    require(wait['actual_wait_returncode']==0 and not wait['wait_exceptions'],'actual CPU child wait not successful')
    require(creator['actual_pack_poll_tools'][-1]['exit_code']==0,'actual creator final tool exit not0')
    require(wait['manifest']==bound(manifest_path),'CPU receipt does not bind actual sealed manifest')
    original_manifest=bound(manifest_path)
    require(manifest['file_count']==len(manifest['files'])==4296,'actual inventory count differs from selected4296')
    require(manifest['raw_bytes']==sum(row['bytes'] for row in manifest['files'])==4343294556,'actual selected raw size differs')
    direct=[]
    for row in manifest['direct_files']:
        path=OUT/row['path']
        require(path.resolve().is_relative_to(OUT),'unsafe direct path')
        require(path.stat().st_size==row['bytes'] and sha(path)==row['sha256'],'direct file differs: '+row['path'])
        direct.append(row)
    combined=hashlib.sha256();total=0;parts=[]
    for row in manifest['parts']:
        path=OUT/row['path']
        require(path.resolve().is_relative_to(OUT),'unsafe part path')
        require(0<path.stat().st_size==row['bytes']<=49_000_000,'part size differs')
        require(sha(path)==row['sha256'],'part SHA differs')
        with path.open('rb') as source:
            for block in iter(lambda:source.read(1024*1024),b''):combined.update(block);total+=len(block)
        parts.append(row)
    require(total==manifest['archive_bytes'] and combined.hexdigest()==manifest['archive_sha256'],'concatenated archive differs')
    expected={row['path']:row for row in manifest['files']};seen=set()
    require(len(expected)==len(manifest['files']),'duplicate inventory member')
    with io.BufferedReader(PartsReader([OUT/row['path'] for row in parts])) as joined:
        with gzip.GzipFile(fileobj=joined,mode='rb') as zipped:
            with tarfile.open(fileobj=zipped,mode='r|') as archive:
                for member in archive:
                    require(member.isfile() and member.name in expected and member.name not in seen,'unexpected/duplicate member')
                    digest=hashlib.sha256();size=0;seen.add(member.name)
                    with archive.extractfile(member) as source:
                        for block in iter(lambda:source.read(1024*1024),b''):digest.update(block);size+=len(block)
                    require(size==expected[member.name]['bytes'] and digest.hexdigest()==expected[member.name]['sha256'],'member differs: '+member.name)
            while zipped.read(1024*1024):pass
    require(seen==set(expected),'member missing')
    verification=json.loads((OUT/'verification_only_bindings.json').read_bytes())
    require(Counter(row['group'] for row in verification)=={'frozen_source':279,'frozen_elf':10},'verification binding set differs')
    for row in verification:
        path=Path(row['path'])
        require(Path(row['original_binding_path']).resolve(strict=True)==path,'verification target changed')
        require(sig(path)==row['stat'] and sha(path)==row['sha256'] and sig(path)==row['stat'],'frozen source/ELF changed')
    for row in manifest['files']:
        require(sig(row['original_path'])==row['stat'],'raw source stat changed after pack: '+row['original_path'])
    inventory=json.loads((OUT/'inventory_draft.json').read_bytes())
    for tree in inventory['directory_membership']:
        root=Path(tree['path']);rows=[]
        for path in sorted(root.rglob('*')):
            require(not path.is_symlink() and (path.is_file() or path.is_dir()),'selected tree changed type')
            rows.append([path.relative_to(root).as_posix(),'directory' if path.is_dir() else 'file'])
        require(rows==tree['entries'],'selected directory membership changed after pack')
    preproof=json.loads(Path('/tmp/mr3_p2a_v13_continuation_prepack_source_absence_proof_v1.json').read_bytes())
    for row in preproof['actual_identity_observations']:
        saved=row['saved'];current=identity(saved['pid'])
        require(current is None or current['start_ticks']!=saved['start_ticks'],'saved runtime identity present again')
    cpu_identities=[]
    for key in ('coordinator_identity','child_identity'):
        saved=wait[key];current=identity(saved['pid']) if saved else None
        require(saved is not None and (current is None or current['start_ticks']!=saved['start_ticks']),'CPU archiver identity not proved gone')
        cpu_identities.append({'saved':saved,'current':current,'same_identity_present':False})
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    remote=subprocess.check_output(['git','rev-parse','origin/main'],cwd=ROOT,text=True).strip()
    require(head==FREEZE,'runtime exact0063 changed before pack endcheck')
    ancestor=subprocess.run(['git','merge-base','--is-ancestor',FREEZE,'origin/main'],cwd=ROOT,check=False).returncode
    require(ancestor==0,'runtime not published ancestor')
    require(not subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),'runtime worktree changed')
    require(bound(manifest_path)==original_manifest,'sealed manifest changed during independent verification')
    result={'scope':'Independent postpack CPU check after actual creator tool rc0. Original scientific FAIL, unsubmitted audits and original unknown metadata are unchanged.',
        'manifest':original_manifest,'member_count':len(seen),'raw_bytes':manifest['raw_bytes'],
        'archive_sha256':manifest['archive_sha256'],'archive_bytes':manifest['archive_bytes'],'parts':parts,
        'independent_all_member_sha_size_roundtrip':True,'independent_gzip_eof_crc':True,
        'independent_part_sha_and_concatenation_sha':True,'all_original_input_stats_stable_after_actual_pack_wait':True,
        'directory_membership_stable_after_wait':True,'frozen_source_count':279,'frozen_elf_count':10,
        'frozen_sources_and_elfs_end_stat_sha_verified':True,'actual_runtime_saved_identity_counts':preproof['saved_identity_counts_by_scope'],
        'actual_runtime_saved_identities_still_gone':True,'cpu_pack_identities_gone':cpu_identities,
        'runtime_head_at_endcheck':head,'origin_main_at_endcheck':remote,'freeze_is_ancestor_actual_returncode':ancestor,
        'runtime_worktree_clean_at_endcheck':True,'observed_wall_monotonic_ns':time.monotonic_ns(),
        'actual_child_wait_returncode':wait['actual_wait_returncode'],'actual_child_wait_wall_seconds':wait['actual_child_wait_wall_seconds'],
        'actual_creator_final_tool_returncode':creator['actual_pack_poll_tools'][-1]['exit_code'],
        'actual_creator_tool_final_poll_wall_seconds':creator['actual_pack_poll_tools'][-1]['wall_time_seconds'],
        'creator_external_total_phase_wall_seconds':None,
        'timing_scope':'Final poll wall is not total pack wall. Child wait wall is exact nanosecond difference. No full external phase start/end was exposed; no native engineering charge added.'}
    path=OUT/'checks/postpack_verification_v1.json'
    with path.open('x') as target:json.dump(result,target,indent=2,allow_nan=False);target.write('\n')
    print(json.dumps({'verification':bound(path),'manifest':original_manifest,'archive_sha256':manifest['archive_sha256'],'parts':parts,'actual_child_wait_wall_seconds':wait['actual_child_wait_wall_seconds'],'actual_creator_tool_returncode':0}),flush=True)


if __name__=='__main__':main()
