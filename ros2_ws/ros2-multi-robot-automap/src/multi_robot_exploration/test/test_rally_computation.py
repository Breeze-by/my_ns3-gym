"""Rally computation stays equivalent without retaining mutable or stale geometry."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

import numpy as np
import pytest

from multi_robot_exploration import control as c

REFERENCE = json.loads((Path(__file__).parent / "fixtures" /
                        "p2c_v40_rally_computation_reference.json").read_text())
assert hashlib.sha256(REFERENCE["reference_functions"].encode()).hexdigest() == \
       REFERENCE["reference_functions_sha256"]
scope = dict(vars(c))
exec(compile(REFERENCE["reference_functions"], "<frozen d70 rally>", "exec"), scope)
original_assign = scope["assign_rally_poses"]


def decode(saved):
    return dict(data=np.frombuffer(zlib.decompress(base64.b64decode(saved["grid"])),
                                  dtype="<i2").reshape(saved["shape"]),
                resolution=saved["resolution"], origin=saved["origin"])


def saved_arguments(event):
    grid = decode(event["planning_map"])
    return dict(raw_grid=grid["data"], resolution=grid["resolution"], origin=grid["origin"],
                robot_positions=event["robot_positions"], target=event["target"],
                objective=event["objective"], battery_states=event["battery_states"],
                observer_robot=event["observer_robot"], current_positions=event["current_positions"],
                hold_sec=event["hold_sec"],
                return_maps={name: decode(saved) for name, saved in event["return_maps"].items()})


@pytest.mark.parametrize("case", REFERENCE["cases"], ids=lambda case: case["name"])
def test_original_inputs_have_exact_frozen_proposals(case):
    assert c.assign_rally_poses(**saved_arguments(case["event"])) == \
           original_assign(**saved_arguments(case["event"]))


@pytest.mark.parametrize("kind", ["immutable", "mutable", "readonly_view"])
def test_only_immutable_sources_reuse_approach_fields_between_levels(monkeypatch, kind):
    coarse = [c.RallyPose(5.05, 4.05, 0.), c.RallyPose(5.05, 4.15, 0.)]
    fine = c.RallyPose(3.05, 4.05, 0.)
    owner = np.zeros((100, 100), dtype=np.int16)
    if kind == "immutable":
        grid = c.immutable_grid_snapshot(owner, owner.shape)
    elif kind == "readonly_view":
        grid = owner.view()
        grid.flags.writeable = False
    else:
        grid = owner
    levels, calls = [], []
    def poses(*args, **kwargs):
        levels.append(args[-1])
        return coarse + [fine] if args[-1] else coarse
    distance = c.path_distance_grid
    def counted(*args, **kwargs):
        calls.append(args[1])
        return distance(*args, **kwargs)
    monkeypatch.setattr(c, "rally_pose_candidates", poses)
    monkeypatch.setattr(c, "path_distance_grid", counted)
    answer = c.assign_rally_poses(grid, .1, (0., 0.),
        {"tb1": (1.05, 1.05), "tb2": (1.05, 2.05)}, (4.05, 4.05))
    assert len(answer) == 2 and levels == [False, True]
    assert len(calls) == (2 if kind == "immutable" else 4)


@pytest.mark.parametrize("readonly_view", [False, True])
def test_mutation_between_tiers_cannot_reuse_pre_mutation_field(monkeypatch, readonly_view):
    owner = np.zeros((100, 100), dtype=np.int16)
    grid = owner.view() if readonly_view else owner
    if readonly_view:
        grid.flags.writeable = False
    coarse = [c.RallyPose(5.05, 4.05, 0.), c.RallyPose(5.05, 4.15, 0.)]
    def poses(*args, **kwargs):
        if args[-1]:
            owner[:, 25:35] = 100
            return coarse + [c.RallyPose(3.55, 4.05, 0.)]
        return coarse
    monkeypatch.setattr(c, "rally_pose_candidates", poses)
    assert not c.assign_rally_poses(grid, .1, (0., 0.),
        {"tb1": (1.05, 1.05), "tb2": (1.05, 2.05)}, (4.05, 4.05))


def synthetic_arguments():
    raw = c.immutable_grid_snapshot(np.zeros((100, 100)), (100, 100))
    positions = {"tb1": (1.05, 1.05), "tb2": (1.05, 2.05)}
    states = {name: dict(mode="ACTIVE", energy=80., capacity=100.,
        charge_x=position[0], charge_y=position[1], charge_radius_m=.8,
        charge_target_fraction=.8, nominal_speed_mps=.18, idle_cost_per_sec=.02,
        move_cost_per_m=1., return_path_factor=2., return_safety_margin=5.,
        charge_duration_sec=6., return_recovery_wait_sec=30.)
        for name, position in positions.items()}
    return dict(raw_grid=raw, resolution=.1, origin=(0., 0.), robot_positions=positions,
        current_positions=positions.copy(), target=(4.05, 4.05),
        battery_states=states, observer_robot="tb1",
        return_maps={name: dict(data=raw, resolution=.1, origin=(0., 0.)) for name in positions})


@pytest.mark.parametrize("missing", [False, True])
def test_unknown_or_missing_local_map_never_drops_qualified_fused_candidates(missing):
    arguments = synthetic_arguments()
    if missing:
        del arguments["return_maps"]["tb2"]
    else:
        arguments["return_maps"]["tb2"]["data"] = c.immutable_grid_snapshot(
            np.full((100, 100), -1), (100, 100))
    answer = c.assign_rally_poses(**arguments)
    assert len(answer) == 2 and answer == original_assign(**arguments)


@pytest.mark.parametrize("change", ["map", "origin", "position", "home", "energy", "mode"])
def test_new_public_proposal_rebuilds_geometry_and_reprices_battery(change):
    arguments = synthetic_arguments()
    assert c.assign_rally_poses(**arguments) == original_assign(**arguments)
    if change == "map":
        raw = np.array(arguments["raw_grid"])
        raw[:, 25:35] = 100
        arguments["raw_grid"] = c.immutable_grid_snapshot(raw, raw.shape)
    elif change == "origin":
        arguments["origin"] = (-.4, -.4)
    elif change == "position":
        arguments["robot_positions"]["tb2"] = (2.05, 2.05)
    elif change == "home":
        arguments["battery_states"]["tb2"]["charge_x"] = 8.05
    elif change == "energy":
        arguments["battery_states"]["tb2"]["energy"] = 0.
    else:
        arguments["battery_states"]["tb2"]["mode"] = "RETURNING"
    assert c.assign_rally_poses(**arguments) == original_assign(**arguments)

