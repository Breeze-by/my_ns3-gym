import hashlib
import json
from pathlib import Path

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
B = Path('/tmp/mr3_p2a0_v24_source_admission_proposal_v1')
sha = lambda raw: hashlib.sha256(raw).hexdigest()
items = [('audit_ppo.proposed_v24_v2.py', W / 'mr3_learning/audit_ppo.py', 'e128e90b6767356b245190cd9095107101d12db2b6c7ecdbf8564c10310404e1', 'cc467064ab66e04507ed4d4e805a4e23cdf09b3716fd85517ebb34fe7b2de521'), ('MR3_ENV_CONTRACT.proposed_pending_v4.md', W / 'MR3_ENV_CONTRACT.md', '27dfaf8416f4938d3b2b389db0b0aa5a69ecc1f151582aec870fbb7184ac8426', 'f1e0be60d35db3677fb9194341c1ae4133a5c74ed7199056fe18f7e797f40416')]
records = []
for name, destination, previous, expected in items:
    raw = (B / name).read_bytes()
    assert sha(raw) == expected and sha(destination.read_bytes()) == previous
    destination.write_bytes(raw)
    assert destination.read_bytes() == raw
    records.append({'source': str(B / name), 'destination': str(destination.relative_to(ROOT)), 'old_sha256': previous, 'sha256': expected, 'bytes': len(raw)})
result = {'schema': 'mr3-v24-root-final-environment-source-promotion-v1', 'scope': 'Only final new ENV causal wording and corresponding three fixed auditor literals, no function or library change. Earlier real16-unit execution retains its own source identity.', 'promoted': records, 'native': False}
Path('/tmp/mr3_p2a0_v24_final_environment_promotion_v1.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
