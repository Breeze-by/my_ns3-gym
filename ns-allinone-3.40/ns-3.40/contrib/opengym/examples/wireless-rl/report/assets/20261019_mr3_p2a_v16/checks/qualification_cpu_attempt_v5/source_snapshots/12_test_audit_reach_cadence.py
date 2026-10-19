"""Reach cadence/source and conjunction attacks on declared artifact fixtures."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from mr3_learning import audit_reach_cadence as gate
from mr3_learning.tests import test_audit_odometry_cadence as old_tests


class ReachCadenceTests(unittest.TestCase):
    def case(self):
        original=old_tests.OdometryCadenceTests(methodName="runTest")
        directory=original.case();self.addCleanup(original.doCleanups)
        path=directory/"metadata.json";meta=json.loads(path.read_bytes())
        meta.update(safety_contract=gate.CONTRACT,quantum_steps=20,
                    execution_phase_protocol="mr3-controlled-execution-phase-v2",
                    reset_handshake="paused-controlled-state-peer-guard-storage-v2")
        old_tests.write(path,meta)
        for robot in gate.ROBOTS:
            for prefix in ("drive_","odometry_"):
                old_tests.mutate(directory/(prefix+robot+".jsonl"),lambda rows:
                    rows[0].update(compiled_drive_feed_sha256="6"*64))
        def new_decisions(rows):
            for row in rows:
                if row["kind"]=="decision":row["kind"]="reach_decision"
        old_tests.mutate(directory/"motion_safety.jsonl",new_decisions)
        return directory

    def necessary_math(self,directory):
        module,_=gate.load_implementation()
        return module.audit(directory,old_tests.FREEZE)

    def test_complete_projection_preserves_original_helper_and_is_private(self):
        raw=(gate.WORKSPACE/gate.HELPER).read_bytes()
        _,proof=gate.project_source(raw)
        self.assertEqual(proof["inverse_sha256"],gate.HELPER_SHA256)
        first,_=gate.load_implementation();second,_=gate.load_implementation()
        first.ROBOTS=("tb1",)
        self.assertEqual(second.ROBOTS,gate.ROBOTS)
        self.assertEqual(len(old_tests.audit.COMPILED),5)
        with self.assertRaises(ValueError):gate.project_source(raw+b"\n# extra change\n")

    def test_new_reach_decisions_use_original_relative20ms_and34ms_math(self):
        result=self.necessary_math(self.case())
        self.assertTrue(result["passed"],result["errors"])
        self.assertEqual(result["schema"],gate.SCHEMA)
        self.assertEqual(result["episodes"][0]["selected_received"]["guard"]["tb1"],11)

    def test_old_profile_or_old_decision_schema_cannot_fill_new_role(self):
        for fault in ("profile","decision"):
            directory=self.case()
            if fault=="profile":
                path=directory/"metadata.json";meta=json.loads(path.read_bytes());meta["safety_contract"]="legacy";old_tests.write(path,meta)
            else:
                def old(rows):
                    for row in rows:
                        if row["kind"]=="reach_decision":row["kind"]="decision"
                old_tests.mutate(directory/"motion_safety.jsonl",old)
            with self.subTest(fault=fault):self.assertFalse(self.necessary_math(directory)["passed"])

    def test_exact20ms_hole_and_actual34ms_change_still_fail(self):
        for fault in ("odom","actuation"):
            directory=self.case()
            if fault=="odom":
                def remove(rows):
                    rows.pop(5)
                    for i,row in enumerate(rows,1):
                        row["record_sequence"]=i
                        if row["kind"]=="publication":row["publication_sequence"]=i-1
                old_tests.mutate(directory/"odometry_tb3.jsonl",remove)
            else:old_tests.mutate(directory/"drive_tb3.jsonl",lambda rows:rows[1].update(dt_ns=20_000_000))
            with self.subTest(fault=fault):self.assertFalse(self.necessary_math(directory)["passed"])

    def test_sixth_compiled_source_must_match_both_real_producers(self):
        directory=self.case()
        old_tests.mutate(directory/"drive_tb3.jsonl",lambda rows:rows[0].update(compiled_drive_feed_sha256="a"*64))
        self.assertFalse(self.necessary_math(directory)["passed"])

    def test_new_guard_cannot_select_an_older_received_source(self):
        directory=self.case()
        def stale(rows):
            p=next(v["payload"] for v in rows if v["kind"]=="reach_decision"
                   and v["payload"]["clock_ns"]==old_tests.BEGIN+gate.PERIOD)
            p["own_state"]["input_sequences"]["odom"]=1
            p["own_state"]["odom_source_stamp"]=(old_tests.BEGIN-5_000_000)/1e9
        old_tests.mutate(directory/"motion_safety.jsonl",stale)
        self.assertFalse(self.necessary_math(directory)["passed"])

    def test_packet_gid_and_complete_tf_tail_are_still_mandatory(self):
        for fault in ("gid","tail"):
            directory=self.case()
            def corrupt(rows):
                if fault=="gid":rows[2]["publisher_gid"]="00"*24
                else:
                    selected=next(i for i in range(len(rows)-1,-1,-1) if rows[i]["kind"]=="tf")
                    rows.pop(selected)
                    for i,row in enumerate(rows,1):row["record_sequence"]=i
            old_tests.mutate(directory/"driver_odometry_receipts.jsonl",corrupt)
            with self.subTest(fault=fault):self.assertFalse(self.necessary_math(directory)["passed"])

    def test_public_role_requires_complete_runtime_v2_and_never_uses_cadence_alone(self):
        directory=self.case()
        with patch.object(gate,"source_proof",return_value={}), \
                patch.object(gate.runtime,"audit_episode",side_effect=ValueError("actual v1 status has no reach credit")) as full:
            result=gate.audit(directory,old_tests.FREEZE)
        self.assertFalse(result["passed"])
        full.assert_called_once_with(directory,old_tests.FREEZE)
        self.assertIn("actual v1 status",result["errors"][0]["error"])

    def test_public_role_conjoins_current_source_bound_runtime_and_preserves_scope(self):
        directory=self.case()
        report={"passed":True,"independent_necessary_replay":True,"continuous_physical_model_proved":False}
        with patch.object(gate,"source_proof",return_value={"fixture":"not scientific credit"}), \
                patch.object(gate.runtime,"audit_episode",return_value=report) as full:
            result=gate.audit(directory,old_tests.FREEZE)
        self.assertTrue(result["passed"],result["errors"])
        self.assertTrue(result["actual_loaded_elf_custody_required"])
        self.assertFalse(result["continuous_physical_model_proved"])
        full.assert_called_once_with(directory,old_tests.FREEZE)


if __name__ == "__main__":
    unittest.main()
