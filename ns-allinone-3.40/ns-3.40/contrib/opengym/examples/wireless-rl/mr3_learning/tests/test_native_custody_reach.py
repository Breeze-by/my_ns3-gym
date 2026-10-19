"""New reach custody attacks using the existing fake-/proc fixture only.

No fixture is source/ELF admission evidence. Original PID/maps/close predicates
execute against these declared files; the new entry must add real conjunctions.
"""
import copy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import native_custody_reach as gate
from mr3_learning.tests import test_native_custody as old_tests


def write(path,value):
    Path(path).write_text(json.dumps(value)+"\n")


class ReachNativeCustodyTests(unittest.TestCase):
    def fixture(self):
        f=old_tests.NativeCustodyTests(methodName="runTest")
        f.setUp();self.addCleanup(f.doCleanups)
        module,proof=gate.load_implementation()
        f.fields["driver"]["compiled_drive_feed_sha256"]={"path":"unused","sha256":"6"*64}
        f.native_configs()
        meta=json.loads((f.ep/"metadata.json").read_bytes())
        meta.update(safety_contract=gate.CONTRACT,quantum_steps=20,execution_phase_protocol=gate.PROTOCOL,
                    reset_handshake="paused-controlled-state-peer-guard-storage-v2")
        write(f.ep/"metadata.json",meta)
        f.binding["reader"]=module.Reader()
        for robot in gate.ROBOTS:
            path=f.ep/("drive_"+robot+".jsonl")
            config=json.loads(path.read_bytes())
            config.update(native_feeds_enabled=True,applied_feed_schema="mr3-drive-applied-v1",
                applied_feed_scope="all_wheel_SetParam_calls_returned_true; not_body_response",
                odometry_calibration_schema="mr3-odom-calibration-v1",
                odometry_conversion_contract="float32-trig-binary64-rn-v1",
                odometry_producer_frame="world-common-model-origin-v1",
                native_feed_qos={"depth":256,"reliability":"reliable","durability":"volatile"})
            write(path,config)
            odom=dict(config,schema="mr3-world-odometry-publication-v1",provider="WORLD")
            write(f.ep/("odometry_"+robot+".jsonl"),odom)
        f.capture=lambda:module.capture_episode(f.ep,f.binding,proc_root=f.proc)
        return f,module,proof

    def closed_fixture(self):
        f,module,proof=self.fixture()
        args=f.close_fixture()
        launch=json.loads(args.launch_receipt.read_bytes())
        launch.update(schema=gate.SCHEMA_WAIT,safety_contract=gate.CONTRACT)
        write(args.launch_receipt,launch)
        capture=json.loads(args.capture.read_bytes())
        stop=capture["stop"]
        stop.update(schema=gate.SCHEMA_STOP,safety_contract=gate.CONTRACT)
        stop["launch_receipt"]["sha256"]=gate.sha(args.launch_receipt.read_bytes())
        write(capture["stop_file"],stop)
        capture.update(schema=gate.SCHEMA_CAPTURE,safety_contract=gate.CONTRACT,implementation_provenance=proof)
        write(args.capture,capture)
        leaf=f.root/"fifo_leaf.json"
        value=json.loads(leaf.read_bytes())
        value.update(schema=gate.SCHEMA_FIFO,safety_contract=gate.CONTRACT)
        write(leaf,value)
        manifest=json.loads(args.fifo_receipts.read_bytes())
        manifest[0]["sha256"]=gate.sha(leaf.read_bytes());write(args.fifo_receipts,manifest)
        return f,module,proof,args

    def review(self,f,module,args):
        with patch.object(module,"load_binding",return_value=f.binding):
            return module.review(args,proc_root=f.proc)

    def test_exact_complete_projection_and_private_module_isolation(self):
        raw=(gate.WORKSPACE/gate.HELPER).read_bytes()
        projected,proof=gate.project_source(raw)
        self.assertNotEqual(projected,raw)
        self.assertTrue(proof["exact_whole_source_inverse"])
        self.assertEqual(proof["inverse_sha256"],gate.HELPER_SHA256)
        first,_=gate.load_implementation();second,_=gate.load_implementation()
        first.COMPILED_FIELDS["driver"].remove("compiled_drive_feed_sha256")
        self.assertIn("compiled_drive_feed_sha256",second.COMPILED_FIELDS["driver"])
        self.assertNotIn("compiled_drive_feed_sha256",old_tests.gate.COMPILED_FIELDS["driver"])

    def test_one_extra_source_edit_cannot_be_projected_as_an_identity_upgrade(self):
        raw=(gate.WORKSPACE/gate.HELPER).read_bytes()
        with self.assertRaisesRegex(ValueError,"immutable"):
            gate.project_source(raw+b"\n# undeclared edit\n")

    def test_reach_live_capture_checks_new_sixth_source_and_real_eight_processes(self):
        f,module,_=self.fixture()
        value=f.capture()
        self.assertEqual(len(value["processes"]),8)
        odoms=[x for x in value["configurations"] if Path(x["path"]).name.startswith("odometry_")]
        self.assertEqual(len(odoms),3)
        self.assertTrue(all(x["configuration"]["compiled_drive_feed_sha256"]=="6"*64 for x in odoms))

    def test_legacy_metadata_never_gets_new_source_credit(self):
        f,module,_=self.fixture()
        path=f.ep/"metadata.json";meta=json.loads(path.read_bytes());meta["safety_contract"]="legacy";write(path,meta)
        with self.assertRaisesRegex(ValueError,"legacy profile"):f.capture()

    def test_missing_feed_header_or_disabled_actual_producer_fails(self):
        for fault in ("header","feed"):
            f,module,_=self.fixture()
            path=f.ep/"drive_tb1.jsonl";cfg=json.loads(path.read_bytes())
            if fault=="header":cfg.pop("compiled_drive_feed_sha256")
            else:cfg["native_feeds_enabled"]=False
            write(path,cfg)
            with self.subTest(fault=fault),self.assertRaises(ValueError):f.capture()

    def test_new_closure_executes_original_identity_and_orderly_close_math(self):
        f,module,_,args=self.closed_fixture()
        result=self.review(f,module,args)
        self.assertTrue(result["passed"],result["errors"])
        self.assertTrue(result["all_native_owned_gone"])
        self.assertEqual(result["schema"],gate.SCHEMA_CLOSURE)

    def test_same_saved_zombie_remains_not_gone_in_new_closure(self):
        f,module,_,args=self.closed_fixture()
        f.make_proc(200,101,[str(f.root/"bin/gzserver")],f.root/"bin/gzserver",[],state="Z")
        result=self.review(f,module,args)
        self.assertFalse(result["passed"])
        self.assertTrue(any("including zombie" in e for e in result["errors"]))

    def test_old_wait_schema_and_changed_wrapper_provenance_are_rejected(self):
        for fault in ("wait","wrapper"):
            f,module,_,args=self.closed_fixture()
            capture=json.loads(args.capture.read_bytes())
            if fault=="wait":
                launch=json.loads(args.launch_receipt.read_bytes());launch.pop("schema");write(args.launch_receipt,launch)
                capture["stop"]["launch_receipt"]["sha256"]=gate.sha(args.launch_receipt.read_bytes())
                write(capture["stop_file"],capture["stop"])
            else:capture["implementation_provenance"]["effective_entry"]["sha256"]="0"*64
            write(args.capture,capture)
            with self.subTest(fault=fault):self.assertFalse(self.review(f,module,args)["passed"])

    def test_new_ready_receipt_contains_current_source_projection_and_cannot_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/"ready.json"
            receipt=gate.write_ready_receipt(path,old_tests.FREEZE,"a"*64)
            self.assertEqual(receipt["schema"],gate.SCHEMA_READY)
            self.assertEqual(receipt["safety_contract"],gate.CONTRACT)
            self.assertEqual(gate.read_ready_receipt(gate.Reader(),path,old_tests.FREEZE,"a"*64),receipt)
            with self.assertRaises(FileExistsError):gate.write_ready_receipt(path,old_tests.FREEZE,"a"*64)

    def test_qualification_wrappers_and_complete_source_chain_are_mandatory(self):
        root=Path("/declared-fixture")
        rows=[{"path":p,"sha256":"a"*64} for p in gate.REQUIRED_SOURCES]
        bound={"document":{"safety_contract":gate.CONTRACT,"execution_phase_protocol":gate.PROTOCOL,
               "source_bindings":rows,"qualification_wrappers":[dict(rows[0])]}}
        self.assertGreater(gate.binding_sources(bound,root)["required_source_count"],20)
        for fault in ("missing_source","unbound_wrapper","old_contract"):
            candidate=copy.deepcopy(bound)
            if fault=="missing_source":candidate["document"]["source_bindings"].pop()
            elif fault=="unbound_wrapper":candidate["document"]["qualification_wrappers"][0]["sha256"]="b"*64
            else:candidate["document"]["safety_contract"]="legacy"
            with self.subTest(fault=fault),self.assertRaises(ValueError):gate.binding_sources(candidate,root)


