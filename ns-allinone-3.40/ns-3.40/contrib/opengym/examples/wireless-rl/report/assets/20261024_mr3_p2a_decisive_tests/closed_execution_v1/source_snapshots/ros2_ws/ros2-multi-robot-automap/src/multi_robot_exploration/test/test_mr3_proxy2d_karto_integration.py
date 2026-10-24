"""Mocked integration contracts; no World constructor, assets, SDK or process.

World methods operate on SimpleNamespace fixtures with mocked ray sources.
The sole advance is a synthetic 40--60ms quantum, never a scene or episode.
"""

import importlib.util
from pathlib import Path
import sys
from types import MethodType, SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from multi_robot_exploration import mr3_proxy2d_karto as karto_module
from multi_robot_exploration import mr3_proxy2d_world as world_module
from mr3_learning import proxy2d as supervisor_module
from mr3_learning import proxy2d_activity as activity_module


ROBOTS = world_module.ROBOTS
SCRIPT = Path(__file__).resolve().parents[3] / "scripts/mr3_proxy2d_worker.py"


def worker_module():
    spec = importlib.util.spec_from_file_location("karto_integration_worker_fixture", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sensor_namespace(monkeypatch):
    """Only method inputs/state exist; all scene rays and randomness are mocked."""
    value = SimpleNamespace(
        _mapper_mode="karto", _scan_sequence=0, _odom_sequence=0,
        _laser={"frame_offset": (-.064, 0.), "frame_yaw": 0.,
                "range_min": .12, "range_max": 10., "noise_std": .01},
        _angles=np.array([0.]), _rectangles=object(), _radius=.1,
        _scans={}, _map_versions={name: 0 for name in ROBOTS},
        _maps={name: np.full((4, 5), -1, dtype=np.int8) for name in ROBOTS},
        _mappers={name: SimpleNamespace(integrate=Mock(return_value=True),
                    grid=Mock(return_value=np.full((4, 5), 100, dtype=np.int8)))
                  for name in ROBOTS},
        _laser_random={name: SimpleNamespace(normal=Mock(return_value=np.zeros(1)))
                       for name in ROBOTS})
    for method in ("_sensor_pose", "_sense", "_integrate_scan", "own_sensors", "local_map"):
        setattr(value, method, MethodType(getattr(world_module.ProxyWorld, method), value))
    boxes = Mock(return_value=np.array([2.]))
    disks = Mock(return_value=np.array([10.]))
    monkeypatch.setattr(world_module, "ray_box_ranges", boxes)
    monkeypatch.setattr(world_module, "ray_disk_ranges", disks)
    return value, boxes


def reset_namespace():
    value = SimpleNamespace(
        _mapper_mode="karto", _mapper_library="not-loaded-cpu-fixture.so", _epoch="cpu/epoch",
        _mappers={name: SimpleNamespace(close=Mock()) for name in ROBOTS},
        starts={name: [float(index * 4), 0.] for index, name in enumerate(ROBOTS)},
        seed=101, shape=(4, 5), resolution=.05, origin=(-1., -2.),
        _angles=np.array([0.]),
        _laser={"range_min": .12, "range_max": 10.,
                "frame_offset": (-.064, 0.), "frame_yaw": .2},
        _sense=Mock(), own_sensors=Mock(return_value={"local": "fixture"}))
    value.close = MethodType(world_module.ProxyWorld.close, value)
    return value


def test_sense_gives_mapper_estimated_body_pose_and_only_ray_source_physical_pose(monkeypatch):
    value, boxes = sensor_namespace(monkeypatch)
    physical = {name: np.array([float(i * 4), 0., 0.]) for i, name in enumerate(ROBOTS)}
    estimated = {name: np.array([float(i * 4 + 1), 2., .3]) for i, name in enumerate(ROBOTS)}
    value._estimated = {name: np.array([999., 999., 0.]) for name in ROBOTS}
    value._sense(physical, estimated, 50_000_000)
    for index, name in enumerate(ROBOTS):
        args = value._mappers[name].integrate.call_args.args
        assert args[:2] == (1, 50_000_000)
        np.testing.assert_array_equal(args[2], estimated[name])
        assert not np.array_equal(args[2], physical[name])
        assert not np.array_equal(args[2], value._sensor_pose(estimated[name]))
        np.testing.assert_array_equal(args[3], value._angles)
        np.testing.assert_array_equal(args[4], [2.])
        assert boxes.call_args_list[index].args[0] == (float(index * 4) - .064, 0.)
        assert value._map_versions[name] == 1
        assert value._scans[name]["source_clock_ns"] == 50_000_000
        np.testing.assert_array_equal(value._maps[name], np.full((4, 5), 100, dtype=np.int8))


def test_scan_at_50ms_uses_interpolated_estimate_not_60ms_end_odometry(monkeypatch):
    value, _ = sensor_namespace(monkeypatch)
    value.resolution, value.origin = .05, (0.,0.)
    value.time_ns, value.quantum_ns, value._next_scan_ns = 40_000_000, 20_000_000, 50_000_000
    value._poses = {name: np.array([float(i * 4), 0., 0.]) for i, name in enumerate(ROBOTS)}
    value._estimated = {name: np.array([float(i * 4 + 1), 0., 0.]) for i, name in enumerate(ROBOTS)}
    value._commands = {name: (.2, 0.) for name in ROBOTS}
    value._encoder_scale = {name: np.array([1.1, 1.1]) for name in ROBOTS}
    value._velocities = {name: (0., 0.) for name in ROBOTS}
    value._paths = {name: 0. for name in ROBOTS}
    value._active_contacts, value._contact_events = set(), []
    value._wall_collision = Mock(return_value=False)
    result = world_module.ProxyWorld.advance(value)
    assert value.time_ns == 60_000_000 and value._next_scan_ns == 100_000_000
    for index, name in enumerate(ROBOTS):
        args = value._mappers[name].integrate.call_args.args
        assert args[:2] == (1, 50_000_000)
        assert args[2][0] == pytest.approx(index * 4 + 1 + .0022, abs=1e-14)
        assert result[name]["odom"]["x"] == pytest.approx(index * 4 + 1 + .0044, abs=1e-14)
        assert abs(args[2][0] - result[name]["odom"]["x"]) > .002
        assert result[name]["odom"]["source_clock_ns"] == 60_000_000
        assert result[name]["scan"]["source_clock_ns"] == 50_000_000
        assert world_module.ProxyWorld.map_record(value, name)["source_clock_ns"] == 50_000_000


@pytest.mark.parametrize("explicit", [False, True])
def test_default_endpoint_path_retains_original_free_hit_and_duplicate_behavior(explicit):
    value = SimpleNamespace(
        _laser={"frame_offset": (0., 0.), "frame_yaw": 0., "range_max": 10.},
        _angles=np.array([0.]), origin=(0., 0.), resolution=.5, shape=(4, 6),
        _last_ray_cells={}, _maps={"tb1": np.full((4, 6), -1, dtype=np.int8)},
        _mappers={"tb1": SimpleNamespace(integrate=Mock(side_effect=AssertionError("Karto used")))})
    if explicit:
        value._mapper_mode = "endpoint"
    value._sensor_pose = MethodType(world_module.ProxyWorld._sensor_pose, value)
    world_module.ProxyWorld._integrate_scan(value, "tb1", (.25, .25, 0.), np.array([.75]))
    expected = np.full((4, 6), -1, dtype=np.int8)
    expected[0, :3] = (0, 0, 100)
    np.testing.assert_array_equal(value._maps["tb1"], expected)
    world_module.ProxyWorld._integrate_scan(value, "tb1", (.25, .25, 0.), np.array([.75]))
    np.testing.assert_array_equal(value._maps["tb1"], expected)
    value._mappers["tb1"].integrate.assert_not_called()


def test_reset_closes_old_three_and_close_releases_three_new_mapper_instances(monkeypatch):
    value = reset_namespace()
    old = dict(value._mappers)
    created = [SimpleNamespace(close=Mock()) for _ in ROBOTS]
    factory = Mock(side_effect=created)
    monkeypatch.setattr(karto_module, "KartoSensorMapper", factory)
    assert world_module.ProxyWorld.reset(value) == {"local": "fixture"}
    assert factory.call_count == 3
    for index, name in enumerate(ROBOTS):
        old[name].close.assert_called_once_with()
        assert value._mappers[name] is created[index]
        assert factory.call_args_list[index].kwargs["epoch"] == f"cpu/epoch/{name}"
        assert factory.call_args_list[index].kwargs["library_path"] == "not-loaded-cpu-fixture.so"
        assert not np.shares_memory(value._poses[name], value._estimated[name])
    assert value._sense.call_args.args[2] == 0
    value.close()
    value.close()
    assert value._mappers == {}
    for mapper in created:
        mapper.close.assert_called_once_with()


def test_reset_constructor_failure_closes_already_created_mapper(monkeypatch):
    value = reset_namespace()
    old = dict(value._mappers)
    first = SimpleNamespace(close=Mock())
    factory = Mock(side_effect=[first, RuntimeError("fixture mapper construction rejected")])
    monkeypatch.setattr(karto_module, "KartoSensorMapper", factory)
    with pytest.raises(RuntimeError, match="fixture mapper construction rejected"):
        world_module.ProxyWorld.reset(value)
    for mapper in old.values():
        mapper.close.assert_called_once_with()
    first.close.assert_called_once_with()
    assert value._mappers == {} and factory.call_count == 2
    value._sense.assert_not_called()


def test_endpoint_reset_never_constructs_a_karto_mapper(monkeypatch):
    value = reset_namespace()
    value._mapper_mode = "endpoint"
    factory = Mock(side_effect=AssertionError("default path loaded Karto"))
    monkeypatch.setattr(karto_module, "KartoSensorMapper", factory)
    world_module.ProxyWorld.reset(value)
    factory.assert_not_called()
    assert value._mappers == {}


@pytest.mark.parametrize("kwargs,mode,library", [({}, "endpoint", None),
    ({"mapper": "karto", "mapper_library": Path("explicit-adapter.so")},
     "karto", Path("explicit-adapter.so"))])
def test_worker_constructor_forwards_only_declared_mapper_to_world(monkeypatch, tmp_path, kwargs, mode, library):
    module = worker_module()
    constructor = Mock(side_effect=RuntimeError("stop before World construction"))
    monkeypatch.setattr(world_module, "ProxyWorld", constructor)
    # These imports are inert mocks; no information/navigation/protocol object
    # is constructed before the intercepted World constructor.
    for suffix, attributes in {
        "mr3_proxy2d_information": ("ProxyInformation",),
        "mr3_proxy2d_navigation": ("ProxyNavigator",),
        "mr3_protocol": ("GoalDispatcher",),
        "mr3_transport": ("IdealTransport", "ReceivedStore"),
        "mr3_activity": ("ReceivedActivity",),
    }.items():
        monkeypatch.setitem(sys.modules, "multi_robot_exploration." + suffix,
                            SimpleNamespace(**{name: Mock() for name in attributes}))
    value = SimpleNamespace()
    with pytest.raises(RuntimeError, match="stop before World construction"):
        module.ProxyWorker.__init__(value, tmp_path, "cpu-epoch", "open", 101, **kwargs)
    constructor.assert_called_once_with("open", 101, mapper=mode, mapper_library=library, epoch="cpu-epoch")


@pytest.mark.parametrize("extra,mode,library", [([], "endpoint", None),
    (["--mapper", "karto", "--mapper-library", "explicit-adapter.so"],
     "karto", Path("explicit-adapter.so"))])
def test_worker_cli_defaults_endpoint_and_passes_explicit_karto_parameters(monkeypatch, tmp_path, extra, mode, library):
    module = worker_module()
    peer = SimpleNamespace(receive=Mock(side_effect=[{"operation": "reset"}, {"operation": "close"}]),
                           send=Mock())
    monkeypatch.setattr(module.ipc, "JsonLinePeer", Mock(return_value=peer))
    monkeypatch.setattr(module, "sys", SimpleNamespace(
        stdin=SimpleNamespace(fileno=lambda: 0), stdout=SimpleNamespace(fileno=lambda: 1)))
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), "--role", "worker", "--directory", str(tmp_path),
        "--epoch", "cpu-epoch", "--scene", "open", "--seed", "101", *extra])
    worker = SimpleNamespace(reset=Mock(return_value={"fixture": True}), close=Mock())
    constructor = Mock(return_value=worker)
    monkeypatch.setattr(module, "ProxyWorker", constructor)
    assert module.main() == 0
    constructor.assert_called_once_with(tmp_path, "cpu-epoch", "open", 101,
                                       mapper=mode, mapper_library=library)
    worker.close.assert_called_once_with()


