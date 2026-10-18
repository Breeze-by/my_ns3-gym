import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v24_install'
B = Path('/tmp/mr3_p2a0_v24_source_admission_proposal_v1')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
identity = json.loads((B / 'auditor_identity_handoff_v1.json').read_text())
custody = json.loads((B / 'custody_source_handoff_v1.json').read_text())
assert identity['source_STOP'] and identity['whole_bytes_and_AST_inverse_to_baseline']
assert custody['source_STOP']
assert sha((W / 'mr3_learning/audit_ppo.py').read_bytes()) == 'de297d83fd5436651e526fe9782ac0ebed02573ed9aa735a58d9fdcf613c0adf'
assert sha((W / 'MR3_ENV_CONTRACT.md').read_bytes()) == 'cace2f98cca4553f6cc618e7f43d7ead24451c7d802aac816583b74527eb5377'
assert sha((ROOT / 'ros2_ws/ros2-multi-robot-automap/src/multi_robot/src/mr3_ray_box_corrector.cpp').read_bytes()) == 'f82646c8434b77c42f585ac1828eda84640bac873f70cc7de6848cfbd6493473'
assert sha((ROOT / 'ros2_ws/ros2-multi-robot-automap/install/multi_robot/lib/libmr3_ray_box_corrector.so').read_bytes()) == '782d388fea8df3646524e54f41d71de5f53480b9d04cc0ea1c453c70e2c1f7d8'
items = [(Path(identity['source']), W / 'mr3_learning/audit_ppo.py', identity['sha256']), (Path(identity['environment']['source']), W / 'MR3_ENV_CONTRACT.md', identity['environment']['sha256'])]
for row in custody['files']:
    destination = A / row['destination_relative_to_new_A24']
    assert not destination.exists()
    items.append((Path(row['source']), destination, row['sha256']))
records = []
for source, destination, expected in items:
    raw = source.read_bytes()
    assert sha(raw) == expected
    old = sha(destination.read_bytes()) if destination.exists() else None
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    assert destination.read_bytes() == raw
    records.append({'source': str(source), 'destination': str(destination.relative_to(ROOT)), 'old_sha256': old, 'sha256': expected, 'bytes': len(raw)})
result = {'schema': 'mr3-v24-root-fixed-source-promotion-v1', 'promoted': records, 'native': False, 'tests_not_yet_run': True}
Path('/tmp/mr3_p2a0_v24_fixed_source_promotion_v1.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
