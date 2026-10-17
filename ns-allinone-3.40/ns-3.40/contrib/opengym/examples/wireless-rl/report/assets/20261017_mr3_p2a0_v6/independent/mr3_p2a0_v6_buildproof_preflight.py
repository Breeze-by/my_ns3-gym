from pathlib import Path
import json,hashlib,gzip,subprocess,sys
root=Path("/home/zhuyulab/ns3-workspace");w=root/"ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl";a=w/"report/assets/20261017_mr3_p2a0_v6"
freeze=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
assert subprocess.check_output(["git","rev-parse","@{u}"],cwd=root,text=True).strip()==freeze
assert not subprocess.check_output(["git","status","--porcelain"],cwd=root,text=True)
sys.path.insert(0,str(w))
from mr3_learning.audit_ppo import load_native_gates
*_,proof=load_native_gates(root,freeze)
plan=json.loads((a/"predeclared_plan_v6.json").read_text());indie=[]
for b in plan["independent_source_bindings"]:
    raw=subprocess.check_output(["git","show",freeze+":"+b["path"]],cwd=root)
    assert raw==(root/b["path"]).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==b["sha256"]
    indie.append(b)
b=json.loads((a/"build_drive_binary_v6.json").read_text())
assert hashlib.sha256((root/plan["drive_contract"]["binary_build_receipt"]["path"]).read_bytes()).hexdigest()==plan["drive_contract"]["binary_build_receipt"]["sha256"]
for p in (Path(b["library_path"]),Path(b["installed_path"])):
    assert hashlib.sha256(p.read_bytes()).hexdigest()==b["library_sha256"]
blob=(root/b["archived_library_gzip"]).read_bytes(); assert hashlib.sha256(blob).hexdigest()==b["archived_library_encoded_sha256"]
assert hashlib.sha256(gzip.decompress(blob)).hexdigest()==b["library_sha256"]
for field,relative in (("compiled_source_sha256","src/mr3_gazebo_diff_drive.cpp"),("compiled_header_sha256","include/multi_robot/mr3_gazebo_diff_drive.hpp"),("compiled_helper_sha256","include/multi_robot/paired_wheel_slew.hpp")):
    rel="ros2_ws/ros2-multi-robot-automap/src/multi_robot/"+relative
    raw=subprocess.check_output(["git","show",freeze+":"+rel],cwd=root); assert hashlib.sha256(raw).hexdigest()==b[field]
    assert b[field].encode() in Path(b["library_path"]).read_bytes()
b.update(schema="mr3-drive-binary-binding-v1",freeze=freeze)
bp=Path("/tmp/mr3_p2a0_v6_binaryproof.json");assert not bp.exists();bp.write_text(json.dumps(b,indent=2)+"\n")
out=Path("/tmp/mr3_p2a0_v6_source_preflight.json");assert not out.exists(); out.write_text(json.dumps(dict(passed=True,freeze=freeze,source_bindings=proof,independent_source_bindings=indie,binary_proof=str(bp),binary_proof_sha256=hashlib.sha256(bp.read_bytes()).hexdigest()),indent=2)+"\n")
print(json.dumps(dict(passed=True,freeze=freeze,source_bindings=len(proof),independent_bindings=len(indie),binary_sha256=b["library_sha256"])))
