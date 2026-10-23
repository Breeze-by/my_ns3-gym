"""Artificial v2 math/dispatch/provenance attacks; no native evidence or World."""
import ast
import copy
from fractions import Fraction as Q
import hashlib
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import audit_reach_runtime as a
from mr3_learning import audit_reach_cadence as cadence
from mr3_learning import reach_support_replay as support
from mr3_learning import reach_gates as gates
from mr3_learning import native_custody_reach as custody
from mr3_learning import reach_preparation
from mr3_learning.tests import test_audit_reach_runtime as fixture
from mr3_learning.tests import test_native_custody_reach as custody_fixture


RULE = "cone-support-v2"
DEFAULT = "binary-cone-v1"
L = Q(18, 125)
FREEZE = "a"*40


class SupportMathTests(unittest.TestCase):
    def test_independent_module_has_no_production_or_tracker_import(self):
        tree = ast.parse(Path(support.__file__).read_text())
        imported = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imported += [x.name for n in ast.walk(tree) if isinstance(n, ast.Import) for x in n.names]
        self.assertEqual(set(imported), {"fractions", "functools", "math"})

    def test_exact_root_enclosure_perfect_nonperfect_tiny_and_large(self):
        for x in (Q(0), Q(1,64), Q(2), Q(3,7), Q(1,2**400), Q(10**40+1)):
            with self.subTest(x=x):
                lo, hi = support.sqrt_interval(x)
                self.assertLessEqual(lo*lo, x); self.assertGreaterEqual(hi*hi, x)
                self.assertLessEqual(hi-lo, Q(1,2**96))
                if hi == lo:self.assertEqual(lo*lo,x)
        for bad in (-1, True, math.inf):
            with self.subTest(bad=bad), self.assertRaises(ValueError):support.sqrt_interval(bad)

    def test_extra_uncertainty_units_are_L_times_ratio_and_origin_is_preserved(self):
        self.assertEqual(support.direction_support_upper((Q(1,8),0), (Q(-3,5),Q(4,5)),
            0,Q(1,10),L), L/5)
        self.assertEqual(support.direction_support_upper((1,0),(-1,0),0,Q(1,10),L),0)
        self.assertEqual(support.direction_support_upper((1,0),(0,1),0,0,L),0)

    def test_fallbacks_and_nonunit_axis_scaling(self):
        for bearing, axis, phi, uncertainty in (
                ((0,0),(-1,0),0,0), ((1,0),(1,0),Q(1,5),0),
                ((1,0),(-1,0),2,0), ((Q(1,2**300),0),(-1,1),1,Q(1,100))):
            self.assertEqual(support.direction_support_upper(bearing,axis,phi,uncertainty,L),L)
        for scale in (Q(1,1024), Q(1), Q(7), Q(2**100)):
            self.assertEqual(support.direction_support_upper((Q(1,8),0),
                (scale*Q(-3,5),scale*Q(4,5)),0,Q(1,10),L),L/5)
        for axis in ((0,0),(True,0),(math.nan,1)):
            with self.assertRaises(ValueError):support.direction_support_upper((1,0),axis,0,0,L)

    def test_upper_dominates_independent_sampled_directions_not_a_continuous_proof(self):
        for bearing in ((1.,0.),(-.45,.45),(-.45,-.45)):
            for axis in ((1.,0.),(-.6,.8)):
                for phi in (0.,.3,.996,1.536,2.):
                    upper=float(support.direction_support_upper(bearing,axis,phi,Q(3,100),L))
                    norm=math.hypot(*bearing); heading=math.atan2(axis[1],axis[0])
                    for fraction in (-1.,-.5,0.,.5,1.):
                        angle=heading+fraction*phi
                        observed=float(L)*max(0.,(bearing[0]*math.cos(angle)+bearing[1]*math.sin(angle))/norm)
                        self.assertGreaterEqual(upper+1e-12,observed)


