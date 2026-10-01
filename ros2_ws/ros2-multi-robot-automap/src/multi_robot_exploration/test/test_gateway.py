import json
from pathlib import Path
from types import SimpleNamespace

from multi_robot_exploration.bypass_audit import source_violations
from geometry_msgs.msg import TransformStamped
from tf2_msgs.msg import TFMessage

from multi_robot_exploration.ideal_gateway import (
    IdealGateway, Route, envelope_is_valid,
)
from multi_robot_exploration.navigation_gateway import battery_mode_allows_navigation
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


def test_returning_battery_mode_allows_only_the_return_navigation_command():
    assert battery_mode_allows_navigation("ACTIVE")
    assert battery_mode_allows_navigation("RETURNING")
    assert not battery_mode_allows_navigation("CHARGING")
    assert not battery_mode_allows_navigation("FAILED")


def make_tf(parent, child, stamp):
    transform = TransformStamped()
    transform.header.frame_id = parent
    transform.child_frame_id = child
    transform.header.stamp.sec = stamp
    transform.transform.rotation.w = 1.0
    return TFMessage(transforms=[transform])


def sender():
    emitted = []
    fake = SimpleNamespace(
        clock=10.0, last_generated_at={}, source_stamps={}, task_phase="RALLY",
        candidate_publishers={"uplink": SimpleNamespace(publish=emitted.append)},
        next_sequence=lambda route: len(emitted) + 1,
        publish_event=lambda *args: None,
    )
    fake.now_sec = lambda: fake.clock
    route = Route(
        "frame_state", "tb1", "headquarters", "/tb1/tf",
        "/gateway/received/tb1/tf", TFMessage, 2.0, min_interval_sec=0.5,
    )
    return fake, route, emitted


def test_unrelated_tf_does_not_consume_frame_state_throttle():
    fake, route, emitted = sender()
    for i in range(10, 15):
        fake.clock = float(i)
        IdealGateway.publish_candidate(
            fake, route, "uplink", make_tf("odom", "base_footprint", i)
        )
        fake.clock = i + 0.01
        IdealGateway.publish_candidate(
            fake, route, "uplink", make_tf("map", "odom", i)
        )
    assert len(emitted) == 5


def test_duplicate_state_does_not_suppress_new_state():
    fake, route, emitted = sender()
    IdealGateway.publish_candidate(fake, route, "uplink", make_tf("map", "odom", 10))
    fake.clock = 11.0
    IdealGateway.publish_candidate(fake, route, "uplink", make_tf("map", "odom", 10))
    fake.clock = 11.01
    IdealGateway.publish_candidate(fake, route, "uplink", make_tf("map", "odom", 11))
    assert len(emitted) == 2


def test_eligible_updates_still_obey_rate_limit_and_preserve_source_time():
    fake, route, emitted = sender()
    IdealGateway.publish_candidate(fake, route, "uplink", make_tf("map", "odom", 9))
    fake.clock = 10.2
    IdealGateway.publish_candidate(fake, route, "uplink", make_tf("map", "odom", 10))
    assert len(emitted) == 1
    fake.clock = 10.6
    IdealGateway.publish_candidate(fake, route, "uplink", make_tf("map", "odom", 10))
    assert len(emitted) == 2
    assert emitted[-1].generation_time.sec == 10
    assert emitted[-1].generation_time.nanosec == 0
    assert emitted[-1].ttl_sec == 2.0
