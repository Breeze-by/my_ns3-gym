"""Conditional synthetic tests; root's finite runner owns actual FAIL/waits."""
from dataclasses import FrozenInstanceError, replace
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import handoff_contract_v1 as h

EPOCH = "cpu-conditional-epoch"
START = 1_000_000_000
Q20 = 20_000_000
FRAMES = ("map", "odom", "base_footprint")


def token(number):
    return "%064x" % number


def raw(source, sequence, *, xy=(0, 0), velocity=(0, 0), frames=FRAMES,
        epoch=EPOCH, robot="tb1"):
    return h.RawSample(source, sequence, frames, xy, xy, velocity, (0, 0, 0),
                       token(sequence), h.SourceBinding(epoch, robot))


def witness(c, mode="disk", target=None):
    return h.ConditionalWitness(mode, EPOCH, "tb1", c.now_ns,
        c._latest.payload_sha256, c.now_ns, c.now_ns + h.H_NS,
        token(200), token(201), token(202), token(203),
        c.intent.sha256 if target and c.intent else "", target.sha256 if target else "",
        c.intent.transition_reach_sha256 if target and c.intent else "")


def actuations(c, through):
    """Complete synthetic 34ms journal, including repeated targets."""
    previous = c._actuation_received
    at, sequence = (previous.time_ns+h.ACTUATION_GAP_NS, previous.sequence+1) if previous else (START, 1)
    while at <= through:
        candidates = [(seq, item) for seq, item in c._stored.items() if item[1] <= at]
        target, _ = max(candidates)[1]
        c.stage_actuation(h.Actuation(at, sequence, target))
        at += h.ACTUATION_GAP_NS; sequence += 1


def clock(c, when, sample):
    c.stage_raw(sample); actuations(c, when)
    c.drain(when, raw_complete_ns=when, actuation_complete_ns=when)


def disk_fixture():
    c = h.HandoffContract(EPOCH, "tb1", START)
    zero = h.Target(EPOCH, "tb1", START, 1, 0., 0.)
    c.publish(zero); c.store(zero, START)
    for i in range(50):
        c.stage_raw(raw(START + i*Q20, i+1))
    end = START + 49*Q20
    actuations(c, end)
    c.drain(end, raw_complete_ns=end, actuation_complete_ns=end)
    c.activate(witness(c))
    return c


def intent_fixture():
    c = disk_fixture()
    zero = h.Target(EPOCH, "tb1", c.now_ns, 2, 0., 0.)
    c.announce_normal(zero, token(300)); c.store(zero, c.now_ns)
    clock(c, c.now_ns+Q20, raw(c.now_ns+Q20, 51))
    return c


def delivered(c, peers=("tb2", "tb3")):
    envelope = h.StateEnvelope(EPOCH, "tb1", c.now_ns, c.now_ns,
                              token(c.now_ns), c.intent.sha256, token(300))
    for i, peer in enumerate(peers):
        c.receive_envelope(peer, envelope)
        c.peer_phase(h.PeerWatermark(peer, envelope, c.now_ns,
                                    "boundary"+str(c.now_ns), token(400+i)))
    return envelope


def publish_normal(c, sequence=3, v=.1):
    target = h.Target(EPOCH, "tb1", c.now_ns, sequence, v, .3)
    output = c.publish(target, witness(c, "normal" if c.mode == "NORMAL" else "transition", target))
    c.store(target, c.now_ns)
    return target, output


def normal_fixture():
    c = intent_fixture(); delivered(c)
    publish_normal(c)
    clock(c, c.now_ns+Q20, raw(c.now_ns+Q20, 52))
    clock(c, c.now_ns+Q20, raw(c.now_ns+Q20, 53, xy=(.001, 0), velocity=(.1, 0)))
    return c


def qualify_again(c, *, permanent=False):
    if permanent:
        c.request_stop()
    zero = h.Target(EPOCH, "tb1", c.now_ns, 4, 0., 0.)
    c.publish(zero); c.store(zero, c.now_ns)
    start, seq = c.now_ns, c._raw_received.sequence
    for i in range(1, 50):
        clock(c, start+i*Q20, raw(start+i*Q20, seq+i, xy=(.001, 0)))


