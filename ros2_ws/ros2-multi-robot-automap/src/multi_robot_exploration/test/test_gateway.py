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


def test_network_commands_cannot_preempt_robot_local_safety_return():
    assert battery_mode_allows_navigation("ACTIVE")
    assert not battery_mode_allows_navigation("RETURNING")
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
        clock=10.0, frame_stamp_offset_sec=0.0, last_generated_at={}, source_stamps={}, task_phase="RALLY",
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


def test_blackout_epoch_excludes_cold_start_and_is_not_reset_by_phase_updates():
    from multi_robot_exploration.fault_model import DeterministicFaultTransport, FaultConfig
    events = []
    transport = DeterministicFaultTransport(FaultConfig())
    gateway = SimpleNamespace(task_phase="EXPLORE", fault_epoch=None,
                              fault_blackout_intervals=((20., 30.),), now_sec=lambda: 150.,
                              transport_by_direction={"uplink": transport}, _record=events.append)
    IdealGateway.task_state_callback(gateway, SimpleNamespace(data="EXPLORE"))
    assert transport.config.blackout_intervals == ((170., 180.),)
    gateway.now_sec = lambda: 200.
    IdealGateway.task_state_callback(gateway, SimpleNamespace(data="EXPLORE"))
    assert transport.config.blackout_intervals == ((170., 180.),)
    assert len(events) == 1


def test_slam_tf_validity_offset_does_not_renew_scan_age_or_mutate_local_tf():
    from rclpy.serialization import deserialize_message
    fake,route,emitted=sender()
    fake.frame_stamp_offset_sec=.2
    tf=make_tf('map','odom',10)
    IdealGateway.publish_candidate(fake,route,'uplink',tf)
    packet=emitted[0]
    assert packet.generation_time.sec==9 and packet.generation_time.nanosec==800000000
    received=deserialize_message(bytes(packet.payload),TFMessage)
    assert received.transforms[0].header.stamp.sec==9
    assert received.transforms[0].header.stamp.nanosec==800000000
    assert tf.transforms[0].header.stamp.sec==10
    assert tf.transforms[0].header.stamp.nanosec==0


def test_charge_request_route_is_reliable_expiring_and_robot_specific():
    from multi_robot_exploration.fault_model import CHARGE_REQUEST_TTL_SEC, RELIABLE_TYPES

    routes = [r for r in IdealGateway._routes(SimpleNamespace(robot_count=2))
              if r.message_type == "charge_request"]
    assert len(routes) == 2 and "charge_request" in RELIABLE_TYPES
    for i, route in enumerate(routes, 1):
        assert route.sender == "headquarters" and route.recipient == f"tb{i}"
        assert route.source_topic == f"/gateway/request/tb{i}/charge"
        assert route.destination_topic == f"/tb{i}/gateway/charge_request"
        assert route.ttl_sec == CHARGE_REQUEST_TTL_SEC and not route.transient


def test_charge_request_decode_deduplicates_and_does_not_ack_expired_command():
    from rclpy.serialization import serialize_message
    from std_msgs.msg import String

    route = next(r for r in IdealGateway._routes(SimpleNamespace(robot_count=1))
                 if r.message_type == "charge_request")
    messages, acks, events = [], [], []
    key = (route.message_type, route.sender, route.recipient)
    node = SimpleNamespace(
        clock=11.0, latest_sequences={}, route_by_key={key: route},
        get_logger=lambda: SimpleNamespace(error=lambda *args: None),
        destination_publishers={key: SimpleNamespace(publish=messages.append)},
        publish_ack=lambda *args: acks.append(args), publish_event=lambda *args: events.append(args),
    )
    node.now_sec = lambda: node.clock
    envelope = GatewayEnvelope()
    envelope.message_type, envelope.sender, envelope.recipient = key
    envelope.sequence, envelope.generation_time.sec, envelope.ttl_sec = 1, 10, 10.0
    envelope.encoding = "cdr"
    envelope.payload = list(serialize_message(String(data=json.dumps({
        "robot": "tb1", "stamp_sec": 10.0, "required_energy": 40.0, "task_phase": "RALLY",
    }))))
    envelope.payload_length = len(envelope.payload)
    IdealGateway.receive_envelope(node, envelope)
    IdealGateway.receive_envelope(node, envelope)
    assert len(messages) == 1 and len(acks) == 2
    event = json.loads(messages[0].data)
    assert event["stamp_sec"] == 10 and event["_gateway"]["source_time"] == 10
    assert event["_gateway"]["message_id"]
    node.clock, envelope.sequence = 20., 2
    IdealGateway.receive_envelope(node, envelope)
    assert len(messages) == 1 and len(acks) == 2
    assert events[-1][0] == "expired"
    node.clock, envelope.generation_time.sec, envelope.sequence = 21., 20, 3
    envelope.payload = list(serialize_message(String(data="malformed JSON")))
    envelope.payload_length = len(envelope.payload)
    IdealGateway.receive_envelope(node, envelope)
    assert len(messages) == 1 and events[-1][0] == "decode_error"
