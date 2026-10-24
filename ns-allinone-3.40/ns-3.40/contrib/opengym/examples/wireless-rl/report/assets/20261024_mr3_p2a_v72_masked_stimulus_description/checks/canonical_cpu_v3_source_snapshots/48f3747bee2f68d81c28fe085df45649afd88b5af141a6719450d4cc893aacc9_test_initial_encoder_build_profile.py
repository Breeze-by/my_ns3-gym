"""Synthetic new-build/profile attacks; no fake artifact supplies native credit."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import native_custody_reach as gate
from mr3_learning import reach_policy_chain as policy
from mr3_learning.tests import test_native_custody_reach as bridge_fixtures

write = bridge_fixtures.write
from mr3_learning.tests.test_reach_policy_chain import plan_fixture, native_fixture


class InitialEncoderBuildTests(unittest.TestCase):
    def setUp(self):
        self.f = f = bridge_fixtures.BuildBridgeTests(methodName="runTest")
        f.setUp(); self.addCleanup(f.doCleanups)
        self.extra = f.root/gate.INITIAL_ENCODER_HEADER
        self.extra.write_text("declared local encoder helper fixture\n")
        extra_spec = f.spec(self.extra)
        f.bound["document"].update(actuation_profile=gate.INITIAL_ENCODER_ACTUATION_PROFILE,
            initial_encoder_compiled_source={"path":gate.INITIAL_ENCODER_HEADER,"sha256":extra_spec["sha256"]})
        self.profile = f.root/gate.INITIAL_ENCODER_SOURCE_PROFILE
        self.profile.parent.mkdir(parents=True,exist_ok=True);self.profile.write_text("sealed inverse fixture\n")
        self.profile_proof = {"profile_path":str(self.profile),**{k:f.spec(self.profile)[k] for k in ("sha256","bytes")},
            "sources":{gate.INITIAL_ENCODER_HEADER:{"sha256":extra_spec["sha256"]}}}
        script=f.root/gate.INITIAL_ENCODER_BUILD_SCRIPT;script.parent.mkdir(parents=True,exist_ok=True)
        script.write_bytes((gate.WORKSPACE/gate.INITIAL_ENCODER_BUILD_SCRIPT).read_bytes())
        native_lib=Path(f.bound["binaries"]["driver"]["resolved_path"])
        native_lib.write_bytes(b"\x7fELF"+b" ".join(row["sha256"].encode() for row in [*f.fields.values(),extra_spec]))
        driver=f.bound["binaries"]["driver"];driver.update(sha256=gate.sha(native_lib.read_bytes()),bytes=native_lib.stat().st_size)
        self.archive=f.root/"new_driver.so.gz";self.archive.write_bytes(gzip.compress(native_lib.read_bytes(),mtime=0))
        self.flags = f.flags.read_bytes().replace(b"CXX_DEFINES = ",
            ("CXX_DEFINES = -DMR3_DRIVE_ENCODER_SERVO_SHA256=\\\""+extra_spec["sha256"]+"\\\" ").encode(),1)
        f.flags.write_bytes(self.flags);f.flags_archive.write_bytes(self.flags)
        source_paths=list(dict.fromkeys([Path(row["path"]) for row in [*f.fields.values(),*f.changed]]+[self.extra,script]))
        sources=[f.spec(path) for path in source_paths]
        self.wait={"schema":"mr3-reach-outer-actual-wait-v1","scope":"cpu","passed":True,"errors":[],
            "actual_waited":True,"actual_returncode":0,"source_unchanged":True,
            "actual_argv":["/bin/bash","--noprofile","--norc",str(script)],"cwd":str(f.root/gate.WIRELESS),
            "started_monotonic_ns":1_000_000_001,"ended_monotonic_ns":2_000_000_002,
            "actual_child_wait_seconds":"1.000000001","coordinator_identity":{"pid":1,"start_ticks":10},
            "child_identity":{"pid":2,"start_ticks":20,"parent":1},"source_before":sources,
            "source_after":copy.deepcopy(sources),"console":f.spec(f.console)}
        self.manifest={"schema":gate.INITIAL_ENCODER_MANIFEST_SCHEMA,"passed":True,"source_unchanged":True,
            "library":{"path":driver["path"],"real_path":driver["resolved_path"],
                       "sha256":driver["sha256"],"bytes":driver["bytes"]},
            "sources":copy.deepcopy(sources),"compiled_sources":{"driver":copy.deepcopy(f.fields)},
            "initial_encoder_compiled_source":extra_spec,
            "archived_library_gzip":dict(f.spec(self.archive),raw_bytes=driver["bytes"],raw_sha256=driver["sha256"])}
        self.scope=gate.INITIAL_ENCODER_BUILD_SCOPE
        self.refresh()

    def refresh(self):
        f=self.f;write(f.build,self.wait)
        self.manifest.update(actual_wait=f.spec(f.build),compiler_flags=dict(f.spec(f.flags),real_path=str(f.flags)),
                             compiler_flags_archive=f.spec(f.flags_archive))
        write(f.manifest,self.manifest)
        write(f.bridge,{"schema":gate.SCHEMA_BUILD_BRIDGE,"safety_contract":gate.CONTRACT,"passed":True,
            "scope":self.scope,"actuation_profile":gate.INITIAL_ENCODER_ACTUATION_PROFILE,
            "actual_wait":f.spec(f.build),"manifest":f.spec(f.manifest),
            "compiler_flags_archive":f.spec(f.flags_archive),"source_derivation":f.spec(self.profile),
            "commands":[{"argv":self.wait["actual_argv"],"returncode":0,"observed_returncode":0}]})

    def verify(self):
        f=self.f
        def frozen(spec,freeze,root,read):
            path=Path(spec["path"]);path=path if path.is_absolute() else root/path
            raw=read(path);gate.require(gate.sha(raw)==spec["sha256"],"fixture artifact SHA differs");return raw
        def fake_git(argv,cwd):
            return (Path(cwd)/argv[2].split(":",1)[1]).read_bytes()
        with patch.object(gate,"load_implementation",return_value=(f.module,{})), \
             patch.object(gate,"frozen_artifact",side_effect=frozen), \
             patch.object(gate,"verify_initial_encoder_source_profile",return_value=self.profile_proof), \
             patch.object(gate.subprocess,"check_output",side_effect=fake_git):
            return gate.verify_build_bridge(f.bridge,"a"*40,f.bound,root=f.root,read=f.module.Reader())

    def test_actual_new_build_does_not_claim_native_or_historical_credit(self):
        result=self.verify()
        self.assertTrue(result["passed"]);self.assertTrue(result["new_build_executed"])
        self.assertEqual(result["actuation_profile"],gate.INITIAL_ENCODER_ACTUATION_PROFILE)
        self.assertEqual(len(result["compiled_source_fields"]),7)
        self.assertFalse(result["native_admission"])

    def test_new_profile_cannot_borrow_old_scope_or_drop_helper(self):
        self.scope="existing-v15-build-revalidated; no-new-build";self.refresh()
        with self.assertRaisesRegex(ValueError,"cannot borrow"):self.verify()
        self.scope=gate.INITIAL_ENCODER_BUILD_SCOPE;self.refresh()
        self.f.bound["document"].pop("initial_encoder_compiled_source")
        with self.assertRaisesRegex(ValueError,"seventh"):self.verify()

    def test_failed_wait_changed_sources_and_false_duration_reject(self):
        for fault in ("returncode","sources","duration"):
            old=copy.deepcopy(self.wait)
            if fault=="returncode":self.wait["actual_returncode"]=1
            elif fault=="sources":self.wait["source_after"][-1]["sha256"]="0"*64
            else:self.wait["actual_child_wait_seconds"]="1.000000002"
            self.refresh()
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.verify()
            self.wait=old

    def test_missing_real_helper_or_cmake_build_input_rejects(self):
        for path in (self.extra,self.f.native/"src/multi_robot/CMakeLists.txt"):
            old=copy.deepcopy(self.wait)
            self.wait["source_before"]=[r for r in self.wait["source_before"] if r["path"]!=str(path)]
            self.wait["source_after"]=copy.deepcopy(self.wait["source_before"]);self.refresh()
            with self.subTest(path=path),self.assertRaises(ValueError):self.verify()
            self.wait=old

    def test_seventh_macro_and_numeric_options_are_not_optional(self):
        faults=[self.flags.replace(b"MR3_DRIVE_ENCODER_SERVO_SHA256",b"WRONG_ENCODER_MACRO"),
                self.flags.replace(b"-ffp-contract=off",b"-ffp-contract=fast"),
                self.flags.replace(b"-fno-fast-math",b"-ffast-math")]
        for raw in faults:
            self.f.flags.write_bytes(raw);self.f.flags_archive.write_bytes(raw);self.refresh()
            with self.subTest(raw=raw[:40]),self.assertRaises(ValueError):self.verify()

    def test_archive_cannot_substitute_a_different_binary(self):
        self.archive.write_bytes(gzip.compress(b"\x7fELFother",mtime=0))
        self.manifest["archived_library_gzip"].update(self.f.spec(self.archive));self.refresh()
        with self.assertRaisesRegex(ValueError,"archive"):self.verify()


class InitialEncoderProfileTests(unittest.TestCase):
    def test_profile_is_explicit_and_unknown_or_unlabelled_helper_is_rejected(self):
        self.assertIsNone(gate.initial_encoder_profile({}))
        self.assertEqual(gate.initial_encoder_profile({"actuation_profile":gate.INITIAL_ENCODER_ACTUATION_PROFILE}),
                         gate.INITIAL_ENCODER_ACTUATION_PROFILE)
        for bad in ({"actuation_profile":None},{"actuation_profile":"other"},{"initial_encoder_compiled_source":{}}):
            with self.subTest(bad=bad),self.assertRaises(ValueError):gate.initial_encoder_profile(bad)

    def test_real_source_profile_recovers_complete_old_sources_without_world(self):
        def current(spec,freeze,root,read):
            path=Path(spec["path"]);path=path if path.is_absolute() else root/path
            raw=read(path);gate.require(gate.sha(raw)==spec["sha256"],"fixture SHA differs");return raw
        module,_=gate.load_implementation()
        with patch.object(gate,"frozen_artifact",side_effect=current):
            result=gate.verify_initial_encoder_source_profile("a"*40,gate.WORKSPACE,module.Reader())
        self.assertEqual(set(result["sources"]),set(gate.INITIAL_ENCODER_BASELINES))
        self.assertTrue(all(row["whole_source_inverse"] for row in result["sources"].values()))
        with patch.object(gate,"INITIAL_ENCODER_SOURCE_PROFILE_SHA256",None),self.assertRaisesRegex(ValueError,"not been sealed"):
            gate.verify_initial_encoder_source_profile("a"*40,gate.WORKSPACE,module.Reader())

    def test_actual_producer_prefix_binds_helper_and_does_not_follow_growing_tail(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"drive_tb1.jsonl"
            config={"kind":"initial_encoder_configuration","epoch":"e","robot":"tb1",
                "actuation_profile":gate.INITIAL_ENCODER_ACTUATION_PROFILE,"compiled_encoder_servo_sha256":"7"*64,
                "position_gain_per_second":1.0,"feedback_rim_limit_mps":.005,"capture_rim_limit_mps":.01,
                "capture_consecutive_samples":3,"update_period_ns":34000000,"reference_capture_count_limit":1,
                "received_nonzero_latch":"first successfully validated stored target; not consumption",
                "reference_lifetime":"one fresh plugin object/epoch; Reset does not rearm"}
            prefix=json.dumps({"kind":"configuration"})+"\n"+json.dumps(config)+"\n"
            path.write_text(prefix)
            expected=gate.initial_encoder_configuration(path,epoch="e",robot="tb1",helper_sha256="7"*64)
            path.write_text(prefix+json.dumps({"kind":"later"})+"\n")
            self.assertEqual(gate.initial_encoder_configuration(path,epoch="e",robot="tb1",helper_sha256="7"*64),expected)
            with self.assertRaises(ValueError):gate.initial_encoder_configuration(path,epoch="e",robot="tb1",helper_sha256="8"*64)
            path.write_text(prefix.rstrip("\n"))
            with self.assertRaises(FileNotFoundError):gate.initial_encoder_configuration(path,epoch="e",robot="tb1",helper_sha256="7"*64)

    def test_three_policy_registry_entries_require_one_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            plan,path,qualification=plan_fixture(Path(directory));plan["actuation_profile"]=gate.INITIAL_ENCODER_ACTUATION_PROFILE
            for spec in plan["policy_stages"].values():spec["actuation_profile"]=gate.INITIAL_ENCODER_ACTUATION_PROFILE
            for stage in policy.STAGES:policy.stage_spec(plan,path,qualification,stage)
            plan["policy_stages"]["pilot"].pop("actuation_profile")
            with self.assertRaisesRegex(ValueError,"actuation profile"):policy.stage_spec(plan,path,qualification,"pilot")

    def test_policy_result_requires_each_independent_new_law_replay(self):
        metadata,native,audit,episodes,spec=native_fixture()
        for row in (metadata,native,spec):row["actuation_profile"]=gate.INITIAL_ENCODER_ACTUATION_PROFILE
        with self.assertRaisesRegex(ValueError,"compound-law"):policy.check_native_result("minimum",metadata,native,audit,episodes,spec)
        audit["reach_episodes"]=[{"runtime_drive":{"passed":True,"actuation_profile":gate.INITIAL_ENCODER_ACTUATION_PROFILE,
            "initial_encoder_compound_replay_passed":True}} for _ in episodes]
        self.assertEqual(policy.check_native_result("minimum",metadata,native,audit,episodes,spec)["eligible_decisions"],16)
        audit["reach_episodes"][1]["runtime_drive"]["initial_encoder_compound_replay_passed"]=False
        with self.assertRaisesRegex(ValueError,"compound-law"):policy.check_native_result("minimum",metadata,native,audit,episodes,spec)


if __name__ == "__main__":
    unittest.main()
