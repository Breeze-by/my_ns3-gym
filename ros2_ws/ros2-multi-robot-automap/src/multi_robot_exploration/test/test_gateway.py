import json
from pathlib import Path
from types import SimpleNamespace

from multi_robot_exploration.bypass_audit import source_violations
from multi_robot_exploration.ideal_gateway import envelope_is_valid
from multi_robot_interfaces.msg import GatewayEnvelope


def test_envelope_validation_rejects_bad_length_expiry_and_stale_sequence():
    envelope = SimpleNamespace(
        payload=b"abc",
        payload_length=3,
        generation_time=SimpleNamespace(sec=10, nanosec=0),
        ttl_sec=2.0,
        sequence=2,
    )
    assert envelope_is_valid(envelope, 11.0, 1) == (True, "")
    envelope.payload_length = 2
    assert envelope_is_valid(envelope, 11.0, 1)[1] == (
        "payload_length_mismatch"
    )
    envelope.payload_length = 3
    assert envelope_is_valid(envelope, 13.0, 1)[1] == "expired"
    assert envelope_is_valid(envelope, 11.0, 2)[1] == "stale_sequence"


def test_forbidden_bypass_manifest_matches_source_tree():
    package_root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        (package_root / "config" / "p3a_forbidden_bypasses.json").read_text(
            encoding="utf-8"
        )
    )
    assert source_violations(manifest, package_root) == []


def test_gateway_envelope_exposes_protocol_metadata():
    fields = GatewayEnvelope.get_fields_and_field_types()
    assert {
        "message_type",
        "sender",
        "recipient",
        "sequence",
        "correlation_id",
        "generation_time",
        "task_phase",
        "payload_length",
        "encoding",
        "ttl_sec",
        "ack_sequence",
        "payload",
    } <= fields.keys()
