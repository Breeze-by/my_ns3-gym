"""Independent handoff attacks; initially unexecuted, root owns finite runs.

These synthetic tests demand contract behavior. They supply no continuous
plant proof, real delivery, native permission, or experimental acceptance.
The first version intentionally exposes known omissions in the sealed model.
"""
from dataclasses import replace
import importlib.util
from pathlib import Path
import sys
import unittest


_SPEC = importlib.util.spec_from_file_location(
    'mr3_v14_handoff_adversarial_under_test',
    Path(__file__).with_name('handoff_contract_v1.py'))
h = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = h
_SPEC.loader.exec_module(h)

EPOCH = 'independent-adversarial-cpu-epoch'
ROBOT = 'tb1'
START = 1_000_000_000
Q20 = 20_000_000
ACTUATOR = 34_000_000
FRAMES = ('map', 'odom', 'base_footprint')


def token(value):
    return h.digest(value)


def raw(source, sequence, *, xy=(0, 0), velocity=(0, 0),
        epoch=EPOCH, robot=ROBOT):
    # The semantic payload owner is included in its immutable digest. A full
    # source contract must additionally carry and validate typed owner binding;
    # an opaque digest alone cannot let the model verify it.
    sha = token([epoch, robot, source, sequence, xy, velocity])
    return h.RawSample(source, sequence, FRAMES, xy, xy, velocity, (0, 0, 0), sha)


def proof(c, mode='disk', target=None):
    return h.ConditionalWitness(
        mode, c.epoch, c.robot, c.now_ns, c._latest.payload_sha256,
        c.now_ns, c.now_ns+h.H_NS, token('geometry'), token('plant'),
        token('backup'), token('terminal'),
        c.intent.sha256 if target is not None else '',
        target.sha256 if target is not None else '',
        c.intent.transition_reach_sha256 if target is not None else '')


class Harness:
    """Independent complete synthetic 50Hz raw / 34ms actuation streams."""
    def __init__(self):
        self.c = h.HandoffContract(EPOCH, ROBOT, START)
        self.raw_sequence, self.actuation_sequence = 0, 0
        self.raw_time, self.actuation_time = START-Q20, START-ACTUATOR
        self.stored = []
        zero = h.Target(EPOCH, ROBOT, START, 1, 0., 0.)
        self.publish_store(zero)

    def publish_store(self, target, witness=None):
        output = self.c.publish(target, witness)
        self.c.store(target, self.c.now_ns)
        self.stored.append(target)
        return output

    def stream_raw(self, through, *, xy=(0, 0), velocity=(0, 0)):
        while self.raw_time+Q20 <= through:
            self.raw_time += Q20
            self.raw_sequence += 1
            self.c.stage_raw(raw(self.raw_time,self.raw_sequence,
                                 xy=xy,velocity=velocity))

    def stream_actuation(self, through):
        while self.actuation_time+ACTUATOR <= through:
            self.actuation_time += ACTUATOR
            self.actuation_sequence += 1
            target = max((t for t in self.stored if t.clock_ns<=self.actuation_time),
                         key=lambda t:(t.clock_ns,t.sequence))
            self.c.stage_actuation(h.Actuation(self.actuation_time,
                                               self.actuation_sequence,target))

    def advance(self, through, *, xy=(0, 0), velocity=(0, 0)):
        self.stream_raw(through,xy=xy,velocity=velocity)
        self.stream_actuation(through)
        self.c.drain(through,raw_complete_ns=through,actuation_complete_ns=through)

    def disk(self):
        self.advance(START+980_000_000)
        self.c.activate(proof(self.c))
        return self

    def deliver(self):
        c = self.c
        envelope = h.StateEnvelope(c.epoch,c.robot,c.now_ns,self.raw_sequence,
                                   token(['bundle',c.now_ns]),c.intent.sha256,
                                   c.intent.transition_reach_sha256)
        for peer in ('tb2','tb3'):
            c.receive_envelope(peer,envelope)
            c.peer_phase(h.PeerWatermark(peer,envelope,c.now_ns,
                                         'boundary'+str(c.now_ns),
                                         token(['receipt',peer,c.now_ns])))

    def intent(self):
        self.disk()
        c = self.c
        zero = h.Target(EPOCH,ROBOT,c.now_ns,2,0.,0.)
        c.announce_normal(zero,token('transition reach'))
        c.store(zero,c.now_ns)
        self.stored.append(zero)
        self.advance(c.now_ns+Q20)
        self.deliver()
        return self

    def normal(self):
        self.intent()
        c = self.c
        target = h.Target(EPOCH,ROBOT,c.now_ns,3,.1,0.)
        self.publish_store(target,proof(c,'transition',target))
        self.advance(c.now_ns+Q20)
        self.advance(c.now_ns+Q20,xy=(.001,0),velocity=(.1,0))
        return self


