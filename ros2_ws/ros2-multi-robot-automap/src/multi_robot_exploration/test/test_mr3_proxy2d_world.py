"""Finite synthetic CPU fixtures; no development episode or capacity activity."""

import copy
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np
import pytest

from multi_robot_exploration.mr3_proxy2d_world import (
    ProxyWorld, ROBOTS, laser_configuration, ray_box_ranges, ray_disk_ranges,
)


def fixture_assets(directory, extra=(), starts=None):
    """Synthetic 6m box room; real file parser/contract loader, no ROS graph."""
    source = Path(__file__).resolve().parents[2] / "multi_robot"
    directory = Path(directory)
    (directory / "worlds").mkdir(parents=True)
    (directory / "config/mr3_p1a").mkdir(parents=True)
    (directory / "models/turtlebot3_waffle").mkdir(parents=True)
    shutil.copyfile(source / "models/turtlebot3_waffle/model.sdf",
                    directory / "models/turtlebot3_waffle/model.sdf")
    boxes = ((-2.95, 0., 0., .1, 6.), (2.95, 0., 0., .1, 6.),
             (0., -2.95, 0., 6., .1), (0., 2.95, 0., 6., .1), *extra)
    body = ["<sdf version='1.7'><world name='synthetic'><model name='walls'><static>true</static><link name='wall'>"]
    for index, (x, y, yaw, sx, sy) in enumerate(boxes):
        body.append(f"<collision name='c{index}'><pose>{x} {y} .5 0 0 {yaw}</pose>"
                    f"<geometry><box><size>{sx} {sy} 1</size></box></geometry></collision>")
    body.append("</link></model></world></sdf>")
    raw = "".join(body).encode()
    (directory / "worlds/p1c_open.world").write_bytes(raw)
    contract = json.loads((source / "config/mr3_p1a/open.json").read_bytes())
    contract["world_sha256"] = hashlib.sha256(raw).hexdigest()
    contract["roi"]["bounds"] = [-3., -3., 3., 3.]
    if starts is not None:
        contract["starts"] = starts
    (directory / "config/mr3_p1a/open.json").write_text(json.dumps(contract))
    return directory


def zeros(**changed):
    return {name: changed.get(name, (0., 0.)) for name in ROBOTS}


def test_vectorized_box_rays_cover_parallel_inside_behind_and_rotated_geometry():
    directions = np.array(((1., 0.), (-1., 0.), (0., 1.)))
    boxes = [(2., 0., 0., .2, 2.)]
    np.testing.assert_allclose(ray_box_ranges((0., 0.), directions, boxes, 10.), [1.9, 10., 10.])
    np.testing.assert_allclose(ray_box_ranges((2., 0.), directions, boxes, 10.), [.1, .1, 1.])
    rotated = ray_box_ranges((0., 0.), directions[:1], [(2., 0., math.pi / 4., 2., 2.)], 10.)
    np.testing.assert_allclose(rotated, [2. - math.sqrt(2.)])
    np.testing.assert_array_equal(ray_box_ranges((0., 0.), directions, [], 10.), [10.] * 3)


def test_vectorized_peer_rays_are_local_sensor_intersections():
    values = ray_disk_ranges((0., 0.), np.array(((1., 0.), (-1., 0.), (0., 1.))),
                             [(2., 0.)], .25, 10.)
    np.testing.assert_allclose(values, [1.75, 10., 10.])


def test_changed_sensor_model_is_not_silently_admitted(tmp_path):
    assets = fixture_assets(tmp_path / "room")
    model = assets / "models/turtlebot3_waffle/model.sdf"
    model.write_text(model.read_text().replace("<max_angle>6.280000</max_angle>",
                                               "<max_angle>6.283185</max_angle>"))
    with pytest.raises(ValueError, match="current laser model"):
        laser_configuration(model)


