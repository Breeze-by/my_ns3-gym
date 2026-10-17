import hashlib,json,re,subprocess
from pathlib import Path
root=Path("/home/zhuyulab/ns3-workspace")
w=root/"ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
a=w/"report/assets/20261017_mr3_p2a0_v8"
plan=json.loads((a/"predeclared_plan_v8.json").read_text())
assert len(plan["independent_source_bindings"])==27
for b in plan["independent_source_bindings"]:
 assert hashlib.sha256((root/b["path"]).read_bytes()).hexdigest()==b["sha256"],b
assert (plan["max_api_records"],plan["max_submitted_script_decisions"],plan["max_total_wall_seconds"])==(608,596,18000)
for s in plan["stages"]:
 assert not Path(s["run_directory"]).exists()
 assert not Path("/tmp/mr3_p2a0_v8_"+s["stage"]+"_launch.json").exists()
assert sum(s["wall_ceiling_seconds"] for s in plan["stages"])==18000
paths=subprocess.check_output(["git","diff","--name-only"],cwd=root,text=True).splitlines()+subprocess.check_output(["git","ls-files","--others","--exclude-standard"],cwd=root,text=True).splitlines()
links=[];docs={}
for rel in paths:
 if not rel.endswith(".md"):continue
 p=root/rel;docs[rel]=hashlib.sha256(p.read_bytes()).hexdigest()
 for target in re.findall(r"\]\(([^)]+)\)",p.read_text()):
  if target.startswith(("http:","https:","#","app:","plugin:")):continue
  dest=target.split("#",1)[0]
  assert (p.parent/dest).exists(),(str(p),target)
  links.append([rel,target])
subprocess.run(["git","diff","--check"],cwd=root,check=True)
out=a/"prefreeze_static_review_v2.json";assert not out.exists()
result=dict(passed=True,schema="mr3-p2a0-v8-prefreeze-static-v1",independent_bindings=plan["independent_source_bindings"],plan_sha256=hashlib.sha256((a/"predeclared_plan_v8.json").read_bytes()).hexdigest(),runtime_native_paths_absent=True,docs=docs,links=links,scope="static source/docs/declared budget only; no native or policy credit")
out.write_text(json.dumps(result,indent=2)+"\n")
print(json.dumps(dict(passed=True,bindings=27,docs=len(docs),links=len(links))))
