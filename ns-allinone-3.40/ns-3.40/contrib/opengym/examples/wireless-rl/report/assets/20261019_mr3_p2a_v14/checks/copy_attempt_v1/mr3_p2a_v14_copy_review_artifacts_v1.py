"""Byte-exact copy of completed CPU/design artifacts, never native evidence."""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path('/home/zhuyulab/ns3-workspace')
OUT = ROOT / 'ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/report/assets/20261019_mr3_p2a_v14'

def binding(path):
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    assert (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}

groups = {
    'readonly_design_originals': [
        '/tmp/mr3_p2a_v14_frame_geometry_review_v1.md',
        '/tmp/mr3_p2a_v14_frame_geometry_review_v1.json',
        '/tmp/mr3_p2a_v14_frame_geometry_directional_addendum_v1.md',
        '/tmp/mr3_p2a_v14_frame_geometry_directional_addendum_v1.json',
        '/tmp/mr3_p2a_v14_frame_geometry_directional_addendum_v2.md',
        '/tmp/mr3_p2a_v14_frame_geometry_directional_addendum_v2.json',
        '/tmp/mr3_p2a_v14_pair_backup_contract_draft_v1.md',
        '/tmp/mr3_p2a_v14_pair_safety_cpu_design_v1.py',
        '/tmp/mr3_p2a_v14_pair_safety_cpu_design_v1.index.json',
        '/tmp/mr3_p2a_v14_pair_model_obligations_static_review_v1.json',
        '/tmp/mr3_p2a_v14_handoff_design_v1.md',
        '/tmp/mr3_p2a_v14_handoff_design_v1.json',
    ],
    'closed_data_only': [
        '/tmp/mr3_p2a_v14_v13_minimum_lateral_artifact_index_v1.json',
    ],
}
index = json.loads(Path(groups['closed_data_only'][0]).read_text())
groups['closed_data_only'] += [row['path'] for row in index['artifacts']]
rows = []
for group, paths in groups.items():
    target_dir = OUT / group
    target_dir.mkdir(exist_ok=False)
    for name in paths:
        source = Path(name)
        before = binding(source)
        target = target_dir / source.name
        shutil.copyfile(source, target)
        copied = binding(target)
        assert before == binding(source)
        assert (before['sha256'], before['bytes']) == (copied['sha256'], copied['bytes'])
        rows.append({'original': before, 'canonical': str(target.relative_to(ROOT)), 'sha256': copied['sha256'], 'bytes': copied['bytes']})
shutil.copyfile(__file__, OUT / 'copy_review_artifacts_v1.py')
result = {'schema': 'mr3-v14-cpu-design-exact-copy-index-v1', 'entries': rows,
          'files': len(rows), 'bytes': sum(r['bytes'] for r in rows),
          'scope': 'Historical drafts retain their not-run text and superseded formulas. Final semantics are per-frame AND and N=2R/X=4R. Closed-data statistics are only necessity diagnostics, never new native/scientific qualification. No original raw episode duplicated.'}
(OUT / 'review_artifacts_copy_index_v1.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'files': result['files'], 'bytes': result['bytes'], 'passed': True}))
