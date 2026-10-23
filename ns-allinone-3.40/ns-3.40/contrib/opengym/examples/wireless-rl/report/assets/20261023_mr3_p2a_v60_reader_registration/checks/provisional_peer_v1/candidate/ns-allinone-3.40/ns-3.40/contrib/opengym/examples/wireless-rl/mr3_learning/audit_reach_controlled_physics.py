"""V2 release/physics dispatch retaining every immutable causal predicate.

The literal source projection admits the additional, independently checked
``safety`` input; no native value is removed or changed. Readiness additionally
binds the complete v2 table to actual state, peer and guard subscription facts.
"""

from pathlib import Path

from . import audit_reach_information as information
from .reach_audit_projection import project_module

SOURCE_SHA256 = "3080521c368c5dc9b47c74337ea200945c80c125231146ac39cb90a71080dc3e"
CONTROL_PROTOCOL = "mr3-controlled-execution-phase-v2"
CONTROLLED_HANDSHAKE = "paused-controlled-state-peer-guard-storage-v2"
SAFETY = ("safety_contract", "intent_refs", "safety_table_sha256")
require, equal, fields = information.require, information.equal, information.fields


def _one(rows, predicate, reason):
    values = [row for row in rows if predicate(row)]
    require(len(values) == 1, reason)
    return values[0]


