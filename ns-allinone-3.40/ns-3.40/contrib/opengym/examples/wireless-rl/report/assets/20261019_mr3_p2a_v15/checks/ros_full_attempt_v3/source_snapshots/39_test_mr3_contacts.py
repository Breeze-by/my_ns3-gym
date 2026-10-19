"""Verify physical contact coverage, conservative filtering and live monitoring."""

import json
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

import pytest

from multi_robot_exploration.mr3_contacts import (
    CONTACT_COMPONENTS, ContactMonitor, contact_topics, filter_non_support_contacts,
)


GROUND = "ground_plane::link::collision"


def contact(first, second):
    return SimpleNamespace(collision1_name=first, collision2_name=second)


def message(time, states=()):
    sec = int(time)
    stamp = SimpleNamespace(sec=sec, nanosec=round((time - sec) * 10**9))
    return SimpleNamespace(header=SimpleNamespace(stamp=stamp), states=list(states))


def fresh_all(monitor, time):
    for robot in monitor.robot_names:
        for name in CONTACT_COMPONENTS:
            monitor.update(robot, name, message(time), time)


def test_every_physical_collision_has_its_own_active_20hz_sensor():
    model = Path(__file__).resolve().parents[2] / "multi_robot/models/turtlebot3_waffle/model.sdf"
    root = ET.parse(model).getroot()
    collisions = {(link.get("name"), col.get("name"))
                  for link in root.findall("./model/link") for col in link.findall("collision")}
    covered = set()
    topics = set()
    for link in root.findall("./model/link"):
        for sensor in link.findall("sensor[@type='contact']"):
            assert sensor.findtext("always_on") == "true"
            assert float(sensor.findtext("update_rate")) == 20.0
            entries = sensor.findall("contact/collision")
            assert len(entries) == 1
            pair = (link.get("name"), entries[0].text)
            assert pair not in covered
            covered.add(pair)
            plugin = sensor.find("plugin")
            assert plugin.get("filename") == "libgazebo_ros_bumper.so"
            topics.add(plugin.findtext("ros/remapping").split(":=", 1)[1])
    assert collisions == covered
    assert len(collisions) == 6
    assert covered == {(spec.link, spec.collision) for spec in CONTACT_COMPONENTS.values()}
    assert topics == {spec.topic_suffix for spec in CONTACT_COMPONENTS.values()}
    assert contact_topics("tb1")["base"] == "/tb1/collision"


@pytest.mark.parametrize(
    "component", ["wheel_left", "wheel_right", "caster_back_left", "caster_back_right"],
)
def test_only_exact_declared_support_contact_is_filtered(component):
    spec = CONTACT_COMPONENTS[component]
    own = f"tb1::{spec.link}::{spec.collision}"
    support = contact(own, GROUND)
    reverse_support = contact(GROUND, own)
    wall = contact(own, "walls::wall::collision")
    robot = contact(own, "tb2::base_link::base_collision")
    misleading_ground_name = contact(own, "obstacle_ground_plane::link::collision")
    wrong_component = contact("tb1::base_link::base_collision", GROUND)
    retained, filtered = filter_non_support_contacts(
        "tb1", component,
        [support, reverse_support, wall, robot, misleading_ground_name, wrong_component],
        {GROUND},
    )
    assert filtered == 2
    assert retained == (wall, robot, misleading_ground_name, wrong_component)
    assert filter_non_support_contacts("tb1", component, [support], set()) == ((support,), 0)


@pytest.mark.parametrize("component", ["base", "lidar"])
def test_body_ground_contact_cannot_be_filtered(component):
    spec = CONTACT_COMPONENTS[component]
    state = contact(f"tb1::{spec.link}::{spec.collision}", GROUND)
    assert filter_non_support_contacts("tb1", component, [state], {GROUND}) == ((state,), 0)


def test_empty_messages_need_fresh_source_and_receipt_from_every_component():
    monitor = ContactMonitor(["tb1", "tb2", "tb3"], {GROUND})
    fresh_all(monitor, 0.0)
    assert not monitor.summary(0.0)["fresh"]
    assert not monitor.summary(0.0)["ever_unhealthy"]
    fresh_all(monitor, 1.0)
    assert monitor.start(1.0) == {}
    assert monitor.summary(1.5)["fresh"]
    assert not monitor.summary(1.5001)["fresh"]
    fresh_all(monitor, 1.6)
    summary = monitor.summary(1.6)
    assert summary["fresh"]
    assert summary["ever_unhealthy"]
    assert len(summary["latched_issues"]) == 18
    assert summary["event_count"] == 0
    json.dumps(summary, allow_nan=False)


def test_missing_sensor_prevents_ready_and_latches_when_started():
    monitor = ContactMonitor(["tb1"], {GROUND})
    for name in CONTACT_COMPONENTS:
        if name != "lidar":
            monitor.update("tb1", name, message(1.0), 1.0)
    assert monitor.start(1.0) == {"tb1/lidar": "missing_source_time"}
    monitor.update("tb1", "lidar", message(1.1), 1.1)
    assert monitor.summary(1.1)["fresh"]
    assert monitor.summary(1.1)["ever_unhealthy"]


