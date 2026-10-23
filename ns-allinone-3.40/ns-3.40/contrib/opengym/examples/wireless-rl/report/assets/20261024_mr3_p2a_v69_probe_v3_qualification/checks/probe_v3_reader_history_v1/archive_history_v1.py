"""Opaque deterministic fixed-root CPU history; never opens original run inputs."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import tarfile

SOURCE=Path('/tmp/mr3_p2a_probe_v3_reader_candidate_v1')
OUT=Path('/tmp/mr3_p2a_probe_v3_reader_history_v1')
ARCHIVE=OUT/'reader_history_v1.tar.gz'
STABLE=('st_dev','st_ino','st_mode','st_size','st_mtime_ns','st_ctime_ns')


def identity():
    t=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()
    return dict(pid=os.getpid(),start_ticks=int(t[19]),parent=int(t[1]),group=int(t[2]),session=int(t[3]))


def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')


def sha(path):
    value=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):value.update(block)
    return value.hexdigest()


save(OUT/'saved_child_identity_v1.json',identity())
paths=[]
for base,dirs,files in os.walk(SOURCE,followlinks=False):
    for name in list(dirs):
        path=Path(base)/name
        if path.is_symlink():paths.append(path);dirs.remove(name)
    paths.extend(Path(base)/name for name in files)
rows=[]
for path in sorted(paths):
    s=path.lstat();relative=str(path.relative_to(SOURCE))
    if stat.S_ISLNK(s.st_mode):row=dict(relative=relative,kind='link',target=os.readlink(path))
    else:
        assert stat.S_ISREG(s.st_mode)
        row=dict(relative=relative,kind='regular',bytes=s.st_size,sha256=sha(path))
    assert tuple(getattr(path.lstat(),k) for k in STABLE)==tuple(getattr(s,k) for k in STABLE)
    row['source_stat']={k:getattr(s,k) for k in STABLE};rows.append(row)
with ARCHIVE.open('xb') as output:
    with gzip.GzipFile(fileobj=output,mode='wb',mtime=0,filename='') as zipped:
        with tarfile.open(fileobj=zipped,mode='w|',format=tarfile.PAX_FORMAT) as tar:
            for row in rows:
                path=SOURCE/row['relative'];info=tarfile.TarInfo(row['relative'])
                info.uid=info.gid=0;info.uname=info.gname='';info.mtime=0;info.mode=0o644
                if row['kind']=='link':
                    info.type=tarfile.SYMTYPE;info.linkname=row['target'];tar.addfile(info)
                else:
                    info.size=row['bytes']
                    with path.open('rb') as stream:tar.addfile(info,stream)
assert ARCHIVE.stat().st_size<=64*1024*1024
restore=OUT/'restore_check_v1';restore.mkdir()
with tarfile.open(ARCHIVE,'r:gz') as tar:
    members=tar.getmembers();assert [m.name for m in members]==[r['relative'] for r in rows]
    for member,row in zip(members,rows):
        rel=Path(member.name);assert not rel.is_absolute() and '..' not in rel.parts
        if row['kind']=='link':assert member.issym() and member.linkname==row['target']
        else:
            assert member.isfile();target=restore/rel;target.parent.mkdir(parents=True,exist_ok=True)
            with tar.extractfile(member) as source,target.open('xb') as output:
                for block in iter(lambda:source.read(1048576),b''):output.write(block)
            assert target.stat().st_size==row['bytes'] and sha(target)==row['sha256']
for row in rows:
    path=SOURCE/row['relative'];s=path.lstat()
    assert {k:getattr(s,k) for k in STABLE}==row['source_stat']
    assert (os.readlink(path)==row['target'] if row['kind']=='link' else sha(path)==row['sha256'])
save(OUT/'inventory_v1.json',dict(schema='mr3-probe-v3-reader-history-opaque-inventory-v1',source_root=str(SOURCE),
    entries=rows,regular_count=sum(r['kind']=='regular' for r in rows),link_count=sum(r['kind']=='link' for r in rows),
    original_bytes=sum(r.get('bytes',0) for r in rows),archive=dict(path=str(ARCHIVE),bytes=ARCHIVE.stat().st_size,sha256=sha(ARCHIVE)),
    deterministic_tar_gzip=True,complete_restore_and_source_posthash_verified=True,links_followed=False,
    original_sources_retained=True,original_V67_inputs_opened=0,native_or_scientific_credit=False))
print(json.dumps(dict(passed=True,regular_count=sum(r['kind']=='regular' for r in rows),links=sum(r['kind']=='link' for r in rows),
    original_bytes=sum(r.get('bytes',0) for r in rows),archive_bytes=ARCHIVE.stat().st_size)))