class BuildBridgeTests(unittest.TestCase):
    """Declared historical facts isolate bridge math; fake Git has no credit."""
    def setUp(self):
        temporary=tempfile.TemporaryDirectory();self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name)
        self.module,_=gate.load_implementation()
        self.native=self.root/"ros2_ws/ros2-multi-robot-automap"
        self.native.mkdir(parents=True)
        self.changed=[]
        for name in ("src/multi_robot/src/mr3_gazebo_diff_drive.cpp",
                     "src/multi_robot/include/multi_robot/mr3_drive_feed.hpp","src/multi_robot/CMakeLists.txt"):
            path=self.native/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(name)
            self.changed.append(self.spec(path))
        self.fields={"compiled_source_sha256":self.changed[0],"compiled_drive_feed_sha256":self.changed[1]}
        for field,name in (("compiled_header_sha256","mr3_gazebo_diff_drive.hpp"),
                           ("compiled_helper_sha256","paired_wheel_slew.hpp"),
                           ("compiled_target_contract_sha256","mr3_drive_target.hpp"),
                           ("compiled_odometry_json_sha256","mr3_odometry_json.hpp")):
            path=self.native/"src/multi_robot/include/multi_robot"/name
            path.write_text(name);self.fields[field]=self.spec(path)
        self.flags=self.root/gate.DRIVER_FLAGS
        self.flags.parent.mkdir(parents=True)
        self.flags_archive=self.root/gate.V15_FLAGS_ARCHIVE
        self.flags_archive.parent.mkdir(parents=True)
        definitions=['-D'+macro+'=\\"'+self.fields[field]["sha256"]+'\\"'
                     for macro,field in gate.DRIVER_DEFINITIONS.items()]
        flags=("CXX_DEFINES = "+" ".join(definitions)+"\n"
               "CXX_FLAGS = -O3 -DNDEBUG -fPIC -fno-fast-math -ffp-contract=off\n").encode()
        self.flags.write_bytes(flags);self.flags_archive.write_bytes(flags)
        verifier=self.root/gate.V15_VERIFY_SCRIPT
        verifier.parent.mkdir(parents=True,exist_ok=True);verifier.write_text("# historical verifier fixture\n")
        self.console=self.root/"console.log";self.console.write_text("actual declared CPU/build fixture\n")
        self.build=self.root/"build_wait.json";self.check=self.root/"manifest_wait.json"
        self.result=self.root/"result.json";self.manifest=self.root/"manifest.json"
        self.bridge=self.root/"bridge.json"
        base={"schema":gate.V15_WAIT_SCHEMA,"actual_waited":True,"actual_returncode":0,"passed":True,
            "source_unchanged":True,"native_admission":False,"started_monotonic_ns":3_000_000_001,
            "ended_monotonic_ns":4_000_000_002,"actual_child_wait_seconds":"1.000000001",
            "coordinator_identity":{"pid":100,"start_ticks":1000},
            "child_identity":{"pid":101,"start_ticks":1010,"parent":100},"console":self.spec(self.console)}
        build=dict(base,actual_argv=gate.V15_BUILD_ARGV,cwd=str(self.native),source_before=self.changed,
                   source_after=copy.deepcopy(self.changed));write(self.build,build)
        sources=[self.spec(verifier)]
        check=dict(base,actual_argv=["/usr/bin/python3","-B",str(verifier),str(self.result)],
                   source_before=sources,source_after=copy.deepcopy(sources));write(self.check,check)
        actual_library=self.root/"build/driver.so";actual_library.parent.mkdir()
        actual_library.write_bytes(b"\x7fELFdeclared fake driver")
        alias=self.root/"install/driver.so";alias.parent.mkdir();alias.symlink_to(actual_library)
        self.library_sha=gate.sha(actual_library.read_bytes())
        library={"path":str(alias),"real_path":str(actual_library),
                 "sha256":self.library_sha,"bytes":actual_library.stat().st_size}
        manifest={"schema":"mr3-v15-static-source-and-built-library-preparation-v1","library":library,
            "compiled_source_sha256":self.changed[0]["sha256"],"compiled_feed_header_sha256":self.changed[1]["sha256"],
            "sources":self.changed[:2],"compiler_flags":dict(self.spec(self.flags),real_path=str(self.flags))}
        write(self.manifest,manifest)
        write(self.result,{"schema":"mr3-v15-static-preparation-review-v1","passed":True,
                          "actual_library_source_and_feed_sha_match":True,"source_manifest":self.spec(self.manifest)})
        self.bound={"binaries":{"driver":{"path":library["path"],"resolved_path":library["real_path"],
                       "sha256":library["sha256"],"bytes":library["bytes"]}},
                    "document":{"compiled_sources":{"driver":self.fields}}}
        self.refresh_bridge()

    def spec(self,path):
        raw=Path(path).read_bytes()
        return {"path":str(path),"sha256":gate.sha(raw),"bytes":len(raw)}

    def refresh_bridge(self):
        write(self.bridge,{"schema":gate.SCHEMA_BUILD_BRIDGE,"safety_contract":gate.CONTRACT,"passed":True,
            "scope":"existing-v15-build-revalidated; no-new-build",
            "commands":[{"argv":gate.V15_BUILD_ARGV,"returncode":0,"observed_returncode":0}],
            "actual_wait":self.spec(self.build),"manifest_actual_wait":self.spec(self.check),
            "manifest_result":self.spec(self.result),"manifest":self.spec(self.manifest),
            "compiler_flags_archive":self.spec(self.flags_archive)})

    def refresh_result(self):
        result=json.loads(self.result.read_bytes());result["source_manifest"]=self.spec(self.manifest)
        write(self.result,result);self.refresh_bridge()

    def replace_flags(self,raw):
        """Keep enclosing fake bindings consistent so attacks reach flags predicates."""
        self.flags.write_bytes(raw);self.flags_archive.write_bytes(raw)
        value=json.loads(self.manifest.read_bytes())
        value["compiler_flags"]=dict(self.spec(self.flags),real_path=str(self.flags))
        write(self.manifest,value);self.refresh_result()

    def verify(self):
        def declared_frozen(spec,freeze,root,read):
            raw=read(spec["path"])
            gate.require(gate.sha(raw)==spec["sha256"],"fixture artifact SHA differs")
            return raw
        with patch.object(gate,"load_implementation",return_value=(self.module,{})), \
                patch.object(gate,"frozen_artifact",side_effect=declared_frozen):
            return gate.verify_build_bridge(self.bridge,old_tests.FREEZE,self.bound,root=self.root,
                                            read=self.module.Reader())

    def test_original_wait_and_manifest_can_revalidate_same_bytes_without_new_execution(self):
        result=self.verify()
        self.assertTrue(result["passed"])
        self.assertFalse(result["new_build_executed"])
        self.assertEqual(result["original_wait_seconds"],["1.000000001"]*2)
        self.assertFalse(result["source_scope"]["cmake_present_in_original_manifest"])
        self.assertEqual(result["compiled_source_fields"],sorted(self.fields))

    def test_duration_is_original_integer_ns_math_not_a_tolerant_known_97_second_claim(self):
        value=json.loads(self.build.read_bytes());value["actual_child_wait_seconds"]="1.000000002"
        write(self.build,value);self.refresh_bridge()
        with self.assertRaisesRegex(ValueError,"duration"):self.verify()

    def test_failed_rc_and_changed_source_are_not_hidden_by_passed_claims(self):
        for fault in ("rc","source","pid","waited"):
            original=json.loads(self.build.read_bytes());value=copy.deepcopy(original)
            if fault=="rc":value["actual_returncode"]=7
            elif fault=="source":value["source_after"][0]["sha256"]="b"*64
            elif fault=="pid":value["child_identity"]["pid"]=0
            else:value["actual_waited"]=False
            write(self.build,value);self.refresh_bridge()
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.verify()
            write(self.build,original)

    def test_different_actual_library_and_fabricated_command_are_rejected(self):
        self.bound["binaries"]["driver"]["sha256"]="b"*64
        with self.assertRaisesRegex(ValueError,"ELF"):self.verify()
        self.bound["binaries"]["driver"]["sha256"]=self.library_sha
        value=json.loads(self.bridge.read_bytes());value["commands"][0]["argv"]=["/bin/true"]
        write(self.bridge,value)
        with self.assertRaisesRegex(ValueError,"commands"):self.verify()

    def test_manifest_is_bound_to_its_actual_static_producer_result(self):
        value=json.loads(self.result.read_bytes());value["source_manifest"]["sha256"]="b"*64
        write(self.result,value);self.refresh_bridge()
        with self.assertRaisesRegex(ValueError,"manifest"):self.verify()

    def test_cmake_still_requires_actual_build_inventory_without_old_manifest_entry(self):
        self.assertTrue(self.verify()["passed"])
        value=json.loads(self.build.read_bytes())
        for key in ("source_before","source_after"):
            value[key]=[row for row in value[key] if not row["path"].endswith("CMakeLists.txt")]
        write(self.build,value);self.refresh_bridge()
        with self.assertRaisesRegex(ValueError,"CMake"):self.verify()

    def test_cpp_and_feed_still_require_original_elf_manifest_source_entries(self):
        original=json.loads(self.manifest.read_bytes())
        for field in ("compiled_source_sha256","compiled_drive_feed_sha256"):
            write(self.manifest,original);self.refresh_result()
            self.assertTrue(self.verify()["passed"])
            value=copy.deepcopy(original)
            value["sources"]=[row for row in value["sources"] if row["path"]!=self.fields[field]["path"]]
            write(self.manifest,value);self.refresh_result()
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,"ELF manifest"):self.verify()

    def test_archive_manifest_and_actual_flags_must_be_identical(self):
        original_flags=self.flags.read_bytes()
        original_manifest=json.loads(self.manifest.read_bytes())
        for fault in ("archive","manifest","actual"):
            self.flags.write_bytes(original_flags);self.flags_archive.write_bytes(original_flags)
            write(self.manifest,original_manifest);self.refresh_result()
            self.assertTrue(self.verify()["passed"])
            if fault=="archive":self.flags_archive.write_bytes(original_flags+b"# changed archive\n")
            elif fault=="actual":self.flags.write_bytes(original_flags+b"# changed actual\n")
            else:
                value=copy.deepcopy(original_manifest);value["compiler_flags"]["sha256"]="b"*64
                write(self.manifest,value);self.refresh_result()
            self.refresh_bridge()
            with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,"compiler flags"):self.verify()

    def test_each_of_six_compiled_source_macros_is_checked_not_just_cpp_and_feed(self):
        original=self.flags.read_bytes()
        for macro,field in gate.DRIVER_DEFINITIONS.items():
            self.replace_flags(original);self.assertTrue(self.verify()["passed"])
            self.replace_flags(original.replace(self.fields[field]["sha256"].encode(),b"b"*64))
            with self.subTest(macro=macro),self.assertRaisesRegex(ValueError,"source SHA"):self.verify()

    def test_repeated_or_comment_only_macro_does_not_bind_a_compiled_source(self):
        original=self.flags.read_bytes()
        macro="MR3_DRIVE_HEADER_SHA256"
        definition=('-D'+macro+'=\\"'+self.fields["compiled_header_sha256"]["sha256"]+'\\"').encode()
        for fault in ("repeat","comment"):
            self.replace_flags(original);self.assertTrue(self.verify()["passed"])
            candidate=(original.replace(b"CXX_DEFINES = ",b"CXX_DEFINES = "+definition+b" ")
                       if fault=="repeat" else b"# "+definition+b"\n"+original.replace(definition,b""))
            self.replace_flags(candidate)
            with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,"source SHA"):self.verify()

    def test_numeric_flags_are_required_and_cannot_be_overridden(self):
        original=self.flags.read_bytes()
        for fault in (b"-fno-fast-math",b"-ffp-contract=off",b"-ffast-math",b"-Ofast",b"-ffp-contract=fast"):
            self.replace_flags(original);self.assertTrue(self.verify()["passed"])
            candidate=(original.replace(fault,b"") if fault in (b"-fno-fast-math",b"-ffp-contract=off")
                       else original.rstrip()+b" "+fault+b"\n")
            self.replace_flags(candidate)
            with self.subTest(fault=fault),self.assertRaisesRegex(ValueError,"no-fast-math"):self.verify()

    def test_identical_flags_copy_cannot_replace_canonical_archived_artifact(self):
        self.assertTrue(self.verify()["passed"])
        alternate=self.root/"copy_flags.make";alternate.write_bytes(self.flags_archive.read_bytes())
        value=json.loads(self.bridge.read_bytes());value["compiler_flags_archive"]=self.spec(alternate)
        write(self.bridge,value)
        with self.assertRaisesRegex(ValueError,"canonical V15"):self.verify()


