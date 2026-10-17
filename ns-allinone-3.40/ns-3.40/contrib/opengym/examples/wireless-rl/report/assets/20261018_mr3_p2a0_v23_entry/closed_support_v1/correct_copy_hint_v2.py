#!/usr/bin/python3
"""Append metadata correction only; never mutate sealed tar/manifest/originals."""
import hashlib
import json
from pathlib import Path

P=Path(__file__).parent
TREE=Path('/tmp/mr3_p2a0_v23_selected_closed_v1')
def sha(raw):return hashlib.sha256(raw).hexdigest()
oldraw=(P/'seal_v1.json').read_bytes();old=json.loads(oldraw)
assert 'A22/native' in old['selected_tree_complete_copy_rule']
expected='ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v23_entry/native/'
rows=[]
for name in ['metadata/manifest.json','native/interface/manifest.json']:
 raw=(TREE/name).read_bytes();value=json.loads(raw)
 assert value['prospective_prefix'].startswith(expected)
 for item in value['files']:
  for part in item['parts']:
   assert part['prospective_canonical'].startswith(expected)
   rows.append(part['prospective_canonical'])
new=dict(old)
new['schema']='mr3-v23-closed-pack-support-seal-v2'
new['selected_tree_complete_copy_rule']='Copy /tmp/mr3_p2a0_v23_selected_closed_v1 whole tree to W/report/assets/20261018_mr3_p2a0_v23_entry/native. Actual per-part prospective paths are already A23/native and unchanged.'
new['description_correction']={'original_seal_path':str(P/'seal_v1.json'),'original_seal_sha256':sha(oldraw),
 'old_text_retained':old['selected_tree_complete_copy_rule'],
 'scope':'Only stale upper-case A22 target prose corrected. No tar/manifest/blob/source or original scientific result modified.',
 'actual_selected_parts_checked':len(rows),'all_actual_prospective_paths_A23':True}
new['correction_script']={'path':str(Path(__file__)),'sha256':sha(Path(__file__).read_bytes())}
assert sha(Path(old['tar']['path']).read_bytes())==old['tar']['sha256']
assert sha(Path(old['manifest']['path']).read_bytes())==old['manifest']['sha256']
with (P/'seal_v2.json').open('x') as out:json.dump(new,out,indent=2,allow_nan=False);out.write('\n')
print(json.dumps({'seal_v2':str(P/'seal_v2.json'),'sha256':sha((P/'seal_v2.json').read_bytes()),
 'actual_A23_parts':len(rows),'tar_unchanged':True,'all_writers_stopped':True},indent=2))