class HandoffContractTests(unittest.TestCase):
    def test_bootstrap_zero_qualifies_once_and_anchor_is_immutable(self):
        c = disk_fixture(); anchor = c.protected_anchor
        with self.assertRaises(FrozenInstanceError):
            anchor.epoch = "changed"
        with self.assertRaises(h.ContractError):
            c.activate(witness(c))
        self.assertIs(c.protected_anchor, anchor)
        self.assertEqual(c.episode_anchors, (anchor,))

    def test_rotation_requires_current_disk_and_exact_target_witness(self):
        c = h.HandoffContract(EPOCH, "tb1", START)
        with self.assertRaises(h.ContractError):
            c.publish(h.Target(EPOCH, "tb1", START, 1, 0., .3))
        c = disk_fixture()
        rotation = h.Target(EPOCH, "tb1", c.now_ns, 2, 0., .3)
        with self.assertRaises(h.ContractError):
            c.publish(rotation)
        wrong = replace(witness(c, target=rotation), target_sha256=token(999))
        with self.assertRaises(h.ContractError):
            c.publish(rotation, wrong)
        c.publish(rotation, witness(c, target=rotation)); c.store(rotation, c.now_ns)
        self.assertTrue(c.disk_active)
        self.assertFalse(c.status()["native_admission"])

    def test_intent_keeps_zero_and_missing_peer_delivery_rejects_translation(self):
        c = intent_fixture(); anchor = c.protected_anchor
        self.assertEqual((c.intent.zero_target.v, c.intent.zero_target.w), (0., 0.))
        delivered(c, ("tb2",))
        with self.assertRaisesRegex(h.ContractError, "all relevant peers"):
            publish_normal(c)
        self.assertIs(c.protected_anchor, anchor)
        self.assertTrue(c.disk_active)
        self.assertEqual(c.mode, "INTENT_PENDING")

    def test_central_intent_and_forged_passed_cannot_substitute_received_proof(self):
        c = intent_fixture()
        env = h.StateEnvelope(EPOCH, "tb1", c.now_ns, 20, token(10), c.intent.sha256, token(300))
        with self.assertRaisesRegex(h.ContractError, "actual delivered"):
            c.peer_phase(h.PeerWatermark("tb2", env, c.now_ns, "boundary"+str(c.now_ns), token(400)))
        delivered(c)
        target = h.Target(EPOCH, "tb1", c.now_ns, 3, .1, .3)
        with self.assertRaisesRegex(h.ContractError, "full conditional"):
            c.publish(target, {"passed": True, "accepted": True, "native_admission": True})
        with self.assertRaises(h.ContractError):
            replace(witness(c, "transition", target), terminal_sha256="")
        self.assertFalse(c.status()["native_admission"])

    def test_phase_binds_exact_received_envelope_and_distinct_peer_receipt(self):
        c = intent_fixture(); env = delivered(c)
        with self.assertRaises(h.ContractError):
            c.peer_phase(h.PeerWatermark("tb2", replace(env, bundle_sha256=token(99)),
                                       c.now_ns, "boundary"+str(c.now_ns), token(900)))
        with self.assertRaisesRegex(h.ContractError, "another peer"):
            c.peer_phase(h.PeerWatermark("tb3", env, c.now_ns, "boundary"+str(c.now_ns), token(400)))

    def test_actual_application_and_strict_later_source_retire_disk_not_history(self):
        c = intent_fixture(); delivered(c); anchor = c.protected_anchor
        target, output = publish_normal(c)
        self.assertEqual(len(output["target"]), 7)
        self.assertTrue(output["conditional_cpu_translation"])
        self.assertFalse(output["native_admission"])
        self.assertTrue(c.disk_active)
        at = c.now_ns+Q20
        clock(c, at, raw(at, 52))
        self.assertEqual(c._first_nonzero_applied.target, target)
        self.assertTrue(c.disk_active)
        clock(c, at+Q20, raw(at+Q20, 53, xy=(.001, 0), velocity=(.1, 0)))
        self.assertEqual(c.mode, "NORMAL")
        self.assertFalse(c.disk_active)
        self.assertIs(c.protected_anchor, anchor)
        self.assertEqual(c.episode_anchors, (anchor,))

    def test_successor_seq_can_apply_without_first_seq_deadlock(self):
        c = intent_fixture(); delivered(c)
        first, _ = publish_normal(c)
        middle = c.now_ns+Q20//2
        clock(c, middle, raw(middle, 52)); delivered(c)
        successor, _ = publish_normal(c, sequence=4)
        at = middle+Q20//2
        clock(c, at, raw(at, 53))
        clock(c, at+Q20, raw(at+Q20, 54, xy=(.001, 0), velocity=(.1, 0)))
        self.assertEqual(c._first_nonzero_applied.target, successor)
        self.assertNotEqual(first.sequence, successor.sequence)
        self.assertEqual(c.mode, "NORMAL")

    def test_same_stamp_raw_precedes_application_and_cannot_hide_peak(self):
        c = intent_fixture(); delivered(c); publish_normal(c)
        at = c.now_ns+Q20
        c.stage_raw(raw(at, 52, velocity=(.02, 0))); actuations(c, at)
        with self.assertRaisesRegex(h.ContractError, "rest peak"):
            c.drain(at, raw_complete_ns=at, actuation_complete_ns=at)
        self.assertEqual(c.mode, "FAULT")

    def test_tiny_stored_never_applied_then_permanent_stop_cannot_reanchor(self):
        c = intent_fixture(); delivered(c); anchor = c.protected_anchor
        tiny, _ = publish_normal(c, v=math.nextafter(0., math.inf))
        c.request_stop()
        zero = h.Target(EPOCH, "tb1", c.now_ns, tiny.sequence+1, 0., 0.)
        c.publish(zero); c.store(zero, c.now_ns)
        at = c.now_ns+Q20
        clock(c, at, raw(at, 52))
        self.assertTrue(c.disk_active)
        self.assertIs(c.protected_anchor, anchor)
        self.assertEqual(c.mode, "STOPPING")
        with self.assertRaises(h.ContractError):
            c.activate(witness(c))

    def test_future_source_waits_then_fault_keeps_bad_source_and_ready_tail(self):
        c = disk_fixture(); old = c.now_ns
        bad = raw(old+Q20, 51, velocity=(0, .02)); tail = raw(old+2*Q20, 52)
        c.stage_raw(bad); c.stage_raw(tail); actuations(c, tail.source_ns)
        c.drain(old+Q20, raw_complete_ns=old, actuation_complete_ns=old)
        self.assertIsNone(c.fault)
        self.assertLess(c.checked_through_ns, c.now_ns)
        with self.assertRaises(h.ContractError):
            c.drain(tail.source_ns, raw_complete_ns=tail.source_ns, actuation_complete_ns=tail.source_ns)
        frontier = c.checked_through_ns
        self.assertIn(bad, tuple(item.payload for item in c.ingress_archive))
        self.assertIn(tail, tuple(item.payload for item in c.ingress_archive))
        self.assertIn((tail.source_ns, 0, tail), c.pending_events)
        with self.assertRaises(h.ContractError):
            c.drain(tail.source_ns, raw_complete_ns=tail.source_ns, actuation_complete_ns=tail.source_ns)
        self.assertEqual(c.checked_through_ns, frontier)

    def test_source_owner_gap_frame_and_full_planar_peak_survive_handoff(self):
        for failure in ("owner", "gap", "frame", "peak"):
            with self.subTest(failure=failure):
                c = intent_fixture(); delivered(c); publish_normal(c)
                at = c.now_ns+Q20
                clock(c, at, raw(at, 52))
                later = at+h.GAP_NS+1 if failure == "gap" else at+Q20
                sample = raw(later, 53, velocity=(0, .31) if failure == "peak" else (0, 0),
                             frames=("map", "different_odom", "base") if failure == "frame" else FRAMES,
                             epoch="foreign" if failure == "owner" else EPOCH)
                with self.assertRaises(h.ContractError):
                    c.stage_raw(sample); actuations(c, later)
                    c.drain(later, raw_complete_ns=later, actuation_complete_ns=later)
                self.assertEqual(c.mode, "FAULT")
                self.assertEqual(len(c.episode_anchors), 1)

    def test_actuation_source_and_trailing_watermark_holes_are_not_complete(self):
        c = disk_fixture(); end = c.now_ns+140_000_000
        with self.assertRaisesRegex(h.ContractError, "actuation source"):
            c.stage_actuation(h.Actuation(end, c._actuation_received.sequence+1, c._actuation_received.target))
        c = disk_fixture(); end = c.now_ns+80_000_000
        c.stage_raw(raw(end, 51))
        with self.assertRaisesRegex(h.ContractError, "final complete actuation"):
            c.drain(end, raw_complete_ns=end, actuation_complete_ns=end)

    def test_superseded_stored_target_cannot_claim_real_application(self):
        c = intent_fixture(); delivered(c); target, _ = publish_normal(c)
        zero = h.Target(EPOCH, "tb1", c.now_ns, 4, 0., 0.)
        c.publish(zero); c.store(zero, c.now_ns)
        at = c.now_ns+Q20
        c.stage_raw(raw(at, 52))
        c.stage_actuation(h.Actuation(at, c._actuation_received.sequence+1, target))
        with self.assertRaisesRegex(h.ContractError, "latest registered"):
            c.drain(at, raw_complete_ns=at, actuation_complete_ns=at)
        self.assertTrue(c.disk_active)

    def test_normal_zero_real_application_and_fresh_qualification_reaches_second_disk(self):
        c = normal_fixture(); old = c.protected_anchor
        qualify_again(c)
        self.assertEqual(c.mode, "QUALIFYING")
        with self.assertRaises(h.ContractError):
            c.activate(replace(witness(c), terminal_sha256=token(999)))
        c.activate(witness(c))
        self.assertEqual(c.mode, "DISK")
        self.assertEqual(len(c.episode_anchors), 2)
        self.assertIs(c.episode_anchors[0], old)
        self.assertNotEqual(c.protected_anchor.sha256, old.sha256)
        self.assertFalse(c.status()["native_admission"])

    def test_permanent_stop_cannot_take_ordinary_requalification_route(self):
        c = normal_fixture(); old = c.protected_anchor
        qualify_again(c, permanent=True)
        with self.assertRaises(h.ContractError):
            c.activate(witness(c))
        self.assertEqual(c.mode, "STOPPING")
        self.assertIs(c.protected_anchor, old)
        self.assertEqual(len(c.episode_anchors), 1)

    def test_all_ingress_and_full_chord_diagnostics_are_retained_without_L1_gate(self):
        c = disk_fixture(); first_anchor = c.protected_anchor; start = c.now_ns
        for i in range(1, 101):
            at = start+i*Q20
            clock(c, at, raw(at, 50+i, xy=(.0001 if i % 2 else 0, 0)))
        self.assertTrue(c.disk_active)
        self.assertIsNone(c.fault)
        self.assertIs(c.protected_anchor, first_anchor)
        self.assertGreater(c.cumulative_chord_diagnostic[0], float(h.R))
        self.assertEqual(len(c.path_diagnostics), 149)
        self.assertEqual(sum(item.kind == "raw" for item in c.ingress_archive), 150)
        self.assertTrue(c.status()["cumulative_chords_are_diagnostic_only"])
        with self.assertRaises(FrozenInstanceError):
            c.ingress_archive[0].kind = "changed"

    def test_conflicting_equal_source_and_disk_excursion_do_not_renew_anchor(self):
        c = disk_fixture()
        with self.assertRaisesRegex(h.ContractError, "conflicting same-stamp"):
            c.stage_raw(raw(c.now_ns, 51, xy=(.001, 0)))
        c = disk_fixture(); later = c.now_ns+Q20
        c.stage_raw(raw(later, 51, xy=(.008, 0))); actuations(c, later)
        with self.assertRaisesRegex(h.ContractError, "disk excursion"):
            c.drain(later, raw_complete_ns=later, actuation_complete_ns=later)
        self.assertEqual(len(c.episode_anchors), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
