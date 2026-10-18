"""CPU-only fake-/proc tests; no ROS, native process, signal or optimizer."""
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from mr3_learning import native_custody as gate

FREEZE = "f" * 40
TOOL = gate.WORKSPACE / ("ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/"
    "report/assets/20261017_mr3_p2a0_v13/independent/mr3_readonly_v13_drive_shim_process_monitor_v2.py")


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value) + "\n")


class NativeCustodyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.proc = self.root / "proc"
        self.proc.mkdir()
        self.run = self.root / "run"
        self.ep = self.run / "worker0/episode001_open_101"
        self.ep.mkdir(parents=True)
        spec = importlib.util.spec_from_file_location("custody_original_cpu_tools", TOOL)
        self.tools = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.tools)
        self.specs = {}
        names = {"smoother_executable":"velocity_smoother", "controller_executable":"controller_server",
                 "odometry_recorder_executable":"mr3_odometry_recorder",
                 "gzserver_executable":"gzserver-11.10.2"}
        for role in gate.BINARY_ROLES:
            path = self.root / "bin" / names.get(role,"lib"+role+".so")
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"\x7fELF" + role.encode())
            path.chmod(0o755)
            self.specs[role] = {"path":str(path),**gate.file_proof(path)}
        gz = self.root / "bin/gzserver"
        gz.symlink_to(self.specs["gzserver_executable"]["resolved_path"])
        self.gz_exe = gate.file_proof(gz)
        self.specs["gzserver_executable"] = {"path":str(gz),**self.gz_exe}
        self.fields = {role:{key:{"path":"unused","sha256":str(i+1)*64} for i,key in enumerate(sorted(keys))}
                       for role,keys in gate.COMPILED_FIELDS.items()}
        self.corrector = SimpleNamespace(ledger_review=lambda *args:{"passed":True})
        self.binding = {"freeze":FREEZE,"sha256":"a"*64,"binaries":self.specs,"tools":self.tools,
                        "document":{"compiled_sources":self.fields},"corrector_tools":self.corrector,
                        "corrector_binding":{"world_names":{"open":"p1c_open"}}}
        self.params = self.root / "params.yaml"
        self.params.write_text("velocity_smoother:\n  ros__parameters:\n    mr3_diagnostic_enabled: false\n    mr3_diagnostic_epoch: ''\n    mr3_diagnostic_arm: ''\n")
        self.benchmark_argv = ["/learner/python","-m","mr3_learning.benchmark","--run-dir",str(self.run)]
        self.identities = {}
        self.make_proc(90,1,self.benchmark_argv,gz,[])
        self.make_proc(100,90,["/usr/bin/python3",str(gate.WORKSPACE/"ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py"),"--run-dir",str(self.ep)],gz,[])
        self.make_proc(101,100,["/usr/bin/python3","ros2","launch"],gz,[])
        self.make_proc(200,101,[str(gz)],gz,["driver","ray_box","ode"])
        for i,robot in enumerate(gate.ROBOTS):
            self.make_proc(300+i,101,[self.specs["smoother_executable"]["path"],"--ros-args","-r","__node:=velocity_smoother","-r","__ns:=/"+robot,"--params-file",str(self.params)],Path(self.specs["smoother_executable"]["path"]),["smoother_core"])
            self.make_proc(400+i,101,[self.specs["controller_executable"]["path"],"--ros-args","-r","__node:=controller_server","-r","__ns:=/"+robot],Path(self.specs["controller_executable"]["path"]),["rotation_shim"])
        self.make_proc(500,101,[self.specs["odometry_recorder_executable"]["path"],"--ros-args","-r","__node:=mr3_odometry_recorder"],Path(self.specs["odometry_recorder_executable"]["path"]),[])
        write_json(self.ep/"metadata.json",{"epoch":"episode","freeze":FREEZE,"scene":"open"})
        write_json(self.ep/"supervisor_metadata.json",{"epoch":"episode","worker_identity":self.identities[100]})
        self.native_configs()

    def map_line(self, path):
        value=gate.file_proof(path)
        stat=value["stat"]
        return "1000-2000 r-xp 00000000 %02x:%02x %d %s" % (gate.os.major(stat["dev"]),gate.os.minor(stat["dev"]),stat["ino"],value["resolved_path"])

    def make_proc(self,pid,parent,argv,exe,roles,start=None,state="S"):
        path=self.proc/str(pid)
        path.mkdir(exist_ok=True)
        suffix=[state,str(parent),"90","90"]+["0"]*16
        suffix[19]=str(start or pid*10)
        (path/"stat").write_text(str(pid)+" (native name) "+" ".join(suffix))
        (path/"cmdline").write_bytes(b"\0".join(x.encode() for x in argv)+b"\0")
        if (path/"exe").is_symlink():(path/"exe").unlink()
        (path/"exe").symlink_to(exe)
        (path/"maps").write_text("\n".join([self.map_line(exe)]+[self.map_line(self.specs[x]["path"])for x in roles])+"\n")
        self.identities[pid]=self.tools.proc_identity(pid,self.proc)

    def native_configs(self):
        for role,names in [("driver",["drive_"+r+".jsonl"for r in gate.ROBOTS]),("recorder",["driver_odometry_receipts.jsonl"]),("ray_box",["ray_box_corrector.jsonl"])]:
            for name in names:
                cfg={"kind":"configuration","epoch":"episode",**{k:v["sha256"]for k,v in self.fields[role].items()}}
                if role in ("driver","ray_box"):cfg["loaded_library_path"]=self.specs[role]["resolved_path"]
                if role=="driver":
                    robot=name[6:-6]
                    cfg.update(robot=robot,command_mode="tagged",command_topic=f"/{robot}/mr3_drive/target",status_topic=f"/{robot}/mr3_drive/status")
                if role=="recorder":cfg.update(output_path=str(self.ep/name),use_sim_time=True,robots=list(gate.ROBOTS))
                write_json(self.ep/name,cfg)

    def capture(self):
        return gate.capture_episode(self.ep,self.binding,proc_root=self.proc)

    def close_fixture(self):
        cap=self.capture()
        closed={"epoch":"episode","pending_goal_count":0,"robot_names":list(gate.ROBOTS),"navigation_failure":False}
        nav={"epoch":"episode","success":True,"failures":[],"protocol":gate.PROTOCOL,"goal_ownership_closed":closed,
             "robots":[{"robot":r,"shutdown":{"response":{"success":True}},"states":[{"node":n,"state":{"id":4,"label":"finalized"}}for n in gate.NAV2_NODES]}for r in gate.ROBOTS]}
        write_json(self.ep/"nav2_shutdown.json",nav)
        write_json(self.ep/"summary.json",{"epoch":"episode","closed":closed,"reason":"terminated","failures":[],"native_failures":[],"launch_returncode":0,"shutdown_protocol":gate.PROTOCOL,"nav2_shutdown":nav})
        native_identity={"pid":600,"start_ticks":6000,"parent":101,"group":90,"session":90,"state":"S"}
        saved=[value for pid,value in self.identities.items()if pid!=1]+[native_identity]
        write_json(self.ep/"supervisor_shutdown.json",{"epoch":"episode","worker_returncode":0,"forced_shutdown":False,"failed_sample":False,"remaining_owned_processes":[],"remaining_owned_zombies":[],"owned_processes_seen":saved})
        write_json(self.ep/"native_stop.json",{"returncode":0,"method":"owned_launch_native_stop","server_clean_exit_recorded":True,"native_cli_pid":600})
        names=[("gzserver-1",200),("mr3_odometry_recorder-1",500),("mr3_gazebo_native_stop-1",600)]+[("velocity_smoother-"+str(i),300+i)for i in range(3)]+[("controller_server-"+str(i),400+i)for i in range(3)]
        lines=[f"[INFO] [{n}]: process started with pid [{pid}]"for n,pid in names]+[f"[INFO] [{n}]: process has finished cleanly [pid {pid}]"for n,pid in names]
        (self.ep/"launch.log").write_text("\n".join(lines)+"\n")
        topology={"schema":"mr3-drive-topology-v1","epoch":"episode","publishers":{},"target_subscribers":{},"legacy_subscribers":{}}
        for robot in gate.ROBOTS:
            driver={"namespace":"/"+robot,"node":"turtlebot3_diff_drive","topic_type":"std_msgs/msg/String"}
            target,status=f"/{robot}/mr3_drive/target",f"/{robot}/mr3_drive/status"
            topology["publishers"][target]=[{"namespace":"/","node":"motion_safety","topic_type":"std_msgs/msg/String"}]
            topology["publishers"][status]=[driver]
            topology["target_subscribers"][target]=[driver]
            topology["legacy_subscribers"][f"/{robot}/cmd_vel"]=[]
            (self.ep/f"drive_model_{robot}.sdf").write_text(f'<sdf><model><plugin name="turtlebot3_diff_drive" filename="libmr3_gazebo_diff_drive.so"><mr3_tagged_commands>true</mr3_tagged_commands><mr3_epoch>episode</mr3_epoch><mr3_audit_path>{self.ep}/drive_{robot}.jsonl</mr3_audit_path></plugin></model></sdf>')
        write_json(self.ep/"drive_topology.json",topology)
        launch=self.root/"launch.json"
        write_json(launch,{"freeze":FREEZE,"returncode":0,"benchmark_parent":self.identities[90],"launcher_identity":{"pid":900,"start_ticks":9000},"argv":self.benchmark_argv})
        stop=self.root/"stop.json"
        stopvalue={"schema":"mr3-native-custody-stop-v1","freeze":FREEZE,"launch_receipt":{"path":str(launch),"sha256":gate.sha(launch.read_bytes())}}
        write_json(stop,stopvalue)
        capture=self.root/"capture.json"
        write_json(capture,{"schema":"mr3-native-custody-live-v1","freeze":FREEZE,"closed":True,"errors":[],"passed":True,"binding_sha256":"a"*64,"run_directory":str(self.run),"stop_file":str(stop),"stop":stopvalue,"episodes":[cap],"watcher_identity":{"pid":901,"start_ticks":9010}})
        leaf=self.root/"fifo_leaf.json"
        write_json(leaf,{"passed":True,"errors":[],"epoch":"episode","freeze":FREEZE,"bindings":{}})
        fifo=self.root/"fifo.json"
        write_json(fifo,[{"episode_directory":str(self.ep),"path":str(leaf),"sha256":gate.sha(leaf.read_bytes())}])
        shutil.rmtree(self.proc)
        self.proc.mkdir()
        return SimpleNamespace(binding=self.root/"binding.json",freeze=FREEZE,capture=capture,launch_receipt=launch,fifo_receipts=fifo,run_directory=self.run,expected_episodes=1,require_parameters=False)

    def review(self,args):
        with patch.object(gate,"load_binding",return_value=self.binding):
            return gate.review(args,proc_root=self.proc)

    def test_normal_capture_has_three_shims_smoothers_and_real_recorder_exe(self):
        cap=self.capture()
        self.assertEqual(len(cap["processes"]),8)
        self.assertIsNone(cap["observer_only_binding"])
        recorder=next(x for x in cap["processes"]if x["component"]=="recorder")
        self.assertEqual(recorder["executable"]["sha256"],self.specs["odometry_recorder_executable"]["sha256"])
        self.assertEqual(recorder["actual_ancestry"][-1]["pid"],90)

    def test_versioned_gzserver_real_symlink_is_exactly_bound(self):
        gz=next(x for x in self.capture()["processes"] if x["component"]=="gzserver")
        self.assertEqual(Path(gz["argv"][0]).name,"gzserver")
        self.assertEqual(Path(gz["executable"]["resolved_path"]).name,"gzserver-11.10.2")
        self.assertEqual(gz["executable"],gz["gzserver_launch_alias"])
        self.assertEqual(gz["executable"],self.gz_exe)

    def test_gzserver_imposter_same_basename_or_same_bytes_is_rejected(self):
        imposter=self.root/"imposter/gzserver"
        imposter.parent.mkdir()
        imposter.write_bytes(Path(self.gz_exe["resolved_path"]).read_bytes())
        imposter.chmod(0o755)
        self.make_proc(200,101,[self.specs["gzserver_executable"]["path"]],imposter,["driver","ray_box","ode"])
        with self.assertRaisesRegex(ValueError,"actual proc exe/argv/device/inode/SHA differs"):
            self.capture()

    def test_gzserver_launch_alias_retargeted_to_imposter_is_rejected(self):
        imposter=self.root/"bin/gzserver-99"
        imposter.write_bytes(Path(self.gz_exe["resolved_path"]).read_bytes())
        alias=Path(self.specs["gzserver_executable"]["path"])
        # Keep the simulated live /proc/exe on the original actual ELF.
        self.make_proc(200,101,[str(alias)],Path(self.gz_exe["resolved_path"]),["driver","ray_box","ode"])
        alias.unlink();alias.symlink_to(imposter)
        with self.assertRaisesRegex(ValueError,"launch alias differs"):
            self.capture()

    def test_gzserver_launch_alias_change_during_capture_is_rejected(self):
        alias=Path(self.specs["gzserver_executable"]["path"])
        original=gate.file_proof
        changed=False
        def read_then_retarget(path):
            nonlocal changed
            result=original(path)
            if Path(path)==alias and not changed:
                changed=True
                other=self.root/"bin/gzserver-99"
                other.write_bytes(Path(self.gz_exe["resolved_path"]).read_bytes())
                alias.unlink();alias.symlink_to(other)
            return result
        # /proc/exe is the real process inode, independent of a later argv alias change.
        self.make_proc(200,101,[str(alias)],Path(self.gz_exe["resolved_path"]),["driver","ray_box","ode"])
        with patch.object(gate,"file_proof",side_effect=read_then_retarget):
            with self.assertRaisesRegex(ValueError,"launch alias changed during capture"):
                self.capture()

    def test_replaced_mapping_inode_never_gets_credit(self):
        p=self.proc/"200/maps"
        p.write_text(p.read_text().replace(str(self.specs["driver"]["stat"]["ino"]),"999999999"))
        with self.assertRaisesRegex(ValueError,"mapped file differs"):self.capture()

    def test_borrowed_recorder_from_another_worker_stays_pending(self):
        p=self.proc/"500/stat"
        p.write_text(p.read_text().replace(" S 101 "," S 999 "))
        with self.assertRaises(gate.PendingCapture):self.capture()

    def test_fifth_json_source_sha_is_not_optional(self):
        path=self.ep/"drive_tb2.jsonl"
        x=json.loads(path.read_bytes());x.pop("compiled_odometry_json_sha256");write_json(path,x)
        with self.assertRaisesRegex(ValueError,"compiled-source"):self.capture()

    def test_diagnostic_true_or_missing_explicit_false_rejected(self):
        for value in ["mr3_diagnostic_enabled: true\n", "use_sim_time: true\n"]:
            with self.subTest(value=value):
                self.params.write_text(value)
                with self.assertRaises(ValueError):self.capture()

    def test_normal_episode_rejects_unrequested_observer_mapping(self):
        with (self.proc/"200/maps").open("a")as f:f.write("1000-2000 r-xp 0 00:00 1 /lib/libmr3_stop_response_observer.so\n")
        with self.assertRaisesRegex(ValueError,"undeclared physics"):self.capture()

    def test_complete_strict_closure_and_original_callback_gate_pass(self):
        args=self.close_fixture()
        calls=[]
        self.corrector.ledger_review=lambda *args:calls.append(args)or{"passed":True}
        result=self.review(args)
        self.assertTrue(result["passed"],result["errors"])
        self.assertEqual(len(calls),1)
        self.assertEqual(calls[0][2:5],("episode",200,"p1c_open"))

    def test_live_hard_error_cannot_be_hidden_by_later_complete_capture(self):
        args=self.close_fixture();x=json.loads(args.capture.read_bytes());x["errors"]=[{"error":"PID reused"}];write_json(args.capture,x)
        self.assertFalse(self.review(args)["passed"])

    def test_live_recorder_exe_tampering_is_rejected(self):
        args=self.close_fixture();x=json.loads(args.capture.read_bytes())
        next(p for p in x["episodes"][0]["processes"]if p["component"]=="recorder")["executable"]["sha256"]="0"*64
        write_json(args.capture,x)
        self.assertFalse(self.review(args)["passed"])

    def test_closed_yaml_replay_cannot_hide_diagnostic_true(self):
        args=self.close_fixture();x=json.loads(args.capture.read_bytes())
        row=next(p for p in x["episodes"][0]["processes"]if p["component"]=="smoother")["normal_smoother_parameter_files"][0]
        row["raw"]=row["raw"].replace("false","true");row["sha256"]=gate.sha(row["raw"].encode());write_json(args.capture,x)
        self.assertFalse(self.review(args)["passed"])

    def test_borrowed_fifo_epoch_is_rejected(self):
        args=self.close_fixture();leaf=self.root/"fifo_leaf.json";x=json.loads(leaf.read_bytes());x["epoch"]="peer";write_json(leaf,x)
        rows=json.loads(args.fifo_receipts.read_bytes());rows[0]["sha256"]=gate.sha(leaf.read_bytes());write_json(args.fifo_receipts,rows)
        self.assertFalse(self.review(args)["passed"])

    def test_native_unknown_exit_and_incomplete_finalization_rejected(self):
        args=self.close_fixture();path=self.ep/"nav2_shutdown.json";x=json.loads(path.read_bytes());x["robots"][0]["states"][0]["state"]={"id":3,"label":"active"};write_json(path,x)
        self.assertFalse(self.review(args)["passed"])

    def test_same_saved_identity_zombie_is_not_gone(self):
        args=self.close_fixture()
        self.make_proc(200,101,[str(self.root/"bin/gzserver")],self.root/"bin/gzserver",[],state="Z")
        result=self.review(args)
        self.assertFalse(result["passed"])
        self.assertTrue(any("including zombie" in e for e in result["errors"]))

    def test_original_closed_callback_failure_is_preserved(self):
        args=self.close_fixture()
        def failed(*unused):raise ValueError("actual callback error")
        self.corrector.ledger_review=failed
        result=self.review(args)
        self.assertFalse(result["passed"])
        self.assertTrue(any("actual callback error"in x for x in result["errors"]))

    def test_exclusive_output_rejects_existing_file(self):
        p=self.root/"exclusive.json";p.write_text("keep")
        with self.assertRaises(FileExistsError):gate.exclusive(p,{"passed":True})
        self.assertEqual(p.read_text(),"keep")

    def test_nested_ppo_discovery_excludes_archives(self):
        nested=self.run/"native/round0000/worker1/episode002_rooms_101/supervisor_metadata.json"
        archive=self.run/"archive/native/round0000/worker1/episode002_rooms_101/supervisor_metadata.json"
        write_json(nested,{})
        write_json(archive,{})
        self.assertEqual(gate.episode_directories(self.run),sorted([self.ep,nested.parent]))

    def test_parent_module_scope_allows_ppo_and_trace_but_not_arbitrary_python(self):
        for module,args in [("mr3_learning.ppo",["--mode","train"]),("mr3_learning.ppo",["--mode","evaluate"]),("mr3_learning.action_trace",[])]:
            self.assertEqual(gate.native_parent_module(["/learner/python","-m",module]+args),module)
        with self.assertRaises(ValueError):gate.native_parent_module(["/learner/python","-m","unrelated"])

    def test_persistent_coordinator_is_real_live_and_excluded_only_from_native_gone(self):
        coord_argv=["/matrix/python","-m","mr3_learning.preparation"]
        gz=self.root/"bin/gzserver"
        self.make_proc(1,0,coord_argv,gz,[])
        coordinator=dict(self.identities[1])
        args=self.close_fixture()
        self.make_proc(1,0,coord_argv,gz,[])
        launch=json.loads(args.launch_receipt.read_bytes())
        launch.update(launcher_identity_scope="persistent_coordinator_not_native_owned",
                      launcher_identity=coordinator,coordinator_identity=coordinator,
                      coordinator_actual_argv=coord_argv)
        write_json(args.launch_receipt,launch)
        cap=json.loads(args.capture.read_bytes())
        cap["stop"]["launch_receipt"]["sha256"]=gate.sha(args.launch_receipt.read_bytes())
        write_json(Path(cap["stop_file"]),cap["stop"])
        write_json(args.capture,cap)
        result=self.review(args)
        self.assertTrue(result["passed"],result["errors"])
        self.assertTrue(result["coordinator"]["same_identity_present"])
        self.assertTrue(result["coordinator"]["final_external_coordinator_absence_required"])
        self.assertNotIn(1,[x["saved"]["pid"]for x in result["identities"]])

    def test_actual_ready_writer_and_wait_fifo_pure_consumers(self):
        ready=self.root/"ready.json"
        wrote=gate.write_ready_receipt(ready,FREEZE,"a"*64)
        read=gate.Reader()
        self.assertEqual(gate.read_ready_receipt(read,ready,FREEZE,"a"*64),wrote)
        self.assertEqual(wrote["watcher_identity"]["pid"],gate.os.getpid())
        args=self.close_fixture()
        stop=json.loads(args.capture.read_bytes())["stop_file"]
        boundary=gate.read_wait_boundary(read,stop,args.launch_receipt,FREEZE)
        self.assertEqual(boundary["launch"]["returncode"],0)
        self.assertEqual(set(gate.read_fifo_receipts(read,args.fifo_receipts,FREEZE,1)),{str(self.ep)})
        with self.assertRaises(ValueError):gate.read_wait_boundary(read,stop,args.launch_receipt,"0"*40)


if __name__=="__main__":unittest.main()
