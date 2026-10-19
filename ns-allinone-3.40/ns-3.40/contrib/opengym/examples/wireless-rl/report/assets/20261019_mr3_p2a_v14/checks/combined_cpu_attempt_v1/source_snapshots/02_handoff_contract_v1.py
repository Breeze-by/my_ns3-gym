"""Isolated conditional handoff model; no ROS, simulator or native admission.

Typed witness/delivery inputs describe assumptions supplied to CPU examples.
This module cannot establish that a real peer received a promise, a physical
stream is complete, or the prospective plant/backup/terminal model is true.
No ``passed`` field or geometric result is an execution permission.

In particular, hashes below name CONDITIONAL evidence, not verified residual,
terminal confinement, stopping-path D or stopping-time H proofs.  The normal
model includes lateral slip and reverse longitudinal residual; a forward
velocity scalar cannot replace that model.  Requalification inherits the
normal backup's terminal commitment until a new disk witness is supplied.
"""
from dataclasses import dataclass
from fractions import Fraction as Q
import hashlib
import json
import math


ROBOTS = ("tb1", "tb2", "tb3")
R = Q(39, 5000)
H_NS = 780_000_000
GAP_NS = 100_000_000
SOURCE_MAX_NS = 500_000_000
PUBLICATION_SETTLE_NS = 940_000_000
STORAGE_SETTLE_NS = 780_000_000
ACTUATION_GAP_NS = 34_000_000
CONTROL_QUANTUM_NS = 20_000_000
COMMAND_BRIDGE_NS = CONTROL_QUANTUM_NS + ACTUATION_GAP_NS


class ContractError(ValueError):
    pass


def integer(value, minimum=0):
    if type(value) is not int or value < minimum:
        raise ContractError("invalid integer endpoint")
    return value


def digest_id(value):
    if (type(value) is not str or len(value) != 64
            or any(c not in "0123456789abcdef" for c in value)):
        raise ContractError("missing/invalid evidence digest")
    return value


def exact(value):
    if type(value) is float:
        if not math.isfinite(value):
            raise ContractError("nonfinite value")
        return Q.from_float(value)
    if type(value) in (int, Q):
        return Q(value)
    raise ContractError("invalid numeric type")


def vector(value, length):
    if not isinstance(value, (tuple, list)) or len(value) != length:
        raise ContractError("invalid vector")
    return tuple(exact(x) for x in value)


def digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class Target:
    epoch: str
    robot: str
    clock_ns: int
    sequence: int
    v: float
    w: float

    def __post_init__(self):
        integer(self.clock_ns); integer(self.sequence, 1)
        if (type(self.epoch) is not str or not self.epoch or self.robot not in ROBOTS
                or any(type(x) not in (int, float) or not math.isfinite(x) for x in (self.v, self.w))
                or abs(self.v) > .20 or abs(self.w) > .8):
            raise ContractError("unsupported target")

    def tag(self):
        return {"schema": "mr3-drive-target-v1", "epoch": self.epoch,
                "robot": self.robot, "clock_ns": self.clock_ns,
                "decision_sequence": self.sequence, "linear_x": self.v,
                "angular_z": self.w}

    @property
    def sha256(self):
        return digest(self.tag())


@dataclass(frozen=True)
class SourceBinding:
    """Declared own-stream identity; native provenance is NOT proved here."""
    epoch: str
    robot: str

    def __post_init__(self):
        if type(self.epoch) is not str or not self.epoch or self.robot not in ROBOTS:
            raise ContractError("invalid raw source owner")


@dataclass(frozen=True)
class RawSample:
    source_ns: int
    sequence: int
    frames: tuple
    map_xy: tuple
    raw_xy: tuple
    linear_xy: tuple
    angular_xyz: tuple
    payload_sha256: str
    binding: SourceBinding

    def __post_init__(self):
        integer(self.source_ns, 1); integer(self.sequence, 1)
        if not isinstance(self.binding, SourceBinding):
            raise ContractError("typed raw source binding required")
        if (not isinstance(self.frames, tuple) or len(self.frames) != 3
                or any(type(s) is not str or not s for s in self.frames)):
            raise ContractError("invalid frame binding")
        for name, length in (("map_xy", 2), ("raw_xy", 2), ("linear_xy", 2), ("angular_xyz", 3)):
            object.__setattr__(self, name, vector(getattr(self, name), length))
        digest_id(self.payload_sha256)