def verify_release_safety(metadata, reset, phases, state_rows, peer_rows, motion_rows, base):
    """Additional necessary v2 checks on complete original release prefixes.

    ``phases`` are the original strict worker request/callback/consumption
    tuples. The independent information and peer/control replays remain
    mandatory: this release check supplies no replacement PASS for them.
    """
    epoch = metadata["epoch"]
    release = information.integer(reset["info"]["release_time_ns"], "release")
    require(metadata.get("safety_contract") == information.CONTRACT
            and metadata.get("execution_phase_protocol") == CONTROL_PROTOCOL
            and metadata.get("reset_handshake") == CONTROLLED_HANDSHAKE,
            "readiness missing explicit reach profile")
    state_req, state, _, _, _ = phases["state"]
    peer_req, peer, _, _, _ = phases["peer"]
    guard_req, guard, _, _, consumed = phases["motion"]
    common = {"schema", "epoch", "request_id", "operation", "target_time_ns", "clock_ns", "ok"}
    fields(state_req, ("schema", "epoch", "request_id", "operation", "target_time_ns", "expected_intents"),
           "release state request")
    fields(peer_req, ("schema", "epoch", "request_id", "operation", "target_time_ns", "state_commit"),
           "release peer request")
    fields(guard_req, ("schema", "epoch", "request_id", "operation", "target_time_ns", "state_commit", "peer_commit"),
           "release motion request")
    fields(state, common | set(SAFETY) | {"scope", "state_sequence", "bundle_sha256", "robots",
           "side_publish_started_wall_monotonic_ns", "bundle_publish_started_wall_monotonic_ns",
           "bundle_publish_completed_wall_monotonic_ns"}, "release state ACK")
    fields(peer, common | set(SAFETY) | {"scope", "commit_sequence", "state_commit", "state_sequence",
           "bundle_sha256", "inputs", "publications", "obstacle_publication_sha256"}, "release peer ACK")
    fields(guard, common | set(SAFETY) | {"status"}, "release motion ACK")
    for component, request, ack in (("state", state_req, state), ("peer", peer_req, peer),
                                     ("motion", guard_req, guard)):
        require(request["schema"] == f"mr3-{component}-{'control' if component == 'motion' else 'phase'}-request-v2"
                and ack["schema"] == f"mr3-{component}-{'control' if component == 'motion' else 'phase'}-ack-v2"
                and request["epoch"] == ack["epoch"] == epoch
                and request["operation"] == ack["operation"] == "commit"
                and request["target_time_ns"] == ack["target_time_ns"] == ack["clock_ns"] == release
                and ack["ok"] is True and ack["safety_contract"] == information.CONTRACT,
                "release v2 request/ACK identity")
    equal(peer_req["state_commit"], state, "release peer request changed complete state ACK")
    equal(peer["state_commit"], state, "release peer ACK changed complete state ACK")
    equal(guard_req["state_commit"], state, "release motion request changed complete state ACK")
    equal(guard_req["peer_commit"], peer, "release motion request changed complete peer ACK")
    publication = _one(state_rows, lambda r: r.get("kind") == "state_publish"
                       and r["payload"].get("message_sha256") == state["bundle_sha256"],
                       "release safety lacks unique actual state publication")
    payload, bundle = publication["payload"], publication["payload"]["message"]
    evidence = information.bundle_evidence(bundle, epoch, base, release)
    require(information.sha(bundle) == state["bundle_sha256"] and publication["clock_ns"] == release,
            "release complete bundle identity")
    for value in (state, peer):
        for key in SAFETY:
            equal(value[key], evidence[key], "release ACK changed complete safety evidence")
    information.validate_refs(state_req["expected_intents"])
    equal(state_req["expected_intents"], evidence["intent_refs"], "release expected intents were not selected")
    fields(state["robots"], information.ROBOTS, "release state robot refs")
    for row in bundle["robots"]:
        reference = state["robots"][row["name"]]
        fields(reference, ("sequence", "version", "source_stamp", "source_ns", "odom_source_ns",
               "tf_source_ns", "odom_topic", "tf_topic", "odom_sha256", "tf_sha256", "safety_sha256"),
               "release complete state robot reference")
        require(reference["safety_sha256"] == information.sha(row["safety"]),
                "release per-robot safety digest differs")
    fields(peer["inputs"], {"bundle", "safety", *[f"{kind}:{name}" for kind in ("odom", "tf")
           for name in information.ROBOTS]}, "release complete peer inputs")
    equal(peer["inputs"]["safety"], evidence, "release peer safety differs from full bundle")
    bundle_ref = peer["inputs"]["bundle"]
    fields(bundle_ref, ("state_sequence", "message_sha256", "received_wall_monotonic_ns", "publisher_identity"),
           "release peer bundle reference")
    received = _one(peer_rows, lambda r: r.get("kind") == "received_state_bundle"
                    and r["payload"].get("received_wall_monotonic_ns") == bundle_ref["received_wall_monotonic_ns"],
                    "release missing actual peer bundle callback")
    equal(received["payload"]["message"], bundle, "release peer callback changed complete bundle")
    equal(received["payload"]["publisher_identity"], bundle_ref["publisher_identity"],
          "release peer publisher identity differs from actual callback")
    information.graph(bundle_ref["publisher_identity"], "/mr3/received/states", "mr3_information", "/")
    status = reset["info"]["initial_motion_status"]
    from .audit_reach_peer_control import validate_status
    require(validate_status(status, epoch) is False, "release cannot use STOP status")
    equal(guard["status"], status, "release motion ACK changed actual initial status")
    for key in SAFETY:
        equal(guard[key], status[key], "release motion ACK changed new owner status metadata")
    require(status["safety_table_sha256"] == evidence["safety_table_sha256"],
            "release guard did not consume complete frozen safety table")
    # Guard owner refs describe newly published intents, whereas state/peer refs
    # describe the old table actually consumed. Never substitute either for the other.
    output = _one(motion_rows, lambda r: r.get("kind") == "output_completed"
                  and information.canonical(r["payload"].get("status")) == information.canonical(status),
                  "release lacks actual guard output completion")
    require(output["wall_monotonic_ns"] <= consumed, "release guard completion follows worker consumption")
    for name, ref in status["intent_refs"].items():
        owner = _one(motion_rows, lambda r: r.get("kind") == "reach_intent_publish"
                     and r["payload"].get("robot") == name
                     and r["payload"].get("payload_sha256") == ref["payload_sha256"],
                     "release owner refs lack actual intent publication")
        value, intent = owner["payload"], owner["payload"]["intent"]
        information.validate_intent(intent, epoch, name, base, release)
        require(intent["intent_sequence"] == ref["intent_sequence"]
                and information.sha(intent) == ref["payload_sha256"]
                and value["publish_started_wall_monotonic_ns"]
                <= value["publish_completed_wall_monotonic_ns"] <= owner["wall_monotonic_ns"]
                <= output["payload"]["publish_started_wall_monotonic_ns"],
                "release owner intent identity/publication order")
    callbacks = [r for r in motion_rows if r.get("kind") == "reach_state_ingress"
                 and information.canonical(r["payload"].get("message")) == information.canonical(bundle)
                 and payload["publish_started_wall_monotonic_ns"] <= r["wall_monotonic_ns"]
                 <= output["payload"]["publish_started_wall_monotonic_ns"]]
    require(callbacks, "release guard lacks actual whole-bundle subscription")
    for callback in callbacks:
        value = callback["payload"]
        equal(base.parse(value["raw_json"]), bundle, "release guard raw JSON differs")
        information.graph(value["publisher_identity"], "/mr3/received/states", "mr3_information", "/")
    delivered = [r for r in motion_rows if r.get("kind") == "received_states"
                 and information.canonical(r.get("payload")) == information.canonical(bundle)
                 and any(c["wall_monotonic_ns"] <= r["wall_monotonic_ns"] for c in callbacks)
                 and r["wall_monotonic_ns"] <= output["payload"]["publish_started_wall_monotonic_ns"]]
    require(delivered, "release lacks delivered complete guard state")
    return {"safety_contract": information.CONTRACT, "state_bundle_sha256": information.sha(bundle),
            **evidence, "new_owner_intent_refs": status["intent_refs"],
            "scope": "complete v2 release conjunction; independent information/control/runtime roles also required"}


