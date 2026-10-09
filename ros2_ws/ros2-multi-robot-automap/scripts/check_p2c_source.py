#!/usr/bin/env python3
"""Verify the explicitly scoped P2C task change against the accepted review."""
import argparse,ast,hashlib,json,subprocess
from pathlib import Path
import yaml
from check_p3c_source import PROJECT,ROOT
import run_p3b_fault_matrix as matrix

BASELINE='5d4b3ebab37d9e3f3a6e5890f6fd394b35d6c3d9'
ALLOWED=('src/multi_robot_exploration/multi_robot_exploration/control.py',
         'src/multi_robot_exploration/multi_robot_exploration/battery_manager.py',
         'src/multi_robot_exploration/multi_robot_exploration/tf_ingress_sampler.py',
         'src/multi_robot/launch/gazebo_multirobot_mapping_with_nav2.launch.py',
         'src/slam_toolbox/src/slam_toolbox_multirobot.cpp',
         'src/slam_toolbox/config/mapper_params_online_multi_async.yaml')
NEW_WORLD='src/multi_robot/worlds/p2c_holdout917.world'
NEW_ACTION_HELPER='src/multi_robot_exploration/multi_robot_exploration/action_callbacks.py'
NEW_SCAN_FILTER='src/slam_toolbox/include/slam_toolbox/scan_self_filter.hpp'


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('do not overwrite source evidence')
    directories=('src/multi_robot_exploration/multi_robot_exploration','src/multi_robot/params',
        'src/multi_robot/worlds','src/multi_robot/models','src/multi_robot/urdf',
        'src/multi_robot/launch','src/slam_toolbox/src','src/slam_toolbox/config','src/slam_toolbox/include',
        'src/merge_map/merge_map','src/multi_robot_interfaces/msg')
    roots=[str((PROJECT/d).relative_to(ROOT)) for d in directories]
    frozen=subprocess.check_output(['git','ls-tree','-r','--name-only',BASELINE,'--',*roots],cwd=ROOT,text=True).splitlines()
    current={str(x.relative_to(ROOT)) for d in directories for x in (PROJECT/d).rglob('*')
             if x.is_file() and '__pycache__' not in x.parts and x.suffix!='.pyc'}
    expected=set(frozen)|{str((PROJECT/name).relative_to(ROOT)) for name in (NEW_WORLD,NEW_ACTION_HELPER,NEW_SCAN_FILTER)}
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
    central=next(n for n in new_tree.body if isinstance(n,ast.ClassDef) and n.name=='HeadquartersControl')
    deferred=[n for n in ast.walk(central) if isinstance(n,ast.Call)
              and isinstance(n.func,ast.Attribute) and n.func.attr=='defer_action_done_callback']
    direct=[n for n in ast.walk(central) if isinstance(n,ast.Call)
            and isinstance(n.func,ast.Attribute) and n.func.attr=='add_done_callback']
    assert len(deferred)==8 and not direct,('unserialized central Future registration',len(deferred),len(direct))
    native_tree=ast.parse((PROJECT/ALLOWED[1]).read_text())
    native=next(n for n in native_tree.body if isinstance(n,ast.ClassDef) and n.name=='BatteryManager')
    native_deferred=[n for n in ast.walk(native) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='defer_action_done_callback']
    assert len(native_deferred)==2 and not any(isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='add_done_callback' for n in ast.walk(native))
    shared=ast.parse((PROJECT/NEW_ACTION_HELPER).read_text())
    direct=[n for n in ast.walk(shared) if isinstance(n,ast.Call)
        and isinstance(n.func,ast.Attribute) and n.func.attr=='add_done_callback']
    assert len(direct)==1
    mapper_path=PROJECT/ALLOWED[-1]
    old_mapper=yaml.safe_load(subprocess.check_output(['git','show',f'{BASELINE}:{mapper_path.relative_to(ROOT)}'],cwd=ROOT))
    new_mapper=yaml.safe_load(mapper_path.read_text())
    key=next(iter(new_mapper))
    assert new_mapper[key]['ros__parameters'].pop('scan_self_filter_body_box')==[-.1965,.0685,-.1325,.1325]
    from p2c_scan_self_filter import physical_range_uncertainty
    assert new_mapper[key]['ros__parameters'].pop('scan_self_filter_range_uncertainty_m')==physical_range_uncertainty()==.0375
    assert old_mapper==new_mapper,'original SLAM mapper configuration changed'
    native_path=PROJECT/ALLOWED[-2]
    old_cpp=subprocess.check_output(['git','show',f'{BASELINE}:{native_path.relative_to(ROOT)}'],cwd=ROOT,text=True)
    suffix='LaserRangeFinder * MultiRobotSlamToolbox::getLaser('
    assert old_cpp.split(suffix,1)[1]==native_path.read_text().split(suffix,1)[1], 'native laser metadata/pose graph callbacks changed'
    protocol=matrix.run_matrix();assert protocol['status']=='PASS' and len(protocol['matrix'])==54
    result=dict(status='PASS',baseline=BASELINE,protected_files=protected,authorized_task_changes=changed,
                new_world_sha256=hashlib.sha256((PROJECT/NEW_WORLD).read_bytes()).hexdigest(),
                native_constants_unchanged=True,static_protocol_matrix=protocol,
                central_future_registrations_deferred=len(deferred),
                native_future_registrations_deferred=len(native_deferred),
                new_action_helper_sha256=hashlib.sha256((PROJECT/NEW_ACTION_HELPER).read_bytes()).hexdigest())
    result['native_scan_self_filter_sha256']=hashlib.sha256((PROJECT/NEW_SCAN_FILTER).read_bytes()).hexdigest()
    result['native_mapper_configuration_unchanged']=True
    result['native_laser_metadata_and_pose_graph_callbacks_unchanged']=True
    result['native_scan_scope']='Native SLAM only: unchanged physical chassis interior plus a contiguous boundary-noise run of at least three matched rays seeded by one physical interior beam; 3 original noise sigma plus half range resolution. NaNs are ignored, never free rays. Original occupancy/return, mapper parameters, source stamps and raw published scan/Nav2 remain protected.'
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status='PASS',protected_files=len(protected),changed_files=len(changed),protocol_cells=len(protocol['matrix']))))

if __name__=='__main__':main()