@dataclass(frozen=True)
class Anchor:
    epoch: str
    source: RawSample

    @property
    def sha256(self):
        return digest([self.epoch, self.source.binding.epoch, self.source.binding.robot,
                       self.source.source_ns, self.source.sequence,
                       self.source.frames, [str(x) for x in self.source.map_xy],
                       [str(x) for x in self.source.raw_xy], self.source.payload_sha256])


@dataclass(frozen=True)
class Intent:
    zero_target: Target
    anchor_sha256: str
    transition_reach_sha256: str

    @property
    def sha256(self):
        return digest([self.zero_target.tag(), self.anchor_sha256, self.transition_reach_sha256])


@dataclass(frozen=True)
class StateEnvelope:
    epoch: str
    owner: str
    clock_ns: int
    state_sequence: int
    bundle_sha256: str
    intent_sha256: str
    reach_sha256: str
    reach_kind: str = "transition"

    def __post_init__(self):
        if (type(self.epoch) is not str or not self.epoch or self.owner not in ROBOTS
                or self.reach_kind != "transition"):
            raise ContractError("invalid transition envelope identity")
        integer(self.clock_ns); integer(self.state_sequence, 1)
        for value in (self.bundle_sha256, self.intent_sha256, self.reach_sha256):
            digest_id(value)


@dataclass(frozen=True)
class PeerWatermark:
    peer: str
    envelope: StateEnvelope
    phase_clock_ns: int
    request_id: str
    receipt_sha256: str

    def __post_init__(self):
        if (self.peer not in ROBOTS or not isinstance(self.envelope, StateEnvelope)
                or type(self.request_id) is not str):
            raise ContractError("invalid peer receipt identity")
        integer(self.phase_clock_ns); digest_id(self.receipt_sha256)


@dataclass(frozen=True)
class ConditionalWitness:
    mode: str
    epoch: str
    robot: str
    checked_through_ns: int
    source_sha256: str
    valid_from_ns: int
    valid_through_ns: int
    geometry_sha256: str
    plant_sha256: str
    backup_sha256: str
    terminal_sha256: str
    intent_sha256: str = ""
    target_sha256: str = ""
    promised_reach_sha256: str = ""

    def __post_init__(self):
        if (self.mode not in ("disk", "transition", "normal") or self.robot not in ROBOTS
                or type(self.epoch) is not str or not self.epoch):
            raise ContractError("invalid conditional witness")
        for value in (self.checked_through_ns, self.valid_from_ns, self.valid_through_ns):
            integer(value)
        if self.valid_through_ns < self.valid_from_ns:
            raise ContractError("reversed witness interval")
        for name in ("source_sha256", "geometry_sha256", "plant_sha256", "backup_sha256", "terminal_sha256"):
            digest_id(getattr(self, name))
        if self.mode != "disk":
            for name in ("intent_sha256", "target_sha256", "promised_reach_sha256"):
                digest_id(getattr(self, name))


@dataclass(frozen=True)
class Actuation:
    time_ns: int
    sequence: int
    target: Target

    def __post_init__(self):
        integer(self.time_ns); integer(self.sequence, 1)
        if not isinstance(self.target, Target):
            raise ContractError("typed applied target required")


@dataclass(frozen=True)
class IngressRecord:
    kind: str
    arrival_clock_ns: int
    payload: object


@dataclass(frozen=True)
class ChordDiagnostic:
    start_source_ns: int
    end_source_ns: int
    map_squared: Q
    raw_squared: Q
    map_chord: float
    raw_chord: float


