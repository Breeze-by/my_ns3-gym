"""Artificial motor traces only. No Gazebo, ROS, learner, or saved native input."""
import copy
from fractions import Fraction as Q
import math
import unittest
from mr3_learning import initial_encoder_replay as m
from mr3_learning import audit_reach_runtime as runtime

EPOCH, ROBOT, SHA = "artificial-encoder-epoch", "tb1", "1"*64

class Fixture:
    def __init__(self):
        self.rows=[]; self.messages=[]; self.seq=0; self.cmd=0; self.act_seq=0
        self.armed=True;self.valid=False;self.count=0;self.rest=0;self.ref=[0.,0.]
        self.genuine=None;self.latest=None;self.first=(0,0,None)
        self.add("configuration",0,actuation_algorithm=m.ALGORITHM,command_mode="tagged",num_wheel_pairs=1,
                 update_rate_hz=30.,max_acceleration_mps2=1.,max_torque_nm=20.,wheel_diameter_m=[.066],wheel_separation_m=[.287])
        self.add("initial_encoder_configuration",0,compiled_encoder_servo_sha256=SHA,**copy.deepcopy(m.CONFIG_VALUES))
    def add(self,kind,clock,**data):
        self.seq+=1;row=dict(schema="mr3-drive-actuation-v2",epoch=EPOCH,robot=ROBOT,record_sequence=self.seq,sim_time_ns=clock,kind=kind,**data)
        self.rows.append(row);return row
    def state(self,suffix=""):
        return {"armed"+suffix:self.armed,"reference_valid"+suffix:self.valid,"reference"+suffix+"_rad":self.ref[:],
                "capture_count"+suffix:self.count,"rest_samples"+suffix:self.rest}
    def first_fields(self):
        return dict(first_nonzero_received_cmd_seq=self.first[0],first_nonzero_received_clock_ns=self.first[1],
                    first_nonzero_received_target=copy.deepcopy(self.first[2]))
    def receive(self,clock,v=0.,w=0.):
        self.cmd+=1;t=dict(schema="mr3-drive-target-v1",epoch=EPOCH,robot=ROBOT,clock_ns=clock,
                          decision_sequence=self.cmd,linear_x=v,angular_z=w)
        if v!=0 or w!=0:
            self.armed=False;self.rest=0
            if not self.first[0]:self.first=(self.cmd,clock,t)
        self.add("initial_encoder_receive",clock,actuation_profile=m.PROFILE,cmd_seq=self.cmd,stored_target=t,
                 **self.state(),**self.first_fields(),scope="validated_target_storage_and_receive_latch; no consumption_or_wheel_write_claim")
        self.add("command_received",clock,cmd_seq=self.cmd,desired_v=v,desired_w=w,target_decision_sequence=self.cmd,target_clock_ns=clock)
        self.genuine=self.latest=t;return t
    def reset(self,clock):
        self.add("reset",clock,cmd_seq=self.cmd,target_reset=True);self.genuine=None
    def act(self,clock,q=None,qd=None):
        q=[0.,0.]if q is None else q;qd=[0.,0.]if qd is None else qd
        self.act_seq+=1;before=self.state("_before");available=self.genuine is not None
        v=self.genuine["linear_x"]if available else 0.;w=self.genuine["angular_z"]if available else 0.
        current=[x*.033 for x in qd];body=[v+w*.287/2,v-w*.287/2];captured=False
        update=self.armed and available
        if update and not self.valid:
            self.rest=self.rest+1 if max(map(abs,current))<=.01 else 0
            if self.rest==3:self.ref=q[:];self.valid=True;self.count=1;captured=True
        effective=[max(-.005,min(.005,.033*(r-a)))for r,a in zip(self.ref,q)]if update and self.valid else body[:]
        budget=Q.from_float(.034);largest=max(abs(Q.from_float(d)-Q.from_float(c))for c,d in zip(current,effective))
        nominal=Q(1)if largest<=budget else budget/largest
        alpha=1. if nominal==1 else math.nextafter(float(nominal),0.)
        while True:
            applied=[float(Q.from_float(c)+Q.from_float(alpha)*(Q.from_float(d)-Q.from_float(c)))for c,d in zip(current,effective)]
            if all(abs(Q.from_float(a)-Q.from_float(c))<=budget for a,c in zip(applied,current)):break
            alpha=math.nextafter(alpha,0.)
        written=[x/.033 for x in applied]
        nested=dict(actuation_profile=m.PROFILE,q_rad=q[:],qd_radps=qd[:],body_desired_rim_mps=body[:],servo_desired_rim_mps=effective[:],
                    current_rim_mps=current[:],update_performed=update,feedback_active=update and self.valid,
                    captured_this_update=captured,**before,**self.state(),**self.first_fields(),
                    genuine_target_available=available,waiting_for_genuine_target=self.armed and not available,
                    genuine_target_cmd_seq=self.cmd if available else 0,genuine_consumed_target=copy.deepcopy(self.genuine),
                    written_motor_target_radps=written[:],readback_motor_target_radps=written[:],
                    left_SetParam_returned=True,right_SetParam_returned=True)
        row=self.add("actuation",clock,actuation_seq=self.act_seq,pair_index=0,cmd_seq=self.cmd,
                     target_decision_sequence=self.latest["decision_sequence"]if self.latest else 0,
                     target_clock_ns=self.latest["clock_ns"]if self.latest else 0,desired_v=v,desired_w=w,
                     dt_ns=m.PERIOD_NS,dt_sec=.034,current_rim_mps=current,desired_rim_mps=body,
                     applied_rim_mps=applied,alpha=alpha,max_acceleration_mps2=1.,initial_encoder_hold=nested)
        if available:
            self.messages.append(dict(schema="mr3-drive-applied-v1",epoch=EPOCH,robot=ROBOT,source_clock_ns=clock,
                actuation_sequence=self.act_seq,cmd_seq=self.cmd,dt_ns=m.PERIOD_NS,target=copy.deepcopy(self.genuine),
                pairs=[{k:copy.deepcopy(row[k])for k in m.PAIR_FIELDS}]))
        return row