def test_duplicate_stamp_does_not_refresh_either_clock():
    monitor = ContactMonitor(["tb1"], {GROUND})
    fresh_all(monitor, 1.0)
    monitor.start(1.0)
    assert not monitor.update("tb1", "base", message(1.0), 1.4)["accepted"]
    state = monitor.summary(1.4)["components"]["tb1"]["base"]
    assert state["last_receipt_time_sec"] == 1.0
    assert state["last_source_time_sec"] == 1.0
    assert state["duplicate_message_count"] == 1
    assert not monitor.summary(1.51)["fresh"]


def test_duplicate_source_stamp_cannot_swallow_or_clear_real_contact():
    monitor = ContactMonitor(["tb1"], {GROUND})
    fresh_all(monitor, 1.0)
    monitor.start(1.0)
    wall = contact("tb1::wheel_left_link::wheel_left_collision", "walls::wall::collision")
    result = monitor.update("tb1", "wheel_left", message(1.0, [wall]), 1.1)
    assert not result["accepted"]
    assert result["active"]
    assert monitor.summary(1.1)["event_count"] == 1
    empty = monitor.update("tb1", "wheel_left", message(1.0), 1.2)
    assert empty["active"]
    state = monitor.summary(1.2)["components"]["tb1"]["wheel_left"]
    assert state["last_source_time_sec"] == 1.0
    assert state["last_receipt_time_sec"] == 1.0
    monitor.update("tb1", "wheel_left", message(1.3), 1.3)
    assert not monitor.summary(1.3)["robots"]["tb1"]["active"]
    assert monitor.summary(1.3)["event_count"] == 1


@pytest.mark.parametrize("source", [0.9, 1.2])
def test_regressed_or_future_source_does_not_replace_valid_health(source):
    monitor = ContactMonitor(["tb1"], {GROUND})
    fresh_all(monitor, 1.0)
    monitor.start(1.0)
    assert not monitor.update("tb1", "base", message(source), 1.1)["accepted"]
    state = monitor.summary(1.1)["components"]["tb1"]["base"]
    assert state["last_source_time_sec"] == 1.0
    assert state["last_receipt_time_sec"] == 1.0
    assert state["invalid_timestamp_count"] == 1
    assert monitor.summary(1.1)["ever_unhealthy"]


def test_poll_free_source_gap_is_still_latched_at_next_update():
    monitor = ContactMonitor(["tb1"], {GROUND})
    fresh_all(monitor, 1.0)
    monitor.start(1.0)
    fresh_all(monitor, 1.6)
    assert monitor.summary(1.6)["fresh"]
    assert monitor.summary(1.6)["ever_unhealthy"]
    component = monitor.summary(1.6)["components"]["tb1"]["base"]
    assert component["max_source_gap_sec"] == pytest.approx(0.6)
    assert component["max_receipt_gap_sec"] == pytest.approx(0.6)


def test_multiple_body_sensors_count_union_events_and_preserve_startup_contacts():
    monitor = ContactMonitor(["tb1"], {GROUND})
    fresh_all(monitor, 1.0)
    base = contact("tb1::base_link::base_collision", "walls::wall::collision")
    wheel = contact("tb1::wheel_left_link::wheel_left_collision", "walls::wall::collision")
    monitor.update("tb1", "base", message(1.1, [base]), 1.1)
    monitor.start(1.1)
    monitor.update("tb1", "wheel_left", message(1.2, [wheel]), 1.2)
    monitor.update("tb1", "base", message(1.3), 1.3)
    assert monitor.summary(1.4)["robots"]["tb1"]["active"]
    monitor.update("tb1", "wheel_left", message(1.4), 1.4)
    summary = monitor.summary(1.4)
    assert summary["event_count"] == 1
    assert summary["duration_sec"] == pytest.approx(0.3)
    assert not summary["robots"]["tb1"]["active"]


def test_support_filter_count_is_explicit_and_invalid_timestamp_cannot_erase_contact():
    monitor = ContactMonitor(["tb1"], {GROUND})
    fresh_all(monitor, 1.0)
    monitor.start(1.0)
    own = "tb1::wheel_left_link::wheel_left_collision"
    monitor.update("tb1", "wheel_left", message(1.1, [contact(own, GROUND)]), 1.1)
    wall = contact(own, "walls::wall::collision")
    monitor.update("tb1", "wheel_left", message(1.2, [wall]), 1.2)
    monitor.update("tb1", "wheel_left", message(1.15), 1.3)
    summary = monitor.summary(1.3)
    assert summary["filtered_support_count"] == 1
    assert summary["event_count"] == 1
    assert summary["robots"]["tb1"]["active"]
    assert summary["ever_unhealthy"]


@pytest.mark.parametrize(
    "supports", [{"collision"}, {"::link::collision"}, {"tb2::base_link::base_collision"}],
)
def test_support_declarations_cannot_be_unscoped_or_a_team_robot(supports):
    with pytest.raises(ValueError):
        ContactMonitor(["tb1", "tb2", "tb3"], supports)