class HandoffContract:
    """One authoritative model instance per robot/epoch; no reset/clear API.

    ``drain`` requires two explicit complete-through watermarks. They are
    conditional input claims, not inferred from elapsed time or an idle queue.
    A future native integration must prove both watermarks and every receipt.
    Actuation is a COMPLETE native journal, not a stream of target switches:
    sequence and timestamps are continuous, with maximum 34ms source/tail gap.
    The 54ms command bridge is only a necessary observer check: actual 20ms
    boundary renewal/revocation and zero storage by T+20ms remain EXTERNAL
    implementation obligations.  This model does not prove that controller.
    H covers a counterfactual backup, never a lease for a nonzero command.
    Ingress is archived before validation and never discarded on failure.
    Cumulative chords are diagnostics only, never an old cumulative-L1 PASS.
    """
    def __init__(self, epoch, robot, release_ns):
        if type(epoch) is not str or not epoch or robot not in ROBOTS:
            raise ContractError("invalid episode owner")
        self.epoch, self.robot = epoch, robot
        self.release_ns = integer(release_ns, 1)
        self.now_ns, self.checked_through_ns = release_ns, release_ns - 1
        self.mode, self.fault, self.stopped = "QUALIFYING", None, False
        self._anchor, self.disk_active, self._can_anchor = None, False, True
        self._anchors, self._history, self._events = [], [], []
        self._ingress, self._chords = [], []
        self._map_chord_total = self._raw_chord_total = 0.
        self._latest, self._raw_received, self._actuation_received = None, None, None
        self._rest = []
        self._published, self._stored, self._proofs = {}, {}, {}
        self._zero_publication_ns = self._zero_storage_ns = None
        self._last_applied, self._first_nonzero_applied = None, None
        self._zero_applied_ns = None
        self._normal_terminal_sha256 = self._qualifying_terminal_sha256 = None
        self.intent, self._envelopes, self._peer_watermarks = None, {}, {}

    @property
    def protected_anchor(self):
        return self._anchor

    @property
    def episode_anchors(self):
        return tuple(self._anchors)

    @property
    def history(self):
        return tuple(self._history)

    @property
    def ingress_archive(self):
        return tuple(self._ingress)

    @property
    def pending_events(self):
        return tuple(self._events)

    @property
    def path_diagnostics(self):
        return tuple(self._chords)

    @property
    def cumulative_chord_diagnostic(self):
        return (self._map_chord_total, self._raw_chord_total)

    def _archive(self, kind, payload):
        self._ingress.append(IngressRecord(kind, self.now_ns, payload))

    def _fail(self, message):
        self.fault = self.fault or message
        self.mode = "FAULT"
        self._history.append(("fault", self.now_ns, message))
        raise ContractError(message)

    def _witness(self, witness, mode, target=None):
        if (not isinstance(witness, ConditionalWitness) or self.fault or self.stopped
                or witness.mode != mode or witness.epoch != self.epoch or witness.robot != self.robot
                or self._latest is None or self.checked_through_ns != self.now_ns
                or witness.checked_through_ns != self.now_ns
                or witness.source_sha256 != self._latest.payload_sha256
                or not witness.valid_from_ns <= self.now_ns
                or witness.valid_through_ns < self.now_ns + H_NS):
            raise ContractError("missing current full conditional/backup/terminal witness")
        if target is not None:
            if witness.target_sha256 != target.sha256:
                raise ContractError("target/promise witness substitution")
            if mode != "disk" and (self.intent is None
                    or witness.intent_sha256 != self.intent.sha256
                    or witness.promised_reach_sha256 != self.intent.transition_reach_sha256):
                raise ContractError("target/promise witness substitution")

    def activate(self, witness):
        if isinstance(witness, ConditionalWitness):
            self._archive("activation_witness", witness)
        self._witness(witness, "disk")
        if (not self._can_anchor or self.disk_active or self.mode != "QUALIFYING"
                or self._zero_publication_ns is None or self._zero_storage_ns is None
                or self.now_ns - self._zero_publication_ns < PUBLICATION_SETTLE_NS
                or self.now_ns - self._zero_storage_ns < STORAGE_SETTLE_NS
                or self._last_applied is None or self._last_applied.target.v != 0 or self._last_applied.target.w != 0
                or self._zero_applied_ns is None
                or self._qualifying_terminal_sha256 is not None
                   and witness.terminal_sha256 != self._qualifying_terminal_sha256
                or len(self._rest) != 3
                or any(s.source_ns < self._zero_publication_ns + PUBLICATION_SETTLE_NS
                       or s.source_ns <= self._zero_applied_ns
                       or not 0 <= self.now_ns - s.source_ns <= GAP_NS for s in self._rest)):
            raise ContractError("incomplete new disk qualification or existing anchor responsibility")
        self._anchor = Anchor(self.epoch, self._latest)
        self._anchors.append(self._anchor)
        self.disk_active, self._can_anchor, self.mode = True, False, "DISK"
        self._first_nonzero_applied = None
        self.intent = None; self._envelopes.clear(); self._peer_watermarks.clear()
        self._history.append(("activate", self.now_ns, self._anchor.sha256))
        return self._anchor

    def announce_normal(self, zero_target, transition_reach_sha256, witness=None):
        if (self.mode != "DISK" or not self.disk_active or self.stopped or self.fault
                or not isinstance(zero_target, Target) or zero_target.v != 0):
            raise ContractError("intent must keep the actual disk zero-line target")
        digest_id(transition_reach_sha256)
        self.publish(zero_target, witness)
        self.intent = Intent(zero_target, self._anchor.sha256, transition_reach_sha256)
        self.mode = "INTENT_PENDING"
        self._envelopes.clear(); self._peer_watermarks.clear()
        self._history.append(("intent_zero", self.now_ns, self.intent.sha256))
        return self.intent

    def receive_envelope(self, peer, envelope):
        if type(peer) is str and isinstance(envelope, StateEnvelope):
            self._archive("peer_delivery", (peer, envelope))
        if (type(peer) is not str or peer not in set(ROBOTS) - {self.robot} or not isinstance(envelope, StateEnvelope)
                or self.intent is None or envelope.epoch != self.epoch or envelope.owner != self.robot
                or envelope.reach_kind != "transition"
                or envelope.intent_sha256 != self.intent.sha256
                or envelope.reach_sha256 != self.intent.transition_reach_sha256
                or not self.intent.zero_target.clock_ns <= envelope.clock_ns <= self.now_ns
                or self.now_ns - envelope.clock_ns > SOURCE_MAX_NS
                or self.intent.zero_target.sequence not in self._stored):
            raise ContractError("no actual peer delivery of this transition intent")
        integer(envelope.clock_ns); integer(envelope.state_sequence, 1)
        for value in (envelope.bundle_sha256, envelope.intent_sha256, envelope.reach_sha256):
            digest_id(value)
        old = self._envelopes.get(peer)
        if old is not None and envelope != old and envelope.state_sequence <= old.state_sequence:
            self._fail("peer envelope changed or regressed")
        self._envelopes[peer] = envelope

    def peer_phase(self, watermark):
        if isinstance(watermark, PeerWatermark):
            self._archive("peer_phase", watermark)
        if (not isinstance(watermark, PeerWatermark)
                or watermark.peer not in set(ROBOTS) - {self.robot}
                or self._envelopes.get(watermark.peer) != watermark.envelope
                or type(watermark.phase_clock_ns) is not int or watermark.phase_clock_ns != self.now_ns
                or not 0 <= self.now_ns - watermark.envelope.clock_ns <= SOURCE_MAX_NS
                or watermark.request_id != "boundary" + str(self.now_ns)):
            raise ContractError("phase did not consume the actual delivered transition envelope")
        digest_id(watermark.receipt_sha256)
        if any(other != watermark.peer and old.receipt_sha256 == watermark.receipt_sha256
               for other, old in self._peer_watermarks.items()):
            raise ContractError("one peer receipt cannot stand for another peer")
        self._peer_watermarks[watermark.peer] = watermark

    def publish(self, target, witness=None):
        if isinstance(target, Target):
            self._archive("publication", target)
        if isinstance(witness, ConditionalWitness):
            self._archive("publication_witness", witness)
        if (not isinstance(target, Target) or target.epoch != self.epoch or target.robot != self.robot
                or target.clock_ns != self.now_ns
                or self._published and target.sequence <= max(self._published)):
            raise ContractError("invalid publication identity/order")
        if (self.stopped or self.fault) and (target.v != 0 or target.w != 0):
            raise ContractError("permanent stop/fault only permits zero publication")
        if target.v == 0 and target.w != 0:
            if self.disk_active and self._first_nonzero_applied is None:
                proof_mode = "disk"
            elif self.mode == "NORMAL":
                proof_mode = "normal"
            else:
                raise ContractError("rotation lacks an active disk/normal cover")
            self._witness(witness, proof_mode, target)
            self._proofs[target.sequence] = witness
        if target.v != 0:
            if self.mode not in ("INTENT_PENDING", "ACTUATION_PENDING", "NORMAL"):
                raise ContractError("nonzero publication lacks transition intent")
            self._witness(witness, "normal" if self.mode == "NORMAL" else "transition", target)
            if (set(self._peer_watermarks) != set(ROBOTS) - {self.robot}
                    or any(w.phase_clock_ns != self.now_ns or self._envelopes.get(peer) != w.envelope
                           for peer, w in self._peer_watermarks.items())):
                raise ContractError("all relevant peers must first commit the delivered TRANSITION reach")
            self._proofs[target.sequence] = witness
            self._zero_publication_ns = self._zero_applied_ns = None; self._rest.clear()
            if self.mode != "NORMAL":
                self.mode = "ACTUATION_PENDING"
        elif self._zero_publication_ns is None:
            self._zero_publication_ns = max(self.release_ns, self.now_ns)
        if target.v == 0 and target.w == 0 and self.mode == "NORMAL":
            # Ordinary braking is reversible after a NEW full qualification;
            # the task's permanent stop channel below is never reversible.
            self._qualifying_terminal_sha256 = self._normal_terminal_sha256
            self.mode = "QUALIFYING"
            self._history.append(("normal_zero_qualification", self.now_ns,
                                  self._qualifying_terminal_sha256))
        self._published[target.sequence] = target
        self._history.append(("publication", self.now_ns, target.sha256))
        return {"target": target.tag(), "sidecar_intent_sha256": self.intent.sha256 if self.intent else None,
                "conditional_cpu_translation": target.v != 0, "native_admission": False}

    def store(self, target, storage_ns):
        integer(storage_ns)
        if isinstance(target, Target):
            self._archive("storage_receipt", (target, storage_ns))
        expected = self._published.get(target.sequence) if isinstance(target, Target) else None
        if (expected is None or target.sha256 != expected.sha256
                or storage_ns != target.clock_ns or storage_ns != self.now_ns):
            self._fail("storage is not the exact paused registered target")
        if target.sequence in self._stored:
            if self._stored[target.sequence] != (target, storage_ns):
                self._fail("storage identity changed")
            return
        if self._stored and target.sequence <= max(self._stored):
            self._fail("storage sequence regressed")
        self._stored[target.sequence] = (target, storage_ns)
        if target.v != 0:
            self._zero_storage_ns = None
        elif self._zero_storage_ns is None:
            self._zero_storage_ns = max(self.release_ns, storage_ns)
        self._history.append(("storage", storage_ns, target.sha256))

    def stage_raw(self, sample):
        if not isinstance(sample, RawSample):
            self._fail("typed raw source required")
        self._archive("raw", sample)
        if self.fault:
            raise ContractError("fault latched; ingress retained without new closure")
        if sample.binding != SourceBinding(self.epoch, self.robot):
            self._fail("raw source epoch/robot mismatch")
        prior = self._raw_received
        if prior is not None:
            if sample.sequence != prior.sequence + 1:
                self._fail("raw ingress sequence gap/regression")
            if sample.source_ns < prior.source_ns:
                self._fail("raw source regressed")
            if sample.source_ns == prior.source_ns:
                if (sample.frames, sample.map_xy, sample.raw_xy, sample.linear_xy,
                    sample.angular_xyz, sample.payload_sha256) != (
                        prior.frames, prior.map_xy, prior.raw_xy, prior.linear_xy,
                        prior.angular_xyz, prior.payload_sha256):
                    self._fail("conflicting same-stamp raw source")
                self._raw_received = sample
                return
        if sample.source_ns <= self.checked_through_ns:
            self._fail("late raw after a closed completeness watermark")
        self._raw_received = sample
        self._events.append((sample.source_ns, 0, sample))

    def stage_actuation(self, event):
        if not isinstance(event, Actuation):
            self._fail("typed actuation event required")
        self._archive("actuation", event)
        if self.fault:
            raise ContractError("fault latched; ingress retained without new closure")
        prior = self._actuation_received
        if prior is not None:
            if event == prior:
                return
            if (event.sequence != prior.sequence + 1
                    or not 0 < event.time_ns - prior.time_ns <= ACTUATION_GAP_NS):
                self._fail("actuation source/sequence gap or regression")
        elif not self.release_ns <= event.time_ns <= self.release_ns + ACTUATION_GAP_NS:
            self._fail("first complete actuation source missing after release")
        if event.time_ns <= self.checked_through_ns:
            self._fail("late actuation after a closed completeness watermark")
        self._actuation_received = event
        self._events.append((event.time_ns, 1, event))

    def drain(self, physical_ns, *, raw_complete_ns, actuation_complete_ns):
        if self.fault:
            raise ContractError("fault latched; unprocessed tail and watermarks retained")
        integer(physical_ns); integer(raw_complete_ns); integer(actuation_complete_ns)
        limit = min(physical_ns, raw_complete_ns, actuation_complete_ns)
        if (physical_ns < self.now_ns or limit < self.checked_through_ns
                or raw_complete_ns > physical_ns or actuation_complete_ns > physical_ns):
            self._fail("invalid physical/completeness watermarks")
        self.now_ns = physical_ns
        ready = sorted((event for event in self._events if event[0] <= limit), key=lambda x: x[:2])
        for entry in ready:
            _, kind, event = entry
            self._raw(event) if kind == 0 else self._actuate(event)
            self._events.remove(entry)
        if self._latest is None or limit - self._latest.source_ns > GAP_NS:
            self._fail("missing/gapped final causal source")
        if (self._last_applied is None
                or limit - self._last_applied.time_ns > ACTUATION_GAP_NS):
            self._fail("missing/gapped final complete actuation source")
        if ((self._last_applied.target.v != 0 or self._last_applied.target.w != 0)
                and limit - self._last_applied.target.clock_ns > COMMAND_BRIDGE_NS):
            self._fail("nonzero target exceeded the necessary 54ms command lease bridge")
        self.checked_through_ns = limit

    def _actuate(self, event):
        candidates = [(seq, value) for seq, value in self._stored.items() if value[1] <= event.time_ns]
        if not candidates:
            self._fail("actuation has no actual stored target")
        target, _ = max(candidates)[1]
        if target.sha256 != event.target.sha256:
            self._fail("actuation did not consume the latest registered stored target")
        if target.v != 0 or target.w != 0:
            if event.time_ns - target.clock_ns > COMMAND_BRIDGE_NS:
                self._fail("nonzero target exceeded the necessary 54ms command lease bridge")
            proof = self._proofs.get(target.sequence)
            if proof is None or not proof.valid_from_ns <= event.time_ns <= proof.valid_through_ns:
                self._fail("applied target lacks continuous conditional witness")
            if proof.mode != "disk":
                self._normal_terminal_sha256 = proof.terminal_sha256
        self._last_applied = event
        if (target.v == 0 and target.w == 0 and self._zero_publication_ns is not None
                and event.time_ns >= self._zero_publication_ns and self._zero_applied_ns is None):
            self._zero_applied_ns = event.time_ns
        if event.target.v != 0 and self.disk_active and self._first_nonzero_applied is None:
            proof = self._proofs.get(event.target.sequence)
            if (proof is None or not proof.valid_from_ns <= event.time_ns <= proof.valid_through_ns):
                self._fail("applied transition lacks continuous bridge witness")
            self._first_nonzero_applied = event
        self._history.append(("actuation", event.time_ns, event.target.sha256))

    def _raw(self, sample):
        prior = self._latest
        if prior is not None and sample.frames == prior.frames and sample.source_ns > prior.source_ns:
            squares = [sum((x-y)**2 for x, y in zip(position, before))
                       for position, before in ((sample.map_xy, prior.map_xy),
                                                (sample.raw_xy, prior.raw_xy))]
            lengths = []
            for squared in squares:
                try:
                    lengths.append(math.sqrt(float(squared)))
                except OverflowError:
                    lengths.append(math.inf)
            self._chords.append(ChordDiagnostic(prior.source_ns, sample.source_ns,
                                               *squares, *lengths))
            self._map_chord_total += lengths[0]; self._raw_chord_total += lengths[1]
        if prior is None:
            if not self.release_ns <= sample.source_ns <= self.release_ns + GAP_NS:
                self._fail("first causal raw source missing after release")
        elif sample.frames != prior.frames or not 0 < sample.source_ns - prior.source_ns <= GAP_NS:
            self._fail("raw frame conflict or source gap across handoff")
        if sum(x*x for x in sample.linear_xy) > Q(3, 10)**2 or sum(x*x for x in sample.angular_xyz) > Q(6, 5)**2:
            self._fail("full planar/angular raw peak")
        applied = self._first_nonzero_applied
        old_disk_interval = self.disk_active and (applied is None or sample.source_ns <= applied.time_ns)
        if old_disk_interval:
            if sample.frames != self._anchor.source.frames or sum(x*x for x in sample.linear_xy) > Q(1, 100)**2:
                self._fail("old disk frame/rest peak before actual handoff")
            for position, anchor in ((sample.map_xy, self._anchor.source.map_xy), (sample.raw_xy, self._anchor.source.raw_xy)):
                if sum((x-y)**2 for x, y in zip(position, anchor)) > R*R:
                    self._fail("fixed anchor disk excursion")
        if prior is not None:
            speed = Q(1, 100) if old_disk_interval and prior.source_ns >= self._anchor.source.source_ns else Q(3, 10)
            travel = speed * Q(sample.source_ns - prior.source_ns, 1_000_000_000)
            for position, before in ((sample.map_xy, prior.map_xy), (sample.raw_xy, prior.raw_xy)):
                if sum((x-y)**2 for x, y in zip(position, before)) > travel*travel:
                    self._fail("raw chord peak across handoff")
        self._latest = sample
        if sum(x*x for x in sample.linear_xy) <= Q(1, 100)**2 and self._zero_publication_ns is not None and sample.source_ns >= self._zero_publication_ns + PUBLICATION_SETTLE_NS:
            self._rest = (self._rest + [sample])[-3:]
        else:
            self._rest.clear()
        if self.disk_active and applied is not None and sample.source_ns > applied.time_ns:
            proof = self._proofs[applied.target.sequence]
            if not proof.valid_from_ns <= applied.time_ns < sample.source_ns <= proof.valid_through_ns:
                self._fail("last-source handoff tail outside bridge")
            self.disk_active = False
            self._can_anchor = not self.stopped and self.fault is None
            if not self.stopped and self.fault is None:
                self.mode = "NORMAL"
            self._history.append(("retire_disk_after_causal_source", sample.source_ns, self._anchor.sha256))

    def request_stop(self):
        self.stopped = True
        if self.fault is None:
            self.mode = "STOPPING"
        self._can_anchor = False
        self._history.append(("permanent_stop", self.now_ns, self._anchor.sha256 if self._anchor else None))

    def status(self):
        return {"mode": self.mode, "fault": self.fault, "disk_active": self.disk_active,
                "anchor_sha256": self._anchor.sha256 if self._anchor else None,
                "episode_anchor_count": len(self._anchors), "checked_through_ns": self.checked_through_ns,
                "physical_ns": self.now_ns, "conditional_model_only": True,
                "continuous_plant_or_delivery_proved_here": False,
                "residual_terminal_H_D_physically_verified_here": False,
                "twenty_ms_boundary_renewal_verified_here": False,
                "cumulative_chords_are_diagnostic_only": True,
                "native_admission": False}
