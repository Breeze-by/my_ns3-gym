"""Bind final canonical V24 library and lossless bytes; no native credit."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v24_install'
OUT=A/'binary'
assert not OUT.exists()
execution=Path('/tmp/mr3_p2a0_v24_canonical_build_v1/execution.json')
raw_execution=execution.read_bytes(); d=json.loads(raw_execution)
assert d['passed'] and d['actual_installed_probe_passed']
lib=Path(d['installed_new_library']['path']); raw=lib.read_bytes()
assert len(raw)==398080 and hashlib.sha256(raw).hexdigest()=='782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8'
assert lib.resolve()==ROOT/'ros2_ws/ros2-multi-robot-automap/build/multi_robot/libmr3_ray_box_corrector.so'
assert d['sources_after']['src/mr3_ray_box_corrector.cpp']['sha256']=='f82646c8434b77c42f585ac1828eda84640bac873f70cc7de6848cfbd6493473'
assert d['old_libraries_before']==d['old_libraries_after']
encoded=gzip.compress(raw,compresslevel=6,mtime=0)
assert gzip.decompress(encoded)==raw
OUT.mkdir(parents=True)
(OUT/'libmr3_ray_box_corrector.so.gz').write_bytes(encoded)
(OUT/'canonical_build_receipt_v1.json').write_bytes(raw_execution)
def binding(path,relative=True):
    b=path.read_bytes()
    return {'path':str(path.relative_to(W)) if relative else str(path),
            'resolved':str(path.resolve()),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
result={'schema':'mr3-v22-ray-box-actual-binary-custody-v1','passed':True,
 'scope':'Final actual canonical colcon artifact/factory/noLoad/ldd/dynamic CPU; no server/world/native/matrix/PPO credit.',
 'installed_library':binding(lib,False),
 'encoded_library':dict(binding(OUT/'libmr3_ray_box_corrector.so.gz'),encoding='gzip',decoded_bytes=len(raw),decoded_sha256=hashlib.sha256(raw).hexdigest()),
 'canonical_build_receipt':binding(OUT/'canonical_build_receipt_v1.json'),
 'sources':d['sources_after'],'old_libraries_before':d['old_libraries_before'],
 'old_libraries_after':d['old_libraries_after'],'old_four_libraries_byte_unchanged':True,
 'actual_ode_library':binding(Path('/lib/x86_64-linux-gnu/libgazebo_ode.so.11'),False),
 'decoded_bytes_full_roundtrip':True}
(OUT/'receipt_v1.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'library':result['installed_library'],'gzip':result['encoded_library'],
 'receipt':binding(OUT/'receipt_v1.json'),'build_receipt':result['canonical_build_receipt']}))
