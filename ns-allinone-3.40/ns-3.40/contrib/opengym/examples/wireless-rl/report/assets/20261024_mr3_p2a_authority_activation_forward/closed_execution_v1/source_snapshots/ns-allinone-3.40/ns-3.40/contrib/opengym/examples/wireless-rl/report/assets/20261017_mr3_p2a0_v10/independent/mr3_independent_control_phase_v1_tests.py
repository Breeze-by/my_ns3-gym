#!/usr/bin/env python3
"""Synthetic causal/mutation checks; no native or physical validation credit."""
import copy
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).with_name("mr3_independent_control_phase_v1.py")
SPEC = importlib.util.spec_from_file_location("independent_control", PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)
R = M.ROBOTS


class Fixture:
    def __init__(self):
        self.epoch = "fixture-epoch"
        self.wall = 100
        (self.info, self.peer, self.motion, self.worker, self.drive, self.physics
         ) = [], [], [], [], [], []
        self.native = {r: [] for r in R}
        self.counts = {r: 0 for r in R}
        self.inputcounts = {(k, r): 0 for k in ("odom", "tf") for r in R}
        self.config_peer()
        self.generate()

    def tick(self):
        self.wall += 10
        return self.wall

    def prow(self, kind, payload, target):
        self.peer.append(
            {"schema": "mr3-peer-phase-audit-v1", "epoch": self.epoch,
             "record_sequence": len(self.peer) + 1, "kind": kind, "clock_ns": target,
             "wall_monotonic_ns": self.tick(),
             "payload": payload})

    def mrow(self, kind, payload):
        self.motion.append(
            {"schema": "mr3-motion-safety-v1", "epoch": self.epoch,
             "record_sequence": len(self.motion) + 1, "kind": kind, "sim_time_sec": 1.,
             "wall_monotonic_ns": self.tick(),
             "payload": payload})

    def wrow(self, kind, target, **payload):
        self.worker.append({"schema": "mr3-controlled-execution-phase-v1", "epoch": self.epoch,
                            "kind": kind, "wall_monotonic_ns": self.tick(),
                            "worker_clock_ns": target, "worker_physical_ns": target, **payload})

    def drow(self, kind, target, **payload):
        self.drive.append({"epoch": self.epoch, "kind": kind, "wall_monotonic_ns": self.tick(),
                           "worker_clock_ns": target, "worker_physical_ns": target, **payload})

    def config_peer(self):
        topics = {k+":"+r: "/mr3/received/"+r+"/"+k
                  for k in ("odom", "tf") for r in R}
        self.prow("configuration", {"stepped_mode": True, "tf_source_lead_sec": .2,
                                    "input_topics": topics}, 1_000_000_000)

    def request(self, component, operation, target, identity, **refs):
        schema = ("mr3-motion-control-request-v1" if component == "motion"
                  else "mr3-"+component+"-phase-request-v1")
        request = {"schema": schema, "epoch": self.epoch, "operation": operation,
                   "request_id": identity, "target_time_ns": target, **refs}
        self.wrow("request", target, component=component, request=request)
        if component == "state":
            self.info.append({"kind": "state_phase_request", "epoch": self.epoch,
                              "clock_ns": target, "wall_monotonic_ns": self.tick(),
                              "payload": {"request": request, "duplicate": False}})
        return request

    def consume(self, component, ack):
        target = ack["target_time_ns"]
        self.wrow("ack_received", target, component=component, ack=ack)
        self.wrow("ack_consumed", target, component=component, ack=ack)

    def iack(self, ack):
        start, end = self.tick(), self.tick()
        self.info.append({"kind": "state_phase_ack",
                          "epoch": self.epoch,
                          "clock_ns": ack["clock_ns"],
                          "wall_monotonic_ns": self.tick(),
                          "payload": {"ack": ack,
                                      "publish_started_wall_monotonic_ns": start,
                                      "publish_completed_wall_monotonic_ns": end}})

    def pack(self, ack):
        start, end = self.tick(), self.tick()
        self.prow("ack_published", {"ack": ack, "publish_started_wall_monotonic_ns": start,
                                    "publish_completed_wall_monotonic_ns": end}, ack["clock_ns"])

    def ack(self, component, operation, target, identity, **extra):
        schema = ("mr3-motion-control-ack-v1" if component == "motion"
                  else "mr3-"+component+"-phase-ack-v1")
        return {"schema": schema, "epoch": self.epoch, "operation": operation, "ok": True,
                "request_id": identity, "target_time_ns": target, "clock_ns": target, **extra}

    def raw(self, kind, robot, target):
        stamp = target if kind == "odom" else target + 200_000_000
        header = {"frame_id": "odom" if kind == "odom" else "map",
                  "stamp": {"sec": stamp//1_000_000_000, "nanosec": stamp % 1_000_000_000}}
        point = {"x": float(R.index(robot)*2), "y": 0., "z": 0.}
        q = {"x": 0., "y": 0., "z": 0., "w": 1.}
        if kind == "tf":
            return {"header": header, "child_frame_id": "odom",
                    "transform": {"translation": {"x": 0., "y": 0., "z": 0.}, "rotation": q}}
        return {
            "header": header,
            "child_frame_id": "base_footprint",
            "pose": {
                "pose": {
                    "position": point,
                    "orientation": q},
                "covariance": [0.]*36},
            "twist": {
                "twist": {
                    "linear": {
                        "x": 0.,
                        "y": 0.,
                        "z": 0.},
                    "angular": {
                        "x": 0.,
                        "y": 0.,
                        "z": 0.}},
                "covariance": [0.]*36}}

    def state_commit(self, target, identity):
        request = self.request("state", "commit", target, identity)
        side_start = self.tick()
        selected = {(k, r): {"raw": self.raw(k, r, target)} for k in ("odom", "tf") for r in R}
        robots = [{"name": r, "epoch": self.epoch, "valid": True, "sequence": 1, "version": 1,
                   "source_stamp": target/1e9, "odom_source_stamp": target/1e9,
                   "tf_source_stamp": target/1e9} for r in R]
        bundle = {"epoch": self.epoch, "sequence": 1, "robots": robots}
        start, end = self.tick(), self.tick()
        self.info.append({"kind": "state_publish",
                          "epoch": self.epoch,
                          "clock_ns": target,
                          "wall_monotonic_ns": self.tick(),
                          "payload": {"message": bundle,
                                      "message_sha256": M.digest(bundle),
                                      "publish_started_wall_monotonic_ns": start,
                                      "publish_completed_wall_monotonic_ns": end}})
        refs = {r: {"sequence": 1, "version": 1, "source_ns": target, "source_stamp": target/1e9,
                    "odom_source_ns": target, "tf_source_ns": target,
                    **{k+"_sha256": M.digest(selected[k, r]["raw"]) for k in ("odom", "tf")},
                    **{k+"_topic": "/mr3/received/"+r+"/"+k for k in ("odom", "tf")}}
                for r in R}
        ack = self.ack("state", "commit", target, identity, state_sequence=1,
                       bundle_sha256=M.digest(bundle), robots=refs,
                       side_publish_started_wall_monotonic_ns=side_start,
                       bundle_publish_started_wall_monotonic_ns=start,
                       bundle_publish_completed_wall_monotonic_ns=end,
                       scope="actual_state_and_side_publish_calls_returned")
        self.iack(ack)
        self.consume("state", ack)
        return ack, bundle, selected, request

    def peer_commit(self, target, identity, state, bundle, selected):
        request = self.request("peer", "commit", target, identity, state_commit=state)
        self.prow("request_received", request, target)
        refs = {}
        for (kind, robot), value in selected.items():
            seq = self.inputcounts[kind, robot] + 1
            self.inputcounts[kind, robot] = seq
            raw = value["raw"]
            payload = {"robot": robot, "input_sequence": seq, "raw": raw,
                       "raw_sha256": M.digest(raw), "received_wall_monotonic_ns": self.tick(),
                       "topic": "/mr3/received/"+robot+"/"+kind}
            self.prow("received_"+kind, payload, target)
            refs[kind+":"+robot] = {k: payload[k] for k in (
                "input_sequence", "raw_sha256", "received_wall_monotonic_ns")}
        payload = {"message": bundle, "message_sha256": M.digest(bundle),
                   "received_wall_monotonic_ns": self.tick()}
        self.prow("received_state_bundle", payload, target)
        refs["bundle"] = {"state_sequence": 1, "message_sha256": M.digest(bundle),
                          "received_wall_monotonic_ns": payload["received_wall_monotonic_ns"]}
        self.prow("inputs_matched", {"request": request, "inputs": refs}, target)
        pubs = []
        for (robot, kind), output in M.expected_outputs(selected, target).items():
            start, end = self.tick(), self.tick()
            pubs.append(
                {"robot": robot, "kind": kind, "payload": output, "topic": "/" + robot +
                 ("/peer_obstacles" if kind == "scan" else "/peer_footprints"),
                 "message_sha256": M.digest(output),
                 "publish_started_wall_monotonic_ns": start,
                 "publish_completed_wall_monotonic_ns": end})
        self.prow("obstacles_published", {"request_id": identity, "publications": pubs}, target)
        ack = self.ack(
            "peer",
            "commit",
            target,
            identity,
            commit_sequence=1,
            state_commit=state,
            state_sequence=1,
            bundle_sha256=M.digest(bundle),
            inputs=refs,
            publications=pubs,
            obstacle_publication_sha256=M.digest(pubs),
            scope="actual_obstacle_publish_calls_returned")
        self.pack(ack)
        self.consume("peer", ack)
        return ack

    def status(self, target, ready=True, stop=False):
        outputs, sequences = {}, {}
        for robot in R:
            self.counts[robot] += 1
            seq = self.counts[robot]
            sequences[robot] = seq
            output = [0., 0.] if not ready or stop else [.13, -.4]
            outputs[robot] = {"linear_x": output[0], "angular_z": output[1]}
            self.mrow("decision", {"robot": robot, "clock_ns": target, "decision_sequence": seq,
                                   "decision": {"output": output}, "ready": ready,
                                   **({"phase_kind": "stop"} if stop else {})})
            self.mrow("actual_cmd_vel",
                      {"robot": robot,
                       "observed_decision_sequence": seq,
                       "twist": {"linear": {"x": output[0],
                                            "y": 0.,
                                            "z": 0.},
                                 "angular": {"x": 0.,
                                             "y": 0.,
                                             "z": output[1]}},
                          "publisher_identity": {"valid": True,
                                                 "scope": "graph_at_callback",
                                                 "topic": "/"+robot+"/cmd_vel",
                                                 "endpoints": [{"namespace": "/",
                                                                "node": "motion_safety"}]}})
        status = {"schema": "mr3-motion-safety-status-v1", "epoch": self.epoch, "clock_ns": target,
                  "ready": ready, "outputs": outputs, "decision_sequences": sequences,
                  "completion_scope": "publication_and_local_topic_receipt",
                  **({"phase_kind": "stop"} if stop else {})}
        start, end = self.tick(), self.tick()
        self.mrow("output_completed",
                  {"status": status,
                   "publish_started_wall_monotonic_ns": start,
                   "publish_completed_wall_monotonic_ns": end})
        return status

    def motion_ack(self, request, status):
        ack = self.ack(
            "motion",
            request["operation"],
            request["target_time_ns"],
            request["request_id"],
            status=status)
        self.mrow("control_ack", ack)
        start, end = self.tick(), self.tick()
        self.mrow("control_ack_published", {"ack": ack, "publish_started_wall_monotonic_ns": start,
                                            "publish_completed_wall_monotonic_ns": end})
        self.consume("motion", ack)
        return ack

    def stored(self, status):
        target = status["clock_ns"]
        receipts = {}
        for robot in R:
            seq = status["decision_sequences"][robot]
            output = status["outputs"][robot]
            native = {"epoch": self.epoch, "robot": robot, "kind": "command_received",
                      "cmd_seq": seq, "sim_time_ns": target, "target_clock_ns": target,
                      "target_decision_sequence": seq, "desired_v": output["linear_x"],
                      "desired_w": output["angular_z"]}
            self.native[robot].append(native)
            ack = {"schema": "mr3-drive-target-consumed-v1", "epoch": self.epoch, "robot": robot,
                   "clock_ns": target, "source_clock_ns": target, "cmd_seq": seq,
                   "decision_sequence": seq, **output}
            receipts[robot] = ack
            self.drow("ack_received", target, topic_robot=robot, ack=ack)
        self.drow("ack_consumed", target, expected_motion=status, receipts=receipts)
        return receipts

    def advance(self, status, identity, kind):
        start = status["clock_ns"]
        receipts = self.stored(status)
        q = "q"+str(len(self.physics)+1)
        self.drow(
            "advance_permitted",
            start,
            request_id=q,
            steps=20,
            start_time_ns=start,
            expected_motion=status,
            receipts=receipts,
            control_kind=kind,
            control_request_id=identity)
        receipt = {"request_id": q,
                   "epoch": self.epoch,
                   "ok": True,
                   "paused": True,
                   "start_time_ns": start,
                   "end_time_ns": start+20_000_000,
                   "start_iterations": (len(self.physics))*20,
                   "end_iterations": (len(self.physics)+1)*20}
        self.physics.append(receipt)
        self.drow("physics_completed", start, receipt=receipt)

    def generate(self):
        t0, t1, t2 = 1_000_000_000, 1_020_000_000, 1_040_000_000
        status = self.status(t0, ready=False)
        identity = "takeover"+str(t0)
        request = self.request("motion", "takeover", t0, identity)
        self.mrow("control_request", request)
        self.motion_ack(request, status)
        self.request("state", "takeover", t0, identity)
        state = self.ack("state", "takeover", t0, identity, scope="automatic_state_timer_disabled")
        self.iack(state)
        self.consume("state", state)
        request = self.request("peer", "takeover", t0, identity)
        self.prow("controlled", request, t0)
        self.prow("request_received", request, t0)
        peer = self.ack("peer", "takeover", t0, identity,
                        scope="automatic_obstacle_timer_disabled")
        self.pack(peer)
        self.consume("peer", peer)
        self.advance(status, identity, "bootstrap_zero")
        identity = "boundary"+str(t1)
        state, bundle, selected, _ = self.state_commit(t1, identity)
        peer = self.peer_commit(t1, identity, state, bundle, selected)
        request = self.request(
            "motion",
            "commit",
            t1,
            identity,
            state_commit=state,
            peer_commit=peer)
        self.mrow("received_states", bundle)
        self.mrow("control_dependency", {"component": "state", "value": state})
        self.mrow("control_dependency", {"component": "peer", "value": peer})
        self.mrow("control_request", request)
        status = self.status(t1)
        self.mrow("control_commit", {"request": request})
        self.motion_ack(request, status)
        self.mrow("release", {"stamp": t1/1e9})
        self.advance(status, identity, "normal")
        request = self.request("motion", "stop", t2, "stop"+str(t2), reason="cleanup")
        self.mrow("control_request", request)
        self.mrow("stop_request", {"stamp": t2/1e9})
        status = self.status(t2, ready=False, stop=True)
        self.motion_ack(request, status)
        self.wrow("stop_observed", t2, status=status, origin="control_ack", duplicate=False)
        self.advance(status, request["request_id"], "stop")

    def replay(self):
        state = M.information_acks(self.info, self.epoch)
        peer = M.PeerReplay(self.epoch, state)
        for row in self.peer:
            peer.record(row)
        peer.finish()
        motion = M.MotionReplay(self.epoch, state, peer.acks)
        for row in self.motion:
            motion.record(row)
        control = M.ControlReplay(
            self.epoch, {
                "state": state, "peer": peer.acks, "motion": motion.acks}, motion)
        for row in self.worker:
            control.record(row)
        native = {r: M.native_receipts(self.native[r], self.epoch, r) for r in R}
        return M.audit_advances(
            self.drive,
            self.physics,
            self.epoch,
            control,
            native,
            motion.release[0][0])


class CausalTests(unittest.TestCase):
    def setUp(self):
        self.f = Fixture()

    def reject(self, change):
        change(self.f)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            self.f.replay()

    def test_full_positive_and_explicit_scopes(self):
        value = self.f.replay()
        self.assertEqual((value["bootstrap_zero_advances"], value["normal_advances"],
                          value["permanent_stop_advances"]), (1, 1, 1))

    def test_actual_nonzero_native_value_mutation(self):
        self.reject(lambda f: f.native["tb1"][1].update(desired_v=.26))

    def test_future_ack_cannot_borrow_sameclock(self):
        self.reject(
            lambda
            f:
            next(
                r for r in f.worker
                if r["kind"] == "ack_received" and r["component"] == "peer" and
                r["ack"]["operation"] == "commit").update(wall_monotonic_ns=100))

    def test_missing_sixth_actual_callback(self):
        self.reject(lambda f: f.peer.remove(next(r for r in f.peer if r["kind"] == "received_tf"
                                                 and r["payload"]["robot"] == "tb3")))

    def test_fake_old_identical_side_payload_callback(self):
        self.reject(
            lambda f: next(
                r for r in f.peer if r["kind"] == "received_odom")["payload"].update(
                received_wall_monotonic_ns=1))

    def test_wrong_raw_callback_sha(self):
        self.reject(lambda f: next(r for r in f.peer if r["kind"] == "received_odom")[
                    "payload"]["raw"]["pose"]["pose"]["position"].update(x=8.))

    def test_cloud_bytes_mutation_with_updated_metadata_sha(self):
        def mutate(f):
            item = next(r for r in f.peer if r["kind"] == "obstacles_published")[
                "payload"]["publications"][1]
            item["payload"]["data_sha256"] = "0"*64
            item["message_sha256"] = M.digest(item["payload"])
        self.reject(mutate)

    def test_scan_false_cannot_replace_zero(self):
        self.reject(lambda f: next(r for r in f.peer if r["kind"] == "obstacles_published")[
                    "payload"]["publications"][0]["payload"].update(scan_time=False))

    def test_peer_ack_before_real_obstacle_calls_returned(self):
        self.reject(
            lambda f: next(
                r for r in f.peer if r["kind"] == "ack_published"
                and r["payload"]["ack"]["operation"] == "commit")["payload"].update(
                publish_started_wall_monotonic_ns=100))

    def test_auto_timer_after_takeover(self):
        def mutate(f):
            row = copy.deepcopy(f.peer[0])
            row["kind"] = "warmup_obstacles_published"
            row["record_sequence"] = len(f.peer)+1
            f.peer.append(row)
        self.reject(mutate)

    def test_normal_status_missing_actual_local_receipt(self):
        self.reject(
            lambda f: f.motion.remove(
                next(
                    r for r in f.motion
                    if r["kind"] == "actual_cmd_vel" and r["payload"]
                    ["observed_decision_sequence"] == 2)))

    def test_filtered_twist_not_native_request(self):
        self.reject(
            lambda
            f:
            next(
                r for r in f.motion
                if r["kind"] == "actual_cmd_vel" and
                r["payload"]["observed_decision_sequence"] == 2)["payload"]["twist"]
            ["linear"].update(x=.26))

    def test_actual_received_bundle_after_decision_cannot_be_borrowed(self):
        def mutate(f):
            row = next(r for r in f.motion if r["kind"] == "received_states")
            f.motion.remove(row)
            at = next(i for i, r in enumerate(f.motion) if r["kind"] == "control_commit")
            f.motion.insert(at, row)
        self.reject(mutate)

    def test_guard_dependency_after_decision_cannot_be_borrowed(self):
        self.reject(lambda f: next(r for r in f.motion if r["kind"] == "control_dependency"
                                   and r["payload"]["component"] == "peer").update(
            wall_monotonic_ns=10**12))

    def test_worker_consume_without_real_callback(self):
        self.reject(
            lambda f: f.worker.remove(
                next(
                    r for r in f.worker
                    if r["kind"] == "ack_received" and r["component"] == "peer" and
                    r["ack"]["operation"] == "commit")))

    def test_motion_before_peer_consumed(self):
        self.reject(
            lambda
            f:
            next(
                r for r in f.worker
                if r["kind"] == "request" and r["component"] == "motion" and
                r["request"]["operation"] == "commit").update(wall_monotonic_ns=1))

    def test_wrong_exact_worker_clock(self):
        self.reject(
            lambda f: next(
                r for r in f.worker if r["kind"] == "ack_consumed").update(
                worker_clock_ns=1))

    def test_missing_one_native_storage(self):
        self.reject(lambda f: f.native["tb2"].pop(1))

    def test_wrong_native_target_sequence(self):
        self.reject(lambda f: f.native["tb2"][1].update(target_decision_sequence=1))

    def test_native_callback_after_consumption(self):
        self.reject(
            lambda f: next(
                r for r in f.drive if r["kind"] == "ack_received"
                and r["ack"]["decision_sequence"] == 2).update(
                wall_monotonic_ns=10**12))

    def test_physics_before_three_storage_ack_consumed(self):
        self.reject(lambda f: next(r for r in f.drive if r["kind"] == "advance_permitted"
                                   and r["control_kind"] == "normal").update(wall_monotonic_ns=1))

    def test_wrong_control_identity_at_advance(self):
        self.reject(
            lambda f: next(
                r for r in f.drive if r["kind"] == "advance_permitted"
                and r["control_kind"] == "normal").update(
                control_request_id="invented"))

    def test_unclassified_physics_cannot_pass(self):
        self.reject(
            lambda f: next(
                r for r in f.drive if r["kind"] == "advance_permitted").pop("control_kind"))

    def test_bootstrap_cannot_repeat_as_normal(self):
        self.reject(
            lambda f: next(
                r for r in f.drive if r["kind"] == "advance_permitted"
                and r["control_kind"] == "normal").update(
                control_kind="bootstrap_zero"))

    def test_bootstrap_cannot_claim_fresh_normal_credit(self):
        self.reject(lambda f: next(r for r in f.drive if r["kind"] == "advance_permitted"
                                   and r["control_kind"] == "bootstrap_zero").update(
            control_kind="normal"))

    def test_stop_status_nonzero(self):
        self.reject(lambda f: next(r for r in f.motion if r["kind"] == "decision"
                                   and r["payload"].get(
            "phase_kind") == "stop")["payload"]["decision"].update(output=[0., .1]))

    def test_stop_not_actual_notification(self):
        self.reject(
            lambda f: f.worker.remove(
                next(
                    r for r in f.worker if r["kind"] == "stop_observed")))

    def test_stop_cannot_be_normal_status(self):
        self.reject(lambda f: next(r for r in f.drive if r["kind"] == "advance_permitted"
                                   and r["control_kind"] == "stop").update(control_kind="normal"))

    def test_task_release_without_initial_chain(self):
        self.reject(
            lambda f: next(
                r for r in f.motion if r["kind"] == "release")["payload"].update(
                stamp=1.))

    def test_changed_actual_physical_end(self):
        self.reject(lambda f: f.physics[1].update(end_time_ns=1_040_000_001))

    def test_legal_late_duplicate_callback_not_reused(self):
        row = copy.deepcopy(next(r for r in self.f.worker if r["kind"] == "ack_received"))
        row.update(worker_clock_ns=1_060_000_000, worker_physical_ns=1_060_000_000,
                   wall_monotonic_ns=self.f.tick())
        self.f.worker.append(row)
        self.f.replay()

    def test_source_stop_inflight_is_diagnostic_until_worker_processes_it(self):
        state = M.information_acks(self.f.info, self.f.epoch)
        peer = M.PeerReplay(self.f.epoch, state)
        for row in self.f.peer:
            peer.record(row)
        motion = M.MotionReplay(self.f.epoch, state, peer.acks)
        for row in self.f.motion:
            motion.record(row)
        components = {'state': state, 'peer': peer.acks, 'motion': motion.acks}
        control = M.ControlReplay(self.f.epoch, components, motion)
        for row in self.f.worker:
            control.record(row)
        native = {r: M.native_receipts(self.f.native[r], self.f.epoch, r) for r in R}
        permit = next(row for row in self.f.drive if row['kind'] == 'advance_permitted'
                      and row['control_kind'] == 'normal')
        # Isolate the predeclared asynchronous-prefix rule; not a native trace credit.
        motion.first_stop_wall = permit['wall_monotonic_ns'] - 1
        value = M.audit_advances(self.f.drive, self.f.physics, self.f.epoch,
                                 control, native, motion.release[0][0])
        self.assertEqual(len(value['source_stop_before_nonstop_permit_diagnostic_only']), 1)
        control.stopped_at.append(permit['wall_monotonic_ns'] - 1)
        with self.assertRaisesRegex(ValueError, 'worker actually processed stop'):
            M.audit_advances(self.f.drive, self.f.physics, self.f.epoch,
                             control, native, motion.release[0][0])

    def test_control_failure_cannot_hide_behind_completed_zero_stop(self):
        self.f.mrow('control_failure', {'error': 'real phase error'})
        with self.assertRaisesRegex(ValueError, 'actual recorded control protocol failure'):
            self.f.replay()

    def test_invalid_bundle_cannot_hide_behind_zero_stop(self):
        self.f.mrow('invalid_received_states', {'reason': 'invalid epoch/schema'})
        with self.assertRaisesRegex(ValueError, 'actual recorded control protocol failure'):
            self.f.replay()

    def test_clock_changed_during_decision_is_control_failure(self):
        self.f.mrow('clock_changed_during_decision', {'decision_clock_ns': 1_040_000_000})
        with self.assertRaisesRegex(ValueError, 'actual recorded control protocol failure'):
            self.f.replay()

    def test_actual_terminal_cancellation_is_legitimate_permanent_stop(self):
        target, identity = 1_040_000_000, 'pending_terminal'
        request = self.f.request('state', 'commit', target, identity)
        notice = {'epoch': self.f.epoch, 'end_sim_time_sec': target/1e9,
                  'termination_reason': 'navigation_failure'}
        ack = self.f.ack('state', 'commit', target, identity)
        ack.update(ok=False, error='state_phase_task_terminal', terminal_notice=notice,
                   clock_ns=target-20_000_000, scope='terminal_cancelled_uncommitted_state_phase')
        self.f.info.append({'kind': 'state_terminal_received', 'epoch': self.f.epoch,
                            'clock_ns': target-20_000_000,
                            'wall_monotonic_ns': self.f.tick(), 'payload': {'notice': notice}})
        self.f.iack(ack)
        self.f.wrow('ack_received', target, component='state', ack=ack)
        self.f.wrow('ack_rejected', target, component='state', ack=ack)
        self.f.wrow('terminal_cancelled', target, component='state', ack=ack,
                    terminal_notice=notice)
        state = M.information_acks(self.f.info, self.f.epoch)
        control = M.ControlReplay(self.f.epoch, {'state': state}, None)
        for row in self.f.worker[-4:]:
            control.record(row)
        self.assertTrue(control.stopped)
        self.assertNotIn(('state', request['request_id']), control.consumed)
        bad = copy.deepcopy(self.f.worker[-4:])
        bad[1]['ack']['error'] = 'state_phase_wall_timeout'
        # Actual rejected phase errors are failures, even if later a zero stop exists.
        state[identity]['ack']['error'] = 'state_phase_wall_timeout'
        control = M.ControlReplay(self.f.epoch, {'state': state}, None)
        with self.assertRaisesRegex(ValueError, 'real control failure'):
            for row in bad:
                control.record(row)

    def test_terminal_cancellation_without_actual_notice_is_not_borrowable(self):
        target, identity = 1_040_000_000, 'fake_terminal'
        self.f.request('state', 'commit', target, identity)
        notice = {'epoch': self.f.epoch, 'end_sim_time_sec': target/1e9,
                  'termination_reason': 'navigation_failure'}
        ack = self.f.ack('state', 'commit', target, identity)
        ack.update(ok=False, error='state_phase_task_terminal', terminal_notice=notice,
                   clock_ns=target-20_000_000, scope='terminal_cancelled_uncommitted_state_phase')
        self.f.iack(ack)
        with self.assertRaisesRegex(ValueError, 'no actual prior information notice'):
            M.information_acks(self.f.info, self.f.epoch)
        row = {'kind': 'state_terminal_received', 'epoch': self.f.epoch,
               'clock_ns': target-20_000_000, 'wall_monotonic_ns': self.f.wall-1,
               'payload': {'notice': {**notice, 'termination_reason': 'other'}}}
        self.f.info.insert(-1, row)
        with self.assertRaisesRegex(ValueError, 'no actual prior information notice'):
            M.information_acks(self.f.info, self.f.epoch)

    def test_successful_state_commit_cannot_borrow_old_clock(self):
        self.reject(lambda f: next(
            row for row in f.info if row['kind'] == 'state_phase_ack'
            and row['payload']['ack']['operation'] == 'commit'
        )['payload']['ack'].update(clock_ns=1_000_000_000))

    def test_boolean_state_sequence_cannot_masquerade_as_one(self):
        publication = next(row['payload'] for row in self.f.info if row['kind'] == 'state_publish')
        ack = next(row['payload']['ack'] for row in self.f.info
                   if row['kind'] == 'state_phase_ack'
                   and row['payload']['ack']['operation'] == 'commit')
        publication['message']['sequence'] = True
        publication['message_sha256'] = M.digest(publication['message'])
        ack.update(state_sequence=True, bundle_sha256=publication['message_sha256'])
        with self.assertRaisesRegex(ValueError, 'state ACK positive sequence'):
            M.information_acks(self.f.info, self.f.epoch)

    def test_original_halfmetre_body_gate_endpoint(self):
        selected = {(k, r): {'raw': self.f.raw(k, r, 1_020_000_000)}
                    for k in ('odom', 'tf') for r in R}
        selected['odom', 'tb2']['raw']['pose']['pose']['position']['x'] = .5
        M.expected_outputs(selected, 1_020_000_000)
        selected['odom', 'tb2']['raw']['pose']['pose']['position']['x'] = .499999999
        with self.assertRaises(ValueError):
            M.expected_outputs(selected, 1_020_000_000)

    def test_original_source_halfsecond_and_one_ns(self):
        selected = {(k, r): {'raw': self.f.raw(k, r, 1_000_000_000)}
                    for k in ('odom', 'tf') for r in R}
        M.expected_outputs(selected, 1_500_000_000)
        with self.assertRaises(ValueError):
            M.expected_outputs(selected, 1_500_000_001)

    def test_v9_fresh_odom_cannot_wash_old_tf(self):
        target = 74_340_000_000
        selected = {(k, r): {'raw': self.f.raw(k, r, target)}
                    for k in ('odom', 'tf') for r in R}
        selected['odom', 'tb2']['raw']['header']['stamp'] = {'sec': 74, 'nanosec': 313000000}
        selected['tf', 'tb2']['raw']['header']['stamp'] = {'sec': 73, 'nanosec': 995000000}
        with self.assertRaisesRegex(ValueError, 'source500ms'):
            M.expected_outputs(selected, target)

    def test_future_raw_source_rejected(self):
        selected = {(k, r): {'raw': self.f.raw(k, r, 1_000_000_001)}
                    for k in ('odom', 'tf') for r in R}
        with self.assertRaises(ValueError):
            M.expected_outputs(selected, 1_000_000_000)

    def test_nan_raw_rejected(self):
        self.reject(lambda f: next(r for r in f.peer if r['kind'] == 'received_odom')[
                    'payload']['raw']['pose']['pose']['position'].update(x=float('nan')))

    def test_cross_epoch_actual_callback(self):
        self.reject(
            lambda f: next(
                r for r in f.peer if r['kind'] == 'received_odom').update(
                epoch='wrong'))

    def test_received_only_topic_required(self):
        self.reject(
            lambda f: next(
                r for r in f.peer if r['kind'] == 'received_odom')['payload'].update(
                topic='/tb1/odom'))

    def test_missing_one_obstacle_call(self):
        self.reject(lambda f: next(r for r in f.peer if r['kind'] == 'obstacles_published')[
                    'payload']['publications'].pop())

    def test_bool_not_integer_sequence(self):
        self.reject(
            lambda f: next(
                r for r in f.peer if r['kind'] == 'received_odom')['payload'].update(
                input_sequence=True))

    def test_actual_peer_clock_must_match(self):
        self.reject(
            lambda f: next(
                r for r in f.peer if r['kind'] == 'obstacles_published').update(
                clock_ns=1_020_000_001))

    def test_normal_ack_cannot_be_overwritten(self):
        def mutate(f):
            row = copy.deepcopy(next(r for r in f.motion if r['kind'] == 'output_completed'))
            row['record_sequence'] = len(f.motion)+1
            f.motion.append(row)
        self.reject(mutate)

    def test_stop_sameclock_keeps_original_normal_ack(self):
        for row in self.f.motion:
            value = row['payload']
            if row['kind'] == 'control_request' and value['operation'] == 'stop':
                value['target_time_ns'] = 1_020_000_000
            if row['kind'] == 'decision' and value.get('phase_kind') == 'stop':
                value['clock_ns'] = 1_020_000_000
            if row['kind'] == 'output_completed' and value['status'].get('phase_kind') == 'stop':
                value['status']['clock_ns'] = 1_020_000_000
            if row['kind'] in ('control_ack', 'control_ack_published'):
                ack = value.get('ack', value)
                if ack['operation'] == 'stop':
                    ack.update(target_time_ns=1_020_000_000, clock_ns=1_020_000_000)
        state = M.information_acks(self.f.info, self.f.epoch)
        peer = M.PeerReplay(self.f.epoch, state)
        for row in self.f.peer:
            peer.record(row)
        motion = M.MotionReplay(self.f.epoch, state, peer.acks)
        for row in self.f.motion:
            motion.record(row)
        self.assertIn((1_020_000_000, 'normal'), motion.completed)
        self.assertIn((1_020_000_000, 'stop'), motion.completed)
        self.assertEqual(motion.completed[1_020_000_000, 'normal']
                         ['status']['outputs']['tb1']['linear_x'], .13)
        self.assertEqual(motion.completed[1_020_000_000, 'stop']
                         ['status']['outputs']['tb1']['linear_x'], 0.)

    def test_stop_has_no_freshness_credit(self):
        self.reject(lambda f: next(r for r in f.motion if r['kind'] == 'output_completed'
                                   and r['payload']['status'].get(
            'phase_kind') == 'stop')['payload']['status'].update(ready=True))

    def test_wrong_actual_component_request(self):
        self.reject(
            lambda
            f:
            next(
                r for r in f.worker
                if r['kind'] == 'request' and r['component'] == 'peer' and
                r['request']['operation'] == 'commit')['request'].update(
                target_time_ns=1_040_000_000))

    def test_real_storage_receipt_wrong_topic_robot(self):
        self.reject(
            lambda f: next(
                r for r in f.drive if r['kind'] == 'ack_received').update(
                topic_robot='tb3'))

    def test_peer_success_without_pub_calls(self):
        self.reject(
            lambda f: f.peer.remove(
                next(
                    r for r in f.peer if r['kind'] == 'obstacles_published')))

    def test_unpermitted_extra_physics_cannot_borrow_previous_ack(self):
        def mutate(f):
            row = copy.deepcopy(f.physics[-1])
            row['request_id'] = 'fake'
            f.physics.append(row)
            f.drow('physics_completed', row['start_time_ns'], receipt=row)
        self.reject(mutate)

    def test_normal_after_latched_stop_rejected(self):
        def mutate(f):
            row = copy.deepcopy(
                next(
                    r for r in f.worker
                    if r['kind'] == 'request' and r['component'] == 'state' and
                    r['request']['operation'] == 'commit'))
            row['request']['request_id'] = 'afterstop'
            row['wall_monotonic_ns'] = f.tick()
            f.worker.append(row)
        self.reject(mutate)

    def test_gzip_archive_and_source_binding(self):
        import gzip
        with tempfile.TemporaryDirectory() as name:
            path = Path(name)
            files = {
                "metadata.json": {"epoch": self.f.epoch, "freeze": "freeze"},
                "summary.json": {},
                "transitions.jsonl": [],
                "physics.jsonl": self.f.physics, "information_states.jsonl": self.f.info,
                "peer_phase.jsonl": self.f.peer, "motion_safety.jsonl": self.f.motion,
                "control_phase_worker.jsonl": self.f.worker,
                "drive_phase_worker.jsonl": self.f.drive, **
                {"drive_" + r + ".jsonl": self.f.native[r] for r in R}}
            for filename, data in files.items():
                text = "".join(
                    json.dumps(row) +
                    "\n" for row in data) if filename.endswith("jsonl") else json.dumps(data)
                (path/(filename+".gz")).write_bytes(gzip.compress(text.encode(), mtime=0))
            result = M.audit(path, "freeze")
            self.assertTrue(result["passed"], result)
            self.assertFalse(M.audit(path, "other")["passed"])
            self.assertTrue(M.audit(path, "freeze", True)["passed"])
            for mode in ([], ['--peer-only']):
                out = path / ('peer.json' if mode else 'control.json')
                call = subprocess.run([sys.executable, str(PATH), str(path),
                                       '--freeze', 'freeze', '--output', str(out), *mode],
                                      capture_output=True, text=True)
                self.assertEqual(call.returncode, 0, call.stderr)
                self.assertTrue(json.loads(out.read_text())['passed'])


if __name__ == "__main__":
    unittest.main()