def load_impl(*, plan_path=None):
    from .audit_reach_peer_control import audit_episode
    module, proof = project_module("audit_controlled_physics.py", SOURCE_SHA256, (
        ("mr3-controlled-execution-phase-v1", CONTROL_PROTOCOL, 1),
        ("paused-controlled-state-peer-guard-storage-v1", CONTROLLED_HANDSHAKE, 1),
        ("mr3-motion-control-ack-v1", "mr3-motion-control-ack-v2", 1),
        ('f"mr3-{component}-phase-ack-v1"', 'f"mr3-{component}-phase-ack-v2"', 1),
        ('set(inputs) == {"bundle", *[', 'set(inputs) == {"bundle", "safety", *[', 1),
    ))
    # The complete v2 replay includes strict safety-table/intent checks. The
    # original bootstrap/readiness mathematics use its unchanged replay fields.
    module.audit_motion = lambda directory: audit_episode(directory, plan_path=plan_path)
    original_readiness = module.controlled_readiness

    def readiness(directory, metadata, transitions, adapter_rows, epoch, motion):
        directory = Path(directory)
        result = original_readiness(directory, metadata, transitions, adapter_rows, epoch, motion)
        require(motion.get("schema") == "mr3-reach-peer-control-fifo-review-v1"
                and motion.get("safety_contract") == information.CONTRACT,
                "readiness requires complete new-profile peer/control replay")
        reset = module._one(transitions, lambda r: r.get("kind") == "reset", "unique reach reset")
        release = reset["info"]["release_time_ns"]
        control = module._rows(directory / "control_phase_worker.jsonl")
        phases = {name: module._phase_receipt(control, name, "commit", release, epoch)
                  for name in ("state", "peer", "motion")}
        end_wall = phases["motion"][4]
        state_rows = module._prefix(directory, "information_states.jsonl", end_wall, result["artifact_proof"])
        peer_rows = module._prefix(directory, "peer_phase.jsonl", end_wall, result["artifact_proof"])
        motion_rows = module._prefix(directory, "motion_safety.jsonl", end_wall, result["artifact_proof"])
        host, _ = information.load_implementation()
        result["reach_release"] = verify_release_safety(metadata, reset, phases, state_rows, peer_rows, motion_rows, host.BASE)
        module.verify_motion_artifacts({"artifact_proof": result["artifact_proof"]})
        return result

    module.controlled_readiness = readiness
    return module, proof


def controlled_bootstrap(*args, **kwargs):
    return load_impl()[0].controlled_bootstrap(*args, **kwargs)


def verify_motion_artifacts(*args, **kwargs):
    return load_impl()[0].verify_motion_artifacts(*args, **kwargs)


def dispatch_controlled_physics(*args, plan_path=None, **kwargs):
    return load_impl(plan_path=plan_path)[0].dispatch_controlled_physics(*args, **kwargs)


def dispatch_controlled_readiness(*args, plan_path=None, **kwargs):
    return load_impl(plan_path=plan_path)[0].dispatch_controlled_readiness(*args, **kwargs)