class RuntimeRuleTests(unittest.TestCase):
    def support_fixture(self):
        value=fixture.fixture()
        value["metadata"]["reach_geometry_rule"]=RULE
        value["motion"][0]["payload"]["reach_geometry_rule"]=RULE
        return value

    def test_default_public_result_is_unchanged_and_v2_is_explicit(self):
        old=a._audit_records(**fixture.fixture())
        self.assertNotIn("reach_geometry_rule",old)
        report=a._audit_records(**self.support_fixture())
        self.assertTrue(report["passed"])
        self.assertEqual(report["reach_geometry_rule"],RULE)

    def test_rule_metadata_cannot_relabel_actual_motion_configuration(self):
        for metadata_rule, configuration_rule in ((RULE,None),(None,RULE),(RULE,DEFAULT)):
            value=fixture.fixture()
            if metadata_rule is not None:value["metadata"]["reach_geometry_rule"]=metadata_rule
            if configuration_rule is not None:value["motion"][0]["payload"]["reach_geometry_rule"]=configuration_rule
            with self.subTest(pair=(metadata_rule,configuration_rule)),self.assertRaisesRegex(ValueError,"configuration geometry"):
                a._audit_records(**value)

    def test_unknown_null_truthy_and_wrong_contract_rules_reject(self):
        self.assertEqual(a.geometry_rule({}),DEFAULT)
        for rule in (None,True,1,"unknown"):
            with self.subTest(rule=rule),self.assertRaises(ValueError):
                a.geometry_rule({"reach_geometry_rule":rule,"safety_contract":a.CONTRACT})
        with self.assertRaises(ValueError):a.geometry_rule({"reach_geometry_rule":RULE,"safety_contract":"legacy"})

    def test_actual_allowed_decision_dispatches_independent_v2(self):
        value=self.support_fixture()
        decision=next(x for x in value["motion"] if x["kind"]=="reach_decision")
        decision["payload"]["decision"]["allow"]=True  # Real artificial HOLD zero, not a new command.
        with patch.object(a,"independent_pair",wraps=a.independent_pair) as independent:
            self.assertTrue(a._audit_records(**value)["passed"])
        self.assertEqual(independent.call_count,2)
        self.assertTrue(all(x.kwargs=={"reach_geometry_rule":RULE} for x in independent.call_args_list))

    def test_D_turn_filter_dispatches_same_v2_and_cannot_invent_a_turn(self):
        def disk_state(robot):
            target=fixture.target(robot,fixture.BEGIN,1)
            owner=fixture.intent(robot,fixture.BEGIN,1,target)
            owner.update(role="D",lineage={"anchor_intent_sequence":1})
            return fixture.state(robot,fixture.BEGIN,owner)
        own=disk_state("tb1");peers={name:disk_state(name) for name in ("tb2","tb3")}
        row={"intent":copy.deepcopy(own["safety"]["intent"]),"request":{
            "supported":True,"publisher_identity":{"valid":True},"received_stamp":fixture.BEGIN/10**9,
            "v":.1,"w":.2},"decision":{"output":[0.,.2],
            "component_filter":{"canonical_input":[.1,.2],"rejected_transition_checks":{}},
            "reason":"linear_brake_preserve_requested_turn"}}
        with patch.object(a,"independent_pair",wraps=a.independent_pair) as independent:
            a.admitted_command(row,own,own,peers,fixture.BEGIN,fixture.EPOCH,reach_geometry_rule=RULE)
        self.assertEqual(independent.call_count,2)
        self.assertTrue(all(x.kwargs=={"reach_geometry_rule":RULE} for x in independent.call_args_list))
        row["decision"]["output"][1]=-.2
        with self.assertRaises(ValueError):
            a.admitted_command(row,own,own,peers,fixture.BEGIN,fixture.EPOCH,reach_geometry_rule=RULE)

    def test_artificial_triangle_new_support_and_raw_map_AND_and_union(self):
        own={"x":0.,"y":0.};peer={"x":-.45,"y":.45}
        left=(fixture.raw(fixture.BEGIN,xy=(0.,0.)),4*a.R,"X",(1,),((Q(1),Q(0)),)*2,50_000_000)
        right=(fixture.raw(fixture.BEGIN,xy=(-.45,.45)),2*a.R,"D",(),((Q(1),Q(0)),)*2,50_000_000)
        with patch.object(a,"state_geometry",side_effect=[left,right]*2):
            self.assertFalse(a.independent_pair(own,peer,fixture.BEGIN,fixture.EPOCH))
            self.assertTrue(a.independent_pair(own,peer,fixture.BEGIN,fixture.EPOCH,reach_geometry_rule=RULE))
        reversed_raw=(fixture.raw(fixture.BEGIN,xy=(.45,.45)),*right[1:])
        with patch.object(a,"state_geometry",side_effect=[left,reversed_raw]):
            self.assertFalse(a.independent_pair(own,peer,fixture.BEGIN,fixture.EPOCH,reach_geometry_rule=RULE))
        two_signs=(*left[:3],(1,-1),*left[4:])
        with patch.object(a,"state_geometry",side_effect=[two_signs,right]):
            self.assertFalse(a.independent_pair(own,peer,fixture.BEGIN,fixture.EPOCH,reach_geometry_rule=RULE))

    def test_run_cannot_combine_geometry_versions_or_mislabel_benchmark(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def save(index,rule):
                p=root/"worker0"/("episode"+str(index));p.mkdir(parents=True)
                metadata={"epoch":"artificial"+str(index),"freeze":FREEZE,"safety_contract":a.CONTRACT,
                    "execution_phase_protocol":"mr3-controlled-execution-phase-v2",
                    "reset_handshake":"paused-controlled-state-peer-guard-storage-v2"}
                if rule!=DEFAULT:metadata["reach_geometry_rule"]=rule
                (p/"metadata.json").write_text(json.dumps(metadata));return p,metadata
            first,meta=save(1,RULE);second,other=save(2,DEFAULT)
            def report(p,f):
                md=json.loads((p/"metadata.json").read_text())
                return {"passed":True,"errors":[],"epoch":md["epoch"],"freeze":f,
                    **({"reach_geometry_rule":RULE} if md.get("reach_geometry_rule")==RULE else {})}
            result=a.audit_episode_set(root,FREEZE,report,schema="artificial")
            self.assertFalse(result["passed"])
            self.assertIn("geometry rule differs",str(result["errors"]))
            other["reach_geometry_rule"]=RULE;(second/"metadata.json").write_text(json.dumps(other))
            self.assertTrue(a.audit_episode_set(root,FREEZE,report,schema="artificial")["passed"])
            (root/"benchmark_summary.json").write_text(json.dumps({"workers_results":[{"episodes":[
                {"output_directory":str(first)},{"output_directory":str(second)}]}]}))
            self.assertFalse(a.audit_episode_set(root,FREEZE,report,schema="artificial")["passed"])


class SupportSourceGateTests(unittest.TestCase):
    def test_source_proof_checks_both_helpers_against_current_and_frozen_bytes_only_in_v2(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);entry=root/"reader.py"
            names=(*a.SOURCES,"ros2_ws/ros2-multi-robot-automap/scripts/mr3_env_worker.py",
                a.NATIVE+"launch/gazebo_multirobot_mapping_with_nav2.launch.py","reader.py",
                a.PURE+"mr3_reach_support.py","reach_support_replay.py")
            frozen={name:(name+" mr3-drive-applied-v1 mr3-reach-v1").encode() for name in names}
            for name,raw in frozen.items():
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
            def git(argv,**kwargs):return frozen[argv[2].split(":",1)[1]]
            with patch.object(a,"__file__",str(entry)),patch.object(a.subprocess,"check_output",side_effect=git):
                old=a.source_proof(root,FREEZE)
                self.assertNotIn("reach_support_replay.py",old)
                new=a.source_proof(root,FREEZE,reach_geometry_rule=RULE)
                self.assertIn(a.PURE+"mr3_reach_support.py",new)
                self.assertIn("reach_support_replay.py",new)
                (root/"reach_support_replay.py").write_bytes(b"tampered")
                with self.assertRaises(ValueError):a.source_proof(root,FREEZE,reach_geometry_rule=RULE)
                (root/"reach_support_replay.py").unlink()
                with self.assertRaises(OSError):a.source_proof(root,FREEZE,reach_geometry_rule=RULE)

    def test_support_pins_preserve_cf46_and_require_both_independent_and_production_helpers(self):
        prefix=gates.ROS+"src/multi_robot_exploration/multi_robot_exploration/"
        sources={prefix+"mr3_reach_geometry.py":gates.SUPPORT_REFERENCE_GEOMETRY_SHA256,
            prefix+"mr3_reach_support.py":"b"*64,
            "ns-allinone-3.40/ns-3.40/contrib/opengym/examples/wireless-rl/mr3_learning/reach_support_replay.py":"c"*64}
        self.assertEqual(gates._support_geometry_pins(sources),sources)
        for name in sources:
            broken=dict(sources);broken.pop(name)
            with self.subTest(name=name),self.assertRaises((KeyError,ValueError)):gates._support_geometry_pins(broken)
        sources[prefix+"mr3_reach_geometry.py"]="d"*64
        with self.assertRaises(ValueError):gates._support_geometry_pins(sources)

    def test_public_gate_passes_explicit_rule_and_preserves_default_omission(self):
        base={"source_bindings":{},"custody_binding":"artificial"}
        for rule in (DEFAULT,RULE):
            plan={**base,**({"reach_geometry_rule":rule} if rule!=DEFAULT else {})}
            with patch.object(reach_preparation,"load_plan",return_value=plan), \
                    patch.object(reach_preparation,"source_check",return_value={}), \
                    patch.object(gates,"_load_versioned_native_gates",return_value="artificial") as load:
                self.assertEqual(gates.load_native_gates(Path("/fixture"),FREEZE,Path("/plan")),"artificial")
            self.assertEqual(load.call_args.kwargs,{} if rule==DEFAULT else {"reach_geometry_rule":RULE})

    def test_custody_inventory_requires_new_helpers_only_for_v2(self):
        root=Path("/artificial")
        rows=[{"path":p,"sha256":"a"*64} for p in custody.REQUIRED_SOURCES]
        document={"safety_contract":custody.CONTRACT,"execution_phase_protocol":custody.PROTOCOL,
            "source_bindings":rows,"qualification_wrappers":[dict(rows[0])]}
        self.assertNotIn("reach_geometry_rule",custody.binding_sources({"document":document},root))
        document["reach_geometry_rule"]=RULE
        with self.assertRaises(ValueError):custody.binding_sources({"document":document},root)
        document["source_bindings"]=[*rows,*({"path":p,"sha256":"b"*64} for p in custody.SUPPORT_SOURCES)]
        proof=custody.binding_sources({"document":document},root)
        self.assertEqual(proof["reach_geometry_rule"],RULE)
        self.assertEqual(proof["required_source_count"],len(custody.REQUIRED_SOURCES)+2)

    def test_custody_episode_supervisor_and_binding_rule_cannot_differ(self):
        metadata={"epoch":"artificial","freeze":FREEZE,"safety_contract":custody.CONTRACT,"quantum_steps":20,
            "execution_phase_protocol":custody.PROTOCOL,
            "reset_handshake":"paused-controlled-state-peer-guard-storage-v2","reach_geometry_rule":RULE}
        saved={"epoch":"artificial","safety_contract":custody.CONTRACT,"reach_geometry_rule":RULE}
        def read(path):return json.dumps(metadata if Path(path).name=="metadata.json" else saved).encode()
        self.assertEqual(custody.profile_metadata(Path("/artificial"),FREEZE,read,reach_geometry_rule=RULE),metadata)
        with self.assertRaises(ValueError):custody.profile_metadata(Path("/artificial"),FREEZE,read,reach_geometry_rule=DEFAULT)
        saved.pop("reach_geometry_rule")
        with self.assertRaises(ValueError):custody.profile_metadata(Path("/artificial"),FREEZE,read,reach_geometry_rule=RULE)

    def test_live_custody_reads_real_motion_envelope_payload_not_a_mocked_configuration(self):
        owner=custody_fixture.ReachNativeCustodyTests(methodName="runTest")
        self.addCleanup(owner.doCleanups)
        f,module,_=owner.fixture()
        f.binding["document"].update(safety_contract=custody.CONTRACT,reach_geometry_rule=RULE)
        for name in ("metadata.json","supervisor_metadata.json"):
            path=f.ep/name;value=json.loads(path.read_bytes())
            value.update(safety_contract=custody.CONTRACT,reach_geometry_rule=RULE)
            path.write_text(json.dumps(value)+"\n")
        # Actual motion log shape: the outer row is a journal envelope, while
        # controlled_execution, robots and the selected rule live in payload.
        motion=copy.deepcopy(fixture.fixture()["motion"][0])
        motion["epoch"]=json.loads((f.ep/"metadata.json").read_bytes())["epoch"]
        motion["payload"]["reach_geometry_rule"]=RULE
        path=f.ep/"motion_safety.jsonl";path.write_text(json.dumps(motion)+"\n")
        entries=module.configurations(f.ep,f.binding)
        recorded=next(x for x in entries if Path(x["path"]).name=="motion_safety.jsonl")
        self.assertEqual(recorded["configuration"],motion)
        self.assertEqual(recorded["first_line_sha256"],hashlib.sha256(path.read_bytes()).hexdigest())
        motion["reach_geometry_rule"]=motion["payload"].pop("reach_geometry_rule")
        path.write_text(json.dumps(motion)+"\n")
        with self.assertRaisesRegex(ValueError,"live motion configuration"):
            module.configurations(f.ep,f.binding)

    def test_cadence_source_proof_forwards_actual_v2_rule(self):
        with patch.object(cadence.runtime,"source_proof",return_value={}) as source, \
                patch.object(cadence.subprocess,"check_output",side_effect=lambda argv,**kw:
                    (cadence.WORKSPACE/argv[2].split(":",1)[1]).read_bytes()):
            proof=cadence.source_proof(FREEZE,reach_geometry_rule=RULE)
        self.assertEqual(source.call_args.kwargs,{"reach_geometry_rule":RULE})
        self.assertTrue(proof)


if __name__ == "__main__":
    unittest.main()
