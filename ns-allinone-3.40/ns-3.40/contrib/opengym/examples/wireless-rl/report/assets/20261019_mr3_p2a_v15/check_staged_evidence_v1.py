"""Verify staged raw evidence using the runner's recorded ordinal names."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
ROOT=Path('/home/zhuyulab/ns3-workspace')
W=ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A=Path(__file__).resolve().parent

def staged(path):
    return subprocess.check_output(['git','show',':'+str(path.relative_to(ROOT))],cwd=ROOT)

for path in A.glob('checks/*/console.log'):
    raw=staged(path)
    assert raw==path.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==json.loads(path.with_name('actual_wait.json').read_text())['console']['sha256']
checks=0
for path in A.glob('checks/*/actual_wait.json'):
    for index,binding in enumerate(json.loads(path.read_text())['source_before']):
        snapshot=path.parent/'source_snapshots'/f'{index:02d}_{Path(binding["path"]).name}'
        assert hashlib.sha256(staged(snapshot)).hexdigest()==binding['sha256']
        checks+=1
links=0
for path in (W/'report/20261019_mr3_p2a_v15.md',ROOT/'ros2_ws/ros2-multi-robot-automap/AGENTS.md',ROOT/'ros2_ws/ros2-multi-robot-automap/launch_commands.md'):
    for target in re.findall(r'(?<!!)\[[^\]]*\]\(([^)]+)\)',path.read_text()):
        if target.startswith(('https:','http:','#','mailto:')):continue
        assert (path.parent/target.split('#',1)[0].strip('<>')).resolve().exists(),target
        links+=1
print(json.dumps({'passed':True,'staged_snapshot_bindings':checks,'console_bytes_exact':22,'latest_docs_links':links}))
