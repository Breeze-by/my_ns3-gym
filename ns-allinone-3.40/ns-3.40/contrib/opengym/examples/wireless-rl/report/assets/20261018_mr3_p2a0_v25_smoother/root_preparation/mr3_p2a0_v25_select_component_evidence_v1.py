import gzip
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path('/home/zhuyulab/ns3-workspace')
A=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v25_smoother'
OUT=A/'component_probe'
OUT.mkdir(exist_ok=False)
records=[]
sha=lambda b:hashlib.sha256(b).hexdigest()
def copy(src,dst):
    raw=src.read_bytes();before=src.stat()
    dst.parent.mkdir(parents=True,exist_ok=True)
    assert not dst.exists()
    dst.write_bytes(raw)
    assert src.read_bytes()==raw and src.stat()==before and dst.read_bytes()==raw
    records.append(dict(source=str(src),selected=str(dst.relative_to(ROOT)),sha256=sha(raw),bytes=len(raw)))
for p in sorted(Path('/tmp/mr3_p2a0_v25_actual_probe_pair_v1').iterdir()):
    assert p.is_file()
    copy(p,OUT/p.name)
for p in sorted(Path('/tmp/mr3_p2a0_v25_smoother_clock_source_review_v1/probe').iterdir()):
    assert p.is_file()
    copy(p,OUT/'source'/p.name)
C=Path('/tmp/mr3_p2a0_v25_actual_probe_compile_v1')
for name in ('started_v1.json','compile_receipt_v1.json','compile.stdout','compile.stderr'):
    copy(C/name,OUT/'compile'/name)
for name in ('CMakeCache.txt','compile_commands.json','CMakeFiles/smoother_clock_probe.dir/link.txt'):
    copy(C/'build'/name,OUT/'compile'/name.replace('/','_'))
probe=C/'build/smoother_clock_probe'
raw=probe.read_bytes()
encoded=gzip.compress(raw,compresslevel=9,mtime=0)
assert gzip.decompress(encoded)==raw
dest=OUT/'compile/smoother_clock_probe.gz'
dest.write_bytes(encoded)
records.append(dict(source=str(probe),selected=str(dest.relative_to(ROOT)),sha256=sha(encoded),bytes=len(encoded),raw_sha256=sha(raw),raw_bytes=len(raw)))
R=Path('/tmp/mr3_p2a0_v25_overlay_resolution_v1')
for p in sorted(R.iterdir()):
    assert p.is_file()
    copy(p,A/'build_evidence/resolution'/p.name)
for p in (Path(__file__),Path('/tmp/mr3_p2a0_v25_compile_probe_v1.py'),Path('/tmp/mr3_p2a0_v25_resolve_overlay_v1.py'),Path('/tmp/mr3_p2a0_v25_append_environment_v1.py'),Path('/tmp/mr3_p2a0_v25_environment_append_v1.json')):
    copy(p,A/'root_preparation'/p.name)
report=dict(schema='mr3-v25-selected-component-evidence-v1',files=records,scope='Closed single stock/fixed component pair plus actual single canonical package/probe build and read-only overlay resolution. No simulator/matrix/PPO credit.',all_sources_stable=True)
(OUT/'selected_manifest_v1.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(files=len(records),bytes=sum(r['bytes'] for r in records))))
