import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote

ROOT = Path('/home/zhuyulab/ns3-workspace')
W = ROOT/'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl'
A = W/'report/assets/20261018_mr3_p2a0_v21_ray'
def git(*args):
    return subprocess.check_output(['rtk','proxy','git',*args],cwd=ROOT,text=True)
changed = git('diff','--name-only').splitlines()
assert len(changed) == 11, changed
links = 0
for name in changed:
    path = ROOT/name
    if path.suffix == '.md':
        for target in re.findall(r'\]\(([^)]+)\)',path.read_text()):
            target = target.strip('<>').split('#')[0]
            if not target or ':' in target or '$' in target:
                continue
            assert (path.parent/unquote(target)).exists(), (name,target)
            links += 1
    elif path.suffix == '.json':
        json.loads(path.read_text())
copy = json.loads((A/'closed_canonical_copy_v1.json').read_text())
assert len(copy['files']) == 205
for row in copy['files']:
    raw = (ROOT/row['canonical']).read_bytes()
    assert len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256']
archives = []
for name in ('closed_core_v1','closed_posthoc_v1'):
    m = json.loads((A/name/'manifest_v1.json').read_text())
    assert m['full_roundtrip_and_source_final_sha_stat_verified']
    assert hashlib.sha256((A/name/'originals.tar.gz').read_bytes()).hexdigest() == m['archive_sha256']
    archives.append({'path':name,'sha256':m['archive_sha256']})
for path in A.rglob('*.json'):
    json.loads(path.read_text())
subprocess.run(['rtk','proxy','git','diff','--check'],cwd=ROOT,check=True)
ignored_patch = str((A/'independent/byte_custody_v1/mr3_p2a0_v21_ray_pack_review_only_v1.patch').relative_to(ROOT))
dry = git('add','-n','.') + git('add','-n','-f',ignored_patch)
Path('/tmp/mr3_p2a0_v21_closed_add_dry_v1.txt').write_text(dry)
paths = [line[5:-1] for line in dry.splitlines()]
untracked = git('ls-files','--others','--exclude-standard').splitlines()
assert set(paths) == set(changed+untracked+[ignored_patch])
assert all(row['canonical'] in paths for row in copy['files'])
assert all(p in changed or p.startswith(str(A.relative_to(ROOT))+'/') for p in paths)
assert not any('/build/' in p or '/install/' in p or '/log/' in p for p in paths)
assert all((ROOT/p).stat().st_size < 100000000 for p in paths)
result = {'schema':'mr3-v21-closed-static-v1','passed':True,
    'scope':'Documentation/link/JSON/exact-custody-copy and archive-hash verification; no audit/native replay.',
    'changed_documents':changed,'checked_local_links':links,'custody_files_exact':205,
    'archives':archives,'actual_add_dry_paths':len(paths),'exact_whitelist':True,
    'dry_path':'/tmp/mr3_p2a0_v21_closed_add_dry_v1.txt',
    'intentional_ignored_original_patch':ignored_patch,
    'ignored_patch_reason':'The selected original review patch is research evidence; ordinary global *.patch ignore is overridden for this exact file.'}
Path('/tmp/mr3_p2a0_v21_closed_static_v1.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('passed','checked_local_links','custody_files_exact','actual_add_dry_paths')}))
