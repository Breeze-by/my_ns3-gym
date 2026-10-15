import datetime, hashlib, json, os, subprocess, sys, time
from pathlib import Path
ROOT=Path("/home/zhuyulab/ns3-workspace")
B=ROOT/"ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl"
ROS=ROOT/"ros2_ws/ros2-multi-robot-automap"
A=B/"report/assets/20261015_mr3_p1c"
FREEZE="c8d483228ecb0105c905459578eddbb4a23d4520"
J=A/"v6_contact_phase_resume_execution.jsonl"
J.open("x").close()
def emit(kind, **kw):
 row=dict(kind=kind, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(), monotonic=time.monotonic(), freeze=FREEZE, **kw)
 with J.open("a") as f: f.write(json.dumps(row)+"\n")
 print(json.dumps(row),flush=True)
def log(message):
 with (B/"log.md").open("a") as f:f.write(message)
def head():return subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip()
def frozen_source_check():
 assert head()==FREEZE
 assert hashlib.sha256((A/"predeclared_native_plan_v6.json").read_bytes()).hexdigest()=="7e8bd75d17ce393ae2e7a7e487fc40cdaf03f16c174dcf435766f23aed443302"
 checks=json.loads((A/"implementation_checks_v6.json").read_text())
 assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==digest for p,digest in checks["source_sha256"].items())
frozen_source_check()
for name in ("pilot","terminal","workers1","workers2"):
 assert json.loads((ROS/f"log/mr3_learning/mr3_p1c_v6_{name}/benchmark_summary.json").read_text())["passed"]
 assert json.loads((A/f"{name}_v6_contact_phase_v2_benchmark_audit.json").read_text())["passed"]
stages=[
 ("workers1",["--workers","1","--schedule","open:101,open:101,rooms:202,corridors:303","--steps","16","--base-domain","132","--base-port","12121"]),
 ("workers2",["--workers","2","--schedule","open:101,open:101","--steps","16","--base-domain","134","--base-port","12131"]),
 ("workers4",["--workers","4","--schedule","open:101,open:101","--steps","16","--base-domain","136","--base-port","12141"]),
 ("fault",["--workers","2","--schedule","open:101,open:101","--steps","8","--fault-probe","--base-domain","140","--base-port","12151"]),
 ("deadline",["--workers","1","--schedule","open:101","--steps","300","--deadline-probe","--base-domain","142","--base-port","12161"])]
stages=stages[2:]  # Only original workers4/fault/deadline; no completed native stage is rerun.
phase_plan=json.loads((A/"predeclared_offline_contact_phase_v1.json").read_text())
wrapper=A/"audit_mr3_env_contact_phase_v2.py"
assert hashlib.sha256(wrapper.read_bytes()).hexdigest()==phase_plan["helper_sha256"]
phase_plan_sha=hashlib.sha256((A/"predeclared_offline_contact_phase_v1.json").read_bytes()).hexdigest()
emit("resume_declared_offline_method",phase_predeclaration_sha256=phase_plan_sha,wrapper_sha256=phase_plan["helper_sha256"],prior_journal_sha256=hashlib.sha256((A/"v6_remaining_execution.jsonl").read_bytes()).hexdigest(),runtime_changes=False)
for name,args in stages:
 frozen_source_check()
 assert hashlib.sha256(wrapper.read_bytes()).hexdigest()==phase_plan["helper_sha256"]
 assert hashlib.sha256((A/"predeclared_offline_contact_phase_v1.json").read_bytes()).hexdigest()==phase_plan_sha
 run_id=f"mr3_p1c_v6_{name}"
 command=["python","-m","mr3_learning.benchmark"]+args+["--run-id",run_id]
 import shlex
 shell="source /home/zhuyulab/miniconda3/etc/profile.d/conda.sh; conda activate ns3gym; export PYTHONNOUSERSITE=1; unset PYTHONPATH; "+shlex.join(command)
 log(f"\n### P1C v6 {name}正式启动\n\n冻结{FREEZE}；wireless-rl cwd，精确命令：`{shell}`。遵循已推送v6预案，所有worker均三台；结果待完成。\n")
 emit("start",stage=name,command=shell,cwd=str(B))
 started=time.monotonic()
 process=subprocess.Popen(["rtk","proxy","bash","-c",shell],cwd=B,start_new_session=True)
 emit("owned_command_started",stage=name,pid=process.pid)
 rc=process.wait()
 path=ROS/f"log/mr3_learning/{run_id}"
 summary=json.loads((path/"benchmark_summary.json").read_text()) if (path/"benchmark_summary.json").exists() else {}
 result={key:summary.get(key) for key in ("passed","valid_transitions","wall_sec_including_all_attempts","effective_transition_per_wall_sec")}
 emit("native_complete",stage=name,returncode=rc,outer_wall_sec=time.monotonic()-started,**result)
 log(f"\n{name} v6原生结果：`{json.dumps(result)}`；命令exit{rc}，全部尝试/回收原件{path.relative_to(ROOT)}。\n")
 audit=A/f"{name}_v6_benchmark_audit.json"
 original_command=["rtk","proxy","/usr/bin/python3",str(ROS/"scripts/audit_mr3_env.py"),str(path),"--output",str(audit)]
 original_rc=subprocess.call(original_command,cwd=ROOT)
 emit("original_audit_complete_retained",stage=name,returncode=original_rc,output=str(audit))
 corrected=A/f"{name}_v6_contact_phase_v2_benchmark_audit.json"
 audit_command=["rtk","proxy","/usr/bin/python3",str(wrapper),str(path),"--output",str(corrected)]
 audit_rc=subprocess.call(audit_command,cwd=ROOT)
 emit("contract_phase_v2_audit_complete",stage=name,returncode=audit_rc,output=str(corrected),wrapper_sha256=phase_plan["helper_sha256"])
 log(f"原审计精确命令：`{shlex.join(original_command)}`，exit{original_rc}，保留{audit.relative_to(B)}；新合同phase v2精确命令：`{shlex.join(audit_command)}`，exit{audit_rc}，独立新件{corrected.relative_to(B)}。\n")
 if rc or not summary.get("passed") or summary.get("freeze")!=FREEZE or audit_rc:
  emit("stopped_after_failure",stage=name)
  sys.exit(1)
emit("all_remaining_stages_complete",offline_contract_auditor="contact_phase_v2")
