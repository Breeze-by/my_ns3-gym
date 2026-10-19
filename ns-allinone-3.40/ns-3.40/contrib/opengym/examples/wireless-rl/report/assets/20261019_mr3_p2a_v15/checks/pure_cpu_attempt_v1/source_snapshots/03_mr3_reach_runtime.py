"""Local causal monitoring and received-only admission for mr3-reach-v1.

This is a necessary runtime monitor of the accepted conditional plant model,
not a proof of future continuous dynamics. Ingress and old path diagnostics
are retained. Only the real node's own sensor/driver callbacks feed a tracker;
peer modes/geometry enter exclusively through the frozen received bundle.
"""
import copy
import math
from fractions import Fraction as Q

from multi_robot_exploration.mr3_episode import timestamp_ns
from multi_robot_exploration.mr3_drive_phase import DrivePhaseClient
from multi_robot_exploration.mr3_safety_intent import (
    canonical_json, odometry_source_ns, payload_sha256, validate_calibration,
    validate_intent, validate_native_applied, validate_odometry, validate_safety,
    validate_target,
)
from multi_robot_exploration.mr3_reach_geometry import (
    Direction, disk, exact, normal, pair_certificate, transition,
)
from multi_robot_exploration.mr3_velocity_metric import physical_residual_certificate


CONTRACT = "mr3-reach-v1"
H_NS = 780_000_000
PUB_NS = 940_000_000
RAW_PERIOD_NS = 20_000_000
ACT_PERIOD_NS = 34_000_000
R = Q(39, 5000)


def raw_xy(raw):
    p = raw["pose"]["pose"]["position"]
    return exact(p["x"]), exact(p["y"])


def heading_axis(raw):
    """Projected own odometry quaternion axis, no trig/libm reconstruction.

    Its relation to physical yaw and the continuous heading-rate bound remain
    the explicit calibrated WORLD sensor/plant assumptions of this profile.
    """
    q = {k: exact(v) for k, v in raw["pose"]["pose"]["orientation"].items()}
    axis = (1-2*(q["y"]**2+q["z"]**2), 2*(q["w"]*q["z"]+q["x"]*q["y"]))
    if sum(x*x for x in axis) == 0:
        raise ValueError("undefined projected physical heading")
    return axis


def model_check(raw, calibration, signs, limit=Q(1, 100)):
    linear = raw["twist"]["twist"]["linear"]
    return physical_residual_certificate(
        linear["x"], linear["y"], calibration["coefficient_c"],
        calibration["coefficient_s"], heading_axis(raw), tuple(signs),
        residual_limit=limit)


def reach_for(state, clock_ns):
    """Reach promised by the actually delivered intent, never measured v=0."""
    safety = validate_safety(state["safety"], epoch=state["epoch"], robot=state["name"],
                             selected_odom=state["odometry"], now_ns=clock_ns)
    intent = safety["intent"]
    role = intent["lineage"]["previous_role"] if intent["role"] == "STOP" else intent["role"]
    if role in ("HOLD", "D"):
        return disk()
    raw_axis = heading_axis(state["odometry"])
    rotation = state["transform"]["transform"]["rotation"]
    q = {k: exact(v) for k, v in rotation.items()}
    tc, ts = 1-2*(q["y"]**2+q["z"]**2), 2*(q["w"]*q["z"]+q["x"]*q["y"])
    map_axis = (tc*raw_axis[0]-ts*raw_axis[1], ts*raw_axis[0]+tc*raw_axis[1])
    age = clock_ns-timestamp_ns(state["source_stamp"])
    if not 0 <= age <= 500_000_000:
        raise ValueError("future/stale geometric source")
    phi = Q(6, 5)*(Q(age, 1_000_000_000)+Q(39, 50))
    directions = tuple(Direction(tuple(sign*x for x in map_axis),
                                 tuple(sign*x for x in raw_axis), phi)
                       for sign in intent["admitted_signs"])
    return transition(directions) if role == "X" else normal(directions)


def pair_checks(own, peers, clock_ns):
    checks = {}
    left = reach_for(own, clock_ns)
    for name, peer in peers.items():
        right = reach_for(peer, clock_ns)
        ox, oy = raw_xy(own["odometry"]); px, py = raw_xy(peer["odometry"])
        checks[name] = pair_certificate(
            (exact(peer["x"])-exact(own["x"]), exact(peer["y"])-exact(own["y"])),
            (px-ox, py-oy),
            (clock_ns-timestamp_ns(own["source_stamp"]),
             clock_ns-timestamp_ns(peer["source_stamp"])), left, right,
            legacy_hard_gates_passed=True, common_world_odom_calibrated=True)
    return checks


