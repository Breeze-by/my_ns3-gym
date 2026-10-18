import gzip
import hashlib
import json
from pathlib import Path
ROOT=Path('/home/zhuyulab/ns3-workspace')
ROS=ROOT/'ros2_ws/ros2-multi-robot-automap'
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v24_install'
P=Path('/tmp/mr3_p2a0_v24_install_lifecycle_proposal_v1')
h=json.loads((P/'handoff_v1.json').read_bytes());assert h['author_source_and_metadata_STOP']
new=Path(h['source_path']).read_bytes();assert hashlib.sha256(new).hexdigest()==h['source_sha256']=='f82646c8434b77c42f585ac1828eda84640bac873f70cc7de6848cfbd6493473'
target=ROS/'src/multi_robot/src/mr3_ray_box_corrector.cpp'
assert hashlib.sha256(target.read_bytes()).hexdigest()=='b165ce49eaf5b3d52853cd759e4809962192d1922f0f210f5c82cff79c2a6b2a'
library=ROS/'install/multi_robot/lib/libmr3_ray_box_corrector.so'
previous=library.read_bytes();assert hashlib.sha256(previous).hexdigest()=='7be79c7f3d2cac53a9d1692aa868d91d4b9977e2b7541203ce4ffe90c605a08f'
assert gzip.decompress((A.parent/'20261018_mr3_p2a0_v22_ray_box/binary/libmr3_ray_box_corrector.so.gz').read_bytes())==previous
S=Path('/tmp/mr3_p2a0_v24_world_created_independent_review_v1')
assert hashlib.sha256((S/'stdout_v1.json').read_bytes()).hexdigest()=='da6603393c763e6bfa56116e821732c65bf56433c0af6687cc7b027739c7294f'
target.write_bytes(new)
original=Path('/tmp/mr3_p2a0_v22_canonical_build_v2.py').read_text()
text=original.replace("OUT=Path('/tmp/mr3_p2a0_v22_canonical_build_v2')","OUT=Path('/tmp/mr3_p2a0_v24_canonical_build_v1')").replace('b165ce49eaf5b3d52853cd759e4809962192d1922f0f210f5c82cff79c2a6b2a',h['source_sha256'])
assert text!=original
assert text.replace("OUT=Path('/tmp/mr3_p2a0_v24_canonical_build_v1')","OUT=Path('/tmp/mr3_p2a0_v22_canonical_build_v2')").replace(h['source_sha256'],'b165ce49eaf5b3d52853cd759e4809962192d1922f0f210f5c82cff79c2a6b2a')==original
dest=Path('/tmp/mr3_p2a0_v24_canonical_build_v1.py');assert not dest.exists();dest.write_text(text)
def copy(p,dest,sha=None):
    raw=p.read_bytes()
    if sha:assert hashlib.sha256(raw).hexdigest()==sha
    assert not dest.exists();dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw);assert dest.read_bytes()==raw
copy(Path(h['archive_path']),A/'offline/sdk/originals.tar.gz',h['archive_sha256'])
copy(Path(h['manifest_path']),A/'offline/sdk/manifest_v1.json',h['manifest_sha256'])
copy(P/'handoff_v1.json',A/'offline/sdk/handoff_v1.json')
copy(Path('/tmp/mr3_p2a0_v24_world_created_independent_review_sealed_v1.tar.gz'),A/'offline/independent_source_review/originals.tar.gz','b4603f5fb18e3caef2ca1683593bb30ffdda0a6b2e6007c89a565fa4abb8dffb')
copy(S/'sealed_manifest_v1.json',A/'offline/independent_source_review/manifest_v1.json','5a04d7242c0873729dbdb482fadad8b4ee3894428c39fe2876aa8e9afde0dc02')
copy(S/'stdout_v1.json',A/'offline/independent_source_review/review_v1.json')
Path('/tmp/mr3_p2a0_v24_source_promotion_v1.json').write_text(json.dumps({'schema':'mr3-v24-source-promotion-v1','source_sha256':h['source_sha256'],'source':h['source_path'],'target':str(target),'previous_library_sha256':hashlib.sha256(previous).hexdigest(),'previous_library_equals_A22_archive':True,'independent_review':'da6603393c763e6bfa56116e821732c65bf56433c0af6687cc7b027739c7294f','build_wrapper':str(dest),'only_wrapper_out_and_expected_cpp_changed':True,'build_schema_compatible_v22':True,'native':0},indent=2)+'\n')
print('Promoted soleCPP f826; sdk/review6 copies exact; prepared actualbuild wrapper (no native).')