class RealV15BuildArchiveTests(unittest.TestCase):
    def test_real_v15_manifest_omits_cmake_and_real_original_bridge_still_verifies(self):
        """Read actual originals; only the temporary new bridge container is mocked.

        No historical artifact is rewritten and no library is executed. This is
        a reader regression fixture, not a new build or live custody receipt.
        """
        root=gate.WORKSPACE
        archive=root/gate.V15_FLAGS_ARCHIVE.parent
        build_path=archive.parent/"final_ros_build_attempt_v1/actual_wait.json"
        check_path=archive/"actual_wait.json";result_path=archive/"result.json"
        manifest_path=archive/"source_binary_manifest.json"
        build=json.loads(build_path.read_bytes());manifest=json.loads(manifest_path.read_bytes())
        cmake=str(root/"ros2_ws/ros2-multi-robot-automap/src/multi_robot/CMakeLists.txt")
        self.assertIn(cmake,{row["path"] for row in build["source_before"]})
        self.assertNotIn(cmake,{row["path"] for row in manifest["sources"]})
        self.assertEqual(manifest["compiler_flags"]["sha256"],
                         "356ffc302b8cf72eaaf5a9fec8c77facedf2b6ef12c079c4997af5df4aa88718")
        def spec(path):
            raw=path.read_bytes();return {"path":str(path),"sha256":gate.sha(raw),"bytes":len(raw)}
        native=root/"ros2_ws/ros2-multi-robot-automap/src/multi_robot"
        field_paths={"compiled_source_sha256":native/"src/mr3_gazebo_diff_drive.cpp",
            "compiled_header_sha256":native/"include/multi_robot/mr3_gazebo_diff_drive.hpp",
            "compiled_helper_sha256":native/"include/multi_robot/paired_wheel_slew.hpp",
            "compiled_target_contract_sha256":native/"include/multi_robot/mr3_drive_target.hpp",
            "compiled_odometry_json_sha256":native/"include/multi_robot/mr3_odometry_json.hpp",
            "compiled_drive_feed_sha256":native/"include/multi_robot/mr3_drive_feed.hpp"}
        library=manifest["library"]
        bound={"binaries":{"driver":{"path":library["path"],"resolved_path":library["real_path"],
            "sha256":library["sha256"],"bytes":library["bytes"]}},
            "document":{"compiled_sources":{"driver":{key:spec(path) for key,path in field_paths.items()}}}}
        freeze=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
        original_frozen=gate.frozen_artifact
        with tempfile.TemporaryDirectory() as temporary:
            bridge_path=Path(temporary)/"new_bridge_fixture.json"
            write(bridge_path,{"schema":gate.SCHEMA_BUILD_BRIDGE,"safety_contract":gate.CONTRACT,"passed":True,
                "scope":"existing-v15-build-revalidated; no-new-build",
                "commands":[{"argv":build["actual_argv"],"returncode":0,"observed_returncode":0}],
                "actual_wait":spec(build_path),"manifest_actual_wait":spec(check_path),
                "manifest_result":spec(result_path),"manifest":spec(manifest_path),
                "compiler_flags_archive":spec(root/gate.V15_FLAGS_ARCHIVE)})
            def frozen(specification,source_freeze,source_root,read):
                if Path(specification["path"])==bridge_path:
                    raw=read(bridge_path)
                    gate.require(gate.sha(raw)==specification["sha256"],"temporary bridge changed")
                    return raw
                return original_frozen(specification,source_freeze,source_root,read)
            with patch.object(gate,"frozen_artifact",side_effect=frozen):
                result=gate.verify_build_bridge(bridge_path,freeze,bound,root=root)
        self.assertTrue(result["passed"])
        self.assertFalse(result["source_scope"]["cmake_present_in_original_manifest"])
        self.assertEqual(result["original_wait_seconds"],["97.687508107","5.821476889"])
        self.assertFalse(result["new_build_executed"])
        self.assertFalse(result["native_admission"])


if __name__ == "__main__":
    unittest.main()
