import importlib,json,hashlib,sys
from pathlib import Path
root=Path("/home/zhuyulab/ns3-workspace")
pkg=root/"ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration"
modules={}
for name in ("mr3_motion_safety","motion_safety","mr3_drive_phase","mr3_control_phase","mr3_motion_control","peer_obstacles","mr3_adapter","mr3_information","mr3_reward","task_evaluator"):
 m=importlib.import_module("multi_robot_exploration."+name)
 actual=Path(m.__file__).resolve(); expected=pkg/(name+".py")
 assert actual==expected and actual.read_bytes()==expected.read_bytes()
 modules[name]={"module_file":m.__file__,"resolved_source":str(actual),"sha256":hashlib.sha256(actual.read_bytes()).hexdigest()}
result=dict(passed=True,schema="mr3-p2a0-system-import-bindings-v1",python=sys.executable,modules=modules,scope="imports only; no ROS init/nodes or native response credit")
out=Path(sys.argv[1]);assert not out.exists();out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(dict(passed=True,modules=len(modules))))