class ReachTracker:
    """One robot, one epoch; no reset API or hidden native permission.

    20ms/34ms cadence watermarks are checked against the configured 1ms
    stepped producer. Missing expected callbacks return not-ready and cannot
    advance physics; a contradictory source/model latches a permanent fault.
    The worker still owns actual per-quantum publication/storage/physics proof.
    """
    def __init__(self, epoch, robot):
        self.epoch, self.robot = epoch, robot
        self.role, self.release_ns, self.stopped, self.fault = "HOLD", None, False, None
        self.anchor, self.anchor_sequence, self.transition_sequence = None, None, None
        self.signs = ()
        self.ingress, self.events, self.processed = [], [], set()
        self.calibrations, self.raw_seen, self.applied_seen = {}, {}, {}
        self.published, self.intents = {}, {}
        self.storage = DrivePhaseClient(epoch)
        self.intent_number = 0
        self.current_intent = self.latest_raw = self.last_applied = self.causal_applied = None
        self.last_clock = None
        self.zero_publication = self.zero_storage = None
        self.rest, self.anchors, self.chords = [], [], []
        self.cumulative_path_m = 0.
        self.first_takeover = None
        self.actual_normal = False
        self.backup_from = self.backup_path_origin = self.terminal_anchor = None
        self.last_motion_clock = None
        self.previous_stop_role = None
        self.previous_stop_sequence = None

    def fail(self, error):
        self.fault = self.fault or str(error)
        raise ValueError(self.fault)

    def _retain(self, kind, value):
        value = copy.deepcopy(value)
        self.ingress.append((kind, value))
        return value

    def receive_raw(self, value, sequence):
        raw = self._retain("raw", value)
        validate_odometry(raw)
        source = odometry_source_ns(raw)
        if type(sequence) is not int or sequence <= 0:
            self.fail("invalid raw ingress sequence")
        old = self.raw_seen.get(source)
        if old is not None:
            if canonical_json(old) != canonical_json(raw):
                self.fail("conflicting same-source raw")
            return
        if self.raw_seen and source < max(self.raw_seen):
            self.fail("raw source regressed")
        self.raw_seen[source] = raw
        self.events.append((source, 0, (source, sequence, raw)))

    def receive_calibration(self, value):
        value = self._retain("calibration", value)
        value = validate_calibration(value, epoch=self.epoch, robot=self.robot)
        source = value["source_clock_ns"]
        old = self.calibrations.get(source)
        if old is not None and canonical_json(old) != canonical_json(value):
            self.fail("conflicting calibration identity")
        if old is None and self.calibrations:
            prior = self.calibrations[max(self.calibrations)]
            if (source <= prior["source_clock_ns"]
                    or value["publication_sequence"] != prior["publication_sequence"]+1):
                self.fail("calibration publication stream gap/regression")
        self.calibrations[source] = value

    def receive_storage(self, value):
        value = self._retain("storage", value)
        self.storage.receive(value)
        target = self.published.get(value["decision_sequence"])
        if (target is None or value["clock_ns"] != target["clock_ns"]
                or value["source_clock_ns"] != target["clock_ns"]
                or any(value[k] != target[k] for k in ("linear_x", "angular_z"))):
            self.fail("storage substituted an unpublished target")
        if target["linear_x"] == target["angular_z"] == 0:
            if self.zero_storage is None:
                self.zero_storage = max(value["clock_ns"], self.release_ns or 0)
        else:
            self.zero_storage = None

    def receive_applied(self, value):
        value = self._retain("applied", value)
        value = validate_native_applied(value, epoch=self.epoch, robot=self.robot)
        seq = value["actuation_sequence"]
        old = self.applied_seen.get(seq)
        if old is not None:
            if canonical_json(old) != canonical_json(value):
                self.fail("conflicting applied identity")
            return
        if self.applied_seen:
            prior = self.applied_seen[max(self.applied_seen)]
            if (seq != prior["actuation_sequence"]+1
                    or value["source_clock_ns"]-prior["source_clock_ns"] != ACT_PERIOD_NS
                    or value["dt_ns"] != ACT_PERIOD_NS):
                self.fail("native applied stream gap/cadence changed")
        self.applied_seen[seq] = value
        self.events.append((value["source_clock_ns"], 1, (seq, value)))

    def synchronize(self, clock_ns):
        if self.fault:
            raise ValueError(self.fault)
        if (type(clock_ns) is not int or clock_ns < 0
                or self.last_clock is not None and clock_ns < self.last_clock):
            self.fail("physical clock regressed")
        for entry in sorted(self.events, key=lambda e: e[:2]):
            source, kind, item = entry
            key = (source, kind)
            if key in self.processed or source > clock_ns:
                continue
            if kind == 0:
                _, sequence, raw = item
                calibration = self.calibrations.get(source)
                if calibration is None:
                    return False
                if canonical_json(calibration["odometry"]) != canonical_json(raw):
                    self.fail("calibration does not bind exact raw odometry")
                self._raw(source, sequence, raw, calibration)
            else:
                self._applied(item[1])
            self.processed.add(key)
            self.events.remove(entry)  # only after success; bad source/tail stay owned
        if self.latest_raw is None:
            return False
        # A source exactly one period old means the next publication must be
        # received before declaring the current frontier complete.
        if not 0 <= clock_ns-self.latest_raw[0] < RAW_PERIOD_NS:
            return False
        if self.last_applied is None:
            first = min((p["clock_ns"] for p in self.published.values()), default=clock_ns)
            if clock_ns-first >= ACT_PERIOD_NS:
                return False
        elif not 0 <= clock_ns-self.last_applied["source_clock_ns"] < ACT_PERIOD_NS:
            return False
        self.last_clock = clock_ns
        return True

    def _applied(self, value):
        target = value["target"]
        sequence = target["decision_sequence"]
        if (sequence not in self.published
                or canonical_json(target) != canonical_json(self.published[sequence])):
            self.fail("actual application has no registered publication")
        stored = self.storage.pending[self.robot].get(sequence)
        if stored is None or stored["cmd_seq"] != value["cmd_seq"]:
            self.fail("actual application has no exact real storage")
        possible = [p for p in self.storage.pending[self.robot].values()
                    if p["clock_ns"] <= value["source_clock_ns"]]
        if not possible or max(possible, key=lambda p: p["cmd_seq"])["cmd_seq"] != value["cmd_seq"]:
            self.fail("actual application is not the latest stored target")
        if target["linear_x"] != 0 or target["angular_z"] != 0:
            if value["source_clock_ns"]-target["clock_ns"] > RAW_PERIOD_NS:
                self.fail("nonzero target missed the 20ms renewal boundary")
        if target["linear_x"] != 0 and self.role in ("X", "N", "STOP"):
            sign = 1 if target["linear_x"] > 0 else -1
            if sign not in self.signs:
                self.fail("actual translation escaped preannounced signs")
            if self.first_takeover is None:
                self.first_takeover = copy.deepcopy(value)
        self.last_applied = value

    def _raw(self, source, sequence, raw, calibration):
        prior = self.latest_raw
        if prior is not None:
            if (source-prior[0] > 100_000_000 or raw["header"]["frame_id"] != prior[2]["header"]["frame_id"]
                    or raw["child_frame_id"] != prior[2]["child_frame_id"]):
                self.fail("raw source gap/frame changed")
            d2 = sum((a-b)**2 for a, b in zip(raw_xy(raw), raw_xy(prior[2])))
            chord = math.sqrt(float(d2))
            self.chords.append((prior[0], source, str(d2), chord))
            self.cumulative_path_m += chord
        protected = self.release_ns is not None and source >= self.release_ns
        old_disk = self.anchor is not None and not self.actual_normal and (
            self.first_takeover is None or source <= self.first_takeover["source_clock_ns"])
        if protected:
            if not model_check(raw, calibration, (), Q(3, 10))["metric_necessary"]:
                self.fail("physical planar speed bound exceeded")
            angular = raw["twist"]["twist"]["angular"]
            if sum(exact(v)**2 for v in angular.values()) > Q(6, 5)**2:
                self.fail("physical angular speed bound exceeded")
            if prior is not None and prior[0] >= self.release_ns:
                before = prior[2]["twist"]["twist"]["angular"]
                if sum((exact(angular[k])-exact(before[k]))**2 for k in angular) > (
                        7*Q(source-prior[0],1_000_000_000))**2:
                    self.fail("physical sampled angular acceleration exceeded")
            signs = () if old_disk else self.signs
            if not model_check(raw, calibration, signs)["metric_necessary"]:
                self.fail("physical rest or complete signed residual bound exceeded")
            if old_disk and sum((a-b)**2 for a,b in zip(raw_xy(raw),raw_xy(self.anchor["odometry"]))) > R*R:
                self.fail("fixed disk radius exceeded")
            if prior is not None:
                speed = Q(1,100) if old_disk and prior[0] >= self.anchor["source_clock_ns"] else Q(3,10)
                if d2 > (speed*Q(source-prior[0],1_000_000_000))**2:
                    self.fail("physical raw chord speed exceeded")
        self.latest_raw = (source, sequence, raw)
        if self.last_applied and self.last_applied["source_clock_ns"] < source:
            self.causal_applied = copy.deepcopy(self.last_applied)
        if self.first_takeover and source > self.first_takeover["source_clock_ns"]:
            self.actual_normal = True
            if not self.stopped:
                self.role = "N"
        rest = model_check(raw, calibration, ())["metric_necessary"]
        if (self.zero_publication is not None and source >= self.zero_publication+PUB_NS and rest):
            self.rest = (self.rest+[(source, raw)])[-3:]
        else:
            self.rest.clear()
        if protected and self.backup_from is not None:
            # This is a lower bound from all raw chords wholly inside the
            # global stop window. Source gaps and continuous path still need
            # the independent physical audit; never call this an upper bound.
            path_lower = Q(0)
            for start, end, squared, _ in self.chords:
                if start >= self.backup_from and end <= source:
                    d = Q(squared)
                    path_lower += Q(math.isqrt((d.numerator*d.denominator) << 128),
                                    d.denominator << 64)
            if path_lower > Q(18,125):
                self.fail("full-body sampled stop path lower bound exceeded D")
            if self.terminal_anchor is None and self.last_applied and all(
                    self.last_applied["target"][k] == 0 for k in ("linear_x","angular_z")) and rest:
                self.terminal_anchor = {"source_clock_ns":source,"odometry":copy.deepcopy(raw)}
                if source > self.backup_from+H_NS:
                    self.fail("body terminal source missed global H")
            if self.terminal_anchor is None and source > self.backup_from+H_NS:
                self.fail("body did not enter terminal disk within global H")
            if self.terminal_anchor is not None and sum((a-b)**2 for a,b in zip(
                    raw_xy(raw),raw_xy(self.terminal_anchor["odometry"]))) > R*R:
                self.fail("fixed terminal disk radius exceeded")

    def release(self, clock_ns):
        if self.release_ns is not None or self.latest_raw is None or self.latest_raw[0] > clock_ns:
            self.fail("invalid or repeated reach release")
        self.release_ns = clock_ns
        self.anchor = {"source_clock_ns": self.latest_raw[0], "odometry":copy.deepcopy(self.latest_raw[2])}
        self.anchors.append(copy.deepcopy(self.anchor))
        self.zero_publication = max(clock_ns, self.zero_publication or clock_ns)
        self.zero_storage = max(clock_ns, self.zero_storage or clock_ns)
        self.rest.clear()

    def qualified(self, clock_ns):
        return (not self.stopped and self.release_ns is not None
                and self.role in ("HOLD","N")
                and self.zero_publication is not None and clock_ns-self.zero_publication >= PUB_NS
                and self.zero_storage is not None and clock_ns-self.zero_storage >= H_NS
                and self.causal_applied is not None
                and self.causal_applied["target"]["linear_x"] == 0
                and self.causal_applied["target"]["angular_z"] == 0
                and len(self.rest)==3
                and all(0 <= clock_ns-s <= 100_000_000 for s,_ in self.rest)
                and (self.role=="HOLD" or self.actual_normal and self.terminal_anchor is not None))

    def stop(self):
        if not self.stopped:
            self.previous_stop_role = self.role
            self.previous_stop_sequence = self.intent_number
            self.stopped = True
            self.role = "STOP"

    def decide(self, request, own, peers, clock_ns, delivered_self):
        result={"allow":False,"reason":"reach_hold","output":[0.,0.],"minimum_margin_m":None}
        if self.fault:
            raise ValueError(self.fault)
        if self.stopped or self.release_ns is None:
            return result
        if self.qualified(clock_ns):
            self.role="D";self.signs=();self.actual_normal=False;self.first_takeover=None
            self.anchor={"source_clock_ns":self.latest_raw[0],"odometry":copy.deepcopy(self.latest_raw[2])}
            self.anchors.append(copy.deepcopy(self.anchor));self.anchor_sequence=self.intent_number+1
            self.transition_sequence=None;self.backup_from=self.terminal_anchor=None
            return result
        received=validate_intent(delivered_self,epoch=self.epoch,robot=self.robot,now_ns=clock_ns)
        known=self.intents.get(received["intent_sequence"])
        if known is None or canonical_json(known)!=canonical_json(received):
            self.fail("delivered self intent is not an actual own publication")
        if (not isinstance(request,(tuple,list)) or len(request)!=2
                or any(type(v) not in (int,float) or not math.isfinite(v) for v in request)):
            result["reason"]="unsupported_command";return result
        v,w=request
        canonical=[]
        for value,limit in ((v,.20),(w,.8)):
            if abs(value)>limit:
                if abs(value)!=math.nextafter(limit,math.inf):
                    result["reason"]="unsupported_command";return result
                value=math.copysign(limit,value)
            canonical.append(float(value))
        v,w=canonical
        if self.role=="D" and v!=0:
            self.role="X";self.signs=(1 if v>0 else -1,)
            self.transition_sequence=self.intent_number+1
            result["reason"]="announce_transition_zero";return result
        if self.role=="HOLD" or received["role"] not in (self.role,"X" if self.role=="N" else self.role):
            return result
        if self.role in ("X","N") and v!=0 and (1 if v>0 else -1) not in self.signs:
            result["reason"]="unannounced_direction";return result
        checks=pair_checks(own,peers,clock_ns)
        result["reach_pair_checks"]=checks
        if not all(row["geometric_necessary"] for row in checks.values()):
            result["reason"]="reach_pair_envelope";return result
        result.update(allow=True,reason="reach_clear",output=[v,w])
        return result

    def publish_target(self,target):
        target=validate_target(target,epoch=self.epoch,robot=self.robot)
        self._retain("publication",target)
        if self.published and target["decision_sequence"]<=max(self.published):
            self.fail("publication sequence regressed")
        if self.stopped and (target["linear_x"]!=0 or target["angular_z"]!=0):
            self.fail("permanent STOP cannot publish motion")
        if target["linear_x"]==target["angular_z"]==0:
            if self.zero_publication is None:self.zero_publication=max(target["clock_ns"],self.release_ns or 0)
            if self.actual_normal and self.backup_from is None:
                self.backup_from=self.last_motion_clock
                self.terminal_anchor=None
        else:
            self.zero_publication=None;self.rest.clear()
            self.last_motion_clock=target["clock_ns"]
            self.backup_from=self.terminal_anchor=None
        self.published[target["decision_sequence"]]=target
        return self.make_intent(target["clock_ns"],target)

    def make_intent(self,clock_ns,target=None):
        self.intent_number+=1
        if self.role=="HOLD":lineage={"release_clock_ns":self.release_ns}
        elif self.role=="D":lineage={"anchor_intent_sequence":self.anchor_sequence}
        elif self.role in ("X","N"):
            lineage={"anchor_intent_sequence":self.anchor_sequence,
                     "transition_intent_sequence":self.transition_sequence}
            if self.role=="N":
                if self.causal_applied is None:self.fail("N has no actual application and later raw")
                lineage.update(actuation_sequence=self.causal_applied["actuation_sequence"],
                    actuation_source_clock_ns=self.causal_applied["source_clock_ns"],
                    causal_source_clock_ns=self.latest_raw[0],cmd_seq=self.causal_applied["cmd_seq"])
        else:lineage={"previous_intent_sequence":self.previous_stop_sequence,
                      "previous_role":self.previous_stop_role}
        intent={"schema":"mr3-safety-intent-v1","epoch":self.epoch,"robot":self.robot,
            "intent_sequence":self.intent_number,"source_clock_ns":clock_ns,"role":self.role,
            "anchor":copy.deepcopy(self.anchor),"admitted_signs":list(self.signs),
            "lineage":lineage,"target":target}
        intent=validate_intent(intent,epoch=self.epoch,robot=self.robot,now_ns=clock_ns)
        self.current_intent=intent;self.intents[self.intent_number]=copy.deepcopy(intent)
        self._retain("intent_publication",intent)
        return intent

    def status(self):
        return {"role":self.role,"fault":self.fault,"permanent_stop":self.stopped,
                "anchor_history":copy.deepcopy(self.anchors),"raw_samples":len(self.raw_seen),
                "applied_samples":len(self.applied_seen),"cumulative_path_diagnostic_m":self.cumulative_path_m,
                "backup_from_clock_ns":self.backup_from,"terminal_anchor":copy.deepcopy(self.terminal_anchor),
                "continuous_physical_model_proved":False}
