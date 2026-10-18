"""Prepare explicit whole-source deltas; the fixed generated SHA is reviewed before freeze."""
import difflib
import hashlib
import json
from pathlib import Path
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=next(p for p in HERE.parents if (p/'.git').exists())
BASE='92f8bdf5bba1ba245dc53ca0964eef81a7fff938'
PATHS=('ros2_ws/ros2-multi-robot-automap/src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py',
       'ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt')
sha=lambda b: hashlib.sha256(b).hexdigest()
result={'schema':'mr3-reviewed-execution-delta-v1','base_freeze':BASE,
        'scope':'V8 default-off diagnostics, V9 passive recorder and independent observed WORLD cadence, V11 exact Gazebo alias, V12 removal of the redundant SDF cadence option. Whole-byte inverse restores the original execution configuration; no physical, actuator, task or safety threshold change. Source provenance only, never native PASS.', 'files':{}}
for name in PATHS:
    before=subprocess.check_output(['git','show',BASE+':'+name],cwd=ROOT)
    after=(ROOT/name).read_bytes()
    old,new=before.decode().splitlines(keepends=True),after.decode().splitlines(keepends=True)
    changes=[{'old_line_start':a,'new_line_start':c,'before':''.join(old[a:b]),'after':''.join(new[c:d])}
             for tag,a,b,c,d in difflib.SequenceMatcher(None,old,new,autojunk=False).get_opcodes() if tag!='equal']
    restored=list(new)
    for v in reversed(changes):
        at=v['new_line_start'];added=v['after'].splitlines(keepends=True)
        assert restored[at:at+len(added)]==added
        restored[at:at+len(added)]=v['before'].splitlines(keepends=True)
    assert ''.join(restored).encode()==before
    result['files'][name]={'before_sha256':sha(before),'after_sha256':sha(after),'changes':changes}
path=HERE/'reviewed_execution_delta.json'
path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'sha256':sha(path.read_bytes()),'files':len(PATHS),'all_whole_source_inverse_exact':True}))