def test_reset_uses_declared_spawns_and_map_is_ray_observed_not_a_truth_copy(tmp_path):
    world = ProxyWorld("open", 101, asset_root=fixture_assets(tmp_path / "room"))
    own = world.own_sensors()
    assert tuple(own) == ROBOTS and world.shape == (120, 120)
    for name in ROBOTS:
        assert [own[name]["odom"]["x"], own[name]["odom"]["y"]] == world.starts[name]
        grid = world.local_map(name)
        assert set(np.unique(grid)) <= {-1, 0, 100}
        assert np.any(grid == -1) and np.any(grid == 0) and np.any(grid == 100)
        assert own[name]["scan"]["sequence"] == 1
        assert len(own[name]["scan"]["ranges"]) == 360
        grid[:] = 100
        own[name]["scan"]["ranges"][:] = 0
        assert np.any(world.local_map(name) == -1)
        assert np.all(world.own_sensors()[name]["scan"]["ranges"] >= .12)
    assert set(world.evaluation_state()) == {
        "time_ns", "poses", "path_lengths", "collision_events", "contact_events", "native_contact_monitoring"}
    json.dumps(world.evaluation_state(), allow_nan=False)


def test_twenty_hz_events_keep_fifty_ms_stamp_on_twenty_ms_integrator(tmp_path):
    world = ProxyWorld("open", 17, asset_root=fixture_assets(tmp_path / "room"))
    world.apply_commands(zeros(tb1=(.2, 0.)))
    assert world.advance()["tb1"]["scan"]["source_clock_ns"] == 0
    assert world.advance()["tb1"]["scan"]["source_clock_ns"] == 0
    sensed = world.advance()["tb1"]
    assert world.time_ns == sensed["odom"]["source_clock_ns"] == 60_000_000
    assert sensed["scan"]["source_clock_ns"] == 50_000_000
    assert world.map_record("tb1")["source_clock_ns"] == 50_000_000
    assert world.map_record("tb1")["version"] == sensed["scan"]["sequence"] == 2


def test_odometry_is_independent_encoder_integration_and_is_not_recopied_from_truth(tmp_path):
    world = ProxyWorld("open", 41, asset_root=fixture_assets(tmp_path / "room"))
    initial = world.own_sensors()["tb1"]["odom"]
    # This fixture introduces a physical localization error. A zero wheel
    # increment cannot correct it by reading the privileged plant pose.
    world._poses["tb1"][0] += .05
    own = world.advance()["tb1"]["odom"]
    assert own["x"] == initial["x"] and own["y"] == initial["y"]
    assert world.evaluation_state()["poses"]["tb1"]["x"] != own["x"]
    world.apply_commands(zeros(tb1=(.2, 0.)))
    world.advance()
    own = world.own_sensors()["tb1"]["odom"]
    assert own["x"] > initial["x"]
    assert own["x"] != world.evaluation_state()["poses"]["tb1"]["x"]


def test_hidden_geometry_changes_do_not_enter_own_sensor_map_inputs(tmp_path):
    screen = (1.5, 0., 0., .1, 5.8)
    first = ProxyWorld("open", 103, asset_root=fixture_assets(tmp_path / "a", [screen]))
    second = ProxyWorld("open", 103, asset_root=fixture_assets(
        tmp_path / "b", [screen, (2., 0., 0., .2, .2)]))
    for name in ROBOTS:
        a, b = first.own_sensors()[name], second.own_sensors()[name]
        assert a["odom"] == b["odom"]
        np.testing.assert_array_equal(a["scan"]["ranges"], b["scan"]["ranges"])
        np.testing.assert_array_equal(first.local_map(name), second.local_map(name))


