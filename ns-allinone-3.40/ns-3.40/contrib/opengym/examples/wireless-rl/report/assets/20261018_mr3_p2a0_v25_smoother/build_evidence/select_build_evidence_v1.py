import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
B=Path('/tmp/mr3_p2a0_v25_actual_overlay_build_v1')
S=Path('/tmp/mr3_p2a0_v25_smoother_clock_source_review_v1')
sha=lambda b:hashlib.sha256(b).hexdigest()
assert not A.exists()
(A/'build_evidence').mkdir(parents=True)
(A/'source_preparation').mkdir()
for src,name in [(B/'build_receipt_v1.json','build_receipt_v1.json'),(B/'started_v1.json','build_started_v1.json'),(B/'build.stdout','build_stdout.txt'),(B/'build.stderr','build_stderr.txt'),(Path(__file__),'select_build_evidence_v1.py'),(Path('/tmp/mr3_p2a0_v25_build_overlay_v1.py'),'build_overlay_v1.py')]:
    shutil.copyfile(src,A/'build_evidence'/name)
for src,name in [(S/'handoff_v1.json','handoff_v1.json'),(S/'manifest_v1.json','manifest_v1.json'),(Path('/tmp/mr3_p2a0_v25_smoother_clock_source_preparation_v1.tar.gz'),'originals.tar.gz')]:
    shutil.copyfile(src,A/'source_preparation'/name)
receipt=json.loads((B/'build_receipt_v1.json').read_text())
rows=[]
for row in receipt['outputs']:
    p=Path(row['path']); raw=p.read_bytes()
    assert sha(raw)==row['sha256']
    encoded=gzip.compress(raw,compresslevel=9,mtime=0)
    assert gzip.decompress(encoded)==raw
    parts=[]
    for i in range(0,len(encoded),2400000):
        part=encoded[i:i+2400000]
        name=p.name+f'.gz.part{i//2400000:03d}'
        dest=A/'build_evidence'/name
        dest.write_bytes(part)
        parts.append(dict(path=str(dest.relative_to(ROOT)),sha256=sha(part),bytes=len(part)))
    rows.append(dict(**row,gzip_sha256=sha(encoded),gzip_bytes=len(encoded),parts=parts))
selected=dict(schema='mr3-v25-smoother-selected-elf-v1',outputs=rows,build_receipt=str((A/'build_evidence/build_receipt_v1.json').relative_to(ROOT)),build_receipt_sha256=sha((A/'build_evidence/build_receipt_v1.json').read_bytes()),roundtrip=True)
(A/'build_evidence/selected_elf_manifest_v1.json').write_text(json.dumps(selected,indent=2)+'\n')
print(json.dumps(selected))