@pytest.mark.parametrize("mode", ["endpoint", "karto"])
def test_supervisor_command_passes_only_explicit_library_without_spawning(monkeypatch, tmp_path, mode):
    library = tmp_path / "not-loaded-adapter.so"
    library.touch()
    owner = supervisor_module.ProxySupervisor(tmp_path / "env", mapper=mode,
        mapper_library=library if mode == "karto" else None)
    popen = Mock(side_effect=RuntimeError("fixture forbids subprocess launch"))
    monkeypatch.setattr(supervisor_module.subprocess, "Popen", popen)
    monkeypatch.setattr(supervisor_module, "ros_environment", Mock(return_value={}))
    with pytest.raises(RuntimeError, match="fixture forbids subprocess launch"):
        owner.reset("open", 101)
    command = popen.call_args.args[0]
    assert command[-2:] == [mode, str(library.resolve()) if mode == "karto" else ""]
    assert '--mapper "$6" ${7:+--mapper-library "$7"}' in command[4]
    assert owner.process is None and owner.console is None


@pytest.mark.parametrize("mode,library", [("endpoint", "unrequested.so"), ("karto", None), ("other", None)])
def test_supervisor_invalid_mapper_pairs_reject_before_directory_creation(tmp_path, mode, library):
    target = tmp_path / "must-not-exist"
    with pytest.raises(ValueError, match="mapper/library"):
        supervisor_module.ProxySupervisor(target, mapper=mode, mapper_library=library)
    assert not target.exists()


def test_static_source_inventory_contains_adapter_cpp_and_all_local_sdk_headers():
    # Metadata/path inventory only: do not read scene contents or load an ELF.
    inventory = set(activity_module.source_paths())
    package = activity_module.ROS_ROOT / "src/multi_robot_exploration/multi_robot_exploration"
    sdk = activity_module.ROS_ROOT / "src/slam_toolbox/lib/karto_sdk/include/karto_sdk"
    assert package / "mr3_proxy2d_karto_native.cpp" in inventory
    headers = set(sdk.glob("*.h")) | set(sdk.glob("*.hpp"))
    assert headers and sdk / "Karto.h" in headers and headers <= inventory
