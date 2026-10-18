import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W / 'report/assets/20261018_mr3_p2a0_v24_install'
sha = lambda raw: hashlib.sha256(raw).hexdigest()
receipt = json.loads((A / 'closed_copy_receipt_v1.json').read_text())
for row in receipt['files']:
    raw = (ROOT / row['canonical']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256'], row['canonical']
assert receipt['native_selected_files'] == 522 and len(receipt['files']) == 550
for directory in (A / 'native/interface', A / 'native/metadata'):
    manifest = json.loads((directory / 'manifest.json').read_text())
    assert ROOT / manifest['prospective_prefix'] == directory
    for original in manifest['files']:
        for part in original['parts']:
            assert ROOT / part['prospective_canonical'] == directory / part['selected']
documents = [ROOT / 'AGENTS.md', ROOT / 'ros2_ws/ros2-multi-robot-automap/AGENTS.md', ROOT / 'ros2_ws/ros2-multi-robot-automap/user_guide.md', ROOT / 'ros2_ws/ros2-multi-robot-automap/launch_commands.md'] + [W / name for name in ('AGENTS.md', 'RESEARCH_PLAN.md', 'IMPLEMENTATION_PLAN.md', 'report/README.md', 'report/20261018_mr3_p2a0_v24_install.md', 'log.md')]
links = 0
for path in documents:
    for target in re.findall(r'\[[^\]]*\]\(([^\s)]+)\)', path.read_text()):
        if target.startswith(('http:', 'https:', '#', 'app:', 'mailto:')):
            continue
        assert (path.parent / target.split('#')[0]).exists(), (str(path), target)
        links += 1
changed = subprocess.check_output(['git', 'diff', '--name-only'], cwd=ROOT, text=True).splitlines()
assert all(ROOT / name in documents for name in changed), changed
subprocess.run(['git', 'diff', '--check'], cwd=ROOT, check=True)
result = {'schema': 'mr3-v24-closed-evidence-static-v1', 'passed': True, 'selected_native_files': 522, 'all_copied_files': 550, 'correct_prospective_destinations': True, 'document_links': links, 'tracked_changes_only_documents': changed, 'scope': 'Byte-copy and document static checks only; V24FAIL/forced cleanup/partial samples/SKIP stay unchanged; no test or native replay.'}
Path('/tmp/mr3_p2a0_v24_closed_static_v1.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
