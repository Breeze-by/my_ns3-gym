"""Opaque copy of four stopped V63 preparation roots; never follows links."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile
import time

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
B=W/'report/assets/20261024_mr3_p2a_v63_profile_description/checks/preparation_history_v1'
ROOTS=[Path('/tmp/mr3_p2a_v63_profile_description_candidate_v1'),
       Path('/tmp/mr3_p2a_v63_profile_description_candidate_v2'),
       Path('/tmp/mr3_p2a_v63_profile_description_candidate_v3'),
       Path('/tmp/mr3_p2a_v63_canonical_cpu_toys_v1')]
RESTORE=Path('/tmp/mr3_p2a_v63_preparation_history_restore_v1')


def require(value,reason):
    if not value:raise ValueError(reason)


def fp(value):
    return {key:getattr(value,key) for key in ('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')}


def write(path,value):
    with path.open('x') as output:json.dump(value,output,indent=2);output.write('\n')


def identity():
    tail=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return dict(pid=os.getpid(),parent=int(tail[1]),group=int(tail[2]),session=int(tail[3]),start_ticks=int(tail[19]))


def scan():
    rows=[]
    def visit(path,member):
        before=path.lstat()
        row=dict(original=str(path),member=member,stat=fp(before),uid=before.st_uid,gid=before.st_gid)
        if stat.S_ISLNK(before.st_mode):row.update(kind='symlink',literal_target=os.readlink(path))
        elif stat.S_ISDIR(before.st_mode):row['kind']='directory'
        elif stat.S_ISREG(before.st_mode):row.update(kind='regular',bytes=before.st_size)
        else:raise ValueError('unsupported special input: '+str(path))
        rows.append(row)
        if row['kind']=='directory':
            for child in sorted(path.iterdir()):visit(child,member+'/'+child.name)
    for root in ROOTS:
        require(root.is_absolute() and root.parent==root.parent.resolve(strict=True),'input root parent not canonical')
        visit(root,root.name)
    return rows


class HashingReader:
    def __init__(self,stream):self.stream,self.digest,self.bytes=stream,hashlib.sha256(),0
    def read(self,size=-1):
        raw=self.stream.read(size);self.digest.update(raw);self.bytes+=len(raw);return raw


def main():
    started=time.monotonic_ns();write(B/'packer_identity_v1.json',identity())
    before=scan();require(not RESTORE.exists(),'restore verification directory exists')
    package=B/'preparation_history_v1.tar.gz'
    with package.open('xb') as encoded:
        with gzip.GzipFile(filename='',mode='wb',fileobj=encoded,mtime=0) as compressed:
            with tarfile.open(fileobj=compressed,mode='w|',format=tarfile.PAX_FORMAT) as archive:
                for row in before:
                    source=Path(row['original']);require(fp(source.lstat())==row['stat'],'source changed before archive')
                    info=tarfile.TarInfo(row['member']);info.mode=stat.S_IMODE(row['stat']['st_mode'])
                    info.uid,info.gid=row['uid'],row['gid'];info.mtime=row['stat']['st_mtime_ns']/10**9
                    if row['kind']=='directory':info.type=tarfile.DIRTYPE;archive.addfile(info)
                    elif row['kind']=='symlink':
                        require(os.readlink(source)==row['literal_target'],'link literal changed')
                        info.type=tarfile.SYMTYPE;info.linkname=row['literal_target'];archive.addfile(info)
                    else:
                        info.size=row['bytes']
                        with os.fdopen(os.open(source,os.O_RDONLY|os.O_NOFOLLOW),'rb') as stream:
                            require(fp(os.fstat(stream.fileno()))==row['stat'],'opened source differs')
                            reader=HashingReader(stream);archive.addfile(info,reader)
                            require(reader.bytes==row['bytes'] and fp(os.fstat(stream.fileno()))==row['stat'],'short/changed source read')
                            row['sha256']=reader.digest.hexdigest()
                    require(fp(source.lstat())==row['stat'],'source changed during archive')
    require(package.stat().st_size<=64*1024**2,'opaque package exceeds64MiB')
    package_sha=hashlib.sha256(package.read_bytes()).hexdigest()
    after=scan()
    require([{k:v for k,v in row.items() if k!='sha256'} for row in before]==after,'original membership/metadata changed')
    RESTORE.mkdir();expected={row['member']:row for row in before};seen=set();restored=[]
    with tarfile.open(package,'r:gz') as archive:
        for member in archive:
            require(member.name in expected and member.name not in seen,'extra/duplicate restore member')
            parts=Path(member.name).parts;require(not Path(member.name).is_absolute() and '..' not in parts,'unsafe archive member')
            target=RESTORE/member.name;require(target.parent==target.parent.resolve(strict=True),'restore parent has a link')
            row=expected[member.name];seen.add(member.name)
            if row['kind']=='directory':
                require(member.isdir(),'directory member type changed');target.mkdir()
            elif row['kind']=='symlink':
                require(member.issym() and member.linkname==row['literal_target'],'symlink metadata changed')
                os.symlink(member.linkname,target)
                require(stat.S_ISLNK(target.lstat().st_mode) and os.readlink(target)==row['literal_target'],'symlink restore differs')
            else:
                require(member.isfile() and member.size==row['bytes'],'regular member type/size changed')
                stream=archive.extractfile(member);digest=hashlib.sha256();count=0
                with target.open('xb') as output:
                    while True:
                        raw=stream.read(1024*1024)
                        if not raw:break
                        output.write(raw);digest.update(raw);count+=len(raw)
                require(count==row['bytes'] and digest.hexdigest()==row['sha256'],'full restored bytes/SHA differ')
                os.chmod(target,member.mode)
                # A separate full restored-file hash verifies actual written bytes.
                require(hashlib.sha256(target.read_bytes()).hexdigest()==row['sha256'],'on-disk restore SHA differs')
                restored.append(dict(member=member.name,bytes=count,sha256=digest.hexdigest()))
    require(seen==set(expected),'missing restore members')
    require(package_sha==hashlib.sha256(package.read_bytes()).hexdigest(),'package changed during restore verification')
    require(after==scan(),'original membership changed before final proof')
    inventory=dict(schema='mr3-v63-opaque-preparation-history-inventory-v1',roots=list(map(str,ROOTS)),entries=before,
        regular_count=sum(row['kind']=='regular' for row in before),link_count=sum(row['kind']=='symlink' for row in before),
        directory_count=sum(row['kind']=='directory' for row in before),regular_bytes=sum(row.get('bytes',0) for row in before),
        package=dict(path=str(package),bytes=package.stat().st_size,sha256=package_sha),
        no_symlink_following=True,original_membership_before_after_stable=True,original_profile_inputs_read=False)
    write(B/'inventory_v1.json',inventory)
    write(B/'restore_verification_v1.json',dict(schema='mr3-v63-opaque-preparation-history-restore-v1',passed=True,
        package=inventory['package'],restored_regular_files=restored,restored_members=len(seen),
        restored_links_literal_only=True,restore_directory=str(RESTORE),all_regular_bytes_and_SHA_match=True,
        original_membership_before_after_stable=True,started_monotonic_ns=started,ended_monotonic_ns=time.monotonic_ns(),
        scientific_qualification=False,capacity_qualified=False,native_runs=0,model_runs=0))
    print(json.dumps({key:inventory[key] for key in ('regular_count','link_count','directory_count','regular_bytes','package')}))
    return 0


if __name__=='__main__':raise SystemExit(main())
