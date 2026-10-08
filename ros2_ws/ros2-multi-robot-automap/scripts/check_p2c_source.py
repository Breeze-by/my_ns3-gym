#!/usr/bin/env python3
"""Verify the explicitly scoped P2C task change against the accepted review."""
import argparse,ast,hashlib,json,subprocess
from pathlib import Path
from check_p3c_source import PROJECT,ROOT
import run_p3b_fault_matrix as matrix

BASELINE='5d4b3ebab37d9e3f3a6e5890f6fd394b35d6c3d9'
ALLOWED=('src/multi_robot_exploration/multi_robot_exploration/control.py',
         'src/multi_robot_exploration/multi_robot_exploration/battery_manager.py',
         'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py')
NEW_WORLD='src/multi_robot/worlds/p2c_holdout917.world'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('do not overwrite source evidence')
    directories=('src/multi_robot_exploration/multi_robot_exploration','src/multi_robot/params',
        'src/multi_robot/worlds','src/multi_robot/models','src/multi_robot/urdf',
        'src/multi_robot/launch','src/slam_toolbox/src','src/slam_toolbox/config',
        'src/merge_map/merge_map','src/multi_robot_interfaces/msg')
    roots=[str((PROJECT/d).relative_to(ROOT)) for d in directories]
    frozen=subprocess.check_output(['git','ls-tree','-r','--name-only',BASELINE,'--',*roots],cwd=ROOT,text=True).splitlines()
    current={str(x.relative_to(ROOT)) for d in directories for x in (PROJECT/d).rglob('*')
             if x.is_file() and '__pycache__' not in x.parts and x.suffix!='.pyc'}
    expected=set(frozen)|{str((PROJECT/NEW_WORLD).relative_to(ROOT))}
    assert current==expected,dict(missing=sorted(expected-current),extra=sorted(current-expected))
    allowed={str((PROJECT/x).relative_to(ROOT)) for x in ALLOWED}
    protected=[];changed=[]
    for name in frozen:
        old=subprocess.check_output(['git','show',f'{BASELINE}:{name}'],cwd=ROOT)
        now=(ROOT/name).read_bytes()
        row=dict(path=name,sha256=hashlib.sha256(now).hexdigest())
        if name in allowed:
            assert old!=now,('declared P2C source did not change',name);changed.append(row)
        else:
            assert old==now,('unscoped task/model change',name);protected.append(row)
    module=PROJECT/ALLOWED[0]
    old_tree=ast.parse(subprocess.check_output(['git','show',f'{BASELINE}:{module.relative_to(ROOT)}'],cwd=ROOT))
    new_tree=ast.parse(module.read_text())
    names=('RALLY_POSITION_TOLERANCE_M','RALLY_LINEAR_TOLERANCE_MPS','RALLY_ANGULAR_TOLERANCE_RADPS','RALLY_HOLD_SEC')
    def constants(tree):
        return {n.targets[0].id:ast.dump(n.value) for n in tree.body if isinstance(n,ast.Assign)
                and len(n.targets)==1 and isinstance(n.targets[0],ast.Name) and n.targets[0].id in names}
    assert constants(old_tree)==constants(new_tree)
    protocol=matrix.run_matrix();assert protocol['status']=='PASS' and len(protocol['matrix'])==54
    result=dict(status='PASS',baseline=BASELINE,protected_files=protected,authorized_task_changes=changed,
                new_world_sha256=hashlib.sha256((PROJECT/NEW_WORLD).read_bytes()).hexdigest(),
                native_constants_unchanged=True,static_protocol_matrix=protocol)
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',protected_files=len(protected),changed_files=len(changed),protocol_cells=len(protocol['matrix']))))

if __name__=='__main__':main()
