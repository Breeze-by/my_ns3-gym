import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
B = Path('/tmp/mr3_p2a0_v24_matrix_metadata_addendum_v2')
A = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261018_mr3_p2a0_v24_install'
source, destination = B / 'predeclared_plan_v24.json', A / 'predeclared_plan_v24.json'
previous, current = destination.read_bytes(), source.read_bytes()
assert hashlib.sha256(previous).hexdigest() == '631d2412d4a224addee7028c1b2cc527ea1a63ff7f132cee3aba9d43f6888f61'
assert hashlib.sha256(current).hexdigest() == 'd682f40c01a660f598cdf6c81d9faa640c25af1ba87d9e96e56701bb2fec4ffc'
old, new = json.loads(previous), json.loads(current)
assert old['native_ray_box_correction']['actual_library_sha256'] == '7be79c7f3d2cac53a9d1692aa868d91d4b9977e2b7541203ce4ffe90c605a08f'
assert new['native_ray_box_correction']['actual_library_sha256'] == '782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8'
new['native_ray_box_correction']['actual_library_sha256'] = old['native_ray_box_correction']['actual_library_sha256']
assert new == old
destination.write_bytes(current)
assert destination.read_bytes() == current
result = {'schema': 'mr3-v24-root-final-plan-metadata-promotion-v2', 'previous_plan_sha256': hashlib.sha256(previous).hexdigest(), 'plan_sha256': hashlib.sha256(current).hexdigest(), 'only_field': '/native_ray_box_correction/actual_library_sha256', 'source_code_changes': 0, 'native': False}
Path('/tmp/mr3_p2a0_v24_final_plan_promotion_v2.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