class IndependentHandoffAttacks(unittest.TestCase):
    def test_bootstrap_cannot_rotate_without_any_protection_witness(self):
        c = h.HandoffContract(EPOCH,ROBOT,START)
        rotation = h.Target(EPOCH,ROBOT,START,1,0.,.3)
        with self.assertRaises(h.ContractError):
            c.publish(rotation)
        self.assertFalse(c.status()['native_admission'])

    def test_incomplete_current_source_cannot_authorize_new_rotation(self):
        a = Harness().disk(); c = a.c
        old = c.now_ns
        a.stream_raw(old+Q20)
        c.drain(old+Q20,raw_complete_ns=old,actuation_complete_ns=old)
        self.assertLess(c.checked_through_ns,c.now_ns)
        rotation = h.Target(EPOCH,ROBOT,c.now_ns,2,0.,.3)
        with self.assertRaises(h.ContractError):
            c.publish(rotation)

    def test_fault_is_absorbing_and_cannot_certify_unprocessed_tail(self):
        a = Harness().disk(); c = a.c
        old = c.checked_through_ns
        first = raw(c.now_ns+Q20,a.raw_sequence+1,velocity=(.02,0))
        tail = raw(c.now_ns+2*Q20,a.raw_sequence+2)
        c.stage_raw(first); c.stage_raw(tail)
        a.stream_actuation(tail.source_ns)
        with self.assertRaises(h.ContractError):
            c.drain(tail.source_ns,raw_complete_ns=tail.source_ns,
                    actuation_complete_ns=tail.source_ns)
        self.assertEqual(c.checked_through_ns,old)
        with self.assertRaises(h.ContractError):
            c.drain(tail.source_ns,raw_complete_ns=tail.source_ns,
                    actuation_complete_ns=tail.source_ns)
        self.assertEqual(c.checked_through_ns,old)

    def test_first_bad_source_and_healthy_ready_tail_remain_owned(self):
        a = Harness().disk(); c = a.c
        first = raw(c.now_ns+Q20,a.raw_sequence+1,velocity=(0,.02))
        tail = raw(c.now_ns+2*Q20,a.raw_sequence+2)
        c.stage_raw(first); c.stage_raw(tail)
        a.stream_actuation(tail.source_ns)
        with self.assertRaises(h.ContractError):
            c.drain(tail.source_ns,raw_complete_ns=tail.source_ns,
                    actuation_complete_ns=tail.source_ns)
        retained = repr(c.history)+repr(getattr(c,'ingress_archive',()))+repr(c._events)
        self.assertIn(first.payload_sha256,retained)
        self.assertIn(tail.payload_sha256,retained)

    def test_complete_actuation_stream_cannot_hide_a_140ms_hole(self):
        a = Harness().disk(); c = a.c
        end = c.now_ns+140_000_000
        a.stream_raw(end)
        # A source-sequence increment of one does not prove a 30Hz stream was
        # complete when the physical timestamps have a much larger hole.
        target = max(a.stored,key=lambda t:t.sequence)
        with self.assertRaises(h.ContractError):
            c.stage_actuation(h.Actuation(end,a.actuation_sequence+1,target))
            c.drain(end,raw_complete_ns=end,actuation_complete_ns=end)
        self.assertFalse(c.status()['native_admission'])

    def test_same_frame_sequence_does_not_replace_epoch_robot_source_binding(self):
        a = Harness().disk(); c = a.c
        foreign = raw(c.now_ns+Q20,a.raw_sequence+1,
                      epoch='previous-episode',robot='tb3')
        with self.assertRaises(h.ContractError):
            c.stage_raw(foreign)

    def test_witness_cannot_begin_at_a_future_actuation_then_restart_H(self):
        a = Harness().intent(); c = a.c
        target = h.Target(EPOCH,ROBOT,c.now_ns,3,.1,0.)
        future_start = c.now_ns+34_000_000
        shifted = replace(proof(c,'transition',target),
                          valid_from_ns=future_start,
                          valid_through_ns=future_start+h.H_NS)
        with self.assertRaises(h.ContractError):
            c.publish(target,shifted)
        self.assertTrue(c.disk_active)

    def test_real_normal_then_new_zero_qualification_can_establish_new_disk(self):
        a = Harness().normal(); c = a.c
        old_anchor = c.protected_anchor
        self.assertEqual(c.mode,'NORMAL')
        self.assertFalse(c.disk_active)
        zero = h.Target(EPOCH,ROBOT,c.now_ns,4,0.,0.)
        a.publish_store(zero)
        a.advance(c.now_ns+980_000_000,xy=(.001,0))
        c.activate(proof(c))
        self.assertEqual(c.mode,'DISK')
        self.assertEqual(len(c.episode_anchors),2)
        self.assertIs(c.episode_anchors[0],old_anchor)
        self.assertNotEqual(c.protected_anchor.sha256,old_anchor.sha256)
        self.assertFalse(c.status()['native_admission'])

    def test_permanent_stop_cannot_use_requalification_to_recover(self):
        a = Harness().normal(); c = a.c
        old_anchor = c.protected_anchor
        c.request_stop()
        zero = h.Target(EPOCH,ROBOT,c.now_ns,4,0.,0.)
        a.publish_store(zero)
        a.advance(c.now_ns+980_000_000,xy=(.001,0))
        with self.assertRaises(h.ContractError):
            c.activate(proof(c))
        self.assertIs(c.protected_anchor,old_anchor)
        self.assertEqual(len(c.episode_anchors),1)
        self.assertEqual(c.mode,'STOPPING')


if __name__ == '__main__':
    unittest.main(verbosity=2)