def test_finite_forward_turn_stop_sequence_has_halved_quantum_agreement(tmp_path):
    assets = fixture_assets(tmp_path / "room")
    regular = ProxyWorld("open", 17, .02, asset_root=assets)
    half = ProxyWorld("open", 17, .01, asset_root=assets)
    for command in ((.2, 0.), (0., .8), (0., 0.)):
        for world, count in ((regular, 5), (half, 10)):
            world.apply_commands(zeros(tb1=command))
            for _ in range(count):
                world.advance()
    assert regular.time_ns == half.time_ns == 300_000_000
    for name in ROBOTS:
        a, b = regular.own_sensors()[name], half.own_sensors()[name]
        for field in ("x", "y", "yaw", "v", "w"):
            assert a["odom"][field] == pytest.approx(b["odom"][field], abs=1e-12)
        np.testing.assert_allclose(a["scan"]["ranges"], b["scan"]["ranges"], atol=1e-12)
        np.testing.assert_array_equal(regular.local_map(name), half.local_map(name))
    assert regular.evaluation_state()["collision_events"] == half.evaluation_state()["collision_events"] == 0
    assert regular.evaluation_state()["path_lengths"]["tb1"] == pytest.approx(.02)
    before = regular.evaluation_state()["poses"]
    regular.advance()
    assert regular.evaluation_state()["poses"] == before


def test_contact_proxy_blocks_motion_and_remains_explicitly_non_native(tmp_path):
    starts = {"tb1": [0., -1.], "tb2": [-1., 1.], "tb3": [-1., -1.]}
    assets = fixture_assets(tmp_path / "room", [( .306, -1., 0., .1, 1.)], starts)
    world = ProxyWorld("open", 101, asset_root=assets)
    world.apply_commands(zeros(tb1=(.2, 0.)))
    world.advance()
    world.advance()
    state = world.evaluation_state()
    assert state["collision_events"] == 1
    assert state["poses"]["tb1"]["x"] == pytest.approx(.004)
    assert state["contact_events"][0]["kind"] == "proxy_blocked_disk_contact"
    assert state["native_contact_monitoring"] is False
    assert state["contact_events"][0]["native_contact"] is False
    assert world.own_sensors()["tb1"]["odom"]["x"] > state["poses"]["tb1"]["x"]


def test_seeded_reset_reproduces_sensor_noise_and_discards_old_state(tmp_path):
    world = ProxyWorld("open", 41, asset_root=fixture_assets(tmp_path / "room"))
    first = world.own_sensors()
    first_maps = {name: world.local_map(name) for name in ROBOTS}
    world.apply_commands(zeros(tb1=(.2, .1)))
    world.advance()
    world.reset()
    assert world.time_ns == 0 and world.evaluation_state()["collision_events"] == 0
    for name in ROBOTS:
        assert first[name]["odom"] == world.own_sensors()[name]["odom"]
        np.testing.assert_array_equal(first[name]["scan"]["ranges"], world.own_sensors()[name]["scan"]["ranges"])
        np.testing.assert_array_equal(first_maps[name], world.local_map(name))


@pytest.mark.parametrize("commands", [
    {}, {"tb1": (0., 0.)}, zeros(tb1=(True, 0.)), zeros(tb2=(.201, 0.)),
    zeros(tb3=(0., .801)), zeros(tb1=(float("nan"), 0.)), zeros(tb2=(0., float("inf"))),
])
def test_bad_joint_commands_are_rejected_without_partial_application(tmp_path, commands):
    world = ProxyWorld("open", 0, asset_root=fixture_assets(tmp_path / "room"))
    before = copy.deepcopy(world._commands)
    with pytest.raises(ValueError):
        world.apply_commands(commands)
    assert world._commands == before


@pytest.mark.parametrize("scene,seed,quantum", [
    ("unknown", 1, .02), ("open", -1, .02), ("open", True, .02),
    ("open", 1, True), ("open", 1, .04),
])
def test_unsupported_scope_rejects_before_asset_loading(scene, seed, quantum):
    with pytest.raises(ValueError):
        ProxyWorld(scene, seed, quantum, asset_root="does-not-exist")
