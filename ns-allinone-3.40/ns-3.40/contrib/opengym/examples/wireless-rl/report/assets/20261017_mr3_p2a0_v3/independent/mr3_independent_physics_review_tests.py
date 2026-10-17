import copy
import json
from pathlib import Path
import unittest
from mr3_independent_physics_review import robot_physics, native_cancel_events


def fixture(deceleration=.5):
    rows=[]
    for i in range(46):
        clock=900000000+round(i*1000000000/30)
        t=(clock-1200000000)/1e9
        braking=max(0.,min(t-.16,.2/deceleration))
        v=.2-deceleration*braking
        if t<=.16:x=.2*(clock/1e9-.9)
        else:x=.2*(1.36-.9)+.2*braking-.5*deceleration*braking**2
        rows.append({"source_ns":clock,"xy":[x,0.],"planar_speed":v,"angular_norm":0.,"abs_wz":0.,"frames":["odom","base_footprint"]})
    commands=[{"clock_ns":1000000000,"v":.2,"w":0.},{"clock_ns":1100000000,"v":.2,"w":0.},{"clock_ns":1200000000,"v":0.,"w":.5}]
    return rows,commands


class IndependentPhysicsTests(unittest.TestCase):
    def test_meaningful_stop_gets_only_sampled_range_credit(self):
        rows,commands=fixture()
        result=robot_physics(rows,commands,1000000000,2400000000)
        self.assertTrue(result["physical_evidence_complete"])
        self.assertEqual(result["eligible_stop_events"],1)
        self.assertEqual(result["credited_sampled_stop_events"],1)
        stop=result["stop_responses"][0]
        self.assertLess(stop["observed_latency_sec"],.78)
        self.assertLess(stop["observed_odom_polyline_m"],.144)

    def test_full_planar_angular_and_chord_components_reject_hidden_excess(self):
        for field in("planar_speed","angular_norm","xy"):
            rows,commands=fixture()
            rows[5][field]=.31 if field=="planar_speed"else 1.3 if field=="angular_norm"else [.5,0.]
            result=robot_physics(rows,commands,1000000000,2400000000)
            self.assertFalse(result["physical_evidence_complete"])
            self.assertTrue(any(result["bound_violation_counts"].values()))

    def test_tiny_motion_is_missing_evidence_and_slow_stop_cannot_pass(self):
        rows,commands=fixture()
        for row in rows:row["planar_speed"]*=.01
        self.assertFalse(robot_physics(rows,commands,1000000000,2400000000)["physical_evidence_complete"])
        rows,commands=fixture(.1)
        result=robot_physics(rows,commands,1000000000,2400000000)
        self.assertFalse(result["physical_evidence_complete"])
        self.assertTrue(result["stop_responses"][0]["observed_nonrest_beyond_horizon"])

    def test_early_resume_and_sparse_sources_do_not_fabricate_rest(self):
        rows,commands=fixture()
        commands.append({"clock_ns":1300000000,"v":.2,"w":0.})
        result=robot_physics(rows,commands,1000000000,2400000000)
        self.assertFalse(result["physical_evidence_complete"])
        self.assertEqual(result["stop_responses"][0]["status"],"resumed_before_proven_rest")
        rows,commands=fixture()
        rows=[r for i,r in enumerate(rows)if i%8==0]
        self.assertFalse(robot_physics(rows,commands,1000000000,2400000000)["physical_evidence_complete"])

    def test_native_cancel_requires_actual_attempt_and_matching_native_completion(self):
        epoch="fixture"
        adapter=[
            {"kind":"native_send","epoch":epoch,"stamp":1.,"payload":{"robot":"tb1","goal_id":"g1"}},
            {"kind":"native_cancel","epoch":epoch,"stamp":1.2,"payload":{"robot":"tb1","goal_id":"g1","stamp":1.2,"scope":"native_cancel_call_attempt"}},
            {"kind":"delivery","epoch":epoch,"stamp":1.21,"payload":{"epoch":epoch,"source":"tb1","source_stamp":1.21,"sequence":1,"stream":"receipt","payload":{"robot":"tb1","goal_id":"g1","type":"cancel","value":True}}}]
        events=native_cancel_events(adapter,epoch)
        self.assertEqual(len(events["tb1"][0]["completion_evidence"]),1)
        changed=copy.deepcopy(adapter);changed[2]["payload"]["payload"]["value"]=False
        self.assertEqual(native_cancel_events(changed,epoch)["tb1"][0]["completion_evidence"],[])
        changed=copy.deepcopy(adapter);changed[1]["kind"]="protocol"
        self.assertEqual(native_cancel_events(changed,epoch)["tb1"],[])
        changed=copy.deepcopy(adapter);changed[2]["payload"]["payload"].update(type="result",value=5)
        self.assertEqual(len(native_cancel_events(changed,epoch)["tb1"][0]["completion_evidence"]),1)

    def test_cancel_family_can_credit_smooth_stop_without_claiming_final_zero(self):
        rows,_=fixture()
        commands=[{"clock_ns":1000000000,"v":.2,"w":0.},
                  {"clock_ns":1100000000,"v":.2,"w":0.},
                  {"clock_ns":1400000000,"v":.1,"w":0.},
                  {"clock_ns":1800000000,"v":0.,"w":0.}]
        cancel={"clock_ns":1200000000,"goal_id":"g1","new_goal_clock_ns":10**30,
                "completion_evidence":[{"kind":"cancel","value":True}]}
        result=robot_physics(rows,commands,1000000000,2400000000,[cancel])
        self.assertTrue(result["physical_evidence_complete"])
        self.assertFalse(result["hard_zero_evidence_complete"])
        self.assertTrue(result["cancel_end_to_end_evidence_complete"])
        self.assertEqual(result["credited_cancel_stop_events"],1)
        for mutation in("unacknowledged","new_goal","linear_resume"):
            change=copy.deepcopy(cancel);output=copy.deepcopy(commands)
            if mutation=="unacknowledged":change["completion_evidence"]=[]
            elif mutation=="new_goal":change["new_goal_clock_ns"]=1400000000
            else:
                output.insert(2,{"clock_ns":1300000000,"v":0.,"w":0.})
                output.insert(3,{"clock_ns":1350000000,"v":.1,"w":0.})
            observed=robot_physics(rows,output,1000000000,2400000000,[change])
            self.assertFalse(observed["cancel_end_to_end_evidence_complete"])

    def test_source_rewind_or_conflicting_duplicate_is_rejected(self):
        rows,commands=fixture()
        changed=copy.deepcopy(rows[7]);changed["planar_speed"]+=.01;rows.insert(8,changed)
        self.assertFalse(robot_physics(rows,commands,1000000000,2400000000)["physical_evidence_complete"])


if __name__=="__main__":unittest.main(verbosity=2)