def base():
    f=Fixture();f.receive(0);f.act(34_000_000,[1.,-1.]);f.act(68_000_000,[1.01,-1.01]);
    f.act(102_000_000,[1.02,-1.02]);f.act(136_000_000,[1.03,-1.03]);return f


def replay(f,**changes):
    args=dict(profile=m.PROFILE,epoch=EPOCH,robot=ROBOT,helper_sha256=SHA);args.update(changes)
    return m.replay_native_drive(f.rows,**args)


def acts(f):return [r for r in f.rows if r["kind"]=="actuation"]

class ReplayTests(unittest.TestCase):
    def test_selected_profile_requires_explicit_current_reach_metadata(self):
        self.assertIsNone(runtime.selected_actuation_profile({}))
        with self.assertRaises(ValueError):
            runtime.selected_actuation_profile({"safety_contract": "mr3-reach-v1"}, required=True)
        self.assertEqual(runtime.selected_actuation_profile({"safety_contract": "mr3-reach-v1", "actuation_profile": m.PROFILE}, required=True), m.PROFILE)

    def test_native_index_really_requires_new_motor_replay_for_all_three(self):
        from mr3_learning.tests.test_audit_reach_runtime import fixture, EPOCH as runtime_epoch
        case = fixture()
        drivers = {}
        for robot in runtime.ROBOTS:
            f = base()
            text = m.canonical(f.rows).replace(EPOCH, runtime_epoch).replace('"tb1"', '"'+robot+'"')
            drivers[robot] = m.json.loads(text)
        indexed = runtime.native_index(drivers, case["odometry_rows"], runtime_epoch,
            actuation_profile=m.PROFILE, encoder_helper_sha256=SHA)
        self.assertTrue(all(indexed[n]["initial_encoder_motor_replay"]["passed"] for n in runtime.ROBOTS))
        bad = copy.deepcopy(drivers)
        row = next(r for r in reversed(bad["tb2"]) if r["kind"] == "actuation")
        row["initial_encoder_hold"]["reference_rad"][0] += .001
        with self.assertRaises(ValueError):
            runtime.native_index(bad, case["odometry_rows"], runtime_epoch,
                actuation_profile=m.PROFILE, encoder_helper_sha256=SHA)

    def test_positive_nonzero_motor_under_original_zero_body(self):
        f=base();before=m.canonical(f.rows);r=replay(f)
        self.assertEqual(r["reference_capture_count"],1)
        self.assertEqual(acts(f)[-1]["desired_rim_mps"],[0.,0.])
        self.assertNotEqual(acts(f)[-1]["applied_rim_mps"],[0.,0.])
        for msg in f.messages:self.assertTrue(m.check_applied_receipt(msg,r))
        self.assertEqual(m.canonical(f.rows),before)
    def test_receive_nonzero_overwritten_before_any_update_still_disarms(self):
        f=base();
        f.act(170_000_000,[1.04,-1.04]);f.receive(180_000_000,.1,0.);f.receive(190_000_000)
        f.act(204_000_000,[1.05,-1.05]);r=replay(f)
        self.assertEqual(r["first_nonzero_received_cmd_seq"],2)
        self.assertFalse(acts(f)[-1]["initial_encoder_hold"]["armed"])
        self.assertEqual(acts(f)[-1]["applied_rim_mps"],[0.,0.])
        bad=copy.deepcopy(f);last=acts(bad)[-1]["initial_encoder_hold"];last.update(armed_before=True,armed=True,update_performed=True,feedback_active=True)
        with self.assertRaises(ValueError):replay(bad)
    def test_pure_turn_receive_is_permanent(self):
        f=base();f.act(170_000_000);f.receive(180_000_000,0.,.2);f.receive(190_000_000);f.act(204_000_000)
        self.assertEqual(replay(f)["first_nonzero_received_cmd_seq"],2)
    def test_consumed_nonzero_uses_original_law_and_exact_budget(self):
        f=base();f.act(170_000_000);f.receive(200_000_000,.2,0.);f.act(204_000_000)
        r=replay(f);m.check_applied_receipt(f.messages[-1],r)
        self.assertEqual(acts(f)[-1]["initial_encoder_hold"]["servo_desired_rim_mps"],[.2,.2])
    def test_implicit_zero_updates_do_not_capture(self):
        f=Fixture()
        for i in range(1,5):f.act(i*m.PERIOD_NS)
        f.receive(140_000_000)
        for i in range(5,8):f.act(i*m.PERIOD_NS,[float(i),float(i)])
        r=replay(f);self.assertEqual(r["reference_capture_count"],1)
        self.assertTrue(acts(f)[-1]["initial_encoder_hold"]["captured_this_update"])
        bad=copy.deepcopy(f);acts(bad)[2]["initial_encoder_hold"].update(reference_valid=True,capture_count=1)
        with self.assertRaises(ValueError):replay(bad)
    def test_reset_does_not_rearm_or_recapture_reference(self):
        f=base();f.reset(140_000_000);f.act(170_000_000);f.receive(180_000_000);f.act(204_000_000,[1.04,-1.04]);r=replay(f)
        self.assertEqual(r["reference_capture_count"],1)
        self.assertEqual(acts(f)[-1]["initial_encoder_hold"]["reference_rad"],[1.02,-1.02])
        bad=copy.deepcopy(f);acts(bad)[-1]["initial_encoder_hold"]["capture_count"]=2
        with self.assertRaises(ValueError):replay(bad)
    def test_profile_and_helper_identity_are_required(self):
        for profile in (None,"legacy","unknown"):
            with self.assertRaises(ValueError):replay(base(),profile=profile)
        with self.assertRaises(ValueError):replay(base(),helper_sha256="2"*64)
    def test_wrong_gain_or_boolean_acceleration_rejected(self):
        f=base();f.rows[1]["position_gain_per_second"]=2.
        with self.assertRaises(ValueError):replay(f)
        f=base();f.rows[0]["max_acceleration_mps2"]=True
        with self.assertRaises(ValueError):replay(f)
    def test_missing_configuration_receive_or_motor_event_rejected(self):
        for kind in ("initial_encoder_configuration","initial_encoder_receive","actuation"):
            f=base();index=next(i for i,r in enumerate(f.rows)if r["kind"]==kind);f.rows.pop(index)
            for i,r in enumerate(f.rows,1):r["record_sequence"]=i
            with self.assertRaises(ValueError):replay(f)
    def test_reference_refresh_and_wrong_third_capture_rejected(self):
        for key,value in (("reference_rad",[1.03,-1.03]),("captured_this_update",True),("capture_count",2)):
            f=base();acts(f)[-1]["initial_encoder_hold"][key]=value
            with self.assertRaises(ValueError):replay(f)
        f=base();acts(f)[1]["initial_encoder_hold"]["reference_valid"]=True
        with self.assertRaises(ValueError):replay(f)
    def test_servo_target_and_measured_feedback_forgery_rejected(self):
        f=base();acts(f)[-1]["initial_encoder_hold"]["servo_desired_rim_mps"][0]+=1e-7
        with self.assertRaises(ValueError):replay(f)
        f=base();acts(f)[-1]["initial_encoder_hold"]["qd_radps"][0]=.01
        with self.assertRaises(ValueError):replay(f)
    def test_nonfinite_encoder_rejected(self):
        f=base();acts(f)[-1]["initial_encoder_hold"]["q_rad"][0]=math.inf
        with self.assertRaises(ValueError):replay(f)
    def test_saturation_is_independently_checked(self):
        f=base();f.act(170_000_000,[100.,-100.]);r=replay(f)
        self.assertEqual(acts(f)[-1]["initial_encoder_hold"]["servo_desired_rim_mps"],[-.005,.005]);self.assertTrue(r["passed"])
    def test_original_body_desired_must_not_be_replaced_with_servo(self):
        f=base();a=acts(f)[-1];a["desired_rim_mps"]=a["initial_encoder_hold"]["servo_desired_rim_mps"][:]
        with self.assertRaises(ValueError):replay(f)
    def test_actual_write_and_readback_and_failure_flags_rejected(self):
        for key,value in (("written_motor_target_radps",[0.,0.]),("readback_motor_target_radps",[0.,0.]),("left_SetParam_returned",False)):
            f=base();acts(f)[-1]["initial_encoder_hold"][key]=value
            with self.assertRaises(ValueError):replay(f)
    def test_common_fraction_forgery_and_one_ulp_budget_excess_rejected(self):
        f=base();acts(f)[-1]["alpha"]=.5
        with self.assertRaises(ValueError):replay(f)
        f=base();f.act(170_000_000);f.receive(200_000_000,.2,0.);a=f.act(204_000_000)
        excess=math.nextafter(.034,math.inf);a["applied_rim_mps"]=[excess,excess]
        n=a["initial_encoder_hold"];n["written_motor_target_radps"]=n["readback_motor_target_radps"]=[excess/.033]*2
        with self.assertRaisesRegex(ValueError,"exact wheel acceleration budget"):replay(f)
    def test_native_sequence_cadence_and_latest_target_rejected(self):
        for mutate in (lambda f:acts(f)[-1].update(actuation_seq=8),lambda f:acts(f)[-1].update(dt_ns=35_000_000),lambda f:acts(f)[-1].update(cmd_seq=0)):
            f=base();mutate(f)
            with self.assertRaises(ValueError):replay(f)
    def test_applied_join_rejects_motor_target_profile_clock_and_extra_fields(self):
        f=base();r=replay(f)
        changes=[lambda x:x["pairs"][0]["applied_rim_mps"].__setitem__(0,0.),lambda x:x["target"].update(linear_x=.1),
                 lambda x:x.update(source_clock_ns=x["source_clock_ns"]+1),lambda x:x.update(cmd_seq=True),lambda x:x.update(extra=True)]
        for mutate in changes:
            value=copy.deepcopy(f.messages[-1]);mutate(value)
            with self.assertRaises(ValueError):m.check_applied_receipt(value,r)
    def test_missing_genuine_source_and_receive_latch_forgery_rejected(self):
        f=base();a=acts(f)[-1];a["initial_encoder_hold"]["genuine_consumed_target"]=None
        with self.assertRaises(ValueError):replay(f)
        f=base();f.act(170_000_000);f.receive(180_000_000,.1);f.receive(190_000_000);f.act(204_000_000)
        for r in f.rows:
            if r["kind"]=="initial_encoder_receive" and r["cmd_seq"]==2:r["armed"]=True
        with self.assertRaises(ValueError):replay(f)

if __name__=="__main__":unittest.main(verbosity=2)
