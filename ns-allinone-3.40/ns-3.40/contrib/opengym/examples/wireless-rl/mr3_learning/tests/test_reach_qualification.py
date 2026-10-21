"""Independent routing/receipt attacks; all executions below are declared data.

Git admission and OS liveness are stubbed only in the qualifier bookkeeping
fixture. These tests never create a scientific qualification or launch native.
"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mr3_learning import reach_preparation as prep
from mr3_learning import native_custody_reach as custody

FREEZE="a"*40


def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value)+"\n")


class ReachQualificationTests(unittest.TestCase):
    def setUp(self):
        # Source-plan construction deliberately rejects a binding outside the
        # canonical workspace. Keep that production boundary in the fixture;
        # only the later Git/liveness bookkeeping checks are explicitly stubbed.
        temporary=tempfile.TemporaryDirectory(prefix=".mr3-reach-qualification-unit-",dir=prep.WORKSPACE)
        self.addCleanup(temporary.cleanup)
        self.root=Path(temporary.name);self.plan_path=self.root/"plan.json"
        binding=self.root/"binding.json";write(binding,{"source_bindings":[],"binaries":{}})
        self.plan=prep.build_plan(plan_path=self.plan_path,output_directory=self.root/"execution",
            run_root=self.root/"native",custody_binding=binding,binary_proof=self.root/"binary.json",
            preflight=self.root/"preflight.json",engineering_remaining_seconds="20000")
        write(self.plan_path,self.plan)

    def test_new_plan_keeps_thirty_scientific_roles_and_twelve_episodes(self):
        prep.validate_plan(self.plan)
        self.assertEqual(sum(len(prep.primitives.roles(stage)) for stage in self.plan["stages"]),30)
        self.assertEqual(sum(stage["expected_episodes"] for stage in self.plan["stages"]),12)
        self.assertTrue(all("--safety-contract" in s["native"]["argv"] for s in self.plan["stages"]))

    def exact_plan(self):
        p=copy.deepcopy(self.plan);p["seed_rule"]="exact-point-bridge-v1"
        for stage in p["stages"]:
            stage["native"]["argv"] += ["--seed-rule",p["seed_rule"]]
            for job in stage["audits"]:
                if job.get("kind")!="aggregate" and (job.get("role")=="input" or job["id"].startswith("input_")):
                    job["argv"]=["/usr/bin/python3","-m","mr3_learning.audit_seed_inputs",*job["argv"][2:]]
        relative="ros2_ws/ros2-multi-robot-automap/src/multi_robot_exploration/multi_robot_exploration/mr3_seed_certificate.py"
        p["source_bindings"][relative]=prep.sha(prep.WORKSPACE/relative)
        return p

    def test_exact_seed_rule_must_be_the_same_in_every_native_stage(self):
        p=self.exact_plan()
        prep.validate_plan(p)
        for stage in p["stages"]:
            changed=copy.deepcopy(p)
            target=changed["stages"][p["stages"].index(stage)]["native"]["argv"]
            target[target.index("--seed-rule")+1]="legacy"
            with self.assertRaisesRegex(ValueError,"seed rule differs"):
                prep.validate_plan(changed)
        p["seed_rule"]="unknown"
        with self.assertRaises(ValueError):prep.validate_plan(p)

    def test_exact_input_cannot_read_another_episode_or_write_another_output(self):
        original=self.exact_plan();prep.validate_plan(original)
        for stage_name in ("interface","reset"):
            for flag in ("--episode","--output"):
                changed=copy.deepcopy(original)
                stage=next(value for value in changed["stages"] if value["stage"]==stage_name)
                job=next(value for value in stage["audits"] if value["id"]=="input_001")
                job["argv"][job["argv"].index(flag)+1]="/synthetic/wrong-input-or-output"
                with self.subTest(stage=stage_name,flag=flag), \
                        self.assertRaisesRegex(ValueError,"input episode/output binding differs"):
                    prep.validate_plan(changed)

    def test_exact_input_cannot_omit_an_episode_or_duplicate_a_cli_flag(self):
        original=self.exact_plan();prep.validate_plan(original)
        for fault in ("missing","duplicate"):
            changed=copy.deepcopy(original)
            stage=next(value for value in changed["stages"] if value["stage"]=="reset")
            if fault=="missing":
                stage["audits"]=[value for value in stage["audits"] if value["id"]!="input_008"]
            else:
                job=next(value for value in stage["audits"] if value["id"]=="input_001")
                job["argv"] += ["--episode","/synthetic/other-episode"]
            with self.subTest(fault=fault),self.assertRaises(ValueError):prep.validate_plan(changed)

    def test_original_physics_consumer_cannot_be_replaced_by_an_always_pass_script(self):
        p=copy.deepcopy(self.plan)
        job=next(j for j in p["stages"][0]["audits"] if j.get("role")=="physics")
        job["argv"][1]="/tmp/always_pass.py"
        with self.assertRaises(ValueError):prep.validate_plan(p)

    def test_empty_fifo_aggregate_or_borrowed_wait_cannot_fill_a_scientific_role(self):
        for fault in ("aggregate","closure","watcher","role"):
            p=copy.deepcopy(self.plan);stage=p["stages"][0]
            if fault=="aggregate":
                job=next(j for j in stage["audits"] if j["id"]=="peer_control")
                job["members"]=job["depends_on"]=[]
            elif fault=="closure":
                job=next(j for j in stage["audits"] if j["id"]=="closure")
                job["argv"][job["argv"].index("--launch-receipt")+1]="/tmp/another-wait.json"
            elif fault=="watcher":stage["watcher"]["argv"][2]="mr3_learning.native_custody"
            else:stage["audits"]=[j for j in stage["audits"] if j.get("role")!="runtime"]
            with self.subTest(fault=fault),self.assertRaises(ValueError):prep.validate_plan(p)

    def test_fresh_source_projection_is_complete_and_does_not_modify_old_executor(self):
        module,proof=prep.load_executor()
        self.assertTrue(proof["whole_source_inverse_equal"])
        self.assertEqual(proof["source_sha256"],prep.PREPARATION_SHA256)
        self.assertIsNot(module,prep.primitives)
        self.assertEqual(prep.primitives.Runner.spawn.__globals__["__name__"],"mr3_learning.preparation")

    def evidence(self):
        coordinator={"pid":9001,"start_ticks":91001}
        summary={"schema":prep.EXECUTION_SCHEMA,"freeze":FREEZE,"plan_sha256":prep.sha(self.plan_path),
            "passed":True,"all_submitted_children_waited":True,"within_matrix_wall_allocation":True,
            "reach_mandatory_roles":30,"old_profile_credit_reused":False,"coordinator_identity":coordinator,
            "stages":[]}
        serial=0
        def child(spec):
            nonlocal serial
            serial+=1
            kind=spec.get("kind","subprocess_waited")
            output={"passed":True,"freeze":FREEZE}
            if kind=="fifo_manifest":output=[]
            write(spec["output"],output)
            value={"id":spec["id"],"role":spec.get("role"),"output":spec["output"],
                "output_sha256":prep.sha(spec["output"]),"passed":True,"execution_kind":kind,"returncode":0}
            if "budget_allocation" in spec:
                value["budget_allocation"]=copy.deepcopy(spec["budget_allocation"])
            if kind=="subprocess_waited":
                argv=[FREEZE if v=="{freeze}" else v for v in spec["argv"]]
                value.update(schema=custody.SCHEMA_WAIT,safety_contract=custody.CONTRACT,freeze=FREEZE,
                    plan_sha256=prep.sha(self.plan_path),argv=argv,command_argv=argv,
                    cwd=str(prep.WORKSPACE/prep.WIRELESS_RELATIVE),receipt=spec["receipt"],errors=[],
                    launcher_identity=coordinator,process_identity={"pid":10000+serial,"start_ticks":20000+serial})
                write(spec["receipt"],value)
            return value
        for i,declared in enumerate(self.plan["stages"]):
            allocation=prep.primitives.borrowed_stage_budget(self.plan,i,i*100_000_000_000)
            native=prep.primitives.budgeted_native_job(dict(declared["native"],id="native"),allocation)
            completed={"stage":declared["stage"],"status":"PASS","passed":True,"skipped_audits":[],
                "within_stage_wall_allocation":True,"budget_allocation":allocation,
                "native":child(native),"watcher":child(dict(declared["watcher"],id="watcher")),
                "audits":{j["id"]:child(j) for j in declared["audits"]}}
            summary["stages"].append(completed)
            argv=declared["native"]["argv"]
            schedule=prep.argument(argv,"--schedule").split(",")
            workers=int(prep.argument(argv,"--workers"))
            for worker in range(workers):
                for number,item in enumerate(schedule,1):
                    path=Path(declared["run_directory"])/f"worker{worker}"/(f"episode{number:03d}_"+item.replace(":","_"))/"metadata.json"
                    write(path,{"freeze":FREEZE,"safety_contract":custody.CONTRACT,
                        "quantum_steps":20,"execution_phase_protocol":"mr3-controlled-execution-phase-v2",
                        "reset_handshake":"paused-controlled-state-peer-guard-storage-v2",
                        "epoch":f"{i}:{worker}:{number}",
                        **({"seed_rule":self.plan["seed_rule"]} if "seed_rule" in self.plan else {})})
                    write(path.parent/"supervisor_metadata.json",
                        {"seed_rule":self.plan.get("seed_rule","legacy")})
        self.summary=Path(self.plan["output_directory"])/"summary.json";write(self.summary,summary)
        self.outer=self.root/"outer.json"
        write(self.outer,{"schema":"mr3-reach-outer-actual-wait-v1","scope":"engineering",
            "safety_contract":custody.CONTRACT,"actual_waited":True,"actual_returncode":0,"passed":True,
            "source_unchanged":True,"actual_argv":["/declared/python","-m","mr3_learning.reach_preparation",
                "--plan",str(self.plan_path),"--freeze",FREEZE],"child_identity":coordinator})
        return summary

    def replay(self):
        with patch.object(prep,"source_check",return_value={}),patch.object(prep.primitives,"identity",return_value=None):
            return prep._qualification_evidence(self.plan_path,FREEZE,self.outer)

    def mutate_child(self,summary,operation):
        child=summary["stages"][0]["audits"]["full"]
        operation(child)
        write(child["receipt"],child);write(self.summary,summary)

    def test_declared_closed_receipts_can_pass_bookkeeping_without_scientific_credit(self):
        self.evidence();result=self.replay()
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["episodes"]),12)
        self.assertFalse(result["policy_reliability_credit"])

    def test_worker_or_supervisor_cannot_borrow_a_different_seed_certificate(self):
        self.evidence()
        episode=Path(self.replay()["episodes"][0]["directory"])
        for filename in ("metadata.json","supervisor_metadata.json"):
            path=episode/filename;original=path.read_bytes()
            value=json.loads(original);value["seed_rule"]="exact-point-bridge-v1";write(path,value)
            with self.subTest(filename=filename),self.assertRaisesRegex(ValueError,"seed rule differs"):
                self.replay()
            path.write_bytes(original)

    def test_real_nonzero_return_or_output_false_cannot_hide_behind_passed_claims(self):
        for fault in ("rc","output","errors","argv"):
            summary=self.evidence()
            self.assertTrue(self.replay()["passed"], "attack fixture must first pass the complete bookkeeping baseline")
            def corrupt(child):
                if fault=="rc":child["returncode"]=7
                elif fault=="errors":child["errors"]=["actual failure"]
                elif fault=="argv":child["argv"]=child["command_argv"]=["/bin/true"]
                else:
                    write(child["output"],{"passed":False,"freeze":FREEZE})
                    child["output_sha256"]=prep.sha(child["output"])
            self.mutate_child(summary,corrupt)
            with self.subTest(fault=fault),self.assertRaises(ValueError):self.replay()

    def test_current_matrix_coordinator_or_same_saved_zombie_prevents_external_qualification(self):
        self.evidence()
        self.assertTrue(self.replay()["passed"], "zombie attack fixture must first pass its closed baseline")
        with patch.object(prep,"source_check",return_value={}), \
                patch.object(prep.primitives,"identity",return_value={"pid":9001,"start_ticks":91001,"state":"Z"}):
            with self.assertRaisesRegex(ValueError,"still present"):
                prep._qualification_evidence(self.plan_path,FREEZE,self.outer)

    def test_complete_closed_archive_bytes_and_file_inventory_cannot_change_after_qualification(self):
        self.evidence()
        episode = Path(self.replay()["episodes"][0]["directory"])
        archive = episode/"observation_inputs/maps/synthetic.json.gz"
        archive.parent.mkdir(parents=True,exist_ok=True)
        archive.write_bytes(b"explicit synthetic archive bytes")
        for fault in ("bytes", "added_file"):
            baseline = self.replay()
            receipt = self.root/"qualification.json"
            write(receipt,dict(baseline,schema=prep.QUALIFICATION_SCHEMA))
            with patch.object(prep,"source_check",return_value={}),patch.object(prep.primitives,"identity",return_value=None):
                self.assertTrue(prep.validate_qualification(receipt,self.plan_path,FREEZE)["passed"])
                if fault == "bytes":
                    archive.write_bytes(b"changed archive after scientific review")
                else:
                    (archive.parent/"unexpected.json.gz").write_bytes(b"unreviewed synthetic extra")
                with self.subTest(fault=fault),self.assertRaises(ValueError):
                    prep.validate_qualification(receipt,self.plan_path,FREEZE)


if __name__ == "__main__":
    unittest.main()
