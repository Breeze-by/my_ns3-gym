"""Artificial wire-shaped records only; never the original motion file or consumer main."""
import copy,hashlib,importlib.util,io,json,time,unittest
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
s=importlib.util.spec_from_file_location("motion_chain",HERE/"describe_motion_chain_v1.py")
m=importlib.util.module_from_spec(s);s.loader.exec_module(m)


def trace(raw_v=.2,effective_v=.2,output_v=.2,reason="reach_clear",*,missing_raw=False,offset_odom=False,late_callback=False):
    rows=[]
    def add(kind,payload,t):
        rows.append(dict(schema="mr3-motion-safety-v1",epoch=m.EPOCH,record_sequence=len(rows)+1,
            sim_time_sec=t,wall_monotonic_ns=len(rows)+1,kind=kind,payload=payload))
    for name in m.ROBOTS:
        q=dict(v=raw_v,w=.3,received_stamp=39.73,sequence=1,publisher_identity={"valid":True},supported=True)
        if not missing_raw:add("raw_request",dict(robot=name,request=q),39.73)
        clock=39740000000
        add("reach_decision",dict(robot=name,clock_ns=clock,decision_sequence=10,request=q,
            effective_request=[effective_v,.3],motion_authority={"permission":"normal_reach" if effective_v else "zero_only","state":"ACTIVE","authority_sequence":1,"owner":{"goal_id":m.EPOCH+":"+name+":1"}},
            decision={"output":[output_v,.3],"reason":reason},intent={"role":"N"},tracker={"role":"N"},started=True,ready=True),39.74)
        target=dict(schema="mr3-drive-target-v1",epoch=m.EPOCH,robot=name,clock_ns=clock,decision_sequence=10,linear_x=output_v,angular_z=.3)
        storage=dict(schema="mr3-drive-target-consumed-v1",epoch=m.EPOCH,robot=name,clock_ns=clock,source_clock_ns=clock,decision_sequence=10,cmd_seq=20,linear_x=output_v,angular_z=.3)
        add("reach_driver_ingress",dict(robot=name,kind="storage",message=storage,raw_json=json.dumps(storage),publisher_identity={"valid":True}),39.74)
        source=39774000000
        pair=dict(pair_index=0,current_rim_mps=[output_v+.04305,output_v-.04305],desired_rim_mps=[output_v+.04305,output_v-.04305],applied_rim_mps=[output_v+.04305,output_v-.04305],alpha=1.,max_acceleration_mps2=1.)
        app=dict(schema="mr3-drive-applied-v1",epoch=m.EPOCH,robot=name,source_clock_ns=source,actuation_sequence=30,cmd_seq=20,dt_ns=34000000,target=target,pairs=[pair])
        add("reach_driver_ingress",dict(robot=name,kind="applied",message=app,raw_json=json.dumps(app),publisher_identity={"valid":True}),53. if late_callback else 39.78)
        odom_source=source+17000000 if offset_odom else source
        msg={"header":{"stamp":{"sec":odom_source//10**9,"nanosec":odom_source%10**9},"frame_id":name+"/odom"},"child_frame_id":name+"/base_footprint","twist":{"twist":{"linear":{"x":.0001,"y":0.,"z":0.},"angular":{"x":0.,"y":0.,"z":.3}}}}
        add("own_odom",dict(robot=name,input_sequence=3,message=msg),39.8)
    return rows


def run(rows):
    raw=b"".join(m.canonical(x)+b"\n" for x in rows)
    return m.analyze_stream(io.BytesIO(raw),expected_bytes=len(raw),expected_sha256=m.sha(raw),deadline_ns=time.monotonic_ns()+10**9)


class MotionDescriptionTests(unittest.TestCase):
    def test_positive_exact_chain_joins_each_robot_without_wheel_or_physical_claim(self):
        v=run(trace());self.assertTrue(v["passed"]);self.assertEqual(v["parse_errors"],0)
        self.assertEqual(len(v["control_tick_rows"]),3)
        for n in m.ROBOTS:
            self.assertEqual(v["exact_raw_join_counts"][n],{"EXACT_RAW_REQUEST":1})
            self.assertEqual(v["native_received_APPLIED"][n]["target_join_counts"],{"EXACT_REACH_TARGET_FIELDS":1})
            self.assertEqual(v["native_received_APPLIED"][n]["storage_join_counts"],{"EXACT_STORAGE_TARGET_FIELDS":1})
            self.assertEqual(v["robot_stream_counts"][n]["EXACT_JOINED_APPLIED_body_target_v"]["positive"],1)
            self.assertEqual(v["raw_own_odom"][n]["maximum_planar_speed_mps"],.0001)
        self.assertFalse(v["actual_wheel_SetParam_or_readback_checked"])
        self.assertEqual(v["raw_goal_generation"],"UNKNOWN_UNSTAMPED_TWIST")

    def test_raw_zero_rotation_effective_zero_and_output_zero_stay_distinct_from_plant_failure(self):
        v=run(trace(0.,0.,0.));self.assertTrue(v["passed"])
        for n in m.ROBOTS:
            self.assertEqual(v["robot_stream_counts"][n]["raw_received_v"]["zero"],1)
            self.assertEqual(v["robot_stream_counts"][n]["Reach_output_v"]["positive"],0)
            self.assertEqual(v["raw_own_odom"][n]["maximum_abs_wz_radps"],.3)
        self.assertFalse(v["physical_stop_or_continuous_bounds_replayed"])

    def test_positive_raw_effective_authority_zero_is_visible(self):
        v=run(trace(.2,0.,0.,"request_unavailable_zero"));self.assertTrue(v["passed"])
        self.assertTrue(all(row["raw_vector"][0]==.2 and row["effective_request"][0]==0. and row["receiving_permission"]=="zero_only" for row in v["control_tick_rows"]))

    def test_positive_effective_linear_brake_is_not_silently_reclassified_as_raw_zero(self):
        v=run(trace(.2,.2,0.,"linear_brake_preserve_requested_turn"));self.assertTrue(v["passed"])
        self.assertTrue(all(row["raw_vector"][0]==row["effective_request"][0]==.2 and row["output"]==[0.,.3] for row in v["control_tick_rows"]))
        self.assertEqual(v["Reach_reason_counts"]["tb1"],{"linear_brake_preserve_requested_turn":1})

    def test_missing_raw_reference_is_UNKNOWN_even_if_close_other_sequence_exists(self):
        rows=trace(missing_raw=True)
        q=dict(v=.2,w=.3,received_stamp=39.73,sequence=2,publisher_identity={"valid":True},supported=True)
        rows.insert(0,dict(schema="mr3-motion-safety-v1",epoch=m.EPOCH,record_sequence=0,sim_time_sec=39.73,kind="raw_request",payload={"robot":"tb1","request":q}))
        for i,row in enumerate(rows,1):row["record_sequence"]=i
        v=run(rows);self.assertTrue(v["passed"])
        self.assertEqual(v["exact_raw_join_counts"]["tb1"],{"UNKNOWN_MISSING_EXACT_RAW_REFERENCE":1})

    def test_nonmatching_native_target_fields_are_CONFLICT_not_nearest_decision(self):
        rows=trace()
        for row in rows:
            if row["kind"]=="reach_driver_ingress" and row["payload"]["kind"]=="applied":
                row["payload"]["message"]["target"]["linear_x"]=.1;row["payload"]["raw_json"]=json.dumps(row["payload"]["message"])
        v=run(rows);self.assertTrue(v["passed"])
        self.assertEqual(v["native_received_APPLIED"]["tb1"]["target_join_counts"],{"CONFLICT_REACH_TARGET_FIELDS":1})
        self.assertEqual(v["robot_stream_counts"]["tb1"]["EXACT_JOINED_APPLIED_body_target_v"]["availability"],"UNKNOWN_ABSENT_OR_NO_EXACT_JOIN")

    def test_callback_time_is_not_native_source_time_and_odom_is_never_nearest_matched(self):
        v=run(trace(offset_odom=True,late_callback=True));self.assertTrue(v["passed"])
        for n in m.ROBOTS:
            self.assertEqual(v["native_received_APPLIED"][n]["unique_APPLIED"],1)
            self.assertEqual(v["native_received_APPLIED"][n]["same_source_odom_count"],0)
            self.assertEqual(v["raw_own_odom"][n]["APPLIED_to_odom_causal_effect_join"],"UNKNOWN_NO_EXACT_EFFECT_REFERENCE")

    def test_unknown_effective_is_not_filled_from_raw_or_zero(self):
        rows=trace()
        for row in rows:
            if row["kind"]=="reach_decision":row["payload"].pop("effective_request")
        v=run(rows);self.assertTrue(v["passed"])
        self.assertTrue(all(row["effective_request"] is None for row in v["control_tick_rows"]))
        self.assertEqual(v["robot_stream_counts"]["tb1"]["effective_v"]["UNKNOWN"],1)

    def test_strict_JSON_and_typed_bool_do_not_become_measurements(self):
        for raw in (b"{\"x\":1,\"x\":2}",b"{\"x\":NaN}",b"{\"x\":1e999}"):
            with self.assertRaises(ValueError):m.decode(raw)
        rows=trace();rows[0]["payload"]["request"]["sequence"]=True
        v=run(rows);self.assertFalse(v["passed"]);self.assertGreater(v["semantic_error_count"],0)

    def test_bounded_selection_overflow_is_INCOMPLETE_with_real_returned_byte_count(self):
        with patch.dict(m.LIMITS,{"max_selected_records":1}):v=run(trace())
        self.assertFalse(v["passed"]);self.assertIn("bound",v["resource_or_finish_failure"])
        self.assertFalse(v["complete_input_read"]);self.assertGreater(v["raw_input_bytes_read"],0)
        self.assertEqual(v["input_hash_domain"],"returned_prefix_only")

    def test_foreign_native_epoch_recorded_then_ignored_is_not_credited_or_rejected_as_current(self):
        rows=trace();wire={"epoch":"foreign","robot":"tb1"}
        rows.insert(0,dict(schema="mr3-motion-safety-v1",epoch=m.EPOCH,record_sequence=0,sim_time_sec=39.72,kind="reach_driver_ingress",payload={"robot":"tb1","kind":"applied","message":wire,"raw_json":json.dumps(wire)}))
        for i,row in enumerate(rows,1):row["record_sequence"]=i
        v=run(rows);self.assertTrue(v["passed"]);self.assertEqual(v["ignored_native_foreign_or_missing_epoch"],1)
        self.assertEqual(v["native_received_APPLIED"]["tb1"]["unique_APPLIED"],1)

    def test_identical_odom_payload_duplicate_with_new_callback_sequence_deduplicates(self):
        rows=trace();copyrow=copy.deepcopy(next(row for row in rows if row["kind"]=="own_odom" and row["payload"]["robot"]=="tb1"))
        copyrow["payload"]["input_sequence"]+=1;rows.append(copyrow)
        for i,row in enumerate(rows,1):row["record_sequence"]=i
        v=run(rows);self.assertTrue(v["passed"])
        self.assertEqual(v["raw_own_odom"]["tb1"]["unique_source_samples"],1)
        self.assertEqual(v["raw_own_odom"]["tb1"]["callback_records"],2)
        self.assertEqual(v["raw_own_odom"]["tb1"]["exact_duplicate_messages"],1)
        rows[-1]["payload"]["message"]["twist"]["twist"]["linear"]["x"]=.2
        bad=run(rows);self.assertFalse(bad["passed"]);self.assertGreater(bad["semantic_error_count"],0)

    def test_unadmitted_spec_refuses_without_real_scope_or_input_access(self):
        with self.assertRaisesRegex(ValueError,"unadmitted"):
            m.validate_admission({"schema":m.SPEC_SCHEMA,"admitted":False},"0"*40)


if __name__=="__main__":unittest.main()
