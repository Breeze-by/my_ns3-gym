import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=W/'report/assets/20261018_mr3_p2a0_v25_smoother'
sha=lambda b:hashlib.sha256(b).hexdigest()
source=Path('/tmp/mr3_p2a0_v25_smoother_offline_v2_v3')
dest=A/'admission_preparation_v2_v3';dest.mkdir()
for name,expected in [('manifest.json','1aac82fc97a2fcf185cafde2fd03856b02aa626b5ded820537c08b8706e1c03d'),('originals.tar.gz','6749642cc2562e59d8ae82e08ae00515de6972f25063a25cedc9c67615383c30')]:
    raw=(source/name).read_bytes();assert sha(raw)==expected
    (dest/name).write_bytes(raw)
shutil.copyfile(source/'pack_v2_v3.py',dest/'pack_v2_v3.py')
source=Path('/tmp/mr3_p2a0_v25_smoother_custody_independent_review_v1')
dest=A/'custody_independent_review';dest.mkdir()
handoff=json.loads((source/'handoff_v1.json').read_text())
for key in ('review','manifest','archive'):
    row=handoff[key];raw=Path(row['source']).read_bytes()
    assert sha(raw)==row['sha256'] and len(raw)==row['bytes']
    (dest/row['name']).write_bytes(raw)
shutil.copyfile(source/'handoff_v1.json',dest/'handoff_v1.json')
shutil.copyfile(Path(__file__),A/'root_preparation'/Path(__file__).name)
print('Selected author v2/v3 and independent custody seals.')
